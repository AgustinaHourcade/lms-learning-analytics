"""
PASO 2 - Ingesta: RAW (Excel) -> BRONZE (Parquet)

Idea de la capa bronze: tener los mismos datos que los Excel, pero
  * sin las filas basura de encabezado,
  * con nombres de columna planos,
  * con dos columnas de linaje: `asignatura` y `archivo_origen`,
  * TODO como texto (dtype=str). Los tipos se corrigen en silver.
    Así, si algo se parsea mal, siempre podemos volver a bronze sin
    releer los Excel (que es lo lento).

Preparada para archivos nuevos (Etapa 1):
  * Cada Excel se reconoce por su CONTENIDO y no por el nombre: un archivo de
    calificaciones tiene "Calificación: ..." arriba aunque se llame distinto.
  * La materia sale del contenido ("Aula: TUCD-MD-Álgebra 2025", "(2319) Álgebra").
  * La fila de encabezado se busca (la primera que tiene "Usuario", "Fecha", etc.)
    en vez de usar un número de fila fijo.
  * Se recorre todo `data/raw/` (subcarpetas incluidas), así que alcanza con
    copiar el Excel nuevo ahí y volver a correr el pipeline.
  * Si dos archivos son "foto" de lo mismo (dos reportes de participación de
    una materia, o dos exportaciones del mismo instrumento), vale la
    exportación más reciente y la otra se informa como reemplazada.

Ejecutar desde la raíz del proyecto:
    python -m src.ingesta
"""
from __future__ import annotations

import html
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd

from src.config import ASIGNATURAS, BRONZE, FILAS_A_INSPECCIONAR, RAW, TIPOS_ARCHIVO


class ArchivoInvalido(Exception):
    """Un Excel de data/raw/ no se puede usar. El mensaje explica por qué."""


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------
def nfc(texto: str) -> str:
    """Normaliza tildes a forma NFC.
    Importante: en Mac los nombres de carpeta con tilde ('Álgebra') suelen
    venir en forma NFD (A + tilde separados) y entonces 'Álgebra' != 'Álgebra'.
    """
    return unicodedata.normalize("NFC", texto)


