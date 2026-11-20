"""Machine learning: grupos de alumnos con K-Means (Etapa 7, D57).

Todo el cálculo está en src/ml_grupos.py; esta página solo lo muestra.
El modelo se ajusta con las tres materias juntas: el filtro de materia de la
barra lateral recorta lo que se ve, pero no cambia los grupos.
Usa el sistema de diseño de componentes.py (como el predictor de abandono)."""
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes as comp
from src.config import GRUPOS_K
from src.ml_grupos import SIN_GRUPO, TIPO_GRUPO

T = comp.TONOS
f = comp.cabecera(
    "Grupos de alumnos",
    "Unos pocos perfiles en vez de cientos de alumnos uno por uno. Se arman con <strong>K-Means</strong> sobre "
    "cinco variables (sesiones, minutos, semanas con actividad, avance y nota), comparando a cada alumno "
    "<strong>con su propia materia</strong>, así que “poca actividad” significa poca para su curso.")

# Tono fijo por tipo de grupo (de mejor a peor perfil): color + forma + nombre.
TONO_GRUPO = {"Comprometidos": "bajo", "Eficientes": "azul", "Esforzados con nota baja": "naranja",
              "Intermitentes": "medio", "Desconectados": "alto", SIN_GRUPO: "neutro"}
# Qué hacer con cada grupo (texto del recuadro de la tarjeta).
ACCION = {
    "Comprometidos": lambda g: (f"<strong>Sin acción.</strong> Ojo igual: {comp.pct(g.get('pct_libre'), 0)} queda "
                                "libre; estar en este grupo no garantiza nada."),
    "Eficientes": lambda g: "<strong>Sin acción.</strong> Rinden bien entrando poco: no hace falta empujarlos.",
    "Esforzados con nota baja": lambda g: ("<strong>Necesitan apoyo con el contenido</strong> (tutoría, consultas), "
                                           "no recordatorios: ya entran."),
    "Intermitentes": lambda g: (f"<strong>Es el grupo que se puede dar vuelta:</strong> entran, avanzaron "
                                f"{comp.pct(g['mediana_avance'], 0)} del material y no rinden."),
    "Desconectados": lambda g: ("<strong>Abandono de hecho.</strong> Un mail masivo no alcanza: contacto individual "
                                "o baja formal."),
}


def tipo(nombre: str) -> str:
    """'Ausentes' -> 'Desconectados', 'Intermitentes (2)' -> 'Intermitentes' (grupos del mismo tipo)."""
    base = re.sub(r" \(\d+\)$", "", nombre)
    return TIPO_GRUPO.get(base, base)


def tono(nombre: str) -> str:
    return TONO_GRUPO.get(tipo(nombre), "neutro")


CORTOS = {"sesiones": "Sesiones", "minutos": "Minutos", "semanas_activas": "Semanas activas",
          "avance": "Avance", "nota_pct": "Nota"}


# --- Cantidad de grupos -----------------------------------------------------
try:   # antes de la primera evaluación no hay con qué armar grupos (se avisa más abajo)
    evaluacion = comp.metrica("evaluar_k")
except ValueError:
    evaluacion = pd.DataFrame(columns=["k", "silhouette", "inercia", "candidato"])
cand = evaluacion[evaluacion["candidato"].astype(bool)]
k_auto = int(cand.loc[cand["silhouette"].idxmax(), "k"]) if not cand.empty else None
AUTO = "Automático"
st.html('<p class="tfi tfi-et" style="margin:4px 0 -6px">Cantidad de grupos</p>')
eleccion = st.segmented_control(
    "Cantidad de grupos", [AUTO, *[str(k) for k in GRUPOS_K if k != k_auto]], default=AUTO, key="ml_k",
    label_visibility="collapsed", format_func=lambda x: f"Automático · {k_auto}" if x == AUTO and k_auto else x)
k = None if eleccion in (None, AUTO) else int(eleccion)
if k_auto:
    st.caption(f"{k_auto} es lo que elige el criterio de silhouette (el k entre 3 y 6 con grupos más separados). "
               "Se puede forzar otro para comparar.")

