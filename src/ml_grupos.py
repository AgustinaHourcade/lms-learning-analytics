"""
ETAPA 7 - ML: grupos de alumnos con K-Means (D57). Va en el dashboard 5.

Agrupa a los alumnos de la base según cómo usan el aula y cómo les va:
sesiones, minutos, semanas con actividad, avance y nota (GRUPOS_VARIABLES).

Pasos:
  1. Variables: salen de `metricas.tabla_alumnos` a la fecha de corte (el
     avance sale del reporte de participación, que es una foto al 24/10, D36).
  2. Transformación: log(1 + x) a sesiones y minutos (muy asimétricas) y
     estandarización (media 0, desvío 1) DENTRO de cada materia. Así cada
     alumno se compara con su curso: 150 minutos no significan lo mismo en PyE
     que en Álgebra, y en AED las notas son más bajas en general.
  3. K-Means con las tres materias juntas: un solo modelo, así los grupos se
     llaman igual en todas las materias y se pueden comparar.
  4. k = el de mayor silhouette entre GRUPOS_K (3 a 6). k = 2 se calcula como
     referencia, pero no es candidato: solo separa "entran / no entran", que ya
     lo dice el estado de actividad (D35).
  5. Nombres: cada grupo se nombra según su centroide (cuánta actividad y qué
     nota tiene respecto del promedio de su materia), no según el número que
     le pone K-Means, que es arbitrario. Grupo 1 = el de mejor perfil.

Funciones (mismos parámetros que src/metricas.py):
  evaluar_k(d, fecha_corte)          silhouette, inercia y tamaños para cada k
  grupos_alumnos(d, fecha_corte, asignatura, umbral, k=None)
                                     tabla_alumnos + grupo, nombre y descripción
  perfil_grupos(d, fecha_corte, asignatura, umbral, k=None, por_materia=False)
                                     una fila por grupo: tamaño, medianas y condición
  centroides(d, fecha_corte, k=None) centroide de cada grupo, en desvíos (formato largo)
  mapa_grupos(d, fecha_corte, asignatura, umbral, k=None)
                                     los grupos proyectados en 2 ejes con PCA (para graficarlos)

El modelo se ajusta siempre con todas las materias; `asignatura` solo filtra
el resultado. Tarda menos de un segundo, así que se recalcula con cada fecha
de corte en vez de guardarse con joblib (eso queda para el predictor).

Probar desde la raíz:
    python -m src.ml_grupos
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

from src import metricas as m
from src.config import (GRUPOS_K, GRUPOS_LOG, GRUPOS_SEMILLA, GRUPOS_VARIABLES, SIN_EVALUACIONES,
                        UMBRAL_INACTIVIDAD_DIAS)

VARIABLES_ACTIVIDAD = [v for v in GRUPOS_VARIABLES if v != "nota_pct"]
K_REFERENCIA = 2   # se informa, pero no se elige (punto 4 del docstring)

# Nombre -> descripción para el tutor, del mejor al peor perfil.
GRUPOS = {
    "Comprometidos": "Entran seguido, avanzan con el material y les va bien. No necesitan intervención.",
    "Eficientes": "Entran menos que el promedio de su materia, pero tienen buena nota.",
    "Esforzados con nota baja": "Entran tanto o más que el promedio, pero la nota no acompaña: "
                                "conviene apoyo académico (consultas, tutorías).",
    "Intermitentes": "Actividad y nota por debajo del promedio: entran de forma irregular y "
                     "rinden poco. Todavía se pueden recuperar.",
    "Desconectados": "Casi no entran al aula y no rinden: riesgo alto de abandono, conviene contactarlos.",
}
UMBRAL_DESCONECTADOS = -1.0   # actividad del centroide (en desvíos) por debajo de la cual
SIN_GRUPO = "Sin grupo"
DESCRIPCION_SIN_GRUPO = ("Su materia todavía no tiene evaluaciones a la fecha de corte: sin nota, "
                         "los grupos no se pueden armar.")


# ---------------------------------------------------------------------------
# Preparación y elección de k
# ---------------------------------------------------------------------------
def matriz(t: pd.DataFrame) -> pd.DataFrame:
    """Variables transformadas y estandarizadas dentro de cada materia.
    Si una variable no varía en una materia (por ej. con una fecha de corte muy
    temprana), queda en 0 y no aporta a la distancia."""
    x = t[GRUPOS_VARIABLES].astype(float).fillna(0)
    if x.empty:
        return x
    for col in GRUPOS_LOG:
        x[col] = np.log1p(x[col])
    z = x.groupby(t["asignatura"]).transform(lambda s: (s - s.mean()) / s.std(ddof=0))
    return z.replace([np.inf, -np.inf], np.nan).fillna(0)


def _con_evaluaciones(t: pd.DataFrame) -> pd.Series:
    """Solo entran las materias que ya tienen alguna evaluación a la fecha de
    corte: antes de la primera, la nota no existe y los grupos solo
    reflejarían la actividad de los primeros días."""
    return t["condicion"].ne(SIN_EVALUACIONES)


def _kmeans(z: pd.DataFrame, k: int) -> KMeans:
    with warnings.catch_warnings():   # pocos puntos distintos -> aviso de convergencia
        warnings.simplefilter("ignore")
        return KMeans(n_clusters=k, n_init=20, random_state=GRUPOS_SEMILLA).fit(z)


def _evaluar(z: pd.DataFrame) -> pd.DataFrame:
    distintos = len(z.drop_duplicates())
    filas = []
    for k in [K_REFERENCIA, *GRUPOS_K]:
        if k >= distintos:   # silhouette necesita al menos un punto más que grupos
            continue
        km = _kmeans(z, k)
        filas.append({"k": k, "silhouette": round(float(silhouette_score(z, km.labels_)), 3),
                      "inercia": round(float(km.inertia_), 1), "candidato": k in GRUPOS_K,
                      "tamanos": sorted(np.bincount(km.labels_).tolist(), reverse=True)})
    r = pd.DataFrame(filas, columns=["k", "silhouette", "inercia", "candidato", "tamanos"])
    cand = r[r["candidato"]]
    r["elegido"] = r["k"].eq(cand.loc[cand["silhouette"].idxmax(), "k"]) if len(cand) else False
    return r


def evaluar_k(d: m.Datos, fecha_corte=None) -> pd.DataFrame:
    """Para cada k: silhouette (más alto = grupos más separados), inercia (para
    el gráfico del codo) y tamaño de los grupos. `elegido` = mayor silhouette
    entre los candidatos (GRUPOS_K)."""
    t = m.tabla_alumnos(d, fecha_corte)
    return _evaluar(matriz(t[_con_evaluaciones(t)]))


# ---------------------------------------------------------------------------
# Ajuste y nombres
# ---------------------------------------------------------------------------
def _nombrar(centros: pd.DataFrame) -> pd.DataFrame:
    """Nombre de cada grupo según su centroide. actividad = promedio de los
    desvíos de las variables de actividad; nota = desvío de la nota."""
    c = centros.assign(actividad=centros[VARIABLES_ACTIVIDAD].mean(axis=1), nota=centros["nota_pct"])
    c["nombre_grupo"] = np.select(
        [c["actividad"] < UMBRAL_DESCONECTADOS,
         (c["actividad"] >= 0) & (c["nota"] >= 0), c["nota"] >= 0, c["actividad"] >= 0],
        ["Desconectados", "Comprometidos", "Eficientes", "Esforzados con nota baja"], default="Intermitentes")
    c["descripcion_grupo"] = c["nombre_grupo"].map(GRUPOS)
    c = c.assign(puntaje=c["actividad"] + c["nota"]).sort_values("puntaje", ascending=False)
    c["grupo"] = range(1, len(c) + 1)   # 1 = mejor perfil
    # Si dos grupos caen en la misma categoría, se numeran: "Intermitentes (1)", "(2)".
    rep = c["nombre_grupo"].duplicated(keep=False)
    c.loc[rep, "nombre_grupo"] += " (" + (c[rep].groupby("nombre_grupo").cumcount() + 1).astype(str) + ")"
    return c.drop(columns="puntaje")


def _ajustar(t: pd.DataFrame, k: int | None = None) -> tuple[pd.Series, pd.DataFrame]:
    """Grupo de cada fila de `t` (1 = mejor perfil) y una tabla por grupo con
    nombre, descripción y centroide en desvíos. Grupo 0 = sin grupo (su
    materia todavía no tiene evaluaciones o no alcanzan los datos)."""
    sin_grupo = pd.DataFrame({"grupo": [0], "nombre_grupo": [SIN_GRUPO], "descripcion_grupo": [DESCRIPCION_SIN_GRUPO]})
    grupo = pd.Series(0, index=t.index)
    entran = _con_evaluaciones(t)
    z = matriz(t[entran])
    r = _evaluar(z)
    if k is None and r["elegido"].any():
        k = int(r.loc[r["elegido"], "k"].iloc[0])
    if k is None or k not in r["k"].tolist():
        return grupo, sin_grupo
    km = _kmeans(z, k)
    info = _nombrar(pd.DataFrame(km.cluster_centers_, columns=GRUPOS_VARIABLES))
    grupo[entran] = pd.Series(km.labels_, index=z.index).map(info["grupo"])
    info = info.sort_values("grupo").reset_index(drop=True)
    if not entran.all():
        info = pd.concat([info, sin_grupo], ignore_index=True)
    return grupo, info


# ---------------------------------------------------------------------------
# Salidas para el dashboard
# ---------------------------------------------------------------------------
def grupos_alumnos(d: m.Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                   k: int | None = None) -> pd.DataFrame:
    """`tabla_alumnos` + grupo (1 = mejor perfil), nombre_grupo y
    descripcion_grupo. `k=None` usa el k elegido por silhouette."""
    t = m.tabla_alumnos(d, fecha_corte, None, umbral)
    grupo, info = _ajustar(t, k)
    t = t.assign(grupo=grupo).merge(info[["grupo", "nombre_grupo", "descripcion_grupo"]], on="grupo", how="left")
    t.attrs["k"] = int(info["grupo"].max())   # 0 = no se pudieron armar grupos
    return m._filtrar(t, asignatura).reset_index(drop=True)


DESCRIPCIONES = {**m.VARIABLES_CRUCE, "nota_pct": "Nota (sobre 100)"}


def mapa_grupos(d: m.Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                k: int | None = None) -> dict:
    """Los grupos en 2 dimensiones, para verlos separados. Resume las 5
    variables (las mismas que ve el K-Means: con log y estandarizadas por
    materia) en 2 ejes con PCA. Devuelve un dict:
      alumnos   una fila por alumno con grupo: eje1, eje2 y sus datos
      centros   el centro de cada grupo en los mismos ejes
      varianza  % de la variación total que explica cada eje
      cargas    peso de cada variable en cada eje (para explicarlos)
    Los signos se fijan para que se lean siempre igual: eje 1 positivo = más
    actividad y mejor nota; eje 2 positivo = mejor nota que lo que entra."""
    t = grupos_alumnos(d, fecha_corte, None, umbral, k)
    t = t[t["grupo"] > 0]
    vacio = {"alumnos": pd.DataFrame(columns=["asignatura", "id_alumno", "grupo", "nombre_grupo", "eje1", "eje2"]),
             "centros": pd.DataFrame(columns=["grupo", "nombre_grupo", "eje1", "eje2", "alumnos"]),
             "varianza": [], "cargas": pd.DataFrame(columns=["variable", "descripcion", "eje1", "eje2"])}
    if len(t) < 3:
        return vacio
    z = matriz(t)
    pca = PCA(n_components=2, random_state=GRUPOS_SEMILLA).fit(z)
    signos = np.sign([pca.components_[0].sum(), pca.components_[1][GRUPOS_VARIABLES.index("nota_pct")]])
    signos[signos == 0] = 1
    ejes = pca.transform(z) * signos
    alumnos = t.assign(eje1=ejes[:, 0].round(3), eje2=ejes[:, 1].round(3))
    centros = (alumnos.groupby(["grupo", "nombre_grupo"])
                      .agg(eje1=("eje1", "mean"), eje2=("eje2", "mean"), alumnos=("id_alumno", "size"))
                      .round(3).reset_index())
    cargas = pd.DataFrame({"variable": GRUPOS_VARIABLES, "descripcion": [DESCRIPCIONES[v] for v in GRUPOS_VARIABLES],
                           "eje1": (pca.components_[0] * signos[0]).round(2),
                           "eje2": (pca.components_[1] * signos[1]).round(2)})
    return {"alumnos": m._filtrar(alumnos, asignatura).reset_index(drop=True), "centros": centros,
            "varianza": [round(100 * float(v), 1) for v in pca.explained_variance_ratio_], "cargas": cargas}


def perfil_grupos(d: m.Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                  k: int | None = None, por_materia: bool = False) -> pd.DataFrame:
    """Una fila por grupo (y materia si `por_materia`): cantidad de alumnos y %,
    mediana de cada variable en sus unidades reales, nota promedio, % por
    condición y % de activos a la fecha de corte."""
    t = grupos_alumnos(d, fecha_corte, asignatura, umbral, k)
    claves = ["asignatura"] if por_materia else []
    g = t.groupby([*claves, "grupo", "nombre_grupo", "descripcion_grupo"])
    p = g[GRUPOS_VARIABLES].median().round(1).add_prefix("mediana_")
    p.insert(0, "alumnos", g.size())
    total = p.groupby(level=claves)["alumnos"].transform("sum") if claves else p["alumnos"].sum()
    p.insert(1, "pct", (100 * p["alumnos"] / total).round(1))
    p["nota_promedio"] = g["nota_pct"].mean().round(1)
    cond = pd.crosstab([t[c] for c in [*claves, "grupo"]], t["condicion"], normalize="index").mul(100).round(1)
    cond.columns = [f"pct_{m._sin_tildes(c).lower().replace(' ', '_')}" for c in cond.columns]
    p["pct_activos"] = g["activo"].mean().mul(100).round(1)
    p = p.reset_index().merge(cond.reset_index(), on=[*claves, "grupo"], how="left")
    return p.sort_values([*claves, "grupo"]).reset_index(drop=True)


def centroides(d: m.Datos, fecha_corte=None, k: int | None = None) -> pd.DataFrame:
    """Centroide de cada grupo en desvíos respecto del promedio de su materia
    (0 = promedio, +1 = un desvío por encima). Formato largo: una fila por
    grupo y variable, para un mapa de calor o un gráfico de barras."""
    _, info = _ajustar(m.tabla_alumnos(d, fecha_corte), k)
    info = info.reindex(columns=["grupo", "nombre_grupo", *GRUPOS_VARIABLES])
    largo = info[info["grupo"] > 0].melt(id_vars=["grupo", "nombre_grupo"], value_vars=GRUPOS_VARIABLES,
                      var_name="variable", value_name="desvios")
    largo["descripcion"] = largo["variable"].map(DESCRIPCIONES)
    largo["desvios"] = largo["desvios"].round(2)
    return largo[["grupo", "nombre_grupo", "variable", "descripcion", "desvios"]]


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    datos = m.cargar()
    print("Elección de k:\n", evaluar_k(datos), "\n")
    print(perfil_grupos(datos).drop(columns="descripcion_grupo"), "\n")
    print(perfil_grupos(datos, por_materia=True)[["asignatura", "grupo", "nombre_grupo", "alumnos", "pct"]])
