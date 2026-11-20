"""Dashboard 5 (del plan): Notas vs. participación. Diseño: componentes_notas.py.

Responde, a la fecha de corte: ¿a los alumnos que más usan el aula les va
mejor?, ¿qué forma de participar se asocia más con la nota? y ¿a quién
contactar primero (debajo de la mediana de actividad y libres)?

  Lectura         una línea armada con nota_por_nivel_actividad: cuántos de cada
                  10 quedan libres en el quinto que menos y que más participa (D85).
  Controles       variable de actividad (VARIABLES_CRUCE) y "solo quienes
                  rindieron algo", que saca los 0 por no rendir (D55).
  KPIs            casos en riesgo (casos alumno–materia y alumnos distintos, Δ
                  contra 7 días antes), brecha de libres entre quintos extremos,
                  activos que igual quedan libres y ρ (todos / quienes rindieron)
                  contra la variable de mayor ρ (D85).
  Pestañas        Dispersión → Por nivel de actividad → Cuadrante de riesgo (con
                  la lista de prioridad de contacto, D37) → Correlaciones (D38).
                  Cada una con un título que es la conclusión, calculada con los datos.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
Los textos de lectura se arman con los datos (src.textos, D77): cambian con la fecha, la
materia y la variable. Las explicaciones van en el (?) o en los expansores, no en la página.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import componentes_notas as comp
from src import textos
from src.config import ESQUEMA, SIN_EVALUACIONES
from src.metricas import SIN_ACTIVIDAD, TODAS_LAS_MATERIAS, VARIABLES_CRUCE

f = comp.encabezado(
    "Notas vs. participación",
    "¿A los alumnos que más usan el aula les va mejor? ¿A quién conviene contactar primero?",
)
lugar_lectura = st.empty()   # la lectura principal va debajo del subtítulo, pero depende de la variable elegida

DEL_REPORTE = {"tiempo_uso_min", "avance"}   # foto del reporte de participación (D36)
UNIDAD = {"minutos": "min", "tiempo_uso_min": "min", "avance": "%"}
# Para escribir las conclusiones en castellano corrido.
EN_PROSA = {"minutos": "los minutos en la plataforma", "sesiones": "las sesiones", "eventos": "las interacciones",
            "dias_activos": "los días con actividad", "semanas_activas": "las semanas con actividad",
            "tiempo_uso_min": "el tiempo estimado de uso", "avance": "el avance en el contenido"}
CORTO = {"minutos": "minutos", "sesiones": "sesiones", "eventos": "interacciones", "dias_activos": "días con actividad",
         "semanas_activas": "semanas con actividad", "tiempo_uso_min": "tiempo de uso", "avance": "avance"}
ORIGEN = {"avance": "del reporte · cuenta las evaluaciones hechas", "tiempo_uso_min": "del reporte",
          "minutos": "calculados con las sesiones"}
ORDEN_CONDICION = ["Promociona", "Regular", "Libre", SIN_EVALUACIONES]      # leyenda de la dispersión
SIMBOLO = {"Promociona": "circle", "Regular": "triangle-up", "Libre": "octagon", SIN_EVALUACIONES: "square"}
PESTANAS = ["Dispersión", "Por nivel de actividad", "Cuadrante de riesgo", "Correlaciones"]
PAG_PREDICTOR, PAG_GRUPOS = "paginas/ml_abandono.py", "paginas/ml_grupos.py"

# Cuadrantes (D37) en el orden de la grilla 2×2: arriba no libre, abajo libre; izquierda debajo de la mediana.
# Etiqueta de src.metricas -> (nombre en pantalla, qué hacer). Solo el de riesgo va en rojo; el resto, neutro.
RIESGO = "Riesgo: poca actividad y nota baja"
CUADRANTES = {
    "Poca actividad con buena nota": ("Debajo de la mediana, no libre", "Les alcanza con poco: el aula no es donde estudian."),
    "Activo con buena nota": ("Sobre la mediana, no libre", "El grupo sano: referencia de cuánta actividad alcanza."),
    RIESGO: ("Debajo de la mediana y libre", ""),   # texto con datos, abajo
    "Activo con nota baja": ("Sobre la mediana y libre", "Están, pero no les rinde: el problema es la comprensión."),
}
COLOR_CUADRANTE = {  # (fondo, borde, número, texto)
    "riesgo": ("#FBE9E6", "#F2CFC9", "#93241C", "#7A3028"), "neutro": ("#F7F6F3", "#E3E1DC", "#35332D", "#57544C"),
}
MARCA_CUADRANTE = {  # gráfico de cuadrantes: (color, símbolo)
    "Poca actividad con buena nota": ("#C9C6BF", "circle"), "Activo con buena nota": ("#A8A49B", "circle"),
    RIESGO: (comp.CRITICO, "octagon"), "Activo con nota baja": ("#6B6861", "diamond"),
}
AYUDA_RHO = ("ρ de Spearman: va de −1 a 1. 1 = el orden por actividad coincide con el orden por nota; 0 = sin "
             "relación; negativo = a más actividad, menos nota. Tamaño (Cohen): menos de 0,10 sin relación; de 0,10 "
             "a 0,29 débil; de 0,30 a 0,49 moderada; 0,50 o más fuerte. Correlación no es causa: los alumnos "
             "comprometidos entran más y también estudian más.")
AYUDA_VARIABLE = (
    "Se cruza con la nota en toda la página.\n\n"
    "**Minutos en la plataforma (sesiones)** es el *tiempo de conexión* de la consigna: lo calculamos con la "
    "trazabilidad (una sesión se corta después de 30 minutos sin clics) y se recorta con la fecha de corte.\n\n"
    "**Tiempo estimado de uso (reporte)** es la cifra del propio LMS: una foto a la fecha de exportación que también "
    "cuenta el rato después del último clic, por eso da algo más.\n\n"
    "**Avance (%) (reporte)** también es una foto, y el LMS cuenta cada evaluación realizada como un ítem visto: "
    "su relación con la nota es en parte circular, sobre todo en Álgebra.")


def es(sujeto: str) -> str:
    """'los minutos' -> 'son', 'el avance' -> 'es'."""
    return "son" if sujeto.startswith(("los ", "las ")) else "es"


def mayuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


# ---------------------------------------------------------------------------
# Controles de la página
# ---------------------------------------------------------------------------
with st.container(border=True):
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    variable = c1.selectbox("Forma de participar", list(VARIABLES_CRUCE), format_func=VARIABLES_CRUCE.get,
                            key="nvp_variable", help=AYUDA_VARIABLE)
    solo_rindieron = c2.toggle(
        "Solo alumnos que rindieron al menos una evaluación", key="nvp_solo_rindieron",
        help="Quien no rindió nada tiene 0 y casi siempre también poca actividad: eso solo ya arma "
             "una correlación. Sacarlos muestra si la actividad se asocia con la nota entre los que sí rinden. "
             "Cambia la lectura de arriba, la brecha de libres, la dispersión, los niveles y las correlaciones; "
             "el cuadrante y la lista incluyen siempre a todos.")
    nombre_var = VARIABLES_CRUCE[variable]
    corto = CORTO[variable]
    if variable in DEL_REPORTE:
        st.caption(f":material/info: *{nombre_var}* sale del reporte de participación: es una foto a la fecha de "
                   "exportación y no se recorta con la fecha de corte.")

alumnos = comp.metrica("cuadrante_riesgo", variable=variable)
if alumnos["nota_pct"].isna().all():
    st.info(f"Al {comp.fmt_fecha(f.fecha_corte)} todavía no se tomó ninguna evaluación en "
            f"{f.materia.lower()}: no hay notas para cruzar. Mové la fecha de corte.", icon=":material/event_busy:")
    st.stop()

corr_todos = comp.metrica("correlaciones", solo_rindieron=False)
corr_rind = comp.metrica("correlaciones", solo_rindieron=True)
corr = corr_rind if solo_rindieron else corr_todos
niveles = comp.metrica("nota_por_nivel_actividad", variable=variable, solo_rindieron=solo_rindieron)
casos = comp.metrica("casos_en_riesgo", variable=variable).set_index("asignatura")
brecha = comp.metrica("brecha_libres", variable=variable, solo_rindieron=solo_rindieron).set_index("asignatura")
act_libres = comp.metrica("activos_libres", variable=variable).set_index("asignatura")

puntos = alumnos[alumnos["rendidos"] > 0] if solo_rindieron else alumnos
materias = [m for m in f.materias if m in set(alumnos["asignatura"])]
con_notas = [m for m in materias if alumnos.loc[alumnos["asignatura"] == m, "nota_pct"].notna().any()]
varias = len(materias) > 1
riesgo = alumnos[alumnos["en_riesgo"]]
total = casos.loc[TODAS_LAS_MATERIAS]


def pivot(c: pd.DataFrame) -> pd.DataFrame:
    return c[c["asignatura"].isin(materias)].pivot(index="variable", columns="asignatura", values="rho") \
        .reindex(columns=materias)


corr = corr[corr["asignatura"].isin(materias)]
matriz, matriz_t, matriz_r = pivot(corr), pivot(corr_todos), pivot(corr_rind)
promedio = matriz.mean(axis=1).dropna().sort_values(ascending=False)   # la más asociada primero
prom_t, prom_r = matriz_t.mean(axis=1), matriz_r.mean(axis=1)


def fmt_var(x) -> str:
    return f"{comp.num(x, 0)} {UNIDAD.get(variable, '')}".strip()


def nota_esc(nota, nota_pct, materia: str) -> str:
    """'94,8/120 (79,0/100)' en Álgebra, '79,0' en las materias sobre 100: igual en todas las pestañas."""
    return textos.nota_en_escala(nota, nota_pct, ESQUEMA[materia]["total_max"])


# ---------------------------------------------------------------------------
# Lectura principal (debajo del subtítulo): del quinto que menos al que más participa
# ---------------------------------------------------------------------------
con_brecha = [m for m in con_notas if m in brecha.index]
lectura = textos.lectura_quintiles([comp.SIGLAS[m] for m in con_brecha],
                                   [brecha.loc[m, "libre_menos"] for m in con_brecha],
                                   [brecha.loc[m, "libre_mas"] for m in con_brecha], EN_PROSA[variable].split(" ", 1)[1])
if lectura:
    comp.html(f'<p class="tfi nvp-lectura">{lectura}'
              f'{comp.ayuda("Cada materia partida en 5 grupos del mismo tamaño según " + nombre_var.lower() + ". Detalle en la pestaña Por nivel de actividad.")}</p>',
              lugar_lectura)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
def ir_a_la_lista() -> None:
    st.session_state["nvp_pestana"] = "Cuadrante de riesgo"


def kpi_riesgo() -> str:
    delta = int(total["casos"] - total["casos_antes"])
    antes = (pd.Timestamp(f.fecha_corte) - pd.Timedelta(days=7)).strftime("%d/%m")
    delta_txt = (f"sin cambios vs. {antes}" if delta == 0
                 else f"{'+' if delta > 0 else '−'}{comp.num(abs(delta))} vs. {antes}")
    unidad = "casos" if varias else "alumnos"
    quienes = (f"{comp.num(total['alumnos'])} alumnos distintos · " if varias else "")
    return comp.kpi(
        "Casos en riesgo",
        f'<p class="nvp-num alerta">{comp.num(total["casos"])}<small>{unidad}</small></p>'
        + comp.linea(f"{quienes}{comp.num(total['sin_rendir'])} sin rendir nada", alerta=True)
        + comp.linea(f'<span class="nvp-delta">{delta_txt}</span>', alerta=True),
        f"Debajo de la mediana de {corto} de su materia y libres al corte.",
        tip="Un caso es un alumno en una materia: el mismo alumno puede estar en riesgo en varias. "
            "La comparación es contra la misma cuenta 7 días antes, con la mediana y la condición de esa fecha. "
            "Incluye a quienes no rindieron nada.", alerta=True)


def kpi_brecha() -> str:
    tip = (f"% de libres en el 20 % de cada materia con menos {nombre_var.lower()} menos el % de libres en el 20 % "
           "con más (pp = puntos porcentuales). Sigue el interruptor «solo quienes rindieron».")
    if not con_brecha:
        return comp.kpi("Brecha de libres", '<p class="nvp-num">–</p>', tip=tip)
    if varias:
        filas = [(comp.SIGLAS[m], f"{comp.num(brecha.loc[m, 'brecha_pp'])} pp",
                  f"{comp.pct(brecha.loc[m, 'libre_menos'], 0)} → {comp.pct(brecha.loc[m, 'libre_mas'], 0)}")
                 for m in con_brecha]
        return comp.kpi("Brecha de libres", comp.filas_materia(filas),
                        f"Libres en el quinto con menos {corto} → con más.", tip=tip)
    b = brecha.loc[con_brecha[0]]
    return comp.kpi("Brecha de libres", f'<p class="nvp-num">{comp.num(b["brecha_pp"])}<small>pp</small></p>'
                    + comp.linea(f"{comp.pct(b['libre_menos'], 0)} → {comp.pct(b['libre_mas'], 0)} libres"),
                    f"Del quinto con menos {corto} al de más.", tip=tip)


def kpi_activos_libres() -> str:
    tip = (f"De los alumnos con {nombre_var.lower()} igual o por encima de la mediana de su materia (los «activos» "
           "del cuadrante, no el estado de los últimos días), qué parte queda libre al corte. "
           "Incluye a quienes no rindieron nada.")
    etiqueta = "Activos y libres igual"
    a = act_libres.reindex(con_notas)
    if varias:
        filas = [(comp.SIGLAS[m], comp.pct(a.loc[m, "pct"], 0),
                  f"{comp.num(a.loc[m, 'libres'])} de {comp.num(a.loc[m, 'sobre_mediana'])}") for m in con_notas]
        return comp.kpi(etiqueta, comp.filas_materia(filas), f"Sobre la mediana de {corto} y libres.", tip=tip)
    m = con_notas[0]
    return comp.kpi(etiqueta, f'<p class="nvp-num">{comp.pct(a.loc[m, "pct"], 0)}</p>'
                    + comp.linea(f"{comp.num(a.loc[m, 'libres'])} de {comp.num(a.loc[m, 'sobre_mediana'])}"),
                    f"Sobre la mediana de {corto} y libres.", tip=tip)


def kpi_rho() -> str:
    mejor = prom_t.dropna().idxmax() if prom_t.notna().any() else None

    def par(var) -> str:
        return f"{comp.num(prom_t.get(var), 2)} / {comp.num(prom_r.get(var), 2)}"

    if mejor is None:
        conclusion = ""
    elif mejor == variable:
        conclusion = "<strong>La que más acompaña a la nota.</strong>"
    else:
        conclusion = (f"<strong>Por debajo de {CORTO[mejor]}</strong> ({par(mejor)}"
                      + (" en promedio" if varias else "") + ").")
    if varias:
        filas = [(comp.SIGLAS[m], comp.num(matriz_t.loc[variable, m], 2), f"/ {comp.num(matriz_r.loc[variable, m], 2)}")
                 for m in con_notas]
        cuerpo = comp.filas_materia(filas)
    else:
        m = con_notas[0]
        cuerpo = (f'<p class="nvp-num">{comp.num(matriz_t.loc[variable, m], 2)}'
                  f'<small>/ {comp.num(matriz_r.loc[variable, m], 2)}</small></p>')
    tip = (AYUDA_RHO + " Primer número: todos los alumnos de la base. Segundo: solo quienes rindieron al menos "
           "una evaluación (sin los 0 por no rendir).")
    return comp.kpi(f'<span style="text-transform:none">ρ</span>&nbsp;de {corto}', cuerpo,
                    "Todos / quienes rindieron. " + conclusion, tip=tip)


k1, k2, k3, k4 = st.columns(4)
with k1, st.container(key="nvp_kpi_riesgo", height="stretch"):
    comp.html(kpi_riesgo())
    if total["casos"]:
        st.button("Ver prioridad de contacto →", key="nvp_ir_lista", type="tertiary", on_click=ir_a_la_lista,
                  help="Abre la pestaña Cuadrante de riesgo, con la lista ordenada para contactar.")
with k2, st.container(key="nvp_kpi_brecha", height="stretch"):
    comp.html(kpi_brecha())
with k3, st.container(key="nvp_kpi_activos", height="stretch"):
    comp.html(kpi_activos_libres())
with k4, st.container(key="nvp_kpi_rho", height="stretch"):
    comp.html(kpi_rho())
st.write("")

tab_disp, tab_nivel, tab_cuad, tab_corr = st.tabs(PESTANAS, key="nvp_pestana", on_change="rerun")

# ---------------------------------------------------------------------------
# Dispersión con tendencia
# ---------------------------------------------------------------------------
def titulo_dispersion() -> str:
    extremos = {m: niveles[niveles["asignatura"] == m].sort_values("orden")["nota_pct"] for m in con_notas}
    extremos = {m: (s.iloc[0], s.iloc[-1]) for m, s in extremos.items() if len(s) >= 2 and s.notna().all()}
    if not extremos:
        return f"{mayuscula(nombre_var)} y nota al corte"
    suben = [m for m, (a, b) in extremos.items() if b > a]
    if len(suben) == len(extremos):
        m = max(suben, key=lambda x: extremos[x][1] - extremos[x][0])
        a, b = extremos[m]
        if len(extremos) == 1:
            return (f"La nota promedio va de {comp.num(a, 1)} a {comp.num(b, 1)} sobre 100 del quinto con menos "
                    f"{corto} al de más")
        todas = "las tres materias" if len(suben) == 3 else textos.enumerar([comp.SIGLAS[x] for x in suben])
        return (f"A más {corto}, más nota en {todas}; el mayor salto, {comp.SIGLAS[m]}: "
                f"de {comp.num(a, 1)} a {comp.num(b, 1)} sobre 100")
    no = [comp.SIGLAS[m] for m in extremos if m not in suben]
    return f"Más {corto} no siempre es más nota: en {textos.enumerar(no)} el quinto con más no supera al de menos"


with tab_disp, st.container(border=True):
    c1, c2 = st.columns([4.4, 1], vertical_alignment="center")
    comp.html(comp.titulo(titulo_dispersion(), tip=(
        f"Eje horizontal: {nombre_var.lower()}. Eje vertical: nota al corte en la escala de la materia "
        "(Álgebra sobre 120). La línea negra une la nota promedio de cada quinto de alumnos, del 20 % con menos "
        "actividad al que más: si sube, a más actividad, más nota. Las líneas punteadas son los cortes de Regular "
        "y Promociona.")) + '<p class="tfi nvp-intro">Cada punto es un alumno. Línea negra: nota promedio por '
        "quinto de actividad.</p>", c1)
    escala_log = c2.toggle("Escala logarítmica", key="nvp_log",
                           help="Separa a los alumnos con poca actividad, que en escala lineal quedan "
                                "amontonados a la izquierda. Los que tienen 0 no se ven en esta escala.")
    presentes = [c for c in ORDEN_CONDICION if c in set(puntos["condicion"])]
    comp.html(comp.leyenda([(c, comp.COLORES_CONDICION[c], comp.TONO_CONDICION[c]) for c in presentes]
                           + [("Promedio por quinto", comp.TEXTO, "linea"),
                              ("Cortes de Regular y Promociona", comp.TEXTO_4, "linea_punteada")]))
    cols = st.columns(len(materias)) if varias else [st.container()]
    for col, materia in zip(cols, materias):
        datos_m = puntos[puntos["asignatura"] == materia]
        tend = niveles[niveles["asignatura"] == materia].sort_values("orden")
        esq = ESQUEMA[materia]
        escala = esq["total_max"]
        sobre_100 = "" if escala == 100 else " (%{customdata[2]:.1f} / 100)"
        comp.html(comp.titulo_materia(materia, f"nota sobre {escala}", sigla=varias), col)
        fig = go.Figure()
        for cond in ORDEN_CONDICION:
            q = datos_m[datos_m["condicion"] == cond]
            if q.empty:
                continue
            fig.add_trace(go.Scatter(
                x=q[variable], y=q["nota_final"], mode="markers", name=cond,
                marker=dict(color=comp.COLORES_CONDICION[cond], size=7, opacity=0.6, symbol=SIMBOLO[cond],
                            line=dict(width=0.6, color="white")),
                customdata=q[["nombre_completo", "id_alumno", "nota_pct"]],
                hovertemplate="%{customdata[0]} (%{customdata[1]})<br>" + nombre_var + ": %{x:,.0f}"
                              f"<br>Nota: %{{y:.1f}} / {escala}{sobre_100}<extra>{cond}</extra>"))
        fig.add_trace(go.Scatter(
            x=tend["mediana_actividad"], y=tend["nota_final"], mode="lines+markers", name="Promedio por quinto",
            line=dict(color=comp.TEXTO, width=2), marker=dict(size=7, color=comp.TEXTO),
            customdata=tend[["nivel", "alumnos", "nota_pct"]],
            hovertemplate="Actividad %{customdata[0]} (%{customdata[1]} alumnos)<br>"
                          f"Nota promedio: %{{y:.1f}} / {escala}{sobre_100}<extra></extra>"))
        for nombre, corte in esq["cortes"].items():
            fig.add_hline(y=corte, line_dash="dash", line_color=comp.COLORES_CONDICION[nombre], line_width=1.2,
                          annotation_text=nombre, annotation_position="top right",
                          annotation_font=dict(color=comp.TONOS[comp.TONO_CONDICION[nombre]][2], size=11))
        en_cero = int(((datos_m[variable] == 0) & (datos_m["nota_final"] == 0)).sum())
        if en_cero and not escala_log:
            fig.add_annotation(x=0, y=0, text=f"<b>{en_cero}</b> en 0 y nota 0", showarrow=True, arrowhead=0,
                               arrowwidth=1, arrowcolor=comp.TEXTO_4, ax=58, ay=-44, bgcolor="rgba(255,255,255,.92)",
                               bordercolor="#E3E1DC", borderpad=3, font=dict(size=10.5, color=comp.TEXTO_2))
        fig.update_layout(height=290, showlegend=False, margin=dict(t=6, l=4, r=6, b=4))
        fig.update_xaxes(title_text=nombre_var, title_font=dict(size=11.5, color=comp.TEXTO_3), tickfont=dict(size=11),
                         type="log" if escala_log else "linear", showgrid=False)
        fig.update_yaxes(title_text=None, tickfont=dict(size=11), range=[-4, escala + 4])
        comp.grafico(fig, col)

        # Leyenda bajo el panel: la misma plantilla y el mismo color en las tres materias.
        partes = []
        if len(tend) >= 2 and tend["nota_pct"].notna().all():
            a, b = tend.iloc[0], tend.iloc[-1]
            partes.append(f"Quinto con menos {corto} → con más: <strong>{nota_esc(a['nota_final'], a['nota_pct'], materia)}"
                          f" → {nota_esc(b['nota_final'], b['nota_pct'], materia)}</strong>")
        med = datos_m[variable].median()
        no_rinden = int(((datos_m["rendidos"] == 0) & (datos_m[variable] > med)).sum())
        if no_rinden:
            partes.append(f"{comp.num(no_rinden)} sobre la mediana no "
                          f"{'rindió' if no_rinden == 1 else 'rindieron'} nada.")
        if en_cero and escala_log:
            partes.append(f"{comp.num(en_cero)} con 0 no se ven en esta escala.")
        if partes:
            comp.html(f'<p class="tfi nvp-pie num">{"<br>".join(partes)}</p>', col)

# ---------------------------------------------------------------------------
# Por nivel de actividad (quintiles)
# ---------------------------------------------------------------------------
def titulo_niveles() -> str:
    no_llegan = []
    for m in con_notas:
        g = niveles[niveles["asignatura"] == m].sort_values("orden")
        if len(g) >= 2 and pd.notna(g["nota_final"].iloc[-1]) and \
                g["nota_final"].iloc[-1] < ESQUEMA[m]["cortes"]["Regular"]:
            no_llegan.append((comp.SIGLAS[m], nota_esc(g["nota_final"].iloc[-1], g["nota_pct"].iloc[-1], m)))
    if len(no_llegan) == 1:
        s, v = no_llegan[0]
        return f"En {s} ni el quinto con más {corto} llega a Regular ({v} en promedio)"
    if no_llegan:
        return (f"En {textos.enumerar([f'{s} ({v})' for s, v in no_llegan])} ni el quinto con más {corto} "
                "llega a Regular en promedio")
    if not con_brecha:
        return f"Condición por nivel de {corto}"
    m = max(con_brecha, key=lambda x: brecha.loc[x, "brecha_pp"])
    b = brecha.loc[m]
    donde = f"En {comp.SIGLAS[m]}, l" if varias else "L"
    return (f"{donde}os libres pasan de {comp.pct(b['libre_menos'], 0)} en el quinto con menos {corto} a "
            f"{comp.pct(b['libre_mas'], 0)} en el de más")


with tab_nivel:
    columnas_cond = {"Libre": "pct_libre", "Regular": "pct_regular", "Promociona": "pct_promociona",
                     SIN_EVALUACIONES: "pct_sin_evaluaciones"}   # Libre anclado a la izquierda
    con_datos = [c for c, col in columnas_cond.items() if not niveles.empty and niveles[col].sum() > 0]
    bloques = []
    for materia in materias:
        n_m = niveles[niveles["asignatura"] == materia].sort_values("orden")
        if n_m.empty:
            continue
        rangos = textos.rangos_quintiles(list(n_m["hasta"]))
        filas = []
        for fila, rango in zip(n_m.itertuples(), rangos):
            segmentos = "".join(
                f'<span style="width:{getattr(fila, columnas_cond[c]):.1f}%;background:{comp.COLORES_CONDICION[c]}"'
                f' title="{c}: {comp.pct(getattr(fila, columnas_cond[c]), 0)}">'
                f'{comp.pct(getattr(fila, columnas_cond[c]), 0) if getattr(fila, columnas_cond[c]) >= 8 else ""}</span>'
                for c in con_datos)
            filas.append(f'<div class="tfi-apilada"><span class="izq num">{fila.nivel} <span>{rango}</span></span>'
                         f'<span class="barra">{segmentos}</span>'
                         f'<span class="der num" title="Nota promedio sobre 100">{comp.num(fila.nota_pct, 1)}</span></div>')
        unidad = UNIDAD.get(variable, corto)
        bloques.append(f'{comp.titulo_materia(materia, f"{unidad} · nota promedio sobre 100")}{"".join(filas)}'
                       '<div style="height:14px"></div>')

    leyenda = comp.leyenda([(c, comp.COLORES_CONDICION[c], "cuadro") for c in con_datos])
    comp.html(f"""
