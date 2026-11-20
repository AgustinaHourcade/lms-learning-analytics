"""Dashboard 6 (del plan): Ficha individual. Rediseño de una sola página (D87).

Responde, para UN alumno y a la fecha de corte: ¿en qué condición está en cada materia?,
¿qué alertas tiene?, ¿cómo le fue en cada instrumento?, ¿cuánto entra comparado con su
curso? y ¿qué hace cuando entra? Se lee de arriba hacia abajo, sin pestañas:

  Barra de control   filtro de grupo (condición o grupo de K-Means), selector de alumno
                     con búsqueda, anterior / siguiente / siguiente en riesgo y la ficha
                     en CSV. Debajo, los filtros globales que se están usando.
  Encabezado         nombre, ID, título con su condición en cada materia, días sin entrar,
                     semanas activas y sus alertas (en rojo, con la materia).
  Estado por materia la tabla protagonista: matrícula, semáforo, nota al corte (Álgebra con
                     la proyección a 120), margen al umbral de promoción, rendidos,
                     actividad de las últimas 8 semanas y riesgo de abandono (D58).
  Notas              una fila de barras por materia, en orden cronológico, sobre 100.
  Participación      percentiles dentro del curso y evolución semanal.
  Trazabilidad       % de clics por tipo contra el curso y mapa de calor día × hora.
  Pie                CSV de notas y de interacciones.

"Curso" es siempre el de metricas.en_curso(): quienes rindieron al menos un instrumento.
Todo responde a la fecha de corte, la materia y el umbral de la barra lateral; los datos
salen de src.metricas vía comp.metrica() (D29, D47) y los títulos de src.textos.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import componentes_ficha as comp
from componentes_ficha import esc
from src import textos
from src.config import APROBADO_PCT, SIN_EVALUACIONES

ab = comp.ml_abandono   # constantes del predictor (niveles de riesgo)
PRIORIDAD_RIESGO = {ab.ALTO: 3, ab.MEDIO: 2, ab.BAJO: 1, ab.SIN_ACTIVIDAD: 0}
TEXTO_RIESGO = {ab.ALTO: "riesgo alto", ab.MEDIO: "riesgo medio", ab.BAJO: "riesgo bajo"}
TODOS = "Todos los alumnos"
CONDICIONES = ["Libre", "Regular", "Promociona", SIN_EVALUACIONES]


def nombre_eje(texto: str, largo: int = 14) -> str:
    """Parte los nombres largos en dos renglones para el eje x (sin rotar las etiquetas)."""
    if len(texto) <= largo or " " not in texto:
        return texto
    palabras = texto.split(" ")
    corte = min(range(1, len(palabras)), key=lambda i: abs(len(" ".join(palabras[:i])) - len(texto) / 2))
    return " ".join(palabras[:corte]) + "<br>" + " ".join(palabras[corte:])


def riesgo_html(r) -> str:
    """'Alto · 43 %' (D58) en tinta neutra: verde, ámbar y rojo son solo de la condición.
    El nivel se distingue por el peso y la intensidad del texto, y siempre dice la palabra."""
    nivel = r["nivel_riesgo"]
    estilo = {ab.ALTO: f"font-weight:700;color:{comp.TINTA}", ab.MEDIO: f"font-weight:600;color:{comp.TINTA_2}"}
    prob = f' · {comp.pct(r["probabilidad"], 0)}' if pd.notna(r["probabilidad"]) else ""
    return (f'<span style="white-space:nowrap;{estilo.get(nivel, f"font-weight:500;color:{comp.TINTA_3}")}">'
            f'{esc(nivel)}{prob}</span>')


# ---------------------------------------------------------------------------
# Título y barra de control
# ---------------------------------------------------------------------------
comp.estilos()
f = comp.filtros()
st.title("Ficha individual")
st.markdown('<div class="tfi-desc">Condición, alertas y actividad de un alumno a la fecha de corte.</div>',
            unsafe_allow_html=True)

alumnos = comp.metrica("buscar_alumnos", texto="", solo_base=True)
if alumnos.empty:
    st.warning(f"No hay alumnos en la base de {f.materia.lower()}.", icon=":material/person_off:")
    st.stop()

# Grupos para filtrar el selector: condición en alguna de las materias de la barra y,
# si se pudieron armar, los grupos de K-Means de la página "Grupos de alumnos" (D57).
condiciones = comp.metrica("nota_final")[["id_alumno", "condicion"]]
grupos = comp.metrica("grupos_alumnos")
grupos = grupos[grupos["grupo"] > 0] if "grupo" in grupos else grupos.iloc[0:0]
opciones = {TODOS: set(alumnos["id_alumno"])}
for c in CONDICIONES:
    ids_c = set(condiciones.loc[condiciones["condicion"] == c, "id_alumno"])
    if ids_c:
        opciones[f"{c} en alguna materia ({comp.num(len(ids_c))})"] = ids_c
for g, sub in grupos.sort_values("grupo").groupby("nombre_grupo", sort=False):
    opciones[f"Grupo: {g} ({comp.num(sub['id_alumno'].nunique())})"] = set(sub["id_alumno"])

riesgo_todos = comp.metrica("riesgo_abandono")
peor = (riesgo_todos.assign(p=riesgo_todos["nivel_riesgo"].map(PRIORIDAD_RIESGO))
        .sort_values("p").groupby("id_alumno")["nivel_riesgo"].last())
nombres = dict(zip(alumnos["id_alumno"], alumnos["nombre_completo"]))

if st.session_state.get("fi_grupo") not in opciones:
    st.session_state.pop("fi_grupo", None)
with st.container(border=True, key="tarjeta_selector"):
    c_grupo, c_sel, c_ant, c_sig, c_riesgo, c_desc = st.columns([2.2, 3.9, 0.55, 0.55, 2.2, 1.8],
                                                                  vertical_alignment="bottom")
    grupo = c_grupo.selectbox("Grupo", list(opciones), key="fi_grupo",
                              help="Acota el selector a una condición (en alguna de las materias de la barra) "
                                   "o a un grupo de la página «Grupos de alumnos».")
    ids = [i for i in alumnos["id_alumno"] if i in opciones[grupo]]
    if not ids:
        st.info("Ningún alumno de la base en ese grupo.", icon=":material/person_off:")
        st.stop()
    if st.session_state.get("fi_alumno") not in ids:   # cambió la materia o el grupo
        st.session_state.pop("fi_alumno", None)

    def mover(paso: int, solo_riesgo: bool = False) -> None:
        """Anterior / siguiente (o el siguiente en riesgo alto), dando la vuelta."""
        actual = st.session_state.get("fi_alumno", ids[0])
        i = ids.index(actual) if actual in ids else -1
        for k in range(1, len(ids) + 1):
            candidato = ids[(i + paso * k) % len(ids)]
            if not solo_riesgo or peor.get(candidato) == ab.ALTO:
                st.session_state["fi_alumno"] = candidato
                return

    id_alumno = c_sel.selectbox(
        f"Alumno · {comp.num(len(ids))} de {comp.num(len(alumnos))}", ids, key="fi_alumno",
        format_func=lambda i: f"{nombres[i]} · {i}" + (f" — {TEXTO_RIESGO[peor[i]]}" if peor.get(i) in TEXTO_RIESGO
                                                        else ""),
        help="Escribí parte del apellido, nombre o ID (ej.: ALU_1263), o «riesgo alto». Ordenados por apellido.")
    c_ant.button(":material/chevron_left:", key="fi_anterior", help="Alumno anterior", width="stretch",
                 on_click=mover, args=(-1,))
    c_sig.button(":material/chevron_right:", key="fi_siguiente", help="Alumno siguiente", width="stretch",
                 on_click=mover, args=(1,))
    c_riesgo.button("Siguiente en riesgo", key="fi_sig_riesgo", icon=":material/priority_high:", width="stretch",
                    on_click=mover, args=(1, True), help="El próximo alumno de la lista con riesgo de abandono alto.")

st.caption(f"Corte: {comp.fmt_fecha(f.fecha_corte)} · {f.materia} · inactivo tras {comp.dias(f.umbral)}")

ficha = comp.metrica("ficha_individual", id_alumno=id_alumno)
materias = ficha["materias"]
if materias.empty:   # no pasa con solo_base=True, pero por las dudas
    st.info("Este alumno no está en la base de ninguna de las materias elegidas.", icon=":material/person_off:")
    st.stop()
suyas = materias["asignatura"].tolist()
riesgo = comp.metrica("riesgo_alumno", id_alumno=id_alumno).set_index("asignatura").reindex(suyas)
datos, resumen = ficha["datos"], ficha["resumen"]
por_materia = materias.set_index("asignatura")
SIG = comp.SIGLAS

with c_desc:
    tabla_ficha = pd.DataFrame({
        "Materia": suyas, "Inscripto": materias["inscripto"].map({True: "Sí", False: "No"}),
        "Condición": materias["condicion"], "Nota al corte": materias["nota_final"].round(2),
        "Escala": materias["escala"], "Puntos": materias["puntos"].round(2),
        "Puntos posibles": materias["puntos_posibles"], "Margen al umbral de promoción": materias["margen"],
        "Le falta para promocionar": materias["falta_promocion"], "Le falta para regularizar": materias["falta_regular"],
        "Rendidos": materias["rendidos"], "Instrumentos": materias["instrumentos"],
        "Actividad": materias["estado_actividad"], "Días sin entrar": materias["dias_sin_actividad"],
        "Última interacción": materias["ultima_interaccion"],
        "Riesgo de abandono": riesgo["nivel_riesgo"].to_numpy(),
        "Probabilidad de abandono (%)": riesgo["probabilidad"].round(1).to_numpy(),
    })
    comp.boton_csv(tabla_ficha, f"ficha_{id_alumno}", "Descargar ficha", key="fi_csv_ficha")

# ---------------------------------------------------------------------------
# Encabezado del alumno
# ---------------------------------------------------------------------------
iniciales = "".join(str(x).strip()[:1] for x in (datos["apellido"], datos["nombre"])).upper()
insight = textos.titulo_condiciones([(SIG[m], c) for m, c in zip(suyas, materias["condicion"])])
chips = []
if resumen["dias_sin_entrar"] is None:
    chips.append(comp.chip_estado("Nunca entró al aula"))
else:
    d_ = resumen["dias_sin_entrar"]
    chips.append(comp.chip_estado(f"Sin entrar hace {comp.dias(d_)}" if d_ else "Entró el día del corte"))
chips.append(comp.chip_estado(f"Activo {resumen['semanas_activas']}/{resumen['semanas_cursada']} semanas"))

alertas = ficha["alertas"]
no_rinde = set(alertas.loc[alertas["tipo"] == "sin_notas", "asignatura"])   # su Libre es consecuencia del 0
alertas = alertas[~((alertas["tipo"] == "libre") & alertas["asignatura"].isin(no_rinde))]
TEXTO_ALERTA = {
    "sin_actividad": lambda a: "Nunca entró ni rindió",
    "sin_notas": lambda a: "Entra pero no rinde",
    "libre": lambda a: "Libre",
    "inactivo": lambda a: f"Sin entrar hace {comp.dias(int(por_materia.loc[a, 'dias_sin_actividad']))}",
    "no_inscripto": lambda a: "No inscripto",
}
if alertas.empty:
    chips.append(comp.chip_estado("✓ Sin alertas"))
else:
    agrupadas = {}   # la misma alerta en varias materias va en un solo chip: "Sin entrar hace 13 días · ALG, PYE"
    for a in alertas.itertuples():
        agrupadas.setdefault(TEXTO_ALERTA[a.tipo](a.asignatura), []).append(SIG[a.asignatura])
    chips += [f'<span class="fx-alerta tfi-num">⚠ {esc(texto)} · {esc(", ".join(siglas))}</span>'
              for texto, siglas in agrupadas.items()]

comp.html(f"""
<section class="fi-card" aria-label="Resumen del alumno"><div class="fx-cab">
  <div class="fx-avatar" aria-hidden="true">{esc(iniciales)}</div>
  <div class="fx-quien">
    <h2 class="fx-nombre">{esc(datos['nombre_completo'])}</h2>
    <div class="fx-id tfi-num">{esc(id_alumno)}</div>
    <h3 class="fx-insight">{esc(insight)}</h3>
    <div class="fx-chips">{''.join(chips)}</div>
  </div>
