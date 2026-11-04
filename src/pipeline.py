"""
Pipeline completo como funciones que la app puede llamar.

  procesar()          raw -> bronze -> silver (y, cuando estén, gold y KPIs).
  agregar_archivo()   valida un Excel nuevo, lo copia a data/raw/ y reprocesa.
                      Si algo falla, data/raw/ y los datos quedan como estaban.

Desde la terminal (en la raíz del proyecto):
    python -m src.pipeline                       # procesa todo
    python -m src.pipeline agregar <archivo.xlsx>  # suma un Excel nuevo y reprocesa
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.config import BRONZE, MATRICULADOS_DIR, RAW, REPORTS, ROOT, SILVER
from src.ingesta import InfoArchivo, ingestar, nfc
from src.limpieza import limpiar
from src.validacion import validar_archivo


def procesar(raw: Path = RAW, bronze: Path = BRONZE, silver: Path = SILVER,
             reportes: Path = REPORTS, verbose: bool = True) -> dict:
    """Corre el pipeline entero y devuelve un resumen:
    {"ingesta": {...}, "silver": {tabla: filas}, "segundos": float}.
    Lanza ArchivoInvalido (o el error de limpieza) si los datos no se pueden procesar."""
    t0 = time.time()
    log = print if verbose else (lambda *a, **k: None)
    log("Ingesta (raw -> bronze)")
    resumen_ingesta = ingestar(raw, bronze, verbose=verbose)
    log("\nLimpieza (bronze -> silver)")
    filas_silver = limpiar(bronze, silver, reportes, ingesta=resumen_ingesta, verbose=verbose)
    # TODO Etapa 2: modelo (silver -> gold).
    segundos = time.time() - t0
    log(f"\nPipeline listo en {segundos:.1f} s")
    return {"ingesta": resumen_ingesta, "silver": filas_silver, "segundos": segundos}


@dataclass
class ResultadoCarga:
    ok: bool
    mensaje: str
    info: InfoArchivo | None = None
    destino: Path | None = None           # dónde quedó el archivo en raw (si se aceptó)
    resumen: dict | None = None           # lo que devolvió procesar()
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _carpeta_destino(info: InfoArchivo, raw: Path) -> Path:
    """Matriculados/ para matriculados; la carpeta de la materia para el resto.
    Si la carpeta ya existe con otra forma de las tildes (Mac), se reutiliza."""
    nombre = MATRICULADOS_DIR.name if info.tipo == "matriculados" else info.asignatura
    for existente in raw.iterdir() if raw.exists() else []:
        if existente.is_dir() and nfc(existente.name) == nombre:
            return existente
    return raw / nombre


def _nombre_libre(carpeta: Path, nombre: str) -> Path:
    destino = carpeta / nombre
    n = 1
    while destino.exists():
        destino = carpeta / f"{Path(nombre).stem}_{n}{Path(nombre).suffix}"
        n += 1
    return destino


def agregar_archivo(contenido: bytes, nombre: str, raw: Path = RAW, bronze: Path = BRONZE,
                    silver: Path = SILVER, reportes: Path = REPORTS, verbose: bool = False) -> ResultadoCarga:
    """Suma un Excel nuevo al pipeline. Pensada para st.file_uploader:
        r = agregar_archivo(archivo.getvalue(), archivo.name)
    Nunca lanza excepciones: si algo falla devuelve ok=False con los motivos
    y deja data/raw/ (y los datos procesados) como estaban."""
    nombre = Path(nombre).name  # sin rutas, por las dudas
    with tempfile.TemporaryDirectory() as tmp:
        temporal = Path(tmp) / nombre  # mismo nombre: lo usa el desempate entre exportaciones
        temporal.write_bytes(contenido)
        info = validar_archivo(temporal, raw)
        if not info.ok:
            return ResultadoCarga(False, f"El archivo «{nombre}» no se cargó.", info,
                                  errores=info.errores, avisos=info.avisos)
        carpeta = _carpeta_destino(info, raw)
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = _nombre_libre(carpeta, nombre)
        shutil.copyfile(temporal, destino)
    info.path = destino

    try:
        resumen = procesar(raw, bronze, silver, reportes, verbose=verbose)
    except Exception as e:
        # Vuelta atrás: se saca el archivo y se regeneran los datos anteriores.
        destino.unlink(missing_ok=True)
        procesar(raw, bronze, silver, reportes, verbose=False)
        return ResultadoCarga(False, f"El archivo «{nombre}» pasó la validación pero el pipeline falló; "
                              "se descartó y los datos quedaron como estaban.", info,
                              errores=[f"{type(e).__name__}: {e}"], avisos=info.avisos)

    detalle = f"{info.tipo} de {info.asignatura}" + (f" («{info.instrumento}»)" if info.instrumento else "")
    return ResultadoCarga(True, f"Se cargó «{nombre}» ({detalle}) y se recalculó todo.", info,
                          destino=destino, resumen=resumen, avisos=info.avisos)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline del TFI (raw -> bronze -> silver).")
    sub = parser.add_subparsers(dest="comando")
    p_agregar = sub.add_parser("agregar", help="Valida un Excel nuevo, lo copia a data/raw/ y reprocesa.")
    p_agregar.add_argument("archivo", type=Path)
    args = parser.parse_args()

    if args.comando == "agregar":
        r = agregar_archivo(args.archivo.read_bytes(), args.archivo.name, verbose=True)
        print(("\n✓ " if r.ok else "\n✗ ") + r.mensaje)
        for e in r.errores:
            print(f"  error: {e}")
        for a in r.avisos:
            print(f"  aviso: {a}")
        if r.destino:
            print(f"  guardado en: {r.destino.relative_to(ROOT)}")
        sys.exit(0 if r.ok else 1)
    procesar()


if __name__ == "__main__":
    main()
