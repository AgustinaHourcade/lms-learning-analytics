"""Dashboard 1: General.

Responde, de un vistazo y a la fecha de corte: ¿cómo vienen las condiciones,
cuánta gente sigue entrando y qué se movió desde 7 días antes?

  Arriba       condición proyectada (Libre / Regular / Promociona como partes de un
               mismo total), tarjetas con la variación contra 7 días antes y una
               lectura rápida escrita a partir de esas variaciones.
  Actividad    quién sigue entrando (activos e inactivos según hace cuánto) y la
               tendencia semanal con las evaluaciones marcadas.
  Notas        condición por materia, nota promedio y distribución de notas.
  Por materia  una tarjeta por materia, la integridad de los datos y la tabla
               completa, descargable en CSV.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página no calcula
reglas de negocio, solo agrega y dibuja. El diseño sigue el sistema visual de
app/componentes_general.py (D60).
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import componentes_general as comp   # sistema visual propio de esta página (ver el módulo)
from src.config import DIAS_INACTIVIDAD_LARGA, ESQUEMA, SIN_EVALUACIONES

f = comp.encabezado(
    "Dashboard general",
    "Las materias a la fecha de corte: cómo vienen las condiciones, cuánta gente sigue entrando "
    "y qué se movió en la última semana.",
)

ORDEN = {"asignatura": list(comp.COLORES_MATERIA)}
DIAS_COMPARACION = 7
CONDICIONES = ["Promociona", "Regular", "Libre", SIN_EVALUACIONES]   # de mejor a peor
corte_anterior = f.fecha_corte - timedelta(days=DIAS_COMPARACION)
fecha_ant = comp.fmt_fecha(corte_anterior)[:5]
materias = [m for m in ORDEN["asignatura"] if m in f.materias]


# ---------------------------------------------------------------------------
# Totales de las materias elegidas, hoy y 7 días antes
# ---------------------------------------------------------------------------
def totales(fecha) -> dict:
    """KPIs agregados de todas las materias elegidas. Cada fila es un alumno en
    una materia: alguien que cursa dos materias cuenta dos veces."""
    notas = comp.metrica("nota_final", fecha_corte=fecha)
    act = comp.metrica("actividad_alumnos", fecha_corte=fecha)
    # Sin datos todavía (antes de la primera interacción o de la primera evaluación)
    # se devuelve NaN: la tarjeta muestra "–" y no se calcula la variación.
    hay_actividad = act["eventos"].sum() > 0
    con_nota = notas[notas["nota_pct"].notna()]
    cond = con_nota["condicion"].value_counts(normalize=True) * 100
    return {
        "base": len(notas),
        "con_nota": len(con_nota),
        "pct_activos": act["activo"].mean() * 100 if hay_actividad else float("nan"),
        "nota_pct": notas["nota_pct"].mean(),
        "cond": {c: (cond.get(c, 0.0) if len(con_nota) else float("nan")) for c in CONDICIONES[:3]},
    }


hoy, antes = totales(f.fecha_corte), totales(corte_anterior)
kpis = comp.metrica("kpis_generales")
notas = comp.metrica("nota_final")


def dif(clave: str, cond: str | None = None) -> float:
    a, b = (hoy["cond"][cond], antes["cond"][cond]) if cond else (hoy[clave], antes[clave])
    return float("nan") if pd.isna(a) or pd.isna(b) else a - b


# ---------------------------------------------------------------------------
# Arriba: condición proyectada + tarjetas
# ---------------------------------------------------------------------------
col_cond, col_kpis = st.columns([1.3, 1], gap="small")

with col_cond:
    segmentos = [(hoy["cond"][c], comp.COLORES_CONDICION[c], comp.pct(hoy["cond"][c]))
                 for c in CONDICIONES[:3]] if hoy["con_nota"] else []
    mejor = {"Promociona": "sube", "Regular": "neutro", "Libre": "baja"}
    variaciones = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:7px;font:500 12px {comp.FUENTE};'
        f'color:{comp.TONOS[comp.TONO_CONDICION[c]][2]}">{comp.forma(comp.TONO_CONDICION[c], 13)}{c} '
        f'{comp.delta(dif("", c), "pp", mejor[c]) or comp.pct(hoy["cond"][c])}</span>'
        for c in CONDICIONES[:3])
    sin_eval = hoy["base"] - hoy["con_nota"]
    nota_sin = (f'<p class="gr-txt" style="margin-top:10px">{comp.num(sin_eval)} alumnos todavía sin '
                f'evaluaciones a la fecha no entran en el reparto.</p>') if sin_eval else ""
    libre = hoy["cond"]["Libre"]
    lectura_cond = ""
    if hoy["con_nota"] and not pd.isna(libre):
        uno_de = round(100 / libre) if libre >= 20 else None
        lectura_cond = (f'<p class="gr-txt" style="margin-top:12px">Hoy {comp.pct(libre)} de los alumnos con nota '
                        f'queda libre'
                        + (f": aproximadamente uno de cada {uno_de} no llega a regularizar." if uno_de else ".")
                        + "</p>")
    comp.html(
        f'<div class="gr-tarjeta" style="padding:18px 20px">'
        f'<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;justify-content:space-between;'
        f'margin-bottom:12px"><p class="gr-etq">Condición proyectada · {comp.num(hoy["con_nota"])} '
        f'{"alumnos" if f.asignatura else "alumnos × materia"}</p>'
        f'<span class="gr-tenue">variaciones contra el {fecha_ant}</span></div>',
        comp.barra_apilada(segmentos, alto=34) if segmentos else
        '<p class="gr-txt">Todavía no hay evaluaciones a esta fecha.</p>',
        f'<div style="display:flex;flex-wrap:wrap;gap:20px;margin-top:12px">{variaciones}</div>',
        lectura_cond, nota_sin, "</div>",
    )

with col_kpis:
    arriba = st.columns(2, gap="small")
    abajo = st.columns(2, gap="small")
    inscriptos = int(kpis["inscriptos"].sum())
    with arriba[0]:
        comp.html(comp.kpi("Alumnos en la base" if f.asignatura else "Alumnos × materia", comp.num(hoy["base"]),
                           f"{comp.num(inscriptos)} inscriptos formales"))
    with arriba[1]:
        comp.html(comp.kpi("Activos", comp.pct(hoy["pct_activos"]),
                           comp.delta(dif("pct_activos"), "pp", "sube") or f"entraron en {f.umbral} días"))
    with abajo[0]:
        comp.html(comp.kpi("Nota promedio", comp.num(hoy["nota_pct"], 1),
                           comp.delta(dif("nota_pct"), "pts", "sube") or "sobre 100", sufijo="/ 100"))
    with abajo[1]:
        alertas = comp.metrica("alertas")
        arranque = alertas[alertas["tipo"].isin(["sin_actividad", "sin_notas"])]
        nunca = int((arranque["tipo"] == "sin_actividad").sum())
        no_rinden = int((arranque["tipo"] == "sin_notas").sum())
        with comp.tarjeta("alerta", gap="small"):
            comp.html(
                f'<p class="gr-etq" style="color:#8A3A31;margin-bottom:8px">Inscriptos sin arrancar</p>'
                f'<p class="gr-grande" style="color:#93241C">{comp.num(arranque[["asignatura", "id_alumno"]].drop_duplicates().shape[0])}</p>'
                f'<p class="gr-txt num" style="color:#8A3A31;margin-top:4px">{comp.num(nunca)} nunca entraron · '
                f'{comp.num(no_rinden)} entran y no rinden</p>')
            st.page_link("paginas/7_matricula_y_alertas.py", label="Ver a quiénes", icon=":material/arrow_forward:")


# ---------------------------------------------------------------------------
# Lectura rápida: una oración armada con las variaciones (sin interpretar causas)
# ---------------------------------------------------------------------------
def lectura_rapida() -> str:
    cambios = [  # (variación, unidad, qué es mejor, frase si sube, frase si baja)
        (dif("pct_activos"), "pp", "sube", "los alumnos activos suben", "los alumnos activos bajan"),
        (dif("", "Promociona"), "pp", "sube", "los que promocionan suben", "los que promocionan bajan"),
        (dif("", "Libre"), "pp", "baja", "los libres suben", "los libres bajan"),
        (dif("nota_pct"), "pts", "sube", "la nota promedio sube", "la nota promedio cae"),
    ]
    frases, buenos, malos = [], 0, 0
    for v, unidad, mejor, sube, baja in cambios:
        if pd.isna(v) or round(v, 1) == 0:
            continue
        frases.append(f"{sube if v > 0 else baja} {comp.num(abs(v), 1)} {unidad}")
        if (v > 0) == (mejor == "sube"):
            buenos += 1
        else:
            malos += 1
    if not frases:
        return ""
    texto = ", ".join(frases[:-1]) + (" y " if len(frases) > 1 else "") + frases[-1]
    if malos and not buenos:
        titulo, tono = f"Desde el {fecha_ant} empeoró todo lo que se mide acá:", "critico"
    elif buenos and not malos:
        titulo, tono = f"Desde el {fecha_ant} mejoró todo lo que se mide acá:", "bien"
    else:
        titulo, tono = f"Desde el {fecha_ant}, movimientos en distintas direcciones:", "atencion"
    return comp.aviso(f"<strong style='font-weight:600'>{titulo}</strong> {texto}.", tono)


if texto_lectura := lectura_rapida():
    comp.html(texto_lectura)

tab_act, tab_notas, tab_mat = st.tabs(["Actividad", "Notas", "Por materia"])

# ---------------------------------------------------------------------------
# Actividad
# ---------------------------------------------------------------------------
with tab_act:
    act = comp.metrica("actividad_alumnos")
    col1, col2 = st.columns([1, 1.3], gap="medium")

    with col1, comp.tarjeta("quien_entra"):
        largo = max(DIAS_INACTIVIDAD_LARGA, f.umbral)
        tramos = [  # (nombre, color, máscara)
            ("Activo", comp.BIEN, act["estado_actividad"].eq("Activo")),
            (f"{f.umbral + 1} a {largo} días", comp.ATENCION,
             act["estado_actividad"].eq("Inactivo") & act["dias_sin_actividad"].le(largo).fillna(False)),
            (f"{largo + 1} días o más", comp.CRITICO,
             act["estado_actividad"].eq("Inactivo") & act["dias_sin_actividad"].gt(largo).fillna(False)),
            ("Nunca entró", comp.NEUTRO, act["estado_actividad"].eq("Sin actividad")),
        ]
        tramos = [t for t in tramos if t[2].any() or t[0] == "Activo"]
        partes = [
            '<p class="gr-h3">Quién sigue entrando</p>',
            f'<p class="gr-txt" style="margin-bottom:18px">Activo: entró en los últimos {f.umbral} días. '
            f'El resto se abre según hace cuánto dejó de entrar.</p>',
        ]
        for m in materias:
            de_m = act["asignatura"].eq(m)
            n = int(de_m.sum())
            if not n:
                continue
            cuentas = [(nombre, color, int((mask & de_m).sum())) for nombre, color, mask in tramos]
            activos = cuentas[0][2]
            partes += [
                f'<p style="display:flex;justify-content:space-between;margin-bottom:7px;font:600 12px '
                f'{comp.FUENTE}">{m}<span class="num gr-tenue" style="color:{comp.TEXTO_3}">{comp.num(n)}</span></p>',
                comp.barra_apilada([(c / n * 100, color, comp.num(c)) for _, color, c in cuentas], alto=28, min_etiqueta=6),
                f'<p class="num gr-tenue" style="margin:6px 0 16px;color:{comp.TEXTO_3}">'
                f'{comp.pct(activos / n * 100, 0)} activos</p>',
            ]
        partes.append(f'<div style="padding-top:14px;border-top:1px solid {comp.BORDE_SUAVE}">'
                      + comp.leyenda([(color, nombre, None) for nombre, color, _ in tramos]) + "</div>")
        comp.html(*partes)

    with col2, comp.tarjeta("tendencia"):
        medidas = {"Alumnos activos": "alumnos_activos", "Interacciones": "eventos", "Sesiones": "sesiones",
                   "Minutos en la plataforma": "minutos"}
        c1, c2 = st.columns([1.6, 1], vertical_alignment="bottom")
        with c1:
            comp.html('<p class="gr-h3">Tendencia semanal</p>'
                      '<p class="gr-txt">Las líneas punteadas verticales son las evaluaciones ya tomadas, '
                      'del color de su materia.</p>')
        medida = c2.selectbox("Medida", list(medidas), label_visibility="collapsed")
        evo = comp.metrica("evolucion_actividad", frecuencia="W")
        fig = px.line(evo, x="periodo", y=medidas[medida], color="asignatura",
                      category_orders=ORDEN, color_discrete_map=comp.COLORES_MATERIA,
                      labels={"periodo": "Semana, desde el lunes", medidas[medida]: "", "asignatura": ""})
        fig.update_traces(line_width=2.2, mode="lines+markers", marker_size=5,
                          hovertemplate="%{fullData.name}: %{y:,.0f}<extra></extra>")
        fig.for_each_trace(lambda t: t.update(name=comp.NOMBRES_CORTOS.get(t.name, t.name)))
        for ev in comp.metrica("fechas_evaluaciones").itertuples():
            fig.add_vline(x=ev.fecha_instrumento, line_width=1, line_dash="dash",
                          line_color=comp.COLORES_MATERIA[ev.asignatura], opacity=0.45)
        fig.update_layout(height=330, hovermode="x unified", yaxis_rangemode="tozero",
                          xaxis=dict(showgrid=False, tickformat="%d/%m"), margin=dict(t=36, l=4, r=4, b=4))
        comp.grafico(fig)
        comp.html(f'<p class="gr-txt" style="padding:12px 14px;border-radius:10px;background:#FBFAF8">'
                  f'La fecha de cada evaluación es la mediana de los intentos registrados. La última semana '
                  f'puede estar incompleta si el corte cae a mitad de semana.</p>')

# ---------------------------------------------------------------------------
# Notas
# ---------------------------------------------------------------------------
with tab_notas:
    resumen = comp.metrica("resumen_calificaciones").set_index("asignatura")
    dist = comp.metrica("distribucion_condicion")
    sin_rendir = notas[notas["rendidos"] == 0].groupby("asignatura").size()

    col1, col2 = st.columns(2, gap="medium")
    with col1, comp.tarjeta("condicion"):
        orden = (resumen.reindex(materias)["pct_libre"].sort_values().index.tolist())
        partes = ['<p class="gr-h3">Condición por materia</p>',
                  '<p class="gr-txt" style="margin-bottom:18px">Ordenado de mejor a peor (menos libres primero). '
                  'Mismos colores y formas que el semáforo del resto de la app.</p>']
        for m in orden:
            dm = dist[dist["asignatura"] == m].set_index("condicion")["pct"]
            segs = []
            for c in CONDICIONES:
                p = dm.get(c, 0)
                etq = f"{comp.pct(p, 0)} {c.lower()}" if p >= 22 else comp.pct(p, 0)
                segs.append((p, comp.COLORES_CONDICION[c], etq))
            partes += [f'<p style="display:flex;align-items:center;gap:8px;margin-bottom:7px;font:600 12px '
                       f'{comp.FUENTE}">{comp.cuadradito(comp.COLORES_MATERIA[m])}{m}</p>',
                       comp.barra_apilada(segs, alto=30, min_etiqueta=7), '<div style="height:14px"></div>']
        partes.append(comp.leyenda([(comp.COLORES_CONDICION[c], c, comp.TONOS[comp.TONO_CONDICION[c]][2])
                                    for c in CONDICIONES if (dist["condicion"] == c).any()]))
        comp.html(*partes)

    with col2, comp.tarjeta("nota_promedio"):
        comp.html('<p class="gr-h3">Nota promedio</p>'
                  '<p class="gr-txt" style="margin-bottom:10px">Todo llevado a escala 100 para poder comparar; '
                  'al lado, la nota en la escala real de cada materia.</p>')
        lugar_barras = st.empty()
        lugar_aviso = st.empty()
        excluir = st.toggle("Excluir a quienes no rindieron ningún instrumento", value=False,
                            help="Son 0 por no rendir, no por rendir mal: suelen ser alumnos que abandonaron. "
                                 "Afecta a esta tarjeta y a la distribución de abajo.")
        filas = []
        for m in materias:
            if m not in resumen.index:
                continue
            r = resumen.loc[m]
            real = r["nota_promedio_rindieron"] if excluir else r["nota_promedio"]
            sobre_100 = real / r["escala"] * 100 if pd.notna(real) else float("nan")
            filas.append(
                f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">'
                f'<span style="flex:0 0 96px;font:500 12px {comp.FUENTE}">{comp.NOMBRES_CORTOS[m]}</span>'
                f'{comp.barra_simple(sobre_100, comp.COLORES_MATERIA[m])}'
                f'<span class="num" style="flex:0 0 110px;text-align:right;font:600 13px {comp.FUENTE}">'
                f'{comp.num(sobre_100, 1)} <span class="gr-tenue" style="color:{comp.TEXTO_3}">· '
                f'{comp.num(real, 1)}/{comp.num(r["escala"])}</span></span></div>')
        with lugar_barras:
            comp.html(*filas)
        n_sin = int(sin_rendir.reindex(materias).fillna(0).sum())
        with lugar_aviso:
            if excluir:
                comp.html(comp.aviso(f"Sin los {comp.num(n_sin)} alumnos que no rindieron nada: el promedio "
                                     "mide solo a quienes se presentaron a algo.", "neutro"))
            elif n_sin:
                comp.html(comp.aviso(f"<strong style='font-weight:600'>Ojo con este promedio:</strong> incluye "
                                     f"con 0 a quienes no rindieron nada. Son {comp.num(n_sin)} alumnos y "
                                     "arrastran el número para abajo.", "atencion"))

    with comp.tarjeta("distribucion"):
        corte_leyenda = (f'<span style="display:inline-flex;align-items:center;gap:7px;font:500 11px {comp.FUENTE};'
                         f'color:{comp.TEXTO_2}"><span style="width:18px;border-top:2px {{}} {comp.TEXTO_2};'
                         f'display:inline-block"></span>{{}}</span>')
        comp.html(
            '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:baseline;justify-content:space-between">'
            '<p class="gr-h3">Distribución de notas</p><div style="display:flex;gap:14px">'
            + corte_leyenda.format("dotted", "Corte de Regular") + corte_leyenda.format("dashed", "Corte de Promociona")
            + '</div></div><p class="gr-txt" style="max-width:88ch">Todas las notas llevadas a escala 100 '
            '(en Álgebra, 60 y 85 sobre 120 quedan en 50 y 70,8). Misma escala vertical en las tres, para que '
            'las alturas se puedan comparar.</p>')
        hist = notas[notas["rendidos"] > 0] if excluir else notas
        hist = hist[hist["nota_pct"].notna()]
        # Bins de 5 puntos armados a mano (el 100 entra en el último), así son iguales en las tres materias.
        ANCHO = 5
        hist = hist.assign(desde=(hist["nota_pct"].clip(0, 99.999) // ANCHO * ANCHO).astype(int))
        barras = hist.groupby(["asignatura", "desde"]).size().rename("alumnos").reset_index()
        barras["centro"] = barras["desde"] + ANCHO / 2
        barras["rango"] = [f"{a} a {a + ANCHO}" for a in barras["desde"]]
        materias_hist = [m for m in materias if m in set(barras["asignatura"])]
        if materias_hist:
            fig = px.bar(barras, x="centro", y="alumnos", color="asignatura", facet_col="asignatura",
                         category_orders={"asignatura": materias_hist}, color_discrete_map=comp.COLORES_MATERIA,
                         custom_data=["rango"], labels={"centro": "", "alumnos": "", "asignatura": ""})
            fig.update_traces(width=ANCHO * 0.86, hovertemplate="Nota de %{customdata[0]}<br>%{y} alumnos<extra></extra>")
            fig.update_xaxes(range=[0, 100], dtick=50, showgrid=False)
            fig.for_each_annotation(lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>", x=a.x - 0.0,
                                                       font=dict(size=13, color=comp.TEXTO)))
            for i, materia in enumerate(materias_hist, start=1):
                escala = ESQUEMA[materia]["total_max"]
                for nombre, corte in ESQUEMA[materia]["cortes"].items():
                    fig.add_vline(x=corte / escala * 100, col=i, line_width=1.5, line_color=comp.TEXTO_2,
                                  line_dash="dot" if nombre == "Regular" else "dash")
            # Rango fijo: dentro de una pestaña oculta el autorange de plotly a veces falla.
            fig.update_yaxes(range=[0, barras["alumnos"].max() * 1.08])
            fig.update_layout(height=300, showlegend=False, bargap=0, margin=dict(t=36, l=4, r=4, b=4))
            comp.grafico(fig)
            if not excluir:
                cols = st.columns(len(materias_hist))
                for col, m in zip(cols, materias_hist):
                    n0 = int(sin_rendir.get(m, 0))
                    n_m = int((notas["asignatura"] == m).sum())
                    if n0:
                        col.html(f'<p class="gr" style="font:400 12px/1.5 {comp.FUENTE};color:{comp.TEXTO_2};margin:0">'
                                 f'{comp.num(n0)} alumnos en 0 por no rendir nada '
                                 f'({comp.pct(n0 / n_m * 100, 0)} de la materia).</p>')
        else:
            st.info("Todavía no hay notas a esta fecha de corte.")

# ---------------------------------------------------------------------------
# Por materia
# ---------------------------------------------------------------------------
with tab_mat:
    k = kpis.set_index("asignatura")
    cols = st.columns(len(materias), gap="small")
    for col, m in zip(cols, materias):
        if m not in k.index:
            continue
        r = k.loc[m]
        segs = [(r["pct_promociona"], comp.BIEN, ""), (r["pct_regular"], comp.ATENCION, ""),
                (r["pct_libre"], comp.CRITICO, "")]
        tono_nota = "critico" if r["nota_promedio"] / r["escala"] * 100 < 40 else None
        color_nota = comp.TONOS[tono_nota][2] if tono_nota else comp.TEXTO
        with col:
            comp.html(
                f'<div class="gr-tarjeta"><div style="display:flex;align-items:center;gap:9px;margin-bottom:14px;'
                f'min-height:42px">'
                f'{comp.cuadradito(comp.COLORES_MATERIA[m], 11)}'
                f'<p style="flex:1 1 auto;font:600 16px {comp.FUENTE_TITULOS}">{m}</p>'
                f'<span class="num gr-tenue" style="color:{comp.TEXTO_3};white-space:nowrap">'
                f'{comp.num(r["base"])} alumnos</span></div>',
                comp.barra_apilada(segs, alto=26),
                f'<p class="num gr-tenue" style="margin:7px 0 16px;color:{comp.TEXTO_3}">'
                f'{comp.pct(r["pct_promociona"])} promociona · {comp.pct(r["pct_regular"])} regular · '
                f'{comp.pct(r["pct_libre"])} libre</p>',
                f'<div class="gr-fila"><span>Nota promedio</span><b style="color:{color_nota}">'
                f'{comp.num(r["nota_promedio"] / r["escala"] * 100, 1)} <span class="gr-tenue">· '
                f'{comp.num(r["nota_promedio"], 1)} / {comp.num(r["escala"])}</span></b></div>',
                f'<div class="gr-fila"><span>Activos</span><b>{comp.pct(r["pct_activos"])} '
                f'<span class="gr-tenue">· {comp.num(r["activos"])}</span></b></div>',
                f'<div class="gr-fila"><span>Avance promedio</span><b>{comp.pct(r["avance_promedio"])}</b></div>',
                f'<div class="gr-fila"><span>Sesiones · minutos por alumno</span><b>'
                f'{comp.num(r["sesiones_promedio"], 1)} · {comp.num(r["minutos_promedio"])}</b></div></div>',
            )

    # Integridad de los datos: decide a quién estamos midiendo.
    no_insc = int(k["no_inscriptos_cursando"].sum())
    sin_act = int(k["inscriptos_sin_actividad"].sum())
    n_sin = int(sin_rendir.reindex(materias).fillna(0).sum())
    base_total = int(k["base"].sum())

    def por_sigla(serie: pd.Series) -> str:
        return " · ".join(f"{comp.SIGLAS[m]} {comp.num(serie.get(m, 0))}" for m in materias)

    def caja(numero: int, titulo: str, detalle: str, destacada: bool = False) -> str:
        estilo = ("border:1px solid #F0E2C4;background:#FBF0DC" if destacada else f"border:1px solid {comp.BORDE}")
        c1, c2 = ("#6B4700", "#7A5000") if destacada else (comp.TEXTO, comp.TEXTO_2)
        return (f'<div style="{estilo};border-radius:11px;padding:14px">'
                f'<p class="num" style="margin-bottom:4px;font:600 22px {comp.FUENTE_TITULOS};color:{c1}">'
                f'{comp.num(numero)}</p><p style="margin-bottom:8px;font:500 13px {comp.FUENTE};color:{c1}">{titulo}</p>'
                f'<p class="num" style="font:400 12px/1.55 {comp.FUENTE};color:{c2}">{detalle}</p></div>')

    st.space("small")
    comp.html(
        f'<div class="gr-tarjeta"><div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
        f'<span style="color:{comp.ATENCION};display:inline-flex">{comp.forma("atencion", 16)}</span>'
        f'<p class="gr-h3" style="margin:0 !important">Integridad de los datos</p></div>'
        f'<p class="gr-txt" style="margin-bottom:16px;max-width:88ch">Quiénes entran en la base de cada materia: '
        f'inscriptos (último estado Aceptada) más quienes tienen alguna nota sin estar inscriptos.</p>'
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px">',
        caja(no_insc, "alumnos con nota pero sin inscripción",
             f"{comp.pct(no_insc / base_total * 100 if base_total else float('nan'), 0)} de la base · "
             f"{por_sigla(k['no_inscriptos_cursando'])}. Puede ser una inscripción sin cargar o alguien "
             f"rindiendo sin estar anotado.", destacada=no_insc > 0),
        caja(sin_act, "inscriptos que nunca entraron",
             f"{por_sigla(k['inscriptos_sin_actividad'])}. Sin interacciones ni notas a la fecha de corte."),
        caja(n_sin, "con nota 0 por no haber rendido",
             f"{por_sigla(sin_rendir)}. Entran en todos los promedios; el interruptor de la pestaña Notas los saca."),
        "</div></div>",
    )

    st.space("small")
    with comp.tarjeta("tabla"):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.html(f'<div class="gr"><p class="gr-h3">Tabla completa</p>'
                f'<p class="gr-txt" style="margin:0">Todas las columnas, para auditar o exportar.</p></div>')
        columnas = {
            "asignatura": "Materia", "base": "En la base", "inscriptos": "Inscriptos",
            "no_inscriptos_cursando": "Con nota sin inscripción", "inscriptos_sin_actividad": "Sin actividad",
            "activos": "Activos", "pct_activos": "% activos", "sesiones_promedio": "Sesiones",
            "minutos_promedio": "Minutos", "avance_promedio": "Avance (%)", "nota_promedio": "Nota prom.",
            "escala": "Escala", "pct_libre": "% Libre", "pct_regular": "% Regular", "pct_promociona": "% Promociona",
        }
        tabla = kpis[list(columnas)].rename(columns=columnas)
        with c2:
            comp.boton_csv(tabla, f"kpis_generales_{f.fecha_corte:%Y%m%d}")
        st.dataframe(tabla, hide_index=True, width="stretch",
                     column_config={
                         **{c: st.column_config.NumberColumn(format="%.1f") for c in
                            ["Sesiones", "Minutos", "Nota prom."]},
                         **{c: st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100)
                            for c in ["% activos", "Avance (%)", "% Libre", "% Regular", "% Promociona"]},
                     })
        st.caption("Sesiones y minutos salen de la trazabilidad hasta la fecha de corte (una sesión se corta tras "
                   "30 minutos sin eventos). El avance sale del reporte de participación, que es una foto al "
                   "24/10 y no cambia con la fecha de corte (D36).")
