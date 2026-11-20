"""Machine learning: predictor de abandono (Etapa 7, D58).

Todo el cálculo está en src/ml_abandono.py; esta página solo lo muestra. El
modelo se entrena una vez (con todas las materias) y se guarda con joblib junto
a gold; la app lo lee con @st.cache_resource (componentes.modelo_abandono).

Es la primera página con el sistema de diseño nuevo (tarjetas, chips y tablas de
componentes.py): sirve de modelo para rediseñar las demás."""
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import componentes as comp
from src import ml_abandono as ab

H = ab.ABANDONO_HORIZONTE_DIAS
T = comp.TONOS
f = comp.cabecera(
    "Predictor de abandono",
    f"De los alumnos que <strong>todavía vienen entrando</strong> al aula (alguna interacción en los últimos "
    f"{H} días), ¿quiénes <strong>no van a entrar en los próximos {H} días</strong>? Sirve para contactar a "
    "tiempo a quien está por dejar, antes de que lo diga la regla “hace una semana que no entra”.")

info = comp.metrica("info_modelo")
riesgo = comp.metrica("riesgo_abandono")
u_modelo = 100 * info["umbral"]   # exacto: así los niveles coinciden con los de src

# --- Umbral de "riesgo alto" ---------------------------------------------------------------
# El slider está más abajo (tarjeta "Dónde poner el corte"), pero su valor se usa en toda la
# página: se lee de session_state antes de dibujarlo. Por defecto, el umbral del modelo (por costo).
OPCIONES_UMBRAL = sorted({x / 2 for x in range(10, 81)} | {u_modelo})
if st.session_state.get("ab_umbral_alto") not in OPCIONES_UMBRAL:
    st.session_state["ab_umbral_alto"] = u_modelo
u = st.session_state["ab_umbral_alto"]

cursa = riesgo["estado_abandono"].eq(ab.CURSANDO)
if u != u_modelo:   # mismos cortes que src (alto >= u, medio >= u/2), con el umbral elegido acá
    p = riesgo["probabilidad"]
    riesgo["nivel_riesgo"] = np.select([~cursa, p >= u, p >= u / 2], [riesgo["estado_abandono"], ab.ALTO, ab.MEDIO],
                                       default=ab.BAJO)
cuenta = riesgo["nivel_riesgo"].value_counts()
n = {nivel: int(cuenta.get(nivel, 0)) for nivel in ab.NIVELES}
cursando = int(cursa.sum())


def _fmt_u(x: float) -> str:
    return comp.pct(x, 0 if float(x).is_integer() else 1)


def _ir_a(fecha) -> None:
    st.session_state["fecha_corte"] = pd.Timestamp(fecha).date()


# --- Cómo funciona + ¿acertó? --------------------------------------------------------------
izq, der = st.columns([1.15, 1], gap="small")
with izq:
    st.html('<div class="tfi tfi-card" style="height:100%">'
            + comp.titulo_tarjeta("Qué mira el modelo")
            + '<div class="tfi-chips" style="margin:8px 0 14px">'
            + "".join(comp.chip(x) for x in ["Días sin entrar", "Su pausa habitual", "Interacciones recientes",
                                             "Si la actividad viene bajando", "Si sigue en sus otras materias",
                                             "Días desde la última evaluación", "Nota a la fecha",
                                             "Si rindió la última evaluación"])
            + "</div>"
            + '<p class="tfi-p">Todo con lo que se sabía a la fecha de corte: cada nota cuenta desde el día en que '
              "el alumno rindió, no la foto de notas del final. Devuelve una probabilidad por alumno.</p></div>")

