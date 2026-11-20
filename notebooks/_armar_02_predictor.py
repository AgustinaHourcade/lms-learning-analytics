"""Arma y ejecuta notebooks/02_predictor_abandono.ipynb.

Uso (desde la raíz):  python notebooks/_armar_02_predictor.py
El notebook queda ejecutado (con salidas). Para cambiarlo, se edita este archivo y se vuelve a correr.
Tarda unos minutos (validación cruzada de 9 modelos y una búsqueda de hiperparámetros).
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "notebooks" / "02_predictor_abandono.ipynb"
celdas = []
md = lambda t: celdas.append(nbf.v4.new_markdown_cell(t.strip()))
py = lambda t: celdas.append(nbf.v4.new_code_cell(t.strip()))

md("""
# 2 · Predictor de abandono de la materia

**Pregunta de negocio:** a una fecha dada, ¿qué alumnos que ya entraron al aula van a **abandonar la materia**?
Abandonar = no vuelve a entrar ni rinde nada más hasta el último dato (D67). La idea es avisarle al docente a tiempo
para contactarlos.

El notebook sigue las etapas de un proyecto de ML real (material de la materia):

1. Problema, objetivo y por qué no alcanza con "dejó de entrar dos semanas".
2. Dataset: cómo se arman los casos, desbalance de clases.
3. Calidad de las variables: nulos, distribuciones, correlaciones y **prueba de fuga de información**.
4. Particiones: prueba (hold-out) por alumno, validación cruzada por grupos y **validación temporal**.
5. Líneas de base: clasificador trivial y la regla "más de 7 días sin entrar".
6. Comparación de 9 modelos (árbol, KNN, SVM, red neuronal, logística, random forest, gradient boosting…) con
   puntaje de entrenamiento vs. validación (sobreajuste).
7. Ajuste de hiperparámetros (búsqueda aleatoria).
8. Umbral de decisión por costo.
9. Evaluación final en prueba: matriz de confusión, precisión / recall / F1, curvas ROC y PR, calibración.
10. Interpretación y controles: importancia, dependencia parcial, etiquetas mezcladas, errores por segmento.
11. Robustez con cursadas sintéticas.

Todo el código que usa la app está en **`src/ml_abandono.py`** (y las cursadas sintéticas en `src/simulacion.py`);
acá se lo llama y se lo analiza.
""")
py("""
import os, time, warnings
from pathlib import Path
if not Path("src").exists():          # el notebook está en notebooks/: subo a la raíz
    os.chdir("..")
warnings.simplefilter("ignore")

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from sklearn.base import clone
from sklearn.calibration import calibration_curve
from sklearn.dummy import DummyClassifier
from sklearn.inspection import partial_dependence
from sklearn.metrics import (average_precision_score, classification_report, confusion_matrix,
                             precision_recall_curve, roc_auc_score, roc_curve)
from sklearn.model_selection import (GroupKFold, GroupShuffleSplit, RandomizedSearchCV,
                                     cross_val_predict, cross_validate)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

from src import metricas as m, ml_abandono as ab, simulacion
from src.config import (ABANDONO_COSTO_FN, ABANDONO_COSTO_FP, ABANDONO_REGLA_DIAS, ABANDONO_SEGUIMIENTO_DIAS,
                        ABANDONO_SEMILLA)

pio.renderers.default = "notebook_connected"
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
d = m.cargar()
V = list(ab.VARIABLES)
""")

# ---------------------------------------------------------------------------
md("""
## 1. Problema y objetivo

Una primera versión predecía "deja de entrar 14 días". Pero dejar de entrar dos semanas **no es abandonar**: muchos
vuelven (por ejemplo, después de un parcial). Para cada foto de la cursada se mide, entre quienes llevan *k* días sin
entrar, cuántos vuelven a entrar o a rendir algo más adelante:
""")
py("""
ds = ab.dataset(d)
ds["vuelve"] = ~ds["abandona"]
tramos = pd.cut(ds["dias_sin_actividad"], [-1, 3, 7, 14, 21, 28, 100],
                labels=["0-3", "4-7", "8-14", "15-21", "22-28", "29+"])
