"""
ETAPA 7 - ML: predictor de abandono (D58). Va en la Ficha individual y en
Matrícula y alertas.

Pregunta: de los alumnos que ya entraron al aula, ¿quiénes van a abandonar la
materia, es decir, no van a volver a entrar ni a rendir nada más?

  * Objetivo (D67): a una fecha de corte c, un alumno de la base que entró
    alguna vez "abandona" si NO tiene ninguna interacción en la materia después
    de c ni rinde una evaluación posterior a la trazabilidad (por ej. una nota
    exportada después del último dato). Se predice también para los que llevan
    14 días o más sin entrar ("Alejado"): casi la mitad vuelve. Quien nunca
    entró queda "Sin actividad" (D35).
    Antes (D58-D66) el objetivo era "no entra en los próximos 14 días", pero
    más de la mitad de los que dejaban 2 semanas volvían: medía pausas.
  * Datos de entrenamiento: "fotos" de la cursada cada 3 días
    (ABANDONO_PASO_DIAS), desde el día 14 hasta ABANDONO_SEGUIMIENTO_DIAS (28)
    días antes del último dato, para tener al menos 4 semanas de seguimiento.
    El seguimiento va de 28 días (última foto) a más de 60 (primera). Un mismo
    alumno aparece en varias fotos.
  * Variables (VARIABLES), todas con lo que se sabía el día de la foto, sin nada
    del futuro: días sin entrar, interacciones y sesiones de las últimas 1 y 2
    semanas, tendencia, % de semanas con actividad, etc. Desde D64 también:
      - ritmo propio: su pausa habitual entre días activos;
      - calendario: días desde la última evaluación de la materia;
      - notas a la fecha: cada nota cuenta desde el día en que ese alumno la
        rindió (su evento 'Realizar evaluación'), no la foto de notas al 24/10;
      - otras materias: si sigue entrando a las demás;
      - mezcla: % de evaluación y de mirar notas.
    El reporte de participación no se usa: es una foto al 24/10 (D36).
  * Modelos: regresión logística, Random Forest y gradient boosting, comparados
    contra la regla simple "más de 7 días sin entrar" (ABANDONO_REGLA_DIAS).
  * Validación separando por alumno: los alumnos de prueba (25 %) no aparecen
    en entrenamiento en ninguna foto ni materia (GroupShuffleSplit). Dentro de
    entrenamiento, validación cruzada también por alumno (GroupKFold) para
    elegir el umbral y el modelo; la prueba se usa solo para informar.
  * Umbral: el que minimiza el costo de equivocarse (clase 10). No detectar a
    quien abandona (FN) cuesta ABANDONO_COSTO_FN; contactar a quien iba a
    seguir (FP) cuesta ABANDONO_COSTO_FP.
  * Se guarda con joblib junto a gold (ABANDONO_ARCHIVO). `cargar_modelo`
    lo vuelve a entrenar solo si los datos cambiaron (por ej. se cargó una
    trazabilidad nueva). En la app se carga con @st.cache_resource.

Funciones:
  variables(d, fecha_corte)                 las variables de cada alumno a esa fecha
  dataset(d)                                todas las fotos con su objetivo (para entrenar)
  entrenar(d) / cargar_modelo(d, ruta)      ajustar, comparar y guardar / leer el modelo
  riesgo_abandono(d, fecha_corte, asignatura, umbral, modelo)
                                            una fila por alumno de la base con su riesgo
  resumen_riesgo(...)                       una fila por materia
  riesgo_alumno(d, id_alumno, fecha_corte, umbral, modelo)
                                            el riesgo de un alumno en cada materia (Ficha)
  evolucion_riesgo(d, id_alumno, fecha_corte, modelo)
                                            su probabilidad en cada semana hasta la fecha de corte
  comparacion_modelos / curva_umbral / importancia_variables (d, modelo)
                                            lo que se guardó al entrenar, para mostrarlo

Probar desde la raíz:
    python -m src.ml_abandono            (entrena, guarda y muestra la comparación)
"""
from __future__ import annotations

import hashlib
import html
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from src import metricas as m
from src.config import (ABANDONO_ARCHIVO, ABANDONO_COSTO_FN, ABANDONO_COSTO_FP, ABANDONO_HORIZONTE_DIAS,
                        ABANDONO_PASO_DIAS, ABANDONO_REGLA_DIAS, ABANDONO_SEGUIMIENTO_DIAS, ABANDONO_SEMILLA,
                        ESQUEMA, GOLD, UMBRAL_INACTIVIDAD_DIAS)
from src.modelo import clave_instrumento

CLAVES = ["asignatura", "id_alumno"]
EVALUACION, NOTAS = "Evaluación", "Notas"   # categorías de dim_accion (D44)

# Variable -> descripción para el tutor. Todas se calculan con datos hasta la fecha de corte.
VARIABLES = {
    "dias_sin_actividad": "Días desde la última vez que entró",
    "eventos_7d": "Interacciones en los últimos 7 días",
    "eventos_14d": "Interacciones en los últimos 14 días",
    "dias_activos_14d": "Días con actividad en los últimos 14 días",
    "sesiones_14d": "Sesiones en los últimos 14 días",
    "minutos_14d": "Minutos en la plataforma en los últimos 14 días",
    "evaluaciones_14d": "Interacciones de evaluación en los últimos 14 días",
    "tendencia": "Tendencia: últimas 2 semanas contra las 2 anteriores (log)",
    "pct_semanas_activas": "% de las semanas de cursada en que entró",
    "eventos_total": "Interacciones desde el inicio de la cursada",
    "dias_de_cursada": "Días desde el inicio de la cursada",
    # D64: ritmo propio del alumno (una pausa larga preocupa menos si siempre hace pausas así)
    "dias_activos_total": "Días con actividad desde el inicio de la cursada",
    "pausa_habitual": "Su pausa habitual entre días activos (percentil 90, días)",
    "sin_vs_habitual": "Días sin entrar contra su pausa habitual",
    # D64: calendario de evaluaciones de la materia (después de un parcial es normal no entrar)
    "dias_desde_evaluacion": "Días desde la última evaluación de la materia",
    "entro_despues_evaluacion": "Entró después de la última evaluación de la materia",
    # D64: notas a la fecha (cada nota cuenta desde el día en que el alumno rindió)
    "tiene_notas": "Ya tiene alguna evaluación tomada",
    "nota_pct": "Nota a la fecha (sobre 100; lo no rendido cuenta 0)",
    "margen_promocion": "Nota a la fecha menos el corte de promoción (puntos sobre 100)",
    "pct_rendidos": "% de las evaluaciones tomadas que rindió",
    "rindio_ultima": "Rindió la última evaluación tomada",
    # D64: lo que hace en sus otras materias
    "eventos_14d_otras": "Interacciones en sus otras materias en los últimos 14 días",
    "materias_activas_14d": "Materias en las que entró en los últimos 14 días",
    "dias_sin_actividad_global": "Días desde que entró a cualquiera de sus materias",
    # D64: qué hace cuando entra
    "pct_evaluacion": "% de sus interacciones que son de evaluación",
    "pct_notas": "% de sus interacciones que son mirar notas",
}
# D65: sentido obligado de algunas variables en el gradient boosting (+1 = más valor, más riesgo).
MONOTONAS = {"dias_sin_actividad": 1, "sin_vs_habitual": 1, "dias_sin_actividad_global": 1, "eventos_7d": -1,
             "eventos_14d": -1, "dias_activos_14d": -1, "eventos_14d_otras": -1, "materias_activas_14d": -1,
             # D66: mejor nota, más rendidas o haber rendido la última nunca suben el riesgo
             "nota_pct": -1, "margen_promocion": -1, "pct_rendidos": -1, "rindio_ultima": -1}
