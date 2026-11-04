"""
Tests de la Etapa 2: modelo (silver -> gold).

Correr desde la raíz:  python -m pytest
El pipeline se corre una sola vez (conftest.py) sobre data/raw/ y escribe en una carpeta
temporal: data/ no se toca.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.config import ESQUEMA
from src.modelo import clave_instrumento, dim_instrumento, sesionizar

CATEGORIAS = {"Navegación", "Contenido", "Evaluación", "Comunicación", "Notas", "Agenda"}
# La fixture `capas` (pipeline completo en una carpeta temporal) está en conftest.py.


# ---------------------------------------------------------------------------
# Granularidad: una fila por lo que corresponde
# ---------------------------------------------------------------------------
def test_un_alumno_por_materia(capas):
    assert not capas("gold", "fact_matricula").duplicated(["asignatura", "id_alumno"]).any()
    assert not capas("gold", "fact_participacion").duplicated(["asignatura", "id_alumno"]).any()
    assert not capas("gold", "fact_calificacion").duplicated(["id_alumno", "id_instrumento"]).any()
    assert capas("gold", "dim_alumno")["id_alumno"].is_unique


def test_todos_los_alumnos_estan_en_la_dimension(capas):
    ids = set(capas("gold", "dim_alumno")["id_alumno"])
    for tabla in ["fact_matricula", "fact_calificacion", "fact_participacion", "fact_interaccion"]:
        assert set(capas("gold", tabla)["id_alumno"]) <= ids, tabla


# ---------------------------------------------------------------------------
# Calificaciones
# ---------------------------------------------------------------------------
def test_notas_entre_cero_y_el_maximo(capas):
    c = capas("gold", "fact_calificacion")
    assert c["puntos"].between(0, c["puntaje_maximo"]).all()
    assert c["puntos_sin_recuperatorio"].between(0, c["puntaje_maximo"]).all()
    assert c["nota_pct"].between(0, 100).all()


def test_no_rendido_vale_cero_y_grilla_completa(capas):
    """D15: cada alumno de la base tiene una fila por instrumento de su materia."""
    c, m, i = capas("gold", "fact_calificacion"), capas("gold", "fact_matricula"), capas("gold", "dim_instrumento")
    esperadas = (m[m["en_base"]].groupby("asignatura").size() * i.groupby("asignatura").size()).sum()
    assert len(c) == esperadas
    assert (c.loc[~c["rindio"], "puntos_sin_recuperatorio"] == 0).all()


def test_recuperatorio_pye_reemplaza(capas):
    """D20: si rindió el recuperatorio vale esa nota, aunque sea más baja o 0."""
    c = capas("gold", "fact_calificacion")
    recu = c[c["rindio_recuperatorio"]]
    assert len(recu) == 21 and set(recu["asignatura"]) == {"Probabilidad y Estadística"}
    assert (recu["puntos"] == recu["nota_recuperatorio"]).all()
    alu = c[(c["id_alumno"] == "ALU_1105") & c["rindio_recuperatorio"]].iloc[0]
    assert (alu["puntos_sin_recuperatorio"], alu["puntos"]) == (93.75, 0)
    # el recuperatorio no cuenta como un instrumento más
    assert not c.loc[c["es_recuperatorio"], "cuenta_en_final"].any()


def test_recuperatorio_algebra_suma():
    """D21: en Álgebra el recuperatorio es un instrumento más que cuenta en el total."""
    assert ESQUEMA["Álgebra"]["recuperatorio"] == "suma"
    cal = pd.DataFrame({
        "asignatura": ["Álgebra"] * 2, "instrumento": ["1° Parcial", "Recuperatorio"],
        "Usuario": ["ALU_0001"] * 2, "Nota máxima": [25.0, 20.0],
        "fecha_exportacion": pd.to_datetime(["2025-10-24"] * 2)})
    traz = pd.DataFrame(columns=["Perfil", "Acción", "Descripción", "Fecha", "asignatura"])
    traz["Fecha"] = pd.to_datetime(traz["Fecha"])
    inst = dim_instrumento(cal, traz).set_index("instrumento")
    assert inst.loc["Recuperatorio", "cuenta_en_final"] and pd.isna(inst.loc["Recuperatorio", "recupera_a"])


def test_clave_instrumento_une_nombres_de_distintas_fuentes():
    assert clave_instrumento("&#128640;Evaluación Semanal Nº1") == clave_instrumento("🚀Evaluación Semanal Nº1")
    assert clave_instrumento("🚀Recuperatorio: Evaluación Semanal Nº1", sin_recuperatorio=True) == \
        clave_instrumento("🚀Evaluación Semanal Nº1")


def test_todos_los_instrumentos_tienen_fecha(capas):
    assert capas("gold", "dim_instrumento")["fecha_inferida"].all()


# ---------------------------------------------------------------------------
# Matrícula y base de alumnos (D11-D13)
# ---------------------------------------------------------------------------
def test_base_de_alumnos(capas):
    m = capas("gold", "fact_matricula")
    sin_nota = m[m["inscripto"] & ~m["tiene_nota"]].groupby("asignatura").size().to_dict()
    assert sin_nota == {"Algoritmos y Estructuras de Datos": 58, "Probabilidad y Estadística": 22, "Álgebra": 21}
    fuera = m[m["tiene_nota"] & ~m["en_matriculados"]].groupby("asignatura").size().to_dict()
    assert fuera == {"Algoritmos y Estructuras de Datos": 39, "Probabilidad y Estadística": 52, "Álgebra": 52}
    assert (m["en_base"] == (m["inscripto"] | m["tiene_nota"])).all()


def test_ultimo_estado_de_matricula(capas):
    m, s = capas("gold", "fact_matricula"), capas("silver", "matriculados")
    assert m["en_matriculados"].sum() == s.groupby(["asignatura", "Identificación"]).ngroups
    assert m.loc[m["movimientos"] > 1].shape[0] == 11


# ---------------------------------------------------------------------------
# Conteos que cierran entre capas
# ---------------------------------------------------------------------------
def test_conteos_cierran_entre_silver_y_gold(capas):
    assert len(capas("gold", "fact_interaccion")) + len(capas("gold", "otros_perfiles_interaccion")) == \
        len(capas("silver", "trazabilidad"))
    assert len(capas("gold", "fact_participacion")) + len(capas("gold", "otros_perfiles_participacion")) == \
        len(capas("silver", "participacion"))
    # cada nota de silver está en gold (los alumnos con nota siempre están en la base)
    c = capas("gold", "fact_calificacion")
    assert c["rindio"].sum() == len(capas("silver", "calificaciones"))
    assert c.loc[c["rindio"], "nota_obtenida"].sum() == pytest.approx(capas("silver", "calificaciones")["Nota obtenida"].sum())


def test_sesiones_cierran_con_interacciones(capas):
    i, s = capas("gold", "fact_interaccion"), capas("gold", "fact_sesion")
    assert s["eventos"].sum() == len(i)
    assert i["id_sesion"].nunique() == len(s)
    assert (s["duracion_min"] >= 0).all()
    # una sesión es de un solo alumno y una sola materia
    assert (i.groupby("id_sesion")[["id_alumno", "asignatura"]].nunique() == 1).all().all()


def test_acciones_categorizadas(capas):
    i = capas("gold", "fact_interaccion")
    assert i["id_accion"].notna().all()
    assert set(capas("gold", "dim_accion")["categoria"]) == CATEGORIAS


def test_calendario_cubre_todas_las_fechas(capas):
    fechas = set(capas("gold", "dim_fecha")["fecha"])
    assert set(capas("gold", "fact_interaccion")["fecha"]) <= fechas
    assert set(capas("gold", "dim_instrumento")["fecha_instrumento"].dropna()) <= fechas


# ---------------------------------------------------------------------------
# Sesiones (D25), con datos armados a mano
# ---------------------------------------------------------------------------
def test_sesion_se_corta_a_los_30_minutos():
    ev = pd.DataFrame({
        "id_alumno": ["A"] * 4 + ["A", "B"],
        "asignatura": ["X"] * 4 + ["Y", "Y"],
        "fecha_hora": pd.to_datetime(["2025-09-01 10:00", "2025-09-01 10:29", "2025-09-01 10:59",
                                      "2025-09-01 11:31",  # 32 min después: sesión nueva
                                      "2025-09-01 11:32",  # otra materia: sesión nueva
                                      "2025-09-01 11:33"]),  # otro alumno: sesión nueva
    })
    assert sesionizar(ev).tolist() == [1, 1, 1, 2, 3, 4]