vuelta = ds.groupby(tramos, observed=True).agg(casos=("vuelve", "size"), vuelven_pct=("vuelve", "mean"))
vuelta["vuelven_pct"] = (100 * vuelta["vuelven_pct"]).round(1)
vuelta
""")
md("""
Con 8 a 14 días sin entrar, la gran mayoría todavía vuelve: marcar "abandono" por un hueco de dos semanas genera
muchas falsas alarmas. Por eso el objetivo es el **desenlace final** (D67):

* **abandona = 1** si después de la foto el alumno no tiene ninguna interacción en la materia hasta el último dato y
  tampoco aparece una nota de algo que no figure en la trazabilidad.
* Solo se usan fotos con al menos **28 días de seguimiento** posteriores (si no, no se sabe el desenlace).
""")

# ---------------------------------------------------------------------------
md("""
## 2. Dataset

Cada fila es una "foto": (materia, alumno, fecha de corte) con las variables calculadas **solo con lo que se sabía
hasta esa fecha**. Se toman fotos cada 3 días desde el día 14 de la cursada hasta 28 días antes del último dato, y
entran los alumnos que ya habían entrado al aula.
""")
py("""
fin = ab.fin_datos(d)
print(f"Datos hasta {fin.date()}; fotos del {ds.fecha_corte.min().date()} al {ds.fecha_corte.max().date()} "
      f"({ds.fecha_corte.nunique()} fotos)")
print(f"{len(ds):,} casos, {ds.id_alumno.nunique()} alumnos, {len(V)} variables; "
      f"abandona = {100 * ds.abandona.mean():.1f} %")
por_foto = ds.groupby("fecha_corte").agg(casos=("abandona", "size"), abandona_pct=("abandona", "mean"))
por_foto["abandona_pct"] = (100 * por_foto["abandona_pct"]).round(1)
px.bar(por_foto.reset_index(), x="fecha_corte", y="abandona_pct", text="casos",
       title="% que abandona según la fecha de la foto (texto: casos)").show()
ds.groupby("asignatura")["abandona"].agg(["size", "mean"]).rename(columns={"size": "casos", "mean": "tasa"}).round(3)
""")
md("""
**Desbalance:** ~1 de cada 10 casos es abandono. Por eso:

* la *accuracy* no sirve (un modelo que nunca avisa acierta el 90 %);
* se miran **AUC-PR**, precisión y recall;
* el umbral no es 0,5 sino el que minimiza un **costo**: perder a alguien que abandona (FN) cuesta
  5 veces más que avisar de más (FP).

Además, el mismo alumno aparece en varias fotos y materias: los casos **no son independientes**, y eso define cómo
se valida (sección 4).
""")

# ---------------------------------------------------------------------------
md("""
## 3. Calidad de las variables

### 3.1 Descripción, nulos y distribuciones
""")
py("""
desc = ds[V].astype(float).describe().T[["mean", "std", "min", "50%", "max"]]
desc.insert(0, "nulos_pct", (100 * ds[V].isna().mean()).round(1))
desc.insert(0, "descripcion", pd.Series(ab.VARIABLES))
desc.round(2)
""")
md("""
Los conteos (eventos, sesiones, minutos) son muy asimétricos: la logística, KNN, SVM y la red neuronal los reciben
con `log1p` y estandarizados (dentro del `Pipeline`, así la transformación se ajusta solo con los datos de
entrenamiento de cada partición). Los árboles no lo necesitan.

### 3.2 ¿Qué variables separan a quienes abandonan?
""")
py("""
sep = []
for c in V:
    x = ds[c].astype(float)
    ok = x.notna()
    auc = roc_auc_score(ds.loc[ok, "abandona"], x[ok]) if x[ok].nunique() > 1 else np.nan
    sep.append({"variable": c, "auc_sola": round(max(auc, 1 - auc), 3), "sentido": "+" if auc >= 0.5 else "-",
                "media_sigue": round(x[~ds.abandona].mean(), 2), "media_abandona": round(x[ds.abandona].mean(), 2)})
sep = pd.DataFrame(sep).sort_values("auc_sola", ascending=False)
sep.head(12)
""")
py("""
for c in ["dias_sin_actividad", "sin_vs_habitual", "eventos_14d", "pct_rendidos"]:
    px.box(ds, x="abandona", y=c, points=False, title=c, height=300).show()
""")
md("""
### 3.3 Correlación entre variables

