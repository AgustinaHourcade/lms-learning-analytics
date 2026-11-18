"""
Sistema visual del dashboard Notas vs. participación (app/paginas/5_notas_vs_participacion.py).

Nació en la rama dashboard/notas-participacion en paralelo al rediseño de main, con los
mismos nombres (TONOS, chip(), icono(), html(), leyenda(), aviso(), encabezado()...) pero
otras firmas y otro CSS. Para que convivan sin pisarse (mismo criterio que General con
componentes_general.py y Matrícula con componentes_matricula.py), vive en este módulo aparte:

  - Reexporta todo lo de componentes (datos, metrica, filtros, formatos, boton_csv...) y
    redefine encima solo las piezas visuales propias. La página hace
    `import componentes_notas as comp` y el resto de las páginas no se entera.
  - Sus clases CSS llevan el prefijo tfi-*; el CSS se inyecta desde encabezado(), o sea
    solo en esta página.

Regla de fondo: el estado nunca se comunica solo con color, siempre color + forma + palabra.
El color de materia identifica y el del semáforo evalúa: nunca se mezclan (D48, D55).
"""
from __future__ import annotations

import streamlit as st

from componentes import *  # noqa: F401,F403  (datos, metrica, filtros, num, pct, boton_csv, TODAS, ...)
from componentes import Filtros, filtros, fmt_fecha  # noqa: F401  (explícitos para los linters)
from src.config import ASIGNATURAS, SIN_EVALUACIONES
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD

# ---------------------------------------------------------------------------
# Paleta
# ---------------------------------------------------------------------------
FONDO, TARJETA, BORDE, BORDE_SUAVE = "#F7F6F3", "#FFFFFF", "#E3E1DC", "#EFEDE8"
TEXTO, TEXTO_2, TEXTO_3, TEXTO_4 = "#1A1917", "#57544C", "#6B6861", "#8A867C"
ACCION = "#1B4B8F"

SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}
_POR_SIGLA = {"ALG": "#2563C9", "AED": "#D4661F", "PYE": "#0E8F62"}
COLORES_MATERIA = {m: _POR_SIGLA[s] for m, s in SIGLAS.items()}
# Etiqueta de materia (fondo, texto): tinte suave del color de la materia.
TINTES_MATERIA = {"ALG": ("#EAF0F8", "#164279"), "AED": ("#FBEFE6", "#8A4415"), "PYE": ("#E6F2EB", "#0B6B49")}

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

CSS = """
<style>
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


# ---------------------------------------------------------------------------
# Piezas HTML (se pintan con html(); clases tfi-* en CSS)
# ---------------------------------------------------------------------------
def html(contenido: str, destino=st) -> None:
    """Pinta HTML. Se pasa a una sola línea: en markdown, una línea con sangría sería un bloque de código."""
    destino.markdown(" ".join(contenido.split("\n")), unsafe_allow_html=True)


_FORMAS = {  # misma forma = mismo significado en toda la página
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


def semaforo(condicion: str, detalle: str = "") -> str:
    """HTML del semáforo: color + forma + texto (nunca solo color, D48)."""
    extra = f" · {detalle}" if detalle else ""
    return chip(f"{condicion}{extra}", TONO_CONDICION.get(condicion, "neutro"), grande=True)


def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página, la pregunta que responde y los filtros que se están usando.
    Inyecta además el CSS tfi-* (solo en esta página)."""
    st.markdown(CSS, unsafe_allow_html=True)
    f = filtros()
    st.title(titulo)
    if descripcion:
        html(f'<p class="tfi tfi-texto" style="max-width:68ch;margin:-6px 0 6px">{descripcion}</p>')
    st.caption(f":gray-badge[:material/event: Datos al {fmt_fecha(f.fecha_corte)}] "
               f":gray-badge[{f.materia}] "
               f":gray-badge[Inactivo después de {f.umbral} días sin entrar]")
    return f
