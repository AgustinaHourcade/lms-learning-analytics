"""
Piezas compartidas por todas las páginas de la app (Etapa 4).

  Datos        datos() y metrica(): gold se lee una vez y cada métrica se cachea (D47).
  Filtros      barra_lateral() dibuja la fecha de corte, la materia y el umbral (D46);
               filtros() los devuelve desde cualquier página.
  Paleta       TONOS, COLORES_* e ICONOS_*: un color y una forma fijos por materia,
               condición y estado (D48; sistema visual del rediseño, D56).
  Visuales     encabezado(), tarjetas(), semaforo(), boton_csv(), num(), pct().
  Piezas HTML  html() pinta; chip(), icono(), etiqueta_materia(), titulo_materia(),
               leyenda(), aviso() devuelven HTML con las clases tfi-* del CSS.
               Las tarjetas son st.container(border=True) o <div class="tfi-card">.

Una página típica:

    import componentes as comp
    f = comp.encabezado("Rendimiento académico", "Notas y condición a la fecha de corte.")
    notas = comp.metrica("nota_final")          # usa la fecha, la materia y el umbral de la barra
    comp.tarjetas([("Alumnos", comp.num(len(notas))), ...])
"""
from __future__ import annotations

import inspect
import os
import sys
from dataclasses import dataclass
from datetime import date
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
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD  # noqa: E402

# ---------------------------------------------------------------------------
# Sistema visual (D48, rediseño D56). Los mismos valores están en
# .streamlit/config.toml para los widgets nativos.
# Regla de fondo: el estado nunca se comunica solo con color, siempre
# color + forma + palabra. El color de materia identifica y el del semáforo
# evalúa: nunca se mezclan en el mismo elemento.
# ---------------------------------------------------------------------------
FONDO, TARJETA, BORDE, BORDE_SUAVE = "#F7F6F3", "#FFFFFF", "#E3E1DC", "#EFEDE8"
TEXTO, TEXTO_2, TEXTO_3, TEXTO_4 = "#1A1917", "#57544C", "#6B6861", "#8A867C"
ACCION = "#1B4B8F"
FUENTE = "Inter, system-ui, sans-serif"
FUENTE_TITULOS = "'Space Grotesk', Inter, sans-serif"

SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}
_POR_SIGLA = {"ALG": "#2563C9", "AED": "#D4661F", "PYE": "#0E8F62"}
COLORES_MATERIA = {m: _POR_SIGLA[s] for m, s in SIGLAS.items()}
# Etiqueta de materia (fondo, texto): tinte suave del color de la materia.
TINTES_MATERIA = {"ALG": ("#EAF0F8", "#164279"), "AED": ("#FBEFE6", "#8A4415"), "PYE": ("#E6F2EB", "#0B6B49")}
# Categórica, en orden fijo: las 3 primeras son las materias (en el orden de ASIGNATURAS).
CATEGORICA = [*COLORES_MATERIA.values(), "#C98A12", "#8E5BB5", "#5E7D1E", "#C2417A", "#5B6B7A"]

# Estados: (color de la marca, fondo del chip, texto del chip) y su forma.
#   bien = círculo, atención = triángulo, crítico = octágono, neutro = cuadrado; "serio" (naranja) = rombo.
TONOS = {
    "bien": ("#16734A", "#E6F2EB", "#116040"),
    "atencion": ("#C98A12", "#FBF0DC", "#7A5000"),
    "serio": ("#C2581A", "#FBEFE6", "#8A4415"),
    "critico": ("#B02A20", "#FBE9E6", "#93241C"),
    "neutro": ("#8A867C", "#EBE9E4", "#35332D"),
    "info": (ACCION, "#EAF0F8", "#164279"),
}
BIEN, ATENCION, SERIO, CRITICO, NEUTRO = (TONOS[t][0] for t in ("bien", "atencion", "serio", "critico", "neutro"))
TONO_CONDICION = {"Promociona": "bien", "Regular": "atencion", "Libre": "critico", SIN_EVALUACIONES: "neutro"}
TONO_ACTIVIDAD = {ACTIVO: "bien", INACTIVO: "atencion", SIN_ACTIVIDAD: "neutro"}
COLORES_CONDICION = {c: TONOS[t][0] for c, t in TONO_CONDICION.items()}
COLORES_ACTIVIDAD = {e: TONOS[t][0] for e, t in TONO_ACTIVIDAD.items()}
# Para tablas (st.dataframe no admite HTML): un símbolo con la misma forma que el chip.
ICONOS_CONDICION = {"Libre": "⬣", "Regular": "▲", "Promociona": "●", SIN_EVALUACIONES: "■"}
ICONOS_ACTIVIDAD = {ACTIVO: "●", INACTIVO: "▲", SIN_ACTIVIDAD: "■"}

