"""
Tests de la Etapa 3: métricas (gold -> KPIs, dependen de la fecha de corte).

Correr desde la raíz:  python -m pytest
Hay dos tipos de test:
  * con datos armados a mano (rápidos y con el resultado exacto esperado),
    para las reglas: nota a la fecha de corte, recuperatorio, condición,
    activo/inactivo;
  * sobre el gold real (fixture de conftest.py), con fechas de corte distintas,
    para controlar que los números cierran entre sí.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src import metricas as m
from src.config import FECHA_CORTE_DEFECTO, SIN_EVALUACIONES

ALG, PYE, AED = "Álgebra", "Probabilidad y Estadística", "Algoritmos y Estructuras de Datos"
FECHAS = ["2025-08-10", "2025-09-15", "2025-09-23", "2025-09-24", "2025-10-11", FECHA_CORTE_DEFECTO]
T = pd.Timestamp


# ---------------------------------------------------------------------------
# Datos armados a mano
# ---------------------------------------------------------------------------
def _instrumento(id_, asig, nombre, maximo, fecha, recupera=False):
    return {"id_instrumento": id_, "asignatura": asig, "instrumento": nombre, "orden": int(id_[-1]),
            "puntaje_maximo": maximo, "fecha_instrumento": T(fecha), "es_recuperatorio": recupera}


def _nota(alumno, inst, obtenida, recu=None, fecha_recu=None):
    """Fila de fact_calificacion. obtenida=None -> no rindió (vale 0)."""
    rindio = obtenida is not None
    sin_recu = obtenida if rindio else 0.0
    return {"id_alumno": alumno, "asignatura": inst["asignatura"], "id_instrumento": inst["id_instrumento"],
            "rindio": rindio, "nota_obtenida": obtenida if rindio else float("nan"),
            "observaciones": "aprobada" if rindio else None, "puntaje_maximo": inst["puntaje_maximo"],
            "puntos_sin_recuperatorio": sin_recu, "rindio_recuperatorio": recu is not None,
            "fecha_recuperatorio": T(fecha_recu) if fecha_recu else pd.NaT,
            "puntos": recu if recu is not None else sin_recu,
            "cuenta_en_final": not inst["es_recuperatorio"], "fecha_instrumento": inst["fecha_instrumento"]}


def _evento(i, alumno, asig, cuando, sesion):
    f = T(cuando)
    return {"id_evento": i, "id_alumno": alumno, "asignatura": asig, "fecha_hora": f, "fecha": f.normalize(),
            "hora": f.hour, "dia_semana": f.day_of_week, "id_sesion": sesion, "categoria": "Contenido",
            "accion": "Ver", "descripcion": "", "en_base": True}


@pytest.fixture
def chicos() -> m.Datos:
    """Álgebra: A1 (inscripto) y A2 (con nota, no inscripto). PyE: P1 con recuperatorio."""
    alg1 = _instrumento("ALG-1", ALG, "Autoevaluación", 10.0, "2025-09-01")
    alg2 = _instrumento("ALG-2", ALG, "Parcial", 25.0, "2025-10-01")
    pye1 = _instrumento("PYE-1", PYE, "Semanal", 100.0, "2025-09-10")
    pye2 = _instrumento("PYE-2", PYE, "Recuperatorio: Semanal", 100.0, "2025-09-20", recupera=True)
    instrumentos = pd.DataFrame([alg1, alg2, pye1, pye2])
    cal = pd.DataFrame([
        _nota("A1", alg1, 8.0), _nota("A1", alg2, None),          # no rindió el parcial -> 0
        _nota("A2", alg1, 10.0), _nota("A2", alg2, 25.0),
        _nota("P1", pye1, 90.0, recu=40.0, fecha_recu="2025-09-20"),  # el recuperatorio reemplaza (más bajo)
        _nota("P1", pye2, 40.0),
    ])
    matricula = pd.DataFrame({
        "asignatura": [ALG, ALG, PYE], "id_alumno": ["A1", "A2", "P1"], "en_base": True,
        "inscripto": [True, False, True], "en_matriculados": [True, False, True],
        "estado": ["Aceptada", None, "Aceptada"]})
    eventos = pd.DataFrame([
        _evento(1, "A1", ALG, "2025-09-01 10:00", 1), _evento(2, "A1", ALG, "2025-09-01 10:10", 1),
        _evento(3, "A1", ALG, "2025-09-20 21:00", 2),
        _evento(4, "A2", ALG, "2025-10-05 09:00", 3),
    ])  # P1 nunca entra
    sesiones = pd.DataFrame({"id_sesion": [1, 2, 3], "id_alumno": ["A1", "A1", "A2"], "asignatura": ALG,
                             "inicio": T("2025-09-01 10:00"), "duracion_min": [10.0, 0.0, 0.0], "en_base": True})
    sesiones.loc[1, "inicio"], sesiones.loc[2, "inicio"] = T("2025-09-20 21:00"), T("2025-10-05 09:00")
    participacion = pd.DataFrame({"asignatura": [ALG, ALG, PYE], "id_alumno": ["A1", "A2", "P1"], "en_base": True,
                                  **{c: [50, 80, 0] for c in m.COLUMNAS_REPORTE}})
    alumnos = pd.DataFrame({"id_alumno": ["A1", "A2", "P1"], "apellido": ["Núñez", "Pérez", "Gómez"],
                            "nombre": ["Ana", "Beto", "Ciro"]})
    alumnos["nombre_completo"] = alumnos["apellido"] + ", " + alumnos["nombre"]
    return m.Datos(alumnos=alumnos, instrumentos=instrumentos, interacciones=eventos, sesiones=sesiones,
                   calificaciones=cal, participacion=participacion, matricula=matricula)


def _fila(df, alumno):
    return df.set_index("id_alumno").loc[alumno]


def test_nota_usa_solo_instrumentos_disponibles(chicos):
    # 15/09: solo la autoevaluación (10 pts). A1 = 8/10 × 120 = 96 -> Promociona
    a1 = _fila(m.nota_final(chicos, "2025-09-15", ALG), "A1")
    assert (a1["puntos"], a1["puntos_posibles"], a1["nota_final"], a1["condicion"]) == (8, 10, 96, "Promociona")
    # 01/10 (inclusive): entra el parcial no rendido. 8/35 × 120 = 27,43 -> Libre
    a1 = _fila(m.nota_final(chicos, "2025-10-01", ALG), "A1")
    assert a1["nota_final"] == pytest.approx(27.43) and a1["condicion"] == "Libre"
    assert a1["nota_pct"] == pytest.approx(22.86)
    assert _fila(m.nota_final(chicos, "2025-10-01", ALG), "A2")["nota_final"] == 120


def test_sin_instrumentos_disponibles(chicos):
    n = m.nota_final(chicos, "2025-08-01")
    assert len(n) == 3 and (n["condicion"] == SIN_EVALUACIONES).all() and n["nota_final"].isna().all()


def test_recuperatorio_se_aplica_desde_su_fecha(chicos):
    """D34: antes de la fecha del recuperatorio vale la nota original."""
    assert _fila(m.nota_final(chicos, "2025-09-19", PYE), "P1")["nota_final"] == 90
    assert _fila(m.nota_final(chicos, "2025-09-20", PYE), "P1")["nota_final"] == 40
    # el recuperatorio no suma un instrumento al promedio
    assert _fila(m.nota_final(chicos, "2025-09-20", PYE), "P1")["instrumentos"] == 1


def test_cortes_de_condicion():
    notas = pd.Series([59.99, 60, 84.99, 85, 89.99, 90, None])
    materias = pd.Series([PYE, PYE, PYE, PYE, AED, AED, ALG])
    assert m.condicion(notas, materias).tolist() == \
        ["Libre", "Regular", "Regular", "Promociona", "Regular", "Promociona", SIN_EVALUACIONES]


def test_activo_inactivo_y_sin_actividad(chicos):
    a = m.actividad_alumnos(chicos, "2025-09-25", None, umbral=7).set_index("id_alumno")
    assert a.loc["A1", "estado_actividad"] == m.ACTIVO and a.loc["A1", "dias_sin_actividad"] == 5
    assert a.loc["A2", "estado_actividad"] == m.SIN_ACTIVIDAD   # su evento es posterior al corte
    assert a.loc["P1", "estado_actividad"] == m.SIN_ACTIVIDAD
    assert (a.loc["A1", "eventos"], a.loc["A1", "sesiones"], a.loc["A1", "minutos"]) == (3, 2, 10)
    # con umbral más corto, A1 pasa a inactivo
    a = m.actividad_alumnos(chicos, "2025-09-25", None, umbral=3).set_index("id_alumno")
    assert a.loc["A1", "estado_actividad"] == m.INACTIVO


def test_fecha_de_corte_incluye_todo_el_dia(chicos):
    a = m.actividad_alumnos(chicos, "2025-09-20", ALG).set_index("id_alumno")
    assert a.loc["A1", "eventos"] == 3 and a.loc["A1", "dias_sin_actividad"] == 0


def test_evolucion_completa_semanas_sin_actividad(chicos):
    e = m.evolucion_actividad(chicos, "2025-10-06", ALG, "W")
    assert e["periodo"].is_monotonic_increasing and e["periodo"].dt.day_of_week.eq(0).all()
    assert len(e) == 6 and e["eventos"].sum() == 4 and (e["eventos"] == 0).sum() == 3


def test_alertas(chicos):
    al = m.alertas(chicos, "2025-10-10", umbral=7)
    por_alumno = al.groupby("id_alumno")["tipo"].apply(set).to_dict()
    assert por_alumno["A2"] == {"no_inscripto"}
    assert por_alumno["P1"] == {"libre"}                     # rindió (40 con el recuperatorio) aunque no entra
    assert por_alumno["A1"] == {"inactivo", "libre"}
    # antes de su primer instrumento, P1 no tiene eventos ni notas: solo "sin actividad", no se repite como Libre
    antes = m.alertas(chicos, "2025-09-05", PYE)
    assert antes["tipo"].tolist() == ["sin_actividad"]


def test_buscar_sin_tildes(chicos):
    assert m.buscar_alumnos(chicos, "nunez")["id_alumno"].tolist() == ["A1"]
    assert m.buscar_alumnos(chicos, "a2")["id_alumno"].tolist() == ["A2"]
    assert m.buscar_alumnos(chicos)["id_alumno"].tolist() == ["P1", "A1", "A2"]  # orden alfabético


def test_materia_desconocida(chicos):
    with pytest.raises(ValueError):
        m.nota_final(chicos, asignatura="Física")


# ---------------------------------------------------------------------------
# Sobre el gold real, con fechas de corte distintas
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def d(carpeta_pipeline) -> m.Datos:
    return m.cargar(carpeta_pipeline / "gold")


@pytest.mark.parametrize("fecha", FECHAS)
def test_una_fila_por_alumno_de_la_base(d, fecha):
    base = d.matricula[d.matricula["en_base"]]
    for tabla in [m.nota_final(d, fecha), m.tabla_alumnos(d, fecha)]:
        assert len(tabla) == len(base)
        assert not tabla.duplicated(["asignatura", "id_alumno"]).any()


@pytest.mark.parametrize("fecha", FECHAS)
def test_notas_en_rango_y_condiciones_suman_100(d, fecha):
    n = m.nota_final(d, fecha).dropna(subset=["nota_final"])
    assert n["nota_final"].between(0, n["escala"]).all()
    dist = m.distribucion_condicion(d, fecha)
    assert dist.groupby("asignatura")["pct"].sum().round().eq(100).all()


def test_a_la_ultima_fecha_coincide_con_gold(d):
    """Con todos los instrumentos disponibles, la nota es Σ puntos / Σ máximos de fact_calificacion."""
    c = d.calificaciones[d.calificaciones["cuenta_en_final"]]
    esperado = c.groupby(["asignatura", "id_alumno"]).apply(
        lambda g: g["puntos"].sum() / g["puntaje_maximo"].sum() * 100, include_groups=False).round(2)
    n = m.nota_final(d, FECHA_CORTE_DEFECTO).set_index(["asignatura", "id_alumno"])["nota_pct"]
    pd.testing.assert_series_equal(n.sort_index(), esperado.sort_index(), check_names=False, atol=0.011)


def test_recuperatorio_real_alu_1105(d):
    """ALU_1105: 93,75 en la Semanal Nº1 y 0 en el recuperatorio (24/09)."""
    antes = _fila(m.notas_instrumento(d, "2025-09-23", PYE).query("id_instrumento == 'PYE-05'"), "ALU_1105")
    despues = _fila(m.notas_instrumento(d, "2025-09-24", PYE).query("id_instrumento == 'PYE-05'"), "ALU_1105")
    assert (antes["puntos_corte"], despues["puntos_corte"]) == (93.75, 0)


def test_la_actividad_acumulada_no_baja_con_la_fecha(d):
    anteriores = None
    for fecha in FECHAS:
        a = m.actividad_alumnos(d, fecha).set_index(["asignatura", "id_alumno"])[["eventos", "sesiones"]]
        if anteriores is not None:
            assert (a >= anteriores).all().all()
        anteriores = a


def test_los_eventos_cierran_entre_funciones(d):
    total = d.interacciones["en_base"].sum()
    assert m.actividad_alumnos(d)["eventos"].sum() == total
    assert m.mapa_calor(d)["eventos"].sum() == total and len(m.mapa_calor(d)) == 7 * 24
    assert m.interacciones_por_categoria(d)["eventos"].sum() == total
    assert m.evolucion_actividad(d, frecuencia="M")["eventos"].sum() == total
    assert m.evolucion_actividad(d, frecuencia="D")["eventos"].sum() == total


def test_rango_de_fechas(d):
    rango = m.interacciones_por_categoria(d, "2025-09-30", desde="2025-09-01")["eventos"].sum()
    ev = d.interacciones
    assert rango == (ev["en_base"] & ev["fecha"].between("2025-09-01", "2025-09-30")).sum()


def test_promedio_por_instrumento_solo_quienes_rindieron(d):
    p = m.promedio_por_instrumento(d).set_index("id_instrumento")
    assert p.loc["AED-05", "rindieron"] == 24
    c = d.calificaciones[(d.calificaciones["id_instrumento"] == "AED-05") & d.calificaciones["rindio"]]
    assert p.loc["AED-05", "promedio_pct"] == pytest.approx(c["nota_obtenida"].mean(), abs=0.01)
    # a una fecha anterior, los instrumentos futuros no aparecen
    assert set(m.promedio_por_instrumento(d, "2025-09-15", AED)["id_instrumento"]) == {"AED-01", "AED-02"}


def test_matricula_y_alertas(d):
    r = m.resumen_matricula(d).set_index("asignatura")
    assert r["no_inscriptos_cursando"].to_dict() == {ALG: 54, PYE: 52, AED: 39}
    assert r["inscriptos_sin_notas"].to_dict() == {ALG: 21, PYE: 22, AED: 58}
    assert (r["activos"] <= r["con_actividad"]).all() and (r["con_actividad"] <= r["base"]).all()
    al = m.alertas(d)
    assert al[al["tipo"] == "no_inscripto"].groupby("asignatura").size().to_dict() == \
        r["no_inscriptos_cursando"].to_dict()


def test_correlaciones_validas(d):
    c = m.correlaciones(d)
    assert len(c) == 3 * len(m.VARIABLES_CRUCE)
    assert c["rho"].between(-1, 1).all() and (c["n"] > 100).all()


def test_correlaciones_solo_rindieron(d):
    todas = m.correlaciones(d)
    solo = m.correlaciones(d, solo_rindieron=True)
    t = m.tabla_alumnos(d)
    esperado = t[t["rendidos"] > 0].groupby("asignatura").size()
    n = solo.groupby("asignatura")["n"].max()
    assert n.to_dict() == esperado.to_dict()
    assert (solo["n"] <= todas["n"]).all()


@pytest.mark.parametrize("fecha", FECHAS)
def test_nota_por_nivel_actividad(d, fecha):
    niveles = m.nota_por_nivel_actividad(d, fecha)
    base = m.base(d).groupby("asignatura").size()
    # cinco grupos parejos por materia, que suman toda la base y van de menos a más actividad
    assert niveles.groupby("asignatura")["alumnos"].sum().to_dict() == base.to_dict()
    assert (niveles.groupby("asignatura").size() == 5).all()
    assert (niveles.groupby("asignatura")["alumnos"].agg(lambda s: s.max() - s.min()) <= 1).all()
    for _, g in niveles.groupby("asignatura"):
        assert list(g["nivel"]) == m.NIVELES_ACTIVIDAD
        assert g["mediana_actividad"].is_monotonic_increasing
    pcts = niveles.filter(like="pct_").sum(axis=1)
    assert pcts.round(1).eq(100).all()


def test_nota_por_nivel_actividad_sube_con_la_actividad(d):
    # hallazgo de D55: el grupo que más entra tiene mejor nota que el que menos
    niveles = m.nota_por_nivel_actividad(d, variable="avance", solo_rindieron=True)
    for _, g in niveles.groupby("asignatura"):
        assert g["nota_pct"].iloc[-1] > g["nota_pct"].iloc[0]


def test_ficha_individual(d):
    primero = m.buscar_alumnos(d)["id_alumno"].iloc[0]
    f = m.ficha_alumno(d, primero)
    assert len(f["materias"]) >= 1 and (f["materias"]["id_alumno"] == primero).all()
    assert (f["instrumentos"]["id_alumno"] == primero).all()
    with pytest.raises(KeyError):
        m.ficha_alumno(d, "ALU_9999")
