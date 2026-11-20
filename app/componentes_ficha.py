"""
Sistema visual de la Ficha individual (app/paginas/6_ficha_individual.py), rediseño D87.

Mismo criterio que General, Matrícula, Notas, Rendimiento y Trazabilidad: reexporta todo
lo de componentes (datos, metrica, filtros, num, pct, chip_estado, pastilla_condicion...)
y redefine encima solo lo propio. La página hace `import componentes_ficha as comp` y el
resto de las páginas no se entera.

Reglas de la ficha:
  - Verde, ámbar y rojo son solo de la condición (semáforo con forma + color + palabra).
    Las materias usan azul / violeta / gris pizarra (COLORES_MATERIA de acá), con
    distinta luminosidad para que se separen también con deuteranopia y protanopia.
  - Mismo orden de materias en todas las secciones: el del ESQUEMA (el de la tabla).
  - Números en es-AR: coma decimal, "%" con espacio, fechas dd/mm/aaaa (también en los CSV).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import componentes as _base
from componentes import *  # noqa: F401,F403  (datos, metrica, filtros, num, pct, esc, html, ...)
from componentes import esc, num  # noqa: F401  (explícitos para los linters)
from src.config import ESQUEMA

# ---------------------------------------------------------------------------
# Paleta de materias de la ficha (fuera del semáforo). Verificada con simulación de
# deuteranopia y protanopia (Machado 2009): diferencia mínima entre materias ΔE 30, y
# todas con contraste >= 3:1 contra el blanco de la tarjeta (marcas gráficas, WCAG 1.4.11).
# ---------------------------------------------------------------------------
ORDEN = list(ESQUEMA)    # Álgebra, Probabilidad y Estadística, AED
COLORES_MATERIA = {"Álgebra": "#3B82F6", "Probabilidad y Estadística": "#4C1D95",
                   "Algoritmos y Estructuras de Datos": "#64748B"}
# Etiquetas de sigla: fondo suave y texto oscuro del mismo matiz (contraste >= 7:1).
CHIP_MATERIA = {"Álgebra": ("#E8F0FE", "#1E4FA8"), "Probabilidad y Estadística": ("#EFEAF8", "#4C1D95"),
                "Algoritmos y Estructuras de Datos": ("#EEF1F4", "#3E4A5C")}
GRIS_NO_RINDIO = "#D9D6CF"
ROJO = _base.TONOS_ESTADO["critico"][2]
SECUENCIAL = ["#F1F5FB", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

CSS = """
<style>
  .fx-cab {display:flex; flex-wrap:wrap; gap:16px; align-items:flex-start; padding:18px 18px 16px;}
  .fx-avatar {width:50px; height:50px; flex:0 0 50px; border-radius:999px; background:#EAF0F8; color:#1B4B8F;
              display:flex; align-items:center; justify-content:center; font:600 16px 'Space Grotesk', Inter, sans-serif;}
  .fx-quien {flex:1 1 420px; min-width:0;}
  .fi-card h2.fx-nombre {margin:0 0 2px !important; font:600 22px 'Space Grotesk', Inter, sans-serif !important;
                          letter-spacing:-.015em;}
  .fx-id {margin:0 0 8px; font-size:12px; color:#6B6861;}
  .fi-card h3.fx-insight {margin:0 0 10px !important; font:600 16px 'Space Grotesk', Inter, sans-serif !important;
                           color:#1A1917;}
  .fx-chips {display:flex; flex-wrap:wrap; gap:7px;}
  .fx-alerta {display:inline-flex; align-items:center; gap:6px; height:28px; padding:0 11px; border-radius:999px;
              background:#FBE9E6; color:#93241C; font:600 12px Inter, sans-serif; white-space:nowrap;}
  .fx-sigla {display:inline-flex; align-items:center; height:20px; padding:0 7px; border-radius:5px;
             font:600 11px Inter, sans-serif; white-space:nowrap;}
  .fx-badge {display:inline-flex; align-items:center; gap:4px; height:20px; padding:0 7px; border-radius:5px;
             font:500 11px Inter, sans-serif; white-space:nowrap; background:#F1EFEA; color:#57544C;}
  .fx-badge.no {background:#FBE9E6; color:#93241C; font-weight:600;}
  .fx-sub {display:block; font-size:11px; color:#6B6861; margin-top:2px; white-space:nowrap;}
  .fx-grande {font-size:15px; font-weight:600; color:#1A1917;}
  .fx-tabla th, .fx-tabla td {padding-left:9px !important; padding-right:9px !important;}
  .fx-tabla td:first-child {min-width:150px;}
  .fx-tabla th {white-space:normal !important; vertical-align:bottom;}
  .fx-grilla {display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:22px; padding:2px 16px 18px;}
  .fx-col-titulo {margin:0 0 12px; display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600;
                  color:#1A1917;}
  .fx-fila {display:flex; align-items:center; gap:10px; margin-bottom:10px;}
  .fx-fila-et {flex:0 0 118px; font-size:12px; color:#57544C; white-space:nowrap;}
  .fx-fila-bar {flex:1 1 auto; min-width:60px;}
  .fx-fila-val {flex:0 0 92px; text-align:right; line-height:1.25;}
  .fx-fila-val b {font-size:12px; font-weight:600; color:#1A1917;}
  .fx-fila-val span {display:block; font-size:11px; color:#6B6861;}
  .fx-info {display:inline-flex; align-items:center; justify-content:center; width:15px; height:15px; margin-left:3px;
            border-radius:999px; border:1px solid #B9B5AC; color:#6B6861; font:600 9px Inter, sans-serif;
            cursor:help; vertical-align:1px;}
  .fx-leyenda {padding:0 16px 14px; font-size:12px; color:#6B6861;}
  .fx-vacio {margin:0 16px 14px; padding:12px 14px; border:1px dashed #D9D6CF; border-radius:10px;
             background:#FBFAF8; font-size:13px; color:#57544C;}
</style>
"""


def estilos() -> None:
    """CSS propio de la ficha (se suma al global de componentes)."""
    st.markdown("\n".join(linea for linea in CSS.splitlines() if linea.strip()), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------
def sigla(asignatura: str) -> str:
    fondo, texto = CHIP_MATERIA.get(asignatura, ("#F1EFEA", "#57544C"))
    return (f'<span class="fx-sigla" style="background:{fondo};color:{texto}">'
            f'{esc(_base.SIGLAS.get(asignatura, asignatura))}</span>')


def info(texto: str) -> str:
    """El ⓘ con un tooltip nativo (title): las explicaciones van acá, no en el cuerpo."""
    return f'<span class="fx-info" title="{esc(texto)}" aria-label="{esc(texto)}">i</span>'


def signo(x, decimales: int = 1) -> str:
    """+6,0 / −12,0 / 0,0 (con el signo menos tipográfico)."""
    if x is None or pd.isna(x):
        return "–"
    return ("+" if x > 0 else "−" if x < 0 else "") + num(abs(x), decimales)


def dias(n: int) -> str:
    return f"{n} {'día' if n == 1 else 'días'}"


def sparkline(valores, color: str, tope: float, ancho: int = 78, alto: int = 24) -> str:
    """Mini línea SVG de las últimas semanas; `tope` es el mismo en todas las materias."""
    v = [float(x) for x in valores]
    if not v:
        return ""
    tope, n = max(tope, 1.0), len(v)
    puntos = " ".join(f"{i * (ancho - 2) / max(n - 1, 1) + 1:.1f},{alto - 2 - x / tope * (alto - 4):.1f}"
                      for i, x in enumerate(v))
    detalle = ", ".join(num(x) for x in v)
    return (f'<svg viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" role="img" '
            f'aria-label="Interacciones por semana: {detalle}" style="display:block">'
            f'<title>Interacciones por semana (últimas {n}): {detalle}</title>'
            f'<polyline points="{puntos}" fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def grafico(fig, contenedor=st) -> None:
    """Gráfico con la plantilla de la app y separadores es-AR (coma decimal, punto de miles)."""
    fig.update_layout(separators=",.", hoverlabel=dict(bgcolor="#FFFFFF", font_color="#1A1917"))
    _base.grafico(fig, contenedor)


def boton_csv(df: pd.DataFrame, nombre: str, etiqueta: str, key: str | None = None) -> None:
    """CSV para Excel en castellano (; y coma decimal) con las fechas en dd/mm/aaaa."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            con_hora = (df[col].dropna().dt.normalize() != df[col].dropna()).any()
            df[col] = df[col].dt.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")
    st.download_button(etiqueta, df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=f"{nombre}.csv", mime="text/csv", icon=":material/download:", key=key)
