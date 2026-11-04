"""
Tests de la Etapa 1: ingesta preparada para archivos nuevos.

Correr desde la raíz:  python -m pytest
Los tests trabajan sobre copias en carpetas temporales: data/raw/ nunca se toca.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from src.config import RAW
from src.ingesta import descubrir, inspeccionar, leer, seleccionar
from src.pipeline import agregar_archivo, procesar
from src.validacion import validar_archivo

ALG = RAW / "Álgebra"
PARCIAL_ALG = ALG / "calificaciones_alumnos_20251024_114944.xlsx"   # '1° Parcial'


def copia_modificada(origen: Path, destino: Path, cambios: dict | None = None, filas_arriba: int = 0) -> Path:
    """Copia un Excel cambiando celdas ({'A3': 'nuevo valor'}) y/o agregando filas al principio."""
    wb = openpyxl.load_workbook(origen)
    ws = wb.active
    if filas_arriba:
        ws.insert_rows(1, filas_arriba)
    for celda, valor in (cambios or {}).items():
        ws[celda] = valor
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


@pytest.fixture
def raw_chico(tmp_path) -> Path:
    """Un data/raw/ mínimo: solo Álgebra (rápido de procesar)."""
    raw = tmp_path / "raw"
    shutil.copytree(ALG, raw / "Álgebra")
    (raw / "Matriculados").mkdir()
    shutil.copy(RAW / "Matriculados" / "Álgebra.xlsx", raw / "Matriculados")
    return raw


# ---------------------------------------------------------------------------
# Reconocimiento por contenido
# ---------------------------------------------------------------------------
def test_reconoce_todos_los_archivos_reales():
    infos = descubrir(RAW)
    assert all(i.ok for i in infos), [(i.nombre, i.errores) for i in infos if not i.ok]
    tipos = pd.Series([i.tipo for i in infos]).value_counts().to_dict()
    assert tipos == {"calificaciones": 17, "trazabilidad": 3, "participacion": 3, "matriculados": 3}
    # la materia que sale del contenido coincide con la carpeta en todos los casos
    assert {i.asignatura for i in infos} == {"Álgebra", "Algoritmos y Estructuras de Datos", "Probabilidad y Estadística"}


def test_archivo_renombrado_y_fuera_de_carpeta(tmp_path):
    p = tmp_path / "notas del parcial.xlsx"
    shutil.copy(PARCIAL_ALG, p)
    info = inspeccionar(p)
    assert (info.tipo, info.asignatura, info.instrumento, info.fila_encabezado) == \
        ("calificaciones", "Álgebra", "1° Parcial", 7)


def test_encabezado_corrido(tmp_path):
    """Dos filas de más arriba: el encabezado se busca, no está fijo en la fila 7."""
    p = copia_modificada(PARCIAL_ALG, tmp_path / "corrido.xlsx", filas_arriba=2)
    info = inspeccionar(p)
    assert info.fila_encabezado == 9
    original = leer(inspeccionar(PARCIAL_ALG)).drop(columns="archivo_origen")
    corrido = leer(info).drop(columns="archivo_origen")
    pd.testing.assert_frame_equal(original, corrido)


def test_materia_en_carpeta_equivocada(tmp_path):
    raw = tmp_path / "raw"
    carpeta = raw / "Probabilidad y Estadística"
    carpeta.mkdir(parents=True)
    shutil.copy(PARCIAL_ALG, carpeta / "x.xlsx")
    [info] = descubrir(raw)
    assert not info.ok and "carpeta" in info.errores[0]


# ---------------------------------------------------------------------------
# Validación de archivos nuevos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cambios, texto_error", [
    ({"D8": "30.00/25.00"}, "fuera de rango"),
    ({"D8": "veinte"}, "obtenido/máximo"),
    ({"A8": "ALUMNO 1"}, "formato inválido"),
    ({"A2": "Nombre del aula: Física 2025"}, "materia"),
    ({"D7": "Puntaje"}, "fila de encabezado"),     # tiene la firma 'Calificación:' pero no la columna Nota
])
def test_validacion_rechaza(tmp_path, raw_chico, cambios, texto_error):
    p = copia_modificada(PARCIAL_ALG, tmp_path / "nuevo.xlsx", cambios)
    info = validar_archivo(p, raw_chico)
    assert not info.ok
    assert any(texto_error in e for e in info.errores), info.errores


def test_validacion_rechaza_lo_que_no_es_del_lms(tmp_path, raw_chico):
    wb = openpyxl.Workbook()
    wb.active["A1"] = "cualquier cosa"
    wb.save(tmp_path / "otro.xlsx")
    (tmp_path / "notas.csv").write_text("a,b\n1,2")
    assert "tipo de archivo" in validar_archivo(tmp_path / "otro.xlsx", raw_chico).errores[0]
    assert ".xlsx" in validar_archivo(tmp_path / "notas.csv", raw_chico).errores[0]


def test_validacion_archivo_repetido(raw_chico):
    info = validar_archivo(PARCIAL_ALG, raw_chico)
    assert not info.ok and "ya está cargado" in info.errores[0]


def test_instrumento_nuevo_se_acepta(tmp_path, raw_chico):
    p = copia_modificada(PARCIAL_ALG, tmp_path / "parcial2.xlsx", {"A3": "Calificación: 2° Parcial"})
    info = validar_archivo(p, raw_chico)
    assert info.ok, info.errores
    assert "Instrumento nuevo" in info.avisos[0]


def test_reexportacion_reemplaza_a_la_anterior(tmp_path, raw_chico):
    """Misma materia e instrumento: vale la exportación más reciente; una más vieja se rechaza."""
    nueva = copia_modificada(PARCIAL_ALG, tmp_path / "nueva.xlsx",
                             {"A1": "Fecha de exportación: 30/10/2025 10:00", "D8": "20.00/25.00"})
    vieja = copia_modificada(PARCIAL_ALG, tmp_path / "vieja.xlsx",
                             {"A1": "Fecha de exportación: 01/10/2025 10:00", "D8": "20.00/25.00"})
    assert validar_archivo(nueva, raw_chico).ok
    assert "Reemplaza" in validar_archivo(nueva, raw_chico).avisos[0]
    assert "más reciente" in validar_archivo(vieja, raw_chico).errores[0]

    shutil.copy(nueva, raw_chico / "Álgebra" / "nueva.xlsx")
    usar, avisos = seleccionar(descubrir(raw_chico))
    assert "nueva.xlsx" in [i.nombre for i in usar] and PARCIAL_ALG.name not in [i.nombre for i in usar]
    assert any("reemplazado" in a for a in avisos)


# ---------------------------------------------------------------------------
# Carga de punta a punta (agregar_archivo + procesar)
# ---------------------------------------------------------------------------
def test_agregar_archivo_y_vuelta_atras(tmp_path, raw_chico):
    salidas = dict(bronze=tmp_path / "bronze", silver=tmp_path / "silver", reportes=tmp_path / "reports",
                   gold=tmp_path / "gold")
    antes = procesar(raw_chico, verbose=False, **salidas)

    # 1) Un archivo inválido no toca raw ni los datos
    malo = copia_modificada(PARCIAL_ALG, tmp_path / "malo.xlsx", {"A3": "Calificación: 2° Parcial", "D8": "99/25"})
    r = agregar_archivo(malo.read_bytes(), "malo.xlsx", raw_chico, **salidas)
    assert not r.ok and r.errores
    assert not list(raw_chico.rglob("malo.xlsx"))

    # 2) Un instrumento nuevo se suma y se recalcula todo
    bueno = copia_modificada(PARCIAL_ALG, tmp_path / "otro_nombre.xlsx", {"A3": "Calificación: 2° Parcial"})
    r = agregar_archivo(bueno.read_bytes(), "otro_nombre.xlsx", raw_chico, **salidas)
    assert r.ok, r.errores
    assert r.destino == raw_chico / "Álgebra" / "otro_nombre.xlsx"
    filas_parcial = len(leer(inspeccionar(PARCIAL_ALG)))
    assert r.resumen["silver"]["calificaciones"] == antes["silver"]["calificaciones"] + filas_parcial
    silver = pd.read_parquet(salidas["silver"] / "calificaciones.parquet")
    assert "2° Parcial" in set(silver["instrumento"])


def test_si_el_pipeline_falla_se_descarta_el_archivo(tmp_path, raw_chico, monkeypatch):
    """Pasa la validación pero el pipeline falla: el archivo se saca de raw y se regeneran los datos."""
    import src.pipeline as pipeline
    salidas = dict(bronze=tmp_path / "bronze", silver=tmp_path / "silver", reportes=tmp_path / "reports",
                   gold=tmp_path / "gold")
    llamadas = []
    original = pipeline.procesar

    def procesar_que_falla_una_vez(*args, **kwargs):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("falla simulada")
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "procesar", procesar_que_falla_una_vez)
    nuevo = copia_modificada(PARCIAL_ALG, tmp_path / "p2.xlsx", {"A3": "Calificación: 2° Parcial"})
    r = pipeline.agregar_archivo(nuevo.read_bytes(), "p2.xlsx", raw_chico, **salidas)
    assert not r.ok and "falla simulada" in r.errores[0]
    assert not list(raw_chico.rglob("p2.xlsx"))
    assert len(llamadas) == 2 and (salidas["silver"] / "calificaciones.parquet").exists()
