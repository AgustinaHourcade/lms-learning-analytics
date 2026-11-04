"""
Fixtures compartidas por los tests.

El pipeline completo (raw -> bronze -> silver -> gold) se corre UNA sola vez
por sesión de pytest y escribe en una carpeta temporal: data/ no se toca.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.pipeline import procesar


@pytest.fixture(scope="session")
def carpeta_pipeline(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pipeline")
    procesar(bronze=tmp / "bronze", silver=tmp / "silver", reportes=tmp / "reports", gold=tmp / "gold",
             verbose=False)
    return tmp


@pytest.fixture(scope="session")
def capas(carpeta_pipeline):
    def leer(capa: str, tabla: str) -> pd.DataFrame:
        return pd.read_parquet(carpeta_pipeline / capa / f"{tabla}.parquet")
    return leer
