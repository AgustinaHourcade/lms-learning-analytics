"""
Piezas compartidas por todas las páginas de la app (Etapa 4).

  Datos        datos() y metrica(): gold se lee una vez y cada métrica se cachea (D47).
  Filtros      barra_lateral() dibuja la fecha de corte, la materia y el umbral (D46);
               filtros() los devuelve desde cualquier página.
  Paleta       COLORES_* e ICONOS_*: un color fijo por materia, tipo, condición y estado (D48, D55).
  Visuales     encabezado(), tarjetas() (KPI), tarjeta() (contenedor blanco con título),
               lectura() y nota() (qué mirar), leyenda(), chip(), mini_tarjeta(),
               semaforo(), boton_csv(), num(), pct(). El CSS está en app/estilos.css.

Una página típica:

    import componentes as comp
    f = comp.encabezado("Rendimiento académico", "Notas y condición a la fecha de corte.")
    notas = comp.metrica("nota_final")          # usa la fecha, la materia y el umbral de la barra
    comp.tarjetas([("Alumnos", comp.num(len(notas))), ...])
"""
from __future__ import annotations

import inspect
import os
import re
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

from src import metricas  # noqa: E402
from src.config import (ASIGNATURAS, FECHA_CORTE_DEFECTO, GOLD, SIN_EVALUACIONES,  # noqa: E402
                        UMBRAL_INACTIVIDAD_DIAS)
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD  # noqa: E402

# ---------------------------------------------------------------------------
# Paleta y sistema visual (D48, D55). Los mismos valores están en .streamlit/config.toml
# y en app/estilos.css. Regla: el color de materia identifica y el del semáforo evalúa;
# nunca se mezclan en un mismo elemento, y un estado nunca va solo con color.
# ---------------------------------------------------------------------------
FONDO, TARJETA, BORDE = "#F7F6F3", "#FFFFFF", "#E3E1DC"
TEXTO, TEXTO_2, TEXTO_3, TEXTO_4 = "#1A1917", "#57544C", "#6B6861", "#8A867C"
ACCION, GRILLA, EJE = "#1B4B8F", "#F1EFEA", "#D9D6CF"

# Categórica, en orden fijo: los 3 primeros son las materias en el orden de ASIGNATURAS
# (ALG azul, AED naranja, PYE verde), así que cada materia tiene su color en cualquier gráfico.
CATEGORICA = ["#2563C9", "#D4661F", "#0E8F62", "#C98A12", "#6E56CF", "#B02A20", "#A8A49B"]
_COLOR_SIGLA = {"ALG": "#2563C9", "AED": "#D4661F", "PYE": "#0E8F62"}
COLORES_MATERIA = {nombre: _COLOR_SIGLA[datos["sigla"]] for nombre, datos in ASIGNATURAS.items()}
SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}
# Nombre corto para leyendas y textos ("Probabilidad" en vez de "Probabilidad y Estadística").
CORTOS = {nombre: nombre.split(" y ")[0] for nombre in ASIGNATURAS}

# Tipos de interacción (categorías de dim_accion). No comparten gráfico con las materias.
COLORES_CATEGORIA = {"Contenido": "#1B4B8F", "Navegación": "#D4661F", "Evaluación": "#16734A",
                     "Comunicación": "#C98A12", "Notas": "#A8A49B", "Agenda": "#CFCBC2"}

# Estados: colores reservados, siempre acompañados de ícono y texto.
BIEN, ATENCION, SERIO, CRITICO, NEUTRO = "#16734A", "#C98A12", "#D9822B", "#B02A20", "#A8A49B"
COLORES_CONDICION = {"Libre": CRITICO, "Regular": ATENCION, "Promociona": BIEN, SIN_EVALUACIONES: NEUTRO}
ICONOS_CONDICION = {"Libre": "🔴", "Regular": "🟡", "Promociona": "🟢", SIN_EVALUACIONES: "⚪"}
COLORES_ACTIVIDAD = {ACTIVO: BIEN, INACTIVO: SERIO, SIN_ACTIVIDAD: NEUTRO}
ICONOS_ACTIVIDAD = {ACTIVO: "🟢", INACTIVO: "🟠", SIN_ACTIVIDAD: "⚪"}

# Secuencial (mapas de calor): un solo tono, de claro a oscuro.
SECUENCIAL = ["#EFF4FB", "#DEE9F6", "#C5D9EF", "#A9C4E6", "#7FA6D9", "#4B7FC4", "#1B4B8F", "#0D2A4F"]

