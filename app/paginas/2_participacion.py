"""Dashboard 2 (del plan): Participación.

Responde: ¿cuántos alumnos siguen entrando al aula?, ¿quiénes se están
desenganchando y en qué materia?, ¿qué cambió esta semana?, ¿qué herramientas
del aula se usan? y ¿cómo viene cada alumno?

  Período         filtro propio de la página (toda la cursada, últimas 4 o 2
                  semanas o desde una fecha) que termina en la fecha de corte (D53).
                  Recorta sesiones, minutos, la evolución y la tabla por alumno.
  Estado          quién sigue entrando a la fecha de corte, en cuatro tramos: activo,
                  enfriándose, desconectado y sin actividad (D35, D54). Mira toda la
                  cursada, no el período.
  Movimientos     qué cambió en los últimos 7 días (D54), con la lista de cada grupo.
  Evolución       accesos por día / semana / mes y por materia (en % de la base o por
                  alumno), con las evaluaciones marcadas; estado por materia, días sin
                  entrar y resumen por materia.
  Reporte         avance, uso de herramientas y control de las sesiones contra el
                  tiempo de uso del LMS (foto al 24/10, D36).
  Por alumno      tabla filtrable con CSV y la evolución semanal de un alumno contra
                  el promedio de su materia.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
El estilo (tarjetas, chips, barras) sale de componentes.py.
"""
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes_participacion as comp
from src.config import DIAS_DESCONECTADO, DIAS_REGRESO
from src.metricas import (ACTIVO, CRUZO_UMBRAL, DESCONECTADO, ENFRIANDOSE, ENTRA_NO_RINDE, NUNCA_ENTRO,
                          SIN_ACTIVIDAD, TRAMOS_ACTIVIDAD, VOLVIO)

f = comp.encabezado(
    "Participación",
    "Cuántos alumnos siguen entrando al aula, quiénes se están desenganchando y en qué materia. La actividad "
    "sale de la trazabilidad; el avance y el uso de herramientas, del reporte de participación (foto al 24/10).",
)

ORDEN = {"asignatura": list(comp.COLORES_MATERIA)}
TONO_TRAMO = {t: comp.TONO_ESTADO[t] for t in TRAMOS_ACTIVIDAD}
H = comp.html

# ---------------------------------------------------------------------------
# Período (filtro propio de la página, D53). Termina siempre en la fecha de corte.
# ---------------------------------------------------------------------------
inicio_datos, _ = comp.rango_fechas()
PERIODOS = ["Toda la cursada", "Últimas 4 semanas", "Últimas 2 semanas", "Desde una fecha"]
c1, c2, c3 = st.columns([3, 1.2, 1.6], vertical_alignment="bottom")
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
desde_real = desde or inicio_datos
semanas_periodo = ((f.fecha_corte - desde_real).days + 1) / 7
c3.caption(f"{comp.fmt_fecha(desde_real, '%d/%m')} → {comp.fmt_fecha(f.fecha_corte, '%d/%m')} · "
           f"{comp.num(semanas_periodo, 0)} semanas")
texto_periodo = f"del {comp.fmt_fecha(desde_real)} al {comp.fmt_fecha(f.fecha_corte)}"
SUFIJO = f"{desde_real:%Y%m%d}_{f.fecha_corte:%Y%m%d}"

alumnos = comp.metrica("participacion_alumnos", desde=desde)   # números del período
estado = comp.metrica("participacion_alumnos")                 # estado a la fecha de corte (toda la cursada)
resumen = comp.metrica("resumen_participacion", desde=desde)

# Los rangos de días de cada tramo, para los textos (dependen del umbral elegido).
lim = max(DIAS_DESCONECTADO, f.umbral)
RANGOS = {ACTIVO: f"hasta {f.umbral} días", ENFRIANDOSE: f"{f.umbral + 1} a {lim} días",
          DESCONECTADO: f"{lim + 1} días o más", SIN_ACTIVIDAD: "nunca entraron"}
NOMBRES = {ACTIVO: "activos", ENFRIANDOSE: "enfriándose", DESCONECTADO: "desconectados",
           SIN_ACTIVIDAD: "sin actividad"}
tramos_visibles = [t for t in TRAMOS_ACTIVIDAD if not (t == ENFRIANDOSE and f.umbral >= DIAS_DESCONECTADO)]


def conteo_tramos(df: pd.DataFrame) -> pd.Series:
    return df["tramo_actividad"].value_counts().reindex(TRAMOS_ACTIVIDAD, fill_value=0)


# ---------------------------------------------------------------------------
# Titular: quién sigue entrando + tarjetas chicas
# ---------------------------------------------------------------------------
n_base = len(estado)
cuenta = conteo_tramos(estado)
pct_activos = cuenta[ACTIVO] / n_base * 100 if n_base else np.nan