# Secuencial (mapas de calor y barras de intensidad): el azul de acción, de claro a oscuro.
SECUENCIAL = ["#EEF3F9", "#D4E1F1", "#A9C4E6", "#7FA6D9", "#4B7FC4", "#1B4B8F", "#123663"]

# Plantilla de plotly: fondo blanco (va dentro de tarjetas), grilla tenue y la paleta categórica.
pio.templates["tfi"] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family=FUENTE, color=TEXTO_2, size=12),
    title=dict(font=dict(family=FUENTE_TITULOS, color=TEXTO, size=15)),
    paper_bgcolor=TARJETA, plot_bgcolor=TARJETA,
    xaxis=dict(gridcolor=BORDE_SUAVE, linecolor="#D9D6CF", zerolinecolor="#D9D6CF", tickcolor="#D9D6CF",
               title=dict(font=dict(size=12, color=TEXTO_3))),
    yaxis=dict(gridcolor=BORDE_SUAVE, linecolor="#D9D6CF", zerolinecolor="#D9D6CF", tickcolor="#D9D6CF",
               title=dict(font=dict(size=12, color=TEXTO_3))),
    margin=dict(t=24, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12)),
    hoverlabel=dict(font=dict(size=13, family=FUENTE), bgcolor=TARJETA, bordercolor=BORDE),
))
pio.templates.default = "plotly_white+tfi"

