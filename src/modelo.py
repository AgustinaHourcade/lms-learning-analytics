"""
ETAPA 2 - Modelo: SILVER (datos limpios) -> GOLD (modelo estrella)

Acá se aplican las reglas de negocio que silver no aplica:
  * Solo el perfil Alumnos entra a los hechos de alumnos (D10). Tutores,
    coordinadores e invitados van a tablas aparte (`otros_perfiles_*`).
  * Base de alumnos por materia = inscriptos (último estado Aceptada) ∪
    alumnos con al menos una nota (D11-D13).
  * Instrumento no rendido = 0 (D15), recuperatorio de PyE/AED reemplaza
    (D20) y el de Álgebra suma (D21).
  * Sesiones: más de 30 minutos sin eventos corta la sesión (D25).

Gold guarda HECHOS, que no dependen de la fecha de corte. Lo que depende de
la fecha (nota a la fecha de corte, activos/inactivos, etc.) se calcula en
src/metricas.py (D29). Por eso, por ejemplo, fact_calificacion guarda la nota
con y sin recuperatorio y la fecha de cada instrumento.

Tablas que genera:
  Dimensiones: dim_alumno, dim_asignatura, dim_instrumento, dim_accion, dim_fecha
  Hechos:      fact_interaccion, fact_sesion, fact_calificacion,
               fact_participacion, fact_matricula
  Aparte:      otros_perfiles_interaccion, otros_perfiles_participacion

Ejecutar desde la raíz del proyecto:
    python -m src.modelo
"""
from __future__ import annotations

import html
import re
import time
from pathlib import Path

import pandas as pd

from src.config import (ASIGNATURAS, CATEGORIA_SIN_MAPEO, CATEGORIAS_ACCIONES, ESQUEMA,
                        ESTADO_INSCRIPTO, GOLD, PALABRA_RECUPERATORIO, PERFIL_ALUMNO, REPORTS,
                        SESION_MINUTOS, SILVER)
from src.ingesta import clave

SIN_ACCION = "(sin acción)"
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# Avisos que se juntan durante la corrida (van al reporte del modelo).
avisos: list[str] = []


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def clave_instrumento(nombre: str, sin_recuperatorio: bool = False) -> str:
    """Clave para comparar nombres de instrumentos entre fuentes: sin emojis,
    tildes, espacios ni signos. '🚀Evaluación Semanal Nº1' -> 'evaluacionsemanalno1'.
    Con sin_recuperatorio=True también saca la palabra 'recuperatorio', así
    '🚀Recuperatorio: Evaluación Semanal Nº1' da la misma clave que el original."""
    texto = clave(html.unescape(str(nombre)))
    if sin_recuperatorio:
        texto = texto.replace(PALABRA_RECUPERATORIO, "")
    return "".join(c for c in texto if c.isascii() and c.isalnum())


def snake(texto: str) -> str:
    """'Foros - Cantidad Temas de debate' -> 'foros_cantidad_temas_de_debate'."""
    return re.sub(r"[^a-z0-9]+", "_", clave(texto)).strip("_")


def es_alumno(df: pd.DataFrame) -> pd.Series:
    return df["Perfil"].eq(PERFIL_ALUMNO)


# ---------------------------------------------------------------------------
# Dimensiones
# ---------------------------------------------------------------------------
def dim_asignatura() -> pd.DataFrame:
    filas = []
    for nombre, datos in ASIGNATURAS.items():
        esquema = ESQUEMA[nombre]
        filas.append({
            "asignatura": nombre, "sigla": datos["sigla"], "codigo": datos["codigo"],
            "metodo": esquema["metodo"], "total_max": esquema["total_max"],
            "corte_regular": esquema["cortes"]["Regular"],
            "corte_promociona": esquema["cortes"]["Promociona"],
            "regla_recuperatorio": esquema["recuperatorio"],
        })
    return pd.DataFrame(filas)