Variables muy correlacionadas no rompen a los árboles, pero vuelven inestables los coeficientes de la logística y
reparten la importancia entre ellas.
""")
py("""
corr = ds[V].astype(float).corr(method="spearman")
px.imshow(corr, color_continuous_scale="RdBu_r", zmin=-1, zmax=1, title="Correlación de Spearman entre variables",
          height=750).show()
pares = (corr.where(np.triu(np.ones(corr.shape, bool), 1)).stack().rename("rho").reset_index()
             .assign(abs=lambda t: t.rho.abs()).sort_values("abs", ascending=False))
pares[pares["abs"] > 0.8].drop(columns="abs").round(2)
""")
md("""
### 3.4 Prueba de fuga de información (*data leakage*)

Si alguna variable usara datos posteriores a la fecha de corte, el modelo se vería mejor de lo que es. Se calculan
las variables con todos los datos y con los datos **cortados** en la fecha de la foto: tienen que dar igual.
""")
py("""
import dataclasses
for corte in pd.to_datetime(["2025-08-28", "2025-09-15", str(ds.fecha_corte.max().date())]):
    lim = corte + pd.Timedelta(days=1)
    cortado = dataclasses.replace(d, interacciones=d.interacciones[d.interacciones.fecha_hora < lim],
                                  sesiones=d.sesiones[d.sesiones.inicio < lim])
    a = ab.variables(d, corte).set_index(ab.CLAVES)[V].astype(float)
    b = ab.variables(cortado, corte).set_index(ab.CLAVES)[V].astype(float).reindex(a.index)
    dif = (((a - b).abs() > 1e-9) & ~(a.isna() & b.isna())).sum()
    print(corte.date(), f"{len(a)} filas; variables con diferencias: {dif[dif > 0].to_dict() or 'ninguna'}")
""")

# ---------------------------------------------------------------------------
md("""
## 4. Particiones: prueba, validación cruzada y validación temporal

* **Prueba (hold-out):** 25 % de los **alumnos** (`GroupShuffleSplit`). Todas sus fotos y materias quedan afuera
  del entrenamiento; solo se miran al final.
* **Validación cruzada:** `GroupKFold(5)` por alumno sobre el 75 % restante. Si se partiera por filas, el modelo
  vería fotos del mismo alumno en entrenamiento y validación y "reconocería" alumnos.
* **Validación temporal:** la app predice en fechas **posteriores** a las fotos con desenlace conocido (por ejemplo,
  el 24/10 es el día 80 y la última foto con desenlace es del día 50). Para simularlo, en cada partición se entrena
  con el primer 60 % de las fechas de unos alumnos y se evalúa en las fechas tardías de otros (D67).
""")
py("""
X, y, g = ds[V].astype(float), ds["abandona"].to_numpy(), ds["id_alumno"].to_numpy()
fechas = ds["fecha_corte"].to_numpy()
ie, ip = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=ABANDONO_SEMILLA).split(X, y, g))
Xe, ye, ge, fe = X.iloc[ie], y[ie], g[ie], fechas[ie]
Xp, yp = X.iloc[ip], y[ip]
assert not set(ge) & set(g[ip])
cv = GroupKFold(5)
print(f"Entrenamiento: {len(ie):,} casos de {len(set(ge))} alumnos (abandona {100 * ye.mean():.1f} %)")
print(f"Prueba:        {len(ip):,} casos de {len(set(g[ip]))} alumnos (abandona {100 * yp.mean():.1f} %)")
print("Corte de la validación temporal:", pd.Timestamp(ab._corte_temporal(fe)).date())
""")

# ---------------------------------------------------------------------------
md("""
## 5. Líneas de base

Antes de cualquier modelo hay que saber cuánto se gana con algo trivial:

* **Trivial (`DummyClassifier`)**: predice la proporción de abandono para todos. AUC 0,5.
* **Regla:** "más de 7 días sin entrar" (la alerta de inactividad del dashboard). No se entrena.

El modelo vale la pena solo si le gana a la regla.
""")
py("""
def costo_100(y_, pred):
    return round(100 * ab.costo(y_, pred) / len(y_), 1)