<div class="tfi tfi-card">
  {comp.titulo(titulo_niveles(), tip="Los alumnos de cada materia se ordenan por " + nombre_var.lower() + " y se parten en cinco grupos del mismo tamaño. Si muchos tienen el mismo valor (por ejemplo, 0), el empate se reparte entre grupos vecinos y el rango se repite. La nota de la derecha es el promedio del grupo sobre 100 (en Álgebra, la nota sobre 120 pasada a 100).")}
  <p class="nvp-intro">Cada materia en 5 grupos iguales según {corto}. Barra: condición; a la derecha, nota promedio
    sobre 100.</p>
  {leyenda}<div style="height:6px"></div>{''.join(bloques)}
</div>""")

    if not niveles.empty:
        vista = niveles.assign(
            Materia=niveles["asignatura"], Nivel=niveles["nivel"], Alumnos=niveles["alumnos"],
            Desde=niveles["desde"], Hasta=niveles["hasta"], **{"Nota promedio (sobre 100)": niveles["nota_pct"]},
            **{f"% {c}": niveles[columnas_cond[c]] for c in con_datos},
        ).drop(columns=niveles.columns)
        st.write("")
        with st.expander("Ver la tabla", icon=":material/table:"):
            st.dataframe(vista, hide_index=True, width="stretch")
            comp.boton_csv(vista, f"nota_por_nivel_{variable}")

# ---------------------------------------------------------------------------
# Cuadrante de riesgo
# ---------------------------------------------------------------------------
def titulo_cuadrante() -> str:
    debajo = alumnos[alumnos[variable] < alumnos["mediana_actividad"]]
    if debajo.empty:
        return f"Nadie queda debajo de la mediana de {corto}"
    if riesgo.empty:
        return f"Nadie debajo de la mediana de {corto} está libre al corte"
    p = len(riesgo) / len(debajo) * 100
    proporcion = textos.proporcion_en_palabras(p)
    return f"{proporcion} de los que están debajo de la mediana de {corto} quedan libres"


with tab_cuad:
    conteo = alumnos.groupby(["asignatura", "cuadrante"]).size()
    grillas = []
    for materia in materias:
        datos_m = alumnos[alumnos["asignatura"] == materia]
        mediana = datos_m["mediana_actividad"].iloc[0]
        # Grilla 2×2 con encabezados: columnas = debajo / sobre la mediana; filas = no libre / libre.
        celdas = ['<span></span><span class="col">Debajo de la mediana</span><span class="col">Sobre la mediana</span>']
        for i, (cuad, (corto_cuad, _)) in enumerate(CUADRANTES.items()):
            if i % 2 == 0:
                celdas.append(f'<span class="fila">{"No libre" if i == 0 else "Libre"}</span>')
            n = int(conteo.get((materia, cuad), 0))
            fondo, borde, c_num, c_txt = COLOR_CUADRANTE["riesgo" if cuad == RIESGO else "neutro"]
            celdas.append(f'<div class="celda" title="{corto_cuad}" style="background:{fondo};border-color:{borde}">'
                          f'<span class="n num" style="color:{c_num}">{comp.num(n)}</span>'
                          f'<span class="p num" style="color:{c_txt}">{comp.pct(n / len(datos_m) * 100, 0)}</span></div>')
        grillas.append(f'<div>{comp.titulo_materia(materia, "mediana " + fmt_var(mediana), sigla=True)}'
                       f'<div class="nvp-cuad">{"".join(celdas)}</div></div>')

    riesgo_txt = (f"Contactar primero: {comp.num(total['casos'])} casos"
                  + (f" de {comp.num(total['alumnos'])} alumnos" if varias else "")
                  + f"; {comp.num(total['sin_rendir'])} no rindieron nada.")
    acciones = []
    for cuad in [RIESGO, "Activo con nota baja", "Poca actividad con buena nota", "Activo con buena nota"]:
        corto_cuad, texto = CUADRANTES[cuad]
        es_riesgo = cuad == RIESGO
        color = comp.TONOS["critico"][2] if es_riesgo else comp.TEXTO_2
        acciones.append(f'<div><p style="margin:0 0 4px;display:flex;align-items:center;gap:7px;'
                        f'font:600 12px Inter,sans-serif;color:{color}">'
                        f'{comp.icono("critico" if es_riesgo else "neutro", 11, None if es_riesgo else "#A8A49B")}'
                        f'{corto_cuad}</p><p class="tfi-texto" style="font-size:12px">{riesgo_txt if es_riesgo else texto}</p></div>')
    comp.html(f"""
