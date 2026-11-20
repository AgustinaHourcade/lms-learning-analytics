"""Arma y ejecuta notebooks/03_grupos_alumnos.ipynb.

Uso (desde la raíz):  python notebooks/_armar_03_grupos.py
El notebook queda ejecutado (con salidas). Para cambiarlo, se edita este archivo y se vuelve a correr.
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "notebooks" / "03_grupos_alumnos.ipynb"
celdas = []
md = lambda t: celdas.append(nbf.v4.new_markdown_cell(t.strip()))
py = lambda t: celdas.append(nbf.v4.new_code_cell(t.strip()))

md("""
# 3 · Grupos de alumnos (aprendizaje no supervisado)

**Pregunta de negocio:** ¿hay "tipos" de alumnos según cómo usan el aula y cómo les va, que le sirvan al docente
para decidir a quién acompañar y cómo?

No hay una etiqueta para aprender: es un problema de **clustering**. El notebook recorre:

1. Variables y su preparación (asimetría, escalas por materia, correlación).
2. Estructura de los datos con PCA.
3. Elección de k con cuatro criterios: codo (inercia), silhouette, Davies-Bouldin y Calinski-Harabasz.
4. Los grupos de K-Means: perfiles, centroides y mapa.
5. Comparación con otros algoritmos (jerárquico, mezcla gaussiana, DBSCAN).
6. Estabilidad (bootstrap y semillas).
7. Validación externa: ¿los grupos dicen algo de la condición y del abandono?
8. Alumnos atípicos.

El código de la app está en **`src/ml_grupos.py`** (D57, D68, D71); acá se lo llama y se lo analiza.
""")
py("""
import os, warnings
from pathlib import Path
if not Path("src").exists():          # el notebook está en notebooks/: subo a la raíz
    os.chdir("..")
warnings.simplefilter("ignore")

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score,
                             silhouette_samples, silhouette_score)
from sklearn.mixture import GaussianMixture
from sklearn.neighbors import NearestNeighbors

from src import metricas as m, ml_abandono as ab, ml_grupos as g
from src.config import FECHA_CORTE_DEFECTO, GRUPOS_LOG, GRUPOS_SEMILLA, GRUPOS_VARIABLES

pio.renderers.default = "notebook_connected"
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
d = m.cargar()
t = m.tabla_alumnos(d, FECHA_CORTE_DEFECTO)
t = t[g._con_evaluaciones(t)].reset_index(drop=True)
z = g.matriz(t)
print(f"Fecha de corte {pd.Timestamp(FECHA_CORTE_DEFECTO).date()}: {len(t)} alumno-materia, variables {GRUPOS_VARIABLES}")
""")

md("""
## 1. Variables y preparación

Cinco variables de `tabla_alumnos`: **sesiones, minutos, semanas con actividad, avance** (reporte de participación)
y **nota** a la fecha (lo no rendido cuenta 0). Cada fila es un alumno en una materia.
""")
py("""
desc = t[GRUPOS_VARIABLES].astype(float).describe().T[["mean", "std", "min", "50%", "max"]]
desc["asimetria"] = t[GRUPOS_VARIABLES].astype(float).skew()
desc.round(2)
""")
py("""
largo = t.melt(id_vars="asignatura", value_vars=GRUPOS_VARIABLES)
px.box(largo, x="asignatura", y="value", facet_col="variable", facet_col_wrap=5, points=False, height=380,
       title="Distribución por materia (unidades reales)").update_yaxes(matches=None, showticklabels=True).show()
""")
md("""
Dos problemas para K-Means, que usa distancias:

* **Escalas y asimetría:** sesiones y minutos tienen colas largas (pocos alumnos con muchísimo uso). Sin
  transformar, dominarían la distancia. Se les aplica `log(1 + x)`.
* **Diferencias entre materias:** 150 minutos no significan lo mismo en PyE que en Álgebra, y en AED las notas son
  más bajas. Se estandariza **dentro de cada materia**: cada alumno se compara con su curso.
""")
py("""
x = t[GRUPOS_VARIABLES].astype(float).copy()
for c in GRUPOS_LOG:
    x[c] = np.log1p(x[c])
pd.DataFrame({"asimetría original": t[GRUPOS_VARIABLES].astype(float).skew(),
              "con log": x.skew(), "estandarizada por materia": z.skew()}).round(2)
