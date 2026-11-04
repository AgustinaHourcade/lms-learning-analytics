"""Portada: qué es la herramienta, cómo se usa y un resumen por materia."""
import streamlit as st

import componentes as comp

f = comp.encabezado(
    "LMS Learning Analytics",
    "Herramienta de BI sobre los datos anonimizados del LMS de **Álgebra**, **Algoritmos y Estructuras "
    "de Datos** y **Probabilidad y Estadística**. Elegí la fecha de corte, la materia y el umbral de "
    "inactividad en la barra de la izquierda: valen para todos los dashboards.",
)

kpis = comp.metrica("kpis_generales")

st.subheader("Resumen por materia")
for _, k in kpis.iterrows():
    escala = int(k["escala"])
    st.markdown(f"**{k['asignatura']}** ({comp.SIGLAS[k['asignatura']]})")
    comp.tarjetas([
        ("Alumnos en la base", comp.num(k["base"]),
         f"Inscriptos ({comp.num(k['inscriptos'])}) más los que tienen nota sin estar inscriptos "
         f"({comp.num(k['no_inscriptos_cursando'])})."),
        ("Activos", comp.pct(k["pct_activos"]), f"Entraron en los últimos {f.umbral} días."),
        ("Nota promedio", f"{comp.num(k['nota_promedio'], 1)} / {escala}",
         "Con los instrumentos tomados a la fecha de corte; lo no rendido cuenta 0."),
        ("🟢 Promociona", comp.pct(k["pct_promociona"])),
        ("🔴 Libre", comp.pct(k["pct_libre"])),
    ])

with st.expander("Cómo se calculan estos números"):
    st.markdown("""
- **Base de alumnos:** inscriptos (último estado Aceptada) más quienes tienen alguna nota.
- **Nota:** puntos obtenidos / puntaje máximo de los instrumentos tomados a la fecha de corte × 100
  (Álgebra, sobre 120). Un instrumento no rendido cuenta 0.
- **Activo / inactivo / sin actividad:** según los días desde la última interacción.

El detalle y la justificación de cada regla están en `docs/decisiones.md`.
""")

st.caption("Para sumar un Excel nuevo (por ejemplo, las notas de un parcial), usá **Cargar archivo** "
           "en el menú. **Explorar datos** muestra las tablas del pipeline tal como están hoy.")
