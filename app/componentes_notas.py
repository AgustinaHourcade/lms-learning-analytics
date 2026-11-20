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

import html as _html

import pandas as pd
import streamlit as st

import componentes as _base
from componentes import *  # noqa: F401,F403  (datos, metrica, filtros, num, pct, boton_csv, TODAS, ...)
from componentes import Filtros, filtros, fmt_fecha  # noqa: F401  (explícitos para los linters)
from src import textos
from src.config import ASIGNATURAS, SIN_EVALUACIONES
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD

# ---------------------------------------------------------------------------
# Paleta
# ---------------------------------------------------------------------------
FONDO, TARJETA, BORDE, BORDE_SUAVE = "#F7F6F3", "#FFFFFF", "#E3E1DC", "#EFEDE8"
TEXTO, TEXTO_2, TEXTO_3, TEXTO_4 = "#1A1917", "#57544C", "#6B6861", "#8A867C"
ACCION = "#1B4B8F"

SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}
# Paleta de materias de General (D78): fuera del semáforo, para que PYE no choque con el verde de Promociona.
_POR_SIGLA = {"ALG": "#1E4FA8", "AED": "#7C3AED", "PYE": "#0891B2"}
COLORES_MATERIA = {m: _POR_SIGLA[s] for m, s in SIGLAS.items()}
# Etiqueta de materia (fondo, texto): tinte suave del color de la materia.
TINTES_MATERIA = {"ALG": ("#E8EEF8", "#1E3F80"), "AED": ("#F1EBFD", "#5B21B6"), "PYE": ("#E3F4F8", "#0E6378")}

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
/* nvp-*: piezas del rediseño. Los selectores llevan elemento + dos clases (p.tfi.nvp-x o .tfi p.nvp-x)
   para ganarle al estilo de párrafo de Streamlit (si no, todo sale a 16 px). */
