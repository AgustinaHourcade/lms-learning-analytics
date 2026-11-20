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


def _kpis_participacion(at) -> str:
    """El HTML de la grilla de KPIs de Participación (se dibuja con st.html, no con st.metric)."""
    cuerpos = [e.proto.body for e in at.get("html") if "pa-kpis" in e.proto.body]
    assert len(cuerpos) == 1
    return cuerpos[0]


def _contexto_general(at) -> str:
    """La línea de contexto debajo del título del General (fecha, materia, umbral, base)."""
    return next(c.value for c in at.caption if c.value.startswith("Datos al"))


def _kpis_general(at) -> str:
    return " ".join(h.proto.body for h in at.get("html") if "gr-kpi-num" in h.proto.body)


def test_entra_al_general(app):
    """Sin portada: la app abre en el Dashboard General con los filtros por defecto (D90)."""
    assert app.title[0].value == "Dashboard general"
    assert "Todas las materias" in _contexto_general(app) or "alumnos × materia" in _contexto_general(app)
    assert app.selectbox(key="materia").value == "Todas las materias"
    assert app.slider(key="umbral").value == 7
    assert any("Valen para todas las páginas" in h.proto.body for h in app.sidebar.get("html"))


def test_filtro_de_materia(app):
    app.selectbox(key="materia").set_value("Probabilidad y Estadística").run()
    assert not app.exception
    assert "Probabilidad y Estadística" in _contexto_general(app)


def test_fecha_de_corte_cambia_los_numeros(app):
    antes = _kpis_general(app)
    app.date_input(key="fecha_corte").set_value("2025-09-15").run()
    assert not app.exception
    assert "15/09/2025" in _contexto_general(app)
    assert _kpis_general(app) != antes


def test_atajo_del_general_abre_la_pestana_de_matricula(app):
    app.button(key="ir_sin_rendir").click().run()
    assert not app.exception, app.exception
    assert app.session_state["ma_pestana"] == "Inscriptos sin notas"
    assert [m.label for m in app.metric][:1] == ["Inscriptos"]      # ya está en Matrícula y alertas


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


def _textos_visibles(at) -> list[str]:
    """El texto de cada elemento de la página (markdown, captions, títulos, help de métricas y
    widgets, etiquetas, tooltips de plotly...): el protobuf de cada hoja del árbol, sin los
    bloques <style> (los comentarios del CSS no se ven) ni los ids internos de los widgets."""
    import re
    textos = []

    def recorrer(nodo):
        hijos = getattr(nodo, "children", None)
        if hijos:
            for hijo in hijos.values():
                recorrer(hijo)
        elif getattr(nodo, "proto", None) is not None:
            texto = re.sub(r"<style>.*?</style>", "", str(nodo.proto), flags=re.S)
            textos.append(re.sub(r'^\s*id: ".*"$', "", texto, flags=re.M))   # ids internos de widgets

    recorrer(at._tree)
    return textos


@pytest.mark.parametrize("pagina", PAGINAS)
def test_sin_codigos_de_decision_visibles(app, pagina):
    """Los códigos de decisión (D7, D62...) van solo en comentarios y docstrings, nunca en pantalla."""
    import re
    app.switch_page(pagina).run()
    assert not app.exception, app.exception
    encontrados = [m.group() for t in _textos_visibles(app) for m in re.finditer(r"\bD\d{1,3}\b", t)]
    assert not encontrados, f"{pagina}: {encontrados}"


def _kpis_trazabilidad(at) -> str:
    return " ".join(m.value for m in at.markdown if m.value.startswith(('<div class="tz-kpi"', '<div class="tz-kpis"')))