CONTEOS = ["eventos_7d", "eventos_14d", "sesiones_14d", "minutos_14d", "evaluaciones_14d", "eventos_total",
           "dias_activos_total", "eventos_14d_otras"]

# Estados de cada alumno a la fecha de corte y niveles de riesgo.
# Cursando = entró en los últimos 14 días; Alejado = entró alguna vez, pero hace 14 días o más
# que no (no es "abandonó": casi la mitad vuelve, D67). A los dos se les predice el riesgo.
CURSANDO, ALEJADO, SIN_ACTIVIDAD = "Cursando", "Alejado", m.SIN_ACTIVIDAD
ALTO, MEDIO, BAJO = "Alto", "Medio", "Bajo"
NIVELES = [ALTO, MEDIO, BAJO, SIN_ACTIVIDAD]
REGLA = "Regla simple"
NOMBRES_MODELOS = {"logistica": "Regresión logística", "random_forest": "Random Forest",
                   "gradient_boosting": "Gradient boosting", "regla": REGLA}


# ---------------------------------------------------------------------------
# Variables a una fecha de corte (sin datos del futuro)
# ---------------------------------------------------------------------------
def _conteo(df: pd.DataFrame, mascara: pd.Series, nombre: str, col: str | None = None, func: str = "size"):
    g = df[mascara].groupby(CLAVES)
    return (g.size() if col is None else g[col].agg(func)).rename(nombre)