alumnos = comp.metrica("grupos_alumnos", k=k)
if alumnos.empty or alumnos["grupo"].eq(0).all():
    st.info("A esta fecha de corte ninguna materia tiene evaluaciones todavía: sin nota, los grupos no se "
            "pueden armar. Mové la fecha de corte a después del 21/08/2025 para ver las tres materias.",
            icon=":material/info:")
    st.stop()

perfil = comp.metrica("perfil_grupos", k=k)
perfil_materia = comp.metrica("perfil_grupos", k=k, por_materia=True)
centros = comp.metrica("centroides", k=k)
k_usado = int(perfil["grupo"].max())
colores = {n: T[tono(n)]["fuerte"] for n in perfil["nombre_grupo"]}
orden = perfil.sort_values("grupo")["nombre_grupo"].tolist()
con_grupo = perfil[perfil["grupo"] > 0]

sin_grupo = alumnos["grupo"].eq(0).sum()
if sin_grupo:
    materias_sin = ", ".join(alumnos.loc[alumnos["grupo"].eq(0), "asignatura"].map(comp.SIGLAS).unique())
    st.html(f'<div class="tfi tfi-card" style="background:{T["medio"]["fondo"]};border-color:{T["medio"]["borde"]};'
            f'padding:12px 16px"><p class="tfi-p" style="color:{T["medio"]["texto"]};display:flex;gap:8px;'
            f'align-items:center">{comp.icono("medio", 13)}{comp.num(sin_grupo)} alumnos quedan sin grupo: su '
            f"materia ({materias_sin}) todavía no tiene evaluaciones a esta fecha de corte.</p></div>")


def _ver(nombre: str) -> None:
    st.session_state["ml_grupos"] = [nombre]


# --- Los grupos ---------------------------------------------------------------
semanas_max = int(alumnos["semanas_activas"].max() or 0)
for fila in range(0, len(con_grupo), 3):
    cols = st.columns(3, gap="small")
    for col, (_, g) in zip(cols, con_grupo.iloc[fila:fila + 3].iterrows()):
        nombre, tn = g["nombre_grupo"], tono(g["nombre_grupo"])
        t = T[tn]
        datos = [("Sesiones · minutos", f"{comp.num(g['mediana_sesiones'])} · {comp.num(g['mediana_minutos'])}"),
                 ("Semanas con actividad", f"{comp.num(g['mediana_semanas_activas'])} de {semanas_max}"),
                 ("Avance · nota", f"{comp.pct(g['mediana_avance'], 0)} · {comp.num(g['mediana_nota_pct'])}"),
                 ("Activos hoy", f'<span style="color:{t["texto"]}">{comp.pct(g["pct_activos"], 0)}</span>')]
        accion = ACCION.get(tipo(nombre), lambda g: "")(g)
        with col, comp.tarjeta_color(f"g{int(g['grupo'])}", tn):
            st.html(comp.encabezado_color(nombre, comp.num(g["alumnos"]), f"{comp.pct(g['pct'])} de la base", tn)
                    + f'<div class="tfi"><p class="tfi-p" style="font-size:13px;color:{comp.TOKENS["texto"]};'
                      f'margin-bottom:10px">{comp.esc(g["descripcion_grupo"]).split(". ")[0].rstrip(".")}.</p>'
                    + "".join(f'<div class="tfi-dato"><span>{a}</span><b>{b}</b></div>' for a, b in datos)
                    + (f'<div class="tfi-accion" style="background:{t["fondo"]};color:{t["texto"]}">{accion}</div>'
                       if accion else "") + "</div>")
            if tipo(nombre) not in ("Comprometidos", "Eficientes"):
                st.button(f"Ver los {comp.num(g['alumnos'])}", key=f"ml_ver_{int(g['grupo'])}",
                          on_click=_ver, args=(nombre,))
st.html('<p class="tfi tfi-pie" style="margin:-4px 0 4px">Medianas de cada grupo. Nota sobre 100 a la fecha de '
        "corte; el avance sale del reporte de participación, que es una foto al 24/10.</p>")