corte_anterior = f.fecha_corte - timedelta(days=7)
chip_delta = ""
if corte_anterior >= inicio_datos and n_base:
    antes = comp.metrica("actividad_alumnos", fecha_corte=corte_anterior)
    dif = pct_activos - antes["activo"].mean() * 100
    tono = "bien" if dif >= 1 else "critico" if dif <= -1 else "neutro"
    signo = "+" if dif >= 0.5 else "−" if dif <= -0.5 else "±"
    chip_delta = comp.chip(f"{signo}{comp.num(abs(dif), 0)} pts vs. la semana anterior", tono)

col_titular, col_kpis = st.columns([1.45, 1], gap="medium")
with col_titular, comp.tarjeta("titular"):
    segmentos = [(cuenta[t], comp.COLORES_TRAMO[t]) for t in TRAMOS_ACTIVIDAD]
    items = [(TONO_TRAMO[t], f'<b class="tfi">{comp.num(cuenta[t])}</b> {NOMBRES[t]} · {RANGOS[t]}')
             for t in tramos_visibles]
    recuperables = cuenta[ENFRIANDOSE]
    lectura = (f"“Inactivo” junta al que faltó una semana con el que se fue hace meses. A los "
               f"<b>{comp.num(recuperables)}</b> que se están enfriando todavía se los recupera con un mensaje; "
               f"los <b>{comp.num(cuenta[DESCONECTADO])}</b> desconectados necesitan otro tipo de contacto."
               if f.umbral < DIAS_DESCONECTADO else
               f"Con un umbral de {f.umbral} días, todos los inactivos llevan más de {DIAS_DESCONECTADO} días "
               "sin entrar: cuentan como desconectados.")
    H(f"""<div class="tfi">
      <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;
                  margin-bottom:12px">
        {comp.etiqueta(f"Quién sigue entrando · al {comp.fmt_fecha(f.fecha_corte, '%d/%m')}")}{chip_delta}
      </div>
      <div style="display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:14px">
        <span class="tfi-big">{comp.pct(pct_activos, 0)}</span>
        <span class="tfi-sub">{comp.num(cuenta[ACTIVO])} de {comp.num(n_base)} entraron en los últimos
          {f.umbral} días</span>
      </div>
      <div style="margin-bottom:10px">{comp.barra_apilada(segmentos, alto=28)}</div>
      {comp.leyenda(items)}
      <p class="tfi-desc" style="margin-top:12px">{lectura}</p>
    </div>""")

with col_kpis:
    def histograma(serie: pd.Series) -> list:
        return np.histogram(serie.dropna(), bins=9)[0].tolist() if serie.notna().any() else []

    foros = alumnos[alumnos["intervenciones_foros"].fillna(0) > 0]
    materias_foros = sorted(comp.SIGLAS[a] for a in foros["asignatura"].unique())
    detalle_foros = (f"{comp.num(len(foros))} alumnos" +
                     (f", todos de {materias_foros[0]}" if len(materias_foros) == 1 else ""))
    k1, k2 = st.columns(2)
    k1.metric("Sesiones por alumno", comp.num(alumnos["sesiones"].mean(), 1), border=True,
              delta=f"mediana {comp.num(alumnos['sesiones'].median(), 0)}", delta_color="off", delta_arrow="off",
              chart_data=histograma(alumnos["sesiones"]), chart_type="bar",
              help="Promedio en el período, sobre toda la base (con los 0). Una sesión es una tanda de eventos "
                   "sin pausas de más de 30 minutos. El gráfico es la distribución.")
    k2.metric("Minutos por alumno", comp.num(alumnos["minutos"].mean(), 0), border=True,
              delta=f"mediana {comp.num(alumnos['minutos'].median(), 0)}", delta_color="off", delta_arrow="off",
              chart_data=histograma(alumnos["minutos"]), chart_type="bar",
              help="Suma de la duración de las sesiones en el período, promediada sobre toda la base.")
    k3, k4 = st.columns(2)
    k3.metric("Avance promedio", comp.pct(alumnos["avance"].mean(), 0), border=True,
              delta="del contenido · al 24/10", delta_color="off", delta_arrow="off",
              help="Del reporte de participación: % del contenido del aula que recorrió el alumno. Es una foto al "
                   "24/10 y no cambia con la fecha de corte ni el período.")
    k4.metric("Uso de foros", comp.pct((alumnos["intervenciones_foros"].fillna(0) > 0).mean() * 100, 1),
              border=True, delta=detalle_foros, delta_color="off", delta_arrow="off",
              help="% de la base que intervino al menos una vez en un foro (reporte al 24/10).")

