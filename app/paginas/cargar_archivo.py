"""
Cargar archivo (D28, D40, D50-D52): suma uno o varios Excel nuevos del LMS y recalcula todo.

Tres pasos: 1) se suben los archivos; 2) se validan juntos (validar_lote) y se
muestra qué se reconoció y qué va a cambiar; 3) el usuario confirma y se llama a
agregar_archivos(), que copia a data/raw/ los válidos y corre el pipeline una vez.
Si el pipeline falla, data/raw/ y los datos quedan como estaban.
"""
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import componentes as comp
from src.config import RAW
from src.ingesta import descubrir, seleccionar
from src.pipeline import agregar_archivos, procesar
from src.validacion import validar_lote

TIPOS = {"calificaciones": "Calificaciones", "trazabilidad": "Trazabilidad",
         "participacion": "Reporte de participación", "matriculados": "Matriculados"}


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
def estado_raw() -> tuple:
    return tuple(sorted((str(p), p.stat().st_mtime_ns) for p in RAW.rglob("*.xlsx")))


@st.cache_data(show_spinner="Validando los archivos…", max_entries=20)
def validar(archivos: tuple, estado_raw: tuple) -> list[dict]:  # estado_raw: revalida si cambió data/raw
    """archivos = ((nombre, contenido), ...). Se validan juntos (D52)."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, (nombre, contenido) in enumerate(archivos):
            carpeta = Path(tmp) / str(i)
            carpeta.mkdir()
            (carpeta / nombre).write_bytes(contenido)
            paths.append(carpeta / nombre)
        infos = validar_lote(paths, RAW)
    return [{"nombre": i.nombre, "ok": i.ok, "tipo": i.tipo, "asignatura": i.asignatura,
             "instrumento": i.instrumento, "fecha_exportacion": i.fecha_exportacion,
             "fila_encabezado": i.fila_encabezado, "filas": i.filas, "errores": i.errores, "avisos": i.avisos}
            for i in infos]


@st.cache_data(show_spinner="Leyendo los archivos cargados…")
def archivos_cargados(estado: tuple) -> tuple[pd.DataFrame, list[str]]:
    infos = descubrir(RAW)
    usados, avisos = seleccionar([i for i in infos if i.ok])
    usados = {i.path for i in usados}
    filas = [{"materia": i.asignatura, "contenido": i.instrumento or TIPOS.get(i.tipo, i.tipo or "?"),
              "tipo": i.tipo or "", "archivo": i.nombre, "exportado": i.fecha_exportacion,
              "en_uso": i.path in usados}
             for i in infos]
    df = pd.DataFrame(filas).sort_values(["exportado", "archivo"], ascending=[False, True], na_position="last")
    return df.reset_index(drop=True), avisos  # lo más reciente primero


def foto() -> pd.DataFrame:
    """Lo que hay cargado ahora, por materia (D51). Ignora la materia de la barra."""
    return comp.metrica("foto_datos", asignatura=None)


def describir(v: dict) -> str:
    detalle = f"«{comp.esc(v['instrumento'])}»" if v.get("instrumento") else TIPOS.get(v.get("tipo"), "archivo")
    return f"{detalle} de {comp.esc(v['asignatura'])}" if v.get("asignatura") else detalle


def tamano(n: int) -> str:
    return f"{comp.num(n / 1024, 1)} KB" if n < 1024 ** 2 else f"{comp.num(n / 1024 ** 2, 1)} MB"


def hace(t: datetime) -> str:
    minutos = int((datetime.now() - t).total_seconds() // 60)
    return "recién" if minutos < 1 else f"hace {minutos} minuto{'s' if minutos > 1 else ''}"


# ---------------------------------------------------------------------------
# Antes y después (D51)
# ---------------------------------------------------------------------------
# Tarjetas por materia: (clave, decimales, sentido). sentido = +1 si subir es bueno,
# -1 si subir es malo, 0 si es neutro. La tarjeta se pinta de rojo si empeoró.
TARJETAS_ANTES_DESPUES = [("notas", 0, +1), ("instrumentos", 0, 0), ("nota_promedio", 2, +1),
                          ("promociona", 0, +1), ("libre", 0, -1)]


def mostrar_antes_despues(antes: pd.DataFrame, despues: pd.DataFrame, asignaturas: list[str]) -> None:
    """Compara los indicadores antes y después de la carga, para verificar que
    los datos nuevos entraron (D51)."""
    tabla = comp.comparar_fotos(antes, despues)
    cambio = tabla["diferencia"].fillna(0).ne(0)
    materias = [a for a in asignaturas if a in set(tabla["asignatura"])] or \
        list(tabla.loc[cambio, "asignatura"].unique()) or list(tabla["asignatura"].unique())

    comp.html(comp.seccion(
        "Antes y después", derecha=" · ".join(comp.SIGLAS.get(m, m) for m in materias),
        subtitulo="Calculado con todos los datos cargados, sin fecha de corte, así un instrumento nuevo se ve "
                  "aunque sea posterior a la fecha elegida. La nota promedio incluye los 0 de quienes no rindieron "
                  "y está en la escala de la materia (Álgebra sobre 120, el resto sobre 100)."))
    if not cambio.any():
        comp.html(comp.aviso("No cambió ningún indicador. Puede pasar si el archivo ya estaba cargado o si "
                             "reemplazó a una exportación con los mismos datos.", "atencion"))

    for materia in materias:
        filas = tabla[tabla["asignatura"] == materia].set_index("clave")
        if len(materias) > 1:
            comp.html(f'<div style="margin:6px 0 8px">{comp.chip_materia(materia, largo=True)}</div>')
        cols = st.columns(len(TARJETAS_ANTES_DESPUES))
        for col, (clave, dec, sentido) in zip(cols, TARJETAS_ANTES_DESPUES):
            f = filas.loc[clave]
            dif = 0 if pd.isna(f["diferencia"]) else f["diferencia"]
            # Rojo si empeoró, verde si mejoró, blanco si no cambió.
            efecto = (sentido or 1) * dif
            estado = "peor" if efecto < 0 else "mejor" if efecto > 0 else "igual"
            with col.container(key=f"ad-{estado}-{comp.SIGLAS.get(materia, materia)}-{clave}"):
                # El signo tiene que ser un "-" común: Streamlit lo usa para elegir la flecha y el color.
                st.metric(f["indicador"], comp.num(f["despues"], dec), border=True,
                          delta=f"{'+' if dif > 0 else ''}{comp.num(dif, dec)} · antes {comp.num(f['antes'], dec)}"
                          if dif else "sin cambios",
                          delta_color="off" if not dif else "inverse" if sentido < 0 else "normal",
                          delta_arrow="auto" if dif else "off")
        bajo_promedio = filas.loc["nota_promedio", "diferencia"]
        if filas.loc["instrumentos", "diferencia"] > 0 and bajo_promedio < 0:
            comp.html(comp.aviso(
                f"La caída de {comp.num(-bajo_promedio, 2)} puntos no es que les fue peor: son los "
                "<strong>0 de quienes no rindieron</strong> el instrumento nuevo. Cada carga de una evaluación "
                "baja el promedio hasta que todos la rinden.", "info"))

    with st.expander("Ver las tres materias e indicadores"):
        t = tabla.drop(columns="clave").rename(columns={
            "asignatura": "Materia", "indicador": "Indicador", "antes": "Antes", "despues": "Después",
            "diferencia": "Diferencia"})
        st.dataframe(t.style.format({"Antes": "{:,.2f}", "Después": "{:,.2f}", "Diferencia": "{:+,.2f}"},
                                    decimal=",", thousands=".")
                     .map(lambda v: "color: #116040" if v > 0 else "color: #93241C" if v < 0 else "",
                          subset=["Diferencia"]),
                     width="stretch", hide_index=True)


def mostrar_resultado(r: dict) -> None:
    with st.container(key="tarjeta-resultado"):
        cargados = r.get("cargados", [])
        if r["ok"]:
            if len(cargados) == 1:
                texto = f"{describir(cargados[0])}."
            elif cargados:
                texto = f"{len(cargados)} archivos: " + "; ".join(describir(c) for c in cargados) + "."
            else:
                texto = comp.esc(r["mensaje"])
            comp.html(comp.aviso(f"{texto} Se recalculó todo {hace(r['hora'])}.", "exito", "Última carga:"))
        else:
            comp.html(comp.aviso(comp.esc(r["mensaje"]), "error", items=[comp.esc(e) for e in r.get("errores", [])]))
        for rech in r.get("rechazados", []):
            comp.html(comp.aviso("", "error", f"No se cargó «{comp.esc(rech['nombre'])}».",
                                 items=[comp.esc(e) for e in rech["errores"]]))
        if r.get("antes") is not None:
            mostrar_antes_despues(r["antes"], r["despues"], r.get("asignaturas", []))
        if st.button("Ocultar", key="ocultar_resultado", type="tertiary", icon=":material/close:"):
            st.session_state.pop("resultado_carga", None)
            st.rerun()


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------
comp.titulo("Cargar archivo",
            "Subí uno o varios Excel exportados del LMS (por ejemplo, las notas de un parcial nuevo). Se reconocen "
            "por su contenido, así que el nombre no importa. Se validan antes de usarlos: si algo no cierra, te "
            "decimos qué y no se toca nada.")
lugar_pasos = st.empty()
st.session_state.setdefault("uploader", 0)

col_archivos, col_reconocido = st.columns([1, 1.15], gap="small")
with col_archivos.container(key="tarjeta-archivos"):
    comp.html(comp.seccion("Archivos", "Podés subir varios a la vez: se validan juntos y se recalcula una sola vez."))
    subidos = st.file_uploader("Excel del LMS (.xlsx)", type=["xlsx"], accept_multiple_files=True,
                               key=f"uploader_{st.session_state['uploader']}", label_visibility="collapsed")

validaciones = validar(tuple((a.name, a.getvalue()) for a in subidos), estado_raw()) if subidos else []
validos = [v for v in validaciones if v["ok"]]

with col_reconocido.container(key="tarjeta-reconocido"):
    if not subidos:
        comp.html(comp.seccion("Qué se reconoció", "Cuando subas un archivo vas a ver acá el tipo, la materia y el "
                                                   "instrumento que se reconocieron, antes de confirmar."))
    else:
        todos_ok = len(validos) == len(validaciones)
        comp.html(comp.seccion("Qué se reconoció", "Revisá que coincida con lo que subiste antes de confirmar.",
                               icono="ok" if todos_ok else "atencion",
                               color_icono="#116040" if todos_ok else "#A06A00"))
        for archivo, v in zip(subidos, validaciones):
            color = "#116040" if v["ok"] else "#93241C"
            exportado = v["fecha_exportacion"].strftime("%d/%m/%Y %H:%M") if v["fecha_exportacion"] else "–"
            datos = [("Tipo", TIPOS.get(v["tipo"], v["tipo"] or "No reconocido")),
                     ("Materia", comp.esc(v["asignatura"] or "No reconocida"))]
            if v["tipo"] == "calificaciones":
                datos.append(("Instrumento", comp.esc(v["instrumento"] or "–")))
            datos += [("Exportado", exportado), ("Encabezado en la fila", v["fila_encabezado"] or "–")]
            if v["filas"] is not None:
                datos.append(("Filas con nota" if v["tipo"] == "calificaciones" else "Filas", comp.num(v["filas"])))
            comp.html(
                f'<div style="display:flex;align-items:center;gap:10px;margin:14px 0 6px">'
                f'<span style="color:{color};display:inline-flex">{comp.ICONOS_SVG["ok" if v["ok"] else "error"]}</span>'
                f'<div style="min-width:0"><p class="tfi-archivo">{comp.esc(v["nombre"])}</p>'
                f'<p class="num" style="margin:0;font-size:11px;color:#6B6861">{tamano(archivo.size)}</p></div></div>'
                + comp.filas_dato(datos))
            if v["errores"]:
                comp.html(comp.aviso("", "error", "No se puede cargar:", items=[comp.esc(e) for e in v["errores"]]))

# Pasos (arriba de todo, se completan ahora que se sabe cómo salió la validación)
if not subidos:
    estados = ["actual", "pendiente", "pendiente"]
elif not validos:
    estados = ["hecho", "error", "pendiente"]
else:
    estados = ["hecho", "hecho", "actual"]
lugar_pasos.markdown(comp.pasos(list(zip(["1 · Subir", "2 · Validar", "3 · Confirmar y recalcular"], estados))),
                     unsafe_allow_html=True)

# Qué va a cambiar + confirmar
if subidos:
    with st.container(key="tarjeta-confirmar"):
        comp.html(comp.seccion("Qué va a cambiar si confirmás"))
        for v in validos:
            for a in v["avisos"]:
                tono = "atencion" if a.startswith("Instrumento nuevo") else "info"
                extra = (" A quienes no lo rindieron les entra un 0 y las condiciones se recalculan."
                         if tono == "atencion" else "")
                comp.html(comp.aviso(comp.esc(a) + extra, tono, f"{comp.esc(v['nombre'])}:"))
        rechazados = len(validaciones) - len(validos)
        if rechazados:
            comp.html(comp.aviso(
                f"{'El archivo marcado' if rechazados == 1 else f'Los {rechazados} archivos marcados'} en rojo no "
                f"se {'va' if rechazados == 1 else 'van'} a cargar." + (" El resto sí." if validos else ""), "error"))

        etiqueta = ("Cargar y recalcular" if len(validos) <= 1 else f"Cargar {len(validos)} archivos y recalcular")
        b1, b2, b3 = st.columns([0.32, 0.16, 0.52], vertical_alignment="center")
        confirmar = b1.button(etiqueta, type="primary", icon=":material/sync:", disabled=not validos, width="stretch")
        if b2.button("Cancelar", width="stretch"):
            st.session_state["uploader"] += 1  # vacía el uploader
            st.rerun()
        with b3:
            comp.html('<p class="mono" style="margin:0;font-size:11px;color:#6B6861">se copia a data/raw/</p>')

        if confirmar:
            antes = foto()
            with st.spinner("Cargando y recalculando (tarda unos segundos)…"):
                r = agregar_archivos([(a.getvalue(), a.name) for a in subidos])
            comp.limpiar_cache()
            st.session_state["resultado_carga"] = {
                "ok": r.ok, "mensaje": r.mensaje, "errores": r.errores, "hora": datetime.now(),
                "cargados": [{"nombre": i.nombre, "tipo": i.tipo, "asignatura": i.asignatura,
                              "instrumento": i.instrumento} for i in r.cargados],
                "rechazados": [{"nombre": i.nombre, "errores": i.errores} for i in r.rechazados],
                "antes": antes if r.ok else None, "despues": foto() if r.ok else None,
                "asignaturas": list(dict.fromkeys(i.asignatura for i in r.cargados))}
            st.session_state["uploader"] += 1
            st.rerun()

# Resultado de la última carga (sobrevive al rerun que limpia el uploader).
if resultado := st.session_state.get("resultado_carga"):
    resultado.setdefault("hora", datetime.now())
    mostrar_resultado(resultado)

# Archivos que ya están
tabla, avisos = archivos_cargados(estado_raw())
with st.container(key="tarjeta-cargados"):
    c1, c2 = st.columns([0.75, 0.25], vertical_alignment="center")
    n_usados = int(tabla["en_uso"].sum())
    resumen = (f"{len(tabla)} archivos · {tabla['materia'].nunique()} materias · "
               + ("todos en uso" if n_usados == len(tabla) else f"{n_usados} en uso, {len(tabla) - n_usados} reemplazados"))
    with c1:
        comp.html(comp.seccion("Archivos cargados", resumen))
    reprocesar = c2.button("Reprocesar todo", icon=":material/refresh:", width="stretch",
                           help="Vuelve a correr el pipeline con lo que hay en data/raw/ (por ejemplo, si se copió "
                                "un Excel a mano o se editó categorias_acciones.csv).")
    estado = {True: '<span style="display:inline-flex;align-items:center;gap:6px;font-weight:500;color:#116040">'
                    '<svg viewBox="0 0 16 16" width="10" height="10" aria-hidden="true"><circle cx="8" cy="8" r="6.6" '
                    'fill="currentColor"/></svg>En uso</span>',
              False: '<span style="display:inline-flex;align-items:center;gap:6px;font-weight:500;color:#6B6861">'
                     '<svg viewBox="0 0 16 16" width="10" height="10" aria-hidden="true"><circle cx="8" cy="8" r="5.8" '
                     'fill="none" stroke="currentColor" stroke-width="1.6"/></svg>Reemplazado</span>'}
    filas = [[comp.chip_materia(f.materia),
              f"<strong style='font-weight:600'>{comp.esc(f.contenido)}</strong>" if i == 0 else comp.esc(f.contenido),
              f'<span class="mono" style="color:#57544C">{comp.esc(f.archivo)}</span>',
              f'<span class="num" style="color:#57544C">{f.exportado:%d/%m %H:%M}</span>' if pd.notna(f.exportado) else "–",
              estado[bool(f.en_uso)]]
             for i, f in enumerate(tabla.itertuples())]
    comp.html(comp.tabla_html(["Materia", "Contenido", "Archivo", "Exportado", "Estado"], filas, alto=320))
    if reprocesar:
        with st.spinner("Procesando…"):
            try:
                res = procesar(verbose=False)
            except Exception as e:  # noqa: BLE001
                st.error(f"El pipeline falló: {type(e).__name__}: {e}")
            else:
                comp.limpiar_cache()
                st.toast(f"Listo: se reprocesó todo en {res['segundos']:.0f} s.", icon=":material/check_circle:")
                for a in res["avisos_modelo"]:
                    st.warning(a)
for a in avisos:
    st.caption(f"ℹ️ {a}")

comp.html(comp.aviso(
    "Para que quede, hay que subir el Excel a <span class='mono' style='font-size:11px'>data/raw/</span> en "
    "GitHub. Es una limitación del alojamiento, no del pipeline.", "info",
    "En la versión publicada, lo que subas acá se pierde cuando la app se reinicia.", icono="nube"))