""")
py("""
corr = z.corr(method="spearman")
px.imshow(corr.round(2), text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1, height=420,
          title="Correlación entre variables (ya transformadas)").show()
""")
md("""
Las cuatro variables de actividad están muy correlacionadas entre sí y bastante con la nota: en la práctica hay
pocas dimensiones "reales". Eso se ve mejor con PCA.

## 2. Estructura con PCA
""")
py("""
pca = PCA().fit(z)
var = pd.DataFrame({"componente": [f"CP{i + 1}" for i in range(len(GRUPOS_VARIABLES))],
                    "varianza_pct": (100 * pca.explained_variance_ratio_).round(1)})
var["acumulada_pct"] = var["varianza_pct"].cumsum().round(1)
display(var)
pd.DataFrame(pca.components_[:3].T, index=GRUPOS_VARIABLES, columns=["CP1", "CP2", "CP3"]).round(2)
""")
md("""
El primer componente (≈ "cuánto participa y le va", todas las cargas del mismo signo) explica la mayor parte de la
variación; el segundo separa **nota** de **actividad** (alumnos que entran poco con buena nota, o al revés). Con dos
componentes se ve casi todo: por eso la app dibuja el mapa de grupos en esos dos ejes.

## 3. ¿Cuántos grupos?

Cuatro criterios para k = 2 a 8. No hay un "k verdadero": se busca uno que tenga grupos separados **y** útiles.
""")
py("""
filas = []
for k in range(2, 9):
    km = KMeans(n_clusters=k, n_init=20, random_state=GRUPOS_SEMILLA).fit(z)
    filas.append({"k": k, "inercia": km.inertia_, "silhouette": silhouette_score(z, km.labels_),
                  "davies_bouldin": davies_bouldin_score(z, km.labels_),
                  "calinski_harabasz": calinski_harabasz_score(z, km.labels_),
                  "grupo_mas_chico": np.bincount(km.labels_).min()})
ks = pd.DataFrame(filas).round(3)
display(ks)
fig = px.line(ks.melt(id_vars="k", value_vars=["inercia", "silhouette", "davies_bouldin", "calinski_harabasz"]),
              x="k", y="value", facet_col="variable", facet_col_wrap=4, markers=True, height=300,
              title="Codo (inercia ↓), silhouette (↑), Davies-Bouldin (↓) y Calinski-Harabasz (↑)")
fig.update_yaxes(matches=None, showticklabels=True).show()
""")
py("""
g.evaluar_k(d, FECHA_CORTE_DEFECTO)     # lo mismo que usa la app (k = 2 de referencia, candidatos 3 a 6)
""")
md("""
* k = 2 tiene el mejor silhouette, pero solo separa "entran / no entran", que ya lo dice el estado de actividad
  (D35): no aporta. Por eso la app elige entre 3 y 6 (D57).
* Entre 3 y 6, **los tres índices coinciden en k = 3** (mayor silhouette, menor Davies-Bouldin, mayor
  Calinski-Harabasz). El codo no es nítido: la inercia baja de forma gradual, típico de datos sin grupos muy marcados.
* Un silhouette de ~0,4 indica una estructura **moderada**: hay grupos, pero con alumnos en las fronteras.

### Silhouette por alumno
""")
py("""
km3 = KMeans(n_clusters=3, n_init=20, random_state=GRUPOS_SEMILLA).fit(z)
sil = pd.DataFrame({"grupo": km3.labels_, "silhouette": silhouette_samples(z, km3.labels_)})
sil = sil.sort_values(["grupo", "silhouette"]).reset_index(drop=True)
px.bar(sil, x=sil.index, y="silhouette", color=sil["grupo"].astype(str), height=320,
       title="Silhouette de cada alumno (negativo = estaría mejor en otro grupo)").update_xaxes(visible=False).show()
print(f"Alumnos con silhouette negativo: {(sil.silhouette < 0).mean():.1%}")
""")

md("""
## 4. Los grupos de K-Means (lo que muestra la app)

Los nombres salen del **centroide** de cada grupo (cuánta actividad y qué nota tiene respecto del promedio de su
materia), no del número arbitrario de K-Means (D57, D68).
""")
py("""
perfil = g.perfil_grupos(d, FECHA_CORTE_DEFECTO)
perfil.drop(columns="descripcion_grupo")
""")
py("""
cen = g.centroides(d, FECHA_CORTE_DEFECTO)
px.imshow(cen.pivot(index="nombre_grupo", columns="descripcion", values="desvios"), text_auto=".2f",
          color_continuous_scale="RdBu", zmin=-2, zmax=2, height=320,
          title="Centroides en desvíos respecto del promedio de la materia").show()
