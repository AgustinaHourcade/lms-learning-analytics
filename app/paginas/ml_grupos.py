"""Machine learning: grupos de alumnos con K-Means (Etapa 7, D57).

Todo el cálculo está en src/ml_grupos.py; esta página solo lo muestra.
El modelo se ajusta con las tres materias juntas: el filtro de materia de la
barra lateral recorta lo que se ve, pero no cambia los grupos."""
import re

import pandas as pd
import plotly.express as px
import streamlit as st

import componentes as comp
from src.config import GRUPOS_K
from src.ml_grupos import SIN_GRUPO

f = comp.encabezado(
    "Grupos de alumnos",
    "Agrupamos a los alumnos con **K-Means** según cómo usan el aula y cómo les va: sesiones, minutos, "
    "semanas con actividad, avance y nota. Cada alumno se compara con **su materia**, así que "
    "\"poca actividad\" quiere decir poca para su curso. Sirve para mirar unos pocos perfiles, cada uno con "
    "una acción, en vez de cientos de alumnos uno por uno.")

# Un color fijo por tipo de grupo (de mejor a peor perfil), siempre con el nombre al lado.
COLORES_GRUPO = {"Comprometidos": comp.BIEN, "Eficientes": comp.CATEGORICA[0],
                 "Esforzados con nota baja": comp.ATENCION, "Intermitentes": comp.SERIO,
                 "Desconectados": comp.CRITICO, SIN_GRUPO: comp.NEUTRO}
ICONOS_GRUPO = {"Comprometidos": "🟢", "Eficientes": "🔵", "Esforzados con nota baja": "🟡",
                "Intermitentes": "🟠", "Desconectados": "🔴", SIN_GRUPO: "⚪"}
DIVERGENTE = [comp.CATEGORICA[1], "#f4f3ef", comp.CATEGORICA[0]]   # abajo del promedio / promedio / arriba


def tipo(nombre: str) -> str:
    """'Intermitentes (2)' -> 'Intermitentes' (si dos grupos caen en el mismo tipo)."""
    return re.sub(r" \(\d+\)$", "", nombre)


# --- Cantidad de grupos -----------------------------------------------------
AUTO = "Automático (silhouette)"
eleccion = st.segmented_control("Cantidad de grupos", [AUTO, *[str(k) for k in GRUPOS_K]], default=AUTO,
                                key="ml_k", help="Por defecto se elige el k con mayor silhouette entre 3 y 6. "
                                                 "Se puede forzar otro para comparar.")
k = None if eleccion in (None, AUTO) else int(eleccion)

alumnos = comp.metrica("grupos_alumnos", k=k)
if alumnos.empty or alumnos["grupo"].eq(0).all():
    st.info("A esta fecha de corte ninguna materia tiene evaluaciones todavía: sin nota, los grupos no se "
            "pueden armar. Mové la fecha de corte a después del 21/08/2025 para ver las tres materias.",
            icon=":material/info:")
    st.stop()

perfil = comp.metrica("perfil_grupos", k=k)
perfil_materia = comp.metrica("perfil_grupos", k=k, por_materia=True)
centros = comp.metrica("centroides", k=k)
evaluacion = comp.metrica("evaluar_k")
k_usado = int(perfil["grupo"].max())
colores = {n: COLORES_GRUPO.get(tipo(n), comp.NEUTRO) for n in perfil["nombre_grupo"]}
orden = perfil.sort_values("grupo")["nombre_grupo"].tolist()

sin_grupo = alumnos["grupo"].eq(0).sum()
if sin_grupo:
    materias_sin = ", ".join(alumnos.loc[alumnos["grupo"].eq(0), "asignatura"].map(comp.SIGLAS).unique())
    st.warning(f"{comp.num(sin_grupo)} alumnos quedan **sin grupo**: su materia ({materias_sin}) todavía no "
               "tiene evaluaciones a esta fecha de corte.", icon=":material/warning:")

