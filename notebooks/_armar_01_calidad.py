"""Arma y ejecuta notebooks/01_calidad_datos.ipynb.

Uso (desde la raíz):  python notebooks/_armar_01_calidad.py
El notebook queda ejecutado (con salidas). Para cambiarlo, se edita este archivo y se vuelve a correr.
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "notebooks" / "01_calidad_datos.ipynb"
celdas = []
md = lambda t: celdas.append(nbf.v4.new_markdown_cell(t.strip()))
py = lambda t: celdas.append(nbf.v4.new_code_cell(t.strip()))

md("""
# 1 · Calidad de datos

Antes de construir KPIs o modelos hay que saber **qué tan confiables son los datos** (Etapa 2 de la guía de
proyecto real: *exploración y análisis de datos*; "enfocarse en la calidad y cantidad de los datos").

Este notebook recorre las cuatro fuentes del LMS (trazabilidad, participación, calificaciones y matriculados):

1. Qué archivos hay y cuáles se usan.
2. Calidad dentro de cada tabla: nulos, duplicados, formatos, valores fuera de rango, atípicos.
3. **Consistencia entre fuentes**: ¿cuentan la misma historia?
4. Resumen de controles y qué decide el proyecto con cada hallazgo.

La limpieza tabla por tabla está en `src/limpieza.py` (y su reporte en `reports/calidad_datos.md`); los controles
entre fuentes que salen de este análisis quedaron como código en **`src/calidad.py`** (D69), así se vuelven a correr
cada vez que llega un archivo nuevo.
""")
py("""
import os
from pathlib import Path
if not Path("src").exists():          # el notebook está en notebooks/: subo a la raíz
    os.chdir("..")

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio

from src import calidad, ingesta, metricas as m
from src.config import BRONZE, RAW, SILVER

pio.renderers.default = "notebook_connected"
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 80)

bronze = {t: pd.read_parquet(BRONZE / f"{t}.parquet") for t in ["trazabilidad", "participacion", "calificaciones", "matriculados"]}
silver = {t: pd.read_parquet(SILVER / f"{t}.parquet") for t in bronze}
d = m.cargar()
""")

md("""
## 1. Inventario de archivos

Cada Excel se reconoce por su **contenido** (tipo y materia), no por el nombre (D31). Las calificaciones y la
participación son "fotos": si hubiera dos del mismo instrumento, vale la más reciente (D32).
""")
py("""
infos = ingesta.descubrir(RAW)
usados, reemplazados = ingesta.seleccionar(infos)
inv = pd.DataFrame([{"tipo": i.tipo, "materia": i.asignatura, "archivo": i.nombre, "exportado": i.fecha_exportacion,
                     "instrumento": i.instrumento, "errores": "; ".join(i.errores)} for i in infos])
print(f"{len(infos)} archivos en raw, {len(usados)} usados, {len(reemplazados)} reemplazados por uno más reciente")
inv.groupby(["tipo", "materia"]).size().unstack(fill_value=0)
""")
py("""
inv[inv["tipo"].eq("calificaciones")].sort_values(["materia", "exportado"])[["materia", "instrumento", "exportado"]]
""")

md("""
## 2. Calidad dentro de cada tabla

### 2.1 Filas de bronze a silver y valores faltantes
""")
py("""
pd.DataFrame({"bronze": {t: len(x) for t, x in bronze.items()}, "silver": {t: len(x) for t, x in silver.items()}}) \\
  .assign(quitadas=lambda t: t["bronze"] - t["silver"])
""")
py("""
nulos = []
for t, x in silver.items():
    for c in x.columns:
        s = x[c]
        faltan = s.isna() | s.astype(str).str.strip().eq("")
        if faltan.any():
            nulos.append({"tabla": t, "columna": c, "faltantes": int(faltan.sum()), "%": round(100 * faltan.mean(), 1)})
pd.DataFrame(nulos).sort_values(["tabla", "%"], ascending=[True, False])
""")
md("""
### 2.2 Trazabilidad: duplicados, perfiles y calendario
""")
py("""
tz_b, tz = bronze["trazabilidad"], silver["trazabilidad"]
dup = tz_b.duplicated().sum()
print(f"Duplicados exactos en bronze: {dup} ({100 * dup / len(tz_b):.2f} %) -> se eliminan en silver")
print(f"Filas sin 'Acción': {tz['Acción'].isna().sum() + tz['Acción'].astype(str).str.strip().eq('').sum()}")
tz.groupby("Perfil").agg(eventos=("Fecha", "size"), usuarios=("Usuario", "nunique"),
                         desde=("Fecha", "min"), hasta=("Fecha", "max"))