def test_trazabilidad(app):
    """Dashboard de Trazabilidad: tarjetas (D80), pestañas, período, controles y bordes."""
    import re
    app.switch_page("paginas/3_trazabilidad.py").run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 4
    antes = _kpis_trazabilidad(app)
    for nombre in ["Días con ingreso por semana", "Interacciones por día de ingreso", "Clics en Evaluación",
                   "Clics entre 18 y 24 h", "alumnos que entraron", "en total"]:
        assert nombre in antes, nombre
    assert "tz-kpi-delta" not in antes                # toda la cursada: sin Δ

    def sin_textos_rotos():
        textos = " ".join(_textos_visibles(app))
        assert not re.search(r"\bnan\b|\bNaN\b|\bNone\b", textos)

    sin_textos_rotos()
    app.button_group(key="traz_periodo").set_value("Últimas 2 semanas").run()
    assert not app.exception, app.exception
    despues = _kpis_trazabilidad(app)
    assert despues != antes and despues.count("tz-kpi-delta") == 3     # Δ en las tarjetas 1 a 3
    sin_textos_rotos()
    app.button_group(key="traz_frecuencia").set_value("Día").run()
    app.toggle(key="traz_tipos_abs").set_value(True).run()
    app.toggle(key="traz_calor_pct").set_value(True).run()
    app.button_group(key="traz_frec_ingreso").set_value("Mes").run()
    app.button_group(key="traz_perfil").set_value("Por hora").run()
    app.multiselect(key="traz_categorias").set_value(["Agenda"]).run()
    app.selectbox(key="traz_eval_medida").set_value("Interacciones por alumno").run()
    assert not app.exception, app.exception
    sin_textos_rotos()
    app.selectbox(key="materia").set_value("Probabilidad y Estadística").run()
    assert not app.exception, app.exception
    sin_textos_rotos()
    app.button_group(key="traz_periodo").set_value("Toda la cursada").run()
    assert "tz-kpi-delta" not in _kpis_trazabilidad(app)
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()
    assert not app.exception, app.exception


def test_rendimiento(app):
    """Dashboard de Rendimiento: con todas las materias, cada materia, otras fechas y el checkbox."""
    app.switch_page("paginas/4_rendimiento.py").run()
    assert not app.exception, app.exception
    assert not [s for s in app.slider if s.key == "umbral"]   # el umbral no cambia nada en esta página
    html = " ".join(m.value for m in app.markdown)
    for texto in ["Tasa de entrega", "Dejaron de entregar", "Libres recuperables", "Sin ninguna entrega",
                  "Por materia", "proyectada", "Promociona", "Regular", "Libre", *ASIGNATURAS]:
        assert texto in html, texto
    for texto in ["Instrumento más flojo", "nota promedio de todos", "Inactivo después de", "Para leer"]:
        assert texto not in html, texto
    assert len(app.tabs) == 3
    assert len(app.expander) == 2          # listas de Dejaron de entregar y Libres recuperables
    app.checkbox[0].set_value(False).run()
    assert not app.exception, app.exception
    for materia in ASIGNATURAS:
        app.selectbox(key="materia").set_value(materia).run()
        assert not app.exception, (materia, app.exception)
    app.selectbox(key="materia").set_value("Todas las materias").run()
    for fecha in ["2025-09-15", "2025-08-14"]:   # la segunda es la primera fecha con evaluaciones
        app.date_input(key="fecha_corte").set_value(fecha).run()
        assert not app.exception, (fecha, app.exception)
    app.date_input(key="fecha_corte").set_value("2025-08-10").run()
    assert not app.exception, app.exception
    assert "todavía no se tomó ninguna evaluación" in app.info[0].value


