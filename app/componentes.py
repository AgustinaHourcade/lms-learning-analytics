"""
Piezas compartidas por todas las páginas de la app (Etapa 4).

  Datos        datos() y metrica(): gold se lee una vez y cada métrica se cachea (D47).
  Filtros      barra_lateral() dibuja la fecha de corte, la materia y el umbral (D46);
               filtros() los devuelve desde cualquier página.
  Paleta       COLORES_* e ICONOS_*: un color fijo por materia, condición y estado (D48).
  Visuales     encabezado(), tarjetas(), semaforo(), boton_csv(), num(), pct().
  Rediseño     titulo(), seccion(), aviso(), chip_materia(), pasos(), filas_dato(),
               barras(), tabla_html(), barra_superior() (D52): piezas en HTML con los
               colores de TOKENS, para lo que los widgets de Streamlit no resuelven.

Una página típica:

    import componentes as comp
    f = comp.encabezado("Rendimiento académico", "Notas y condición a la fecha de corte.")
    notas = comp.metrica("nota_final")          # usa la fecha, la materia y el umbral de la barra
    comp.tarjetas([("Alumnos", comp.num(len(notas))), ...])
"""
from __future__ import annotations

import html as _html
import inspect
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:  # streamlit corre desde app/: se agrega la raíz para importar src
    sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import plotly.io as pio  # noqa: E402
import streamlit as st  # noqa: E402

from src import metricas  # noqa: E402
from src.config import (ASIGNATURAS, FECHA_CORTE_DEFECTO, GOLD, SIN_EVALUACIONES,  # noqa: E402
                        UMBRAL_INACTIVIDAD_DIAS)
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD, comparar_fotos  # noqa: E402,F401 (comparar_fotos: D51)

# ---------------------------------------------------------------------------
# Paleta (D48). Valores validados para daltonismo (skill de dataviz).
# ---------------------------------------------------------------------------
# Categórica, en orden fijo: los 3 primeros son los de las materias (Álgebra,
# AED, PyE, en el orden de ASIGNATURAS), los mismos del rediseño (D52).
CATEGORICA = ["#2563C9", "#D4661F", "#0E8F62", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
COLORES_MATERIA = dict(zip(ASIGNATURAS, CATEGORICA))
SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}
# Chips de materia: (fondo, texto).
CHIP_MATERIA = dict(zip(ASIGNATURAS, [("#EAF0F8", "#164279"), ("#FBEFE6", "#8A4415"), ("#E6F2EB", "#0B6B49")]))

# Tokens del rediseño (D52): los mismos valores que .streamlit/config.toml.
TOKENS = {
    "fondo": "#F7F6F3", "superficie": "#FFFFFF", "superficie_2": "#FBFAF8", "lateral": "#FCFBF9",
    "borde": "#E3E1DC", "borde_suave": "#EFEDE8", "borde_fuerte": "#D4D1CA",
    "texto": "#1A1917", "texto_2": "#2C2A25", "texto_suave": "#57544C", "texto_tenue": "#6B6861",
    "primario": "#1B4B8F", "primario_suave": "#EAF0F8",
}
# Tonos de los avisos: (fondo, borde, texto, ícono).
TONOS = {
    "exito": ("#E6F2EB", "#CFE3D8", "#0B6B49", "#116040"),
    "atencion": ("#FBF0DC", "#F0E2C4", "#6B4700", "#A06A00"),
    "error": ("#FBE9E6", "#F2CFC9", "#7A3028", "#93241C"),
    "info": ("#FBFAF8", "#E3E1DC", "#57544C", "#6B6861"),
}