conocido = riesgo[riesgo["abandono_real"].notna()]
with der:
    if conocido.empty:
        hasta = pd.Timestamp(info["datos_hasta"])
        prueba = min(hasta - pd.Timedelta(days=H), pd.Timestamp(f.fecha_corte) - pd.Timedelta(days=H))
        with comp.tarjeta("acierto", "ambar"):
            st.html(f'<div class="tfi"><h3 class="tfi-h3" style="color:#6B4700">'
                    f'<span style="color:{T["medio"]["fuerte"]};display:flex">{comp.icono("medio", 15)}</span>'
                    f'Todavía no sabemos si acierta</h3>'
                    f'<p class="tfi-p" style="color:{T["medio"]["texto"]};margin-top:8px">Con el corte en '
                    f'{comp.fmt_fecha(f.fecha_corte)} no hay {H} días posteriores para comparar: los datos llegan hasta '
                    f'el {comp.fmt_fecha(hasta)}. Para ver cuánto hubiera acertado, mové la fecha de corte dos semanas '
                    "hacia atrás.</p></div>")
            st.button(f"Probar con corte {prueba:%d/%m}", on_click=_ir_a, args=(prueba,), key="ab_probar")
    else:
        real = conocido["abandono_real"].astype(bool)
        alto = conocido["nivel_riesgo"].eq(ab.ALTO)
        regla = conocido["regla_simple"]
        det_mod, det_regla = int((alto & real).sum()), int((regla & real).sum())
        tot = max(int(real.sum()), 1)
        with comp.tarjeta("acierto", "verde"):
            st.html(f'<div class="tfi"><h3 class="tfi-h3" style="color:{T["bajo"]["texto"]}">'
                    f'<span style="display:flex">{comp.icono("bajo", 15)}</span>Esta fecha ya pasó: se puede ver qué '
                    f'hubiera acertado</h3><p class="tfi-p" style="color:{T["bajo"]["texto"]};margin-top:8px">'
                    f'De los {comp.num(cursando)} que venían entrando, <strong>{comp.num(real.sum())} no volvieron a '
                    f'entrar</strong> en los {H} días siguientes. El modelo marcó a {comp.num(alto.sum())} en riesgo '
                    f'alto y detectó a <strong>{comp.num(det_mod)} ({comp.pct(100 * det_mod / tot, 0)})</strong>. '
                    f'La regla “más de {f.umbral} días sin entrar” marcó a {comp.num(regla.sum())} y detectó a '
                    f'{comp.num(det_regla)} ({comp.pct(100 * det_regla / tot, 0)}).</p>'
                    f'<p class="tfi-p" style="color:{T["bajo"]["texto"]};margin-top:6px;font-size:11.5px">Ojo: el '
                    "modelo se entrenó con fotos de estas mismas semanas, así que acá acierta algo más que con "
                    "alumnos nuevos. La medida honesta es la de los alumnos de prueba (al final).</p></div>")
            defecto = comp.DEFECTOS["fecha_corte"]
            st.button(f"Volver al corte {defecto:%d/%m}", on_click=_ir_a, args=(defecto,), key="ab_volver")

if riesgo.attrs.get("aviso"):
    st.html(f'<div class="tfi tfi-card" style="background:{T["medio"]["fondo"]};border-color:{T["medio"]["borde"]};'
            f'padding:12px 16px"><p class="tfi-p" style="color:{T["medio"]["texto"]};display:flex;gap:8px;'
            f'align-items:center">{comp.icono("medio", 13)}{comp.esc(riesgo.attrs["aviso"])}</p></div>')

# --- Indicadores ---------------------------------------------------------------------------
def _de_cursando(x: int) -> str:
    return comp.pct(100 * x / cursando, 0) if cursando else "–"


comp.kpis([
    comp.kpi("Vienen entrando", comp.num(cursando), "el modelo opina sobre estos"),
    comp.kpi("Riesgo alto", comp.num(n[ab.ALTO]), f"{_de_cursando(n[ab.ALTO])} de los que entran · desde "
             f"{_fmt_u(u)}", "alto"),
    comp.kpi("Riesgo medio", comp.num(n[ab.MEDIO]), f"{_de_cursando(n[ab.MEDIO])} · seguirlos de cerca", "medio"),
    comp.kpi("Ya abandonaron", comp.num(n[ab.YA_ABANDONO]),
             f"{H} días o más sin entrar · + {comp.num(n[ab.SIN_ACTIVIDAD])} que nunca entraron", "abandono"),
])