# ---------------------------------------------------------------------------
# Qué se movió esta semana (D54)
# ---------------------------------------------------------------------------
mov = comp.metrica("movimientos_semana")
TEXTOS_MOV = {
    CRUZO_UMBRAL: (f"cruzaron el umbral de {f.umbral} días", "Ver la lista para contactarlos"),
    VOLVIO: (f"volvieron después de {DIAS_REGRESO // 7} semanas o más sin entrar", "Ver quiénes"),
    ENTRA_NO_RINDE: ("están activos y no rindieron ningún instrumento", "Ver quiénes"),
    NUNCA_ENTRO: ("nunca entraron en toda la cursada", "Ver quiénes"),
}
with comp.tarjeta("movimientos"):
    c1, c2 = st.columns([2, 1.4], vertical_alignment="bottom")
    with c1:
        comp.titulo_seccion("Qué se movió esta semana")
    c2.caption(f"Del {comp.fmt_fecha(corte_anterior + timedelta(days=1), '%d/%m')} al "
               f"{comp.fmt_fecha(f.fecha_corte, '%d/%m')} contra la semana anterior · toda la cursada")
    for i, (col, (clave, (texto, enlace))) in enumerate(zip(st.columns(4), TEXTOS_MOV.items())):
        grupo = mov[mov["movimiento"] == clave]
        urgente = clave == CRUZO_UMBRAL and len(grupo) > 0
        color = (comp.TONOS["critico"]["texto"] if urgente else
                 comp.TONOS["bien"]["texto"] if clave == VOLVIO and len(grupo) else comp.TEXTO)
        with col, st.container(border=True, key=f"{'alerta' if urgente else 'tarjeta'}_mov_{i}"):
            H(f'<div class="tfi"><p class="tfi-num" style="color:{color}">{comp.num(len(grupo))}</p>'
              f'<p style="margin:2px 0 4px; font:500 13px Inter, sans-serif; color:{comp.TEXTO_2}; min-height:38px">'
              f'{texto}</p></div>')
            if grupo.empty:
                st.caption("Nadie en este grupo.")
            else:
                with st.popover(enlace, width="stretch"):
                    lista = grupo.assign(materia=grupo["asignatura"].map(comp.SIGLAS))
                    st.dataframe(lista[["nombre_completo", "id_alumno", "materia", "dias_sin_actividad",
                                        "ultima_interaccion"]], hide_index=True, width="stretch", column_config={
                        "nombre_completo": "Alumno", "id_alumno": "ID", "materia": "Materia",
                        "dias_sin_actividad": st.column_config.NumberColumn("Sin entrar", format="%d d"),
                        "ultima_interaccion": st.column_config.DatetimeColumn("Último ingreso",
                                                                              format="DD/MM HH:mm")})
                    comp.boton_csv(lista.drop(columns="materia"), f"{clave.lower().replace(' ', '_')}_{SUFIJO}",
                                   "Descargar lista")

st.write("")
tab_evo, tab_reporte, tab_alumnos = st.tabs(["Evolución", "Reporte del aula (al 24/10)", "Por alumno"])

# ---------------------------------------------------------------------------
# Evolución de los accesos y estado de actividad
# ---------------------------------------------------------------------------
MEDIDAS = {
    "% de la base que entró": ("pct_base_activa", "% de la base", "%{y:.1f} %",
                               "Porcentaje de la base de cada materia que entró en el período, para comparar "
                               "materias aunque tengan distinta cantidad de alumnos."),
    "Sesiones por alumno": ("sesiones_por_alumno", "Sesiones por alumno", "%{y:.2f} sesiones por alumno",
                            "Sesiones del período divididas por el tamaño de la base de cada materia."),
    "Minutos por alumno": ("minutos_por_alumno", "Minutos por alumno", "%{y:.1f} min por alumno",
                           "Minutos de sesión del período divididos por el tamaño de la base de cada materia."),
    "Interacciones por alumno": ("eventos_por_alumno", "Interacciones por alumno",
                                 "%{y:.1f} interacciones por alumno",
                                 "Clics registrados en el período divididos por el tamaño de la base."),
    "Alumnos que entraron": ("alumnos_activos", "Alumnos", "%{y} alumnos", "Cantidad de alumnos que entraron."),
    "Sesiones (total)": ("sesiones", "Sesiones", "%{y} sesiones", "Cantidad total de sesiones."),
    "Interacciones (total)": ("eventos", "Interacciones", "%{y} interacciones", "Cantidad total de clics."),
}
FRECUENCIAS = {"Día": "D", "Semana": "W", "Mes": "M"}

