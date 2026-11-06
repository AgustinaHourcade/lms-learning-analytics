"""
Cargar archivo (D28, D40, D50): suma un Excel nuevo del LMS y recalcula todo.

Dos pasos: 1) se valida y se muestra qué se reconoció; 2) el usuario confirma
y se llama a agregar_archivo(), que lo copia a data/raw/ y corre el pipeline.
Si algo falla, data/raw/ y los datos quedan como estaban.
"""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

import componentes as comp
from src.config import RAW
from src.ingesta import descubrir, seleccionar
from src.pipeline import agregar_archivo, procesar
from src.validacion import validar_archivo

TIPOS = {"calificaciones": "Calificaciones", "trazabilidad": "Trazabilidad",
         "participacion": "Reporte de participación", "matriculados": "Matriculados"}

st.title("Cargar archivo")
st.markdown(
    "Subí un Excel exportado del LMS (por ejemplo, las notas de un parcial nuevo). Se reconoce por su "
    "**contenido**, así que no importa cómo se llame. Antes de usarlo se valida: si tiene un problema, "
    "se muestra el motivo y no se toca nada."
)


@st.cache_data(show_spinner="Validando el archivo…", max_entries=20)
def validar(contenido: bytes, nombre: str, estado_raw: tuple):  # estado_raw: revalida si cambió data/raw
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / nombre
        path.write_bytes(contenido)
        info = validar_archivo(path, RAW)
    return {"ok": info.ok, "tipo": info.tipo, "asignatura": info.asignatura, "instrumento": info.instrumento,
            "fecha_exportacion": info.fecha_exportacion, "fila_encabezado": info.fila_encabezado,
            "errores": info.errores, "avisos": info.avisos}


def estado_raw() -> tuple:
    return tuple(sorted((str(p), p.stat().st_mtime_ns) for p in RAW.rglob("*.xlsx")))


@st.cache_data(show_spinner="Leyendo los archivos cargados…")
def archivos_cargados(estado: tuple) -> tuple[pd.DataFrame, list[str]]:
    infos = descubrir(RAW)
    usados, avisos = seleccionar([i for i in infos if i.ok])
    usados = {i.path for i in usados}
    filas = [{"Carpeta": i.path.parent.name, "Archivo": i.nombre, "Tipo": TIPOS.get(i.tipo, i.tipo or "?"),
              "Materia": i.asignatura or "", "Instrumento": i.instrumento or "",
              "Exportado": i.fecha_exportacion, "Se usa": "Sí" if i.path in usados else "No (reemplazado)"}
             for i in infos]
    return pd.DataFrame(filas).sort_values(["Tipo", "Materia", "Instrumento", "Exportado"]), avisos


def foto() -> pd.DataFrame:
    """Lo que hay cargado ahora, por materia (D51). Ignora la materia de la barra."""
    return comp.metrica("foto_datos", asignatura=None)


# Tarjetas que se muestran para la materia del archivo: (clave, decimales, ¿subir es malo?)
TARJETAS_ANTES_DESPUES = [("notas", 0, False), ("instrumentos", 0, False), ("nota_promedio", 2, False),
                          ("alumnos", 0, False), ("promociona", 0, False), ("regular", 0, False),
                          ("libre", 0, True), ("eventos", 0, False)]


def mostrar_antes_despues(antes: pd.DataFrame, despues: pd.DataFrame, asignatura: str | None) -> None:
    """Compara los indicadores antes y después de la carga, para verificar que
    los datos nuevos entraron (D51)."""
    comp_ = comp.comparar_fotos(antes, despues)
    st.subheader("Antes y después de la carga")
    if not comp_["diferencia"].fillna(0).ne(0).any():
        st.warning("No cambió ningún indicador. Puede pasar si el archivo ya estaba cargado o si reemplazó a "
                   "una exportación con los mismos datos.", icon=":material/info:")
    st.caption("Calculado con todos los datos cargados (sin fecha de corte), así un instrumento nuevo se ve "
               "aunque sea posterior a la fecha elegida en la barra. La nota promedio incluye los 0 de quienes "
               "no rindieron y está en la escala de la materia (Álgebra sobre 120, el resto sobre 100).")

    materias = [asignatura] if asignatura in set(comp_["asignatura"]) else list(comp_["asignatura"].unique())
    for materia in materias:
        filas = comp_[comp_["asignatura"] == materia].set_index("clave")
        st.markdown(f"**{materia}**")
        items = []
        for clave, dec, invertir in TARJETAS_ANTES_DESPUES:
            f = filas.loc[clave]
            dif = f["diferencia"]
            items.append({"label": f["indicador"], "value": comp.num(f["despues"], dec),
                          "delta": None if pd.isna(dif) or dif == 0 else
                          f"{'+' if dif > 0 else ''}{comp.num(dif, dec)} (antes {comp.num(f['antes'], dec)})",
                          "delta_color": "inverse" if invertir else "normal"})
        comp.tarjetas(items, columnas=4)

    with st.expander("Todas las materias e indicadores"):
        tabla = comp_.drop(columns="clave").rename(columns={
            "asignatura": "Materia", "indicador": "Indicador", "antes": "Antes", "despues": "Después",
            "diferencia": "Diferencia"})
        st.dataframe(tabla.style.format({"Antes": "{:,.2f}", "Después": "{:,.2f}", "Diferencia": "{:+,.2f}"},
                                        decimal=",", thousands=".")
                     .map(lambda v: "color: #0ca30c" if v > 0 else "color: #d03b3b" if v < 0 else "",
                          subset=["Diferencia"]),
                     width="stretch", hide_index=True)


