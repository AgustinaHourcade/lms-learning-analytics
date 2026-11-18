"""
Piezas compartidas por todas las páginas de la app (Etapa 4).

  Datos        datos() y metrica(): gold se lee una vez y cada métrica se cachea (D47).
  Filtros      barra_lateral() dibuja la fecha de corte, la materia y el umbral (D46);
               filtros() los devuelve desde cualquier página.
  Paleta       COLORES_* e ICONOS_*: un color fijo por materia, condición y estado (D48).
  Visuales     encabezado(), tarjetas(), semaforo(), boton_csv(), num(), pct().
  Piezas HTML  pintar(), forma(), swatch(), etiqueta_materia(), barra(): bloques del
               sistema visual (clases tc-* del CSS) armados como texto.

Una página típica:

    import componentes as comp
    f = comp.encabezado("Rendimiento académico", "Notas y condición a la fecha de corte.")
    notas = comp.metrica("nota_final")          # usa la fecha, la materia y el umbral de la barra
    comp.tarjetas([("Alumnos", comp.num(len(notas))), ...])
"""
from __future__ import annotations

import html
import inspect
import os
import re
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
# Sistema visual (D48, rediseño de la maqueta "Ficha individual · rediseño"): base cálida, un azul de acción, un color
# por materia y el semáforo. Regla de fondo: el estado nunca se comunica solo
# con color, siempre color + forma + palabra.
# ---------------------------------------------------------------------------
FONDO, TARJETA, BORDE, BORDE_SUAVE, PISTA = "#F7F6F3", "#FFFFFF", "#E3E1DC", "#EFEDE8", "#EDEBE6"
TEXTO, TEXTO_2, TEXTO_3, TEXTO_4 = "#1A1917", "#57544C", "#6B6861", "#8A867C"   # de más a menos fuerte
ACCION = "#1B4B8F"

# Materias: el color identifica (nunca evalúa). Los 3 primeros de la categórica.
CATEGORICA = ["#2563C9", "#D4661F", "#0E8F62", "#C98A12", "#9B5BB5", "#2F8F9D", "#C2456E", "#6B6861"]
COLORES_MATERIA = {"Álgebra": "#2563C9", "Algoritmos y Estructuras de Datos": "#D4661F",
                   "Probabilidad y Estadística": "#0E8F62"}
COLORES_MATERIA = {m: COLORES_MATERIA.get(m, c) for m, c in zip(ASIGNATURAS, CATEGORICA)}
# Etiqueta de materia (fondo, texto)
ETIQUETA_MATERIA = {"Álgebra": ("#EAF0F8", "#164279"), "Algoritmos y Estructuras de Datos": ("#FBEFE6", "#8A4415"),
                    "Probabilidad y Estadística": ("#E6F2EB", "#0B6B49")}
SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}


def nombre_materia_corto(materia: str) -> str:
    """'Probabilidad y Estadística' -> 'Probabilidad' (para tarjetas chicas)."""
    return materia.split(" ")[0]


# Semáforo: de mejor a peor, en el mismo orden en toda la app.
BIEN, ATENCION, CRITICO, TERMINAL = "#16734A", "#C98A12", "#B02A20", "#3C3A34"
SERIO, NEUTRO = "#D9822B", "#A8A49B"
COLORES_CONDICION = {"Promociona": BIEN, "Regular": ATENCION, "Libre": CRITICO, SIN_EVALUACIONES: NEUTRO}
TEXTO_CONDICION = {"Promociona": "#116040", "Regular": "#7A5000", "Libre": "#93241C", SIN_EVALUACIONES: TEXTO_2}
FONDO_CONDICION = {"Promociona": "#E6F2EB", "Regular": "#FBF0DC", "Libre": "#FBE9E6", SIN_EVALUACIONES: "#EBE9E4"}
ICONOS_CONDICION = {"Promociona": "🟢", "Regular": "🟡", "Libre": "🔴", SIN_EVALUACIONES: "⚪"}  # para texto plano
COLORES_ACTIVIDAD = {ACTIVO: BIEN, INACTIVO: SERIO, SIN_ACTIVIDAD: NEUTRO}
ICONOS_ACTIVIDAD = {ACTIVO: "🟢", INACTIVO: "🟠", SIN_ACTIVIDAD: "⚪"}
# Texto de valores buenos / flojos / malos (la versión oscura de cada color del semáforo).
VERDE, AMBAR, ROJO = TEXTO_CONDICION["Promociona"], TEXTO_CONDICION["Regular"], TEXTO_CONDICION["Libre"]

