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

import pandas as pd
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
    separators=",.",   # es-AR: decimales con coma, miles con punto
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12, color="#2C2A25"),
                title=dict(text="")),
    hoverlabel=dict(font_size=12, bgcolor=TARJETA, bordercolor=BORDE, font=dict(color=TEXTO)),
))

# Forma del marcador de cada materia en los gráficos de líneas (además del color).
MARCADORES = dict(zip(ASIGNATURAS, ["circle", "square", "diamond"]))

CSS = Path(__file__).with_name("estilos_trazabilidad.css")


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
    st.caption(f"Corte: {fmt_fecha(f.fecha_corte)} · {f.materia}")
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


def ayuda(texto: str) -> str:
    """Signo (?) con una aclaración que aparece al pasar el mouse (limitaciones, definiciones)."""
    texto = texto.replace('"', "&quot;")
    return f'<span class="tz-ayuda" title="{texto}" aria-label="{texto}">?</span>'


def titulo_tarjeta(titulo: str, subtitulo: str = "", tip: str = "") -> None:
    """Título (el dato principal), una línea para leer el gráfico y, si hay `tip`, el (?)
    con las aclaraciones. Va al lado de un control (dentro de una columna) o solo."""
    _html(f'<p class="tz-h3">{titulo}{ayuda(tip) if tip else ""}</p>'
          + (f'<p class="tz-sub">{_md(subtitulo)}</p>' if subtitulo else ""))


def delta(valor, unidad: str = "", mejor: str = "neutro", decimales: int = 1, referencia: str = "") -> str:
    """Variación contra el período anterior como pastilla, con el mismo estilo que General:
    verde si mejora, roja si empeora, gris si `mejor="neutro"` o no cambia; 'vs. ...' al lado.
    Sin dato devuelve ""."""
    if valor is None or pd.isna(valor):
        return ""
    ref = f'<span class="tz-kpi-ref">vs. {referencia}</span>' if referencia else ""
    if round(valor, decimales) == 0:
        return f'<span class="tz-kpi-delta" style="background:#EFEDE8;color:{TEXTO_2}">= sin cambios</span>{ref}'
    sube = valor > 0
    if mejor == "neutro":
        fondo, texto = "#EFEDE8", TEXTO_2
    else:
        fondo, texto = ("#E3F1E8", "#0F5A37") if sube == (mejor == "sube") else ("#F8E4E1", "#93241C")
    flecha = "polygon(50% 10%,100% 80%,0 80%)" if sube else "polygon(0 20%,100% 20%,50% 90%)"
    return (f'<span class="tz-kpi-delta" style="background:{fondo};color:{texto}"><span aria-hidden="true" '
            f'style="display:inline-block;width:9px;height:9px;background:currentColor;clip-path:{flecha}"></span>'
            f'{"+" if sube else "−"}{num(abs(valor), decimales)}{" " + unidad if unidad else ""}</span>{ref}')


def kpi_html(etiqueta: str, valor: str, detalle: str = "", variacion: str = "", tip: str = "") -> str:
    """HTML de una tarjeta de KPI: etiqueta con su (?), número grande, variación y una línea de detalle."""
    return (f'<div class="tz-kpi"><p class="tz-kpi-etq">{etiqueta}{ayuda(tip) if tip else ""}</p>'
            f'<div class="tz-kpi-fila"><span class="tz-kpi-num">{valor}</span>'
            f'<span class="tz-kpi-var">{variacion}</span></div>'
            + (f'<p class="tz-kpi-detalle">{detalle}</p>' if detalle else "") + "</div>")


def kpi(etiqueta: str, valor: str, detalle: str = "", variacion: str = "", tip: str = "") -> None:
    """Una tarjeta de KPI suelta (para una fila de varias, mejor kpis(): quedan todas del mismo alto)."""
    _html(kpi_html(etiqueta, valor, detalle, variacion, tip))


def kpis(tarjetas: list[str]) -> None:
    """Fila de KPIs (cada uno armado con kpi_html) en una grilla: todas las tarjetas del mismo alto,
    con margen abajo, y en pantallas angostas pasan a dos columnas."""
    _html(f'<div class="tz-kpis">{"".join(tarjetas)}</div>')


def a_la_derecha(columna):
    """Contenedor alineado a la derecha dentro de una columna: para los controles de una tarjeta
    (toggle, Semana / Mes...), que quedan contra el borde derecho del gráfico.
    Uso: valor = comp.a_la_derecha(c2).toggle(...)."""
    return columna.container(horizontal=True, horizontal_alignment="right")


def estilo_tabla(df: pd.DataFrame, decimales: dict | None = None):
    """Styler en es-AR (miles con punto, decimales con coma) que conserva los números,
    así la tabla se sigue ordenando como número. `decimales`: {columna: cantidad} (0 por defecto)."""
    decimales = decimales or {}
    sty = df.style
    for col in df.select_dtypes("number").columns:
        sty = sty.format(precision=decimales.get(col, 0), subset=[col], thousands=".", decimal=",")
    return sty


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


def mini_tarjeta(titulo: str, valor: str, texto: str, color: str | None = None, tip: str = "") -> str:
    """HTML de una tarjeta chica (resumen de una materia dentro de una tarjeta grande)."""
    marca = f'<i style="background:{color}"></i>' if color else ""
    return (f'<div class="tz-mini"><p class="titulo">{marca}{titulo}{ayuda(tip) if tip else ""}</p>'
            f'<p class="valor">{valor}</p><p class="texto">{_md(texto)}</p></div>')


def tarjetas(items: list, columnas: int | None = None) -> None:
    """Fila de tarjetas de KPI. Cada item es (etiqueta, valor) o
    (etiqueta, valor, ayuda) o un dict con las claves de st.metric."""
    items = [it if isinstance(it, dict) else dict(zip(["label", "value", "help"], it)) for it in items]
    cols = st.columns(columnas or len(items))
    for i, it in enumerate(items):
        cols[i % len(cols)].metric(border=True, **it)