# Estados: colores reservados, siempre acompañados de ícono y texto.
BIEN, ATENCION, SERIO, CRITICO, NEUTRO = "#0ca30c", "#fab219", "#ec835a", "#d03b3b", "#898781"
COLORES_CONDICION = {"Libre": CRITICO, "Regular": ATENCION, "Promociona": BIEN, SIN_EVALUACIONES: NEUTRO}
ICONOS_CONDICION = {"Libre": "🔴", "Regular": "🟡", "Promociona": "🟢", SIN_EVALUACIONES: "⚪"}
COLORES_ACTIVIDAD = {ACTIVO: BIEN, INACTIVO: SERIO, SIN_ACTIVIDAD: NEUTRO}
ICONOS_ACTIVIDAD = {ACTIVO: "🟢", INACTIVO: "🟠", SIN_ACTIVIDAD: "⚪"}

# Secuencial (mapas de calor): un solo tono, de claro a oscuro.
SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Plantilla de plotly: fondo blanco, grilla tenue y la paleta categórica.
pio.templates["tfi"] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family='Inter, system-ui, -apple-system, "Segoe UI", sans-serif', color="#2C2A25"),
    xaxis=dict(gridcolor="#EFEDE8", linecolor="#D4D1CA"),
    yaxis=dict(gridcolor="#EFEDE8", linecolor="#D4D1CA"),
    margin=dict(t=48, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    hoverlabel=dict(font_size=13),
))
pio.templates.default = "plotly_white+tfi"

