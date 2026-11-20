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
from src.config import DIAS_DESCONECTADO, DIAS_REGRESO, FECHA_CORTE_DEFECTO, SIN_EVALUACIONES

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


def test_alertas_por_alumno_y_prioridad(chicos):
    p = m.alertas_por_alumno(chicos, "2025-10-10", umbral=7).set_index("id_alumno")
    assert p.loc["A2", "prioridad"] == "Administrativa"    # solo cursa sin inscripción
    assert p.loc["P1", "prioridad"] == "Media"             # una sola alerta académica (Libre)
    assert p.loc["A1", "prioridad"] == "Alta"              # inactivo + Libre
    assert p.loc["A1", "cantidad"] == 2 and p.index[0] == "A1"  # la más urgente primero
    assert m.alertas_por_alumno(chicos, "2025-09-05", PYE)["prioridad"].tolist() == ["Alta"]  # sin actividad


def test_buscar_sin_tildes(chicos):
    assert m.buscar_alumnos(chicos, "nunez")["id_alumno"].tolist() == ["A1"]
    assert m.buscar_alumnos(chicos, "a2")["id_alumno"].tolist() == ["A2"]
    assert m.buscar_alumnos(chicos)["id_alumno"].tolist() == ["P1", "A1", "A2"]  # orden alfabético
    assert m.buscar_alumnos(chicos, asignatura=PYE)["id_alumno"].tolist() == ["P1"]
    assert m.buscar_alumnos(chicos, "a", asignatura=ALG)["id_alumno"].tolist() == ["A1", "A2"]


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


@pytest.mark.parametrize("frecuencia", ["D", "W", "M"])
def test_evolucion_interacciones_cierra_con_el_total(d, frecuencia):
    """Dashboard de Trazabilidad (D62): por materia y por tipo suman lo mismo."""
    total = (d.interacciones["en_base"] & (d.interacciones["fecha"] <= T("2025-09-30"))).sum()
    por_materia = m.evolucion_interacciones(d, "2025-09-30", frecuencia=frecuencia)
    por_tipo = m.evolucion_interacciones(d, "2025-09-30", frecuencia=frecuencia, por="categoria")
    assert por_materia["eventos"].sum() == por_tipo["eventos"].sum() == total
    assert set(por_tipo["categoria"]) == set(m.categorias_presentes(d))
    pct = por_tipo.groupby("periodo")["pct_periodo"].sum()
    assert ((pct - 100).abs() < 0.1).all()


def test_interacciones_por_accion(d):
    a = m.interacciones_por_accion(d, asignatura=ALG)
    assert a["eventos"].sum() == m.interacciones_por_categoria(d, asignatura=ALG)["eventos"].sum()
    assert a["pct"].sum() == pytest.approx(100, abs=0.1)
    assert not a.duplicated(["categoria", "seccion", "accion"]).any()
    assert (a["pct_alumnos"] <= 100).all()


def test_actividad_alrededor_evaluaciones(d):
    x = m.actividad_alrededor_evaluaciones(d, "2025-09-30", dias_antes=3, dias_despues=2)
    assert x["dia_relativo"].between(-3, 2).all()
    assert x["fecha"].max() <= T("2025-09-30")
    assert "PYE-06" not in set(x["id_instrumento"])  # el recuperatorio no se cuenta
    assert set(x["id_instrumento"]) <= set(m.fechas_evaluaciones(d, "2025-09-30")["id_instrumento"])
    fila = x[(x["id_instrumento"] == "ALG-01") & (x["dia_relativo"] == 0)].iloc[0]
    ev = d.interacciones
    assert fila["eventos"] == (ev["en_base"] & (ev["asignatura"] == ALG) & (ev["fecha"] == fila["fecha"])).sum()
    assert (x["eventos_evaluacion"] <= x["eventos"]).all()


def test_promedio_por_instrumento_solo_quienes_rindieron(d):
    p = m.promedio_por_instrumento(d).set_index("id_instrumento")
    assert p.loc["AED-05", "rindieron"] == 24
    c = d.calificaciones[(d.calificaciones["id_instrumento"] == "AED-05") & d.calificaciones["rindio"]]
    assert p.loc["AED-05", "promedio_pct"] == pytest.approx(c["nota_obtenida"].mean(), abs=0.01)
    # a una fecha anterior, los instrumentos futuros no aparecen
    assert set(m.promedio_por_instrumento(d, "2025-09-15", AED)["id_instrumento"]) == {"AED-01", "AED-02"}


@pytest.mark.parametrize("fecha", FECHAS)
def test_notas_rendidas_cierran_con_el_promedio(d, fecha):
    r = m.notas_rendidas(d, fecha)
    assert r["nota_pct_instrumento"].between(0, 100).all()
    p = m.promedio_por_instrumento(d, fecha).set_index("id_instrumento")
    if len(r):
        g = r.groupby("id_instrumento")["nota_pct_instrumento"]
        assert (g.size() == p.loc[g.size().index, "rindieron"]).all()
        assert (g.mean() - p.loc[g.size().index, "promedio_pct"]).abs().max() < 0.01