# Secuencial (mapas de calor): un solo tono (el azul de Álgebra/acción), de claro a oscuro.
SECUENCIAL = ["#EAF0F8", "#C3D5EE", "#93B4E2", "#5F8FD3", "#2563C9", "#1B4B8F", "#123663"]

# Plantilla de plotly: fondo transparente (va dentro de tarjetas), Inter y grilla tenue.
pio.templates["tfi"] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family="Inter, system-ui, sans-serif", color=TEXTO_2, size=12),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#F1EFEA", linecolor="#D9D6CF", zerolinecolor="#D9D6CF"),
    yaxis=dict(gridcolor="#F1EFEA", linecolor="#D9D6CF", zerolinecolor="#D9D6CF"),
    margin=dict(t=48, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    hoverlabel=dict(font_size=13, font_family="Inter, sans-serif", bgcolor=TARJETA, bordercolor=BORDE),
))
pio.templates.default = "plotly_white+tfi"

CSS = f"""
<style>
  /* Base */
  .num, [data-testid="stMetricValue"] {{font-variant-numeric: tabular-nums;}}
  .block-container {{padding-top: 3.5rem; max-width: 1240px;}}
  h1, h2, h3 {{letter-spacing: -.01em;}}
  [data-testid="stCaptionContainer"] {{color: {TEXTO_3};}}

  /* Tarjetas: cualquier st.container(key="tarjeta_...") y los st.metric con borde */
  [class*="st-key-tarjeta"] {{background:{TARJETA}; border:1px solid {BORDE}; border-radius:13px; padding:18px;}}
  [data-testid="stMetric"] {{background:{TARJETA}; border-color:{BORDE} !important; border-radius:13px !important;}}
  [data-testid="stMetricValue"] {{font-family:'Space Grotesk', Inter, sans-serif; font-size:1.75rem; font-weight:600;}}

  /* Opciones destacadas: st.container(key="opcion_...") con un checkbox o toggle */
  [class*="st-key-opcion"] {{background:#EAF0F8; border:1px solid #DCE5F1; border-radius:10px; padding:10px 12px;}}
  [class*="st-key-opcion"] label p {{font-size:12px; font-weight:500; color:#164279;}}

  /* Pestañas */
  [data-testid="stTab"] {{height:42px; padding:0 16px;}}
  [data-testid="stTab"] p {{font-size:14px; font-weight:500; color:{TEXTO_2};}}
  [data-testid="stTab"][aria-selected="true"] p {{font-weight:600; color:{ACCION};}}

  /* Botones secundarios: blancos con borde, como en el diseño */
  [data-testid="stBaseButton-secondary"] {{background:{TARJETA}; border-color:#D4D1CA; color:#2C2A25;}}

  /* Encabezado de página */
  .tc-titulo {{display:flex; flex-wrap:wrap; gap:6px 16px; align-items:baseline; justify-content:space-between;}}
  .tc-titulo h1 {{margin:0 0 5px; padding:0; font:600 27px 'Space Grotesk', Inter, sans-serif; letter-spacing:-.02em; color:{TEXTO};}}
  .tc-titulo p {{margin:0; max-width:72ch; font-size:13px; line-height:1.55; color:{TEXTO_2};}}
  .tc-pastilla {{display:inline-flex; align-items:center; gap:6px; height:28px; padding:0 11px; border-radius:999px;
                 background:#F1EFEA; font-size:12px; color:{TEXTO_2}; white-space:nowrap;}}

  /* Piezas HTML (tc- = "tablero"), siempre dentro de <div class="tc"> (lo pone pintar()):
     el prefijo les gana a los estilos de párrafo de Streamlit. */
  .tc .tc-fila {{display:flex; flex-wrap:wrap; gap:14px; margin-bottom:14px;}}
  .tc .tc-grilla {{display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:12px; margin-bottom:18px;}}
  .tc .tc-card {{background:{TARJETA}; border:1px solid {BORDE}; border-radius:13px; padding:18px 20px; min-width:0;}}
  .tc .tc-card.chica {{padding:15px;}}
  .tc .tc-card.alerta {{background:#FBE9E6; border-color:#F2CFC9;}}
  .tc .tc-card h3 {{margin:0; padding:0; font:600 16px 'Space Grotesk', Inter, sans-serif; color:{TEXTO};}}
  .tc .tc-card h4 {{margin:0 0 4px; padding:0; font:600 15px 'Space Grotesk', Inter, sans-serif; color:{TEXTO};}}
  .tc .tc-etiqueta {{margin:0 0 12px; font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:{TEXTO_3};}}
  .tc .tc-grande {{margin:0 0 3px; font:600 34px/1.15 'Space Grotesk', Inter, sans-serif; letter-spacing:-.02em; font-variant-numeric:tabular-nums;}}
  .tc .tc-medio {{font:600 22px/1.2 'Space Grotesk', Inter, sans-serif; font-variant-numeric:tabular-nums;}}
  .tc .tc-texto {{margin:0; font-size:12px; line-height:1.55; color:{TEXTO_2};}}
  .tc .tc-chico {{font-size:11px; color:{TEXTO_3}; font-weight:400;}}
  .tc .tc-aviso {{margin:0; padding:12px 14px; border-radius:10px; background:#FBF0DC; font-size:13px; line-height:1.6; color:#6B4700;}}
  .tc .tc-nota {{margin:0; padding:12px 14px; border-radius:10px; background:#FBFAF8; font-size:12px; line-height:1.6; color:{TEXTO_2};}}
  .tc .tc-swatch {{display:inline-block; width:9px; height:9px; border-radius:3px; flex:none;}}
  .tc .tc-sigla {{display:inline-flex; align-items:center; height:20px; padding:0 7px; border-radius:5px; font-size:11px; font-weight:600;}}
  .tc .tc-barra {{display:inline-block; height:8px; border-radius:999px; background:{PISTA}; overflow:hidden; flex:none;}}
  .tc .tc-barra > span {{display:block; height:100%; border-radius:999px;}}
  .tc .tc-leyenda {{display:flex; flex-wrap:wrap; gap:16px;}}
  .tc .tc-leyenda span {{display:inline-flex; align-items:center; gap:7px; font-size:12px; font-weight:500;}}
  .tc .tc-tabla {{overflow-x:auto;}}
  .tc .tc-tabla table {{border-collapse:collapse; width:100%; margin:0; border:none;}}
  .tc .tc-tabla th {{font-size:11px; letter-spacing:.05em; text-transform:uppercase; color:{TEXTO_3}; font-weight:600;
                 text-align:left; padding:10px 12px; border:none; border-bottom:1px solid {BORDE}; white-space:nowrap; background:none;}}
  .tc .tc-tabla td {{font-size:13px; color:#2C2A25; padding:11px 12px; border:none; border-bottom:1px solid {BORDE_SUAVE};
                 vertical-align:middle; white-space:nowrap; font-variant-numeric:tabular-nums;}}
  .tc .tc-tabla tbody tr:last-child td {{border-bottom:none;}}
  .tc .tc-tabla tr.tenue td {{background:#FBFAF8;}}

  /* Semáforo */
  .semaforo {{display:inline-flex; align-items:center; gap:6px; height:24px; padding:0 10px; border-radius:999px;
              font-size:12px; font-weight:600;}}
</style>
"""


