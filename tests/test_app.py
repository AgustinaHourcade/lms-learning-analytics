"""Tests de humo de la app (Etapa 4): que cada página corra sin errores y que
los filtros de la barra lateral lleguen a las métricas.
Usan st.testing (AppTest), que corre la app sin navegador.

La app lee el gold temporal que genera conftest.py (variable LMS_GOLD): data/ no se toca."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

INICIO = str(Path(__file__).resolve().parents[1] / "app" / "Inicio.py")
PAGINAS = ["paginas/1_general.py", "paginas/2_participacion.py", "paginas/3_trazabilidad.py",
           "paginas/4_rendimiento.py", "paginas/5_notas_vs_participacion.py", "paginas/6_ficha_individual.py",
           "paginas/7_matricula_y_alertas.py", "paginas/cargar_archivo.py", "paginas/explorar_datos.py"]


@pytest.fixture
def app(carpeta_pipeline, monkeypatch):
    monkeypatch.setenv("LMS_GOLD", str(carpeta_pipeline / "gold"))
    at = AppTest.from_file(INICIO, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def _valores_metricas(at) -> dict:
    return {m.label: m.value for m in at.metric}


def test_inicio_muestra_las_tres_materias(app):
    assert len(app.metric) == 3 * 5
    assert app.selectbox(key="materia").value == "Todas las materias"
    assert app.slider(key="umbral").value == 7


def test_filtro_de_materia(app):
    app.selectbox(key="materia").set_value("Probabilidad y Estadística").run()
    assert not app.exception
    assert len(app.metric) == 5
    assert "Probabilidad y Estadística" in app.caption[0].value


def test_fecha_de_corte_cambia_los_numeros(app):
    antes = _valores_metricas(app)
    app.date_input(key="fecha_corte").set_value("2025-09-15").run()
    assert not app.exception
    assert "15/09/2025" in app.caption[0].value
    assert _valores_metricas(app) != antes


@pytest.mark.parametrize("pagina", PAGINAS)
def test_cada_pagina_corre_y_conserva_los_filtros(app, pagina):
    app.selectbox(key="materia").set_value("Álgebra").run()
    app.switch_page(pagina).run()
    assert not app.exception, app.exception
    assert app.selectbox(key="materia").value == "Álgebra"


def test_matricula_y_alertas(app):
    """Dashboard de Matrícula y alertas: tarjetas, pestañas, filtros de la lista y una fecha temprana."""
    app.switch_page("paginas/7_matricula_y_alertas.py").run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 4
    assert len(app.error) == 1 and "prioridad alta" in app.error[0].value
    app.multiselect(key="alertas_prioridad").set_value(["Administrativa"]).run()
    assert not app.exception, app.exception
    app.text_input(key="alertas_buscar").set_value("ALU_1").run()
    assert not app.exception, app.exception
    app.selectbox(key="materia").set_value("Algoritmos y Estructuras de Datos").run()
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-10").run()
    assert not app.exception, app.exception