# --- Qué distingue + por materia --------------------------------------------------
izq, der = st.columns([1.15, 1], gap="small")
with izq:
    bloques, cercano = [], None
    for nombre in [n for n in orden if n in set(centros["nombre_grupo"])]:
        c = centros[centros["nombre_grupo"].eq(nombre)].assign(a=lambda x: x["desvios"].abs())
        c = c.sort_values("a", ascending=False)
        if cercano is None or c["a"].mean() < cercano[1]:
            cercano = (nombre, c["a"].mean(), c.iloc[0])
        t = T[tono(nombre)]
        bloques.append(f'<p class="tfi-h3" style="font-size:13px;margin:6px 0 8px;color:{t["texto"]}">'
                       f'<span style="color:{t["fuerte"]};display:flex">{comp.icono(tono(nombre))}</span>'
                       f'{comp.esc(nombre)}</p>'
                       + "".join(comp.barra_divergente(CORTOS.get(r["variable"], r["descripcion"]), r["desvios"], t["fuerte"])
                                 for _, r in c.iterrows())
                       + '<div style="height:10px"></div>')
    nota = ""
    if cercano is not None:
        nombre, _, mayor = cercano
        nota = (f'<p class="tfi-nota">Los <strong>{comp.esc(nombre)}</strong> son los más cercanos al promedio: su '
                f'diferencia más grande es {CORTOS.get(mayor["variable"], mayor["descripcion"]).lower()} '
                f'({comp.num(mayor["desvios"], 1).replace("-", "−")} desvíos).</p>')
    st.html('<div class="tfi tfi-card" style="height:100%">'
            + comp.titulo_tarjeta("Qué distingue a cada grupo", "Centro de cada grupo en desvíos respecto del "
                                  "promedio de su materia: 0 es el promedio (la línea del medio), +1 bastante por "
                                  "encima, −1 bastante por debajo.")
            + "".join(bloques) + nota + "</div>")

with der:
    filas = []
    pm = perfil_materia[perfil_materia["grupo"] > 0]
    for asig, sub in pm.groupby("asignatura"):
        sub = sub.set_index("nombre_grupo").reindex([n for n in orden if n in set(sub["nombre_grupo"])])
        filas.append(comp.fila_barra(asig.split(" ")[0], [(n, r["pct"], colores[n], comp.pct(r["pct"], 0))
                                                           for n, r in sub.iterrows()]))
    nota_mat = ""
    desc = pm[pm["nombre_grupo"].map(tipo).eq("Desconectados")]
    if len(desc) > 1:
        lo, hi = desc["pct"].min(), desc["pct"].max()
        frase = (f"El {comp.pct(hi, 0)} de desconectados es casi igual en las tres." if hi - lo <= 3 else
                 f"Los desconectados van del {comp.pct(lo, 0)} al {comp.pct(hi, 0)} según la materia.")
        nota_mat = (f'<p class="tfi-nota" style="margin-bottom:16px"><strong>{frase}</strong> Lo que más cambia entre '
                    "materias es el reparto entre los otros grupos.</p>")
    cond_filas = []
    for _, g in con_grupo.iterrows():
        segs = [("Promociona", g.get("pct_promociona", 0) or 0, T["bajo"]["fuerte"]),
                ("Regular", g.get("pct_regular", 0) or 0, T["medio"]["fuerte"]),
                ("Libre", g.get("pct_libre", 0) or 0, T["alto"]["fuerte"])]
        cond_filas.append(comp.fila_barra(g["nombre_grupo"], [
            (n, v, c, comp.pct(v, 0) + (" libre" if n == "Libre" and v >= 60 else "")) for n, v, c in segs], chica=True))
    st.html('<div class="tfi tfi-card" style="height:100%">'
            + comp.titulo_tarjeta("Cuántos hay en cada materia", "En % de la base de cada materia.")
            + "".join(filas) + nota_mat
            + '<h4 class="tfi-h3" style="font-size:13px;margin:0 0 4px">Los grupos no son la condición</h4>'
            + '<p class="tfi-sub" style="margin-bottom:10px">Condición dentro de cada grupo.</p>'
            + "".join(cond_filas)
            + comp.leyenda([("Promociona", "bajo"), ("Regular", "medio"), ("Libre", "alto")])
            + f'<p class="tfi-pie">Hay comprometidos que igual quedan libres y alumnos que entran mucho y están '
              f"libres: el grupo describe el comportamiento, no el resultado.</p></div>")

