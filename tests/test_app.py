"""Tests de humo de la app (Etapa 4): que cada página corra sin errores y que
los filtros de la barra lateral lleguen a las métricas.
Usan st.testing (AppTest), que corre la app sin navegador.

La app lee el gold temporal que genera conftest.py (variable LMS_GOLD): data/ no se toca."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.config import ASIGNATURAS

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


SIN_FILTROS = {"paginas/cargar_archivo.py", "paginas/explorar_datos.py"}


@pytest.mark.parametrize("pagina", PAGINAS)
def test_cada_pagina_corre_y_conserva_los_filtros(app, pagina):
    app.selectbox(key="materia").set_value("Álgebra").run()
    app.switch_page(pagina).run()
    assert not app.exception, app.exception
    if pagina in SIN_FILTROS:  # no dibujan los filtros, pero los conservan (D52)
        assert not [s for s in app.selectbox if s.key == "materia"]
        assert any("Filtros desactivados" in m.value for m in app.sidebar.markdown)
        app.switch_page("paginas/1_general.py").run()
    assert app.selectbox(key="materia").value == "Álgebra"


def test_trazabilidad(app):
    """Dashboard de Trazabilidad: tarjetas, pestañas, período, frecuencia y evaluaciones."""
    app.switch_page("paginas/3_trazabilidad.py").run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 4
    antes = _valores_metricas(app)
    app.button_group(key="traz_periodo").set_value("Últimas 2 semanas").run()
    assert not app.exception, app.exception
    assert _valores_metricas(app)["Interacciones"] != antes["Interacciones"]
    app.button_group(key="traz_frecuencia").set_value("Día").run()
    app.button_group(key="traz_medida").set_value("Por alumno").run()
    app.toggle(key="traz_pct").set_value(True).run()
    app.toggle(key="traz_calor_pct").set_value(True).run()
    app.button_group(key="traz_perfil").set_value("Por hora").run()
    app.multiselect(key="traz_categorias").set_value(["Evaluación"]).run()
    app.selectbox(key="traz_eval_medida").set_value("Interacciones por alumno").run()
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()
    assert not app.exception, app.exception


def test_rendimiento(app):
    """Dashboard de Rendimiento: con todas las materias, sin evaluaciones a la fecha y con el checkbox."""
    app.switch_page("paginas/4_rendimiento.py").run()
    assert not app.exception, app.exception
    html = " ".join(m.value for m in app.markdown)
    for texto in ["Lo que explica la nota", "Condición al corte", "Instrumento más flojo",
                  "Promociona", "Regular", "Libre", *ASIGNATURAS]:
        assert texto in html, texto
    assert len(app.tabs) == 4
    app.checkbox[0].set_value(False).run()
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-10").run()
    assert not app.exception, app.exception
    assert "todavía no se tomó ninguna evaluación" in app.info[0].value


def test_participacion(app):
    """Dashboard de Participación: tarjetas, pestañas, período, frecuencia y medida."""
    app.switch_page("paginas/2_participacion.py").run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 3
    antes = _valores_metricas(app)
    app.button_group(key="part_periodo").set_value("Últimas 2 semanas").run()
    assert not app.exception, app.exception
    assert _valores_metricas(app)["Sesiones por alumno"] != antes["Sesiones por alumno"]
    app.button_group(key="part_periodo").set_value("Desde una fecha").run()
    app.date_input(key="part_desde").set_value("2025-09-01").run()
    assert not app.exception, app.exception
    app.button_group(key="part_frecuencia").set_value("Día").run()
    app.selectbox(key="part_medida").set_value("Minutos por alumno").run()
    app.text_input(key="part_buscar").set_value("zzzz-nadie").run()
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()
    assert not app.exception, app.exception


def test_notas_vs_participacion_controles(app):
    app.switch_page("paginas/5_notas_vs_participacion.py").run()
    assert not app.exception, app.exception
    def titular():  # el bloque HTML con el ρ de cada materia y la tarjeta de riesgo
        return next(m.value for m in app.markdown if "tfi-rho" in m.value)

    antes = titular()
    assert antes.count('class="tfi-rho"') == 3
    for materia in ["Álgebra", "Algoritmos y Estructuras de Datos", "Probabilidad y Estadística"]:
        assert materia in antes
    app.selectbox(key="nvp_variable").set_value("avance").run()
    app.toggle(key="nvp_solo_rindieron").set_value(True).run()
    app.toggle(key="nvp_log").set_value(True).run()
    app.selectbox(key="nvp_riesgo_materia").set_value("Álgebra").run()
    assert not app.exception, app.exception
    assert titular() != antes


def test_notas_vs_participacion_sin_evaluaciones(app):
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()
    app.switch_page("paginas/5_notas_vs_participacion.py").run()
    assert not app.exception, app.exception


def test_matricula_y_alertas(app):
    """Dashboard de Matrícula y alertas: tarjetas, pestañas, filtros de la lista y una fecha temprana."""
    app.switch_page("paginas/7_matricula_y_alertas.py").run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 4
    assert [m.label for m in app.metric][:5] == ["Inscriptos", "Activos", "Cursan sin inscripción",
                                                  "Inscriptos sin notas", "Prioridad alta"]
    app.pills(key="alertas_prioridad").set_value(["Administrativa"]).run()
    assert not app.exception, app.exception
    app.selectbox(key="no_insc_orden").set_value("Solo con baja").run()
    assert not app.exception, app.exception
    app.segmented_control(key="sin_notas_grupo").set_value("Nunca entraron").run()
    assert not app.exception, app.exception
    app.text_input(key="alertas_buscar").set_value("ALU_1").run()
    assert not app.exception, app.exception
    app.selectbox(key="materia").set_value("Algoritmos y Estructuras de Datos").run()
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-10").run()
    assert not app.exception, app.exception


def test_ficha_individual_buscador(app):
    app.switch_page("paginas/6_ficha_individual.py").run()
    assert not app.exception, app.exception
    primero = app.selectbox(key="fi_alumno").value          # muestra al primero por defecto
    assert primero.startswith("ALU_")
    assert not app.text_input                                # un solo buscador: el desplegable
    assert any("Riesgo de abandono" in m.value for m in app.markdown)   # cabecera con el predictor (D58)
    assert any("Estado por materia" in m.value for m in app.markdown)
    app.selectbox(key="fi_alumno").set_value("ALU_1105").run()
    assert not app.exception, app.exception
    assert any("ALU_1105" in m.value for m in app.markdown)
    app.button(key="fi_siguiente").click().run()                       # anterior / siguiente
    assert not app.exception, app.exception
    assert app.selectbox(key="fi_alumno").value != "ALU_1105"
    app.button(key="fi_sig_riesgo").click().run()                      # siguiente en riesgo
    assert not app.exception, app.exception
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


def test_predictor_con_corte_pasado_y_otro_umbral(app):
    """Con una fecha de corte del pasado aparece el botón para volver; mover el umbral no rompe la página."""
    app.date_input(key="fecha_corte").set_value("2025-09-20").run()
    app.switch_page("paginas/ml_abandono.py").run()
    assert not app.exception, app.exception
    assert app.button(key="ab_volver") is not None
    app.select_slider(key="ab_umbral_alto").set_value(25.0).run()
    assert not app.exception, app.exception
    app.button(key="ab_umbral_reset").click().run()
    assert not app.exception, app.exception


def test_cargar_archivo_muestra_antes_y_despues(app, carpeta_pipeline):
    """Después de una carga se muestran las tarjetas de antes/después (D51). Se
    simula el resultado (no se sube un archivo para no tocar data/raw)."""
    from src import metricas as m
    antes = m.foto_datos(m.cargar(carpeta_pipeline / "gold"))
    despues = antes.copy()
    pye = despues["asignatura"] == "Probabilidad y Estadística"
    despues.loc[pye, ["notas", "instrumentos"]] += [94, 1]
    app.switch_page("paginas/cargar_archivo.py").run()
    app.session_state["resultado_carga"] = {
        "ok": True, "mensaje": "Se cargó", "errores": [], "rechazados": [],
        "cargados": [{"nombre": "x.xlsx", "tipo": "calificaciones", "asignatura": "Probabilidad y Estadística",
                      "instrumento": "Semanal 3"}],
        "antes": antes, "despues": despues, "asignaturas": ["Probabilidad y Estadística"]}
    app.run()
    assert not app.exception, app.exception
    valores = {mt.label: mt for mt in app.metric}
    assert valores["Notas cargadas"].delta.startswith("+94")
    assert valores["Instrumentos"].delta.startswith("+1")
    assert valores["Libres"].delta == "sin cambios"
