"""Dashboard 2 (del plan): Participación.

Responde: ¿cuántos alumnos están entrando al aula y con qué intensidad?, ¿cómo
evolucionaron los accesos a lo largo de la cursada?, ¿qué herramientas del aula
se usan? y ¿cómo viene cada alumno?

  Período         filtro propio de la página (toda la cursada, últimas 4 o 2
                  semanas o desde una fecha) que termina en la fecha de corte (D53).
  Tarjetas        alumnos, activos, sesiones, minutos y avance promedio por alumno.
  Evolución       accesos por día / semana / mes y por materia (en % de la base o por
                  alumno, para comparar materias de distinto tamaño), con las
                  evaluaciones marcadas; estado de actividad y días sin entrar.
  Reporte         avance, uso de foros / encuestas / correo y el control de las
                  sesiones contra el tiempo de uso del LMS (foto al 24/10, D36).
  Por alumno      tabla filtrable con CSV y la evolución semanal de un alumno contra
                  el promedio de su materia.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes as comp
from src.metricas import ESTADOS_ACTIVIDAD

f = comp.encabezado(
    "Participación",
    "Cuánto y cómo entran los alumnos al aula virtual. La actividad sale de la trazabilidad y se recorta "
    "por el período elegido; el avance y el uso de herramientas salen del reporte de participación "
    "(una foto al 24/10).",
)

ORDEN = {"asignatura": list(comp.COLORES_MATERIA)}

# ---------------------------------------------------------------------------
# Período (filtro propio de la página, D53). Termina siempre en la fecha de corte.
# ---------------------------------------------------------------------------
inicio_datos, _ = comp.rango_fechas()
PERIODOS = ["Toda la cursada", "Últimas 4 semanas", "Últimas 2 semanas", "Desde una fecha"]
c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
periodo = c1.segmented_control("Período", PERIODOS, default=PERIODOS[0], key="part_periodo") or PERIODOS[0]
if periodo == "Desde una fecha":
    st.session_state.setdefault("part_desde", max(inicio_datos, f.fecha_corte - timedelta(days=27)))
    st.session_state["part_desde"] = min(max(st.session_state["part_desde"], inicio_datos), f.fecha_corte)
    desde = c2.date_input("Desde", min_value=inicio_datos, max_value=f.fecha_corte, key="part_desde",
                          format="DD/MM/YYYY")
elif periodo == "Toda la cursada":
    desde = None  # sin recorte: comparte el caché con las otras páginas
else:
    semanas = 4 if "4" in periodo else 2
    desde = max(inicio_datos, f.fecha_corte - timedelta(days=7 * semanas - 1))
texto_periodo = (f"del {comp.fmt_fecha(desde)} al {comp.fmt_fecha(f.fecha_corte)}" if desde
                 else f"desde el inicio de la cursada ({comp.fmt_fecha(inicio_datos)}) al {comp.fmt_fecha(f.fecha_corte)}")
SUFIJO = f"{(desde or inicio_datos):%Y%m%d}_{f.fecha_corte:%Y%m%d}"

alumnos = comp.metrica("participacion_alumnos", desde=desde)
resumen = comp.metrica("resumen_participacion", desde=desde)

# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------
activos = int(alumnos["activo"].sum())
con_actividad = int((alumnos["eventos"] > 0).sum())
comp.tarjetas([
    dict(label="Alumnos", value=comp.num(len(alumnos)),
         delta=f"{comp.num(con_actividad)} entraron en el período", delta_color="off", delta_arrow="off",
         help="Base de alumnos de la materia (inscriptos + con alguna nota, D11). Un alumno que cursa dos "
              "materias cuenta dos veces."),
    dict(label="🟢 Activos", value=comp.num(activos),
         delta=f"{comp.pct(activos / len(alumnos) * 100, 0)} de la base", delta_color="off", delta_arrow="off",
         help=f"Entraron al aula en los últimos {f.umbral} días antes de la fecha de corte (D35)."),
    dict(label="Sesiones por alumno", value=comp.num(alumnos["sesiones"].mean(), 1),
         delta=f"mediana {comp.num(alumnos['sesiones'].median(), 0)}", delta_color="off", delta_arrow="off",
         help="Promedio en el período. Una sesión es una tanda de eventos sin pausas de más de 30 minutos (D25)."),
    dict(label="Minutos por alumno", value=comp.num(alumnos["minutos"].mean(), 0),
         delta=f"mediana {comp.num(alumnos['minutos'].median(), 0)}", delta_color="off", delta_arrow="off",
         help="Suma de la duración de las sesiones en el período, promediada sobre toda la base (con los 0)."),
    dict(label="Avance promedio (al 24/10)", value=comp.pct(alumnos["avance"].mean(), 0),
         help="Del reporte de participación: % del contenido del aula que recorrió el alumno. Es una foto al "
              "24/10 y no cambia con la fecha de corte ni el período (D36)."),
])
st.caption(f"Actividad {texto_periodo}.")

tab_evo, tab_reporte, tab_alumnos = st.tabs(["Evolución", "Reporte de participación (al 24/10)", "Por alumno"])

# ---------------------------------------------------------------------------
# Evolución de los accesos y estado de actividad
# ---------------------------------------------------------------------------
MEDIDAS = {
    "% de la base que entró": ("pct_base_activa", "% de la base", "%{y:.1f} %"),
    "Sesiones por alumno": ("sesiones_por_alumno", "Sesiones por alumno", "%{y:.2f} sesiones por alumno"),
    "Minutos por alumno": ("minutos_por_alumno", "Minutos por alumno", "%{y:.1f} min por alumno"),
    "Interacciones por alumno": ("eventos_por_alumno", "Interacciones por alumno", "%{y:.1f} interacciones por alumno"),
    "Alumnos que entraron": ("alumnos_activos", "Alumnos", "%{y} alumnos"),
    "Sesiones (total)": ("sesiones", "Sesiones", "%{y} sesiones"),
    "Interacciones (total)": ("eventos", "Interacciones", "%{y} interacciones"),
}
FRECUENCIAS = {"Día": "D", "Semana": "W", "Mes": "M"}

with tab_evo:
    st.subheader("Evolución de los accesos")
    c1, c2, c3 = st.columns([1.2, 1.6, 1], vertical_alignment="bottom")
    frecuencia = c1.segmented_control("Agrupar por", list(FRECUENCIAS), default="Semana",
                                      key="part_frecuencia") or "Semana"
    medida = c2.selectbox("Medida", list(MEDIDAS), key="part_medida")
    marcar = c3.toggle("Marcar evaluaciones", value=True, key="part_marcar")
    col, eje, hover = MEDIDAS[medida]

    evo = comp.metrica("evolucion_participacion", frecuencia=FRECUENCIAS[frecuencia], desde=desde)
    fig = px.line(evo, x="periodo", y=col, color="asignatura", markers=frecuencia != "Día",
                  category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                  labels={"periodo": "", col: eje, "asignatura": ""})
    formato_x = {"D": "%d/%m", "W": "sem. del %d/%m", "M": "%m/%Y"}[FRECUENCIAS[frecuencia]]
    fig.update_traces(hovertemplate=f"%{{x|{formato_x}}}<br>%{{fullData.name}}: {hover}<extra></extra>", line_width=2)
    if marcar:
        evals = comp.metrica("fechas_evaluaciones")
        if desde is not None:
            evals = evals[evals["fecha_instrumento"] >= pd.Timestamp(desde)]
        for asig, g in evals.groupby("asignatura"):
            fig.add_trace(go.Scatter(
                x=g["fecha_instrumento"], y=[0] * len(g), mode="markers", name=f"Evaluación {comp.SIGLAS[asig]}",
                marker=dict(symbol="triangle-up", size=11, color=comp.COLORES_MATERIA[asig],
                            line=dict(color="white", width=1)),
                text=g["instrumento"].str.replace(r"^\W+", "", regex=True),
                hovertemplate="%{x|%d/%m}: %{text}<extra>" + asig + "</extra>"))
    fig.update_xaxes(tickformat="%d/%m" if FRECUENCIAS[frecuencia] != "M" else "%m/%Y")
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(height=400, hovermode="closest")
    st.plotly_chart(fig, width="stretch")
    st.caption("Las medidas **por alumno** y el **% de la base** dividen por el tamaño de la base de cada materia, "
               "así se pueden comparar materias con distinta cantidad de alumnos. Las semanas empiezan el lunes y "
               "el último período puede estar incompleto (termina en la fecha de corte). Los triángulos son las "
               "fechas de las evaluaciones (D18): los picos de actividad suelen caer la semana de un parcial.")

    st.subheader("Estado de actividad a la fecha de corte")
    c1, c2 = st.columns(2)
    with c1:
        estado = (alumnos.groupby(["asignatura", "estado_actividad"]).size().rename("alumnos").reset_index())
        estado["pct"] = estado["alumnos"] / estado.groupby("asignatura")["alumnos"].transform("sum") * 100
        estado["etiqueta"] = comp.con_icono(estado["estado_actividad"], comp.ICONOS_ACTIVIDAD)
        fig = px.bar(estado, x="pct", y="asignatura", color="estado_actividad", orientation="h",
                     category_orders={**ORDEN, "estado_actividad": ESTADOS_ACTIVIDAD},
                     color_discrete_map=comp.COLORES_ACTIVIDAD, custom_data=["etiqueta", "alumnos"],
                     text=estado["pct"].map(lambda v: comp.pct(v, 0) if v >= 6 else ""),
                     labels={"pct": "% de la base", "asignatura": "", "estado_actividad": ""})
        fig.update_traces(hovertemplate="%{y}<br>%{customdata[0]}: %{customdata[1]} alumnos (%{x:.1f} %)"
                                        "<extra></extra>",
                          textposition="inside", insidetextanchor="middle", marker_line_width=2,
                          marker_line_color="white")
        fig.update_yaxes(ticktext=[comp.SIGLAS[a] for a in f.materias], tickvals=f.materias)
        fig.update_xaxes(range=[0, 100])
        fig.update_layout(barmode="stack", height=120 + 60 * len(f.materias), bargap=0.3)
        st.plotly_chart(fig, width="stretch")
        st.caption(f"**Activo**: entró en los últimos {f.umbral} días; **inactivo**: entró alguna vez en el período, "
                   "pero hace más; **sin actividad**: no entró en todo el período (D35). Se mueve con el umbral de "
                   "la barra lateral.")
    with c2:
        dias = alumnos.dropna(subset=["dias_sin_actividad"]).astype({"dias_sin_actividad": int})
        fig = px.histogram(dias, x="dias_sin_actividad", color="asignatura", barmode="overlay", opacity=0.75,
                           category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                           labels={"dias_sin_actividad": "Días desde el último ingreso", "asignatura": ""})
        fig.update_traces(xbins=dict(start=-0.5, size=1), hovertemplate="%{x} días: %{y} alumnos<extra></extra>")
        fig.add_vline(x=f.umbral + 0.5, line_dash="dash", line_color=comp.NEUTRO,
                      annotation_text=f"umbral ({f.umbral} días)", annotation_position="top right")
        fig.update_layout(height=120 + 60 * max(len(f.materias), 3), yaxis_title="Alumnos", bargap=0.05)
        st.plotly_chart(fig, width="stretch")
        st.caption("A la derecha de la línea, los inactivos. Una cola larga son alumnos que dejaron hace semanas; "
                   "muchos justo pasando el umbral pueden ser solo una semana floja.")

    st.subheader("Resumen por materia")
    st.dataframe(resumen, hide_index=True, width="stretch", column_config={
        "asignatura": "Materia", "alumnos": st.column_config.NumberColumn("Alumnos", format="%d"),
        "sesiones_promedio": st.column_config.NumberColumn("Sesiones (prom.)", format="%.1f"),
        "sesiones_mediana": st.column_config.NumberColumn("Sesiones (mediana)", format="%.0f"),
        "minutos_promedio": st.column_config.NumberColumn("Minutos (prom.)", format="%.0f"),
        "eventos_promedio": st.column_config.NumberColumn("Interacciones (prom.)", format="%.0f"),
        "tiempo_uso_promedio_min": st.column_config.NumberColumn("Tiempo de uso LMS (prom., al 24/10)",
                                                                 format="%.0f"),
        "avance_promedio": st.column_config.NumberColumn("Avance (prom., al 24/10)", format="%.1f %%"),
        "pct_con_intervencion_foros": st.column_config.NumberColumn("% con intervención en foros", format="%.1f %%"),
        "activo": st.column_config.NumberColumn("Activos", format="%d"),
        "inactivo": st.column_config.NumberColumn("Inactivos", format="%d"),
        "sin_actividad": st.column_config.NumberColumn("Sin actividad", format="%d"),
        "pct_activos": st.column_config.NumberColumn("% activos", format="%.1f %%")})
    comp.boton_csv(resumen, f"resumen_participacion_{SUFIJO}", "Descargar resumen por materia")

# ---------------------------------------------------------------------------
# Reporte de participación (foto al 24/10, D36)
# ---------------------------------------------------------------------------
with tab_reporte:
    st.info("Estos datos salen del **reporte de participación** que exporta el LMS: son una foto al 24/10 y no "
            "cambian con la fecha de corte ni con el período (D36).", icon=":material/photo_camera:")

    st.subheader("Avance en el contenido del aula")
    av = alumnos.dropna(subset=["avance"])
    fig = px.histogram(av, x="avance", color="asignatura", facet_col="asignatura", category_orders=ORDEN,
                       color_discrete_map=comp.COLORES_MATERIA,
                       labels={"avance": "Avance (%)", "asignatura": ""})
    fig.update_traces(xbins=dict(start=0, end=100.001, size=10),
                      hovertemplate="Avance %{x} %: %{y} alumnos<extra></extra>")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_layout(height=320, showlegend=False, bargap=0.05, yaxis_title="Alumnos")
    st.plotly_chart(fig, width="stretch")
    sin_avance = int((av["avance"] == 0).sum())
    st.caption(f"% de los recursos del aula que abrió cada alumno. {comp.num(sin_avance)} alumnos de la base tienen "
               "avance 0. El avance es la variable de actividad que más se relaciona con la nota (D38).")

    st.subheader("Uso de las herramientas del aula")
    herr = comp.metrica("uso_herramientas")
    c1, c2 = st.columns([1.6, 1])
    with c1:
        fig = px.bar(herr, x="pct_alumnos", y="herramienta", color="asignatura", barmode="group", orientation="h",
                     text=herr["pct_alumnos"].map(lambda v: comp.pct(v, 1)), custom_data=["alumnos", "usos"],
                     category_orders={**ORDEN, "herramienta": list(herr["herramienta"].drop_duplicates())},
                     color_discrete_map=comp.COLORES_MATERIA,
                     labels={"pct_alumnos": "% de alumnos que la usó al menos una vez", "herramienta": "",
                             "asignatura": ""})
        fig.update_traces(textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}<br>%{fullData.name}: %{customdata[0]} alumnos (%{x:.1f} %), "
                                        "%{customdata[1]} usos<extra></extra>")
        fig.update_xaxes(range=[0, max(20, herr["pct_alumnos"].max() * 1.3)])
        fig.update_layout(height=140 + 24 * len(herr), bargap=0.2, bargroupgap=0.05)
        st.plotly_chart(fig, width="stretch")
    with c2:
        recursos = herr.pivot(index="herramienta", columns="asignatura", values="recursos") \
                       .reindex(index=herr["herramienta"].drop_duplicates(), columns=f.materias)
        recursos.columns = [comp.SIGLAS[c] for c in recursos.columns]
        st.markdown("**Recursos que ofrece el aula**")
        st.dataframe(recursos.map(lambda v: "–" if pd.isna(v) else str(int(v))), width="stretch")
        st.caption("Cantidad de temas de foro, encuestas, archivos y wikis publicados en cada aula. El correo "
                   "interno no tiene recursos: siempre está disponible.")
    def y_ni(palabras) -> str:
        """['encuestas', 'archivos', 'wikis'] -> 'encuestas, archivos ni wikis'."""
        palabras = list(palabras)
        return palabras[0] if len(palabras) == 1 else ", ".join(palabras[:-1]) + " ni " + palabras[-1]

    maximo = herr.loc[herr["pct_alumnos"].idxmax()] if not herr.empty else None
    if maximo is not None and maximo["pct_alumnos"] < 25:
        foros = herr[(herr["herramienta"] == "Foros") & (herr["recursos"].fillna(0) > 0)]
        sin_recursos = [h for h, g in herr.groupby("herramienta", sort=False)
                        if g["recursos"].notna().all() and (g["recursos"] == 0).all()]
        detalle_foros = (" Hay foros en " + ", ".join(
            f"{comp.SIGLAS[r.asignatura]} ({r.recursos} temas, participa el {comp.pct(r.pct_alumnos)})"
            for r in foros.itertuples()) + "." if not foros.empty else " Ninguna materia tiene foros.")
        st.caption(f"**Hallazgo:** las herramientas de comunicación casi no se usan: la más usada "
                   f"({maximo['herramienta'].lower()} en {comp.SIGLAS[maximo['asignatura']]}) llega al "
                   f"{comp.pct(maximo['pct_alumnos'])} de los alumnos.{detalle_foros}"
                   + (f" No hay {y_ni(h.lower() for h in sin_recursos)} publicados en ninguna materia."
                      if sin_recursos else "")
                   + " La participación se mide entonces por accesos y avance, no por intervenciones: para medir "
                     "participación activa, el equipo docente tendría que proponer actividades en foros o encuestas.")

    st.subheader("Control: minutos de las sesiones vs. tiempo de uso del LMS")
    conc = comp.metrica("concordancia_tiempo")
    control = comp.metrica("participacion_alumnos", fecha_corte=comp.DEFECTOS["fecha_corte"])
    fig = px.scatter(control.dropna(subset=["tiempo_uso_min"]), x="tiempo_uso_min", y="minutos",
                     color="asignatura", category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                     hover_name="nombre_completo", opacity=0.7,
                     labels={"tiempo_uso_min": "Tiempo estimado de uso del reporte (min)",
                             "minutos": "Minutos según las sesiones (min)", "asignatura": ""})
    fig.update_traces(marker_size=7, hovertemplate="%{hovertext}<br>Reporte: %{x} min · Sesiones: %{y:.0f} min"
                                                   "<extra></extra>")
    tope = float(max(control["tiempo_uso_min"].max(), control["minutos"].max()))
    fig.add_trace(go.Scatter(x=[0, tope], y=[0, tope], mode="lines", name="Iguales",
                             line=dict(color=comp.NEUTRO, dash="dot"), hoverinfo="skip"))
    fig.update_layout(height=420)
    st.plotly_chart(fig, width="stretch")
    rhos = " · ".join(f"{comp.SIGLAS[r.asignatura]}: ρ = {comp.num(r.rho, 3)}, las sesiones suman el "
                      f"{comp.pct(r.minutos_total / r.tiempo_uso_total * 100, 0)} del tiempo del reporte"
                      for r in conc.itertuples())
    st.caption(f"Spearman por materia, a la fecha del reporte (24/10). {rhos}. Que el orden de los alumnos sea casi "
               "el mismo valida la forma de armar las sesiones (cortar a los 30 minutos sin eventos, D25): las dos "
               "fuentes cuentan la misma historia. Los minutos de las sesiones pueden quedar por debajo porque no "
               "cuentan el tiempo que pasa después del último clic de cada sesión.")

# ---------------------------------------------------------------------------
# Por alumno
# ---------------------------------------------------------------------------
with tab_alumnos:
    c1, c2 = st.columns([1.4, 2])
    estados = c1.multiselect("Estado de actividad", ESTADOS_ACTIVIDAD, key="part_estados", placeholder="Todos",
                             format_func=lambda e: f"{comp.ICONOS_ACTIVIDAD[e]} {e}")
    texto = c2.text_input("Buscar alumno", key="part_buscar", placeholder="Apellido, nombre o ID")
    vista = alumnos
    if estados:
        vista = vista[vista["estado_actividad"].isin(estados)]
    if texto.strip():
        buscado = vista["nombre_completo"].fillna("") + " " + vista["id_alumno"]
        vista = vista[buscado.str.contains(texto.strip(), case=False, regex=False)]

    columnas = {"asignatura": "Materia", "id_alumno": "ID", "nombre_completo": "Alumno",
                "estado_actividad": "Actividad", "sesiones": "Sesiones", "minutos": "Minutos",
                "eventos": "Interacciones", "dias_activos": "Días activos", "semanas_activas": "Semanas activas",
                "ultima_interaccion": "Último ingreso", "dias_sin_actividad": "Días sin entrar",
                "avance": "Avance (al 24/10)", "tiempo_uso_min": "Tiempo de uso LMS (al 24/10)",
                "intervenciones_foros": "Foros", "encuestas_respondidas": "Encuestas", "emails_enviados": "Correos",
                "inscripto": "Inscripto"}
    if f.asignatura:
        columnas.pop("asignatura")
    tabla = vista.assign(estado_actividad=comp.con_icono(vista["estado_actividad"], comp.ICONOS_ACTIVIDAD))
    tabla = tabla[list(columnas)].rename(columns=columnas)
    st.dataframe(tabla, hide_index=True, width="stretch", height=420, column_config={
        "Último ingreso": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        "Minutos": st.column_config.NumberColumn(format="%.0f"),
        "Avance (al 24/10)": st.column_config.ProgressColumn(format="%d %%", min_value=0, max_value=100),
        "Inscripto": st.column_config.CheckboxColumn()})
    st.caption(f"{comp.num(len(vista))} de {comp.num(len(alumnos))} alumnos. Sesiones, minutos, interacciones y días "
               f"son del período ({texto_periodo}); avance, tiempo de uso, foros, encuestas y correos, del reporte "
               "al 24/10.")
    comp.boton_csv(tabla.assign(Actividad=vista["estado_actividad"].values), f"participacion_alumnos_{SUFIJO}",
                   "Descargar esta lista")

    st.subheader("Actividad de un alumno")
    if vista.empty:
        st.info("No hay alumnos con esos filtros.", icon=":material/search_off:")
    else:
        opciones = list(vista.index)
        elegido = st.selectbox(
            "Alumno", opciones, key="part_alumno",
            format_func=lambda i: f"{vista.at[i, 'nombre_completo']} ({vista.at[i, 'id_alumno']}) · "
                                  f"{comp.SIGLAS[vista.at[i, 'asignatura']]}")
        fila = vista.loc[elegido]
        comp.tarjetas([
            ("Actividad", f"{comp.ICONOS_ACTIVIDAD[fila['estado_actividad']]} {fila['estado_actividad']}",
             f"Último ingreso: {comp.fmt_fecha(fila['ultima_interaccion'])}"),
            ("Sesiones", comp.num(fila["sesiones"])),
            ("Minutos", comp.num(fila["minutos"])),
            ("Semanas activas", comp.num(fila["semanas_activas"])),
            ("Avance (al 24/10)", comp.pct(fila["avance"], 0)),
        ])
        propio = comp.metrica("evolucion_actividad", frecuencia="W", desde=desde, id_alumno=fila["id_alumno"],
                              asignatura=fila["asignatura"])
        materia = comp.metrica("evolucion_participacion", frecuencia="W", desde=desde,
                               asignatura=fila["asignatura"])
        if propio.empty:
            st.info("Este alumno no tiene interacciones en el período.", icon=":material/event_busy:")
        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=propio["periodo"], y=propio["eventos"], name=fila["nombre_completo"],
                                 marker_color=comp.COLORES_MATERIA[fila["asignatura"]],
                                 hovertemplate="sem. del %{x|%d/%m}: %{y} interacciones<extra></extra>"))
            fig.add_trace(go.Scatter(x=materia["periodo"], y=materia["eventos_por_alumno"], mode="lines+markers",
                                     name=f"Promedio de {comp.SIGLAS[fila['asignatura']]}",
                                     line=dict(color=comp.NEUTRO, width=2, dash="dot"),
                                     hovertemplate="sem. del %{x|%d/%m}: %{y:.1f} por alumno<extra></extra>"))
            fig.update_xaxes(tickformat="%d/%m")
            fig.update_layout(height=340, yaxis_title="Interacciones por semana", bargap=0.25)
            st.plotly_chart(fig, width="stretch")
            st.caption("Barras: interacciones del alumno por semana. Línea: promedio de su materia (sobre toda la "
                       "base). Semanas en 0 seguidas al final son la señal típica de abandono. La ficha completa, "
                       "con notas, está en **Ficha individual**.")
