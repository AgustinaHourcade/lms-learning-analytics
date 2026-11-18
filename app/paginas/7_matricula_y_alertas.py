"""Dashboard 3 (del plan): Matrícula y alertas.

Responde, a la fecha de corte: ¿cuántos de los inscriptos están cursando de
verdad?, ¿quién cursa sin estar inscripto?, ¿quién se inscribió y no aparece? y
¿a quién conviene contactar primero?

  Tarjetas        inscriptos, activos, no inscriptos cursando, inscriptos sin
                  notas y alumnos con prioridad alta.
  Matrícula       embudo base -> entraron -> con nota -> activos, evolución de
                  inscripciones contra el primer ingreso al aula y condición de
                  inscriptos vs. no inscriptos.
  Alertas         tarjetas por prioridad, alertas por tipo y materia y la lista
                  priorizada por alumno (D37, D52), filtrable y en CSV.
  No inscriptos   quiénes cursan sin estar en Matriculados (para la secretaría).
  Sin notas       inscriptos que no rindieron nada: nunca entraron o entran y no rinden.

Diseño: sistema visual del rediseño (tarjetas, chips con forma, notas de lectura).
Las notas de lectura se arman con los datos de la fecha de corte, no son texto fijo.
Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

import componentes as comp
from src.metricas import TIPOS_ALERTA

f = comp.encabezado(
    "Matrícula y alertas",
    "El cruce entre la inscripción formal y lo que pasa en el aula virtual, y la lista de alumnos que "
    "necesitan seguimiento, ordenada por prioridad.",
)

MATERIAS = [m for m in comp.ORDEN_MATERIAS if m in f.materias]
ORDEN = {"asignatura": MATERIAS}
SUFIJO = f"{f.fecha_corte:%Y%m%d}"
APRUEBA = ["Regular", "Promociona"]

resumen = comp.metrica("resumen_matricula")
tabla = comp.metrica("tabla_alumnos")
por_alumno = comp.metrica("alertas_por_alumno")
alertas = comp.metrica("alertas")
por_materia = resumen.set_index("asignatura").reindex(MATERIAS)


def total(col: str) -> int:
    return int(resumen[col].sum())


def corto(asignatura: str) -> str:
    return comp.NOMBRE_CORTO.get(asignatura, asignatura)


def nota_txt(df: pd.DataFrame) -> pd.Series:
    return df["nota_final"].map(lambda v: comp.num(v, 1)).astype(str) + " / " + df["escala"].astype("Int64").astype(str)


# ---------------------------------------------------------------------------
# Tarjetas
# ---------------------------------------------------------------------------
no_insc = tabla[~tabla["inscripto"]]
aprueban_sin_insc = int(no_insc["condicion"].isin(APRUEBA).sum())
altas = int((por_alumno["prioridad"] == "Alta").sum())
comp.tarjetas([
    dict(label="Inscriptos", value=comp.num(total("inscriptos")),
         delta=f"sobre {comp.num(total('base'))} de la base",
         help=f"Último estado Aceptada en Matriculados (D11). Hay además {comp.num(total('bajas'))} bajas. "
              "Un alumno que cursa dos materias cuenta dos veces."),
    dict(label="Activos", value=comp.num(total("activos")), tono_valor="bien",
         delta=f"{comp.pct(total('activos') / max(total('base'), 1) * 100, 0)} de la base",
         help=f"Alumnos de la base (inscriptos + con nota) que entraron en los últimos {f.umbral} días (D35)."),
    dict(label="Cursan sin inscripción", value=comp.num(total("no_inscriptos_cursando")), tono="atencion",
         delta=f"{comp.num(aprueban_sin_insc)} van a aprobar",
         help="Tienen notas o actividad, pero no figuran como Aceptada en Matriculados. Abajo, cuántos de "
              "ellos están Regulares o promocionan a la fecha de corte."),
    dict(label="Inscriptos sin notas", value=comp.num(total("inscriptos_sin_notas")),
         delta=f"{comp.num(total('inscriptos_sin_actividad'))} nunca entraron",
         help="Inscriptos que no rindieron ningún instrumento a la fecha de corte."),
    dict(label="Prioridad alta", value=comp.num(altas), tono="critico", delta="contactar esta semana",
         help="Inscriptos sin actividad o con dos o más alertas académicas a la vez (inactivo, Libre, entra "
              "pero no rinde) (D52)."),
])

tab_mat, tab_alertas, tab_no_insc, tab_sin_notas = st.tabs(
    ["Matrícula", "Alertas", "Cursan sin inscripción", "Inscriptos sin notas"])

# ---------------------------------------------------------------------------
# Matrícula: embudo, evolución y condición por grupo
# ---------------------------------------------------------------------------
PASOS = [("base", "con_actividad", "antes de entrar al aula"),
         ("con_actividad", "con_nota", "ya en el paso de rendir algo"),
         ("con_nota", "activos", "entre tener nota y seguir entrando")]


def embudo(asig: str, r: pd.Series) -> str:
    """Base -> entraron -> con nota -> activos, con la caída más grande marcada en rojo."""
    caidas = [(int(r[a] - r[b]), b, texto) for a, b, texto in PASOS]
    mayor, donde, texto = max(caidas)
    rojo = comp.TONOS["critico"][1]
    color = comp.COLORES_MATERIA[asig]
    filas = [
        comp.barra("Base", r["base"], r["base"], color),
        comp.barra("Entraron alguna vez", r["con_actividad"], r["base"], color,
                   color_numero=rojo if donde == "con_actividad" else None),
        comp.barra("Con al menos una nota", r["con_nota"], r["base"], color,
                   color_numero=rojo if donde == "con_nota" else None),
        comp.barra(f"Activos (últ. {f.umbral} días)", r["activos"], r["base"], comp.BIEN,
                   color_numero=comp.TONOS["bien"][1], destacada=True),
    ]
    caida = (f'<p class="num" style="margin:8px 0 0;font-size:.8rem;font-weight:500;color:{rojo}">'
             f'−{comp.num(mayor)} {texto}</p>') if mayor > 0 else ""
    return (f'<p style="margin:0 0 12px;font-size:.87rem">{comp.punto_materia(asig)}</p>'
            + "".join(filas) + caida)


def lectura_embudo() -> str:
    entraron = por_materia["con_actividad"].sum() / max(por_materia["base"].sum(), 1) * 100
    partes = []
    if entraron >= 90:
        partes.append(f"Casi todos entraron alguna vez ({comp.pct(entraron, 0)} de la base): el problema no es "
                      "el arranque, es sostener.")
    else:
        partes.append(f"Solo el {comp.pct(entraron, 0)} de la base entró alguna vez al aula.")
    if len(MATERIAS) > 1:
        sin_rendir = (por_materia["con_actividad"] - por_materia["con_nota"]).clip(lower=0)
        peor, otros = sin_rendir.idxmax(), sin_rendir.drop(sin_rendir.idxmax())
        if sin_rendir[peor] >= 10 and sin_rendir[peor] >= 1.5 * max(otros.max(), 1):
            partes.append(f"{corto(peor)} pierde gente un paso antes que las otras: {comp.num(sin_rendir[peor])} "
                          "de su base entraron pero nunca rindieron nada.")
    return " ".join(partes)


def condicion_por_grupo(sit: pd.DataFrame) -> tuple[str, float | None]:
    """HTML de las barras apiladas de condición y la diferencia (pp) de aprobados
    entre inscriptos y no inscriptos, ponderada por alumnos."""
    sit = sit[sit["condicion"].isin(["Promociona", "Regular", "Libre"])]
    html, aprob = [], {}
    for asig in MATERIAS:
        sub = sit[sit["asignatura"] == asig]
        if sub.empty:
            continue
        html.append(f'<p style="margin:10px 0 7px;font-size:.8rem;font-weight:600">{corto(asig)}</p>')
        for grupo in ["Inscriptos", "No inscriptos"]:
            g = sub[sub["grupo"] == grupo].set_index("condicion")["alumnos"]
            n = g.sum()
            if not n:
                continue
            partes = [(g.get(c, 0) / n * 100, comp.COLORES_CONDICION[c], f"{c}: {g.get(c, 0)} de {n} alumnos")
                      for c in ["Promociona", "Regular", "Libre"]]
            html.append(comp.barra_apilada(f"{grupo} ({comp.num(n)})", partes, ancho_etiqueta=118))
            a = aprob.setdefault(grupo, [0, 0])
            a[0] += g.reindex(APRUEBA).fillna(0).sum()
            a[1] += n
    if len(aprob) < 2:
        return "".join(html), None
    tasa = {k: v[0] / v[1] * 100 for k, v in aprob.items()}
    return "".join(html), tasa["Inscriptos"] - tasa["No inscriptos"]


with tab_mat:
    with comp.tarjeta("embudo"):
        comp.seccion("De la base al alumno activo",
                     "La <strong>base</strong> de cada materia son los inscriptos más los que tienen alguna nota "
                     "sin estar inscriptos. El embudo muestra dónde se pierde gente; el número en rojo es el paso "
                     "donde más alumnos se caen.")
        for col, asig in zip(st.columns(len(MATERIAS), gap="large"), MATERIAS):
            col.html(embudo(asig, por_materia.loc[asig]))
        comp.nota(lectura_embudo())

    c1, c2 = st.columns(2)
    with c1, comp.tarjeta("evolucion"):
        comp.seccion("Inscripciones vs. primer ingreso",
                     "Acumulado de inscripciones aceptadas contra alumnos que ya entraron al aula. Cuando la línea "
                     "de ingresos va por encima, hay gente cursando antes de (o sin) inscribirse.")
        evo = comp.metrica("evolucion_matricula")
        if evo.empty:
            comp.nota("A esta fecha de corte todavía no hay inscripciones ni ingresos.")
        else:
            series = {"Ya entraron al aula": comp.ATENCION, "Inscriptos": comp.CATEGORICA[3]}
            st.html(comp.leyenda(list(series.items()), "linea"))
            fig = px.line(evo, x="fecha", y="alumnos", color="serie", facet_col="asignatura",
                          category_orders=ORDEN, line_shape="hv", color_discrete_map=series,
                          labels={"fecha": "", "alumnos": "Alumnos (acumulado)", "serie": "", "asignatura": ""})
            fig.update_traces(hovertemplate="%{x|%d/%m}: %{y} alumnos<extra>%{fullData.name}</extra>",
                              line_width=2.4)
            fig.for_each_annotation(lambda a: a.update(text=corto(a.text.split("=")[-1]),
                                                       font=dict(size=12, color=comp.TEXTO)))
            fig.update_xaxes(tickformat="%d/%m", nticks=4)
            fig.update_yaxes(title_text="", nticks=4)
            fig.update_layout(height=270, showlegend=False, margin=dict(t=28, l=4, r=4, b=4))
            comp.grafico(fig)
            n = total("no_inscriptos_cursando")
            if n:
                comp.nota(f"Hoy hay <strong>{comp.num(n)} alumnos</strong> cursando sin figurar como inscriptos. "
                          "Si la inscripción se completa tarde, la brecha se ve como una línea de ingresos que "
                          "corre por encima durante semanas.", "atencion")

    with c2, comp.tarjeta("condicion"):
        comp.seccion("¿Rinden distinto los no inscriptos?",
                     "Condición a la fecha de corte de cada grupo. Si se parecen, no son alumnos perdidos: es un "
                     "problema administrativo.")
        sit = comp.metrica("situacion_academica")
        html_cond, dif = condicion_por_grupo(sit) if not sit.empty else ("", None)
        if not html_cond:
            comp.nota("A esta fecha de corte todavía no se tomó ninguna evaluación.")
        else:
            st.html(comp.leyenda([(c, comp.COLORES_CONDICION[c]) for c in ["Promociona", "Regular", "Libre"]])
                    + html_cond)
            if dif is not None:
                if abs(dif) <= 10:
                    comp.nota(f"<strong>Rinden parecido</strong> (la proporción que aprueba difiere "
                              f"{comp.num(abs(dif), 0)} puntos). Los no inscriptos no son alumnos perdidos: son un "
                              "problema administrativo a regularizar antes del cierre de actas.", "bien")
                else:
                    peor = "los no inscriptos" if dif > 0 else "los inscriptos"
                    comp.nota(f"<strong>Hay diferencia:</strong> entre {peor} aprueban {comp.num(abs(dif), 0)} "
                              "puntos menos. Igual conviene regularizar a los que van aprobando.", "atencion")

    with comp.tarjeta("tabla_matricula"):
        t1, t2 = st.columns([3, 1], vertical_alignment="center")
        with t1:
            comp.seccion("Matrícula por materia")
        tabla_res = resumen.set_index("asignatura").reindex(MATERIAS).reset_index()
        with t2:
            comp.boton_csv(tabla_res, f"resumen_matricula_{SUFIJO}")
        st.dataframe(
            comp.estilo_tabla(tabla_res, materias=["asignatura"],
                              color_columnas={"no_inscriptos_cursando": comp.TONOS["atencion"][1]}),
            hide_index=True, width="stretch", column_config={
                "asignatura": "Materia", "base": "Base", "inscriptos": "Inscriptos", "bajas": "Bajas",
                "con_actividad": "Entraron", "activos": "Activos", "con_nota": "Con nota",
                "no_inscriptos_cursando": "Sin inscripción", "inscriptos_sin_actividad": "Insc. sin actividad",
                "inscriptos_sin_notas": "Insc. sin notas"})

# ---------------------------------------------------------------------------
# Alertas: tarjetas por prioridad, conteo por tipo y lista priorizada
# ---------------------------------------------------------------------------
PRIORIDADES = {
    "Alta": ("critico", "Acumulan dos o más señales de abandono, o están inscriptos sin aparecer. "
                        "Contactar esta semana."),
    "Media": ("atencion", "Una sola señal: inactivo, Libre o no rinde. Seguir de cerca."),
    "Administrativa": ("info", "Cursan bien pero sin inscripción. Derivar a secretaría, no al docente."),
}


def lectura_tipos(cuenta: pd.DataFrame) -> str:
    """El tipo de alerta más concentrado en una sola materia (si lo hay)."""
    if len(MATERIAS) < 2:
        return ""
    tot = cuenta.groupby("alerta")["alumnos"].sum()
    top = cuenta.loc[cuenta.groupby("alerta")["alumnos"].idxmax()].set_index("alerta")
    top["share"] = top["alumnos"] / tot
    top = top[tot.reindex(top.index) >= 10].sort_values("share", ascending=False)
    if top.empty or top["share"].iloc[0] < 0.5:
        return ""
    alerta, fila = top.index[0], top.iloc[0]
    return (f"“{alerta}” está concentrada en {corto(fila['asignatura'])}: {comp.num(fila['alumnos'])} de "
            f"{comp.num(tot[alerta])}. Es un problema de esa materia, no de toda la cohorte.")


with tab_alertas:
    if por_alumno.empty:
        comp.nota("No hay alumnos con alertas a esta fecha de corte.", "bien", icono=True)
    else:
        conteo = por_alumno["prioridad"].value_counts()
        comp.avisos([comp.aviso(f"Prioridad {p.lower()}" if p != "Administrativa" else p,
                                comp.num(int(conteo.get(p, 0))), texto, tono)
                     for p, (tono, texto) in PRIORIDADES.items()])

        with comp.tarjeta("tipos"):
            comp.seccion("Alertas por tipo",
                         "Un alumno puede tener varias. Inactivo depende del umbral de la barra lateral; "
                         "“Condición Libre” no se repite para quien ya figura como inscripto sin actividad.")
            cuenta = alertas.groupby(["asignatura", "alerta"]).size().rename("alumnos").reset_index()
            cuenta["pct"] = cuenta["alumnos"] / cuenta["asignatura"].map(resumen.set_index("asignatura")["base"]) * 100
            orden_tipos = cuenta.groupby("alerta")["alumnos"].sum().sort_values(ascending=False).index.tolist()
            fig = px.bar(cuenta, x="alumnos", y="alerta", color="asignatura", barmode="group", orientation="h",
                         text="alumnos", custom_data=["pct"],
                         category_orders={**ORDEN, "alerta": orden_tipos},
                         color_discrete_map=comp.COLORES_MATERIA,
                         labels={"alumnos": "Alumnos", "alerta": "", "asignatura": ""})
            fig.update_traces(textposition="outside", cliponaxis=False, textfont_size=11,
                              hovertemplate="%{y}<br>%{fullData.name}: %{x} alumnos (%{customdata[0]:.1f} % de la "
                                            "base)<extra></extra>")
            fig.for_each_trace(lambda t: t.update(name=corto(t.name)))
            fig.update_xaxes(showgrid=False, showticklabels=False, title_text="")
            # Dentro de cada tipo, ALG arriba y AED abajo (como la leyenda): en barras horizontales
            # plotly apila los grupos de abajo hacia arriba, así que se invierten las trazas.
            fig.data = fig.data[::-1]
            fig.update_layout(height=70 + 15 * len(orden_tipos) * len(MATERIAS) + 22 * len(orden_tipos),
                              bargap=0.28, bargroupgap=0.06, legend_traceorder="reversed",
                              margin=dict(t=30, l=4, r=24, b=4))
            comp.grafico(fig)
            lectura = lectura_tipos(cuenta)
            if lectura:
                comp.nota(lectura)

        with comp.tarjeta("lista_alertas"):
            comp.seccion("A quién contactar primero")
            c1, c2, c3 = st.columns([1.3, 2, 1.4], vertical_alignment="bottom")
            prioridades = c1.pills("Prioridad", list(PRIORIDADES), selection_mode="multi",
                                   default=["Alta", "Media"], key="alertas_prioridad")
            tipos = c2.multiselect("Tipo de alerta", list(TIPOS_ALERTA), format_func=TIPOS_ALERTA.get,
                                   key="alertas_tipo", placeholder="Todas")
            texto = c3.text_input("Buscar alumno", key="alertas_buscar", placeholder="Apellido, nombre o ID")

            vista = por_alumno[por_alumno["prioridad"].isin(prioridades or list(PRIORIDADES))]
            if tipos:
                vista = vista[vista["tipos"].map(lambda ts: bool(set(tipos) & set(ts)))]
            if texto.strip():
                buscado = vista["nombre_completo"].fillna("") + " " + vista["id_alumno"]
                vista = vista[buscado.str.contains(texto.strip(), case=False, regex=False)]
            st.html(f'<p class="tfi-pie num" style="margin:-4px 0 6px">{comp.num(len(vista))} de '
                    f'{comp.num(len(por_alumno))} alumnos con alguna alerta</p>')

            mostrar = pd.DataFrame({
                "Prioridad": comp.con_forma(vista["prioridad"].astype(str)),
                "Alumno": vista["nombre_completo"].fillna("—"),
                "ID": vista["id_alumno"],
                "Materia": vista["asignatura"].map(comp.SIGLAS),
                "Por qué": vista["alertas"],
                "Condición": comp.con_forma(vista["condicion"]),
                "Nota": nota_txt(vista),
                "Sin entrar": vista["dias_sin_actividad"].map(comp.fmt_dias),
                "Avance": vista["avance"],
            }, index=vista.index)
            if f.asignatura:
                mostrar = mostrar.drop(columns="Materia")
            st.dataframe(comp.estilo_tabla(mostrar, estados=["Prioridad", "Condición"], materias=["Materia"]),
                         hide_index=True, width="stretch", height=420, column_config={
                             "Avance": st.column_config.ProgressColumn(
                                 "Avance", format="%d %%", min_value=0, max_value=100,
                                 help="Avance en el aula según el reporte de participación (foto al 24/10, D36)."),
                             "Por qué": st.column_config.TextColumn(width="medium")})
            comp.pie("<strong>Prioridad:</strong> alta = inscripto sin actividad, o dos o más alertas académicas "
                     "juntas · media = una sola · administrativa = solo cursa sin inscripción.")
            b1, b2, _ = st.columns([1, 1.4, 1.6])
            with b1:
                comp.boton_csv(vista.drop(columns=["tipos"]), f"alertas_por_alumno_{SUFIJO}", "Descargar lista")
            with b2:
                comp.boton_csv(alertas.drop(columns="tipo"), f"alertas_detalle_{SUFIJO}",
                               "Descargar todas (una fila por alerta)")

# ---------------------------------------------------------------------------
# No inscriptos cursando
# ---------------------------------------------------------------------------
with tab_no_insc:
    comp.nota("Alumnos con notas o actividad en la materia que <strong>no figuran como Aceptada en "
              "Matriculados</strong>: nunca se inscribieron, o su último movimiento es una baja. <strong>Si "
              "aprueban, no van a poder figurar en el acta.</strong> Conviene derivarlos a secretaría antes del "
              "cierre.", "atencion", icono=True)
    if no_insc.empty:
        comp.nota("Todos los alumnos que cursan están inscriptos.", "bien", icono=True)
    else:
        comp.tarjetas([
            dict(label="Cursan sin inscripción", value=comp.num(len(no_insc)),
                 delta=f"{comp.pct(len(no_insc) / max(total('base'), 1) * 100, 0)} de la base"),
            dict(label="No están en Matriculados", value=comp.num(int((~no_insc["en_matriculados"]).sum())),
                 delta="nunca se inscribieron"),
            dict(label="Con baja", value=comp.num(int(no_insc["estado"].eq("Baja").sum())),
                 delta="se dieron de baja y siguen"),
            dict(label="Regularizan o promocionan", value=comp.num(aprueban_sin_insc), tono="bien",
                 delta="aprueban y no pueden figurar"),
        ])

        with comp.tarjeta("secretaria"):
            t1, t2, t3 = st.columns([2, 1.3, 1], vertical_alignment="bottom")
            with t1:
                comp.seccion("Lista para secretaría")
            orden = t2.selectbox("Mostrar", ["Primero los que aprueban", "Todos", "Solo con baja"],
                                 key="no_insc_orden", label_visibility="collapsed")
            lista = no_insc.assign(aprueba=no_insc["condicion"].isin(APRUEBA))
            if orden == "Primero los que aprueban":
                lista = lista.sort_values(["aprueba", "nota_final"], ascending=[False, False])
            elif orden == "Solo con baja":
                lista = lista[lista["estado"].eq("Baja")]
            mostrar = pd.DataFrame({
                "Alumno": lista["nombre_completo"].fillna("—"),
                "ID": lista["id_alumno"],
                "Materia": lista["asignatura"].map(comp.SIGLAS),
                "Condición": comp.con_forma(lista["condicion"]),
                "Nota": nota_txt(lista),
                "Rindió": lista["rendidos"].astype(str) + " de " + lista["instrumentos"].astype(str),
                "Actividad": comp.con_forma(lista["estado_actividad"]),
                "Último ingreso": lista["ultima_interaccion"].map(comp.fmt_fecha),
                "Estado en Matriculados": lista["estado"].where(lista["en_matriculados"], "No figura").fillna("No figura"),
            }, index=lista.index)
            if f.asignatura:
                mostrar = mostrar.drop(columns="Materia")
            with t3:
                comp.boton_csv(mostrar, f"no_inscriptos_cursando_{SUFIJO}", "Descargar lista")
            if mostrar.empty:
                comp.nota("Nadie en este grupo.")
            else:
                st.dataframe(comp.estilo_tabla(mostrar, estados=["Condición", "Actividad", "Estado en Matriculados"],
                                               materias=["Materia"], resaltar=lista["aprueba"]),
                             hide_index=True, width="stretch", height=400)
            comp.pie("Las filas resaltadas son las urgentes: aprueban la materia (Regular o Promociona) y no "
                     "figuran en el acta.")

# ---------------------------------------------------------------------------
# Inscriptos sin notas
# ---------------------------------------------------------------------------
with tab_sin_notas:
    sin_notas = tabla[tabla["inscripto"] & (tabla["rendidos"] == 0)]
    sin_notas = sin_notas.assign(nunca=sin_notas["eventos"].fillna(0).eq(0)) \
                         .sort_values(["nunca", "eventos"], ascending=[False, False])
    st.html('<p class="tfi-desc" style="margin:4px 0 2px">Inscriptos que <strong>no rindieron ningún '
            'instrumento</strong> a la fecha de corte: todo cuenta 0, así que están Libres. Se separan en dos '
            'grupos porque piden acciones distintas.</p>')
    nunca, entra = int(sin_notas["nunca"].sum()), int((~sin_notas["nunca"]).sum())
    comp.avisos([
        comp.aviso("Nunca entraron", comp.num(nunca),
                   "Se inscribieron y nunca abrieron el aula. Son pocos y muy accionables: un mail o una llamada "
                   "antes de que venza el plazo de baja.", "neutro"),
        comp.aviso("Entran pero no rinden", comp.num(entra),
                   "Usan el aula y no se presentan a nada. Antes de darlos por perdidos, conviene descartar un "
                   "problema de acceso a las evaluaciones.", "atencion"),
    ])

    with comp.tarjeta("sin_notas"):
        t1, t2 = st.columns([3, 1], vertical_alignment="center")
        grupo = t1.segmented_control("Mostrar", ["Todos", "Nunca entraron", "Entran pero no rinden"],
                                     default="Todos", key="sin_notas_grupo", label_visibility="collapsed")
        if grupo == "Nunca entraron":
            sin_notas = sin_notas[sin_notas["nunca"]]
        elif grupo == "Entran pero no rinden":
            sin_notas = sin_notas[~sin_notas["nunca"]]
        mostrar = pd.DataFrame({
            "Alumno": sin_notas["nombre_completo"].fillna("—"),
            "ID": sin_notas["id_alumno"],
            "Materia": sin_notas["asignatura"].map(comp.SIGLAS),
            "Situación": comp.con_forma(sin_notas["nunca"].map({True: "Nunca entró", False: "Entra, no rinde"})),
            "Rindió": "0 de " + sin_notas["instrumentos"].astype(str),
            "Interacciones": sin_notas["eventos"].fillna(0).astype(int),
            "Último ingreso": sin_notas["ultima_interaccion"].map(comp.fmt_fecha),
        }, index=sin_notas.index)
        if f.asignatura:
            mostrar = mostrar.drop(columns="Materia")
        with t2:
            comp.boton_csv(mostrar, f"inscriptos_sin_notas_{SUFIJO}", "Descargar lista")
        if mostrar.empty:
            comp.nota("Todos los inscriptos rindieron al menos un instrumento.", "bien", icono=True)
        else:
            st.dataframe(comp.estilo_tabla(mostrar, estados=["Situación"], materias=["Materia"]),
                         hide_index=True, width="stretch", height=400)
            entran = sin_notas[~sin_notas["nunca"]]
            if not entran.empty:
                top = entran.iloc[0]
                comp.pie(f"{comp.esc(top['nombre_completo'])} tiene {comp.num(top['eventos'])} interacciones y "
                         "ninguna evaluación rendida: es el tipo de caso que más vale revisar, porque no parece "
                         "desinterés.")