def test_evolucion_condicion(d):
    e = m.evolucion_condicion(d, asignatura=PYE)
    # una fecha por evaluación tomada (el recuperatorio cuenta como fecha propia)
    assert e["fecha"].nunique() == len(m.fechas_evaluaciones(d, asignatura=PYE)["fecha_instrumento"].unique())
    assert e.groupby("fecha")["pct"].sum().round().eq(100).all()
    # el último punto es la distribución a la fecha de la última evaluación
    ultima = e[e["fecha"] == e["fecha"].max()].set_index("condicion")["alumnos"]
    hoy = m.distribucion_condicion(d, asignatura=PYE).set_index("condicion")["alumnos"]
    assert ultima.reindex(hoy.index).eq(hoy).all()
    assert m.evolucion_condicion(d, "2025-08-01").empty


def test_matricula_y_alertas(d):
    r = m.resumen_matricula(d).set_index("asignatura")
    assert r["no_inscriptos_cursando"].to_dict() == {ALG: 54, PYE: 52, AED: 39}
    assert r["inscriptos_sin_notas"].to_dict() == {ALG: 21, PYE: 22, AED: 58}
    assert (r["activos"] <= r["con_actividad"]).all() and (r["con_actividad"] <= r["base"]).all()
    al = m.alertas(d)
    assert al[al["tipo"] == "no_inscripto"].groupby("asignatura").size().to_dict() == \
        r["no_inscriptos_cursando"].to_dict()
    p = m.alertas_por_alumno(d)
    assert not p.duplicated(["asignatura", "id_alumno"]).any()
    assert len(p) == len(al.drop_duplicates(["asignatura", "id_alumno"]))
    assert p["cantidad"].sum() == len(al)
    # quien entra pero no rinde (y por eso es Libre) no pasa a Alta solo por eso
    solo = p[p["tipos"].map(lambda ts: set(ts) == {"sin_notas", "libre"})]
    assert (solo["prioridad"] == "Media").all()


@pytest.mark.parametrize("fecha", ["2025-08-10", FECHA_CORTE_DEFECTO])
def test_evolucion_matricula(d, fecha):
    e = m.evolucion_matricula(d, fecha)
    assert e["fecha"].max() == pd.Timestamp(fecha)
    assert (e.groupby(["asignatura", "serie"])["alumnos"].diff().dropna() >= 0).all()  # acumulado
    if fecha == FECHA_CORTE_DEFECTO:
        final = e[e["fecha"] == e["fecha"].max()].set_index(["asignatura", "serie"])["alumnos"]
        r = m.resumen_matricula(d).set_index("asignatura")
        assert final.xs("Inscriptos", level="serie").to_dict() == r["inscriptos"].to_dict()
        assert final.xs("Ya entraron al aula", level="serie").to_dict() == r["con_actividad"].to_dict()
    assert m.evolucion_matricula(d, "2025-07-01").empty


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


@pytest.mark.parametrize("fecha", ["2025-09-15", FECHA_CORTE_DEFECTO])
def test_casos_en_riesgo(d, fecha):
    """D85: casos alumno–materia vs. alumnos distintos, y la comparación contra 7 días antes."""
    c = m.casos_en_riesgo(d, fecha).set_index("asignatura")
    q = m.cuadrante_riesgo(d, fecha)
    r = q[q["en_riesgo"]]
    total = c.loc[m.TODAS_LAS_MATERIAS]
    assert total["casos"] == len(r) == c.drop(m.TODAS_LAS_MATERIAS)["casos"].sum()
    assert total["alumnos"] == r["id_alumno"].nunique() <= total["casos"]
    assert total["sin_rendir"] == (r["rendidos"] == 0).sum()
    por_materia = c.drop(m.TODAS_LAS_MATERIAS)
    assert (por_materia["alumnos"] == por_materia["casos"]).all()   # en una materia, un caso = un alumno
    antes = m.cuadrante_riesgo(d, T(fecha) - pd.Timedelta(days=7))
    assert total["casos_antes"] == antes["en_riesgo"].sum()
    una = m.casos_en_riesgo(d, fecha, asignatura=ALG).set_index("asignatura")
    assert una.loc[ALG, "casos"] == una.loc[m.TODAS_LAS_MATERIAS, "casos"] == c.loc[ALG, "casos"]


def test_brecha_libres(d):
    b = m.brecha_libres(d).set_index("asignatura")
    n = m.nota_por_nivel_actividad(d)
    for materia, g in n.sort_values("orden").groupby("asignatura"):
        assert b.loc[materia, "libre_menos"] == g["pct_libre"].iloc[0]
        assert b.loc[materia, "libre_mas"] == g["pct_libre"].iloc[-1]
        assert b.loc[materia, "brecha_pp"] == pytest.approx(g["pct_libre"].iloc[0] - g["pct_libre"].iloc[-1], abs=0.01)
    assert (b["brecha_pp"] > 0).all()   # el quinto que menos entra tiene más libres en las tres materias
    assert m.brecha_libres(d, "2025-07-01").empty or m.brecha_libres(d, "2025-07-01")["libre_menos"].eq(0).all()


def test_activos_libres(d):
    a = m.activos_libres(d).set_index("asignatura")
    q = m.cuadrante_riesgo(d)
    conteo = q.groupby(["asignatura", "cuadrante"]).size()
    for materia in a.index:
        libres = conteo.get((materia, "Activo con nota baja"), 0)
        sanos = conteo.get((materia, "Activo con buena nota"), 0)
        assert a.loc[materia, "libres"] == libres
        assert a.loc[materia, "sobre_mediana"] == libres + sanos
    assert a["pct"].between(0, 100).all()


