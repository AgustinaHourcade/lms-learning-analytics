"""
Tests de la Etapa 7: predictor de abandono (src/ml_abandono.py, D58).

Correr desde la raíz:  python -m pytest tests/test_ml_abandono.py
  * con datos a mano: el costo y la elección del umbral;
  * sobre el gold real (fixture de conftest.py): que las variables no usen
    datos del futuro, que el objetivo sea el de la definición, que la prueba
    tenga alumnos que no están en entrenamiento, que el modelo se guarde y se
    lea con joblib y que la predicción cubra a toda la base en cualquier fecha.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from src import metricas as m
from src import ml_abandono as ab
from src.config import ABANDONO_COSTO_FN, ABANDONO_COSTO_FP, ABANDONO_HORIZONTE_DIAS, ABANDONO_SEGUIMIENTO_DIAS

FECHAS = ["2025-08-10", "2025-09-15", "2025-10-24"]


# ---------------------------------------------------------------------------
# Costo y umbral (datos a mano)
# ---------------------------------------------------------------------------
def test_costo_cuenta_falsos_negativos_y_positivos():
    y = [True, True, False, False, False]
    pred = [True, False, True, False, False]   # 1 FN y 1 FP
    assert ab.costo(y, pred) == ABANDONO_COSTO_FN + ABANDONO_COSTO_FP
    assert ab.costo(y, pred, costo_fn=10, costo_fp=0) == 10


def test_umbral_minimiza_el_costo():
    y = np.array([True] * 10 + [False] * 90)
    prob = np.r_[np.linspace(0.3, 0.9, 10), np.linspace(0.0, 0.5, 90)]
    u = ab.elegir_umbral(y, prob)
    costos = ab.tabla_umbral(y, prob).set_index("umbral")["costo"]
    assert costos.loc[u] == costos.min()
    # si no detectar sale más caro, el umbral baja (se marca a más gente)
    assert ab.elegir_umbral(y, prob, costo_fn=20) <= ab.elegir_umbral(y, prob, costo_fn=1)


# ---------------------------------------------------------------------------
# Sobre el gold real
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def d(carpeta_pipeline) -> m.Datos:
    return m.cargar(carpeta_pipeline / "gold")


@pytest.fixture(scope="module")
def modelo(d, carpeta_pipeline) -> ab.ModeloAbandono:
    return ab.cargar_modelo(d, carpeta_pipeline / "gold" / "modelo_test.joblib", reentrenar=True)


def _hasta(d: m.Datos, corte: str) -> m.Datos:
    """Los mismos datos, pero sin nada posterior a la fecha de corte."""
    fin = pd.Timestamp(corte) + pd.Timedelta(days=1)
    return dataclasses.replace(d, interacciones=d.interacciones[d.interacciones["fecha_hora"] < fin],
                               sesiones=d.sesiones[d.sesiones["inicio"] < fin])


@pytest.mark.parametrize("corte", ["2025-08-25", "2025-09-20"])
def test_variables_no_usan_datos_del_futuro(d, corte):
    completo = ab.variables(d, corte).set_index(ab.CLAVES)
    cortado = ab.variables(_hasta(d, corte), corte).set_index(ab.CLAVES)
    pd.testing.assert_frame_equal(completo[list(ab.VARIABLES)], cortado.loc[completo.index, list(ab.VARIABLES)])


def test_variables_cubren_la_base(d):
    v = ab.variables(d)
    assert len(v) == len(m.base(d)) and not v.duplicated(ab.CLAVES).any()
    # vacías solo para quien nunca entró (no se le predice nada)
    assert v[list(ab.VARIABLES)].drop(columns=["dias_sin_actividad", "sin_vs_habitual"]).notna().all().all()
    assert v["sin_vs_habitual"].isna().equals(v["dias_sin_actividad"].isna())
    assert v["pct_semanas_activas"].between(0, 100).all()
    assert (v["eventos_7d"] <= v["eventos_14d"]).all() and (v["eventos_14d"] <= v["eventos_total"]).all()
    # días sin actividad = lo mismo que usa el estado de actividad (D35)
    act = m.actividad_alumnos(d).set_index(ab.CLAVES)["dias_sin_actividad"]
    assert v.set_index(ab.CLAVES)["dias_sin_actividad"].equals(act.astype(float).reindex(v.set_index(ab.CLAVES).index))


def test_nota_cuenta_desde_que_el_alumno_rinde(d):
    """D64: la nota de un instrumento entra a las variables el día en que ESE alumno lo rindió."""
    real = ab._realizaciones(d)
    fila = real[real["id_instrumento"].eq("ALG-03")].sort_values("rindio_el").iloc[-1]   # el último en rendir
    dia = fila["rindio_el"].normalize()
    clave = (fila["asignatura"], fila["id_alumno"])
    antes = ab.variables(d, dia - pd.Timedelta(days=1)).set_index(ab.CLAVES).loc[clave]
    ese_dia = ab.variables(d, dia).set_index(ab.CLAVES).loc[clave]
    nota = d.calificaciones.set_index([*ab.CLAVES, "id_instrumento"]).loc[(*clave, "ALG-03")]
    if dia - pd.Timedelta(days=1) >= d.instrumentos.set_index("id_instrumento").loc["ALG-03", "fecha_instrumento"]:
        assert ese_dia["pct_rendidos"] > antes["pct_rendidos"]   # ya estaba tomada: pasa de no rendida a rendida
    if nota["puntos"] > 0:
        assert ese_dia["nota_pct"] != antes["nota_pct"]
    assert ese_dia["rindio_ultima"] == 1


def test_variables_nuevas_tienen_sentido(d):
    v = ab.variables(d, "2025-10-01")
    assert v["pct_rendidos"].between(0, 100).all() and v["nota_pct"].between(0, 100).all()
    assert v["materias_activas_14d"].between(0, 3).all()
    # sin actividad global nunca supera la de la propia materia
    entro = v["dias_sin_actividad"].notna()
    assert (v.loc[entro, "dias_sin_actividad_global"] <= v.loc[entro, "dias_sin_actividad"]).all()
    assert (v["dias_desde_evaluacion"] >= 0).all()


def test_objetivo_es_abandonar_la_materia(d):
    """D67: abandona = no vuelve a entrar después del corte ni rinde una evaluación posterior a la trazabilidad."""
    corte = pd.Timestamp("2025-09-10")
    ds = ab.dataset(d, [corte])
    assert ds["eventos_total"].gt(0).all()                                   # todos los que entraron alguna vez
    assert ds["dias_sin_actividad"].ge(ABANDONO_HORIZONTE_DIAS).any()        # incluidos los alejados
    ev = d.interacciones[d.interacciones["en_base"]]
    despues = ev[ev["fecha"] > corte]
    siguen = set(map(tuple, despues[ab.CLAVES].drop_duplicates().to_numpy()))
    siguen |= set(map(tuple, ab._notas_posteriores(d).to_numpy()))
    esperado = [tuple(r) not in siguen for r in ds[ab.CLAVES].to_numpy()]
    assert ds["abandona"].tolist() == esperado
    assert 0 < ds["abandona"].mean() < 0.5
    # los alejados abandonan mucho más que los que vienen entrando, pero no todos (muchos vuelven)
    cur = ab._cursando(ds)
    assert ds.loc[cur, "abandona"].mean() < ds.loc[~cur, "abandona"].mean() < 0.9


def test_notas_posteriores_cuentan_como_seguir(d):
    """Quien rinde una evaluación que no figura en la trazabilidad (posterior al último dato) no abandonó.
    Hoy no hay ninguna: se simula corriendo la primera realización de un instrumento a después del final."""
    ins = d.instrumentos.copy()
    ins.loc[ins["id_instrumento"].eq("PYE-01"), "fecha_primera_realizacion"] = pd.NaT
    otro = dataclasses.replace(d, instrumentos=ins)
    tarde = ab._notas_posteriores(otro)
    c = d.calificaciones
    rindieron = c[c["id_instrumento"].eq("PYE-01") & c["rindio"]]
    assert len(tarde) == len(rindieron) > 0
    vuelven = ab._vuelven(otro, ab.fin_datos(d))   # después del último dato solo quedan esas notas
    assert len(vuelven) == len(tarde)


def test_las_fotos_conocen_su_desenlace(d):
    cortes = ab.cortes_entrenamiento(d)
    assert len(cortes) > 5
    assert cortes.max() + pd.Timedelta(days=ABANDONO_SEGUIMIENTO_DIAS) <= ab.fin_datos(d)
    assert all(ab.desenlace_conocido(d, c) for c in cortes)
    assert len(set(cortes.day_of_week)) > 1   # caen en distintos días de la semana


def test_modelo_y_comparacion(modelo):
    c = modelo.comparacion
    assert set(c["modelo"]) == set(ab.NOMBRES_MODELOS.values())
    assert set(c["conjunto"]) == {"validación cruzada", ab.VALIDACION_TEMPORAL, "prueba"}
    assert c.loc[c["elegido"], "modelo"].nunique() == 1 and modelo.nombre in c["modelo"].tolist()
    assert c["auc_roc"].between(0.5, 1).all()
    assert 0 < modelo.umbral < 1
    # el elegido es el de menor costo en la validación temporal (sin contar la regla, D67)
    cv = c[c["conjunto"].eq(ab.VALIDACION_TEMPORAL) & c["modelo"].ne(ab.REGLA)]
    assert cv.loc[cv["elegido"], "costo"].item() == cv["costo"].min()
    # los modelos ordenan mejor que la regla en los alumnos de prueba
    p = c[c["conjunto"].eq("prueba")].set_index("modelo")
    assert p.loc[modelo.nombre, "auc_roc"] > p.loc[ab.REGLA, "auc_roc"]
    assert set(modelo.importancia["variable"]) == set(ab.VARIABLES)


def test_prueba_separada_por_alumno(d):
    """Mismo split que entrenar(): ningún alumno de prueba está en entrenamiento."""
    from sklearn.model_selection import GroupShuffleSplit
    ds = ab.dataset(d)
    e, p = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=ab.ABANDONO_SEMILLA)
                .split(ds, ds["abandona"], ds["id_alumno"]))
    assert not set(ds["id_alumno"].iloc[e]) & set(ds["id_alumno"].iloc[p])


def test_joblib_ida_y_vuelta(d, modelo, carpeta_pipeline):
    ruta = carpeta_pipeline / "gold" / "modelo_test.joblib"
    assert ruta.exists()
    leido = ab.cargar_modelo(d, ruta)
    assert leido.firma == ab.firma(d) and leido.umbral == modelo.umbral
    v = ab.variables(d, "2025-09-15")
    v = v[ab._con_actividad(v)]
    np.testing.assert_allclose(leido.probabilidad(v), modelo.probabilidad(v))
    # si los datos cambian, la firma no coincide y se reentrena
    menos = _hasta(d, "2025-10-20")
    assert ab.firma(menos) != leido.firma


@pytest.mark.parametrize("fecha", FECHAS)
def test_riesgo_cubre_la_base(d, modelo, fecha):
    r = ab.riesgo_abandono(d, fecha, modelo=modelo)
    assert len(r) == len(m.base(d)) and not r.duplicated(ab.CLAVES).any()
    entro = r["estado_abandono"].ne(ab.SIN_ACTIVIDAD)
    assert r.loc[entro, "probabilidad"].between(0, 100).all()
    assert r.loc[~entro, "probabilidad"].isna().all()
    assert set(r["nivel_riesgo"]) <= set(ab.NIVELES)
    alto = r["nivel_riesgo"].eq(ab.ALTO)
    assert (r.loc[alto, "probabilidad"] >= 100 * modelo.umbral).all()
    assert r.loc[r["estado_abandono"].eq(ab.ALEJADO), "dias_sin_actividad"].ge(ABANDONO_HORIZONTE_DIAS).all()
    assert r.loc[r["estado_abandono"].eq(ab.CURSANDO), "dias_sin_actividad"].lt(ABANDONO_HORIZONTE_DIAS).all()
    s = ab.resumen_riesgo(d, fecha, modelo=modelo)
    niveles = ["riesgo_alto", "riesgo_medio", "riesgo_bajo", "sin_actividad"]
    assert (s[niveles].sum(axis=1) == s["base"]).all()
    assert (s["cursando"] + s["alejados"] + s["sin_actividad"] == s["base"]).all()


def test_desenlace_solo_si_ya_se_sabe(d, modelo):
    pasado = ab.riesgo_abandono(d, "2025-09-15", modelo=modelo)
    entro = pasado["estado_abandono"].ne(ab.SIN_ACTIVIDAD)
    assert pasado.loc[entro, "abandono_real"].notna().all()
    assert ab.riesgo_abandono(d, "2025-10-10", modelo=modelo)["abandono_real"].isna().all()   # < 28 días después
    assert ab.riesgo_abandono(d, "2025-10-24", modelo=modelo)["abandono_real"].isna().all()


def test_antes_del_inicio_nadie_cursa(d, modelo):
    r = ab.riesgo_abandono(d, "2025-08-01", modelo=modelo)
    assert r["estado_abandono"].eq(ab.SIN_ACTIVIDAD).all()
    temprano = ab.riesgo_abandono(d, "2025-08-10", modelo=modelo)
    assert temprano.attrs["aviso"]


def test_ficha_un_alumno(d, modelo):
    alumno = m.base(d)["id_alumno"].iloc[0]
    r = ab.riesgo_alumno(d, alumno, modelo=modelo)
    assert set(r["id_alumno"]) == {alumno}
    assert len(r) == m.base(d)["id_alumno"].eq(alumno).sum()
    ev = ab.evolucion_riesgo(d, alumno, "2025-09-30", modelo=modelo)
    assert ev["fecha_corte"].max() == pd.Timestamp("2025-09-30")
    assert set(ev["asignatura"]) == set(r["asignatura"])