with tab_evo:
    with comp.tarjeta("evolucion"):
        c1, c2, c3 = st.columns([2.2, 1.3, 1.1], vertical_alignment="bottom")
        medida = c2.selectbox("Medida", list(MEDIDAS), key="part_medida",
                              help="Las medidas por alumno y el % de la base dividen por el tamaño de la base de "
                                   "cada materia.")
        frecuencia = c3.segmented_control("Agrupar por", list(FRECUENCIAS), default="Semana",
                                          key="part_frecuencia") or "Semana"
        col, eje, hover, explicacion = MEDIDAS[medida]
        with c1:
            comp.titulo_seccion("Evolución de los accesos", explicacion)

        evo = comp.metrica("evolucion_participacion", frecuencia=FRECUENCIAS[frecuencia], desde=desde)
        fig = px.line(evo, x="periodo", y=col, color="asignatura", markers=frecuencia != "Día",
                      category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                      labels={"periodo": "", col: eje, "asignatura": ""})
        formato_x = {"D": "%d/%m", "W": "sem. del %d/%m", "M": "%m/%Y"}[FRECUENCIAS[frecuencia]]
        fig.update_traces(hovertemplate=f"%{{x|{formato_x}}}<br>%{{fullData.name}}: {hover}<extra></extra>",
                          line_width=2.4, marker_size=6)
        marcar = st.toggle("Marcar evaluaciones", value=True, key="part_marcar",
                           help="Fechas de las evaluaciones: mediana del día en que los alumnos las rindieron.")
        if marcar:
            evals = comp.metrica("fechas_evaluaciones")
            if desde is not None:
                evals = evals[evals["fecha_instrumento"] >= pd.Timestamp(desde)]
            for asig, g in evals.groupby("asignatura"):
                fig.add_trace(go.Scatter(
                    x=g["fecha_instrumento"], y=[0] * len(g), mode="markers",
                    name=f"Evaluación {comp.SIGLAS[asig]}", showlegend=False,
                    marker=dict(symbol="triangle-up", size=11, color=comp.COLORES_MATERIA[asig],
                                line=dict(color="white", width=1)),
                    text=g["instrumento"].str.replace(r"^\W+", "", regex=True),
                    hovertemplate="%{x|%d/%m}: %{text}<extra>" + asig + "</extra>"))
        fig.update_xaxes(tickformat="%d/%m" if FRECUENCIAS[frecuencia] != "M" else "%m/%Y", showgrid=False)
        fig.update_yaxes(rangemode="tozero")
        fig.update_layout(height=320, hovermode="closest", showlegend=False, margin=dict(t=10))
        # Leyenda propia arriba del gráfico (como en el diseño): materias a la izquierda y,
        # a la derecha, qué son los triángulos.
        triangulo = ('<span style="margin-left:auto">'
                     f'<span style="width:0; height:0; border-left:5px solid transparent; border-right:5px solid '
                     f'transparent; border-bottom:9px solid {comp.TEXTO_2}"></span>Evaluación tomada</span>'
                     if marcar else "")
        H('<div class="tfi-leyenda" style="margin-top:4px">' + "".join(
            f'<span>{comp.punto_materia(a)}{a}</span>' for a in f.materias) + triangulo + "</div>")
        comp.grafico(fig)
        unidad = {"D": "El último día", "W": "La última semana", "M": "El último mes"}[FRECUENCIAS[frecuencia]]
        H(comp.nota("<strong>Para leer:</strong> los triángulos son las evaluaciones; los picos de actividad suelen "
                    "caer esa semana. Si las tres materias bajan a la vez, es estacional y no un problema de una "
                    f"cátedra. {unidad} puede estar incompleto: termina en la fecha de corte. Semanas de lunes a "
                    "domingo."))

    c1, c2 = st.columns(2, gap="medium")
    with c1, comp.tarjeta("estado_materia"):
        comp.titulo_seccion("Estado de actividad por materia",
                            "Mismo semáforo que la ficha del alumno, con la cantidad además del porcentaje. "
                            "A la fecha de corte, mirando toda la cursada.")
        bloques = []
        for asig in f.materias:
            g = estado[estado["asignatura"] == asig]
            c = conteo_tramos(g)
            n = len(g) or 1
            seg = [(c[t], comp.COLORES_TRAMO[t], comp.num(c[t])) for t in TRAMOS_ACTIVIDAD]
            pie = " · ".join(f"{comp.pct(c[t] / n * 100, 0)} {NOMBRES[t]}" for t in tramos_visibles
                             if t != SIN_ACTIVIDAD) + f" · {comp.num(c[SIN_ACTIVIDAD])} sin actividad"
            bloques.append(
                f'<div style="margin-top:16px"><p style="display:flex; justify-content:space-between; '
                f'align-items:center; margin-bottom:7px; font:600 12px Inter, sans-serif">{asig}'
                f'<span class="tfi-muted" style="font-weight:400">{comp.num(len(g))} alumnos</span></p>'
                f'{comp.barra_apilada(seg, alto=30, numeros=True)}'
                f'<p class="tfi-muted" style="margin-top:7px">{pie}</p></div>')
        H(f'<div class="tfi">{"".join(bloques)}</div>')
        H(f'<div style="margin-top:14px">{comp.leyenda([(TONO_TRAMO[t], NOMBRES[t].capitalize()) for t in tramos_visibles])}</div>')

    with c2, comp.tarjeta("dias_sin_entrar"):
        comp.titulo_seccion("Hace cuánto que no entran",
                            "Alumnos agrupados por días desde el último ingreso. Los colores son los tramos y la "
                            "línea punteada, el umbral que elegiste en la barra lateral.")
        dias = estado.dropna(subset=["dias_sin_actividad"]).astype({"dias_sin_actividad": int})
        fig = px.histogram(dias, x="dias_sin_actividad", color="tramo_actividad",
                           category_orders={"tramo_actividad": TRAMOS_ACTIVIDAD},
                           color_discrete_map=comp.COLORES_TRAMO,
                           labels={"dias_sin_actividad": "Días desde el último ingreso", "tramo_actividad": ""})
        fig.update_traces(xbins=dict(start=-0.5, size=1), hovertemplate="%{x} días: %{y} alumnos<extra></extra>")
        fig.add_vline(x=f.umbral + 0.5, line_dash="dash", line_color=comp.TEXTO_2, line_width=1.5,
                      annotation_text=f"umbral {f.umbral} d", annotation_position="top right",
                      annotation_font=dict(size=11, color=comp.TEXTO))
        fig.update_layout(height=300, yaxis_title="Alumnos", bargap=0.08, showlegend=False, margin=dict(t=20))
        comp.grafico(fig)
        justo = int(dias["dias_sin_actividad"].between(f.umbral + 1, f.umbral + 3).sum())
        H(comp.nota(f"<strong>Para leer:</strong> {comp.num(justo)} alumnos llevan apenas {f.umbral + 1} a "
                    f"{f.umbral + 3} días sin entrar: muchos son solo una semana floja. La cola larga de la derecha "
                    "ya no se recupera con un recordatorio.", "atencion"))

    with comp.tarjeta("resumen"):
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        with c1:
            comp.titulo_seccion("Resumen por materia",
                                f"Sesiones y minutos del período ({texto_periodo}); avance del reporte al 24/10.")
        with c2:
            comp.boton_csv(resumen, f"resumen_participacion_{SUFIJO}", "Descargar CSV")
        filas = []
        for r in resumen.sort_values("pct_activos", ascending=False).itertuples():
            c = conteo_tramos(estado[estado["asignatura"] == r.asignatura])
            reparto = comp.barra_apilada([(c[t], comp.COLORES_TRAMO[t]) for t in TRAMOS_ACTIVIDAD], alto=12)
            filas.append(
                f"<tr><td><span style='display:inline-flex; align-items:center; gap:8px'>"
                f"{comp.punto_materia(r.asignatura)}<strong>{r.asignatura}</strong></span></td>"
                f"<td class='tfi'>{comp.num(r.alumnos)}</td><td class='tfi'>{comp.pct(r.pct_activos, 0)}</td>"
                f"<td style='min-width:140px'>{reparto}</td>"
                f"<td style='min-width:150px'>{comp.progreso(r.avance_promedio)}</td>"
                f"<td class='tfi' style='white-space:nowrap'>{comp.num(r.sesiones_promedio, 1)} "
                f"<span class='tfi-muted'>· med. {comp.num(r.sesiones_mediana, 0)}</span></td>"
                f"<td class='tfi'>{comp.num(r.minutos_promedio, 0)}</td>"
                f"<td class='tfi'>{comp.pct(r.pct_con_intervencion_foros, 1)}</td></tr>")
        H("<div style='overflow-x:auto'><table class='tfi-tabla'><thead><tr><th>Materia</th><th>Alumnos</th>"
          "<th>Activos</th><th>Reparto del semáforo</th><th>Avance</th><th>Sesiones</th><th>Minutos</th>"
          f"<th>Foros</th></tr></thead><tbody>{''.join(filas)}</tbody></table></div>")
        H(comp.nota("Promedio y mediana juntos a propósito: cuando se separan mucho, un grupo chico de alumnos muy "
                    "activos está inflando el promedio. El CSV trae además interacciones, tiempo de uso del LMS y "
                    "la cantidad de alumnos en cada estado."))

