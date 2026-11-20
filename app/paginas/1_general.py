"""Dashboard 1: General.

Responde de un vistazo, a la fecha de corte y sin clicks, los cuatro pedidos de la
consigna: resumen por materia, activos vs. inactivos, rendimiento y distribución de
notas, y tendencia de participación. Los títulos dicen la conclusión, calculada con
los datos (no se escribe fija).

Una sola página, sin pestañas, en este orden:
  Contexto      fecha de corte, materias, umbral y cómo se arma la base.
  Aviso         qué cambió en la semana (corte − 7 días, corte]: variaciones de los
                KPIs que superan 1 pp o 1 alumno y las evaluaciones que entraron.
  KPIs          activos, alcanzan Regular, alumnos en riesgo e inscriptos que no
                rindieron nada, con su variación contra 7 días antes.
  Por materia   título con la comparación de libres, interruptor "excluir de las notas a
                quienes no rindieron nada" y una tarjeta por materia (de menos a más
                libres): condición, nota contra el corte de Regular, activos, tasa de
                rendición, avance, sesiones y minutos.
  Actividad     quién sigue entrando (por tramo de días sin entrar) y la tendencia
                semanal, con la semana parcial punteada y las evaluaciones en el eje.
  Distribución  histograma de notas en escala 100 por materia, con los cortes.
  Integridad    con nota sin inscripción, inscriptos que nunca entraron, 0 por no rendir.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página no calcula
reglas de negocio, solo suma conteos, arma textos y dibuja. Los textos dinámicos
usan src.textos (D77). Diseño: app/componentes_general.py (D60, D78).
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import componentes_general as comp   # sistema visual propio de esta página (ver el módulo)
from src.config import DIAS_INACTIVIDAD_LARGA, ESQUEMA, SIN_EVALUACIONES
from src.textos import comparacion_veces, enumerar, proporcion_en_palabras

NAN = float("nan")
DIAS_COMPARACION = 7
CONDICIONES = ["Promociona", "Regular", "Libre", SIN_EVALUACIONES]   # de mejor a peor
f = comp.filtros()
corte = pd.Timestamp(f.fecha_corte)
corte_anterior = f.fecha_corte - timedelta(days=DIAS_COMPARACION)
fecha_ant, fecha_hoy = comp.fmt_fecha(corte_anterior)[:5], comp.fmt_fecha(corte)[:5]
materias = [m for m in comp.COLORES_MATERIA if m in f.materias]
una_materia = len(materias) == 1
NOMBRE = {m: comp.nombre_materia(m) for m in materias}


def vacio(x) -> bool:
    return x is None or pd.isna(x)


def por_sigla(serie: pd.Series) -> str:
    """'ALG 54 · AED 39 · PYE 52' (la sigla sola va solo en estos desgloses)."""
    return " · ".join(f"{comp.SIGLAS[m]} {comp.num(serie.get(m, 0))}" for m in materias)


# ---------------------------------------------------------------------------
# Totales de las materias elegidas, hoy y 7 días antes. Cada fila de las métricas es
# un alumno en una materia: alguien que cursa dos materias cuenta dos veces.
# ---------------------------------------------------------------------------
def totales(fecha) -> dict:
    act = comp.metrica("actividad_alumnos", fecha_corte=fecha)
    alc = comp.metrica("alcanzan_regular", fecha_corte=fecha)
    al = comp.metrica("alertas", fecha_corte=fecha)
    hay_evaluaciones = alc["con_condicion"].sum() > 0
    hay_instrumentos = comp.metrica("nota_final", fecha_corte=fecha)["instrumentos"].sum() > 0
    arranque = al[al["tipo"].isin(["sin_actividad", "sin_notas"])]
    base, inscriptos_ = len(act), int(act["inscripto"].sum())
    # Sin datos todavía (antes de la primera interacción o de la primera evaluación) queda
    # NaN: la tarjeta muestra "–" y la variación y su texto se omiten.
    return {
        "pct_activos": act["activo"].mean() * 100 if act["eventos"].sum() > 0 else NAN,
        "pct_alcanzan": alc["alcanzan"].sum() / alc["con_condicion"].sum() * 100 if hay_evaluaciones else NAN,
        "riesgo": len(comp.metrica("alumnos_en_riesgo", fecha_corte=fecha)) if hay_evaluaciones else NAN,
        "sin_rendir": arranque[["asignatura", "id_alumno"]].drop_duplicates().shape[0] if hay_instrumentos else NAN,
        "nunca": int((arranque["tipo"] == "sin_actividad").sum()),
        "entran": int((arranque["tipo"] == "sin_notas").sum()),
        # Denominadores, para que cada número diga sobre cuántos
        "base": base, "inscriptos": inscriptos_, "activos": int(act["activo"].sum()),
        "alcanzan": int(alc["alcanzan"].sum()), "con_condicion": int(alc["con_condicion"].sum()),
    }


hoy, antes = totales(f.fecha_corte), totales(corte_anterior)


def dif(clave: str) -> float:
    a, b = hoy[clave], antes[clave]
    return NAN if vacio(a) or vacio(b) else a - b


kpis = comp.metrica("kpis_generales").set_index("asignatura").reindex(materias)
kpis_ant = comp.metrica("kpis_generales", fecha_corte=corte_anterior).set_index("asignatura").reindex(materias)
notas = comp.metrica("nota_final")
sin_rendir = comp.metrica("sin_rendir")
n_sin_rendir = sin_rendir.groupby("asignatura").size()

# ---------------------------------------------------------------------------
# Título y contexto
# ---------------------------------------------------------------------------
base_total = int(kpis["base"].sum())
inscriptos = int(kpis["inscriptos"].sum())
no_inscriptos = int(kpis["no_inscriptos_cursando"].sum())
comp.encabezado(
    "Dashboard general",
    f"Datos al **{comp.fmt_fecha(corte)}** · {NOMBRE[materias[0]] if una_materia else f.materia} · "
    f"Inactivo después de {f.umbral} días sin entrar · {comp.num(base_total)} "
    f"{'alumnos' if una_materia else 'alumnos × materia'}: {comp.num(inscriptos)} inscriptos + "
    f"{comp.num(no_inscriptos)} con nota sin inscripción",
)


# ---------------------------------------------------------------------------
# Aviso de la semana: variaciones de los KPIs y evaluaciones que entraron
# ---------------------------------------------------------------------------
def signo(v: float, decimales: int, unidad: str = "") -> str:
    return f"{'+' if v > 0 else '−'}{comp.num(abs(v), decimales)}{' ' + unidad if unidad else ''}"


def aviso_semana() -> str:
    # (variación, umbral, qué es mejor, sujeto, es porcentaje)
    cambios = [
        (dif("pct_activos"), 1, "sube", "los activos", True),
        (dif("pct_alcanzan"), 1, "sube", "los que alcanzan Regular", True),
        (dif("riesgo"), 1, "baja", "los alumnos en riesgo", False),
        (dif("sin_rendir"), 1, "baja", "los inscriptos que no rindieron nada", False),
    ]
    cambios = [c for c in cambios if not vacio(c[0]) and abs(c[0]) >= c[1]]
    buenos = sum((v > 0) == (mejor == "sube") for v, _, mejor, _, _ in cambios)
    malos = len(cambios) - buenos

    # Se agrupan los consecutivos del mismo tipo y sentido: "caen A (−x) y B (−y)".
    grupos: list[list] = []
    for c in cambios:
        clave = (c[4], c[0] > 0)
        if grupos and grupos[-1][0] == clave:
            grupos[-1][1].append(c)
        else:
            grupos.append([clave, [c]])
    frases = []
    for (es_pct, sube), items in grupos:
        partes = [f"{suj} ({signo(v, 1, 'pp') if es_pct else signo(v, 0)})" for v, _, _, suj, _ in items]
        if es_pct:
            frases.append(f"{'suben' if sube else 'caen'} {enumerar(partes)}")
        elif len(items) == 1:
            v, _, _, suj, _ = items[0]
            frases.append(f"{suj} {'suben' if sube else 'bajan'} ({signo(v, 0)})")
        else:
            frases.append(f"{enumerar(partes)} {'suben' if sube else 'bajan'}")

    ev = comp.metrica("evaluaciones_en_periodo")
    texto_ev = ""
    if not ev.empty:
        n_ev = len(ev)
        desglose = " · ".join(f"{comp.SIGLAS[m]} {k}" for m, k in ev.groupby("asignatura").size()
                              .reindex(materias).dropna().astype(int).items())
        faltan = len(comp.metrica("no_rindieron_periodo"))
        entro = f"Entró 1 evaluación ({desglose})" if n_ev == 1 else f"Entraron {n_ev} evaluaciones ({desglose})"
        quienes = (f"{comp.num(faltan)} {'alumno' if faltan == 1 else 'alumnos'} "
                   + (f"no la {'rindió' if faltan == 1 else 'rindieron'}" if n_ev == 1
                      else f"no {'rindió' if faltan == 1 else 'rindieron'} alguna"))
        texto_ev = (f" {entro} y {quienes}: cuentan como 0 en la condición proyectada." if faltan
                    else f" {entro} y todos los alumnos {'la' if n_ev == 1 else 'las'} rindieron.")

    semana = f"Semana {fecha_ant}–{fecha_hoy}:"
    if not frases:
        return comp.aviso(f"<strong style='font-weight:600'>{semana}</strong> sin cambios relevantes.{texto_ev}",
                          "neutro")
    tono = "critico" if malos and not buenos else "bien" if buenos and not malos else "atencion"
    return comp.aviso(f"<strong style='font-weight:600'>{semana}</strong> {'; '.join(frases)}.{texto_ev}", tono)


comp.html(aviso_semana())
st.space("small")

# ---------------------------------------------------------------------------
# KPIs (las 4 tarjetas del mismo alto, ver CSS .st-key-fila_kpis)
# ---------------------------------------------------------------------------
def tip_regular() -> str:
    """'Usa el corte de cada materia: Álgebra 60/120, el resto 60/100.' (sale del ESQUEMA)."""
    corte_de = {m: f"{ESQUEMA[m]['cortes']['Regular']}/{ESQUEMA[m]['total_max']}" for m in materias}
    if una_materia:
        return f"Usa el corte de Regular de {materias[0]}: {corte_de[materias[0]]}."
    distintos = pd.Series(corte_de).value_counts()
    comun = distintos.index[0]
    otros = [f"{m} {c}" for m, c in corte_de.items() if c != comun]
    if not otros:
        return f"Usa el corte de Regular de cada materia: {comun} en todas."
    return f"Usa el corte de cada materia: {', '.join(otros)}, el resto {comun}."

def sobre(parte, total) -> float:
    """Porcentaje para la barra de la tarjeta (NaN si no hay dato o el total es 0)."""
    return NAN if vacio(parte) or not total else parte / total * 100


unidad_base = "alumnos" if una_materia else "alumnos × materia"
with st.container(key="fila_kpis"):
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1, st.container(border=True, key="kpi_activos"):
        comp.html(comp.kpi(
            "Activos", comp.pct(hoy["pct_activos"]),
            comp.pastilla_delta(dif("pct_activos"), "pp", "sube", referencia=fecha_ant),
            proporcion=hoy["pct_activos"],
            detalle=(f"<b>{comp.num(hoy['activos'])}</b> de {comp.num(hoy['base'])} entraron en los últimos "
                     f"{f.umbral} días" if not vacio(hoy["pct_activos"]) else "Todavía no hay actividad")))
    with c2, st.container(border=True, key="kpi_regular"):
        comp.html(comp.kpi(
            "Alcanzan Regular", comp.pct(hoy["pct_alcanzan"]),
            comp.pastilla_delta(dif("pct_alcanzan"), "pp", "sube", referencia=fecha_ant),
            proporcion=hoy["pct_alcanzan"], tip=tip_regular(),
            detalle=(f"<b>{comp.num(hoy['alcanzan'])}</b> de {comp.num(hoy['con_condicion'])} con nota, "
                     f"Regular o Promociona" if not vacio(hoy["pct_alcanzan"]) else "Todavía no hay evaluaciones")))
    with c3, st.container(border=True, key="kpi_riesgo"):
        comp.html(comp.kpi(
            "Alumnos en riesgo", comp.num(hoy["riesgo"]),
            comp.pastilla_delta(dif("riesgo"), "", "baja", decimales=0, referencia=fecha_ant),
            proporcion=sobre(hoy["riesgo"], hoy["base"]), color_barra=comp.CRITICO,
            tip=f"Libre a la fecha y sin entrar en los últimos {f.umbral} días",
            detalle=(f"<b>{comp.pct(sobre(hoy['riesgo'], hoy['base']), 0)}</b> de {comp.num(hoy['base'])} "
                     f"{unidad_base} · libres y sin entrar" if not vacio(hoy["riesgo"]) else
                     "Todavía no hay evaluaciones")))
        st.page_link("paginas/7_matricula_y_alertas.py", label="Ver alertas", icon=":material/arrow_forward:")
    with c4, st.container(border=True, key="kpi_alerta"):
        comp.html(comp.kpi(
            "Inscriptos que no rindieron nada", comp.num(hoy["sin_rendir"]),
            comp.pastilla_delta(dif("sin_rendir"), "", "baja", decimales=0, referencia=fecha_ant),
            proporcion=sobre(hoy["sin_rendir"], hoy["inscriptos"]), color_barra=comp.CRITICO, alerta=True,
            detalle=(f"de {comp.num(hoy['inscriptos'])} inscriptos · <b>{comp.num(hoy['nunca'])}</b> nunca "
                     f"entraron, <b>{comp.num(hoy['entran'])}</b> entran y no rinden"
                     if not vacio(hoy["sin_rendir"]) else "Todavía no hay evaluaciones")))
        st.page_link("paginas/7_matricula_y_alertas.py", label="Ver a quiénes", icon=":material/arrow_forward:")

st.space("medium")

# ---------------------------------------------------------------------------
# Por materia
# ---------------------------------------------------------------------------
dist = comp.metrica("distribucion_condicion")
resumen = comp.metrica("resumen_calificaciones").set_index("asignatura")
tasa = comp.metrica("tasa_rendicion").set_index("asignatura")
alc = comp.metrica("alcanzan_regular").set_index("asignatura")
fecha_reporte = comp.metrica("fecha_reporte_participacion")
hay_condicion = alc["con_condicion"].reindex(materias).fillna(0).sum() > 0
libre = kpis["pct_libre"]
orden = libre.sort_values(na_position="last").index.tolist() if hay_condicion else materias


def titulo_por_materia() -> str:
    if not hay_condicion or libre.dropna().empty:
        return "Todavía no hay evaluaciones a esta fecha"
    if una_materia:
        m = materias[0]
        return f"{NOMBRE[m]}: {comp.pct(libre[m], 0)} libre, {comp.pct(kpis.loc[m, 'pct_promociona'], 0)} promociona"
    peor, mejor = libre.idxmax(), libre.idxmin()
    if peor == mejor or libre[peor] == 0:
        return f"Ninguna materia tiene alumnos libres a la fecha" if libre[peor] == 0 else NOMBRE[peor]
    veces = comparacion_veces(libre[peor], libre[mejor])
    comparacion = f"{veces} {NOMBRE[mejor]}" if veces else f"frente a {comp.pct(libre[mejor], 0)} en {NOMBRE[mejor]}"
    return f"{NOMBRE[peor]}: {comp.pct(libre[peor], 0)} libre, {comparacion}"


comp.html('<p class="gr-etq">Por materia</p>', f'<p class="gr-h2">{titulo_por_materia()}</p>')
excluir = st.toggle("Excluir de las notas a quienes no rindieron nada", value=False,
                    help="Saca de la nota promedio y de la distribución a quienes tienen 0 por no rendir ningún "
                         "instrumento. La condición (libre, regular, promociona) no cambia.")
n_sin_total = int(n_sin_rendir.reindex(materias).fillna(0).sum())
if not excluir and n_sin_total:
    comp.html(comp.aviso(f"Las notas incluyen con 0 a {comp.num(n_sin_total)} "
                         f"{'alumno que no rindió' if n_sin_total == 1 else 'alumnos que no rindieron'} nada.",
                         "neutro"))

tip_avance = "El avance sale del reporte de participación y no cambia con la fecha de corte."
avance_foto = fecha_reporte is not None and pd.Timestamp(fecha_reporte).normalize() != corte


def fila(etiqueta: str, valor: str, extra: str = "", clase: str = "", tip: str = "") -> str:
    extra = f' <span class="gr-tenue">{extra}</span>' if extra else ""
    return (f'<div class="gr-fila {clase}"><span>{etiqueta}{comp.ayuda(tip) if tip else ""}</span>'
            f'<b>{valor}{extra}</b></div>')


cols = st.columns(max(len(orden), 3), gap="small")   # con una sola materia, la tarjeta no ocupa todo el ancho
for col, m in zip(cols, orden):
    r, r_ant = kpis.loc[m], kpis_ant.loc[m]
    dm = dist[dist["asignatura"] == m].set_index("condicion")["pct"]
    segs = []
    for c in CONDICIONES:
        p = dm.get(c, 0)
        segs.append((p, comp.COLORES_CONDICION[c], f"{comp.pct(p, 0)} {c.lower()}" if p >= 22 else comp.pct(p, 0)))
    d_libre = NAN if vacio(r["pct_libre"]) or vacio(r_ant["pct_libre"]) or not hay_condicion else \
        r["pct_libre"] - r_ant["pct_libre"]
    linea_libre = (f'<p class="num gr-tenue" style="margin:7px 0 10px;color:{comp.TEXTO_3}">Libre '
                   f'{comp.delta(d_libre, "pp", "baja")} vs. {fecha_ant}</p>' if not vacio(d_libre)
                   else '<div style="height:12px"></div>')

    escala = ESQUEMA[m]["total_max"]
    corte_reg = ESQUEMA[m]["cortes"]["Regular"] / escala * 100
    real = resumen["nota_promedio_rindieron"].get(m) if excluir else resumen["nota_promedio"].get(m)
    sobre_100 = real / escala * 100 if not vacio(real) else NAN
    color_nota = comp.TONOS["critico"][2] if not vacio(sobre_100) and sobre_100 < corte_reg else comp.TEXTO
    nota_html = (
        f'<div class="gr-fila" style="display:block"><div style="display:flex;justify-content:space-between">'
        f'<span>Nota promedio</span><b style="color:{color_nota}">{comp.num(sobre_100, 1)}/100 '
        f'<span class="gr-tenue">· {comp.num(real, 1)}/{escala}</span></b></div>'
        + comp.barra_marca(sobre_100, corte_reg, comp.COLORES_MATERIA[m],
                           f"Corte de Regular: {comp.num(corte_reg, 1)}/100")
        + f'<p class="gr-tenue" style="margin-top:3px">La raya marca el corte de Regular '
          f'({comp.num(ESQUEMA[m]["cortes"]["Regular"])}/{escala})</p></div>')
    tr = tasa.loc[m] if m in tasa.index else None
    avance = fila("Avance promedio", comp.pct(r["avance_promedio"]),
                  f"foto al {comp.fmt_fecha(fecha_reporte)[:5]}" if avance_foto else "",
                  "gr-atenuado" if avance_foto else "", tip_avance if avance_foto else "")
    with col:
        comp.html(
            f'<div class="gr-tarjeta"><div style="display:flex;align-items:flex-start;gap:9px;margin-bottom:14px;'
            f'min-height:44px"><span style="margin-top:5px">{comp.cuadradito(comp.COLORES_MATERIA[m], 11)}</span>'
            f'<p style="flex:1 1 auto;font:600 15px/1.35 {comp.FUENTE_TITULOS}">{NOMBRE[m]}</p>'
            f'<span class="num gr-tenue" style="color:{comp.TEXTO_3};white-space:nowrap;margin-top:3px">'
            f'{comp.num(r["base"])} alumnos</span></div>',
            comp.barra_apilada(segs, alto=28, min_etiqueta=12) if hay_condicion else
            '<p class="gr-txt">Todavía no hay evaluaciones a esta fecha.</p>',
            linea_libre,
            nota_html,
            fila("Activos", comp.pct(r["pct_activos"]), comp.num(r["activos"])),
            fila("Tasa de rendición", comp.pct(tr["pct_rendidos"]) if tr is not None else "–",
                 f"{comp.num(tr['rendidos'])} de {comp.num(tr['instrumentos'])}" if tr is not None
                 and tr["instrumentos"] else "",
                 tip="Instrumentos rendidos sobre los que había para rendir a la fecha, sumando todos los alumnos."),
            avance,
            fila("Sesiones por alumno", comp.num(r["sesiones_promedio"], 1)),
            fila("Minutos por alumno", comp.num(r["minutos_promedio"])),
            "</div>",
        )
comp.html(f'<div style="margin-top:10px">' + comp.leyenda(
    [(comp.COLORES_CONDICION[c], c, comp.TONOS[comp.TONO_CONDICION[c]][2])
     for c in CONDICIONES if (dist["condicion"] == c).any()]) + "</div>")

st.space("medium")

# ---------------------------------------------------------------------------
# Actividad: quién sigue entrando | tendencia semanal
# ---------------------------------------------------------------------------
comp.html('<p class="gr-etq" style="margin-bottom:8px">Actividad</p>')
act = comp.metrica("actividad_alumnos")
col1, col2 = st.columns([1, 1.3], gap="small")

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
    proporcion = proporcion_en_palabras(hoy["pct_activos"])
    partes = [
        f'<p class="gr-h3">{proporcion} entró en los últimos {f.umbral} días</p>' if proporcion
        else '<p class="gr-h3">Quién sigue entrando</p>',
        f'<p class="gr-txt" style="margin-bottom:18px">Activo = entró en los últimos {f.umbral} días.</p>',
    ]
    for m in materias:
        de_m = act["asignatura"].eq(m)
        n = int(de_m.sum())
        if not n:
            continue
        cuentas = [(nombre, color, int((mask & de_m).sum())) for nombre, color, mask in tramos]
        partes += [
            f'<p style="display:flex;justify-content:space-between;gap:8px;margin-bottom:7px;font:600 12px '
            f'{comp.FUENTE}">{NOMBRE[m]}<span class="num gr-tenue" style="color:{comp.TEXTO_3}">'
            f'{comp.num(n)}</span></p>',
            comp.barra_apilada([(c / n * 100, color, comp.num(c)) for _, color, c in cuentas], alto=28,
                               min_etiqueta=6),
            f'<p class="num gr-tenue" style="margin:6px 0 16px;color:{comp.TEXTO_3}">'
            f'{comp.pct(cuentas[0][2] / n * 100, 0)} activos</p>',
        ]
    partes.append(f'<div style="padding-top:14px;border-top:1px solid {comp.BORDE_SUAVE}">'
                  + comp.leyenda([(color, nombre, None) for nombre, color, _ in tramos]) + "</div>")
    comp.html(*partes)

with col2, comp.tarjeta("tendencia"):
    medidas = {"Alumnos activos": "alumnos_activos", "Interacciones": "eventos", "Sesiones": "sesiones",
               "Minutos en la plataforma": "minutos"}
    c1, c2 = st.columns([1.6, 1], vertical_alignment="bottom")
    with c1:
        comp.html('<p class="gr-h3">Tendencia semanal'
                  + comp.ayuda("Las marcas sobre el eje son las evaluaciones, del color de su materia. La fecha de "
                               "cada evaluación es la mediana de los intentos registrados.") + "</p>")
    medida = c2.selectbox("Medida", list(medidas), label_visibility="collapsed")
    y = medidas[medida]
    evo = comp.metrica("evolucion_actividad", frecuencia="W")
    evo = evo[evo["asignatura"].isin(materias)]
    if evo.empty or evo[y].sum() == 0:
        comp.html('<p class="gr-txt" style="padding:40px 0">Todavía no hay actividad a esta fecha.</p>')
    else:
        periodos = sorted(evo["periodo"].unique())
        dias_ultima = corte.day_of_week + 1          # lunes = 1 ... domingo = 7
        parcial = dias_ultima < 7 and len(periodos) > 1
        evaluaciones = comp.metrica("fechas_evaluaciones")
        evaluaciones = evaluaciones[evaluaciones["asignatura"].isin(materias)].assign(
            semana=lambda e: e["fecha_instrumento"] - pd.to_timedelta(e["fecha_instrumento"].dt.day_of_week, unit="D"))
        fmt = ",.0f"
        fig = go.Figure()
        for m in materias:
            s = evo[evo["asignatura"] == m].sort_values("periodo")
            color, nombre = comp.COLORES_MATERIA[m], NOMBRE[m]
            completas = s.iloc[:-1] if parcial else s
            # Espacios al final: plotly mide la leyenda antes de que cargue Inter y recortaba el nombre largo.
            fig.add_scatter(x=completas["periodo"], y=completas[y], mode="lines", name=nombre + " " * 3,
                            legendgroup=m,
                            line=dict(color=color, width=2.2), hoverinfo="skip")
            if parcial:
                fig.add_scatter(x=s["periodo"].iloc[-2:], y=s[y].iloc[-2:], mode="lines", legendgroup=m,
                                showlegend=False, line=dict(color=color, width=2.2, dash="dot"), hoverinfo="skip")
            fig.add_scatter(x=s["periodo"], y=s[y], mode="markers", legendgroup=m, showlegend=False, name=nombre,
                            marker=dict(color=color, size=6),
                            hovertemplate=f"{nombre}: %{{y:{fmt}}}<extra></extra>")
        # Evaluaciones: marcas chicas sobre el eje (sin hover propio) y una línea en el hover de su semana.
        for m in materias:
            e = evaluaciones[evaluaciones["asignatura"] == m]
            if not e.empty:
                fig.add_scatter(x=e["fecha_instrumento"], y=[0] * len(e), mode="markers", showlegend=False,
                                hoverinfo="skip", cliponaxis=False,
                                marker=dict(symbol="triangle-up", size=10, color=comp.COLORES_MATERIA[m],
                                            line=dict(color="white", width=1)))
        por_semana = (evaluaciones.assign(txt=evaluaciones["asignatura"].map(comp.SIGLAS) + " "
                                          + evaluaciones["instrumento"].map(comp.nombre_instrumento))
                      .groupby("semana")["txt"].agg(" · ".join))
        por_semana = por_semana[por_semana.index.isin(periodos)]
        if not por_semana.empty:
            fig.add_scatter(x=por_semana.index, y=[0] * len(por_semana), mode="markers", showlegend=False,
                            marker=dict(size=1, opacity=0), customdata=por_semana.values, name="",
                            hovertemplate="Evaluaciones: %{customdata}<extra></extra>")
        if parcial:   # arriba del área del gráfico, sobre la última semana: no pisa las líneas
            fig.add_annotation(x=periodos[-1], y=1, yref="paper", yanchor="bottom", text=f"parcial ({dias_ultima} "
                               f"de 7 días)", showarrow=False, xanchor="right", font=dict(size=11, color=comp.TEXTO_3))
        # Leyenda en columna arriba a la izquierda: con los nombres completos, en fila se recortaban.
        fig.update_layout(
            height=400, hovermode="x unified", margin=dict(t=84, l=4, r=8, b=4),
            legend=dict(orientation="v", yanchor="bottom", y=1.03, x=0, xanchor="left", tracegroupgap=2),
            yaxis=dict(rangemode="tozero", title_text=medida, tickformat=fmt),
            xaxis=dict(showgrid=False, title_text="Semana (desde el lunes)", tickformat="%d/%m",
                       tickvals=periodos[::2], hoverformat="%d/%m"),
        )
        comp.grafico(fig)

st.space("medium")

# ---------------------------------------------------------------------------
# Distribución de notas (a ancho completo)
# ---------------------------------------------------------------------------
with comp.tarjeta("distribucion"):
    corte_leyenda = (f'<span style="display:inline-flex;align-items:center;gap:7px;font:500 11px {comp.FUENTE};'
                     f'color:{comp.TEXTO_2}"><span style="width:18px;border-top:2px {{}} {comp.TEXTO_2};'
                     f'display:inline-block"></span>{{}}</span>')
    conversiones = [
        f"En {m}, {ESQUEMA[m]['cortes']['Regular']} y {ESQUEMA[m]['cortes']['Promociona']} sobre "
        f"{ESQUEMA[m]['total_max']} quedan en "
        f"{comp.num(ESQUEMA[m]['cortes']['Regular'] / ESQUEMA[m]['total_max'] * 100, 1)} y "
        f"{comp.num(ESQUEMA[m]['cortes']['Promociona'] / ESQUEMA[m]['total_max'] * 100, 1)} sobre 100."
        for m in materias if ESQUEMA[m]["total_max"] != 100]
    tip_cortes = " ".join(["Todas las notas llevadas a escala 100.", *conversiones])
    comp.html(
        '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:baseline;justify-content:space-between">'
        f'<p class="gr-h3">Distribución de notas{comp.ayuda(tip_cortes)}</p><div style="display:flex;gap:14px">'
        + corte_leyenda.format("dotted", "Corte de Regular") + corte_leyenda.format("dashed", "Corte de Promociona")
        + '</div></div><p class="gr-txt">Escala 100 · eje vertical compartido.</p>')
    hist = notas[notas["rendidos"] > 0] if excluir else notas
    hist = hist[hist["nota_pct"].notna() & hist["asignatura"].isin(materias)]
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
        fig.for_each_annotation(lambda a: a.update(text=f"<b>{comp.nombre_materia(a.text.split('=')[-1])}</b>",
                                                   font=dict(size=13, color=comp.TEXTO)))
        maximo = barras["alumnos"].max()
        for i, materia in enumerate(materias_hist, start=1):
            escala = ESQUEMA[materia]["total_max"]
            for nombre, valor in ESQUEMA[materia]["cortes"].items():
                fig.add_vline(x=valor / escala * 100, col=i, line_width=1.5, line_color=comp.TEXTO_2,
                              line_dash="dot" if nombre == "Regular" else "dash")
            n0 = int(n_sin_rendir.get(materia, 0))
            if not excluir and n0:
                alto0 = barras[(barras["asignatura"] == materia) & (barras["desde"] == 0)]["alumnos"].sum()
                fig.add_annotation(row=1, col=i, x=1, y=alto0, text=f"{comp.num(n0)} sin rendir", showarrow=False,
                                   xanchor="left", yanchor="bottom", yshift=3,
                                   font=dict(size=11, color=comp.TEXTO_2))
        fig.update_yaxes(range=[0, maximo * 1.15])
        fig.update_layout(height=320, showlegend=False, bargap=0, margin=dict(t=36, l=4, r=4, b=4))
        comp.grafico(fig)
    else:
        comp.html('<p class="gr-txt" style="padding:20px 0">Todavía no hay notas a esta fecha de corte.</p>')

st.space("medium")

# ---------------------------------------------------------------------------
# Integridad de los datos: decide a quién estamos midiendo.
# ---------------------------------------------------------------------------
sin_act = int(kpis["inscriptos_sin_actividad"].sum())


def caja(numero: int, titulo: str, detalle: str, destacada: bool = False) -> str:
    estilo = "border:1px solid #F0E2C4;background:#FBF0DC" if destacada else f"border:1px solid {comp.BORDE}"
    c1, c2 = ("#6B4700", "#6B4700") if destacada else (comp.TEXTO, comp.TEXTO_2)
    return (f'<div style="{estilo};border-radius:11px;padding:14px">'
            f'<p class="num" style="margin-bottom:4px;font:600 22px {comp.FUENTE_TITULOS};color:{c1}">'
            f'{comp.num(numero)}</p><p style="margin-bottom:8px;font:500 13px {comp.FUENTE};color:{c1}">{titulo}</p>'
            f'<p class="num" style="font:400 12px/1.55 {comp.FUENTE};color:{c2}">{detalle}</p></div>')


comp.html(
    f'<div class="gr-tarjeta"><div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'
    f'<span style="color:{comp.ATENCION};display:inline-flex">{comp.forma("atencion", 16)}</span>'
    f'<p class="gr-h3" style="margin:0 !important">Integridad de los datos'
    + comp.ayuda("La base de cada materia son los inscriptos con último estado Aceptada más quienes tienen "
                 "alguna nota sin estar inscriptos.") + '</p></div>'
    f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px">',
    caja(no_inscriptos, "alumnos con nota pero sin inscripción",
         f"{comp.pct(no_inscriptos / base_total * 100 if base_total else NAN, 0)} de la base · "
         f"{por_sigla(kpis['no_inscriptos_cursando'])}", destacada=no_inscriptos > 0),
    caja(sin_act, "inscriptos que nunca entraron",
         f"{por_sigla(kpis['inscriptos_sin_actividad'])}. Sin interacciones ni notas a la fecha de corte."),
    caja(n_sin_total, "con nota 0 por no haber rendido",
         f"{por_sigla(n_sin_rendir)}. Cuentan como 0 en los promedios."),
    "</div></div>",
)