# Resultado de la última carga (sobrevive al rerun que limpia el uploader).
if resultado := st.session_state.pop("resultado_carga", None):
    if resultado["ok"]:
        st.success(resultado["mensaje"], icon=":material/check_circle:")
    else:
        st.error(resultado["mensaje"], icon=":material/error:")
    for e in resultado["errores"]:
        st.markdown(f"- ❌ {e}")
    for a in resultado["avisos"]:
        st.markdown(f"- ⚠️ {a}")
    if resultado.get("antes") is not None:
        mostrar_antes_despues(resultado["antes"], resultado["despues"], resultado["asignatura"])
    if resultado.get("gold"):
        with st.expander("Filas de cada tabla después de recalcular"):
            st.dataframe(pd.Series(resultado["gold"], name="filas").rename_axis("tabla"), width="content")

# ---------------------------------------------------------------------------
# Paso 1: subir y validar
# ---------------------------------------------------------------------------
st.subheader("1. Subir y validar")
st.session_state.setdefault("uploader", 0)
archivo = st.file_uploader("Excel del LMS (.xlsx)", type=["xlsx"], key=f"uploader_{st.session_state['uploader']}")

if archivo is not None:
    contenido = archivo.getvalue()
    v = validar(contenido, archivo.name, estado_raw())

    datos = {
        "Tipo": TIPOS.get(v["tipo"], v["tipo"] or "No reconocido"),
        "Materia": v["asignatura"] or "No reconocida",
        "Instrumento": v["instrumento"] or "–",
        "Exportado": v["fecha_exportacion"].strftime("%d/%m/%Y %H:%M") if v["fecha_exportacion"] else "–",
        "Encabezado en la fila": v["fila_encabezado"] or "–",
    }
    st.dataframe(pd.Series(datos, name="Qué se reconoció").astype(str), width="content")

    if v["errores"]:
        st.error("El archivo no se puede cargar:", icon=":material/error:")
        for e in v["errores"]:
            st.markdown(f"- ❌ {e}")
    for a in v["avisos"]:
        st.warning(a, icon=":material/info:")

    # -----------------------------------------------------------------------
    # Paso 2: confirmar
    # -----------------------------------------------------------------------
    if v["ok"]:
        st.subheader("2. Confirmar")
        st.markdown("Se va a copiar a `data/raw/` y se recalculan todos los dashboards. Al terminar se "
                    "muestran los indicadores de antes y después, para verificar que los datos entraron.")
        if st.button("Cargar y recalcular", type="primary", icon=":material/sync:"):
            antes = foto()
            with st.spinner("Cargando y recalculando (tarda unos segundos)…"):
                r = agregar_archivo(contenido, archivo.name)
            comp.limpiar_cache()
            st.session_state["resultado_carga"] = {
                "ok": r.ok, "mensaje": r.mensaje, "errores": r.errores, "avisos": r.avisos,
                "gold": r.resumen["gold"] if r.resumen else None,
                "antes": antes if r.ok else None, "despues": foto() if r.ok else None,
                "asignatura": v["asignatura"]}
            st.session_state["uploader"] += 1  # vacía el uploader
            st.rerun()

st.info("En la versión publicada (Streamlit Cloud) lo que se carga se pierde cuando la app se reinicia (D50). "
        "Para que quede, hay que subir el Excel a `data/raw/` en GitHub.", icon=":material/cloud_off:")

# ---------------------------------------------------------------------------
# Archivos que ya están
# ---------------------------------------------------------------------------
st.subheader("Archivos cargados")
tabla, avisos = archivos_cargados(estado_raw())
st.dataframe(tabla, width="stretch", hide_index=True,
             column_config={"Exportado": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
for a in avisos:
    st.caption(f"ℹ️ {a}")

with st.expander("Reprocesar todo"):
    st.markdown("Vuelve a correr el pipeline completo con lo que hay en `data/raw/` "
                "(por ejemplo, si se copió un Excel a mano o se editó `categorias_acciones.csv`).")
    if st.button("Reprocesar", icon=":material/refresh:"):
        with st.spinner("Procesando…"):
            try:
                res = procesar(verbose=False)
            except Exception as e:  # noqa: BLE001
                st.error(f"El pipeline falló: {type(e).__name__}: {e}")
            else:
                comp.limpiar_cache()
                st.success(f"Listo en {res['segundos']:.0f} s.")
                for a in res["avisos_modelo"]:
                    st.warning(a)
