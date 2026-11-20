"""
ETAPA 3 - Métricas: GOLD -> KPIs para los dashboards (D29)

Gold guarda hechos que no dependen de la fecha de corte. Este módulo calcula
todo lo que SÍ depende de ella. Las páginas de Streamlit solo llaman a estas
funciones: no calculan nada por su cuenta, así todos ven los mismos números.

Todas las funciones reciben los mismos parámetros:
  d               los datos de gold, cargados una vez con `cargar()`
  fecha_corte     día de corte (inclusive). Por defecto, FECHA_CORTE_DEFECTO.
                  Acepta "2025-10-24", date o Timestamp.
  asignatura      nombre de la materia, una lista de materias o None (= todas)
  umbral          días sin entrar a partir de los cuales un alumno es inactivo
  desde           (algunas) inicio del rango de fechas, para los filtros

Reglas (ver docs/decisiones.md):
  * Población: la base de alumnos de cada materia (D11), solo perfil Alumnos (D10).
  * Un instrumento está disponible si su fecha (D18) es <= la fecha de corte.
    El recuperatorio que reemplaza se aplica solo si su fecha ya pasó (D34).
  * Nota final = Σ puntos / Σ máximos de lo disponible × 100; Álgebra × 120 (D17).
  * Activo = entró en los últimos `umbral` días; Inactivo = entró alguna vez,
    pero hace más; Sin actividad = nunca entró hasta la fecha de corte (D35).
  * El reporte de participación (avance, tiempo estimado, foros) es una foto
    a la fecha de exportación: no se puede recortar por fecha (D36).

Probar desde la raíz:
    python -m src.metricas
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from src.config import (CONDICIONES, DIAS_DESCONECTADO, DIAS_REGRESO, ESQUEMA, FECHA_CORTE_DEFECTO, GOLD,
                        SIN_EVALUACIONES, UMBRAL_INACTIVIDAD_DIAS)

ACTIVO, INACTIVO, SIN_ACTIVIDAD = "Activo", "Inactivo", "Sin actividad"
ESTADOS_ACTIVIDAD = [ACTIVO, INACTIVO, SIN_ACTIVIDAD]
# D54: los inactivos se parten en dos tramos según hace cuánto que no entran.
ENFRIANDOSE, DESCONECTADO = "Enfriándose", "Desconectado"
TRAMOS_ACTIVIDAD = [ACTIVO, ENFRIANDOSE, DESCONECTADO, SIN_ACTIVIDAD]
# Movimientos de la última semana (D54)
CRUZO_UMBRAL, VOLVIO, ENTRA_NO_RINDE, NUNCA_ENTRO = (
    "Cruzó el umbral", "Volvió", "Entra y no rinde", "Nunca entró")
MOVIMIENTOS = [CRUZO_UMBRAL, VOLVIO, ENTRA_NO_RINDE, NUNCA_ENTRO]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Variables de actividad que se cruzan con la nota (dashboard 5).
VARIABLES_CRUCE = {
    "minutos": "Minutos en la plataforma (sesiones)",
    "sesiones": "Sesiones",
    "eventos": "Interacciones",
    "dias_activos": "Días con actividad",
    "semanas_activas": "Semanas con actividad",
    "tiempo_uso_min": "Tiempo estimado de uso (reporte)",
    "avance": "Avance (%) (reporte)",
}


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
@dataclass
class Datos:
    """Las tablas de gold que usan las métricas. `version` cambia cada vez que
    se regenera gold: sirve como clave de caché en la app."""
    alumnos: pd.DataFrame
    instrumentos: pd.DataFrame
    interacciones: pd.DataFrame
    sesiones: pd.DataFrame
    calificaciones: pd.DataFrame
    participacion: pd.DataFrame
    matricula: pd.DataFrame
    version: str = ""


TABLAS = {"alumnos": "dim_alumno", "instrumentos": "dim_instrumento", "interacciones": "fact_interaccion",
          "sesiones": "fact_sesion", "calificaciones": "fact_calificacion", "participacion": "fact_participacion",
          "matricula": "fact_matricula"}


def cargar(gold: Path = GOLD) -> Datos:
    archivos = {campo: gold / f"{tabla}.parquet" for campo, tabla in TABLAS.items()}
    faltan = [p.name for p in archivos.values() if not p.exists()]
    if faltan:
        raise FileNotFoundError(f"Faltan tablas de gold ({', '.join(faltan)}). Correr: python -m src.pipeline")
    version = str(max(p.stat().st_mtime_ns for p in archivos.values()))
    return Datos(**{campo: pd.read_parquet(p) for campo, p in archivos.items()}, version=version)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def fecha_de_corte(fecha=None) -> pd.Timestamp:
    """Día de corte a las 00:00. Se incluye todo ese día."""
    return pd.Timestamp(FECHA_CORTE_DEFECTO if fecha is None else fecha).normalize()


def _fin_del_dia(corte: pd.Timestamp) -> pd.Timestamp:
    return corte + pd.Timedelta(days=1)


def _materias(asignatura) -> list[str]:
    if asignatura is None:
        return list(ESQUEMA)
    lista = [asignatura] if isinstance(asignatura, str) else list(asignatura)
    desconocidas = [a for a in lista if a not in ESQUEMA]
    if desconocidas:
        raise ValueError(f"Materia desconocida: {desconocidas}. Opciones: {list(ESQUEMA)}")
    return lista


def _filtrar(df: pd.DataFrame, asignatura) -> pd.DataFrame:
    return df[df["asignatura"].isin(_materias(asignatura))]


def _eventos(d: Datos, fecha_corte, asignatura, desde=None) -> pd.DataFrame:
    """Interacciones de alumnos de la base entre `desde` y la fecha de corte."""
    i = _filtrar(d.interacciones, asignatura)
    i = i[i["en_base"] & (i["fecha_hora"] < _fin_del_dia(fecha_de_corte(fecha_corte)))]
    if desde is not None:
        i = i[i["fecha_hora"] >= pd.Timestamp(desde).normalize()]
    return i


def _sesiones(d: Datos, fecha_corte, asignatura, desde=None) -> pd.DataFrame:
    s = _filtrar(d.sesiones, asignatura)
    s = s[s["en_base"] & (s["inicio"] < _fin_del_dia(fecha_de_corte(fecha_corte)))]
    if desde is not None:
        s = s[s["inicio"] >= pd.Timestamp(desde).normalize()]
    return s


def base(d: Datos, asignatura=None) -> pd.DataFrame:
    """Base de alumnos (D11): una fila por alumno y materia."""
    m = _filtrar(d.matricula, asignatura)
    return m.loc[m["en_base"], ["asignatura", "id_alumno", "inscripto", "en_matriculados", "estado"]] \
            .reset_index(drop=True)


def condicion(nota: pd.Series, asignatura: pd.Series) -> pd.Series:
    """Libre / Regular / Promociona según los cortes del ESQUEMA de cada materia."""
    regular = asignatura.map(lambda a: ESQUEMA[a]["cortes"]["Regular"])
    promociona = asignatura.map(lambda a: ESQUEMA[a]["cortes"]["Promociona"])
    n = nota.round(2)
    resultado = np.select([n.isna(), n >= promociona, n >= regular], [SIN_EVALUACIONES, "Promociona", "Regular"],
                          default="Libre")
    return pd.Series(resultado, index=nota.index)


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)).lower()


# ---------------------------------------------------------------------------
# Calificaciones
# ---------------------------------------------------------------------------
def notas_instrumento(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Una fila por alumno de la base × instrumento disponible a la fecha de corte.
    `puntos_corte` aplica el recuperatorio solo si ya se tomó a esa fecha (D34)."""
    corte = fecha_de_corte(fecha_corte)
    c = _filtrar(d.calificaciones, asignatura)
    c = c[c["fecha_instrumento"].isna() | (c["fecha_instrumento"] <= corte)].copy()
    aplica = c["rindio_recuperatorio"] & (c["fecha_recuperatorio"].isna() | (c["fecha_recuperatorio"] <= corte))
    c["recuperatorio_aplicado"] = aplica
    c["puntos_corte"] = c["puntos"].where(aplica, c["puntos_sin_recuperatorio"])
    c["nota_pct_corte"] = (c["puntos_corte"] / c["puntaje_maximo"] * 100).round(2)
    return c.reset_index(drop=True)