p.tfi.nvp-lectura {margin:4px 0 16px; padding:12px 16px; max-width:none; background:#FFFFFF; border:1px solid #E3E1DC;
  border-left:3px solid #1B4B8F; border-radius:10px; font:500 14px/1.55 Inter, sans-serif; color:#1A1917;}
.nvp-ayuda {display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px;
  border-radius:999px; border:1px solid #C9C6BF; font:600 10px Inter, sans-serif; color:#6B6861; cursor:help;
  text-transform:none; letter-spacing:0; vertical-align:middle; margin-left:5px; flex:0 0 15px;}
.tfi p.nvp-etq {margin:0 0 10px; display:flex; align-items:center; gap:2px; font:600 11px/1.3 Inter, sans-serif;
  letter-spacing:.06em; text-transform:uppercase; color:#6B6861; white-space:nowrap;}
.tfi p.nvp-etq.alerta {color:#8A3A31;}
.tfi p.nvp-num {margin:0 0 6px; font:600 32px/1.1 'Space Grotesk', Inter, sans-serif; letter-spacing:-.02em;
  font-variant-numeric:tabular-nums; color:#1A1917;}
.tfi p.nvp-num small {font:500 13px Inter, sans-serif; color:#6B6861; letter-spacing:0; margin-left:4px;}
.tfi p.nvp-num.alerta {color:#93241C;}
.tfi p.nvp-det {margin:8px 0 0; font:400 12px/1.5 Inter, sans-serif; color:#6B6861;}
.tfi p.nvp-det strong {font-weight:600; color:#1A1917;}
.tfi p.nvp-det.alerta, .tfi p.nvp-det.alerta strong {color:#7A3028;}
.tfi p.nvp-linea {margin:0 0 4px; font:500 12.5px/1.5 Inter, sans-serif; color:#57544C;}
.tfi p.nvp-linea.alerta {color:#7A3028;}
.nvp-filas {margin:0; display:grid; gap:4px;}
.nvp-filas div {display:grid; grid-template-columns:34px 64px 1fr; align-items:baseline; gap:6px;
  font:400 12px Inter, sans-serif; color:#6B6861;}
.nvp-filas b {font:600 11px Inter, sans-serif; color:#35332D; letter-spacing:.03em;}
.nvp-filas span.v {font:600 19px 'Space Grotesk', Inter, sans-serif; color:#1A1917; font-variant-numeric:tabular-nums;
  white-space:nowrap;}
.nvp-filas span.s {font-variant-numeric:tabular-nums; white-space:nowrap;}
.nvp-delta {display:inline-block; padding:1px 7px; border-radius:999px; background:#FFFFFF; border:1px solid #F2CFC9;
  color:#7A3028; font:600 11px Inter, sans-serif; font-variant-numeric:tabular-nums;}
p.tfi.nvp-titulo, .tfi p.nvp-titulo {margin:0 0 4px; font:600 15px/1.4 'Space Grotesk', Inter, sans-serif;
  color:#1A1917; display:flex; align-items:center; gap:2px;}
p.tfi.nvp-intro, .tfi p.nvp-intro {margin:0 0 12px; font:400 12.5px/1.5 Inter, sans-serif; color:#6B6861;}
p.tfi.nvp-pie {margin:2px 0 0; font:400 12px/1.5 Inter, sans-serif; color:#6B6861;}
p.tfi.nvp-pie strong {font-weight:600; color:#35332D;}
.nvp-grillas {display:grid; grid-template-columns:repeat(auto-fit, minmax(250px, 1fr)); gap:22px;}
.nvp-cuad {display:grid; grid-template-columns:52px 1fr 1fr; gap:6px; align-items:stretch;}
.nvp-cuad .col {font:500 11px Inter, sans-serif; color:#6B6861; text-align:center; padding-bottom:2px;}
.nvp-cuad .fila {font:500 11px Inter, sans-serif; color:#6B6861; align-self:center;}
.nvp-cuad .celda {border:1px solid; border-radius:9px; padding:10px 12px; display:flex; align-items:baseline;
  justify-content:space-between; gap:6px;}
.nvp-cuad .n {font:600 22px/1.1 'Space Grotesk', Inter, sans-serif;}
.nvp-cuad .p {font:500 12px Inter, sans-serif;}
.nvp-acciones {display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:14px 24px;
  margin-top:18px; padding-top:16px; border-top:1px solid #EFEDE8;}
[class*="st-key-nvp_kpi_"] {background:#FFFFFF; border:1px solid #E3E1DC; border-radius:13px; padding:16px 18px 14px;
  gap:0;}
.st-key-nvp_kpi_riesgo {background:#FBE9E6; border-color:#F2CFC9; box-shadow:inset 4px 0 0 #B02A20;}
.st-key-nvp_kpi_riesgo button {padding:0; min-height:0; margin-top:10px;}
.st-key-nvp_kpi_riesgo button p {font-size:12.5px; font-weight:600; color:#93241C;}
.st-key-nvp_caja_hacer {background:#FFFFFF; border:1px solid #E3E1DC; border-radius:13px; padding:18px 20px;}
.st-key-nvp_lista {background:#FFFFFF; border:1px solid #E3E1DC; border-radius:13px; padding:18px 20px;}
</style>
"""


# ---------------------------------------------------------------------------
# Piezas HTML (se pintan con html(); clases tfi-* en CSS)
# ---------------------------------------------------------------------------
def num(x, decimales: int = 0) -> str:
    """Como componentes.num, pero con el redondeo de escuela de src.textos (144,5 -> 145),
    el mismo que hacen los tooltips y las tablas: así un número se ve igual en todos lados."""
    return "–" if x is None or pd.isna(x) else textos.numero(float(x), decimales)


def pct(x, decimales: int = 1) -> str:
    return "–" if x is None or pd.isna(x) else f"{num(x, decimales)} %"


def esc(texto) -> str:
    return _html.escape(str(texto), quote=True)


def ayuda(texto: str) -> str:
    """Círculo (?) con la definición al pasar el mouse (las explicaciones van acá, no en la página)."""
    return f'<span class="nvp-ayuda" title="{esc(texto)}" aria-label="{esc(texto)}">?</span>'


def titulo(texto: str, tip: str = "") -> str:
    """Título de una pieza: la conclusión, calculada con los datos, con su (?)."""
    return f'<p class="tfi nvp-titulo">{texto}{ayuda(tip) if tip else ""}</p>'


def kpi(etiqueta: str, cuerpo: str, detalle: str = "", tip: str = "", alerta: bool = False) -> str:
    """Contenido de una tarjeta de KPI (va dentro de st.container(key="nvp_kpi_...")).
    cuerpo = número grande (clase nvp-num) o una línea por materia (filas_materia()).
    etiqueta admite HTML (por ejemplo, la ρ sin pasar a mayúscula)."""
    a = " alerta" if alerta else ""
    return (f'<div class="tfi"><p class="nvp-etq{a}">{etiqueta}{ayuda(tip) if tip else ""}</p>{cuerpo}'
            + (f'<p class="nvp-det{a}">{detalle}</p>' if detalle else "") + "</div>")


def linea(texto: str, alerta: bool = False) -> str:
    """Una línea de dato debajo del número grande de un KPI."""
    return f'<p class="nvp-linea{" alerta" if alerta else ""}">{texto}</p>'


def filas_materia(filas: list[tuple[str, str, str]]) -> str:
    """[(sigla, valor, detalle)] -> una línea por materia dentro de una tarjeta de KPI."""
    return ('<div class="nvp-filas">' + "".join(
        f'<div><b>{s}</b><span class="v">{v}</span><span class="s">{d}</span></div>' for s, v, d in filas)
        + "</div>")


def grafico(fig, destino=st) -> None:
    """componentes.grafico (sin barra de herramientas) con coma decimal y punto de miles en ejes y tooltips."""
    fig.update_layout(separators=",.")
    _base.grafico(fig, destino)


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


def titulo_materia(materia: str, sub: str = "", sigla: bool = False) -> str:
    """Encabezado de un bloque por materia: cuadrito de color + nombre o sigla (+ dato a la derecha).
    sigla=True en grillas angostas, para que AED no ocupe dos líneas y desalinee la fila."""
    extra = f'<span class="sub num">{sub}</span>' if sub else ""
    nombre = SIGLAS.get(materia, materia) if sigla else materia
    return (f'<p class="tfi tfi-titulo-materia" title="{esc(materia)}">'
            f'{cuadrito(COLORES_MATERIA.get(materia, NEUTRO))}{nombre}{extra}</p>')


def leyenda(items: list[tuple[str, str, str]]) -> str:
    """items = [(texto, color, forma)], forma en punto | cuadro | linea | linea_punteada, o un tono de
    _FORMAS (bien, atencion, critico, neutro...) para dibujar la misma forma que el marcador del gráfico."""
    marcas = {"punto": "width:10px;height:10px;border-radius:999px", "cuadro": "width:11px;height:11px;border-radius:2px",
              "linea": "width:18px;height:2px", "linea_punteada": "width:18px;height:0;border-top:2px dashed"}

    def marca(color, forma):
        if forma in _FORMAS:
            return icono(forma, 11, color)
        fondo = f"border-color:{color}" if forma == "linea_punteada" else f"background:{color}"
        return f'<span style="{marcas[forma]};{fondo};display:inline-block"></span>'

    partes = [f'<span class="item">{marca(color, forma)}{texto}</span>' for texto, color, forma in items]
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
