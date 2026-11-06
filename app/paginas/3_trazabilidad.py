"""Dashboard 3 (del plan): Trazabilidad.

Responde: ¿qué hacen los alumnos cuando entran al aula?, ¿cuándo se conectan
(día y hora)?, ¿cómo evolucionó la actividad a lo largo de la cursada? y ¿cuánto
se mueve la actividad alrededor de cada evaluación?

  Período         filtro propio de la página (como en Participación, D53) que termina
                  en la fecha de corte de la barra lateral.
  Tarjetas        interacciones, por día, por alumno, tipo más frecuente y momento pico.
  Línea de tiempo interacciones por día / semana / mes, por materia (líneas) y por tipo
                  de interacción (barras apiladas), con las evaluaciones marcadas.
  Tipos           % por tipo en cada materia, mapa de árbol tipo > sección > acción y
                  tabla de acciones con CSV.
  Días y horarios mapa de calor día × hora y perfiles por hora y por día de cada materia.
  Evaluaciones    actividad en los días anteriores y posteriores a cada evaluación,
                  relativa a un día típico de la materia (D54).

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes as comp
from src.metricas import CATEGORIAS, DIAS

f = comp.encabezado(
    "Trazabilidad",
    "Qué hacen los alumnos en el aula virtual y cuándo. Cada clic que registra el LMS es una **interacción**; "
    "las acciones se agrupan en seis tipos (contenido, navegación, evaluación, comunicación, notas y agenda).",
)

ORDEN = {"asignatura": list(comp.COLORES_MATERIA), "categoria": CATEGORIAS}
# Un color fijo por tipo de interacción, en el orden de la paleta (D48, D54). Los tipos y
# las materias nunca comparten un mismo gráfico, así que no se confunden.
COLORES_CATEGORIA = dict(zip(CATEGORIAS, comp.CATEGORICA))
DIAS_CORTOS = [d[:3] for d in DIAS]

# ---------------------------------------------------------------------------
# Período (filtro propio de la página, como en Participación, D53)
# ---------------------------------------------------------------------------
inicio_datos, _ = comp.rango_fechas()
PERIODOS = ["Toda la cursada", "Últimas 4 semanas", "Últimas 2 semanas", "Desde una fecha"]
c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
periodo = c1.segmented_control("Período", PERIODOS, default=PERIODOS[0], key="traz_periodo") or PERIODOS[0]
if periodo == "Desde una fecha":
    st.session_state.setdefault("traz_desde", max(inicio_datos, f.fecha_corte - timedelta(days=27)))
    st.session_state["traz_desde"] = min(max(st.session_state["traz_desde"], inicio_datos), f.fecha_corte)
    desde = c2.date_input("Desde", min_value=inicio_datos, max_value=f.fecha_corte, key="traz_desde",
                          format="DD/MM/YYYY")
elif periodo == "Toda la cursada":
    desde = None
else:
    semanas = 4 if "4" in periodo else 2
    desde = max(inicio_datos, f.fecha_corte - timedelta(days=7 * semanas - 1))
inicio_periodo = desde or inicio_datos
texto_periodo = f"del {comp.fmt_fecha(inicio_periodo)} al {comp.fmt_fecha(f.fecha_corte)}"
SUFIJO = f"{inicio_periodo:%Y%m%d}_{f.fecha_corte:%Y%m%d}"

categorias = comp.metrica("interacciones_por_categoria", desde=desde)
calor = comp.metrica("mapa_calor", desde=desde)
base = comp.metrica("base")
total = int(categorias["eventos"].sum())

if total == 0:
    st.info(f"No hay interacciones de alumnos {texto_periodo}.", icon=":material/event_busy:")
    st.stop()

# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------
dias_periodo = (pd.Timestamp(f.fecha_corte) - pd.Timestamp(inicio_periodo)).days + 1
por_tipo = categorias.groupby("categoria")["eventos"].sum().sort_values(ascending=False)
tipo_top = por_tipo.index[0]
pico = calor.loc[calor["eventos"].idxmax()]
franja = calor.groupby("hora")["eventos"].sum()
hora_pico = int(franja.idxmax())
comp.tarjetas([
    dict(label="Interacciones", value=comp.num(total),
         delta=f"en {comp.num(dias_periodo)} días", delta_color="off", delta_arrow="off",
         help="Clics de los alumnos de la base registrados por el LMS en el período (solo perfil Alumnos, D10). "
              "Sin las filas duplicadas exactas de la trazabilidad (D7)."),
    dict(label="Por día", value=comp.num(total / dias_periodo, 0),
         help="Interacciones del período divididas por los días calendario (con fines de semana)."),
    dict(label="Por alumno", value=comp.num(total / max(len(base), 1), 0),
         delta=f"base de {comp.num(len(base))}", delta_color="off", delta_arrow="off",
         help="Total del período dividido por la base de alumnos (D11). Un alumno que cursa dos materias "
              "cuenta dos veces."),
    dict(label="Tipo más frecuente", value=tipo_top,
         delta=f"{comp.pct(por_tipo.iloc[0] / total * 100, 0)} de las interacciones", delta_color="off",
         delta_arrow="off", help="Categoría de dim_accion con más interacciones en el período."),
    dict(label="Momento pico", value=f"{DIAS_CORTOS[int(pico['dia_semana'])]} {int(pico['hora'])} h",
         delta=f"hora pico: {hora_pico} a {hora_pico + 1} h", delta_color="off", delta_arrow="off",
         help="Día de la semana y hora con más interacciones en el período (mapa de calor)."),
])
st.caption(f"Interacciones {texto_periodo}.")

tab_tiempo, tab_tipos, tab_horarios, tab_evals = st.tabs(
    ["Línea de tiempo", "Tipos de interacción", "Días y horarios", "Alrededor de las evaluaciones"])

FRECUENCIAS = {"Día": "D", "Semana": "W", "Mes": "M"}
FORMATO_X = {"D": "%d/%m", "W": "sem. del %d/%m", "M": "%m/%Y"}


def marcar_evaluaciones(fig: go.Figure, color_por_materia: bool) -> None:
    """Triángulos en la base del gráfico en la fecha de cada evaluación (D18)."""
    evals = comp.metrica("fechas_evaluaciones")
    if desde is not None:
        evals = evals[evals["fecha_instrumento"] >= pd.Timestamp(desde)]
    for asig, g in evals.groupby("asignatura"):
        color = comp.COLORES_MATERIA[asig] if color_por_materia else comp.NEUTRO
        fig.add_trace(go.Scatter(
            x=g["fecha_instrumento"], y=[0] * len(g), mode="markers", name=f"Evaluación {comp.SIGLAS[asig]}",
            marker=dict(symbol="triangle-up", size=11, color=color, line=dict(color="white", width=1)),
            text=g["instrumento"].str.replace(r"^\W+", "", regex=True),
            hovertemplate="%{x|%d/%m}: %{text}<extra>" + asig + "</extra>",
            showlegend=color_por_materia))


# ---------------------------------------------------------------------------
# Línea de tiempo
# ---------------------------------------------------------------------------
with tab_tiempo:
    c1, c2, c3 = st.columns([1.2, 1.6, 1], vertical_alignment="bottom")
    frecuencia = c1.segmented_control("Agrupar por", list(FRECUENCIAS), default="Semana",
                                      key="traz_frecuencia") or "Semana"
    relativo = c2.segmented_control("Medida", ["Total", "Por alumno"], default="Total", key="traz_medida") \
        or "Total"
    marcar = c3.toggle("Marcar evaluaciones", value=True, key="traz_marcar")
    frec = FRECUENCIAS[frecuencia]
    col = "eventos" if relativo == "Total" else "eventos_por_alumno"
    eje = "Interacciones" if relativo == "Total" else "Interacciones por alumno"
    hover = "%{y:,}" if relativo == "Total" else "%{y:.1f} por alumno"

    st.subheader("Por materia")
    evo = comp.metrica("evolucion_interacciones", frecuencia=frec, desde=desde)
    fig = px.line(evo, x="periodo", y=col, color="asignatura", markers=frec != "D", category_orders=ORDEN,
                  color_discrete_map=comp.COLORES_MATERIA, labels={"periodo": "", col: eje, "asignatura": ""})
    fig.update_traces(hovertemplate=f"%{{x|{FORMATO_X[frec]}}}<br>%{{fullData.name}}: {hover}<extra></extra>",
                      line_width=2)
    if marcar:
        marcar_evaluaciones(fig, color_por_materia=True)
    fig.update_xaxes(tickformat="%m/%Y" if frec == "M" else "%d/%m")
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(height=380, hovermode="closest")
    st.plotly_chart(fig, width="stretch")
    st.caption("**Por alumno** divide por la base de cada materia, para comparar materias de distinto tamaño. "
               "Las semanas empiezan el lunes y el último período puede estar incompleto. Los triángulos son las "
               "fechas de las evaluaciones (D18).")

    st.subheader("Por tipo de interacción")
    apilado = st.toggle("Ver en % de cada período", key="traz_pct",
                        help="Cada barra suma 100 %: muestra cómo cambia la mezcla de tipos, no el volumen.")
    tipos = comp.metrica("evolucion_interacciones", frecuencia=frec, desde=desde, por="categoria")
    y = "pct_periodo" if apilado else col
    fig = px.bar(tipos, x="periodo", y=y, color="categoria", category_orders=ORDEN,
                 color_discrete_map=COLORES_CATEGORIA,
                 labels={"periodo": "", y: "% del período" if apilado else eje, "categoria": ""})
    formato = "%{y:.1f} %" if apilado else hover
    fig.update_traces(hovertemplate=f"%{{x|{FORMATO_X[frec]}}}<br>%{{fullData.name}}: {formato}<extra></extra>",
                      marker_line_width=1, marker_line_color="white")
    if marcar:
        marcar_evaluaciones(fig, color_por_materia=False)
    fig.update_xaxes(tickformat="%m/%Y" if frec == "M" else "%d/%m")
    fig.update_layout(barmode="stack", height=380, bargap=0.15, hovermode="closest")
    st.plotly_chart(fig, width="stretch")
    st.caption(f"Suma {f.materia.lower() if f.asignatura is None else f.materia}. Los triángulos grises son las "
               "evaluaciones. En las semanas de evaluación crece la parte de **Evaluación**; el resto del tiempo "
               "domina leer contenido y navegar.")

# ---------------------------------------------------------------------------
# Tipos de interacción
# ---------------------------------------------------------------------------
with tab_tipos:
    st.subheader("Qué hacen en el aula")
    c1, c2 = st.columns([1, 1.3])
    with c1:
        mezcla = categorias.groupby(["asignatura", "categoria"], as_index=False)["eventos"].sum()
        mezcla["pct"] = mezcla["eventos"] / mezcla.groupby("asignatura")["eventos"].transform("sum") * 100
        fig = px.bar(mezcla, x="pct", y="asignatura", color="categoria", orientation="h",
                     category_orders=ORDEN, color_discrete_map=COLORES_CATEGORIA, custom_data=["eventos"],
                     text=mezcla["pct"].map(lambda v: comp.pct(v, 0) if v >= 7 else ""),
                     labels={"pct": "% de las interacciones de la materia", "asignatura": "", "categoria": ""})
        fig.update_traces(hovertemplate="%{y}<br>%{fullData.name}: %{customdata[0]:,} (%{x:.1f} %)<extra></extra>",
                          textposition="inside", insidetextanchor="middle", marker_line_width=2,
                          marker_line_color="white")
        fig.update_yaxes(ticktext=[comp.SIGLAS[a] for a in f.materias], tickvals=f.materias)
        fig.update_xaxes(range=[0, 100])
        fig.update_layout(barmode="stack", height=160 + 70 * len(f.materias), bargap=0.3)
        st.plotly_chart(fig, width="stretch")
        st.caption("Cada barra suma 100 %. Comparar la parte de **Evaluación** entre materias muestra cuánto pesan "
                   "las actividades evaluadas en el uso del aula.")
    acciones = comp.metrica("interacciones_por_accion", desde=desde)
    with c2:
        arbol = acciones.assign(seccion=acciones["seccion"].fillna("(sin sección)"))
        fig = px.treemap(arbol, path=[px.Constant("Todas"), "categoria", "seccion", "accion"], values="eventos",
                         color="categoria", color_discrete_map={**COLORES_CATEGORIA, "(?)": "#f0efec"})
        fig.update_traces(hovertemplate="%{label}<br>%{value:,} interacciones<br>%{percentRoot:.1%} del total"
                                        "<extra></extra>", root_color="#f0efec", marker_line_color="white",
                          marker_line_width=2)
        fig.update_layout(height=160 + 70 * max(len(f.materias), 3), margin=dict(t=8, l=0, r=0, b=0))
        st.plotly_chart(fig, width="stretch")
        st.caption("Tipo > sección > acción. Hacer clic en un recuadro para entrar; clic arriba para volver.")

    st.subheader("Acciones más frecuentes")
    elegidas = st.multiselect("Tipo de interacción", CATEGORIAS, key="traz_categorias", placeholder="Todos")
    vista = acciones[acciones["categoria"].isin(elegidas)] if elegidas else acciones
    columnas = {"categoria": "Tipo", "seccion": "Sección", "accion": "Acción", "eventos": "Interacciones",
                "pct": "% del total", "alumnos": "Alumnos", "pct_alumnos": "% de la base"}
    tabla = vista[list(columnas)].rename(columns=columnas)
    st.dataframe(tabla, hide_index=True, width="stretch", height=380, column_config={
        "% del total": st.column_config.NumberColumn(format="%.2f %%"),
        "% de la base": st.column_config.ProgressColumn(format="%.0f %%", min_value=0, max_value=100)})
    st.caption(f"{comp.num(len(vista))} acciones. **Alumnos** cuenta a los de la base que hicieron esa acción al "
               "menos una vez en el período: una acción con muchas interacciones pero pocos alumnos la usa un grupo "
               "chico muy intensamente. 'Acceder' a Inicio y a Programa son filas distintas (D54).")
    comp.boton_csv(tabla, f"trazabilidad_acciones_{SUFIJO}", "Descargar acciones")

# ---------------------------------------------------------------------------
# Días y horarios
# ---------------------------------------------------------------------------
with tab_horarios:
    st.subheader("Mapa de calor: día de la semana × hora")
    en_pct = st.toggle("Ver en % del total", key="traz_calor_pct")
    matriz = calor.pivot(index="dia_semana", columns="hora", values="eventos").reindex(index=range(7))
    if en_pct:
        matriz = matriz / matriz.values.sum() * 100
    fig = go.Figure(go.Heatmap(
        z=matriz.values, x=[f"{h} h" for h in matriz.columns], y=DIAS, colorscale=comp.SECUENCIAL,
        xgap=2, ygap=2, colorbar=dict(title="%" if en_pct else "Interacc.", thickness=12),
        hovertemplate="%{y} de %{x}: %{z:" + (".2f} %" if en_pct else ",}") + "<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=340, xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch")
    noche = calor.loc[calor["hora"].between(18, 23), "eventos"].sum() / total * 100
    finde = calor.loc[calor["dia_semana"] >= 5, "eventos"].sum() / total * 100
    st.caption(f"Suma {f.materia.lower() if f.asignatura is None else f.materia}, en la hora del servidor del LMS. "
               f"El {comp.pct(noche, 0)} de las interacciones cae entre las 18 y las 24 h y el {comp.pct(finde, 0)} "
               "en fin de semana: es el horario en que conviene publicar material o avisos y en el que más se "
               "aprovecharía una consulta en línea.")

    st.subheader("Perfil de cada materia")
    perfiles = pd.concat([comp.metrica("mapa_calor", asignatura=a, desde=desde).assign(asignatura=a)
                          for a in f.materias])
    c1, c2 = st.columns(2)
    with c1:
        por_hora = perfiles.groupby(["asignatura", "hora"], as_index=False)["eventos"].sum()
        por_hora["pct"] = por_hora["eventos"] / por_hora.groupby("asignatura")["eventos"].transform("sum") * 100
        fig = px.line(por_hora, x="hora", y="pct", color="asignatura", markers=True, category_orders=ORDEN,
                      color_discrete_map=comp.COLORES_MATERIA,
                      labels={"hora": "Hora del día", "pct": "% de las interacciones de la materia", "asignatura": ""})
        fig.update_traces(hovertemplate="%{x} h · %{fullData.name}: %{y:.1f} %<extra></extra>", line_width=2,
                          marker_size=6)
        fig.update_xaxes(dtick=3)
        fig.update_yaxes(rangemode="tozero")
        fig.update_layout(height=340)
        st.plotly_chart(fig, width="stretch")
    with c2:
        por_dia = perfiles.groupby(["asignatura", "dia_semana"], as_index=False)["eventos"].sum()
        por_dia["pct"] = por_dia["eventos"] / por_dia.groupby("asignatura")["eventos"].transform("sum") * 100
        por_dia["dia"] = por_dia["dia_semana"].map(dict(enumerate(DIAS_CORTOS)))
        fig = px.bar(por_dia, x="dia", y="pct", color="asignatura", barmode="group",
                     category_orders={**ORDEN, "dia": DIAS_CORTOS}, color_discrete_map=comp.COLORES_MATERIA,
                     labels={"dia": "", "pct": "% de las interacciones de la materia", "asignatura": ""})
        fig.update_traces(hovertemplate="%{x} · %{fullData.name}: %{y:.1f} %<extra></extra>")
        fig.update_layout(height=340, bargap=0.2, bargroupgap=0.05)
        st.plotly_chart(fig, width="stretch")
    fuertes = por_dia.loc[por_dia.groupby("asignatura")["pct"].idxmax()]
    dia_fuerte = " · ".join(f"**{comp.SIGLAS[r.asignatura]}**: {DIAS[int(r.dia_semana)].lower()} "
                            f"({comp.pct(r.pct, 0)})" for r in fuertes.itertuples())
    st.caption(f"Día con más actividad de cada materia: {dia_fuerte}. Si cada materia tiene su propio día fuerte, "
               "probablemente es el día de la clase o el de la publicación del material: el aula se usa como "
               "complemento de la cursada y no de forma pareja durante la semana. "
               "En % de las interacciones de cada materia, para comparar el horario sin que pese el tamaño. Los días "
               "de la semana no aparecen la misma cantidad de veces en el período (puede haber uno más de algún día), "
               "así que diferencias chicas entre días no son significativas.")

# ---------------------------------------------------------------------------
# Alrededor de las evaluaciones (D54)
# ---------------------------------------------------------------------------
MEDIDAS_EVAL = {
    "Relativa a un día típico": ("relativo", "Veces un día típico", "%{y:.2f} × un día típico"),
    "Interacciones por alumno": ("eventos_por_alumno", "Interacciones por alumno", "%{y:.2f} por alumno"),
    "Solo de evaluación, por alumno": ("evaluacion_por_alumno", "Interacciones de evaluación por alumno",
                                       "%{y:.2f} por alumno"),
}
with tab_evals:
    st.markdown("¿Los alumnos estudian con tiempo o el día antes? Se toma cada evaluación ya tomada a la fecha de "
                "corte y se mira la actividad de su materia en los días de alrededor. El **día 0** es la fecha de la "
                "evaluación (la mediana de las realizaciones, D18). Este análisis usa toda la cursada hasta el "
                "corte: no se recorta por el período.")
    c1, c2 = st.columns([1.6, 1.4], vertical_alignment="bottom")
    medida = c1.selectbox("Medida", list(MEDIDAS_EVAL), key="traz_eval_medida")
    antes, despues = c2.slider("Días antes y después", -14, 7, (-7, 3), key="traz_eval_ventana")
    col, eje, hover = MEDIDAS_EVAL[medida]
    alrededor = comp.metrica("actividad_alrededor_evaluaciones", dias_antes=max(-antes, 0),
                             dias_despues=max(despues, 0))
    alrededor = alrededor[alrededor["dia_relativo"].between(antes, despues)]

    if alrededor.empty:
        st.info("Todavía no hay evaluaciones tomadas a la fecha de corte.", icon=":material/event_busy:")
    else:
        prom = alrededor.groupby(["asignatura", "dia_relativo"], as_index=False) \
                        .agg(valor=(col, "mean"), evaluaciones=("id_instrumento", "nunique"))
        fig = px.line(prom, x="dia_relativo", y="valor", color="asignatura", markers=True, category_orders=ORDEN,
                      color_discrete_map=comp.COLORES_MATERIA, custom_data=["evaluaciones"],
                      labels={"dia_relativo": "Días respecto de la evaluación", "valor": eje, "asignatura": ""})
        fig.update_traces(hovertemplate="Día %{x}<br>%{fullData.name}: " + hover
                                        + " (promedio de %{customdata[0]} evaluaciones)<extra></extra>",
                          line_width=2, marker_size=8)
        fig.add_vline(x=0, line_dash="dot", line_color=comp.NEUTRO, annotation_text="evaluación",
                      annotation_position="top")
        if col == "relativo":
            fig.add_hline(y=1, line_dash="dash", line_color=comp.NEUTRO, annotation_text="día típico",
                          annotation_position="bottom right")
        fig.update_xaxes(dtick=1)
        fig.update_yaxes(rangemode="tozero")
        fig.update_layout(height=380)
        st.plotly_chart(fig, width="stretch")

        rel = alrededor.groupby(["asignatura", "dia_relativo"])["relativo"].mean()
        frases = []
        for asig in [a for a in f.materias if a in rel.index.get_level_values(0)]:
            r = rel.loc[asig]
            frases.append(f"**{comp.SIGLAS[asig]}**: pico el día {int(r.idxmax())} "
                          f"({comp.num(r.max(), 1)} × un día típico)")
        st.caption("Promedio de las evaluaciones de cada materia; **1** es un día típico de la materia (promedio "
                   "diario de la cursada). " + " · ".join(frases) + ". Un pico en los días previos indica que se "
                   "estudia para la evaluación; un pico en el día 0 o una actividad plana, que la evaluación "
                   "queda abierta varios días y se resuelve sin preparación especial (típico de las "
                   "autoevaluaciones). Ojo: en PyE las evaluaciones están a pocos días entre sí, así que las "
                   "ventanas se superponen.")

        st.subheader("Evaluación por evaluación")
        materia_eval = st.selectbox("Materia", [a for a in f.materias if a in set(alrededor["asignatura"])],
                                    key="traz_eval_materia")
        g = alrededor[alrededor["asignatura"] == materia_eval].copy()
        g["nombre"] = g["instrumento"].str.replace(r"^\W+", "", regex=True).str.strip() + " (" + \
            g["fecha_instrumento"].dt.strftime("%d/%m") + ")"
        orden_filas = list(dict.fromkeys(g.sort_values("fecha_instrumento")["nombre"]))
        matriz = g.pivot(index="nombre", columns="dia_relativo", values=col).reindex(orden_filas)
        fig = go.Figure(go.Heatmap(
            z=matriz.values, x=[str(c) for c in matriz.columns], y=matriz.index, colorscale=comp.SECUENCIAL,
            xgap=2, ygap=2, colorbar=dict(title="", thickness=12),
            hovertemplate="%{y}<br>Día %{x}: %{z:.2f}<extra></extra>"))
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(height=120 + 38 * len(matriz), xaxis=dict(title="Días respecto de la evaluación",
                                                                    showgrid=False), yaxis=dict(showgrid=False))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"{eje} en cada día alrededor de cada evaluación de {materia_eval}. Las celdas vacías son días "
                   "fuera de los datos (antes del inicio o después de la fecha de corte).")
        comp.boton_csv(g.drop(columns=["nombre"]), f"trazabilidad_evaluaciones_{comp.SIGLAS[materia_eval]}_"
                       f"{f.fecha_corte:%Y%m%d}", "Descargar estos datos")