CSS = """
<style>
/* --- Estructura ------------------------------------------------------- */
.block-container {padding-top: 2.2rem; max-width: 1240px;}
h1 {letter-spacing: -.02em;}
/* Contenedores con borde = tarjetas blancas */
[data-testid="stVerticalBlock"][class*="border"], div[data-testid="stVerticalBlockBorderWrapper"] {
  background: #FFFFFF; border-radius: 13px !important;}
[data-testid="stExpander"] details {background: #FFFFFF; border-radius: 13px;}
[data-testid="stMetric"] {background: #FFFFFF; border-radius: 13px;}
/* Pestañas: subrayado azul en la activa */
[data-testid="stTabs"] button[role="tab"] p {font-size: 14px; font-weight: 500; color: #57544C;}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {font-weight: 600; color: #1B4B8F;}
/* Barra lateral */
[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a span {font-size: 13px;}
[data-testid="stSidebarNavSeparator"] {display:none;}
/* --- Piezas HTML (tfi-*) ------------------------------------------------ */
.tfi {font-family: Inter, system-ui, sans-serif; color: #1A1917;}
.tfi .num, .tfi.num {font-variant-numeric: tabular-nums;}
.tfi-card {background:#FFFFFF; border:1px solid #E3E1DC; border-radius:13px; padding:18px 20px; height:100%;}
.tfi-card.critico {background:#FBE9E6; border-color:#F2CFC9;}
.tfi-label {margin:0 0 12px; font:600 11px Inter, sans-serif; letter-spacing:.06em; text-transform:uppercase;
  color:#6B6861;}
.tfi-h3 {margin:0 0 4px; font:600 15px 'Space Grotesk', Inter, sans-serif; color:#1A1917;}
.tfi-desc {margin:0 0 16px; max-width:88ch; font:400 12.5px Inter, sans-serif; line-height:1.55; color:#57544C;}
.tfi-texto {margin:0; font:400 13px Inter, sans-serif; line-height:1.55; color:#57544C;}
.tfi-texto strong, .tfi-desc strong, .tfi-nota strong {font-weight:600; color:#1A1917;}
.tfi-big {margin:0 0 4px; font:600 28px 'Space Grotesk', Inter, sans-serif; letter-spacing:-.01em;
  font-variant-numeric: tabular-nums;}
.tfi-chip {display:inline-flex; align-items:center; gap:6px; height:22px; padding:0 8px; border-radius:999px;
  font:600 11px Inter, sans-serif; white-space:nowrap; vertical-align:middle;}
.tfi-chip.grande {height:26px; padding:0 10px; font-size:12px; gap:7px;}
.tfi-materia {display:inline-flex; align-items:center; height:20px; padding:0 7px; border-radius:5px;
  font:600 11px Inter, sans-serif; vertical-align:middle;}
.tfi-titulo-materia {margin:0 0 8px; display:flex; align-items:center; gap:8px; font:600 13px Inter, sans-serif;
  color:#1A1917;}
.tfi-titulo-materia .sub {font:400 11px Inter, sans-serif; color:#6B6861; margin-left:auto; white-space:nowrap;}
.tfi-cuadrito {width:9px; height:9px; border-radius:3px; display:inline-block; flex:0 0 9px;}
.tfi-nota {margin:0; padding:12px 14px; border-radius:10px; background:#FBFAF8; font:400 12.5px Inter, sans-serif;
  line-height:1.6; color:#57544C;}
.tfi-aviso {display:flex; gap:12px; align-items:flex-start; padding:14px; border-radius:11px; border:1px solid;}
.tfi-aviso p {margin:0; font:400 13px Inter, sans-serif; line-height:1.6;}
.tfi-aviso strong {font-weight:600;}
.tfi-leyenda {display:flex; flex-wrap:wrap; gap:16px; margin:0 0 12px;}
.tfi-leyenda span.item {display:inline-flex; align-items:center; gap:7px; font:500 12px Inter, sans-serif;}
.tfi-tabla {width:100%; border-collapse:collapse; border:none; margin:0;}
.tfi-tabla tr {border:none; background:none;}
.tfi-tabla th {font:600 11px Inter, sans-serif; letter-spacing:.05em; text-transform:uppercase; color:#6B6861;
  text-align:left; padding:10px 12px; border:none; border-bottom:1px solid #E3E1DC; white-space:nowrap; background:none;}
.tfi-tabla td {font:400 13px Inter, sans-serif; color:#2C2A25; padding:11px 12px; border-bottom:1px solid #EFEDE8;
  border-top:none; border-left:none; border-right:none; vertical-align:middle; white-space:nowrap;}
.tfi-tabla tr:last-child td {border-bottom:none;}
.tfi-tabla .sub {font:400 11px Inter, sans-serif; color:#6B6861;}
.tfi-barrita {display:flex; align-items:center; gap:9px;}
.tfi-barrita .pista {flex:0 0 72px; height:10px; border-radius:3px; background:#EDEBE6; overflow:hidden;
  display:inline-block;}
.tfi-barrita .pista span {display:block; height:100%;}
.tfi-apilada {display:flex; align-items:center; gap:12px; margin-bottom:8px;}
.tfi-apilada .izq {flex:0 0 165px; font:400 12px Inter, sans-serif; color:#57544C;}
.tfi-apilada .izq span {color:#8A867C;}
.tfi-apilada .barra {flex:1 1 auto; display:flex; height:24px; border-radius:5px; overflow:hidden;
  background:#EDEBE6;}
.tfi-apilada .barra span {display:flex; align-items:center; justify-content:center; overflow:hidden;
  font:600 11px Inter, sans-serif; color:#FFFFFF; white-space:nowrap;}
.tfi-apilada .der {flex:0 0 48px; text-align:right; font:600 13px Inter, sans-serif;}
.tfi-cuadrante {display:grid; grid-template-columns:1fr 1fr; gap:8px;}
.tfi-cuadrante div {border:1px solid; border-radius:10px; padding:12px;}
.tfi-cuadrante .n {margin:0 0 3px; font:600 20px 'Space Grotesk', Inter, sans-serif;}
.tfi-cuadrante .t {margin:0; font:500 11px Inter, sans-serif; line-height:1.45;}
.tfi-grilla {display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:14px 22px;}
</style>
"""


