"""
Piezas compartidas por todas las páginas de la app (Etapa 4).

  Datos        datos() y metrica(): gold se lee una vez y cada métrica se cachea (D47).
  Filtros      barra_lateral() dibuja la fecha de corte, la materia y el umbral (D46);
               filtros() los devuelve desde cualquier página.
  Paleta       COLORES_* e ICONOS_*: un color fijo por materia, condición y estado (D48).
  Visuales     encabezado(), tarjetas(), semaforo(), boton_csv(), num(), pct().
  Diseño       TOKENS/TONOS + CSS global; cabecera(), kpis(kpi(...)), tarjeta(), chip(),
               barra_apilada(), leyenda(), tabla_html(). Las usa el predictor de abandono
               (app/paginas/ml_abandono.py), que es el modelo para rediseñar las demás páginas.

Una página típica:

    import componentes as comp
    f = comp.encabezado("Rendimiento académico", "Notas y condición a la fecha de corte.")
    notas = comp.metrica("nota_final")          # usa la fecha, la materia y el umbral de la barra
    comp.tarjetas([("Alumnos", comp.num(len(notas))), ...])
"""
from __future__ import annotations

import html as html_lib
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

from src import metricas, ml_abandono, ml_grupos  # noqa: E402
from src.config import (ASIGNATURAS, FECHA_CORTE_DEFECTO, GOLD, SIN_EVALUACIONES,  # noqa: E402
                        UMBRAL_INACTIVIDAD_DIAS)
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD  # noqa: E402

# ---------------------------------------------------------------------------
# Paleta (D48). Valores validados para daltonismo (skill de dataviz).
# ---------------------------------------------------------------------------
# Categórica, en orden fijo: los 3 primeros sirven para cualquier gráfico
# (también dispersión), así que cada materia tiene uno.
CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
COLORES_MATERIA = dict(zip(ASIGNATURAS, CATEGORICA))
SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}

# Estados: colores reservados, siempre acompañados de ícono y texto.
BIEN, ATENCION, SERIO, CRITICO, NEUTRO = "#0ca30c", "#fab219", "#ec835a", "#d03b3b", "#898781"
COLORES_CONDICION = {"Libre": CRITICO, "Regular": ATENCION, "Promociona": BIEN, SIN_EVALUACIONES: NEUTRO}
ICONOS_CONDICION = {"Libre": "🔴", "Regular": "🟡", "Promociona": "🟢", SIN_EVALUACIONES: "⚪"}
COLORES_ACTIVIDAD = {ACTIVO: BIEN, INACTIVO: SERIO, SIN_ACTIVIDAD: NEUTRO}
ICONOS_ACTIVIDAD = {ACTIVO: "🟢", INACTIVO: "🟠", SIN_ACTIVIDAD: "⚪"}
# ---------------------------------------------------------------------------
# Sistema de diseño (rediseño a partir del predictor de abandono)
# Los colores de base están también en .streamlit/config.toml.
# ---------------------------------------------------------------------------
TOKENS = dict(
    fondo="#F7F6F3", superficie="#FFFFFF", superficie_2="#FBFAF8", lateral="#FCFBF9",
    borde="#E3E1DC", borde_suave="#EFEDE8", borde_input="#D9D6CF",
    tinta="#1A1917", texto="#2C2A25", texto_2="#57544C", texto_3="#6B6861", texto_4="#8A867C",
    azul="#1B4B8F", azul_hover="#123663", azul_suave="#EAF0F8", azul_texto="#164279",
)
FUENTE = "Inter, system-ui, sans-serif"
FUENTE_TITULOS = "'Space Grotesk', Inter, system-ui, sans-serif"