""")
py("""
al = tz[tz["Perfil"].eq("Alumnos")]
por_dia = al.groupby([al["Fecha"].dt.normalize(), "asignatura"]).size().rename("eventos").reset_index()
fig = px.line(por_dia, x="Fecha", y="eventos", color="asignatura", title="Eventos de alumnos por día")
fig.update_layout(height=330, legend_title=None)
fig.show()
dias = pd.date_range(al["Fecha"].min().normalize(), al["Fecha"].max().normalize())
faltan = sorted(set(dias) - set(al["Fecha"].dt.normalize()))
print("Días de cursada sin ningún evento de alumnos:", [f"{x:%d/%m}" for x in faltan] or "ninguno")
print("Último evento:", al["Fecha"].max(), "(la exportación es del 24/10 a la mañana: ese día está incompleto)")
""")
py("""
hora = al["Fecha"].dt.hour.value_counts().sort_index()
fig = px.bar(x=hora.index, y=hora.values, labels={"x": "Hora", "y": "Eventos"}, title="Eventos de alumnos por hora")
fig.update_layout(height=280)
fig.show()
""")
md("""
### 2.3 Atípicos en la actividad

Se marca como atípico a quien supera Q3 + 1,5 × IQR de eventos en su materia. No se borran: un alumno que entra
mucho no es un error, pero conviene saber cuántos hay porque arrastran los promedios (por eso los dashboards usan
medianas y Spearman, D38).
""")
py("""
e = al.groupby(["asignatura", "Usuario"]).size().rename("eventos").reset_index()
def iqr(s):
    q1, q3 = s.quantile([0.25, 0.75])
    return q3 + 1.5 * (q3 - q1)
e["tope"] = e.groupby("asignatura")["eventos"].transform(iqr)
print(e.groupby("asignatura").apply(lambda g: pd.Series({"alumnos": len(g), "mediana": g["eventos"].median(),
      "tope_IQR": round(g["tope"].iloc[0]), "atipicos": int((g["eventos"] > g["tope"]).sum()),
      "maximo": g["eventos"].max()}), include_groups=False))
fig = px.box(e, x="asignatura", y="eventos", points="outliers", title="Eventos por alumno y materia")
fig.update_layout(height=320)
fig.show()
""")
py("""
s = d.sesiones[d.sesiones["en_base"]]
print(s["duracion_min"].describe(percentiles=[0.5, 0.75, 0.9, 0.99]).round(1))
print(f"Sesiones de menos de 1 minuto: {100 * (s['duracion_min'] < 1).mean():.0f} %  "
      "(una sesión de un solo evento dura 0: los minutos subestiman el tiempo real)")
""")
md("""
### 2.4 Calificaciones

`Nota` viene como texto `"24.00/25.00"`: el denominador es el puntaje máximo del instrumento. Se controla que
el máximo sea siempre el mismo dentro de cada instrumento y que ninguna nota quede fuera de rango.
""")
py("""
ca = silver["calificaciones"]
print("Máximos distintos por instrumento:", ca.groupby("instrumento")["Nota máxima"].nunique().max())
print("Notas fuera de rango (< 0 o > máximo):", int(((ca["Nota obtenida"] < 0) | (ca["Nota obtenida"] > ca["Nota máxima"])).sum()))
print("Duplicados alumno × instrumento:", int(ca.duplicated(["Usuario", "instrumento"]).sum()))
fig = px.box(ca, x="instrumento", y="Nota (%)", color="asignatura", title="Nota (%) por instrumento (solo quienes rindieron)")
fig.update_layout(height=380, xaxis_title=None, legend_title=None)
fig.show()
""")
md("""
**¿Sirve la columna `Observaciones` (aprobada / no aprobada)?** Si fuera el corte de la materia (60 %), los
"aprobada" deberían estar todos arriba de 60.
""")
py("""
obs = calidad.observaciones_vs_nota()
obs[["asignatura", "instrumento", "min_aprobada", "max_aprobada", "min_no_aprobada", "max_no_aprobada"]]
""")
md("""
**¿Cada nota tiene su rendición en la trazabilidad?** Las notas se fechan con el evento "Realizar evaluación"
del alumno (D64), así que importa cuántas no lo tienen.
""")
py("""
sin = calidad.notas_sin_rendicion(d)
print(f"{len(sin)} notas sin evento de rendición, de {int(d.calificaciones['rindio'].sum())}")
sin
""")
md("""
### 2.5 Participación
""")
py("""
pa = silver["participacion"]
print(pa["Perfil"].value_counts().to_dict())
pal = pa[pa["Perfil"].eq("Alumnos")]
print("Alumnos por materia en el reporte:", pal["asignatura"].value_counts().to_dict())
print("Con 0 interacciones:", int(pd.to_numeric(pal["Interacciones"], errors="coerce").eq(0).sum()))
print("Columnas vacías en todas las filas:", [c for c in pa.columns if pa[c].isna().all() or pa[c].astype(str).str.strip().eq("").all()])
""")
md("""
### 2.6 Matriculados
""")
py("""
ma = silver["matriculados"]
print(ma["Estado Insc."].value_counts().to_dict(), "| comisiones:", ma["Comisión"].value_counts().to_dict())
varias = ma.groupby(["asignatura", "Identificación"]).size()
print("Alumnos con más de una fila (altas y bajas):", int((varias > 1).sum()), "-> vale el último estado (D2)")
""")

md("""
## 3. Consistencia entre fuentes

