"""
Sistema visual del dashboard Trazabilidad (app/paginas/3_trazabilidad.py).

Nació en la rama dashboard/trazabilidad en paralelo al rediseño de main, con los mismos
nombres que componentes (tarjeta(), chip(), leyenda(), nota()...) pero otras firmas y otro
CSS. Para que convivan sin pisarse (mismo criterio que Matrícula, General, Participación y
Rendimiento), vive en este módulo aparte:

  - Reexporta todo lo de componentes (datos, metrica, filtros, formatos, boton_csv...) y
    redefine encima solo las piezas visuales propias. La página hace
    `import componentes_trazabilidad as comp` y el resto de las páginas no se entera.
  - Sus clases CSS llevan el prefijo tz-* y sus contenedores la key tz_tarjeta_*; el CSS
    (app/estilos_trazabilidad.css) se inyecta desde encabezado(), o sea solo en esta página.
  - Su plantilla de plotly ("tfi_trazabilidad") se aplica en grafico(), sin cambiar la
    plantilla por defecto de la app.

Regla: el color de materia identifica y el del semáforo evalúa; nunca se mezclan en un
mismo elemento, y un estado nunca va solo con color (D48, D63).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from componentes import *  # noqa: F401,F403  (datos, metrica, filtros, num, pct, boton_csv, ...)
from componentes import Filtros, _rango_fechas, datos, filtros, fmt_fecha  # noqa: F401
from src.config import ASIGNATURAS

PLANTILLA = "tfi_trazabilidad"

# Base (los mismos valores que .streamlit/config.toml y app/estilos_trazabilidad.css)
FONDO, TARJETA, BORDE = "#F7F6F3", "#FFFFFF", "#E3E1DC"
TEXTO, TEXTO_2, TEXTO_3, TEXTO_4 = "#1A1917", "#57544C", "#6B6861", "#8A867C"
ACCION, GRILLA, EJE = "#1B4B8F", "#F1EFEA", "#D9D6CF"

# Categórica, en orden fijo: los 3 primeros son las materias en el orden de ASIGNATURAS
# (ALG azul, AED naranja, PYE verde), así que cada materia tiene su color en cualquier gráfico.
CATEGORICA = ["#2563C9", "#D4661F", "#0E8F62", "#C98A12", "#6E56CF", "#B02A20", "#A8A49B"]
_COLOR_SIGLA = {"ALG": "#2563C9", "AED": "#D4661F", "PYE": "#0E8F62"}
COLORES_MATERIA = {nombre: _COLOR_SIGLA[d["sigla"]] for nombre, d in ASIGNATURAS.items()}
SIGLAS = {nombre: d["sigla"] for nombre, d in ASIGNATURAS.items()}
# Nombre corto para leyendas y textos ("Probabilidad" en vez de "Probabilidad y Estadística").
CORTOS = {nombre: nombre.split(" y ")[0] for nombre in ASIGNATURAS}

# Tipos de interacción (categorías de dim_accion). No comparten gráfico con las materias.
COLORES_CATEGORIA = {"Contenido": "#1B4B8F", "Navegación": "#D4661F", "Evaluación": "#16734A",
                     "Comunicación": "#C98A12", "Notas": "#A8A49B", "Agenda": "#CFCBC2"}

# Estados: colores reservados, siempre acompañados de ícono y texto.
BIEN, ATENCION, SERIO, CRITICO, NEUTRO = "#16734A", "#C98A12", "#D9822B", "#B02A20", "#A8A49B"

# Secuencial (mapas de calor): un solo tono, de claro a oscuro.
SECUENCIAL = ["#EFF4FB", "#DEE9F6", "#C5D9EF", "#A9C4E6", "#7FA6D9", "#4B7FC4", "#1B4B8F", "#0D2A4F"]

# Plantilla de plotly: los gráficos van dentro de tarjetas blancas, con grilla tenue,
# ejes grises, leyenda arriba a la izquierda y tooltip blanco.
pio.templates[PLANTILLA] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family="Inter, system-ui, sans-serif", size=12, color=TEXTO_2),
    paper_bgcolor=TARJETA, plot_bgcolor=TARJETA,
    xaxis=dict(gridcolor=GRILLA, linecolor=EJE, zerolinecolor=EJE, tickfont=dict(color=TEXTO_3),
               title=dict(font=dict(color=TEXTO_4, size=11))),
    yaxis=dict(gridcolor=GRILLA, linecolor="rgba(0,0,0,0)", zerolinecolor=EJE, tickfont=dict(color=TEXTO_3),
               title=dict(font=dict(color=TEXTO_4, size=11))),
    margin=dict(t=36, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12, color="#2C2A25"),
                title=dict(text="")),
    hoverlabel=dict(font_size=12, bgcolor=TARJETA, bordercolor=BORDE, font=dict(color=TEXTO)),
))

CSS = Path(__file__).with_name("estilos_trazabilidad.css")
ICONO_DATO = ('<svg viewBox="0 0 16 16" width="17" height="17" aria-hidden="true">'
              '<circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" stroke-width="1.5"/>'
              '<path d="M8 7.2v4.2M8 4.8v.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>')


def _md(texto: str) -> str:
    """Markdown mínimo para los recuadros en HTML: **negrita** y *cursiva*."""
    texto = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texto)
    return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", texto)


def _html(contenido: str) -> None:
    st.markdown(contenido, unsafe_allow_html=True)


def rango_fechas() -> tuple[date, date]:
    """Primer y último día que se puede elegir (para filtros de fechas de la página)."""
    return _rango_fechas(datos())


def grafico(fig: go.Figure, alto: int, config: dict | None = None) -> None:
    """Gráfico de plotly con la plantilla de esta página. El fondo se fija en el layout
    (si viene solo en la plantilla, Streamlit lo pinta de gris) y theme=None evita que el
    tema de Streamlit pise la plantilla."""
    fig.update_layout(template=f"plotly_white+{PLANTILLA}", height=alto,
                      plot_bgcolor=TARJETA, paper_bgcolor=TARJETA)
    st.plotly_chart(fig, width="stretch", config=config or {"displayModeBar": False}, theme=None)


def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Inyecta el CSS de la página, dibuja el título, la explicación en una línea y los filtros
    que se están usando."""
    _html(f"<style>{CSS.read_text(encoding='utf-8')}</style>")
    f = filtros()
    st.title(titulo, anchor=False)
    if descripcion:
        _html(f'<p class="tz-desc">{_md(descripcion)}</p>')
    st.caption(f"Corte: **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
               f"Inactivo después de {f.umbral} días sin entrar")
    return f