def estilos() -> None:
    """El CSS del sistema visual, inyectado una sola vez desde Inicio.py."""
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
def pintar(codigo_html: str) -> None:
    """Dibuja un bloque de HTML del sistema visual. Va en una sola línea para
    que el markdown de Streamlit no lo interprete (sangrías = bloque de código)."""
    st.markdown('<div class="tc">' + re.sub(r"\s*\n\s*", " ", codigo_html).strip() + "</div>",
                unsafe_allow_html=True)


def esc(texto) -> str:
    return html.escape(str(texto), quote=True)


def encabezado(titulo: str, descripcion: str = "", acciones=None) -> Filtros:
    """Título de la página, descripción y, abajo, los filtros que se están usando.
    `acciones`: función sin argumentos que dibuja botones a la derecha del título
    (por ejemplo, descargas)."""
    f = filtros()
    descripcion = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", descripcion)  # admite **negrita**
    bloque = (f'<div class="tc-titulo"><div><h1>{esc(titulo)}</h1>'
              + (f"<p>{descripcion}</p>" if descripcion else "") + "</div></div>")
    if acciones:
        izq, der = st.columns([3, 2], vertical_alignment="center")
        with izq:
            pintar(bloque)
        with der, st.container(horizontal=True, horizontal_alignment="right"):
            acciones()
    else:
        pintar(bloque)
    st.caption(f"Corte: **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
               f"Inactivo después de {f.umbral} días sin entrar")
    return f