</div></section>""")

# ---------------------------------------------------------------------------
# Estado por materia (la tabla protagonista)
# ---------------------------------------------------------------------------
semanal = ficha["semanal"]
ultimas = semanal.groupby("asignatura").tail(comp.metricas.SEMANAS_SPARKLINE)
tope_spark = ultimas["eventos"].max() if not ultimas.empty else 1
filas = []
for fila in materias.itertuples():
    m = fila.asignatura
    color_m = comp.COLORES_MATERIA[m]
    matricula = ('<span class="fx-badge">Inscripto ✓</span>' if fila.inscripto
                 else '<span class="fx-badge no">No inscripto ⚠</span>')
    if fila.instrumentos == 0:
        nota = margen = f'<span style="color:{comp.TENUE}">–</span>'
    else:
        if fila.escala != 100:   # Álgebra: acumulativa, se proyecta a la escala (D17)
            pct_posible = fila.puntos / fila.puntos_posibles * 100
            nota = (f'<span class="fx-grande" style="font-size:13px;white-space:nowrap">'
                    f'{comp.num(fila.puntos, 1)} de {comp.num(fila.puntos_posibles, 0)} pts posibles '
                    f'({comp.num(pct_posible, 0)} %)</span>'
                    f'<span class="fx-sub">· proy. <b style="color:{comp.TINTA}">{comp.num(fila.nota_final, 1)}'
                    f'/{fila.escala}</b></span>')
        else:
            nota = (f'<span class="fx-grande">{comp.num(fila.nota_final, 1)}</span> '
                    f'<span style="font-size:12px;color:{comp.TENUE}">/ {fila.escala}</span>')
        margen = (f'<span class="fx-grande">{comp.signo(fila.margen)}</span>'
                  f'<span class="fx-sub">vs. {fila.corte_promocion} (promoción)</span>')
        if fila.condicion == "Regular":
            margen += f'<span class="fx-sub">le faltan {comp.num(fila.falta_promocion, 1)} para promocionar</span>'
        elif fila.condicion == "Libre":
            margen += (f'<span class="fx-sub">le faltan {comp.num(fila.falta_regular, 1)} para el '
                       f'{fila.corte_regular}</span>')
    cuando = (f"hace {comp.dias(int(fila.dias_sin_actividad))}" if fila.eventos and fila.dias_sin_actividad
              else "el día del corte" if fila.eventos else "nunca entró")
    actividad = (f'{comp.sparkline(ultimas.loc[ultimas["asignatura"] == m, "eventos"], color_m, tope_spark)}'
                 f'<span class="fx-sub">{cuando}</span>')
    celda_riesgo = riesgo_html(riesgo.loc[m]) if pd.notna(riesgo.loc[m, "nivel_riesgo"]) else "–"
    filas.append(f"""<tr>
      <td><span style="display:inline-flex;align-items:center;gap:9px">{comp.cuadro(color_m)}
        <span><strong style="font-weight:600">{esc(m)}</strong><br>
        <span style="display:inline-flex;gap:5px;margin-top:3px">{comp.sigla(m)}{matricula}</span></span></span></td>
      <td>{comp.pastilla_condicion(fila.condicion)}</td>
      <td>{nota}</td><td>{margen}</td>
      <td>{fila.rendidos} de {fila.instrumentos}</td>
      <td>{actividad}</td><td>{celda_riesgo}</td></tr>""")
pie = "Lo no rendido cuenta 0." + (" Álgebra: proyección a 120 pts." if "Álgebra" in suyas else "")
ayuda_riesgo = comp.info("Probabilidad de que abandone la materia (no vuelva a entrar ni rinda nada más), "
                         "según el predictor de abandono. Detalle y advertencias en la página «Predictor de "
                         "abandono».")
ayuda_margen = comp.info("Nota al corte menos el umbral de promoción de la materia (85; AED 90), en la escala "
                         "de la materia.")
comp.html(f"""
<section class="fi-card" aria-label="Estado por materia">
  <div class="fi-card-cab"><h3 class="fi-h3">Estado por materia</h3></div>
  <div style="overflow-x:auto"><table class="fi-tabla fx-tabla">
    <thead><tr><th scope="col">Materia</th><th scope="col">Condición</th><th scope="col">Nota al corte</th>
      <th scope="col">Margen al umbral {ayuda_margen}</th><th scope="col">Rendidos</th>
      <th scope="col">Actividad {comp.metricas.SEMANAS_SPARKLINE} sem.</th>
      <th scope="col">Riesgo de abandono {ayuda_riesgo}</th></tr></thead>
    <tbody>{''.join(filas)}</tbody></table></div>
  <div class="fi-card-pie">{pie}</div>
