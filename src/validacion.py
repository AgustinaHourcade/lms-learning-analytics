"""
Validación de un Excel nuevo ANTES de sumarlo a data/raw/.

La usa `pipeline.agregar_archivo()` (y la página "Cargar archivo" de la app).
Nunca lanza excepciones: devuelve un InfoArchivo con `errores` (el archivo no
se puede usar) y `avisos` (se puede usar, pero conviene saberlo).

Controles:
  1. Se reconoce el tipo de archivo y la materia por el contenido.
  2. Tiene las columnas esperadas y al menos una fila de datos.
  3. Los IDs respetan el formato ALU_#### / DOC_## / STAFF_##.
  4. Calificaciones: la nota tiene la forma 'obtenido/máximo' y está en rango.
  5. Pasa la misma limpieza que el resto de los datos (red de seguridad).
  6. Comparación con lo que ya hay en data/raw/: archivo repetido, exportación
     más vieja que la que ya está, o qué archivo reemplaza.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from src.config import FORMATO_ID, RAW, TIPOS_ARCHIVO
from src.ingesta import InfoArchivo, clave_foto, descubrir, inspeccionar, leer
from src.limpieza import LIMPIADORES

PATRON_NOTA = r"\s*\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*"
MAX_EJEMPLOS = 5


def huella(path: Path) -> str:
    """Hash del contenido: dos archivos con la misma huella son el mismo archivo."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _ejemplos(valores) -> str:
    valores = list(dict.fromkeys(map(str, valores)))
    extra = f" (y {len(valores) - MAX_EJEMPLOS} más)" if len(valores) > MAX_EJEMPLOS else ""
    return ", ".join(valores[:MAX_EJEMPLOS]) + extra


def _controlar_datos(info: InfoArchivo, df: pd.DataFrame) -> None:
    faltan = [c for c in TIPOS_ARCHIVO[info.tipo]["requeridas"] if c not in df.columns]
    if faltan:
        info.errores.append(f"Faltan columnas: {', '.join(faltan)}.")
        return
    if df.empty:
        info.errores.append("El archivo no tiene filas de datos.")
        return

    col_id = "Identificación" if info.tipo == "matriculados" else "Usuario"
    ids = df[col_id].dropna().astype(str).str.strip().str.upper()
    if info.tipo == "matriculados":  # el pie 'Cantidad de filas:' no tiene ID
        ids = ids[ids != ""]
    malos = ids[~ids.str.fullmatch(FORMATO_ID)]
    if len(malos):
        info.errores.append(f"{len(malos)} IDs con formato inválido (se espera ALU_####, DOC_## o STAFF_##): "
                            f"{_ejemplos(malos)}.")
    if info.tipo != "matriculados" and df[col_id].isna().any():
        info.errores.append(f"{df[col_id].isna().sum()} filas sin `{col_id}`.")

    if info.tipo == "calificaciones":
        nota = df["Nota"].astype(str)
        mal_formato = ~nota.str.fullmatch(PATRON_NOTA)
        if mal_formato.any():
            info.errores.append(f"{mal_formato.sum()} notas sin la forma 'obtenido/máximo' (ej. '24.00/25.00'): "
                                f"{_ejemplos(nota[mal_formato])}.")
            return
        partes = nota.str.split("/", expand=True).astype(float)
        obtenida, maxima = partes[0], partes[1]
        fuera = (obtenida < 0) | (obtenida > maxima) | (maxima <= 0)
        if fuera.any():
            info.errores.append(f"{fuera.sum()} notas fuera de rango (menores a 0 o mayores al máximo): "
                                f"{_ejemplos(df.loc[fuera, 'Usuario'] + ' ' + nota[fuera])}.")
        if maxima.nunique() > 1:
            info.avisos.append(f"El puntaje máximo no es el mismo para todos: {_ejemplos(sorted(maxima.unique()))}.")
        repetidos = ids[ids.duplicated()]
        if len(repetidos):
            info.errores.append(f"Alumnos con más de una nota en el mismo instrumento: {_ejemplos(repetidos)}.")


def _comparar_con_raw(info: InfoArchivo, raw: Path) -> None:
    existentes = [i for i in descubrir(raw) if i.ok]
    mia = huella(info.path)
    for otro in existentes:
        if huella(otro.path) == mia:
            info.errores.append(f"Este archivo ya está cargado ({otro.path.relative_to(raw)}).")
            return

    k = clave_foto(info)
    previos = [o for o in existentes if k is not None and clave_foto(o) == k]
    if previos:
        actual = max(previos, key=InfoArchivo.orden)
        # Mismo criterio que ingesta.seleccionar(): fecha de exportación y, si empata, el nombre
        # (los reportes del LMS traen la hora en el nombre: ..._20251024_115446.xlsx).
        if info.orden() < actual.orden():
            info.errores.append(f"Ya hay una exportación igual o más reciente de lo mismo ({actual.nombre}). "
                                "Este archivo no se usaría.")
        else:
            info.avisos.append(f"Reemplaza a {actual.nombre} (se usa la exportación más reciente).")
    elif info.tipo == "calificaciones":
        info.avisos.append(f"Instrumento nuevo en {info.asignatura}: «{info.instrumento}». Se suma al cálculo de la nota.")
    elif info.tipo in ("trazabilidad", "matriculados"):
        info.avisos.append("Se suma a los datos que ya hay; las filas repetidas se descartan.")


def validar_archivo(path: Path, raw: Path = RAW) -> InfoArchivo:
    """Valida un Excel que todavía NO está en `raw`. Devuelve el InfoArchivo con
    errores y avisos; si `info.ok` es True se puede copiar a raw y procesar."""
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        info = InfoArchivo(path=path)
        info.errores.append("Solo se aceptan archivos .xlsx (los reportes que exporta el LMS).")
        return info

    info = inspeccionar(path)
    if not info.ok:
        return info
    try:
        df = leer(info)
    except Exception as e:
        info.errores.append(f"No se pudo leer el contenido ({type(e).__name__}: {e}).")
        return info

    _controlar_datos(info, df)
    if not info.ok:
        return info

    # Red de seguridad: la misma limpieza que se le aplica a todo el dataset.
    try:
        LIMPIADORES[info.tipo](df.copy())
    except Exception as e:
        info.errores.append(f"Los datos no pasan la limpieza: {e}")
        return info

    _comparar_con_raw(info, raw)
    return info