dias = Xe["dias_sin_actividad"].to_numpy()
regla = dias > ABANDONO_REGLA_DIAS
base = pd.DataFrame([
    {"modelo": "trivial (nunca avisa)", "auc_roc": 0.5, "auc_pr": round(ye.mean(), 3), "recall": 0.0,
     "precision": np.nan, "pct_marcados": 0.0, "costo_100": costo_100(ye, np.zeros_like(ye))},
    {"modelo": "trivial (avisa a todos)", "auc_roc": 0.5, "auc_pr": round(ye.mean(), 3), "recall": 100.0,
     "precision": round(100 * ye.mean(), 1), "pct_marcados": 100.0, "costo_100": costo_100(ye, np.ones_like(ye))},
    {"modelo": f"regla > {ABANDONO_REGLA_DIAS} días", "auc_roc": round(roc_auc_score(ye, dias), 3),
     "auc_pr": round(average_precision_score(ye, dias), 3), "recall": round(100 * regla[ye].mean(), 1),
     "precision": round(100 * ye[regla].mean(), 1), "pct_marcados": round(100 * regla.mean(), 1),
     "costo_100": costo_100(ye, regla)},
])
base
""")
md("""
La regla ya es muy buena (AUC ~0,85): "días sin entrar" es, por lejos, la variable más fuerte. El costo cada 100
casos es la vara contra la que se mide todo lo que sigue.
""")

# ---------------------------------------------------------------------------
md("""
## 6. Comparación de modelos

Se prueban los modelos vistos en la materia, todos dentro de un `Pipeline` (el preprocesamiento se ajusta dentro de
cada partición de la validación cruzada). Se informa **media ± desvío** en las 5 particiones y el puntaje en
entrenamiento: si el de entrenamiento es mucho mayor que el de validación, el modelo sobreajusta (alta varianza).
""")
py("""
prep = lambda: ab.modelos()["logistica"].steps[:2]          # log1p en conteos + estandarizar
zoo = {
    "Trivial": DummyClassifier(strategy="prior"),
    "Árbol de decisión": DecisionTreeClassifier(max_depth=4, min_samples_leaf=50, random_state=ABANDONO_SEMILLA),
    "KNN (k=50)": Pipeline(prep() + [("modelo", KNeighborsClassifier(n_neighbors=50))]),
    "SVM (RBF)": Pipeline(prep() + [("modelo", SVC(C=1.0, probability=True, random_state=ABANDONO_SEMILLA))]),
    "Red neuronal (MLP)": Pipeline(prep() + [("modelo", MLPClassifier(hidden_layer_sizes=(32, 16), alpha=1e-2,
                                                                       early_stopping=True, max_iter=500,
                                                                       random_state=ABANDONO_SEMILLA))]),
    **{ab.NOMBRES_MODELOS[k]: v for k, v in ab.modelos().items()},
}
filas = []
for nombre, est in zoo.items():
    t0 = time.time()
    r = cross_validate(est, Xe, ye, groups=ge, cv=cv, scoring=["roc_auc", "average_precision"],
                       return_train_score=True)
    filas.append({"modelo": nombre,
                  "auc_val": r["test_roc_auc"].mean(), "auc_sd": r["test_roc_auc"].std(),
                  "auc_pr_val": r["test_average_precision"].mean(), "auc_pr_sd": r["test_average_precision"].std(),
                  "auc_train": r["train_roc_auc"].mean(),
                  "brecha_auc": r["train_roc_auc"].mean() - r["test_roc_auc"].mean(),
                  "segundos": time.time() - t0})
zoo_res = pd.DataFrame(filas).round(3).sort_values("auc_pr_val", ascending=False)
zoo_res
""")
py("""
fig = go.Figure()
for _, r in zoo_res.iterrows():
    fig.add_trace(go.Scatter(x=[r.auc_pr_val], y=[r.modelo], error_x=dict(type="data", array=[r.auc_pr_sd]),
                             mode="markers", marker_size=10, showlegend=False))
fig.add_vline(x=base.loc[2, "auc_pr"], line_dash="dot", annotation_text="regla 7 días")
fig.update_layout(title="AUC-PR en validación cruzada (media ± desvío entre particiones)", height=420).show()
""")
md("""
**Lectura:**

