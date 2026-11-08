"""Dashboard 2 (del plan): Rendimiento académico.

Responde, a la fecha de corte: ¿qué instrumentos cuestan más?, ¿cuántos los
rinden?, ¿cómo se reparten las notas? y ¿cómo se fue moviendo la condición
(Libre / Regular / Promociona) a medida que se tomaron las evaluaciones?

  Tarjetas        fila 1: nota promedio (con y sin los 0, con el promedio de cada
                  materia abajo), tasa de entrega e instrumento con el promedio
                  más bajo. Fila 2: % de alumnos Libre, Regular y Promociona.
  Por instrumento chips con promedio, mínimo y máximo de cada instrumento y
                  boxplot (solo quienes lo rindieron, D22) con el % de la base
                  que lo rindió abajo.
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


def puntos(pct: float, maximo: float) -> str:
    """Nota sobre 100 -> puntos del instrumento, sin ',0' si da entero (75 sobre 100 con máximo 10 -> '7,5')."""
    p = round(pct * maximo / 100, 1)
    return comp.num(p, 0 if p == int(p) else 1)


def chip_instrumento(fila, color: str) -> dict:
    """Chip de un instrumento: promedio, mínimo y máximo obtenidos (solo quienes lo rindieron, D22),
    sobre 100 y, si el instrumento no es sobre 100 (Álgebra), también en sus puntos."""
    if not fila.rindieron:
        return dict(titulo=fila.nombre, valor="–", detalle="nadie lo rindió", color=comp.NEUTRO)
    maximo = fila.puntaje_maximo
    en_puntos = pd.notna(maximo) and maximo != 100
    detalle = [f"mín {comp.num(fila.minimo_pct, 0)} · máx {comp.num(fila.maximo_pct, 0)} (sobre 100)"]
    if en_puntos:
        detalle.insert(0, f"{puntos(fila.promedio_pct, maximo)} de {comp.num(maximo, 0)} pts en promedio")
        detalle.append(f"mín {puntos(fila.minimo_pct, maximo)} · máx {puntos(fila.maximo_pct, maximo)} "
                       f"(de {comp.num(maximo, 0)} pts)")
    detalle.append(f"rindieron {comp.num(fila.rindieron)}")
    return dict(
        titulo=fila.nombre, valor=comp.num(fila.promedio_pct, 1), unidad="/ 100 prom.", detalle=detalle,
        color=comp.NEUTRO if fila.es_recuperatorio else color,
        ayuda=f"{fila.nombre}: promedio, nota más baja y más alta OBTENIDAS por los {fila.rindieron} que lo "
              "rindieron (D22), no los límites de la escala. Los que no lo rindieron no cuentan."
              + (f" El instrumento vale {comp.num(maximo, 0)} puntos." if en_puntos else "")
              + (" Recuperatorio." if fila.es_recuperatorio else ""))


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


def por_materia(df: pd.DataFrame) -> str | None:
    """Con varias materias, el promedio (sobre 100) de cada una en una línea: 'ALG 52 · AED 61 · PYE 58'."""
    if len(materias) < 2:
        return None
    prom = df.groupby("asignatura")["nota_pct"].mean()
    return " · ".join(f"{comp.SIGLAS[m]} {comp.num(prom[m], 0)}" for m in materias if pd.notna(prom.get(m)))


comp.tarjetas([
    dict(label="Nota promedio", value=f"{comp.num(notas['nota_pct'].mean(), 1)} / 100",
         delta=por_materia(notas), delta_color="off", delta_arrow="off",
         help="Toda la base, con 0 en lo no rendido (D16-D17). Sobre 100 para comparar Álgebra con el resto."
              + (" Abajo, el promedio de cada materia." if len(materias) > 1 else "")),
    dict(label="Nota (rindieron)",value=f"{comp.num(con_nota['nota_pct'].mean(), 1)} / 100",
         delta=por_materia(con_nota), delta_color="off", delta_arrow="off",
         help=f"Solo los {comp.num(len(con_nota))} alumnos con al menos una evaluación rendida. La diferencia "
              "con la tarjeta anterior es el peso de los que no rinden."
              + (" Abajo, el promedio de cada materia." if len(materias) > 1 else "")),
    dict(label="Tasa de entrega", value=comp.pct(tasa_entrega),
         help="Evaluaciones rendidas / (alumnos de la base × evaluaciones tomadas). No cuenta el recuperatorio."),
    dict(label="Promedio más bajo",
         value=comp.num(mas_bajo["promedio_pct"].iloc[0], 1) if len(mas_bajo) else "–",
         delta=mas_bajo["nombre"].iloc[0] if len(mas_bajo) else None, delta_color="off", delta_arrow="off",
         help="El instrumento con el promedio (sobre 100, solo quienes lo rindieron) más bajo."
              + ("" if f.asignatura else f" Materia: {mas_bajo['asignatura'].iloc[0]}." if len(mas_bajo) else "")),
])

# Segunda fila: % de la base en cada condición (sumando las materias elegidas).
total_base = dist["alumnos"].sum()
AYUDA_CONDICION = {
    "Libre": "Por debajo del corte de Regular (60 en las tres materias; en Álgebra, 60 de 120).",
    "Regular": "Entre el corte de Regular y el de Promociona (Álgebra y PyE de 60 a < 85; AED de 60 a < 90).",
    "Promociona": "Desde el corte de Promociona (Álgebra y PyE ≥ 85; AED ≥ 90).",
}
fila_condicion = []
for cond, ayuda in AYUDA_CONDICION.items():
    d_cond = dist[dist["condicion"] == cond]
    n_cond = int(d_cond["alumnos"].sum())
    detalle = (" Por materia: " + " · ".join(f"{comp.SIGLAS[r.asignatura]} {comp.pct(r.pct, 0)}"
                                             for r in d_cond.itertuples()) + "." if len(f.materias) > 1 else "")
    fila_condicion.append(dict(
        label=f"{comp.ICONOS_CONDICION[cond]} {cond}",
        value=comp.pct(n_cond / total_base * 100 if total_base else 0),
        delta=f"{comp.num(n_cond)} de {comp.num(total_base)} alumnos", delta_color="off", delta_arrow="off",
        help=f"Alumnos de la base a la fecha de corte, con 0 en lo no rendido (D16-D17). {ayuda}{detalle}"))
comp.tarjetas(fila_condicion)

tab_inst, tab_dist, tab_cond, tab_tabla = st.tabs(["Por instrumento", "Distribución", "Condición", "Tabla"])

# ---------------------------------------------------------------------------
# Por instrumento: boxplot + % que lo rindió
# ---------------------------------------------------------------------------
with tab_inst:
    st.caption("Los chips dan el promedio y la nota más baja y más alta **obtenidas** por quienes lo rindieron, "
               "sobre 100 y, en Álgebra, también en los puntos del instrumento. "
               "En el gráfico, cada caja resume las notas (sobre 100) de **quienes rindieron** ese instrumento (D22): "
               "la línea del medio es la mediana, la punteada el promedio y los puntos sueltos, casos atípicos. "
               "Abajo, qué % de la base lo rindió. Un promedio alto con pocas entregas suele ser selección: "
               "rinden los que vienen bien.")
    for materia in materias:
        prom = instrumentos[instrumentos["asignatura"] == materia]
        notas_m = rendidas[rendidas["asignatura"] == materia]
        color = comp.COLORES_MATERIA[materia]
        st.subheader(materia)
        comp.chips([chip_instrumento(fila, color) for fila in prom.itertuples()])
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