def clave(texto) -> str:
    """Texto para comparar: sin tildes, sin espacios de más y en minúsculas.
    'Álgebra' -> 'algebra'. Así 'Calificacion:' o 'ALGEBRA' también matchean."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto))
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return " ".join(sin_tildes.split()).casefold()


# ---------------------------------------------------------------------------
# Reconocimiento del archivo por su contenido
# ---------------------------------------------------------------------------
@dataclass
class InfoArchivo:
    """Lo que se sabe de un Excel después de mirar sus primeras filas."""
    path: Path
    tipo: str | None = None              # calificaciones / trazabilidad / participacion / matriculados
    asignatura: str | None = None
    fila_encabezado: int | None = None   # número de fila de Excel (empieza en 1)
    fecha_exportacion: datetime | None = None
    instrumento: str | None = None       # solo calificaciones
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def nombre(self) -> str:
        return self.path.name

    @property
    def ok(self) -> bool:
        return not self.errores

    def orden(self) -> tuple:
        """Para elegir la exportación más reciente (desempata el nombre, que trae la hora)."""
        return (self.fecha_exportacion or datetime.min, self.nombre)


def _celdas_texto(fila) -> list[str]:
    return [nfc(str(v)).strip() for v in fila if v is not None and str(v).strip()]


def _asignatura_en(texto: str) -> str | None:
    """Busca el nombre o el código de una materia dentro de un texto."""
    t = clave(texto)
    for nombre, datos in ASIGNATURAS.items():
        if clave(nombre) in t or f"({datos['codigo']})" in t:
            return nombre
    return None


def _parsear_fecha(valor) -> datetime | None:
    if isinstance(valor, datetime):
        return valor
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor).strip(), formato)
        except ValueError:
            pass
    return None


def inspeccionar(path: Path, asignatura_carpeta: str | None = None) -> InfoArchivo:
    """Mira las primeras filas del Excel y deduce tipo, materia, fila de encabezado,
    fecha de exportación e instrumento. No lanza excepciones: los problemas
    quedan en `info.errores`."""
    info = InfoArchivo(path=Path(path))
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        filas = [tuple(f) for f in wb.active.iter_rows(max_row=FILAS_A_INSPECCIONAR, values_only=True)]
        wb.close()
    except Exception as e:  # archivo corrupto, no es un .xlsx, etc.
        info.errores.append(f"No se pudo abrir como Excel ({type(e).__name__}: {e}).")
        return info

    textos = [_celdas_texto(f) for f in filas]
    # Solo la primera celda de cada fila: la firma está en la columna A, y así un
    # texto parecido dentro de los datos (por ej. en 'Descripción') no confunde.
    planos = [clave(fila[0]) for fila in textos if fila]

    # 1) Tipo: primero por la firma (título o "Calificación:"), si no por el encabezado
    def fila_con(columnas: list[str]) -> int | None:
        buscadas = {clave(c) for c in columnas}
        for i, fila in enumerate(textos, start=1):
            if buscadas <= {clave(t) for t in fila}:
                return i
        return None

    for tipo, regla in TIPOS_ARCHIVO.items():
        firma = regla["firma"]
        if firma and any(clave(firma) in t for t in planos):
            info.tipo = tipo
            break
    if info.tipo is None:
        for tipo, regla in TIPOS_ARCHIVO.items():
            if fila_con(regla["encabezado"]):
                info.tipo = tipo
                break
    if info.tipo is None:
        info.errores.append(
            "No se reconoce el tipo de archivo: no es un reporte de calificaciones, trazabilidad, "
            "participación ni matriculados del LMS.")
        return info

    # 2) Fila de encabezado: la primera que tiene todas las columnas clave
    info.fila_encabezado = fila_con(TIPOS_ARCHIVO[info.tipo]["encabezado"])
    if info.fila_encabezado is None:
        info.errores.append(
            f"Parece un archivo de {info.tipo}, pero no encontré la fila de encabezado con "
            f"{TIPOS_ARCHIVO[info.tipo]['encabezado']} en las primeras {FILAS_A_INSPECCIONAR} filas.")
        return info

    # 3) Metadatos de las filas de arriba del encabezado
    for fila in textos[: info.fila_encabezado - 1]:
        if not fila:
            continue
        etiqueta, _, resto = fila[0].partition(":")
        etiqueta_c = clave(etiqueta)
        if etiqueta_c == "fecha de exportacion":
            info.fecha_exportacion = _parsear_fecha(resto.strip() or (fila[1] if len(fila) > 1 else ""))
        elif etiqueta_c == "calificacion" and info.tipo == "calificaciones":
            # '&#129504; PARCIAL 1' -> '🧠 PARCIAL 1'
            info.instrumento = html.unescape(resto.strip()) or None
        if info.asignatura is None:
            info.asignatura = _asignatura_en(" ".join(fila))

    if info.tipo == "calificaciones" and not info.instrumento:
        info.errores.append("Archivo de calificaciones sin nombre de instrumento ('Calificación: ...').")

    # 4) Materia: el contenido manda; la carpeta solo sirve de respaldo y de control
    if info.asignatura is None:
        if asignatura_carpeta:
            info.asignatura = asignatura_carpeta
            info.avisos.append(f"La materia no figura en el archivo; se toma la de la carpeta ({asignatura_carpeta}).")
        else:
            info.errores.append("No se pudo reconocer la materia (Álgebra, AED o PyE) en el encabezado del archivo.")
    elif asignatura_carpeta and asignatura_carpeta != info.asignatura:
        info.errores.append(
            f"El archivo dice ser de {info.asignatura}, pero está en la carpeta de {asignatura_carpeta}.")
    return info


# ---------------------------------------------------------------------------
# Lectores (uno por tipo de archivo). Reciben el InfoArchivo ya inspeccionado.
# ---------------------------------------------------------------------------
def _linaje(df: pd.DataFrame, info: InfoArchivo) -> pd.DataFrame:
    df["asignatura"] = info.asignatura
    df["archivo_origen"] = info.nombre
    return df


def leer_trazabilidad(info: InfoArchivo) -> pd.DataFrame:
    """Log de eventos: una fila por evento debajo del encabezado."""
    df = pd.read_excel(info.path, header=info.fila_encabezado - 1, dtype=str).dropna(how="all")
    return _linaje(df, info).reset_index(drop=True)


def leer_participacion(info: InfoArchivo) -> pd.DataFrame:
    """Reporte con encabezado en DOS niveles (la fila encontrada y la siguiente).
    Ej: 'Foros' arriba y 'Cantidad' / 'Cargados' abajo -> 'Foros - Cantidad'.
    """
    crudo = pd.read_excel(info.path, header=None, dtype=str)
    i = info.fila_encabezado - 1
    nivel1 = crudo.iloc[i].ffill()       # propaga 'Foros' hacia la derecha
    nivel2 = crudo.iloc[i + 1]
    # si la columna NO tiene sub-encabezado, se usa solo el nivel 1
    columnas = [f"{a} - {b}" if pd.notna(b) else a for a, b in zip(nivel1, nivel2)]
    df = crudo.iloc[i + 2:].copy()
    df.columns = columnas
    df = df.dropna(how="all")
    return _linaje(df, info).reset_index(drop=True)


def leer_calificaciones(info: InfoArchivo) -> pd.DataFrame:
    """Un archivo por instrumento. Se usa openpyxl (y no pandas) porque
    'Los coloreados indican usuarios desactivados' -> hay que leer el color
    de relleno de la celda, cosa que pandas ignora.
    """
    wb = openpyxl.load_workbook(info.path, read_only=False)
    ws = wb.active

    meta = {}
    for fila in range(1, info.fila_encabezado):
        valor = ws.cell(fila, 1).value
        if valor and ":" in str(valor):
            etiqueta, _, contenido = str(valor).partition(":")
            meta[clave(etiqueta)] = contenido.strip()

    encabezado = [c.value for c in ws[info.fila_encabezado]]
    filas = []
    for row in ws.iter_rows(min_row=info.fila_encabezado + 1, max_col=len(encabezado)):
        valores = [c.value for c in row]
        if all(v is None for v in valores):
            continue
        celda = row[0]
        color = celda.fill.fgColor.rgb if celda.fill and celda.fill.fill_type else None
        # Blanco ('FFFFFFFF') o sin relleno = usuario activo
        desactivado = color not in (None, "FFFFFFFF", "00000000")
        filas.append(valores + [str(color), desactivado])
    wb.close()

    df = pd.DataFrame(filas, columns=encabezado + ["color_celda", "desactivado"])
    df = df.astype({c: "string" for c in encabezado})
    df["instrumento_raw"] = meta.get("calificacion")
    df["instrumento"] = info.instrumento
    df["aula"] = meta.get("nombre del aula")
    df["fecha_exportacion"] = meta.get("fecha de exportacion")
    return _linaje(df, info)


def leer_matriculados(info: InfoArchivo) -> pd.DataFrame:
    """Título '(2319) Álgebra' arriba y encabezado en la fila encontrada."""
    df = pd.read_excel(info.path, header=info.fila_encabezado - 1, dtype=str).dropna(how="all")
    df = _linaje(df, info)
    df.insert(df.columns.get_loc("archivo_origen"), "codigo_asignatura", ASIGNATURAS[info.asignatura]["codigo"])
    return df.reset_index(drop=True)


LECTORES = {
    "trazabilidad": leer_trazabilidad,
    "participacion": leer_participacion,
    "calificaciones": leer_calificaciones,
    "matriculados": leer_matriculados,
}


def leer(info: InfoArchivo) -> pd.DataFrame:
    return LECTORES[info.tipo](info)


# ---------------------------------------------------------------------------
# Recorrido de data/raw/
# ---------------------------------------------------------------------------
def asignatura_de_carpeta(path: Path, raw: Path) -> str | None:
    """Si el archivo está dentro de la carpeta de una materia, devuelve esa materia."""
    for parte in path.relative_to(raw).parts[:-1]:
        if nfc(parte) in ASIGNATURAS:
            return nfc(parte)
    return None


def descubrir(raw: Path = RAW) -> list[InfoArchivo]:
    """Inspecciona todos los .xlsx de raw (con subcarpetas). Ignora los
    temporales de Excel ('~$...')."""
    return [inspeccionar(p, asignatura_de_carpeta(p, raw))
            for p in sorted(raw.rglob("*.xlsx")) if not p.name.startswith("~$")]


def clave_foto(info: InfoArchivo) -> tuple | None:
    """Archivos que son una 'foto' completa de algo: si hay dos, vale el más reciente.
    Trazabilidad y matriculados se acumulan (los duplicados se sacan en limpieza)."""
    if info.tipo == "participacion":
        return (info.tipo, info.asignatura)
    if info.tipo == "calificaciones":
        return (info.tipo, info.asignatura, clave(info.instrumento))
    return None


def seleccionar(infos: list[InfoArchivo]) -> tuple[list[InfoArchivo], list[str]]:
    """Se queda con los archivos a usar y devuelve los avisos de los reemplazados."""
    elegidos: dict[tuple, InfoArchivo] = {}
    usar, avisos = [], []
    for info in infos:
        k = clave_foto(info)
        if k is None:
            usar.append(info)
        elif k not in elegidos or info.orden() > elegidos[k].orden():
            elegidos[k] = info
    for info in infos:
        k = clave_foto(info)
        if k is not None and elegidos[k] is not info:
            avisos.append(f"{info.path.name} queda reemplazado por {elegidos[k].path.name} "
                          f"(exportación más reciente de {' / '.join(map(str, k[1:]))}).")
    usar = sorted(usar + list(elegidos.values()), key=lambda i: (i.tipo, i.asignatura, i.nombre))
    return usar, avisos


def ingestar(raw: Path = RAW, destino: Path = BRONZE, verbose: bool = True) -> dict:
    """Lee todos los Excel de `raw`, escribe bronze y devuelve un resumen:
    {"tablas": {nombre: filas}, "archivos": [...], "avisos": [...]}.
    Si algún archivo no se puede usar, lanza ArchivoInvalido con todos los motivos."""
    log = print if verbose else (lambda *a, **k: None)
    destino.mkdir(parents=True, exist_ok=True)

    infos = descubrir(raw)
    malos = [i for i in infos if not i.ok]
    if malos:
        raise ArchivoInvalido("Hay archivos en data/raw/ que no se pueden usar:\n" + "\n".join(
            f"  - {i.path.relative_to(raw)}: {' '.join(i.errores)}" for i in malos))

    usar, avisos = seleccionar(infos)
    avisos += [f"{i.nombre}: {a}" for i in usar for a in i.avisos]

    partes: dict[str, list[pd.DataFrame]] = {t: [] for t in LECTORES}
    for info in usar:
        partes[info.tipo].append(leer(info))
        log(f"  ✓ {info.tipo:<15} {info.asignatura:<34} {info.nombre}")

    faltan = [t for t, dfs in partes.items() if not dfs]
    if faltan:
        raise ArchivoInvalido(f"No hay ningún archivo de: {', '.join(faltan)}.")

    tablas = {}
    for nombre, dfs in partes.items():
        df = pd.concat(dfs, ignore_index=True)
        df.to_parquet(destino / f"{nombre}.parquet", index=False)
        tablas[nombre] = len(df)
        log(f"  {nombre:<15} {len(df):>8,} filas  {df.shape[1]:>3} cols  -> {destino.name}/{nombre}.parquet")
    for a in avisos:
        log(f"  [!] {a}")
    return {"tablas": tablas, "archivos": [i.nombre for i in usar], "avisos": avisos}


def main() -> None:
    t0 = time.time()
    ingestar()
    print(f"\nListo en {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
