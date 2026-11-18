"""
Sistema visual del dashboard General (app/paginas/1_general.py).

Nació en la rama dashboard/general en paralelo al rediseño de main, con los mismos
nombres (TONOS, tarjeta(), html(), kpi(), barra_apilada(), leyenda(), aviso(), grafico()...)
pero otras firmas y otro CSS. Para que convivan sin pisarse (mismo criterio que Matrícula
y alertas con componentes_matricula.py), vive en este módulo aparte:

  - Reexporta todo lo de componentes (datos, metrica, filtros, formatos, boton_csv...) y
    redefine encima solo las piezas visuales propias. La página hace
    `import componentes_general as comp` y el resto de las páginas no se entera.
  - Sus clases CSS llevan el prefijo gr-*; el CSS se inyecta desde encabezado(), o sea
    solo en esta página.
  - Su plantilla de plotly ("tfi_general") se aplica en grafico(), sin cambiar la
    plantilla por defecto de la app.

  - El color de materia IDENTIFICA, el del semáforo EVALÚA: nunca se mezclan en el mismo elemento.
  - El color nunca va solo: el semáforo repite el estado con forma (círculo, triángulo,
    octágono, cuadrado) y texto (D48, D60).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from componentes import *  # noqa: F401,F403  (datos, metrica, filtros, num, pct, boton_csv, ...)
from componentes import Filtros, filtros, fmt_fecha, num  # noqa: F401  (explícitos para los linters)
from src.config import ASIGNATURAS, SIN_EVALUACIONES
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD

PLANTILLA = "tfi_general"

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

# Plantilla de plotly: fondo blanco (el gráfico vive en una tarjeta blanca),
# grilla tenue y la paleta categórica.
pio.templates[PLANTILLA] = go.layout.Template(layout=dict(
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

CSS = f"""
<style>
  /* Tarjeta de alerta (roja clara) */
  .st-key-tarjeta_alerta {{background: #FBE9E6 !important; border-color: #F2CFC9 !important;}}
  .st-key-tarjeta_alerta a p {{color: #93241C; font-weight: 600;}}

  /* Piezas HTML (ver las funciones de abajo) */
  .gr {{font-family: {FUENTE}; color: {TEXTO};}}
  .gr p {{margin: 0;}}
  .gr-etq {{font: 600 11px {FUENTE}; letter-spacing: .06em; text-transform: uppercase; color: {TEXTO_3};}}
  .gr-txt {{font: 400 12px/1.55 {FUENTE}; color: {TEXTO_2};}}
  .gr-tenue {{font: 400 11px {FUENTE}; color: {TENUE};}}
  .gr-h3 {{font: 600 15px {FUENTE_TITULOS}; color: {TEXTO}; margin: 0 0 4px !important;}}
  .gr-grande {{font: 600 24px {FUENTE_TITULOS}; color: {TEXTO}; font-variant-numeric: tabular-nums;}}
  .gr-tarjeta {{background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 13px; padding: 18px;}}
  .gr-barra {{display: flex; border-radius: 7px; overflow: hidden;}}
  .gr-barra > div {{display: flex; align-items: center; justify-content: center; overflow: hidden;
                     font: 600 12px {FUENTE}; color: #fff; white-space: nowrap; font-variant-numeric: tabular-nums;}}
  .gr-leyenda {{display: flex; flex-wrap: wrap; gap: 6px 16px;}}
  .gr-leyenda span {{display: inline-flex; align-items: center; gap: 6px; font: 500 11px {FUENTE};}}
  .gr-chip {{display: inline-flex; align-items: center; gap: 7px; height: 26px; padding: 0 10px;
              border-radius: 999px; font: 600 12px {FUENTE}; white-space: nowrap;}}
  .gr-materia {{display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 5px;
                 font: 600 11px {FUENTE};}}
  .gr-aviso {{display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; border-radius: 12px;
               font: 400 13px/1.6 {FUENTE};}}
  .gr-fila {{display: flex; align-items: baseline; justify-content: space-between; padding: 9px 0;
              border-top: 1px solid {BORDE_SUAVE}; font: 400 12px {FUENTE}; color: {TEXTO_2};}}
  .gr-fila b {{font: 600 13px {FUENTE}; color: {TEXTO}; font-variant-numeric: tabular-nums;}}
  .gr-delta {{display: inline-flex; align-items: center; gap: 5px; font: 600 12px {FUENTE};
               font-variant-numeric: tabular-nums;}}
</style>
"""


def estilos() -> None:
    """CSS de esta página (lo llama encabezado())."""
    st.html(CSS)


# ---------------------------------------------------------------------------
# Componentes visuales
# ---------------------------------------------------------------------------
def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página y, abajo, los filtros que se están usando."""
    f = filtros()
    estilos()
    st.title(titulo)
    if descripcion:
        st.html(f'<p class="gr" style="margin:-6px 0 0;max-width:72ch;font:400 13px/1.55 {FUENTE};'
                f'color:{TEXTO_2}">{descripcion}</p>')
    st.caption(f"Datos al **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
               f"Inactivo después de {f.umbral} días sin entrar")
    return f


def grafico(fig, **kwargs) -> None:
    """st.plotly_chart con la plantilla de esta página. Los fondos se fijan en el layout
    porque el tema de Streamlit los pisa aunque se pase theme=None."""
    fig.update_layout(template=f"plotly_white+{PLANTILLA}")
    fig.update_layout(paper_bgcolor=TARJETA, plot_bgcolor=TARJETA)
    st.plotly_chart(fig, width="stretch", theme=None, **kwargs)


def tarjeta(nombre: str, **kwargs):
    """Contenedor con borde y fondo blanco: `with comp.tarjeta("notas"):`.
    `nombre` tiene que ser único en la página (se usa como key)."""
    return st.container(border=True, key=f"tarjeta_{nombre}", **kwargs)


# ---------------------------------------------------------------------------
# Piezas HTML. Devuelven texto: se combinan y se pintan con comp.html(...).
# Todos los números pasan por num()/pct() (coma decimal).
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
    st.html('<div class="gr">' + "".join(partes) + "</div>")


def forma(tono: str, tam: int = 12) -> str:
    """Ícono del semáforo: círculo (bien), triángulo (atención), octágono (crítico), cuadrado (neutro)."""
    return (f'<span aria-hidden="true" style="display:inline-block;width:{tam}px;height:{tam}px;'
            f'flex:0 0 {tam}px;background:currentColor;{_FORMAS[tono]}"></span>')


def semaforo(condicion: str, detalle: str = "") -> str:
    """Chip del semáforo: color + forma + texto (nunca solo color)."""
    _, fondo, texto = TONOS[TONO_CONDICION.get(condicion, "neutro")]
    extra = f" · {detalle}" if detalle else ""
    return (f'<span class="gr-chip" style="background:{fondo};color:{texto}">'
            f'{forma(TONO_CONDICION.get(condicion, "neutro"))}{condicion}{extra}</span>')


def mostrar_semaforo(condicion: str, detalle: str = "") -> None:
    html(semaforo(condicion, detalle))


def etiqueta_materia(materia: str) -> str:
    fondo, texto = ETIQUETA_MATERIA.get(materia, ("#EBE9E4", "#35332D"))
    return f'<span class="gr-materia" style="background:{fondo};color:{texto}">{SIGLAS.get(materia, materia)}</span>'


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
    return f'<div class="gr-barra" style="height:{alto}px">{"".join(tramos)}</div>'


def barra_simple(pct_: float, color: str, alto: int = 22) -> str:
    ancho = 0 if pct_ is None or pd.isna(pct_) else max(0.0, min(100.0, pct_))
    return (f'<span style="flex:1 1 auto;height:{alto}px;border-radius:5px;background:#EDEBE6;overflow:hidden;'
            f'display:inline-block"><span style="display:block;width:{ancho:.1f}%;height:100%;'
            f'background:{color}"></span></span>')


def leyenda(items: list) -> str:
    """items: [(color, texto, color_del_texto | None), ...]."""
    partes = [f'<span style="color:{tc or TEXTO}">{cuadradito(c, 10)}{t}</span>' for c, t, tc in items]
    return f'<div class="gr-leyenda">{"".join(partes)}</div>'


def delta(valor, unidad: str = "pp", mejor: str = "sube", decimales: int = 1) -> str:
    """Variación con flecha. `mejor` = "sube", "baja" o "neutro" decide si se pinta
    verde (mejora) o roja (empeora). Sin dato devuelve ""."""
    if valor is None or pd.isna(valor):
        return ""
    if round(valor, decimales) == 0:
        return f'<span class="gr-delta" style="color:{TEXTO_3}">= sin cambios</span>'
    sube = valor > 0
    if mejor == "neutro":
        color = TEXTO_2
    else:
        color = TONOS["bien" if sube == (mejor == "sube") else "critico"][2]
    flecha = "polygon(50% 10%,100% 80%,0 80%)" if sube else "polygon(0 20%,100% 20%,50% 90%)"
    signo = "+" if sube else "−"
    return (f'<span class="gr-delta" style="color:{color}"><span aria-hidden="true" style="display:inline-block;'
            f'width:10px;height:10px;background:currentColor;clip-path:{flecha}"></span>'
            f'{signo}{num(abs(valor), decimales)} {unidad}</span>')


def kpi(etiqueta: str, valor: str, pie: str = "", sufijo: str = "") -> str:
    """Tarjeta chica de KPI: etiqueta, número grande y una línea de pie (texto o delta)."""
    sufijo = f' <span style="font:400 13px {FUENTE};color:{TENUE}">{sufijo}</span>' if sufijo else ""
    pie = f'<p class="gr-txt num" style="margin-top:4px">{pie}</p>' if pie else ""
    return (f'<div class="gr-tarjeta" style="padding:15px;height:100%">'
            f'<p class="gr-etq" style="margin-bottom:8px">{etiqueta}</p>'
            f'<p class="gr-grande">{valor}{sufijo}</p>{pie}</div>')


def aviso(texto: str, tono: str = "atencion") -> str:
    """Recuadro de lectura rápida, con la forma del tono a la izquierda."""
    relleno, fondo, color = TONOS[tono]
    borde = {"atencion": "#F0E2C4", "critico": "#F2CFC9", "bien": "#CFE5D8", "neutro": BORDE}[tono]
    return (f'<div class="gr-aviso" style="background:{fondo};border:1px solid {borde};color:{color}">'
            f'<span style="color:{relleno};margin-top:3px;display:inline-flex">{forma(tono, 15)}</span>'
            f'<p style="margin:0">{texto}</p></div>')