def test_ficha_individual(d):
    primero = m.buscar_alumnos(d)["id_alumno"].iloc[0]
    f = m.ficha_alumno(d, primero)
    assert len(f["materias"]) >= 1 and (f["materias"]["id_alumno"] == primero).all()
    assert (f["instrumentos"]["id_alumno"] == primero).all()
    with pytest.raises(KeyError):
        m.ficha_alumno(d, "ALU_9999")


# ---------------------------------------------------------------------------
# Dashboard de Participación (D53)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("desde", [None, "2025-10-01"])
def test_participacion_alumnos_respeta_el_rango(d, desde):
    p = m.participacion_alumnos(d, desde=desde)
    assert len(p) == len(d.matricula[d.matricula["en_base"]])
    assert not p.duplicated(["asignatura", "id_alumno"]).any()
    ev = d.interacciones[d.interacciones["en_base"] & (d.interacciones["fecha"] <= FECHA_CORTE_DEFECTO)]
    if desde:
        ev = ev[ev["fecha"] >= desde]
    assert p["eventos"].sum() == len(ev)
    assert p["avance"].between(0, 100).all()


def test_evolucion_participacion_relativa_a_la_base(d):
    e = m.evolucion_participacion(d, frecuencia="W")
    n = m.base(d).groupby("asignatura").size()
    fila = e.iloc[3]
    assert fila["pct_base_activa"] == pytest.approx(fila["alumnos_activos"] / n[fila["asignatura"]] * 100, abs=0.01)
    assert e["pct_base_activa"].between(0, 100).all()
    assert e["eventos"].sum() == d.interacciones["en_base"].sum()


def test_uso_herramientas(d):
    h = m.uso_herramientas(d)
    assert len(h) == 3 * len(m.HERRAMIENTAS)
    assert h["pct_alumnos"].between(0, 100).all() and (h["alumnos"] <= h["base_reporte"]).all()
    foros = h[h["herramienta"] == "Foros"].set_index("asignatura")
    assert foros.loc[ALG, "recursos"] == 5 and foros.loc[AED, "alumnos"] == 0


def test_concordancia_tiempo(d):
    c = m.concordancia_tiempo(d)
    assert len(c) == 3 and (c["rho"] > 0.9).all()


@pytest.mark.parametrize("desde", [None, "2025-09-27"])
def test_ritmo_semanal_cierra_con_las_sesiones(d, desde):
    r = m.ritmo_semanal(d, desde=desde).set_index("asignatura")
    p = m.participacion_alumnos(d, desde=desde)
    inicio = T(desde) if desde else d.interacciones["fecha"].min()
    semanas = ((T(FECHA_CORTE_DEFECTO) - inicio).days + 1) / 7
    todas = r.loc[m.TODAS_LAS_MATERIAS]
    assert todas["alumnos"] == len(p)
    assert todas["sesiones_semana"] == pytest.approx(p["sesiones"].sum() / len(p) / semanas)
    assert todas["minutos_semana_mediana"] == pytest.approx((p["minutos"] / semanas).median())
    assert (r["semanas_activas_mediana"] <= r["semanas_periodo"]).all()
    assert r.loc[ALG, "alumnos"] == (p["asignatura"] == ALG).sum()


def test_ritmo_semanal_respeta_la_materia(d):
    alg = m.ritmo_semanal(d, asignatura=ALG).set_index("asignatura")
    todas = m.ritmo_semanal(d).set_index("asignatura")
    assert list(alg.index) == [ALG, m.TODAS_LAS_MATERIAS]
    assert alg.loc[m.TODAS_LAS_MATERIAS, "sesiones_semana"] == pytest.approx(todas.loc[ALG, "sesiones_semana"])


@pytest.mark.parametrize("fecha", ["2025-09-15", FECHA_CORTE_DEFECTO])
def test_retencion_semanal(d, fecha):
    r = m.retencion_semanal(d, fecha).set_index("asignatura")
    corte = T(fecha)
    ev = d.interacciones[d.interacciones["en_base"] & (d.interacciones["fecha"] <= corte)
                         & (d.interacciones["fecha"] >= corte - pd.Timedelta(days=13))]
    esta = set(map(tuple, ev.loc[ev["fecha"] >= corte - pd.Timedelta(days=6), ["asignatura", "id_alumno"]].values))
    antes = set(map(tuple, ev.loc[ev["fecha"] < corte - pd.Timedelta(days=6), ["asignatura", "id_alumno"]].values))
    todas = r.loc[m.TODAS_LAS_MATERIAS]
    assert todas["activos_semana_anterior"] == len(antes) and todas["volvieron"] == len(antes & esta)
    assert r["retencion"].between(0, 100).all()
    assert r.drop(m.TODAS_LAS_MATERIAS)["volvieron"].sum() == todas["volvieron"]


def test_acceso_semanal_es_el_promedio_ponderado(d):
    s = m.acceso_semanal(d)
    e = m.evolucion_participacion(d, frecuencia="W")
    n = m.base(d).groupby("asignatura").size()
    fila = s.iloc[2]
    semana = e[e["periodo"] == fila["periodo"]]
    assert fila["pct"] == pytest.approx(semana["alumnos_activos"].sum() / n.sum() * 100)
    assert s["completa"].iloc[:-1].all() and not s["completa"].iloc[-1]   # el 24/10/2025 es viernes


