"""Dashboard 3 (del plan): Trazabilidad.

Responde: ¿cuándo y cada cuánto entran los alumnos al aula?, ¿qué hacen cuando entran?,
¿cómo evolucionó la actividad? y ¿cuánto se mueve alrededor de cada evaluación?

  Período         filtro propio de la página (como en Participación, D53) que termina
                  en la fecha de corte de la barra lateral.
  Tarjetas        días con ingreso por semana, interacciones por día de ingreso, % de clics
                  en Evaluación y % entre las 18 y las 24 h (D80), con Δ contra el período
                  anterior de igual largo.
  Pestañas        Cuándo y cada cuánto entran (mapa de calor, frecuencia de ingreso, día fuerte)
                  · Qué hacen (mezcla de tipos, acciones, mapa de árbol) · Evolución (por alumno
                  y por tipo) · Alrededor de las evaluaciones (D62).

Diseño (D63, D80): el dashboard muestra datos, no explica. Cada título dice el dato principal,
calculado con los datos; el subtítulo dice solo cómo leer el gráfico y las limitaciones van en
el (?) de cada tarjeta. Las interpretaciones van al informe (docs/conclusiones_trazabilidad.md).
Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes_trazabilidad as comp
from src.metricas import CATEGORIAS, DIAS, TRAMOS_FRECUENCIA

f = comp.encabezado("Trazabilidad", "Qué hacen los alumnos en el aula y cuándo. Cada clic del LMS es una interacción.")

ORDEN = {"asignatura": list(comp.COLORES_MATERIA), "categoria": CATEGORIAS}
COLORES_CATEGORIA = comp.COLORES_CATEGORIA
DIAS_CORTOS = [d[:3] for d in DIAS]
SIN_BARRA = {"displayModeBar": False}
UNA = f.asignatura is not None
NOMBRE_TODAS = comp.CORTOS[f.asignatura] if UNA else "las materias elegidas"
HORA_SERVIDOR = "La hora es la del servidor del LMS: las fechas vienen sin zona horaria."
TIPOS_AYUDA = ("Contenido = materiales y vistas (textos, archivos, unidades). Evaluación = exámenes, autoevaluaciones "
               "y encuestas. Navegación = clics de acceso a secciones, búsquedas y perfiles. Comunicación = foros, "
               "noticias y mensajes. Notas = consulta de calificaciones y avances. Agenda = calendario.")


def grafico(fig: go.Figure, alto: int) -> None:
    comp.grafico(fig, alto, config=SIN_BARRA)   # con la plantilla tfi_trazabilidad


def leyenda_materias(linea: bool = True) -> None:
    comp.leyenda({comp.CORTOS[a]: comp.COLORES_MATERIA[a] for a in f.materias}, linea=linea)


def sin_emoji(serie: pd.Series) -> pd.Series:
    return serie.str.replace(r"^\W+", "", regex=True).str.strip()


def por_materia(valores: dict, formato) -> str:
    """'Probabilidad, el 11 %; Algoritmos, el 6 %' (sin la primera materia, que va en la oración)."""
    return "; ".join(f"{comp.CORTOS[a]}, {formato(v)}" for a, v in valores.items())


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

resumen = comp.metrica("resumen_trazabilidad", desde=desde)
actual = resumen.loc["actual"]
if actual["interacciones_total"] == 0:
    st.info(f"No hay interacciones de alumnos {texto_periodo}.", icon=":material/event_busy:")
    st.stop()
categorias = comp.metrica("interacciones_por_categoria", desde=desde)
calor = comp.metrica("mapa_calor", desde=desde)

# ---------------------------------------------------------------------------
# Tarjetas (D80). Δ contra el período anterior de igual largo, si entra entero en los datos.
# ---------------------------------------------------------------------------
anterior = resumen.loc["anterior"] if periodo != "Toda la cursada" and "anterior" in resumen.index else None
referencia = f"{anterior['desde']:%d/%m}–{anterior['hasta']:%d/%m}" if anterior is not None else ""


def variacion(col: str, unidad: str = "", mejor: str = "neutro", decimales: int = 1) -> str:
    if anterior is None:
        return ""
    return comp.delta(actual[col] - anterior[col], unidad, mejor, decimales, referencia)


k1, k2, k3, k4 = st.columns(4)
with k1:
    comp.kpi("Días con ingreso por semana", comp.num(actual["dias_ingreso_semana"], 1),
             f"de {comp.num(actual['alumnos'])} alumnos que entraron", variacion("dias_ingreso_semana", "", "sube"),
             tip="Mediana, entre los alumnos que entraron en el período, de los días distintos con al menos una "
                 "interacción dividido por las semanas del período (días / 7). Quien cursa dos materias cuenta "
                 "una vez por materia.")
with k2:
    comp.kpi("Interacciones por día de ingreso", comp.num(actual["interacciones_por_dia_ingreso"], 1),
             f"{comp.num(actual['interacciones_total'])} en total · {comp.num(actual['interacciones_por_dia'])} por día",
             variacion("interacciones_por_dia_ingreso"),
             tip="Mediana, entre los alumnos que entraron, de sus interacciones divididas por sus días con ingreso. "
                 "Por día = total del período / días calendario, con fines de semana.")
with k3:
    comp.kpi("Clics en Evaluación", comp.pct(actual["pct_evaluacion"], 1), "de las interacciones del período",
             variacion("pct_evaluacion", "pp"),
             tip="Interacciones de tipo Evaluación (realizar, ver o finalizar exámenes, autoevaluaciones y "
                 "encuestas) sobre el total del período.")
with k4:
    comp.kpi("Clics entre 18 y 24 h", comp.pct(actual["pct_nocturno"], 1), "de las interacciones del período",
             tip="Interacciones con hora entre las 18:00 y las 23:59. " + HORA_SERVIDOR)

tab_cuando, tab_que, tab_evolucion, tab_evals = st.tabs(
    ["Cuándo y cada cuánto entran", "Qué hacen", "Evolución", "Alrededor de las evaluaciones"])

# ---------------------------------------------------------------------------
# Cuándo y cada cuánto entran
# ---------------------------------------------------------------------------
with tab_cuando:
    with comp.tarjeta("calor"):
        pico = calor.loc[calor["eventos"].idxmax()]
        dia_pico, hora_pico = DIAS[int(pico["dia_semana"])], int(pico["hora"])
        c1, c2 = st.columns([3, 1.1], vertical_alignment="bottom")
        with c1:
            comp.titulo_tarjeta(f"Pico: {dia_pico.lower()} de {hora_pico} a {hora_pico + 1} h",
                                f"Interacciones por día y hora, suma de {NOMBRE_TODAS}. Más oscuro, más interacciones.",
                                tip=HORA_SERVIDOR)
        en_pct = c2.toggle("Ver en % del total", key="traz_calor_pct")
        matriz = calor.pivot(index="dia_semana", columns="hora", values="eventos") \
                      .reindex(index=range(7), columns=range(24)).fillna(0)
        if en_pct:
            matriz = matriz / matriz.values.sum() * 100
        fig = go.Figure(go.Heatmap(
            z=matriz.values, x=[f"{h} h" for h in matriz.columns], y=DIAS, colorscale=comp.SECUENCIAL,
            xgap=2, ygap=2, showscale=False,
            hovertemplate="%{y} de %{x}: %{z:" + (",.2f} %" if en_pct else ",.0f} interacciones") + "<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=comp.TEXTO_2, size=11))
        fig.update_xaxes(showgrid=False, side="top", dtick=3, tickfont=dict(color=comp.TEXTO_4, size=10))
        fig.update_layout(margin=dict(t=24, l=8, r=8, b=0))
        grafico(fig, 270)
        escala = "".join(f'<i style="display:inline-block;width:26px;height:12px;background:{c}"></i>'
                         for c in comp.SECUENCIAL)
        st.markdown(f'<div style="display:flex;gap:12px;align-items:center;font-size:11px;color:{comp.TEXTO_3}">'
                    f'Menos <span style="display:flex;gap:2px">{escala}</span> Más</div>', unsafe_allow_html=True)

    with comp.tarjeta("frecuencia"):
        c1, c2 = st.columns([3, 1.1], vertical_alignment="bottom")
        unidad = c2.segmented_control("Frecuencia", ["Semana", "Mes"], default="Semana", key="traz_frec_ingreso",
                                      label_visibility="collapsed") or "Semana"
        clave = "W" if unidad == "Semana" else "M"
        frecuencia = comp.metrica("frecuencia_ingreso", desde=desde, frecuencia=clave)
        frecuencia = frecuencia[frecuencia["total"] > 0]
        tramos = TRAMOS_FRECUENCIA[clave][1]
        bajos, corte_bajo = (tramos[:2], "2 días por semana") if clave == "W" else (tramos[:2], "8 días por mes")
        pct_bajo = frecuencia[frecuencia["tramo"].isin(bajos)].groupby("asignatura")["pct"].sum() \
                                                               .reindex(f.materias).dropna()
        if len(pct_bajo) > 1 and round(pct_bajo.min()) != round(pct_bajo.max()):
            titulo = f"Entre el {comp.pct(pct_bajo.min(), 0)} y el {comp.pct(pct_bajo.max(), 0)} entra menos de {corte_bajo}"
        else:
            titulo = f"El {comp.pct(pct_bajo.max(), 0)} entra menos de {corte_bajo}" + ("" if UNA else " en cada materia")
        with c1:
            comp.titulo_tarjeta(titulo, f"Alumnos que entraron en el período, según sus días con ingreso por "
                                        f"{unidad.lower()}.",
                                tip="Días con ingreso = días distintos con al menos una interacción, divididos por "
                                    "las semanas (días / 7) o los meses (días / 30) del período. Cada tramo incluye "
                                    "su límite inferior: 2 días justos por semana van en 2–3. "
                                    + ("El tramo 1–3 incluye a quienes entraron menos de un día por mes."
                                       if clave == "M" else ""))
        colores_tramo = dict(zip(tramos, comp.SECUENCIAL[1::2] + [comp.SECUENCIAL[-1]]))
        frecuencia = frecuencia.assign(materia=frecuencia["asignatura"].map(comp.CORTOS),
                                       tramo=frecuencia["tramo"].astype(str))
        comp.leyenda({f"{t} días": colores_tramo[t] for t in tramos})
        fig = px.bar(frecuencia, x="pct", y="materia", color="tramo", orientation="h",
                     category_orders={"tramo": tramos, "materia": [comp.CORTOS[a] for a in f.materias]},
                     color_discrete_map=colores_tramo, custom_data=["alumnos", "total"],
                     text=frecuencia["pct"].map(lambda v: comp.pct(v, 0) if v >= 6 else ""),
                     labels={"pct": "", "materia": "", "tramo": ""})
        fig.update_traces(hovertemplate="%{y} · %{fullData.name} días por " + unidad.lower()
                                        + "<br>%{x:,.1f} % (%{customdata[0]:,.0f} de %{customdata[1]:,.0f})"
                                          "<extra></extra>",
                          textposition="inside", insidetextanchor="middle", marker_line_width=2,
                          marker_line_color="white", textfont=dict(size=11))
        for traza in fig.data:   # texto blanco sobre los tonos oscuros
            traza.textfont.color = "white" if tramos.index(traza.name) >= 2 else comp.TEXTO
        fig.update_xaxes(range=[0, 100], showgrid=False, showticklabels=False)
        fig.update_yaxes(tickfont=dict(color=comp.TEXTO, size=12))
        fig.update_layout(barmode="stack", bargap=0.35, showlegend=False, margin=dict(t=8, b=0))
        grafico(fig, 70 + 52 * len(f.materias))

    perfiles = pd.concat([comp.metrica("mapa_calor", asignatura=a, desde=desde).assign(asignatura=a)
                          for a in f.materias])
    with comp.tarjeta("perfil"):
        c1, c2 = st.columns([3, 1.1], vertical_alignment="bottom")
        vista_perfil = c2.segmented_control("Perfil", ["Por día", "Por hora"], default="Por día",
                                            key="traz_perfil", label_visibility="collapsed") or "Por día"
        por_dia = vista_perfil == "Por día"
        clave_t = "dia_semana" if por_dia else "hora"
        perfil = perfiles.groupby(["asignatura", clave_t], as_index=False)["eventos"].sum()
        perfil["pct"] = perfil["eventos"] / perfil.groupby("asignatura")["eventos"].transform("sum") * 100
        perfil = perfil.dropna(subset=["pct"])
        fuertes = perfil.loc[perfil.groupby("asignatura")["pct"].idxmax()].set_index("asignatura") \
                        .reindex([a for a in f.materias if a in set(perfil["asignatura"])])

        def momento(fila) -> str:
            return DIAS[int(fila[clave_t])].lower() if por_dia else f"a las {int(fila[clave_t])} h"

        partes = [f"el {comp.pct(fila['pct'], 0)} {'el ' if por_dia else ''}{momento(fila)}"
                  for _, fila in fuertes.iterrows()]
        if len(fuertes) == 1:
            titulo = f"{comp.CORTOS[fuertes.index[0]]} concentra {partes[0]} de sus clics"
        else:
            titulo = (f"{comp.CORTOS[fuertes.index[0]]} concentra {partes[0]}; "
                      + "; ".join(f"{comp.CORTOS[a]}, {p}" for a, p in zip(fuertes.index[1:], partes[1:])))
        with c1:
            comp.titulo_tarjeta(titulo, "En % de las interacciones de cada materia, para compararlas aunque tengan "
                                        "distinto tamaño.",
                                tip="Los días de la semana no aparecen la misma cantidad de veces en el período: "
                                    "diferencias chicas entre días no son significativas. " + HORA_SERVIDOR)
        parejo = 100 / (7 if por_dia else 24)
        if por_dia:
            perfil["dia"] = perfil["dia_semana"].map(dict(enumerate(DIAS_CORTOS)))
            fig = px.bar(perfil, x="dia", y="pct", color="asignatura", barmode="group",
                         category_orders={**ORDEN, "dia": DIAS_CORTOS}, color_discrete_map=comp.COLORES_MATERIA,
                         labels={"dia": "", "pct": "", "asignatura": ""})
            fig.update_traces(hovertemplate="%{x} · %{fullData.name}: %{y:,.1f} %<extra></extra>")
            fig.update_layout(bargap=0.25, bargroupgap=0.08)
        else:
            fig = px.line(perfil, x="hora", y="pct", color="asignatura", symbol="asignatura", markers=True,
                          category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                          symbol_map=comp.MARCADORES, labels={"hora": "", "pct": "", "asignatura": ""})
            fig.update_traces(hovertemplate="%{x} h · %{fullData.name}: %{y:,.1f} %<extra></extra>", line_width=2.4,
                              marker_size=6)
            fig.update_xaxes(dtick=3, ticksuffix=" h")
        fig.add_hline(y=parejo, line_dash="dot", line_color=comp.TEXTO_3, line_width=1.2,
                      annotation_text="reparto parejo", annotation_position="top right",
                      annotation_font=dict(size=11, color=comp.TEXTO_2))
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(ticksuffix=" %", rangemode="tozero")
        fig.update_layout(showlegend=False, margin=dict(t=12))
        leyenda_materias(linea=not por_dia)
        grafico(fig, 280)

# ---------------------------------------------------------------------------
# Qué hacen
# ---------------------------------------------------------------------------
with tab_que:
    mezcla = categorias.groupby(["asignatura", "categoria"], as_index=False)["eventos"].sum()
    mezcla["pct"] = mezcla["eventos"] / mezcla.groupby("asignatura")["eventos"].transform("sum") * 100
    mezcla["materia"] = mezcla["asignatura"].map(comp.CORTOS)
    pct_eval = mezcla[mezcla["categoria"] == "Evaluación"].set_index("asignatura")["pct"] \
                     .reindex([a for a in f.materias if a in set(mezcla["asignatura"])]).fillna(0)
    pct_eval = pct_eval.sort_values(ascending=False)
    primera = pct_eval.index[0]
    titulo = f"{comp.CORTOS[primera]} dedica el {comp.pct(pct_eval.iloc[0], 0)} de sus clics a Evaluación"
    if len(pct_eval) > 1:
        titulo += "; " + por_materia(pct_eval.iloc[1:].to_dict(), lambda v: f"el {comp.pct(v, 0)}")
    with comp.tarjeta("mezcla"):
        comp.titulo_tarjeta(titulo, "Cada barra suma el 100 % de las interacciones de la materia.", tip=TIPOS_AYUDA)
        comp.leyenda({c: COLORES_CATEGORIA[c] for c in CATEGORIAS if c in set(mezcla["categoria"])})
        etiqueta = [comp.pct(v, 0) if v >= 6 or c == "Evaluación" else ""
                    for v, c in zip(mezcla["pct"], mezcla["categoria"])]
        fig = px.bar(mezcla, x="pct", y="materia", color="categoria", orientation="h",
                     category_orders={**ORDEN, "materia": [comp.CORTOS[a] for a in f.materias]},
                     color_discrete_map=COLORES_CATEGORIA, custom_data=["eventos"], text=etiqueta,
                     labels={"pct": "", "materia": "", "categoria": ""})
        fig.update_traces(hovertemplate="%{y}<br>%{fullData.name}: %{customdata[0]:,.0f} (%{x:,.1f} %)"
                                        "<extra></extra>",
                          textposition="inside", insidetextanchor="middle", marker_line_width=2,
                          marker_line_color="white", textfont=dict(color="white", size=11))
        fig.for_each_trace(lambda t: t.update(constraintext="none") if t.name == "Evaluación" else None)
        fig.update_xaxes(range=[0, 100], showgrid=False, showticklabels=False)
        fig.update_yaxes(tickfont=dict(color=comp.TEXTO, size=12))
        fig.update_layout(barmode="stack", bargap=0.35, showlegend=False, margin=dict(t=8, b=0),
                          uniformtext=dict(minsize=9, mode="show"))
        grafico(fig, 70 + 52 * len(f.materias))

    acciones = comp.metrica("interacciones_por_accion", desde=desde)
    with comp.tarjeta("acciones"):
        c1, c2 = st.columns([2.2, 1.3], vertical_alignment="bottom")
        elegidas = c2.multiselect("Tipo de interacción", CATEGORIAS, key="traz_categorias", placeholder="Todos los tipos",
                                  label_visibility="collapsed")
        vista = acciones[acciones["categoria"].isin(elegidas)] if elegidas else acciones
        with c1:
            if vista.empty:
                comp.titulo_tarjeta("Sin acciones de ese tipo en el período")
            else:
                masiva = vista.loc[vista["pct_alumnos"].idxmax()]
                donde = f" a {masiva['seccion']}" if masiva["seccion"] else ""
                comp.titulo_tarjeta(f"La acción que más alumnos hicieron es {masiva['accion']}{donde}: "
                                    f"{comp.pct(masiva['pct_alumnos'], 0)} de la base",
                                    f"{comp.num(len(vista))} acciones. Alumnos = cuántos de la base la hicieron al "
                                    "menos una vez.",
                                    tip="La misma acción en dos secciones (Acceder a Inicio y a Programa) son filas "
                                        "distintas. Quien cursa dos materias cuenta una vez por materia. " + TIPOS_AYUDA)
        columnas = {"accion": "Acción", "categoria": "Tipo", "seccion": "Sección", "eventos": "Interacciones",
                    "pct": "% del total", "alumnos": "Alumnos", "pct_alumnos": "% de la base"}
        tabla = vista[list(columnas)].rename(columns=columnas)
        st.dataframe(comp.estilo_tabla(tabla, {"% del total": 1, "% de la base": 0}), hide_index=True,
                     width="stretch", height=380, column_config={
                         "Acción": st.column_config.TextColumn(width="medium"),
                         "% de la base": st.column_config.ProgressColumn(format="%.0f %%", min_value=0,
                                                                         max_value=100, color=comp.ACCION)})
        comp.boton_csv(tabla, f"trazabilidad_acciones_{SUFIJO}", "Descargar")

    with st.expander("Ver el detalle tipo › sección › acción (mapa de árbol)", icon=":material/account_tree:"):
        arbol = acciones.assign(seccion=acciones["seccion"].fillna("(sin sección)"))
        fig = px.treemap(arbol, path=[px.Constant("Todas"), "categoria", "seccion", "accion"], values="eventos",
                         color="categoria", color_discrete_map={**COLORES_CATEGORIA, "(?)": comp.GRILLA})
        fig.update_traces(hovertemplate="%{label}<br>%{value:,.0f} interacciones<br>%{percentRoot:.1%} del total"
                                        "<extra></extra>", root_color=comp.GRILLA, marker_line_color="white",
                          marker_line_width=2)
        fig.update_layout(margin=dict(t=8, l=0, r=0, b=0))
        grafico(fig, 420)
        st.caption("Clic en un recuadro para entrar; clic arriba para volver.")

# ---------------------------------------------------------------------------
# Evolución
# ---------------------------------------------------------------------------
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


def nota_incompleto(df: pd.DataFrame) -> pd.Series:
    """Aclaración para el tooltip de los períodos cortados por el inicio o la fecha de corte."""
    return df.apply(lambda r: "" if r["completo"]
                    else f"<br>período incompleto ({r['dias']} de {r['dias_periodo']} días)", axis=1)


with tab_evolucion:
    with comp.tarjeta("evolucion"):
        c1, c2 = st.columns([3, 1.2], vertical_alignment="bottom")
        frecuencia_evo = c2.segmented_control("Agrupar por", list(FRECUENCIAS), default="Semana",
                                              key="traz_frecuencia", label_visibility="collapsed") or "Semana"
        frec = FRECUENCIAS[frecuencia_evo]
        nombre_frec = {"D": "día", "W": "semana", "M": "mes"}[frec]
        evo = comp.metrica("evolucion_interacciones", frecuencia=frec, desde=desde)
        top = evo.loc[evo["eventos_por_alumno"].idxmax()]
        cuando = {"D": f"el {top['periodo']:%d/%m}", "W": f"la semana del {top['periodo']:%d/%m}",
                  "M": f"en {top['periodo']:%m/%Y}"}[frec]
        with c1:
            comp.titulo_tarjeta(f"Máximo: {comp.CORTOS[top['asignatura']]}, {cuando}, con "
                                f"{comp.num(top['eventos_por_alumno'], 1)} interacciones por alumno",
                                "Interacciones de cada materia divididas por su base. Los triángulos son las "
                                "evaluaciones.",
                                tip="La semana va de lunes a domingo. El primer y el último período pueden quedar "
                                    "cortados por el inicio del período y la fecha de corte: se marcan con un punto "
                                    "hueco.")
        leyenda_materias()
        fig = go.Figure()
        for asig in [a for a in f.materias if a in set(evo["asignatura"])]:
            g = evo[evo["asignatura"] == asig].sort_values("periodo")
            simbolo = comp.MARCADORES[asig]
            fig.add_trace(go.Scatter(
                x=g["periodo"], y=g["eventos_por_alumno"], mode="lines+markers", name=comp.CORTOS[asig],
                line=dict(color=comp.COLORES_MATERIA[asig], width=2.4),
                marker=dict(symbol=[simbolo if c else f"{simbolo}-open" for c in g["completo"]],
                            size=5 if frec == "D" else 8, color=comp.COLORES_MATERIA[asig],
                            line=dict(width=1.6, color=comp.COLORES_MATERIA[asig])),
                customdata=nota_incompleto(g),
                hovertemplate=f"%{{x|{FORMATO_X[frec]}}}<br>%{{fullData.name}}: %{{y:,.1f}} por alumno"
                              "%{customdata}<extra></extra>"))
        marcar_evaluaciones(fig, color_por_materia=True)
        fig.update_xaxes(tickformat="%m/%Y" if frec == "M" else "%d/%m", showgrid=False)
        fig.update_yaxes(rangemode="tozero", title_text="Interacciones por alumno")
        fig.update_layout(showlegend=False, hovermode="closest", margin=dict(t=12))
        grafico(fig, 320)

    with comp.tarjeta("tipos_tiempo"):
        c1, c2 = st.columns([3, 1.2], vertical_alignment="bottom")
        absoluto = c2.toggle("Ver en interacciones", key="traz_tipos_abs",
                             help="Muestra el volumen de cada tipo en vez de su % del período.")
        tipos = comp.metrica("evolucion_interacciones", frecuencia=frec, desde=desde, por="categoria")
        PRINCIPALES = ["Contenido", "Navegación", "Evaluación", "Comunicación"]
        tipos = tipos.assign(categoria=tipos["categoria"].where(tipos["categoria"].isin(PRINCIPALES), "Otros"))
        tipos = tipos.groupby(["categoria", "periodo"], as_index=False).agg(
            eventos=("eventos", "sum"), completo=("completo", "first"), dias=("dias", "first"),
            dias_periodo=("dias_periodo", "first"))
        total_periodo = tipos.groupby("periodo")["eventos"].transform("sum")
        tipos["pct"] = (tipos["eventos"] / total_periodo.where(total_periodo > 0) * 100).fillna(0)
        orden_tipos = PRINCIPALES + ["Otros"]
        colores_tipos = {**COLORES_CATEGORIA, "Otros": COLORES_CATEGORIA["Notas"]}
        ev_tipo = tipos[(tipos["categoria"] == "Evaluación") & (total_periodo > 0)]
        with c1:
            if ev_tipo.empty or ev_tipo["pct"].max() == 0:
                titulo = "Sin interacciones de Evaluación en el período"
            else:
                mx = ev_tipo.loc[ev_tipo["pct"].idxmax()]
                cuando = {"D": f"el {mx['periodo']:%d/%m}", "W": f"la semana del {mx['periodo']:%d/%m}",
                          "M": f"en {mx['periodo']:%m/%Y}"}[frec]
                titulo = f"Evaluación llega al {comp.pct(mx['pct'], 0)} de los clics {cuando}"
            comp.titulo_tarjeta(titulo, f"Suma de {NOMBRE_TODAS}. Los triángulos grises son las evaluaciones.",
                                tip="Otros = Notas y Agenda. " + TIPOS_AYUDA)
        comp.leyenda({c: colores_tipos[c] for c in orden_tipos if c in set(tipos["categoria"])})
        y = "eventos" if absoluto else "pct"
        tipos["extra"] = nota_incompleto(tipos)
        fig = px.bar(tipos, x="periodo", y=y, color="categoria", category_orders={"categoria": orden_tipos},
                     color_discrete_map=colores_tipos, custom_data=["extra"],
                     labels={"periodo": "", y: "", "categoria": ""})
        formato = "%{y:,.0f} interacciones" if absoluto else "%{y:,.1f} %"
        fig.update_traces(hovertemplate=f"%{{x|{FORMATO_X[frec]}}}<br>%{{fullData.name}}: {formato}"
                                        "%{customdata[0]}<extra></extra>", marker_line_width=0)
        marcar_evaluaciones(fig, color_por_materia=False)
        fig.update_xaxes(tickformat="%m/%Y" if frec == "M" else "%d/%m", showgrid=False)
        fig.update_yaxes(ticksuffix="" if absoluto else " %", range=None if absoluto else [0, 100],
                         title_text=f"Interacciones por {nombre_frec}" if absoluto
                         else f"% de las interacciones de cada {nombre_frec}")
        fig.update_layout(barmode="stack", bargap=0.18, showlegend=False, hovermode="closest", margin=dict(t=12))
        grafico(fig, 300)

# ---------------------------------------------------------------------------
# Alrededor de las evaluaciones (D62)
# ---------------------------------------------------------------------------
MEDIDAS_EVAL = {
    "Relativa a un día típico": ("relativo", "Veces un día típico", "%{y:,.2f}× un día típico", "×"),
    "Interacciones por alumno": ("eventos_por_alumno", "Interacciones por alumno", "%{y:,.2f} por alumno",
                                 " por alumno"),
    "Solo de evaluación, por alumno": ("evaluacion_por_alumno", "Interacciones de evaluación por alumno",
                                       "%{y:,.2f} por alumno", " por alumno"),
}
SUPERPOSICION = "Las evaluaciones de Probabilidad están a pocos días entre sí: sus ventanas se superponen."


def dia_en_palabras(dia: int) -> str:
    if dia == 0:
        return "el mismo día"
    n = abs(dia)
    return f"{n} día{'s' if n > 1 else ''} {'antes' if dia < 0 else 'después'}"


with tab_evals:
    with comp.tarjeta("alrededor"):
        c1, c2 = st.columns([1.4, 1.6], vertical_alignment="bottom")
        medida = c1.selectbox("Medida", list(MEDIDAS_EVAL), key="traz_eval_medida")
        antes, despues = c2.slider("Días antes y después", -14, 7, (-7, 3), key="traz_eval_ventana")
        col, eje, hover, sufijo = MEDIDAS_EVAL[medida]
        alrededor = comp.metrica("actividad_alrededor_evaluaciones", dias_antes=max(-antes, 0),
                                 dias_despues=max(despues, 0))
        alrededor = alrededor[alrededor["dia_relativo"].between(antes, despues)]

        if alrededor.empty:
            st.info("Todavía no hay evaluaciones tomadas a la fecha de corte.", icon=":material/event_busy:")
        else:
            prom = alrededor.groupby(["asignatura", "dia_relativo"], as_index=False) \
                            .agg(valor=(col, "mean"), evaluaciones=("id_instrumento", "nunique"))
            mx = prom.loc[prom["valor"].idxmax()]
            hay_pye = "Probabilidad y Estadística" in set(prom["asignatura"])
            comp.titulo_tarjeta(f"Máximo: {comp.CORTOS[mx['asignatura']]}, {dia_en_palabras(int(mx['dia_relativo']))} "
                                f"de la evaluación ({comp.num(mx['valor'], 1)}{sufijo})",
                                "Promedio de las evaluaciones tomadas de cada materia. El día 0 es la fecha de la "
                                "evaluación.",
                                tip="La fecha de una evaluación es la mediana de sus realizaciones. Usa toda la "
                                    "cursada hasta el corte, no el período elegido; 1× = promedio diario de la "
                                    "materia. Sin recuperatorios." + (" " + SUPERPOSICION if hay_pye else ""))
            leyenda_materias()
            fig = px.line(prom, x="dia_relativo", y="valor", color="asignatura", symbol="asignatura", markers=True,
                          category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                          symbol_map=comp.MARCADORES, custom_data=["evaluaciones"],
                          labels={"dia_relativo": "Días respecto de la evaluación", "valor": "", "asignatura": ""})
            fig.update_traces(hovertemplate="Día %{x}<br>%{fullData.name}: " + hover
                                            + " (promedio de %{customdata[0]} evaluaciones)<extra></extra>",
                              line_width=2.4, marker_size=8)
            fig.add_vline(x=0, line_dash="dot", line_color=comp.TEXTO_2, line_width=1.2,
                          annotation_text="evaluación", annotation_position="top",
                          annotation_font=dict(size=11, color="#2C2A25"))
            if col == "relativo":
                fig.add_hline(y=1, line_dash="dash", line_color=comp.NEUTRO, line_width=1.4,
                              annotation_text="1× día típico", annotation_position="bottom left",
                              annotation_font=dict(size=11, color=comp.TEXTO_2))
                fig.update_yaxes(ticksuffix="×")
            fig.update_xaxes(dtick=1, showgrid=False, ticksuffix=" d")
            fig.update_yaxes(rangemode="tozero", title_text=eje)
            fig.update_layout(showlegend=False, margin=dict(t=28))
            grafico(fig, 300)

            rel = alrededor.groupby(["asignatura", "dia_relativo"])["relativo"].mean()
            presentes = [a for a in f.materias if a in rel.index.get_level_values(0)]
            cols = st.columns(len(presentes))
            for c, asig in zip(cols, presentes):
                r = rel.loc[asig]
                dia = int(r.idxmax())
                c.markdown(comp.mini_tarjeta(
                    comp.CORTOS[asig], f"{comp.num(r.max(), 1)}×",
                    f"Pico {dia_en_palabras(dia)}: {comp.num(r.max(), 1)}× un día típico",
                    comp.COLORES_MATERIA[asig],
                    tip=SUPERPOSICION if asig == "Probabilidad y Estadística" else ""), unsafe_allow_html=True)

    if not alrededor.empty:
        with comp.tarjeta("por_evaluacion"):
            materias_eval = [a for a in f.materias if a in set(alrededor["asignatura"])]
            c1, c2 = st.columns([2.4, 1.2], vertical_alignment="bottom")
            materia_eval = c2.selectbox("Materia", materias_eval, key="traz_eval_materia",
                                        label_visibility="collapsed")
            g = alrededor[alrededor["asignatura"] == materia_eval].copy()
            g["nombre"] = sin_emoji(g["instrumento"]) + "  " + g["fecha_instrumento"].dt.strftime("%d/%m")
            orden_filas = list(dict.fromkeys(g.sort_values("fecha_instrumento")["nombre"]))
            matriz = g.pivot(index="nombre", columns="dia_relativo", values=col).reindex(orden_filas)
            fila_max = matriz.max(axis=1).idxmax()
            dia_max = int(matriz.loc[fila_max].idxmax())
            with c1:
                comp.titulo_tarjeta(f"Máximo: {fila_max.split('  ')[0]}, {dia_en_palabras(dia_max)} "
                                    f"({comp.num(matriz.loc[fila_max].max(), 1)}{sufijo})",
                                    f"{eje} en cada día alrededor de cada evaluación de {comp.CORTOS[materia_eval]}.",
                                    tip="Las celdas vacías son días fuera de los datos (antes del inicio o después "
                                        "de la fecha de corte)."
                                        + (" " + SUPERPOSICION if materia_eval == "Probabilidad y Estadística" else ""))
            fig = go.Figure(go.Heatmap(
                z=matriz.values, x=[f"{c:+d}".replace("+0", "0").replace("-", "−") for c in matriz.columns],
                y=matriz.index, colorscale=comp.SECUENCIAL, xgap=3, ygap=3,
                colorbar=dict(title="", thickness=10, outlinewidth=0, tickfont=dict(color=comp.TEXTO_3, size=10)),
                hovertemplate="%{y}<br>Día %{x}: %{z:,.2f}<extra></extra>"))
            fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=comp.TEXTO_2, size=11))
            fig.update_xaxes(showgrid=False, side="top", tickfont=dict(color=comp.TEXTO_4, size=10))
            fig.update_layout(margin=dict(t=24, l=8, r=8, b=0))
            grafico(fig, 70 + 34 * len(matriz))
            comp.boton_csv(g.drop(columns=["nombre"]), f"trazabilidad_evaluaciones_{comp.SIGLAS[materia_eval]}_"
                           f"{f.fecha_corte:%Y%m%d}", "Descargar estos datos")
