"""
Sistema visual del dashboard Matrícula y alertas (app/paginas/7_matricula_y_alertas.py).

Nació en la rama dashboard/matricula en paralelo al rediseño de main, con los mismos
nombres (TONOS, tarjeta(), seccion(), aviso(), chip(), barra(), leyenda(), grafico()...)
pero otras firmas y otro CSS. Para que convivan sin pisarse (mismo criterio que la Ficha
individual con sus *_estado y clases fi-*), vive en este módulo aparte:

  - Reexporta todo lo de componentes (datos, metrica, filtros, formatos, boton_csv...) y
    redefine encima solo las piezas visuales propias. La página hace
    `import componentes_matricula as comp` y el resto de las páginas no se entera.
  - Sus clases CSS llevan el prefijo ma-* y sus claves de contenedor ma_*; el CSS se
    inyecta desde encabezado(), o sea solo en esta página.
  - Su plantilla de plotly ("tfi_matricula") se aplica en grafico(), sin cambiar la
    plantilla por defecto de la app.

El estado siempre va con color + forma + palabra (●▲⬣■ en tablas, SVG en HTML; D48).
"""
from __future__ import annotations

import html as html_lib  # con alias: componentes define una función html() que el import * pisaría
import re
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from componentes import *  # noqa: F401,F403  (datos, metrica, filtros, num, pct, boton_csv, ...)
from componentes import Filtros, filtros, num, pct  # noqa: F401  (explícitos para los linters)
from src.config import ASIGNATURAS, SIN_EVALUACIONES
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD

PLANTILLA = "tfi_matricula"

# Base
FONDO, TARJETA, BORDE, BORDE_SUAVE = "#F7F6F3", "#FFFFFF", "#E3E1DC", "#EFEDE8"
TEXTO, TEXTO_2, TEXTO_3, TEXTO_4 = "#1A1917", "#57544C", "#6B6861", "#8A867C"
ACCION = "#1B4B8F"
FUENTE_TITULOS = "'Space Grotesk', Inter, sans-serif"

# Categórica, en orden fijo: las tres primeras son las materias (ALG, PYE, AED).
CATEGORICA = ["#2563C9", "#0E8F62", "#D4661F", "#6B4FA8", "#C98A12", "#B8487A", "#4A8FA8", "#7A7468"]
_POR_SIGLA = {"ALG": ("#2563C9", "#EAF0F8", "#164279"),   # (color, fondo de etiqueta, texto de etiqueta)
              "PYE": ("#0E8F62", "#E6F2EB", "#0B6B49"),
              "AED": ("#D4661F", "#FBEFE6", "#8A4415")}
SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}
COLORES_MATERIA = {nombre: _POR_SIGLA[s][0] for nombre, s in SIGLAS.items()}
ORDEN_MATERIAS = sorted(ASIGNATURAS, key=lambda n: list(_POR_SIGLA).index(SIGLAS[n]))  # ALG, PYE, AED
NOMBRE_CORTO = {"Álgebra": "Álgebra", "Probabilidad y Estadística": "Probabilidad",
                "Algoritmos y Estructuras de Datos": "Algoritmos"}

# Estados: forma + color fuerte + texto oscuro + fondo claro (+ símbolo para las tablas).
BIEN, ATENCION, CRITICO, NEUTRO, INFO = "#16734A", "#C98A12", "#B02A20", "#3C3A34", ACCION
_TONOS = {  # tono: (color fuerte, texto sobre fondo claro, fondo claro, borde del fondo)
    "bien": (BIEN, "#116040", "#E6F2EB", "#CFE3D8"),
    "atencion": (ATENCION, "#7A5000", "#FBF0DC", "#F0E2C4"),
    "critico": (CRITICO, "#93241C", "#FBE9E6", "#F2CFC9"),
    "neutro": (NEUTRO, "#35332D", "#EBE9E4", "#D9D6CF"),
    "info": (INFO, "#164279", "#EAF0F8", "#DCE5F1"),
}
_FORMAS = {"bien": "circulo", "atencion": "triangulo", "critico": "octogono", "neutro": "cuadrado", "info": "info"}
SIMBOLOS = {"circulo": "●", "triangulo": "▲", "octogono": "⬣", "cuadrado": "■", "info": "ⓘ"}

