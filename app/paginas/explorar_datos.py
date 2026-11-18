"""Explorar datos: las tablas que genera el pipeline (silver y gold), con búsqueda,
filtros, control de vacíos y descarga en CSV. No usa los filtros de la barra lateral."""
import pandas as pd
import streamlit as st

import componentes as comp
from src.config import GOLD, SILVER

# Columnas de trazabilidad del pipeline: ocultas por defecto, se activan desde "Columnas".
TECNICAS = ["archivo_origen", "instrumento_raw", "color_celda", "desactivado"]
MAX_FILAS = 1000
MAX_TARJETAS_VACIOS = 8

comp.titulo("Explorar datos", "Las tablas tal como quedaron después del pipeline, para auditar un número o buscar "
                              "un caso puntual.")

capas = {"silver": SILVER, "gold": comp.carpeta_gold()}
disponibles = {f"{capa} / {p.stem}": p for capa, carpeta in capas.items() for p in sorted(carpeta.glob("*.parquet"))}
if not disponibles:
    comp.html(comp.aviso("Corré <span class='mono'>python -m src.pipeline</span> desde la raíz del repo.",
                         "atencion", "No hay tablas todavía."))
    st.stop()


@st.cache_data(max_entries=4, show_spinner="Leyendo la tabla…")
def leer(path: str, modificado: float) -> pd.DataFrame:  # `modificado` invalida el caché al regenerar
    return pd.read_parquet(path)


def buscar(df: pd.DataFrame, texto: str) -> pd.DataFrame:
    """Filas donde alguna columna de texto contiene `texto` (sin distinguir mayúsculas)."""
    columnas = [c for c in df.columns if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])]
    if not texto.strip() or not columnas:
        return df
    mascara = pd.Series(False, index=df.index)
    for c in columnas:
        mascara |= df[c].astype("string").str.contains(texto.strip(), case=False, regex=False, na=False)
    return df[mascara]


def columna_id(df: pd.DataFrame) -> tuple[str, str] | None:
    for col, etiqueta in [("id_alumno", "Alumnos"), ("Identificación", "Alumnos"), ("Usuario", "Usuarios")]:
        if col in df:
            return col, etiqueta
    return None


def calidad(df: pd.DataFrame) -> list[dict]:
    """Columnas con vacíos o con un solo valor, de la más a la menos problemática."""
    filas = []
    n = len(df)
    for c in df.columns:
        vacios = int(df[c].isna().sum())
        if vacios:
            pct = vacios / n * 100
            filas.append({"columna": c, "orden": pct, "tono": "error" if pct == 100 else "atencion" if pct >= 50
                          else "info", "valor": "< 0,1 % vacía" if pct < 0.05 else
                          f"{comp.num(pct, 0 if pct == 100 else 1)} % vacía",
                          "detalle": f"{comp.num(vacios)} de {comp.num(n)} filas sin dato"})
        elif n > 1:
            try:
                unicos = df[c].nunique()
            except TypeError:  # valores no comparables (listas, etc.)
                continue
            if unicos == 1:
                filas.append({"columna": c, "orden": -1, "tono": "info", "valor": "1 valor",
                              "detalle": f"siempre «{comp.esc(df[c].iloc[0])}»: no aporta información"})
    return sorted(filas, key=lambda f: -f["orden"])


def tarjeta_vacio(f: dict) -> str:
    fondo, borde, color, color_fuerte = {"error": ("#FBE9E6", "#F2CFC9", "#7A3028", "#93241C"),
                                         "atencion": ("#FBF0DC", "#F0E2C4", "#7A5000", "#6B4700"),
                                         "info": ("#FFFFFF", "#E3E1DC", "#57544C", "#1A1917")}[f["tono"]]
    return (f'<div class="tfi-vacio" style="background:{fondo};border-color:{borde}">'
            f'<p class="col" style="color:{color}">{comp.esc(f["columna"])}</p>'
            f'<p class="val num" style="color:{color_fuerte}">{f["valor"]}</p>'
            f'<p class="det" style="color:{color}">{f["detalle"]}</p></div>')