# --- Los grupos ---------------------------------------------------------------
st.subheader(f"Los {k_usado} grupos")
con_grupo = perfil[perfil["grupo"] > 0]
cols = st.columns(len(con_grupo))
for col, (_, g) in zip(cols, con_grupo.iterrows()):
    with col.container(border=True):
        st.markdown(f"**{ICONOS_GRUPO.get(tipo(g['nombre_grupo']), '⚪')} {g['nombre_grupo']}**")
        st.metric(f"Alumnos · {comp.pct(g['pct'])} de la base", comp.num(g["alumnos"]))
        st.caption(g["descripcion_grupo"])
        st.markdown(
            f"- **{comp.num(g['mediana_sesiones'])}** sesiones · **{comp.num(g['mediana_minutos'])}** min\n"
            f"- **{comp.num(g['mediana_semanas_activas'])}** semanas con actividad\n"
            f"- Avance **{comp.pct(g['mediana_avance'], 0)}** · nota **{comp.num(g['mediana_nota_pct'])}**\n"
            f"- Libre **{comp.pct(g.get('pct_libre'), 0)}** · activos hoy **{comp.pct(g['pct_activos'], 0)}**")
st.caption("Medianas de cada grupo. Nota sobre 100 a la fecha de corte; el avance es el del reporte de "
           "participación (foto al 24/10).")

izq, der = st.columns(2)
with izq:
    st.markdown("**Qué distingue a cada grupo**")
    mapa = (centros.pivot(index="nombre_grupo", columns="descripcion", values="desvios")
                   .reindex([n for n in orden if n in set(centros["nombre_grupo"])]))
    fig = px.imshow(mapa, text_auto=".1f", aspect="auto", zmin=-2, zmax=2, color_continuous_scale=DIVERGENTE,
                    labels={"x": "", "y": "", "color": "Desvíos"})
    fig.update_layout(height=320, coloraxis_colorbar=dict(title="Desvíos"))
    fig.update_xaxes(tickangle=-20)
    st.plotly_chart(fig, width="stretch")
    st.caption("Centro de cada grupo, en desvíos respecto del promedio de su materia: 0 = el promedio, "
               "+1 = bastante por encima, −1 = bastante por debajo.")
with der:
    st.markdown("**Cuántos hay de cada grupo en cada materia**")
    pm = perfil_materia.assign(materia=perfil_materia["asignatura"].map(comp.SIGLAS))
    fig = px.bar(pm, x="pct", y="materia", color="nombre_grupo", orientation="h", text="pct",
                 color_discrete_map=colores, category_orders={"nombre_grupo": orden},
                 labels={"pct": "% de la base", "materia": "", "nombre_grupo": "Grupo"},
                 hover_data={"alumnos": True})
    fig.update_traces(texttemplate="%{text:.0f} %", textposition="inside")
    fig.update_layout(height=320, xaxis_range=[0, 100])
    st.plotly_chart(fig, width="stretch")

# --- Mapa de los grupos (PCA) ---------------------------------------------------
st.subheader("Mapa de los grupos")
st.markdown("El K-Means mira las 5 variables a la vez. Para poder dibujarlo, las resumimos en **2 ejes** con "
            "PCA (análisis de componentes principales): cada punto es un alumno y alumnos parecidos quedan cerca. "
            "La ✕ marca el centro de cada grupo.")
