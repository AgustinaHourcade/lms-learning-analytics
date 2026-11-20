"""
Cursadas sintéticas para probar el predictor de abandono (D67).

Hay una sola cursada real, así que para ver qué tan robusto es el modelo frente a
cohortes distintas se arman cursadas "parecidas" a partir de la real, cambiándole la
historia a una parte de los alumnos:

  * abandono inyectado: desde un día al azar (entre el día 18 y el 70 de la cursada) el
    alumno no vuelve a entrar, en una materia o en todas (60 %), y lo que iba a rendir
    después queda sin rendir (nota 0);
  * pausa inyectada: el alumno no entra entre 15 y 30 días y después vuelve; lo que iba a
    rendir en ese lapso queda sin rendir.

Limitación: los abandonos inyectados son bruscos (sin la caída previa de actividad que
tienen los reales) y los alumnos son los mismos. Sirve para medir robustez, no para
estimar cómo le iría con otra cohorte real.

Uso:
    from src import simulacion
    d2, cambios = simulacion.cursada_sintetica(d, p_abandono=0.25, p_pausa=0.10, semilla=1)
    ab.dataset(d2)    # mismas funciones que con los datos reales
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from src import metricas as m

CLAVES = ["asignatura", "id_alumno"]
DIAS_ABANDONO = (18, 70)       # día de la cursada en que empieza el abandono inyectado
DIAS_PAUSA = (18, 55)          # día en que empieza la pausa
LARGO_PAUSA = (15, 31)         # días que dura la pausa (el tope no se incluye)
TODAS_LAS_MATERIAS = 0.6       # probabilidad de que el abandono sea en todas sus materias


def cursada_sintetica(d: m.Datos, p_abandono: float = 0.0, p_pausa: float = 0.0,
                      semilla: int = 0) -> tuple[m.Datos, pd.DataFrame]:
    """Devuelve (datos modificados, cambios). `cambios` tiene una fila por (materia, alumno)
    modificado: tipo ("abandono" / "pausa") y el período borrado [desde, hasta)."""
    from src.ml_abandono import _realizaciones, fin_datos   # import local: evita un ciclo

    rng = np.random.default_rng(semilla)
    inicio = d.interacciones["fecha"].min().normalize()
    fin = fin_datos(d) + pd.Timedelta(days=1)
    pares = m.base(d)[CLAVES].drop_duplicates()
    cambios = []
    for alumno, mats in pares.groupby("id_alumno")["asignatura"]:
        mats = mats.tolist()
        u = rng.random()
        if u < p_abandono:
            desde = inicio + pd.Timedelta(days=int(rng.integers(*DIAS_ABANDONO)))
            elegidas = mats if rng.random() < TODAS_LAS_MATERIAS else [mats[int(rng.integers(len(mats)))]]
            cambios += [(s, alumno, "abandono", desde, fin) for s in elegidas]
        elif u < p_abandono + p_pausa:
            desde = inicio + pd.Timedelta(days=int(rng.integers(*DIAS_PAUSA)))
            hasta = desde + pd.Timedelta(days=int(rng.integers(*LARGO_PAUSA)))
            cambios += [(s, alumno, "pausa", desde, hasta) for s in mats]
    c = pd.DataFrame(cambios, columns=[*CLAVES, "tipo", "desde", "hasta"])
    if c.empty:
        return d, c

    def borrar(t: pd.DataFrame, col: str) -> pd.DataFrame:
        x = t[CLAVES + [col]].merge(c[CLAVES + ["desde", "hasta"]], on=CLAVES, how="left")
        quitar = (x["desde"].notna() & (x[col] >= x["desde"]) & (x[col] < x["hasta"])).to_numpy()
        return t[~quitar]

    # lo que iba a rendir dentro del período borrado queda sin rendir
    r = _realizaciones(d).merge(c, on=CLAVES)
    perdidas = r.loc[(r["rindio_el"] >= r["desde"]) & (r["rindio_el"] < r["hasta"]), CLAVES + ["id_instrumento"]]
    cal = d.calificaciones.merge(perdidas.assign(_perdida=True), on=CLAVES + ["id_instrumento"], how="left")
    perdida = cal["_perdida"].eq(True)
    cal.loc[perdida, ["rindio", "rindio_recuperatorio"]] = False
    cal.loc[perdida, ["nota_obtenida", "puntos", "puntos_sin_recuperatorio", "nota_pct"]] = 0.0
    nuevo = dataclasses.replace(d, interacciones=borrar(d.interacciones, "fecha_hora"),
                                sesiones=borrar(d.sesiones, "inicio"), calificaciones=cal.drop(columns="_perdida"))
    return nuevo, c