* Todos los modelos le ganan al trivial, y los mejores (logística, random forest, gradient boosting, red neuronal)
  quedan muy cerca entre sí: el desvío entre particiones (±0,13 de AUC-PR) es **más grande** que las diferencias entre
  ellos. Con 228 alumnos no hay datos para distinguirlos con seguridad.
* SVM y random forest tienen la mayor brecha entrenamiento-validación (sobreajustan: alta varianza). Un árbol solo
  es demasiado simple (más sesgo) y además varía mucho entre particiones; los ensambles de árboles lo corrigen.
* Se siguen comparando tres (logística, random forest y gradient boosting), que son los que interpreta la app.
""")

# ---------------------------------------------------------------------------
md("""
## 7. Ajuste de hiperparámetros (búsqueda aleatoria)

Búsqueda aleatoria de 30 combinaciones para el gradient boosting, con la misma validación por alumno y AUC-PR como
métrica. Se guardan también los puntajes de entrenamiento para ver qué combinaciones sobreajustan.
""")
py("""
dist = {"modelo__max_depth": [2, 3, 4, None], "modelo__learning_rate": [0.02, 0.05, 0.1, 0.2],
        "modelo__max_iter": [100, 200, 400], "modelo__min_samples_leaf": [20, 50, 100, 200],
        "modelo__l2_regularization": [0, 0.1, 1, 5]}
t0 = time.time()
busqueda = RandomizedSearchCV(ab.modelos()["gradient_boosting"], dist, n_iter=30, scoring="average_precision",
                              cv=cv, random_state=ABANDONO_SEMILLA, n_jobs=-1, return_train_score=True)
busqueda.fit(Xe, ye, groups=ge)
res = pd.DataFrame(busqueda.cv_results_).sort_values("rank_test_score").reset_index(drop=True)
res = pd.concat([pd.json_normalize(res["params"]).rename(columns=lambda c: c.replace("modelo__", "")),
                 res[["mean_test_score", "std_test_score", "mean_train_score"]]], axis=1)
print(f"{time.time() - t0:.0f} s")
res.round(3).head(10)
""")
py("""
px.scatter(res, x="mean_train_score", y="mean_test_score",
           color=res["max_depth"].map(lambda v: "sin límite" if pd.isna(v) else str(int(v))),
           size="min_samples_leaf", hover_data=list(res.columns[:5]),
           labels={"mean_train_score": "AUC-PR entrenamiento", "mean_test_score": "AUC-PR validación",
                   "color": "profundidad"},
           title="Más complejidad = más puntaje en entrenamiento, no en validación").show()
""")
md("""
Las mejores combinaciones son las **más regularizadas**: poca profundidad, aprendizaje lento (`learning_rate`
0,02) y hojas grandes (200 casos). Las profundas llegan a casi 1 en entrenamiento y bajan en validación: sobreajuste
de manual. Como la búsqueda optimiza AUC-PR y la app decide por costo, se confirma el cambio con el costo en las tres
validaciones, comparando la receta anterior (lr 0,05, hojas de 50) con la nueva (D70):
""")
py("""
def evaluar(est):
    oof = cross_val_predict(est, Xe, ye, groups=ge, cv=cv, method="predict_proba")[:, 1]
    u = ab.elegir_umbral(ye, oof)
    yt, pt = ab._validacion_temporal(est, Xe, ye, ge, fe, cv)
    pp = clone(est).fit(Xe, ye).predict_proba(Xp)[:, 1]
    return {"umbral": u, "costo_cv": costo_100(ye, oof >= u), "costo_temporal": costo_100(yt, pt >= u),
            "costo_prueba": costo_100(yp, pp >= u), "auc_pr_prueba": round(average_precision_score(yp, pp), 3)}

anterior = clone(ab.modelos()["gradient_boosting"]).set_params(modelo__learning_rate=0.05,
                                                                modelo__min_samples_leaf=50)
t_ = Xe["dias_sin_actividad"].to_numpy() > ABANDONO_REGLA_DIAS
tarde = fe > ab._corte_temporal(fe)
pd.DataFrame({
    "GB anterior (lr 0,05, hoja 50)": evaluar(anterior),
    "GB ajustado (lr 0,02, hoja 200)": evaluar(ab.modelos()["gradient_boosting"]),
    "Regla 7 días": {"umbral": np.nan, "costo_cv": costo_100(ye, t_),
                     "costo_temporal": costo_100(ye[tarde], t_[tarde]),
                     "costo_prueba": costo_100(yp, Xp["dias_sin_actividad"].to_numpy() > ABANDONO_REGLA_DIAS),
                     "auc_pr_prueba": round(average_precision_score(yp, Xp["dias_sin_actividad"]), 3)},
}).T
""")

# ---------------------------------------------------------------------------
md("""
## 8. Selección del modelo y umbral

