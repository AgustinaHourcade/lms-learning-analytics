"""Tests de las cursadas sintéticas (src/simulacion.py), sobre el pipeline real de conftest."""
import pandas as pd
import pytest

from src import metricas as m
from src import ml_abandono as ab
from src import simulacion


@pytest.fixture(scope="module")
def d(carpeta_pipeline):
    return m.cargar(carpeta_pipeline / "gold")


def test_sin_cambios_devuelve_los_mismos_datos(d):
    d2, c = simulacion.cursada_sintetica(d)
    assert c.empty and d2 is d


def test_abandono_inyectado_borra_todo_lo_posterior(d):
    d2, c = simulacion.cursada_sintetica(d, p_abandono=0.3, semilla=1)
    assert not c.empty and set(c["tipo"]) == {"abandono"}
    x = d2.interacciones.merge(c, on=simulacion.CLAVES)
    assert not (x["fecha_hora"] >= x["desde"]).any()
    assert len(d2.interacciones) < len(d.interacciones)
    # las notas no cambian de forma ni de cantidad: lo perdido queda en 0 y sin rendir
    assert len(d2.calificaciones) == len(d.calificaciones)
    assert d2.calificaciones["rindio"].sum() <= d.calificaciones["rindio"].sum()


def test_pausa_vuelve_despues(d):
    d2, c = simulacion.cursada_sintetica(d, p_pausa=0.3, semilla=2)
    assert set(c["tipo"]) == {"pausa"}
    assert ((c["hasta"] - c["desde"]).dt.days.between(15, 30)).all()
    x = d2.interacciones.merge(c, on=simulacion.CLAVES)
    assert not ((x["fecha_hora"] >= x["desde"]) & (x["fecha_hora"] < x["hasta"])).any()


def test_mas_abandono_sube_la_tasa(d):
    real = ab.dataset(d)["abandona"].mean()
    d2, _ = simulacion.cursada_sintetica(d, p_abandono=0.4, semilla=3)
    assert ab.dataset(d2)["abandona"].mean() > real


def test_es_reproducible(d):
    _, c1 = simulacion.cursada_sintetica(d, p_abandono=0.2, p_pausa=0.1, semilla=5)
    _, c2 = simulacion.cursada_sintetica(d, p_abandono=0.2, p_pausa=0.1, semilla=5)
    pd.testing.assert_frame_equal(c1, c2)
