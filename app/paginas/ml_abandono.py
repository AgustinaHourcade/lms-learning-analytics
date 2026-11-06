"""Machine learning: predictor de abandono (Etapa 7, D58).

Todo el cálculo está en src/ml_abandono.py; esta página solo lo muestra. El
modelo se entrena una vez (con todas las materias) y se guarda con joblib junto
a gold; la app lo lee con @st.cache_resource (componentes.modelo_abandono)."""
import pandas as pd
import plotly.express as px
import streamlit as st

import componentes as comp
from src import ml_abandono as ab

H = ab.ABANDONO_HORIZONTE_DIAS
f = comp.encabezado(
    "Predictor de abandono",
    f"De los alumnos que **vienen entrando** al aula (alguna interacción en los últimos {H} días), ¿quiénes "
    f"**no van a entrar en los próximos {H} días**? El modelo mira solo la actividad hasta la fecha de corte "
    "(días sin entrar, cuánto entró las últimas semanas, si viene bajando, si hizo evaluaciones) y da una "
    "probabilidad. Sirve para contactar a tiempo a quien está por dejar, antes de que lo diga la regla "
    "\"no entra hace una semana\".")

info = comp.metrica("info_modelo")
riesgo = comp.metrica("riesgo_abandono")
umbral = 100 * info["umbral"]
if riesgo.attrs.get("aviso"):
    st.warning(riesgo.attrs["aviso"], icon=":material/warning:")

cuenta = riesgo["nivel_riesgo"].value_counts()
cursando = int(riesgo["estado_abandono"].eq(ab.CURSANDO).sum())
comp.tarjetas([
    ("Vienen entrando", comp.num(cursando), f"Con alguna interacción en los últimos {H} días: a ellos se les predice."),
    (f"{comp.ICONOS_RIESGO[ab.ALTO]} Riesgo alto", comp.num(cuenta.get(ab.ALTO, 0)),
     f"Probabilidad de abandono ≥ {comp.pct(umbral, 0)} (umbral elegido por costo)."),
    (f"{comp.ICONOS_RIESGO[ab.MEDIO]} Riesgo medio", comp.num(cuenta.get(ab.MEDIO, 0)),
     f"Entre {comp.pct(umbral / 2, 0)} y {comp.pct(umbral, 0)}: seguirlos de cerca."),
    (f"{comp.ICONOS_RIESGO[ab.YA_ABANDONO]} Ya abandonaron", comp.num(cuenta.get(ab.YA_ABANDONO, 0)),
     f"Entraron alguna vez, pero hace {H} días o más que no: ya no hay que predecirlo."),
    (f"{comp.ICONOS_RIESGO[ab.SIN_ACTIVIDAD]} Nunca entraron", comp.num(cuenta.get(ab.SIN_ACTIVIDAD, 0))),
])

# --- ¿Acertó? (solo con fechas de corte del pasado) -----------------------------------
conocido = riesgo[riesgo["abandono_real"].notna()]
if not conocido.empty:
    real = conocido["abandono_real"].astype(bool)
    alto = conocido["nivel_riesgo"].eq(ab.ALTO)
    regla = conocido["regla_simple"]
    st.success(
        f"**Esta fecha de corte ya pasó: se puede ver qué hubiera acertado.** De los {comp.num(cursando)} que venían "
        f"entrando, **{comp.num(real.sum())} no volvieron a entrar** en los {H} días siguientes. El modelo marcó "
        f"en riesgo alto a {comp.num(alto.sum())} y detectó a **{comp.num((alto & real).sum())}** de ellos "
        f"({comp.pct(100 * (alto & real).sum() / max(real.sum(), 1), 0)}). La regla \"más de {f.umbral} días sin "
        f"entrar\" marcó a {comp.num(regla.sum())} y detectó a {comp.num((regla & real).sum())} "
        f"({comp.pct(100 * (regla & real).sum() / max(real.sum(), 1), 0)}).", icon=":material/fact_check:")
    st.caption("Ojo: el modelo se entrenó con fotos de estas mismas semanas, así que acá acierta algo más que con "
               "alumnos nuevos. La medida honesta es la de los alumnos de prueba (al final de la página).")