ESTADOS = {  # valor que aparece en los datos -> tono
    "Promociona": "bien", "Regular": "atencion", "Libre": "critico", SIN_EVALUACIONES: "neutro",
    ACTIVO: "bien", INACTIVO: "atencion", SIN_ACTIVIDAD: "neutro",
    "Alta": "critico", "Media": "atencion", "Administrativa": "info",
    "Nunca entró": "neutro", "Entra, no rinde": "atencion",
    "No figura": "critico", "Baja": "neutro",                  # estado en Matriculados
}
TONOS = _TONOS  # para las páginas: TONOS["critico"][1] es el texto rojo oscuro
COLORES_CONDICION = {c: _TONOS[ESTADOS[c]][0] for c in ("Libre", "Regular", "Promociona", SIN_EVALUACIONES)}
COLORES_ACTIVIDAD = {c: _TONOS[ESTADOS[c]][0] for c in (ACTIVO, INACTIVO, SIN_ACTIVIDAD)}
COLORES_PRIORIDAD = {c: _TONOS[ESTADOS[c]][0] for c in ("Alta", "Media", "Administrativa")}
ICONOS_CONDICION = {c: SIMBOLOS[_FORMAS[ESTADOS[c]]] for c in COLORES_CONDICION}
ICONOS_ACTIVIDAD = {c: SIMBOLOS[_FORMAS[ESTADOS[c]]] for c in COLORES_ACTIVIDAD}
ICONOS_PRIORIDAD = {c: SIMBOLOS[_FORMAS[ESTADOS[c]]] for c in COLORES_PRIORIDAD}

# Secuencial (mapas de calor): un solo tono (el azul de acción), de claro a oscuro.
SECUENCIAL = ["#E3EBF6", "#BFD1EA", "#93B2DB", "#6690CA", "#3F6FB2", "#1B4B8F", "#123663"]

# Plantilla de plotly: fondo blanco (el gráfico va dentro de una tarjeta blanca),
# grilla tenue, textos en gris cálido y la paleta categórica.
pio.templates[PLANTILLA] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family="Inter, system-ui, sans-serif", color=TEXTO_2, size=12),
    paper_bgcolor=TARJETA, plot_bgcolor=TARJETA,
    xaxis=dict(gridcolor="#F1EFEA", linecolor="#D9D6CF", zerolinecolor="#D9D6CF", tickcolor="#D9D6CF",
               title_font=dict(color=TEXTO_3, size=11)),
    yaxis=dict(gridcolor="#F1EFEA", linecolor="#D9D6CF", zerolinecolor="#D9D6CF", tickcolor="#D9D6CF",
               title_font=dict(color=TEXTO_3, size=11)),
    margin=dict(t=40, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12, color=TEXTO)),
    hoverlabel=dict(font_size=13, font_family="Inter, sans-serif", bgcolor=TARJETA, bordercolor=BORDE,
                    font_color=TEXTO),
))