def test_semanas_sin_actividad(d):
    nunca = m.actividad_alumnos(d).query("eventos == 0").iloc[0]
    r = m.semanas_sin_actividad(d, nunca["id_alumno"], nunca["asignatura"])
    assert r == {"semanas": 3, "sin_actividad": 3}
    assert m.semanas_sin_actividad(d, nunca["id_alumno"], nunca["asignatura"], "2025-08-12")["semanas"] == 1


# ---------------------------------------------------------------------------
# Tramos de actividad y movimientos de la semana (D54)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("umbral", [3, 7, 30])
def test_tramos_parten_a_los_inactivos(d, umbral):
    a = m.actividad_alumnos(d, umbral=umbral)
    assert set(a["tramo_actividad"]) <= set(m.TRAMOS_ACTIVIDAD)
    # activos y sin actividad son los mismos; los inactivos se reparten en dos tramos
    assert (a["tramo_actividad"] == m.ACTIVO).equals(a["estado_actividad"] == m.ACTIVO)
    inactivos = a[a["estado_actividad"] == m.INACTIVO]
    assert inactivos["tramo_actividad"].isin([m.ENFRIANDOSE, m.DESCONECTADO]).all()
    lim = max(DIAS_DESCONECTADO, umbral)
    assert (inactivos["tramo_actividad"] == m.DESCONECTADO).tolist() == (inactivos["dias_sin_actividad"] > lim).tolist()


def test_movimientos_de_la_semana(d):
    corte = T(FECHA_CORTE_DEFECTO)
    mov = m.movimientos_semana(d, corte)
    ahora = m.actividad_alumnos(d, corte).set_index(["asignatura", "id_alumno"])
    antes = m.actividad_alumnos(d, corte - pd.Timedelta(days=7)).set_index(["asignatura", "id_alumno"])
    for nombre, g in mov.groupby("movimiento", observed=True):
        claves = list(zip(g["asignatura"], g["id_alumno"]))
        if nombre == m.CRUZO_UMBRAL:
            assert antes.loc[claves, "activo"].all() and not ahora.loc[claves, "activo"].any()
        elif nombre == m.VOLVIO:
            assert ahora.loc[claves, "activo"].all()
            assert (antes.loc[claves, "dias_sin_actividad"] >= DIAS_REGRESO).all()
        elif nombre in (m.ENTRA_NO_RINDE,):
            assert ahora.loc[claves, "activo"].all() and (g["rendidos"] == 0).all()
        else:
            assert (ahora.loc[claves, "eventos"] == 0).all()
    # cruzar el umbral cuadra con la caída de activos de una semana a la otra
    cruzaron = (mov["movimiento"] == m.CRUZO_UMBRAL).sum()
    assert cruzaron == (antes["activo"] & ~ahora["activo"]).sum()


@pytest.mark.parametrize("fecha", ["2025-09-15", FECHA_CORTE_DEFECTO])
def test_ficha_cierra_con_las_otras_metricas(d, fecha):
    """La ficha de un alumno de la base muestra los mismos números que las tablas generales (D56)."""
    primero = m.buscar_alumnos(d, solo_base=True)["id_alumno"].iloc[0]
    f = m.ficha_alumno(d, primero, fecha)
    t = m.tabla_alumnos(d, fecha)
    suyo = t[t["id_alumno"] == primero].set_index("asignatura")
    mat = f["materias"].set_index("asignatura")
    assert set(mat.index) == set(suyo.index)
    assert (mat["nota_final"].fillna(-1) == suyo.loc[mat.index, "nota_final"].fillna(-1)).all()
    assert mat["percentil_minutos"].between(0, 100).all() and (mat["alumnos_materia"] > 100).all()
    # sus interacciones por tipo suman su total y los % suman 100 por materia
    cat = f["categorias"]
    assert cat["eventos"].sum() == len(f["eventos"]) == suyo["eventos"].sum()
    assert cat.groupby("asignatura")["pct_eventos"].sum().round(0).eq(100).all()
    # el promedio del curso por instrumento es el de promedio_por_instrumento
    prom = m.promedio_por_instrumento(d, fecha).set_index("id_instrumento")["promedio_pct"]
    inst = f["instrumentos"].set_index("id_instrumento")
    assert (inst["promedio_curso_pct"].fillna(-1) == prom.reindex(inst.index).fillna(-1)).all()
    assert (f["alertas"]["id_alumno"] == primero).all()
    assert (f["eventos"]["fecha_hora"] < m.fecha_de_corte(fecha) + pd.Timedelta(days=1)).all()


def test_buscador_solo_base(d):
    todos, en_base = m.buscar_alumnos(d), m.buscar_alumnos(d, solo_base=True)
    assert len(en_base) == m.base(d)["id_alumno"].nunique() < len(todos)
    assert len(m.buscar_alumnos(d, asignatura=ALG)) == len(m.base(d, ALG))


def test_foto_datos_coincide_con_gold(d):
    """La foto de antes/después (D51) cuenta todo lo cargado, sin fecha de corte."""
    f = m.foto_datos(d).set_index("asignatura")
    assert f["alumnos"].sum() == d.matricula["en_base"].sum()
    assert f["notas"].sum() == d.calificaciones["rindio"].sum()
    assert f["instrumentos"].sum() == len(d.instrumentos)
    assert f["eventos"].sum() == len(d.interacciones)
    assert (f[["libre", "regular", "promociona"]].sum(axis=1) <= f["alumnos"]).all()


