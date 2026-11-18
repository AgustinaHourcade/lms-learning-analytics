"""
Tests de la Etapa 7: grupos de alumnos con K-Means (src/ml_grupos.py, D57).

Correr desde la raíz:  python -m pytest tests/test_ml_grupos.py
  * con centroides armados a mano: las reglas de nombres;
  * sobre el gold real (fixture de conftest.py): que cada alumno de la base
    tenga un grupo, que el k elegido sea el de mayor silhouette, que el
    resultado sea reproducible y que las fechas de corte tempranas no rompan.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src import metricas as m
from src import ml_grupos as g
from src.config import GRUPOS_K, GRUPOS_VARIABLES

ALG = "Álgebra"
FECHAS = ["2025-07-01", "2025-08-15", "2025-09-15", "2025-10-24"]


# ---------------------------------------------------------------------------
# Nombres de los grupos (centroides a mano, en desvíos)
# ---------------------------------------------------------------------------
def _centros(filas: list[tuple[float, float]]) -> pd.DataFrame:
    """Cada fila = (actividad, nota): todas las variables de actividad iguales."""
    return pd.DataFrame([{**{v: a for v in g.VARIABLES_ACTIVIDAD}, "nota_pct": n} for a, n in filas],
                        columns=GRUPOS_VARIABLES)


def test_nombres_segun_centroide():
    c = g._nombrar(_centros([(0.6, 0.7), (-0.4, 0.5), (0.3, -0.6), (-0.3, -0.7), (-1.8, -1.3)]))
    assert c.sort_index()["nombre_grupo"].tolist() == [
        "Comprometidos", "Eficientes", "Esforzados con nota baja", "Intermitentes", "Desconectados"]
    # grupo 1 = mejor perfil (actividad + nota), el último = Desconectados
    assert c.set_index("nombre_grupo")["grupo"].to_dict() == {
        "Comprometidos": 1, "Eficientes": 2, "Esforzados con nota baja": 3, "Intermitentes": 4, "Desconectados": 5}
    assert c["descripcion_grupo"].notna().all()


def test_nombres_repetidos_se_numeran():
    c = g._nombrar(_centros([(0.9, 0.9), (0.3, 0.2), (-1.5, -1.0)]))
    assert sorted(c["nombre_grupo"]) == ["Comprometidos (1)", "Comprometidos (2)", "Desconectados"]
    assert c.loc[c["grupo"].eq(1), "nombre_grupo"].item() == "Comprometidos (1)"


def test_matriz_estandariza_dentro_de_cada_materia():
    t = pd.DataFrame({"asignatura": ["A"] * 3 + ["B"] * 3,
                      "sesiones": [1, 10, 100, 0, 0, 0], "minutos": [5, 50, 500, 1, 2, 3],
                      "semanas_activas": [1, 2, 3, 10, 11, 12], "avance": [10, 20, 30, 70, 80, 90],
                      "nota_pct": [None, 50, 100, 60, 70, 80]})
    z = g.matriz(t)
    medias = z.groupby(t["asignatura"]).mean()
    assert (medias.abs() < 1e-9).all().all()
    assert (z.loc[3:, "sesiones"] == 0).all()   # no varía en B -> 0, sin NaN
    assert z.notna().all().all()
    # B tiene más semanas que A, pero dentro de su materia queda igual de "arriba"
    assert z.loc[2, "semanas_activas"] == pytest.approx(z.loc[5, "semanas_activas"])


# ---------------------------------------------------------------------------
# Sobre el gold real
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def d(carpeta_pipeline) -> m.Datos:
    return m.cargar(carpeta_pipeline / "gold")


def test_k_elegido_es_el_de_mayor_silhouette(d):
    r = g.evaluar_k(d)
    assert r["elegido"].sum() == 1
    cand = r[r["candidato"]]
    assert set(cand["k"]) == set(GRUPOS_K)
    assert r.loc[r["elegido"], "silhouette"].item() == cand["silhouette"].max()
    assert not r.loc[r["k"].eq(g.K_REFERENCIA), "candidato"].item()
    assert r["silhouette"].between(-1, 1).all()
    assert r["inercia"].is_monotonic_decreasing   # más grupos -> menos inercia


def test_cada_alumno_de_la_base_tiene_un_grupo(d):
    t = g.grupos_alumnos(d)
    assert len(t) == len(m.base(d))
    assert not t.duplicated(["asignatura", "id_alumno"]).any()
    k = t.attrs["k"]
    assert k in GRUPOS_K
    assert set(t["grupo"]) == set(range(1, k + 1))
    assert t["nombre_grupo"].notna().all() and t["descripcion_grupo"].notna().all()
    assert t.groupby("grupo")["nombre_grupo"].nunique().eq(1).all()


def test_el_grupo_1_tiene_mejor_perfil_que_el_ultimo(d):
    p = g.perfil_grupos(d)
    primero, ultimo = p.iloc[0], p.iloc[-1]
    for var in GRUPOS_VARIABLES:
        assert primero[f"mediana_{var}"] >= ultimo[f"mediana_{var}"]
    assert primero["pct_libre"] < ultimo["pct_libre"]


def test_perfil_cierra_con_la_base(d):
    p = g.perfil_grupos(d)
    assert p["alumnos"].sum() == len(m.base(d))
    assert p["pct"].sum() == pytest.approx(100, abs=0.2)
    pm = g.perfil_grupos(d, por_materia=True)
    assert pm.groupby("asignatura")["pct"].sum().sub(100).abs().lt(0.2).all()
    assert pm.groupby("asignatura")["alumnos"].sum().to_dict() == m.base(d).groupby("asignatura").size().to_dict()


def test_filtrar_por_materia_no_cambia_los_grupos(d):
    todas = g.grupos_alumnos(d).set_index(["asignatura", "id_alumno"])["grupo"]
    alg = g.grupos_alumnos(d, asignatura=ALG).set_index(["asignatura", "id_alumno"])["grupo"]
    assert alg.index.get_level_values("asignatura").unique().tolist() == [ALG]
    assert alg.equals(todas.loc[alg.index])


def test_reproducible(d):
    a = g.grupos_alumnos(d)[["asignatura", "id_alumno", "grupo"]]
    b = g.grupos_alumnos(d)[["asignatura", "id_alumno", "grupo"]]
    pd.testing.assert_frame_equal(a, b)


def test_k_fijo(d):
    t = g.grupos_alumnos(d, k=4)
    assert t.attrs["k"] == 4 and t["grupo"].nunique() == 4
    assert len(g.centroides(d, k=4)) == 4 * len(GRUPOS_VARIABLES)


@pytest.mark.parametrize("fecha", FECHAS)
def test_fechas_de_corte(d, fecha):
    t = g.grupos_alumnos(d, fecha)
    sin_eval = t["condicion"].eq(m.SIN_EVALUACIONES)
    # quien todavía no tiene evaluaciones en su materia queda "Sin grupo"; el resto tiene grupo
    assert (t.loc[sin_eval, "grupo"] == 0).all()
    assert (t.loc[~sin_eval, "grupo"] > 0).all()
    assert t.loc[sin_eval, "nombre_grupo"].eq(g.SIN_GRUPO).all()
    p = g.perfil_grupos(d, fecha)
    assert p["alumnos"].sum() == len(t)


def test_antes_de_la_primera_evaluacion_no_hay_grupos(d):
    t = g.grupos_alumnos(d, "2025-07-01")
    assert t.attrs["k"] == 0 and t["nombre_grupo"].eq(g.SIN_GRUPO).all()
    assert g.evaluar_k(d, "2025-07-01").empty
    assert g.centroides(d, "2025-07-01").empty


def test_mapa_pca(d):
    r = g.mapa_grupos(d)
    assert len(r["alumnos"]) == len(m.base(d))
    assert len(r["varianza"]) == 2 and r["varianza"][0] >= r["varianza"][1] > 0 and sum(r["varianza"]) <= 100
    # signos fijos: eje 1 crece con todo, eje 2 crece con la nota
    assert (r["cargas"]["eje1"] > 0).all()
    assert r["cargas"].set_index("variable").loc["nota_pct", "eje2"] > 0
    # el centro de cada grupo es el promedio de sus alumnos; el grupo 1 queda más a la derecha
    c = r["centros"].set_index("grupo")
    assert c.loc[1, "eje1"] == c["eje1"].max()
    assert c["alumnos"].sum() == len(r["alumnos"])
    assert g.mapa_grupos(d, "2025-07-01")["alumnos"].empty