# --- Por materia + umbral ------------------------------------------------------------------
izq, der = st.columns([1.1, 1], gap="small")
with izq:
    por = riesgo.groupby(["asignatura", "nivel_riesgo"]).size().unstack(fill_value=0).reindex(columns=ab.NIVELES,
                                                                                             fill_value=0)
    por = por.assign(total=por.sum(axis=1)).sort_values(ab.ALTO, ascending=False)
    peor_alto = por[ab.ALTO].idxmax() if len(por) > 1 else None
    tasa_ya = por[ab.YA_ABANDONO] / por["total"]
    peor_ya = tasa_ya.idxmax() if len(por) > 1 else None
    bloques = []
    for asig, fila in por.iterrows():
        nota, tono = f"{comp.num(fila[ab.ALTO])} en riesgo alto · {comp.num(fila[ab.YA_ABANDONO])} ya abandonaron", None
        if asig == peor_ya:
            nota, tono = (f"{comp.num(fila[ab.YA_ABANDONO])} ya abandonaron ({comp.pct(100 * tasa_ya[asig], 0)}): "
                          f"la que más alumnos perdió · {comp.num(fila[ab.ALTO])} en riesgo alto"), "alto"
        elif asig == peor_alto:
            nota += ": la que más riesgo alto tiene"
        segmentos = [(nivel, int(fila[nivel]), comp.COLORES_RIESGO[nivel]) for nivel in ab.NIVELES]
        bloques.append(comp.barra_apilada(asig, fila["total"], segmentos, nota, tono))
    st.html('<div class="tfi tfi-card" style="height:100%">'
            + comp.titulo_tarjeta("Riesgo por materia", "Sobre la base completa de cada materia, incluidos los que "
                                  "ya dejaron.")
            + "".join(bloques)
            + comp.leyenda([("Alto", "alto"), ("Medio", "medio"), ("Bajo", "bajo"), ("Ya abandonó", "abandono"),
                            ("Nunca entró", "neutro")])
            + "</div>")

with der, comp.tarjeta("umbral"):
    st.html('<div class="tfi">' + comp.titulo_tarjeta(
        "Dónde poner el corte", "Cómo se reparten las probabilidades de los que vienen entrando. La línea marca el "
        "umbral de “riesgo alto”: moverla cambia a cuánta gente hay que contactar.") + "</div>")
    prob = riesgo.loc[cursa, "probabilidad"].dropna()
    if prob.empty:
        st.caption("Nadie viene entrando a esta fecha de corte.")
    else:
        ancho = 2.5
        tope = max(np.ceil(max(prob.max(), u) / ancho) * ancho, 20)
        cuentas, bordes = np.histogram(prob, bins=np.arange(0, tope + ancho, ancho))
        colores = [T["alto"]["suave"] if b >= u else T["azul"]["suave"] for b in bordes[:-1]]
        fig = go.Figure(go.Bar(
            x=bordes[:-1] + ancho / 2, y=cuentas, width=ancho * 0.88, marker_color=colores,
            customdata=np.c_[bordes[:-1], bordes[1:]],
            hovertemplate="%{customdata[0]:.1f}–%{customdata[1]:.1f} %: %{y} alumnos<extra></extra>"))
        fig.add_vline(x=u, line_dash="dash", line_width=2, line_color=T["alto"]["fuerte"])
        fig.add_annotation(x=u, y=1, yref="paper", text=f"umbral {_fmt_u(u)}",
                           showarrow=False, xanchor="left", xshift=6, yanchor="top",
                           font=dict(color=T["alto"]["texto"], size=11, family=comp.FUENTE))
        fig.update_layout(height=200, margin=dict(t=8, l=4, r=4, b=4), showlegend=False, bargap=0,
                          xaxis=dict(ticksuffix=" %", showgrid=False), yaxis=dict(title=None, nticks=4))
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})

    marcados = int(((riesgo["probabilidad"] >= u) & cursa).sum())
    st.html(f'<div class="tfi" style="display:flex;justify-content:space-between;align-items:baseline;'
            f'font:500 12px {comp.FUENTE};color:{comp.TOKENS["texto_2"]}"><span>Umbral de riesgo alto</span>'
            f'<span class="num" style="font-weight:600;font-size:13px;color:{comp.TOKENS["tinta"]}">'
            f'{_fmt_u(u)} · {comp.num(marcados)} alumnos</span></div>')
    st.select_slider("Umbral de riesgo alto", OPCIONES_UMBRAL, key="ab_umbral_alto", label_visibility="collapsed",
                     format_func=_fmt_u)
    if u != u_modelo:
        st.button(f"Volver al umbral del modelo ({comp.pct(u_modelo)})", key="ab_umbral_reset",
                  on_click=lambda: st.session_state.update(ab_umbral_alto=u_modelo))
    if not prob.empty:
        p95 = prob.quantile(0.95)
        st.html(f'<p class="tfi tfi-nota">El modelo eligió <strong>{comp.pct(u_modelo)}</strong> minimizando el costo '
                f"(no detectar a quien abandona cuesta {info['costo_fn']}, un contacto de más cuesta "
                f"{info['costo_fp']}). El 95 % está por debajo de {comp.pct(p95, 0)}: lo que importa no es la "
                "probabilidad en sí, sino <strong>el orden</strong>: a cuántos podés contactar esta semana y "
                "quiénes son los primeros de la lista.</p>")

