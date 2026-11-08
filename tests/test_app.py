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
           "paginas/7_matricula_y_alertas.py", "paginas/ml_grupos.py", "paginas/ml_abandono.py",
           "paginas/cargar_archivo.py",
           "paginas/explorar_datos.py"]


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


def test_ficha_individual_buscador(app):
    app.switch_page("paginas/6_ficha_individual.py").run()
    assert not app.exception, app.exception
    primero = app.selectbox(key="fi_alumno").value          # muestra al primero por defecto
    assert primero.startswith("ALU_")
    assert not app.text_input                                # un solo buscador: el desplegable
    assert any(m.label == "Riesgo de abandono" for m in app.metric)   # card del predictor (D58)
    app.selectbox(key="fi_alumno").set_value("ALU_1105").run()
    assert not app.exception, app.exception
    assert any("ALU_1105" in s.value for s in app.subheader)
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()   # antes de cualquier evaluación
    assert not app.exception, app.exception


def test_predictor_buscador_individual(app):
    """La página del predictor tiene el mismo buscador que la Ficha y el resumen del alumno (D58)."""
    app.switch_page("paginas/ml_abandono.py").run()
    assert not app.exception, app.exception
    assert app.selectbox(key="ab_alumno").value.startswith("ALU_")   # muestra al primero por defecto
    app.selectbox(key="ab_alumno").set_value("ALU_1105").run()
    assert not app.exception, app.exception
    assert any("ALU_1105" in m.value for m in app.markdown)
    assert any("riesgo de abandono" in m.value for m in app.markdown)
    app.selectbox(key="materia").set_value("Álgebra").run()           # el buscador se acota a la materia
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()   # antes del día 14 de la cursada
    assert not app.exception, app.exception


def test_grupos_antes_de_la_primera_evaluacion(app):
    """Con una fecha de corte sin evaluaciones, la página de grupos avisa en vez de romperse."""
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()
    app.switch_page("paginas/ml_grupos.py").run()
    assert not app.exception, app.exception
    assert any("evaluaciones" in i.value for i in app.info)


def test_bloque_de_riesgo_para_la_ficha(carpeta_pipeline, monkeypatch):
    """El bloque del predictor de abandono que va en la Ficha individual corre solo (D58)."""
    monkeypatch.setenv("LMS_GOLD", str(carpeta_pipeline / "gold"))

    def ficha():
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path.cwd() / "app"))
        import componentes as comp
        alumno = comp.metrica("riesgo_abandono", asignatura=None)["id_alumno"].iloc[0]
        comp.riesgo_abandono_alumno(alumno)

    at = AppTest.from_function(ficha, default_timeout=120).run()
    assert not at.exception, at.exception
    assert any("riesgo de abandono" in m.value for m in at.markdown)