# --- Mapa de los grupos (PCA) ---------------------------------------------------
mapa = comp.metrica("mapa_grupos", k=k)
var1, var2 = mapa["varianza"]
pts = mapa["alumnos"].assign(materia=lambda t: t["asignatura"].map(comp.SIGLAS))
leyenda_grupos = comp.leyenda([(n, tono(n)) for n in orden if n in colores and tipo(n) != SIN_GRUPO])
with comp.tarjeta("mapa"):
    st.html('<div class="tfi">' + comp.titulo_tarjeta(
        "Mapa de los grupos", "El modelo mira cinco variables a la vez. Para poder dibujarlo, se resumen en dos ejes "
        "con PCA: cada punto es un alumno y los parecidos quedan cerca. La × es el centro de cada grupo.") + "</div>")
    izq, der = st.columns([1.6, 1], gap="medium")
    with izq:
        st.html(f'<div class="tfi">{leyenda_grupos}</div>')
        fig = px.scatter(pts, x="eje1", y="eje2", color="nombre_grupo", color_discrete_map=colores,
                         category_orders={"nombre_grupo": orden}, opacity=0.7,
                         hover_data={"id_alumno": True, "nombre_completo": True, "materia": True, "condicion": True,
                                     "nota_pct": ":.1f", "minutos": ":.0f", "avance": True, "eje1": False,
                                     "eje2": False},
                         labels={"eje1": "− compromiso   ·   eje 1   ·   + compromiso", "eje2": "Eje 2",
                                 "nombre_grupo": "Grupo", "nombre_completo": "Alumno", "id_alumno": "ID",
                                 "materia": "Materia", "condicion": "Condición", "nota_pct": "Nota",
                                 "minutos": "Minutos", "avance": "Avance (%)"})
        fig.update_traces(marker=dict(size=6))
        c = mapa["centros"]
        fig.add_scatter(x=c["eje1"], y=c["eje2"], mode="markers", text=c["nombre_grupo"],
                        marker=dict(symbol="x-thin", size=18, line=dict(width=4, color=[
                            colores.get(n, comp.NEUTRO) for n in c["nombre_grupo"]])),
                        name="Centro", showlegend=False, hovertemplate="%{text}<extra>centro</extra>")
        fig.update_layout(height=420, showlegend=False, margin=dict(t=8, l=4, r=4, b=4),
                          xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                          yaxis=dict(showgrid=False, zerolinecolor=comp.TOKENS["borde"], showticklabels=False))
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    with der:
        st.html(f'<div class="tfi"><p class="tfi-et">Cómo leer los ejes</p>'
                f'<div class="tfi-eje"><p class="t">Eje horizontal · {comp.pct(var1, 0)} de la variación</p><p>'
                "Compromiso general: las cinco variables pesan casi igual. A la derecha, los que entran más, avanzan "
                "más y tienen mejor nota.</p></div>"
                f'<div class="tfi-eje"><p class="t">Eje vertical · {comp.pct(var2, 0)}</p><p>Contrapone nota y '
                "avance contra sesiones y minutos. Arriba, los que rinden más de lo que entran; abajo, los que entran "
                "mucho para la nota que sacan.</p></div>"
                f'<p class="tfi-nota" style="margin-bottom:14px">Entre los dos resumen el <strong>'
                f"{comp.pct(var1 + var2, 0)}</strong> de la información de las cinco variables, así que el mapa "
                "representa bien lo que ve el modelo.</p>"
                '<p class="tfi-pie">Las variables están en desvíos respecto del promedio de cada materia (con '
                "logaritmo en sesiones y minutos), igual que en el modelo: por eso los ejes no tienen unidades.</p>"
                "</div>")

# --- Alumnos en las variables originales -----------------------------------------
VARIABLES = {"minutos": "Minutos en la plataforma", "sesiones": "Sesiones",
             "semanas_activas": "Semanas con actividad", "avance": "Avance (%)"}