CSS = """
<style>
  /* ---- Rediseño (D52): tarjetas blancas sobre fondo cálido ---- */
  .block-container {max-width: 1240px; padding-top: 3.4rem;}
  h1 {letter-spacing: -.02em;}
  .num {font-variant-numeric: tabular-nums;}
  .mono {font-family: 'JetBrains Mono', ui-monospace, monospace;}

  /* Contenedores con key "tarjeta-...": superficie blanca con borde */
  [class*="st-key-tarjeta"] {background: #FFFFFF; border: 1px solid #E3E1DC; border-radius: 13px;
      padding: 18px;}

  /* Métricas (st.metric con border=True) */
  [data-testid="stMetric"] {background: #FFFFFF; border-radius: 11px;}
  [data-testid="stMetricLabel"] p {font-size: 11px !important; font-weight: 600; letter-spacing: .06em;
      text-transform: uppercase; color: #6B6861;}
  [data-testid="stMetricValue"] {font-family: 'Space Grotesk', Inter, sans-serif; font-weight: 600;
      font-size: 1.75rem; font-variant-numeric: tabular-nums;}
  [data-testid="stMetricDelta"] {font-weight: 600; font-variant-numeric: tabular-nums;}
  [class*="st-key-ad-peor"] [data-testid="stMetric"] {background: #FBE9E6; border-color: #F2CFC9;}
  [class*="st-key-ad-peor"] [data-testid="stMetricLabel"] p {color: #8A3A31;}
  [class*="st-key-ad-peor"] [data-testid="stMetricValue"] {color: #93241C;}
  [class*="st-key-ad-mejor"] [data-testid="stMetric"] {background: #E6F2EB; border-color: #CFE3D8;}
  [class*="st-key-ad-mejor"] [data-testid="stMetricLabel"] p {color: #0B6B49;}
  [class*="st-key-ad-mejor"] [data-testid="stMetricValue"] {color: #116040;}
  /* Tarjetas de antes/después: todas del mismo alto */
  [class*="st-key-ad-"], [class*="st-key-ad-"] [data-testid="stElementContainer"] {height: 100%;}
  [class*="st-key-ad-"] [data-testid="stMetric"] {height: 100%; min-height: 118px;}

  /* Menú lateral */
  [data-testid="stSidebarNav"] a {border-radius: 8px;}
  [data-testid="stSidebarNav"] a span {font-weight: 500; color: #2C2A25;}
  [data-testid="stSidebarNav"] a[aria-current="page"] {background: #EAF0F8;}
  [data-testid="stSidebarNav"] a[aria-current="page"] span {color: #1B4B8F; font-weight: 600;}
  [data-testid="stNavSectionHeader"] {font-size: 10px !important; font-weight: 600; letter-spacing: .08em;
      text-transform: uppercase; color: #8A867C !important;}

  /* Subida de archivos */
  [data-testid="stFileUploaderDropzone"] {background: #FFFFFF; border: 1px dashed #C9C5BC; border-radius: 11px;}

  /* Chips de materia en los multiselect */
  [data-tag][aria-label="Álgebra"] {background: #EAF0F8 !important;}
  [data-tag][aria-label="Álgebra"], [data-tag][aria-label="Álgebra"] * {color: #164279 !important;}
  [data-tag][aria-label="Algoritmos y Estructuras de Datos"] {background: #FBEFE6 !important;}
  [data-tag][aria-label="Algoritmos y Estructuras de Datos"], [data-tag][aria-label="Algoritmos y Estructuras de Datos"] * {color: #8A4415 !important;}
  [data-tag][aria-label="Probabilidad y Estadística"] {background: #E6F2EB !important;}
  [data-tag][aria-label="Probabilidad y Estadística"], [data-tag][aria-label="Probabilidad y Estadística"] * {color: #0B6B49 !important;}

  /* Piezas HTML (titulo, seccion, aviso, pasos, ...) */
  .tfi-desc {margin: -.4rem 0 1rem; max-width: 76ch; font-size: 13px; line-height: 1.55; color: #57544C;}
  .tfi-h3 {margin: 0 0 4px; font: 600 15px 'Space Grotesk', Inter, sans-serif; color: #1A1917;
      display: flex; align-items: center; gap: 9px;}
  .tfi-sub {margin: 0 0 12px; font-size: 12px; line-height: 1.55; color: #57544C;}
  .tfi-cab {display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; justify-content: space-between;}
  .tfi-cab .tfi-der {font-size: 12px; color: #6B6861;}
  .tfi-etq {margin: 0 0 8px; font: 600 11px Inter, sans-serif; letter-spacing: .06em; text-transform: uppercase;
      color: #6B6861;}
  .tfi-aviso {display: flex; gap: 12px; align-items: flex-start; padding: 13px 15px; border: 1px solid;
      border-radius: 11px; margin: 0 0 12px;}
  .tfi-aviso svg {flex: 0 0 17px; margin-top: 2px;}
  .tfi-aviso p, .tfi-aviso div {margin: 0; font-size: 13px; line-height: 1.6;}
  .tfi-aviso ul {margin: 4px 0 0; padding-left: 18px;}
  .tfi-aviso li {font-size: 12.5px; line-height: 1.55; margin: 0;}
  .tfi-pasos {display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 0 0 6px;}
  .tfi-paso {display: inline-flex; align-items: center; gap: 9px; height: 38px; padding: 0 14px; border-radius: 999px;
      font: 600 13px Inter, sans-serif;}
  .tfi-paso-hecho {background: #E6F2EB; color: #0B6B49;}
  .tfi-paso-actual {background: #1B4B8F; color: #FFFFFF;}
  .tfi-paso-pendiente {background: #FFFFFF; color: #6B6861; border: 1px solid #E3E1DC;}
  .tfi-paso-error {background: #FBE9E6; color: #93241C;}
  .tfi-sep {width: 20px; height: 1px; background: #D4D1CA; display: inline-block;}
  .tfi-dato {display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 8px 0;
      border-top: 1px solid #EFEDE8;}
  .tfi-dato span:first-child {font-size: 12px; color: #57544C;}
  .tfi-dato span:last-child {font-size: 13px; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums;}
  .tfi-chip {display: inline-flex; align-items: center; height: 20px; padding: 0 7px; border-radius: 5px;
      font: 600 11px Inter, sans-serif; white-space: nowrap;}
  .tfi-pill {display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 11px; border-radius: 999px;
      background: #F1EFEA; font-size: 12px; color: #57544C;}
  .tfi-top {display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; margin: -6px 0 2px;}
  .tfi-archivo {font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; font-weight: 500;
      overflow-wrap: anywhere; margin: 0 0 2px;}
  .tfi-barra {display: flex; align-items: center; gap: 10px; margin-bottom: 8px;}
  .tfi-barra > span:first-child {flex: 0 0 104px; font-size: 12px; color: #57544C; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap;}
  .tfi-barra .pista {flex: 1 1 auto; height: 12px; border-radius: 3px; background: #EDEBE6; overflow: hidden;}
  .tfi-barra .pista span {display: block; height: 100%;}
  .tfi-barra > span:last-child {flex: 0 0 56px; text-align: right; font-size: 12px; font-weight: 500;
      font-variant-numeric: tabular-nums;}
  .tfi-grilla {display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px;}
  .tfi-vacio {border: 1px solid #E3E1DC; border-radius: 10px; padding: 12px;}
  .tfi-vacio .col {margin: 0 0 6px; font: 500 12px 'JetBrains Mono', monospace; overflow-wrap: anywhere;}
  .tfi-vacio .val {margin: 0 0 6px; font: 600 18px 'Space Grotesk', Inter, sans-serif;}
  .tfi-vacio .det {margin: 0; font-size: 11px; line-height: 1.5;}
  .tfi-tabla {overflow: auto; border-top: 1px solid #EFEDE8; margin: 0 -18px -18px;}
  .tfi-tabla table {border-collapse: collapse; width: 100%; margin: 0; border: none;}
  .tfi-tabla th {position: sticky; top: 0; background: #FCFBF9; font-size: 11px; letter-spacing: .05em;
      text-transform: uppercase; color: #6B6861; font-weight: 600; text-align: left; padding: 10px 12px;
      border: none; border-bottom: 1px solid #E3E1DC; white-space: nowrap;}
  .tfi-tabla td {font-size: 12px; color: #2C2A25; padding: 9px 12px; border: none; border-bottom: 1px solid #EFEDE8;
      vertical-align: middle; white-space: nowrap;}
  .tfi-tabla tr:last-child td {border-bottom: none;}
  .tfi-tabla th:first-child, .tfi-tabla td:first-child {padding-left: 18px;}

  /* Semáforo (Ficha individual) */
  .semaforo {display:inline-flex; align-items:center; gap:.4rem; padding:.25rem .7rem; border-radius:999px;
             font-weight:600; border:1px solid rgba(11,11,11,.10);}
  .semaforo-Libre      {background:#FBE9E6; color:#93241C;}
  .semaforo-Regular    {background:#FBF0DC; color:#6B4700;}
  .semaforo-Promociona {background:#E6F2EB; color:#0B6B49;}
  .semaforo-otro       {background:#F1EFEA; color:#57544C;}
</style>
"""