# Tonos de estado: fondo y borde de la tarjeta, texto sobre ese fondo y color "fuerte"
# (barras, puntos). Siempre van con ícono y texto, nunca solo color (D48).
TONOS = {
    "alto":     dict(fondo="#FBE9E6", borde="#F2CFC9", texto="#93241C", fuerte="#B02A20", suave="#E9C3BE"),
    "medio":    dict(fondo="#FBF0DC", borde="#F0E2C4", texto="#7A5000", fuerte="#C98A12", suave="#EED9AE"),
    "naranja":  dict(fondo="#FCEDE3", borde="#F3D3BE", texto="#8A4415", fuerte="#D4661F", suave="#F0C9AE"),
    "bajo":     dict(fondo="#E6F2EA", borde="#C9E3D3", texto="#116040", fuerte="#16734A", suave="#B9DCC6"),
    "abandono": dict(fondo="#EBE9E4", borde="#D9D6CF", texto="#35332D", fuerte="#3C3A34", suave="#C9C6BE"),
    "neutro":   dict(fondo="#F1EFEA", borde="#E3E1DC", texto="#57544C", fuerte="#A8A49B", suave="#DAD7D0"),
    "azul":     dict(fondo="#EAF0F8", borde="#D3E0F0", texto="#164279", fuerte="#1B4B8F", suave="#C5D9EF"),
}
# Insignia de cada materia (mismo matiz que su color categórico).
TONOS_MATERIA = {"ALG": dict(fondo="#EAF0F8", texto="#164279"), "AED": dict(fondo="#FBEFE6", texto="#8A4415"),
                 "PYE": dict(fondo="#E6F2EA", texto="#116040")}

# Riesgo de abandono (D58): nivel del predictor o estado si no hace falta predecir.
TONO_RIESGO = {ml_abandono.ALTO: "alto", ml_abandono.MEDIO: "medio", ml_abandono.BAJO: "bajo",
               ml_abandono.YA_ABANDONO: "abandono", ml_abandono.SIN_ACTIVIDAD: "neutro"}
COLORES_RIESGO = {nivel: TONOS[tono]["fuerte"] for nivel, tono in TONO_RIESGO.items()}
ICONOS_RIESGO = {ml_abandono.ALTO: "🔴", ml_abandono.MEDIO: "🟡", ml_abandono.BAJO: "🟢",
                 ml_abandono.YA_ABANDONO: "⚫", ml_abandono.SIN_ACTIVIDAD: "⚪"}

# Secuencial (mapas de calor): un solo tono, de claro a oscuro.
SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Plantilla de plotly (usar st.plotly_chart(..., theme=None) para que Streamlit no la pise;
# el fondo lo vuelve transparente el CSS, así toma el de la tarjeta),
# grilla tenue cálida, tipografía Inter y la paleta categórica.
pio.templates["tfi"] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family=FUENTE, color=TOKENS["texto_2"], size=12),
    title=dict(font=dict(family=FUENTE_TITULOS, size=15, color=TOKENS["tinta"])),
    paper_bgcolor=TOKENS["superficie"], plot_bgcolor=TOKENS["superficie"],
    xaxis=dict(gridcolor=TOKENS["borde_suave"], linecolor=TOKENS["borde_input"], zerolinecolor=TOKENS["borde"]),
    yaxis=dict(gridcolor=TOKENS["borde_suave"], linecolor=TOKENS["borde_input"], zerolinecolor=TOKENS["borde"]),
    margin=dict(t=48, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    hoverlabel=dict(font_size=13, font_family=FUENTE),
))
pio.templates.default = "plotly_white+tfi"

