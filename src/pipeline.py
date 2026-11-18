"""
Pipeline completo como funciones que la app puede llamar.

  procesar()          raw -> bronze -> silver -> gold (modelo estrella).
  agregar_archivos()  valida uno o varios Excel nuevos, copia a data/raw/ los que
                      pasan y reprocesa una sola vez (D52). Si el pipeline falla,
                      data/raw/ y los datos quedan como estaban.
  agregar_archivo()   lo mismo para un solo archivo.

Desde la terminal (en la raíz del proyecto):
    python -m src.pipeline                       # procesa todo
    python -m src.pipeline agregar <a.xlsx> [b.xlsx ...]  # suma Excel nuevos y reprocesa
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.config import BRONZE, GOLD, MATRICULADOS_DIR, RAW, REPORTS, ROOT, SILVER
from src.ingesta import InfoArchivo, ingestar, nfc
from src.limpieza import limpiar
from src.modelo import modelar
from src.validacion import validar_lote


def procesar(raw: Path = RAW, bronze: Path = BRONZE, silver: Path = SILVER,
             reportes: Path = REPORTS, gold: Path = GOLD, verbose: bool = True) -> dict:
    """Corre el pipeline entero y devuelve un resumen:
    {"ingesta": {...}, "silver": {tabla: filas}, "gold": {tabla: filas},
     "avisos_modelo": [...], "segundos": float}.
    Lanza ArchivoInvalido (o el error de limpieza) si los datos no se pueden procesar."""
    t0 = time.time()
    log = print if verbose else (lambda *a, **k: None)
    log("Ingesta (raw -> bronze)")
    resumen_ingesta = ingestar(raw, bronze, verbose=verbose)
    log("\nLimpieza (bronze -> silver)")
    filas_silver = limpiar(bronze, silver, reportes, ingesta=resumen_ingesta, verbose=verbose)
    log("\nModelo (silver -> gold)")
    modelo = modelar(silver, gold, reportes, verbose=verbose)
    segundos = time.time() - t0
    log(f"\nPipeline listo en {segundos:.1f} s")
    return {"ingesta": resumen_ingesta, "silver": filas_silver, "gold": modelo["filas"],
            "avisos_modelo": modelo["avisos"], "segundos": segundos}


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


@dataclass
class ResultadoLote:
    """Resultado de cargar varios archivos juntos (D52)."""
    ok: bool                                   # se cargó al menos uno y el pipeline anduvo
    mensaje: str
    cargados: list[InfoArchivo] = field(default_factory=list)    # info.path = dónde quedó en raw
    rechazados: list[InfoArchivo] = field(default_factory=list)  # con sus errores
    resumen: dict | None = None
    errores: list[str] = field(default_factory=list)             # del pipeline, si falló


def _describir(info: InfoArchivo) -> str:
    return f"{info.tipo} de {info.asignatura}" + (f" («{info.instrumento}»)" if info.instrumento else "")


def agregar_archivos(archivos: list[tuple[bytes, str]], raw: Path = RAW, bronze: Path = BRONZE,
                     silver: Path = SILVER, reportes: Path = REPORTS, gold: Path = GOLD,
                     verbose: bool = False) -> ResultadoLote:
    """Suma uno o varios Excel nuevos y recalcula una sola vez (D52). Pensada para
    st.file_uploader(accept_multiple_files=True):
        r = agregar_archivos([(a.getvalue(), a.name) for a in subidos])
    Los que no pasan la validación se dejan afuera (quedan en `rechazados`) y el
    resto se carga. Nunca lanza excepciones: si el pipeline falla se sacan TODOS
    los archivos del lote y data/raw/ (y los datos procesados) quedan como estaban."""
    with tempfile.TemporaryDirectory() as tmp:
        temporales = []
        for i, (contenido, nombre) in enumerate(archivos):
            nombre = Path(nombre).name  # sin rutas, por las dudas
            carpeta = Path(tmp) / str(i)  # una carpeta por archivo: dos pueden llamarse igual
            carpeta.mkdir()
            temporal = carpeta / nombre    # mismo nombre: lo usa el desempate entre exportaciones
            temporal.write_bytes(contenido)
            temporales.append(temporal)
        infos = validar_lote(temporales, raw)

        cargados, rechazados = [], []
        for info in infos:
            if not info.ok:
                rechazados.append(info)
                continue
            carpeta = _carpeta_destino(info, raw)
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = _nombre_libre(carpeta, info.nombre)
            shutil.copyfile(info.path, destino)
            info.path = destino
            cargados.append(info)

    if not cargados:
        n = len(rechazados)
        return ResultadoLote(False, "El archivo no se cargó." if n == 1 else f"Ninguno de los {n} archivos se cargó.",
                             rechazados=rechazados)

    try:
        resumen = procesar(raw, bronze, silver, reportes, gold, verbose=verbose)
    except Exception as e:
        # Vuelta atrás: se sacan los archivos del lote y se regeneran los datos anteriores.
        for info in cargados:
            info.path.unlink(missing_ok=True)
        procesar(raw, bronze, silver, reportes, gold, verbose=False)
        return ResultadoLote(False, "Los archivos pasaron la validación pero el pipeline falló; se descartaron "
                             "y los datos quedaron como estaban.", rechazados=rechazados + cargados,
                             errores=[f"{type(e).__name__}: {e}"])

    if len(cargados) == 1:
        mensaje = f"Se cargó «{cargados[0].nombre}» ({_describir(cargados[0])}) y se recalculó todo."
    else:
        mensaje = f"Se cargaron {len(cargados)} archivos y se recalculó todo una sola vez."
    if rechazados:
        mensaje += f" {len(rechazados)} no se cargaron (abajo, el motivo)."
    return ResultadoLote(True, mensaje, cargados=cargados, rechazados=rechazados, resumen=resumen)


def agregar_archivo(contenido: bytes, nombre: str, raw: Path = RAW, bronze: Path = BRONZE,
                    silver: Path = SILVER, reportes: Path = REPORTS, gold: Path = GOLD,
                    verbose: bool = False) -> ResultadoCarga:
    """Suma UN Excel nuevo (atajo de agregar_archivos para la terminal y los tests):
        r = agregar_archivo(archivo.getvalue(), archivo.name)
    Nunca lanza excepciones: si algo falla devuelve ok=False con los motivos
    y deja data/raw/ (y los datos procesados) como estaban."""
    nombre = Path(nombre).name
    r = agregar_archivos([(contenido, nombre)], raw, bronze, silver, reportes, gold, verbose)
    info = (r.cargados or r.rechazados or [None])[0]
    if r.ok:
        return ResultadoCarga(True, r.mensaje, info, destino=info.path, resumen=r.resumen, avisos=info.avisos)
    if r.errores:  # falló el pipeline
        return ResultadoCarga(False, f"El archivo «{nombre}» pasó la validación pero el pipeline falló; "
                              "se descartó y los datos quedaron como estaban.", info,
                              errores=r.errores, avisos=info.avisos)
    return ResultadoCarga(False, f"El archivo «{nombre}» no se cargó.", info,
                          errores=info.errores, avisos=info.avisos)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline del TFI (raw -> bronze -> silver -> gold).")
    sub = parser.add_subparsers(dest="comando")
    p_agregar = sub.add_parser("agregar", help="Valida uno o varios Excel nuevos, los copia a data/raw/ y reprocesa.")
    p_agregar.add_argument("archivos", type=Path, nargs="+")
    args = parser.parse_args()

    if args.comando == "agregar":
        r = agregar_archivos([(a.read_bytes(), a.name) for a in args.archivos], verbose=True)
        print(("\n✓ " if r.ok else "\n✗ ") + r.mensaje)
        for info in r.cargados:
            print(f"  cargado: {info.nombre} -> {info.path.relative_to(ROOT)}")
            for a in info.avisos:
                print(f"    aviso: {a}")
        for info in r.rechazados:
            print(f"  no se cargó: {info.nombre}")
            for e in info.errores:
                print(f"    error: {e}")
        for e in r.errores:
            print(f"  error del pipeline: {e}")
        sys.exit(0 if r.ok else 1)
    procesar()


if __name__ == "__main__":
    main()