def fechas_de_instrumentos(traz: pd.DataFrame) -> pd.DataFrame:
    """Fecha de cada instrumento inferida de los eventos 'Realizar evaluación'
    de los alumnos (D18). Devuelve una fila por (asignatura, clave del instrumento)."""
    ev = traz[es_alumno(traz) & traz["Acción"].eq("Realizar evaluación")].copy()
    nombre = html.unescape  # la descripción trae los emojis como '&#128073;'
    ev["nombre"] = ev["Descripción"].map(nombre).str.extract(r"evaluaci[oó]n '(.+?)' de la unidad", expand=False)
    ev = ev.dropna(subset=["nombre"])
    ev["clave"] = ev["nombre"].map(clave_instrumento)
    return (ev.groupby(["asignatura", "clave"])
              .agg(nombre_en_trazabilidad=("nombre", "first"),
                   fecha_primera_realizacion=("Fecha", "min"),
                   fecha_mediana=("Fecha", "median"),
                   fecha_ultima_realizacion=("Fecha", "max"),
                   eventos_realizacion=("Fecha", "size"))
              .reset_index())


def dim_instrumento(cal: pd.DataFrame, traz: pd.DataFrame) -> pd.DataFrame:
    """Una fila por instrumento con notas. La fecha del instrumento es la MEDIANA
    de las realizaciones: la mitad del curso ya lo había rendido (D18)."""
    g = cal.groupby(["asignatura", "instrumento"])
    inst = g.agg(puntaje_maximo=("Nota máxima", "max"), puntajes_distintos=("Nota máxima", "nunique"),
                 alumnos_con_nota=("Usuario", "nunique"), fecha_exportacion=("fecha_exportacion", "max")).reset_index()
    if (inst["puntajes_distintos"] > 1).any():
        raise ValueError("Instrumento con más de un puntaje máximo:\n"
                         f"{inst.loc[inst['puntajes_distintos'] > 1, ['asignatura', 'instrumento']]}")
    inst = inst.drop(columns="puntajes_distintos")

    inst["clave"] = inst["instrumento"].map(clave_instrumento)
    inst = inst.merge(fechas_de_instrumentos(traz), on=["asignatura", "clave"], how="left")
    inst["fecha_instrumento"] = inst["fecha_mediana"].dt.normalize()
    inst["fecha_inferida"] = inst["fecha_instrumento"].notna()
    for _, f in inst[~inst["fecha_inferida"]].iterrows():
        avisos.append(f"{f['asignatura']}: «{f['instrumento']}» no tiene eventos 'Realizar evaluación' en la "
                      "trazabilidad; queda sin fecha y se considera disponible en cualquier fecha de corte.")

    # Recuperatorios: a qué instrumento recuperan y cómo se aplican.
    inst["es_recuperatorio"] = inst["instrumento"].map(lambda n: PALABRA_RECUPERATORIO in clave(n))
    inst["regla_recuperatorio"] = inst["asignatura"].map(lambda a: ESQUEMA[a]["recuperatorio"]).where(inst["es_recuperatorio"])
    inst["recupera_a"] = None
    for i, f in inst[inst["es_recuperatorio"] & inst["regla_recuperatorio"].eq("reemplaza")].iterrows():
        base = clave_instrumento(f["instrumento"], sin_recuperatorio=True)
        candidatos = inst[(inst["asignatura"] == f["asignatura"]) & ~inst["es_recuperatorio"]
                          & (inst["clave"] == base)]
        if len(candidatos) == 1:
            inst.at[i, "recupera_a"] = candidatos["instrumento"].iloc[0]
        else:
            avisos.append(f"{f['asignatura']}: no se encontró qué instrumento recupera «{f['instrumento']}». "
                          "No se tiene en cuenta para la nota final.")
    # Cuenta en la nota final todo lo que no sea un recuperatorio "reemplaza"
    # (ese se aplica sobre el instrumento original).
    inst["cuenta_en_final"] = ~(inst["es_recuperatorio"] & inst["regla_recuperatorio"].eq("reemplaza"))
    if inst.groupby(["asignatura", "recupera_a"]).size().gt(1).any():
        raise ValueError("Hay un instrumento con más de un recuperatorio; la regla de reemplazo no lo contempla.")

    siglas = inst["asignatura"].map(lambda a: ASIGNATURAS[a]["sigla"])
    inst = inst.assign(_sigla=siglas).sort_values(["asignatura", "fecha_instrumento", "instrumento"], na_position="last")
    inst["orden"] = inst.groupby("asignatura").cumcount() + 1
    inst["id_instrumento"] = inst["_sigla"] + "-" + inst["orden"].astype(str).str.zfill(2)
    columnas = ["id_instrumento", "asignatura", "instrumento", "orden", "puntaje_maximo", "es_recuperatorio",
                "regla_recuperatorio", "recupera_a", "cuenta_en_final", "fecha_instrumento", "fecha_inferida",
                "fecha_primera_realizacion", "fecha_ultima_realizacion", "eventos_realizacion",
                "alumnos_con_nota", "fecha_exportacion"]
    return inst[columnas].reset_index(drop=True)