# ---------------------------------------------------------------------------
# Selector, búsqueda y filtros
# ---------------------------------------------------------------------------
with st.container(key="tarjeta-selector"):
    c1, c2 = st.columns([1, 1.15])
    elegida = c1.selectbox("Tabla", list(disponibles))
    texto = c2.text_input("Buscar en la tabla", placeholder="ID, apellido, instrumento…",
                          help="Busca en todas las columnas de texto, sin distinguir mayúsculas.")
    path = disponibles[elegida]
    df_total = leer(str(path), path.stat().st_mtime)
    df = df_total

    f1, f2 = st.columns([1, 1.15])
    if "asignatura" in df:
        opciones = [a for a in comp.ASIGNATURAS if a in set(df["asignatura"])] + \
                   sorted(set(df["asignatura"].dropna()) - set(comp.ASIGNATURAS))
        materias = f1.multiselect("Asignatura", opciones, default=opciones, placeholder="Elegí una o más materias")
        df = df[df["asignatura"].isin(materias)]
    if "Perfil" in df:
        perfiles_todos = sorted(df_total["Perfil"].dropna().unique())
        perfiles = f2.multiselect("Perfil", perfiles_todos, default=perfiles_todos)
        df = df[df["Perfil"].isin(perfiles)]
    df_filtrado = df          # la calidad de las columnas se mira sin la búsqueda de texto
    df = buscar(df, texto)

# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
col_kpis, col_barras = st.columns([1, 1.15]) if "asignatura" in df else (st.container(), None)
with col_kpis:
    ident = columna_id(df)
    items = [("Filas", comp.num(len(df)), None if len(df) == len(df_total) else f"de {comp.num(len(df_total))} en total"),
             ("Columnas", comp.num(df.shape[1]))]
    if ident:
        items.append((ident[1], comp.num(df[ident[0]].nunique()), f"Valores distintos de `{ident[0]}`."))
    comp.tarjetas(items)
if col_barras is not None:
    with col_barras.container(key="tarjeta-barras"):
        conteo = df["asignatura"].value_counts()
        filas = [(a.split()[0], int(n), comp.COLORES_MATERIA.get(a, comp.NEUTRO)) for a, n in conteo.items()]
        comp.html('<p class="tfi-etq">Filas por asignatura</p>' +
                  (comp.barras(filas) if filas else '<p class="tfi-sub">No hay filas con estos filtros.</p>'))

# ---------------------------------------------------------------------------
# Calidad de las columnas
# ---------------------------------------------------------------------------
with st.container(key="tarjeta-calidad"):
    problemas = calidad(df_filtrado)
    con_vacios = sum(1 for p in problemas if p["orden"] >= 0)
    comp.html(comp.seccion("Columnas con vacíos",
                           derecha=f"{con_vacios} con vacíos · {len(problemas) - con_vacios} con un solo valor"
                           if problemas else "",
                           subtitulo="Es lo primero que conviene mirar antes de usar una columna en un indicador. "
                                     "Usa los filtros de materia y perfil, no la búsqueda."))
    if not problemas:
        comp.html(comp.aviso("Todas las columnas están completas y tienen más de un valor.", "exito"))
    else:
        comp.html('<div class="tfi-grilla">' + "".join(tarjeta_vacio(p) for p in problemas[:MAX_TARJETAS_VACIOS])
                  + "</div>")
        if len(problemas) > MAX_TARJETAS_VACIOS:
            with st.expander(f"Ver las {len(problemas)} columnas"):
                st.dataframe(pd.DataFrame(problemas)[["columna", "valor", "detalle"]]
                             .rename(columns={"columna": "Columna", "valor": "Problema", "detalle": "Detalle"}),
                             hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
with st.container(key="tarjeta-datos"):
    tecnicas = [c for c in TECNICAS if c in df.columns]
    clave_cols = f"columnas_{elegida}"
    st.session_state.setdefault(clave_cols, [c for c in df.columns if c not in tecnicas])
    visibles = [c for c in st.session_state[clave_cols] if c in df.columns] or list(df.columns)

    t1, t2, t3 = st.columns([0.6, 0.2, 0.2], vertical_alignment="center")
    with t1:
        comp.html(f'<p class="num" style="margin:0;font-size:12px;color:#6B6861">Mostrando '
                  f'{comp.num(min(len(df), MAX_FILAS))} de {comp.num(len(df))} filas · la descarga trae todas '
                  f'las filtradas</p>')
    with t2.popover(f"Columnas · {len(visibles)} de {df.shape[1]}", width="stretch"):
        st.multiselect("Columnas visibles", list(df.columns), key=clave_cols)
    with t3:
        comp.boton_csv(df[visibles], elegida.replace(" / ", "_"))

    st.dataframe(df[visibles].head(MAX_FILAS), width="stretch", height=420)
    if tecnicas:
        comp.html('<p class="tfi-sub" style="margin:8px 0 0">Las columnas técnicas ('
                  + ", ".join(f'<span class="mono">{c}</span>' for c in tecnicas)
                  + ') quedan ocultas por defecto y se activan desde “Columnas”.</p>')