`src/ml_abandono.entrenar()` hace todo esto en la app: compara logística, random forest y gradient boosting, elige el
umbral de **menor costo** en la validación cruzada y se queda con el de menor costo en la **validación temporal**
(la prueba solo se informa). El modelo elegido se reentrena con todos los alumnos y se guarda.
""")
mod_py = """
mod = ab.cargar_modelo(d)
print(f"Elegido: {mod.nombre}, umbral {mod.umbral}")
comp = mod.comparacion.pivot_table(index="modelo", columns="conjunto", values="costo_por_100")
comp[["validación cruzada", ab.VALIDACION_TEMPORAL, "prueba"]].sort_values(ab.VALIDACION_TEMPORAL)
"""
py(mod_py)
py("""
mod.comparacion.drop(columns=["costo"]).set_index(["conjunto", "modelo"]).sort_index()
""")
md("""
La logística gana en la validación cruzada común, pero en la temporal se desploma: extrapola mal a fechas que no vio
(por ejemplo, con más días de cursada que en cualquier foto de entrenamiento). Los modelos de árboles con
restricciones monótonas (D65) se mantienen: por eso se elige por validación temporal.

### Umbral por costo vs. umbral por F1
""")
py("""
est = ab.modelos()[mod.clave]
oof = cross_val_predict(est, Xe, ye, groups=ge, cv=cv, method="predict_proba")[:, 1]
tu = ab.tabla_umbral(ye, oof)
tu["f1"] = 2 * tu.precision * tu.recall / (tu.precision + tu.recall)
u_costo, u_f1 = ab.elegir_umbral(ye, oof), tu.loc[tu.f1.idxmax(), "umbral"]
fig = go.Figure()
fig.add_trace(go.Scatter(x=tu.umbral, y=tu.costo / len(ye) * 100, name="costo cada 100"))
fig.add_trace(go.Scatter(x=tu.umbral, y=tu.f1, name="F1 (%)", yaxis="y2"))
fig.add_vline(x=u_costo, line_dash="dot", annotation_text=f"costo mín. {u_costo}")
fig.add_vline(x=u_f1, line_dash="dash", annotation_text=f"F1 máx. {u_f1}", annotation_position="bottom right")
fig.update_layout(yaxis2=dict(overlaying="y", side="right"), title="Elegir el umbral (validación cruzada)",
                  xaxis_range=[0, 0.6]).show()
tu[tu.umbral.isin([u_costo, u_f1, 0.5])]
""")
md("""
Con F1 se cuidan por igual falsos positivos y negativos; acá no es así: no avisar a tiempo a alguien que abandona es
peor que mandar un mensaje de más. Con el costo 5:1 el umbral baja, se marcan más alumnos y sube el recall.
Sensibilidad al costo elegido:
""")
py("""
pd.DataFrame([{"costo_fn:fp": f"{fn}:1", "umbral": ab.elegir_umbral(ye, oof, fn, 1),
               **tu.set_index("umbral").loc[ab.elegir_umbral(ye, oof, fn, 1), ["pct_marcados", "precision", "recall"]]}
              for fn in [1, 2, 3, 5, 8, 10]])
""")

# ---------------------------------------------------------------------------
md("""
## 9. Evaluación final en prueba

Alumnos que el modelo nunca vio, con el modelo entrenado solo con el 75 % y el umbral de la validación cruzada.
""")
py("""
modelo_e = clone(est).fit(Xe, ye)
pp = modelo_e.predict_proba(Xp)[:, 1]
pred = pp >= mod.umbral
pred_regla = Xp["dias_sin_actividad"].to_numpy() > ABANDONO_REGLA_DIAS
for nombre, p_ in [(mod.nombre, pred), ("Regla 7 días", pred_regla)]:
    cm = pd.DataFrame(confusion_matrix(yp, p_), index=["sigue (real)", "abandona (real)"],
                      columns=["sigue (pred.)", "abandona (pred.)"])
    print(f"--- {nombre}: costo cada 100 = {costo_100(yp, p_)}")
    print(cm, "\\n")
    print(classification_report(yp, p_, target_names=["sigue", "abandona"], digits=3))