_T = TOKENS
CSS = f"""
<style>
  /* --- Estructura general ------------------------------------------------ */
  [data-testid="stMainBlockContainer"] {{padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1240px;}}
  [data-testid="stHeader"] {{background: transparent;}}
  h1, h2, h3, h4 {{font-family: {FUENTE_TITULOS}; letter-spacing: -.01em;}}
  /* Streamlit pinta el fondo de plotly con el de la página: que tome el de su tarjeta. */
  [data-testid="stPlotlyChart"] .main-svg {{background: transparent !important;}}
  [data-testid="stPlotlyChart"] .bglayer .bg {{fill: transparent !important;}}

  /* --- Menú lateral ------------------------------------------------------ */
  [data-testid="stSidebar"] {{border-right: 1px solid {_T['borde']};}}
  [data-testid="stNavSectionHeader"] {{font: 600 10px {FUENTE} !important; letter-spacing: .08em;
      text-transform: uppercase; color: {_T['texto_4']} !important;}}
  [data-testid="stNavSectionHeader"] * {{font: inherit !important; color: inherit !important;}}
  a[data-testid="stSidebarNavLink"] {{border-radius: 8px;}}
  a[data-testid="stSidebarNavLink"] span {{font-weight: 500; color: {_T['texto']};}}
  a[data-testid="stSidebarNavLink"][aria-current="page"] {{background: {_T['azul_suave']};}}
  a[data-testid="stSidebarNavLink"][aria-current="page"] span {{color: {_T['azul']}; font-weight: 600;}}
  .st-key-filtros_card {{background: {_T['superficie']}; border: 1px solid {_T['borde']}; border-radius: 12px;
      padding: 14px;}}

  /* --- Tarjetas que contienen widgets: st.container(key="tfi_<tono>_<nombre>") */
  [class*="st-key-tfi_blanco_"], [class*="st-key-tfi_ambar_"], [class*="st-key-tfi_verde_"] {{
      border-radius: 13px; padding: 18px; border: 1px solid {_T['borde']}; background: {_T['superficie']};}}
  [class*="st-key-tfi_ambar_"] {{background: {TONOS['medio']['fondo']}; border-color: {TONOS['medio']['borde']};}}
  [class*="st-key-tfi_verde_"] {{background: {TONOS['bajo']['fondo']}; border-color: {TONOS['bajo']['borde']};}}
  [class*="st-key-tfi_ambar_"] button {{border-color: {TONOS['medio']['fuerte']}; color: #6B4700; font-weight: 600;}}
  [class*="st-key-tfi_verde_"] button {{border-color: {TONOS['bajo']['fuerte']}; color: {TONOS['bajo']['texto']};
      font-weight: 600;}}

  /* --- Tarjeta con encabezado de color: st.container(key="tfi_g_<tono>_<nombre>") */
  [class*="st-key-tfi_g_"] {{background: {_T['superficie']}; border: 1px solid {_T['borde']}; border-radius: 13px;
      overflow: hidden; padding: 0 18px 18px; gap: 0;}}
  [class*="st-key-tfi_g_"] button {{margin-top: 10px;}}
  .tfi-ghead {{margin: 0 -18px 14px; padding: 16px 18px 14px;}}
  .tfi-ghead .nom {{margin: 0 0 10px; display: flex; align-items: center; gap: 9px; font: 600 15px {FUENTE_TITULOS};}}
  .tfi-ghead .big {{font: 600 32px {FUENTE_TITULOS}; letter-spacing: -.02em; font-variant-numeric: tabular-nums;}}
  .tfi-ghead .pct {{font: 500 13px {FUENTE}; margin-left: 10px;}}
  .tfi-dato {{display: flex; align-items: baseline; justify-content: space-between; padding: 6px 0;
      border-bottom: 1px solid {_T['borde_suave']}; font: 400 12px {FUENTE}; color: {_T['texto_2']};}}
  .tfi-dato b {{font: 600 13px {FUENTE}; color: {_T['tinta']}; font-variant-numeric: tabular-nums;}}
  .tfi-accion {{margin-top: 14px; padding: 11px 13px; border-radius: 10px; font: 500 12px/1.55 {FUENTE};}}
  .tfi-accion strong {{font-weight: 600; color: {_T['tinta']};}}
  .tfi-fila {{display: flex; align-items: center; gap: 12px; margin-bottom: 12px;}}
  .tfi-fila > .et {{flex: 0 0 96px; font: 600 12px {FUENTE}; color: {_T['tinta']};}}
  .tfi-fila > .bar {{flex: 1 1 auto; display: flex; height: 30px; border-radius: 7px; overflow: hidden;
      background: {_T['borde_suave']};}}
  .tfi-fila.chica {{margin-bottom: 5px; gap: 10px;}}
  .tfi-fila.chica > .et {{font: 400 11px {FUENTE}; color: {_T['texto_2']};}}
  .tfi-fila.chica > .bar {{height: 20px; border-radius: 4px;}}
  .tfi-fila .bar > span {{display: flex; align-items: center; justify-content: center; overflow: hidden;
      font: 600 12px {FUENTE}; color: #FFFFFF; font-variant-numeric: tabular-nums; white-space: nowrap;}}
  .tfi-fila.chica .bar > span {{font-size: 10px;}}
  .tfi-div {{display: flex; align-items: center; gap: 8px; margin-bottom: 4px;}}
  .tfi-div > .et {{flex: 0 0 110px; font: 400 11px {FUENTE}; color: {_T['texto_2']};}}
  .tfi-div > .bar {{flex: 1 1 auto; height: 13px; position: relative; display: block;}}
  .tfi-div > .bar > i {{position: absolute; top: 0; height: 100%; display: block;}}
  .tfi-div > .val {{flex: 0 0 36px; text-align: right; font: 500 11px {FUENTE}; font-variant-numeric: tabular-nums;}}
  .tfi-eje {{padding: 13px 14px; border: 1px solid {_T['borde']}; border-radius: 11px; margin-bottom: 10px;}}
  .tfi-eje p {{margin: 0; font: 400 12px/1.55 {FUENTE}; color: {_T['texto_2']};}}
  .tfi-eje p.t {{margin: 0 0 5px; font-weight: 600; color: {_T['tinta']};}}
  .tfi-et {{margin: 0 0 12px; font: 600 11px {FUENTE}; letter-spacing: .06em; text-transform: uppercase;
      color: {_T['texto_3']};}}

  /* --- Piezas de HTML propio --------------------------------------------- */
  .tfi {{font-family: {FUENTE}; color: {_T['tinta']};}}
  .tfi-h1 {{margin: 0 0 6px; font: 600 27px {FUENTE_TITULOS}; letter-spacing: -.02em; color: {_T['tinta']};}}
  .tfi-lead {{margin: 0; max-width: 80ch; font: 400 13.5px/1.6 {FUENTE}; color: {_T['texto_2']};}}
  .tfi-lead strong, .tfi-p strong {{font-weight: 600; color: {_T['tinta']};}}
  .tfi-pills {{display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px;}}
  .tfi-pill {{display: inline-flex; align-items: center; height: 26px; padding: 0 10px; border-radius: 999px;
      background: #F1EFEA; font: 500 12px {FUENTE}; color: {_T['texto_2']};}}
  .tfi-h3 {{margin: 0 0 4px; font: 600 15px {FUENTE_TITULOS}; color: {_T['tinta']}; display: flex;
      align-items: center; gap: 8px;}}
  .tfi-sub {{margin: 0 0 16px; font: 400 12px/1.55 {FUENTE}; color: {_T['texto_2']};}}
  .tfi-p {{margin: 0; font: 400 12.5px/1.6 {FUENTE}; color: {_T['texto_2']};}}
  .tfi-nota {{margin: 0; padding: 12px 14px; border-radius: 10px; background: {_T['superficie_2']};
      font: 400 12px/1.6 {FUENTE}; color: {_T['texto_2']};}}
  .tfi-nota strong {{font-weight: 600; color: {_T['tinta']};}}
  .tfi-card {{background: {_T['superficie']}; border: 1px solid {_T['borde']}; border-radius: 13px; padding: 18px;}}
  .num {{font-variant-numeric: tabular-nums;}}

  .tfi-chips {{display: flex; flex-wrap: wrap; gap: 6px;}}
  .tfi-chip {{display: inline-flex; align-items: center; min-height: 26px; padding: 2px 11px; border-radius: 999px;
      font: 500 12px/1.3 {FUENTE};}}
  .tfi-chip.sm {{min-height: 22px; padding: 2px 8px; font-size: 11px;}}
  .tfi-badge {{display: inline-flex; align-items: center; height: 20px; padding: 0 7px; border-radius: 5px;
      font: 600 11px {FUENTE};}}

  .tfi-kpis {{display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px;}}
  .tfi-kpi {{border-radius: 13px; padding: 15px; border: 1px solid {_T['borde']}; background: {_T['superficie']};}}
  .tfi-kpi .et {{margin: 0 0 8px; display: flex; align-items: center; gap: 7px; font: 600 11px {FUENTE};
      letter-spacing: .06em; text-transform: uppercase; color: {_T['texto_3']};}}
  .tfi-kpi .val {{margin: 0 0 4px; font: 600 26px {FUENTE_TITULOS}; color: {_T['tinta']};
      font-variant-numeric: tabular-nums;}}
  .tfi-kpi .det {{margin: 0; font: 400 12px/1.45 {FUENTE}; color: {_T['texto_3']};}}

  .tfi-stack-et {{margin: 0 0 7px; display: flex; align-items: baseline; justify-content: space-between;
      font: 600 12px {FUENTE}; color: {_T['tinta']};}}
  .tfi-stack-et span {{font: 400 11px {FUENTE}; color: {_T['texto_3']};}}
  .tfi-stack {{display: flex; height: 26px; border-radius: 6px; overflow: hidden; margin-bottom: 6px;
      background: {_T['borde_suave']};}}
  .tfi-stack > span {{display: flex; align-items: center; justify-content: center; font: 600 11px {FUENTE};
      color: #FFFFFF; font-variant-numeric: tabular-nums; min-width: 0; overflow: hidden;}}
  .tfi-stack-nota {{margin: 0 0 16px; font: 400 11px {FUENTE}; color: {_T['texto_3']};}}
  .tfi-leyenda {{display: flex; flex-wrap: wrap; gap: 14px; padding-top: 14px; border-top: 1px solid {_T['borde_suave']};}}
  .tfi-leyenda span {{display: inline-flex; align-items: center; gap: 6px; font: 500 11px {FUENTE};}}
  .tfi-leyenda i {{width: 10px; height: 10px; border-radius: 2px; display: inline-block;}}

  .tfi-tabla-wrap {{overflow: auto; max-height: 460px; border-top: 1px solid {_T['borde_suave']};}}
  .tfi-tabla {{border-collapse: collapse; width: 100%;}}
  .tfi-tabla th {{position: sticky; top: 0; background: {_T['superficie']}; z-index: 1; font: 600 11px {FUENTE};
      letter-spacing: .05em; text-transform: uppercase; color: {_T['texto_3']}; text-align: left;
      padding: 10px 12px; border-bottom: 1px solid {_T['borde']}; white-space: nowrap;}}
  .tfi-tabla td {{font: 400 13px {FUENTE}; color: {_T['texto']}; padding: 10px 12px; vertical-align: middle;
      border-bottom: 1px solid {_T['borde_suave']}; white-space: nowrap;}}
  .tfi-tabla td.wrap {{white-space: normal; min-width: 340px;}}
  .tfi-tabla tbody tr:last-child td {{border-bottom: none;}}
  .tfi-tabla tbody tr:hover td {{background: {_T['superficie_2']};}}
  .tfi-tabla .sec {{font: 400 11px {FUENTE}; color: {_T['texto_3']};}}
  .tfi-meter {{display: flex; align-items: center; gap: 9px;}}
  .tfi-meter > span:first-child {{flex: 0 0 56px; height: 8px; border-radius: 999px; background: #EDEBE6;
      overflow: hidden; display: inline-block;}}
  .tfi-meter > span:first-child > span {{display: block; height: 100%;}}
  .tfi-pie {{margin: 10px 0 0; font: 400 11.5px/1.55 {FUENTE}; color: {_T['texto_3']};}}

  /* --- Semáforo de condición (Ficha) -------------------------------------- */
  .semaforo {{display:inline-flex; align-items:center; gap:.4rem; padding:.25rem .7rem; border-radius:999px;
             font-weight:600; border:1px solid rgba(11,11,11,.10);}}
  .semaforo-Libre      {{background:#fde8e8; color:#8a1f1f;}}
  .semaforo-Regular    {{background:#fff4d6; color:#6b4a00;}}
  .semaforo-Promociona {{background:#e2f6e2; color:#006300;}}
  .semaforo-otro       {{background:#f0efec; color:#52514e;}}
  [data-testid="stMetric"] {{background: {_T['superficie']};}}
  [data-testid="stMetric"] [data-testid="stMetricValue"] {{font-size: 1.9rem; font-family: {FUENTE_TITULOS};}}
</style>
"""