mapa = comp.metrica("mapa_grupos", k=k)
var1, var2 = mapa["varianza"]
pts = mapa["alumnos"].assign(materia=lambda t: t["asignatura"].map(comp.SIGLAS))
izq, der = st.columns([2, 1])
with izq:
    fig = px.scatter(pts, x="eje1", y="eje2", color="nombre_grupo", color_discrete_map=colores,
                     category_orders={"nombre_grupo": orden}, opacity=0.65,
                     hover_data={"id_alumno": True, "nombre_completo": True, "materia": True, "condicion": True,
                                 "nota_pct": ":.1f", "minutos": ":.0f", "avance": True, "eje1": False, "eje2": False},
                     labels={"eje1": f"Eje 1 · compromiso general ({comp.pct(var1, 0)} de la variación)",
                             "eje2": f"Eje 2 · rinde más de lo que entra ({comp.pct(var2, 0)})",
                             "nombre_grupo": "Grupo", "nombre_completo": "Alumno", "id_alumno": "ID",
                             "materia": "Materia", "condicion": "Condición", "nota_pct": "Nota",
                             "minutos": "Minutos", "avance": "Avance (%)"})
    c = mapa["centros"]
    fig.add_scatter(x=c["eje1"], y=c["eje2"], mode="markers", text=c["nombre_grupo"],
                    marker=dict(symbol="x", size=16, color=[colores.get(n, comp.NEUTRO) for n in c["nombre_grupo"]],
                                line=dict(width=2, color="#0b0b0b")),
                    name="Centro", showlegend=False, hovertemplate="%{text}<extra>centro</extra>")
    for _, centro in c.iterrows():   # etiqueta con fondo para que se lea sobre los puntos
        fig.add_annotation(x=centro["eje1"], y=centro["eje2"], text=f"<b>{centro['nombre_grupo']}</b>",
                           yshift=18, showarrow=False, bgcolor="rgba(255,255,255,0.85)",
                           bordercolor=colores.get(centro["nombre_grupo"], comp.NEUTRO), borderpad=3)
    fig.update_layout(height=460)
    st.plotly_chart(fig, width="stretch")
with der:
    st.markdown("**Cómo leer los ejes**")
    cargas = mapa["cargas"].melt(id_vars=["variable", "descripcion"], value_vars=["eje1", "eje2"],
                                 var_name="eje", value_name="peso")
    cargas["eje"] = cargas["eje"].map({"eje1": "Eje 1", "eje2": "Eje 2"})
    cortos = {"sesiones": "Sesiones", "minutos": "Minutos", "semanas_activas": "Semanas activas",
              "avance": "Avance", "nota_pct": "Nota"}
    cargas["nombre"] = cargas["variable"].map(cortos)
    fig = px.bar(cargas, x="peso", y="nombre", color="eje", barmode="group", orientation="h", text="peso",
                 color_discrete_sequence=[comp.CATEGORICA[0], comp.CATEGORICA[1]],
                 category_orders={"nombre": list(cortos.values())},
                 hover_data={"descripcion": True, "nombre": False},
                 labels={"peso": "Peso en el eje", "nombre": "", "eje": "", "descripcion": "Variable"})
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
    fig.update_layout(height=320, xaxis_range=[-1, 1.15], margin=dict(l=8, r=24))
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        f"- **Eje 1 (horizontal, {comp.pct(var1, 0)}):** todas las variables pesan casi igual. A la derecha, los "
        "que entran más, avanzan más y tienen mejor nota; a la izquierda, lo contrario.\n"
        f"- **Eje 2 (vertical, {comp.pct(var2, 0)}):** contrapone nota y avance contra sesiones y minutos. Arriba, "
        "los que rinden más de lo que entran; abajo, los que entran mucho para la nota que tienen.\n\n"
        f"Entre los dos ejes resumen el **{comp.pct(var1 + var2, 0)}** de la información de las 5 variables, así "
        "que el mapa representa bien lo que ve el modelo.")
st.caption("Las variables están en desvíos respecto del promedio de cada materia (con logaritmo en sesiones y "
           "minutos), igual que en el modelo: por eso los ejes no tienen unidades.")

# --- Alumnos en las variables originales -----------------------------------------
st.subheader("Cómo se ven los grupos en las variables originales")
st.caption("Acá se ven solo 2 de las 5 variables y en sus unidades reales, así que los grupos se superponen: "
           "un alumno puede estar cerca de otro grupo en minutos y nota, pero lejos en avance o semanas activas.")