with comp.tarjeta("variables"):
    izq, der = st.columns([3, 1], vertical_alignment="bottom")
    izq.html('<div class="tfi">' + comp.titulo_tarjeta(
        "Los grupos en las variables reales", "Acá se ven solo 2 de las 5 variables, así que los grupos se "
        "superponen: un alumno puede estar cerca de otro grupo en minutos y nota, y lejos en avance o semanas "
        "activas.").replace('class="tfi-sub"', 'class="tfi-sub" style="margin-bottom:0"') + "</div>")
    variable = der.selectbox("Variable del eje horizontal", list(VARIABLES), format_func=VARIABLES.get,
                             key="ml_var", label_visibility="collapsed")
    puntos = alumnos[alumnos["grupo"] > 0].assign(materia=lambda t: t["asignatura"])
    log = variable in ("minutos", "sesiones")
    if log:
        puntos = puntos[puntos[variable] > 0]
    fig = px.scatter(puntos, x=variable, y="nota_pct", color="nombre_grupo",
                     facet_col="materia" if not f.asignatura else None, facet_col_spacing=0.05,
                     color_discrete_map=colores, category_orders={"nombre_grupo": orden}, opacity=0.75, log_x=log,
                     hover_data={"id_alumno": True, "nombre_completo": True, "condicion": True, "materia": False},
                     labels={variable: VARIABLES[variable], "nota_pct": "Nota", "nombre_grupo": "Grupo",
                             "nombre_completo": "Alumno", "id_alumno": "ID", "condicion": "Condición"})
    fig.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>", font=dict(
        family=comp.FUENTE, size=12, color=comp.TOKENS["tinta"])))
    fig.update_traces(marker=dict(size=6))
    fig.update_layout(height=330, showlegend=False, margin=dict(t=30, l=4, r=4, b=4))
    fig.update_yaxes(range=[-5, 105])
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    st.html(leyenda_grupos + ('<p class="tfi tfi-pie">Eje horizontal en escala logarítmica; los alumnos con 0 no se '
                              "ven.</p>" if log else ""))

# --- Buscar un alumno ------------------------------------------------------------
# Mismo buscador que la Ficha y el predictor: alumnos de la materia de la barra, por apellido.
with comp.tarjeta("buscar"):
    st.html('<div class="tfi">' + comp.titulo_tarjeta(
        "Buscar un alumno", "A qué grupo pertenece en cada materia y cómo se compara con la mediana de su "
        "grupo.") + "</div>")
    nombres = (alumnos.sort_values("nombre_completo").drop_duplicates("id_alumno")
                      .set_index("id_alumno")["nombre_completo"].to_dict())
    id_alumno = st.selectbox(
        f"Alumno ({comp.num(len(nombres))})", list(nombres), key="ml_grupos_alumno",
        format_func=lambda i: f"{nombres[i]} · {i}",
        help="Escribí parte del apellido, nombre o ID (ej.: ALU_1263) para filtrar.")
    todos = comp.metrica("grupos_alumnos", k=k, asignatura=None)
    suyo = todos[todos["id_alumno"].eq(id_alumno)].sort_values("asignatura")
    medianas = perfil_materia.set_index(["asignatura", "grupo"])
    VARS = [("nota_pct", "Nota", 1), ("sesiones", "Sesiones", 0), ("minutos", "Minutos", 0),
            ("semanas_activas", "Semanas", 0), ("avance", "Avance (%)", 0)]
    filas = []
    for _, r in suyo.iterrows():
        nombre = r["nombre_grupo"]
        tg = T[tono(nombre)] if r["grupo"] > 0 else T["neutro"]
        icono = comp.icono(tono(nombre)) if r["grupo"] > 0 else ""
        clave = (r["asignatura"], r["grupo"])
        celdas = []
        for col, _, dec in VARS:
            med = medianas.loc[clave, f"mediana_{col}"] if clave in medianas.index else None
            celdas.append(f'<strong style="font-weight:600">{comp.num(r[col], dec)}</strong>'
                          + (f'<br><span class="sec num">grupo {comp.num(med, dec)}</span>' if med is not None
                             else ""))
        filas.append([
            comp.insignia_materia(r["asignatura"]),
            f'<span style="display:inline-flex;align-items:center;gap:6px;font-weight:600;color:{tg["texto"]}">'
            f'<span style="color:{tg["fuerte"]};display:flex">{icono}</span>{comp.esc(nombre)}</span>'
            f'<br><span class="sec">{comp.esc(str(r["descripcion_grupo"]).split(". ")[0].rstrip("."))}.</span>',
            comp.esc(r["condicion"]), *celdas,
        ])
    st.html(comp.tabla_html(["Materia", "Grupo", "Condición", *[v[1] for v in VARS]], filas,
                            ["", "wrap", "", "num", "num", "num", "num", "num"]))
    st.html('<p class="tfi tfi-pie">Debajo de cada valor, la mediana de su grupo en esa materia. Muestra todas '
            "las materias del alumno, aunque la barra filtre una.</p>")