<div class="tfi tfi-card" style="margin-bottom:14px">
  {comp.titulo(titulo_cuadrante(), tip="Debajo de la mediana: " + nombre_var.lower() + " menor que la mediana de su materia (la mitad de la base queda debajo, salvo empates). Libre: condición al corte. Es una partición, no una predicción: para anticipar quién va a dejar, ver Predictor de abandono.")}
  <p class="nvp-intro">Dos cortes: {corto} contra la mediana de la materia y libre o no al corte. Incluye a quienes no
    rindieron nada.</p>
  <div class="nvp-grillas">{''.join(grillas)}</div>
  <div class="nvp-acciones">{''.join(acciones)}</div>
</div>""")

    with st.expander("Ver el gráfico de cuadrantes", icon=":material/scatter_plot:"):
        comp.html(comp.leyenda([(CUADRANTES[c][0], MARCA_CUADRANTE[c][0], "critico" if c == RIESGO else "punto")
                                for c in CUADRANTES]
                               + [("Mediana de la materia", comp.NEUTRO, "linea_punteada"),
                                  ("Corte de Regular", comp.CRITICO, "linea_punteada")]))
        cols = st.columns(len(materias)) if varias else [st.container()]
        for col, materia in zip(cols, materias):
            datos_m = alumnos[alumnos["asignatura"] == materia]
            esq = ESQUEMA[materia]
            mediana = datos_m["mediana_actividad"].iloc[0]
            comp.html(comp.titulo_materia(materia, f"mediana {fmt_var(mediana)} · nota sobre {esq['total_max']}",
                                          sigla=True), col)
            fig = go.Figure()
            for cuad, (corto_cuad, _) in CUADRANTES.items():
                q = datos_m[datos_m["cuadrante"] == cuad]
                color, simbolo = MARCA_CUADRANTE[cuad]
                fig.add_trace(go.Scatter(
                    x=q[variable], y=q["nota_final"], mode="markers", name=corto_cuad,
                    marker=dict(color=color, size=7, opacity=0.75 if cuad == RIESGO else 0.6, symbol=simbolo,
                                line=dict(width=0.6, color="white")),
                    customdata=q[["nombre_completo", "id_alumno"]],
                    hovertemplate="%{customdata[0]} (%{customdata[1]})<br>" + nombre_var + ": %{x:,.0f}"
                                  f"<br>Nota: %{{y:.1f}} / {esq['total_max']}<extra>{corto_cuad}</extra>"))
            fig.add_vline(x=mediana, line_dash="dash", line_color=comp.NEUTRO)
            fig.add_hline(y=esq["cortes"]["Regular"], line_dash="dash", line_color=comp.CRITICO, line_width=1.2)
            fig.update_layout(height=320, showlegend=False, margin=dict(t=8, l=4, r=4, b=4))
            fig.update_xaxes(title_text=nombre_var, showgrid=False)
            fig.update_yaxes(title_text=None, range=[-4, esq["total_max"] + 4])
            comp.grafico(fig, col)

    st.write("")
    with st.container(key="nvp_lista"):
        c1, c2 = st.columns([3, 1.2], vertical_alignment="center")
        cuantos = (f"{comp.num(total['casos'])} casos · {comp.num(total['alumnos'])} alumnos distintos" if varias
                   else f"{comp.num(total['casos'])} alumnos")
        comp.html(f'<div class="tfi">{comp.titulo("Prioridad de contacto")}<p class="nvp-intro" style="margin:0">'
                  f"<strong>{cuantos}</strong> debajo de la mediana y libres. Ordenados por días sin entrar; los que "
                  "nunca entraron van primero.</p></div>", c1)
        lista = riesgo
        if varias and not riesgo.empty:
            n_por = riesgo["asignatura"].value_counts()
            opciones = [comp.TODAS, *[m for m in materias if n_por.get(m, 0)]]
            filtro = c2.selectbox("Materia de la lista", opciones, key="nvp_riesgo_materia", label_visibility="collapsed",
                                  format_func=lambda m: m if m == comp.TODAS else f"{m} ({n_por[m]})")
            if filtro != comp.TODAS:
                lista = riesgo[riesgo["asignatura"] == filtro]
        if riesgo.empty:
            st.success("No hay alumnos debajo de la mediana y libres a la fecha de corte.")
        else:
            columna_var = nombre_var.replace(" (sesiones)", "").replace(" (reporte)", "")
            materias_en_riesgo = riesgo.groupby("id_alumno")["asignatura"].transform("size")
            lista = lista.assign(_nunca=lista["estado_actividad"].eq(SIN_ACTIVIDAD),
                                 _materias=materias_en_riesgo.reindex(lista.index)).sort_values(
                ["_nunca", "dias_sin_actividad", "nota_pct"], ascending=[False, False, True])
            tabla = pd.DataFrame({
                "Alumno": lista["nombre_completo"], "ID": lista["id_alumno"],
                "Materia": lista["asignatura"].map(comp.SIGLAS),
                **({"Materias en riesgo": lista["_materias"].astype(int)} if varias else {}),
                "Actividad": comp.con_icono(lista["estado_actividad"].replace({SIN_ACTIVIDAD: "Nunca entró"}),
                                            {**comp.ICONOS_ACTIVIDAD, "Nunca entró": "■"}),
                "Sin entrar": [("—" if e == SIN_ACTIVIDAD or pd.isna(dias) else f"{dias:.0f} d")
                               for e, dias in zip(lista["estado_actividad"], lista["dias_sin_actividad"])],
                "Nota": [f"{comp.num(n, 1)} / {e}" for n, e in zip(lista["nota_final"], lista["escala"])],
                "Rindió": lista["rendidos"].astype(int).astype(str) + " de " + lista["instrumentos"].astype(int).astype(str),
                columna_var: [textos.redondear(x) for x in lista[variable]],
                "Inscripto": lista["inscripto"].map({True: "Sí", False: "No"}),
            })
            st.dataframe(tabla, hide_index=True, width="stretch", height=min(38 + 35 * len(tabla), 420),
                         column_config={
                             columna_var: st.column_config.NumberColumn(format="%.0f"),
                             "Materias en riesgo": st.column_config.NumberColumn(
                                 help="En cuántas materias está este alumno debajo de la mediana y libre."),
                         })
            c1, c2 = st.columns([3, 1], vertical_alignment="center")
            c1.caption(f"Mostrando {comp.num(len(tabla))} de {comp.num(len(riesgo))}.")
            with c2:
                comp.boton_csv(tabla, f"alumnos_en_riesgo_{variable}")

# ---------------------------------------------------------------------------
# Correlaciones
# ---------------------------------------------------------------------------
def barrita(rho, significativa: bool) -> str:
    if pd.isna(rho):
        return '<span class="sub">sin datos</span>'
    color = ("#1B4B8F" if rho >= 0.7 else "#4B7FC4" if rho >= 0.55 else "#7FA6D9" if rho >= 0.45 else "#A9C4E6")
    if rho < 0:
        color = "#E3A49E"
    estilo = "" if significativa else "color:#8A867C"
    ns = "" if significativa else ' <span class="sub" title="no significativa (p ≥ 0,05)">n.s.</span>'
    return (f'<span class="tfi-barrita"><span class="pista"><span style="width:{min(abs(rho), 1) * 100:.0f}%;'
            f'background:{color}"></span></span><span class="num" style="font-weight:500;{estilo}">'
            f'{comp.num(rho, 2)}</span>{ns}</span>')


def titulo_correlaciones() -> str:
    if promedio.empty:
        return "No hay datos suficientes para calcular la correlación"
    mejor = promedio.index[0]
    prom = " en promedio" if varias else ""
    return (f"{mayuscula(EN_PROSA[mejor])} {es(EN_PROSA[mejor])} lo que más acompaña a la nota "
            f"(ρ {comp.num(promedio[mejor], 2)}{prom})")


with tab_corr:
    sig = corr.pivot(index="variable", columns="asignatura", values="significativa").reindex(columns=materias)
    filas = []
    for var in promedio.index:
        nombre = VARIABLES_CRUCE[var].replace(" (reporte)", "").replace(" (sesiones)", "")
        origen = f'<br><span class="sub">{ORIGEN[var]}</span>' if var in ORIGEN else ""
        elegida_css = ' style="background:#F4F8FC"' if var == variable else ""
        celdas = "".join(f"<td>{barrita(matriz.loc[var, m], bool(sig.loc[var, m]))}</td>" for m in materias)
        filas.append(f'<tr{elegida_css}><td><strong style="font-weight:600">{nombre}</strong>{origen}</td>{celdas}'
                     f'<td class="num" style="font-weight:600">{comp.num(promedio[var], 2)}</td></tr>')
    encabezados = "".join(f'<th scope="col">{comp.SIGLAS[m]}</th>' for m in materias)
    tip_corr = (AYUDA_RHO + " El promedio es el de las materias elegidas. El avance cuenta cada evaluación realizada "
                "como un ítem visto: parte de su relación con la nota es circular.")
    comp.html(f"""
