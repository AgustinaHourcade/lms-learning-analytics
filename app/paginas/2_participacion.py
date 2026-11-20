"""Dashboard 2 (del plan): Participación.

Responde: ¿cuántos alumnos siguen entrando al aula?, ¿quiénes se están yendo y en
qué materia? y ¿cómo viene cada alumno?

  Período         filtro propio de la página (toda la cursada, últimas 4 o 2
                  semanas o desde una fecha) que termina en la fecha de corte (D53).
                  Recorta sesiones, minutos, la evolución y la tabla por alumno.
  Hero            quién sigue entrando a la fecha de corte, en cuatro tramos: activo,
                  enfriándose, desconectado y sin actividad (D35, D54), con la lista de
                  los que se están enfriando. Mira toda la cursada, no el período.
  KPIs            sesiones y minutos por alumno por semana (período, con Δ contra el
                  período anterior de igual duración), avance (foto del LMS, D36) y
                  retención semanal (al corte).
  Evolución       % de la base que entró por semana (o día / mes, u otras medidas).
  Estado          tramos por materia (con ritmo y regularidad) y días sin entrar.
  Por alumno      tabla filtrable con CSV y la evolución semanal de un alumno contra
                  el promedio de su materia, en cada materia que cursa.
  Herramientas    foto del LMS (D36): avance en el contenido y uso de herramientas.

El control de calidad de las sesiones contra el tiempo del LMS (D25) ya no se dibuja:
está en analysis/validacion_sesiones.py, que guarda el gráfico y los ρ en reports/.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
import unicodedata
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes_participacion as comp
from src.config import DIAS_DESCONECTADO
from src.metricas import ACTIVO, DESCONECTADO, ENFRIANDOSE, SIN_ACTIVIDAD, TODAS_LAS_MATERIAS, TRAMOS_ACTIVIDAD
from src.textos import enumerar

f = comp.encabezado("Participación", "Quién sigue entrando, quién se está yendo y en qué materia.")

ORDEN = {"asignatura": list(comp.COLORES_MATERIA)}
TONO_TRAMO = {t: comp.TONO_ESTADO[t] for t in TRAMOS_ACTIVIDAD}
H = comp.html
PAG_NOTAS = "paginas/5_notas_vs_participacion.py"
PAG_FICHA = "paginas/6_ficha_individual.py"

# Fecha del reporte de participación del LMS (foto): avance y herramientas (D36, D76).
fecha_foto = comp.metrica("fecha_reporte_participacion") or pd.Timestamp(comp.DEFECTOS["fecha_corte"])
FOTO = comp.fmt_fecha(fecha_foto, "%d/%m")
corte_es_foto = pd.Timestamp(f.fecha_corte) == pd.Timestamp(fecha_foto).normalize()

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
dias_periodo = (f.fecha_corte - desde_real).days + 1
c3.caption(f"{comp.fmt_fecha(desde_real, '%d/%m')} → {comp.fmt_fecha(f.fecha_corte, '%d/%m')} · "
           f"{comp.num(dias_periodo / 7, 0)} semanas")
SUFIJO = f"{desde_real:%Y%m%d}_{f.fecha_corte:%Y%m%d}"

alumnos = comp.metrica("participacion_alumnos", desde=desde)   # números del período
estado = comp.metrica("participacion_alumnos")                 # estado a la fecha de corte (toda la cursada)
ritmo = comp.metrica("ritmo_semanal", desde=desde).set_index("asignatura")

# Período anterior de igual duración (para los Δ). Solo si entra entero en los datos.
ritmo_antes = None
if desde is not None:
    desde_antes = desde_real - timedelta(days=dias_periodo)
    if desde_antes >= inicio_datos:
        ritmo_antes = comp.metrica("ritmo_semanal", fecha_corte=desde_real - timedelta(days=1),
                                   desde=desde_antes).set_index("asignatura")

# Los rangos de días de cada tramo, para los textos (dependen del umbral elegido).
lim = max(DIAS_DESCONECTADO, f.umbral)
RANGOS = {ACTIVO: f"hasta {f.umbral} días", ENFRIANDOSE: f"{f.umbral + 1} a {lim} días",
          DESCONECTADO: f"{lim + 1} días o más", SIN_ACTIVIDAD: "nunca entraron"}
NOMBRES = {ACTIVO: "activos", ENFRIANDOSE: "enfriándose", DESCONECTADO: "desconectados",
           SIN_ACTIVIDAD: "sin actividad"}
tramos_visibles = [t for t in TRAMOS_ACTIVIDAD if not (t == ENFRIANDOSE and f.umbral >= DIAS_DESCONECTADO)]


def conteo_tramos(df: pd.DataFrame) -> pd.Series:
    return df["tramo_actividad"].value_counts().reindex(TRAMOS_ACTIVIDAD, fill_value=0)


def con_signo(x: float, decimales: int = 0) -> str:
    """+3 / −2 / ±0, con la coma decimal de la app."""
    redondeado = round(x, decimales)
    signo = "+" if redondeado > 0 else "−" if redondeado < 0 else "±"
    return f"{signo}{comp.num(abs(redondeado), decimales)}"


def chip_delta(dif: float, unidad: str = "pts", decimales: int = 0) -> str:
    tono = "bien" if round(dif, decimales) > 0 else "critico" if round(dif, decimales) < 0 else "neutro"
    return comp.chip(f"{con_signo(dif, decimales)} {unidad}".strip(), tono, False)


def lista_alumnos(df: pd.DataFrame, nombre_csv: str) -> None:
    """Tabla chica (alumno, materia, días sin entrar, último ingreso) con su CSV."""
    lista = df.assign(materia=df["asignatura"].map(comp.SIGLAS))
    st.dataframe(lista[["nombre_completo", "id_alumno", "materia", "dias_sin_actividad", "ultima_interaccion"]],
                 hide_index=True, width="stretch", column_config={
                     "nombre_completo": "Alumno", "id_alumno": "ID", "materia": "Materia",
                     "dias_sin_actividad": st.column_config.NumberColumn("Sin entrar", format="%d d"),
                     "ultima_interaccion": st.column_config.DatetimeColumn("Último ingreso", format="DD/MM HH:mm")})
    comp.boton_csv(lista[["asignatura", "id_alumno", "nombre_completo", "dias_sin_actividad", "ultima_interaccion",
                          "inscripto"]], f"{nombre_csv}_{SUFIJO}", "Descargar lista")


# ---------------------------------------------------------------------------
# Hero: quién sigue entrando + 4 KPIs
# ---------------------------------------------------------------------------
n_base = len(estado)
cuenta = conteo_tramos(estado)
pct_activos = cuenta[ACTIVO] / n_base * 100 if n_base else np.nan

# Δ: el mismo % de activos (ventana móvil de `umbral` días) medido 7 días antes.
corte_anterior = f.fecha_corte - timedelta(days=7)
delta_hero = ""
if corte_anterior >= inicio_datos and n_base:
    antes = comp.metrica("actividad_alumnos", fecha_corte=corte_anterior)
    dif = pct_activos - antes["activo"].mean() * 100
    delta_hero = (f'{chip_delta(dif)}<span class="pa-sub" style="font-size:13px">vs. 7 días antes</span>')

# Referencia fija: el mismo % al cierre de la semana 2 de la cursada.
cierre_s2 = inicio_datos + timedelta(days=13)
referencia_s2 = ""
if f.fecha_corte >= cierre_s2 and n_base:
    s2 = comp.metrica("actividad_alumnos", fecha_corte=cierre_s2)
    referencia_s2 = (f'<p class="pa-muted" style="font-size:12px; margin:6px 0 0">vs. {comp.pct(s2["activo"].mean() * 100, 0)} '
                     f'al cierre de la semana 2 ({comp.fmt_fecha(cierre_s2, "%d/%m")})</p>')

col_titular, col_kpis = st.columns([1.3, 1], gap="medium")
with col_titular, comp.tarjeta("titular"):
    segmentos = [(cuenta[t], comp.COLORES_TRAMO[t]) for t in TRAMOS_ACTIVIDAD]
    items = [(TONO_TRAMO[t], f'<b>{comp.num(cuenta[t])}</b> {NOMBRES[t]} · {RANGOS[t]}') for t in tramos_visibles]
    lectura = (f"<b>{comp.num(cuenta[ENFRIANDOSE])}</b> todavía se recuperan con un mensaje; "
               f"<b>{comp.num(cuenta[DESCONECTADO])}</b> necesitan otro contacto."
               if f.umbral < DIAS_DESCONECTADO else
               f"Con un umbral de {f.umbral} días, todos los inactivos llevan más de {DIAS_DESCONECTADO} días "
               f"sin entrar: los <b>{comp.num(cuenta[DESCONECTADO])}</b> necesitan otro contacto.")
    H(f"""<div class="pa">
      <div style="margin-bottom:10px">{comp.etiqueta(f"Quién sigue entrando · al {comp.fmt_fecha(f.fecha_corte, '%d/%m')}")}</div>
      <div style="display:flex; align-items:center; gap:14px; flex-wrap:wrap">
        <span class="pa-big">{comp.pct(pct_activos, 0)}</span>
        <span style="display:inline-flex; align-items:center; gap:8px">{delta_hero}</span>
      </div>
      <p class="pa-sub" style="margin-top:8px">{comp.num(cuenta[ACTIVO])} de {comp.num(n_base)} entraron en los
        últimos {f.umbral} días</p>
      {referencia_s2}
      <div style="margin:16px 0 10px">{comp.barra_apilada(segmentos, alto=28)}</div>
      {comp.leyenda(items)}
      <p class="pa-desc" style="margin-top:12px; font-size:13px">{lectura}</p>
    </div>""")
    enfriandose = estado[estado["tramo_actividad"] == ENFRIANDOSE].sort_values("dias_sin_actividad")
    if len(enfriandose):
        with st.popover(f"Ver los {comp.num(len(enfriandose))} para contactarlos"):
            lista_alumnos(enfriandose, "enfriandose")

# --- KPIs ------------------------------------------------------------------
TODAS_R = TODAS_LAS_MATERIAS


def kpi(etiqueta: str, chip: str, valor: str, secundario: str, delta: float | None = None, decimales: int = 0,
        unidad_delta: str = "", contra: str = "", ayuda: str = "", atenuada: bool = False, aviso: str = "") -> str:
    """HTML de una tarjeta KPI: etiqueta y chip de base temporal arriba, el valor grande y abajo el Δ
    (con color y signo) junto a la línea secundaria. La ayuda aparece al pasar por el ícono (i)."""
    icono = (f'<span class="pa-ayuda" tabindex="0" role="img" aria-label="{ayuda}" data-tip="{ayuda}">?</span>'
             if ayuda else "")
    linea_delta = ""
    if delta is not None and pd.notna(delta):
        r = round(delta, decimales)
        tono = "bien" if r > 0 else "critico" if r < 0 else "neutro"
        linea_delta = (f'<p class="pa-kpi-delta"><span style="color:{comp.TONOS[tono]["texto"]}">'
                       f'{con_signo(delta, decimales)}{(" " + unidad_delta) if unidad_delta else ""}</span> {contra}</p>')
    aviso_html = f'<span class="pa-kpi-aviso">{aviso}</span>' if aviso else ""
    return (f'<div class="pa pa-kpi{" pa-kpi-atenuada" if atenuada else ""}">'
            f'<div class="pa-kpi-cab"><span class="pa-chip-sm">{chip}</span>{icono}</div>'
            f'<p class="pa-kpi-label">{etiqueta}</p>'
            f'<p class="pa-kpi-valor">{valor}</p>'
            f'<div class="pa-kpi-pie">{linea_delta}<p class="pa-kpi-sec">{secundario}{aviso_html}</p></div></div>')


def delta_ritmo(col: str) -> float | None:
    if ritmo_antes is None or TODAS_R not in ritmo_antes.index:
        return None
    return ritmo.at[TODAS_R, col] - ritmo_antes.at[TODAS_R, col]


reten = comp.metrica("retencion_semanal").set_index("asignatura")
reten_antes = comp.metrica("retencion_semanal", fecha_corte=corte_anterior).set_index("asignatura")
avance = estado["avance"].astype(float)
valor_ret = reten.at[TODAS_R, "retencion"]
previas = f"vs. {comp.num(dias_periodo / 7, 0)} semanas previas"

with col_kpis:
    H('<div class="pa-kpis">' + "".join([
        kpi("Sesiones por alumno por semana", "Período", comp.num(ritmo.at[TODAS_R, "sesiones_semana"], 1),
            f"mediana {comp.num(ritmo.at[TODAS_R, 'sesiones_semana_mediana'], 1)}",
            delta_ritmo("sesiones_semana"), 1, contra=previas,
            ayuda="Sesiones del período / alumnos de la base / semanas del período (días / 7). Incluye a los que "
                  "no entraron. Una sesión es una tanda de eventos sin pausas de más de 30 minutos. El Δ compara "
                  "con el período anterior de igual duración."),
        kpi("Minutos por alumno por semana", "Período", comp.num(ritmo.at[TODAS_R, "minutos_semana"], 0),
            f"mediana {comp.num(ritmo.at[TODAS_R, 'minutos_semana_mediana'], 0)}",
            delta_ritmo("minutos_semana"), 0, contra=previas,
            ayuda="Minutos de sesión del período / alumnos de la base / semanas del período. El Δ compara con el "
                  "período anterior de igual duración."),
        kpi("Avance promedio", f"Foto LMS {FOTO}", comp.pct(avance.mean(), 0),
            f"mediana {comp.pct(avance.median(), 0)}",
            ayuda=f"Del reporte de participación del LMS: % de los recursos del aula que abrió el alumno. Es una "
                  f"foto al {FOTO}: no cambia con la fecha de corte ni con el período.",
            atenuada=not corte_es_foto, aviso="" if corte_es_foto else f"Dato al {FOTO}"),
        kpi("Retención semanal", "Al corte", comp.pct(valor_ret, 0),
            f"{comp.num(reten.at[TODAS_R, 'volvieron'])} de "
            f"{comp.num(reten.at[TODAS_R, 'activos_semana_anterior'])} volvieron",
            valor_ret - reten_antes.at[TODAS_R, "retencion"], 0, "pts", "vs. 7 días antes",
            ayuda="De los que entraron la semana anterior, qué % volvió a entrar esta semana."),
    ]) + "</div>")

# ---------------------------------------------------------------------------
# Evolución de los accesos (a ancho completo)
# ---------------------------------------------------------------------------
MEDIDAS = {
    "% de la base que entró": ("pct_base_activa", "% de la base", "%{y:.1f} %", None),
    "Sesiones por alumno": ("sesiones_por_alumno", "Sesiones por alumno", "%{y:.2f} sesiones por alumno",
                            "Sesiones divididas por el tamaño de la base de cada materia."),
    "Minutos por alumno": ("minutos_por_alumno", "Minutos por alumno", "%{y:.1f} min por alumno",
                           "Minutos de sesión divididos por el tamaño de la base de cada materia."),
    "Interacciones por alumno": ("eventos_por_alumno", "Interacciones por alumno",
                                 "%{y:.1f} interacciones por alumno",
                                 "Clics registrados divididos por el tamaño de la base de cada materia."),
    "Alumnos que entraron": ("alumnos_activos", "Alumnos", "%{y} alumnos", "Cantidad de alumnos que entraron."),
    "Sesiones (total)": ("sesiones", "Sesiones", "%{y} sesiones", "Cantidad total de sesiones."),
    "Interacciones (total)": ("eventos", "Interacciones", "%{y} interacciones", "Cantidad total de clics."),
}
FRECUENCIAS = {"Día": "D", "Semana": "W", "Mes": "M"}
UNIDAD = {"D": "en el día", "W": "en la semana", "M": "en el mes"}

# Título: con semanas completas, si la última quedó 10 pts o más debajo del máximo.
semanal = comp.metrica("acceso_semanal", desde=desde)
completas = semanal[semanal["completa"] & semanal["pct"].notna()]
titulo_evo = "Evolución de los accesos"
if len(completas) >= 2:
    pico, ultima = completas.loc[completas["pct"].idxmax()], completas.iloc[-1]
    if pico["pct"] - ultima["pct"] >= 10:
        titulo_evo = (f"El acceso semanal cayó de {comp.pct(pico['pct'], 0)} a {comp.pct(ultima['pct'], 0)} "
                      f"desde la semana del {comp.fmt_fecha(pico['periodo'], '%d/%m')}")

with comp.tarjeta("evolucion"):
    c1, c2, c3 = st.columns([2.4, 1.3, 1.1], vertical_alignment="bottom")
    medida = c2.selectbox("Medida", list(MEDIDAS), key="part_medida",
                          help="Las medidas por alumno y el % de la base dividen por el tamaño de la base de "
                               "cada materia.")
    frecuencia = c3.segmented_control("Agrupar por", list(FRECUENCIAS), default="Semana",
                                      key="part_frecuencia") or "Semana"
    frec = FRECUENCIAS[frecuencia]
    col, eje, hover, explicacion = MEDIDAS[medida]
    with c1:
        comp.titulo_seccion(titulo_evo, explicacion or
                            f"% de los alumnos de cada materia que entró al menos una vez {UNIDAD[frec]}.")

    evo = comp.metrica("evolucion_participacion", frecuencia=frec, desde=desde)
    fig = px.line(evo, x="periodo", y=col, color="asignatura", markers=frec != "D",
                  category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                  labels={"periodo": "", col: eje, "asignatura": ""})
    formato_x = {"D": "%d/%m", "W": "sem. del %d/%m", "M": "%m/%Y"}[frec]
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
    fig.update_xaxes(tickformat="%d/%m" if frec != "M" else "%m/%Y", showgrid=False)
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(height=320, hovermode="closest", showlegend=False, margin=dict(t=10))
    triangulo = ('<span style="margin-left:auto; display:inline-flex; align-items:center; gap:6px">'
                 f'<span style="width:0; height:0; border-left:5px solid transparent; border-right:5px solid '
                 f'transparent; border-bottom:9px solid {comp.TEXTO_2}"></span>Evaluación tomada</span>'
                 if marcar else "")
    H('<div class="pa pa-leyenda" style="margin-top:4px">' + "".join(
        f'<span>{comp.punto_materia(a)}{a}</span>' for a in f.materias) + triangulo + "</div>")
    comp.grafico(fig)
    corte_ts = pd.Timestamp(f.fecha_corte)
    parcial = {"D": "", "W": "Última semana parcial" if corte_ts.day_of_week != 6 else "",
               "M": "Último mes parcial" if not corte_ts.is_month_end else ""}[frec]
    pie = (f"{parcial} (hasta el {comp.fmt_fecha(f.fecha_corte, '%d/%m')}). " if parcial else "")
    if frec == "W":
        pie += "Semanas de lunes a domingo."
    if pie:
        st.caption(pie)

# ---------------------------------------------------------------------------
# Estado por materia y días sin entrar
# ---------------------------------------------------------------------------
c1, c2 = st.columns(2, gap="medium")
with c1, comp.tarjeta("estado_materia"):
    pct_desc = {a: (g["tramo_actividad"] == DESCONECTADO).mean() * 100
                for a, g in estado.groupby("asignatura") if len(g)}
    if f.asignatura is None and pct_desc:
        peor = max(pct_desc, key=pct_desc.get)
        titulo_estado = f"{peor} tiene la mayor proporción de desconectados ({comp.pct(pct_desc[peor], 0)})"
    elif pct_desc:
        titulo_estado = f"{comp.pct(next(iter(pct_desc.values())), 0)} de desconectados en {f.asignatura}"
    else:
        titulo_estado = "Estado de actividad por materia"
    comp.titulo_seccion(titulo_estado, "Alumnos por estado al corte.")
    bloques = []
    for asig in f.materias:
        g = estado[estado["asignatura"] == asig]
        c = conteo_tramos(g)
        n = len(g) or 1
        seg = [(c[t], comp.COLORES_TRAMO[t], comp.num(c[t])) for t in TRAMOS_ACTIVIDAD]
        pie = " · ".join(f"{comp.pct(c[t] / n * 100, 0)} {NOMBRES[t]}" for t in tramos_visibles
                         if t != SIN_ACTIVIDAD) + f" · {comp.num(c[SIN_ACTIVIDAD])} sin actividad"
        r = ritmo.loc[asig] if asig in ritmo.index else None
        mediana_sem = r["semanas_activas_mediana"] if r is not None else np.nan
        detalle = (f"{comp.num(len(g))} alumnos · {comp.num(r['sesiones_semana'], 1)} sesiones/sem · "
                   f"{comp.num(mediana_sem, 0 if pd.isna(mediana_sem) or mediana_sem % 1 == 0 else 1)} de "
                   f"{comp.num(r['semanas_periodo'])} semanas activas" if r is not None else
                   f"{comp.num(len(g))} alumnos")
        bloques.append(
            f'<div style="margin-top:16px"><p style="display:flex; justify-content:space-between; flex-wrap:wrap; '
            f'gap:4px 12px; align-items:center; margin-bottom:7px; font:600 12px Inter, sans-serif">{asig}'
            f'<span class="pa-muted" style="font-weight:400">{detalle}</span></p>'
            f'{comp.barra_apilada(seg, alto=30, numeros=True)}'
            f'<p class="pa-muted" style="margin-top:7px">{pie}</p></div>')
    H(f'<div class="pa">{"".join(bloques)}</div>')
    H(f'<div class="pa" style="margin-top:14px">'
      f'{comp.leyenda([(TONO_TRAMO[t], NOMBRES[t].capitalize()) for t in tramos_visibles])}</div>')
    st.caption("Sesiones/sem: promedio por alumno en el período. Semanas activas: mediana de semanas con al menos "
               "un ingreso, sobre las semanas del período.")

with c2, comp.tarjeta("dias_sin_entrar"):
    dias = estado.dropna(subset=["dias_sin_actividad"]).astype({"dias_sin_actividad": int})
    justo = int(dias["dias_sin_actividad"].between(f.umbral + 1, f.umbral + 3).sum())
    comp.titulo_seccion(f"{comp.num(justo)} alumnos llevan apenas {f.umbral + 1}–{f.umbral + 3} días sin entrar: "
                        "los más fáciles de recuperar",
                        "Días desde el último ingreso. Línea: umbral de inactividad.")
    fig = px.histogram(dias, x="dias_sin_actividad", color="tramo_actividad",
                       category_orders={"tramo_actividad": TRAMOS_ACTIVIDAD},
                       color_discrete_map=comp.COLORES_TRAMO,
                       labels={"dias_sin_actividad": "Días desde el último ingreso", "tramo_actividad": ""})
    fig.update_traces(xbins=dict(start=-0.5, size=1), hovertemplate="%{x} días: %{y} alumnos<extra></extra>")
    fig.add_vline(x=f.umbral + 0.5, line_dash="dash", line_color=comp.TEXTO_2, line_width=1.5,
                  annotation_text=f"umbral {f.umbral} d", annotation_position="top right",
                  annotation_font=dict(size=11, color=comp.TEXTO))
    fig.update_layout(height=330, yaxis_title="Alumnos", bargap=0.08, showlegend=False, margin=dict(t=20))
    comp.grafico(fig)

st.write("")
tab_alumnos, tab_foto = st.tabs(["Por alumno", f"Herramientas del aula (foto {FOTO})"])

# ---------------------------------------------------------------------------
# Por alumno
# ---------------------------------------------------------------------------
# Estado y último ingreso a la fecha de corte (toda la cursada); sesiones, minutos
# y demás, del período.
COLS_ESTADO = ["estado_actividad", "tramo_actividad", "activo", "dias_sin_actividad", "ultima_interaccion"]
por_alumno = alumnos.drop(columns=COLS_ESTADO).merge(estado[["asignatura", "id_alumno", *COLS_ESTADO]], how="left")
NO_INSCRIPTO = "No inscripto"
AL_CORTE, EN_PERIODO, DE_FOTO = "A la fecha de corte.", "En el período seleccionado.", f"Foto LMS {FOTO}."


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)).lower()


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
            buscado = (vista["nombre_completo"].fillna("") + " " + vista["id_alumno"]).map(sin_tildes)
            vista = vista[buscado.str.contains(sin_tildes(texto.strip()), regex=False)]

        PRINCIPALES = {"nombre_completo": "Alumno", "id_alumno": "ID", "asignatura": "Materia",
                       "tramo_actividad": "Actividad", "dias_sin_actividad": "Sin entrar",
                       "ultima_interaccion": "Último ingreso", "sesiones": "Sesiones", "minutos": "Minutos",
                       "avance": "Avance", "inscripto": "Inscripto"}
        EXTRA = {"eventos": "Interacciones", "dias_activos": "Días activos", "semanas_activas": "Semanas activas",
                 "tiempo_uso_min": "Tiempo de uso LMS", "intervenciones_foros": "Foros",
                 "encuestas_respondidas": "Encuestas", "emails_enviados": "Correos"}
        AYUDAS = {"Actividad": AL_CORTE, "Sin entrar": AL_CORTE, "Último ingreso": AL_CORTE,
                  "Sesiones": EN_PERIODO, "Minutos": EN_PERIODO, "Interacciones": EN_PERIODO,
                  "Días activos": EN_PERIODO, "Semanas activas": EN_PERIODO, "Avance": DE_FOTO,
                  "Tiempo de uso LMS": DE_FOTO, "Foros": DE_FOTO, "Encuestas": DE_FOTO, "Correos": DE_FOTO,
                  "Inscripto": "Vacío si figura como inscripto en Matriculados."}
        if f.asignatura:
            PRINCIPALES.pop("asignatura")
        with c3.popover(f"Columnas · {len(PRINCIPALES)}+", width="stretch"):
            extra = st.multiselect("Agregar columnas", list(EXTRA), format_func=EXTRA.get, key="part_columnas")
        columnas = {**PRINCIPALES, **{k: EXTRA[k] for k in extra}}
        tabla = vista.assign(
            tramo_actividad=comp.con_icono(vista["tramo_actividad"], comp.ICONOS_TRAMO),
            asignatura=vista["asignatura"].map(comp.SIGLAS),
            inscripto=vista["inscripto"].map(lambda v: [] if bool(v) else [NO_INSCRIPTO]),
        )[list(columnas)].rename(columns=columnas)
        with c4:
            comp.boton_csv(vista[["asignatura", *[c for c in columnas if c != "asignatura"]]]
                           .rename(columns={"asignatura": "Materia", **columnas}),
                           f"participacion_alumnos_{SUFIJO}", "Descargar lista")
        config = {nombre: st.column_config.Column(help=ayuda) for nombre, ayuda in AYUDAS.items()}
        config.update({
            "Sin entrar": st.column_config.NumberColumn(format="%d d", help=AL_CORTE),
            "Último ingreso": st.column_config.DatetimeColumn(format="DD/MM HH:mm", help=AL_CORTE),
            "Minutos": st.column_config.NumberColumn(format="%.0f", help=EN_PERIODO),
            "Avance": st.column_config.ProgressColumn(format="%d %%", min_value=0, max_value=100, help=DE_FOTO),
            "Inscripto": st.column_config.MultiselectColumn(options=[NO_INSCRIPTO], color="orange",
                                                            help=AYUDAS["Inscripto"]),
        })
        st.dataframe(tabla, hide_index=True, width="stretch", height=420,
                     column_config={k: v for k, v in config.items() if k in tabla.columns})
        st.caption(f"{comp.num(len(vista))} de {comp.num(len(alumnos))} alumnos.")

    with comp.tarjeta("un_alumno"):
        comp.titulo_seccion("Actividad de un alumno", "Sus interacciones por semana contra el promedio de su materia.")
        st.page_link(PAG_FICHA, label="Ver la ficha completa, con notas, en Ficha individual",
                     icon=":material/person_search:")
        quienes = (por_alumno.groupby("id_alumno", as_index=False)
                   .agg(nombre_completo=("nombre_completo", "first"))
                   .sort_values(["nombre_completo", "id_alumno"]))
        if quienes.empty:
            st.info("No hay alumnos con esta materia.", icon=":material/search_off:")
        else:
            nombres = dict(zip(quienes["id_alumno"], quienes["nombre_completo"]))
            # El selectbox filtra mientras se escribe: sirve de buscador por apellido, nombre o ID.
            id_elegido = st.selectbox("Alumno", list(nombres), key="part_alumno",
                                      format_func=lambda i: f"{nombres[i]} ({i})",
                                      placeholder="Escribí apellido, nombre o ID",
                                      help=f"{comp.num(len(nombres))} alumnos. Escribí para filtrar la lista.")
            filas_alumno = por_alumno[por_alumno["id_alumno"] == id_elegido]
            materias_alumno = [a for a in f.materias if a in set(filas_alumno["asignatura"])]
            elegidas = st.pills("Materias", materias_alumno, selection_mode="multi", default=materias_alumno,
                                format_func=lambda a: comp.SIGLAS.get(a, a), key=f"part_alumno_materias_{id_elegido}")
            if not elegidas:
                st.caption("Elegí al menos una materia.")
            for asig in [a for a in materias_alumno if a in (elegidas or [])]:
                fila = filas_alumno[filas_alumno["asignatura"] == asig].iloc[0]
                dias_txt = ("nunca entró" if pd.isna(fila["dias_sin_actividad"])
                            else f"último ingreso hace {int(fila['dias_sin_actividad'])} d "
                                 f"({comp.fmt_fecha(fila['ultima_interaccion'], '%d/%m')})")
                H(f'<div class="pa" style="display:flex; flex-wrap:wrap; align-items:center; gap:10px; '
                  f'margin-top:14px">{comp.etiqueta_materia(asig)}<b style="font-size:13px">{asig}</b>'
                  f'{comp.chip_estado(fila["tramo_actividad"])}'
                  f'<span class="pa-muted" style="font-size:12px">{dias_txt}</span></div>')
                comp.tarjetas([
                    ("Sesiones", comp.num(fila["sesiones"])),
                    ("Minutos", comp.num(fila["minutos"])),
                    ("Semanas activas", comp.num(fila["semanas_activas"])),
                    (f"Avance (foto {FOTO})", comp.pct(fila["avance"], 0)),
                ])
                propio = comp.metrica("evolucion_actividad", frecuencia="W", desde=desde, id_alumno=id_elegido,
                                      asignatura=asig)
                materia = comp.metrica("evolucion_participacion", frecuencia="W", desde=desde, asignatura=asig)
                if propio.empty:
                    st.info("No tiene interacciones en el período.", icon=":material/event_busy:")
                else:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=propio["periodo"], y=propio["eventos"], name=fila["nombre_completo"],
                                         marker_color=comp.COLORES_MATERIA[asig],
                                         hovertemplate="sem. del %{x|%d/%m}: %{y} interacciones<extra></extra>"))
                    fig.add_trace(go.Scatter(x=materia["periodo"], y=materia["eventos_por_alumno"],
                                             mode="lines+markers", name=f"Promedio de {comp.SIGLAS[asig]}",
                                             line=dict(color=comp.TEXTO_2, width=2, dash="dot"),
                                             hovertemplate="sem. del %{x|%d/%m}: %{y:.1f} por alumno<extra></extra>"))
                    fig.update_xaxes(tickformat="%d/%m", showgrid=False)
                    fig.update_layout(height=280, yaxis_title="Interacciones por semana", bargap=0.25)
                    comp.grafico(fig, key=f"alumno_{id_elegido}_{comp.SIGLAS[asig]}")
                vacias = comp.metrica("semanas_sin_actividad", id_alumno=id_elegido, asignatura=asig)
                if vacias["sin_actividad"] >= 2:
                    H(comp.nota(f"Sin actividad en {vacias['sin_actividad']} de las últimas "
                                f"{vacias['semanas']} semanas.", "atencion"))

# ---------------------------------------------------------------------------
# Herramientas del aula: foto del LMS (D36). No responde a la fecha de corte.
# ---------------------------------------------------------------------------
with tab_foto:
    H(comp.nota(f"<strong>Foto del LMS al {FOTO}:</strong> no responde a la fecha de corte ni al período.", "info"))
    st.write("")

    with comp.tarjeta("avance"):
        av = estado.dropna(subset=["avance"]).astype({"avance": float})
        # ρ de Spearman contra la nota (la misma cuenta que Notas vs. participación).
        corr = comp.metrica("correlaciones", variables=["avance", "sesiones", "minutos"])
        rhos = corr.pivot(index="asignatura", columns="variable", values="rho") if not corr.empty else pd.DataFrame()
        c1, c2 = st.columns([3, 1.5], vertical_alignment="top")
        with c1:
            comp.titulo_seccion("Avance en el contenido del aula", "% de recursos abiertos por alumno, en tramos de 10 pts.")
        with c2:
            if not rhos.empty and "avance" in rhos:
                ra = rhos["avance"].dropna()
                if len(ra) == 1:
                    texto_rho = f"Avance vs. nota: ρ = {comp.num(ra.iloc[0], 2)}"
                elif len(ra):
                    texto_rho = (f"Avance vs. nota: ρ = {comp.num(ra.min(), 2)} a {comp.num(ra.max(), 2)}"
                                 if ra.min() != ra.max() else f"Avance vs. nota: ρ = {comp.num(ra.min(), 2)}")
                else:
                    texto_rho = ""
                if texto_rho:
                    H(f'<div style="text-align:right">{comp.chip(texto_rho, "neutro", False)}</div>')
                rhos = rhos.reindex([a for a in f.materias if a in rhos.index])
                mayor = [comp.SIGLAS[a] for a, r in rhos.iterrows()
                         if pd.notna(r["avance"]) and r.drop("avance").notna().any()
                         and r["avance"] > r.drop("avance").max()]
                if len(rhos) == 1:
                    r = rhos.iloc[0]
                    detalle = (f"Sesiones: ρ = {comp.num(r.get('sesiones'), 2)} · minutos: ρ = "
                               f"{comp.num(r.get('minutos'), 2)}" + (". El avance es la más alta de las tres."
                                                                      if mayor else "."))
                else:
                    detalle = " · ".join(f"{comp.SIGLAS[a]} {comp.num(r['avance'], 2)}" for a, r in rhos.iterrows())
                    if mayor:
                        detalle += ("<br>Más alto que sesiones y minutos en "
                                    + ("las tres materias" if len(mayor) == len(rhos) else enumerar(mayor)) + ".")
                H(f'<p class="pa-muted" style="text-align:right; margin-top:6px" title="Correlación de Spearman con la '
                  f'nota a la fecha de corte, sobre toda la base.">{detalle}</p>')
            st.page_link(PAG_NOTAS, label="Ver en Notas vs. participación", icon=":material/scatter_plot:")

        BORDES = np.r_[np.arange(0, 100, 10), 100.001]
        y_max = max([np.histogram(av.loc[av["asignatura"] == a, "avance"], bins=BORDES)[0].max()
                     for a in f.materias if (av["asignatura"] == a).any()] or [1])
        cols = st.columns(len(f.materias))
        for colu, asig in zip(cols, f.materias):
            g = av[av["asignatura"] == asig]
            with colu:
                H(f'<p class="pa" style="display:flex; align-items:center; gap:8px; font:600 12px Inter, sans-serif">'
                  f'{comp.punto_materia(asig)}{asig}</p>')
                fig = px.histogram(g, x="avance", color_discrete_sequence=[comp.COLORES_MATERIA[asig]])
                fig.update_traces(xbins=dict(start=0, end=100.001, size=10),
                                  hovertemplate="Avance %{x} %: %{y} alumnos<extra></extra>")
                fig.update_xaxes(range=[-3, 103], title=None, tickvals=[0, 50, 100], ticktext=["0 %", "50 %", "100 %"],
                                 showgrid=False)
                fig.update_yaxes(title=None, range=[0, y_max * 1.08])
                fig.update_layout(height=190, bargap=0.08, margin=dict(t=8, b=0))
                comp.grafico(fig, key=f"avance_{asig}")
                if len(g):
                    st.caption(f"Mediana {comp.pct(g['avance'].median(), 0)} · "
                               f"{comp.pct((g['avance'] >= 80).mean() * 100, 0)} pasó el 80 % · "
                               f"{comp.num((g['avance'] == 0).sum())} en 0")
        sin_avance = av[av["avance"] == 0]
        if len(sin_avance):
            H(comp.nota(f"<strong>{comp.num(len(sin_avance))} alumnos no abrieron ningún recurso del aula.</strong>",
                        "critico"))
            with st.popover(f"Ver esos {comp.num(len(sin_avance))} alumnos"):
                st.dataframe(sin_avance.assign(materia=sin_avance["asignatura"].map(comp.SIGLAS),
                                               inscripto=sin_avance["inscripto"].map(
                                                   lambda v: [] if bool(v) else [NO_INSCRIPTO]))
                             [["nombre_completo", "id_alumno", "materia", "inscripto"]],
                             hide_index=True, width="stretch",
                             column_config={"nombre_completo": "Alumno", "id_alumno": "ID", "materia": "Materia",
                                            "inscripto": st.column_config.MultiselectColumn(
                                                "Inscripto", options=[NO_INSCRIPTO], color="orange")})

    with comp.tarjeta("herramientas"):
        comp.titulo_seccion("Uso de las herramientas del aula",
                            "% de alumnos que usó cada herramienta al menos una vez.")
        herr = comp.metrica("uso_herramientas")
        sin_publicar = [h for h, g in herr.groupby("herramienta", sort=False)
                        if g["recursos"].notna().all() and (g["recursos"] == 0).all()]
        filas = []
        for nombre, g in herr.groupby("herramienta", sort=False):
            if nombre in sin_publicar:
                continue
            g = g.set_index("asignatura")
            if g["recursos"].isna().all():
                sub = "siempre disponible"
            else:
                pub = [f"{int(r)} en {comp.SIGLAS[a]}" for a, r in g["recursos"].items() if pd.notna(r) and r > 0]
                sub = "publicados: " + ", ".join(pub) if pub else "nada publicado"
            celdas = []
            for asig in f.materias:
                if asig not in g.index:
                    celdas.append(f"<td class='pa-muted'>{comp.VACIO}</td>")
                    continue
                r = g.loc[asig]
                if pd.notna(r["recursos"]) and r["recursos"] == 0:
                    celdas.append("<td class='pa-muted'>Sin publicar</td>")
                else:
                    celdas.append(f"<td style='min-width:150px'>{comp.progreso(r['pct_alumnos'], comp.COLORES_MATERIA[asig])}"
                                  f"<span class='pa-muted'>{comp.num(r['alumnos'])} alumnos · "
                                  f"{comp.num(r['usos'])} usos</span></td>")
            filas.append(f"<tr><td><strong>{nombre}</strong><br><span class='pa-muted'>{sub}</span></td>"
                         f"{''.join(celdas)}</tr>")
        cabecera = "".join(f"<th>{a}</th>" for a in f.materias)
        H(f"<div class='pa' style='overflow-x:auto'><table class='pa-tabla'><thead><tr><th>Herramienta</th>{cabecera}"
          f"</tr></thead><tbody>{''.join(filas)}</tbody></table></div>")
        if sin_publicar:
            donde = "en ninguna materia" if len(f.materias) > 1 else f"en {comp.SIGLAS.get(f.asignatura, f.asignatura)}"
            st.caption(f"Sin publicar {donde}: {enumerar(sin_publicar)}.")

        # Qué no se puede medir: foros publicados y herramientas sin publicar, desde los datos.
        foros = herr[herr["herramienta"] == "Foros"]
        con_foros = [comp.SIGLAS[a] for a in foros.loc[foros["recursos"].fillna(0) > 0, "asignatura"]]
        partes = []
        if not con_foros:
            partes.append("ninguna materia publicó foros" if len(foros) > 1 else
                          f"{comp.SIGLAS.get(f.asignatura, f.asignatura)} no publicó foros")
        elif len(con_foros) < len(foros):
            partes.append(f"solo {enumerar(con_foros)} publicó foros")
        if sin_publicar:
            partes.append(f"no hay {enumerar([h.lower() for h in sin_publicar], 'ni')}")
        if partes:
            H(comp.nota(f"<strong>La participación activa no se puede medir:</strong> {' y '.join(partes)}. "
                        "Esta página mide accesos y avance.", "atencion"))