def estilos() -> None:
    """CSS global: tarjetas, pestañas y las piezas HTML (clases tfi-*) del sistema visual."""
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


def barra_lateral() -> Filtros:
    """Dibuja los filtros globales. Se llama una sola vez, desde Inicio.py,
    antes de correr la página elegida: así valen para todas."""
    inicio, fin = _rango_fechas(datos())
    for clave, valor in DEFECTOS.items():
        st.session_state.setdefault(clave, valor)
    # Si los datos cambiaron y la fecha guardada quedó fuera de rango, se acomoda.
    st.session_state["fecha_corte"] = min(max(st.session_state["fecha_corte"], inicio), fin)

    with st.sidebar, st.container(border=True):
        st.markdown('<p class="tfi-label" style="margin:0">Filtros</p>', unsafe_allow_html=True)
        fecha = st.date_input("Fecha de corte", min_value=inicio, max_value=fin, key="fecha_corte",
                              format="DD/MM/YYYY",
                              help="Todo se calcula con lo que se sabía ese día (inclusive): notas de los "
                                   "instrumentos ya tomados, actividad hasta esa fecha.")
        materia = st.selectbox("Materia", [TODAS, *ASIGNATURAS], key="materia")
        umbral = st.slider("Inactivo desde (días sin entrar)", 1, 30, key="umbral", format="%d días",
                           help="Un alumno que no entra hace más de estos días cuenta como inactivo (D35).")
        st.button("Restablecer filtros", on_click=_restablecer, width="stretch")
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
        return "—"
    return f"{x:,.{decimales}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, decimales: int = 1) -> str:
    """x ya en porcentaje (52.07 -> '52,1 %')."""
    return "—" if x is None or pd.isna(x) else f"{num(x, decimales)} %"


def fmt_fecha(x) -> str:
    return "—" if x is None or pd.isna(x) else pd.Timestamp(x).strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Piezas HTML del sistema visual (se pintan con html(); clases en CSS)
# ---------------------------------------------------------------------------
def html(contenido: str, destino=st) -> None:
    """Pinta HTML. Se pasa a una sola línea: en markdown, una línea con sangría sería un bloque de código."""
    destino.markdown(" ".join(contenido.split("\n")), unsafe_allow_html=True)


_FORMAS = {  # misma forma = mismo significado en toda la app
    "bien": '<circle cx="8" cy="8" r="6.6" fill="currentColor"/>',
    "atencion": '<path d="M8 1.6l6.6 11.8H1.4z" fill="currentColor"/>',
    "serio": '<path d="M8 1.2l6.8 6.8L8 14.8 1.2 8z" fill="currentColor"/>',
    "critico": '<path d="M5.2 1.4h5.6l3.8 3.8v5.6l-3.8 3.8H5.2l-3.8-3.8V5.2z" fill="currentColor"/>',
    "neutro": '<rect x="2" y="2" width="12" height="12" rx="3" fill="currentColor"/>',
    "info": '<circle cx="8" cy="8" r="6.6" fill="currentColor"/>',
}


def icono(tono: str, tam: int = 12, color: str | None = None) -> str:
    """Forma del estado en SVG: círculo, triángulo, rombo, octágono o cuadrado."""
    c = color or TONOS[tono][0]
    return (f'<svg viewBox="0 0 16 16" width="{tam}" height="{tam}" aria-hidden="true" '
            f'style="color:{c};flex:0 0 {tam}px">{_FORMAS[tono]}</svg>')