mapa = g.mapa_grupos(d, FECHA_CORTE_DEFECTO)
px.scatter(mapa["alumnos"], x="eje1", y="eje2", color="nombre_grupo", symbol="asignatura", opacity=0.7, height=480,
           labels={"eje1": f"Eje 1: actividad y nota ({mapa['varianza'][0]} %)",
                   "eje2": f"Eje 2: nota vs. actividad ({mapa['varianza'][1]} %)"},
           title="Grupos en los dos primeros componentes").show()
""")
py("""
g.perfil_grupos(d, FECHA_CORTE_DEFECTO, por_materia=True)[["asignatura", "nombre_grupo", "alumnos", "pct",
                                                            "nota_promedio", "pct_activos"]]
""")
md("""
### ¿Y con más grupos?

Si el docente fuerza k = 5, aparecen subgrupos con nombre propio (D68): por ejemplo "Muy comprometidos" y
"Comprometidos". Sirve para afinar, pero los grupos chicos son menos estables (sección 6).
""")
py("""
g.perfil_grupos(d, FECHA_CORTE_DEFECTO, k=5)[["grupo", "nombre_grupo", "alumnos", "pct", "nota_promedio",
                                              "pct_activos"]]
""")

md("""
## 5. Comparación con otros algoritmos

Mismos datos y k = 3. El **índice de Rand ajustado (ARI)** mide cuánto coinciden dos agrupamientos (1 = iguales,
0 = como al azar).

* **Jerárquico (Ward):** une grupos de abajo hacia arriba minimizando la varianza; no depende de la semilla.
* **Mezcla gaussiana (GMM):** grupos elípticos y asignación probabilística.
* **DBSCAN:** grupos por densidad; no pide k y marca "ruido". El `eps` se elige con el gráfico de distancia al
  k-ésimo vecino.
""")
py("""
vec = np.sort(NearestNeighbors(n_neighbors=10).fit(z).kneighbors(z)[0][:, -1])
px.line(y=vec, labels={"index": "alumnos ordenados", "y": "distancia al 10.º vecino"}, height=280,
        title="Elegir eps de DBSCAN: el 'codo' de esta curva").show()
""")
py("""
algoritmos = {
    "K-Means": km3.labels_,
    "Jerárquico (Ward)": AgglomerativeClustering(n_clusters=3, linkage="ward").fit_predict(z),
    "Mezcla gaussiana": GaussianMixture(n_components=3, n_init=5, random_state=GRUPOS_SEMILLA).fit(z).predict(z),
    "DBSCAN (eps 0,9)": DBSCAN(eps=0.9, min_samples=10).fit_predict(z),
}
filas = []
for nombre, et in algoritmos.items():
    sin_ruido = et >= 0
    n = len(set(et[sin_ruido]))
    filas.append({"algoritmo": nombre, "grupos": n, "ruido_pct": round(100 * (~sin_ruido).mean(), 1),
                  "silhouette": round(silhouette_score(z[sin_ruido], et[sin_ruido]), 3) if n > 1 else np.nan,
                  "ARI vs K-Means": round(adjusted_rand_score(km3.labels_, et), 3),
                  "tamaños": sorted(np.bincount(et[sin_ruido]).tolist(), reverse=True)})
pd.DataFrame(filas)
""")
md("""
El jerárquico coincide bastante con K-Means (ARI ~0,7) y la mezcla gaussiana menos (~0,5): el "tramo alto / medio /
bajo" aparece con todos, pero **las fronteras entre grupos cambian según el algoritmo**, lo esperable si los alumnos
forman un continuo. K-Means tiene el mejor silhouette de los tres. DBSCAN, en cambio, encuentra sobre todo **un gran bloque denso** y algo de ruido: no hay
grupos separados por zonas vacías, sino un continuo de "más a menos participación". K-Means sirve para **segmentar**
ese continuo en tramos interpretables, que es lo que se busca.

## 6. Estabilidad