else:
    st.caption(f"Con esta fecha de corte todavía no se sabe qué pasa en los {H} días siguientes (los datos llegan "
               f"hasta el {comp.fmt_fecha(info['datos_hasta'])}). Mové la fecha de corte hacia atrás para ver cuánto "
               "hubiera acertado el modelo.")

# --- Por materia -------------------------------------------------------------------------
izq, der = st.columns([3, 2])
with izq:
    st.markdown("**Riesgo de abandono por materia**")
    por = riesgo.groupby(["asignatura", "nivel_riesgo"]).size().rename("alumnos").reset_index()
    por["pct"] = 100 * por["alumnos"] / por.groupby("asignatura")["alumnos"].transform("sum")
    por["materia"] = por["asignatura"].map(comp.SIGLAS)
    fig = px.bar(por, x="pct", y="materia", color="nivel_riesgo", orientation="h", text="alumnos",
                 color_discrete_map=comp.COLORES_RIESGO, category_orders={"nivel_riesgo": ab.NIVELES},
                 labels={"pct": "% de la base", "materia": "", "nivel_riesgo": ""}, hover_data={"alumnos": True})
    fig.update_traces(textposition="inside")
    fig.update_layout(height=280, xaxis_range=[0, 100])
    st.plotly_chart(fig, width="stretch")
with der:
    st.markdown("**Cómo se reparten las probabilidades**")
    cur = riesgo[riesgo["estado_abandono"].eq(ab.CURSANDO)].assign(materia=lambda t: t["asignatura"].map(comp.SIGLAS))
    fig = px.histogram(cur, x="probabilidad", nbins=20, color_discrete_sequence=[comp.CATEGORICA[0]],
                       labels={"probabilidad": "Probabilidad de abandono (%)", "count": "Alumnos"})
    fig.add_vline(x=umbral, line_dash="dash", line_color=comp.CRITICO, annotation_text="Riesgo alto")
    fig.update_layout(height=280, yaxis_title="Alumnos", bargap=0.05)
    st.plotly_chart(fig, width="stretch")

# --- Lista para contactar ----------------------------------------------------------------
st.subheader("A quién contactar")
niveles = st.multiselect("Niveles", ab.NIVELES, default=[ab.ALTO, ab.YA_ABANDONO], key="ab_niveles",
                         format_func=lambda n: f"{comp.ICONOS_RIESGO[n]} {n}")
lista = riesgo[riesgo["nivel_riesgo"].isin(niveles)]
tabla = pd.DataFrame({
    "Materia": lista["asignatura"].map(comp.SIGLAS), "ID": lista["id_alumno"], "Alumno": lista["nombre_completo"],
    "Riesgo": [comp.texto_riesgo(r) for _, r in lista.iterrows()],
    "Días sin entrar": lista["dias_sin_actividad"], "Días activos (14 d)": lista["dias_activos_14d"],
    "Interacciones (14 d)": lista["eventos_14d"], "Semanas con actividad (%)": lista["pct_semanas_activas"],
    "Inscripto": lista["inscripto"].map({True: "Sí", False: "No"}), "Señales": lista["motivos"],
})
st.dataframe(tabla, hide_index=True, width="stretch",
             column_config={"Días sin entrar": st.column_config.NumberColumn(format="%d"),
                            "Señales": st.column_config.TextColumn(width="large")})
st.caption(f"{comp.num(len(tabla))} alumnos, de mayor a menor riesgo. Las señales describen los datos del alumno; "
           "la probabilidad sale del modelo, que las pesa todas juntas.")
comp.boton_csv(tabla, "riesgo_abandono")