def test_participacion(app):
    """Dashboard de Participación: tarjetas, pestañas, período, frecuencia y medida."""
    app.switch_page("paginas/2_participacion.py").run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 2
    antes = _kpis_participacion(app)
    for nombre in ["Sesiones por alumno por semana", "Minutos por alumno por semana", "Avance promedio",
                   "Retención semanal"]:
        assert nombre in antes
    assert "semanas previas" not in antes          # toda la cursada: sin período anterior, sin Δ
    app.button_group(key="part_periodo").set_value("Últimas 2 semanas").run()
    assert not app.exception, app.exception
    despues = _kpis_participacion(app)
    assert despues != antes and "vs. 2 semanas previas" in despues
    app.selectbox(key="materia").set_value("Álgebra").run()
    assert not app.exception, app.exception
    assert _kpis_participacion(app) != despues
    app.selectbox(key="materia").set_value("Todas las materias").run()
    app.button_group(key="part_periodo").set_value("Desde una fecha").run()
    app.date_input(key="part_desde").set_value("2025-09-01").run()
    assert not app.exception, app.exception
    app.button_group(key="part_frecuencia").set_value("Día").run()
    app.selectbox(key="part_medida").set_value("Minutos por alumno").run()
    app.text_input(key="part_buscar").set_value("zzzz-nadie").run()
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()
    assert not app.exception, app.exception


def test_notas_vs_participacion_controles(app, carpeta_pipeline):
    app.switch_page("paginas/5_notas_vs_participacion.py").run()
    assert not app.exception, app.exception
    def kpis():  # las cuatro tarjetas de arriba (casos en riesgo, brecha, activos libres, ρ)
        return " ".join(m.value for m in app.markdown if m.value.startswith('<div class="tfi"><p class="nvp-etq'))

    def lectura():
        return next(m.value for m in app.markdown if m.value.startswith('<p class="tfi nvp-lectura'))

    from src import metricas
    d = metricas.cargar(carpeta_pipeline / "gold")
    casos = metricas.casos_en_riesgo(d).set_index("asignatura").loc[metricas.TODAS_LAS_MATERIAS].astype(int)
    antes = kpis()
    assert f"{casos['casos']}<small>casos</small>" in antes and f"{casos['alumnos']} alumnos distintos" in antes
    for sigla in ["ALG", "AED", "PYE"]:
        assert f"<b>{sigla}</b>" in antes and f"en {sigla}" in lectura()
    assert "Va de 0" not in " ".join(m.value for m in app.markdown)   # Spearman va de −1 a 1
    lista = next(df.value for df in app.dataframe if "Materias en riesgo" in df.value.columns)
    assert len(lista) == casos["casos"] and lista["ID"].nunique() == casos["alumnos"]
    assert "Mediana de la materia" not in lista.columns

    app.button(key="nvp_ir_lista").click().run()   # "Prioridad de contacto →" abre la pestaña del cuadrante
    assert not app.exception, app.exception
    assert app.session_state["nvp_pestana"] == "Cuadrante de riesgo"

    app.selectbox(key="nvp_variable").set_value("avance").run()
    app.toggle(key="nvp_solo_rindieron").set_value(True).run()
    app.toggle(key="nvp_log").set_value(True).run()
    app.selectbox(key="nvp_riesgo_materia").set_value("Álgebra").run()
    assert not app.exception, app.exception
    assert kpis() != antes

    app.selectbox(key="materia").set_value("Álgebra").run()   # una materia: sin siglas ni "alumnos distintos"
    assert not app.exception, app.exception
    assert "alumnos distintos" not in kpis() and "en ALG" not in lectura()


def test_notas_vs_participacion_sin_evaluaciones(app):
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()
    app.switch_page("paginas/5_notas_vs_participacion.py").run()
    assert not app.exception, app.exception