CSS = f"""
<style>
  .num, [data-testid="stMetricValue"] {{font-variant-numeric: tabular-nums;}}
  [data-testid="stMainBlockContainer"] {{padding-top: 2.2rem; max-width: 1280px;}}
  h1 {{letter-spacing: -.02em; font-size: 1.8rem !important;}}

  /* Encabezado de página */
  .ma-desc {{margin: -.2rem 0 .35rem; max-width: 72ch; font-size: .87rem; line-height: 1.55; color: {TEXTO_2};}}
  .st-key-ma_pill_filtros {{width: fit-content;}}
  .st-key-ma_pill_filtros [data-testid="stCaptionContainer"] {{display: inline-flex; align-items: center;
      height: 30px; padding: 0 12px; border-radius: 999px; background: #F1EFEA; color: {TEXTO_2};
      font-size: .8rem;}}
  .st-key-ma_pill_filtros [data-testid="stCaptionContainer"] p {{margin: 0;}}

  /* Tarjetas (st.container con key "tarjeta_...") */
  div[class*="st-key-ma_tarjeta_"] {{background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 13px;
      padding: 18px;}}
  .ma-h3 {{margin: 0 0 4px; font: 600 1rem {FUENTE_TITULOS}; color: {TEXTO};}}
  .ma-sub {{margin: 0 0 6px; max-width: 88ch; font-size: .8rem; line-height: 1.55; color: {TEXTO_2};}}
  .ma-sub strong {{font-weight: 600; color: {TEXTO};}}
  .ma-pie {{margin: 0; font-size: .74rem; line-height: 1.55; color: {TEXTO_3};}}
  .ma-pie strong {{font-weight: 600; color: #2C2A25;}}

  /* KPI (st.metric) */
  [data-testid="stMetric"] {{background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 13px;
      padding: 15px; height: 100%;}}
  [data-testid="stMetricLabel"] p {{font-size: .73rem !important; font-weight: 600; letter-spacing: .05em;
      text-transform: uppercase; color: {TEXTO_3}; white-space: normal !important; line-height: 1.3;}}
  [data-testid="stMetricLabel"] div {{overflow: visible !important; white-space: normal !important;}}
  [data-testid="stMetricValue"] {{font-family: {FUENTE_TITULOS};}}
  [data-testid="stMetricDelta"] {{background: none !important; padding: 0 !important; color: {TEXTO_3} !important;
      font-size: .8rem;}}
  [data-testid="stMetricDelta"] svg {{display: none;}}
  [data-testid="stMetricDelta"] div {{white-space: normal !important; overflow: visible !important;}}
  {"".join(f'''
  div[class*="st-key-ma_kpi_{t}"] [data-testid="stMetric"] {{background: {c[2]}; border-color: {c[3]};}}
  div[class*="st-key-ma_kpi_{t}"] [data-testid="stMetricLabel"] p,
  div[class*="st-key-ma_kpi_{t}"] [data-testid="stMetricDelta"] {{color: {c[1]} !important;}}
  div[class*="st-key-ma_kpi_{t}"] [data-testid="stMetricValue"],
  div[class*="st-key-ma_kpivalor_{t}"] [data-testid="stMetricValue"] {{color: {c[1]};}}''' for t, c in _TONOS.items())}

  /* Pestañas: subrayado azul, sin fondo */
  [data-baseweb="tab-list"] {{gap: 4px; border-bottom: 1px solid {BORDE}; margin-bottom: .4rem;}}
  [data-baseweb="tab-list"] button[data-baseweb="tab"] {{padding: 10px 14px; height: auto;}}
  [data-baseweb="tab-list"] button[data-baseweb="tab"] p {{font-size: .87rem; font-weight: 500; color: {TEXTO_2};}}
  [data-baseweb="tab-list"] button[aria-selected="true"] p {{font-weight: 600; color: {ACCION};}}
  [data-baseweb="tab-highlight"] {{background-color: {ACCION};}}
  [data-baseweb="tab-border"] {{display: none;}}

  /* Chips y etiquetas */
  .ma-chip {{display: inline-flex; align-items: center; gap: 7px; height: 26px; padding: 0 10px;
      border-radius: 999px; font-size: .8rem; font-weight: 600; white-space: nowrap;}}
  .ma-estado {{display: inline-flex; align-items: center; gap: 6px; font-size: .8rem; font-weight: 600;
      white-space: nowrap;}}
  .ma-materia {{display: inline-flex; align-items: center; height: 20px; padding: 0 7px; border-radius: 5px;
      font-size: .73rem; font-weight: 600;}}
  .ma-punto {{display: inline-block; width: 9px; height: 9px; border-radius: 3px;}}

  /* Avisos (nota destacada debajo de un gráfico o banner) */
  .ma-nota {{display: flex; gap: 10px; align-items: flex-start; margin: 6px 0 0; padding: 12px 14px;
      border-radius: 10px; font-size: .8rem; line-height: 1.6;}}
  .ma-nota svg {{flex: 0 0 auto; margin-top: 3px;}}
  .ma-nota strong {{font-weight: 600;}}

  /* Tarjetas grandes de aviso (prioridades, grupos) */
  .ma-aviso {{height: 100%; border: 1px solid; border-radius: 12px; padding: 15px;}}
  .ma-aviso .t {{margin: 0 0 6px; display: flex; align-items: center; gap: 8px; font-size: .73rem;
      font-weight: 600; letter-spacing: .06em; text-transform: uppercase;}}
  .ma-aviso .v {{margin: 0 0 6px; font: 600 1.75rem {FUENTE_TITULOS}; font-variant-numeric: tabular-nums;}}
  .ma-aviso .d {{margin: 0; font-size: .8rem; line-height: 1.5;}}

  /* Barras horizontales en HTML (embudo, distribución) */
  .ma-fila {{display: flex; align-items: center; gap: 10px; margin-bottom: 6px;}}
  .ma-fila .e {{flex: 0 0 var(--ancho-etiqueta, 120px); font-size: .8rem; color: {TEXTO_2};}}
  .ma-fila .b {{flex: 1 1 auto; display: flex; height: var(--alto, 22px); border-radius: 4px;
      background: #EDEBE6; overflow: hidden;}}
  .ma-fila .b > span {{display: flex; align-items: center; justify-content: center; height: 100%;
      font-size: .67rem; font-weight: 600; color: #fff; font-variant-numeric: tabular-nums;}}
  .ma-fila .n {{flex: 0 0 38px; text-align: right; font-size: .87rem; font-weight: 600;
      font-variant-numeric: tabular-nums;}}
  .ma-leyenda {{display: flex; flex-wrap: wrap; gap: 16px; margin: 4px 0 10px;}}
  .ma-leyenda span {{display: inline-flex; align-items: center; gap: 7px; font-size: .8rem; font-weight: 500;
      color: #2C2A25;}}

  /* Tablas y botones */
  [data-testid="stDataFrame"] {{border: 1px solid {BORDE_SUAVE}; border-radius: 10px; overflow: hidden;}}
  [data-testid="stDownloadButton"] button, [data-testid="stBaseButton-secondary"] {{background: {TARJETA};
      border-color: #D4D1CA;}}
</style>
"""