def estilos() -> None:
    """CSS del rediseño (D52). El tema base (colores, tipografías, bordes) está en
    .streamlit/config.toml; acá va lo que el tema no cubre."""
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Datos y caché (D47, D49)
# ---------------------------------------------------------------------------
def carpeta_gold() -> Path:
    """data/gold, salvo que la variable de entorno LMS_GOLD diga otra (la usan los tests)."""
    return Path(os.environ.get("LMS_GOLD", GOLD))


def version_gold() -> str:
    """Cambia cada vez que se regenera gold ("" si todavía no existe)."""
    archivos = [carpeta_gold() / f"{t}.parquet" for t in metricas.TABLAS.values()]
    if not all(p.exists() for p in archivos):
        return ""
    return str(max(p.stat().st_mtime_ns for p in archivos))


def asegurar_gold() -> None:
    """Si gold no existe (primera vez o Streamlit Cloud), corre el pipeline (D49)."""
    if version_gold():
        return
    from src.pipeline import procesar
    with st.spinner("Es la primera vez que se abre la app: procesando los Excel (tarda unos segundos)…"):
        try:
            procesar(gold=carpeta_gold(), verbose=False)
        except Exception as e:  # noqa: BLE001 - se muestra el motivo en vez de romper la app
            st.error(f"No se pudieron procesar los datos: {type(e).__name__}: {e}")
            st.stop()


@st.cache_resource(max_entries=1, show_spinner="Leyendo los datos…")
def _datos(version: str) -> metricas.Datos:  # `version` invalida el caché al regenerar gold
    return metricas.cargar(carpeta_gold())