# ---------------------------------------------------------------------------
# Reporte del aula (foto al 24/10, D36)
# ---------------------------------------------------------------------------
with tab_reporte:
    H(comp.nota("Esta pestaña es una <strong>foto al 24/10</strong> que exporta el LMS: no se mueve con la fecha de "
                "corte ni con el período que elijas arriba.", "info"))
    st.write("")

    with comp.tarjeta("avance"):
        av = alumnos.dropna(subset=["avance"])
        c1, c2 = st.columns([3, 1.3], vertical_alignment="top")
        with c1:
            comp.titulo_seccion("Avance en el contenido del aula",
                                "Porcentaje de los recursos del aula que abrió cada alumno. Cada barra son los alumnos "
                                "que caen en ese tramo de 10 puntos; misma escala en todas las materias.")
        with c2:
            H(f'<div style="text-align:right">{comp.chip("La variable que más se relaciona con la nota", "neutro", False)}</div>')
        cols = st.columns(len(f.materias))
        for colu, asig in zip(cols, f.materias):
            g = av[av["asignatura"] == asig]
            with colu:
                H(f'<p style="display:flex; align-items:center; gap:8px; font:600 12px Inter, sans-serif">'
                  f'{comp.punto_materia(asig)}{asig}</p>')
                fig = px.histogram(g, x="avance", color_discrete_sequence=[comp.COLORES_MATERIA[asig]])
                fig.update_traces(xbins=dict(start=0, end=100.001, size=10),
                                  hovertemplate="Avance %{x} %: %{y} alumnos<extra></extra>")
                fig.update_xaxes(range=[-3, 103], title=None, tickvals=[0, 50, 100], ticktext=["0 %", "50 %", "100 %"],
                                 showgrid=False)
                fig.update_yaxes(title=None)
                fig.update_layout(height=190, bargap=0.08, margin=dict(t=8, b=0))
                comp.grafico(fig, key=f"avance_{asig}")
                if len(g):
                    st.caption(f"Mediana {comp.pct(g['avance'].median(), 0)} · "
                               f"{comp.pct((g['avance'] >= 80).mean() * 100, 0)} pasó el 80 % · "
                               f"{comp.num((g['avance'] == 0).sum())} en 0")
        sin_avance = av[av["avance"] == 0]
        if len(sin_avance):
            H(comp.nota(f"<strong>{comp.num(len(sin_avance))} alumnos tienen avance 0:</strong> no abrieron ni un "
                        "recurso del aula. Son el grupo con el que conviene empezar.", "critico"))
            with st.popover(f"Ver esos {comp.num(len(sin_avance))} alumnos"):
                st.dataframe(sin_avance.assign(materia=sin_avance["asignatura"].map(comp.SIGLAS))
                             [["nombre_completo", "id_alumno", "materia", "inscripto"]],
                             hide_index=True, width="stretch",
                             column_config={"nombre_completo": "Alumno", "id_alumno": "ID", "materia": "Materia",
                                            "inscripto": st.column_config.CheckboxColumn("Inscripto")})

    with comp.tarjeta("herramientas"):
        comp.titulo_seccion("Uso de las herramientas del aula",
                            "Una fila por herramienta y una columna por materia: qué porcentaje de alumnos la usó al "
                            "menos una vez. Donde la cátedra no publicó nada se dice, en vez de dibujar una barra en 0.")
        herr = comp.metrica("uso_herramientas")
        filas = []
        for nombre, g in herr.groupby("herramienta", sort=False):
            g = g.set_index("asignatura")
            if g["recursos"].isna().all():
                sub = "siempre disponible"
            else:
                pub = [f"{int(r)} en {comp.SIGLAS[a]}" for a, r in g["recursos"].items() if pd.notna(r) and r > 0]
                sub = "publicados: " + ", ".join(pub) if pub else "nada publicado"
            celdas = []
            for asig in f.materias:
                if asig not in g.index:
                    celdas.append(f"<td class='tfi-muted'>{comp.VACIO}</td>")
                    continue
                r = g.loc[asig]
                if pd.notna(r["recursos"]) and r["recursos"] == 0:
                    celdas.append("<td class='tfi-muted'>Sin publicar</td>")
                else:
                    celdas.append(f"<td style='min-width:150px'>{comp.progreso(r['pct_alumnos'], comp.COLORES_MATERIA[asig])}"
                                  f"<span class='tfi-muted'>{comp.num(r['alumnos'])} alumnos · "
                                  f"{comp.num(r['usos'])} usos</span></td>")
            filas.append(f"<tr><td><strong>{nombre}</strong><br><span class='tfi-muted'>{sub}</span></td>"
                         f"{''.join(celdas)}</tr>")
        cabecera = "".join(f"<th>{a}</th>" for a in f.materias)
        H(f"<div style='overflow-x:auto'><table class='tfi-tabla'><thead><tr><th>Herramienta</th>{cabecera}</tr>"
          f"</thead><tbody>{''.join(filas)}</tbody></table></div>")

        def y_ni(palabras) -> str:
            """['encuestas', 'archivos', 'wikis'] -> 'encuestas, archivos ni wikis'."""
            palabras = list(palabras)
            return palabras[0] if len(palabras) == 1 else ", ".join(palabras[:-1]) + " ni " + palabras[-1]

        maximo = herr.loc[herr["pct_alumnos"].idxmax()] if not herr.empty else None
        if maximo is not None and maximo["pct_alumnos"] < 25:
            con_foros = herr[(herr["herramienta"] == "Foros") & (herr["recursos"].fillna(0) > 0)]
            sin_recursos = [h for h, g in herr.groupby("herramienta", sort=False)
                            if g["recursos"].notna().all() and (g["recursos"] == 0).all()]
            texto_foros = (" De foros, solo publicó " + ", ".join(comp.SIGLAS[a] for a in con_foros["asignatura"])
                           + "." if not con_foros.empty else " Ninguna materia publicó foros.")
            H(comp.nota(f"<strong>La participación activa no se puede medir hoy.</strong> La herramienta más usada es "
                        f"{maximo['herramienta'].lower()} y llega al {comp.pct(maximo['pct_alumnos'])} en "
                        f"{comp.SIGLAS[maximo['asignatura']]}.{texto_foros}"
                        + (f" No hay {y_ni(h.lower() for h in sin_recursos)} publicados en ninguna materia."
                           if sin_recursos else "")
                        + " Mientras no haya consignas en foros o encuestas, la participación se mide por accesos y "
                          "avance, no por intervenciones.", "atencion"))

    with comp.tarjeta("control"):
        conc = comp.metrica("concordancia_tiempo")
        coinciden = not conc.empty and (conc["rho"] >= 0.9).all()
        c1, c2 = st.columns([3, 1.3])
        with c1:
            comp.titulo_seccion("Control de calidad del dato",
                                "Los minutos que calculamos armando sesiones con la trazabilidad, contra el tiempo de "
                                "uso que informa el LMS. Cada punto es un alumno; la línea punteada es la igualdad.")
        with c2:
            H(f'<div style="text-align:right">'
              f'{comp.chip("Las dos fuentes coinciden" if coinciden else "Revisar: no coinciden del todo", "bien" if coinciden else "atencion")}'
              f'</div>')
        control = comp.metrica("participacion_alumnos", fecha_corte=comp.DEFECTOS["fecha_corte"])
        g1, g2 = st.columns([2.2, 1], gap="medium")
        with g1:
            fig = px.scatter(control.dropna(subset=["tiempo_uso_min"]), x="tiempo_uso_min", y="minutos",
                             color="asignatura", category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                             hover_name="nombre_completo", opacity=0.75,
                             labels={"tiempo_uso_min": "Minutos informados por el LMS",
                                     "minutos": "Minutos según las sesiones", "asignatura": ""})
            fig.update_traces(marker_size=6, hovertemplate="%{hovertext}<br>LMS: %{x} min · Sesiones: %{y:.0f} min"
                                                           "<extra></extra>")
            tope = float(max(control["tiempo_uso_min"].max(), control["minutos"].max()))
            fig.add_trace(go.Scatter(x=[0, tope], y=[0, tope], mode="lines", name="Iguales",
                                     line=dict(color="#A8A49B", dash="dash", width=1.4), hoverinfo="skip"))
            fig.update_layout(height=340, showlegend=False, margin=dict(t=10))  # los colores, en la lista de al lado
            comp.grafico(fig)
        with g2:
            filas = "".join(
                f'<div style="display:grid; grid-template-columns:16px 1fr auto; gap:4px 10px; align-items:center; '
                f'padding:12px 0; border-bottom:1px solid {comp.BORDE_SUAVE}">{comp.punto_materia(r.asignatura)}'
                f'<span style="font:600 13px Inter, sans-serif">{r.asignatura}</span>'
                f'<span class="tfi-num" style="font-size:18px">{comp.num(r.rho, 3)}</span><span></span>'
                f'<span class="tfi-muted" style="grid-column:2 / 4">las sesiones suman el '
                f'{comp.pct(r.minutos_total / r.tiempo_uso_total * 100, 0)} del tiempo del LMS</span></div>'
                for r in conc.sort_values("rho", ascending=False).itertuples())
            H(f'<div class="tfi">{comp.etiqueta("Correlación de Spearman")}{filas}</div>')
        H(comp.nota("Que el orden de los alumnos sea casi el mismo en las dos fuentes valida cómo armamos las sesiones "
                    "(se cortan a los 30 minutos sin eventos). Los minutos propios quedan por debajo porque no "
                    "cuentan el rato posterior al último clic: es esperable, no un error."))