def test_comparar_fotos(d):
    antes = m.foto_datos(d)
    despues = antes.copy()
    despues.loc[0, "notas"] += 10
    c = m.comparar_fotos(antes, despues)
    assert len(c) == len(antes) * len(m.FOTO_DATOS)
    cambios = c[c["diferencia"] != 0]
    assert len(cambios) == 1 and cambios.iloc[0]["clave"] == "notas" and cambios.iloc[0]["diferencia"] == 10


# ---------------------------------------------------------------------------
# Dashboard General: KPIs nuevos (D72-D76)
# ---------------------------------------------------------------------------
def test_alcanzan_regular_chicos(chicos):
    a = m.alcanzan_regular(chicos, "2025-10-24").set_index("asignatura")
    assert (a.loc[ALG, "con_condicion"], a.loc[ALG, "alcanzan"], a.loc[ALG, "pct_alcanzan"]) == (2, 1, 50.0)
    assert a.loc[PYE, "pct_alcanzan"] == 0.0           # P1 queda Libre por el recuperatorio
    assert pd.isna(a.loc[AED, "pct_alcanzan"])          # sin alumnos con condición: vacío, no 0


def test_alumnos_en_riesgo_chicos(chicos):
    r = m.alumnos_en_riesgo(chicos, "2025-10-24", umbral=7)
    # A1: Libre e inactivo; P1: Libre y nunca entró. A2 promociona aunque esté inactivo.
    assert sorted(r["id_alumno"]) == ["A1", "P1"]
    assert m.alumnos_en_riesgo(chicos, "2025-10-24", umbral=40)["id_alumno"].tolist() == ["P1"]


def test_tasa_rendicion_chicos(chicos):
    t = m.tasa_rendicion(chicos, "2025-10-24").set_index("asignatura")
    assert (t.loc[ALG, "instrumentos"], t.loc[ALG, "rendidos"], t.loc[ALG, "pct_rendidos"]) == (4, 3, 75.0)
    assert t.loc[PYE, "pct_rendidos"] == 100.0          # el recuperatorio no suma un instrumento
    assert pd.isna(t.loc[AED, "pct_rendidos"])


def test_evaluaciones_en_periodo_chicos(chicos):
    e = m.evaluaciones_en_periodo(chicos, "2025-10-05")
    assert e["id_instrumento"].tolist() == ["ALG-2"]
    assert (e.loc[0, "base"], e.loc[0, "rindieron"], e.loc[0, "no_rindieron"]) == (2, 1, 1)
    assert m.no_rindieron_periodo(chicos, "2025-10-05")["id_alumno"].tolist() == ["A1"]
    # El 01/10 entra en (corte - 7, corte] hasta el 07/10 y deja de entrar el 08/10.
    assert len(m.evaluaciones_en_periodo(chicos, "2025-10-07")) == 1
    assert m.evaluaciones_en_periodo(chicos, "2025-10-08").empty
    # Los recuperatorios no cuentan como evaluación nueva (no rendirlos no da 0).
    assert m.evaluaciones_en_periodo(chicos, "2025-09-25").empty
    assert m.no_rindieron_periodo(chicos, "2025-09-25").empty


@pytest.mark.parametrize("fecha", FECHAS)
def test_kpis_general_cierran(d, fecha):
    a = m.alcanzan_regular(d, fecha)
    dist = m.distribucion_condicion(d, fecha)
    alc = dist[dist["condicion"].isin(["Regular", "Promociona"])].groupby("asignatura")["alumnos"].sum()
    assert a.set_index("asignatura")["alcanzan"].reindex(alc.index).eq(alc).all()
    riesgo = m.alumnos_en_riesgo(d, fecha)
    assert riesgo["estado_actividad"].ne(m.ACTIVO).all()
    t = m.tasa_rendicion(d, fecha)
    assert t["pct_rendidos"].dropna().between(0, 100).all()
    n = m.nota_final(d, fecha)
    assert t["rendidos"].sum() == n["rendidos"].sum()


def test_evaluaciones_en_periodo_real(d):
    e = m.evaluaciones_en_periodo(d, FECHA_CORTE_DEFECTO)
    corte = T(FECHA_CORTE_DEFECTO)
    assert e["fecha_instrumento"].gt(corte - pd.Timedelta(days=7)).all() and e["fecha_instrumento"].le(corte).all()
    falta = m.no_rindieron_periodo(d, FECHA_CORTE_DEFECTO)
    por_materia = falta.groupby("asignatura").size()
    maximo = e.groupby("asignatura")["no_rindieron"]
    assert por_materia.reindex(maximo.max().index).ge(maximo.max()).all()
    assert por_materia.reindex(maximo.sum().index).le(maximo.sum()).all()


@pytest.mark.parametrize("fecha", ["2025-09-15", "2025-09-23", "2025-10-11", FECHA_CORTE_DEFECTO])
def test_inscriptos_sin_rendir_coinciden_con_integridad(d, fecha):
    """El KPI 'Inscriptos que no rindieron nada' (alertas sin_actividad + sin_notas)
    es el mismo grupo que los inscriptos con rendidos == 0 de la caja de integridad."""
    al = m.alertas(d, fecha)
    kpi = set(map(tuple, al.loc[al["tipo"].isin(["sin_actividad", "sin_notas"]),
                                ["asignatura", "id_alumno"]].values))
    s = m.sin_rendir(d, fecha)
    assert kpi == set(map(tuple, s.loc[s["inscripto"], ["asignatura", "id_alumno"]].values))
    if fecha == FECHA_CORTE_DEFECTO:
        # Al 24/10 todos los no inscriptos ya rindieron algo: la caja entera es el mismo grupo (101).
        assert kpi == set(map(tuple, s[["asignatura", "id_alumno"]].values))