def datos() -> metricas.Datos:
    """Las tablas de gold, leídas una sola vez y compartidas entre páginas."""
    return _datos(version_gold())


@st.cache_data(max_entries=500, show_spinner="Calculando…")
def _metrica(nombre: str, version: str, args: tuple, kwargs: tuple):
    return getattr(metricas, nombre)(_datos(version), *args, **dict(kwargs))


def metrica(nombre: str, *args, **kwargs):
    """Llama a `src.metricas.<nombre>` con la caché de la app. Si la función recibe
    fecha_corte, asignatura o umbral y no se pasan, usa los de la barra lateral.
    Ejemplos: metrica("nota_final"), metrica("evolucion_actividad", frecuencia="M"),
              metrica("nota_final", asignatura=None)   # todas, ignorando la barra"""
    parametros = inspect.signature(getattr(metricas, nombre)).parameters
    f = filtros()
    for clave, valor in {"fecha_corte": f.fecha_corte, "asignatura": f.asignatura, "umbral": f.umbral}.items():
        if clave in parametros and clave not in kwargs:
            kwargs[clave] = valor
    return _metrica(nombre, version_gold(), args, tuple(sorted(kwargs.items())))


def limpiar_cache() -> None:
    """Después de cargar un archivo: todas las páginas vuelven a leer gold."""
    st.cache_data.clear()
    st.cache_resource.clear()


# ---------------------------------------------------------------------------
# Barra lateral global (D46)
# ---------------------------------------------------------------------------
TODAS = "Todas las materias"
DEFECTOS = {"fecha_corte": pd.Timestamp(FECHA_CORTE_DEFECTO).date(), "materia": TODAS,
            "umbral": UMBRAL_INACTIVIDAD_DIAS}


@dataclass(frozen=True)
class Filtros:
    fecha_corte: date
    asignatura: str | None   # None = todas
    umbral: int

    @property
    def materia(self) -> str:
        return self.asignatura or TODAS

    @property
    def materias(self) -> list[str]:
        return [self.asignatura] if self.asignatura else list(ASIGNATURAS)


def _rango_fechas(d: metricas.Datos) -> tuple[date, date]:
    fechas = d.interacciones["fecha_hora"]
    inicio = fechas.min().date()
    fin = max(fechas.max().date(), DEFECTOS["fecha_corte"])
    return inicio, fin


def _restablecer() -> None:
    for clave, valor in DEFECTOS.items():
        st.session_state[clave] = valor


def barra_lateral(sin_filtros: str | None = None) -> Filtros:
    """Dibuja los filtros globales. Se llama una sola vez, desde Inicio.py,
    antes de correr la página elegida: así valen para todas.
    Las páginas que no usan filtros (Cargar archivo, Explorar datos) pasan en
    `sin_filtros` el motivo: se muestra eso en vez de los widgets y los valores
    elegidos se conservan para cuando se vuelve a un dashboard (D52)."""
    inicio, fin = _rango_fechas(datos())
    for clave, valor in DEFECTOS.items():
        st.session_state.setdefault(clave, valor)
        # Reasignar evita que Streamlit borre el valor en las páginas donde el widget no se dibuja.
        st.session_state[clave] = st.session_state[clave]
    # Si los datos cambiaron y la fecha guardada quedó fuera de rango, se acomoda.
    st.session_state["fecha_corte"] = min(max(st.session_state["fecha_corte"], inicio), fin)

    if sin_filtros:
        with st.sidebar:
            html(f'<div style="margin-top:8px;padding:14px;background:#F1EFEA;border:1px dashed #D4D1CA;'
                 f'border-radius:12px"><p class="tfi-etq" style="display:flex;align-items:center;gap:8px">'
                 f'{ICONOS_SVG["cruz"]}Filtros desactivados</p>'
                 f'<p style="margin:0;font-size:12px;line-height:1.55;color:#57544C">{sin_filtros}</p></div>')
        ss = st.session_state
        f = Filtros(fecha_corte=ss["fecha_corte"], asignatura=None if ss["materia"] == TODAS else ss["materia"],
                    umbral=int(ss["umbral"]))
        st.session_state["_filtros"] = f
        return f

    with st.sidebar:
        st.header("Filtros")
        fecha = st.date_input("Fecha de corte", min_value=inicio, max_value=fin, key="fecha_corte",
                              format="DD/MM/YYYY",
                              help="Todo se calcula con lo que se sabía ese día (inclusive): notas de los "
                                   "instrumentos ya tomados, actividad hasta esa fecha.")
        materia = st.selectbox("Materia", [TODAS, *ASIGNATURAS], key="materia")
        umbral = st.slider("Inactivo después de (días sin entrar)", 1, 30, key="umbral",
                           help="Un alumno que no entra hace más de estos días cuenta como inactivo (D35).")
        st.button("Restablecer", on_click=_restablecer, width="stretch")
        st.caption(f"Datos del {fmt_fecha(inicio)} al {fmt_fecha(fin)}.")

    f = Filtros(fecha_corte=fecha, asignatura=None if materia == TODAS else materia, umbral=int(umbral))
    st.session_state["_filtros"] = f
    return f