VARIABLES = {"minutos": "Minutos en la plataforma", "sesiones": "Sesiones",
             "semanas_activas": "Semanas con actividad", "avance": "Avance (%)"}
variable = st.selectbox("Actividad (eje horizontal)", list(VARIABLES), format_func=VARIABLES.get, key="ml_var")
puntos = alumnos[alumnos["grupo"] > 0].assign(materia=lambda t: t["asignatura"].map(comp.SIGLAS))
fig = px.scatter(puntos, x=variable, y="nota_pct", color="nombre_grupo", facet_col="materia" if not f.asignatura else None,
                 color_discrete_map=colores, category_orders={"nombre_grupo": orden}, opacity=0.75,
                 log_x=variable in ("minutos", "sesiones"),
                 hover_data={"id_alumno": True, "nombre_completo": True, "condicion": True, "materia": False},
                 labels={variable: VARIABLES[variable], "nota_pct": "Nota (sobre 100)", "nombre_grupo": "Grupo",
                         "nombre_completo": "Alumno", "id_alumno": "ID", "condicion": "Condición"})
fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
fig.update_layout(height=420)
st.plotly_chart(fig, width="stretch")
if variable in ("minutos", "sesiones"):
    st.caption("Eje horizontal en escala logarítmica (los alumnos con 0 no se ven).")

izq, der = st.columns(2)
with izq:
    st.markdown("**Condición de cada grupo**")
    cond = (alumnos[alumnos["grupo"] > 0].groupby(["nombre_grupo", "condicion"]).size()
            .rename("alumnos").reset_index())
    cond["pct"] = 100 * cond["alumnos"] / cond.groupby("nombre_grupo")["alumnos"].transform("sum")
    fig = px.bar(cond, x="pct", y="nombre_grupo", color="condicion", orientation="h", text="pct",
                 color_discrete_map=comp.COLORES_CONDICION,
                 category_orders={"nombre_grupo": orden, "condicion": ["Libre", "Regular", "Promociona"]},
                 labels={"pct": "% del grupo", "nombre_grupo": "", "condicion": "Condición"},
                 hover_data={"alumnos": True})
    fig.update_traces(texttemplate="%{text:.0f} %", textposition="inside")
    fig.update_layout(height=280, xaxis_range=[0, 100])
    st.plotly_chart(fig, width="stretch")
with der:
    st.markdown("**Estado de actividad de cada grupo**")
    act = (alumnos[alumnos["grupo"] > 0].groupby(["nombre_grupo", "estado_actividad"]).size()
           .rename("alumnos").reset_index())
    act["pct"] = 100 * act["alumnos"] / act.groupby("nombre_grupo")["alumnos"].transform("sum")
    fig = px.bar(act, x="pct", y="nombre_grupo", color="estado_actividad", orientation="h", text="pct",
                 color_discrete_map=comp.COLORES_ACTIVIDAD, category_orders={"nombre_grupo": orden},
                 labels={"pct": "% del grupo", "nombre_grupo": "", "estado_actividad": "Actividad"},
                 hover_data={"alumnos": True})
    fig.update_traces(texttemplate="%{text:.0f} %", textposition="inside")
    fig.update_layout(height=280, xaxis_range=[0, 100])
    st.plotly_chart(fig, width="stretch")
st.caption(f"Los grupos no son lo mismo que la condición ni que el estado de actividad (inactivo = más de "
           f"{f.umbral} días sin entrar): hay alumnos que entran mucho y están libres, y otros comprometidos "
           "que dejaron de entrar hace poco.")

# --- Lista de alumnos ------------------------------------------------------------
st.subheader("Alumnos por grupo")
elegidos = st.multiselect("Grupos", orden, default=[n for n in orden if tipo(n) != "Comprometidos"], key="ml_grupos",
                          help="Por defecto, los grupos que piden alguna acción.")