# --- Lista de alumnos ------------------------------------------------------------
with comp.tarjeta("lista"):
    st.session_state.setdefault("ml_grupos", [n for n in orden if tipo(n) not in ("Comprometidos", "Eficientes")])
    st.session_state["ml_grupos"] = [n for n in st.session_state["ml_grupos"] if n in orden]
    elegidos = st.session_state["ml_grupos"]
    lista = alumnos[alumnos["nombre_grupo"].isin(elegidos)].sort_values(["nombre_completo", "asignatura"])
    st.html('<div class="tfi">' + comp.titulo_tarjeta(
        "Alumnos por grupo", f"{comp.num(len(lista))} alumnos en los grupos seleccionados.") + "</div>")
    st.pills("Grupos", orden, selection_mode="multi", key="ml_grupos", label_visibility="collapsed",
             format_func=lambda n: f"{n} ({comp.num(int(alumnos['nombre_grupo'].eq(n).sum()))})")
    COLOR_COND = {"Libre": T["alto"]["texto"], "Regular": T["medio"]["texto"], "Promociona": T["bajo"]["texto"]}
    if lista.empty:
        st.caption("Elegí al menos un grupo para ver la lista.")
    else:
        filas = []
        for _, r in lista.head(300).iterrows():
            tg = T[tono(r["nombre_grupo"])]
            filas.append([
                f'<strong style="font-weight:600">{comp.esc(r["nombre_completo"])}</strong><br>'
                f'<span class="sec num">{comp.esc(r["id_alumno"])}</span>',
                comp.insignia_materia(r["asignatura"]),
                f'<span style="display:inline-flex;align-items:center;gap:6px;font-weight:500;color:{tg["texto"]}">'
                f'<span style="color:{tg["fuerte"]};display:flex">{comp.icono(tono(r["nombre_grupo"]))}</span>'
                f'{comp.esc(r["nombre_grupo"])}</span>',
                f'<span style="font-weight:500;color:{COLOR_COND.get(r["condicion"], comp.TOKENS["texto_2"])}">'
                f'{comp.esc(r["condicion"])}</span>',
                comp.num(r["nota_pct"], 1), comp.num(r["sesiones"]), comp.num(r["minutos"]),
                comp.num(r["semanas_activas"]),
                (f'<span style="font-weight:600;color:{T["bajo"]["texto"]}">{comp.pct(r["avance"], 0)}</span>'
                 if pd.notna(r["avance"]) and r["avance"] >= 80 else comp.pct(r["avance"], 0)),
                f'{comp.num(r["dias_sin_actividad"])} d' if pd.notna(r["dias_sin_actividad"]) else "–",
            ])
        st.html(comp.tabla_html(["Alumno", "Materia", "Grupo", "Condición", "Nota", "Sesiones", "Minutos",
                                 "Semanas", "Avance", "Sin entrar"], filas,
                                ["", "", "", "", "num", "num", "num", "num", "num", "num"]))
        # Una frase sobre el caso más llamativo: mucho avance y nota baja (leyó y no rinde).
        caso = lista[(lista["avance"] >= 70) & (lista["nota_pct"] < 40)].assign(
            gap=lambda t: t["avance"] - t["nota_pct"]).sort_values("gap", ascending=False)
        pie = (f"Se muestran los primeros 300 de {comp.num(len(lista))}; el CSV tiene todos. " if len(lista) > 300
               else "")
        if not caso.empty:
            c0 = caso.iloc[0]
            pie += (f"{comp.esc(c0['nombre_completo'])} tiene {comp.pct(c0['avance'], 0)} de avance y nota "
                    f"{comp.num(c0['nota_pct'])}: leyó casi toda la materia y no rinde. Es el perfil que más "
                    "justifica un mensaje antes del cierre.")
        if pie:
            st.html(f'<p class="tfi tfi-pie">{pie}</p>')
        tabla = pd.DataFrame({
            "Materia": lista["asignatura"].map(comp.SIGLAS), "ID": lista["id_alumno"],
            "Alumno": lista["nombre_completo"], "Grupo": lista["nombre_grupo"], "Condición": lista["condicion"],
            "Nota": lista["nota_pct"], "Sesiones": lista["sesiones"], "Minutos": lista["minutos"],
            "Semanas activas": lista["semanas_activas"], "Avance (%)": lista["avance"],
            "Días sin entrar": lista["dias_sin_actividad"],
        })
        comp.boton_csv(tabla, "grupos_alumnos", f"Descargar CSV ({comp.num(len(tabla))})")

