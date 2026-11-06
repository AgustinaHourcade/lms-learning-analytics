"""
App de Streamlit del TFI. Ejecutar desde la raíz del repo:
    streamlit run app/Inicio.py

Este archivo es el punto de entrada (también en Streamlit Cloud): arma el menú
con st.navigation, dibuja la barra lateral global (fecha de corte, materia y
umbral, D46) y después corre la página elegida, que está en app/paginas/.
Para agregar una página: crear el archivo en app/paginas/ y sumarlo a PAGINAS.
"""
import streamlit as st

st.set_page_config(page_title="LMS Learning Analytics", page_icon=":material/school:", layout="wide")

import componentes as comp  # noqa: E402  (después de set_page_config)

comp.estilos()
comp.asegurar_gold()

PAGINAS = {
    "": [
        st.Page("paginas/inicio.py", title="Inicio", icon=":material/home:", default=True),
    ],
    "Dashboards": [
        st.Page("paginas/1_general.py", title="General", icon=":material/dashboard:"),
        st.Page("paginas/2_participacion.py", title="Participación", icon=":material/groups:"),
        st.Page("paginas/3_trazabilidad.py", title="Trazabilidad", icon=":material/timeline:"),
        st.Page("paginas/4_rendimiento.py", title="Rendimiento académico", icon=":material/grading:"),
        st.Page("paginas/5_notas_vs_participacion.py", title="Notas vs. participación",
                icon=":material/scatter_plot:"),
        st.Page("paginas/6_ficha_individual.py", title="Ficha individual", icon=":material/person_search:"),
        st.Page("paginas/7_matricula_y_alertas.py", title="Matrícula y alertas",
                icon=":material/notification_important:"),
    ],
    "Machine learning": [
        st.Page("paginas/ml_grupos.py", title="Grupos de alumnos", icon=":material/bubble_chart:"),
        st.Page("paginas/ml_abandono.py", title="Predictor de abandono", icon=":material/trending_down:"),
    ],
    "Datos": [
        st.Page("paginas/cargar_archivo.py", title="Cargar archivo", icon=":material/upload_file:"),
        st.Page("paginas/explorar_datos.py", title="Explorar datos", icon=":material/table_view:"),
    ],
}

pagina = st.navigation(PAGINAS)
comp.barra_lateral()
pagina.run()
