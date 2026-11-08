"""
Piezas compartidas por todas las páginas de la app (Etapa 4).

  Datos        datos() y metrica(): gold se lee una vez y cada métrica se cachea (D47).
  Filtros      barra_lateral() dibuja la fecha de corte, la materia y el umbral (D46);
               filtros() los devuelve desde cualquier página.
  Paleta       COLORES_* e ICONOS_*: un color fijo por materia, condición y estado (D48).
  Visuales     encabezado(), tarjetas(), semaforo(), boton_csv(), num(), pct().

Una página típica:

    import componentes as comp
    f = comp.encabezado("Rendimiento académico", "Notas y condición a la fecha de corte.")
    notas = comp.metrica("nota_final")          # usa la fecha, la materia y el umbral de la barra
    comp.tarjetas([("Alumnos", comp.num(len(notas))), ...])
"""
from __future__ import annotations

import inspect
import os
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

from src import metricas, ml_abandono, ml_grupos  # noqa: E402
from src.config import (ASIGNATURAS, FECHA_CORTE_DEFECTO, GOLD, SIN_EVALUACIONES,  # noqa: E402
                        UMBRAL_INACTIVIDAD_DIAS)
from src.metricas import ACTIVO, INACTIVO, SIN_ACTIVIDAD  # noqa: E402

# ---------------------------------------------------------------------------
# Paleta (D48). Valores validados para daltonismo (skill de dataviz).
# ---------------------------------------------------------------------------
# Categórica, en orden fijo: los 3 primeros sirven para cualquier gráfico
# (también dispersión), así que cada materia tiene uno.
CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
COLORES_MATERIA = dict(zip(ASIGNATURAS, CATEGORICA))
SIGLAS = {nombre: datos["sigla"] for nombre, datos in ASIGNATURAS.items()}

# Estados: colores reservados, siempre acompañados de ícono y texto.
BIEN, ATENCION, SERIO, CRITICO, NEUTRO = "#0ca30c", "#fab219", "#ec835a", "#d03b3b", "#898781"
COLORES_CONDICION = {"Libre": CRITICO, "Regular": ATENCION, "Promociona": BIEN, SIN_EVALUACIONES: NEUTRO}
ICONOS_CONDICION = {"Libre": "🔴", "Regular": "🟡", "Promociona": "🟢", SIN_EVALUACIONES: "⚪"}
COLORES_ACTIVIDAD = {ACTIVO: BIEN, INACTIVO: SERIO, SIN_ACTIVIDAD: NEUTRO}
ICONOS_ACTIVIDAD = {ACTIVO: "🟢", INACTIVO: "🟠", SIN_ACTIVIDAD: "⚪"}
# Riesgo de abandono (D58): nivel del predictor o estado si no hace falta predecir.
COLORES_RIESGO = {ml_abandono.ALTO: CRITICO, ml_abandono.MEDIO: ATENCION, ml_abandono.BAJO: BIEN,
                  ml_abandono.YA_ABANDONO: "#7a2a2a", ml_abandono.SIN_ACTIVIDAD: NEUTRO}
ICONOS_RIESGO = {ml_abandono.ALTO: "🔴", ml_abandono.MEDIO: "🟡", ml_abandono.BAJO: "🟢",
                 ml_abandono.YA_ABANDONO: "⚫", ml_abandono.SIN_ACTIVIDAD: "⚪"}

# Secuencial (mapas de calor): un solo tono, de claro a oscuro.
SECUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Plantilla de plotly: fondo blanco, grilla tenue y la paleta categórica.
pio.templates["tfi"] = go.layout.Template(layout=dict(
    colorway=CATEGORICA,
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'),
    xaxis=dict(gridcolor="#e1e0d9", linecolor="#c3c2b7"),
    yaxis=dict(gridcolor="#e1e0d9", linecolor="#c3c2b7"),
    margin=dict(t=48, l=8, r=8, b=8),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    hoverlabel=dict(font_size=13),
))
pio.templates.default = "plotly_white+tfi"

CSS = """
<style>
  .semaforo {display:inline-flex; align-items:center; gap:.4rem; padding:.25rem .7rem; border-radius:999px;
             font-weight:600; border:1px solid rgba(11,11,11,.10);}
  .semaforo-Libre      {background:#fde8e8; color:#8a1f1f;}
  .semaforo-Regular    {background:#fff4d6; color:#6b4a00;}
  .semaforo-Promociona {background:#e2f6e2; color:#006300;}
  .semaforo-otro       {background:#f0efec; color:#52514e;}
  [data-testid="stMetric"] [data-testid="stMetricValue"] {font-size: 1.9rem;}
</style>
"""


def estilos() -> None:
    """CSS mínimo (como en el ejemplo de la clase 10): solo el semáforo y las tarjetas."""
    st.markdown(CSS, unsafe_allow_html=True)


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


# Módulos donde metrica() busca la función, en este orden.
MODULOS = [metricas, ml_grupos, ml_abandono]


def _funcion(nombre: str):
    for modulo in MODULOS:
        if hasattr(modulo, nombre):
            return getattr(modulo, nombre)
    raise AttributeError(f"No hay ninguna métrica llamada {nombre!r} en {[m.__name__ for m in MODULOS]}")