lista = alumnos[alumnos["nombre_grupo"].isin(elegidos)]
tabla = pd.DataFrame({
    "Materia": lista["asignatura"].map(comp.SIGLAS), "ID": lista["id_alumno"], "Alumno": lista["nombre_completo"],
    "Grupo": lista["nombre_grupo"].map(lambda n: f"{ICONOS_GRUPO.get(tipo(n), '⚪')} {n}"),
    "Condición": comp.con_icono(lista["condicion"], comp.ICONOS_CONDICION),
    "Nota": lista["nota_pct"], "Sesiones": lista["sesiones"], "Minutos": lista["minutos"],
    "Semanas activas": lista["semanas_activas"], "Avance (%)": lista["avance"],
    "Días sin entrar": lista["dias_sin_actividad"],
})
st.dataframe(tabla, hide_index=True, width="stretch",
             column_config={"Nota": st.column_config.NumberColumn(format="%.1f"),
                            "Minutos": st.column_config.NumberColumn(format="%.0f")})
st.caption(f"{comp.num(len(tabla))} alumnos.")
comp.boton_csv(tabla, "grupos_alumnos")

# --- Cómo se eligió k ------------------------------------------------------------
with st.expander("Cómo se armaron los grupos y qué tan confiables son", icon=":material/science:"):
    st.markdown(
        "1. **Variables:** sesiones, minutos, semanas con actividad, avance y nota, a la fecha de corte.\n"
        "2. **Preparación:** a sesiones y minutos se les aplica un logaritmo (unos pocos alumnos con muchísimas "
        "sesiones dominarían las distancias) y todas se **estandarizan dentro de cada materia**.\n"
        "3. **Un solo modelo para las tres materias**, así los grupos se llaman igual en todo el tablero.\n"
        "4. **Cantidad de grupos:** la de mayor **silhouette** entre 3 y 6. El silhouette mide qué tan cerca está "
        "cada alumno de su grupo comparado con el grupo más cercano (de −1 a 1). k = 2 se muestra como "
        "referencia, pero no se elige: solo separa \"entran / no entran\", que ya lo dice el estado de actividad.\n"
        "5. **Nombres:** salen del centro de cada grupo (cuánta actividad y qué nota tiene respecto de su materia).")
    ev = evaluacion.assign(tipo=evaluacion["candidato"].map({True: "Candidato", False: "Referencia"}))
    c1, c2 = st.columns(2)
    fig = px.line(ev, x="k", y="silhouette", markers=True, title="Silhouette (más alto = grupos más separados)")
    fig.add_scatter(x=[k_usado], y=ev.loc[ev["k"].eq(k_usado), "silhouette"], mode="markers",
                    marker=dict(size=14, color=comp.CATEGORICA[1]), name="Usado")
    fig.update_layout(height=300, showlegend=False, xaxis_dtick=1)
    c1.plotly_chart(fig, width="stretch")
    fig = px.line(ev, x="k", y="inercia", markers=True, title="Inercia (dónde deja de bajar mucho = codo)")
    fig.update_layout(height=300, xaxis_dtick=1)
    c2.plotly_chart(fig, width="stretch")
    sil = ev.loc[ev["k"].eq(k_usado), "silhouette"].item()
    st.markdown(
        f"Con k = {k_usado} el silhouette es **{comp.num(sil, 2)}**: una estructura moderada. Los alumnos no "
        "forman tipos bien separados sino un continuo de \"más o menos enganchados\", y los grupos son una forma "
        "útil de resumirlo. **Limitaciones:** una sola cursada y unos 210 alumnos por materia; el avance es una "
        "foto al 24/10; y como la nota entra en el modelo, los grupos se parecen a la condición. Un grupo "
        "describe, no predice: para anticipar el abandono está el predictor.")
