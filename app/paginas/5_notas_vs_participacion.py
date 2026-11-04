"""Dashboard 5 (del plan): Notas vs. participación.

Responde, a la fecha de corte: ¿a los alumnos que más usan el aula les va
mejor?, ¿qué forma de participar se asocia más con la nota? y ¿quiénes están
en riesgo (poca actividad y nota baja)?

  Controles       variable de actividad (VARIABLES_CRUCE) y "solo quienes
                  rindieron algo", que saca los 0 por no rendir (D55).
  Tarjetas        ρ de Spearman de la variable elegida en cada materia y
                  alumnos en riesgo (D37).
  Dispersión      un punto por alumno, coloreado por condición, con la
                  tendencia (nota promedio de cada quinto de actividad) y los
                  cortes de Regular y Promociona.
  Correlaciones   mapa de calor variable × materia con ρ, y la tabla con
                  p-valor, n y fuerza (D38).
  Por nivel       los alumnos en 5 grupos iguales según la actividad: % por
                  condición y nota promedio de cada grupo (D55).
  Cuadrante       actividad vs. nota partido por la mediana y por Libre (D37),
                  conteo por cuadrante y lista de alumnos en riesgo con CSV.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
import plotly.graph_objects as go
import streamlit as st

import componentes as comp
from src.config import CONDICIONES, ESQUEMA, SIN_EVALUACIONES
from src.metricas import NIVELES_ACTIVIDAD, VARIABLES_CRUCE

f = comp.encabezado(
    "Notas vs. participación",
    "¿A los alumnos que más usan el aula les va mejor? ¿Quiénes tienen poca actividad y nota baja?",
)

DEL_REPORTE = {"tiempo_uso_min", "avance"}   # foto del reporte de participación (D36)
UNIDAD = {"minutos": "min", "tiempo_uso_min": "min", "avance": "%"}
CUADRANTES = {  # orden de lectura, color e ícono: el riesgo en rojo, el resto en tonos de estado (D48)
    "Riesgo: poca actividad y nota baja": (comp.CRITICO, "🔴"),
    "Activo con nota baja": (comp.SERIO, "🟠"),
    "Poca actividad con buena nota": (comp.ATENCION, "🟡"),
    "Activo con buena nota": (comp.BIEN, "🟢"),
}

# ---------------------------------------------------------------------------
# Controles de la página
# ---------------------------------------------------------------------------
c1, c2 = st.columns([2, 3], vertical_alignment="bottom")
variable = c1.selectbox("Actividad", list(VARIABLES_CRUCE), format_func=VARIABLES_CRUCE.get, key="nvp_variable",
                        help="La variable de participación que se cruza con la nota en toda la página.")
solo_rindieron = c2.toggle(
    "Solo alumnos que rindieron al menos una evaluación", key="nvp_solo_rindieron",
    help="Quien no rindió nada tiene 0 (D15) y casi siempre también poca actividad: eso solo ya arma "
         "una correlación. Sacarlos muestra si la actividad se asocia con la nota entre los que sí rinden (D55).")
nombre_var = VARIABLES_CRUCE[variable]
if variable in DEL_REPORTE:
    st.caption(f":material/info: *{nombre_var}* sale del reporte de participación: es una foto a la fecha de "
               "exportación y no se recorta con la fecha de corte (D36).")

alumnos = comp.metrica("cuadrante_riesgo", variable=variable)
if alumnos["nota_pct"].isna().all():
    st.info(f"Al {comp.fmt_fecha(f.fecha_corte)} todavía no se tomó ninguna evaluación en "
            f"{f.materia.lower()}: no hay notas para cruzar. Mové la fecha de corte.", icon=":material/event_busy:")
    st.stop()

corr = comp.metrica("correlaciones", solo_rindieron=solo_rindieron)
niveles = comp.metrica("nota_por_nivel_actividad", variable=variable, solo_rindieron=solo_rindieron)
puntos = alumnos[alumnos["rendidos"] > 0] if solo_rindieron else alumnos
materias = [m for m in f.materias if m in set(alumnos["asignatura"])]


def fmt_var(x) -> str:
    return f"{comp.num(x, 0)} {UNIDAD.get(variable, '')}".strip()


# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------
elegida = corr[corr["variable"] == variable].set_index("asignatura")
items = []
for materia in materias:
    fila = elegida.loc[materia]
    items.append(dict(
        label=f"ρ {comp.SIGLAS[materia]}", value=comp.num(fila["rho"], 2),
        delta=f"{fila['fuerza']}{'' if fila['significativa'] else ' · no significativa'}",
        delta_color="off", delta_arrow="off",
        help=f"Correlación de Spearman entre {nombre_var.lower()} y la nota en {materia} "
             f"(n = {fila['n']}, p = {comp.num(fila['p_valor'], 4)}). Va de -1 a 1: cuanto más cerca de 1, "
             "más se cumple que a más actividad, más nota (D38)."))
riesgo = alumnos[alumnos["en_riesgo"]]
items.append(dict(
    label="🔴 En riesgo", value=comp.num(len(riesgo)),
    delta=f"{comp.pct(len(riesgo) / len(alumnos) * 100)} de la base", delta_color="off", delta_arrow="off",
    help=f"Alumnos con {nombre_var.lower()} por debajo de la mediana de su materia y condición Libre "
         "a la fecha de corte (D37)."))
comp.tarjetas(items)

tab_disp, tab_corr, tab_nivel, tab_cuad = st.tabs(
    ["Dispersión", "Correlaciones", "Por nivel de actividad", "Cuadrante de riesgo"])

# ---------------------------------------------------------------------------
# Dispersión con tendencia
# ---------------------------------------------------------------------------
with tab_disp:
    st.caption(f"Cada punto es un alumno: {nombre_var.lower()} contra la nota a la fecha de corte, en la escala "
               "de la materia. El color es la condición. La línea une la **nota promedio de cada quinto** de "
               "alumnos (del 20 % que menos actividad tiene al que más): si sube, a más actividad, más nota. "
               "Las líneas punteadas son los cortes de Regular y Promociona.")
    escala_log = st.toggle("Eje horizontal en escala logarítmica", key="nvp_log",
                           help="Separa a los alumnos con poca actividad, que en escala lineal quedan "
                                "amontonados a la izquierda. Los que tienen 0 no se ven en esta escala.")
    presentes = [c for c in [*CONDICIONES, SIN_EVALUACIONES] if c in set(puntos["condicion"])]
    st.markdown(" · ".join(f"{comp.ICONOS_CONDICION[c]} {c}" for c in presentes) + " · ◆ **Tendencia**")
    cols = st.columns(len(materias)) if len(materias) > 1 else [st.container()]
    for col, materia in zip(cols, materias):
        datos_m = puntos[puntos["asignatura"] == materia]
        tend = niveles[niveles["asignatura"] == materia]
        esq = ESQUEMA[materia]
        fig = go.Figure()
        for cond in [*CONDICIONES, SIN_EVALUACIONES]:
            q = datos_m[datos_m["condicion"] == cond]
            if q.empty:
                continue
            fig.add_trace(go.Scatter(
                x=q[variable], y=q["nota_final"], mode="markers", name=f"{comp.ICONOS_CONDICION[cond]} {cond}",
                marker=dict(color=comp.COLORES_CONDICION[cond], size=7, opacity=0.7,
                            line=dict(width=0.5, color="white")),
                customdata=q[["nombre_completo", "id_alumno"]],
                hovertemplate="%{customdata[0]} (%{customdata[1]})<br>" + nombre_var + ": %{x:,.0f}"
                              "<br>Nota: %{y:.1f}<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=tend["mediana_actividad"], y=tend["nota_final"], mode="lines+markers", name="Tendencia",
            line=dict(color="#0b0b0b", width=2.5), marker=dict(size=9, symbol="diamond"),
            customdata=tend[["nivel", "alumnos"]],
            hovertemplate="Actividad %{customdata[0]} (%{customdata[1]} alumnos)<br>"
                          "Nota promedio: %{y:.1f}<extra></extra>"))
        for nombre, corte in esq["cortes"].items():
            fig.add_hline(y=corte, line_dash="dot", line_color=comp.COLORES_CONDICION[nombre], line_width=1.5,
                          annotation_text=nombre, annotation_position="top left",
                          annotation_font_color=comp.COLORES_CONDICION[nombre])
        fig.update_layout(title=dict(text=materia if len(materias) > 1 else "", font_size=15),
                          height=430, showlegend=False, margin=dict(t=40))
        fig.update_xaxes(title_text=nombre_var, type="log" if escala_log else "linear")
        fig.update_yaxes(title_text=f"Nota (sobre {esq['total_max']})", range=[-4, esq["total_max"] + 4])
        col.plotly_chart(fig, width="stretch", key=f"disp_{materia}")

# ---------------------------------------------------------------------------
# Correlaciones
# ---------------------------------------------------------------------------
with tab_corr:
    st.caption("Correlación de Spearman entre cada forma de participar y la nota (sobre 100), en cada materia "
               "(D38). Va de -1 a 1: 0 es que no hay relación y 1 que el orden por actividad coincide con el "
               "orden por nota. Guía: < 0,1 nula, < 0,3 débil, < 0,5 moderada, ≥ 0,5 fuerte. "
               "**Correlación no es causa:** los alumnos más comprometidos entran más *y* estudian más.")
    tabla = corr[corr["asignatura"].isin(materias)]
    matriz = tabla.pivot(index="descripcion", columns="asignatura", values="rho")
    matriz = matriz.loc[[VARIABLES_CRUCE[v] for v in VARIABLES_CRUCE if VARIABLES_CRUCE[v] in matriz.index],
                        materias]
    matriz = matriz.loc[matriz.mean(axis=1).sort_values().index]   # la más asociada arriba
    texto = matriz.map(lambda v: comp.num(v, 2))
    fig = go.Figure(go.Heatmap(
        z=matriz.values, x=[comp.SIGLAS[m] for m in matriz.columns], y=list(matriz.index),
        zmin=0, zmax=1, colorscale=[[i / (len(comp.SECUENCIAL) - 1), c] for i, c in enumerate(comp.SECUENCIAL)],
        text=texto.values, texttemplate="%{text}", textfont_size=14, xgap=3, ygap=3,
        colorbar=dict(title="ρ", thickness=12),
        hovertemplate="%{y}<br>%{x}: ρ = %{z:.2f}<extra></extra>"))
    fig.update_layout(height=80 + 52 * len(matriz), margin=dict(t=16))
    fig.update_xaxes(side="top", showgrid=False)
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, width="stretch", key="corr_heatmap")

    if solo_rindieron:
        st.caption("Calculadas solo con quienes rindieron al menos una evaluación.")
    vista = tabla.assign(
        Materia=tabla["asignatura"], Variable=tabla["descripcion"], ρ=tabla["rho"],
        **{"p-valor": tabla["p_valor"], "Alumnos (n)": tabla["n"], "Fuerza": tabla["fuerza"],
           "Significativa (p < 0,05)": tabla["significativa"]},
    )[["Materia", "Variable", "ρ", "p-valor", "Alumnos (n)", "Fuerza", "Significativa (p < 0,05)"]]
    st.dataframe(vista, hide_index=True, width="stretch",
                 column_config={"ρ": st.column_config.NumberColumn(format="%.2f"),
                                "p-valor": st.column_config.NumberColumn(format="%.4f")})
    comp.boton_csv(vista, "correlaciones_notas_participacion")

# ---------------------------------------------------------------------------
# Por nivel de actividad (quintiles)
# ---------------------------------------------------------------------------
with tab_nivel:
    st.caption(f"Los alumnos de cada materia se ordenan por {nombre_var.lower()} y se parten en **5 grupos del "
               "mismo tamaño** (D55). Cada barra muestra cómo se reparte la condición dentro del grupo; el número "
               "de arriba es la nota promedio sobre 100. Se lee sin estadística: *del 20 % que menos entra, "
               "¿cuántos están libres?*")
    columnas_cond = {c: f"pct_{c.lower()}" for c in CONDICIONES} | {SIN_EVALUACIONES: "pct_sin_evaluaciones"}
    for materia in materias:
        n_m = niveles[niveles["asignatura"] == materia].sort_values("orden")
        if n_m.empty:
            continue
        eje = [f"{fila.nivel}<br><sub>{fmt_var(fila.desde)} a {fmt_var(fila.hasta)}</sub>"
               for fila in n_m.itertuples()]
        fig = go.Figure()
        for cond, col_pct in columnas_cond.items():
            if n_m[col_pct].sum() == 0:
                continue
            fig.add_trace(go.Bar(
                x=eje, y=n_m[col_pct], name=f"{comp.ICONOS_CONDICION[cond]} {cond}",
                marker_color=comp.COLORES_CONDICION[cond],
                text=n_m[col_pct].map(lambda v: comp.pct(v, 0) if v >= 7 else ""), textposition="inside",
                insidetextanchor="middle", customdata=n_m[["alumnos"]],
                hovertemplate=f"{cond}: %{{y:.1f}} % de %{{customdata[0]}} alumnos<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=eje, y=[104] * len(n_m), mode="text", showlegend=False, hoverinfo="skip",
            text=n_m["nota_pct"].map(lambda v: f"<b>{comp.num(v, 1)}</b>"), textfont=dict(size=13)))
        fig.update_layout(barmode="stack", height=380, bargap=0.3, margin=dict(t=56),
                          title=dict(text=materia, font_size=15))
        fig.update_yaxes(title_text="% del grupo", range=[0, 110], dtick=25)
        fig.update_xaxes(title_text=f"Nivel de actividad ({nombre_var.lower()})", tickangle=0)
        st.plotly_chart(fig, width="stretch", key=f"nivel_{materia}")

    if not niveles.empty:
        vista = niveles.assign(
            Materia=niveles["asignatura"], Nivel=niveles["nivel"], Alumnos=niveles["alumnos"],
            Desde=niveles["desde"], Hasta=niveles["hasta"], **{"Nota promedio (sobre 100)": niveles["nota_pct"]},
            **{f"% {c}": niveles[col] for c, col in columnas_cond.items() if niveles[col].sum() > 0},
        ).drop(columns=niveles.columns)
        with st.expander("Ver la tabla"):
            st.dataframe(vista, hide_index=True, width="stretch")
            comp.boton_csv(vista, f"nota_por_nivel_{variable}")

# ---------------------------------------------------------------------------
# Cuadrante de riesgo
# ---------------------------------------------------------------------------
with tab_cuad:
    st.caption(f"Se parte a los alumnos en cuatro según dos preguntas (D37): ¿su {nombre_var.lower()} está por "
               "debajo de la **mediana de su materia**? (línea vertical) y ¿está **Libre** a la fecha de corte? "
               "(debajo de la línea de Regular). Abajo a la izquierda están los que piden contacto primero. "
               "Usa toda la base, también a quienes no rindieron nada.")
    conteo = (alumnos.groupby(["asignatura", "cuadrante"]).size().rename("alumnos").reset_index())
    cols = st.columns(len(materias)) if len(materias) > 1 else [st.container()]
    for col, materia in zip(cols, materias):
        datos_m = alumnos[alumnos["asignatura"] == materia]
        esq = ESQUEMA[materia]
        mediana = datos_m["mediana_actividad"].iloc[0]
        corte = esq["cortes"]["Regular"]
        fig = go.Figure()
        for cuad, (color, _) in CUADRANTES.items():
            q = datos_m[datos_m["cuadrante"] == cuad]
            fig.add_trace(go.Scatter(
                x=q[variable], y=q["nota_final"], mode="markers", name=cuad,
                marker=dict(color=color, size=7, opacity=0.75, line=dict(width=0.5, color="white"),
                            symbol="x" if cuad.startswith("Riesgo") else "circle"),
                customdata=q[["nombre_completo", "id_alumno"]],
                hovertemplate="%{customdata[0]} (%{customdata[1]})<br>" + nombre_var + ": %{x:,.0f}"
                              "<br>Nota: %{y:.1f}<extra></extra>"))
        fig.add_vline(x=mediana, line_dash="dash", line_color=comp.NEUTRO,
                      annotation_text=f"Mediana: {fmt_var(mediana)}", annotation_position="top right")
        fig.add_hline(y=corte, line_dash="dash", line_color=comp.CRITICO,
                      annotation_text="Corte de Regular", annotation_position="bottom right",
                      annotation_font_color=comp.CRITICO)
        fig.update_layout(title=dict(text=materia if len(materias) > 1 else "", font_size=15), height=430,
                          showlegend=False, margin=dict(t=40))
        fig.update_xaxes(title_text=nombre_var)
        fig.update_yaxes(title_text=f"Nota (sobre {esq['total_max']})", range=[-4, esq["total_max"] + 4])
        col.plotly_chart(fig, width="stretch", key=f"cuad_{materia}")

        c = conteo[conteo["asignatura"] == materia].set_index("cuadrante")["alumnos"]
        col.markdown("  \n".join(
            f"{icono} {cuad}: **{comp.num(c.get(cuad, 0))}** ({comp.pct(c.get(cuad, 0) / len(datos_m) * 100, 0)})"
            for cuad, (_, icono) in CUADRANTES.items()))

    st.subheader(f"Alumnos en riesgo ({comp.num(len(riesgo))})")
    if riesgo.empty:
        st.success("No hay alumnos con poca actividad y condición Libre a la fecha de corte.")
    else:
        lista = riesgo.sort_values(["asignatura", "nota_pct", variable]).assign(
            Materia=riesgo["asignatura"], ID=riesgo["id_alumno"], Alumno=riesgo["nombre_completo"],
            Inscripto=riesgo["inscripto"],
            **{"Nota": riesgo["nota_final"], "Escala": riesgo["escala"], "Rendidas": riesgo["rendidos"],
               "Evaluaciones": riesgo["instrumentos"], nombre_var: riesgo[variable],
               "Mediana de la materia": riesgo["mediana_actividad"],
               "Días sin entrar": riesgo["dias_sin_actividad"],
               "Actividad": comp.con_icono(riesgo["estado_actividad"], comp.ICONOS_ACTIVIDAD)},
        )[["Materia", "ID", "Alumno", "Inscripto", "Nota", "Escala", "Rendidas", "Evaluaciones", nombre_var,
           "Mediana de la materia", "Días sin entrar", "Actividad"]]
        st.dataframe(lista, hide_index=True, width="stretch",
                     column_config={"Nota": st.column_config.NumberColumn(format="%.1f"),
                                    nombre_var: st.column_config.NumberColumn(format="%.0f")})
        comp.boton_csv(lista, f"alumnos_en_riesgo_{variable}")
