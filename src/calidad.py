"""
Controles de calidad de datos entre fuentes (D69). Complementa a `src/limpieza.py`:
la limpieza mira cada tabla por separado (formatos, duplicados, nulos) y escribe
reports/calidad_datos.md; acá se controla que las fuentes cuenten la misma historia.

El análisis completo, con gráficos, está en notebooks/01_calidad_datos.ipynb; este
módulo deja los controles como código para que se puedan volver a correr cada vez
que llega un archivo nuevo.

Uso:
    from src import calidad
    calidad.chequeos()            # una fila por control: resultado, valor y qué implica
    calidad.observaciones_vs_nota()
    python -m src.calidad          (imprime la tabla)

Cada control devuelve:
    area, control, resultado ("OK" / "Atención"), valor (texto corto) y decision
    (qué hace el proyecto con eso). "Atención" no es un error del pipeline: es algo de
    los datos que hay que tener en cuenta al leer los indicadores.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src import metricas as m
from src.config import GOLD, SILVER

OK, ATENCION = "OK", "Atención"
ALUMNO = "Alumnos"


def _silver(tabla: str, silver: Path = SILVER) -> pd.DataFrame:
    return pd.read_parquet(Path(silver) / f"{tabla}.parquet")


def _alumnos(serie: pd.Series) -> set:
    return set(serie[serie.astype(str).str.startswith("ALU_")])


def _fila(area, control, ok, valor, decision) -> dict:
    return {"area": area, "control": control, "resultado": OK if ok else ATENCION, "valor": valor,
            "decision": decision}


# ---------------------------------------------------------------------------
# Controles con detalle (los usa el notebook)
# ---------------------------------------------------------------------------
def cobertura_ids(silver: Path = SILVER) -> pd.DataFrame:
    """Cuántos alumnos (ALU_) hay en cada fuente y cuántos faltan en cada una de las otras."""
    tz, pa = _silver("trazabilidad", silver), _silver("participacion", silver)
    ca, ma = _silver("calificaciones", silver), _silver("matriculados", silver)
    ids = {"trazabilidad": _alumnos(tz.loc[tz["Perfil"].eq(ALUMNO), "Usuario"]),
           "participacion": _alumnos(pa.loc[pa["Perfil"].eq(ALUMNO), "Usuario"]),
           "calificaciones": _alumnos(ca["Usuario"]), "matriculados": _alumnos(ma["Identificación"])}
    filas = [{"fuente": k, "alumnos": len(s), **{f"no estan en {o}": len(s - t) for o, t in ids.items() if o != k}}
             for k, s in ids.items()]
    return pd.DataFrame(filas).fillna(0)


def nombres_inconsistentes(silver: Path = SILVER) -> pd.DataFrame:
    """IDs que aparecen con más de un apellido o nombre entre trazabilidad, participación y notas."""
    partes = []
    for tabla in ["trazabilidad", "participacion", "calificaciones"]:
        t = _silver(tabla, silver)
        partes.append(t[["Usuario", "Apellido", "Nombre"]].drop_duplicates().assign(fuente=tabla))
    n = pd.concat(partes)
    distintos = n.groupby("Usuario")[["Apellido", "Nombre"]].nunique().max(axis=1)
    return n[n["Usuario"].isin(distintos[distintos > 1].index)].sort_values("Usuario")


def observaciones_vs_nota(silver: Path = SILVER) -> pd.DataFrame:
    """Por instrumento: rango de Nota (%) de los 'aprobada' y de los 'no aprobada'. Si se
    superponen, Observaciones no es un corte de la nota; si 'aprobada' baja de 60 %, el
    criterio del instrumento no es el de la materia."""
    ca = _silver("calificaciones", silver)
    ca = ca.assign(obs=ca["Observaciones"].astype(str).str.strip().str.lower())
    g = ca.pivot_table(index=["asignatura", "instrumento"], columns="obs", values="Nota (%)",
                       aggfunc=["min", "max", "size"])
    g.columns = [f"{a}_{b}".replace(" ", "_") for a, b in g.columns]
    g = g.reset_index()
    for c in ["min_aprobada", "max_no_aprobada"]:
        if c not in g:
            g[c] = np.nan
    g["se_superponen"] = g["max_no_aprobada"].ge(g["min_aprobada"]).fillna(False)
    return g


def notas_sin_rendicion(d: m.Datos) -> pd.DataFrame:
    """Notas (sin recuperatorios) sin el evento 'Realizar evaluación' del alumno en la trazabilidad."""
    from src.ml_abandono import _realizaciones   # import local: ml_abandono importa metricas
    c = d.calificaciones
    c = c[c["rindio"] & ~c["es_recuperatorio"].fillna(False).astype(bool)]
    x = c.merge(_realizaciones(d), on=["asignatura", "id_alumno", "id_instrumento"], how="left")
    return x.loc[x["rindio_el"].isna(), ["asignatura", "id_alumno", "id_instrumento", "instrumento", "nota_pct"]]


def participacion_vs_trazabilidad(silver: Path = SILVER) -> pd.DataFrame:
    """Por alumno y materia: interacciones según el reporte de participación y eventos en la trazabilidad."""
    tz, pa = _silver("trazabilidad", silver), _silver("participacion", silver)
    eventos = tz[tz["Perfil"].eq(ALUMNO)].groupby(["asignatura", "Usuario"]).size().rename("trazabilidad")
    pa = pa[pa["Perfil"].eq(ALUMNO)].assign(participacion=lambda t: pd.to_numeric(t["Interacciones"], errors="coerce"))
    x = pa.set_index(["asignatura", "Usuario"])[["participacion"]].join(eventos, how="outer").fillna(0)
    x["cociente"] = x["participacion"] / x["trazabilidad"].replace(0, np.nan)
    return x.reset_index()


def inscripcion_vs_actividad(d: m.Datos) -> pd.DataFrame:
    """Inscriptos (último estado Aceptada): fecha de inscripción contra su primer ingreso al aula."""
    t = d.matricula
    t = t[t["inscripto"]][["asignatura", "id_alumno", "estado", "fecha_inscripcion", "primera_interaccion"]].copy()
    t["dias_inscripcion_menos_ingreso"] = (t["fecha_inscripcion"] - t["primera_interaccion"]).dt.days
    return t


def ips_compartidas(silver: Path = SILVER) -> pd.Series:
    """Cantidad de alumnos distintos por IP (solo IPs con más de uno)."""
    tz = _silver("trazabilidad", silver)
    n = tz[tz["Perfil"].eq(ALUMNO)].groupby("IP Usuario")["Usuario"].nunique()
    return n[n > 1].sort_values(ascending=False)


# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
def chequeos(d: m.Datos | None = None, silver: Path = SILVER, gold: Path = GOLD) -> pd.DataFrame:
    """Una fila por control entre fuentes, con su resultado y qué decide el proyecto."""
    d = d if d is not None else m.cargar(gold)
    tz = _silver("trazabilidad", silver)
    al = tz[tz["Perfil"].eq(ALUMNO)]
    filas = []

    cob = cobertura_ids(silver).set_index("fuente")
    sin_traz = int(cob.loc["participacion", "no estan en trazabilidad"])
    filas.append(_fila("Identidad", "Alumnos del reporte de participación sin ningún evento en la trazabilidad",
                       sin_traz == 0, f"{sin_traz} de {cob.loc['participacion', 'alumnos']}",
                       "Participación lista a toda la cohorte (319); la base de cada materia es inscriptos ∪ con nota (D2)."))
    cal_sin_traz = int(cob.loc["calificaciones", "no estan en trazabilidad"])
    filas.append(_fila("Identidad", "Alumnos con nota que nunca entraron al aula", cal_sin_traz == 0,
                       str(cal_sin_traz), "Si hubiera, la nota no tendría actividad que la explique."))
    mat_sin = int(cob.loc["matriculados", "no estan en trazabilidad"])
    filas.append(_fila("Identidad", "Matriculados que nunca entraron al aula", mat_sin == 0, str(mat_sin),
                       "Quedan en la base con todo en 0 (Libre) y alimentan la alerta de inscriptos sin actividad."))
    inc = nombres_inconsistentes(silver)["Usuario"].nunique()
    filas.append(_fila("Identidad", "IDs con más de un nombre entre fuentes", inc == 0, str(inc),
                       "El ID es la clave: los nombres solo se muestran."))

    ca = _silver("calificaciones", silver)
    obs = ca["Observaciones"].astype(str).str.strip().str.lower()
    raras = int((obs.eq("aprobada") & ca["Nota (%)"].lt(60)).sum() + (obs.eq("no aprobada") & ca["Nota (%)"].ge(60)).sum())
    filas.append(_fila("Notas", "'Observaciones' no coincide con el corte de 60 % de la nota", raras == 0,
                       f"{raras} de {len(ca)} notas (cada instrumento tiene su propio criterio)",
                       "No se usa Observaciones: la condición sale de la nota y los cortes de ESQUEMA (D16-D17)."))
    maximos = int(_silver("calificaciones", silver).groupby("instrumento")["Nota máxima"].nunique().max())
    filas.append(_fila("Notas", "Puntaje máximo distinto dentro de un mismo instrumento", maximos <= 1,
                       f"{maximos} máximo(s) por instrumento", "El máximo del instrumento sale del denominador de la nota."))
    sr = notas_sin_rendicion(d)
    filas.append(_fila("Notas", "Notas sin el evento 'Realizar evaluación' del alumno", sr.empty,
                       f"{len(sr)} de {int(d.calificaciones['rindio'].sum())}",
                       "Para fechar esas notas se usa la última realización del instrumento (D64)."))

    pv = participacion_vs_trazabilidad(silver)
    pv = pv[pv["trazabilidad"] > 0]
    iguales = 100 * (pv["participacion"] == pv["trazabilidad"]).mean()
    rho = pv[["participacion", "trazabilidad"]].corr(method="spearman").iloc[0, 1]
    filas.append(_fila("Actividad", "Interacciones del reporte de participación contra eventos de la trazabilidad",
                       iguales > 90, f"iguales en {iguales:.0f} %, cociente mediano {pv['cociente'].median():.2f}, "
                       f"ρ = {rho:.2f}",
                       "Miden lo mismo con otra regla de conteo: la actividad se calcula siempre con la trazabilidad."))
    inicio = al["Fecha"].min()
    previos = int((tz["Fecha"] < inicio).sum())
    filas.append(_fila("Actividad", "Eventos anteriores al primer ingreso de un alumno", True,
                       f"{previos} (docentes armando el aula desde el {tz['Fecha'].min():%d/%m})",
                       "Son de Tutores y Coordinadores: van a otros_perfiles_interaccion (D4)."))
    s = d.sesiones[d.sesiones["en_base"]]
    filas.append(_fila("Actividad", "Sesiones de menos de 1 minuto", True,
                       f"{100 * (s['duracion_min'] < 1).mean():.0f} % (mediana {s['duracion_min'].median():.1f} min)",
                       "Una sesión de un solo evento dura 0: los minutos subestiman el tiempo real."))
    ips = ips_compartidas(silver)
    filas.append(_fila("Actividad", "IPs usadas por más de un alumno", True,
                       f"{len(ips)} IPs, hasta {int(ips.max()) if len(ips) else 0} alumnos en una",
                       "Probablemente redes de la universidad o de proveedores: la IP no identifica a nadie."))

    ins = inscripcion_vs_actividad(d)
    antes = int((ins["dias_inscripcion_menos_ingreso"] > 0).sum())
    filas.append(_fila("Matrícula", "Inscriptos que entraron al aula antes de su fecha de inscripción", antes == 0,
                       f"{antes} de {len(ins)}",
                       "La fecha de inscripción no marca el inicio de la cursada: el inicio sale del primer evento."))
    mt = d.matricula
    bajas = mt[mt["estado"].eq("Baja")]
    activas = int((bajas["ultima_interaccion"] > bajas["fecha_inscripcion"]).sum())
    filas.append(_fila("Matrícula", "Bajas con actividad posterior a la fecha registrada", activas == 0,
                       f"{activas} de {len(bajas)}",
                       "La fecha de una baja puede ser la de la inscripción original y la baja no frena el acceso "
                       "al aula: no se usa como abandono (D67), el abandono sale de la actividad."))
    return pd.DataFrame(filas)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 90)
    print(chequeos().to_string(index=False))
