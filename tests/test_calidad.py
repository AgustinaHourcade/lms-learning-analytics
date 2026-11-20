"""Tests de los controles entre fuentes (src/calidad.py, D69), sobre el pipeline real de conftest."""
import pandas as pd
import pytest

from src import calidad
from src import metricas as m


@pytest.fixture(scope="module")
def silver(carpeta_pipeline):
    return carpeta_pipeline / "silver"


@pytest.fixture(scope="module")
def d(carpeta_pipeline):
    return m.cargar(carpeta_pipeline / "gold")


def test_chequeos_tiene_todos_los_controles(d, silver):
    c = calidad.chequeos(d, silver=silver)
    assert list(c.columns) == ["area", "control", "resultado", "valor", "decision"]
    assert set(c["resultado"]) <= {calidad.OK, calidad.ATENCION}
    assert c["decision"].str.len().gt(10).all() and not c["control"].duplicated().any()
    assert {"Identidad", "Notas", "Actividad", "Matrícula"} <= set(c["area"])


def test_cobertura_ids(silver):
    c = calidad.cobertura_ids(silver).set_index("fuente")
    # participación lista a toda la cohorte; ningún alumno con nota falta en la trazabilidad
    assert c.loc["participacion", "alumnos"] >= c.loc["trazabilidad", "alumnos"]
    assert c.loc["calificaciones", "no estan en trazabilidad"] == 0
    assert c.loc["trazabilidad", "no estan en participacion"] == 0


def test_observaciones_no_es_el_corte_de_la_nota(silver):
    o = calidad.observaciones_vs_nota(silver)
    assert len(o) == 17
    assert (o["min_aprobada"] < 60).any()   # hay "aprobada" por debajo del 60 %


def test_notas_sin_rendicion_son_pocas(d):
    sin = calidad.notas_sin_rendicion(d)
    assert 0 <= len(sin) < 0.01 * d.calificaciones["rindio"].sum()


def test_participacion_y_trazabilidad_ordenan_igual(silver):
    pv = calidad.participacion_vs_trazabilidad(silver)
    pv = pv[pv["trazabilidad"] > 0]
    assert pv[["participacion", "trazabilidad"]].corr(method="spearman").iloc[0, 1] > 0.95


def test_inscripcion_vs_actividad(d):
    t = calidad.inscripcion_vs_actividad(d)
    assert len(t) == int(d.matricula["inscripto"].sum())
    assert pd.api.types.is_numeric_dtype(t["dias_inscripcion_menos_ingreso"])
