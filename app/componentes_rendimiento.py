"""
Sistema visual del dashboard Rendimiento académico (app/paginas/4_rendimiento.py).

Nació en la rama dashboard/rendimiento en paralelo al rediseño de main, con algunos
nombres iguales (encabezado(), barra(), semaforo(), esc()...) pero otras firmas y otro
CSS. Para que convivan sin pisarse (mismo criterio que General, Matrícula, Notas y
Participación), vive en este módulo aparte:

  - Reexporta todo lo de componentes (datos, metrica, filtros, formatos, boton_csv...) y
    redefine encima solo las piezas visuales propias. La página hace
    `import componentes_rendimiento as comp` y el resto de las páginas no se entera.
  - Sus clases CSS llevan el prefijo tc-*; el CSS se inyecta desde encabezado(), o sea
    solo en esta página.
  - Piezas HTML: pintar(html) (envuelve en <div class="tc">, necesario para que las clases
    tc-* le ganen al CSS de Streamlit), forma(), swatch(), etiqueta_materia(), barra(),
    aclarar(). Tarjeta con widgets: st.container(key="tarjeta_..."); opción destacada
    (checkbox azul): st.container(key="opcion_..."). encabezado(..., acciones=fn) pone
    botones a la derecha del título.
  - El color de materia IDENTIFICA, el del semáforo EVALÚA. El estado nunca va solo con
    color: color + forma + palabra (D48).
"""
from __future__ import annotations

import html as html_lib  # con alias: componentes define una función html() que el import * pisaría
import re

import pandas as pd
import streamlit as st

from componentes import *  # noqa: F401,F403  (datos, metrica, filtros, num, pct, boton_csv, ...)
from componentes import Filtros, filtros, fmt_fecha  # noqa: F401  (explícitos para los linters)
from src.config import ASIGNATURAS, SIN_EVALUACIONES
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD


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
    """CSS de esta página (lo llama encabezado())."""
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Componentes visuales
# ---------------------------------------------------------------------------
def pintar(codigo_html: str) -> None:
    """Dibuja un bloque de HTML del sistema visual. Va en una sola línea para
    que el markdown de Streamlit no lo interprete (sangrías = bloque de código)."""
    st.markdown('<div class="tc">' + re.sub(r"\s*\n\s*", " ", codigo_html).strip() + "</div>",
                unsafe_allow_html=True)


def esc(texto) -> str:
    return html_lib.escape(str(texto), quote=True)


def encabezado(titulo: str, descripcion: str = "", acciones=None) -> Filtros:
    """Título de la página, descripción y, abajo, los filtros que se están usando.
    `acciones`: función sin argumentos que dibuja botones a la derecha del título
    (por ejemplo, descargas)."""
    estilos()
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


def semaforo(condicion: str, detalle: str = "") -> str:
    """HTML del semáforo: color + forma + texto (nunca solo color, D48)."""
    fondo = FONDO_CONDICION.get(condicion, "#EBE9E4")
    texto = TEXTO_CONDICION.get(condicion, TERMINAL)
    extra = f" · {esc(detalle)}" if detalle else ""
    return (f'<span class="semaforo" style="background:{fondo};color:{texto}">'
            f'{forma(condicion)}{esc(condicion)}{extra}</span>')


def mostrar_semaforo(condicion: str, detalle: str = "") -> None:
    pintar(semaforo(condicion, detalle))


def nombre_corto(instrumento: str) -> str:
    """Para ejes y leyendas: saca los emojis y espacios del principio
    ('👉  Actividad Rápida 1' -> 'Actividad Rápida 1')."""
    return re.sub(r"^\W+", "", str(instrumento)).strip()