def variables(d: m.Datos, fecha_corte=None) -> pd.DataFrame:
    """Una fila por alumno de la base con las VARIABLES a la fecha de corte,
    calculadas solo con las interacciones hasta ese día (inclusive).
    Quien todavía no entró tiene eventos_total = 0 y dias_sin_actividad vacío."""
    corte = m.fecha_de_corte(fecha_corte)
    ev = m._eventos(d, corte, None)
    ses = m._sesiones(d, corte, None)
    if ev.empty:   # antes del primer evento: nadie entró todavía
        v = m.base(d)[CLAVES].assign(ultima=pd.NaT, eventos_14d_previos=0.0, semanas_activas=0.0,
                                     materias_en_base=1, **{c: 0.0 for c in VARIABLES})
        v["dias_sin_actividad"] = np.nan
        v.insert(2, "fecha_corte", corte)
        return v
    inicio = ev.groupby("asignatura")["fecha"].min().rename("inicio")   # primer evento de la materia
    ev = ev.assign(atras=(corte - ev["fecha"]).dt.days, semana=(ev["fecha"] - ev["asignatura"].map(inicio)).dt.days // 7)
    ses = ses.assign(atras=(corte - ses["fecha"]).dt.days)
    ult7, ult14, previas = ev["atras"] < 7, ev["atras"] < 14, ev["atras"].between(14, 27)
    partes = [
        ev.groupby(CLAVES)["fecha"].max().rename("ultima"),
        ev.groupby(CLAVES).size().rename("eventos_total"),
        ev.groupby(CLAVES)["semana"].nunique().rename("semanas_activas"),
        _conteo(ev, ult7, "eventos_7d"),
        _conteo(ev, ult14, "eventos_14d"),
        _conteo(ev, previas, "eventos_14d_previos"),
        _conteo(ev, ult14, "dias_activos_14d", "fecha", "nunique"),
        _conteo(ev, ult14 & ev["categoria"].eq(EVALUACION), "evaluaciones_14d"),
        _conteo(ses, ses["atras"] < 14, "sesiones_14d"),
        _conteo(ses, ses["atras"] < 14, "minutos_14d", "duracion_min", "sum"),
    ]
    v = m.base(d)[CLAVES].merge(pd.concat(partes, axis=1).reset_index(), on=CLAVES, how="left")
    for col in [c for c in v.columns if c not in (*CLAVES, "ultima")]:
        v[col] = v[col].fillna(0)
    v["dias_sin_actividad"] = (corte - v["ultima"]).dt.days.astype(float)
    dias = (corte - v["asignatura"].map(inicio)).dt.days
    v["dias_de_cursada"] = dias.fillna(0).clip(lower=0).astype(float)
    v["pct_semanas_activas"] = (100 * v["semanas_activas"] / (dias // 7 + 1)).fillna(0).clip(upper=100).round(1)
    v["tendencia"] = np.log((v["eventos_14d"] + 1) / (v["eventos_14d_previos"] + 1)).round(3)
    v["minutos_14d"] = v["minutos_14d"].round(1)
    v = _ritmo(v, ev)
    v = _calendario(d, v, corte)
    v = _notas_a_la_fecha(d, v, corte)
    v = _otras_materias(v)
    v = _mezcla(v, ev)
    v.insert(2, "fecha_corte", corte)
    return v


def _ritmo(v: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    """Días activos y pausa habitual (percentil 90 de los huecos entre días con
    actividad, sin contar el hueco actual). Sin pausas todavía: los días de cursada."""
    dias = ev[[*CLAVES, "fecha"]].drop_duplicates().sort_values([*CLAVES, "fecha"])
    dias["hueco"] = dias.groupby(CLAVES)["fecha"].diff().dt.days
    g = pd.concat([dias.groupby(CLAVES).size().rename("dias_activos_total"),
                   dias.groupby(CLAVES)["hueco"].quantile(0.9).rename("pausa_habitual")], axis=1).reset_index()
    v = v.merge(g, on=CLAVES, how="left")
    v["dias_activos_total"] = v["dias_activos_total"].fillna(0)
    v["pausa_habitual"] = v["pausa_habitual"].fillna(v["dias_de_cursada"]).round(1)
    v["sin_vs_habitual"] = (v["dias_sin_actividad"] / (v["pausa_habitual"] + 1)).round(3)
    return v


def _calendario(d: m.Datos, v: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """Días desde la última evaluación de la materia (fecha del instrumento, D18)
    y si el alumno entró después. Sin evaluaciones todavía: los días de cursada."""
    inst = d.instrumentos[d.instrumentos["fecha_instrumento"] <= corte]
    por_materia = inst.groupby("asignatura")["fecha_instrumento"].max()
    ultima = v["asignatura"].map(por_materia.to_dict()).astype("datetime64[us]")   # dict: anda aunque esté vacío
    v["dias_desde_evaluacion"] = (corte - ultima).dt.days.astype(float).fillna(v["dias_de_cursada"])
    v["entro_despues_evaluacion"] = v["dias_sin_actividad"].lt(v["dias_desde_evaluacion"]).astype(float)
    return v


def _realizaciones(d: m.Datos) -> pd.DataFrame:
    """Primer evento 'Realizar evaluación' de cada alumno en cada instrumento
    (la descripción dice cuál es): el día en que su nota pasa a conocerse."""
    i = d.interacciones
    ev = i[i["en_base"] & i["accion"].eq("Realizar evaluación")]
    nombre = ev["descripcion"].map(html.unescape).str.extract(r"evaluaci[oó]n '(.+?)' de la unidad", expand=False)
    claves = d.instrumentos.assign(clave=d.instrumentos["instrumento"].map(clave_instrumento))
    ev = ev.assign(clave=nombre.map(clave_instrumento, na_action="ignore")).dropna(subset=["clave"])
    ev = ev.merge(claves[["asignatura", "clave", "id_instrumento"]], on=["asignatura", "clave"])
    return ev.groupby([*CLAVES, "id_instrumento"])["fecha_hora"].min().rename("rindio_el").reset_index()


def _notas_a_la_fecha(d: m.Datos, v: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """Nota de cada alumno con lo que se sabía a la fecha de corte, sin usar el futuro:
      * una evaluación está "tomada" si su fecha (D18) ya pasó o si el alumno ya la rindió;
      * cada nota cuenta desde el día en que ESE alumno la rindió (su evento 'Realizar
        evaluación'); si no hay evento, desde la última realización del instrumento;
      * lo tomado y no rendido cuenta 0 (D16) y el recuperatorio reemplaza (D19) desde que se rinde.
    Los instrumentos sin ninguna fecha (sin eventos en la trazabilidad) no se usan."""
    fin = m._fin_del_dia(corte)
    inst = d.instrumentos.set_index("id_instrumento")
    c = d.calificaciones[d.calificaciones["cuenta_en_final"]].merge(_realizaciones(d), how="left",
                                                                     on=[*CLAVES, "id_instrumento"])
    c["conocida"] = c["rindio_el"].fillna(c["id_instrumento"].map(inst["fecha_ultima_realizacion"]))
    rec = _realizaciones(d).rename(columns={"id_instrumento": "id_recuperatorio", "rindio_el": "recupero_el"})
    c = c.merge(rec, how="left", on=[*CLAVES, "id_recuperatorio"])
    c["recupero_el"] = c["recupero_el"].fillna(c["id_recuperatorio"].map(inst["fecha_ultima_realizacion"]))
    rindio = c["rindio"] & (c["conocida"] < fin)
    recupero = c["rindio_recuperatorio"] & (c["recupero_el"] < fin)
    tomada = (c["id_instrumento"].map(inst["fecha_instrumento"]) <= corte) | rindio | recupero
    c = c.assign(pts=np.where(recupero, c["puntos"], np.where(rindio, c["puntos_sin_recuperatorio"], 0.0)),
                 rend=rindio | recupero, fecha=c["id_instrumento"].map(inst["fecha_instrumento"]))[tomada]
    g = c.groupby(CLAVES).agg(pts=("pts", "sum"), maximo=("puntaje_maximo", "sum"), rendidos=("rend", "sum"),
                              tomadas=("id_instrumento", "size")).reset_index()
    ultima = c.sort_values("fecha").groupby(CLAVES).tail(1)[[*CLAVES, "rend"]].rename(columns={"rend": "rindio_ultima"})
    v = v.merge(g, on=CLAVES, how="left").merge(ultima, on=CLAVES, how="left")
    promo = v["asignatura"].map({a: 100 * e["cortes"]["Promociona"] / e["total_max"] for a, e in ESQUEMA.items()})
    v["tiene_notas"] = v["tomadas"].fillna(0).gt(0).astype(float)
    v["nota_pct"] = (100 * v["pts"] / v["maximo"]).fillna(0).round(2)
    v["margen_promocion"] = np.where(v["tiene_notas"] > 0, v["nota_pct"] - promo, 0.0).round(2)
    v["pct_rendidos"] = (100 * v["rendidos"] / v["tomadas"]).fillna(0).round(1)
    v["rindio_ultima"] = v["rindio_ultima"].astype("boolean").fillna(False).astype(float)
    return v.drop(columns=["pts", "maximo", "rendidos", "tomadas"])


def _otras_materias(v: pd.DataFrame) -> pd.DataFrame:
    """Lo que hace el mismo alumno en sus otras materias de la base."""
    por_alumno = v.groupby("id_alumno")
    v["materias_en_base"] = por_alumno["asignatura"].transform("size")   # no es variable: solo para los motivos
    v["eventos_14d_otras"] = por_alumno["eventos_14d"].transform("sum") - v["eventos_14d"]
    v["materias_activas_14d"] = por_alumno["eventos_14d"].transform(lambda s: (s > 0).sum()).astype(float)
    v["dias_sin_actividad_global"] = por_alumno["dias_sin_actividad"].transform("min").fillna(v["dias_de_cursada"])
    return v


def _mezcla(v: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    """% de sus interacciones que son de evaluación y de mirar notas (D44)."""
    mezcla = pd.crosstab([ev["asignatura"], ev["id_alumno"]], ev["categoria"], normalize="index")
    mezcla = (100 * mezcla.reindex(columns=[EVALUACION, NOTAS], fill_value=0)).round(1)
    mezcla.columns = ["pct_evaluacion", "pct_notas"]
    v = v.merge(mezcla.reset_index(), on=CLAVES, how="left")
    v[["pct_evaluacion", "pct_notas"]] = v[["pct_evaluacion", "pct_notas"]].fillna(0)
    return v


def _cursando(v: pd.DataFrame) -> pd.Series:
    """Los que vienen entrando: alguna interacción en los últimos 14 días."""
    return v["dias_sin_actividad"].lt(ABANDONO_HORIZONTE_DIAS).fillna(False).astype(bool)


def _con_actividad(v: pd.DataFrame) -> pd.Series:
    """Los que entraron alguna vez hasta la fecha de corte (a ellos se les predice)."""
    return v["eventos_total"].gt(0)


def _estado(v: pd.DataFrame) -> np.ndarray:
    return np.select([_cursando(v), ~_con_actividad(v)], [CURSANDO, SIN_ACTIVIDAD], default=ALEJADO)


def _notas_posteriores(d: m.Datos) -> pd.DataFrame:
    """(asignatura, id_alumno) que rindieron una evaluación que no figura en la trazabilidad
    (su primera realización es posterior al último dato o no existe): siguieron cursando."""
    ins = d.instrumentos
    fin = fin_datos(d) + pd.Timedelta(days=1)
    fuera = ins.loc[ins["fecha_primera_realizacion"].isna() | (ins["fecha_primera_realizacion"] >= fin),
                    "id_instrumento"]
    c = d.calificaciones
    return c.loc[c["id_instrumento"].isin(fuera) & c["rindio"], CLAVES].drop_duplicates()


def _vuelven(d: m.Datos, corte: pd.Timestamp) -> pd.Index:
    """(asignatura, id_alumno) que siguen después del corte: alguna interacción en la materia
    después de ese día o una nota de una evaluación posterior a la trazabilidad (D67)."""
    i = d.interacciones
    i = i.loc[i["en_base"] & (i["fecha_hora"] >= corte + pd.Timedelta(days=1)), CLAVES].drop_duplicates()
    return pd.MultiIndex.from_frame(pd.concat([i, _notas_posteriores(d)]).drop_duplicates())


def desenlace_conocido(d: m.Datos, corte: pd.Timestamp) -> bool:
    """Hay al menos ABANDONO_SEGUIMIENTO_DIAS días de datos después del corte."""
    return corte + pd.Timedelta(days=ABANDONO_SEGUIMIENTO_DIAS) <= fin_datos(d)


def fin_datos(d: m.Datos) -> pd.Timestamp:
    """Último día con interacciones de alumnos de la base."""
    return d.interacciones.loc[d.interacciones["en_base"], "fecha"].max().normalize()


def cortes_entrenamiento(d: m.Datos) -> pd.DatetimeIndex:
    """Fechas de las fotos: cada ABANDONO_PASO_DIAS días desde el día 14 de la
    cursada hasta ABANDONO_SEGUIMIENTO_DIAS días antes del último dato (para
    conocer el desenlace con al menos 4 semanas de seguimiento)."""
    fechas = d.interacciones.loc[d.interacciones["en_base"], "fecha"]
    if fechas.empty:
        return pd.DatetimeIndex([])
    primero = fechas.min().normalize() + pd.Timedelta(days=ABANDONO_HORIZONTE_DIAS)
    ultimo = fin_datos(d) - pd.Timedelta(days=ABANDONO_SEGUIMIENTO_DIAS)
    return pd.date_range(primero, ultimo, freq=f"{ABANDONO_PASO_DIAS}D")


def dataset(d: m.Datos, cortes=None) -> pd.DataFrame:
    """Todas las fotos: una fila por (fecha de corte, materia, alumno que ya entró
    alguna vez), con las VARIABLES y `abandona` (no vuelve a entrar ni rinde nada
    más, D67)."""
    filas = []
    for corte in cortes_entrenamiento(d) if cortes is None else pd.to_datetime(list(cortes)):
        v = variables(d, corte)
        v = v[_con_actividad(v)].copy()
        v["abandona"] = ~pd.MultiIndex.from_frame(v[CLAVES]).isin(_vuelven(d, corte))
        filas.append(v)
    if not filas:
        return pd.DataFrame(columns=["fecha_corte", *CLAVES, *VARIABLES, "abandona"])
    return pd.concat(filas, ignore_index=True)


# ---------------------------------------------------------------------------
# Modelos, umbral y comparación
# ---------------------------------------------------------------------------
def modelos() -> dict:
    """Los tres modelos a comparar. La logística necesita log en los conteos (muy
    asimétricos) y variables estandarizadas; a los de árboles no les hace falta.
    Los árboles van con hojas grandes y poca profundidad: hay pocos alumnos (D64)."""
    columnas = list(VARIABLES)
    prep = ColumnTransformer([("log", FunctionTransformer(np.log1p), CONTEOS)], remainder="passthrough")
    todas = ColumnTransformer([("todas", "passthrough", columnas)])
    return {
        "logistica": Pipeline([("log", prep), ("escala", StandardScaler()),
                               ("modelo", LogisticRegression(max_iter=3000, C=0.5))]),
        "random_forest": Pipeline([("sel", todas),
                                   ("modelo", RandomForestClassifier(
                                       n_estimators=400, min_samples_leaf=20, max_features="sqrt",
                                       n_jobs=-1, random_state=ABANDONO_SEMILLA))]),
        # D65: árboles de profundidad 2 (casi aditivo) y restricciones monótonas, para que el riesgo
        # nunca baje por llevar más días sin entrar ni suba por entrar más. D70: learning_rate 0,02 y
        # hojas de 200 (búsqueda aleatoria con validación por alumno; ver notebooks/02_predictor_abandono).
        "gradient_boosting": Pipeline([("sel", todas),
                                       ("modelo", HistGradientBoostingClassifier(
                                           max_depth=2, learning_rate=0.02, max_iter=200, min_samples_leaf=200,
                                           l2_regularization=1.0, random_state=ABANDONO_SEMILLA,
                                           monotonic_cst=[MONOTONAS.get(c, 0) for c in columnas]))]),
    }


def costo(y, pred, costo_fn: float = ABANDONO_COSTO_FN, costo_fp: float = ABANDONO_COSTO_FP) -> float:
    y, pred = np.asarray(y, bool), np.asarray(pred, bool)
    return float(costo_fn * (y & ~pred).sum() + costo_fp * (~y & pred).sum())


UMBRALES = np.round(np.arange(0.01, 1.0, 0.01), 2)


def tabla_umbral(y, prob, costo_fn: float = ABANDONO_COSTO_FN, costo_fp: float = ABANDONO_COSTO_FP) -> pd.DataFrame:
    """Para cada umbral: costo, alertas (% marcados), precisión y recall."""
    y, prob = np.asarray(y, bool), np.asarray(prob, float)
    filas = []
    for u in UMBRALES:
        pred = prob >= u
        vp = (y & pred).sum()
        filas.append({"umbral": u, "costo": costo(y, pred, costo_fn, costo_fp),
                      "pct_marcados": 100 * pred.mean(),
                      "precision": 100 * vp / pred.sum() if pred.sum() else np.nan,
                      "recall": 100 * vp / y.sum() if y.sum() else np.nan})
    return pd.DataFrame(filas).round(2)


def elegir_umbral(y, prob, costo_fn: float = ABANDONO_COSTO_FN, costo_fp: float = ABANDONO_COSTO_FP) -> float:
    """El umbral de menor costo total (si empatan, el más alto: menos alertas)."""
    t = tabla_umbral(y, prob, costo_fn, costo_fp)
    return float(t.loc[t["costo"] == t["costo"].min(), "umbral"].max())


VALIDACION_TEMPORAL = "validación temporal"


def _corte_temporal(fechas) -> pd.Timestamp:
    """Separa las fotos en el primer 60 % de fechas (para entrenar) y el resto (para evaluar)."""
    u = np.sort(pd.unique(fechas))
    return u[max(int(len(u) * 0.6) - 1, 0)]


def _validacion_temporal(est, X, y, grupos, fechas, cv) -> tuple[np.ndarray, np.ndarray]:
    """Validación por alumno Y por tiempo (D67): en cada partición se entrena con las fotos
    tempranas de unos alumnos y se predicen las fotos tardías de los otros. Es lo que pasa en
    la app: se predice en fechas posteriores a las que el modelo vio."""
    corte = _corte_temporal(fechas)
    temprana = fechas <= corte
    ys, ps = [], []
    for i_ent, i_val in cv.split(X, y, grupos):
        ent, val = i_ent[temprana[i_ent]], i_val[~temprana[i_val]]
        if len(val) == 0 or len(np.unique(y[ent])) < 2:
            continue
        ys.append(y[val])
        ps.append(clone(est).fit(X.iloc[ent], y[ent]).predict_proba(X.iloc[val])[:, 1])
    return np.concatenate(ys), np.concatenate(ps)


def _metricas(y, score, pred, nombre: str, conjunto: str) -> dict:
    y, pred = np.asarray(y, bool), np.asarray(pred, bool)
    vp, fp, fn = (y & pred).sum(), (~y & pred).sum(), (y & ~pred).sum()
    es_prob = nombre != REGLA
    return {"modelo": nombre, "conjunto": conjunto, "filas": len(y), "abandonos": int(y.sum()),
            "auc_roc": round(roc_auc_score(y, score), 3), "auc_pr": round(average_precision_score(y, score), 3),
            "brier": round(brier_score_loss(y, score), 4) if es_prob else np.nan,
            "precision": round(100 * vp / (vp + fp), 1) if vp + fp else np.nan,
            "recall": round(100 * vp / (vp + fn), 1) if vp + fn else np.nan,
            "pct_marcados": round(100 * pred.mean(), 1),
            "costo": costo(y, pred), "costo_por_100": round(100 * costo(y, pred) / len(y), 1)}


@dataclass
class ModeloAbandono:
    """Lo que se guarda con joblib: el modelo elegido ya entrenado con todos
    los datos, su umbral y todo lo que la app muestra para explicarlo."""
    modelo: Pipeline
    clave: str                          # "logistica" o "random_forest"
    umbral: float
    variables: list[str]
    comparacion: pd.DataFrame           # métricas de los 3 en validación cruzada y en prueba
    curva: pd.DataFrame                 # costo, precisión y recall por umbral (modelo elegido, prueba)
    importancia: pd.DataFrame           # importancia por permutación (modelo elegido, prueba)
    resumen: dict = field(default_factory=dict)
    firma: str = ""

    @property
    def nombre(self) -> str:
        return NOMBRES_MODELOS[self.clave]

    def probabilidad(self, v: pd.DataFrame) -> np.ndarray:
        return self.modelo.predict_proba(v[self.variables].astype(float))[:, 1]


def firma(d: m.Datos) -> str:
    """Cambia si cambian los datos con los que se entrena, la versión de scikit-learn
    o la receta del modelo (variables, modelos y sus parámetros, costos): así un cambio
    en el código también obliga a reentrenar el modelo guardado."""
    i = d.interacciones
    receta = repr(("objetivo D67", list(VARIABLES), modelos(), ABANDONO_COSTO_FN, ABANDONO_COSTO_FP,
                   ABANDONO_HORIZONTE_DIAS, ABANDONO_SEGUIMIENTO_DIAS, ABANDONO_PASO_DIAS))
    return (f"{len(i)}|{i['fecha_hora'].max()}|{len(m.base(d))}|sklearn {sklearn.__version__}"
            f"|receta {hashlib.md5(receta.encode()).hexdigest()[:10]}")


def entrenar(d: m.Datos, verbose: bool = False) -> ModeloAbandono:
    """Arma las fotos, compara los modelos con validación por alumno, elige
    umbral y modelo por costo y reentrena el elegido con todos los datos."""
    t0 = time.perf_counter()
    ds = dataset(d)
    if ds.empty or ds["abandona"].nunique() < 2:
        raise ValueError("No hay datos suficientes para entrenar el predictor de abandono "
                         "(hacen falta al menos 4 semanas de trazabilidad).")
    X, y, grupos = ds[list(VARIABLES)].astype(float), ds["abandona"].to_numpy(), ds["id_alumno"].to_numpy()
    # 1. Prueba = 25 % de los alumnos (todas sus fotos y materias).
    entren, prueba = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=ABANDONO_SEMILLA)
                          .split(X, y, grupos))
    Xe, ye, ge, Xp, yp = X.iloc[entren], y[entren], grupos[entren], X.iloc[prueba], y[prueba]
    fe = ds["fecha_corte"].to_numpy()[entren]
    cv = GroupKFold(n_splits=5)
    filas, ajustados, umbrales, prob_prueba = [], {}, {}, {}
    for clave, est in modelos().items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            oof = cross_val_predict(est, Xe, ye, groups=ge, cv=cv, method="predict_proba")[:, 1]
            umbrales[clave] = elegir_umbral(ye, oof)
            yt, pt = _validacion_temporal(est, Xe, ye, ge, fe, cv)
        filas.append(_metricas(ye, oof, oof >= umbrales[clave], NOMBRES_MODELOS[clave], "validación cruzada"))
        filas.append(_metricas(yt, pt, pt >= umbrales[clave], NOMBRES_MODELOS[clave], VALIDACION_TEMPORAL))
        ajustados[clave] = clone(est).fit(Xe, ye)
        prob_prueba[clave] = ajustados[clave].predict_proba(Xp)[:, 1]
        filas.append(_metricas(yp, prob_prueba[clave], prob_prueba[clave] >= umbrales[clave],
                               NOMBRES_MODELOS[clave], "prueba"))
    # La regla no se entrena: "más de 7 días sin entrar". Para el AUC, el puntaje son los días.
    tarde = fe > _corte_temporal(fe)
    for nombre_conj, Xc, yc in [("validación cruzada", Xe, ye), (VALIDACION_TEMPORAL, Xe[tarde], ye[tarde]),
                                ("prueba", Xp, yp)]:
        dias = Xc["dias_sin_actividad"].to_numpy()
        filas.append(_metricas(yc, dias, dias > ABANDONO_REGLA_DIAS, REGLA, nombre_conj))
    comp = pd.DataFrame(filas)
    # 2. Se elige el modelo de menor costo en la validación temporal (D67): la app predice en fechas
    #    posteriores a las fotos con desenlace, y ahí un modelo que extrapola mal (la logística)
    #    se equivoca mucho aunque gane en la validación cruzada común. La prueba solo se informa.
    cv_ = comp[comp["conjunto"].eq(VALIDACION_TEMPORAL) & comp["modelo"].ne(REGLA)]
    clave = {v: k for k, v in NOMBRES_MODELOS.items()}[cv_.sort_values(["costo", "auc_pr"],
                                                                      ascending=[True, False]).iloc[0]["modelo"]]
    comp["elegido"] = comp["modelo"].eq(NOMBRES_MODELOS[clave])
    curva = tabla_umbral(yp, prob_prueba[clave])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        imp = permutation_importance(ajustados[clave], Xp, yp, scoring="average_precision", n_repeats=5,
                                     random_state=ABANDONO_SEMILLA, n_jobs=1)
    importancia = (pd.DataFrame({"variable": list(VARIABLES), "descripcion": list(VARIABLES.values()),
                                 "importancia": imp.importances_mean.round(4),
                                 "desvio": imp.importances_std.round(4)})
                     .sort_values("importancia", ascending=False).reset_index(drop=True))
    if clave == "logistica":   # signo del coeficiente: + = más riesgo
        coef = dict(zip(VARIABLES, ajustados[clave].named_steps["modelo"].coef_[0]))
        importancia["coeficiente"] = importancia["variable"].map(coef).round(3)
    # 3. El elegido se reentrena con todos los alumnos, con el umbral de la validación cruzada.
    final = clone(modelos()[clave]).fit(X, y)
    resumen = {"fotos": len(cortes_entrenamiento(d)), "filas": len(ds), "alumnos": int(ds["id_alumno"].nunique()),
               "alumnos_prueba": int(pd.Series(grupos[prueba]).nunique()),
               "tasa_abandono": round(100 * float(y.mean()), 1),
               "primera_foto": ds["fecha_corte"].min(), "ultima_foto": ds["fecha_corte"].max(),
               "datos_hasta": fin_datos(d), "costo_fn": ABANDONO_COSTO_FN, "costo_fp": ABANDONO_COSTO_FP,
               "regla_dias": ABANDONO_REGLA_DIAS, "horizonte_dias": ABANDONO_HORIZONTE_DIAS,
               "seguimiento_dias": ABANDONO_SEGUIMIENTO_DIAS,
               "segundos": round(time.perf_counter() - t0, 1), "entrenado": pd.Timestamp.now().floor("s")}
    if verbose:
        print(f"Predictor de abandono: {resumen['filas']} filas, {resumen['alumnos']} alumnos, "
              f"{resumen['tasa_abandono']} % abandona; elegido {NOMBRES_MODELOS[clave]} "
              f"(umbral {umbrales[clave]}), {resumen['segundos']} s")
    return ModeloAbandono(modelo=final, clave=clave, umbral=umbrales[clave], variables=list(VARIABLES),
                          comparacion=comp, curva=curva, importancia=importancia, resumen=resumen, firma=firma(d))


def ruta_modelo(gold: Path = GOLD) -> Path:
    return Path(gold) / ABANDONO_ARCHIVO


def cargar_modelo(d: m.Datos, ruta: Path | None = None, reentrenar: bool = False) -> ModeloAbandono:
    """Lee el modelo guardado con joblib. Si no existe, si los datos cambiaron
    (otra firma) o si `reentrenar`, lo entrena y lo guarda."""
    ruta = Path(ruta) if ruta is not None else ruta_modelo()
    if ruta.exists() and not reentrenar:
        try:
            mod = joblib.load(ruta)
            if isinstance(mod, ModeloAbandono) and mod.firma == firma(d):
                return mod
        except Exception:  # noqa: BLE001 - archivo viejo o de otra versión: se reentrena
            pass
    mod = entrenar(d)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(mod, ruta, compress=3)
    except OSError:   # disco de solo lectura: se usa igual, sin guardar
        pass
    return mod


# ---------------------------------------------------------------------------
# Predicción a una fecha de corte (lo que muestran los dashboards)
# ---------------------------------------------------------------------------
def _motivos(v: pd.DataFrame) -> pd.Series:
    """Señales que se ven en los datos, en palabras, para que el tutor sepa por qué."""
    reglas = [
        (v["dias_sin_actividad"] > ABANDONO_REGLA_DIAS, lambda r: f"{r.dias_sin_actividad:.0f} días sin entrar"),
        ((v["eventos_14d_previos"] > 0) & (v["eventos_14d"] < 0.5 * v["eventos_14d_previos"]),
         lambda r: f"su actividad bajó de {r.eventos_14d_previos:.0f} a {r.eventos_14d:.0f} interacciones "
                   "(últimas 2 semanas contra las 2 anteriores)"),
        (v["dias_activos_14d"] <= 2, lambda r: f"entró solo {r.dias_activos_14d:.0f} día(s) en las últimas 2 semanas"),
        ((v["evaluaciones_14d"] == 0) & (v["dias_de_cursada"] >= 14), lambda r: "no hizo evaluaciones en las últimas 2 semanas"),
        (v["pct_semanas_activas"] < 50, lambda r: f"entró en el {r.pct_semanas_activas:.0f} % de las semanas"),
        (v["dias_sin_actividad"] > v["pausa_habitual"] + 1,
         lambda r: f"lleva más días sin entrar que su pausa habitual ({r.pausa_habitual:.0f})"),
        ((v["tiene_notas"] > 0) & (v["rindio_ultima"] == 0), lambda r: "no rindió la última evaluación"),
        ((v["tiene_notas"] > 0) & (v["margen_promocion"] < -25), lambda r: f"nota a la fecha baja ({r.nota_pct:.0f} sobre 100)"),
        ((v["materias_en_base"] > 1) & (v["dias_sin_actividad_global"] >= v["dias_sin_actividad"])
         & (v["dias_sin_actividad"] > ABANDONO_REGLA_DIAS), lambda r: "tampoco entra a sus otras materias"),
    ]
    textos = pd.Series([[] for _ in range(len(v))], index=v.index, dtype=object)
    for mascara, texto in reglas:
        for i, r in zip(v.index[mascara], v[mascara].itertuples()):
            textos[i].append(texto(r))
    return textos.map(lambda t: "; ".join(t).capitalize() if t else "")


def riesgo_abandono(d: m.Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                    modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    """Una fila por alumno de la base, a la fecha de corte:
      estado_abandono   Cursando (entró en los últimos 14 días) / Alejado (entró, pero
                        hace 14 días o más que no) / Sin actividad (nunca entró)
      probabilidad      de abandonar la materia: no volver a entrar ni rendir nada más
                        (Cursando y Alejado), en %
      nivel_riesgo      Alto (>= umbral del modelo) / Medio (>= la mitad del umbral) /
                        Bajo; Sin actividad para quien nunca entró
      regla_simple      más de `umbral` días sin entrar (la regla contra la que se compara)
      motivos           las señales de los datos, en palabras
      abandono_real     si ya se sabe (fecha de corte + 28 días <= último dato): si de
                        verdad no volvió a entrar ni rindió nada más"""
    mod = modelo or cargar_modelo(d)
    corte = m.fecha_de_corte(fecha_corte)
    v = variables(d, corte)
    activos = _con_actividad(v)
    v["estado_abandono"] = _estado(v)
    v["probabilidad"] = np.nan
    if activos.any():
        v.loc[activos, "probabilidad"] = (100 * mod.probabilidad(v[activos])).round(1)
    u = 100 * mod.umbral
    v["nivel_riesgo"] = np.select([~activos, v["probabilidad"] >= u, v["probabilidad"] >= u / 2],
                                  [SIN_ACTIVIDAD, ALTO, MEDIO], default=BAJO)
    v["regla_simple"] = v["dias_sin_actividad"].gt(umbral).fillna(False).astype(bool) & activos
    v["motivos"] = ""
    v.loc[activos, "motivos"] = _motivos(v[activos])
    v["abandono_real"] = pd.Series(pd.NA, index=v.index, dtype="boolean")
    if desenlace_conocido(d, corte):
        vuelve = pd.MultiIndex.from_frame(v[CLAVES]).isin(_vuelven(d, corte))
        v.loc[activos, "abandono_real"] = ~vuelve[activos.to_numpy()]
    nombres = d.alumnos[["id_alumno", "nombre_completo"]]
    ins = m.base(d)[[*CLAVES, "inscripto"]]
    v = v.merge(nombres, on="id_alumno", how="left").merge(ins, on=CLAVES, how="left")
    columnas = [*CLAVES, "nombre_completo", "inscripto", "fecha_corte", "estado_abandono", "probabilidad",
                "nivel_riesgo", "regla_simple", "motivos", "abandono_real", *VARIABLES, "eventos_14d_previos"]
    # Evaluaciones posteriores a la última foto con desenlace: la pausa que suele venir
    # después todavía no la vio el modelo, así que puede sobrestimar el riesgo (D64).
    # Solo para quien entró por última vez a rendir una evaluación posterior a esa foto.
    ultima_foto = mod.resumen.get("ultima_foto", corte)
    real = _realizaciones(d)
    real = real[(real["rindio_el"] >= ultima_foto + pd.Timedelta(days=1)) & (real["rindio_el"] < m._fin_del_dia(corte))]
    real = (real.sort_values("rindio_el").groupby(CLAVES).tail(1)
                .merge(d.instrumentos[["id_instrumento", "instrumento"]], on="id_instrumento"))
    v = v.merge(real[[*CLAVES, "rindio_el", "instrumento"]], on=CLAVES, how="left")
    pausa = v["estado_abandono"].ne(SIN_ACTIVIDAD) & (v["ultima"].dt.normalize() <= v["rindio_el"].dt.normalize()
                                                 + pd.Timedelta(days=1))
    v["advertencia"] = ""
    v.loc[pausa, "advertencia"] = [
        f"Su último ingreso fue para rendir «{html.unescape(str(r.instrumento)).strip()}» el {r.rindio_el:%d/%m}. "
        "Después de una evaluación es normal una pausa, y el modelo (entrenado con fotos hasta el "
        f"{ultima_foto:%d/%m}) todavía no vio cómo siguen esas pausas: puede exagerar el riesgo."
        for r in v[pausa].itertuples()]
    columnas.append("advertencia")
    v = m._filtrar(v[columnas], asignatura)
    v["_orden"] = v["nivel_riesgo"].map({n: i for i, n in enumerate(NIVELES)})
    v = v.sort_values(["asignatura", "_orden", "probabilidad"], ascending=[True, True, False])
    v = v.drop(columns="_orden").reset_index(drop=True)
    avisos = []
    if v["dias_de_cursada"].max() < ABANDONO_HORIZONTE_DIAS:
        avisos.append("La fecha de corte es anterior al día 14 de la cursada: el modelo se entrenó desde ese "
                      "día, así que la predicción es poco confiable.")
    en_pausa = v["advertencia"].ne("") & v["nivel_riesgo"].eq(ALTO)
    if en_pausa.any():
        materias = ", ".join(f"{n} de {a}" for a, n in v[en_pausa].groupby("asignatura").size().items())
        avisos.append(f"{en_pausa.sum()} de los alumnos en riesgo alto ({materias}) entraron por última vez a rendir "
                      f"una evaluación posterior al {ultima_foto:%d/%m}, la última foto con desenlace conocido. "
                      "Después de una evaluación es normal una pausa y el modelo todavía no vio cómo siguen esas "
                      "pausas, así que en ellos puede exagerar el riesgo.")
    v.attrs.update(umbral=u, modelo=mod.nombre, aviso=" ".join(avisos))
    return v


def resumen_riesgo(d: m.Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                   modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    """Una fila por materia: cuántos hay en cada nivel y, si ya se sabe qué pasó
    después, cuántos de los marcados en riesgo alto abandonaron de verdad."""
    r = riesgo_abandono(d, fecha_corte, asignatura, umbral, modelo)
    g = r.groupby("asignatura")
    res = pd.DataFrame({"base": g.size(), "cursando": g["estado_abandono"].apply(lambda s: s.eq(CURSANDO).sum()),
                        "alejados": g["estado_abandono"].apply(lambda s: s.eq(ALEJADO).sum())})
    res["con_actividad"] = res["cursando"] + res["alejados"]
    for nivel, col in [(ALTO, "riesgo_alto"), (MEDIO, "riesgo_medio"), (BAJO, "riesgo_bajo"),
                       (SIN_ACTIVIDAD, "sin_actividad")]:
        res[col] = g["nivel_riesgo"].apply(lambda s, n=nivel: s.eq(n).sum())
    res["pct_riesgo_alto"] = (100 * res["riesgo_alto"] / res["con_actividad"].replace(0, np.nan)).round(1)
    res["regla_simple"] = g["regla_simple"].sum()
    res["probabilidad_promedio"] = g["probabilidad"].mean().round(1)
    conocido = r[r["abandono_real"].notna()]
    if not conocido.empty:
        gc = conocido.groupby("asignatura")
        res["abandonaron_despues"] = gc["abandono_real"].sum().astype(int)
        res["aciertos_alto"] = gc.apply(lambda x: (x["nivel_riesgo"].eq(ALTO) & x["abandono_real"]).sum())
    return res.reset_index()


def riesgo_alumno(d: m.Datos, id_alumno: str, fecha_corte=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                  modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    """El riesgo de un alumno en cada materia de su base (para la Ficha individual)."""
    r = riesgo_abandono(d, fecha_corte, None, umbral, modelo)
    return r[r["id_alumno"] == id_alumno].reset_index(drop=True)


def evolucion_riesgo(d: m.Datos, id_alumno: str, fecha_corte=None,
                     modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    """La probabilidad de abandonar de cada materia del alumno, semana a semana, desde
    el día 14 de la cursada hasta la fecha de corte (cada punto usa solo lo que se sabía ese día)."""
    mod = modelo or cargar_modelo(d)
    corte = m.fecha_de_corte(fecha_corte)
    fechas = d.interacciones.loc[d.interacciones["en_base"], "fecha"]
    if fechas.empty:
        return pd.DataFrame(columns=["fecha_corte", "asignatura", "estado_abandono", "probabilidad"])
    inicio = fechas.min().normalize() + pd.Timedelta(days=ABANDONO_HORIZONTE_DIAS)
    puntos = [*pd.date_range(inicio, corte, freq="7D"), corte] if corte >= inicio else [corte]
    filas = []
    for c in sorted(set(puntos)):
        v = variables(d, c)
        v = v[v["id_alumno"] == id_alumno].copy()
        activos = _con_actividad(v)
        v["estado_abandono"] = _estado(v)
        v["probabilidad"] = np.nan
        if activos.any():
            v.loc[activos, "probabilidad"] = (100 * mod.probabilidad(v[activos])).round(1)
        filas.append(v[["fecha_corte", "asignatura", "estado_abandono", "probabilidad", "dias_sin_actividad"]])
    return pd.concat(filas, ignore_index=True)


# --- Lo que se guardó al entrenar, para la página del modelo -----------------
def comparacion_modelos(d: m.Datos, modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    return (modelo or cargar_modelo(d)).comparacion


def curva_umbral(d: m.Datos, modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    return (modelo or cargar_modelo(d)).curva


def importancia_variables(d: m.Datos, modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    return (modelo or cargar_modelo(d)).importancia


def info_modelo(d: m.Datos, modelo: ModeloAbandono | None = None) -> dict:
    mod = modelo or cargar_modelo(d)
    return {"nombre": mod.nombre, "clave": mod.clave, "umbral": mod.umbral, **mod.resumen}


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    datos = m.cargar()
    mod = cargar_modelo(datos, reentrenar=True)
    print(f"Elegido: {mod.nombre} · umbral {mod.umbral} · {mod.resumen}\n")
    print(mod.comparacion.drop(columns="elegido").to_string(index=False), "\n")
    print(mod.importancia.to_string(index=False), "\n")
    print(resumen_riesgo(datos, modelo=mod).to_string(index=False))
    print(resumen_riesgo(datos, "2025-09-20", modelo=mod).to_string(index=False))