""")
py("""
fig = go.Figure()
for nombre, s in [(mod.nombre, pp), ("Regla (días sin entrar)", Xp["dias_sin_actividad"])]:
    fpr, tpr, _ = roc_curve(yp, s)
    fig.add_trace(go.Scatter(x=fpr, y=tpr, name=f"{nombre} (AUC {roc_auc_score(yp, s):.3f})"))
fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], line_dash="dot", name="azar"))
fig.update_layout(title="Curva ROC (prueba)", xaxis_title="FPR", yaxis_title="TPR (recall)", height=420).show()
fig = go.Figure()
for nombre, s in [(mod.nombre, pp), ("Regla (días sin entrar)", Xp["dias_sin_actividad"])]:
    pr, rc, _ = precision_recall_curve(yp, s)
    fig.add_trace(go.Scatter(x=rc, y=pr, name=f"{nombre} (AP {average_precision_score(yp, s):.3f})"))
fig.add_hline(y=yp.mean(), line_dash="dot", annotation_text="azar")
fig.update_layout(title="Curva precisión-recall (prueba)", xaxis_title="recall", yaxis_title="precisión",
                  height=420).show()
""")
md("""
### Calibración

La ficha muestra un **porcentaje** de riesgo, así que conviene que la probabilidad signifique algo: entre los que
el modelo da 30 %, ¿abandona más o menos el 30 %?
""")
py("""
frac, media = calibration_curve(yp, pp, n_bins=8, strategy="quantile")
fig = px.line(x=media, y=frac, markers=True, labels={"x": "probabilidad predicha", "y": "proporción real"},
              title="Calibración en prueba (8 grupos del mismo tamaño)")
fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], line_dash="dot", name="perfecta"))
fig.update_layout(height=400).show()
print("Brier:", round(((pp - yp) ** 2).mean(), 4), "| Brier de predecir siempre la tasa:",
      round(((ye.mean() - yp) ** 2).mean(), 4))
""")

# ---------------------------------------------------------------------------
md("""
## 10. Interpretación y controles

### 10.1 Importancia por permutación (la que muestra la app)
""")
py("""
imp = mod.importancia.head(12)
px.bar(imp[::-1], x="importancia", y="descripcion", error_x="desvio", orientation="h", height=450,
       title="Cuánto baja el AUC-PR en prueba al mezclar cada variable").show()
""")
md("""### 10.2 Dependencia parcial: cómo cambia el riesgo con cada variable (el resto fijo)""")
py("""
for c in ["dias_sin_actividad", "sin_vs_habitual", "pct_rendidos", "dias_de_cursada"]:
    pdp = partial_dependence(modelo_e, Xe, [V.index(c)], grid_resolution=30)
    px.line(x=pdp["grid_values"][0], y=pdp["average"][0], labels={"x": c, "y": "probabilidad media"},
            title=f"Dependencia parcial: {c}", height=280).show()
""")
md("""
Las curvas son monótonas donde se impuso (D65): más días sin entrar nunca bajan el riesgo. `dias_de_cursada` muestra
por qué importa la validación temporal: el modelo no vio fotos después del día ~50 y para fechas posteriores la
curva queda plana (los árboles no extrapolan; la logística sí, y mal).

### 10.3 Control con etiquetas mezcladas

Si se mezcla el objetivo al azar, cualquier modelo honesto tiene que caer a AUC ≈ 0,5. Si no cae, hay fuga.
""")
py("""
rng = np.random.default_rng(0)
mezclado = []
for i in range(3):
    y_mez = rng.permutation(ye)
    o = cross_val_predict(est, Xe, y_mez, groups=ge, cv=cv, method="predict_proba")[:, 1]
    mezclado.append(roc_auc_score(y_mez, o))
print("AUC con etiquetas mezcladas:", np.round(mezclado, 3))
""")
md("""### 10.4 ¿Dónde se equivoca? Errores por materia, estado y nivel de notas (prueba)""")
py("""
t = ds.iloc[ip].assign(prob=pp, alerta=pred)
t["estado"] = ab._estado(t)
t["notas"] = pd.cut(t["nota_pct"], [-1, 40, 60, 85, 101], labels=["< 40", "40-60", "60-85", "≥ 85"])
def seg(col):
    return (t.groupby(col, observed=True)
             .apply(lambda s: pd.Series({"casos": len(s), "abandona_pct": 100 * s.abandona.mean(),
                                         "marcados_pct": 100 * s.alerta.mean(),
                                         "recall": 100 * s.alerta[s.abandona].mean() if s.abandona.any() else np.nan,
                                         "precision": 100 * s.abandona[s.alerta].mean() if s.alerta.any() else np.nan,
                                         "costo_100": costo_100(s.abandona, s.alerta)}))
             .round(1))
display(seg("asignatura")); display(seg("estado")); seg("notas")
""")
md("""
Los alejados (14+ días sin entrar) concentran casi todas las alertas y casi todos los abandonos. Entre quienes
están cursando, el modelo avisa poco: sin un hueco de actividad, casi no hay señal de que alguien va a dejar.
""")