# Plantilla de plotly: los gráficos van dentro de tarjetas blancas, con grilla tenue,
# ejes grises, leyenda arriba a la izquierda y tooltip blanco.
pio.templates["tfi"] = go.layout.Template(layout=dict(
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
pio.templates.default = "plotly_white+tfi"

CSS = Path(__file__).with_name("estilos.css")
ICONO_DATO = ('<svg viewBox="0 0 16 16" width="17" height="17" aria-hidden="true">'
              '<circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" stroke-width="1.5"/>'
              '<path d="M8 7.2v4.2M8 4.8v.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>')


def estilos() -> None:
    """Carga app/estilos.css (D55): tarjetas, KPI, pestañas, controles, lecturas y semáforo."""
    st.markdown(f"<style>{CSS.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


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


@st.cache_data(max_entries=500, show_spinner="Calculando…")
def _metrica(nombre: str, version: str, args: tuple, kwargs: tuple):
    return getattr(metricas, nombre)(_datos(version), *args, **dict(kwargs))


def metrica(nombre: str, *args, **kwargs):
    """Llama a `src.metricas.<nombre>` con la caché de la app. Si la función recibe
    fecha_corte, asignatura o umbral y no se pasan, usa los de la barra lateral.
    Ejemplos: metrica("nota_final"), metrica("evolucion_actividad", frecuencia="M"),
              metrica("nota_final", asignatura=None)   # todas, ignorando la barra"""
    parametros = inspect.signature(getattr(metricas, nombre)).parameters
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


def rango_fechas() -> tuple[date, date]:
    """Primer y último día que se puede elegir (para filtros de fechas de una página)."""
    return _rango_fechas(datos())


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

    with st.sidebar, st.container(border=True, key="tarjeta_filtros"):
        st.markdown('<p class="tfi-etiqueta">Filtros</p>', unsafe_allow_html=True)
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
def _md(texto: str) -> str:
    """Markdown mínimo para los recuadros en HTML: **negrita** y *cursiva*."""
    texto = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texto)
    return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", texto)


def _html(contenido: str) -> None:
    st.markdown(contenido, unsafe_allow_html=True)


def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página, la explicación en una línea y los filtros que se están usando."""
    f = filtros()
    st.title(titulo, anchor=False)
    if descripcion:
        _html(f'<p class="tfi-desc">{_md(descripcion)}</p>')
    st.caption(f"Corte: **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
               f"Inactivo después de {f.umbral} días sin entrar")
    return f


def tarjeta(clave: str, titulo: str = "", subtitulo: str = ""):
    """Contenedor blanco con borde (D55) y, si se pasa, su título y explicación. Se usa con `with`:
        with comp.tarjeta("evolucion", "Interacciones por semana", "Los triángulos son las evaluaciones."):
            st.plotly_chart(fig)"""
    c = st.container(border=True, key=f"tarjeta_{clave}")
    if titulo or subtitulo:
        c.markdown((f'<p class="tfi-h3">{titulo}</p>' if titulo else "")
                   + (f'<p class="tfi-sub">{_md(subtitulo)}</p>' if subtitulo else ""), unsafe_allow_html=True)
    return c


def titulo_tarjeta(titulo: str, subtitulo: str = "") -> None:
    """Título y explicación de una tarjeta cuando van al lado de un control (dentro de una columna)."""
    _html(f'<p class="tfi-h3">{titulo}</p>' + (f'<p class="tfi-sub">{_md(subtitulo)}</p>' if subtitulo else ""))


def lectura(texto: str, titulo: str = "", tono: str = "info") -> None:
    """Recuadro con el dato que hay que mirar: título en negrita y la explicación.
    tono: "info" (azul) o "atencion" (ámbar)."""
    cuerpo = (f"<strong>{titulo}</strong> " if titulo else "") + _md(texto)
    _html(f'<div class="tfi-lectura {tono}">{ICONO_DATO}<p>{cuerpo}</p></div>')


def nota(texto: str, tono: str = "") -> None:
    """Nota debajo de un gráfico: cómo leerlo o qué se ve (fondo gris; tono="atencion" para ámbar)."""
    _html(f'<p class="tfi-nota {tono}">{_md(texto)}</p>')


def chip(texto: str, gris: bool = False) -> str:
    """HTML de una etiqueta redondeada (por ej., 'Pico: miércoles de 20 a 21 h')."""
    return f'<span class="tfi-chip{" gris" if gris else ""}">{texto}</span>'


def leyenda(colores: dict, linea: bool = False) -> None:
    """Leyenda en HTML ({etiqueta: color}), para gráficos que se dibujan sin la de plotly.
    linea=True dibuja un trazo (series en el tiempo) en vez de un cuadrado."""
    clase = ' class="linea"' if linea else ""
    _html('<div class="tfi-leyenda">' + "".join(
        f'<span><i{clase} style="background:{c}"></i>{e}</span>' for e, c in colores.items()) + "</div>")


def mini_tarjeta(titulo: str, valor: str, texto: str, color: str | None = None) -> str:
    """HTML de una tarjeta chica (resumen de una materia dentro de una tarjeta grande)."""
    marca = f'<i style="background:{color}"></i>' if color else ""
    return (f'<div class="tfi-mini"><p class="titulo">{marca}{titulo}</p><p class="valor">{valor}</p>'
            f'<p class="texto">{_md(texto)}</p></div>')


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

