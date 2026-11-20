"""Dashboard 3 (del plan): Trazabilidad.

Responde: ¿qué hacen los alumnos cuando entran al aula?, ¿cuándo se conectan
(día y hora)?, ¿cómo evolucionó la actividad a lo largo de la cursada? y ¿cuánto
se mueve la actividad alrededor de cada evaluación?

  Período         filtro propio de la página (como en Participación, D53) que termina
                  en la fecha de corte de la barra lateral.
  Tarjetas        interacciones (y por día), por alumno, tipo más frecuente y momento pico,
                  más una lectura con el dato principal (noche y fin de semana).
  Línea de tiempo interacciones por día / semana / mes, por materia (líneas) y por tipo
                  de interacción (barras apiladas), con las evaluaciones marcadas.
  Tipos           % por tipo en cada materia, tabla de acciones con CSV y mapa de árbol
                  tipo > sección > acción.
  Días y horarios mapa de calor día × hora y perfil por día o por hora de cada materia.
  Evaluaciones    actividad en los días anteriores y posteriores a cada evaluación,
                  relativa a un día típico de la materia (D62), con un resumen por materia.

Diseño (D63): cada bloque es una tarjeta con título, explicación en una línea y, debajo
del gráfico, una nota con lo que se ve. Los textos de las notas se calculan con los datos.
Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes_trazabilidad as comp
from src.metricas import CATEGORIAS, DIAS

f = comp.encabezado(
    "Trazabilidad",
    "Qué hacen los alumnos en el aula y cuándo. Cada clic que registra el LMS es una interacción, agrupada en "
    "seis tipos: contenido, navegación, evaluación, comunicación, notas y agenda.",
)

ORDEN = {"asignatura": list(comp.COLORES_MATERIA), "categoria": CATEGORIAS}
COLORES_CATEGORIA = comp.COLORES_CATEGORIA
DIAS_CORTOS = [d[:3] for d in DIAS]
SIN_BARRA = {"displayModeBar": False}
NOMBRE_TODAS = "las tres materias" if f.asignatura is None else comp.CORTOS[f.asignatura]


def grafico(fig: go.Figure, alto: int) -> None:
    comp.grafico(fig, alto, config=SIN_BARRA)   # con la plantilla tfi_trazabilidad


def leyenda_materias(linea: bool = True) -> None:
    comp.leyenda({comp.CORTOS[a]: comp.COLORES_MATERIA[a] for a in f.materias}, linea=linea)


def sin_emoji(serie: pd.Series) -> pd.Series:
    return serie.str.replace(r"^\W+", "", regex=True).str.strip()


# ---------------------------------------------------------------------------
# Período (filtro propio de la página, como en Participación, D53)
# ---------------------------------------------------------------------------
inicio_datos, _ = comp.rango_fechas()
PERIODOS = ["Toda la cursada", "Últimas 4 semanas", "Últimas 2 semanas", "Desde una fecha"]
c1, c2, c3 = st.columns([2.6, 1, 1.1], vertical_alignment="bottom")
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
dias_periodo = (pd.Timestamp(f.fecha_corte) - pd.Timestamp(inicio_periodo)).days + 1
texto_periodo = f"del {comp.fmt_fecha(inicio_periodo)} al {comp.fmt_fecha(f.fecha_corte)}"
c3.markdown(comp.chip(f"{inicio_periodo:%d/%m} → {f.fecha_corte:%d/%m} · {comp.num(dias_periodo)} días", gris=True),
            unsafe_allow_html=True)
SUFIJO = f"{inicio_periodo:%Y%m%d}_{f.fecha_corte:%Y%m%d}"

categorias = comp.metrica("interacciones_por_categoria", desde=desde)
calor = comp.metrica("mapa_calor", desde=desde)
base = comp.metrica("base")
total = int(categorias["eventos"].sum())

if total == 0:
    st.info(f"No hay interacciones de alumnos {texto_periodo}.", icon=":material/event_busy:")
    st.stop()

# ---------------------------------------------------------------------------
# Tarjetas y lectura
# ---------------------------------------------------------------------------
por_tipo = categorias.groupby("categoria")["eventos"].sum().sort_values(ascending=False)
tipo_top = por_tipo.index[0]
pico = calor.loc[calor["eventos"].idxmax()]
dia_pico, hora_pico = DIAS[int(pico["dia_semana"])], int(pico["hora"])
comp.tarjetas([
    dict(label="Interacciones", value=comp.num(total),
         delta=f"{comp.num(total / dias_periodo)} por día", delta_color="off", delta_arrow="off",
         help="Clics de los alumnos de la base registrados por el LMS en el período (solo perfil Alumnos), "
              "sin las filas duplicadas exactas. Por día divide por los días calendario, con fines de semana."),
    dict(label="Por alumno", value=comp.num(total / max(len(base), 1)),
         delta=f"sobre {comp.num(len(base))} de la base", delta_color="off", delta_arrow="off",
         help="Total del período dividido por la base de alumnos. Un alumno que cursa dos materias "
              "cuenta dos veces."),
    dict(label="Tipo más frecuente", value=tipo_top,
         delta=f"{comp.pct(por_tipo.iloc[0] / total * 100, 0)} de los clics", delta_color="off",
         delta_arrow="off", help="Categoría de dim_accion con más interacciones en el período."),
    dict(label="Momento pico", value=f"{dia_pico} {hora_pico} h",
         delta=f"franja de {hora_pico} a {hora_pico + 1} h", delta_color="off", delta_arrow="off",
         help="Día de la semana y hora con más interacciones en el período (mapa de calor)."),
])

noche = calor.loc[calor["hora"].between(18, 23), "eventos"].sum() / total * 100
finde = calor.loc[calor["dia_semana"] >= 5, "eventos"].sum() / total * 100
manana = calor.loc[calor["hora"].between(6, 11), "eventos"].sum() / total * 100
if noche >= 35 or finde >= 30:
    titulo_lectura = "El aula se usa de noche y los fines de semana:" if noche >= 35 and finde >= 30 else (
        "El aula se usa de noche:" if noche >= 35 else "El aula se usa mucho los fines de semana:")
else:
    titulo_lectura = "El aula se usa sobre todo en horario diurno:"
comp.lectura(f"el {comp.pct(noche, 0)} de las interacciones cae entre las 18 y las 24 h, el {comp.pct(manana, 0)} "
             f"entre las 6 y las 12 h y el {comp.pct(finde, 0)} en sábado o domingo. Es el horario en el que "
             "conviene publicar material o avisos, y el que más aprovecharía una consulta en línea.", titulo_lectura)

tab_tiempo, tab_tipos, tab_horarios, tab_evals = st.tabs(
    ["Línea de tiempo", "Tipos de interacción", "Días y horarios", "Alrededor de las evaluaciones"])

FRECUENCIAS = {"Día": "D", "Semana": "W", "Mes": "M"}
FORMATO_X = {"D": "%d/%m", "W": "sem. del %d/%m", "M": "%m/%Y"}
evaluaciones = comp.metrica("fechas_evaluaciones")
if desde is not None:
    evaluaciones = evaluaciones[evaluaciones["fecha_instrumento"] >= pd.Timestamp(desde)]


def marcar_evaluaciones(fig: go.Figure, color_por_materia: bool) -> None:
    """Triángulos en la base del gráfico en la fecha de cada evaluación (D18)."""
    for asig, g in evaluaciones.groupby("asignatura"):
        color = comp.COLORES_MATERIA[asig] if color_por_materia else comp.TEXTO_4
        fig.add_trace(go.Scatter(
            x=g["fecha_instrumento"], y=[0] * len(g), mode="markers", name=f"Evaluación {comp.SIGLAS[asig]}",
            marker=dict(symbol="triangle-up", size=11, color=color, line=dict(color="white", width=1)),
            text=sin_emoji(g["instrumento"]), cliponaxis=False, showlegend=False,
            hovertemplate="%{x|%d/%m}: %{text}<extra>" + asig + "</extra>"))


def evaluacion_en(asig: str, inicio: pd.Timestamp, frec: str) -> str | None:
    """Nombre de una evaluación de la materia dentro del período que empieza en `inicio`."""
    fin = inicio + {"D": pd.Timedelta(days=1), "W": pd.Timedelta(days=7), "M": pd.offsets.MonthBegin(1)}[frec]
    g = evaluaciones[(evaluaciones["asignatura"] == asig) & (evaluaciones["fecha_instrumento"] >= inicio)
                     & (evaluaciones["fecha_instrumento"] < fin)]
    return None if g.empty else sin_emoji(g["instrumento"]).iloc[0]


# ---------------------------------------------------------------------------
# Línea de tiempo
# ---------------------------------------------------------------------------
with tab_tiempo:
    with comp.tarjeta("evolucion"):
        c1, c2, c3 = st.columns([2.2, 1, 1], vertical_alignment="bottom")
        frecuencia = c2.segmented_control("Agrupar por", list(FRECUENCIAS), default="Semana",
                                          key="traz_frecuencia", label_visibility="collapsed") or "Semana"
        relativo = c3.segmented_control("Medida", ["Total", "Por alumno"], default="Total", key="traz_medida",
                                        label_visibility="collapsed") or "Total"
        frec = FRECUENCIAS[frecuencia]
        nombre_frec = {"D": "día", "W": "semana", "M": "mes"}[frec]
        with c1:
            comp.titulo_tarjeta(f"Interacciones por {nombre_frec} y materia",
                                "Los triángulos son las fechas de las evaluaciones, del color de su materia."
                                + (" **Por alumno** divide por la base de cada materia." if relativo != "Total"
                                   else ""))
        col = "eventos" if relativo == "Total" else "eventos_por_alumno"
        eje = "Interacciones" if relativo == "Total" else "Interacciones por alumno"
        hover = "%{y:,}" if relativo == "Total" else "%{y:.1f} por alumno"

        evo = comp.metrica("evolucion_interacciones", frecuencia=frec, desde=desde)
        leyenda_materias()
        fig = px.line(evo, x="periodo", y=col, color="asignatura", markers=frec != "D", category_orders=ORDEN,
                      color_discrete_map=comp.COLORES_MATERIA, labels={"periodo": "", col: "", "asignatura": ""})
        fig.update_traces(hovertemplate=f"%{{x|{FORMATO_X[frec]}}}<br>%{{fullData.name}}: {hover}<extra></extra>",
                          line_width=2.4, marker_size=6)
        marcar_evaluaciones(fig, color_por_materia=True)
        fig.update_xaxes(tickformat="%m/%Y" if frec == "M" else "%d/%m", showgrid=False)
        fig.update_yaxes(rangemode="tozero", title_text=eje if relativo != "Total" else "")
        fig.update_layout(showlegend=False, hovermode="closest", margin=dict(t=12))
        grafico(fig, 320)

        if not evo.empty:
            top = evo.loc[evo[col].idxmax()]
            ev = evaluacion_en(top["asignatura"], pd.Timestamp(top["periodo"]), frec)
            valor_top = comp.num(top[col]) if relativo == "Total" else comp.num(top[col], 1) + " por alumno"
            momento = {"D": f"el {top['periodo']:%d/%m}", "W": f"la semana del {top['periodo']:%d/%m}",
                       "M": f"en {top['periodo']:%m/%Y}"}[frec]
            texto = f"El pico es de **{comp.CORTOS[top['asignatura']]}**, {momento} ({valor_top})"
            texto += f", y coincide con **{ev}**." if ev else ", sin una evaluación de la materia en ese período."
            texto += (" Los últimos períodos pueden estar incompletos: la semana empieza el lunes y el último "
                      "período termina en la fecha de corte.") if frec != "D" else ""
            comp.nota(texto)

    with comp.tarjeta("tipos_tiempo"):
        c1, c2 = st.columns([3, 1.2], vertical_alignment="bottom")
        with c1:
            comp.titulo_tarjeta(f"En qué se gastan los clics, {nombre_frec} a {nombre_frec}",
                                f"Suma de {NOMBRE_TODAS}. Los triángulos grises son las evaluaciones.")
        apilado = c2.toggle(f"Ver en % de cada {nombre_frec}", key="traz_pct",
                            help="Cada barra suma 100 %: muestra cómo cambia la mezcla de tipos, no el volumen.")
        tipos = comp.metrica("evolucion_interacciones", frecuencia=frec, desde=desde, por="categoria")
        presentes = [c for c in CATEGORIAS if c in set(tipos["categoria"])]
        comp.leyenda({c: COLORES_CATEGORIA[c] for c in presentes})
        y = "pct_periodo" if apilado else col
        fig = px.bar(tipos, x="periodo", y=y, color="categoria", category_orders=ORDEN,
                     color_discrete_map=COLORES_CATEGORIA, labels={"periodo": "", y: "", "categoria": ""})
        formato = "%{y:.1f} %" if apilado else hover
        fig.update_traces(hovertemplate=f"%{{x|{FORMATO_X[frec]}}}<br>%{{fullData.name}}: {formato}<extra></extra>",
                          marker_line_width=0)
        marcar_evaluaciones(fig, color_por_materia=False)
        fig.update_xaxes(tickformat="%m/%Y" if frec == "M" else "%d/%m", showgrid=False)
        fig.update_yaxes(ticksuffix=" %" if apilado else "", range=[0, 100] if apilado else None)
        fig.update_layout(barmode="stack", bargap=0.18, showlegend=False, hovermode="closest", margin=dict(t=12))
        grafico(fig, 300)

        ev_tipo = tipos[tipos["categoria"] == "Evaluación"]
        if not ev_tipo.empty:
            mx = ev_tipo.loc[ev_tipo["pct_periodo"].idxmax()]
            comp.nota(f"En los períodos de evaluación crece la franja verde; el resto del tiempo domina leer contenido "
                      f"y navegar. **Evaluación nunca pasa del {comp.pct(mx['pct_periodo'], 0)} de los clics** de "
                      f"un período (máximo: {nombre_frec} del {mx['periodo']:%d/%m}).")

# ---------------------------------------------------------------------------
# Tipos de interacción
# ---------------------------------------------------------------------------
with tab_tipos:
    with comp.tarjeta("mezcla", "Qué hacen en el aula",
                      "Cada barra suma 100 % de las interacciones de esa materia. Comparar la parte de *Evaluación* "
                      "muestra cuánto pesan las actividades evaluadas en el uso del aula."):
        mezcla = categorias.groupby(["asignatura", "categoria"], as_index=False)["eventos"].sum()
        mezcla["pct"] = mezcla["eventos"] / mezcla.groupby("asignatura")["eventos"].transform("sum") * 100
        mezcla["materia"] = mezcla["asignatura"].map(comp.CORTOS)
        comp.leyenda({c: COLORES_CATEGORIA[c] for c in CATEGORIAS if c in set(mezcla["categoria"])})
        fig = px.bar(mezcla, x="pct", y="materia", color="categoria", orientation="h",
                     category_orders={**ORDEN, "materia": [comp.CORTOS[a] for a in f.materias]},
                     color_discrete_map=COLORES_CATEGORIA, custom_data=["eventos"],
                     text=mezcla["pct"].map(lambda v: comp.pct(v, 0) if v >= 6 else ""),
                     labels={"pct": "", "materia": "", "categoria": ""})
        fig.update_traces(hovertemplate="%{y}<br>%{fullData.name}: %{customdata[0]:,} (%{x:.1f} %)<extra></extra>",
                          textposition="inside", insidetextanchor="middle", marker_line_width=2,
                          marker_line_color="white", textfont=dict(color="white", size=11))
        fig.update_xaxes(range=[0, 100], showgrid=False, showticklabels=False)
        fig.update_yaxes(tickfont=dict(color=comp.TEXTO, size=12))
        fig.update_layout(barmode="stack", bargap=0.35, showlegend=False, margin=dict(t=8, b=0))
        grafico(fig, 70 + 52 * len(f.materias))

        pct_eval = mezcla[mezcla["categoria"] == "Evaluación"].set_index("asignatura")["pct"]
        if len(pct_eval) > 1:
            alta, baja = pct_eval.idxmax(), pct_eval.idxmin()
            comp.nota(f"**{comp.CORTOS[alta]} es la que más peso le da a Evaluación** "
                      f"({comp.pct(pct_eval[alta], 0)} de sus clics) y **{comp.CORTOS[baja]} la que menos** "
                      f"({comp.pct(pct_eval[baja], 0)}): en esa materia se entra, se navega y se lee mucho más de lo "
                      "que se rinde.", tono="atencion")
        elif len(pct_eval) == 1:
            comp.nota(f"En {comp.CORTOS[pct_eval.index[0]]}, Evaluación es el "
                      f"{comp.pct(pct_eval.iloc[0], 0)} de los clics.")

    acciones = comp.metrica("interacciones_por_accion", desde=desde)
    with comp.tarjeta("acciones"):
        c1, c2 = st.columns([2.2, 1.3], vertical_alignment="bottom")
        with c1:
            comp.titulo_tarjeta("Acciones más frecuentes",
                                f"{comp.num(len(acciones))} acciones distintas. **Alumnos** cuenta a cuántos de la "
                                "base la hicieron al menos una vez: una acción con muchas interacciones y pocos "
                                "alumnos la usa un grupo chico muy intensamente.")
        elegidas = c2.multiselect("Tipo de interacción", CATEGORIAS, key="traz_categorias", placeholder="Todos los tipos",
                                  label_visibility="collapsed")
        vista = acciones[acciones["categoria"].isin(elegidas)] if elegidas else acciones
        columnas = {"accion": "Acción", "categoria": "Tipo", "seccion": "Sección", "eventos": "Interacciones",
                    "pct": "% del total", "alumnos": "Alumnos", "pct_alumnos": "% de la base"}
        tabla = vista[list(columnas)].rename(columns=columnas)
        st.dataframe(tabla, hide_index=True, width="stretch", height=380, column_config={
            "Acción": st.column_config.TextColumn(width="medium"),
            "Interacciones": st.column_config.NumberColumn(format="localized"),
            "% del total": st.column_config.NumberColumn(format="%.1f %%"),
            "% de la base": st.column_config.ProgressColumn(format="%.0f %%", min_value=0, max_value=100,
                                                            color=comp.ACCION)})
        if not vista.empty:
            masiva = vista.loc[vista["pct_alumnos"].idxmax()]
            comp.nota(f"La acción que más alumnos hicieron es **{masiva['accion']}** "
                      f"({masiva['seccion'] or 'sin sección'}): {comp.pct(masiva['pct_alumnos'], 0)} de la base. "
                      "'Acceder' a Inicio y a Programa son filas distintas.")
        comp.boton_csv(tabla, f"trazabilidad_acciones_{SUFIJO}", "Descargar")

    with st.expander("Ver el detalle tipo › sección › acción (mapa de árbol)", icon=":material/account_tree:"):
        arbol = acciones.assign(seccion=acciones["seccion"].fillna("(sin sección)"))
        fig = px.treemap(arbol, path=[px.Constant("Todas"), "categoria", "seccion", "accion"], values="eventos",
                         color="categoria", color_discrete_map={**COLORES_CATEGORIA, "(?)": comp.GRILLA})
        fig.update_traces(hovertemplate="%{label}<br>%{value:,} interacciones<br>%{percentRoot:.1%} del total"
                                        "<extra></extra>", root_color=comp.GRILLA, marker_line_color="white",
                          marker_line_width=2)
        fig.update_layout(margin=dict(t=8, l=0, r=0, b=0))
        grafico(fig, 420)
        st.caption("Hacer clic en un recuadro para entrar; clic arriba para volver.")

# ---------------------------------------------------------------------------
# Días y horarios
# ---------------------------------------------------------------------------
with tab_horarios:
    with comp.tarjeta("calor"):
        c1, c2 = st.columns([3, 1.1], vertical_alignment="bottom")
        with c1:
            comp.titulo_tarjeta("Cuándo entran: día de la semana × hora",
                                f"Suma de {NOMBRE_TODAS}, en la hora del servidor del LMS. Cuanto más oscuro, más "
                                "interacciones en esa franja.")
        en_pct = c2.toggle("Ver en % del total", key="traz_calor_pct")
        matriz = calor.pivot(index="dia_semana", columns="hora", values="eventos") \
                      .reindex(index=range(7), columns=range(24)).fillna(0)
        if en_pct:
            matriz = matriz / matriz.values.sum() * 100
        fig = go.Figure(go.Heatmap(
            z=matriz.values, x=[f"{h} h" for h in matriz.columns], y=DIAS, colorscale=comp.SECUENCIAL,
            xgap=2, ygap=2, showscale=False,
            hovertemplate="%{y} de %{x}: %{z:" + (".2f} %" if en_pct else ",}") + "<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=comp.TEXTO_2, size=11))
        fig.update_xaxes(showgrid=False, side="top", dtick=3, tickfont=dict(color=comp.TEXTO_4, size=10))
        fig.update_layout(margin=dict(t=24, l=8, r=8, b=0))
        grafico(fig, 270)
        escala = "".join(f'<i style="display:inline-block;width:26px;height:12px;background:{c}"></i>'
                         for c in comp.SECUENCIAL)
        st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;font-size:11px;'
                    f'color:{comp.TEXTO_3}">Menos <span style="display:flex;gap:2px">{escala}</span> Más'
                    f'<span style="margin-left:auto">{comp.chip(f"Pico: {dia_pico.lower()} de {hora_pico} a {hora_pico + 1} h")}'
                    '</span></div>', unsafe_allow_html=True)

    perfiles = pd.concat([comp.metrica("mapa_calor", asignatura=a, desde=desde).assign(asignatura=a)
                          for a in f.materias])
    with comp.tarjeta("perfil"):
        c1, c2 = st.columns([3, 1.1], vertical_alignment="bottom")
        vista_perfil = c2.segmented_control("Perfil", ["Por día", "Por hora"], default="Por día",
                                            key="traz_perfil", label_visibility="collapsed") or "Por día"
        por_dia = perfiles.groupby(["asignatura", "dia_semana"], as_index=False)["eventos"].sum()
        por_dia["pct"] = por_dia["eventos"] / por_dia.groupby("asignatura")["eventos"].transform("sum") * 100
        por_dia["dia"] = por_dia["dia_semana"].map(dict(enumerate(DIAS_CORTOS)))
        fuertes = por_dia.loc[por_dia.groupby("asignatura")["pct"].idxmax()].set_index("asignatura")
        with c1:
            comp.titulo_tarjeta("El día fuerte de cada materia" if vista_perfil == "Por día"
                                else "La hora fuerte de cada materia",
                                "En % de las interacciones de cada materia, para compararlas aunque tengan distinto "
                                "tamaño.")
        if vista_perfil == "Por día":
            fig = px.bar(por_dia, x="dia", y="pct", color="asignatura", barmode="group",
                         category_orders={**ORDEN, "dia": DIAS_CORTOS}, color_discrete_map=comp.COLORES_MATERIA,
                         labels={"dia": "", "pct": "", "asignatura": ""})
            fig.update_traces(hovertemplate="%{x} · %{fullData.name}: %{y:.1f} %<extra></extra>")
            fig.update_layout(bargap=0.25, bargroupgap=0.08)
        else:
            por_hora = perfiles.groupby(["asignatura", "hora"], as_index=False)["eventos"].sum()
            por_hora["pct"] = por_hora["eventos"] / por_hora.groupby("asignatura")["eventos"].transform("sum") * 100
            fig = px.line(por_hora, x="hora", y="pct", color="asignatura", markers=True, category_orders=ORDEN,
                          color_discrete_map=comp.COLORES_MATERIA, labels={"hora": "", "pct": "", "asignatura": ""})
            fig.update_traces(hovertemplate="%{x} h · %{fullData.name}: %{y:.1f} %<extra></extra>", line_width=2.4,
                              marker_size=5)
            fig.update_xaxes(dtick=3, ticksuffix=" h")
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(ticksuffix=" %", rangemode="tozero")
        fig.update_layout(showlegend=False, margin=dict(t=12))
        grafico(fig, 280)
        comp.leyenda({f"{comp.CORTOS[a]} · {DIAS[int(fuertes.loc[a, 'dia_semana'])].lower()} "
                      f"{comp.pct(fuertes.loc[a, 'pct'], 0)}": comp.COLORES_MATERIA[a]
                      for a in f.materias if a in fuertes.index})
        maxima = fuertes["pct"].max()
        concentrada = fuertes["pct"].idxmax()
        comp.nota(("El " + comp.pct(maxima, 0) + f" de {comp.CORTOS[concentrada]} en un solo día es mucho. "
                   if maxima >= 25 else "") +
                  "Si cada materia tiene su propio día fuerte, probablemente sea el de la clase o el de la publicación "
                  "del material: el aula se usa como complemento de la cursada y no de forma pareja durante la "
                  "semana. Los días no aparecen la misma cantidad de veces en el período, así que diferencias chicas "
                  "entre días no son significativas.")

# ---------------------------------------------------------------------------
# Alrededor de las evaluaciones (D62)
# ---------------------------------------------------------------------------
MEDIDAS_EVAL = {
    "Relativa a un día típico": ("relativo", "Veces un día típico", "%{y:.2f} × un día típico"),
    "Interacciones por alumno": ("eventos_por_alumno", "Interacciones por alumno", "%{y:.2f} por alumno"),
    "Solo de evaluación, por alumno": ("evaluacion_por_alumno", "Interacciones de evaluación por alumno",
                                       "%{y:.2f} por alumno"),
}


def lectura_pico(dia: int, veces: float) -> str:
    """Interpretación del día con más actividad alrededor de las evaluaciones de una materia."""
    if veces < 1.2:
        return "Actividad casi plana: las evaluaciones no mueven el uso del aula."
    if dia < 0:
        return f"Suben desde antes y el pico llega {abs(dia)} día{'s' if abs(dia) > 1 else ''} antes: estudian " \
               "para la evaluación."
    if dia == 0:
        return "Se concentra en el mismo día: se entra a rendir más que a prepararse."
    return "El pico llega después del día 0: la evaluación queda abierta varios días o las ventanas se " \
           "superponen con la siguiente."


with tab_evals:
    with comp.tarjeta("alrededor"):
        comp.titulo_tarjeta("¿Estudian con tiempo o el día antes?",
                            "Para cada evaluación ya tomada se mira la actividad de su materia en los días de "
                            "alrededor. El **día 0** es la fecha de la evaluación (la mediana de las realizaciones). "
                            "Usa toda la cursada hasta el corte: no se recorta por el período.")
        c1, c2 = st.columns([1.4, 1.6], vertical_alignment="bottom")
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
            leyenda_materias()
            fig = px.line(prom, x="dia_relativo", y="valor", color="asignatura", markers=True, category_orders=ORDEN,
                          color_discrete_map=comp.COLORES_MATERIA, custom_data=["evaluaciones"],
                          labels={"dia_relativo": "Días respecto de la evaluación", "valor": "", "asignatura": ""})
            fig.update_traces(hovertemplate="Día %{x}<br>%{fullData.name}: " + hover
                                            + " (promedio de %{customdata[0]} evaluaciones)<extra></extra>",
                              line_width=2.4, marker_size=7)
            fig.add_vline(x=0, line_dash="dot", line_color=comp.TEXTO_2, line_width=1.2,
                          annotation_text="evaluación", annotation_position="top",
                          annotation_font=dict(size=11, color="#2C2A25"))
            if col == "relativo":
                fig.add_hline(y=1, line_dash="dash", line_color=comp.NEUTRO, line_width=1.4,
                              annotation_text="1× día normal", annotation_position="bottom left",
                              annotation_font=dict(size=11, color=comp.TEXTO_2))
                fig.update_yaxes(ticksuffix="×")
            fig.update_xaxes(dtick=1, showgrid=False, ticksuffix=" d")
            fig.update_yaxes(rangemode="tozero", title_text=eje if col != "relativo" else "")
            fig.update_layout(showlegend=False, margin=dict(t=28))
            grafico(fig, 300)

            rel = alrededor.groupby(["asignatura", "dia_relativo"])["relativo"].mean()
            presentes = [a for a in f.materias if a in rel.index.get_level_values(0)]
            cols = st.columns(len(presentes))
            for c, asig in zip(cols, presentes):
                r = rel.loc[asig]
                dia = int(r.idxmax())
                titulo = f"{comp.CORTOS[asig]} · pico " + ("el día 0" if dia == 0 else f"en {dia:+d}".replace("-", "−"))
                c.markdown(comp.mini_tarjeta(titulo, f"{comp.num(r.max(), 1)}×", lectura_pico(dia, r.max()),
                                             comp.COLORES_MATERIA[asig]), unsafe_allow_html=True)
            st.caption("Promedio de las evaluaciones de cada materia; 1× es un día típico de la materia (promedio "
                       "diario de la cursada). En PyE las evaluaciones están a pocos días entre sí, así que las "
                       "ventanas se superponen.")

    if not alrededor.empty:
        with comp.tarjeta("por_evaluacion"):
            materias_eval = [a for a in f.materias if a in set(alrededor["asignatura"])]
            c1, c2 = st.columns([2.4, 1.2], vertical_alignment="bottom")
            materia_eval = c2.selectbox("Materia", materias_eval, key="traz_eval_materia",
                                        label_visibility="collapsed")
            with c1:
                comp.titulo_tarjeta("Evaluación por evaluación",
                                    f"{eje} en cada día alrededor de cada evaluación de {materia_eval}.")
            g = alrededor[alrededor["asignatura"] == materia_eval].copy()
            g["nombre"] = sin_emoji(g["instrumento"]) + "  " + g["fecha_instrumento"].dt.strftime("%d/%m")
            orden_filas = list(dict.fromkeys(g.sort_values("fecha_instrumento")["nombre"]))
            matriz = g.pivot(index="nombre", columns="dia_relativo", values=col).reindex(orden_filas)
            fig = go.Figure(go.Heatmap(
                z=matriz.values, x=[f"{c:+d}".replace("+0", "0").replace("-", "−") for c in matriz.columns],
                y=matriz.index, colorscale=comp.SECUENCIAL, xgap=3, ygap=3,
                colorbar=dict(title="", thickness=10, outlinewidth=0, tickfont=dict(color=comp.TEXTO_3, size=10)),
                hovertemplate="%{y}<br>Día %{x}: %{z:.2f}<extra></extra>"))
            fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=comp.TEXTO_2, size=11))
            fig.update_xaxes(showgrid=False, side="top", tickfont=dict(color=comp.TEXTO_4, size=10))
            fig.update_layout(margin=dict(t=24, l=8, r=8, b=0))
            grafico(fig, 70 + 34 * len(matriz))
            fila_max = matriz.max(axis=1).idxmax()
            dia_max = matriz.loc[fila_max].idxmax()
            comp.nota(f"El valor más alto es de **{fila_max.split('  ')[0]}**, el día "
                      f"{'de la evaluación' if dia_max == 0 else f'{dia_max:+d}'.replace('-', '−')} "
                      f"({comp.num(matriz.loc[fila_max].max(), 1)}). Las celdas vacías son días fuera de los datos "
                      "(antes del inicio o después de la fecha de corte).")
            comp.boton_csv(g.drop(columns=["nombre"]), f"trazabilidad_evaluaciones_{comp.SIGLAS[materia_eval]}_"
                           f"{f.fecha_corte:%Y%m%d}", "Descargar estos datos")
