"""Dashboard 6 (del plan): Ficha individual.

Responde, para UN alumno y a la fecha de corte: ¿cómo le va en cada materia?,
¿cuánto entra al aula comparado con su curso?, ¿qué hace cuando entra? y
¿tiene alguna alerta que pida contactarlo?

  Selector        un solo desplegable con búsqueda: se escribe parte del apellido,
                  nombre o ID y filtra la lista; muestra al primero por defecto.
                  Lista solo a los alumnos de la base (D11) de la materia elegida
                  en la barra lateral (D56).
  Resumen         una tarjeta por materia con el semáforo (🟢 Promociona,
                  🟡 Regular, 🔴 Libre), la nota contra el promedio del curso,
                  el riesgo de abandono (nivel y probabilidad, D58), los
                  instrumentos rendidos y el estado de actividad (D35).
  Alertas         las de D37 para este alumno.
  Notas           cada instrumento contra el promedio de quienes lo rindieron
                  (D22), en dos vistas a elección: Libreta (una tarjeta por
                  instrumento con su nota, si aprobó y el promedio del
                  curso) o Barras; y la tabla
                  con el recuperatorio (D34).
  Actividad       su evolución semanal contra el promedio por alumno del curso,
                  su posición (percentil) y el reporte de participación (D36).
  Trazabilidad    qué tipo de interacciones hace (contra el curso) y todos sus
                  eventos hasta la fecha de corte, con CSV.

La ficha muestra todas las materias del alumno aunque la barra lateral tenga
una elegida: el filtro de materia solo acota el buscador.
Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
import html
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import componentes as comp
from src.config import ESQUEMA

f = comp.encabezado(
    "Ficha individual",
    "Todo sobre un alumno: notas, actividad y alertas en sus materias, comparado con su curso.",
)

GRIS = "#c3c2b7"
GRIS_TEXTO = "#52514e"

# Estilos de la libreta de notas: van en la página (no en componentes.CSS) para que se vean
# apenas se guarda el archivo, sin reiniciar Streamlit.
CSS_LIBRETA = """
<style>
  /* Ficha individual: libreta de notas (una tarjeta por instrumento) */
  .libreta {display:grid; grid-template-columns:repeat(auto-fill, minmax(165px, 1fr)); gap:.6rem; margin:.3rem 0 1.2rem;}
  .nota {border:1px solid rgba(11,11,11,.10); border-left-width:5px; border-radius:.5rem; padding:.55rem .7rem;
         background:#fff; line-height:1.25;}
  .nota-nombre {font-size:.8rem; color:#52514e; min-height:2.1em;}
  .nota-valor  {font-size:1.7rem; font-weight:700; color:#0b0b0b;}
  .nota-puntos {font-size:.8rem; color:#52514e; font-weight:400; margin-left:.25rem;}
  .nota-estado {font-size:.82rem; font-weight:600; margin-top:.1rem;}
  .nota-curso  {font-size:.78rem; color:#52514e; margin-top:.35rem; border-top:1px dashed #e1e0d9; padding-top:.3rem;}
  .nota-aprobada    {border-left-color:#0ca30c;} .nota-aprobada .nota-estado    {color:#006300;}
  .nota-no-aprobada {border-left-color:#d03b3b; background:#fff7f7;} .nota-no-aprobada .nota-estado {color:#8a1f1f;}
  .nota-no-rindio   {border-left-color:#c3c2b7; background:#f6f5f2;} .nota-no-rindio .nota-valor {color:#898781;}
  .nota-no-rindio .nota-estado {color:#52514e;}
</style>
"""


def nombre_corto(instrumento: str) -> str:
    """'👉  Actividad Rápida 1' -> 'Actividad Rápida 1' (saca los emojis del LMS)."""
    return re.sub(r"^[^\wÁÉÍÓÚáéíóúÑñ°]+", "", str(instrumento)).strip()


def en_dos_lineas(texto: str, largo: int = 14) -> str:
    """Parte los nombres largos en dos renglones para el eje x (sin rotar las etiquetas)."""
    if len(texto) <= largo or " " not in texto:
        return texto
    palabras = texto.split(" ")
    corte = min(range(1, len(palabras)), key=lambda i: abs(len(" ".join(palabras[:i])) - len(texto) / 2))
    return " ".join(palabras[:corte]) + "<br>" + " ".join(palabras[corte:])


def signo(x, decimales: int = 1) -> str:
    return ("+" if x > 0 else "") + comp.num(x, decimales)


def tarjeta_nota(t) -> str:
    """HTML de una tarjeta de la libreta: nota, si aprobó y el promedio del curso (fila de ficha['instrumentos'])."""
    nombre = html.escape(nombre_corto(t.instrumento))
    curso = (f"Curso: {comp.pct(t.promedio_curso_pct, 0)}" if pd.notna(t.promedio_curso_pct) else "Curso: –")
    if not t.rindio:
        estado = "No lo rindió" if t.es_recuperatorio else "No rindió · cuenta 0"
        return (f'<div class="nota nota-no-rindio"><div class="nota-nombre">{nombre}</div>'
                f'<div class="nota-valor">–</div><div class="nota-estado">{estado}</div>'
                f'<div class="nota-curso">{curso}</div></div>')
    aprobada = str(t.observaciones).strip().lower() == "aprobada"
    clase, estado = ("nota-aprobada", "✓ Aprobada") if aprobada else ("nota-no-aprobada", "✗ No aprobada")
    if t.recuperatorio_aplicado:
        estado += " · la reemplaza el recuperatorio"
    if pd.notna(t.promedio_curso_pct):
        dif = t.nota_pct - t.promedio_curso_pct
        curso += f" · {'▲' if dif >= 0 else '▼'} {comp.num(abs(dif), 0)} pts"
    return (f'<div class="nota {clase}"><div class="nota-nombre">{nombre}</div>'
            f'<div class="nota-valor">{comp.pct(t.nota_pct, 0)}'
            f'<span class="nota-puntos">{comp.num(t.nota_obtenida, 2)} / {comp.num(t.puntaje_maximo, 0)}</span></div>'
            f'<div class="nota-estado">{estado}</div><div class="nota-curso">{curso}</div></div>')


# ---------------------------------------------------------------------------
# Selector de alumno (el desplegable ya trae búsqueda: se escribe y filtra)
# ---------------------------------------------------------------------------
alumnos = comp.metrica("buscar_alumnos", texto="", solo_base=True)
if alumnos.empty:
    st.warning(f"No hay alumnos en la base de {f.materia.lower()}.", icon=":material/person_off:")
    st.stop()

nombres = dict(zip(alumnos["id_alumno"], alumnos["nombre_completo"]))
id_alumno = st.selectbox(
    f"Alumno ({comp.num(len(alumnos))} en la base)", list(nombres),
    format_func=lambda i: f"{nombres[i]} · {i}", key="fi_alumno",
    help="Escribí parte del apellido, nombre o ID (ej.: ALU_1263) para filtrar. Ordenados por apellido; "
         "por defecto se muestra el primero.")

ficha = comp.metrica("ficha_alumno", id_alumno=id_alumno)
materias = ficha["materias"]
st.subheader(f"{ficha['datos']['nombre_completo']} · {id_alumno}")
if f.asignatura:
    st.caption(f"El buscador lista solo alumnos de {f.asignatura}, pero la ficha muestra todas sus materias.")

if materias.empty:  # no pasa con solo_base=True, pero por las dudas
    st.info("Este alumno no está en la base de ninguna materia (D11).", icon=":material/person_off:")
    st.stop()
orden = {m: i for i, m in enumerate(ESQUEMA)}
materias = materias.sort_values("asignatura", key=lambda s: s.map(orden)).reset_index(drop=True)
riesgo = comp.metrica("riesgo_alumno", id_alumno=id_alumno).set_index("asignatura")   # D58
umbral_riesgo = 100 * comp.metrica("info_modelo")["umbral"]
ab = comp.ml_abandono   # constantes del predictor (estados y horizonte)

# ---------------------------------------------------------------------------
# Resumen por materia
# ---------------------------------------------------------------------------
cols = st.columns(len(materias))
for col, fila in zip(cols, materias.itertuples()):
    with col.container(border=True):
        st.markdown(f"**{fila.asignatura}**")
        sin_notas = fila.instrumentos == 0
        comp.mostrar_semaforo(fila.condicion)
        st.metric("Nota a la fecha de corte",
                  "–" if sin_notas else f"{comp.num(fila.nota_final, 1)} / {fila.escala}",
                  delta=None if sin_notas else f"{signo(fila.nota_final - fila.promedio_nota_final)} vs. "
                                               f"promedio ({comp.num(fila.promedio_nota_final, 1)})",
                  help=f"Σ puntos / Σ máximos de los instrumentos ya tomados × {fila.escala} (D17). "
                       "Lo no rendido cuenta 0 (D15). El promedio es el de toda la base de la materia.")
        if fila.asignatura in riesgo.index:
            r = riesgo.loc[fila.asignatura]
            if r["estado_abandono"] == ab.CURSANDO:
                ayuda = (f"Probabilidad de que no entre al aula en los próximos "
                         f"{ab.ABANDONO_HORIZONTE_DIAS} días, según el predictor "
                         f"(D58). Alto desde {comp.pct(umbral_riesgo, 0)}, Medio desde la mitad."
                         + (f" Señales: {r['motivos']}." if r["motivos"] else ""))
            elif r["estado_abandono"] == ab.YA_ABANDONO:
                ayuda = (f"Hace {comp.num(r['dias_sin_actividad'])} días que no entra: ya cumple la definición "
                         f"de abandono ({ab.ABANDONO_HORIZONTE_DIAS} días sin entrar). Conviene contactarlo.")
            else:
                ayuda = "Nunca entró al aula hasta la fecha de corte."
            st.metric("Riesgo de abandono", comp.texto_riesgo(r), help=ayuda)
        estado = f"{comp.ICONOS_ACTIVIDAD[fila.estado_actividad]} {fila.estado_actividad}"
        if fila.eventos:
            estado += f" · última vez hace {fila.dias_sin_actividad} días ({comp.fmt_fecha(fila.ultima_interaccion)})"
        st.markdown(
            f"- Rindió **{fila.rendidos} de {fila.instrumentos}** instrumentos\n"
            f"- {estado}\n"
            f"- {'Inscripto' if fila.inscripto else '⚠️ **No inscripto** (cursa sin estar en Matriculados)'}")

# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------
alertas = ficha["alertas"].sort_values("asignatura", key=lambda s: s.map(orden), kind="stable")
if alertas.empty:
    st.success("Sin alertas a la fecha de corte.", icon=":material/check_circle:")
else:
    lineas = [f"- **{comp.SIGLAS[a.asignatura]}** · {a.alerta}: {a.detalle}" for a in alertas.itertuples()]
    st.warning(f"**{len(alertas)} {'alerta' if len(alertas) == 1 else 'alertas'}** a la fecha de corte (D37):\n"
               + "\n".join(lineas), icon=":material/warning:")

tab_notas, tab_act, tab_traz = st.tabs(["Notas", "Actividad", "Trazabilidad"])

# ---------------------------------------------------------------------------
# Notas
# ---------------------------------------------------------------------------
with tab_notas:
    inst = ficha["instrumentos"]
    if inst.empty:
        st.info(f"Al {comp.fmt_fecha(f.fecha_corte)} todavía no se tomó ninguna evaluación en sus materias.",
                icon=":material/event_busy:")
    else:
        inst = inst.assign(nombre=inst["instrumento"].map(nombre_corto),
                           nota_pct=(inst["nota_obtenida"] / inst["puntaje_maximo"] * 100).round(1))  # la original
        inst["eje"] = inst["nombre"].map(en_dos_lineas)
        presentes_notas = [m for m in materias["asignatura"] if m in set(inst["asignatura"])]
        vista = st.segmented_control("Vista", ["Libreta", "Barras"], default="Libreta",
                                     key="fi_vista_notas") or "Libreta"

        if vista == "Libreta":
            st.caption("Una tarjeta por instrumento, en el orden en que se tomaron: su nota (en % del máximo y en "
                       "puntos), si la aprobó y el promedio de **quienes lo rindieron** (D22). Lo que no rindió "
                       "cuenta 0 para la nota final (D15). Si rindió el recuperatorio, su nota reemplaza a la "
                       "original (D34).")
            st.markdown(CSS_LIBRETA, unsafe_allow_html=True)
            for materia in presentes_notas:
                fila = materias[materias["asignatura"] == materia].iloc[0]
                q = inst[inst["asignatura"] == materia]
                nota_materia = ("–" if fila.instrumentos == 0
                                else f"{comp.num(fila.nota_final, 1)} / {fila.escala}")
                st.markdown(f"**{materia}** &nbsp; {comp.semaforo(fila.condicion)} &nbsp; "
                            f"Nota a la fecha de corte: **{nota_materia}** · rindió {fila.rendidos} de "
                            f"{fila.instrumentos}", unsafe_allow_html=True)
                st.markdown(f'<div class="libreta">{"".join(tarjeta_nota(t) for t in q.itertuples())}</div>',
                            unsafe_allow_html=True)
        else:
            st.caption("Cada barra es su nota en el instrumento (en % del máximo). En gris, lo que no rindió: "
                       "cuenta 0 para la nota final (D15). El rombo ◆ es el promedio de **quienes lo rindieron** "
                       "(D22). Los recuperatorios van aparte: si lo rindió, su nota reemplaza a la original (D34).")
            for materia in presentes_notas:
                q = inst[inst["asignatura"] == materia]
                rindio = q["rindio"]
                fig = go.Figure()
                fig.add_bar(x=q["eje"], y=q["nota_pct"].where(rindio, 0), showlegend=False,
                            marker_color=[comp.COLORES_MATERIA[materia] if r else GRIS for r in rindio],
                            text=[comp.pct(v, 0) if r else "No rindió" for v, r in zip(q["nota_pct"], rindio)],
                            textposition="outside", cliponaxis=False,
                            customdata=q[["nombre", "nota_obtenida", "puntaje_maximo"]].fillna(0),
                            hovertemplate="%{customdata[0]}<br>Nota: %{customdata[1]:g} / %{customdata[2]:g}"
                                          "<extra></extra>")
                fig.add_scatter(x=q["eje"], y=q["promedio_curso_pct"], mode="markers", showlegend=False,
                                marker=dict(symbol="diamond", size=11, color="#0b0b0b"),
                                customdata=q[["nombre", "rindieron"]],
                                hovertemplate="%{customdata[0]}<br>Promedio de quienes lo rindieron: %{y:.1f} %"
                                              "<br>(%{customdata[1]} alumnos)<extra></extra>")
                fig.update_yaxes(range=[0, 115], ticksuffix=" %")
                fig.update_xaxes(tickangle=0)
                fig.update_layout(title=materia, height=300, bargap=0.35)
                st.plotly_chart(fig, width="stretch")

        tabla = inst.assign(
            Materia=inst["asignatura"], Instrumento=inst["nombre"], Fecha=inst["fecha_instrumento"].dt.date,
            Rindió=inst["rindio"].map({True: "Sí", False: "No"}),
            Nota=[f"{comp.num(n, 2)} / {comp.num(m_, 0)}" if r else "–"
                  for n, m_, r in zip(inst["nota_obtenida"], inst["puntaje_maximo"], inst["rindio"])],
            **{"Nota (%)": inst["nota_pct"].where(inst["rindio"]),
               "Cuenta para la final (%)": inst["nota_pct_corte"].where(inst["cuenta_en_final"]),
               "Promedio del curso (%)": inst["promedio_curso_pct"],
               "Observaciones": inst["observaciones"].fillna(""),
               "Recuperatorio aplicado": inst["recuperatorio_aplicado"].map({True: "Sí", False: ""})},
        )[["Materia", "Instrumento", "Fecha", "Rindió", "Nota", "Nota (%)", "Cuenta para la final (%)",
           "Promedio del curso (%)", "Observaciones", "Recuperatorio aplicado"]]
        st.dataframe(tabla, hide_index=True, width="stretch",
                     column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                    **{c: st.column_config.NumberColumn(format="%.1f")
                                       for c in ["Nota (%)", "Cuenta para la final (%)", "Promedio del curso (%)"]}})
        st.caption("*Cuenta para la final* es lo que entra en la nota a la fecha de corte: 0 si no rindió y, si "
                   "rindió el recuperatorio, la nota del recuperatorio. Los recuperatorios no suman un instrumento "
                   "más al promedio, por eso esa columna queda vacía en ellos.")
        comp.boton_csv(tabla, f"notas_{id_alumno}", "Descargar notas (CSV)")

# ---------------------------------------------------------------------------
# Actividad
# ---------------------------------------------------------------------------
with tab_act:
    st.markdown("**Dónde queda dentro de su curso**")
    st.caption("El percentil dice qué parte de la base de la materia tiene un valor igual o menor: 80 = está por "
               "encima del 80 % de sus compañeros. *Avance* sale del reporte de participación: es una foto a la "
               "fecha de exportación y no se recorta con la fecha de corte (D36).")
    VARIABLES = {"nota_final": "Nota", "minutos": "Minutos en la plataforma", "eventos": "Interacciones",
                 "avance": "Avance (%)"}
    comparacion = pd.DataFrame([
        {"Materia": fila.asignatura, "Variable": etiqueta, "Alumno": getattr(fila, col),
         "Promedio del curso": getattr(fila, f"promedio_{col}"), "Percentil": getattr(fila, f"percentil_{col}")}
        for fila in materias.itertuples() for col, etiqueta in VARIABLES.items()])
    st.dataframe(comparacion, hide_index=True, width="stretch", column_config={
        "Alumno": st.column_config.NumberColumn(format="%.1f"),
        "Promedio del curso": st.column_config.NumberColumn(format="%.1f"),
        "Percentil": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d",
                                                     help="0 = el que menos de su materia, 100 = el que más.")})

    st.markdown("**Evolución semanal**")
    semanal = ficha["semanal"]
    if semanal.empty or semanal["eventos"].sum() == 0:
        st.info("No tiene interacciones registradas hasta la fecha de corte.", icon=":material/visibility_off:")
    else:
        ver = st.segmented_control("Ver", ["Interacciones", "Minutos", "Sesiones"], default="Interacciones",
                                   key="fi_ver_semanal") or "Interacciones"
        columna = {"Interacciones": "eventos", "Minutos": "minutos", "Sesiones": "sesiones"}[ver]
        st.caption("Semanas de lunes a domingo. Las líneas verticales son las evaluaciones ya tomadas de cada "
                   "materia." + (" La línea punteada es el promedio de interacciones por alumno de la base "
                                 "en esa semana." if columna == "eventos" else ""))
        evaluaciones = ficha["evaluaciones"]
        presentes = [m for m in materias["asignatura"] if m in set(semanal["asignatura"])]
        fig = make_subplots(rows=len(presentes), cols=1, subplot_titles=presentes, shared_xaxes=True,
                            vertical_spacing=0.1)
        for i, materia in enumerate(presentes, start=1):
            q = semanal[semanal["asignatura"] == materia]
            color = comp.COLORES_MATERIA[materia]
            fig.add_scatter(x=q["periodo"], y=q[columna], mode="lines+markers", line=dict(color=color, width=2.5),
                            name="El alumno", showlegend=i == 1, legendgroup="alumno", row=i, col=1,
                            hovertemplate=f"Semana del %{{x|%d/%m}}: %{{y:,.0f}} {ver.lower()}<extra></extra>")
            if columna == "eventos":
                fig.add_scatter(x=q["periodo"], y=q["curso_eventos"], mode="lines",
                                line=dict(color=color, width=1.5, dash="dot"), name="Promedio del curso",
                                showlegend=i == 1, legendgroup="curso", row=i, col=1,
                                hovertemplate="Semana del %{x|%d/%m}: %{y:.1f} por alumno<extra></extra>")
            for ev in evaluaciones[evaluaciones["asignatura"] == materia].itertuples():
                fig.add_vline(x=ev.fecha_instrumento, line=dict(color=GRIS, width=1, dash="dash"), row=i, col=1)
            fig.update_yaxes(rangemode="tozero", row=i, col=1)
            fig.update_xaxes(tickformat="%d/%m", row=i, col=1)
        fig.update_layout(height=230 * len(presentes) + 60, legend=dict(itemclick=False, itemdoubleclick=False))
        st.plotly_chart(fig, width="stretch")

    st.markdown("**Reporte de participación** (foto a la fecha de exportación, D36)")
    reporte = materias.assign(Materia=materias["asignatura"])[
        ["Materia", "sesiones", "minutos", "dias_activos", "semanas_activas", "avance", "tiempo_uso_min",
         "intervenciones_foros", "encuestas_respondidas", "emails_enviados"]]
    st.dataframe(reporte, hide_index=True, width="stretch", column_config={
        "sesiones": st.column_config.NumberColumn("Sesiones", help="Cortadas a los 30 min sin eventos (D25)."),
        "minutos": st.column_config.NumberColumn("Minutos (sesiones)", format="%.0f"),
        "dias_activos": "Días con actividad", "semanas_activas": "Semanas con actividad",
        "avance": st.column_config.ProgressColumn("Avance", min_value=0, max_value=100, format="%d %%"),
        "tiempo_uso_min": st.column_config.NumberColumn("Tiempo de uso (min)", help="Del reporte del LMS."),
        "intervenciones_foros": "Intervenciones en foros", "encuestas_respondidas": "Encuestas",
        "emails_enviados": "Correos enviados"})

# ---------------------------------------------------------------------------
# Trazabilidad
# ---------------------------------------------------------------------------
with tab_traz:
    eventos = ficha["eventos"]
    if eventos.empty:
        st.info("No tiene interacciones registradas hasta la fecha de corte.", icon=":material/visibility_off:")
    else:
        cat = ficha["categorias"]
        st.markdown("**Qué hace cuando entra**")
        st.caption("Sus interacciones por tipo, en % de su total en cada materia. El rombo ◆ es el % del curso: "
                   "si su barra queda muy por debajo en *Evaluación* o *Contenido*, entra pero no estudia ni rinde.")
        presentes = [m for m in materias["asignatura"] if m in set(cat["asignatura"])]
        tipos = sorted(cat["categoria"].unique())
        fig = make_subplots(rows=1, cols=len(presentes), subplot_titles=[comp.SIGLAS[m] for m in presentes],
                            shared_yaxes=True, horizontal_spacing=0.04)
        for i, materia in enumerate(presentes, start=1):
            q = cat[cat["asignatura"] == materia].set_index("categoria").reindex(tipos)
            color = comp.COLORES_MATERIA[materia]
            fig.add_bar(y=tipos, x=q["pct_eventos"].fillna(0), orientation="h", marker_color=color,
                        showlegend=False, row=1, col=i, customdata=q["eventos"].fillna(0),
                        hovertemplate="%{y}: %{x:.1f} % (%{customdata:.0f} interacciones)<extra></extra>")
            fig.add_scatter(y=tipos, x=q["pct_curso"], mode="markers", showlegend=False, row=1, col=i,
                            marker=dict(symbol="diamond", size=10, color="#0b0b0b"),
                            hovertemplate="%{y}: el curso, %{x:.1f} %<extra></extra>")
            tope = max(cat["pct_eventos"].max(), cat["pct_curso"].max()) * 1.08   # misma escala en las tres
            fig.update_xaxes(ticksuffix=" %", range=[0, tope], row=1, col=i)
        fig.update_layout(height=60 + 42 * len(tipos), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")

        st.markdown(f"**Sus interacciones** ({comp.num(len(eventos))} hasta la fecha de corte)")
        c1, c2 = st.columns(2)
        sel_materias = c1.multiselect("Materia", presentes, default=presentes, key="fi_traz_materia",
                                      format_func=comp.SIGLAS.get)
        sel_tipos = c2.multiselect("Tipo", tipos, default=tipos, key="fi_traz_tipo")
        filtrados = eventos[eventos["asignatura"].isin(sel_materias) & eventos["categoria"].isin(sel_tipos)]
        tabla = filtrados.rename(columns={"fecha_hora": "Fecha y hora", "asignatura": "Materia", "categoria": "Tipo",
                                          "seccion": "Sección", "accion": "Acción", "descripcion": "Descripción"})
        st.dataframe(tabla, hide_index=True, width="stretch", height=420,
                     column_config={"Fecha y hora": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
        comp.boton_csv(tabla, f"trazabilidad_{id_alumno}", "Descargar interacciones (CSV)")
