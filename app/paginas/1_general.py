"""Dashboard 1: General.

Responde, de un vistazo y a la fecha de corte: ¿cuántos alumnos hay, cuántos
siguen entrando, cómo les va y hacia dónde va la participación?

  Tarjetas   totales de las materias elegidas, con la variación contra 7 días antes.
  Actividad  % activos / inactivos / sin actividad y tendencia semanal (con las
             evaluaciones marcadas).
  Notas      nota promedio, distribución y % por condición.
  Por materia  la tabla de KPIs, descargable en CSV.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página no calcula
reglas de negocio, solo agrega y dibuja.
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import componentes as comp
from src.config import ESQUEMA

f = comp.encabezado(
    "Dashboard general",
    "Foto de las materias a la fecha de corte: cuántos alumnos siguen activos, cómo vienen las notas "
    "y cómo evoluciona la participación semana a semana.",
)

ORDEN = {"asignatura": list(comp.COLORES_MATERIA)}
DIAS_COMPARACION = 7
corte_anterior = f.fecha_corte - timedelta(days=DIAS_COMPARACION)


# ---------------------------------------------------------------------------
# Tarjetas: totales de las materias elegidas y variación contra 7 días antes
# ---------------------------------------------------------------------------
def totales(fecha) -> dict:
    """KPIs agregados de todas las materias elegidas. Cada fila es un alumno en
    una materia: alguien que cursa dos materias cuenta dos veces."""
    notas = comp.metrica("nota_final", fecha_corte=fecha)
    act = comp.metrica("actividad_alumnos", fecha_corte=fecha)
    # Sin datos todavía (antes de la primera interacción o de la primera evaluación)
    # se devuelve NaN: la tarjeta muestra "–" y no se calcula la variación.
    hay_actividad = act["eventos"].sum() > 0
    con_nota = notas[notas["nota_pct"].notna()]
    cond = con_nota["condicion"].value_counts(normalize=True) * 100 if len(con_nota) else pd.Series(dtype=float)
    return {
        "base": len(notas),
        "pct_activos": act["activo"].mean() * 100 if hay_actividad else float("nan"),
        "nota_pct": notas["nota_pct"].mean(),
        "pct_promociona": cond.get("Promociona", 0.0) if len(con_nota) else float("nan"),
        "pct_libre": cond.get("Libre", 0.0) if len(con_nota) else float("nan"),
    }


def variacion(actual, anterior, unidad: str = "pp", decimales: int = 1):
    if pd.isna(actual) or pd.isna(anterior):
        return None
    dif = actual - anterior
    signo = "+" if dif > 0 else ""
    return f"{signo}{comp.num(dif, decimales)} {unidad}".strip()


hoy, antes = totales(f.fecha_corte), totales(corte_anterior)
ayuda_delta = f"Variación contra el {comp.fmt_fecha(corte_anterior)} ({DIAS_COMPARACION} días antes)."
comp.tarjetas([
    dict(label="Alumnos en la base" if f.asignatura else "Alumnos × materia", value=comp.num(hoy["base"]),
         help="Inscriptos (último estado Aceptada) más quienes tienen alguna nota sin estar inscriptos (D11)."
              + ("" if f.asignatura else " Un alumno que cursa dos materias cuenta dos veces.")),
    dict(label="Activos", value=comp.pct(hoy["pct_activos"]),
         delta=variacion(hoy["pct_activos"], antes["pct_activos"]),
         help=f"Entraron al LMS en los últimos {f.umbral} días. {ayuda_delta}"),
    dict(label="Nota promedio", value="–" if pd.isna(hoy["nota_pct"]) else f"{comp.num(hoy['nota_pct'], 1)} / 100",
         delta=variacion(hoy["nota_pct"], antes["nota_pct"], unidad="pts"),
         help="Puntos obtenidos / puntaje máximo de los instrumentos tomados a la fecha, × 100. Lo no rendido "
              f"cuenta 0 (D16-D17). Sobre 100 para poder comparar Álgebra con el resto. {ayuda_delta}"),
    dict(label="🟢 Promociona", value=comp.pct(hoy["pct_promociona"]),
         delta=variacion(hoy["pct_promociona"], antes["pct_promociona"]), help=ayuda_delta),
    dict(label="🔴 Libre", value=comp.pct(hoy["pct_libre"]),
         delta=variacion(hoy["pct_libre"], antes["pct_libre"]), delta_color="inverse",
         help=f"Una suba es mala noticia (por eso se muestra en rojo). {ayuda_delta}"),
])

tab_act, tab_notas, tab_tabla = st.tabs(["Actividad", "Notas", "Por materia"])

# ---------------------------------------------------------------------------
# Actividad
# ---------------------------------------------------------------------------
with tab_act:
    act = comp.metrica("actividad_alumnos")
    estados = list(comp.COLORES_ACTIVIDAD)
    reparto = (act.groupby("asignatura")["estado_actividad"].value_counts(normalize=True)
                  .mul(100).rename("pct").reset_index())
    reparto["alumnos"] = act.groupby(["asignatura", "estado_actividad"]).size() \
                            .reindex(pd.MultiIndex.from_frame(reparto[["asignatura", "estado_actividad"]])).values
    reparto["estado"] = comp.con_icono(reparto["estado_actividad"], comp.ICONOS_ACTIVIDAD)

    col1, col2 = st.columns([2, 3])
    with col1:
        st.subheader("Activos vs. inactivos")
        fig = px.bar(reparto, x="pct", y="asignatura", color="estado_actividad", orientation="h",
                     category_orders={**ORDEN, "estado_actividad": estados},
                     color_discrete_map=comp.COLORES_ACTIVIDAD, text=reparto["pct"].map(lambda v: comp.pct(v, 0)),
                     custom_data=["estado", "alumnos"],
                     labels={"pct": "% de alumnos", "asignatura": "", "estado_actividad": ""})
        fig.update_traces(hovertemplate="%{y}<br>%{customdata[0]}: %{customdata[1]} alumnos (%{x:.1f} %)"
                                        "<extra></extra>",
                          textposition="inside", insidetextanchor="middle", marker_line_width=2,
                          marker_line_color="white")
        fig.update_layout(barmode="stack", height=320, xaxis=dict(range=[0, 100], dtick=25), bargap=0.35)
        st.plotly_chart(fig, width="stretch")
        st.caption(f"**Activo:** entró en los últimos {f.umbral} días. **Inactivo:** entró alguna vez, pero "
                   "hace más. **Sin actividad:** nunca entró (D35).")

    with col2:
        st.subheader("Tendencia semanal")
        medidas = {"Alumnos activos": "alumnos_activos", "Interacciones": "eventos", "Sesiones": "sesiones",
                   "Minutos en la plataforma": "minutos"}
        c1, c2 = st.columns([2, 1], vertical_alignment="center")
        medida = c1.selectbox("Medida", list(medidas), label_visibility="collapsed")
        marcar = c2.toggle("Evaluaciones", value=True, help="Marca las evaluaciones ya tomadas.")
        evo = comp.metrica("evolucion_actividad", frecuencia="W")
        fig = px.line(evo, x="periodo", y=medidas[medida], color="asignatura", markers=True,
                      category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                      labels={"periodo": "Semana (desde el lunes)", medidas[medida]: medida, "asignatura": ""})
        fig.update_traces(line_width=2, marker_size=7,
                          hovertemplate="%{fullData.name}<br>Semana del %{x|%d/%m}: %{y:,.0f}<extra></extra>")
        if marcar:
            for ev in comp.metrica("fechas_evaluaciones").itertuples():
                fig.add_vline(x=ev.fecha_instrumento, line_width=1, line_dash="dot",
                              line_color=comp.COLORES_MATERIA[ev.asignatura], opacity=0.55)
        fig.update_layout(height=320, hovermode="x unified", yaxis_rangemode="tozero")
        st.plotly_chart(fig, width="stretch")
        st.caption("Las líneas punteadas son las evaluaciones ya tomadas (su fecha es la mediana de los intentos en la trazabilidad, "
                   "D34), del color de su materia. La última semana puede estar incompleta si la fecha de "
                   "corte cae a mitad de semana.")

# ---------------------------------------------------------------------------
# Notas
# ---------------------------------------------------------------------------
with tab_notas:
    notas = comp.metrica("nota_final")
    resumen = comp.metrica("resumen_calificaciones")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("% por condición")
        dist = comp.metrica("distribucion_condicion")
        condiciones = [c for c in comp.COLORES_CONDICION if c in set(dist["condicion"])]
        dist["etiqueta"] = comp.con_icono(dist["condicion"], comp.ICONOS_CONDICION)
        fig = px.bar(dist, x="pct", y="asignatura", color="condicion", orientation="h",
                     category_orders={**ORDEN, "condicion": condiciones},
                     color_discrete_map=comp.COLORES_CONDICION, text=dist["pct"].map(lambda v: comp.pct(v, 0)),
                     custom_data=["etiqueta", "alumnos"],
                     labels={"pct": "% de alumnos", "asignatura": "", "condicion": ""})
        fig.update_traces(hovertemplate="%{y}<br>%{customdata[0]}: %{customdata[1]} alumnos (%{x:.1f} %)"
                                        "<extra></extra>",
                          textposition="inside", insidetextanchor="middle", marker_line_width=2,
                          marker_line_color="white")
        fig.update_layout(barmode="stack", height=320, xaxis=dict(range=[0, 100], dtick=25), bargap=0.35)
        st.plotly_chart(fig, width="stretch")

    with col2:
        st.subheader("Nota promedio")
        resumen["etiqueta"] = [f"{comp.num(n, 1)} / {e}" for n, e in zip(resumen["nota_promedio"], resumen["escala"])]
        fig = px.bar(resumen, x="nota_pct_promedio", y="asignatura", orientation="h", color="asignatura",
                     category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA, text="etiqueta",
                     custom_data=["etiqueta", "nota_promedio_rindieron", "con_alguna_nota", "alumnos"],
                     labels={"nota_pct_promedio": "Nota promedio (sobre 100)", "asignatura": ""})
        fig.update_traces(hovertemplate="%{y}<br>Promedio: %{customdata[0]} (%{x:.1f} sobre 100)<br>"
                                        "Solo quienes rindieron algo: %{customdata[1]:.1f} "
                                        "(%{customdata[2]} de %{customdata[3]})<extra></extra>",
                          textposition="outside", cliponaxis=False)
        fig.update_layout(height=320, xaxis=dict(range=[0, 100], dtick=25), showlegend=False, bargap=0.45)
        st.plotly_chart(fig, width="stretch")
        st.caption("La etiqueta está en la escala de la materia (Álgebra sobre 120); la barra, sobre 100 para "
                   "poder comparar. El promedio incluye los 0 de lo no rendido.")

    st.subheader("Distribución de notas")
    excluir = st.toggle("Excluir a quienes no rindieron ningún instrumento", value=False,
                        help="Son 0 por no rendir, no por rendir mal: suelen ser alumnos que abandonaron.")
    hist = notas[notas["rendidos"] > 0] if excluir else notas
    hist = hist[hist["nota_pct"].notna()]
    sin_rendir = int((notas["rendidos"] == 0).sum())
    # Bins de 5 puntos armados a mano (el 100 entra en el último), así son iguales en las tres materias.
    ANCHO = 5
    hist = hist.assign(desde=(hist["nota_pct"].clip(0, 99.999) // ANCHO * ANCHO).astype(int))
    barras = hist.groupby(["asignatura", "desde"]).size().rename("alumnos").reset_index()
    barras["centro"] = barras["desde"] + ANCHO / 2
    barras["rango"] = [f"{a} a {a + ANCHO}" for a in barras["desde"]]
    materias_hist = [m for m in ORDEN["asignatura"] if m in set(barras["asignatura"])]
    fig = px.bar(barras, x="centro", y="alumnos", color="asignatura", facet_col="asignatura",
                 category_orders={"asignatura": materias_hist}, color_discrete_map=comp.COLORES_MATERIA,
                 custom_data=["rango"], labels={"centro": "Nota (sobre 100)", "alumnos": "Alumnos", "asignatura": ""})
    fig.update_traces(width=ANCHO * 0.9, hovertemplate="Nota de %{customdata[0]}<br>%{y} alumnos<extra></extra>")
    fig.update_xaxes(range=[0, 100], dtick=20)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    for i, materia in enumerate(materias_hist, start=1):
        escala = ESQUEMA[materia]["total_max"]
        for nombre, corte in ESQUEMA[materia]["cortes"].items():
            fig.add_vline(x=corte / escala * 100, col=i, line_width=1.5, line_color="#52514e",
                          line_dash="dot" if nombre == "Regular" else "dash")
    # Rango fijo: dentro de una pestaña oculta el autorange de plotly a veces falla.
    fig.update_yaxes(range=[0, barras["alumnos"].max() * 1.08 if len(barras) else 1])
    fig.update_layout(height=340, showlegend=False, bargap=0)
    st.plotly_chart(fig, width="stretch")
    st.caption("Línea punteada: corte de **Regular**; línea de guiones: corte de **Promociona**, pasados a "
               "escala de 100 (en Álgebra, 60 y 85 sobre 120 quedan en 50 y 70,8)."
               + ("" if excluir else f" Hay {comp.num(sin_rendir)} alumnos con 0 porque no rindieron nada."))

# ---------------------------------------------------------------------------
# Tabla por materia
# ---------------------------------------------------------------------------
with tab_tabla:
    kpis = comp.metrica("kpis_generales")
    columnas = {
        "asignatura": "Materia", "base": "Alumnos en la base", "inscriptos": "Inscriptos",
        "no_inscriptos_cursando": "Con nota sin inscripción", "activos": "Activos", "pct_activos": "% activos",
        "inscriptos_sin_actividad": "Inscriptos sin actividad", "sesiones_promedio": "Sesiones promedio",
        "minutos_promedio": "Minutos promedio", "avance_promedio": "Avance promedio (%)",
        "nota_promedio": "Nota promedio", "escala": "Escala", "pct_libre": "% Libre",
        "pct_regular": "% Regular", "pct_promociona": "% Promociona",
    }
    tabla = kpis[list(columnas)].rename(columns=columnas)
    st.dataframe(tabla, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.1f") for c in
                                ["% activos", "Sesiones promedio", "Minutos promedio", "Avance promedio (%)",
                                 "Nota promedio", "% Libre", "% Regular", "% Promociona"]})
    st.caption("Sesiones y minutos salen de la trazabilidad hasta la fecha de corte (una sesión se corta tras "
               "30 minutos sin eventos). El avance sale del reporte de participación, que es una foto al "
               "24/10 (D36) y no cambia con la fecha de corte.")
    comp.boton_csv(tabla, f"kpis_generales_{f.fecha_corte:%Y%m%d}")