def fmt_dias(x) -> str:
    """Días sin entrar: 15 -> '15 d'."""
    return "—" if x is None or pd.isna(x) else f"{int(x)} d"


def esc(texto) -> str:
    """Escapa texto que viene de los datos antes de meterlo en HTML."""
    return html_lib.escape("" if texto is None else str(texto))


# ---------------------------------------------------------------------------
# Componentes visuales
# ---------------------------------------------------------------------------
def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página, una línea que explica qué responde y la píldora con
    los filtros que se están usando."""
    f = filtros()
    estilos()
    st.title(titulo, anchor=False)
    if descripcion:  # admite **negrita** al estilo markdown
        st.html(f'<p class="ma-desc">{re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", descripcion)}</p>')
    with st.container(key="ma_pill_filtros"):
        st.caption(f"Datos al **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
                   f"inactivo después de {f.umbral} días sin entrar")
    return f


def tarjetas(items: list, columnas: int | None = None) -> None:
    """Fila de tarjetas de KPI (st.metric). Cada item es (etiqueta, valor) o
    (etiqueta, valor, ayuda) o un dict con las claves de st.metric, más dos opcionales:
      tono        "bien" | "atencion" | "critico" | "neutro" | "info": pinta toda la tarjeta.
      tono_valor  igual, pero solo colorea el número (tarjeta blanca).
    Lo que va en `delta` se muestra como texto gris debajo del número."""
    items = [dict(it) if isinstance(it, dict) else dict(zip(["label", "value", "help"], it)) for it in items]
    cols = st.columns(columnas or len(items))
    for i, it in enumerate(items):
        tono, tono_valor = it.pop("tono", None), it.pop("tono_valor", None)
        if "delta" in it:
            it.setdefault("delta_color", "off")
            it.setdefault("delta_arrow", "off")
        with cols[i % len(cols)]:
            if tono or tono_valor:
                clave = f"ma_kpi_{tono}" if tono else f"ma_kpivalor_{tono_valor}"
                with st.container(key=f"{clave}_{_slug(it['label'])}"):
                    st.metric(**it)
            else:
                st.metric(**it)


def _slug(texto: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in texto.lower())[:40]


def tarjeta(clave: str):
    """Contenedor blanco con borde y esquinas redondeadas (las secciones de cada página).
    Uso:  with comp.tarjeta("embudo"): ...   (la clave tiene que ser única en la página)."""
    return st.container(key=f"ma_tarjeta_{clave}")


def seccion(titulo: str, descripcion: str = "") -> None:
    """Título de una tarjeta y, debajo, una sola línea que dice qué muestra."""
    sub = f'<p class="ma-sub">{descripcion}</p>' if descripcion else ""
    st.html(f'<h3 class="ma-h3">{titulo}</h3>{sub}')


def pie(texto: str) -> None:
    """Nota al pie de una tarjeta (definiciones, aclaraciones)."""
    st.html(f'<p class="ma-pie">{texto}</p>')


def nota(texto: str, tono: str = "neutro", icono: bool = False) -> None:
    """Recuadro de lectura: qué conclusión sacar del gráfico de arriba.
    tono "neutro" es gris claro; los demás usan el fondo del estado."""
    if tono == "neutro":
        fondo, color = "#FBFAF8", TEXTO_2
    else:
        _, color, fondo, _ = _TONOS[tono]
    ic = forma(_FORMAS[tono], color, 15, fondo) if icono and tono != "neutro" else ""
    st.html(f'<div class="ma-nota" style="background:{fondo};color:{color}">{ic}<span>{texto}</span></div>')


def forma(nombre: str, color: str, tam: int = 12, contraste: str = "#FFFFFF") -> str:
    """SVG de la forma de un estado: círculo, triángulo, octógono, cuadrado o info.
    Se distinguen sin color (impresión, daltonismo)."""
    trazo = f'stroke="{contraste}" stroke-linecap="round" stroke-linejoin="round"'
    dibujos = {
        "circulo": f'<circle cx="8" cy="8" r="6.6" fill="{color}"/>'
                   f'<path d="M4.9 8.3l2.1 2.1 4.2-4.5" fill="none" stroke-width="1.7" {trazo}/>',
        "triangulo": f'<path d="M8 1.6l6.6 11.8H1.4z" fill="{color}"/>'
                     f'<path d="M8 6v3.1M8 11.2v.1" stroke-width="1.5" {trazo}/>',
        "octogono": f'<path d="M5.2 1.4h5.6l3.8 3.8v5.6l-3.8 3.8H5.2l-3.8-3.8V5.2z" fill="{color}"/>'
                    f'<path d="M8 4.8v4M8 10.8v.1" stroke-width="1.6" {trazo}/>',
        "cuadrado": f'<rect x="2" y="2" width="12" height="12" rx="3" fill="{color}"/>'
                    f'<path d="M5 8h6" stroke-width="1.8" {trazo}/>',
        "info": f'<circle cx="8" cy="8" r="6.6" fill="none" stroke="{color}" stroke-width="1.6"/>'
                f'<path d="M8 7.2v4M8 4.8v.1" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>',
    }
    # st.html limpia los <svg> en línea: se embebe como imagen (data URI), que sí pasa.
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">{dibujos[nombre]}</svg>'
    return (f'<img src="data:image/svg+xml,{quote(svg)}" width="{tam}" height="{tam}" alt="" '
            f'style="flex:0 0 auto;display:inline-block">')


def tono_de(valor: str) -> str:
    return ESTADOS.get(valor, "neutro")


def chip(valor: str, texto: str | None = None, relleno: bool = True) -> str:
    """HTML del estado (condición, actividad, prioridad): forma + color + palabra.
    relleno=True es la píldora con fondo; False, solo ícono y texto (para tablas)."""
    t = tono_de(valor)
    fuerte, oscuro, fondo, _ = _TONOS[t]
    if relleno:
        return (f'<span class="ma-chip" style="background:{fondo};color:{oscuro}">'
                f'{forma(_FORMAS[t], oscuro, 12, fondo)}{esc(texto or valor)}</span>')
    return (f'<span class="ma-estado" style="color:{oscuro}">'
            f'{forma(_FORMAS[t], fuerte, 12)}{esc(texto or valor)}</span>')


def semaforo(condicion: str, detalle: str = "") -> str:
    """Semáforo de condición: la píldora de chip() con un detalle opcional."""
    return chip(condicion, f"{condicion} · {detalle}" if detalle else condicion)


def mostrar_semaforo(condicion: str, detalle: str = "") -> None:
    st.html(semaforo(condicion, detalle))


def etiqueta_materia(asignatura: str) -> str:
    """Etiqueta chica con la sigla de la materia (ALG / PYE / AED) en su color."""
    s = SIGLAS.get(asignatura, asignatura)
    _, fondo, texto = _POR_SIGLA.get(s, (NEUTRO, "#EBE9E4", "#35332D"))
    return f'<span class="ma-materia" style="background:{fondo};color:{texto}">{esc(s)}</span>'


def punto_materia(asignatura: str, nombre: str | None = None) -> str:
    """Cuadradito de color + nombre de la materia (títulos de gráficos por materia)."""
    return (f'<span style="display:inline-flex;align-items:center;gap:8px;font-weight:600">'
            f'<span class="ma-punto" style="background:{COLORES_MATERIA.get(asignatura, NEUTRO)}"></span>'
            f'{esc(nombre or asignatura)}</span>')


def aviso(titulo: str, valor: str, texto: str, tono: str) -> str:
    """HTML de una tarjeta grande de aviso (prioridades, grupos de alumnos): fondo
    del tono, forma del estado, número grande y una línea que dice qué hacer."""
    _, oscuro, fondo, borde = _TONOS[tono]
    return (f'<div class="ma-aviso" style="background:{fondo};border-color:{borde}">'
            f'<p class="t" style="color:{oscuro}">{forma(_FORMAS[tono], oscuro, 13, fondo)}{titulo}</p>'
            f'<p class="v" style="color:{oscuro}">{valor}</p>'
            f'<p class="d" style="color:{oscuro}">{texto}</p></div>')


def avisos(items: list[str]) -> None:
    """Fila de tarjetas de aviso (cada item es el HTML de aviso())."""
    for col, contenido in zip(st.columns(len(items)), items):
        col.html(contenido)


def barra(etiqueta: str, valor: float, maximo: float, color: str, texto: str | None = None,
          color_numero: str | None = None, destacada: bool = False) -> str:
    """Una fila de barra horizontal en HTML: etiqueta, barra proporcional y número."""
    ancho = 0 if not maximo else max(0.0, min(100.0, valor / maximo * 100))
    estilo_e = ' style="color:#2C2A25;font-weight:500"' if destacada else ""
    estilo_n = f' style="color:{color_numero}"' if color_numero else ""
    return (f'<div class="ma-fila"><span class="e"{estilo_e}>{etiqueta}</span>'
            f'<span class="b"><span style="width:{ancho:.1f}%;background:{color}"></span></span>'
            f'<span class="n"{estilo_n}>{texto if texto is not None else num(valor)}</span></div>')


def barra_apilada(etiqueta: str, partes: list[tuple[float, str, str]], ancho_etiqueta: int = 90,
                  minimo_texto: float = 12) -> str:
    """Barra 100 % apilada: partes = [(porcentaje, color, ayuda), ...]. El porcentaje
    se escribe adentro solo si el segmento es lo bastante ancho para leerse."""
    segs = "".join(
        f'<span title="{esc(ayuda)}" style="width:{p:.1f}%;background:{c}">'
        f'{pct(p, 0) if p >= minimo_texto else ""}</span>' for p, c, ayuda in partes if p > 0)
    return (f'<div class="ma-fila" style="--ancho-etiqueta:{ancho_etiqueta}px;--alto:20px;margin-bottom:5px">'
            f'<span class="e" style="font-size:.74rem">{etiqueta}</span><span class="b">{segs}</span></div>')


def leyenda(items: list[tuple[str, str]], forma_marca: str = "cuadrado") -> str:
    """Leyenda en HTML: [(texto, color), ...]. forma_marca "cuadrado" o "linea"."""
    marca = ('<span style="width:16px;height:3px;border-radius:2px;background:{c};display:inline-block"></span>'
             if forma_marca == "linea" else
             '<span style="width:10px;height:10px;border-radius:2px;background:{c};display:inline-block"></span>')
    return '<div class="ma-leyenda">' + "".join(
        f'<span>{marca.format(c=c)}{esc(t)}</span>' for t, c in items) + "</div>"


def con_icono(serie: pd.Series, iconos: dict) -> pd.Series:
    """Para tablas: 'Libre' -> '⬣ Libre' (la forma repite lo que dice el color)."""
    return serie.map(lambda v: f"{iconos.get(v, '')} {v}".strip())


def con_forma(serie: pd.Series) -> pd.Series:
    """Para tablas: antepone la forma del estado ('Libre' -> '⬣ Libre')."""
    return serie.map(lambda v: v if pd.isna(v) else f"{SIMBOLOS[_FORMAS[tono_de(v)]]} {v}")


def estilo_tabla(df: pd.DataFrame, estados=(), materias=(), resaltar: pd.Series | None = None,
                 color_columnas: dict | None = None):
    """Styler para st.dataframe con los colores del sistema visual:
      estados        columnas con valores de ESTADOS (con o sin la forma adelante): texto en su color.
      materias       columnas con la sigla o el nombre de la materia: texto en su color.
      resaltar       Serie booleana (mismo índice que df): fondo verde muy suave en esas filas.
      color_columnas {columna: color}: texto en ese color y en negrita (un conteo a mirar)."""
    def color_estado(v):
        if pd.isna(v):
            return ""
        valor = str(v).split(" ", 1)[-1] if str(v)[:1] in SIMBOLOS.values() else str(v)
        return f"color: {_TONOS[tono_de(valor)][1]}; font-weight: 600" if valor in ESTADOS else ""

    por_materia = {**{s: v[2] for s, v in _POR_SIGLA.items()}, **{n: _POR_SIGLA[s][2] for n, s in SIGLAS.items()}}

    def color_materia(v):
        return f"color: {por_materia[v]}; font-weight: 600" if v in por_materia else ""

    sty = df.style
    if estados:
        sty = sty.map(color_estado, subset=[c for c in estados if c in df.columns])
    if materias:
        sty = sty.map(color_materia, subset=[c for c in materias if c in df.columns])
    for col, color in (color_columnas or {}).items():
        if col in df.columns:
            sty = sty.map(lambda _, c=color: f"color: {c}; font-weight: 600", subset=[col])
    if resaltar is not None:
        marcadas = set(resaltar[resaltar.astype(bool)].index)
        sty = sty.apply(lambda fila: ["background-color: #F3F9F5" if fila.name in marcadas else ""] * len(fila),
                        axis=1)
    return sty


def grafico(fig, **kwargs) -> None:
    """st.plotly_chart con la plantilla de la app (theme=None: si no, Streamlit pisa
    los colores y el fondo con su propio tema) y sin la barra de herramientas.
    El fondo se fija en la figura: Streamlit completa los que vienen solo de la plantilla."""
    fig.update_layout(template=f"plotly_white+{PLANTILLA}")
    fig.update_layout(paper_bgcolor=fig.layout.paper_bgcolor or TARJETA,
                      plot_bgcolor=fig.layout.plot_bgcolor or TARJETA)
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False}, **kwargs)


def estilos() -> None:
    """CSS de esta página (lo llama encabezado()). Sin líneas en blanco: el markdown
    cortaría el bloque <style> en la primera."""
    st.markdown("\n".join(linea for linea in CSS.splitlines() if linea.strip()), unsafe_allow_html=True)