# --- A quién contactar ---------------------------------------------------------------------
ORDEN = {nivel: i for i, nivel in enumerate(ab.NIVELES)}
# Las señales de src, en versión chip (el texto completo queda en el tooltip).
CORTOS = [(r"^su actividad bajó de (\d+) a (\d+) interacciones$", r"actividad bajó de \1 a \2"),
          (r"^entró solo 1 día\(s\) en las últimas 2 semanas$", "1 solo día activo"),
          (r"^entró solo (\d+) día\(s\) en las últimas 2 semanas$", r"solo \1 días activos"),
          (r"^no hizo evaluaciones en las últimas 2 semanas$", "sin evaluaciones recientes"),
          (r"^entró en el (\d+) % de las semanas$", r"entró el \1 % de las semanas")]


def _motivos(fila) -> list[str]:
    """Chips de 'por qué': las señales de src, cortas, con el texto completo en el tooltip."""
    chips = []
    if fila["estado_abandono"] == ab.YA_ABANDONO:
        chips.append(comp.chip(f"{fila['dias_sin_actividad']:.0f} días sin entrar", "abandono", True))
    elif fila["estado_abandono"] == ab.SIN_ACTIVIDAD:
        chips.append(comp.chip("nunca entró al aula", "neutro", True))
    for m in filter(None, str(fila["motivos"]).split("; ")):
        corto = m.split(" (")[0]
        corto = corto[0].lower() + corto[1:]
        for largo, breve in CORTOS:
            corto = re.sub(largo, breve, corto)
        chips.append(comp.chip(comp.esc(corto), "alto" if "sin entrar" in corto else "medio", True, titulo=m))
    if pd.notna(fila["inscripto"]) and not fila["inscripto"]:
        chips.append(comp.chip("además, sin inscripción", "azul", True))
    return chips


def _riesgo(fila) -> str:
    tono = comp.TONO_RIESGO[fila["nivel_riesgo"]]
    if pd.isna(fila["probabilidad"]):
        return comp.chip(f'{comp.icono(tono, 10)}&nbsp;{fila["nivel_riesgo"]}', tono, True)
    p = fila["probabilidad"]
    return (f'<span class="tfi-meter"><span><span style="width:{min(p, 100):.0f}%;background:{T[tono]["fuerte"]}">'
            f'</span></span><span class="num" style="font-weight:600;color:{T[tono]["texto"]}">'
            f'{comp.pct(p, 0)}</span></span>')