# ---------------------------------------------------------------------------
md("""
## 11. Robustez: cursadas sintéticas

Hay **una sola cursada**. Para ver qué pasa con cohortes distintas, `src/simulacion.py` arma cursadas a partir de la
real con más abandonos (desde una fecha al azar el alumno no vuelve a entrar y lo que iba a rendir queda sin rendir) o
con pausas de 15 a 30 días. Se entrena un modelo **sin los alumnos de prueba** y se evalúa solo en ellos.

Limitación: los abandonos inyectados son bruscos (los reales suelen tener una caída previa de actividad) y los alumnos
son los mismos, así que esto mide robustez, no el rendimiento esperado en otra cohorte.
""")
py("""
umbral_e = ab.elegir_umbral(ye, oof)
prueba = set(g[ip])
escenarios = {"real": (0, 0), "más abandono (25 %)": (0.25, 0), "muchas pausas (30 %)": (0, 0.30),
              "mixta (15 % + 20 % pausas)": (0.15, 0.20), "abandono masivo (40 %)": (0.40, 0.10)}
filas = []
for nombre, (pa, pp_) in escenarios.items():
    for semilla in ([0] if pa == pp_ == 0 else [1, 2]):
        d2, _ = simulacion.cursada_sintetica(d, p_abandono=pa, p_pausa=pp_, semilla=semilla)
        t2 = ab.dataset(d2)
        t2 = t2[t2.id_alumno.isin(prueba)]
        y2, p2 = t2.abandona.to_numpy(), modelo_e.predict_proba(t2[V].astype(float))[:, 1]
        r2 = t2.dias_sin_actividad.to_numpy() > ABANDONO_REGLA_DIAS
        filas.append({"cursada": nombre, "semilla": semilla, "abandona_pct": 100 * y2.mean(),
                      "auc_modelo": roc_auc_score(y2, p2), "auc_regla": roc_auc_score(y2, t2.dias_sin_actividad),
                      "recall_modelo": 100 * (p2 >= umbral_e)[y2].mean(), "recall_regla": 100 * r2[y2].mean(),
                      "costo_modelo": costo_100(y2, p2 >= umbral_e), "costo_regla": costo_100(y2, r2)})
sint = pd.DataFrame(filas).groupby("cursada", sort=False).mean(numeric_only=True).drop(columns="semilla").round(2)
sint
""")
md("""@@CONCLUSIONES@@""")

nb = nbf.v4.new_notebook(cells=celdas, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"},
                                                 "language_info": {"name": "python"}})
if __name__ == "__main__":
    conclusiones = Path(__file__).with_name("_conclusiones_02.md")
    texto = conclusiones.read_text(encoding="utf-8") if conclusiones.exists() else "## Conclusiones\n\n(pendiente)"
    for c in nb.cells:
        if c.source == "@@CONCLUSIONES@@":
            c.source = texto.strip()
    NotebookClient(nb, timeout=1800, kernel_name="python3", resources={"metadata": {"path": str(RAIZ / "notebooks")}}).execute()
    nbf.write(nb, SALIDA)
    print("ok ->", SALIDA)
