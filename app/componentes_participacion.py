"""
Sistema visual del dashboard de Participación (app/paginas/2_participacion.py).

Nació en la rama dashboard/participacion en paralelo al rediseño de main, con los mismos
nombres (TONOS, tarjeta(), chip(), chip_estado(), barra_apilada(), leyenda(), html(),
encabezado(), grafico()...) pero otras firmas y otro CSS. Para que convivan sin pisarse
(mismo criterio que General, Matrícula y Notas vs. participación), vive en este módulo aparte:

  - Reexporta todo lo de componentes (datos, metrica, filtros, boton_csv, tarjetas...) y
    redefine encima solo las piezas visuales propias. La página hace
    `import componentes_participacion as comp` y el resto de las páginas no se entera.
  - Sus clases CSS llevan el prefijo pa-*; el CSS se inyecta desde encabezado(), o sea
    solo en esta página.
  - Su plantilla de plotly ("tfi_participacion") se aplica en grafico().

Semáforo de 4 tonos (bien, atencion, critico, terminal + neutro), siempre color + forma +
palabra. El color de materia identifica y el del semáforo evalúa: no se mezclan (D48).
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from componentes import *  # noqa: F401,F403  (datos, metrica, filtros, boton_csv, tarjetas, TODAS, ...)
from componentes import Filtros, _rango_fechas, datos, filtros  # noqa: F401  (explícitos: _rango_fechas no entra en *)
from src.config import ASIGNATURAS, SIN_EVALUACIONES
from src.metricas import (ACTIVO, DESCONECTADO, ENFRIANDOSE, ESTADOS_ACTIVIDAD, INACTIVO, SIN_ACTIVIDAD,
                          TRAMOS_ACTIVIDAD)

PLANTILLA = "tfi_participacion"

# ---------------------------------------------------------------------------
# Paleta (D48, rediseño). Los mismos valores están en .streamlit/config.toml.
# ---------------------------------------------------------------------------
FONDO, TARJETA, BORDE, BORDE_SUAVE = "#F7F6F3", "#FFFFFF", "#E3E1DC", "#EFEDE8"
TEXTO, TEXTO_2, TEXTO_3, TEXTO_4 = "#1A1917", "#57544C", "#6B6861", "#8A867C"
ACCION = "#1B4B8F"
FUENTE = "Inter, system-ui, sans-serif"

# Materias: el color identifica, nunca evalúa (eso es del semáforo).
_MATERIA = {"ALG": "#2563C9", "AED": "#D4661F", "PYE": "#0E8F62"}
SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}
COLORES_MATERIA = {nombre: _MATERIA[sigla] for nombre, sigla in SIGLAS.items()}
CATEGORICA = [*COLORES_MATERIA.values(), "#C98A12", "#7A4FC4", "#B02A20", "#5E8C2F", "#C2457A"]

# Etiqueta de materia: fondo claro y texto oscuro del mismo tono.
ETIQUETA_MATERIA = {"ALG": ("#EAF0F8", "#164279"), "AED": ("#FBEFE6", "#8A4415"), "PYE": ("#E6F2EB", "#0B6B49")}

# Semáforo: cuatro tonos con un solo significado en toda la app. Cada uno tiene
# color, fondo, texto y una FORMA (círculo, triángulo, octágono, cuadrado), para
# que el estado nunca dependa solo del color. En tablas va el emoji de esa forma.
TONOS = {
    "bien":     {"color": "#16734A", "fondo": "#E6F2EB", "texto": "#116040", "emoji": "🟢"},
    "atencion": {"color": "#C98A12", "fondo": "#FBF0DC", "texto": "#7A5000", "emoji": "⚠️"},
    "critico":  {"color": "#B02A20", "fondo": "#FBE9E6", "texto": "#93241C", "emoji": "🛑"},
    "terminal": {"color": "#3C3A34", "fondo": "#EBE9E4", "texto": "#35332D", "emoji": "⬛"},
    "neutro":   {"color": "#8A867C", "fondo": "#F1EFEA", "texto": "#57544C", "emoji": "⚪"},
}
BIEN, ATENCION, CRITICO, TERMINAL, NEUTRO = (TONOS[k]["color"] for k in
                                             ("bien", "atencion", "critico", "terminal", "neutro"))
SERIO = CRITICO  # nombre viejo
TONO_ESTADO = {
    "Promociona": "bien", "Regular": "atencion", "Libre": "critico", SIN_EVALUACIONES: "neutro",
    ACTIVO: "bien", INACTIVO: "critico", SIN_ACTIVIDAD: "terminal", ENFRIANDOSE: "atencion", DESCONECTADO: "critico",
}


def _por_estado(estados, campo: str) -> dict:
    return {e: TONOS[TONO_ESTADO[e]][campo] for e in estados}


_CONDICIONES = ["Libre", "Regular", "Promociona", SIN_EVALUACIONES]
COLORES_CONDICION, ICONOS_CONDICION = _por_estado(_CONDICIONES, "color"), _por_estado(_CONDICIONES, "emoji")
COLORES_ACTIVIDAD, ICONOS_ACTIVIDAD = _por_estado(ESTADOS_ACTIVIDAD, "color"), _por_estado(ESTADOS_ACTIVIDAD, "emoji")
COLORES_TRAMO, ICONOS_TRAMO = _por_estado(TRAMOS_ACTIVIDAD, "color"), _por_estado(TRAMOS_ACTIVIDAD, "emoji")

# Secuencial (mapas de calor): un solo tono, de claro a oscuro.
SECUENCIAL = ["#E3EBF6", "#C3D4EC", "#97B5DE", "#6890CB", "#3E6DB3", "#1B4B8F", "#123663"]

# Plantilla de plotly: fondo blanco (va dentro de tarjetas blancas), grilla tenue,
# textos grises y la paleta categórica.
_EJE = dict(gridcolor="#F1EFEA", linecolor="#D9D6CF", zerolinecolor="#D9D6CF",
            tickfont=dict(color=TEXTO_3), title_font=dict(color=TEXTO_3, size=12))
pio.templates[PLANTILLA] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family=FUENTE, size=12, color=TEXTO_2),
    paper_bgcolor=TARJETA, plot_bgcolor=TARJETA,
    xaxis=_EJE, yaxis=_EJE,
    margin=dict(t=36, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=TEXTO, size=12)),
    hoverlabel=dict(font=dict(family=FUENTE, size=12, color=TEXTO), bgcolor=TARJETA, bordercolor=BORDE),
))

CSS = """
<style>
  /* Títulos y números grandes en Space Grotesk; etiquetas en mayúscula chica */
  .stApp h1 {letter-spacing: -.02em;}
  [data-testid="stMetric"] {background: #FFFFFF;}
  [data-testid="stMetricLabel"] p {font-size: 11px !important; font-weight: 600; letter-spacing: .06em;
                                   text-transform: uppercase; color: #6B6861;}
  [data-testid="stMetricValue"] {font-family: 'Space Grotesk', Inter, sans-serif; letter-spacing: -.01em;}
  [data-testid="stCaptionContainer"] {color: #6B6861;}
  /* Tarjetas: los st.container(border=True, key="tarjeta_...") van en blanco */
  [class*="st-key-tarjeta"] {background: #FFFFFF; border-radius: 13px;}
  [class*="st-key-alerta"] {background: #FBE9E6; border-color: #F2CFC9 !important; border-radius: 11px;}
  /* Pestañas */
  .stTabs [data-baseweb="tab"] p {font-weight: 600; font-size: 13px;}
  /* Menú lateral: la página actual, resaltada */
  [data-testid="stSidebarNav"] a[aria-current="page"] {background: #EAF0F8;}
  [data-testid="stSidebarNav"] a[aria-current="page"] span {color: #1B4B8F; font-weight: 600;}

  /* Piezas propias (las arman las funciones de abajo) */
  .pa {font-family: Inter, system-ui, sans-serif; color: #1A1917; font-variant-numeric: tabular-nums;}
  .pa p {margin: 0;}
  .pa-label {font: 600 11px Inter, sans-serif; letter-spacing: .06em; text-transform: uppercase; color: #6B6861;}
  .pa-h3 {margin: 0 0 4px !important; font: 600 15px 'Space Grotesk', Inter, sans-serif; color: #1A1917;}
  .pa-desc {max-width: 78ch; font: 400 12px/1.55 Inter, sans-serif; color: #57544C;}
  .pa-big {font: 600 40px/1.1 'Space Grotesk', Inter, sans-serif; letter-spacing: -.02em;}
  .pa-num {font: 600 22px/1.2 'Space Grotesk', Inter, sans-serif;}
  .pa-sub {font: 500 14px Inter, sans-serif; color: #57544C;}
  .pa-chip {display: inline-flex; align-items: center; gap: 6px; height: 26px; padding: 0 10px;
             border-radius: 999px; font: 600 12px Inter, sans-serif; white-space: nowrap;}
  .pa-mat {display: inline-flex; align-items: center; height: 20px; padding: 0 7px; border-radius: 5px;
            font: 600 11px Inter, sans-serif;}
  .pa-barra {display: flex; border-radius: 7px; overflow: hidden; background: #EDEBE6;}
  .pa-barra > div {display: flex; align-items: center; justify-content: center; min-width: 0; overflow: hidden;
                    font: 600 12px Inter, sans-serif; color: #FFFFFF;}
  .pa-leyenda {display: flex; flex-wrap: wrap; gap: 6px 18px;}
  .pa-leyenda > span {display: inline-flex; align-items: center; gap: 7px; font: 500 12px Inter, sans-serif;}
  .pa-nota {padding: 12px 14px; border-radius: 10px; font: 400 12px/1.6 Inter, sans-serif;}
  .pa-nota strong {font-weight: 600;}
  .pa-progreso {height: 7px; border-radius: 999px; background: #EDEBE6; overflow: hidden;}
  .pa-progreso > div {height: 100%; border-radius: 999px;}
  table.pa-tabla {border-collapse: collapse; width: 100%;}
  table.pa-tabla th {font: 600 11px Inter, sans-serif; letter-spacing: .05em; text-transform: uppercase;
                      color: #6B6861; text-align: left; padding: 10px 12px; border-bottom: 1px solid #E3E1DC;
                      background: none;}
  table.pa-tabla td {font-size: 13px; color: #2C2A25; padding: 12px; border: none;
                      border-bottom: 1px solid #EFEDE8; vertical-align: middle;}
  table.pa-tabla tbody tr:last-child td {border-bottom: none;}
  .pa-muted {color: #6B6861; font-size: 11px;}
</style>
"""


def rango_fechas() -> tuple[date, date]:
    """Primer y último día que se puede elegir (para filtros de fechas de una página)."""
    return _rango_fechas(datos())


# ---------------------------------------------------------------------------
# Formatos (en castellano: 1.234,5). Un vacío se escribe "—", nunca None.
# ---------------------------------------------------------------------------
VACIO = "—"


def num(x, decimales: int = 0) -> str:
    if x is None or pd.isna(x):
        return VACIO
    return f"{x:,.{decimales}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, decimales: int = 1) -> str:
    """x ya en porcentaje (52.07 -> '52,1 %')."""
    return VACIO if x is None or pd.isna(x) else f"{num(x, decimales)} %"


def fmt_fecha(x, formato: str = "%d/%m/%Y") -> str:
    return VACIO if x is None or pd.isna(x) else pd.Timestamp(x).strftime(formato)


# ---------------------------------------------------------------------------
# Componentes visuales
# ---------------------------------------------------------------------------
def html(contenido: str) -> None:
    """Dibuja HTML propio (chips, barras, tablas chicas). Usa las clases .pa-* del CSS."""
    st.html(contenido)


def estilos() -> None:
    """CSS de este dashboard. Se inyecta desde encabezado(), o sea solo en esta página."""
    st.markdown(CSS, unsafe_allow_html=True)


def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página, una línea que explica qué responde y los filtros en uso."""
    f = filtros()
    estilos()
    st.title(titulo)
    if descripcion:
        html(f'<p class="pa-desc" style="font-size:13px; max-width:90ch">{descripcion}</p>')
    st.caption(f"Corte: **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
               f"Inactivo después de {f.umbral} días sin entrar")
    return f


def tarjeta(clave: str, **kwargs):
    """Contenedor blanco con borde (las tarjetas del diseño). Usar con `with`."""
    return st.container(border=True, key=f"tarjeta_{clave}", **kwargs)


def titulo_seccion(titulo: str, descripcion: str = "") -> None:
    """Encabezado de una tarjeta: título en Space Grotesk y una línea de explicación."""
    desc = f'<p class="pa-desc">{descripcion}</p>' if descripcion else ""
    html(f'<div class="pa"><p class="pa-h3">{titulo}</p>{desc}</div>')


def etiqueta(texto: str) -> str:
    return f'<span class="pa-label">{texto}</span>'


# Formas del semáforo en CSS puro (st.html no deja pasar SVG): círculo,
# triángulo, octágono y cuadrado. Toman el color del texto que las rodea.
_FORMAS = {
    "bien": "border-radius:50%",
    "atencion": "clip-path:polygon(50% 4%,100% 92%,0 92%)",
    "critico": "clip-path:polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%)",
    "terminal": "border-radius:22%",
    "neutro": "border-radius:50%; background:none !important; box-shadow:inset 0 0 0 2px currentColor",
}


def forma(tono: str, tam: int = 12) -> str:
    """La forma del tono (círculo, triángulo, octágono o cuadrado), del color del texto."""
    return (f'<span aria-hidden="true" style="display:inline-block; flex:none; width:{tam}px; height:{tam}px; '
            f'background:currentColor; {_FORMAS[tono]}"></span>')


def chip(texto: str, tono: str = "neutro", con_forma: bool = True) -> str:
    """Píldora de estado: fondo claro, texto oscuro y la forma del tono."""
    t = TONOS[tono]
    icono = forma(tono, 11) if con_forma else ""
    return f'<span class="pa-chip" style="background:{t["fondo"]}; color:{t["texto"]}">{icono}{texto}</span>'


def chip_estado(estado: str, detalle: str = "") -> str:
    """Chip para una condición (Libre / Regular / Promociona) o un estado de actividad."""
    extra = f" · {detalle}" if detalle else ""
    return chip(f"{estado}{extra}", TONO_ESTADO.get(estado, "neutro"))


def etiqueta_materia(asignatura: str) -> str:
    sigla = SIGLAS.get(asignatura, asignatura)
    fondo, texto = ETIQUETA_MATERIA.get(sigla, (TONOS["neutro"]["fondo"], TEXTO_2))
    return f'<span class="pa-mat" style="background:{fondo}; color:{texto}">{sigla}</span>'


def punto_materia(asignatura: str) -> str:
    """Rayita del color de la materia, para leyendas y tablas."""
    return (f'<span style="display:inline-block; width:16px; height:3px; border-radius:2px; '
            f'background:{COLORES_MATERIA.get(asignatura, NEUTRO)}"></span>')


def barra_apilada(segmentos: list[tuple], alto: int = 28, numeros: bool = False) -> str:
    """Barra horizontal 100 %. segmentos = [(valor, color, texto_opcional), ...].
    Con numeros=True escribe el texto adentro si el tramo es ancho."""
    total = sum(s[0] for s in segmentos) or 1
    partes = []
    for valor, color, *texto in segmentos:
        ancho = valor / total * 100
        if ancho <= 0:
            continue
        dentro = texto[0] if (numeros and texto and ancho >= 7) else ""
        partes.append(f'<div style="width:{ancho:.2f}%; background:{color}">{dentro}</div>')
    return f'<div class="pa-barra" style="height:{alto}px">{"".join(partes)}</div>'


def leyenda(items: list[tuple]) -> str:
    """items = [(tono, html_del_texto), ...]: forma de color + texto, en una fila."""
    spans = "".join(f'<span style="color:{TONOS[tono]["texto"]}">{forma(tono, 13)}{texto}</span>'
                    for tono, texto in items)
    return f'<div class="pa-leyenda">{spans}</div>'


def nota(texto: str, tono: str = "neutro") -> str:
    """Recuadro de lectura ("Lo que se ve", "Para leer"). tono: neutro, atencion o critico."""
    fondo, color = {"neutro": ("#FBFAF8", TEXTO_2), "atencion": ("#FBF0DC", "#6B4700"),
                    "critico": ("#FBE9E6", "#7A3028"), "info": ("#EAF0F8", "#164279")}[tono]
    return f'<p class="pa-nota" style="background:{fondo}; color:{color}">{texto}</p>'


def progreso(valor, color: str = ACCION, ancho: int | None = None) -> str:
    """Barrita de avance 0-100 con el número al lado."""
    if valor is None or pd.isna(valor):
        return f'<span class="pa-muted">{VACIO}</span>'
    estilo = f"width:{ancho}px" if ancho else "flex:1"
    return (f'<span style="display:flex; align-items:center; gap:8px">'
            f'<span class="pa-progreso" style="{estilo}"><div style="width:{min(max(valor, 0), 100):.1f}%; '
            f'background:{color}"></div></span><span class="pa">{pct(valor)}</span></span>')


def semaforo(condicion: str, detalle: str = "") -> str:
    """HTML del semáforo: color + forma + texto (nunca solo color, D48)."""
    return chip_estado(condicion, detalle)


def mostrar_semaforo(condicion: str, detalle: str = "") -> None:
    html(semaforo(condicion, detalle))


def con_icono(serie: pd.Series, iconos: dict) -> pd.Series:
    """Para tablas: 'Libre' -> '🛑 Libre' (el emoji repite la forma del semáforo)."""
    return serie.map(lambda v: f"{iconos.get(v, '')} {v}".strip())


def grafico(fig, **kwargs) -> None:
    """st.plotly_chart con la plantilla de la app. El fondo va explícito en el layout:
    si no, Streamlit lo pinta con el color secundario del tema."""
    fig.update_layout(template=f"plotly_white+{PLANTILLA}")
    fig.update_layout(paper_bgcolor=TARJETA, plot_bgcolor=TARJETA)
    # Ancho fijo por ítem de leyenda: plotly mide el texto antes de que cargue Inter
    # y, si no, los nombres largos se pisan.
    nombres = [tr.name for tr in fig.data if tr.name and tr.showlegend is not False]
    if nombres:
        fig.update_layout(legend=dict(entrywidthmode="pixels", entrywidth=max(map(len, nombres)) * 7 + 40))
    st.plotly_chart(fig, width="stretch", theme=None, **kwargs)