def test_matricula_y_alertas(app):
    """Dashboard de Matrícula y alertas: tarjetas, pestañas, filtros de la lista y una fecha temprana."""
    app.switch_page("paginas/7_matricula_y_alertas.py").run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 4
    assert [m.label for m in app.metric][:5] == ["Inscriptos", "Inscriptos activos", "Cursan sin inscripción",
                                                  "Inscriptos sin notas", "Prioridad alta"]
    cuerpo = " ".join(h.proto.body for h in app.get("html"))
    assert "Casi todos entraron al aula" in cuerpo and "¿Rinden distinto los no inscriptos?" in cuerpo
    assert "uno de cada tres inscriptos entra pero no rinde nada" in cuerpo
    assert app.button(key="alertas_ver_ficha").disabled          # sin fila elegida no hay ficha a la que ir
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
    app.slider(key="umbral").set_value(14).run()
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-15").run()
    assert not app.exception, app.exception
    app.selectbox(key="materia").set_value("Todas las materias").run()
    assert not app.exception, app.exception
    cuerpo = " ".join(h.proto.body for h in app.get("html"))
    assert "Álgebra y Probabilidad: sin casos para comparar." in cuerpo
    app.date_input(key="fecha_corte").set_value("2025-08-10").run()
    assert not app.exception, app.exception


def test_ficha_individual_buscador(app):
    app.switch_page("paginas/6_ficha_individual.py").run()
    assert not app.exception, app.exception
    primero = app.selectbox(key="fi_alumno").value          # muestra al primero por defecto
    assert primero.startswith("ALU_")
    assert not app.text_input                                # un solo buscador: el desplegable
    assert any("Riesgo de abandono" in m.value for m in app.markdown)   # columna del predictor (D58)
    assert any("Estado por materia" in m.value for m in app.markdown)
    assert not app.tabs                                      # una sola página, sin pestañas (D87)
    assert not any("&#" in m.value for m in app.markdown)
    app.selectbox(key="fi_alumno").set_value("ALU_1105").run()
    assert not app.exception, app.exception
    assert any("ALU_1105" in m.value for m in app.markdown)
    app.button(key="fi_siguiente").click().run()                       # anterior / siguiente
    assert not app.exception, app.exception
    assert app.selectbox(key="fi_alumno").value != "ALU_1105"
    app.button(key="fi_sig_riesgo").click().run()                      # siguiente en riesgo
    assert not app.exception, app.exception
    libre = next(o for o in app.selectbox(key="fi_grupo").options if o.startswith("Libre"))
    app.selectbox(key="fi_grupo").set_value(libre).run()               # filtro de grupo
    assert not app.exception, app.exception
    app.selectbox(key="fi_grupo").set_value("Todos los alumnos").run()
    app.selectbox(key="fi_alumno").set_value("ALU_1293").run()
    cuerpo = " ".join(m.value for m in app.markdown)
    assert "44,2 de 45 pts posibles (98 %)" in cuerpo and "117,8/120" in cuerpo
    assert "Aprobó 15 de 16 instrumentos" in cuerpo
    app.date_input(key="fecha_corte").set_value("2025-09-01").run()
    assert not app.exception, app.exception
    app.date_input(key="fecha_corte").set_value("2025-08-06").run()   # antes de cualquier evaluación
    assert not app.exception, app.exception
    assert "Sin evaluaciones" in " ".join(m.value for m in app.markdown)


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


@pytest.mark.parametrize("fecha", ["2025-08-05", "2025-08-10", "2025-09-08", "2025-10-14", "2025-10-24"])
@pytest.mark.parametrize("materia", ["Todas las materias", "Álgebra"])
def test_general_sin_pestanas_ni_nan(app, fecha, materia):
    """Dashboard General: corre en los bordes (antes de la primera evaluación, una sola
    materia, con el interruptor) sin pestañas, sin 'nan' y sin referencias D*."""
    import re
    app.date_input(key="fecha_corte").set_value(fecha)
    app.selectbox(key="materia").set_value(materia)
    app.switch_page("paginas/1_general.py").run()
    assert not app.exception, app.exception
    assert len(app.tabs) == 0
    for valor in [False, True]:
        app.toggle[0].set_value(valor).run()
        assert not app.exception, app.exception
        textos = " ".join(str(getattr(e, "value", "")) for e in [*app.markdown, *app.caption])
        assert not re.search(r"\bnan\b", textos, re.I), fecha
        assert not re.search(r"\bD\d+\b", textos), fecha