def filtros() -> Filtros:
    """Los filtros elegidos en la barra lateral (o los de por defecto)."""
    return st.session_state.get("_filtros") or Filtros(DEFECTOS["fecha_corte"], None, DEFECTOS["umbral"])


# ---------------------------------------------------------------------------
# Formatos (en castellano: 1.234,5)
# ---------------------------------------------------------------------------
def num(x, decimales: int = 0) -> str:
    if x is None or pd.isna(x):
        return "–"
    return f"{x:,.{decimales}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, decimales: int = 1) -> str:
    """x ya en porcentaje (52.07 -> '52,1 %')."""
    return "–" if x is None or pd.isna(x) else f"{num(x, decimales)} %"


def fmt_fecha(x) -> str:
    return "–" if x is None or pd.isna(x) else pd.Timestamp(x).strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Componentes visuales
# ---------------------------------------------------------------------------
def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página y, abajo, los filtros que se están usando."""
    f = filtros()
    st.title(titulo)
    if descripcion:
        st.markdown(descripcion)
    st.caption(f"Corte: **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
               f"Inactivo después de {f.umbral} días sin entrar")
    return f


def tarjetas(items: list, columnas: int | None = None) -> None:
    """Fila de tarjetas de KPI. Cada item es (etiqueta, valor) o
    (etiqueta, valor, ayuda) o un dict con las claves de st.metric."""
    items = [it if isinstance(it, dict) else dict(zip(["label", "value", "help"], it)) for it in items]
    cols = st.columns(columnas or len(items))
    for i, it in enumerate(items):
        cols[i % len(cols)].metric(border=True, **it)


def semaforo(condicion: str, detalle: str = "") -> str:
    """HTML del semáforo: color + ícono + texto (nunca solo color, D48)."""
    clase = condicion if condicion in ("Libre", "Regular", "Promociona") else "otro"
    icono = ICONOS_CONDICION.get(condicion, "⚪")
    extra = f" · {detalle}" if detalle else ""
    return f'<span class="semaforo semaforo-{clase}">{icono} {condicion}{extra}</span>'


def mostrar_semaforo(condicion: str, detalle: str = "") -> None:
    st.markdown(semaforo(condicion, detalle), unsafe_allow_html=True)


def con_icono(serie: pd.Series, iconos: dict) -> pd.Series:
    """Para tablas: 'Libre' -> '🔴 Libre'."""
    return serie.map(lambda v: f"{iconos.get(v, '')} {v}".strip())


def boton_csv(df: pd.DataFrame, nombre: str, etiqueta: str = "Descargar CSV") -> None:
    """Descarga en CSV que abre bien en Excel en castellano (separador ; y UTF-8 con BOM)."""
    st.download_button(etiqueta, df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=nombre if nombre.endswith(".csv") else f"{nombre}.csv",
                       mime="text/csv", icon=":material/download:")


# ---------------------------------------------------------------------------
# Piezas del rediseño (D52): HTML con los tokens, para lo que los widgets no resuelven
# ---------------------------------------------------------------------------
ICONOS_SVG = {
    "ok": '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="6.6" '
          'fill="currentColor"/><path d="M4.9 8.3l2.1 2.1 4.2-4.5" fill="none" stroke="#fff" stroke-width="1.8" '
          'stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "atencion": '<svg viewBox="0 0 16 16" width="17" height="17" aria-hidden="true"><path d="M8 1.6l6.6 11.8H1.4z" '
                'fill="currentColor"/><path d="M8 6v3.1M8 11.2v.1" stroke="#fff" stroke-width="1.5" '
                'stroke-linecap="round"/></svg>',
    "error": '<svg viewBox="0 0 16 16" width="17" height="17" aria-hidden="true"><circle cx="8" cy="8" r="6.6" '
             'fill="currentColor"/><path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" stroke="#fff" stroke-width="1.6" '
             'stroke-linecap="round"/></svg>',
    "info": '<svg viewBox="0 0 16 16" width="17" height="17" aria-hidden="true"><circle cx="8" cy="8" r="6.6" '
            'fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 7.2v4.2M8 4.8v.1" '
            'stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    "nube": '<svg viewBox="0 0 16 16" width="17" height="17" aria-hidden="true"><path d="M2 8s2.4-4 6-4 6 4 6 4-2.4 '
            '4-6 4-6-4-6-4z" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M3 13L13 3" '
            'stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    "cruz": '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" '
            'stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    "planilla": '<svg viewBox="0 0 16 16" width="17" height="17" aria-hidden="true"><rect x="2.5" y="2" width="11" '
                'height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M2.5 6.5h11M6.5 '
                '6.5v7.5" stroke="currentColor" stroke-width="1.4"/></svg>',
}
ICONO_TONO = {"exito": "ok", "atencion": "atencion", "error": "error", "info": "info"}

LOGO_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="210" height="32" viewBox="0 0 210 32">'
            '<rect x="0" y="2" width="28" height="28" rx="8" fill="#1B4B8F"/>'
            '<text x="14" y="21.5" text-anchor="middle" font-family="Space Grotesk, Segoe UI, Arial, sans-serif" '
            'font-weight="700" font-size="15" fill="#FFFFFF">A</text>'
            '<text x="38" y="21.5" font-family="Space Grotesk, Segoe UI, Arial, sans-serif" font-weight="600" '
            'font-size="15.5" fill="#1A1917">Analítica académica</text></svg>')
ICONO_LOGO_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
                  '<rect x="2" y="2" width="28" height="28" rx="8" fill="#1B4B8F"/>'
                  '<text x="16" y="21.5" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
                  'font-weight="700" font-size="15" fill="#FFFFFF">A</text></svg>')


def html(contenido: str) -> None:
    """Escribe HTML (las piezas de abajo devuelven texto para poder combinarlas)."""
    st.markdown(contenido, unsafe_allow_html=True)


def esc(texto) -> str:
    """Escapa texto que viene de los datos (nombres de archivo, instrumentos)."""
    return _html.escape(str(texto))


def titulo(texto: str, descripcion: str = "") -> None:
    """Título de página del rediseño, con la bajada en gris."""
    st.title(texto, anchor=False)
    if descripcion:
        html(f'<p class="tfi-desc">{descripcion}</p>')


def seccion(texto: str, subtitulo: str = "", derecha: str = "", icono: str = "", color_icono: str = "") -> str:
    """Encabezado de una tarjeta: título en Space Grotesk, subtítulo y un dato a la derecha."""
    ic = (f'<span style="color:{color_icono or "#116040"};display:inline-flex">{ICONOS_SVG[icono]}</span>'
          if icono else "")
    der = f'<span class="tfi-der num">{derecha}</span>' if derecha else ""
    sub = f'<p class="tfi-sub">{subtitulo}</p>' if subtitulo else '<div style="height:10px"></div>'
    return f'<div class="tfi-cab"><p class="tfi-h3">{ic}{texto}</p>{der}</div>{sub}'


def aviso(texto: str, tono: str = "info", titulo_: str = "", items: list[str] | None = None,
          icono: str | None = None) -> str:
    """Caja de aviso con ícono (exito / atencion / error / info). Nunca solo color (D48)."""
    fondo, borde, color, color_icono = TONOS[tono]
    svg = ICONOS_SVG[icono or ICONO_TONO[tono]]
    cab = f'<strong style="font-weight:600">{titulo_}</strong> ' if titulo_ else ""
    lista = "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>" if items else ""
    return (f'<div class="tfi-aviso" style="background:{fondo};border-color:{borde}">'
            f'<span style="color:{color_icono};display:inline-flex">{svg}</span>'
            f'<div style="color:{color}">{cab}{texto}{lista}</div></div>')


def chip_materia(asignatura: str | None, largo: bool = False) -> str:
    if not asignatura:
        return '<span class="tfi-chip" style="background:#F1EFEA;color:#57544C">–</span>'
    fondo, color = CHIP_MATERIA.get(asignatura, ("#F1EFEA", "#57544C"))
    return (f'<span class="tfi-chip" style="background:{fondo};color:{color}">'
            f'{esc(asignatura if largo else SIGLAS.get(asignatura, asignatura))}</span>')


def pasos(items: list[tuple[str, str]]) -> str:
    """Indicador de pasos. Cada item es (texto, estado) con estado hecho / actual / pendiente / error."""
    iconos = {"hecho": ICONOS_SVG["ok"].replace('stroke="#fff"', 'stroke="#E6F2EB"'),
              "error": ICONOS_SVG["error"].replace('stroke="#fff"', 'stroke="#FBE9E6"')}
    partes = [f'<span class="tfi-paso tfi-paso-{estado}">{iconos.get(estado, "")}{texto}</span>'
              for texto, estado in items]
    return '<div class="tfi-pasos" aria-label="Pasos">' + '<span class="tfi-sep"></span>'.join(partes) + "</div>"


def filas_dato(pares: list[tuple[str, str]]) -> str:
    """Lista etiqueta -> valor con líneas finas (como 'Qué se reconoció')."""
    return "".join(f'<div class="tfi-dato"><span>{k}</span><span>{v}</span></div>' for k, v in pares)


def barras(filas: list[tuple[str, float, str]], decimales: int = 0) -> str:
    """Barras horizontales simples: (etiqueta, valor, color). El largo es relativo al máximo."""
    maximo = max((v for _, v, _ in filas), default=0) or 1
    return "".join(
        f'<div class="tfi-barra"><span title="{esc(e)}">{esc(e)}</span><span class="pista">'
        f'<span style="width:{v / maximo * 100:.1f}%;background:{c}"></span></span>'
        f'<span>{num(v, decimales)}</span></div>' for e, v, c in filas)


def tabla_html(columnas: list[str], filas: list[list[str]], alto: int | None = None) -> str:
    """Tabla HTML con el estilo del rediseño (las celdas ya vienen como HTML)."""
    cab = "".join(f'<th scope="col">{c}</th>' for c in columnas)
    cuerpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in fila) + "</tr>" for fila in filas)
    estilo = f' style="max-height:{alto}px"' if alto else ""
    return f'<div class="tfi-tabla"{estilo}><table><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table></div>'


def barra_superior(chips: list[str]) -> None:
    """Píldoras arriba a la derecha (fecha de los datos, último recálculo)."""
    html('<div class="tfi-top">' + "".join(f'<span class="tfi-pill num">{c}</span>' for c in chips) + "</div>")


def ultimo_recalculo() -> str:
    """'hoy 10:25' u '07/11 10:25', según cuándo se regeneró gold."""
    v = version_gold()
    if not v:
        return "–"
    t = datetime.fromtimestamp(int(v) / 1e9)
    return f"hoy {t:%H:%M}" if t.date() == date.today() else f"{t:%d/%m %H:%M}"
