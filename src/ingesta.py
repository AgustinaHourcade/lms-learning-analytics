"""
PASO 2 - Ingesta: RAW (Excel) -> BRONZE (Parquet)

Idea de la capa bronze: tener los mismos datos que los Excel, pero
  * sin las filas basura de encabezado,
  * con nombres de columna planos,
  * con dos columnas de linaje: `asignatura` y `archivo_origen`,
  * TODO como texto (dtype=str). Los tipos se corrigen en silver.
    Así, si algo se parsea mal, siempre podemos volver a bronze sin
    releer los Excel (que es lo lento).

Ejecutar desde la raíz del proyecto:
    python -m src.ingesta
"""
from __future__ import annotations

import html
import re
import time
import unicodedata
from pathlib import Path

import openpyxl
import pandas as pd

from src.config import ASIGNATURAS, BRONZE, MATRICULADOS_DIR, RAW


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def nfc(texto: str) -> str:
    """Normaliza tildes a forma NFC.
    Importante: en Mac los nombres de carpeta con tilde ('Álgebra') suelen
    venir en forma NFD (A + tilde separados) y entonces 'Álgebra' != 'Álgebra'.
    """
    return unicodedata.normalize("NFC", texto)


def carpetas_asignatura() -> dict[str, Path]:
    """Devuelve {nombre_asignatura: carpeta} para las 3 materias."""
    encontradas = {}
    for carpeta in RAW.iterdir():
        nombre = nfc(carpeta.name)
        if carpeta.is_dir() and nombre in ASIGNATURAS:
            encontradas[nombre] = carpeta
    faltan = set(ASIGNATURAS) - set(encontradas)
    if faltan:
        raise FileNotFoundError(f"No encontré las carpetas: {faltan}")
    return encontradas


# ---------------------------------------------------------------------------
# Lectores (uno por tipo de archivo)
# ---------------------------------------------------------------------------
def leer_trazabilidad(path: Path, asignatura: str) -> pd.DataFrame:
    """Log de eventos. Encabezado real en la fila 6 de Excel (índice 5)."""
    df = pd.read_excel(path, header=5, dtype=str)
    df["asignatura"] = asignatura
    df["archivo_origen"] = path.name
    return df


def leer_participacion(path: Path, asignatura: str) -> pd.DataFrame:
    """Reporte con encabezado en DOS niveles (filas 6 y 7 de Excel).
    Ej: 'Foros' arriba y 'Cantidad' / 'Cargados' abajo -> 'Foros - Cantidad'.
    """
    crudo = pd.read_excel(path, header=None, dtype=str)
    nivel1 = crudo.iloc[5].ffill()       # propaga 'Foros' hacia la derecha
    nivel2 = crudo.iloc[6]
    # si la columna NO tiene sub-encabezado, se usa solo el nivel 1
    columnas = [f"{a} - {b}" if pd.notna(b) else a for a, b in zip(nivel1, nivel2)]
    df = crudo.iloc[7:].copy()
    df.columns = columnas
    df = df.dropna(how="all")
    df["asignatura"] = asignatura
    df["archivo_origen"] = path.name
    return df.reset_index(drop=True)


def leer_calificaciones(path: Path, asignatura: str) -> pd.DataFrame:
    """Un archivo por instrumento. Se usa openpyxl (y no pandas) porque:
      1) el nombre del instrumento está en la celda A3 ('Calificación: ...')
      2) 'Los coloreados indican usuarios desactivados' -> hay que leer el
         color de relleno de la celda, cosa que pandas ignora.
    """
    wb = openpyxl.load_workbook(path, read_only=False)
    ws = wb.active

    meta = {}
    for fila in range(1, 6):
        valor = ws.cell(fila, 1).value
        if valor and ":" in str(valor):
            clave, _, contenido = str(valor).partition(":")
            meta[clave.strip()] = contenido.strip()

    encabezado = [c.value for c in ws[7]]
    filas = []
    for row in ws.iter_rows(min_row=8):
        valores = [c.value for c in row]
        if all(v is None for v in valores):
            continue
        celda = row[0]
        color = celda.fill.fgColor.rgb if celda.fill and celda.fill.fill_type else None
        # Blanco ('FFFFFFFF') o sin relleno = usuario activo
        desactivado = color not in (None, "FFFFFFFF", "00000000")
        filas.append(valores + [str(color), desactivado])

    df = pd.DataFrame(filas, columns=encabezado + ["color_celda", "desactivado"])
    df = df.astype({c: "string" for c in encabezado})
    df["instrumento_raw"] = meta.get("Calificación")
    # '&#129504; PARCIAL 1' -> '🧠 PARCIAL 1'
    df["instrumento"] = html.unescape(meta.get("Calificación", ""))
    df["aula"] = meta.get("Nombre del aula")
    df["fecha_exportacion"] = meta.get("Fecha de exportación")
    df["asignatura"] = asignatura
    df["archivo_origen"] = path.name
    return df


def leer_matriculados(path: Path) -> pd.DataFrame:
    """Primera fila: '(2319) Álgebra'. Encabezado real en la fila 2."""
    titulo = str(pd.read_excel(path, header=None, nrows=1).iloc[0, 0])
    m = re.match(r"\((\d+)\)\s*(.+)", titulo)
    codigo, asignatura = (m.group(1), nfc(m.group(2).strip())) if m else (None, nfc(path.stem))
    df = pd.read_excel(path, header=1, dtype=str).dropna(how="all")
    df["asignatura"] = asignatura
    df["codigo_asignatura"] = codigo
    df["archivo_origen"] = path.name
    return df


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
def main() -> None:
    BRONZE.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    trazas, partic, notas = [], [], []

    for asignatura, carpeta in carpetas_asignatura().items():
        for archivo in sorted(carpeta.glob("*.xlsx")):
            nombre = archivo.name
            if nombre.startswith("reporte_trazabilidad"):
                trazas.append(leer_trazabilidad(archivo, asignatura))
            elif nombre.startswith("reporte_participacion"):
                partic.append(leer_participacion(archivo, asignatura))
            elif nombre.startswith("calificaciones_alumnos"):
                notas.append(leer_calificaciones(archivo, asignatura))
            else:
                print(f"  [!] Archivo no reconocido, se ignora: {archivo}")
        print(f"  ✓ {asignatura}")

    matric = [leer_matriculados(p) for p in sorted(MATRICULADOS_DIR.glob("*.xlsx"))]

    salidas = {
        "trazabilidad": pd.concat(trazas, ignore_index=True),
        "participacion": pd.concat(partic, ignore_index=True),
        "calificaciones": pd.concat(notas, ignore_index=True),
        "matriculados": pd.concat(matric, ignore_index=True),
    }
    print()
    for nombre, df in salidas.items():
        destino = BRONZE / f"{nombre}.parquet"
        df.to_parquet(destino, index=False)
        print(f"  {nombre:<15} {len(df):>8,} filas  {df.shape[1]:>3} cols  -> {destino.relative_to(BRONZE.parents[1])}")
    print(f"\nListo en {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