Si los grupos fueran un accidente de la muestra, cambiarían mucho al remuestrear. `g.estabilidad()` (D71) remuestrea a
los alumnos con reposición 30 veces, reajusta y compara con el ARI.
""")
py("""
est = pd.concat([g.estabilidad(d, FECHA_CORTE_DEFECTO, k=k, repeticiones=30) for k in [3, 4, 5, 6]])
display(est.groupby("k")["ari"].describe()[["mean", "std", "min", "50%"]].round(3))
px.box(est, x="k", y="ari", points="all", height=330, title="Estabilidad bootstrap (ARI con el modelo original)").show()
""")
py("""
semillas = [KMeans(n_clusters=3, n_init=1, random_state=s).fit(z).labels_ for s in range(20)]
ari_sem = [adjusted_rand_score(km3.labels_, s) for s in semillas]
print(f"Con una sola inicialización, ARI contra el modelo de la app: media {np.mean(ari_sem):.3f}, mín. {min(ari_sem):.3f}")
""")
md("""
Con k = 3 los grupos son muy estables (ARI ~0,95): con otros alumnos de la misma cursada se obtendrían los mismos
grupos. Con más grupos la estabilidad baja (k = 5 es el más inestable): los subgrupos de k grande dependen más de la
muestra. Con k = 3 ni siquiera importa la inicialización (todas las semillas dan lo mismo); igual la app usa
`n_init=20` por si cambian los datos.

## 7. Validación externa: ¿los grupos dicen algo útil?

Los grupos se armaron sin mirar la condición ni el abandono. Si son útiles, deberían diferenciarse en ambas.
""")
py("""
gr = g.grupos_alumnos(d, FECHA_CORTE_DEFECTO)
pd.crosstab(gr["nombre_grupo"], gr["condicion"], normalize="index").mul(100).round(1)
""")
md("""
Para el abandono se arman los grupos a una fecha con desenlace conocido (20/09: hay más de 28 días de datos después)
y se mira qué proporción de cada grupo abandonó la materia (D67).
""")
py("""
corte = pd.Timestamp("2025-09-20")
g_corte = g.grupos_alumnos(d, corte)
desenlace = ab.dataset(d, cortes=[corte])[ab.CLAVES + ["abandona"]]
x = g_corte.merge(desenlace, on=ab.CLAVES, how="left")
x["abandona"] = x["abandona"].astype("boolean")
res = x.groupby("nombre_grupo").agg(alumnos=("id_alumno", "size"), entraron=("abandona", "count"),
                                    abandonaron_pct=("abandona", "mean"))
res["abandonaron_pct"] = (100 * res["abandonaron_pct"]).round(1)
res.sort_values("abandonaron_pct")
""")
md("""
## 8. Alumnos atípicos

`IsolationForest` marca al 3 % de alumnos con combinaciones menos comunes. No son errores de datos (eso se revisó en
el notebook 1).
""")
py("""
iso = IsolationForest(contamination=0.03, random_state=GRUPOS_SEMILLA).fit(z)
t["atipico"] = iso.predict(z) == -1
t["grupo"] = gr.set_index(ab.CLAVES).loc[pd.MultiIndex.from_frame(t[ab.CLAVES]), "nombre_grupo"].to_numpy()
print(f"{t.atipico.sum()} atípicos de {len(t)}")
display(pd.crosstab(t["grupo"], t["atipico"]))
t.loc[t.atipico, ["asignatura", "id_alumno", "grupo", *GRUPOS_VARIABLES, "condicion"]].sort_values("grupo")
""")
md("""
Los atípicos son casi todos el extremo inferior: alumnos que entraron una vez o nunca y no rindieron. Confirma que el
grupo "Desconectados" es una cola larga y no un grupo compacto; no aparecen perfiles raros dentro de los otros grupos
que justifiquen tratarlos aparte. Por eso no se agregó una alerta de "atípico" a la app.
""")
md("""@@CONCLUSIONES@@""")

nb = nbf.v4.new_notebook(cells=celdas, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"},
                                                 "language_info": {"name": "python"}})
if __name__ == "__main__":
    conclusiones = Path(__file__).with_name("_conclusiones_03.md")
    texto = conclusiones.read_text(encoding="utf-8") if conclusiones.exists() else "## Conclusiones\n\n(pendiente)"
    for c in nb.cells:
        if c.source == "@@CONCLUSIONES@@":
            c.source = texto.strip()
    NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(RAIZ / "notebooks")}}).execute()
    nbf.write(nb, SALIDA)
    print("ok ->", SALIDA)