# --- Piezas HTML chicas (devuelven texto para armar bloques más grandes) ----
_FORMAS = {  # el estado nunca solo con color: círculo, triángulo, octágono, cuadrado
    "Promociona": '<circle cx="8" cy="8" r="6.6"/>',
    "Regular": '<path d="M8 1.6l6.6 11.8H1.4z"/>',
    "Libre": '<path d="M5.2 1.4h5.6l3.8 3.8v5.6l-3.8 3.8H5.2l-3.8-3.8V5.2z"/>',
}


def forma(condicion: str, color: str | None = None, tam: int = 12) -> str:
    """Ícono SVG de la condición (forma + color)."""
    figura = _FORMAS.get(condicion, '<rect x="2" y="2" width="12" height="12" rx="2"/>')
    color = color or COLORES_CONDICION.get(condicion, TERMINAL)
    return (f'<svg viewBox="0 0 16 16" width="{tam}" height="{tam}" aria-hidden="true" '
            f'style="fill:{color}; flex:none">{figura}</svg>')


def swatch(materia: str, tam: int = 9) -> str:
    return (f'<span class="tc-swatch" style="background:{COLORES_MATERIA.get(materia, NEUTRO)};'
            f'width:{tam}px;height:{tam}px"></span>')


def etiqueta_materia(materia: str) -> str:
    """Etiqueta chica con la sigla (ALG / AED / PYE) en los colores de la materia."""
    fondo, texto = ETIQUETA_MATERIA.get(materia, ("#F1EFEA", TEXTO_2))
    return f'<span class="tc-sigla" style="background:{fondo};color:{texto}">{SIGLAS.get(materia, materia)}</span>'


def barra(pct_valor, color: str, ancho: int | str = 80, alto: int = 8) -> str:
    """Barra de avance horizontal (0-100). `ancho` en px o como texto CSS ('100%')."""
    v = 0 if pct_valor is None or pd.isna(pct_valor) else max(0.0, min(100.0, float(pct_valor)))
    css = f"{ancho}px" if isinstance(ancho, int) else f"{ancho};display:block"
    return (f'<span class="tc-barra" style="width:{css};height:{alto}px">'
            f'<span style="width:{v:.1f}%;background:{color}"></span></span>')


def aclarar(color: str, t: float = 0.78) -> str:
    """Mezcla un color con blanco (t = cuánto blanco): para rellenos suaves."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#{:02X}{:02X}{:02X}".format(*(round(c + (255 - c) * t) for c in (r, g, b)))


def tarjetas(items: list, columnas: int | None = None) -> None:
    """Fila de tarjetas de KPI. Cada item es (etiqueta, valor) o
    (etiqueta, valor, ayuda) o un dict con las claves de st.metric."""
    items = [it if isinstance(it, dict) else dict(zip(["label", "value", "help"], it)) for it in items]
    cols = st.columns(columnas or len(items))
    for i, it in enumerate(items):
        cols[i % len(cols)].metric(border=True, **it)


def semaforo(condicion: str, detalle: str = "") -> str:
    """HTML del semáforo: color + forma + texto (nunca solo color, D48)."""
    fondo = FONDO_CONDICION.get(condicion, "#EBE9E4")
    texto = TEXTO_CONDICION.get(condicion, TERMINAL)
    extra = f" · {esc(detalle)}" if detalle else ""
    return (f'<span class="semaforo" style="background:{fondo};color:{texto}">'
            f'{forma(condicion)}{esc(condicion)}{extra}</span>')


def mostrar_semaforo(condicion: str, detalle: str = "") -> None:
    pintar(semaforo(condicion, detalle))


def con_icono(serie: pd.Series, iconos: dict) -> pd.Series:
    """Para tablas: 'Libre' -> '🔴 Libre'."""
    return serie.map(lambda v: f"{iconos.get(v, '')} {v}".strip())


def nombre_corto(instrumento: str) -> str:
    """Para ejes y leyendas: saca los emojis y espacios del principio
    ('👉  Actividad Rápida 1' -> 'Actividad Rápida 1')."""
    return re.sub(r"^\W+", "", str(instrumento)).strip()


def boton_csv(df: pd.DataFrame, nombre: str, etiqueta: str = "Descargar CSV") -> None:
    """Descarga en CSV que abre bien en Excel en castellano (separador ; y UTF-8 con BOM)."""
    st.download_button(etiqueta, df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=nombre if nombre.endswith(".csv") else f"{nombre}.csv",
                       mime="text/csv", icon=":material/download:")

