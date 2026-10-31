"""
PASO 3 - Limpieza: BRONZE (Parquet, todo texto) -> SILVER (Parquet tipado)

Regla: las columnas del Excel se mantienen con su nombre original.
  * Solo se corrigen tipos (fechas, números) y se sacan filas basura/duplicadas.
  * Si un valor necesita otra forma (ej. Nota '24.00/25.00'), se agrega una
    columna NUEVA al lado y la original queda intacta.
  * No se aplican reglas de negocio (0 por no rendido, recuperatorio, filtro
    por perfil): eso va en modelo/kpis. Silver = datos limpios, nada más.

Genera además reports/calidad_datos.md con lo que se encontró y se corrigió.

Ejecutar desde la raíz del proyecto:
    python -m src.limpieza
"""
from __future__ import annotations

import time

import pandas as pd

from src.config import BRONZE, REPORTS, SILVER

# Cada limpiador anota acá lo que hizo; al final se vuelca al reporte.
hallazgos: dict[str, list[str]] = {}


def anotar(tabla: str, texto: str) -> None:
    hallazgos.setdefault(tabla, []).append(texto)


def fecha(serie: pd.Series, formato: str) -> pd.Series:
    """Parsea con formato explícito: si algún valor no respeta el formato, falla
    (mejor enterarse que tener fechas mal leídas en silencio)."""
    return pd.to_datetime(serie, format=formato)


# ---------------------------------------------------------------------------
# Limpiadores (uno por tabla)
# ---------------------------------------------------------------------------
def limpiar_trazabilidad(df: pd.DataFrame) -> pd.DataFrame:
    df["Fecha"] = fecha(df["Fecha"], "%Y-%m-%d %H:%M:%S")

    dup = df.duplicated()
    anotar("trazabilidad", f"{dup.sum():,} filas duplicadas exactas eliminadas (mismo usuario, segundo, acción).")
    df = df[~dup]

    sin_accion = df["Acción"].isna()
    anotar("trazabilidad", f"{sin_accion.sum()} filas sin `Acción` (descargas de adjuntos en Foros). Se conservan con `Acción` vacía.")
    anotar("trazabilidad", f"Rango de fechas: {df['Fecha'].min()} a {df['Fecha'].max()}.")
    anotar("trazabilidad", "Eventos por perfil: " + ", ".join(f"{k} {v:,}" for k, v in df["Perfil"].value_counts().items()) + ".")
    return df.reset_index(drop=True)


def limpiar_participacion(df: pd.DataFrame) -> pd.DataFrame:
    df["Fecha alta"] = fecha(df["Fecha alta"], "%d/%m/%Y")
    for col in ["Primera interacción", "Última interacción"]:
        df[col] = fecha(df[col], "%d/%m/%Y %H:%M:%S")

    # 'hh:mm' puede pasar de 24 h (ej. '87:47'), por eso no se usa un tipo hora.
    hh, mm = df["Tiempo estimado de uso"].str.split(":", expand=True).astype(int).T.values
    df["Tiempo estimado de uso (min)"] = hh * 60 + mm

    texto = {"Usuario", "Apellido", "Nombre", "Email", "Aula", "Perfil", "Tiempo estimado de uso",
             "Fecha alta", "Primera interacción", "Última interacción", "asignatura", "archivo_origen"}
    numericas = [c for c in df.columns if c not in texto and c != "Tiempo estimado de uso (min)"]
    no_aplica = df["Avance"].eq("no aplica")
    anotar("participacion", f"`Avance` = 'no aplica' en {no_aplica.sum()} filas (solo perfiles no alumno: "
           + ", ".join(f"{k} {v}" for k, v in df.loc[no_aplica, "Perfil"].value_counts().items()) + "). Quedan vacías.")
    df.loc[no_aplica, "Avance"] = None
    df[numericas] = df[numericas].astype("Int64")  # falla si hay algo no numérico

    sin_actividad = df["Primera interacción"].isna()
    anotar("participacion", f"{sin_actividad.sum()} usuarios sin ninguna interacción (sin `Primera/Última interacción`).")
    anotar("participacion", "`Email` viene vacío en todas las filas (anonimizado). Se conserva la columna.")
    anotar("participacion", "Usuarios por perfil: " + ", ".join(f"{k} {v}" for k, v in df["Perfil"].value_counts().items()) + ".")
    return df