def estilos() -> None:
    """CSS global del sistema de diseño y el logo del menú. Se llama una vez, desde Inicio.py."""
    # Sin líneas en blanco: el markdown cortaría el bloque <style> en la primera.
    st.markdown("\n".join(linea for linea in CSS.splitlines() if linea.strip()), unsafe_allow_html=True)
    st.logo(str(Path(__file__).parent / "assets" / "logo.svg"), size="large")


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


# Módulos donde metrica() busca la función, en este orden.
MODULOS = [metricas, ml_grupos, ml_abandono]


def _funcion(nombre: str):
    for modulo in MODULOS:
        if hasattr(modulo, nombre):
            return getattr(modulo, nombre)
    raise AttributeError(f"No hay ninguna métrica llamada {nombre!r} en {[m.__name__ for m in MODULOS]}")


@st.cache_resource(max_entries=1, show_spinner="Cargando el predictor de abandono (la primera vez se entrena)…")
def _modelo_abandono(version: str) -> ml_abandono.ModeloAbandono:
    """El predictor de abandono, leído con joblib una sola vez (D58). Se guarda
    junto a gold; si los datos cambiaron, cargar_modelo lo reentrena."""
    return ml_abandono.cargar_modelo(_datos(version), ml_abandono.ruta_modelo(carpeta_gold()))