def tarjeta(clave: str, titulo: str = "", subtitulo: str = ""):
    """Contenedor blanco con borde (D63) y, si se pasa, su título y explicación. Se usa con `with`:
        with comp.tarjeta("evolucion", "Interacciones por semana", "Los triángulos son las evaluaciones."):
            comp.grafico(fig, 360)"""
    c = st.container(border=True, key=f"tz_tarjeta_{clave}")
    if titulo or subtitulo:
        c.markdown((f'<p class="tz-h3">{titulo}</p>' if titulo else "")
                   + (f'<p class="tz-sub">{_md(subtitulo)}</p>' if subtitulo else ""), unsafe_allow_html=True)
    return c


def titulo_tarjeta(titulo: str, subtitulo: str = "") -> None:
    """Título y explicación de una tarjeta cuando van al lado de un control (dentro de una columna)."""
    _html(f'<p class="tz-h3">{titulo}</p>' + (f'<p class="tz-sub">{_md(subtitulo)}</p>' if subtitulo else ""))


def lectura(texto: str, titulo: str = "", tono: str = "info") -> None:
    """Recuadro con el dato que hay que mirar: título en negrita y la explicación.
    tono: "info" (azul) o "atencion" (ámbar)."""
    cuerpo = (f"<strong>{titulo}</strong> " if titulo else "") + _md(texto)
    _html(f'<div class="tz-lectura {tono}">{ICONO_DATO}<p>{cuerpo}</p></div>')


def nota(texto: str, tono: str = "") -> None:
    """Nota debajo de un gráfico: cómo leerlo o qué se ve (fondo gris; tono="atencion" para ámbar)."""
    _html(f'<p class="tz-nota {tono}">{_md(texto)}</p>')


def chip(texto: str, gris: bool = False) -> str:
    """HTML de una etiqueta redondeada (por ej., 'Pico: miércoles de 20 a 21 h')."""
    return f'<span class="tz-chip{" gris" if gris else ""}">{texto}</span>'


def leyenda(colores: dict, linea: bool = False) -> None:
    """Leyenda en HTML ({etiqueta: color}), para gráficos que se dibujan sin la de plotly.
    linea=True dibuja un trazo (series en el tiempo) en vez de un cuadrado."""
    clase = ' class="linea"' if linea else ""
    _html('<div class="tz-leyenda">' + "".join(
        f'<span><i{clase} style="background:{c}"></i>{e}</span>' for e, c in colores.items()) + "</div>")


def mini_tarjeta(titulo: str, valor: str, texto: str, color: str | None = None) -> str:
    """HTML de una tarjeta chica (resumen de una materia dentro de una tarjeta grande)."""
    marca = f'<i style="background:{color}"></i>' if color else ""
    return (f'<div class="tz-mini"><p class="titulo">{marca}{titulo}</p><p class="valor">{valor}</p>'
            f'<p class="texto">{_md(texto)}</p></div>')


def tarjetas(items: list, columnas: int | None = None) -> None:
    """Fila de tarjetas de KPI. Cada item es (etiqueta, valor) o
    (etiqueta, valor, ayuda) o un dict con las claves de st.metric."""
    items = [it if isinstance(it, dict) else dict(zip(["label", "value", "help"], it)) for it in items]
    cols = st.columns(columnas or len(items))
    for i, it in enumerate(items):
        cols[i % len(cols)].metric(border=True, **it)