# ---------------------------------------------------------------------------
# Por alumno
# ---------------------------------------------------------------------------
# Estado y último ingreso a la fecha de corte (toda la cursada); sesiones, minutos
# y demás, del período.
COLS_ESTADO = ["estado_actividad", "tramo_actividad", "activo", "dias_sin_actividad", "ultima_interaccion"]
por_alumno = alumnos.drop(columns=COLS_ESTADO).merge(estado[["asignatura", "id_alumno", *COLS_ESTADO]], how="left")

with tab_alumnos:
    with comp.tarjeta("tabla_alumnos"):
        OPCIONES_TRAMO = {t: f"{comp.ICONOS_TRAMO[t]} {t} ({RANGOS[t]})" for t in tramos_visibles}
        c1, c2, c3, c4 = st.columns([1.6, 1.6, 1, 1], vertical_alignment="bottom")
        tramos = c1.multiselect("Estado de actividad", list(OPCIONES_TRAMO), key="part_estados",
                                placeholder="Todos", format_func=OPCIONES_TRAMO.get)
        texto = c2.text_input("Buscar alumno", key="part_buscar", placeholder="Apellido, nombre o ID")
        vista = por_alumno
        if tramos:
            vista = vista[vista["tramo_actividad"].isin(tramos)]
        if texto.strip():
            buscado = vista["nombre_completo"].fillna("") + " " + vista["id_alumno"]
            vista = vista[buscado.str.contains(texto.strip(), case=False, regex=False)]

        PRINCIPALES = {"nombre_completo": "Alumno", "id_alumno": "ID", "asignatura": "Materia",
                       "tramo_actividad": "Actividad", "dias_sin_actividad": "Sin entrar",
                       "ultima_interaccion": "Último ingreso", "sesiones": "Sesiones", "minutos": "Minutos",
                       "avance": "Avance al 24/10", "inscripto": "Inscripto"}
        EXTRA = {"eventos": "Interacciones", "dias_activos": "Días activos", "semanas_activas": "Semanas activas",
                 "tiempo_uso_min": "Tiempo de uso LMS (al 24/10)", "intervenciones_foros": "Foros",
                 "encuestas_respondidas": "Encuestas", "emails_enviados": "Correos"}
        if f.asignatura:
            PRINCIPALES.pop("asignatura")
        with c3.popover(f"Columnas · {len(PRINCIPALES)}+", width="stretch"):
            extra = st.multiselect("Agregar columnas", list(EXTRA), format_func=EXTRA.get, key="part_columnas")
        columnas = {**PRINCIPALES, **{k: EXTRA[k] for k in extra}}
        tabla = vista.assign(
            tramo_actividad=comp.con_icono(vista["tramo_actividad"], comp.ICONOS_TRAMO),
            asignatura=vista["asignatura"].map(comp.SIGLAS))[list(columnas)].rename(columns=columnas)
        with c4:
            comp.boton_csv(vista[["asignatura", *[c for c in columnas if c != "asignatura"]]]
                           .rename(columns={"asignatura": "Materia", **columnas}),
                           f"participacion_alumnos_{SUFIJO}", "Descargar lista")
        st.dataframe(tabla, hide_index=True, width="stretch", height=420, column_config={
            "Sin entrar": st.column_config.NumberColumn(format="%d d"),
            "Último ingreso": st.column_config.DatetimeColumn(format="DD/MM HH:mm"),
            "Minutos": st.column_config.NumberColumn(format="%.0f"),
            "Avance al 24/10": st.column_config.ProgressColumn(format="%d %%", min_value=0, max_value=100),
            "Inscripto": st.column_config.CheckboxColumn()})
        st.caption(f"{comp.num(len(vista))} de {comp.num(len(alumnos))} alumnos. Actividad, días sin entrar y "
                   f"último ingreso, a la fecha de corte; sesiones, minutos e interacciones, del período "
                   f"({texto_periodo}); avance y lo que dice «al 24/10», del reporte del LMS.")

    with comp.tarjeta("un_alumno"):
        comp.titulo_seccion("Actividad de un alumno",
                            "Sus interacciones por semana contra el promedio de su materia. La ficha completa, con "
                            "notas, está en Ficha individual.")
        if vista.empty:
            st.info("No hay alumnos con esos filtros.", icon=":material/search_off:")
        else:
            opciones = list(vista.index)
            elegido = st.selectbox(
                "Alumno", opciones, key="part_alumno",
                format_func=lambda i: f"{vista.at[i, 'nombre_completo']} ({vista.at[i, 'id_alumno']}) · "
                                      f"{comp.SIGLAS[vista.at[i, 'asignatura']]}")
            fila = vista.loc[elegido]
            dias_txt = ("nunca entró" if pd.isna(fila["dias_sin_actividad"])
                        else f"último ingreso hace {int(fila['dias_sin_actividad'])} d "
                             f"({comp.fmt_fecha(fila['ultima_interaccion'], '%d/%m')})")
            H(f'<div class="tfi" style="display:flex; flex-wrap:wrap; align-items:center; gap:10px">'
              f'{comp.etiqueta_materia(fila["asignatura"])}{comp.chip_estado(fila["tramo_actividad"])}'
              f'<span class="tfi-muted" style="font-size:12px">{dias_txt}</span></div>')
            comp.tarjetas([
                ("Sesiones", comp.num(fila["sesiones"])),
                ("Minutos", comp.num(fila["minutos"])),
                ("Semanas activas", comp.num(fila["semanas_activas"])),
                ("Avance al 24/10", comp.pct(fila["avance"], 0)),
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
                fig.add_trace(go.Scatter(x=materia["periodo"], y=materia["eventos_por_alumno"],
                                         mode="lines+markers", name=f"Promedio de {comp.SIGLAS[fila['asignatura']]}",
                                         line=dict(color=comp.TEXTO_2, width=2, dash="dot"),
                                         hovertemplate="sem. del %{x|%d/%m}: %{y:.1f} por alumno<extra></extra>"))
                fig.update_xaxes(tickformat="%d/%m", showgrid=False)
                fig.update_layout(height=320, yaxis_title="Interacciones por semana", bargap=0.25)
                comp.grafico(fig)
                H(comp.nota("Semanas en 0 seguidas al final son la señal típica de abandono."))