def dim_accion(traz: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (Sección, Acción) vista en la trazabilidad, con su categoría.
    La categoría sale del CSV de referencia: primero se busca la combinación
    exacta sección + acción y, si no está, la acción sola (sección vacía)."""
    mapa = pd.read_csv(CATEGORIAS_ACCIONES, dtype=str, keep_default_na=False, encoding="utf-8")
    exacto = {(s, a): c for s, a, c in mapa[mapa["seccion"] != ""].itertuples(index=False)}
    por_accion = {a: c for s, a, c in mapa[mapa["seccion"] == ""].itertuples(index=False)}

    acc = (traz.assign(accion=traz["Acción"].fillna(SIN_ACCION))
               .groupby(["Sección", "accion"]).size().rename("eventos").reset_index()
               .rename(columns={"Sección": "seccion"}))
    acc["categoria"] = [exacto.get((s, a), por_accion.get(a, CATEGORIA_SIN_MAPEO))
                        for s, a in zip(acc["seccion"], acc["accion"])]
    sin_mapeo = acc.loc[acc["categoria"] == CATEGORIA_SIN_MAPEO, "accion"].unique()
    if len(sin_mapeo):
        avisos.append(f"Acciones sin categoría en {CATEGORIAS_ACCIONES.name} (quedan como "
                      f"'{CATEGORIA_SIN_MAPEO}'): {', '.join(sorted(sin_mapeo))}.")
    acc = acc.sort_values(["categoria", "seccion", "accion"]).reset_index(drop=True)
    acc.insert(0, "id_accion", range(1, len(acc) + 1))
    return acc


def dim_fecha(*series: pd.Series) -> pd.DataFrame:
    """Calendario diario continuo entre la primera y la última fecha de los datos."""
    todas = pd.concat([s.dropna() for s in series])
    dias = pd.date_range(todas.min().normalize(), todas.max().normalize(), freq="D")
    iso = dias.isocalendar()
    return pd.DataFrame({
        "fecha": dias,
        "anio": dias.year, "mes": dias.month, "nombre_mes": [MESES[m - 1] for m in dias.month],
        "dia": dias.day, "dia_semana": dias.day_of_week, "nombre_dia": [DIAS[d] for d in dias.day_of_week],
        "es_fin_de_semana": dias.day_of_week >= 5,
        "semana_iso": iso["week"].to_numpy(),
        "inicio_semana": dias - pd.to_timedelta(dias.day_of_week, unit="D"),
        "inicio_mes": dias.to_period("M").to_timestamp(),
    })


def dim_alumno(traz, part, cal, mat) -> pd.DataFrame:
    """Todos los alumnos que aparecen en alguna fuente (para que la ficha
    individual encuentre a cualquiera). El nombre se toma, en este orden, de
    calificaciones, participación, trazabilidad y matriculados."""
    fuentes = [
        cal[["Usuario", "Apellido", "Nombre"]],
        part.loc[es_alumno(part), ["Usuario", "Apellido", "Nombre"]],
        traz.loc[es_alumno(traz), ["Usuario", "Apellido", "Nombre"]],
    ]
    # Matriculados trae 'PÉREZ, FELIPE': se separa y se pasa a formato título.
    partes = mat["Alumno"].str.split(",", n=1, expand=True)
    fuentes.append(pd.DataFrame({"Usuario": mat["Identificación"],
                                 "Apellido": partes[0].str.strip().str.title(),
                                 "Nombre": partes[1].str.strip().str.title()}))
    todos = pd.concat(fuentes, ignore_index=True).dropna(subset=["Usuario"])

    distintos = todos.drop_duplicates().assign(k=lambda d: (d["Apellido"] + d["Nombre"]).map(clave))
    inconsistentes = distintos.groupby("Usuario")["k"].nunique().gt(1).sum()
    if inconsistentes:
        avisos.append(f"{inconsistentes} alumnos tienen el nombre escrito distinto según la fuente; "
                      "se usa el de la primera fuente disponible.")

    alu = todos.drop_duplicates("Usuario").rename(columns={"Usuario": "id_alumno", "Apellido": "apellido",
                                                          "Nombre": "nombre"})
    alu["nombre_completo"] = alu["apellido"] + ", " + alu["nombre"]
    return alu.sort_values("id_alumno").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Hechos
# ---------------------------------------------------------------------------
def fact_matricula(mat: pd.DataFrame, cal: pd.DataFrame, traz: pd.DataFrame) -> pd.DataFrame:
    """Una fila por alumno y materia: todos los que figuran en Matriculados
    (con su ÚLTIMO estado, D13) y todos los que tienen alguna nota.
    `en_base` marca la base de alumnos de la materia (D11): inscripto o con nota."""
    ult = (mat.sort_values(["Fecha inscripción", "Nro de Transacción"])
              .groupby(["asignatura", "Identificación"])
              .agg(estado=("Estado Insc.", "last"), fecha_inscripcion=("Fecha inscripción", "last"),
                   instancia=("Instancia", "last"), movimientos=("Estado Insc.", "size"))
              .reset_index().rename(columns={"Identificación": "id_alumno"}))
    ult["en_matriculados"] = True

    notas = (cal.groupby(["asignatura", "Usuario"]).size().rename("instrumentos_con_nota")
                .reset_index().rename(columns={"Usuario": "id_alumno"}))
    ev = traz[es_alumno(traz)]
    actividad = (ev.groupby(["asignatura", "Usuario"])["Fecha"].agg(["min", "max", "size"])
                   .set_axis(["primera_interaccion", "ultima_interaccion", "interacciones"], axis=1)
                   .reset_index().rename(columns={"Usuario": "id_alumno"}))

    df = ult.merge(notas, on=["asignatura", "id_alumno"], how="outer")
    df = df.merge(actividad, on=["asignatura", "id_alumno"], how="left")
    df["en_matriculados"] = df["en_matriculados"].fillna(False).astype(bool)
    df["instrumentos_con_nota"] = df["instrumentos_con_nota"].fillna(0).astype(int)
    df["interacciones"] = df["interacciones"].fillna(0).astype(int)
    df["inscripto"] = df["estado"].eq(ESTADO_INSCRIPTO)
    df["tiene_nota"] = df["instrumentos_con_nota"] > 0
    df["en_base"] = df["inscripto"] | df["tiene_nota"]
    columnas = ["id_alumno", "asignatura", "en_base", "inscripto", "tiene_nota", "en_matriculados", "estado",
                "fecha_inscripcion", "instancia", "movimientos", "instrumentos_con_nota", "interacciones",
                "primera_interaccion", "ultima_interaccion"]
    return df[columnas].sort_values(["asignatura", "id_alumno"]).reset_index(drop=True)


def fact_calificacion(cal: pd.DataFrame, inst: pd.DataFrame, matricula: pd.DataFrame) -> pd.DataFrame:
    """Una fila por alumno de la base × instrumento de su materia (D15: lo no
    rendido es 0). Columnas clave para las métricas:
      puntos_sin_recuperatorio  nota del instrumento, 0 si no lo rindió
      puntos                    igual, pero si rindió el recuperatorio que
                                reemplaza (D20) vale la nota del recuperatorio
      fecha_recuperatorio       para aplicar el reemplazo solo si el
                                recuperatorio ya pasó a la fecha de corte
      cuenta_en_final           False para los recuperatorios que reemplazan
                                (ya están aplicados en `puntos` del original)
    """
    base = matricula.loc[matricula["en_base"], ["asignatura", "id_alumno", "inscripto"]]
    grilla = base.merge(inst[["asignatura", "id_instrumento", "instrumento", "puntaje_maximo", "es_recuperatorio",
                              "recupera_a", "cuenta_en_final", "fecha_instrumento"]], on="asignatura")

    notas = cal.rename(columns={"Usuario": "id_alumno", "Nota obtenida": "nota_obtenida",
                                "Observaciones": "observaciones"})[
        ["asignatura", "id_alumno", "instrumento", "nota_obtenida", "observaciones"]]
    df = grilla.merge(notas, on=["asignatura", "id_alumno", "instrumento"], how="left")
    df["rindio"] = df["nota_obtenida"].notna()
    df["puntos_sin_recuperatorio"] = df["nota_obtenida"].fillna(0.0)

    # Recuperatorios que reemplazan: se pegan al instrumento original.
    recu = df.loc[df["recupera_a"].notna() & df["rindio"],
                  ["asignatura", "id_alumno", "recupera_a", "id_instrumento", "nota_obtenida", "fecha_instrumento"]]
    recu = recu.rename(columns={"recupera_a": "instrumento", "id_instrumento": "id_recuperatorio",
                                "nota_obtenida": "nota_recuperatorio", "fecha_instrumento": "fecha_recuperatorio"})
    df = df.merge(recu, on=["asignatura", "id_alumno", "instrumento"], how="left")
    df["rindio_recuperatorio"] = df["nota_recuperatorio"].notna()
    df["puntos"] = df["nota_recuperatorio"].where(df["rindio_recuperatorio"], df["puntos_sin_recuperatorio"])
    df["nota_pct"] = (df["puntos"] / df["puntaje_maximo"] * 100).round(2)

    columnas = ["id_alumno", "asignatura", "id_instrumento", "instrumento", "inscripto", "rindio", "nota_obtenida",
                "observaciones", "puntaje_maximo", "puntos_sin_recuperatorio", "rindio_recuperatorio",
                "id_recuperatorio", "nota_recuperatorio", "fecha_recuperatorio", "puntos", "nota_pct",
                "cuenta_en_final", "es_recuperatorio", "fecha_instrumento"]
    return df[columnas].sort_values(["asignatura", "id_alumno", "id_instrumento"]).reset_index(drop=True)


def _con_base(df: pd.DataFrame, matricula: pd.DataFrame) -> pd.DataFrame:
    """Agrega `en_base` e `inscripto` (alumno × materia) a una tabla de alumnos."""
    flags = matricula[["asignatura", "id_alumno", "en_base", "inscripto"]]
    df = df.merge(flags, on=["asignatura", "id_alumno"], how="left")
    df[["en_base", "inscripto"]] = df[["en_base", "inscripto"]].fillna(False).astype(bool)
    return df


def sesionizar(ev: pd.DataFrame) -> pd.Series:
    """Número de sesión global: una sesión nueva empieza con el primer evento de
    cada alumno y materia, o después de más de SESION_MINUTOS sin eventos (D25).
    `ev` tiene que venir ordenado por usuario, materia y fecha."""
    mismo = (ev["id_alumno"].eq(ev["id_alumno"].shift()) & ev["asignatura"].eq(ev["asignatura"].shift()))
    hueco = ev["fecha_hora"].diff() > pd.Timedelta(minutes=SESION_MINUTOS)
    return (~mismo | hueco).cumsum()


def _interacciones(traz: pd.DataFrame, acciones: pd.DataFrame) -> pd.DataFrame:
    df = traz.rename(columns={"Fecha": "fecha_hora", "Usuario": "id_alumno", "IP Usuario": "ip",
                              "Perfil": "perfil", "Sección": "seccion", "Descripción": "descripcion"})
    df["accion"] = df["Acción"].fillna(SIN_ACCION)
    df = df.merge(acciones[["id_accion", "seccion", "accion", "categoria"]], on=["seccion", "accion"], how="left")
    df["fecha"] = df["fecha_hora"].dt.normalize()
    df["hora"] = df["fecha_hora"].dt.hour
    df["dia_semana"] = df["fecha_hora"].dt.day_of_week
    return df


def fact_interaccion(traz: pd.DataFrame, acciones: pd.DataFrame, matricula: pd.DataFrame) -> pd.DataFrame:
    df = _interacciones(traz[es_alumno(traz)], acciones)
    df = df.sort_values(["id_alumno", "asignatura", "fecha_hora"], kind="stable").reset_index(drop=True)
    df["id_sesion"] = sesionizar(df)
    df = _con_base(df, matricula)
    df.insert(0, "id_evento", range(1, len(df) + 1))
    columnas = ["id_evento", "id_alumno", "asignatura", "fecha_hora", "fecha", "hora", "dia_semana", "id_sesion",
                "id_accion", "seccion", "accion", "categoria", "descripcion", "ip", "en_base", "inscripto"]
    return df[columnas]


def fact_sesion(inter: pd.DataFrame) -> pd.DataFrame:
    """Una fila por sesión. Una sesión de un solo evento dura 0 minutos."""
    s = (inter.groupby("id_sesion")
              .agg(id_alumno=("id_alumno", "first"), asignatura=("asignatura", "first"),
                   inicio=("fecha_hora", "min"), fin=("fecha_hora", "max"), eventos=("id_evento", "size"),
                   en_base=("en_base", "first"), inscripto=("inscripto", "first"))
              .reset_index())
    s["duracion_min"] = ((s["fin"] - s["inicio"]).dt.total_seconds() / 60).round(2)
    s["fecha"] = s["inicio"].dt.normalize()
    return s


COLUMNAS_PARTICIPACION = {
    "Usuario": "id_alumno", "Perfil": "perfil", "Fecha alta": "fecha_alta", "Avance": "avance",
    "Interacciones": "interacciones", "Primera interacción": "primera_interaccion",
    "Última interacción": "ultima_interaccion", "Tiempo estimado de uso (min)": "tiempo_uso_min",
    "Cantidad de emails enviados": "emails_enviados",
}
DESCARTAR_PARTICIPACION = ["Apellido", "Nombre", "Email", "Aula", "Tiempo estimado de uso", "archivo_origen"]


def _participacion(part: pd.DataFrame) -> pd.DataFrame:
    df = part.drop(columns=DESCARTAR_PARTICIPACION).rename(columns=COLUMNAS_PARTICIPACION)
    return df.rename(columns={c: snake(c) for c in df.columns if c not in COLUMNAS_PARTICIPACION.values()})


def fact_participacion(part: pd.DataFrame, matricula: pd.DataFrame) -> pd.DataFrame:
    """Reporte de participación, solo alumnos. Ojo (D14): lista a toda la cohorte
    (319 por materia); `en_base` marca a los de la base de la materia."""
    df = _participacion(part[es_alumno(part)]).drop(columns="perfil")
    df = _con_base(df, matricula)
    df["sin_actividad"] = df["primera_interaccion"].isna()
    primeras = ["id_alumno", "asignatura", "en_base", "inscripto"]
    return df[primeras + [c for c in df.columns if c not in primeras]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
def modelar(origen: Path = SILVER, destino: Path = GOLD, reportes: Path = REPORTS, verbose: bool = True) -> dict:
    """Lee silver, arma el modelo y escribe gold. Devuelve {tabla: filas}."""
    log = print if verbose else (lambda *a, **k: None)
    avisos.clear()
    destino.mkdir(parents=True, exist_ok=True)
    traz, part, cal, mat = (pd.read_parquet(origen / f"{t}.parquet")
                            for t in ["trazabilidad", "participacion", "calificaciones", "matriculados"])

    acciones = dim_accion(traz)
    instrumentos = dim_instrumento(cal, traz)
    matricula = fact_matricula(mat, cal, traz)
    interaccion = fact_interaccion(traz, acciones, matricula)

    tablas = {
        "dim_alumno": dim_alumno(traz, part, cal, mat),
        "dim_asignatura": dim_asignatura(),
        "dim_instrumento": instrumentos,
        "dim_accion": acciones,
        "dim_fecha": dim_fecha(traz["Fecha"], mat["Fecha inscripción"], part["Fecha alta"]),
        "fact_interaccion": interaccion,
        "fact_sesion": fact_sesion(interaccion),
        "fact_calificacion": fact_calificacion(cal, instrumentos, matricula),
        "fact_participacion": fact_participacion(part, matricula),
        "fact_matricula": matricula,
        "otros_perfiles_interaccion": _interacciones(traz[~es_alumno(traz)], acciones)
            .drop(columns=["Acción", "Apellido", "Nombre", "Aula", "archivo_origen"]),
        "otros_perfiles_participacion": _participacion(part[~es_alumno(part)]),
    }
    filas = {}
    for nombre, df in tablas.items():
        df.to_parquet(destino / f"{nombre}.parquet", index=False)
        filas[nombre] = len(df)
        log(f"  {nombre:<30} {len(df):>8,} filas")

    escribir_reporte(tablas, reportes)
    for a in avisos:
        log(f"  aviso: {a}")
    return {"filas": filas, "avisos": list(avisos)}


def escribir_reporte(t: dict[str, pd.DataFrame], reportes: Path) -> None:
    """reports/modelo.md: conteos que sirven para el informe y para controlar."""
    reportes.mkdir(parents=True, exist_ok=True)
    m = t["fact_matricula"]
    base = (m.groupby("asignatura")
             .agg(base=("en_base", "sum"), inscriptos=("inscripto", "sum"),
                  inscriptos_sin_nota=("inscripto", lambda s: (s & ~m.loc[s.index, "tiene_nota"]).sum()),
                  con_nota_no_inscriptos=("tiene_nota", lambda s: (s & ~m.loc[s.index, "inscripto"]).sum()))
             .reset_index())
    inst = t["dim_instrumento"]
    lineas = ["# Modelo (silver -> gold)", "", "Generado por el pipeline (`python -m src.pipeline`). No editar a mano.", "",
              "| Tabla | Filas |", "|---|---|", *[f"| {k} | {len(v):,} |" for k, v in t.items()], "",
              "## Base de alumnos por materia (D11)", "",
              "| Materia | Base | Inscriptos | Inscriptos sin nota | Con nota sin estar inscriptos |",
              "|---|---|---|---|---|",
              *[f"| {r.asignatura} | {r.base} | {r.inscriptos} | {r.inscriptos_sin_nota} | {r.con_nota_no_inscriptos} |"
                for r in base.itertuples()], "",
              "## Instrumentos (fecha = mediana de los eventos 'Realizar evaluación', D18)", "",
              "| ID | Materia | Instrumento | Máx. | Notas | Fecha | Recupera a |", "|---|---|---|---|---|---|---|",
              *[f"| {r.id_instrumento} | {r.asignatura} | {r.instrumento} | {r.puntaje_maximo:g} | {r.alumnos_con_nota} | "
                f"{r.fecha_instrumento.date() if pd.notna(r.fecha_instrumento) else 's/d'} | {r.recupera_a or ''} |"
                for r in inst.itertuples()], "",
              f"## Sesiones (corte a {SESION_MINUTOS} minutos sin eventos, D25)", "",
              f"- {len(t['fact_sesion']):,} sesiones de alumnos; duración mediana "
              f"{t['fact_sesion']['duracion_min'].median():.1f} min.", ""]
    if avisos:
        lineas += ["## Avisos", *[f"- {a}" for a in avisos], ""]
    (reportes / "modelo.md").write_text("\n".join(lineas), encoding="utf-8")


def main() -> None:
    t0 = time.time()
    modelar()
    print(f"Listo en {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