</section>""")

# ---------------------------------------------------------------------------
# Notas: una fila de barras por materia, en orden cronológico, sobre 100
# ---------------------------------------------------------------------------
inst = ficha["instrumentos"]
cuentan = inst[inst["cuenta_en_final"]]
rendidos_ = cuentan[cuentan["rindio"] | cuentan["recuperatorio_aplicado"]]
mas_baja = None
if not rendidos_.empty:
    r_ = rendidos_.loc[rendidos_["nota_pct_corte"].idxmin()]
    mas_baja = (r_["nombre"], SIG[r_["asignatura"]], r_["nota_pct_corte"])
titulo_notas = textos.titulo_notas(int(cuentan["aprobado"].sum()), len(cuentan),
                                   len(cuentan) - len(rendidos_), mas_baja)
with st.container(border=True, key="tarjeta_notas"):
    st.markdown(f'<h3 class="fi-h3">{esc(titulo_notas)}</h3>', unsafe_allow_html=True)
    for m in suyas:
        q = inst[inst["asignatura"] == m]
        if q.empty:
            st.markdown(f'<div class="fx-col-titulo" style="margin-top:10px">{comp.cuadro(comp.COLORES_MATERIA[m])}'
                        f'{esc(m)}<span style="font-weight:400;color:{comp.TINTA_3}">· {SIN_EVALUACIONES.lower()} '
                        f'a la fecha de corte</span></div>', unsafe_allow_html=True)
            continue
        rindio = q["rindio"].to_numpy()
        eje = [nombre_eje(n) for n in q["nombre"]]
        valor = q["nota_pct"].where(q["rindio"])
        colores = [comp.GRIS_NO_RINDIO if not r else (comp.COLORES_MATERIA[m] if v >= APROBADO_PCT else comp.ROJO)
                   for r, v in zip(rindio, valor.fillna(0))]
        etiquetas = [comp.pct(v, 0) if r else "no rindió" for r, v in zip(rindio, valor)]
        detalle = [
            (f"Nota: {comp.num(o, 2)} / {comp.num(mx, 0)} ({comp.pct(v, 1)})" if r else "No rindió · cuenta 0"
             if c else "No rindió")
            + (" · la reemplaza el recuperatorio" if ra else "")
            for r, o, mx, v, c, ra in zip(rindio, q["nota_obtenida"], q["puntaje_maximo"], valor,
                                          q["cuenta_en_final"], q["recuperatorio_aplicado"])]
        fechas = q["fecha_instrumento"].map(comp.fmt_fecha)
        fig = go.Figure()
        fig.add_bar(x=eje, y=valor.fillna(2.5), marker_color=colores, showlegend=False,
                    marker_line=dict(color=[comp.ROJO if (r and v < APROBADO_PCT) else "rgba(0,0,0,0)"
                                            for r, v in zip(rindio, valor.fillna(0))], width=1.2),
                    customdata=list(zip(q["nombre"], detalle, fechas)),
                    hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Fecha: %{customdata[2]}"
                                  "<extra></extra>")
        fig.add_scatter(x=eje, y=q["promedio_curso_pct"], mode="markers", showlegend=False,
                        marker=dict(symbol="diamond", size=10, color=comp.TINTA, line=dict(color="#FFFFFF", width=1.5)),
                        customdata=list(zip(q["nombre"], q["rindieron"].fillna(0).astype(int))),
                        hovertemplate="<b>%{customdata[0]}</b><br>Promedio de quienes lo rindieron: %{y:.1f} %"
                                      "<br>%{customdata[1]} alumnos<extra></extra>")
        # Etiquetas en una franja fija arriba de 100: el rombo del curso nunca las tapa.
        fig.add_scatter(x=eje, y=[109] * len(eje), mode="text", text=etiquetas, showlegend=False, hoverinfo="skip",
                        textfont=dict(size=11, color=[comp.TINTA_2 if r else comp.TENUE for r in rindio]))
        fig.add_hline(y=APROBADO_PCT, line=dict(color=comp.TINTA_3, width=1, dash="dash"),
                      annotation_text=f"{APROBADO_PCT} %", annotation_position="right",
                      annotation_font=dict(size=10, color=comp.TINTA_3))
        fig.update_yaxes(range=[0, 116], tickvals=[0, 50, 100], ticksuffix=" %", showgrid=True)
        fig.update_xaxes(tickangle=0, tickfont=dict(size=11))
        fig.update_layout(title=dict(text=m, font=dict(size=13)), height=230, bargap=0.45,
                          margin=dict(t=34, l=4, r=36, b=4))
        comp.grafico(fig)
    st.caption("% de la nota máxima. ◆ = promedio de quienes lo rindieron. Gris = no rindió.")

# ---------------------------------------------------------------------------
# Participación: percentiles dentro del curso y evolución semanal
# ---------------------------------------------------------------------------
titulo_part = textos.titulo_participacion([
    (m, por_materia.loc[m, "percentil_nota_final"], por_materia.loc[m, "percentil_minutos"],
     por_materia.loc[m, "percentil_sesiones"]) for m in suyas])
TOOLTIP_PERCENTIL = ("Percentil dentro del curso (quienes rindieron al menos un instrumento): p80 = igual o por "
                     "encima del 80 % de ellos.")
bloques = []
for fila in materias.itertuples():
    color_m = comp.COLORES_MATERIA[fila.asignatura]
    filas_p = []
    for col, et in comp.metricas.VARIABLES_FICHA.items():
        v, p, c = getattr(fila, col), getattr(fila, f"percentil_{col}"), getattr(fila, f"curso_{col}")
        dec, suf = (1, "") if col == "nota_final" else (0, " %") if col == "avance" else (0, "")
        extra = comp.info("Foto a la fecha de exportación; no se recorta con el corte.") if col == "avance" else ""
        filas_p.append(
            f'<div class="fx-fila" title="{esc(TOOLTIP_PERCENTIL)}"><span class="fx-fila-et">{esc(et)}{extra}</span>'
            f'<div class="fx-fila-bar">{comp.barra(p, color_m)}</div>'
            f'<div class="fx-fila-val tfi-num"><b>{"p" + comp.num(p) if pd.notna(p) else "–"} · '
            f'{comp.num(v, dec)}{suf if pd.notna(v) else ""}</b><span>curso {comp.num(c, dec)}'
            f'{suf if pd.notna(c) else ""}</span></div></div>')
    reporte = comp.info(f"Reporte del LMS: {comp.num(fila.intervenciones_foros)} intervenciones en foros · "
                        f"{comp.num(fila.emails_enviados)} correos enviados.")
    bloques.append(f'<div><div class="fx-col-titulo">{comp.cuadro(color_m)}{esc(fila.asignatura)}{reporte}</div>'
                   f'{"".join(filas_p)}</div>')
comp.html(f"""<section class="fi-card" aria-label="Participación">
  <div class="fi-card-cab"><h3 class="fi-h3">{esc(titulo_part)}</h3></div>
  <div class="fx-grilla">{''.join(bloques)}</div></section>""")

with st.container(border=True, key="tarjeta_semanal"):
    c_t, c_v = st.columns([3, 2], vertical_alignment="center")
    c_t.markdown('<h3 class="fi-h3">Evolución semanal</h3>', unsafe_allow_html=True)
    if semanal.empty or semanal["eventos"].sum() == 0:
        st.info("No tiene interacciones registradas hasta la fecha de corte.", icon=":material/visibility_off:")
    else:
        ver = c_v.segmented_control("Ver", ["Interacciones", "Minutos", "Sesiones"], default="Interacciones",
                                    key="fi_ver_semanal", label_visibility="collapsed") or "Interacciones"
        columna = {"Interacciones": "eventos", "Minutos": "minutos", "Sesiones": "sesiones"}[ver]
        evaluaciones = ficha["evaluaciones"]
        tope = max(semanal[columna].max(), semanal[f"curso_{columna}"].max())
        decimales = ",.1f" if columna == "minutos" else ",.0f"
        for col, m in zip(st.columns(len(suyas)), suyas):
            q = semanal[semanal["asignatura"] == m]
            color = comp.COLORES_MATERIA[m]
            fig = go.Figure()
            for ev in evaluaciones[evaluaciones["asignatura"] == m].itertuples():
                fig.add_vline(x=ev.fecha_instrumento, line=dict(color=comp.GRIS_NO_RINDIO, width=1))
            fig.add_scatter(x=q["periodo"], y=q[f"curso_{columna}"], mode="lines", name="Promedio del curso",
                            line=dict(color=color, width=1.4, dash="dot"), opacity=0.7,
                            hovertemplate=f"Semana del %{{x|%d/%m/%Y}}: %{{y:,.1f}} {ver.lower()} por alumno"
                                          "<extra>Curso</extra>")
            fig.add_scatter(x=q["periodo"], y=q[columna], mode="lines+markers", name="El alumno",
                            line=dict(color=color, width=2.2), marker=dict(size=5),
                            hovertemplate=f"Semana del %{{x|%d/%m/%Y}}: %{{y:{decimales}}} {ver.lower()}"
                                          "<extra>El alumno</extra>")
            fig.update_yaxes(range=[0, tope * 1.1 if tope else 1])   # misma escala en todas
            fig.update_xaxes(tickformat="%d/%m", nticks=5)
            fig.update_layout(title=dict(text=m, font=dict(size=13)), height=230, showlegend=False,
                              margin=dict(t=36, l=4, r=4, b=4))
            comp.grafico(fig, col)
        st.caption("— alumno · ··· promedio del curso · │ evaluación")

# ---------------------------------------------------------------------------
# Trazabilidad: % de clics por tipo contra el curso y mapa de calor día × hora
# ---------------------------------------------------------------------------
cat = ficha["categorias"]
titulo_traz = textos.titulo_trazabilidad([(SIG[r.asignatura], r.tipo, r.pct_eventos, r.pct_curso)
                                          for r in cat.itertuples()])
with st.container(border=True, key="tarjeta_trazabilidad"):
    st.markdown(f'<h3 class="fi-h3">{esc(titulo_traz)}</h3>', unsafe_allow_html=True)
    if cat.empty:
        st.info("No tiene interacciones registradas hasta la fecha de corte.", icon=":material/visibility_off:")
    else:
        tope = max(cat["pct_eventos"].max(), cat["pct_curso"].max())   # misma escala en todas
        bloques = []
        for m in suyas:
            q = cat[cat["asignatura"] == m]
            color_m = comp.COLORES_MATERIA[m]
            if q.empty:
                cuerpo = f'<div style="font-size:12px;color:{comp.TINTA_3}">Sin interacciones.</div>'
            else:
                cuerpo = "".join(
                    f'<div class="fx-fila" title="{esc(r.tipo)}: {comp.pct(r.pct_eventos)} de sus clics · curso '
                    f'{comp.pct(r.pct_curso)} ({comp.signo(r.pct_eventos - r.pct_curso)} p.p.)">'
                    f'<span class="fx-fila-et" style="flex-basis:92px">{esc(r.tipo)}</span>'
                    f'<div class="fx-fila-bar">{comp.barra(r.pct_eventos, color_m, alto=11, maximo=tope, marca=r.pct_curso)}'
                    f'</div><div class="fx-fila-val tfi-num" style="flex-basis:70px"><b>{comp.pct(r.pct_eventos, 0)}</b>'
                    f'<span>curso {comp.pct(r.pct_curso, 0)}</span></div></div>' for r in q.itertuples())
            bloques.append(f'<div><div class="fx-col-titulo">{comp.cuadro(color_m)}{esc(m)}</div>{cuerpo}</div>')
        comp.html(f'<div class="fx-grilla" style="padding:6px 0 4px">{"".join(bloques)}</div>')
        st.caption("% de clics por tipo. │ = curso. Otros = Agenda + Notas.")

        calor = ficha["calor"]
        matriz = calor.pivot(index="dia_semana", columns="hora", values="eventos").sort_index()
        dias_semana = [calor.loc[calor["dia_semana"] == i, "nombre_dia"].iloc[0] for i in matriz.index]
        fig = go.Figure(go.Heatmap(
            z=matriz.to_numpy(), x=[f"{h:02d}" for h in matriz.columns], y=dias_semana,
            colorscale=[[i / (len(comp.SECUENCIAL) - 1), c] for i, c in enumerate(comp.SECUENCIAL)],
            xgap=2, ygap=2, colorbar=dict(title=dict(text="Clics", side="right"), thickness=10),
            hovertemplate="%{y} de %{x} a %{x}:59 h: %{z:,.0f} interacciones<extra></extra>"))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(showgrid=False, title_text="Hora del día", title_font=dict(size=11))
        fig.update_layout(title=dict(text=f"Cuándo entra · {comp.num(calor['eventos'].sum())} interacciones hasta el "
                                          f"{comp.fmt_fecha(f.fecha_corte)}", font=dict(size=13)),
                          height=290, margin=dict(t=36, l=4, r=4, b=4))
        comp.grafico(fig)

# ---------------------------------------------------------------------------
# Pie: descargas
# ---------------------------------------------------------------------------
notas_csv = pd.DataFrame({
    "Materia": inst["asignatura"], "Instrumento": inst["nombre"], "Fecha": inst["fecha_instrumento"],
    "Rindió": inst["rindio"].map({True: "Sí", False: "No"}), "Nota obtenida": inst["nota_obtenida"],
    "Puntaje máximo": inst["puntaje_maximo"], "Nota (%)": inst["nota_pct"],
    "Cuenta para la nota (%)": inst["nota_pct_corte"].where(inst["cuenta_en_final"]),
    "Aprobado": inst["aprobado"].where(inst["cuenta_en_final"]).map({True: "Sí", False: "No"}),
    "Promedio de quienes lo rindieron (%)": inst["promedio_curso_pct"], "Rindieron": inst["rindieron"],
    "Recuperatorio aplicado": inst["recuperatorio_aplicado"].map({True: "Sí", False: ""}),
})
eventos = ficha["eventos"].rename(columns={"fecha_hora": "Fecha y hora", "asignatura": "Materia", "categoria": "Tipo",
                                           "seccion": "Sección", "accion": "Acción", "descripcion": "Descripción"})
c1, c2, _ = st.columns([1.3, 1.6, 3])
with c1:
    comp.boton_csv(notas_csv, f"notas_{id_alumno}", "Descargar notas (CSV)", key="fi_csv_notas")
with c2:
    comp.boton_csv(eventos, f"interacciones_{id_alumno}", "Descargar interacciones (CSV)", key="fi_csv_eventos")