def limpiar_calificaciones(df: pd.DataFrame) -> pd.DataFrame:
    # '24.00/25.00' -> obtenida 24.0, máxima 25.0. 'Nota' original queda igual.
    partes = df["Nota"].str.split("/", expand=True).astype(float)
    df["Nota obtenida"], df["Nota máxima"] = partes[0], partes[1]
    df["Nota (%)"] = (df["Nota obtenida"] / df["Nota máxima"] * 100).round(2)

    fuera_rango = (df["Nota obtenida"] < 0) | (df["Nota obtenida"] > df["Nota máxima"])
    if fuera_rango.any():
        raise ValueError(f"Notas fuera de rango:\n{df.loc[fuera_rango, ['Usuario', 'instrumento', 'Nota']]}")

    dup = df.duplicated(["asignatura", "instrumento", "Usuario"])
    if dup.any():
        raise ValueError(f"Alumno con dos notas en el mismo instrumento:\n{df.loc[dup, ['Usuario', 'instrumento']]}")

    df["fecha_exportacion"] = fecha(df["fecha_exportacion"], "%d/%m/%Y %H:%M")
    anotar("calificaciones", f"`Nota` separada en `Nota obtenida`, `Nota máxima` y `Nota (%)`. Ninguna fuera de rango.")
    anotar("calificaciones", f"Usuarios desactivados (celda coloreada): {int(df['desactivado'].sum())}.")
    anotar("calificaciones", "`Detalle` viene vacío en todas las filas. Se conserva la columna.")
    anotar("calificaciones", "Instrumentos por asignatura: " + "; ".join(
        f"{a} {g['instrumento'].nunique()}" for a, g in df.groupby("asignatura")) + ".")
    return df


def limpiar_matriculados(df: pd.DataFrame) -> pd.DataFrame:
    pie = df["Identificación"].isna() & df["Alumno"].str.startswith("Cantidad de filas", na=False)
    anotar("matriculados", f"{pie.sum()} filas de pie de tabla ('Cantidad de filas:') eliminadas.")
    df = df[~pie].copy()

    df["Fecha inscripción"] = fecha(df["Fecha inscripción"], "%d/%m/%Y %H:%M:%S")
    n = df.groupby(["asignatura", "Identificación"]).size()
    anotar("matriculados", f"{(n > 1).sum()} alumnos con más de una fila (altas y bajas). Se conservan todas; el último estado se toma en el modelo.")
    anotar("matriculados", "Estados: " + ", ".join(f"{k} {v}" for k, v in df["Estado Insc."].value_counts().items()) + ".")
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
LIMPIADORES = {
    "trazabilidad": limpiar_trazabilidad,
    "participacion": limpiar_participacion,
    "calificaciones": limpiar_calificaciones,
    "matriculados": limpiar_matriculados,
}


def main() -> None:
    SILVER.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    resumen = []

    for nombre, limpiar in LIMPIADORES.items():
        bronze = pd.read_parquet(BRONZE / f"{nombre}.parquet")
        silver = limpiar(bronze.copy())
        silver.to_parquet(SILVER / f"{nombre}.parquet", index=False)
        resumen.append(f"| {nombre} | {len(bronze):,} | {len(silver):,} | {silver.shape[1]} |")
        print(f"  {nombre:<15} {len(bronze):>8,} -> {len(silver):>8,} filas")

    lineas = ["# Calidad de datos (bronze -> silver)", "",
              "Generado por `python -m src.limpieza`. No editar a mano.", "",
              "| Tabla | Filas bronze | Filas silver | Columnas |", "|---|---|---|---|", *resumen, ""]
    for tabla, items in hallazgos.items():
        lineas += [f"## {tabla}", *[f"- {i}" for i in items], ""]
    (REPORTS / "calidad_datos.md").write_text("\n".join(lineas), encoding="utf-8")
    print(f"\n  Reporte -> reports/calidad_datos.md\nListo en {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