with comp.tarjeta("contactar"):
    st.html('<div class="tfi">' + comp.titulo_tarjeta(
        "A quién contactar", "Ordenados por nivel y probabilidad. Las señales dicen por qué el modelo lo marcó; "
        "la probabilidad sale del modelo, que las pesa todas juntas.") + "</div>")
    st.session_state.setdefault("ab_niveles", [ab.ALTO, ab.YA_ABANDONO])
    niveles = st.pills("Niveles", ab.NIVELES, selection_mode="multi", key="ab_niveles",
                       format_func=lambda x: f"{x} ({comp.num(n[x])})", label_visibility="collapsed")
    lista = riesgo[riesgo["nivel_riesgo"].isin(niveles or [])].copy()
    lista["_o"] = lista["nivel_riesgo"].map(ORDEN)
    lista = lista.sort_values(["_o", "probabilidad", "dias_sin_actividad"], ascending=[True, False, False])

    if lista.empty:
        st.caption("Elegí al menos un nivel para ver la lista.")
    else:
        MAXIMO = 300
        filas = []
        for _, r in lista.head(MAXIMO).iterrows():
            insc = ("con inscripción" if r["inscripto"] else
                    f'<span style="color:{T["alto"]["texto"]}">sin inscripción</span>')
            filas.append([
                f'<strong style="font-weight:600">{comp.esc(r["nombre_completo"])}</strong><br>'
                f'<span class="sec num">{comp.esc(r["id_alumno"])} · {insc}</span>',
                comp.insignia_materia(r["asignatura"]),
                _riesgo(r),
                f'<span style="font-weight:600">{comp.num(r["dias_sin_actividad"])} d</span>'
                if pd.notna(r["dias_sin_actividad"]) else "–",
                comp.num(r["dias_activos_14d"]), comp.num(r["eventos_14d"]),
                f'<span class="tfi-chips" style="gap:5px">{"".join(_motivos(r))}</span>',
            ])
        st.html(comp.tabla_html(
            ["Alumno", "Materia", "Riesgo", "Sin entrar", f"Días activos ({H} d)", f"Interacciones ({H} d)",
             "Por qué"], filas, ["", "", "", "num", "num", "num", "wrap"]))

        primeros = lista.head(10)["asignatura"].map(comp.SIGLAS).value_counts()
        reparto = ", ".join(f"{v} de {k}" for k, v in primeros.items())
        mostrados = (f"Se muestran los primeros {comp.num(MAXIMO)} de {comp.num(len(lista))}; el CSV tiene todos. "
                     if len(lista) > MAXIMO else f"{comp.num(len(lista))} alumnos. ")
        st.html(f'<p class="tfi tfi-pie">{mostrados}De los 10 primeros de la lista: {reparto}.</p>')

        tabla = pd.DataFrame({
            "Materia": lista["asignatura"].map(comp.SIGLAS), "ID": lista["id_alumno"],
            "Alumno": lista["nombre_completo"], "Nivel": lista["nivel_riesgo"],
            "Probabilidad (%)": lista["probabilidad"], "Días sin entrar": lista["dias_sin_actividad"],
            "Días activos (14 d)": lista["dias_activos_14d"], "Interacciones (14 d)": lista["eventos_14d"],
            "Semanas con actividad (%)": lista["pct_semanas_activas"],
            "Inscripto": lista["inscripto"].map({True: "Sí", False: "No"}), "Señales": lista["motivos"],
        })
        comp.boton_csv(tabla, "riesgo_abandono", f"Descargar la lista ({comp.num(len(tabla))})")

