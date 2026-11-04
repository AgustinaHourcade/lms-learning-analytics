"""Dashboard 3 (del plan): Matrícula y alertas.

Responde, a la fecha de corte: ¿cuántos de los inscriptos están cursando de
verdad?, ¿quién cursa sin estar inscripto?, ¿quién se inscribió y no aparece? y
¿a quién conviene contactar primero?

  Tarjetas        inscriptos, activos, no inscriptos cursando, inscriptos sin
                  notas y alumnos con prioridad alta.
  Matrícula       inscriptos vs. con actividad vs. activos vs. con nota, evolución
                  de inscripciones contra el primer ingreso al aula y condición
                  de inscriptos vs. no inscriptos.
  Alertas         cuántas hay de cada tipo por materia y la lista priorizada por
                  alumno (D37, D52), filtrable y en CSV.
  No inscriptos   quiénes cursan sin estar en Matriculados (para la secretaría).
  Sin notas       inscriptos que no rindieron nada: nunca entraron o entran y no rinden.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

import componentes as comp
from src.metricas import TIPOS_ALERTA

f = comp.encabezado(
    "Matrícula y alertas",
    "Cruce entre la inscripción formal y lo que pasa en el aula virtual, y la lista de alumnos "
    "que necesitan un seguimiento, ordenada por prioridad.",
)

ORDEN = {"asignatura": list(comp.COLORES_MATERIA)}
SUFIJO = f"{f.fecha_corte:%Y%m%d}"

resumen = comp.metrica("resumen_matricula")
tabla = comp.metrica("tabla_alumnos")
por_alumno = comp.metrica("alertas_por_alumno")
alertas = comp.metrica("alertas")


def total(col: str) -> int:
    return int(resumen[col].sum())


# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------
inscriptos = total("inscriptos")
altas = int((por_alumno["prioridad"] == "Alta").sum())
comp.tarjetas([
    dict(label="Inscriptos", value=comp.num(inscriptos),
         help=f"Último estado Aceptada en Matriculados (D11). Hay además {comp.num(total('bajas'))} bajas. "
              "Un alumno que cursa dos materias cuenta dos veces."),
    dict(label="🟢 Activos", value=comp.num(total("activos")),
         delta=f"{comp.pct(total('activos') / total('base') * 100, 0)} de la base", delta_color="off",
         delta_arrow="off",
         help=f"Alumnos de la base (inscriptos + con nota) que entraron en los últimos {f.umbral} días (D35)."),
    dict(label="Sin inscripción", value=comp.num(total("no_inscriptos_cursando")),
         help="Tienen notas o actividad, pero no figuran como Aceptada en Matriculados."),
    dict(label="Inscriptos sin notas", value=comp.num(total("inscriptos_sin_notas")),
         delta=f"{comp.num(total('inscriptos_sin_actividad'))} nunca entraron", delta_color="off",
         delta_arrow="off",
         help="Inscriptos que no rindieron ningún instrumento a la fecha de corte. Abajo, los que además "
              "nunca entraron al aula."),
    dict(label="🔴 Prioridad alta", value=comp.num(altas),
         help="Alumnos con alerta de prioridad alta (D52): inscriptos sin actividad o con dos o más alertas "
              "académicas a la vez (inactivo, Libre, entra pero no rinde)."),
])

tab_mat, tab_alertas, tab_no_insc, tab_sin_notas = st.tabs(
    ["Matrícula", "Alertas", "Cursan sin inscripción", "Inscriptos sin notas"])

# ---------------------------------------------------------------------------
# Matrícula: embudo, evolución y condición por grupo
# ---------------------------------------------------------------------------
with tab_mat:
    st.subheader("Inscriptos vs. activos vs. con nota")
    etapas = {"inscriptos": "Inscriptos", "base": "Base<br>(inscriptos + con nota)",
              "con_actividad": "Entraron<br>alguna vez", "activos": f"Activos<br>(últimos {f.umbral} días)",
              "con_nota": "Con al menos<br>una nota"}
    largo = resumen.melt(id_vars="asignatura", value_vars=list(etapas), var_name="etapa", value_name="alumnos")
    largo["etapa"] = largo["etapa"].map(etapas)
    fig = px.bar(largo, x="etapa", y="alumnos", color="asignatura", barmode="group",
                 text="alumnos", category_orders={**ORDEN, "etapa": list(etapas.values())},
                 color_discrete_map=comp.COLORES_MATERIA, labels={"alumnos": "Alumnos", "etapa": "",
                                                                   "asignatura": ""})
    fig.update_traces(textposition="outside", cliponaxis=False,
                      hovertemplate="%{x}<br>%{fullData.name}: %{y} alumnos<extra></extra>")
    fig.update_xaxes(tickangle=0)
    fig.update_layout(height=380, bargap=0.25, bargroupgap=0.05)
    st.plotly_chart(fig, width="stretch")
    st.caption("La **base** de cada materia son los inscriptos más los que tienen alguna nota sin estar "
               "inscriptos (D11): por eso supera a los inscriptos. Que casi todos hayan entrado alguna vez pero "
               "bastantes menos estén activos indica abandono a lo largo de la cursada.")

    st.subheader("Inscripciones vs. primer ingreso al aula")
    evo = comp.metrica("evolucion_matricula")
    if evo.empty:
        st.info("A esta fecha de corte todavía no hay inscripciones ni ingresos.", icon=":material/event_busy:")
    else:
        fig = px.line(evo, x="fecha", y="alumnos", color="serie", facet_col="asignatura",
                      category_orders=ORDEN, line_shape="hv",
                      color_discrete_map={"Inscriptos": comp.CATEGORICA[6], "Ya entraron al aula": comp.CATEGORICA[3]},
                      labels={"fecha": "", "alumnos": "Alumnos (acumulado)", "serie": "", "asignatura": ""})
        fig.update_traces(hovertemplate="%{x|%d/%m}: %{y} alumnos<extra>%{fullData.name}</extra>", line_width=2)
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        fig.update_xaxes(tickformat="%d/%m")
        fig.update_layout(height=360, legend=dict(y=1.16), margin=dict(t=80))
        st.plotly_chart(fig, width="stretch")
        st.caption("Inscriptos: acumulado según la fecha de inscripción del último estado Aceptada. "
                   "Ya entraron: alumnos de la base según su primera interacción en la trazabilidad. Cuando la "
                   "línea de ingresos va por encima, hay alumnos cursando antes (o sin) haberse inscripto.")

    st.subheader("Condición de inscriptos y no inscriptos")
    sit = comp.metrica("situacion_academica")
    if sit.empty or sit["condicion"].isin(list(comp.COLORES_CONDICION)[:3]).sum() == 0:
        st.info("A esta fecha de corte todavía no se tomó ninguna evaluación.", icon=":material/event_busy:")
    else:
        sit["pct"] = sit["alumnos"] / sit.groupby(["asignatura", "grupo"])["alumnos"].transform("sum") * 100
        sit["etiqueta"] = comp.con_icono(sit["condicion"], comp.ICONOS_CONDICION)
        conds = [c for c in comp.COLORES_CONDICION if c in set(sit["condicion"])]
        fig = px.bar(sit, x="pct", y="grupo", color="condicion", facet_col="asignatura", orientation="h",
                     facet_col_spacing=0.04,
                     category_orders={**ORDEN, "condicion": conds, "grupo": ["Inscriptos", "No inscriptos"]},
                     color_discrete_map=comp.COLORES_CONDICION, custom_data=["etiqueta", "alumnos"],
                     text=sit["pct"].map(lambda v: comp.pct(v, 0) if v >= 6 else ""),
                     labels={"pct": "% de alumnos", "grupo": "", "condicion": "", "asignatura": ""})
        fig.update_traces(hovertemplate="%{y}<br>%{customdata[0]}: %{customdata[1]} alumnos (%{x:.1f} %)"
                                        "<extra></extra>",
                          textposition="inside", insidetextanchor="middle", marker_line_width=2,
                          marker_line_color="white")
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        fig.update_xaxes(range=[0, 100], dtick=50)
        fig.update_layout(barmode="stack", height=280, bargap=0.3, legend=dict(y=1.22), margin=dict(t=90))
        st.plotly_chart(fig, width="stretch")
        st.caption("Muchos no inscriptos rinden y les va bien: no son alumnos perdidos sino un problema "
                   "administrativo a regularizar antes del cierre de actas.")

    st.dataframe(resumen, hide_index=True, width="stretch", column_config={
        "asignatura": "Materia", "base": "Base", "inscriptos": "Inscriptos", "bajas": "Bajas",
        "con_actividad": "Entraron alguna vez", "activos": "Activos", "con_nota": "Con nota",
        "no_inscriptos_cursando": "Cursan sin inscripción", "inscriptos_sin_actividad": "Inscriptos sin actividad",
        "inscriptos_sin_notas": "Inscriptos sin notas"})
    comp.boton_csv(resumen, f"resumen_matricula_{SUFIJO}", "Descargar resumen por materia")

# ---------------------------------------------------------------------------
# Alertas: conteo por tipo y lista priorizada
# ---------------------------------------------------------------------------
with tab_alertas:
    if por_alumno.empty:
        st.success("No hay alumnos con alertas a esta fecha de corte.", icon=":material/check_circle:")
    else:
        # Mensajes estilo clase 10 (st.error / st.warning / st.info), uno por prioridad.
        conteo = por_alumno["prioridad"].value_counts()
        mensajes = {
            "Alta": (st.error, "contactar esta semana: no aparecen o acumulan varias señales de abandono."),
            "Media": (st.warning, "seguir de cerca: una sola señal (inactivo, Libre o no rinde)."),
            "Administrativa": (st.info, "cursan bien pero sin inscripción: derivar a la secretaría."),
        }
        for prioridad, (caja, texto) in mensajes.items():
            n = int(conteo.get(prioridad, 0))
            if n:
                caja(f"**{comp.ICONOS_PRIORIDAD[prioridad]} {n} alumnos con prioridad {prioridad.lower()}**: {texto}")

        st.subheader("Alertas por tipo y materia")
        cuenta = alertas.groupby(["asignatura", "alerta"]).size().rename("alumnos").reset_index()
        cuenta["pct"] = cuenta["alumnos"] / cuenta["asignatura"].map(resumen.set_index("asignatura")["base"]) * 100
        fig = px.bar(cuenta, x="alumnos", y="alerta", color="asignatura", barmode="group", orientation="h",
                     text="alumnos", custom_data=["pct"],
                     category_orders={**ORDEN, "alerta": list(TIPOS_ALERTA.values())},
                     color_discrete_map=comp.COLORES_MATERIA,
                     labels={"alumnos": "Alumnos", "alerta": "", "asignatura": ""})
        fig.update_traces(textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}<br>%{fullData.name}: %{x} alumnos (%{customdata[0]:.1f} % de la "
                                        "base)<extra></extra>")
        fig.update_layout(height=140 + 22 * len(TIPOS_ALERTA) * len(f.materias) + 20 * len(TIPOS_ALERTA),
                          bargap=0.2, bargroupgap=0.05)
        st.plotly_chart(fig, width="stretch")
        st.caption("Un alumno puede tener varias alertas (D37). \"Condición Libre\" no se repite para quien no "
                   "tiene ni actividad ni notas: ese ya figura como inscripto sin actividad. Inactivo depende del "
                   "umbral de la barra lateral.")

        st.subheader("A quién contactar primero")
        c1, c2, c3 = st.columns([1, 2, 1.4])
        prioridades = c1.multiselect("Prioridad", list(comp.ICONOS_PRIORIDAD), default=["Alta", "Media"],
                                     key="alertas_prioridad")
        tipos = c2.multiselect("Tipo de alerta", list(TIPOS_ALERTA), format_func=TIPOS_ALERTA.get,
                               key="alertas_tipo", placeholder="Todas")
        texto = c3.text_input("Buscar alumno", key="alertas_buscar", placeholder="Apellido, nombre o ID")

        vista = por_alumno[por_alumno["prioridad"].isin(prioridades or list(comp.ICONOS_PRIORIDAD))]
        if tipos:
            vista = vista[vista["tipos"].map(lambda ts: bool(set(tipos) & set(ts)))]
        if texto.strip():
            buscado = vista["nombre_completo"].fillna("") + " " + vista["id_alumno"]
            vista = vista[buscado.str.contains(texto.strip(), case=False, regex=False)]
        vista = vista.assign(
            prioridad=comp.con_icono(vista["prioridad"].astype(str), comp.ICONOS_PRIORIDAD),
            condicion=comp.con_icono(vista["condicion"], comp.ICONOS_CONDICION),
            estado_actividad=comp.con_icono(vista["estado_actividad"], comp.ICONOS_ACTIVIDAD),
            nota=vista["nota_final"].map(lambda v: comp.num(v, 1)) + " / "
                 + vista["escala"].astype("Int64").astype(str),
        )
        columnas = {"prioridad": "Prioridad", "asignatura": "Materia", "id_alumno": "ID",
                    "nombre_completo": "Alumno", "alertas": "Alertas", "condicion": "Condición", "nota": "Nota",
                    "estado_actividad": "Actividad", "dias_sin_actividad": "Días sin entrar",
                    "ultima_interaccion": "Último ingreso", "avance": "Avance (al 24/10)"}
        if f.asignatura:
            columnas.pop("asignatura")
        st.dataframe(vista[list(columnas)].rename(columns=columnas), hide_index=True, width="stretch",
                     height=420, column_config={
                         "Último ingreso": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                         "Avance (al 24/10)": st.column_config.ProgressColumn(format="%d %%", min_value=0,
                                                                              max_value=100),
                         "Alertas": st.column_config.TextColumn(width="large")})
        st.caption(f"{comp.num(len(vista))} de {comp.num(len(por_alumno))} alumnos con alguna alerta. "
                   "Prioridad (D52): **alta** = inscripto sin actividad o dos o más alertas académicas a la vez; "
                   "**media** = una sola; **administrativa** = solo cursa sin inscripción. El avance es una foto "
                   "del reporte de participación (D36).")
        c1, c2 = st.columns(2)
        with c1:
            comp.boton_csv(vista.drop(columns=["tipos", "nota"]), f"alertas_por_alumno_{SUFIJO}",
                           "Descargar esta lista")
        with c2:
            comp.boton_csv(alertas.drop(columns="tipo"), f"alertas_detalle_{SUFIJO}",
                           "Descargar todas las alertas (una fila por alerta)")

# ---------------------------------------------------------------------------
# No inscriptos cursando
# ---------------------------------------------------------------------------
COLUMNAS_ALUMNO = {"asignatura": "Materia", "id_alumno": "ID", "nombre_completo": "Alumno",
                   "condicion": "Condición", "nota": "Nota", "rendidos_txt": "Rindió",
                   "estado_actividad": "Actividad", "eventos": "Interacciones",
                   "ultima_interaccion": "Último ingreso", "en_matriculados": "En Matriculados", "estado": "Estado"}
CONFIG_ALUMNO = {"Último ingreso": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                 "En Matriculados": st.column_config.CheckboxColumn()}


def lista_alumnos(df: pd.DataFrame, columnas: list[str], nombre_csv: str, vacio: str) -> None:
    if df.empty:
        st.success(vacio, icon=":material/check_circle:")
        return
    df = df.assign(
        condicion=comp.con_icono(df["condicion"], comp.ICONOS_CONDICION),
        estado_actividad=comp.con_icono(df["estado_actividad"], comp.ICONOS_ACTIVIDAD),
        nota=df["nota_final"].map(lambda v: comp.num(v, 1)) + " / "
             + df["escala"].astype("Int64").astype(str),
        rendidos_txt=df["rendidos"].astype(str) + " de " + df["instrumentos"].astype(str),
    )
    if f.asignatura:
        columnas = [c for c in columnas if c != "asignatura"]
    nombres = {c: COLUMNAS_ALUMNO[c] for c in columnas}
    st.dataframe(df[columnas].rename(columns=nombres), hide_index=True, width="stretch", height=400,
                 column_config={k: v for k, v in CONFIG_ALUMNO.items() if k in nombres.values()})
    comp.boton_csv(df[columnas].rename(columns=nombres), f"{nombre_csv}_{SUFIJO}", "Descargar lista")


with tab_no_insc:
    no_insc = tabla[~tabla["inscripto"]].sort_values(["asignatura", "apellido", "nombre"])
    st.markdown("Alumnos que **tienen notas o actividad** en la materia pero **no figuran como Aceptada** en "
                "Matriculados (nunca se inscribieron o su último movimiento es una baja). Si aprueban, no van a "
                "poder figurar en el acta: conviene derivarlos a la secretaría.")
    if not no_insc.empty:
        sin_registro = int((~no_insc["en_matriculados"]).sum())
        con_baja = int(no_insc["estado"].eq("Baja").sum())
        aprobando = int(no_insc["condicion"].isin(["Regular", "Promociona"]).sum())
        comp.tarjetas([
            ("Cursan sin inscripción", comp.num(len(no_insc))),
            ("No están en Matriculados", comp.num(sin_registro), "Nunca aparecieron en el archivo de inscripciones."),
            ("Con baja", comp.num(con_baja), "Se inscribieron y después se dieron de baja, pero siguen rindiendo."),
            ("🟢🟡 Regulares o promocionan", comp.num(aprobando),
             "Los más urgentes de regularizar: van camino a aprobar."),
        ])
    lista_alumnos(no_insc, ["asignatura", "id_alumno", "nombre_completo", "condicion", "nota", "rendidos_txt",
                            "estado_actividad", "ultima_interaccion", "en_matriculados", "estado"],
                  "no_inscriptos_cursando", "Todos los alumnos que cursan están inscriptos.")

# ---------------------------------------------------------------------------
# Inscriptos sin notas
# ---------------------------------------------------------------------------
with tab_sin_notas:
    sin_notas = tabla[tabla["inscripto"] & (tabla["rendidos"] == 0)]
    sin_notas = sin_notas.assign(nunca=sin_notas["eventos"].eq(0)) \
                         .sort_values(["nunca", "asignatura", "apellido"], ascending=[False, True, True])
    st.markdown("Inscriptos que **no rindieron ningún instrumento** a la fecha de corte (todo cuenta 0, así que "
                "están Libres). Se separan en dos grupos porque piden acciones distintas:")
    nunca, entra = int(sin_notas["nunca"].sum()), int((~sin_notas["nunca"]).sum())
    comp.tarjetas([
        ("⚪ Nunca entraron", comp.num(nunca),
         "Sin interacciones ni notas: posiblemente nunca empezaron. Confirmar si siguen cursando o darlos de baja."),
        ("🟠 Entran pero no rinden", comp.num(entra),
         "Miran el aula pero no se presentan a las evaluaciones: el grupo donde una intervención del tutor "
         "puede cambiar el resultado."),
    ])
    grupo = st.segmented_control("Mostrar", ["Todos", "Nunca entraron", "Entran pero no rinden"],
                                 default="Todos", key="sin_notas_grupo")
    if grupo == "Nunca entraron":
        sin_notas = sin_notas[sin_notas["nunca"]]
    elif grupo == "Entran pero no rinden":
        sin_notas = sin_notas[~sin_notas["nunca"]]
    lista_alumnos(sin_notas, ["asignatura", "id_alumno", "nombre_completo", "rendidos_txt", "estado_actividad",
                              "eventos", "ultima_interaccion"],
                  "inscriptos_sin_notas", "Todos los inscriptos rindieron al menos un instrumento.")
