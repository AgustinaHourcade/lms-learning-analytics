"""Dashboard 7: Matrícula y alertas (rediseño D88-D89).

Responde, a la fecha de corte: ¿cuántos de los inscriptos están cursando de verdad?,
¿quién cursa sin estar inscripto?, ¿quién se inscribió y no aparece? y ¿a quién
conviene contactar primero?

Las cifras son CASOS (alumno × materia): un alumno que cursa dos materias cuenta dos
veces. Donde suma, se agrega cuántos alumnos distintos hay detrás.

  Tarjetas        inscriptos, inscriptos activos (Δ 7 días), cursan sin inscripción,
                  inscriptos sin notas y prioridad alta (Δ 7 días).
  Matrícula       matriz inscripción × actividad por materia, condición de inscriptos
                  vs. no inscriptos (por materia y total), tabla por materia y
                  evolución de inscripciones vs. primer ingreso.
  Alertas         tarjetas por prioridad, tabla materia × prioridad, alertas por tipo
                  y la lista priorizada (D89) con riesgo de abandono y paso a la Ficha.
  No inscriptos   quiénes cursan sin estar en Matriculados (para la secretaría).
  Sin notas       inscriptos que no rindieron nada: nunca entraron o entran y no rinden.

Los títulos y las notas de lectura se arman con los datos de la fecha de corte
(src.textos), no son texto fijo. Todo sale de src.metricas / src.ml_abandono vía
comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes_matricula as comp   # sistema visual propio de esta página (ver el módulo)
from src import textos
from src.config import DIAS_PRIORIDAD_ALTA
from src.metricas import ACTIVIDAD_MATRIZ, MATRICULA, TIPOS_ALERTA, TOTAL

FICHA = "paginas/6_ficha_individual.py"

f = comp.encabezado("Matrícula y alertas", "Inscripción formal vs. actividad real, y a quién contactar primero.")

MATERIAS = [m for m in comp.ORDEN_MATERIAS if m in f.materias]
ORDEN = {"asignatura": MATERIAS}
SUFIJO = f"{f.fecha_corte:%Y%m%d}"
APRUEBA = ["Regular", "Promociona"]
CONDICIONES = ["Promociona", "Regular", "Libre"]
BASE_TXT = ("La base de cada materia son los inscriptos (último estado Aceptada en Matriculados) más quienes "
            "tienen alguna nota cargada sin estar inscriptos. La actividad en el aula sola no alcanza para entrar.")
NOTA_TXT = ("Nota proyectada = puntos obtenidos / puntos posibles de los instrumentos ya tomados a la fecha de "
            "corte × escala (100; Álgebra 120). Lo no rendido cuenta 0. Es la nota que tendría si sigue al mismo "
            "ritmo.")

k = comp.metrica("tarjetas_matricula")
resumen = comp.metrica("resumen_matricula")
tabla = comp.metrica("tabla_alumnos")
por_alumno = comp.metrica("alertas_priorizadas")
alertas = comp.metrica("alertas")
fecha_reporte = comp.metrica("fecha_reporte_participacion")


def corto(asignatura: str) -> str:
    return comp.NOMBRE_CORTO.get(asignatura, asignatura)


def nota_txt(df: pd.DataFrame) -> pd.Series:
    return df["nota_final"].map(lambda v: comp.num(v, 1)).astype(str) + " / " + df["escala"].astype("Int64").astype(str)


def cambio(ahora: int, antes: int) -> str:
    dif = ahora - antes
    return "igual que hace 7 días" if dif == 0 else f"{'▲' if dif > 0 else '▼'} {comp.num(abs(dif))} vs. hace 7 días"


def casos(n: int) -> str:
    return f"{comp.num(n)} caso{'s' if n != 1 else ''}"


# ---------------------------------------------------------------------------
# Tarjetas (casos = alumno × materia; cierran con la tabla "Matrícula por materia")
# ---------------------------------------------------------------------------
comp.tarjetas([
    dict(label="Inscriptos", value=comp.num(k["inscriptos"]),
         delta=f"de {casos(k['base'])} de la base · {comp.num(k['base_unicos'])} alumnos",
         help=f"Último estado Aceptada en Matriculados. Hay además {comp.num(k['bajas'])} bajas. Cada alumno cuenta "
              f"una vez por materia (caso). {BASE_TXT}"),
    dict(label="Inscriptos activos", value=comp.num(k["inscriptos_activos"]), tono_valor="bien",
         delta=f"{comp.pct(k['inscriptos_activos'] / max(k['inscriptos'], 1) * 100, 0)} de "
               f"{comp.num(k['inscriptos'])} · {cambio(k['inscriptos_activos'], k['inscriptos_activos_antes'])}",
         help=f"Inscriptos que entraron al aula en los últimos {f.umbral} días, sobre el total de inscriptos. "
              "El cambio es contra la misma cuenta 7 días antes de la fecha de corte."),
    dict(label="Cursan sin inscripción", value=comp.num(k["no_inscriptos_cursando"]), tono="atencion",
         delta=f"{comp.num(k['aprueban_sin_inscripcion'])} aprobarían al ritmo actual",
         help="Tienen alguna nota cargada pero no figuran como Aceptada en Matriculados. Abajo, cuántos están "
              f"Regulares o promocionan con la nota proyectada. {NOTA_TXT}"),
    dict(label="Inscriptos sin notas", value=comp.num(k["inscriptos_sin_notas"]),
         delta=f"{comp.pct(k['inscriptos_sin_notas'] / max(k['inscriptos'], 1) * 100, 0)} de "
               f"{comp.num(k['inscriptos'])} · {comp.num(k['inscriptos_sin_actividad'])} nunca entraron",
         help="Inscriptos que no rindieron ningún instrumento a la fecha de corte, en materias que ya tomaron "
              "alguno."),
    dict(label="Prioridad alta", value=comp.num(k["alta"]), tono="critico",
         delta=f"{comp.num(k['alta_unicos'])} alumnos distintos · {cambio(k['alta'], k['alta_antes'])}",
         help=f"Casos inscriptos sin actividad, o inscriptos Libres que no entran hace {DIAS_PRIORIDAD_ALTA} días o "
              f"más. Son {comp.pct(k['alta'] / max(k['base'], 1) * 100, 0)} de la base."),
])

tab_mat, tab_alertas, tab_no_insc, tab_sin_notas = st.tabs(
    ["Matrícula", "Alertas", "Cursan sin inscripción", "Inscriptos sin notas"])

# ---------------------------------------------------------------------------
# Matrícula: matriz, condición por grupo, tabla y evolución
# ---------------------------------------------------------------------------
COLUMNAS_MATRIZ = {"Activo": f"Activo<br>(≤ {f.umbral} días)", "Inactivo": "Inactivo", "Nunca entró": "Nunca<br>entró"}


def matriz(m: pd.DataFrame, asig: str, zmax: int) -> go.Figure:
    """Mapa de calor chico de una materia. Las tres usan los mismos ejes y la misma escala
    (zmax común); van en columnas, así en el celular se apilan en vez de aplastarse."""
    escala = [[i / (len(comp.SECUENCIAL) - 1), c] for i, c in enumerate(comp.SECUENCIAL)]
    sub = m[m["asignatura"] == asig].set_index(["matricula", "actividad"])
    z = [[int(sub.loc[(fila, col), "casos"]) for col in ACTIVIDAD_MATRIZ] for fila in MATRICULA]
    p = [[sub.loc[(fila, col), "pct_base"] for col in ACTIVIDAD_MATRIZ] for fila in MATRICULA]
    texto = [[f"<b>{comp.num(z[r][c])}</b><br><span style='font-size:11px'>{comp.pct(p[r][c], 0)}</span>"
              for c in range(len(ACTIVIDAD_MATRIZ))] for r in range(len(MATRICULA))]
    fig = go.Figure(go.Heatmap(
        z=z, x=[COLUMNAS_MATRIZ[c] for c in ACTIVIDAD_MATRIZ], y=[f.replace(" ", "<br>") for f in MATRICULA],
        text=texto, texttemplate="%{text}", textfont=dict(size=15), zmin=0, zmax=zmax, colorscale=escala,
        showscale=False, xgap=3, ygap=3, customdata=p,
        hovertemplate=f"{corto(asig)} · %{{y}} · %{{x}}<br>%{{z}} casos "
                      "(%{customdata:.1f} % de la base de la materia)<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=11))
    fig.update_xaxes(showgrid=False, side="bottom", tickfont=dict(size=11))
    fig.update_layout(title=dict(text=f"{corto(asig)} ({comp.SIGLAS[asig]})", x=0.5, xanchor="center",
                                 font=dict(size=12, color=comp.TEXTO)),
                      height=250, margin=dict(t=30, l=4, r=4, b=4))
    return fig


def condicion_por_grupo(sit: pd.DataFrame) -> str:
    """HTML de las barras apiladas de condición (inscriptos vs. no inscriptos) por materia y total."""
    filas = MATERIAS + ([TOTAL] if len(MATERIAS) > 1 else [])
    html = []
    for asig in filas:
        sub = sit[sit["asignatura"] == asig]
        if sub.empty:
            continue
        nombre = "Total (situación general)" if asig == TOTAL else corto(asig)
        html.append(f'<p style="margin:10px 0 7px;font-size:.8rem;font-weight:600">{nombre}</p>')
        for grupo in ["Inscriptos", "No inscriptos"]:
            g = sub[sub["grupo"] == grupo].set_index("condicion")
            n = int(g["alumnos"].sum())
            if not n:
                html.append(f'<div class="ma-fila" style="--ancho-etiqueta:118px"><span class="e" '
                            f'style="font-size:.74rem">{grupo} (0)</span><span class="ma-pie">sin casos</span></div>')
                continue
            partes = [(g["pct"].get(c, 0), comp.COLORES_CONDICION[c],
                       f"{c}: {comp.num(g['alumnos'].get(c, 0))} de {comp.num(n)} casos "
                       f"({comp.pct(g['pct'].get(c, 0), 0)})") for c in CONDICIONES]
            html.append(comp.barra_apilada(f"{grupo} ({comp.num(n)})", partes, ancho_etiqueta=118))
    return "".join(html)


with tab_mat:
    mz = comp.metrica("matriz_matricula")
    with comp.tarjeta("matriz"):
        comp.seccion(textos.titulo_matriz(k["pct_entraron"], k["pct_activos"]),
                     f"Casos por materia según inscripción y actividad. Número grande: casos; chico: % de la base "
                     f"de la materia. {BASE_TXT}")
        if k["base"] == 0:
            comp.nota("No hay casos en la base a esta fecha de corte.")
        else:
            zmax = max(int(mz["casos"].max()), 1)
            for col, asig in zip(st.columns(len(MATERIAS), gap="small"), MATERIAS):
                with col:
                    comp.grafico(matriz(mz, asig, zmax), key=f"matriz_{comp.SIGLAS[asig]}")

    with comp.tarjeta("condicion"):
        comp.seccion("¿Rinden distinto los no inscriptos?",
                     "Condición proyectada a la fecha de corte, solo casos que rindieron algo.")
        sit = comp.metrica("situacion_academica")
        dif = comp.metrica("diferencia_aprobacion").set_index("asignatura")
        if sit.empty:
            comp.nota("A esta fecha de corte nadie rindió todavía ninguna evaluación.")
        else:
            st.html(comp.leyenda([(c, comp.COLORES_CONDICION[c]) for c in CONDICIONES]) + condicion_por_grupo(sit))
            filas = [(corto(a), dif.loc[a, "diferencia_pp"]) for a in MATERIAS]
            sin_datos = [corto(a) for a in MATERIAS if pd.isna(dif.loc[a, "diferencia_pp"])]
            lectura = textos.lectura_diferencia(filas, sin_datos)
            if lectura:
                comp.nota(lectura)

    with comp.tarjeta("tabla_matricula"):
        t1, t2 = st.columns([3, 1], vertical_alignment="center")
        with t1:
            comp.seccion("Matrícula por materia", "Casos (alumno × materia). Los totales son las tarjetas de arriba.")
        tabla_res = resumen.set_index("asignatura").reindex(MATERIAS).reset_index()
        tabla_res.insert(1, "sigla", tabla_res["asignatura"].map(comp.SIGLAS))
        with comp.a_la_derecha(t2):
            comp.boton_csv(tabla_res, f"resumen_matricula_{SUFIJO}")
        vista_res = tabla_res[["sigla", "base", "inscriptos", "bajas", "con_actividad", "activos",
                               "inscriptos_activos", "con_nota", "no_inscriptos_cursando", "inscriptos_sin_actividad",
                               "inscriptos_sin_notas", "pct_insc_sin_notas"]]
        st.dataframe(
            comp.estilo_tabla(vista_res, materias=["sigla"],
                              color_columnas={"no_inscriptos_cursando": comp.TONOS["atencion"][1]}),
            hide_index=True, width="stretch", column_config={
                "sigla": "Materia", "base": st.column_config.NumberColumn("Base", help=BASE_TXT),
                "inscriptos": "Inscriptos", "bajas": "Bajas",
                "con_actividad": st.column_config.NumberColumn("Entraron", help="Entraron al aula alguna vez."),
                "activos": st.column_config.NumberColumn(
                    "Activos", help=f"Casos de toda la base que entraron en los últimos {f.umbral} días."),
                "inscriptos_activos": st.column_config.NumberColumn(
                    "Insc. activos", help=f"Inscriptos que entraron en los últimos {f.umbral} días."),
                "con_nota": st.column_config.NumberColumn("Con nota", help="Rindieron al menos un instrumento."),
                "no_inscriptos_cursando": "Sin inscripción",
                "inscriptos_sin_actividad": st.column_config.NumberColumn(
                    "Insc. sin actividad", help="Inscriptos sin interacciones ni notas."),
                "inscriptos_sin_notas": "Insc. sin notas",
                "pct_insc_sin_notas": st.column_config.NumberColumn(
                    "% insc. sin notas", format="%.0f %%", help="Inscriptos sin notas / inscriptos de la materia.")})

    with comp.tarjeta("evolucion"):
        h = comp.metrica("hitos_matricula")
        comp.seccion(textos.titulo_evolucion(comp.fmt_fecha(h["aula_llena"])[:5] if h else None,
                                             h.get("pct_lleno", 90), h.get("inscripciones_despues", 0),
                                             h.get("inscriptos", 0),
                                             comp.fmt_fecha(h["ultima_inscripcion"])[:5] if h else None),
                     "Acumulado por fecha. Línea oscura arriba = gente cursando sin inscripción.")
        evo = comp.metrica("evolucion_matricula")
        if evo.empty:
            comp.nota("A esta fecha de corte todavía no hay inscripciones ni ingresos.")
        else:
            series = {"Ya entraron al aula": comp.LINEA_INGRESOS, "Inscriptos": comp.LINEA_INSCRIPTOS}
            st.html(comp.leyenda(list(series.items()), "linea"))
            fig = px.line(evo, x="fecha", y="alumnos", color="serie", facet_col="asignatura",
                          category_orders=ORDEN, line_shape="hv", color_discrete_map=series,
                          labels={"fecha": "", "alumnos": "Casos acumulados", "serie": "", "asignatura": ""})
            fig.update_traces(hovertemplate="%{x|%d/%m}: %{y} casos<extra>%{fullData.name}</extra>", line_width=2.4)
            fig.for_each_annotation(lambda a: a.update(text=corto(a.text.split("=")[-1]),
                                                       font=dict(size=12, color=comp.TEXTO)))
            fig.update_xaxes(tickformat="%d/%m", nticks=4)
            fig.update_yaxes(title_text="", nticks=4)
            fig.update_yaxes(title_text="Casos acumulados", col=1)
            fig.update_layout(height=280, showlegend=False, margin=dict(t=28, l=4, r=4, b=4))
            comp.grafico(fig)

# ---------------------------------------------------------------------------
# Alertas: prioridades, materia × prioridad, por tipo y lista priorizada
# ---------------------------------------------------------------------------
PRIORIDADES = {
    "Alta": ("critico", f"Libre y {DIAS_PRIORIDAD_ALTA}+ días sin entrar, o inscripto sin actividad."),
    "Media": ("atencion", "Inactivo, Libre o no rinde, sin llegar a Alta."),
    "Administrativa": ("info", "Solo falta la inscripción → secretaría."),
}
AYUDA_PRIORIDAD = (f"Alta = inscripto sin actividad, o inscripto Libre que no entra hace {DIAS_PRIORIDAD_ALTA} días o "
                   "más. Media = alguna otra alerta académica (inactivo, Libre, entra pero no rinde). "
                   "Administrativa = solo cursa sin inscripción.")


def ir_a_ficha(id_alumno: str, asignatura: str) -> None:
    """Deja elegidos el alumno y la materia para la Ficha individual (corre antes de los widgets)."""
    st.session_state["materia"] = asignatura
    st.session_state["fi_alumno"] = id_alumno
    st.session_state.pop("fi_grupo", None)
    st.session_state["ma_ir_a_ficha"] = True


with tab_alertas:
    if por_alumno.empty:
        comp.nota("No hay casos con alertas a esta fecha de corte.", "bien", icono=True)
    else:
        conteo = por_alumno["prioridad"].value_counts()
        comp.avisos([comp.aviso(f"Prioridad {p.lower()}" if p != "Administrativa" else p,
                                comp.num(int(conteo.get(p, 0))), texto, tono)
                     for p, (tono, texto) in PRIORIDADES.items()])

        with comp.tarjeta("por_materia"):
            comp.seccion("Casos por materia y prioridad", "Entre paréntesis, la base de la materia.")
            pm = comp.metrica("alertas_por_materia")
            pm = pm[pm["asignatura"].isin(MATERIAS + ([TOTAL] if len(MATERIAS) > 1 else []))]
            vista_pm = pd.DataFrame({
                "Materia": pm["asignatura"].map(lambda a: a if a == TOTAL else comp.SIGLAS[a])
                           + " (" + pm["base"].map(comp.num) + ")",
                **{f"{comp.ICONOS_PRIORIDAD[p]} {p}": pm[p] for p in PRIORIDADES}})
            st.dataframe(comp.estilo_tabla(vista_pm, color_columnas={
                f"{comp.ICONOS_PRIORIDAD[p]} {p}": comp.TONOS[t][1] for p, (t, _) in PRIORIDADES.items()}),
                hide_index=True, width="stretch")

        with comp.tarjeta("tipos"):
            cuenta = comp.metrica("alertas_por_tipo")
            comp.seccion(textos.titulo_alertas_tipo(
                [(corto(r.asignatura), r.tipo, r.casos, r.pct, r.parte_del_tipo) for r in cuenta.itertuples()]),
                "Un alumno puede tener varias.")
            orden_tipos = cuenta.groupby("alerta")["casos"].sum().sort_values(ascending=False).index.tolist()
            cuenta = cuenta.assign(sobre_txt=cuenta["sobre"].map({"base": "de la base", "inscriptos": "de los inscriptos"}))
            fig = px.bar(cuenta, x="casos", y="alerta", color="asignatura", barmode="group", orientation="h",
                         text="casos", custom_data=["pct", "sobre_txt"],
                         category_orders={**ORDEN, "alerta": orden_tipos},
                         color_discrete_map=comp.COLORES_MATERIA,
                         labels={"casos": "Casos", "alerta": "", "asignatura": ""})
            fig.update_traces(textposition="outside", cliponaxis=False, textfont_size=11,
                              hovertemplate="%{y}<br>%{fullData.name}: %{x} casos (%{customdata[0]:.0f} % "
                                            "%{customdata[1]})<extra></extra>")
            fig.for_each_trace(lambda t: t.update(name=corto(t.name)))
            fig.update_xaxes(showgrid=False, showticklabels=False, title_text="")
            # Dentro de cada tipo, ALG arriba y AED abajo (como la leyenda): en barras horizontales
            # plotly apila los grupos de abajo hacia arriba, así que se invierten las trazas.
            fig.data = fig.data[::-1]
            fig.update_layout(height=70 + 15 * len(orden_tipos) * len(MATERIAS) + 22 * len(orden_tipos),
                              bargap=0.28, bargroupgap=0.06, legend_traceorder="reversed",
                              margin=dict(t=30, l=4, r=24, b=4))
            comp.grafico(fig)

        with comp.tarjeta("lista_alertas"):
            comp.seccion("A quién contactar primero",
                         "Orden: prioridad, cantidad de alertas y riesgo de abandono. Elegí una fila para ver su ficha.")
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
            st.html(f'<p class="ma-pie num" style="margin:-4px 0 6px">{comp.num(len(vista))} de '
                    f'{casos(len(por_alumno))} con alguna alerta · {comp.num(vista["id_alumno"].nunique())} de '
                    f'{comp.num(k["alertas_unicos"])} alumnos distintos</p>')

            avance = f"Avance (al {comp.fmt_fecha(fecha_reporte)[:5]})" if fecha_reporte is not None else "Avance"
            mostrar = pd.DataFrame({
                "Prioridad": comp.con_forma(vista["prioridad"].astype(str)),
                "Alumno": vista["nombre_completo"].fillna("—"),
                "ID": vista["id_alumno"],
                "Materia": vista["asignatura"].map(comp.SIGLAS),
                "Por qué": vista["motivos"],
                "Riesgo": vista["probabilidad"],
                "Condición": comp.con_forma(vista["condicion"]),
                "Nota proyectada": nota_txt(vista),
                "Sin entrar": vista["dias_sin_actividad"].map(comp.fmt_dias),
                avance: vista["avance"],
            }, index=vista.index)
            if f.asignatura:
                mostrar = mostrar.drop(columns="Materia")
            seleccion = st.dataframe(
                comp.estilo_tabla(mostrar, estados=["Prioridad", "Condición"], materias=["Materia"]),
                hide_index=True, width="stretch", height=420, key="alertas_lista",
                on_select="rerun", selection_mode="single-row", column_config={
                    "Prioridad": st.column_config.TextColumn("Prioridad", help=AYUDA_PRIORIDAD),
                    "Por qué": st.column_config.TextColumn(
                        "Por qué", width="medium", help="Sin insc. = cursa sin inscripción · Sin actividad = inscripto que nunca "
                                        "entró · No rinde = entra y no rindió nada · Inactivo · Libre. El detalle, "
                                        "en el CSV."),
                    "Riesgo": st.column_config.NumberColumn(
                        "Riesgo", format="%.0f %%",
                        help="Probabilidad de abandonar la materia (no volver a entrar ni rendir nada más) según el "
                             "predictor de abandono, a la fecha de corte. Vacío si nunca entró."),
                    "Nota proyectada": st.column_config.TextColumn("Nota proyectada", help=NOTA_TXT),
                    avance: st.column_config.ProgressColumn(
                        avance, format="%d %%", min_value=0, max_value=100,
                        help="Avance en el aula según el reporte de participación del LMS: es una foto a esa "
                             "fecha, no se recorta por la fecha de corte.")})
            filas = seleccion.selection.rows if seleccion is not None else []
            b1, b2 = st.columns([1, 1.5], vertical_alignment="center")
            with b1:
                if filas:
                    fila = vista.iloc[filas[0]]
                    nombre = fila["nombre_completo"] if isinstance(fila["nombre_completo"], str) else fila["id_alumno"]
                    st.button(f"Ver ficha de {nombre} ({comp.SIGLAS[fila['asignatura']]})",
                              icon=":material/person_search:", key="alertas_ver_ficha", type="primary",
                              on_click=ir_a_ficha, args=(fila["id_alumno"], fila["asignatura"]))
                else:
                    st.button("Ver ficha", icon=":material/person_search:", key="alertas_ver_ficha", disabled=True,
                              help="Elegí una fila de la lista.")
            with comp.a_la_derecha(b2):
                comp.boton_csv(vista.drop(columns=["tipos"]), f"alertas_por_alumno_{SUFIJO}", "Descargar lista")
                comp.boton_csv(alertas.drop(columns="tipo"), f"alertas_detalle_{SUFIJO}",
                               "Descargar todas (una fila por alerta)")

if st.session_state.pop("ma_ir_a_ficha", False):
    st.switch_page(FICHA)

# ---------------------------------------------------------------------------
# No inscriptos cursando
# ---------------------------------------------------------------------------
no_insc = tabla[~tabla["inscripto"]]
with tab_no_insc:
    comp.nota("Tienen alguna nota cargada y no figuran como Aceptada en Matriculados. Si aprueban, no entran al "
              "acta: derivar a secretaría antes del cierre.", "atencion", icono=True)
    if no_insc.empty:
        comp.nota("Todos los casos de la base están inscriptos.", "bien", icono=True)
    else:
        comp.tarjetas([
            dict(label="Cursan sin inscripción", value=comp.num(len(no_insc)),
                 delta=f"{comp.pct(len(no_insc) / max(k['base'], 1) * 100, 0)} de {casos(k['base'])} de la base"),
            dict(label="No están en Matriculados", value=comp.num(int((~no_insc["en_matriculados"]).sum())),
                 delta="nunca se inscribieron"),
            dict(label="Con baja", value=comp.num(int(no_insc["estado"].eq("Baja").sum())),
                 delta="se dieron de baja y siguen"),
            dict(label="Regularizan o promocionan", value=comp.num(k["aprueban_sin_inscripcion"]), tono="bien",
                 delta="aprobarían al ritmo actual", help=NOTA_TXT),
        ])

        with comp.tarjeta("secretaria"):
            t1, t2 = st.columns([1, 1.6], vertical_alignment="center")
            with t1:
                comp.seccion("Lista para secretaría")
            derecha = comp.a_la_derecha(t2)
            orden = derecha.selectbox("Mostrar", ["Primero los que aprueban", "Todos", "Solo con baja"],
                                      key="no_insc_orden", label_visibility="collapsed", width=250)
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
                "Nota proyectada": nota_txt(lista),
                "Rindió": lista["rendidos"].astype(str) + " de " + lista["instrumentos"].astype(str),
                "Actividad": comp.con_forma(lista["estado_actividad"]),
                "Último ingreso": lista["ultima_interaccion"].map(comp.fmt_fecha),
                "Estado en Matriculados": lista["estado"].where(lista["en_matriculados"], "No figura").fillna("No figura"),
            }, index=lista.index)
            if f.asignatura:
                mostrar = mostrar.drop(columns="Materia")
            with derecha:
                comp.boton_csv(mostrar, f"no_inscriptos_cursando_{SUFIJO}", "Descargar lista")
            if mostrar.empty:
                comp.nota("Nadie en este grupo.")
            else:
                st.dataframe(comp.estilo_tabla(mostrar, estados=["Condición", "Actividad", "Estado en Matriculados"],
                                               materias=["Materia"], resaltar=lista["aprueba"]),
                             hide_index=True, width="stretch", height=400, column_config={
                                 "Nota proyectada": st.column_config.TextColumn("Nota proyectada", help=NOTA_TXT)})
            comp.pie("Resaltadas: aprueban y no figuran en el acta.")

# ---------------------------------------------------------------------------
# Inscriptos sin notas (mismo criterio que la tarjeta: materias con algún instrumento tomado)
# ---------------------------------------------------------------------------
with tab_sin_notas:
    sin_notas = tabla[tabla["inscripto"] & (tabla["rendidos"] == 0) & (tabla["instrumentos"] > 0)]
    sin_notas = sin_notas.assign(nunca=sin_notas["eventos"].fillna(0).eq(0)) \
                         .sort_values(["nunca", "eventos"], ascending=[False, False])
    st.html('<p class="ma-desc" style="margin:4px 0 2px">Inscriptos con <strong>0 instrumentos rendidos</strong> '
            '(quedan Libres). Dos grupos, dos acciones.</p>')
    nunca, entra = int(sin_notas["nunca"].sum()), int((~sin_notas["nunca"]).sum())
    comp.avisos([
        comp.aviso("Nunca entraron", comp.num(nunca),
                   "Nunca abrieron el aula. Mail o llamada antes del plazo de baja.", "neutro"),
        comp.aviso("Entran pero no rinden", comp.num(entra),
                   "Usan el aula y no rinden. Descartar primero un problema de acceso a las evaluaciones.",
                   "atencion"),
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
        with comp.a_la_derecha(t2):
            comp.boton_csv(mostrar, f"inscriptos_sin_notas_{SUFIJO}", "Descargar lista")
        if mostrar.empty:
            comp.nota("Todos los inscriptos rindieron al menos un instrumento.", "bien", icono=True)
        else:
            st.dataframe(comp.estilo_tabla(mostrar, estados=["Situación"], materias=["Materia"]),
                         hide_index=True, width="stretch", height=400)
            entran = sin_notas[~sin_notas["nunca"]]
            if not entran.empty:
                top = entran.iloc[0]
                comp.pie(f"{comp.esc(top['nombre_completo'])}: {comp.num(top['eventos'])} interacciones, "
                         "0 evaluaciones. Revisar: no parece desinterés.")
