"""
Piezas compartidas por todas las páginas de la app (Etapa 4).

  Datos        datos() y metrica(): gold se lee una vez y cada métrica se cachea (D47).
  Filtros      barra_lateral() dibuja la fecha de corte, la materia y el umbral (D46);
               filtros() los devuelve desde cualquier página.
  Paleta       COLORES_*, TONOS e ICONOS_*: un color fijo por materia, condición y estado (D48, D51).
  Visuales     encabezado(), tarjetas(), tarjeta(), semaforo(), boton_csv(), num(), pct().
  Piezas HTML  html(), kpi(), barra_apilada(), barra_simple(), leyenda(), delta(), aviso(),
               forma(), etiqueta_materia(): el sistema visual del rediseño, en HTML liviano.

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
# Sistema visual (D48, rediseño D51)
#   - El color de materia IDENTIFICA, el del semáforo EVALÚA: nunca se mezclan
#     en el mismo elemento.
#   - El color nunca va solo: el semáforo repite el estado con forma
#     (círculo, triángulo, octágono, cuadrado) y texto.
# ---------------------------------------------------------------------------
# Base (también en .streamlit/config.toml)
FONDO, TARJETA, BORDE, BORDE_SUAVE = "#F7F6F3", "#FFFFFF", "#E3E1DC", "#EFEDE8"
TEXTO, TEXTO_2, TEXTO_3, TENUE, ACCION = "#1A1917", "#57544C", "#6B6861", "#8A867C", "#1B4B8F"
FUENTE = "Inter, system-ui, sans-serif"
FUENTE_TITULOS = "'Space Grotesk', Inter, sans-serif"

# Categórica, en orden fijo: las 3 primeras son las materias (en el orden de ASIGNATURAS).
CATEGORICA = ["#2563C9", "#D4661F", "#0E8F62", "#7A5AC8", "#C2407A", "#5C7C8A", "#A68A1E", "#3C3A34"]
COLORES_MATERIA = dict(zip(ASIGNATURAS, CATEGORICA))
SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}
NOMBRES_CORTOS = {"Álgebra": "Álgebra", "Algoritmos y Estructuras de Datos": "Algoritmos",
                  "Probabilidad y Estadística": "Probabilidad"}
# Etiqueta de materia: fondo claro y texto oscuro del mismo tono.
ETIQUETA_MATERIA = dict(zip(ASIGNATURAS, [("#EAF0F8", "#164279"), ("#FBEFE6", "#8A4415"), ("#E6F2EB", "#0B6B49")]))

# Estados: (relleno, fondo claro, texto). Reservados para evaluar.
BIEN, ATENCION, CRITICO, NEUTRO = "#16734A", "#C98A12", "#B02A20", "#3C3A34"
TONOS = {
    "bien": (BIEN, "#E6F2EB", "#116040"),
    "atencion": (ATENCION, "#FBF0DC", "#7A5000"),
    "critico": (CRITICO, "#FBE9E6", "#93241C"),
    "neutro": (NEUTRO, "#EBE9E4", "#35332D"),
}
TONO_CONDICION = {"Promociona": "bien", "Regular": "atencion", "Libre": "critico", SIN_EVALUACIONES: "neutro"}
TONO_ACTIVIDAD = {ACTIVO: "bien", INACTIVO: "atencion", SIN_ACTIVIDAD: "neutro"}
COLORES_CONDICION = {c: TONOS[t][0] for c, t in TONO_CONDICION.items()}
COLORES_ACTIVIDAD = {c: TONOS[t][0] for c, t in TONO_ACTIVIDAD.items()}
# Para tablas y textos planos, donde no entra el SVG.
ICONOS_CONDICION = {"Libre": "🔴", "Regular": "🟡", "Promociona": "🟢", SIN_EVALUACIONES: "⚪"}
ICONOS_ACTIVIDAD = {ACTIVO: "🟢", INACTIVO: "🟠", SIN_ACTIVIDAD: "⚪"}

# Secuencial (mapas de calor): un solo tono, de claro a oscuro, sobre el azul de acción.
SECUENCIAL = ["#E4ECF6", "#C3D4EA", "#97B4DA", "#6A93C7", "#3F70B0", "#1B4B8F", "#0F2F5C"]

# Plantilla de plotly: fondo blanco (el gráfico vive en una tarjeta blanca),
# grilla tenue y la paleta categórica.
pio.templates["tfi"] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family=FUENTE, color=TEXTO_2, size=12),
    paper_bgcolor=TARJETA, plot_bgcolor=TARJETA,
    xaxis=dict(gridcolor="#F1EFEA", linecolor="#D9D6CF", tickcolor="#D9D6CF", tickfont=dict(color=TEXTO_3),
               title_font=dict(color=TENUE, size=11), zeroline=False),
    yaxis=dict(gridcolor="#F1EFEA", linecolor="#D9D6CF", tickfont=dict(color=TEXTO_3),
               title_font=dict(color=TENUE, size=11), zeroline=False),
    margin=dict(t=40, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=TEXTO, size=12), title_text=""),
    hoverlabel=dict(font=dict(family=FUENTE, size=13), bgcolor="white", bordercolor=BORDE),
))
pio.templates.default = "plotly_white+tfi"

CSS = f"""
<style>
  /* Títulos y números grandes en Space Grotesk; el resto, Inter (config.toml). */
  h1 {{font-size: 27px !important; letter-spacing: -.02em; font-weight: 600 !important;}}
  h2 {{font-size: 20px !important; letter-spacing: -.01em;}}
  h3 {{font-size: 15px !important;}}
  .block-container {{padding-top: 2.2rem; max-width: 1240px;}}
  .num {{font-variant-numeric: tabular-nums;}}

  /* Tarjetas: st.container(border=True) y st.metric se ven como las tarjetas HTML. */
  [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]),
  div[class*="st-key-tarjeta"] {{background: {TARJETA}; border-radius: 13px;}}
  [data-testid="stMetric"] {{background: {TARJETA}; border-radius: 13px; padding: 15px 16px;}}
  [data-testid="stMetricLabel"] p {{font-size: 11px; font-weight: 600; letter-spacing: .06em;
                                   text-transform: uppercase; color: {TEXTO_3};}}
  [data-testid="stMetricValue"] {{font-family: {FUENTE_TITULOS}; font-size: 24px; font-weight: 600;}}

  /* Pestañas subrayadas, como en el diseño. */
  [data-baseweb="tab-list"] {{gap: 4px; border-bottom: 1px solid {BORDE};}}
  [data-baseweb="tab"] {{height: 42px; padding: 0 16px;}}
  [data-baseweb="tab"] p {{font-size: 14px; font-weight: 500; color: {TEXTO_2};}}
  [data-baseweb="tab"][aria-selected="true"] p {{font-weight: 600; color: {ACCION};}}

  /* Barra lateral: navegación con el ítem activo en azul claro y el bloque de filtros en tarjeta. */
  [data-testid="stSidebarNav"] a[aria-current="page"] {{background: #EAF0F8;}}
  [data-testid="stSidebarNav"] a[aria-current="page"] span {{color: {ACCION}; font-weight: 600;}}
  [data-testid="stSidebarNavSeparator"] {{display: none;}}
  .st-key-filtros {{background: {TARJETA}; border-radius: 12px;}}

  /* Tarjeta de alerta (roja clara) */
  .st-key-tarjeta_alerta {{background: #FBE9E6 !important; border-color: #F2CFC9 !important;}}
  .st-key-tarjeta_alerta a p {{color: #93241C; font-weight: 600;}}

  /* Piezas HTML (ver las funciones de abajo) */
  .tfi {{font-family: {FUENTE}; color: {TEXTO};}}
  .tfi p {{margin: 0;}}
  .tfi-etq {{font: 600 11px {FUENTE}; letter-spacing: .06em; text-transform: uppercase; color: {TEXTO_3};}}
  .tfi-txt {{font: 400 12px/1.55 {FUENTE}; color: {TEXTO_2};}}
  .tfi-tenue {{font: 400 11px {FUENTE}; color: {TENUE};}}
  .tfi-h3 {{font: 600 15px {FUENTE_TITULOS}; color: {TEXTO}; margin: 0 0 4px !important;}}
  .tfi-grande {{font: 600 24px {FUENTE_TITULOS}; color: {TEXTO}; font-variant-numeric: tabular-nums;}}
  .tfi-tarjeta {{background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 13px; padding: 18px;}}
  .tfi-barra {{display: flex; border-radius: 7px; overflow: hidden;}}
  .tfi-barra > div {{display: flex; align-items: center; justify-content: center; overflow: hidden;
                     font: 600 12px {FUENTE}; color: #fff; white-space: nowrap; font-variant-numeric: tabular-nums;}}
  .tfi-leyenda {{display: flex; flex-wrap: wrap; gap: 6px 16px;}}
  .tfi-leyenda span {{display: inline-flex; align-items: center; gap: 6px; font: 500 11px {FUENTE};}}
  .tfi-chip {{display: inline-flex; align-items: center; gap: 7px; height: 26px; padding: 0 10px;
              border-radius: 999px; font: 600 12px {FUENTE}; white-space: nowrap;}}
  .tfi-materia {{display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 5px;
                 font: 600 11px {FUENTE};}}
  .tfi-aviso {{display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; border-radius: 12px;
               font: 400 13px/1.6 {FUENTE};}}
  .tfi-fila {{display: flex; align-items: baseline; justify-content: space-between; padding: 9px 0;
              border-top: 1px solid {BORDE_SUAVE}; font: 400 12px {FUENTE}; color: {TEXTO_2};}}
  .tfi-fila b {{font: 600 13px {FUENTE}; color: {TEXTO}; font-variant-numeric: tabular-nums;}}
  .tfi-delta {{display: inline-flex; align-items: center; gap: 5px; font: 600 12px {FUENTE};
               font-variant-numeric: tabular-nums;}}
</style>
"""


def estilos() -> None:
    """El CSS del sistema visual, inyectado una sola vez desde Inicio.py."""
    st.html(CSS)


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

    with st.sidebar, st.container(border=True, key="filtros"):
        st.html(f'<p class="tfi-etq" style="font:600 11px {FUENTE};letter-spacing:.06em;'
                f'text-transform:uppercase;color:{TEXTO_3};margin:0">Filtros</p>')
        fecha = st.date_input("Fecha de corte", min_value=inicio, max_value=fin, key="fecha_corte",
                              format="DD/MM/YYYY",
                              help="Todo se calcula con lo que se sabía ese día (inclusive): notas de los "
                                   "instrumentos ya tomados, actividad hasta esa fecha.")
        materia = st.selectbox("Materia", [TODAS, *ASIGNATURAS], key="materia")
        umbral = st.slider("Inactivo después de (días sin entrar)", 1, 30, key="umbral",
                           help="Un alumno que no entra hace más de estos días cuenta como inactivo (D35).")
        st.button("Restablecer filtros", on_click=_restablecer, width="stretch")
    st.sidebar.caption(f"Datos del {fmt_fecha(inicio)} al {fmt_fecha(fin)}.")

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
        st.html(f'<p class="tfi" style="margin:-6px 0 0;max-width:72ch;font:400 13px/1.55 {FUENTE};'
                f'color:{TEXTO_2}">{descripcion}</p>')
    st.caption(f"Datos al **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
               f"Inactivo después de {f.umbral} días sin entrar")
    return f


def tarjetas(items: list, columnas: int | None = None) -> None:
    """Fila de tarjetas de KPI. Cada item es (etiqueta, valor) o
    (etiqueta, valor, ayuda) o un dict con las claves de st.metric."""
    items = [it if isinstance(it, dict) else dict(zip(["label", "value", "help"], it)) for it in items]
    cols = st.columns(columnas or len(items))
    for i, it in enumerate(items):
        cols[i % len(cols)].metric(border=True, **it)


def grafico(fig, **kwargs) -> None:
    """st.plotly_chart con la plantilla de la app. Los fondos se fijan en el layout
    porque el tema de Streamlit los pisa aunque se pase theme=None."""
    fig.update_layout(paper_bgcolor=TARJETA, plot_bgcolor=TARJETA)
    st.plotly_chart(fig, width="stretch", theme=None, **kwargs)


def tarjeta(nombre: str, **kwargs):
    """Contenedor con borde y fondo blanco: `with comp.tarjeta("notas"):`.
    `nombre` tiene que ser único en la página (se usa como key)."""
    return st.container(border=True, key=f"tarjeta_{nombre}", **kwargs)


# ---------------------------------------------------------------------------
# Piezas HTML del sistema visual. Devuelven texto: se combinan y se pintan con
# comp.html(...). Todos los números pasan por num()/pct() (coma decimal).
# ---------------------------------------------------------------------------
# Formas del semáforo hechas con CSS (st.html filtra los <svg>): un span del color
# del texto recortado con clip-path o border-radius.
_FORMAS = {
    "bien": "border-radius:50%",
    "atencion": "clip-path:polygon(50% 4%,100% 92%,0 92%)",
    "critico": "clip-path:polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%)",
    "neutro": "border-radius:22%;transform:scale(.85)",
}


def html(*partes: str) -> None:
    """Pinta piezas HTML (sin scripts) dentro de la página."""
    st.html('<div class="tfi">' + "".join(partes) + "</div>")


def forma(tono: str, tam: int = 12) -> str:
    """Ícono del semáforo: círculo (bien), triángulo (atención), octágono (crítico), cuadrado (neutro)."""
    return (f'<span aria-hidden="true" style="display:inline-block;width:{tam}px;height:{tam}px;'
            f'flex:0 0 {tam}px;background:currentColor;{_FORMAS[tono]}"></span>')


def semaforo(condicion: str, detalle: str = "") -> str:
    """Chip del semáforo: color + forma + texto (nunca solo color)."""
    _, fondo, texto = TONOS[TONO_CONDICION.get(condicion, "neutro")]
    extra = f" · {detalle}" if detalle else ""
    return (f'<span class="tfi-chip" style="background:{fondo};color:{texto}">'
            f'{forma(TONO_CONDICION.get(condicion, "neutro"))}{condicion}{extra}</span>')


def mostrar_semaforo(condicion: str, detalle: str = "") -> None:
    html(semaforo(condicion, detalle))


def etiqueta_materia(materia: str) -> str:
    fondo, texto = ETIQUETA_MATERIA.get(materia, ("#EBE9E4", "#35332D"))
    return f'<span class="tfi-materia" style="background:{fondo};color:{texto}">{SIGLAS.get(materia, materia)}</span>'


def cuadradito(color: str, tam: int = 9) -> str:
    return (f'<span style="width:{tam}px;height:{tam}px;border-radius:3px;background:{color};'
            f'display:inline-block;flex:0 0 {tam}px"></span>')


def barra_apilada(segmentos: list, alto: int = 30, min_etiqueta: float = 9) -> str:
    """Barra 100 % apilada. segmentos: [(porcentaje, color, etiqueta), ...].
    La etiqueta se escribe solo si el tramo mide al menos `min_etiqueta` %."""
    total = sum(p for p, _, _ in segmentos if p and p > 0) or 1
    tramos = []
    for p, color, etiqueta in segmentos:
        if not p or p <= 0:
            continue
        ancho = p / total * 100
        texto = etiqueta if ancho >= min_etiqueta else ""
        tramos.append(f'<div style="width:{ancho:.2f}%;background:{color}" title="{etiqueta}">{texto}</div>')
    return f'<div class="tfi-barra" style="height:{alto}px">{"".join(tramos)}</div>'


def barra_simple(pct_: float, color: str, alto: int = 22) -> str:
    ancho = 0 if pct_ is None or pd.isna(pct_) else max(0.0, min(100.0, pct_))
    return (f'<span style="flex:1 1 auto;height:{alto}px;border-radius:5px;background:#EDEBE6;overflow:hidden;'
            f'display:inline-block"><span style="display:block;width:{ancho:.1f}%;height:100%;'
            f'background:{color}"></span></span>')


def leyenda(items: list) -> str:
    """items: [(color, texto, color_del_texto | None), ...]."""
    partes = [f'<span style="color:{tc or TEXTO}">{cuadradito(c, 10)}{t}</span>' for c, t, tc in items]
    return f'<div class="tfi-leyenda">{"".join(partes)}</div>'


def delta(valor, unidad: str = "pp", mejor: str = "sube", decimales: int = 1) -> str:
    """Variación con flecha. `mejor` = "sube", "baja" o "neutro" decide si se pinta
    verde (mejora) o roja (empeora). Sin dato devuelve ""."""
    if valor is None or pd.isna(valor):
        return ""
    if round(valor, decimales) == 0:
        return f'<span class="tfi-delta" style="color:{TEXTO_3}">= sin cambios</span>'
    sube = valor > 0
    if mejor == "neutro":
        color = TEXTO_2
    else:
        color = TONOS["bien" if sube == (mejor == "sube") else "critico"][2]
    flecha = "polygon(50% 10%,100% 80%,0 80%)" if sube else "polygon(0 20%,100% 20%,50% 90%)"
    signo = "+" if sube else "−"
    return (f'<span class="tfi-delta" style="color:{color}"><span aria-hidden="true" style="display:inline-block;'
            f'width:10px;height:10px;background:currentColor;clip-path:{flecha}"></span>'
            f'{signo}{num(abs(valor), decimales)} {unidad}</span>')


def kpi(etiqueta: str, valor: str, pie: str = "", sufijo: str = "") -> str:
    """Tarjeta chica de KPI: etiqueta, número grande y una línea de pie (texto o delta)."""
    sufijo = f' <span style="font:400 13px {FUENTE};color:{TENUE}">{sufijo}</span>' if sufijo else ""
    pie = f'<p class="tfi-txt num" style="margin-top:4px">{pie}</p>' if pie else ""
    return (f'<div class="tfi-tarjeta" style="padding:15px;height:100%">'
            f'<p class="tfi-etq" style="margin-bottom:8px">{etiqueta}</p>'
            f'<p class="tfi-grande">{valor}{sufijo}</p>{pie}</div>')


def aviso(texto: str, tono: str = "atencion") -> str:
    """Recuadro de lectura rápida, con la forma del tono a la izquierda."""
    relleno, fondo, color = TONOS[tono]
    borde = {"atencion": "#F0E2C4", "critico": "#F2CFC9", "bien": "#CFE5D8", "neutro": BORDE}[tono]
    return (f'<div class="tfi-aviso" style="background:{fondo};border:1px solid {borde};color:{color}">'
            f'<span style="color:{relleno};margin-top:3px;display:inline-flex">{forma(tono, 15)}</span>'
            f'<p style="margin:0">{texto}</p></div>')


def con_icono(serie: pd.Series, iconos: dict) -> pd.Series:
    """Para tablas: 'Libre' -> '🔴 Libre'."""
    return serie.map(lambda v: f"{iconos.get(v, '')} {v}".strip())


def boton_csv(df: pd.DataFrame, nombre: str, etiqueta: str = "Descargar CSV") -> None:
    """Descarga en CSV que abre bien en Excel en castellano (separador ; y UTF-8 con BOM)."""
    st.download_button(etiqueta, df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=nombre if nombre.endswith(".csv") else f"{nombre}.csv",
                       mime="text/csv", icon=":material/download:")

