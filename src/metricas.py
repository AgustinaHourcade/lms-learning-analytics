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

from src.config import (CONDICIONES, ESQUEMA, FECHA_CORTE_DEFECTO, GOLD, SIN_EVALUACIONES,
                        UMBRAL_INACTIVIDAD_DIAS)

ACTIVO, INACTIVO, SIN_ACTIVIDAD = "Activo", "Inactivo", "Sin actividad"
ESTADOS_ACTIVIDAD = [ACTIVO, INACTIVO, SIN_ACTIVIDAD]
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
    (entró alguna vez, pero hace más) o Sin actividad (nunca entró) (D35)."""
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


def fechas_evaluaciones(d: Datos, fecha_corte=None, asignatura=None) -> pd.DataFrame:
    """Instrumentos ya tomados a la fecha de corte, para marcarlos en las líneas de tiempo."""
    i = _filtrar(d.instrumentos, asignatura)
    i = i[i["fecha_instrumento"].notna() & (i["fecha_instrumento"] <= fecha_de_corte(fecha_corte))]
    return i[["asignatura", "id_instrumento", "instrumento", "fecha_instrumento", "es_recuperatorio"]] \
            .reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cruces: notas vs. participación
# ---------------------------------------------------------------------------
def _fuerza(rho: float) -> str:
    r = abs(rho)
    return "nula" if r < 0.1 else "débil" if r < 0.3 else "moderada" if r < 0.5 else "fuerte"


def correlaciones(d: Datos, fecha_corte=None, asignatura=None, umbral: int = UMBRAL_INACTIVIDAD_DIAS,
                  variables: list[str] | None = None) -> pd.DataFrame:
    """Correlación de Spearman entre cada variable de actividad y la nota (sobre
    100), por materia. Spearman porque las variables son asimétricas y con
    muchos ceros: mide si a más actividad hay más nota, sin suponer una recta."""
    t = tabla_alumnos(d, fecha_corte, asignatura, umbral)
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
                    contra el % del curso
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
        categorias = categorias.merge(_por_tipo(ev_todos, "curso")[["asignatura", "categoria", "pct_curso"]],
                                      how="left")

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