# --- Cómo funciona -----------------------------------------------------------------------
with st.expander("Cómo se armó el modelo y qué tan bueno es", icon=":material/science:"):
    st.markdown(
        f"1. **Fotos de la cursada.** Cada {ab.ABANDONO_PASO_DIAS} días, del {comp.fmt_fecha(info['primera_foto'])} al "
        f"{comp.fmt_fecha(info['ultima_foto'])} ({info['fotos']} fotos), se miró a cada alumno que venía entrando y "
        f"se anotó si entró o no en los {H} días siguientes. Son {comp.num(info['filas'])} casos de "
        f"{comp.num(info['alumnos'])} alumnos; abandona el **{comp.pct(info['tasa_abandono'])}**.\n"
        "2. **Variables:** solo la actividad hasta el día de la foto. Las notas no se usan: son una foto al 24/10 y "
        "le contarían al modelo cosas que todavía no habían pasado.\n"
        "3. **Validación separando por alumno:** el 25 % de los alumnos "
        f"({comp.num(info['alumnos_prueba'])}) quedó afuera del entrenamiento en todas sus fotos y materias, y se "
        "usó solo para medir. Así el modelo no \"reconoce\" a un alumno que ya vio.\n"
        f"4. **Umbral por costo** (como en la clase 10): no detectar a quien abandona cuesta {info['costo_fn']} y "
        f"contactar a alguien que iba a seguir cuesta {info['costo_fp']}. El umbral que minimiza el costo es "
        f"**{comp.pct(umbral, 0)}**: bajo, porque perder un alumno es mucho más caro que un mensaje de más.\n"
        f"5. **Modelo elegido: {info['nombre']}**, el de menor costo en la validación cruzada.")
    comparacion = comp.metrica("comparacion_modelos")
    prueba = comparacion[comparacion["conjunto"].eq("prueba")]
    st.markdown("**Comparación en los alumnos de prueba**")
    st.dataframe(pd.DataFrame({
        "Modelo": prueba["modelo"] + prueba["elegido"].map({True: " ✓", False: ""}),
        "AUC ROC": prueba["auc_roc"], "AUC PR": prueba["auc_pr"],
        "Precisión (%)": prueba["precision"], "Recall (%)": prueba["recall"],
        "Marcados (%)": prueba["pct_marcados"], "Costo cada 100 casos": prueba["costo_por_100"],
    }), hide_index=True, width="stretch")
    st.caption("AUC ROC: qué tan bien ordena (0,5 = azar, 1 = perfecto). AUC PR: lo mismo, mirando solo a los que "
               f"abandonan (azar = {comp.num(info['tasa_abandono'] / 100, 2)}). Precisión: de los marcados, cuántos "
               "abandonaron. Recall: de los que abandonaron, a cuántos marcó. La regla simple marca a quien lleva más "
               f"de {info['regla_dias']} días sin entrar.")
    c1, c2 = st.columns(2)
    curva = comp.metrica("curva_umbral")
    largo = curva.melt(id_vars="umbral", value_vars=["precision", "recall", "pct_marcados"], var_name="medida",
                       value_name="valor").assign(umbral=lambda t: 100 * t["umbral"])
    largo["medida"] = largo["medida"].map({"precision": "Precisión", "recall": "Recall", "pct_marcados": "% marcados"})
    fig = px.line(curva.assign(umbral=100 * curva["umbral"]), x="umbral", y="costo",
                  title="Costo total según el umbral (alumnos de prueba)",
                  labels={"umbral": "Umbral (%)", "costo": "Costo"})
    fig.add_vline(x=umbral, line_dash="dash", line_color=comp.CRITICO, annotation_text="Elegido")
    fig.update_layout(height=300)
    c1.plotly_chart(fig, width="stretch")
    fig = px.line(largo, x="umbral", y="valor", color="medida", title="Lo que se gana y se pierde con el umbral",
                  labels={"umbral": "Umbral (%)", "valor": "%", "medida": ""})
    fig.add_vline(x=umbral, line_dash="dash", line_color=comp.CRITICO)
    fig.update_layout(height=300)
    c2.plotly_chart(fig, width="stretch")
    imp = comp.metrica("importancia_variables")
    fig = px.bar(imp.sort_values("importancia"), x="importancia", y="descripcion", orientation="h",
                 color_discrete_sequence=[comp.CATEGORICA[0]], error_x="desvio",
                 title="Qué variables usa más el modelo",
                 labels={"importancia": "Cuánto empeora el AUC PR si se mezcla la variable", "descripcion": ""})
    fig.update_layout(height=380)
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        "**Limitaciones.** Una sola cursada y unos 210 alumnos por materia (226 personas distintas): el modelo "
        "aprende cómo se comportó esta cohorte y habría que revalidarlo con la próxima. \"Abandono\" acá es dejar "
        f"de entrar {H} días, no la baja formal: algunos vuelven. Los modelos mejoran a la regla simple, pero no por "
        "mucho: la mayoría de los marcados no abandona. Por eso sirve para **priorizar a quién contactar**, no para "
        "decidir nada sobre un alumno.")