def test_fecha_reporte_participacion(d):
    assert m.fecha_reporte_participacion(d) == T(FECHA_CORTE_DEFECTO)


# ---------------------------------------------------------------------------
# Trazabilidad: resumen y frecuencia de ingreso (D80)
# ---------------------------------------------------------------------------
@pytest.fixture
def constante() -> m.Datos:
    """Álgebra, del lunes 04/08 al domingo 26/10/2025 (12 semanas): A entra lunes y jueves
    (3 interacciones a las 10 h, la del jueves de Evaluación); B entra todos los días a las
    20 h (1 interacción). C es de la base y nunca entra. PyE: P entra solo los sábados."""
    filas, i = [], 0
    for dia in pd.date_range("2025-08-04", "2025-10-26", freq="D"):
        visitas = [("B", ALG, 20, 1)]
        if dia.day_of_week in (0, 3):
            visitas.append(("A", ALG, 10, 3))
        if dia.day_of_week == 5:
            visitas.append(("P", PYE, 15, 2))
        for alumno, asig, hora, n in visitas:
            for _ in range(n):
                i += 1
                e = _evento(i, alumno, asig, dia + pd.Timedelta(hours=hora), i)
                if alumno == "A" and dia.day_of_week == 3:
                    e["categoria"] = "Evaluación"
                filas.append(e)
    eventos = pd.DataFrame(filas)
    sesiones = eventos[["id_sesion", "id_alumno", "asignatura", "en_base"]].assign(
        inicio=eventos["fecha_hora"], duracion_min=0.0)
    matricula = pd.DataFrame({"asignatura": [ALG, ALG, ALG, PYE], "id_alumno": ["A", "B", "C", "P"],
                              "en_base": True, "inscripto": True, "en_matriculados": True, "estado": "Aceptada"})
    vacio = pd.DataFrame()
    return m.Datos(alumnos=vacio, instrumentos=vacio, interacciones=eventos, sesiones=sesiones,
                   calificaciones=vacio, participacion=vacio, matricula=matricula)


@pytest.mark.parametrize("desde", [None, "2025-09-01", "2025-10-13", "2025-10-20"])
def test_resumen_trazabilidad_no_depende_del_largo(constante, desde):
    """Con actividad constante, los KPIs dan lo mismo en cualquier período de semanas enteras."""
    r = m.resumen_trazabilidad(constante, "2025-10-26", ALG, desde=desde).loc["actual"]
    dias = r["dias"]
    assert r["alumnos"] == 2                                     # C no entró: no cuenta
    assert r["dias_ingreso_semana"] == pytest.approx((2 + 7) / 2)   # mediana de A (2) y B (7)
    assert r["interacciones_por_dia_ingreso"] == pytest.approx(2)   # mediana de A (3) y B (1)
    assert r["interacciones_por_dia"] == pytest.approx((2 * 3 + 7) / 7)
    assert r["interacciones_total"] == pytest.approx(dias * (2 * 3 + 7) / 7)
    assert r["pct_evaluacion"] == pytest.approx(3 / 13 * 100)
    assert r["pct_nocturno"] == pytest.approx(7 / 13 * 100)


def test_resumen_trazabilidad_periodo_anterior(constante, d):
    r = m.resumen_trazabilidad(constante, "2025-10-26", ALG, desde="2025-10-13")
    assert r.loc["anterior", "desde"] == T("2025-09-29") and r.loc["anterior", "hasta"] == T("2025-10-12")
    assert r.loc["anterior", "dias"] == r.loc["actual", "dias"] == 14
    assert r.loc["anterior", "dias_ingreso_semana"] == r.loc["actual", "dias_ingreso_semana"]
    # toda la cursada o un anterior que no entra entero en los datos: sin fila "anterior"
    assert "anterior" not in m.resumen_trazabilidad(constante, "2025-10-26", ALG).index
    assert "anterior" not in m.resumen_trazabilidad(constante, "2025-10-26", ALG, desde="2025-08-20").index
    # en los datos reales, el anterior es el mismo cálculo corrido en sus fechas
    r = m.resumen_trazabilidad(d, "2025-10-24", desde="2025-10-11")
    solo = m.resumen_trazabilidad(d, "2025-10-10", desde="2025-09-27").loc["actual"]
    assert r.loc["anterior"].drop(["desde", "hasta"]).astype(float).tolist() == \
        pytest.approx(solo.drop(["desde", "hasta"]).astype(float).tolist())


def test_resumen_trazabilidad_una_materia(constante, d):
    p = m.resumen_trazabilidad(constante, "2025-10-26", PYE).loc["actual"]
    assert p["alumnos"] == 1 and p["dias_ingreso_semana"] == pytest.approx(1)
    assert p["pct_finde"] == pytest.approx(100) and p["pct_nocturno"] == 0
    total = m.resumen_trazabilidad(d, "2025-10-24").loc["actual", "interacciones_total"]
    por_materia = sum(m.resumen_trazabilidad(d, "2025-10-24", a).loc["actual", "interacciones_total"]
                      for a in (ALG, PYE, AED))
    assert total == por_materia == m.interacciones_por_categoria(d, "2025-10-24")["eventos"].sum()