# --- Un alumno -----------------------------------------------------------------------------
# Mismo buscador que la Ficha individual: un desplegable con búsqueda por nombre o ID, solo
# alumnos de la base de la materia de la barra, ordenados por apellido; muestra al primero.
with comp.tarjeta("alumno"):
    st.html('<div class="tfi">' + comp.titulo_tarjeta(
        "Buscar un alumno", "Su riesgo en cada materia, cómo evolucionó y sus indicadores contra la mediana "
        "del curso.") + "</div>")
    alumnos = comp.metrica("buscar_alumnos", texto="", solo_base=True)
    if alumnos.empty:
        st.info(f"No hay alumnos en la base de {f.materia.lower()}.", icon=":material/person_off:")
    else:
        nombres = dict(zip(alumnos["id_alumno"], alumnos["nombre_completo"]))
        # El ícono del peor nivel del alumno (entre las materias de la barra) ayuda a ubicarlo en la lista.
        orden_nivel = {nv: i for i, nv in enumerate(ab.NIVELES)}
        peor = (riesgo.assign(_o=riesgo["nivel_riesgo"].map(orden_nivel)).sort_values("_o")
                .drop_duplicates("id_alumno").set_index("id_alumno")["nivel_riesgo"])
        id_alumno = st.selectbox(
            f"Alumno ({comp.num(len(alumnos))} en la base)", list(nombres), key="ab_alumno",
            format_func=lambda i: f"{comp.ICONOS_RIESGO.get(peor.get(i), '')} {nombres[i]} · {i}".strip(),
            help="Escribí parte del apellido, nombre o ID (ej.: ALU_1263) para filtrar. Ordenados por apellido; "
                 "por defecto se muestra el primero. El ícono es su nivel de riesgo más alto.")
        st.markdown(f"**{nombres[id_alumno]} · {id_alumno}**")
        if f.asignatura:
            st.caption(f"El buscador lista solo alumnos de {f.asignatura}, pero el resumen muestra todas sus materias.")

        # Tarjeta por materia (nivel, probabilidad, señales) y evolución semana a semana.
        comp.riesgo_abandono_alumno(id_alumno)

        # Sus indicadores contra la mediana de quienes vienen entrando en la misma materia.
        todos = comp.metrica("riesgo_abandono", asignatura=None)
        suyo = todos[todos["id_alumno"].eq(id_alumno)]
        curso = todos[todos["estado_abandono"].eq(ab.CURSANDO)].groupby("asignatura")
        indicadores = ["dias_sin_actividad", "pausa_habitual", "dias_desde_evaluacion", "nota_pct", "pct_rendidos",
                       "eventos_14d_otras", "eventos_7d", "eventos_14d", "eventos_14d_previos", "dias_activos_14d",
                       "sesiones_14d", "minutos_14d", "evaluaciones_14d", "pct_semanas_activas", "eventos_total"]
        nombres_ind = {**ab.VARIABLES, "eventos_14d_previos": "Interacciones en las 2 semanas anteriores"}
        resumen = pd.DataFrame({"Indicador": [nombres_ind[c] for c in indicadores]})
        for _, fila in suyo.iterrows():
            sigla = comp.SIGLAS.get(fila["asignatura"], fila["asignatura"])
            mediana = curso.get_group(fila["asignatura"])[indicadores].median() if fila["asignatura"] in curso.groups \
                else pd.Series(index=indicadores, dtype=float)
            resumen[f"{sigla} · alumno"] = [fila[c] for c in indicadores]
            resumen[f"{sigla} · mediana del curso"] = mediana.to_numpy()
        st.markdown("**Sus indicadores a la fecha de corte**")
        st.dataframe(resumen, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.0f") for c in resumen.columns[1:]})
        st.caption("Mediana del curso = la de los alumnos de esa materia que vienen entrando (a quienes se les "
                   f"predice). Son las mismas variables que usa el modelo, calculadas solo con la actividad hasta "
                   f"el {comp.fmt_fecha(f.fecha_corte)}. Para notas y participación, ver la Ficha individual.")
        comp.boton_csv(resumen, f"riesgo_{id_alumno}")

# --- Cómo funciona -----------------------------------------------------------------------
with st.expander("Cómo se armó el modelo y qué tan bueno es", icon=":material/science:"):
    st.markdown(
        f"1. **Fotos de la cursada.** Cada {ab.ABANDONO_PASO_DIAS} días, del {comp.fmt_fecha(info['primera_foto'])} al "
        f"{comp.fmt_fecha(info['ultima_foto'])} ({info['fotos']} fotos), se miró a cada alumno que venía entrando y "
        f"se anotó si entró o no en los {H} días siguientes. Son {comp.num(info['filas'])} casos de "
        f"{comp.num(info['alumnos'])} alumnos; abandona el **{comp.pct(info['tasa_abandono'])}**.\n"
        f"2. **Variables ({len(ab.VARIABLES)}):** todo con lo que se sabía el día de la foto. Actividad reciente, "
        "su pausa habitual entre días activos, lo que hace en sus otras materias, los días desde la última "
        "evaluación de la materia y su nota a la fecha. Cada nota cuenta desde el día en que ese alumno rindió "
        "(su evento «Realizar evaluación»), así el modelo no ve notas que todavía no existían. El reporte de "
        "participación no se usa porque es una foto al 24/10.\n"
        "3. **Validación separando por alumno:** el 25 % de los alumnos "
        f"({comp.num(info['alumnos_prueba'])}) quedó afuera del entrenamiento en todas sus fotos y materias, y se "
        "usó solo para medir. Así el modelo no \"reconoce\" a un alumno que ya vio.\n"
        f"4. **Umbral por costo** (como en la clase 10): no detectar a quien abandona cuesta {info['costo_fn']} y "
        f"contactar a alguien que iba a seguir cuesta {info['costo_fp']}. El umbral que minimiza el costo es "
        f"**{comp.pct(u_modelo)}**: bajo, porque perder un alumno es mucho más caro que un mensaje de más.\n"
        f"5. **Modelo elegido: {info['nombre']}**, el de menor costo en la validación cruzada.")
    comparacion = comp.metrica("comparacion_modelos")
    prueba = comparacion[comparacion["conjunto"].eq("prueba")]
    costo_cv = comparacion[comparacion["conjunto"].eq("validación cruzada")].set_index("modelo")["costo_por_100"]
    st.markdown("**Comparación en los alumnos de prueba**")
    st.dataframe(pd.DataFrame({
        "Modelo": prueba["modelo"] + prueba["elegido"].map({True: " ✓", False: ""}),
        "Costo cada 100 (validación cruzada)": prueba["modelo"].map(costo_cv),
        "AUC ROC": prueba["auc_roc"], "AUC PR": prueba["auc_pr"],
        "Precisión (%)": prueba["precision"], "Recall (%)": prueba["recall"],
        "Marcados (%)": prueba["pct_marcados"], "Costo cada 100 (prueba)": prueba["costo_por_100"],
    }), hide_index=True, width="stretch")
    st.caption("El modelo se elige por el costo en validación cruzada (✓), que usa a todos los alumnos de "
               "entrenamiento repartidos en 5 grupos. La prueba es una sola partición de un cuarto de los alumnos: "
               "sirve para informar, y con tan pocos alumnos puede ordenar los modelos distinto.")
    st.caption("AUC ROC: qué tan bien ordena (0,5 = azar, 1 = perfecto). AUC PR: lo mismo, mirando solo a los que "
               f"abandonan (azar = {comp.num(info['tasa_abandono'] / 100, 2)}). Precisión: de los marcados, cuántos "
               "abandonaron. Recall: de los que abandonaron, a cuántos marcó. La regla simple marca a quien lleva más "
               f"de {info['regla_dias']} días sin entrar.")
    c1, c2 = st.columns(2)
    curva = comp.metrica("curva_umbral")
    largo = curva.melt(id_vars="umbral", value_vars=["precision", "recall", "pct_marcados"], var_name="medida",
                       value_name="valor").assign(umbral=lambda t: 100 * t["umbral"])
    largo["medida"] = largo["medida"].map({"precision": "Precisión", "recall": "Recall", "pct_marcados": "% marcados"})
    rojo, azul = T["alto"]["fuerte"], comp.TOKENS["azul"]
    fig = go.Figure(go.Scatter(x=100 * curva["umbral"], y=curva["costo"], mode="lines", line=dict(color=azul, width=2),
                               hovertemplate="Umbral %{x:.1f} %: costo %{y:,.0f}<extra></extra>"))
    fig.add_vline(x=u_modelo, line_dash="dash", line_color=rojo, annotation_text="Elegido")
    fig.update_layout(height=300, title="Costo total según el umbral (alumnos de prueba)",
                      xaxis_title="Umbral (%)", yaxis_title="Costo")
    c1.plotly_chart(fig, width="stretch", theme=None)
    fig = go.Figure()
    for medida, color in [("Precisión", azul), ("Recall", T["bajo"]["fuerte"]), ("% marcados", T["medio"]["fuerte"])]:
        t = largo[largo["medida"].eq(medida)]
        fig.add_scatter(x=t["umbral"], y=t["valor"], mode="lines", name=medida, line=dict(color=color, width=2))
    fig.add_vline(x=u_modelo, line_dash="dash", line_color=rojo)
    fig.update_layout(height=300, title="Lo que se gana y se pierde con el umbral", xaxis_title="Umbral (%)",
                      yaxis_title="%", legend=dict(y=-0.25, yanchor="top"))
    c2.plotly_chart(fig, width="stretch", theme=None)
    imp = comp.metrica("importancia_variables").sort_values("importancia").tail(12)   # las 12 que más pesan
    fig = go.Figure(go.Bar(x=imp["importancia"], y=imp["descripcion"], orientation="h", marker_color=azul,
                           error_x=dict(type="data", array=imp["desvio"], color=comp.TOKENS["texto_4"])))
    fig.update_layout(height=420, title="Las 12 variables que más usa el modelo",
                      xaxis_title="Cuánto empeora el AUC PR si se mezcla la variable")
    fig.update_yaxes(automargin=True, ticklabelstandoff=6)
    st.plotly_chart(fig, width="stretch", theme=None)
    st.markdown(
        "**Limitaciones.** Una sola cursada y unos 210 alumnos por materia (226 personas distintas): el modelo "
        "aprende cómo se comportó esta cohorte y habría que revalidarlo con la próxima. \"Abandono\" acá es dejar "
        f"de entrar {H} días, no la baja formal: algunos vuelven, por ejemplo después de un parcial. Los modelos "
        "mejoran a la regla simple, pero la mayoría de los marcados igual no abandona. Por eso sirve para "
        "**priorizar a quién contactar**, no para decidir nada sobre un alumno. Además, el modelo solo aprende de "
        f"fotos con {H} días posteriores conocidos: la pausa que sigue a una evaluación muy reciente todavía no la "
        "vio, y en esos casos puede exagerar el riesgo (la página lo avisa).")