@st.cache_resource(max_entries=1, show_spinner="Cargando el predictor de abandono (la primera vez se entrena)…")
def _modelo_abandono(version: str) -> ml_abandono.ModeloAbandono:
    """El predictor de abandono, leído con joblib una sola vez (D58). Se guarda
    junto a gold; si los datos cambiaron, cargar_modelo lo reentrena."""
    return ml_abandono.cargar_modelo(_datos(version), ml_abandono.ruta_modelo(carpeta_gold()))


def modelo_abandono() -> ml_abandono.ModeloAbandono:
    return _modelo_abandono(version_gold())


@st.cache_data(max_entries=500, show_spinner="Calculando…")
def _metrica(nombre: str, version: str, args: tuple, kwargs: tuple):
    funcion, kwargs = _funcion(nombre), dict(kwargs)
    if "modelo" in inspect.signature(funcion).parameters:   # funciones del predictor de abandono
        kwargs.setdefault("modelo", _modelo_abandono(version))
    return funcion(_datos(version), *args, **kwargs)


def metrica(nombre: str, *args, **kwargs):
    """Llama a `src.metricas.<nombre>` (o a `src.ml_grupos` / `src.ml_abandono`) con la caché de la app.
    Si la función recibe fecha_corte, asignatura o umbral y no se pasan, usa los de la barra lateral.
    Ejemplos: metrica("nota_final"), metrica("evolucion_actividad", frecuencia="M"),
              metrica("nota_final", asignatura=None)   # todas, ignorando la barra"""
    parametros = inspect.signature(_funcion(nombre)).parameters
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

    with st.sidebar:
        st.header("Filtros")
        fecha = st.date_input("Fecha de corte", min_value=inicio, max_value=fin, key="fecha_corte",
                              format="DD/MM/YYYY",
                              help="Todo se calcula con lo que se sabía ese día (inclusive): notas de los "
                                   "instrumentos ya tomados, actividad hasta esa fecha.")
        materia = st.selectbox("Materia", [TODAS, *ASIGNATURAS], key="materia")
        umbral = st.slider("Inactivo después de (días sin entrar)", 1, 30, key="umbral",
                           help="Un alumno que no entra hace más de estos días cuenta como inactivo (D35).")
        st.button("Restablecer", on_click=_restablecer, width="stretch")
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
def encabezado(titulo: str, descripcion: str = "") -> Filtros:
    """Título de la página y, abajo, los filtros que se están usando."""
    f = filtros()
    st.title(titulo)
    if descripcion:
        st.markdown(descripcion)
    st.caption(f"Corte: **{fmt_fecha(f.fecha_corte)}** · {f.materia} · "
               f"Inactivo después de {f.umbral} días sin entrar")
    return f


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



# ---------------------------------------------------------------------------
# Predictor de abandono (D58): bloques para la Ficha individual y Matrícula y alertas
# ---------------------------------------------------------------------------
def texto_riesgo(fila) -> str:
    """'🔴 Alto · 42 %' o '⚫ Ya abandonó' (ícono + texto, nunca solo color)."""
    nivel = fila["nivel_riesgo"]
    prob = f" · {pct(fila['probabilidad'], 0)}" if pd.notna(fila["probabilidad"]) else ""
    return f"{ICONOS_RIESGO.get(nivel, '')} {nivel}{prob}"


def riesgo_abandono_alumno(id_alumno: str) -> None:
    """Para la Ficha individual: el riesgo de abandono del alumno en cada materia,
    con los motivos y su evolución semana a semana. Uso: comp.riesgo_abandono_alumno(id)."""
    import plotly.express as px

    r = metrica("riesgo_alumno", id_alumno=id_alumno)
    if r.empty:
        st.caption("El alumno no está en la base de ninguna materia.")
        return
    umbral = 100 * metrica("info_modelo")["umbral"]
    cols = st.columns(len(r))
    for col, (_, fila) in zip(cols, r.iterrows()):
        with col.container(border=True):
            st.markdown(f"**{SIGLAS.get(fila['asignatura'], fila['asignatura'])}** · riesgo de abandono")
            st.markdown(f"### {texto_riesgo(fila)}")
            if fila["estado_abandono"] == ml_abandono.CURSANDO:
                st.caption(f"Probabilidad de no entrar en los próximos {ml_abandono.ABANDONO_HORIZONTE_DIAS} días "
                           f"(riesgo alto desde {pct(umbral, 0)}).")
                if fila["motivos"]:
                    st.markdown(f"Señales: {fila['motivos']}.")
            elif fila["estado_abandono"] == ml_abandono.YA_ABANDONO:
                st.caption(f"Hace {num(fila['dias_sin_actividad'])} días que no entra: ya cumple la definición "
                           "de abandono. Conviene contactarlo.")
            else:
                st.caption("Nunca entró al aula hasta la fecha de corte.")
    ev = metrica("evolucion_riesgo", id_alumno=id_alumno)
    ev = ev[ev["probabilidad"].notna()].assign(materia=lambda t: t["asignatura"].map(SIGLAS))
    if len(ev) > 1:
        fig = px.line(ev, x="fecha_corte", y="probabilidad", color="asignatura", markers=True,
                      color_discrete_map=COLORES_MATERIA,
                      labels={"fecha_corte": "", "probabilidad": "Probabilidad de abandono (%)", "asignatura": ""})
        fig.add_hline(y=umbral, line_dash="dash", line_color=CRITICO, annotation_text="Riesgo alto")
        fig.update_layout(height=280, yaxis_range=[0, 100])
        st.plotly_chart(fig, width="stretch")
        st.caption("Cada punto usa solo lo que se sabía ese día. Sin punto = ese día no venía entrando.")
