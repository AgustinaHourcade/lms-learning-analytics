"""Mira las tablas que genera el pipeline (silver y gold), con filtros y descarga en CSV."""
import pandas as pd
import streamlit as st

import componentes as comp
from src.config import GOLD, SILVER

st.title("Explorar datos")
st.caption("Las tablas tal como quedaron en el pipeline. Esta página no usa los filtros de la barra lateral.")

capas = {"silver": SILVER, "gold": GOLD}
disponibles = {f"{capa} / {p.stem}": p for capa, carpeta in capas.items() for p in sorted(carpeta.glob("*.parquet"))}
if not disponibles:
    st.warning("No hay tablas todavía. Corré `python -m src.pipeline` desde la raíz del repo.")
    st.stop()


@st.cache_data
def leer(path: str, modificado: float) -> pd.DataFrame:  # `modificado` invalida el caché al regenerar
    return pd.read_parquet(path)


elegida = st.selectbox("Tabla", list(disponibles))
path = disponibles[elegida]
df = leer(str(path), path.stat().st_mtime)

c1, c2 = st.columns(2)
if "asignatura" in df:
    materias = c1.multiselect("Asignatura", sorted(df["asignatura"].unique()), default=sorted(df["asignatura"].unique()))
    df = df[df["asignatura"].isin(materias)]
if "Perfil" in df:
    perfiles = c2.multiselect("Perfil", sorted(df["Perfil"].unique()), default=sorted(df["Perfil"].unique()))
    df = df[df["Perfil"].isin(perfiles)]

m1, m2, m3 = st.columns(3)
m1.metric("Filas", f"{len(df):,}")
m2.metric("Columnas", df.shape[1])
m3.metric("Usuarios distintos", f"{df['Usuario'].nunique():,}" if "Usuario" in df else "-")

if "asignatura" in df:
    conteo = df.groupby(["asignatura", "Perfil"] if "Perfil" in df else "asignatura").size()
    st.bar_chart(conteo.unstack(fill_value=0) if "Perfil" in df else conteo, horizontal=True)

st.dataframe(df.head(1000), width="stretch")
st.caption("Se muestran hasta 1.000 filas; la descarga tiene todas las filas filtradas.")
comp.boton_csv(df, elegida.replace(" / ", "_"))

with st.expander("Valores vacíos por columna"):
    st.dataframe(df.isna().sum().rename("vacíos").to_frame().query("vacíos > 0"))