def nota_final(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Nota y condición de cada alumno de la base a la fecha de corte (D16-D17).
      puntos / puntos_posibles  lo acumulado y el máximo de lo disponible
      nota_final                en la escala de la materia (Álgebra 120, resto 100)
      nota_pct                  la misma nota sobre 100, para comparar materias
    Si todavía no hay instrumentos, la nota queda vacía y la condición es
    'Sin evaluaciones'."""
    c = notas_instrumento(d, fecha_corte, asignatura)
    c = c[c["cuenta_en_final"]]
    # rendido = tiene nota en el instrumento o en su recuperatorio (hay alumnos
    # que solo rindieron el recuperatorio)
    c = c.assign(con_nota=c["rindio"] | c["recuperatorio_aplicado"])
    g = (c.groupby(["asignatura", "id_alumno"])
          .agg(puntos=("puntos_corte", "sum"), puntos_posibles=("puntaje_maximo", "sum"),
               instrumentos=("id_instrumento", "size"), rendidos=("con_nota", "sum"))
          .reset_index())
    df = base(d, asignatura)[["asignatura", "id_alumno", "inscripto"]].merge(g, how="left")
    df[["instrumentos", "rendidos"]] = df[["instrumentos", "rendidos"]].fillna(0).astype(int)
    escala = df["asignatura"].map(lambda a: ESQUEMA[a]["total_max"])
    df["nota_pct"] = (df["puntos"] / df["puntos_posibles"] * 100).round(2)
    df["nota_final"] = (df["puntos"] / df["puntos_posibles"] * escala).round(2)
    df["escala"] = escala
    df["condicion"] = condicion(df["nota_final"], df["asignatura"])
    return df


def promedio_por_instrumento(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Promedio de cada instrumento SOLO entre quienes lo rindieron (D22). La
    nota es la original: el recuperatorio aparece como un instrumento aparte."""
    c = notas_instrumento(d, fecha_corte, asignatura)
    c = c.assign(pct=c["nota_obtenida"] / c["puntaje_maximo"] * 100,
                 aprobada=c["observaciones"].eq("aprobada"))
    r = c[c["rindio"]]
    g = (r.groupby(["asignatura", "id_instrumento"])
          .agg(rindieron=("id_alumno", "size"), promedio_pct=("pct", "mean"), mediana_pct=("pct", "median"),
               minimo_pct=("pct", "min"), maximo_pct=("pct", "max"), pct_aprobada=("aprobada", "mean"))
          .reset_index())
    inst = d.instrumentos[["id_instrumento", "instrumento", "orden", "puntaje_maximo", "fecha_instrumento",
                           "es_recuperatorio"]]
    tot = c.groupby(["asignatura", "id_instrumento"]).size().rename("base").reset_index()
    df = tot.merge(inst, on="id_instrumento").merge(g, how="left")
    df["rindieron"] = df["rindieron"].fillna(0).astype(int)
    df["pct_rindio"] = (df["rindieron"] / df["base"] * 100).round(1)
    df["pct_aprobada"] = (df["pct_aprobada"] * 100).round(1)
    for col in ["promedio_pct", "mediana_pct", "minimo_pct", "maximo_pct"]:
        df[col] = df[col].round(2)
    return df.sort_values(["asignatura", "orden"]).reset_index(drop=True)


def notas_rendidas(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Una fila por alumno × instrumento que RINDIÓ (D22), con la nota original
    sobre 100. Es el detalle de promedio_por_instrumento: sirve para los
    boxplots del dashboard de Rendimiento (D61). El recuperatorio va aparte."""
    c = notas_instrumento(d, fecha_corte, asignatura)
    r = c[c["rindio"]].merge(d.instrumentos[["id_instrumento", "orden"]], on="id_instrumento")
    r = r.assign(nota_pct_instrumento=(r["nota_obtenida"] / r["puntaje_maximo"] * 100).round(2))
    columnas = ["asignatura", "id_alumno", "inscripto", "id_instrumento", "instrumento", "orden",
                "es_recuperatorio", "fecha_instrumento", "nota_obtenida", "puntaje_maximo",
                "nota_pct_instrumento", "observaciones"]
    return r[columnas].sort_values(["asignatura", "orden", "id_alumno"]).reset_index(drop=True)


def evolucion_condicion(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Distribución por condición de cada materia el día de cada evaluación ya
    tomada a la fecha de corte (D61): muestra cómo se mueve el reparto Libre /
    Regular / Promociona a medida que se suman instrumentos (incluido el
    recuperatorio, que cambia notas sin sumar un instrumento)."""
    partes = []
    for (materia, fecha), ev in fechas_evaluaciones(d, fecha_corte, asignatura).groupby(
            ["asignatura", "fecha_instrumento"]):
        dist = distribucion_condicion(d, fecha, materia)
        partes.append(dist.assign(fecha=fecha, instrumentos=" + ".join(ev["instrumento"])))
    if not partes:
        return pd.DataFrame(columns=["asignatura", "condicion", "alumnos", "pct", "fecha", "instrumentos"])
    return pd.concat(partes, ignore_index=True).sort_values(["asignatura", "fecha"]).reset_index(drop=True)


def distribucion_condicion(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Cantidad y % de alumnos por condición y materia (las tres condiciones
    aparecen siempre, aunque tengan 0)."""
    n = nota_final(d, fecha_corte, asignatura)
    categorias = CONDICIONES + ([SIN_EVALUACIONES] if n["condicion"].eq(SIN_EVALUACIONES).any() else [])
    tabla = (pd.crosstab(n["asignatura"], pd.Categorical(n["condicion"], categorias), dropna=False)
               .reindex(_materias(asignatura), fill_value=0))
    largo = tabla.stack().rename("alumnos").reset_index()
    largo.columns = ["asignatura", "condicion", "alumnos"]
    largo["pct"] = (largo["alumnos"] / largo.groupby("asignatura")["alumnos"].transform("sum") * 100).round(1)
    return largo


def resumen_calificaciones(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Por materia: nota promedio de la base (con los 0) y de quienes rindieron algo."""
    n = nota_final(d, fecha_corte, asignatura)
    rindio = n[n["rendidos"] > 0]
    df = n.groupby("asignatura").agg(alumnos=("id_alumno", "size"), instrumentos=("instrumentos", "max"),
                                     nota_promedio=("nota_final", "mean"), nota_mediana=("nota_final", "median"),
                                     nota_pct_promedio=("nota_pct", "mean"))
    df["con_alguna_nota"] = rindio.groupby("asignatura").size()
    df["nota_promedio_rindieron"] = rindio.groupby("asignatura")["nota_final"].mean()
    for cond in CONDICIONES:
        df[f"pct_{cond.lower()}"] = n.groupby("asignatura")["condicion"].apply(lambda s: (s == cond).mean() * 100)
    df["escala"] = [ESQUEMA[a]["total_max"] for a in df.index]
    df["con_alguna_nota"] = df["con_alguna_nota"].fillna(0).astype(int)
    return df.round(2).reset_index()


# ---------------------------------------------------------------------------
# Actividad por alumno (trazabilidad) y tabla maestra
# ---------------------------------------------------------------------------
def actividad_alumnos(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                      desde=None) -> pd.DataFrame:
    """Una fila por alumno de la base con su actividad hasta la fecha de corte.
    estado_actividad: Activo (entró en los últimos `umbral` días), Inactivo
    (entró alguna vez, pero hace más) o Sin actividad (nunca entró) (D35).
    tramo_actividad: lo mismo, pero los inactivos se separan en Enfriándose
    (hasta DIAS_DESCONECTADO días sin entrar) y Desconectado (más) (D54)."""
    corte = fecha_de_corte(fecha_corte)
    ev = _eventos(d, corte, asignatura, desde)
    ev = ev.assign(semana=ev["fecha"] - pd.to_timedelta(ev["fecha"].dt.day_of_week, unit="D"))
    a = (ev.groupby(["asignatura", "id_alumno"])
           .agg(eventos=("id_evento", "size"), dias_activos=("fecha", "nunique"),
                semanas_activas=("semana", "nunique"), primera_interaccion=("fecha_hora", "min"),
                ultima_interaccion=("fecha_hora", "max"))
           .reset_index())
    s = (_sesiones(d, corte, asignatura, desde).groupby(["asignatura", "id_alumno"])
           .agg(sesiones=("id_sesion", "size"), minutos=("duracion_min", "sum")).reset_index())
    df = base(d, asignatura)[["asignatura", "id_alumno", "inscripto"]].merge(a, how="left").merge(s, how="left")
    for col in ["eventos", "dias_activos", "semanas_activas", "sesiones"]:
        df[col] = df[col].fillna(0).astype(int)
    df["minutos"] = df["minutos"].fillna(0).round(1)
    df["minutos_por_sesion"] = (df["minutos"] / df["sesiones"].replace(0, np.nan)).round(1)
    df["dias_sin_actividad"] = (corte - df["ultima_interaccion"].dt.normalize()).dt.days.astype("Int64")
    df["estado_actividad"] = np.select(
        [df["eventos"].eq(0), df["dias_sin_actividad"].le(umbral).fillna(False).astype(bool)],
        [SIN_ACTIVIDAD, ACTIVO], default=INACTIVO)
    df["activo"] = df["estado_actividad"].eq(ACTIVO)
    lejos = df["dias_sin_actividad"].gt(max(DIAS_DESCONECTADO, umbral)).fillna(False).astype(bool)
    df["tramo_actividad"] = df["estado_actividad"].where(
        df["estado_actividad"].ne(INACTIVO), np.where(lejos, DESCONECTADO, ENFRIANDOSE))
    return df


COLUMNAS_REPORTE = {"avance": "avance", "tiempo_uso_min": "tiempo_uso_min",
                    "foros_cantidad_de_intervenciones_del_usuario": "intervenciones_foros",
                    "foros_temas_de_debate_con_intervencion": "temas_foro_con_intervencion",
                    "encuestas_cargados": "encuestas_respondidas", "emails_enviados": "emails_enviados"}


def tabla_alumnos(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS) -> pd.DataFrame:
    """Tabla maestra: una fila por alumno de la base con nota, condición,
    actividad (a la fecha de corte) y el reporte de participación (foto, D36).
    La usan Notas vs. Participación, Ficha individual, Alertas y el ML."""
    nota = nota_final(d, fecha_corte, asignatura).drop(columns="inscripto")
    act = actividad_alumnos(d, fecha_corte, asignatura, umbral).drop(columns="inscripto")
    rep = d.participacion[["asignatura", "id_alumno", *COLUMNAS_REPORTE]].rename(columns=COLUMNAS_REPORTE)
    nombres = d.alumnos[["id_alumno", "apellido", "nombre", "nombre_completo"]]
    df = (base(d, asignatura).merge(nombres, on="id_alumno", how="left")
            .merge(nota, how="left").merge(act, how="left").merge(rep, how="left"))
    return df.sort_values(["asignatura", "apellido", "nombre"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Participación
# ---------------------------------------------------------------------------
def resumen_participacion(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                          desde=None) -> pd.DataFrame:
    """Por materia: sesiones y minutos promedio por alumno, activos vs. inactivos
    y, del reporte de participación, avance y tiempo estimado promedio."""
    t = tabla_alumnos(d, fecha_corte, asignatura, umbral)
    if desde is not None:  # con rango de fechas, la actividad se recalcula en ese rango
        act = actividad_alumnos(d, fecha_corte, asignatura, umbral, desde)
        cols = ["sesiones", "minutos", "eventos"]
        t = t.drop(columns=cols).merge(act[["asignatura", "id_alumno", *cols]], how="left")
    g = t.groupby("asignatura")
    df = pd.DataFrame({
        "alumnos": g.size(),
        "sesiones_promedio": g["sesiones"].mean(), "sesiones_mediana": g["sesiones"].median(),
        "minutos_promedio": g["minutos"].mean(), "eventos_promedio": g["eventos"].mean(),
        "tiempo_uso_promedio_min": g["tiempo_uso_min"].mean(), "avance_promedio": g["avance"].mean(),
        "pct_con_intervencion_foros": g["intervenciones_foros"].apply(lambda s: (s.fillna(0) > 0).mean() * 100),
    })
    for estado in ESTADOS_ACTIVIDAD:
        clave = estado.lower().replace(" ", "_")
        df[clave] = g["estado_actividad"].apply(lambda s: (s == estado).sum())
    df["pct_activos"] = df["activo"] / df["alumnos"] * 100
    return df.astype(float).round(2).reset_index()


def evolucion_actividad(d: Datos, fecha_corte=None, asignatura=None, frecuencia: str = "W",
                        desde=None, id_alumno: str | None = None) -> pd.DataFrame:
    """Actividad por período ('D' día, 'W' semana que empieza el lunes, 'M' mes):
    alumnos activos, interacciones, sesiones y minutos. Los períodos sin
    actividad aparecen con 0, así las líneas no saltan."""
    if frecuencia not in {"D", "W", "M"}:
        raise ValueError("frecuencia tiene que ser 'D', 'W' o 'M'")
    corte = fecha_de_corte(fecha_corte)
    ev, se = _eventos(d, corte, asignatura, desde), _sesiones(d, corte, asignatura, desde)
    if id_alumno is not None:
        ev, se = ev[ev["id_alumno"] == id_alumno], se[se["id_alumno"] == id_alumno]

    def periodo(f: pd.Series) -> pd.Series:
        if frecuencia == "D":
            return f.dt.normalize()
        if frecuencia == "W":
            return f.dt.normalize() - pd.to_timedelta(f.dt.day_of_week, unit="D")
        return f.dt.to_period("M").dt.to_timestamp()

    a = (ev.assign(periodo=periodo(ev["fecha_hora"])).groupby(["asignatura", "periodo"])
           .agg(alumnos_activos=("id_alumno", "nunique"), eventos=("id_evento", "size")))
    s = (se.assign(periodo=periodo(se["inicio"])).groupby(["asignatura", "periodo"])
           .agg(sesiones=("id_sesion", "size"), minutos=("duracion_min", "sum")))
    df = a.join(s, how="outer")
    inicio = pd.Timestamp(desde).normalize() if desde is not None else d.interacciones["fecha"].min()
    periodos = periodo(pd.Series(pd.date_range(inicio, corte, freq="D"))).unique()
    materias = _materias(asignatura) if id_alumno is None else sorted(ev["asignatura"].unique())
    grilla = pd.MultiIndex.from_product([materias, periodos], names=["asignatura", "periodo"])
    df = df.reindex(grilla, fill_value=0).fillna(0)
    df[["alumnos_activos", "eventos", "sesiones"]] = df[["alumnos_activos", "eventos", "sesiones"]].astype(int)
    df["minutos"] = df["minutos"].round(1)
    return df.reset_index()


def reporte_participacion(d: Datos, asignatura=None) -> pd.DataFrame:
    """El reporte de participación de los alumnos de la base, tal cual (foto a
    la fecha de exportación, D36): avance, tiempo estimado, foros, encuestas."""
    p = _filtrar(d.participacion, asignatura)
    return p[p["en_base"]].merge(d.alumnos[["id_alumno", "nombre_completo"]], on="id_alumno", how="left") \
                          .reset_index(drop=True)


def evolucion_participacion(d: Datos, fecha_corte=None, asignatura=None, frecuencia: str = "W",
                            desde=None) -> pd.DataFrame:
    """evolucion_actividad() más las mismas series relativas al tamaño de la base
    de cada materia (D53): % de la base que entró en el período e interacciones,
    sesiones y minutos por alumno. Sirve para comparar materias de distinto tamaño."""
    df = evolucion_actividad(d, fecha_corte, asignatura, frecuencia, desde)
    n = df["asignatura"].map(base(d, asignatura).groupby("asignatura").size())
    df["pct_base_activa"] = (df["alumnos_activos"] / n * 100).round(2)
    for col in ["eventos", "sesiones", "minutos"]:
        df[f"{col}_por_alumno"] = (df[col] / n).round(2)
    return df


def participacion_alumnos(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                          desde=None) -> pd.DataFrame:
    """Una fila por alumno de la base: actividad entre `desde` y la fecha de corte
    (trazabilidad) y el reporte de participación (foto, D36). Es tabla_alumnos()
    sin las notas, pero respetando el rango de fechas del dashboard (D53)."""
    act = actividad_alumnos(d, fecha_corte, asignatura, umbral, desde)
    rep = d.participacion[["asignatura", "id_alumno", *COLUMNAS_REPORTE]].rename(columns=COLUMNAS_REPORTE)
    nombres = d.alumnos[["id_alumno", "apellido", "nombre", "nombre_completo"]]
    df = act.merge(nombres, on="id_alumno", how="left").merge(rep, how="left")
    return df.sort_values(["asignatura", "apellido", "nombre"]).reset_index(drop=True)


def movimientos_semana(d: Datos, fecha_corte=None, asignatura=None,
                       umbral: int = UMBRAL_INACTIVIDAD_DIAS) -> pd.DataFrame:
    """Qué cambió en los últimos 7 días antes de la fecha de corte (D54). Una fila
    por alumno y movimiento (un alumno puede aparecer en más de uno):
      Cruzó el umbral   activo hace una semana, inactivo ahora
      Volvió            activo ahora y, una semana antes, llevaba DIAS_REGRESO
                        días o más sin entrar (no cuenta a quien entra por primera vez)
      Entra y no rinde  activo ahora, con instrumentos tomados y ninguno rendido
      Nunca entró       sin ninguna interacción en toda la cursada
    Siempre mira la cursada completa: no depende del período del dashboard."""
    corte = fecha_de_corte(fecha_corte)
    ahora = tabla_alumnos(d, corte, asignatura, umbral)
    antes = actividad_alumnos(d, corte - pd.Timedelta(days=7), asignatura, umbral)
    df = ahora.merge(antes[["asignatura", "id_alumno", "activo", "dias_sin_actividad", "eventos"]]
                     .rename(columns=lambda c: c if c in ("asignatura", "id_alumno") else f"{c}_antes"),
                     how="left")
    lejos_antes = df["dias_sin_actividad_antes"].ge(DIAS_REGRESO).fillna(False)
    reglas = {
        CRUZO_UMBRAL: df["activo_antes"].fillna(False).astype(bool) & ~df["activo"],
        VOLVIO: df["activo"] & lejos_antes.astype(bool),
        ENTRA_NO_RINDE: df["activo"] & df["instrumentos"].gt(0) & df["rendidos"].eq(0),
        NUNCA_ENTRO: df["eventos"].eq(0),
    }
    columnas = ["asignatura", "id_alumno", "nombre_completo", "dias_sin_actividad", "ultima_interaccion",
                "eventos", "rendidos", "instrumentos", "inscripto"]
    partes = [df.loc[filtro, columnas].assign(movimiento=nombre) for nombre, filtro in reglas.items()]
    out = pd.concat(partes, ignore_index=True)
    out["movimiento"] = pd.Categorical(out["movimiento"], MOVIMIENTOS)
    return out[["movimiento", *columnas]].sort_values(["movimiento", "asignatura", "nombre_completo"])                                           .reset_index(drop=True)


# Herramientas del reporte de participación: (uso del alumno, recursos que ofrece el aula).
HERRAMIENTAS = {
    "Foros": ("foros_cantidad_de_intervenciones_del_usuario", "foros_cantidad_temas_de_debate"),
    "Encuestas": ("encuestas_cargados", "encuestas_cantidad"),
    "Correo interno": ("emails_enviados", None),
    "Archivos": ("archivos_cargados", "archivos_cantidad"),
    "Wikis": ("wikis_cargados", "wikis_cantidad"),
}


def uso_herramientas(d: Datos, asignatura=None) -> pd.DataFrame:
    """Por materia y herramienta (foto al 24/10, D36): cuántos recursos ofrece el
    aula (temas de foro, encuestas...), cuántos alumnos de la base la usaron al
    menos una vez, qué % son y cuántos usos hubo en total (D53)."""
    p = reporte_participacion(d, asignatura)
    filas = []
    for asig, g in p.groupby("asignatura"):
        for herramienta, (uso, recursos) in HERRAMIENTAS.items():
            usos = g[uso].fillna(0)
            filas.append({"asignatura": asig, "herramienta": herramienta,
                          "recursos": int(g[recursos].max()) if recursos else pd.NA,
                          "alumnos": int((usos > 0).sum()), "pct_alumnos": round((usos > 0).mean() * 100, 2),
                          "usos": int(usos.sum()), "base_reporte": len(g)})
    df = pd.DataFrame(filas, columns=["asignatura", "herramienta", "recursos", "alumnos", "pct_alumnos", "usos",
                                      "base_reporte"])
    df["recursos"] = df["recursos"].astype("Int64")
    return df


def concordancia_tiempo(d: Datos, asignatura=None) -> pd.DataFrame:
    """Control de las sesiones (D25): por materia, Spearman entre los minutos que
    salen de la trazabilidad (sesiones cortadas a los 30 min) y el tiempo estimado
    de uso del reporte de participación. Se compara a la fecha del reporte
    (FECHA_CORTE_DEFECTO), porque el reporte es una foto (D36)."""
    t = participacion_alumnos(d, FECHA_CORTE_DEFECTO, asignatura).dropna(subset=["tiempo_uso_min"])
    filas = []
    for asig, g in t.groupby("asignatura"):
        rho, p = stats.spearmanr(g["minutos"], g["tiempo_uso_min"]) if len(g) > 2 else (np.nan, np.nan)
        filas.append({"asignatura": asig, "rho": round(float(rho), 3), "p_valor": float(p), "n": len(g),
                      "minutos_total": round(g["minutos"].sum(), 1), "tiempo_uso_total": g["tiempo_uso_min"].sum()})
    return pd.DataFrame(filas)


TODAS_LAS_MATERIAS = "Todas"


def _inicio_periodo(d: Datos, desde) -> pd.Timestamp:
    return pd.Timestamp(desde).normalize() if desde is not None else pd.Timestamp(d.interacciones["fecha"].min())


def _lunes(f) -> pd.Timestamp:
    f = pd.Timestamp(f).normalize()
    return f - pd.Timedelta(days=f.day_of_week)


def ritmo_semanal(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                  desde=None) -> pd.DataFrame:
    """Sesiones y minutos por alumno por semana entre `desde` (o el primer dato) y
    la fecha de corte, por materia y en total (fila asignatura = "Todas"):
      semanas            días del período / 7 (admite fracción)
      sesiones_semana    Σ sesiones / alumnos de la base / semanas (incluye a los que no entraron)
      sesiones_semana_mediana  mediana entre alumnos de sesiones del alumno / semanas
      minutos_semana(_mediana) lo mismo con los minutos de sesión
      semanas_periodo    semanas de calendario (lunes a domingo) que toca el período
      semanas_activas_mediana  mediana de semanas con al menos un ingreso por alumno (regularidad)"""
    corte = fecha_de_corte(fecha_corte)
    inicio = _inicio_periodo(d, desde)
    semanas = ((corte - inicio).days + 1) / 7
    semanas_cal = ((_lunes(corte) - _lunes(inicio)).days // 7 + 1) if corte >= inicio else 0
    act = actividad_alumnos(d, corte, asignatura, umbral, desde)
    grupos = [(a, g) for a, g in act.groupby("asignatura")] + [(TODAS_LAS_MATERIAS, act)]
    filas = []
    for asig, g in grupos:
        div = semanas if semanas > 0 else np.nan
        filas.append({"asignatura": asig, "alumnos": len(g), "semanas": round(semanas, 3),
                      "sesiones_semana": g["sesiones"].mean() / div,
                      "sesiones_semana_mediana": (g["sesiones"] / div).median(),
                      "minutos_semana": g["minutos"].mean() / div,
                      "minutos_semana_mediana": (g["minutos"] / div).median(),
                      "semanas_periodo": semanas_cal,
                      "semanas_activas_mediana": g["semanas_activas"].median()})
    return pd.DataFrame(filas)


def retencion_semanal(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """De los alumnos que entraron la semana anterior ([corte−13, corte−7]), qué %
    volvió a entrar esta semana ([corte−6, corte]). Por materia y en total
    ("Todas", contando alumno × materia)."""
    corte = fecha_de_corte(fecha_corte)
    ev = _eventos(d, corte, asignatura, desde=corte - pd.Timedelta(days=13))
    dia = ev["fecha_hora"].dt.normalize()
    pares = ev.assign(esta=dia >= corte - pd.Timedelta(days=6))[["asignatura", "id_alumno", "esta"]]
    esta = set(map(tuple, pares.loc[pares["esta"], ["asignatura", "id_alumno"]].drop_duplicates().values))
    antes = set(map(tuple, pares.loc[~pares["esta"], ["asignatura", "id_alumno"]].drop_duplicates().values))
    filas = []
    for asig in [*_materias(asignatura), TODAS_LAS_MATERIAS]:
        a = {p for p in antes if asig == TODAS_LAS_MATERIAS or p[0] == asig}
        e = {p for p in esta if asig == TODAS_LAS_MATERIAS or p[0] == asig}
        volvieron = len(a & e)
        filas.append({"asignatura": asig, "activos_semana_anterior": len(a), "activos_semana": len(e),
                      "volvieron": volvieron, "retencion": volvieron / len(a) * 100 if a else np.nan})
    return pd.DataFrame(filas)


def acceso_semanal(d: Datos, fecha_corte=None, asignatura=None, desde=None) -> pd.DataFrame:
    """% de la base que entró al menos una vez en cada semana (lunes a domingo)
    del período, sumando las materias elegidas (promedio ponderado por el tamaño
    de la base). completa = False en la última semana si la fecha de corte cae
    antes del domingo."""
    corte = fecha_de_corte(fecha_corte)
    evo = evolucion_actividad(d, corte, asignatura, "W", desde)
    n_base = base(d, asignatura).groupby("asignatura").size()
    evo = evo.assign(base=evo["asignatura"].map(n_base))
    df = evo.groupby("periodo")[["alumnos_activos", "base"]].sum().reset_index()
    df["pct"] = df["alumnos_activos"] / df["base"].replace(0, np.nan) * 100
    df["completa"] = df["periodo"] + pd.Timedelta(days=6) <= corte
    return df


def semanas_sin_actividad(d: Datos, id_alumno: str, asignatura: str, fecha_corte=None, semanas: int = 3) -> dict:
    """En cuántas de las últimas `semanas` semanas completas (lunes a domingo,
    terminadas a la fecha de corte) el alumno no tuvo ninguna interacción en la
    materia. Solo cuenta semanas desde el primer dato."""
    corte = fecha_de_corte(fecha_corte)
    ultima = _lunes(corte) if corte.day_of_week == 6 else _lunes(corte) - pd.Timedelta(days=7)
    primera = _lunes(d.interacciones["fecha"].min())
    lunes = [ultima - pd.Timedelta(days=7 * k) for k in range(semanas)]
    lunes = [x for x in lunes if x >= primera]
    ev = _eventos(d, corte, asignatura)
    ev = ev[ev["id_alumno"] == id_alumno]
    con_actividad = set(_lunes_serie(ev["fecha_hora"]))
    return {"semanas": len(lunes), "sin_actividad": sum(x not in con_actividad for x in lunes)}


def _lunes_serie(f: pd.Series) -> pd.Series:
    return f.dt.normalize() - pd.to_timedelta(f.dt.day_of_week, unit="D")


# ---------------------------------------------------------------------------
# Trazabilidad
# ---------------------------------------------------------------------------
def interacciones_por_categoria(d: Datos, fecha_corte=None, asignatura=None, desde=None,
                                por_accion: bool = False) -> pd.DataFrame:
    """Interacciones por tipo (categoría de dim_accion) o por acción."""
    ev = _eventos(d, fecha_corte, asignatura, desde)
    claves = ["asignatura", "categoria"] + (["accion"] if por_accion else [])
    df = ev.groupby(claves).agg(eventos=("id_evento", "size"), alumnos=("id_alumno", "nunique")).reset_index()
    df["pct"] = (df["eventos"] / df.groupby("asignatura")["eventos"].transform("sum") * 100).round(2)
    return df.sort_values(["asignatura", "eventos"], ascending=[True, False]).reset_index(drop=True)


def mapa_calor(d: Datos, fecha_corte=None, asignatura=None, desde=None) -> pd.DataFrame:
    """Interacciones por día de la semana × hora (grilla completa de 7 × 24),
    sumando las materias elegidas."""
    ev = _eventos(d, fecha_corte, asignatura, desde)
    t = ev.groupby(["dia_semana", "hora"]).size()
    grilla = pd.MultiIndex.from_product([range(7), range(24)], names=["dia_semana", "hora"])
    df = t.reindex(grilla, fill_value=0).rename("eventos").reset_index()
    df["nombre_dia"] = df["dia_semana"].map(dict(enumerate(DIAS)))
    return df


def interacciones_promedio_por_dia(d: Datos, fecha_corte=None, asignatura=None, desde=None) -> pd.DataFrame:
    """Por materia: interacciones por día calendario (desde el primer evento
    del período hasta la fecha de corte) y por alumno activo por día."""
    corte = fecha_de_corte(fecha_corte)
    ev = _eventos(d, corte, asignatura, desde)
    filas = []
    for materia, e in ev.groupby("asignatura"):
        inicio = pd.Timestamp(desde).normalize() if desde is not None else e["fecha"].min()
        dias = (corte - inicio).days + 1
        por_alumno_dia = e.groupby(["id_alumno", "fecha"]).size()
        filas.append({"asignatura": materia, "eventos": len(e), "dias": dias,
                      "dias_con_actividad": e["fecha"].nunique(),
                      "eventos_por_dia": round(len(e) / dias, 1),
                      "eventos_por_alumno_por_dia_activo": round(por_alumno_dia.mean(), 1)})
    return pd.DataFrame(filas)


def franjas_horarias(calor: pd.DataFrame) -> dict:
    """% de las interacciones de un `mapa_calor` en cada franja: noche (18 a 24 h),
    mañana (6 a 12 h) y fin de semana (sábado y domingo). Hora del servidor del LMS."""
    total = calor["eventos"].sum()
    if total == 0:
        return {"pct_nocturno": np.nan, "pct_manana": np.nan, "pct_finde": np.nan}
    def parte(filtro):
        return float(calor.loc[filtro, "eventos"].sum() / total * 100)
    return {"pct_nocturno": parte(calor["hora"].between(18, 23)), "pct_manana": parte(calor["hora"].between(6, 11)),
            "pct_finde": parte(calor["dia_semana"] >= 5)}


def _resumen_periodo(d: Datos, corte: pd.Timestamp, asignatura, inicio: pd.Timestamp) -> dict:
    """KPIs de trazabilidad entre `inicio` y `corte` (inclusive), ver resumen_trazabilidad."""
    dias = (corte - inicio).days + 1
    act = actividad_alumnos(d, corte, asignatura, desde=inicio)
    entraron = act[act["eventos"] > 0]
    total = int(act["eventos"].sum())
    cat = interacciones_por_categoria(d, corte, asignatura, desde=inicio)
    evaluacion = cat.loc[cat["categoria"] == "Evaluación", "eventos"].sum()
    return {"desde": inicio, "hasta": corte, "dias": dias, "alumnos": len(entraron),
            "dias_ingreso_semana": (entraron["dias_activos"] / (dias / 7)).median() if len(entraron) else np.nan,
            "interacciones_por_dia_ingreso": (entraron["eventos"] / entraron["dias_activos"]).median()
                                             if len(entraron) else np.nan,
            "interacciones_total": total, "interacciones_por_dia": total / dias,
            "pct_evaluacion": evaluacion / total * 100 if total else np.nan,
            **franjas_horarias(mapa_calor(d, corte, asignatura, desde=inicio))}


def resumen_trazabilidad(d: Datos, fecha_corte=None, asignatura=None, desde=None) -> pd.DataFrame:
    """KPIs del dashboard de Trazabilidad (D80), para el período (fila "actual",
    de `desde` o el primer dato a la fecha de corte, inclusive) y para el período
    anterior de igual largo (fila "anterior", solo si entra entero en los datos).
    Unidad: alumno × materia de la base. "Entraron" = con al menos una interacción
    en el período.
      alumnos                        alumnos que entraron (denominador de las medianas)
      dias_ingreso_semana            mediana de días con ingreso / (días del período / 7)
      interacciones_por_dia_ingreso  mediana de interacciones / días con ingreso
      interacciones_total            interacciones del período
      interacciones_por_dia          total / días calendario del período
      pct_evaluacion                 % de las interacciones de tipo Evaluación
      pct_nocturno, pct_manana, pct_finde   ver franjas_horarias"""
    corte = fecha_de_corte(fecha_corte)
    inicio = _inicio_periodo(d, desde)
    filas = {"actual": _resumen_periodo(d, corte, asignatura, inicio)}
    if desde is not None:
        dias = (corte - inicio).days + 1
        inicio_ant = inicio - pd.Timedelta(days=dias)
        if inicio_ant >= pd.Timestamp(d.interacciones["fecha"].min()):
            filas["anterior"] = _resumen_periodo(d, inicio - pd.Timedelta(days=1), asignatura, inicio_ant)
    return pd.DataFrame.from_dict(filas, orient="index").rename_axis("periodo")


TRAMOS_FRECUENCIA = {
    "W": ([0, 1, 2, 3, 4, np.inf], ["0–1", "1–2", "2–3", "3–4", "4 o más"]),
    "M": ([0, 4, 8, 12, 16, np.inf], ["1–3", "4–7", "8–11", "12–15", "16 o más"]),
}


def frecuencia_ingreso(d: Datos, fecha_corte=None, asignatura=None, desde=None,
                       frecuencia: str = "W") -> pd.DataFrame:
    """Por materia, % de los alumnos que entraron en el período según cuántos días
    con ingreso tienen por semana ('W': días / (días del período / 7)) o por mes
    ('M': días / (días del período / 30)), en los tramos de TRAMOS_FRECUENCIA
    (cerrados a la izquierda: 1 día por semana cae en "1–2"; en 'M', "1–3" incluye
    a los que entraron menos de 4 días por mes). Grilla completa (tramos con 0)."""
    if frecuencia not in TRAMOS_FRECUENCIA:
        raise ValueError("frecuencia tiene que ser 'W' o 'M'")
    corte = fecha_de_corte(fecha_corte)
    inicio = _inicio_periodo(d, desde)
    dias = (corte - inicio).days + 1
    act = actividad_alumnos(d, corte, asignatura, desde=inicio)
    act = act[act["eventos"] > 0]
    tasa = act["dias_activos"] / (dias / (7 if frecuencia == "W" else 30))
    bordes, etiquetas = TRAMOS_FRECUENCIA[frecuencia]
    act = act.assign(tramo=pd.cut(tasa, bordes, labels=etiquetas, right=False))
    grilla = pd.MultiIndex.from_product([_materias(asignatura), etiquetas], names=["asignatura", "tramo"])
    df = act.groupby(["asignatura", "tramo"], observed=True).size().reindex(grilla, fill_value=0) \
            .rename("alumnos").reset_index()
    df["total"] = df.groupby("asignatura")["alumnos"].transform("sum")
    df["pct"] = (df["alumnos"] / df["total"].where(df["total"] > 0) * 100).fillna(0)
    return df


def fechas_evaluaciones(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Instrumentos ya tomados a la fecha de corte, para marcarlos en las líneas de tiempo."""
    i = _filtrar(d.instrumentos, asignatura)
    i = i[i["fecha_instrumento"].notna() & (i["fecha_instrumento"] <= fecha_de_corte(fecha_corte))]
    return i[["asignatura", "id_instrumento", "instrumento", "fecha_instrumento", "es_recuperatorio"]] \
            .reset_index(drop=True)


# Orden fijo de las categorías de dim_accion (de la más a la menos frecuente):
# así cada tipo de interacción conserva su color en todos los gráficos (D62).
CATEGORIAS = ["Contenido", "Navegación", "Evaluación", "Comunicación", "Notas", "Agenda"]


def categorias_presentes(d: Datos) -> list[str]:
    """CATEGORIAS más las que aparezcan en los datos y no estén en la lista."""
    extra = sorted(set(d.interacciones["categoria"].dropna()) - set(CATEGORIAS))
    return CATEGORIAS + extra


def _periodo(f: pd.Series, frecuencia: str) -> pd.Series:
    """Fecha -> inicio de su día, semana (lunes) o mes."""
    if frecuencia == "D":
        return f.dt.normalize()
    if frecuencia == "W":
        return f.dt.normalize() - pd.to_timedelta(f.dt.day_of_week, unit="D")
    if frecuencia == "M":
        return f.dt.to_period("M").dt.to_timestamp()
    raise ValueError("frecuencia tiene que ser 'D', 'W' o 'M'")


def evolucion_interacciones(d: Datos, fecha_corte=None, asignatura=None, frecuencia: str = "W",
                            desde=None, por: str = "asignatura") -> pd.DataFrame:
    """Interacciones por período ('D', 'W' o 'M'), separadas por materia
    (`por="asignatura"`) o por tipo de interacción (`por="categoria"`, sumando
    las materias elegidas). Grilla completa: los períodos sin eventos van con 0.
      eventos_por_alumno   eventos / tamaño de la base (de la materia o de las elegidas)
      pct_periodo          % de los eventos del período que son de ese grupo (D62)
      dias, dias_periodo   días del período dentro de [desde, corte] y largo del período (1, 7 o días del mes)
      completo             dias == dias_periodo (el primero y el último pueden estar cortados)"""
    if por not in {"asignatura", "categoria"}:
        raise ValueError("por tiene que ser 'asignatura' o 'categoria'")
    corte = fecha_de_corte(fecha_corte)
    ev = _eventos(d, corte, asignatura, desde)
    ev = ev.assign(periodo=_periodo(ev["fecha_hora"], frecuencia), par=ev["asignatura"] + "|" + ev["id_alumno"])
    df = ev.groupby([por, "periodo"]).agg(eventos=("id_evento", "size"), alumnos=("par", "nunique"))
    inicio = pd.Timestamp(desde).normalize() if desde is not None else d.interacciones["fecha"].min()
    periodos = _periodo(pd.Series(pd.date_range(inicio, corte, freq="D")), frecuencia).unique()
    grupos = _materias(asignatura) if por == "asignatura" else categorias_presentes(d)
    grilla = pd.MultiIndex.from_product([grupos, periodos], names=[por, "periodo"])
    df = df.reindex(grilla, fill_value=0).astype(int).reset_index()
    tam = base(d, asignatura).groupby("asignatura").size()
    n = df["asignatura"].map(tam) if por == "asignatura" else tam.sum()
    df["eventos_por_alumno"] = (df["eventos"] / n).round(2)
    total = df.groupby("periodo")["eventos"].transform("sum")
    df["pct_periodo"] = (df["eventos"] / total.where(total > 0) * 100).round(2).fillna(0)
    # Períodos incompletos: el primero y el último pueden quedar cortados por `desde` y la fecha de corte.
    cubiertos = _periodo(pd.Series(pd.date_range(inicio, corte, freq="D")), frecuencia).value_counts()
    largo = {"D": lambda p: 1, "W": lambda p: 7, "M": lambda p: p.days_in_month}[frecuencia]
    df["dias"] = df["periodo"].map(cubiertos).fillna(0).astype(int)
    df["dias_periodo"] = df["periodo"].map(lambda p: largo(pd.Timestamp(p))).astype(int)
    df["completo"] = df["dias"] >= df["dias_periodo"]
    return df


def interacciones_por_accion(d: Datos, fecha_corte=None, asignatura=None, desde=None) -> pd.DataFrame:
    """Interacciones por categoría, sección y acción, sumando las materias
    elegidas. 'Acceder' a Inicio y 'Acceder' a Programa son filas distintas:
    la acción sola no dice dónde pasó (D62).
      alumnos       alumnos (de la base, por materia) que la hicieron al menos una vez
      pct           % de todas las interacciones del período
      pct_alumnos   % de la base que la hizo al menos una vez"""
    ev = _eventos(d, fecha_corte, asignatura, desde)
    ev = ev.assign(par=ev["asignatura"] + "|" + ev["id_alumno"])
    df = (ev.groupby(["categoria", "seccion", "accion"])
            .agg(eventos=("id_evento", "size"), alumnos=("par", "nunique")).reset_index())
    df["pct"] = (df["eventos"] / max(len(ev), 1) * 100).round(2)
    df["pct_alumnos"] = (df["alumnos"] / max(len(base(d, asignatura)), 1) * 100).round(2)
    return df.sort_values("eventos", ascending=False).reset_index(drop=True)


def actividad_alrededor_evaluaciones(d: Datos, fecha_corte=None, asignatura=None, dias_antes: int = 7,
                                     dias_despues: int = 3) -> pd.DataFrame:
    """Para cada evaluación ya tomada a la fecha de corte (sin recuperatorios),
    la actividad de su materia en cada día desde `dias_antes` antes hasta
    `dias_despues` después. Día 0 = fecha del instrumento (D18). Los días fuera
    de los datos (antes del primer evento o después del corte) no aparecen.
      eventos_por_alumno       interacciones del día / base de la materia
      evaluacion_por_alumno    lo mismo, solo la categoría Evaluación
      relativo                 eventos del día / promedio diario de la materia en
                               toda la cursada hasta el corte (1 = un día típico, D62)"""
    corte = fecha_de_corte(fecha_corte)
    ev = _eventos(d, corte, asignatura)
    dias = pd.date_range(d.interacciones["fecha"].min(), corte, freq="D")
    grilla = pd.MultiIndex.from_product([_materias(asignatura), dias], names=["asignatura", "fecha"])
    diario = pd.DataFrame({
        "eventos": ev.groupby(["asignatura", "fecha"]).size(),
        "eventos_evaluacion": ev[ev["categoria"] == "Evaluación"].groupby(["asignatura", "fecha"]).size(),
    }).reindex(grilla, fill_value=0).fillna(0).astype(int).reset_index()
    tam = base(d, asignatura).groupby("asignatura").size()
    promedio = diario.groupby("asignatura")["eventos"].mean()

    ins = fechas_evaluaciones(d, corte, asignatura)
    ins = ins[~ins["es_recuperatorio"]]
    ventana = pd.DataFrame({"dia_relativo": range(-dias_antes, dias_despues + 1)})
    df = ins.merge(ventana, how="cross")
    df["fecha"] = df["fecha_instrumento"].dt.normalize() + pd.to_timedelta(df["dia_relativo"], unit="D")
    df = df.merge(diario, on=["asignatura", "fecha"], how="inner")
    columnas = ["asignatura", "id_instrumento", "instrumento", "fecha_instrumento", "dia_relativo", "fecha",
                "eventos", "eventos_evaluacion", "eventos_por_alumno", "evaluacion_por_alumno", "relativo"]
    if df.empty:  # todavía no hay evaluaciones tomadas a la fecha de corte
        return df.reindex(columns=columnas)
    n = df["asignatura"].map(tam).astype(float)
    df["eventos_por_alumno"] = (df["eventos"] / n).round(3)
    df["evaluacion_por_alumno"] = (df["eventos_evaluacion"] / n).round(3)
    df["relativo"] = (df["eventos"] / df["asignatura"].map(promedio).astype(float)).round(3)
    return df[columnas].sort_values(["asignatura", "fecha_instrumento", "dia_relativo"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cruces: notas vs. participación
# ---------------------------------------------------------------------------
def _fuerza(rho: float) -> str:
    r = abs(rho)
    return "nula" if r < 0.1 else "débil" if r < 0.3 else "moderada" if r < 0.5 else "fuerte"


def _tabla_cruce(d: Datos, fecha_corte, asignatura, umbral, solo_rindieron: bool) -> pd.DataFrame:
    """tabla_alumnos, opcionalmente solo con quienes rindieron al menos una
    evaluación a la fecha de corte (D55: sin los que tienen 0 por no rendir)."""
    t = tabla_alumnos(d, fecha_corte, asignatura, umbral)
    return t[t["rendidos"] > 0].reset_index(drop=True) if solo_rindieron else t


def correlaciones(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                  variables: list[str] | None = None, solo_rindieron: bool = False) -> pd.DataFrame:
    """Correlación de Spearman entre cada variable de actividad y la nota (sobre
    100), por materia. Spearman porque las variables son asimétricas y con
    muchos ceros: mide si a más actividad hay más nota, sin suponer una recta.
    solo_rindieron=True deja afuera a quienes no rindieron nada (D55)."""
    t = _tabla_cruce(d, fecha_corte, asignatura, umbral, solo_rindieron)
    filas = []
    for materia, g in t.groupby("asignatura"):
        for var in variables or list(VARIABLES_CRUCE):
            par = g[[var, "nota_pct"]].astype(float).dropna()
            if len(par) < 3 or par[var].nunique() < 2 or par["nota_pct"].nunique() < 2:
                rho, p = np.nan, np.nan
            else:
                rho, p = stats.spearmanr(par[var], par["nota_pct"])
            filas.append({"asignatura": materia, "variable": var, "descripcion": VARIABLES_CRUCE.get(var, var),
                          "rho": round(float(rho), 3), "p_valor": round(float(p), 4), "n": len(par),
                          "fuerza": _fuerza(rho) if pd.notna(rho) else "sin datos",
                          "significativa": bool(pd.notna(p) and p < 0.05)})
    return pd.DataFrame(filas)


def cuadrante_riesgo(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                     variable: str = "minutos") -> pd.DataFrame:
    """Tabla de alumnos con su cuadrante. 'Poca actividad' = por debajo de la
    mediana de `variable` en su materia; "nota baja" = condición Libre (D37)."""
    t = tabla_alumnos(d, fecha_corte, asignatura, umbral)
    mediana = t.groupby("asignatura")[variable].transform("median")
    t["mediana_actividad"] = mediana
    poca = t[variable] < mediana
    baja = t["condicion"].eq("Libre")
    t["cuadrante"] = np.select([poca & baja, ~poca & baja, poca & ~baja],
                               ["Riesgo: poca actividad y nota baja", "Activo con nota baja",
                                "Poca actividad con buena nota"], default="Activo con buena nota")
    t["en_riesgo"] = poca & baja
    return t


NIVELES_ACTIVIDAD = ["Muy baja", "Baja", "Media", "Alta", "Muy alta"]


def nota_por_nivel_actividad(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                             variable: str = "minutos", solo_rindieron: bool = False) -> pd.DataFrame:
    """Los alumnos de cada materia partidos en 5 grupos del mismo tamaño
    (quintiles) según `variable`, de la que menos a la que más actividad, con
    la nota promedio y el % por condición de cada grupo (D55). Es la "tendencia"
    del gráfico de dispersión, en una forma que se lee sin estadística: "del 20 %
    que menos entra, tantos están libres". Sin evaluaciones a la fecha de corte,
    la nota queda vacía y todos cuentan en 'Sin evaluaciones'."""
    t = _tabla_cruce(d, fecha_corte, asignatura, umbral, solo_rindieron)
    filas = []
    for materia, g in t.groupby("asignatura"):
        g = g.dropna(subset=[variable])
        k = min(len(NIVELES_ACTIVIDAD), len(g))
        if k == 0:
            continue
        # rank(method="first") parte los empates (muchos ceros) para que los grupos sean parejos
        niveles = NIVELES_ACTIVIDAD if k == len(NIVELES_ACTIVIDAD) else [f"Grupo {i + 1}" for i in range(k)]
        g = g.assign(nivel=pd.qcut(g[variable].rank(method="first"), k, labels=niveles))
        for orden, (nivel, q) in enumerate(g.groupby("nivel", observed=True)):
            fila = {"asignatura": materia, "orden": orden, "nivel": str(nivel), "alumnos": len(q),
                    "desde": float(q[variable].min()), "hasta": float(q[variable].max()),
                    "mediana_actividad": float(q[variable].median()),
                    "nota_pct": q["nota_pct"].mean(), "nota_final": q["nota_final"].mean()}
            for cond in [*CONDICIONES, SIN_EVALUACIONES]:
                fila[f"pct_{_sin_tildes(cond).lower().replace(' ', '_')}"] = (q["condicion"] == cond).mean() * 100
            filas.append(fila)
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    df["variable"] = variable
    return df.round(2)


# ---------------------------------------------------------------------------
# Matrícula y alertas
# ---------------------------------------------------------------------------
def resumen_matricula(d: Datos, fecha_corte=None, asignatura=None,
                      umbral: int = UMBRAL_INACTIVIDAD_DIAS) -> pd.DataFrame:
    """Por materia: inscriptos vs. activos vs. con nota, y las dos alertas de
    matrícula (activos no inscriptos e inscriptos sin actividad)."""
    t = tabla_alumnos(d, fecha_corte, asignatura, umbral)
    t["con_nota"] = t["rendidos"] > 0
    t["con_actividad"] = t["eventos"] > 0
    m = _filtrar(d.matricula, asignatura)
    g = t.groupby("asignatura")
    df = pd.DataFrame({
        "base": g.size(), "inscriptos": g["inscripto"].sum(),
        "bajas": m[m["estado"].eq("Baja")].groupby("asignatura").size(),
        "con_actividad": g["con_actividad"].sum(), "activos": g["activo"].sum(), "con_nota": g["con_nota"].sum(),
        "no_inscriptos_cursando": g.apply(lambda x: (~x["inscripto"]).sum(), include_groups=False),
        "inscriptos_sin_actividad": g.apply(lambda x: (x["inscripto"] & ~x["con_actividad"] & ~x["con_nota"]).sum(),
                                            include_groups=False),
        "inscriptos_sin_notas": g.apply(lambda x: (x["inscripto"] & ~x["con_nota"]).sum(), include_groups=False),
    }).reindex(_materias(asignatura)).fillna(0).astype(int)
    return df.reset_index(names="asignatura")


def situacion_academica(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Condición académica separada por inscriptos y no inscriptos."""
    n = nota_final(d, fecha_corte, asignatura)
    n["grupo"] = np.where(n["inscripto"], "Inscriptos", "No inscriptos")
    return n.groupby(["asignatura", "grupo", "condicion"]).size().rename("alumnos").reset_index()


TIPOS_ALERTA = {
    "no_inscripto": "Cursa sin estar inscripto",
    "sin_actividad": "Inscripto sin actividad",
    "sin_notas": "Inscripto que entra pero no rinde",
    "inactivo": "Inactivo",
    "libre": "Condición Libre",
}


def alertas(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS) -> pd.DataFrame:
    """Lista larga de alertas (un alumno puede tener varias). Para la tabla de
    Matrícula y Alertas y la descarga en CSV."""
    t = tabla_alumnos(d, fecha_corte, asignatura, umbral)
    sin_nada = (t["eventos"] == 0) & (t["rendidos"] == 0)
    reglas = {
        "no_inscripto": (~t["inscripto"], lambda r: f"Tiene {r.rendidos} instrumento(s) rendido(s) y "
                                                   f"{r.eventos} interacciones"),
        "sin_actividad": (t["inscripto"] & sin_nada, lambda r: "Sin interacciones ni notas a la fecha de corte"),
        "sin_notas": (t["inscripto"] & (t["eventos"] > 0) & (t["rendidos"] == 0) & (t["instrumentos"] > 0),
                      lambda r: f"{r.eventos} interacciones y 0 de {r.instrumentos} instrumentos rendidos"),
        "inactivo": (t["estado_actividad"].eq(INACTIVO), lambda r: f"{r.dias_sin_actividad} días sin entrar"),
        "libre": (t["condicion"].eq("Libre") & ~sin_nada,
                  lambda r: f"Nota {r.nota_final:g} / {r.escala} ({r.rendidos} de {r.instrumentos} rendidos)"),
    }
    partes = []
    for tipo, (mascara, detalle) in reglas.items():
        sub = t[mascara]
        partes.append(pd.DataFrame({
            "asignatura": sub["asignatura"], "id_alumno": sub["id_alumno"],
            "nombre_completo": sub["nombre_completo"], "inscripto": sub["inscripto"],
            "tipo": tipo, "alerta": TIPOS_ALERTA[tipo], "detalle": [detalle(r) for r in sub.itertuples()]}))
    return pd.concat(partes, ignore_index=True).sort_values(["asignatura", "tipo", "nombre_completo"]) \
             .reset_index(drop=True)


PRIORIDADES = ["Alta", "Media", "Administrativa"]
ALERTAS_ACADEMICAS = {"inactivo", "libre", "sin_notas"}


def alertas_por_alumno(d: Datos, fecha_corte=None, asignatura=None,
                       umbral: int = UMBRAL_INACTIVIDAD_DIAS) -> pd.DataFrame:
    """Una fila por alumno y materia con al menos una alerta, con su prioridad (D52):
      Alta            inscripto sin actividad, o dos o más alertas académicas
                      (inactivo, Libre, entra pero no rinde) a la vez. "Entra pero
                      no rinde" + Libre cuentan como una (el 0 ya lo deja Libre).
      Media           una sola alerta académica
      Administrativa  solo cursa sin estar inscripto (lo resuelve la secretaría)
    Ordenada de más a menos urgente, para que el tutor sepa a quién contactar primero."""
    al = alertas(d, fecha_corte, asignatura, umbral)
    t = tabla_alumnos(d, fecha_corte, asignatura, umbral)
    claves = ["asignatura", "id_alumno"]
    g = (al.groupby(claves)
           .agg(tipos=("tipo", lambda s: sorted(set(s), key=list(TIPOS_ALERTA).index)), cantidad=("tipo", "size"))
           .reset_index())
    # Quien entra pero no rinde tiene 0 y por eso también es Libre: cuenta como una sola alerta.
    academicas = g["tipos"].map(lambda ts: len(ALERTAS_ACADEMICAS.intersection(ts))
                                - int({"sin_notas", "libre"} <= set(ts)))
    g["prioridad"] = np.select(
        [g["tipos"].map(lambda ts: "sin_actividad" in ts) | academicas.ge(2), academicas.eq(1)],
        PRIORIDADES[:2], default=PRIORIDADES[2])
    g["alertas"] = g["tipos"].map(lambda ts: " · ".join(TIPOS_ALERTA[x] for x in ts))
    cols = ["nombre_completo", "inscripto", "condicion", "nota_final", "escala", "rendidos", "instrumentos",
            "estado_actividad", "dias_sin_actividad", "ultima_interaccion", "eventos", "avance"]
    df = g.merge(t[claves + cols], on=claves, how="left")
    df["prioridad"] = pd.Categorical(df["prioridad"], PRIORIDADES, ordered=True)
    df = df.sort_values(["prioridad", "cantidad", "asignatura", "nombre_completo"],
                        ascending=[True, False, True, True])
    return df[claves + ["nombre_completo", "prioridad", "cantidad", "alertas", "tipos", *cols[1:]]] \
             .reset_index(drop=True)


def evolucion_matricula(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Por materia y día hasta la fecha de corte, acumulado: alumnos con la
    inscripción aceptada (por fecha de inscripción, último estado) y alumnos de
    la base que ya habían entrado al aula (por su primera interacción).
    Muestra si los alumnos empiezan a cursar antes de inscribirse."""
    corte = fecha_de_corte(fecha_corte)
    m = _filtrar(d.matricula, asignatura)
    series = {
        "Inscriptos": m.loc[m["inscripto"], ["asignatura", "fecha_inscripcion"]],
        "Ya entraron al aula": m.loc[m["en_base"], ["asignatura", "primera_interaccion"]],
    }
    partes = []
    for nombre, s in series.items():
        s = s.set_axis(["asignatura", "fecha"], axis=1).dropna()
        s = s.assign(fecha=s["fecha"].dt.normalize())
        s = s[s["fecha"] <= corte]
        if s.empty:
            continue
        diario = s.groupby(["asignatura", "fecha"]).size().rename("nuevos").reset_index()
        partes.append(diario.assign(serie=nombre))
    if not partes:
        return pd.DataFrame(columns=["asignatura", "serie", "fecha", "nuevos", "alumnos"])
    df = pd.concat(partes, ignore_index=True)
    inicio = df["fecha"].min()
    dias = pd.date_range(inicio, corte, freq="D")
    completo = pd.MultiIndex.from_product([_materias(asignatura), list(series), dias],
                                          names=["asignatura", "serie", "fecha"])
    df = (df.set_index(["asignatura", "serie", "fecha"])["nuevos"].reindex(completo, fill_value=0)
            .reset_index())
    df["alumnos"] = df.groupby(["asignatura", "serie"])["nuevos"].cumsum()
    return df


# ---------------------------------------------------------------------------
# KPIs generales y ficha individual
# ---------------------------------------------------------------------------
def kpis_generales(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS) -> pd.DataFrame:
    """Las tarjetas del dashboard General, una fila por materia."""
    cal = resumen_calificaciones(d, fecha_corte, asignatura)
    par = resumen_participacion(d, fecha_corte, asignatura, umbral)
    mat = resumen_matricula(d, fecha_corte, asignatura, umbral)
    return (mat[["asignatura", "base", "inscriptos", "activos", "no_inscriptos_cursando", "inscriptos_sin_actividad",
                 "inscriptos_sin_notas"]]
            .merge(par[["asignatura", "pct_activos", "sesiones_promedio", "minutos_promedio", "avance_promedio"]])
            .merge(cal[["asignatura", "nota_promedio", "escala", "pct_libre", "pct_regular", "pct_promociona"]]))


# ---------------------------------------------------------------------------
# Dashboard General: KPIs nuevos (D72-D76)
# ---------------------------------------------------------------------------
def alcanzan_regular(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Por materia: alumnos con condición a la fecha (los que ya tienen nota) y
    cuántos alcanzan Regular o Promociona con el corte de su materia (D72).
    pct_alcanzan = (Regular + Promociona) / con_condicion × 100; vacío si
    todavía no hay evaluaciones."""
    n = nota_final(d, fecha_corte, asignatura)
    n = n[n["condicion"].ne(SIN_EVALUACIONES)]
    g = (n.assign(alcanza=n["condicion"].isin(["Regular", "Promociona"]))
          .groupby("asignatura").agg(con_condicion=("id_alumno", "size"), alcanzan=("alcanza", "sum"))
          .reindex(_materias(asignatura)).fillna(0).astype(int))
    g["pct_alcanzan"] = (g["alcanzan"] / g["con_condicion"].replace(0, np.nan) * 100).round(2)
    return g.reset_index(names="asignatura")


def alumnos_en_riesgo(d: Datos, fecha_corte=None, asignatura=None,
                      umbral: int = UMBRAL_INACTIVIDAD_DIAS) -> pd.DataFrame:
    """Alumnos en riesgo (D73): Libre a la fecha de corte y sin entrar en los
    últimos `umbral` días (Inactivo o Sin actividad). Una fila por alumno y materia."""
    t = tabla_alumnos(d, fecha_corte, asignatura, umbral)
    r = t[t["condicion"].eq("Libre") & t["estado_actividad"].ne(ACTIVO)]
    cols = ["asignatura", "id_alumno", "nombre_completo", "inscripto", "nota_final", "escala", "rendidos",
            "instrumentos", "estado_actividad", "dias_sin_actividad"]
    return r[cols].reset_index(drop=True)


def tasa_rendicion(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Por materia (D74): Σ instrumentos rendidos / Σ instrumentos disponibles a la
    fecha, sobre todos los alumnos de la base (alumno × instrumento). Rendido =
    tiene nota en el instrumento o en su recuperatorio, como en nota_final."""
    n = nota_final(d, fecha_corte, asignatura)
    g = (n.groupby("asignatura")[["instrumentos", "rendidos"]].sum()
          .reindex(_materias(asignatura)).fillna(0).astype(int))
    g["pct_rendidos"] = (g["rendidos"] / g["instrumentos"].replace(0, np.nan) * 100).round(2)
    return g.reset_index(names="asignatura")


def sin_rendir(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Alumnos de la base que no rindieron ningún instrumento a la fecha (rendidos
    == 0): su nota es 0 por no rendir (D15). Con `inscripto` y `eventos` para
    separar a quienes nunca entraron de quienes entran y no rinden."""
    n = nota_final(d, fecha_corte, asignatura)
    act = actividad_alumnos(d, fecha_corte, asignatura)[["asignatura", "id_alumno", "eventos"]]
    s = n[(n["rendidos"] == 0) & (n["instrumentos"] > 0)].merge(act, how="left")
    return s[["asignatura", "id_alumno", "inscripto", "instrumentos", "eventos"]].reset_index(drop=True)


def evaluaciones_en_periodo(d: Datos, fecha_corte=None, asignatura=None, dias: int = 7) -> pd.DataFrame:
    """Instrumentos que cuentan para la nota final cuya fecha cae en
    (corte − dias, corte] (D75), con cuántos alumnos de la base lo rindieron y
    cuántos no (que cuentan 0). Los recuperatorios no van: no rendirlos no da 0."""
    corte = fecha_de_corte(fecha_corte)
    c = notas_instrumento(d, corte, asignatura)
    c = c[c["cuenta_en_final"] & c["fecha_instrumento"].gt(corte - pd.Timedelta(days=dias))]
    c = c.assign(con_nota=c["rindio"] | c["recuperatorio_aplicado"])
    if c.empty:
        return pd.DataFrame(columns=["asignatura", "id_instrumento", "instrumento", "fecha_instrumento", "base",
                                     "rindieron", "no_rindieron"])
    g = (c.groupby(["asignatura", "id_instrumento", "fecha_instrumento"])
          .agg(base=("id_alumno", "size"), rindieron=("con_nota", "sum")).reset_index()
          .merge(d.instrumentos[["id_instrumento", "instrumento"]], on="id_instrumento", how="left"))
    g["no_rindieron"] = g["base"] - g["rindieron"]
    return g.sort_values(["fecha_instrumento", "asignatura"]).reset_index(drop=True)


def no_rindieron_periodo(d: Datos, fecha_corte=None, asignatura=None, dias: int = 7) -> pd.DataFrame:
    """Alumno × materia con al menos un instrumento de evaluaciones_en_periodo()
    sin rendir (D75). `faltan` = cuántos de esos instrumentos le faltan."""
    corte = fecha_de_corte(fecha_corte)
    c = notas_instrumento(d, corte, asignatura)
    c = c[c["cuenta_en_final"] & c["fecha_instrumento"].gt(corte - pd.Timedelta(days=dias))]
    c = c[~(c["rindio"] | c["recuperatorio_aplicado"])]
    return (c.groupby(["asignatura", "id_alumno"]).size().rename("faltan").reset_index())


def fecha_reporte_participacion(d: Datos) -> pd.Timestamp | None:
    """Día del reporte de participación (D76). La fecha de exportación del Excel no
    llega a gold, así que se usa la última interacción que registra el reporte:
    el LMS la calcula al exportar. El avance es una foto de ese día (D36)."""
    f = d.participacion["ultima_interaccion"].max()
    return None if pd.isna(f) else pd.Timestamp(f).normalize()


def corte_con_todo(d: Datos) -> pd.Timestamp:
    """La fecha de corte que incluye todo lo cargado: el último instrumento o la
    última interacción, lo que sea más tarde."""
    fechas = [d.instrumentos["fecha_instrumento"].max(), d.interacciones["fecha_hora"].max(),
              fecha_de_corte(None)]
    return max(pd.Timestamp(f) for f in fechas if pd.notna(f)).normalize()


FOTO_DATOS = {"alumnos": "Alumnos en la base", "inscriptos": "Inscriptos", "instrumentos": "Instrumentos",
              "notas": "Notas cargadas", "nota_promedio": "Nota promedio", "promociona": "Promocionan",
              "regular": "Regulares", "libre": "Libres", "eventos": "Eventos de trazabilidad"}


def foto_datos(d: Datos, asignatura=None) -> pd.DataFrame:
    """Resumen por materia de lo que hay cargado, para comparar antes y después
    de subir un archivo (D51). Usa la fecha de corte que incluye todo
    (corte_con_todo): así un instrumento nuevo se ve aunque sea posterior a la
    fecha de corte elegida en la barra."""
    corte = corte_con_todo(d)
    n = nota_final(d, corte, asignatura)
    g = n.groupby("asignatura")
    df = pd.DataFrame({"alumnos": g.size(), "inscriptos": g["inscripto"].sum(),
                       "nota_promedio": g["nota_final"].mean().round(2)})
    for cond in CONDICIONES:
        df[cond.lower()] = g["condicion"].apply(lambda s: int((s == cond).sum()))
    inst = _filtrar(d.instrumentos, asignatura)
    df["instrumentos"] = inst.groupby("asignatura").size()
    cal = _filtrar(d.calificaciones, asignatura)
    df["notas"] = cal[cal["rindio"]].groupby("asignatura").size()
    df["eventos"] = _filtrar(d.interacciones, asignatura).groupby("asignatura").size()
    df = df.reindex(_materias(asignatura))
    enteros = [c for c in FOTO_DATOS if c != "nota_promedio"]
    df[enteros] = df[enteros].fillna(0).astype(int)
    return df[list(FOTO_DATOS)].rename_axis("asignatura").reset_index()


def comparar_fotos(antes: pd.DataFrame, despues: pd.DataFrame) -> pd.DataFrame:
    """Tabla larga materia × indicador con antes, después y diferencia (D51)."""
    a = antes.melt("asignatura", var_name="clave", value_name="antes")
    b = despues.melt("asignatura", var_name="clave", value_name="despues")
    df = a.merge(b, on=["asignatura", "clave"], how="outer")
    df["diferencia"] = (df["despues"].astype(float) - df["antes"].astype(float)).round(2)
    df["indicador"] = df["clave"].map(FOTO_DATOS)
    orden = {c: i for i, c in enumerate([*_materias(None), *FOTO_DATOS])}
    return (df.sort_values(["asignatura", "clave"], key=lambda s: s.map(orden))
              [["asignatura", "clave", "indicador", "antes", "despues", "diferencia"]].reset_index(drop=True))


def buscar_alumnos(d: Datos, texto: str = "", asignatura=None, solo_base: bool = False) -> pd.DataFrame:
    """Busca por ID o por apellido/nombre (sin importar tildes ni mayúsculas).
    Con texto vacío devuelve a todos; la ficha muestra al primero por defecto.
    solo_base=True deja solo a los alumnos de la base de `asignatura` (D11):
    los demás no tienen notas ni actividad en los KPIs (D56)."""
    a = d.alumnos.sort_values(["apellido", "nombre"])
    if solo_base or asignatura is not None:
        a = a[a["id_alumno"].isin(base(d, asignatura)["id_alumno"])]
    if texto.strip():
        objetivo = _sin_tildes(texto.strip())
        campo = (a["id_alumno"] + " " + a["apellido"].fillna("") + " " + a["nombre"].fillna("")).map(_sin_tildes)
        a = a[campo.str.contains(objetivo, regex=False)]
    return a.reset_index(drop=True)


def ficha_alumno(d: Datos, id_alumno: str, fecha_corte=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS) -> dict:
    """Todo lo de un alumno para la Ficha individual (D56):
      datos         fila de dim_alumno
      materias      su fila de tabla_alumnos en cada materia de su base, más la
                    comparación con su curso: promedio de la materia y percentil
                    (0-100, en qué lugar queda dentro de la base) de la nota,
                    los minutos, las interacciones y el avance
      instrumentos  sus notas por instrumento a la fecha de corte, con el
                    promedio del curso entre quienes lo rindieron (D22)
      semanal       su actividad por semana y materia, con las interacciones
                    promedio por alumno de la base en esa semana (curso_eventos)
      categorias    sus interacciones por tipo y materia, en cantidad y en %,
                    contra el % del curso (con 0 los tipos que usa el curso y él no)
      alertas       sus alertas (D37) a la fecha de corte
      evaluaciones  las fechas de las evaluaciones ya tomadas, para marcarlas
      eventos       toda su trazabilidad hasta la fecha de corte, de la más nueva
                    a la más vieja"""
    datos = d.alumnos[d.alumnos["id_alumno"] == id_alumno]
    if datos.empty:
        raise KeyError(f"No existe el alumno {id_alumno}")
    t = tabla_alumnos(d, fecha_corte, None, umbral)
    por_materia = t.groupby("asignatura")
    for col in ["nota_final", "minutos", "eventos", "avance"]:
        t[f"promedio_{col}"] = por_materia[col].transform("mean").round(2)
        t[f"percentil_{col}"] = (por_materia[col].rank(pct=True, method="average") * 100).round(0)
    t["alumnos_materia"] = por_materia["id_alumno"].transform("size")
    materias = t[t["id_alumno"] == id_alumno].reset_index(drop=True)
    suyas = materias["asignatura"].tolist()

    inst = notas_instrumento(d, fecha_corte)
    inst = inst[inst["id_alumno"] == id_alumno]
    if suyas:
        prom = promedio_por_instrumento(d, fecha_corte, suyas)[["id_instrumento", "rindieron", "promedio_pct"]]
        inst = inst.merge(prom.rename(columns={"promedio_pct": "promedio_curso_pct"}), on="id_instrumento",
                          how="left")
    inst = inst.merge(d.instrumentos[["id_instrumento", "orden"]], on="id_instrumento", how="left") \
               .sort_values(["asignatura", "orden"])

    ev_todos = _eventos(d, fecha_corte, suyas or None)
    ev = ev_todos[ev_todos["id_alumno"] == id_alumno]

    semanal = evolucion_actividad(d, fecha_corte, None, "W", id_alumno=id_alumno)
    if suyas:
        curso = evolucion_actividad(d, fecha_corte, suyas, "W")
        tam = base(d, suyas).groupby("asignatura").size()
        curso["curso_eventos"] = (curso["eventos"] / curso["asignatura"].map(tam)).round(1)
        semanal = semanal.merge(curso[["asignatura", "periodo", "curso_eventos"]], how="left")

    def _por_tipo(e: pd.DataFrame, nombre: str) -> pd.DataFrame:
        g = e.groupby(["asignatura", "categoria"]).size().rename(nombre).reset_index()
        g[f"pct_{nombre}"] = (g[nombre] / g.groupby("asignatura")[nombre].transform("sum") * 100).round(1)
        return g

    categorias = _por_tipo(ev, "eventos")
    if not categorias.empty:
        # Outer: también los tipos que el curso usa y el alumno no (0 %, por ej. nunca entró a
        # Evaluación), pero solo en las materias donde tiene alguna interacción.
        curso = _por_tipo(ev_todos, "curso")[["asignatura", "categoria", "pct_curso"]]
        curso = curso[curso["asignatura"].isin(categorias["asignatura"])]
        categorias = (categorias.merge(curso, how="outer").fillna({"eventos": 0, "pct_eventos": 0.0})
                      .astype({"eventos": "int64"}).sort_values(["asignatura", "categoria"], ignore_index=True))

    al = alertas(d, fecha_corte, suyas, umbral) if suyas else pd.DataFrame(columns=["asignatura", "id_alumno"])
    return {
        "datos": datos.iloc[0],
        "materias": materias,
        "instrumentos": inst.reset_index(drop=True),
        "semanal": semanal,
        "categorias": categorias,
        "alertas": al[al["id_alumno"] == id_alumno].reset_index(drop=True),
        "evaluaciones": fechas_evaluaciones(d, fecha_corte, suyas or None).iloc[: None if suyas else 0],
        "eventos": ev.sort_values("fecha_hora", ascending=False)
                     [["fecha_hora", "asignatura", "categoria", "seccion", "accion", "descripcion"]]
                     .reset_index(drop=True),
    }


# ---------------------------------------------------------------------------
def main() -> None:
    pd.set_option("display.width", 200, "display.max_columns", 30)
    d = cargar()
    for fecha in ["2025-09-15", FECHA_CORTE_DEFECTO]:
        print(f"\n=== Fecha de corte {fecha} ===")
        print(kpis_generales(d, fecha).to_string(index=False))
    print("\nCorrelaciones (Spearman, nota vs. actividad):")
    c = correlaciones(d)
    print(c.pivot(index="variable", columns="asignatura", values="rho").to_string())


if __name__ == "__main__":
    main()
