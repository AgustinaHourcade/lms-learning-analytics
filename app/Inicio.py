"""
App de Streamlit del TFI. Ejecutar desde la raíz del repo:
    streamlit run app/Inicio.py
Cada archivo de app/pages/ es un dashboard (Streamlit los ordena por el número).
"""
import streamlit as st

st.set_page_config(page_title="LMS Learning Analytics", layout="wide")

st.title("LMS Learning Analytics")
st.markdown("""
Herramienta de BI sobre datos anonimizados del LMS para **Álgebra**,
**Algoritmos y Estructuras de Datos** y **Probabilidad y Estadística**.

Usá el menú de la izquierda para ir a cada dashboard.
**Explorar datos** muestra las tablas del pipeline tal como están hoy.
""")