@pytest.mark.parametrize("desde", [None, "2025-09-01", "2025-10-13"])
def test_frecuencia_ingreso(constante, desde):
    f = m.frecuencia_ingreso(constante, "2025-10-26", desde=desde).set_index(["asignatura", "tramo"])
    assert f.loc[(ALG, "2–3"), "alumnos"] == 1 and f.loc[(ALG, "4 o más"), "alumnos"] == 1   # A: 2, B: 7
    assert f.loc[(PYE, "1–2"), "pct"] == 100
    sumas = f.groupby("asignatura")["pct"].sum()
    assert (sumas[ALG], sumas[PYE], sumas[AED]) == pytest.approx((100, 100, 0))   # AED: nadie entró
    mes = m.frecuencia_ingreso(constante, "2025-10-26", ALG, desde=desde, frecuencia="M").set_index("tramo")
    assert mes.loc["8–11", "alumnos"] == 1 and mes.loc["16 o más", "alumnos"] == 1   # A: 8,6; B: 30 por mes
    assert mes["total"].eq(2).all()
    with pytest.raises(ValueError):
        m.frecuencia_ingreso(constante, frecuencia="D")


def test_evolucion_marca_periodos_incompletos(d):
    w = m.evolucion_interacciones(d, "2025-10-24", frecuencia="W", desde="2025-10-11")
    semanas = w.drop_duplicates("periodo").set_index("periodo")
    assert semanas.loc[T("2025-10-06"), "dias"] == 2 and not semanas.loc[T("2025-10-06"), "completo"]
    assert semanas.loc[T("2025-10-13"), "completo"]
    assert semanas.loc[T("2025-10-20"), "dias"] == 5
    mes = m.evolucion_interacciones(d, "2025-10-24", frecuencia="M").drop_duplicates("periodo")
    assert mes.set_index("periodo").loc[T("2025-09-01"), "completo"]
    assert not mes.set_index("periodo").loc[T("2025-10-01"), "completo"]


# ---------------------------------------------------------------------------
# Entregas: instrumentos cerrados, dejaron de entregar, libres recuperables (D81-D83)
# ---------------------------------------------------------------------------
@pytest.fixture
def entregas() -> m.Datos:
    """PyE con 4 instrumentos (01/09, 08/09, 15/09, 22/09) + recuperatorio del primero (10/09).
      E1 rinde todo                       -> sigue
      E2 rinde solo el 1                  -> dejó (si hay 3+ cerrados)
      E3 rinde el 1 y el 4                -> sigue (el 4 es uno de los últimos o está abierto)
      E4 solo rinde el recuperatorio      -> nunca empezó: no cuenta
      E5 no rinde nada                    -> no cuenta
    Álgebra con un solo instrumento: nunca tiene "dejaron"."""
    p = [_instrumento(f"PYE-{i}", PYE, f"Semanal {i}", 100.0, f) for i, f in
         [(1, "2025-09-01"), (2, "2025-09-08"), (3, "2025-09-15"), (4, "2025-09-22")]]
    rec = _instrumento("PYE-5", PYE, "Recuperatorio: Semanal 1", 100.0, "2025-09-10", recupera=True)
    alg = _instrumento("ALG-1", ALG, "Autoevaluación", 10.0, "2025-09-01")
    rinde = {"E1": {1: 90, 2: 80, 3: 70, 4: 60}, "E2": {1: 55}, "E3": {1: 70, 4: 100}, "E4": {}, "E5": {}}
    filas = []
    for alumno, notas in rinde.items():
        for i, inst in enumerate(p, start=1):
            recu = 50.0 if (alumno == "E4" and i == 1) else None
            filas.append(_nota(alumno, inst, notas.get(i), recu=recu, fecha_recu="2025-09-10" if recu else None))
        filas.append(_nota(alumno, rec, 50.0 if alumno == "E4" else None))
    filas += [_nota("G1", alg, 4.5), _nota("G2", alg, None)]
    ids = list(rinde) + ["G1", "G2"]
    matricula = pd.DataFrame({"asignatura": [PYE] * 5 + [ALG] * 2, "id_alumno": ids, "en_base": True,
                              "inscripto": True, "en_matriculados": True, "estado": "Aceptada"})
    alumnos = pd.DataFrame({"id_alumno": ids, "apellido": ids, "nombre": "X"})
    alumnos["nombre_completo"] = alumnos["apellido"] + ", X"
    vacio = pd.DataFrame()
    return m.Datos(alumnos=alumnos, instrumentos=pd.DataFrame([*p, rec, alg]), interacciones=vacio,
                   sesiones=vacio, calificaciones=pd.DataFrame(filas), participacion=vacio, matricula=matricula)


def test_instrumento_cerrado():
    fechas = pd.Series([T("2025-10-17"), T("2025-10-18"), pd.NaT])
    assert m.cerrado(fechas, "2025-10-24").tolist() == [True, False, True]   # 7 días justos = cerrado