### 3.1 ¿Están los mismos alumnos?
""")
py("""
calidad.cobertura_ids()
""")
py("""
b = m.base(d)
print("Base por materia (inscriptos ∪ con nota, D2):")
b.groupby("asignatura").agg(base=("id_alumno", "size"), inscriptos=("inscripto", "sum"),
                            no_inscriptos=("inscripto", lambda s: int((~s).sum())))
""")
md("""
### 3.2 Participación contra trazabilidad

El reporte de participación trae "Interacciones" por alumno; la trazabilidad, un evento por fila. Si midieran
lo mismo deberían coincidir.
""")
py("""
pv = calidad.participacion_vs_trazabilidad()
pv1 = pv[pv["trazabilidad"] > 0]
print(f"Iguales: {100 * (pv1['participacion'] == pv1['trazabilidad']).mean():.1f} %  |  "
      f"cociente mediano participación / trazabilidad: {pv1['cociente'].median():.2f}  |  "
      f"Spearman: {pv1[['participacion', 'trazabilidad']].corr(method='spearman').iloc[0, 1]:.3f}")
fig = px.scatter(pv1, x="trazabilidad", y="participacion", color="asignatura", log_x=True, log_y=True, opacity=0.6,
                 title="Interacciones: reporte de participación vs. eventos de trazabilidad (escala log)")
fig.add_shape(type="line", x0=1, y0=1, x1=1500, y1=1500, line=dict(dash="dash", color="gray"))
fig.update_layout(height=380, legend_title=None)
fig.show()
""")
py("""
m.concordancia_tiempo(d)
""")
md("""
### 3.3 Matrícula contra actividad
""")
py("""
ins = calidad.inscripcion_vs_actividad(d)
print(f"Inscriptos que entraron antes de inscribirse: {(ins['dias_inscripcion_menos_ingreso'] > 0).sum()} de {len(ins)}")
fig = px.histogram(ins, x="dias_inscripcion_menos_ingreso", color="asignatura", nbins=40,
                   title="Días entre el primer ingreso al aula y la inscripción (positivo = se inscribió después)")
fig.update_layout(height=320, legend_title=None, bargap=0.05)
fig.show()
bajas = d.matricula[d.matricula["estado"].eq("Baja")]
bajas[["asignatura", "id_alumno", "fecha_inscripcion", "ultima_interaccion", "en_base"]]
""")
py("""
ips = calidad.ips_compartidas()
print(f"{len(ips)} IPs con más de un alumno; las 5 con más: {ips.head().tolist()}")
""")

md("""
## 4. Resumen de controles

La misma tabla sale de `python -m src.calidad`.
""")
py("""
calidad.chequeos(d)
""")
md("""@@CONCLUSIONES@@""")

nb = nbf.v4.new_notebook(cells=celdas, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"},
                                                 "language_info": {"name": "python"}})
if __name__ == "__main__":
    import sys
    conclusiones = Path(__file__).with_name("_conclusiones_01.md")
    texto = conclusiones.read_text(encoding="utf-8") if conclusiones.exists() else "## Conclusiones\n\n(pendiente)"
    for c in nb.cells:
        if c.source == "@@CONCLUSIONES@@":
            c.source = texto.strip()
    NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(RAIZ / "notebooks")}}).execute()
    nbf.write(nb, SALIDA)
    print("ok ->", SALIDA)