def modelo_abandono() -> ml_abandono.ModeloAbandono:
    return _modelo_abandono(version_gold())


@st.cache_data(max_entries=500, show_spinner="Calculando…")
def _metrica(nombre: str, version: str, args: tuple, kwargs: tuple):
    funcion, kwargs = _funcion(nombre), dict(kwargs)
    if "modelo" in inspect.signature(funcion).parameters:   # funciones del predictor de abandono
        kwargs.setdefault("modelo", _modelo_abandono(version))
    return funcion(_datos(version), *args, **kwargs)


def metrica(nombre: str, *args, **kwargs):
    """Llama a `src.metricas.<nombre>` (o a `src.ml_grupos` / `src.ml_abandono`) con la caché de la app.
    Si la función recibe fecha_corte, asignatura o umbral y no se pasan, usa los de la barra lateral.
    Ejemplos: metrica("nota_final"), metrica("evolucion_actividad", frecuencia="M"),
              metrica("nota_final", asignatura=None)   # todas, ignorando la barra"""
    parametros = inspect.signature(_funcion(nombre)).parameters
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

    with st.sidebar, st.container(key="filtros_card"):
        st.html(f'<p class="tfi" style="margin:0;font:600 11px {FUENTE};letter-spacing:.06em;'
                f'text-transform:uppercase;color:{TOKENS["texto_3"]}">Filtros</p>')
        fecha = st.date_input("Fecha de corte", min_value=inicio, max_value=fin, key="fecha_corte",
                              format="DD/MM/YYYY",
                              help="Todo se calcula con lo que se sabía ese día (inclusive): notas de los "
                                   "instrumentos ya tomados, actividad hasta esa fecha.")
        materia = st.selectbox("Materia", [TODAS, *ASIGNATURAS], key="materia")
        umbral = st.slider("Inactivo después de (días sin entrar)", 1, 30, key="umbral",
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
# Sistema de diseño: piezas de HTML (devuelven texto; se dibujan con st.html)
# ---------------------------------------------------------------------------
# Forma distinta por tono: el estado se entiende sin color. Se dibujan con CSS (clip-path)
# porque st.html descarta los <svg>.
_FORMAS = {
    "alto": "clip-path:polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%)",
    "medio": "clip-path:polygon(50% 4%,100% 92%,0 92%)",
    "naranja": "clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%)",
    "bajo": "border-radius:50%",
    "abandono": "border-radius:22%",
    "neutro": "border-radius:50%;background:transparent !important;box-shadow:inset 0 0 0 1.6px currentColor",
    "azul": "border-radius:50%",
}


def esc(texto) -> str:
    """Escapa texto que viene de los datos antes de meterlo en HTML."""
    return html_lib.escape("" if texto is None else str(texto))


def icono(tono: str, tam: int = 12) -> str:
    return (f'<span aria-hidden="true" style="display:inline-block;flex:none;width:{tam}px;height:{tam}px;'
            f'background:currentColor;{_FORMAS.get(tono, _FORMAS["neutro"])}"></span>')


def chip(texto: str, tono: str = "azul", chico: bool = False, titulo: str = "") -> str:
    t = TONOS[tono]
    extra = f' title="{esc(titulo)}"' if titulo else ""
    return (f'<span class="tfi-chip{" sm" if chico else ""}" style="background:{t["fondo"]};color:{t["texto"]}"'
            f'{extra}>{texto}</span>')


def insignia_materia(asignatura: str) -> str:
    sigla = SIGLAS.get(asignatura, asignatura)
    t = TONOS_MATERIA.get(sigla, TONOS["neutro"])
    return (f'<span class="tfi-badge" style="background:{t["fondo"]};color:{t["texto"]}" '
            f'title="{esc(asignatura)}">{esc(sigla)}</span>')


def kpi(etiqueta: str, valor: str, detalle: str = "", tono: str | None = None) -> str:
    """Tarjeta de indicador. Con tono (alto, medio, abandono…) se pinta y lleva su ícono."""
    if tono:
        t = TONOS[tono]
        caja = f'background:{t["fondo"]};border-color:{t["borde"]}'
        return (f'<div class="tfi-kpi" style="{caja}"><p class="et" style="color:{t["texto"]}">{icono(tono)}'
                f'{etiqueta}</p><p class="val" style="color:{t["texto"]}">{valor}</p>'
                f'<p class="det" style="color:{t["texto"]}">{detalle}</p></div>')
    return (f'<div class="tfi-kpi"><p class="et">{etiqueta}</p><p class="val">{valor}</p>'
            f'<p class="det">{detalle}</p></div>')


def kpis(tarjetas_html: list[str]) -> None:
    st.html(f'<div class="tfi tfi-kpis">{"".join(tarjetas_html)}</div>')


def cabecera(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página (estilo nuevo), bajada en HTML y los filtros en uso como píldoras.
    Reemplaza a encabezado() en las páginas rediseñadas."""
    f = filtros()
    pills = [f"Datos al {fmt_fecha(f.fecha_corte)}", f.materia, f"Inactivo después de {f.umbral} días"]
    st.html(f'<div class="tfi"><h1 class="tfi-h1">{titulo}</h1>'
            + (f'<p class="tfi-lead">{descripcion}</p>' if descripcion else "")
            + '<div class="tfi-pills">' + "".join(f'<span class="tfi-pill">{esc(p)}</span>' for p in pills)
            + "</div></div>")
    return f


def tarjeta(nombre: str, tono: str = "blanco"):
    """Contenedor con estilo de tarjeta para poner widgets adentro (blanco, ambar o verde).
    Uso: with comp.tarjeta("umbral"): st.slider(...)."""
    return st.container(key=f"tfi_{tono}_{nombre}")


def titulo_tarjeta(titulo: str, subtitulo: str = "", icono_tono: str | None = None) -> str:
    ico = icono(icono_tono, 15) if icono_tono else ""
    sub = f'<p class="tfi-sub">{subtitulo}</p>' if subtitulo else ""
    return f'<h3 class="tfi-h3">{ico}{titulo}</h3>{sub}'


def barra_apilada(etiqueta: str, total, segmentos: list[tuple[str, int, str]], nota: str = "",
                  nota_tono: str | None = None) -> str:
    """Una barra 100 % apilada. segmentos = [(nombre, cantidad, color)]; la cantidad se escribe
    adentro si el tramo es lo bastante ancho."""
    suma = sum(n for _, n, _ in segmentos) or 1
    tramos = []
    for nombre, n, color in segmentos:
        if not n:
            continue
        ancho = 100 * n / suma
        texto = num(n) if ancho >= 6 else ""
        tramos.append(f'<span style="width:{ancho:.2f}%;background:{color}" title="{esc(nombre)}: {num(n)}">'
                      f'{texto}</span>')
    estilo = f' style="color:{TONOS[nota_tono]["texto"]};font-weight:500"' if nota_tono else ""
    return (f'<p class="tfi-stack-et">{esc(etiqueta)} <span class="num">{num(total)}</span></p>'
            f'<div class="tfi-stack">{"".join(tramos)}</div>'
            + (f'<p class="tfi-stack-nota num"{estilo}>{nota}</p>' if nota else '<div style="height:12px"></div>'))


def tarjeta_color(nombre: str, tono: str):
    """Contenedor con el borde del tono; adentro, encabezado_color() pinta la franja de arriba."""
    return st.container(key=f"tfi_g_{tono}_{nombre}")


def encabezado_color(titulo: str, numero: str, detalle: str, tono: str) -> str:
    t = TONOS[tono]
    return (f'<div class="tfi tfi-ghead" style="background:{t["fondo"]}"><p class="nom" style="color:{t["texto"]}">'
            f'<span style="color:{t["fuerte"]};display:flex">{icono(tono, 15)}</span>{esc(titulo)}</p>'
            f'<span class="big" style="color:{t["texto"]}">{numero}</span>'
            f'<span class="pct num" style="color:{t["texto"]}">{detalle}</span></div>')


def fila_barra(etiqueta: str, segmentos: list[tuple[str, float, str, str]], chica: bool = False) -> str:
    """Etiqueta a la izquierda y barra 100 % apilada. segmentos = [(nombre, valor, color, texto adentro)];
    el texto se oculta si el tramo es muy angosto."""
    suma = sum(v for _, v, _, _ in segmentos) or 1
    tramos = "".join(
        f'<span style="width:{100 * v / suma:.2f}%;background:{c}" title="{esc(n)}: {esc(tx)}">'
        f'{tx if 100 * v / suma >= (9 if chica else 7) else ""}</span>'
        for n, v, c, tx in segmentos if v)
    return (f'<div class="tfi-fila{" chica" if chica else ""}"><span class="et">{esc(etiqueta)}</span>'
            f'<span class="bar">{tramos}</span></div>')


def barra_divergente(etiqueta: str, valor: float, color: str, tope: float = 2.0) -> str:
    """Barra que sale del centro hacia la derecha (+) o la izquierda (−). Para desvíos."""
    ancho = 50 * min(abs(valor), tope) / tope
    lado = "left" if valor >= 0 else "right"
    peso = 600 if abs(valor) >= 1 else 500
    signo = num(valor, 1) if valor < 0 else f"+{num(valor, 1)}"
    return (f'<div class="tfi-div"><span class="et">{esc(etiqueta)}</span><span class="bar">'
            f'<i style="left:50%;width:1px;background:{TOKENS["borde_input"]}"></i>'
            f'<i style="{lado}:50%;width:{ancho:.1f}%;background:{color};border-radius:3px"></i></span>'
            f'<span class="val" style="font-weight:{peso}">{signo.replace("-", "−")}</span></div>')


def leyenda(items: list[tuple[str, str]]) -> str:
    """items = [(texto, tono)]: cuadradito del color fuerte + texto en el color de texto del tono."""
    return ('<div class="tfi-leyenda">' + "".join(
        f'<span style="color:{TONOS[t]["texto"]}"><i style="background:{TONOS[t]["fuerte"]}"></i>{esc(x)}</span>'
        for x, t in items) + "</div>")


def tabla_html(encabezados: list[str], filas: list[list[str]], clases: list[str] | None = None) -> str:
    """Tabla con el estilo del sistema. Las celdas ya vienen en HTML (escapar lo que venga de datos)."""
    clases = clases or [""] * len(encabezados)
    cab = "".join(f'<th scope="col">{h}</th>' for h in encabezados)
    cuerpo = "".join("<tr>" + "".join(f'<td class="{c}">{v}</td>' for c, v in zip(clases, fila)) + "</tr>"
                     for fila in filas)
    return (f'<div class="tfi tfi-tabla-wrap"><table class="tfi-tabla"><thead><tr>{cab}</tr></thead>'
            f'<tbody>{cuerpo}</tbody></table></div>')


# ---------------------------------------------------------------------------
# Predictor de abandono (D58): bloques para la Ficha individual y Matrícula y alertas
# ---------------------------------------------------------------------------
def texto_riesgo(fila) -> str:
    """'🔴 Alto · 42 %' o '⚫ Ya abandonó' (ícono + texto, nunca solo color)."""
    nivel = fila["nivel_riesgo"]
    prob = f" · {pct(fila['probabilidad'], 0)}" if pd.notna(fila["probabilidad"]) else ""
    return f"{ICONOS_RIESGO.get(nivel, '')} {nivel}{prob}"


def riesgo_abandono_alumno(id_alumno: str) -> None:
    """Para la Ficha individual: el riesgo de abandono del alumno en cada materia,
    con los motivos y su evolución semana a semana. Uso: comp.riesgo_abandono_alumno(id)."""
    import plotly.express as px

    r = metrica("riesgo_alumno", id_alumno=id_alumno)
    if r.empty:
        st.caption("El alumno no está en la base de ninguna materia.")
        return
    umbral = 100 * metrica("info_modelo")["umbral"]
    cols = st.columns(len(r))
    for col, (_, fila) in zip(cols, r.iterrows()):
        with col.container(border=True):
            st.markdown(f"**{SIGLAS.get(fila['asignatura'], fila['asignatura'])}** · riesgo de abandono")
            st.markdown(f"### {texto_riesgo(fila)}")
            if fila["estado_abandono"] == ml_abandono.CURSANDO:
                st.caption(f"Probabilidad de no entrar en los próximos {ml_abandono.ABANDONO_HORIZONTE_DIAS} días "
                           f"(riesgo alto desde {pct(umbral, 0)}).")
                if fila["motivos"]:
                    st.markdown(f"Señales: {fila['motivos']}.")
            elif fila["estado_abandono"] == ml_abandono.YA_ABANDONO:
                st.caption(f"Hace {num(fila['dias_sin_actividad'])} días que no entra: ya cumple la definición "
                           "de abandono. Conviene contactarlo.")
            else:
                st.caption("Nunca entró al aula hasta la fecha de corte.")
    ev = metrica("evolucion_riesgo", id_alumno=id_alumno)
    ev = ev[ev["probabilidad"].notna()].assign(materia=lambda t: t["asignatura"].map(SIGLAS))
    if len(ev) > 1:
        fig = px.line(ev, x="fecha_corte", y="probabilidad", color="asignatura", markers=True,
                      color_discrete_map=COLORES_MATERIA,
                      labels={"fecha_corte": "", "probabilidad": "Probabilidad de abandono (%)", "asignatura": ""})
        fig.add_hline(y=umbral, line_dash="dash", line_color=CRITICO, annotation_text="Riesgo alto")
        fig.update_layout(height=280, yaxis_range=[0, 100])
        st.plotly_chart(fig, width="stretch")
        st.caption("Cada punto usa solo lo que se sabía ese día. Sin punto = ese día no venía entrando.")