# --- Cómo se eligió k ------------------------------------------------------------
with st.expander("Cómo se armaron los grupos y qué tan confiables son", icon=":material/science:"):
    st.markdown(
        "1. **Variables:** sesiones, minutos, semanas con actividad, avance y nota, a la fecha de corte.\n"
        "2. **Preparación:** a sesiones y minutos se les aplica un logaritmo (unos pocos alumnos con muchísimas "
        "sesiones dominarían las distancias) y todas se **estandarizan dentro de cada materia**.\n"
        "3. **Un solo modelo para las tres materias**, así los grupos se llaman igual en todo el tablero.\n"
        "4. **Cantidad de grupos:** la de mayor **silhouette** entre 3 y 6. El silhouette mide qué tan cerca está "
        "cada alumno de su grupo comparado con el grupo más cercano (de −1 a 1). k = 2 se muestra como "
        "referencia, pero no se elige: solo separa \"entran / no entran\", que ya lo dice el estado de actividad.\n"
        "5. **Nombres:** salen del centro de cada grupo (cuánta actividad y qué nota tiene respecto de su materia).")
    azul, rojo = comp.TOKENS["azul"], T["alto"]["fuerte"]
    c1, c2 = st.columns(2)
    fig = go.Figure(go.Scatter(x=evaluacion["k"], y=evaluacion["silhouette"], mode="lines+markers",
                               line=dict(color=azul, width=2), marker=dict(size=7)))
    fig.add_scatter(x=[k_usado], y=evaluacion.loc[evaluacion["k"].eq(k_usado), "silhouette"], mode="markers",
                    marker=dict(size=14, color=rojo), name="Usado")
    fig.update_layout(height=300, showlegend=False, xaxis_dtick=1, xaxis_title="k", yaxis_title="Silhouette",
                      title="Silhouette (más alto = grupos más separados)")
    c1.plotly_chart(fig, width="stretch", theme=None)
    fig = go.Figure(go.Scatter(x=evaluacion["k"], y=evaluacion["inercia"], mode="lines+markers",
                               line=dict(color=azul, width=2), marker=dict(size=7)))
    fig.update_layout(height=300, xaxis_dtick=1, xaxis_title="k", yaxis_title="Inercia",
                      title="Inercia (dónde deja de bajar mucho = codo)")
    c2.plotly_chart(fig, width="stretch", theme=None)
    sil = evaluacion.loc[evaluacion["k"].eq(k_usado), "silhouette"].item()
    st.markdown(
        f"Con k = {k_usado} el silhouette es **{comp.num(sil, 2)}**: una estructura moderada. Los alumnos no "
        "forman tipos bien separados sino un continuo de \"más o menos enganchados\", y los grupos son una forma "
        "útil de resumirlo. **Limitaciones:** una sola cursada y unos 210 alumnos por materia; el avance es una "
        "foto al 24/10; y como la nota entra en el modelo, los grupos se parecen a la condición. Un grupo "
        "describe, no predice: para anticipar el abandono está el predictor.")