def test_pct_aprobada_usa_la_nota(d):
    """D81: aprobada = nota >= 60 sobre 100, no la columna Observaciones."""
    p = m.promedio_por_instrumento(d).set_index("id_instrumento")
    c = d.calificaciones[d.calificaciones["rindio"]]
    c = c.assign(pct=c["nota_obtenida"] / c["puntaje_maximo"] * 100)
    esperado = c.groupby("id_instrumento")["pct"].apply(lambda s: (s.round(2) >= 60).mean() * 100).round(1)
    assert (p.loc[esperado.index, "pct_aprobada"] == esperado).all()
    assert (p["pct_aprobada"] != p["pct_aprobada_lms"]).any()   # el LMS marca "aprobada" con notas menores a 60


def test_dejaron_de_entregar_casos_borde(entregas):
    # 24/10: los 4 cerrados; últimos 2 = 3 y 4. Solo E2 dejó (E3 rindió el 4, E4 solo el recuperatorio)
    dj = m.dejaron_de_entregar(entregas, "2025-10-24")
    assert dj["id_alumno"].tolist() == ["E2"]
    fila = dj.iloc[0]
    assert fila["ultimo_rendido"] == "Semanal 1" and fila["fecha_ultimo_rendido"] == T("2025-09-01")
    assert (fila["rendidos"], fila["instrumentos"], fila["nombre"]) == (1, 4, "E2, X")
    # 25/09: el 4 está abierto (3 días) -> cerrados 1, 2, 3: los últimos son 2 y 3, y E3, que rindió el abierto, sigue
    assert m.dejaron_de_entregar(entregas, "2025-09-25")["id_alumno"].tolist() == ["E2"]
    # 20/09: solo 2 cerrados (1 y 2) -> menos de 3: vacío
    assert m.dejaron_de_entregar(entregas, "2025-09-20").empty
    # sin instrumentos cerrados ni disponibles
    assert m.dejaron_de_entregar(entregas, "2025-08-01").empty
    # Álgebra tiene un solo instrumento: nunca aparece
    assert m.dejaron_de_entregar(entregas, "2025-10-24", ALG).empty


def test_caida_entrega_casos_borde(entregas):
    c = m.caida_entrega(entregas, "2025-10-24").set_index("asignatura")
    pye = c.loc[PYE]
    assert (pye["cerrados"], pye["abiertos"]) == (4, 0)
    assert (pye["pct_primero"], pye["pct_ultimo"], pye["diferencia_pp"]) == (60.0, 40.0, -20.0)  # 3/5 -> 2/5
    assert (pye["empezaron"], pye["dejaron"]) == (3, 1)          # E4 (solo recuperatorio) no empezó
    alg = c.loc[ALG]                                             # un solo instrumento: sin diferencia ni "dejaron"
    assert alg["cerrados"] == 1 and pd.isna(alg["diferencia_pp"]) and pd.isna(alg["dejaron"])
    abierto = m.caida_entrega(entregas, "2025-09-25").set_index("asignatura").loc[PYE]
    assert (abierto["cerrados"], abierto["abiertos"], abierto["ultimo"]) == (3, 1, "Semanal 3")
    assert m.caida_entrega(entregas, "2025-08-01").empty


def test_libres_recuperables_casos_borde(entregas):
    # 24/10: E2 = 55/400 -> 13,75 (lejos); E3 = 170/400 = 42,5 (lejos); E1 = 75 Regular. Nadie.
    assert m.libres_recuperables(entregas, "2025-10-24", PYE).empty
    # Álgebra: G1 = 4,5/10 × 120 = 54 -> Libre a 6 del corte; G2 no rindió nada -> no cuenta
    lr = m.libres_recuperables(entregas, "2025-10-24", ALG)
    assert lr["id_alumno"].tolist() == ["G1"] and lr.iloc[0]["faltan"] == 6
    # E4 solo rindió el recuperatorio (50 en el 1, 0 en el resto): cuenta como rendido
    n = m.nota_final(entregas, "2025-09-10", PYE).set_index("id_alumno")
    assert n.loc["E4", "rendidos"] == 1


def test_entregas_coinciden_con_la_pagina(d):
    """Mismo cálculo que hacía la página de Rendimiento al 24/10 (libres a menos de 10 del corte)."""
    n = m.nota_final(d, FECHA_CORTE_DEFECTO)
    h = n[n["nota_final"].notna() & (n["rendidos"] > 0)]
    reg = h["asignatura"].map({ALG: 60, PYE: 60, AED: 60})
    esperado = h[(h["condicion"] == "Libre") & (h["nota_final"] >= reg - 10)].groupby("asignatura").size()
    lr = m.libres_recuperables(d, FECHA_CORTE_DEFECTO).groupby("asignatura").size()
    assert lr.to_dict() == esperado.to_dict()
    assert lr[ALG] == 5 and lr[AED] == 12
    # dejaron: todos rindieron algo cerrado y nada de los 2 últimos cerrados ni de los abiertos
    dj = m.dejaron_de_entregar(d, FECHA_CORTE_DEFECTO)
    assert (dj["rendidos"] >= 1).all() and dj["condicion"].isin(m.CONDICIONES).all()
    c = m.caida_entrega(d, FECHA_CORTE_DEFECTO).set_index("asignatura")
    assert dj.groupby("asignatura").size().to_dict() == c["dejaron"].dropna().astype(int).to_dict()
    assert (c["dejaron"] <= c["empezaron"]).all()
    # AED Unidad 5 (21/10) sigue abierta al 24/10: el último cerrado es la Unidad 4
    assert c.loc[AED, "abiertos"] == 1 and "Unidad 4" in c.loc[AED, "ultimo"]
