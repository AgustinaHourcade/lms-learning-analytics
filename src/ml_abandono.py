"""
ETAPA 7 - ML: predictor de abandono (D58). Va en la Ficha individual y en
Matrícula y alertas.

Pregunta: de los alumnos que vienen entrando al aula, ¿quiénes van a dejar de
entrar en las próximas 2 semanas?

  * Objetivo: a una fecha de corte c, un alumno de la base que tuvo actividad
    en los últimos 14 días (ABANDONO_HORIZONTE_DIAS) "abandona" si NO tiene
    ninguna interacción en los 14 días siguientes (c, c + 14]. Quien ya lleva
    14 días o más sin entrar ya cumple la definición ("Ya abandonó") y quien
    nunca entró queda "Sin actividad" (D35): no hace falta predecir nada.
  * Datos de entrenamiento: "fotos" de la cursada cada 3 días
    (ABANDONO_PASO_DIAS), desde el día 14 hasta 14 días antes del último dato,
    para saber qué pasó después. Un mismo alumno aparece en varias fotos.
  * Variables: solo la actividad hasta la fecha de la foto (trazabilidad), sin
    nada del futuro: días sin entrar, interacciones y sesiones de las últimas
    1 y 2 semanas, tendencia contra las 2 semanas anteriores, evaluaciones
    hechas, % de semanas con actividad, etc. (VARIABLES). No se usan las notas:
    son una foto al 24/10 y "filtrarían" el futuro (D34).
  * Modelos: regresión logística y Random Forest, comparados contra la regla
    simple "más de 7 días sin entrar" (ABANDONO_REGLA_DIAS).
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from src import metricas as m
from src.config import (ABANDONO_ARCHIVO, ABANDONO_COSTO_FN, ABANDONO_COSTO_FP, ABANDONO_HORIZONTE_DIAS,
                        ABANDONO_PASO_DIAS, ABANDONO_REGLA_DIAS, ABANDONO_SEMILLA, GOLD,
                        UMBRAL_INACTIVIDAD_DIAS)

CLAVES = ["asignatura", "id_alumno"]
EVALUACION = "Evaluación"   # categoría de dim_accion (D44)

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
}
CONTEOS = ["eventos_7d", "eventos_14d", "sesiones_14d", "minutos_14d", "evaluaciones_14d", "eventos_total"]

# Estados de cada alumno a la fecha de corte y niveles de riesgo.
CURSANDO, YA_ABANDONO, SIN_ACTIVIDAD = "Cursando", "Ya abandonó", m.SIN_ACTIVIDAD
ALTO, MEDIO, BAJO = "Alto", "Medio", "Bajo"
NIVELES = [ALTO, MEDIO, BAJO, YA_ABANDONO, SIN_ACTIVIDAD]
REGLA = "Regla simple"
NOMBRES_MODELOS = {"logistica": "Regresión logística", "random_forest": "Random Forest", "regla": REGLA}


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
                                     **{c: 0.0 for c in VARIABLES})
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
    v.insert(2, "fecha_corte", corte)
    return v


def _cursando(v: pd.DataFrame) -> pd.Series:
    """Los que vienen entrando: alguna interacción en los últimos 14 días."""
    return v["dias_sin_actividad"].lt(ABANDONO_HORIZONTE_DIAS).fillna(False).astype(bool)


def _entran_despues(d: m.Datos, corte: pd.Timestamp) -> pd.Index:
    """(asignatura, id_alumno) con alguna interacción en (corte, corte + 14 días]."""
    i = d.interacciones
    hasta = corte + pd.Timedelta(days=ABANDONO_HORIZONTE_DIAS + 1)
    i = i[i["en_base"] & (i["fecha_hora"] >= corte + pd.Timedelta(days=1)) & (i["fecha_hora"] < hasta)]
    return pd.MultiIndex.from_frame(i[CLAVES].drop_duplicates())


def fin_datos(d: m.Datos) -> pd.Timestamp:
    """Último día con interacciones de alumnos de la base."""
    return d.interacciones.loc[d.interacciones["en_base"], "fecha"].max().normalize()


def cortes_entrenamiento(d: m.Datos) -> pd.DatetimeIndex:
    """Fechas de las fotos: cada ABANDONO_PASO_DIAS días desde el día 14 de la
    cursada hasta 14 días antes del último dato (para conocer el desenlace)."""
    fechas = d.interacciones.loc[d.interacciones["en_base"], "fecha"]
    if fechas.empty:
        return pd.DatetimeIndex([])
    primero = fechas.min().normalize() + pd.Timedelta(days=ABANDONO_HORIZONTE_DIAS)
    ultimo = fin_datos(d) - pd.Timedelta(days=ABANDONO_HORIZONTE_DIAS)
    return pd.date_range(primero, ultimo, freq=f"{ABANDONO_PASO_DIAS}D")


def dataset(d: m.Datos, cortes=None) -> pd.DataFrame:
    """Todas las fotos: una fila por (fecha de corte, materia, alumno que viene
    entrando), con las VARIABLES y `abandona` (no entra en los 14 días siguientes)."""
    filas = []
    for corte in cortes_entrenamiento(d) if cortes is None else pd.to_datetime(list(cortes)):
        v = variables(d, corte)
        v = v[_cursando(v)].copy()
        v["abandona"] = ~pd.MultiIndex.from_frame(v[CLAVES]).isin(_entran_despues(d, corte))
        filas.append(v)
    if not filas:
        return pd.DataFrame(columns=["fecha_corte", *CLAVES, *VARIABLES, "abandona"])
    return pd.concat(filas, ignore_index=True)


# ---------------------------------------------------------------------------
# Modelos, umbral y comparación
# ---------------------------------------------------------------------------
def modelos() -> dict:
    """Los dos modelos a comparar. La logística necesita log en los conteos (muy
    asimétricos) y variables estandarizadas; al Random Forest no le hace falta."""
    columnas = list(VARIABLES)
    prep = ColumnTransformer([("log", FunctionTransformer(np.log1p), CONTEOS)], remainder="passthrough")
    return {
        "logistica": Pipeline([("log", prep), ("escala", StandardScaler()),
                               ("modelo", LogisticRegression(max_iter=2000))]),
        "random_forest": Pipeline([("sel", ColumnTransformer([("todas", "passthrough", columnas)])),
                                   ("modelo", RandomForestClassifier(
                                       n_estimators=300, min_samples_leaf=20, max_features="sqrt",
                                       n_jobs=-1, random_state=ABANDONO_SEMILLA))]),
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
    """Cambia si cambian los datos con los que se entrena (o la versión de scikit-learn)."""
    i = d.interacciones
    return f"{len(i)}|{i['fecha_hora'].max()}|{len(m.base(d))}|sklearn {sklearn.__version__}"


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
    cv = GroupKFold(n_splits=5)
    filas, ajustados, umbrales, prob_prueba = [], {}, {}, {}
    for clave, est in modelos().items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            oof = cross_val_predict(est, Xe, ye, groups=ge, cv=cv, method="predict_proba")[:, 1]
        umbrales[clave] = elegir_umbral(ye, oof)
        filas.append(_metricas(ye, oof, oof >= umbrales[clave], NOMBRES_MODELOS[clave], "validación cruzada"))
        ajustados[clave] = clone(est).fit(Xe, ye)
        prob_prueba[clave] = ajustados[clave].predict_proba(Xp)[:, 1]
        filas.append(_metricas(yp, prob_prueba[clave], prob_prueba[clave] >= umbrales[clave],
                               NOMBRES_MODELOS[clave], "prueba"))
    # La regla no se entrena: "más de 7 días sin entrar". Para el AUC, el puntaje son los días.
    for nombre_conj, Xc, yc in [("validación cruzada", Xe, ye), ("prueba", Xp, yp)]:
        dias = Xc["dias_sin_actividad"].to_numpy()
        filas.append(_metricas(yc, dias, dias > ABANDONO_REGLA_DIAS, REGLA, nombre_conj))
    comp = pd.DataFrame(filas)
    # 2. Se elige el modelo de menor costo en validación cruzada (la prueba solo se informa).
    cv_ = comp[comp["conjunto"].eq("validación cruzada") & comp["modelo"].ne(REGLA)]
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
    ]
    textos = pd.Series([[] for _ in range(len(v))], index=v.index, dtype=object)
    for mascara, texto in reglas:
        for i, r in zip(v.index[mascara], v[mascara].itertuples()):
            textos[i].append(texto(r))
    return textos.map(lambda t: "; ".join(t).capitalize() if t else "")


def riesgo_abandono(d: m.Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                    modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    """Una fila por alumno de la base, a la fecha de corte:
      estado_abandono   Cursando (entró en los últimos 14 días) / Ya abandonó
                        (14 días o más sin entrar) / Sin actividad (nunca entró)
      probabilidad      de no entrar en los próximos 14 días (solo Cursando), en %
      nivel_riesgo      Alto (>= umbral del modelo) / Medio (>= la mitad del umbral) /
                        Bajo; para el resto, su estado
      regla_simple      más de `umbral` días sin entrar (la regla contra la que se compara)
      motivos           las señales de los datos, en palabras
      abandono_real     si ya se sabe (fecha de corte + 14 días <= último dato):
                        si de verdad no entró en los 14 días siguientes"""
    mod = modelo or cargar_modelo(d)
    corte = m.fecha_de_corte(fecha_corte)
    v = variables(d, corte)
    cursando = _cursando(v)
    v["estado_abandono"] = np.select([cursando, v["eventos_total"].eq(0)], [CURSANDO, SIN_ACTIVIDAD],
                                     default=YA_ABANDONO)
    v["probabilidad"] = np.nan
    if cursando.any():
        v.loc[cursando, "probabilidad"] = (100 * mod.probabilidad(v[cursando])).round(1)
    u = 100 * mod.umbral
    v["nivel_riesgo"] = np.select([~cursando, v["probabilidad"] >= u, v["probabilidad"] >= u / 2],
                                  [v["estado_abandono"], ALTO, MEDIO], default=BAJO)
    v["regla_simple"] = v["dias_sin_actividad"].gt(umbral).fillna(False).astype(bool) & cursando
    v["motivos"] = ""
    v.loc[cursando, "motivos"] = _motivos(v[cursando])
    v["abandono_real"] = pd.Series(pd.NA, index=v.index, dtype="boolean")
    if corte + pd.Timedelta(days=ABANDONO_HORIZONTE_DIAS) <= fin_datos(d):
        despues = pd.MultiIndex.from_frame(v[CLAVES]).isin(_entran_despues(d, corte))
        v.loc[cursando, "abandono_real"] = ~despues[cursando.to_numpy()]
    nombres = d.alumnos[["id_alumno", "nombre_completo"]]
    ins = m.base(d)[[*CLAVES, "inscripto"]]
    v = v.merge(nombres, on="id_alumno", how="left").merge(ins, on=CLAVES, how="left")
    columnas = [*CLAVES, "nombre_completo", "inscripto", "fecha_corte", "estado_abandono", "probabilidad",
                "nivel_riesgo", "regla_simple", "motivos", "abandono_real", *VARIABLES, "eventos_14d_previos"]
    v = m._filtrar(v[columnas], asignatura)
    v["_orden"] = v["nivel_riesgo"].map({n: i for i, n in enumerate(NIVELES)})
    v = v.sort_values(["asignatura", "_orden", "probabilidad"], ascending=[True, True, False])
    v = v.drop(columns="_orden").reset_index(drop=True)
    v.attrs.update(umbral=u, modelo=mod.nombre,
                   aviso=("La fecha de corte es anterior al día 14 de la cursada: el modelo se entrenó desde ese "
                          "día, así que la predicción es poco confiable." if v["dias_de_cursada"].max() < ABANDONO_HORIZONTE_DIAS
                          else ""))
    return v


def resumen_riesgo(d: m.Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                   modelo: ModeloAbandono | None = None) -> pd.DataFrame:
    """Una fila por materia: cuántos hay en cada nivel y, si ya se sabe qué pasó
    después, cuántos de los marcados en riesgo alto abandonaron de verdad."""
    r = riesgo_abandono(d, fecha_corte, asignatura, umbral, modelo)
    g = r.groupby("asignatura")
    res = pd.DataFrame({"base": g.size(), "cursando": g["estado_abandono"].apply(lambda s: s.eq(CURSANDO).sum())})
    for nivel, col in [(ALTO, "riesgo_alto"), (MEDIO, "riesgo_medio"), (BAJO, "riesgo_bajo"),
                       (YA_ABANDONO, "ya_abandonaron"), (SIN_ACTIVIDAD, "sin_actividad")]:
        res[col] = g["nivel_riesgo"].apply(lambda s, n=nivel: s.eq(n).sum())
    res["pct_riesgo_alto"] = (100 * res["riesgo_alto"] / res["cursando"].replace(0, np.nan)).round(1)
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
    """La probabilidad del alumno en cada materia, semana a semana, desde el día
    14 de la cursada hasta la fecha de corte (cada punto usa solo lo que se sabía ese día)."""
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
        cursando = _cursando(v)
        v["estado_abandono"] = np.select([cursando, v["eventos_total"].eq(0)], [CURSANDO, SIN_ACTIVIDAD],
                                         default=YA_ABANDONO)
        v["probabilidad"] = np.nan
        if cursando.any():
            v.loc[cursando, "probabilidad"] = (100 * mod.probabilidad(v[cursando])).round(1)
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