<div class="tfi tfi-card" style="margin-bottom:14px">
  {comp.titulo(titulo_correlaciones(), tip=tip_corr)}
  <p class="nvp-intro">ρ de Spearman con la nota sobre 100, dentro de cada materia: va de −1 (a más actividad, menos
    nota) a 1 (mismo orden). Fila resaltada: la elegida arriba.{' Solo quienes rindieron algo.' if solo_rindieron else ''}</p>
  <div style="overflow-x:auto"><table class="tfi-tabla">
    <thead><tr><th scope="col">Forma de participar</th>{encabezados}<th scope="col">Promedio</th></tr></thead>
    <tbody>{''.join(filas)}</tbody></table></div>
</div>""")

    # Qué hacer con esto (con los datos).
    puntos_clave = []
    if not promedio.empty:
        mejor = promedio.index[0]
        puntos_clave.append((comp.TEXTO_4, f"<strong>{mayuscula(EN_PROSA[mejor])} {es(EN_PROSA[mejor])} lo que más "
                                          f"acompaña a la nota al corte</strong> (ρ {comp.num(promedio[mejor], 2)}). "
                                          "Es una foto: no prueba que sirva para anticipar quién va a dejar."))
        celdas = matriz.stack().dropna()
        if not celdas.empty:
            v_floja, m_floja = celdas.idxmin()   # índice (variable, materia)
            puntos_clave.append((comp.TEXTO_4, f"<strong>Lo más flojo {es(EN_PROSA[v_floja])} {EN_PROSA[v_floja]} en "
                                                f"{comp.SIGLAS[m_floja]}</strong> (ρ {comp.num(celdas.min(), 2)}): "
                                                "con esa variable sola no alcanza para anticipar la nota."))
        regularidad = promedio.reindex(["dias_activos", "semanas_activas"]).mean()
        minutos = promedio.get("minutos")
        if pd.notna(regularidad) and pd.notna(minutos):
            prom = " promedio" if varias else ""
            if regularidad >= minutos:
                txt = (f"<strong>Los días y semanas con actividad acompañan algo más a la nota que los minutos</strong> "
                       f"(ρ{prom} {comp.num(regularidad, 2)} contra {comp.num(minutos, 2)}).")
            else:
                txt = (f"<strong>Los minutos acompañan algo más a la nota que los días y semanas con actividad"
                       f"</strong> (ρ{prom} {comp.num(minutos, 2)} contra {comp.num(regularidad, 2)}).")
            puntos_clave.append((comp.TEXTO_4, txt))
    items = "".join(f'<div style="display:flex;gap:11px;margin-bottom:12px">'
                    f'<span style="flex:0 0 8px;height:8px;margin-top:6px;border-radius:2px;background:{c}"></span>'
                    f'<p class="tfi-texto">{t}</p></div>' for c, t in puntos_clave)
    with st.container(key="nvp_caja_hacer"):
        comp.html(f'<div class="tfi">{comp.titulo("Qué hacer con esto")}<div style="height:8px"></div>{items}</div>')
        st.page_link(PAG_PREDICTOR, label="Ir al Predictor de abandono", icon=":material/trending_down:")

    n_min, n_max = corr["n"].min(), corr["n"].max()
    n_txt = f"n = {n_min}" if n_min == n_max else f"n entre {n_min} y {n_max}"
    k_sig, total_rho = int(corr["significativa"].sum()), int(corr["rho"].notna().sum())
    if k_sig == total_rho:
        sig_txt = (f"Todas dan p < 0,05 con {n_txt}. Pero **significativa no quiere decir importante**: con muestras "
                   "grandes, hasta una relación chica da significativa.")
    else:
        sig_txt = (f"{k_sig} de {total_rho} dan p < 0,05 ({n_txt}); las que no, están marcadas con «n.s.». Y "
                   "**significativa no quiere decir importante**: mirá también el tamaño de ρ.")
    vista = corr.assign(
        Materia=corr["asignatura"], Variable=corr["descripcion"], ρ=corr["rho"],
        **{"p-valor": corr["p_valor"], "Alumnos (n)": corr["n"], "Fuerza": corr["fuerza"],
           "Significativa (p < 0,05)": corr["significativa"]},
    )[["Materia", "Variable", "ρ", "p-valor", "Alumnos (n)", "Fuerza", "Significativa (p < 0,05)"]]
    st.write("")
    with st.expander("Ver la tabla con p-valor y n", icon=":material/table:"):
        st.caption(sig_txt)
        st.dataframe(vista, hide_index=True, width="stretch",
                     column_config={"ρ": st.column_config.NumberColumn(format="%.2f"),
                                    "p-valor": st.column_config.NumberColumn(format="%.4f")})
        comp.boton_csv(vista, "correlaciones_notas_participacion")

# ---------------------------------------------------------------------------
# Pie: los modelos que siguen a esta foto
# ---------------------------------------------------------------------------
st.write("")
p1, p2, _ = st.columns([1, 1, 2])
p1.page_link(PAG_GRUPOS, label="Grupos de alumnos", icon=":material/bubble_chart:",
             help="Perfiles de participación armados con K-Means.")
p2.page_link(PAG_PREDICTOR, label="Predictor de abandono", icon=":material/trending_down:",
             help="Quién tiene más probabilidad de dejar la materia, con los datos hasta cada fecha.")
