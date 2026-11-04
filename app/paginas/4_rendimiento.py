"""Dashboard 2 (del plan): Rendimiento académico.

Responde, a la fecha de corte: ¿qué instrumentos cuestan más?, ¿cuántos los
rinden?, ¿cómo se reparten las notas? y ¿cómo se fue moviendo la condición
(Libre / Regular / Promociona) a medida que se tomaron las evaluaciones?

  Tarjetas        nota promedio (con y sin los 0), tasa de entrega, instrumento
                  con el promedio más bajo y % Libre.
  Por instrumento boxplot de cada instrumento (solo quienes lo rindieron, D22)
                  con el % de la base que lo rindió abajo.
  Distribución    histograma en la escala de la materia, coloreado por condición,
                  con los cortes del ESQUEMA.
  Condición       % por condición hoy y su evolución evaluación a evaluación (D51).
  Tabla           el resumen por instrumento y el detalle por alumno, en CSV.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo agrega y dibuja.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import componentes as comp
from src.config import ESQUEMA

f = comp.encabezado(
    "Rendimiento académico",
    "Cómo les va a los alumnos en cada evaluación y cómo queda su condición a la fecha de corte.",
)

ORDEN = {"asignatura": list(comp.COLORES_MATERIA)}
GRIS_TEXTO = "#52514e"

notas = comp.metrica("nota_final")
instrumentos = comp.metrica("promedio_por_instrumento")
rendidas = comp.metrica("notas_rendidas")
dist = comp.metrica("distribucion_condicion")

if instrumentos.empty:
    st.info(f"Al {comp.fmt_fecha(f.fecha_corte)} todavía no se tomó ninguna evaluación en "
            f"{f.materia.lower()}. Mové la fecha de corte para ver notas.", icon=":material/event_busy:")
    st.stop()

def en_dos_lineas(texto: str, largo: int = 16) -> str:
    """Parte los nombres largos en dos renglones para el eje x (sin rotar las etiquetas)."""
    if len(texto) <= largo or " " not in texto:
        return texto
    palabras = texto.split(" ")
    corte = min(range(1, len(palabras)), key=lambda i: abs(len(" ".join(palabras[:i])) - len(texto) / 2))
    return " ".join(palabras[:corte]) + "<br>" + " ".join(palabras[corte:])


instrumentos["nombre"] = instrumentos["instrumento"].map(comp.nombre_corto)
instrumentos["eje"] = instrumentos["nombre"].map(en_dos_lineas)
rendidas["nombre"] = rendidas["instrumento"].map(comp.nombre_corto)
materias = [m for m in f.materias if m in set(instrumentos["asignatura"])]

# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------
cuentan = instrumentos[~instrumentos["es_recuperatorio"]]
tasa_entrega = cuentan["rindieron"].sum() / cuentan["base"].sum() * 100
con_nota = notas[notas["rendidos"] > 0]
mas_bajo = cuentan.dropna(subset=["promedio_pct"]).nsmallest(1, "promedio_pct")
libre = dist.loc[dist["condicion"] == "Libre", "alumnos"].sum() / dist["alumnos"].sum() * 100

comp.tarjetas([
    dict(label="Nota promedio", value=f"{comp.num(notas['nota_pct'].mean(), 1)} / 100",
         help="Toda la base, con 0 en lo no rendido (D16-D17). Sobre 100 para comparar Álgebra con el resto."),
    dict(label="Nota (rindieron)",value=f"{comp.num(con_nota['nota_pct'].mean(), 1)} / 100",
         help=f"Solo los {comp.num(len(con_nota))} alumnos con al menos una evaluación rendida. La diferencia "
              "con la tarjeta anterior es el peso de los que no rinden."),
    dict(label="Tasa de entrega", value=comp.pct(tasa_entrega),
         help="Evaluaciones rendidas / (alumnos de la base × evaluaciones tomadas). No cuenta el recuperatorio."),
    dict(label="Promedio más bajo",
         value=comp.num(mas_bajo["promedio_pct"].iloc[0], 1) if len(mas_bajo) else "–",
         delta=mas_bajo["nombre"].iloc[0] if len(mas_bajo) else None, delta_color="off", delta_arrow="off",
         help="El instrumento con el promedio (sobre 100, solo quienes lo rindieron) más bajo."
              + ("" if f.asignatura else f" Materia: {mas_bajo['asignatura'].iloc[0]}." if len(mas_bajo) else "")),
    dict(label="🔴 Libre", value=comp.pct(libre),
         help="Alumnos de la base que a la fecha de corte están por debajo del corte de Regular."),
])

tab_inst, tab_dist, tab_cond, tab_tabla = st.tabs(["Por instrumento", "Distribución", "Condición", "Tabla"])

# ---------------------------------------------------------------------------
# Por instrumento: boxplot + % que lo rindió
# ---------------------------------------------------------------------------
with tab_inst:
    st.caption("Arriba, cada caja resume las notas (sobre 100) de **quienes rindieron** ese instrumento (D22): "
               "la línea del medio es la mediana, la punteada el promedio y los puntos sueltos, casos atípicos. "
               "Abajo, qué % de la base lo rindió. Un promedio alto con pocas entregas suele ser selección: "
               "rinden los que vienen bien.")
    for materia in materias:
        prom = instrumentos[instrumentos["asignatura"] == materia]
        notas_m = rendidas[rendidas["asignatura"] == materia]
        color = comp.COLORES_MATERIA[materia]
        st.subheader(materia)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.06)
        for fila in prom.itertuples():
            valores = notas_m.loc[notas_m["id_instrumento"] == fila.id_instrumento, "nota_pct_instrumento"]
            fig.add_trace(go.Box(
                y=valores, x=[fila.eje] * len(valores), name=fila.nombre, boxmean=True,
                marker_color=comp.NEUTRO if fila.es_recuperatorio else color, line_width=1.5,
                boxpoints="outliers", marker_size=4, showlegend=False,
                hovertemplate=f"{fila.nombre}<br>%{{y:.1f}}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Bar(
            x=prom["eje"], y=prom["pct_rindio"], showlegend=False,
            marker_color=[comp.NEUTRO if r else color for r in prom["es_recuperatorio"]], opacity=0.55,
            text=prom["pct_rindio"].map(lambda v: comp.pct(v, 0)), textposition="outside", cliponaxis=False,
            customdata=prom[["rindieron", "base", "nombre"]],
            hovertemplate="%{customdata[2]}<br>Lo rindieron %{customdata[0]} de %{customdata[1]} (%{y:.1f} %)"
                          "<extra></extra>"),
            row=2, col=1)
        fig.update_yaxes(title_text="Nota (sobre 100)", range=[-3, 103], row=1, col=1)
        fig.update_yaxes(title_text="% rindió", range=[0, 118], dtick=50, row=2, col=1)
        fig.update_xaxes(categoryorder="array", categoryarray=list(prom["eje"]), tickangle=0)
        fig.update_layout(height=470, margin=dict(t=16), bargap=0.45)
        st.plotly_chart(fig, width="stretch", key=f"box_{materia}")
        if prom["es_recuperatorio"].any():
            st.caption("En gris, el recuperatorio: su nota reemplaza a la original en la condición (D20), "
                       "pero acá se muestra aparte y la original queda como se rindió.")

# ---------------------------------------------------------------------------
# Distribución: histograma en la escala de la materia, por condición
# ---------------------------------------------------------------------------
with tab_dist:
    excluir = st.toggle("Excluir a quienes no rindieron ninguna evaluación", value=True,
                        help="Tienen 0 por no rendir, no por rendir mal: suelen ser alumnos que abandonaron.")
    hist = notas[notas["nota_final"].notna()]
    sin_rendir = int((hist["rendidos"] == 0).sum())
    if excluir:
        hist = hist[hist["rendidos"] > 0]
    condiciones = [c for c in comp.COLORES_CONDICION if c in set(hist["condicion"])]

    fig = make_subplots(rows=1, cols=len(materias), subplot_titles=materias, horizontal_spacing=0.06)
    for i, materia in enumerate(materias, start=1):
        escala = ESQUEMA[materia]["total_max"]
        ancho = escala / 20  # 20 barras en cualquier escala (5 puntos sobre 100, 6 sobre 120)
        h = hist[hist["asignatura"] == materia]
        h = h.assign(desde=(h["nota_final"].clip(0, escala - 1e-6) // ancho * ancho))
        barras = h.groupby(["desde", "condicion"]).size().rename("alumnos").reset_index()
        for cond in condiciones:
            b = barras[barras["condicion"] == cond]
            fig.add_trace(go.Bar(
                x=b["desde"] + ancho / 2, y=b["alumnos"], width=ancho * 0.92, name=cond,
                legendgroup=cond, showlegend=i == 1, marker_color=comp.COLORES_CONDICION[cond],
                customdata=[f"{comp.num(a, 0)} a {comp.num(a + ancho, 0)}" for a in b["desde"]],
                hovertemplate=f"{comp.ICONOS_CONDICION.get(cond, '')} {cond}<br>Nota de %{{customdata}}"
                              "<br>%{y} alumnos<extra></extra>"), row=1, col=i)
        for nombre, corte in ESQUEMA[materia]["cortes"].items():
            fig.add_vline(x=corte, row=1, col=i, line_width=1.5, line_color=GRIS_TEXTO,
                          line_dash="dot" if nombre == "Regular" else "dash")
        fig.update_xaxes(range=[0, escala], dtick=escala / 4, title_text=f"Nota (sobre {escala})", row=1, col=i)
    fig.update_yaxes(title_text="Alumnos", row=1, col=1)
    fig.update_layout(barmode="stack", height=400, bargap=0, legend=dict(title_text="", y=1.16),
                      margin=dict(t=80))
    st.plotly_chart(fig, width="stretch")
    st.caption("Cada materia en su propia escala (Álgebra sobre 120). Línea punteada: corte de **Regular**; "
               "línea de guiones: corte de **Promociona** (Álgebra y PyE 60 / 85; AED 60 / 90)."
               + (f" Se excluyen {comp.num(sin_rendir)} alumnos que no rindieron nada (tienen 0)." if excluir
                  else f" Incluye {comp.num(sin_rendir)} alumnos con 0 porque no rindieron nada."))

    st.subheader("Resumen estadístico")
    resumen = (hist.groupby("asignatura")["nota_final"]
                   .agg(alumnos="size", promedio="mean", desvio="std", minimo="min",
                        p25=lambda s: s.quantile(0.25), mediana="median", p75=lambda s: s.quantile(0.75),
                        maximo="max")
                   .reindex(materias).reset_index())
    resumen.insert(1, "escala", [ESQUEMA[m]["total_max"] for m in resumen["asignatura"]])
    st.dataframe(resumen, hide_index=True, width="stretch", column_config={
        "asignatura": "Materia", "escala": "Escala", "alumnos": "Alumnos",
        **{c: st.column_config.NumberColumn(n, format="%.1f") for c, n in
           [("promedio", "Promedio"), ("desvio", "Desvío"), ("minimo", "Mínimo"), ("p25", "Percentil 25"),
            ("mediana", "Mediana"), ("p75", "Percentil 75"), ("maximo", "Máximo")]}})

# ---------------------------------------------------------------------------
# Condición: hoy y evolución
# ---------------------------------------------------------------------------
with tab_cond:
    st.subheader("% por condición a la fecha de corte")
    conds = [c for c in comp.COLORES_CONDICION if c in set(dist["condicion"])]
    dist["etiqueta"] = comp.con_icono(dist["condicion"], comp.ICONOS_CONDICION)
    fig = px.bar(dist, x="pct", y="asignatura", color="condicion", orientation="h",
                 category_orders={**ORDEN, "condicion": conds}, color_discrete_map=comp.COLORES_CONDICION,
                 text=dist["pct"].map(lambda v: comp.pct(v, 0) if v >= 4 else ""),
                 custom_data=["etiqueta", "alumnos"], labels={"pct": "% de alumnos", "asignatura": "", "condicion": ""})
    fig.update_traces(hovertemplate="%{y}<br>%{customdata[0]}: %{customdata[1]} alumnos (%{x:.1f} %)<extra></extra>",
                      textposition="inside", insidetextanchor="middle", marker_line_width=2,
                      marker_line_color="white")
    fig.update_layout(barmode="stack", height=90 + 70 * len(f.materias), xaxis=dict(range=[0, 100], dtick=25),
                      bargap=0.35)
    st.plotly_chart(fig, width="stretch")

    st.subheader("Cómo se fue moviendo la condición")
    evo = comp.metrica("evolucion_condicion")
    evo = evo[evo["condicion"].isin(comp.COLORES_CONDICION)]
    evo["instrumentos"] = evo["instrumentos"].map(lambda s: " + ".join(comp.nombre_corto(x) for x in s.split(" + ")))
    fig = px.line(evo, x="fecha", y="pct", color="condicion", facet_col="asignatura", markers=True,
                  line_shape="hv", category_orders={**ORDEN, "condicion": conds},
                  color_discrete_map=comp.COLORES_CONDICION, custom_data=["instrumentos", "alumnos"],
                  labels={"fecha": "", "pct": "% de alumnos", "condicion": "", "asignatura": ""})
    fig.update_traces(hovertemplate="%{x|%d/%m}: %{fullData.name} %{y:.1f} % (%{customdata[1]} alumnos)<br>"
                                    "Después de: %{customdata[0]}<extra></extra>", line_width=2)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_yaxes(range=[0, 100], dtick=25)
    fig.update_xaxes(tickformat="%d/%m")
    fig.update_layout(height=380, legend=dict(y=1.16), margin=dict(t=80))
    st.plotly_chart(fig, width="stretch")
    st.caption("Un punto por cada fecha de evaluación ya tomada a la fecha de corte (D51): muestra la condición "
               "que tenía cada alumno ese día, con los instrumentos que había hasta entonces y 0 en lo no rendido. "
               "Las caídas de Promociona después de un parcial o un recuperatorio son las que conviene mirar.")

# ---------------------------------------------------------------------------
# Tabla
# ---------------------------------------------------------------------------
with tab_tabla:
    columnas = {
        "asignatura": "Materia", "nombre": "Instrumento", "fecha_instrumento": "Fecha",
        "puntaje_maximo": "Puntaje máximo", "rindieron": "Rindieron", "pct_rindio": "% de la base",
        "promedio_pct": "Promedio", "mediana_pct": "Mediana", "minimo_pct": "Mínimo", "maximo_pct": "Máximo",
        "pct_aprobada": "% aprobada",
    }
    tabla = instrumentos[list(columnas)].rename(columns=columnas)
    st.dataframe(tabla, hide_index=True, width="stretch", column_config={
        "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "% de la base": st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100),
        **{c: st.column_config.NumberColumn(format="%.1f") for c in
           ["Promedio", "Mediana", "Mínimo", "Máximo", "% aprobada"]}})
    st.caption("Promedio, mediana, mínimo y máximo sobre 100, solo entre quienes rindieron (D22). La fecha es la "
               "mediana de los intentos en la trazabilidad (D18). \"% aprobada\" sale de la columna Observaciones "
               "del Excel.")
    c1, c2 = st.columns(2)
    with c1:
        comp.boton_csv(tabla, f"rendimiento_por_instrumento_{f.fecha_corte:%Y%m%d}",
                       "Descargar resumen por instrumento")
    with c2:
        detalle = rendidas.drop(columns=["orden", "instrumento"]).rename(columns={"nombre": "instrumento"})
        comp.boton_csv(detalle, f"notas_por_alumno_{f.fecha_corte:%Y%m%d}", "Descargar notas por alumno")