def chip(texto: str, tono: str = "neutro", grande: bool = False, con_icono: bool = True) -> str:
    """Pastilla de estado: fondo suave + forma + palabra."""
    _, fondo, letra = TONOS[tono]
    ico = icono(tono, 11 if not grande else 12, letra) if con_icono else ""
    return (f'<span class="tfi-chip{" grande" if grande else ""}" style="background:{fondo};color:{letra}">'
            f'{ico}{texto}</span>')


def etiqueta_materia(materia: str) -> str:
    """Etiqueta ALG / AED / PYE con el tinte de la materia."""
    sigla = SIGLAS.get(materia, materia)
    fondo, letra = TINTES_MATERIA.get(sigla, ("#EBE9E4", "#35332D"))
    return f'<span class="tfi-materia" style="background:{fondo};color:{letra}">{sigla}</span>'


def cuadrito(color: str) -> str:
    return f'<span class="tfi-cuadrito" style="background:{color}"></span>'


def titulo_materia(materia: str, sub: str = "") -> str:
    """Encabezado de un bloque por materia: cuadrito de color + nombre (+ dato a la derecha)."""
    extra = f'<span class="sub num">{sub}</span>' if sub else ""
    return (f'<p class="tfi tfi-titulo-materia">{cuadrito(COLORES_MATERIA.get(materia, NEUTRO))}'
            f'{materia}{extra}</p>')


def leyenda(items: list[tuple[str, str, str]]) -> str:
    """items = [(texto, color, forma)], forma en punto | cuadro | linea."""
    marcas = {"punto": "width:10px;height:10px;border-radius:999px", "cuadro": "width:11px;height:11px;border-radius:2px",
              "linea": "width:18px;height:2px"}
    partes = [f'<span class="item"><span style="{marcas[forma]};background:{color};display:inline-block"></span>'
              f'{texto}</span>' for texto, color, forma in items]
    return f'<div class="tfi tfi-leyenda">{"".join(partes)}</div>'


def aviso(texto_html: str, tono: str = "atencion") -> str:
    """Recuadro de aviso con forma + texto (para conclusiones o advertencias de lectura)."""
    marca, fondo, letra = TONOS[tono]
    borde = {"atencion": "#F0E2C4", "critico": "#F2CFC9", "bien": "#CFE3D8", "info": "#D4E1F1"}.get(tono, BORDE)
    return (f'<div class="tfi tfi-aviso" style="background:{fondo};border-color:{borde}">'
            f'{icono(tono, 16, marca)}<p style="color:{letra}">{texto_html}</p></div>')


# ---------------------------------------------------------------------------
# Componentes visuales
# ---------------------------------------------------------------------------
def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página, la pregunta que responde y los filtros que se están usando."""
    f = filtros()
    st.title(titulo)
    if descripcion:
        html(f'<p class="tfi tfi-texto" style="max-width:68ch;margin:-6px 0 6px">{descripcion}</p>')
    st.caption(f":gray-badge[:material/event: Datos al {fmt_fecha(f.fecha_corte)}] "
               f":gray-badge[{f.materia}] "
               f":gray-badge[Inactivo después de {f.umbral} días sin entrar]")
    return f


def tarjetas(items: list, columnas: int | None = None) -> None:
    """Fila de tarjetas de KPI. Cada item es (etiqueta, valor) o
    (etiqueta, valor, ayuda) o un dict con las claves de st.metric."""
    items = [it if isinstance(it, dict) else dict(zip(["label", "value", "help"], it)) for it in items]
    cols = st.columns(columnas or len(items))
    for i, it in enumerate(items):
        cols[i % len(cols)].metric(border=True, **it)


def semaforo(condicion: str, detalle: str = "") -> str:
    """HTML del semáforo: color + forma + texto (nunca solo color, D48)."""
    extra = f" · {detalle}" if detalle else ""
    return chip(f"{condicion}{extra}", TONO_CONDICION.get(condicion, "neutro"), grande=True)


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

