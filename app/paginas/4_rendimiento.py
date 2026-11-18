"""Dashboard 2 (del plan): Rendimiento académico.

Responde, a la fecha de corte: ¿qué explica la nota (notas o entregas)?, ¿qué
instrumentos cuestan más y cuántos los rinden?, ¿cómo se reparten las notas? y
¿cómo se fue moviendo la condición (Promociona / Regular / Libre)?

  Lectura principal  nota de todos -> nota de quienes rindieron y tasa de entrega,
                     con una frase que dice qué pesa más; condición al corte.
  Por materia        nota promedio (y "si rindió") de cada materia e instrumento más flojo.
  Por instrumento    una tabla por materia: cuántos lo rindieron, promedio, % aprobada
                     y una caja con la distribución de las notas (solo quienes rindieron, D22).
  Distribución       histograma en la escala de cada materia, coloreado por condición,
                     con los cortes del ESQUEMA, y el resumen estadístico.
  Condición          % por condición hoy y su evolución evaluación a evaluación (D51).
  Tabla              todos los instrumentos, ordenable, y las descargas en CSV.

Diseño: sistema visual de componentes.py (piezas HTML de componentes.py, clases tc-*). Los
textos que interpretan los datos se arman con los números, no están escritos a mano.
Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo agrega y dibuja.
"""
import pandas as pd
import streamlit as st

import componentes as comp
from componentes import esc, num
from src.config import ESQUEMA

f = comp.filtros()
notas = comp.metrica("nota_final")
instrumentos = comp.metrica("promedio_por_instrumento")
rendidas = comp.metrica("notas_rendidas")
dist = comp.metrica("distribucion_condicion")

instrumentos["nombre"] = instrumentos["instrumento"].map(comp.nombre_corto)
rendidas["nombre"] = rendidas["instrumento"].map(comp.nombre_corto)
corte_txt = pd.Timestamp(f.fecha_corte).strftime("%d/%m")

# Tablas para descargar (botones de arriba y pestaña Tabla).
COLUMNAS_TABLA = {
    "asignatura": "Materia", "nombre": "Instrumento", "fecha_instrumento": "Fecha",
    "puntaje_maximo": "Puntaje máximo", "rindieron": "Rindieron", "pct_rindio": "% de la base",
    "promedio_pct": "Promedio", "mediana_pct": "Mediana", "minimo_pct": "Mínimo", "maximo_pct": "Máximo",
    "pct_aprobada": "% aprobada",
}
tabla = instrumentos[list(COLUMNAS_TABLA)].rename(columns=COLUMNAS_TABLA)
detalle_alumnos = rendidas.drop(columns=["orden", "instrumento"]).rename(columns={"nombre": "instrumento"})


def descargas() -> None:
    if instrumentos.empty:
        return
    comp.boton_csv(tabla, f"rendimiento_por_instrumento_{f.fecha_corte:%Y%m%d}", "Resumen por instrumento")
    comp.boton_csv(detalle_alumnos, f"notas_por_alumno_{f.fecha_corte:%Y%m%d}", "Notas por alumno")


comp.encabezado(
    "Rendimiento académico",
    f"Cómo les va a los alumnos en cada evaluación y cómo queda su condición al {corte_txt}.",
    acciones=descargas,
)

if instrumentos.empty:
    st.info(f"Al {comp.fmt_fecha(f.fecha_corte)} todavía no se tomó ninguna evaluación en "
            f"{f.materia.lower()}. Mové la fecha de corte para ver notas.", icon=":material/event_busy:")
    st.stop()

materias = [m for m in f.materias if m in set(instrumentos["asignatura"])]
CONDICIONES = [c for c in comp.COLORES_CONDICION if c in set(dist.loc[dist["alumnos"] > 0, "condicion"])]


# ---------------------------------------------------------------------------
# Formatos y reglas de color (el semáforo evalúa; el color de materia identifica)
# ---------------------------------------------------------------------------
def pct_corto(v, decimales: int = 1) -> str:
    """'100 %' en vez de '100,0 %'; '—' si no hay dato."""
    if v is None or pd.isna(v):
        return "—"
    return comp.pct(v, 0 if float(v).is_integer() else decimales)


def puntos(pct_valor: float, maximo: float) -> str:
    """Nota sobre 100 -> puntos del instrumento (75 sobre 100 con máximo 10 -> '7,5')."""
    p = round(pct_valor * maximo / 100, 1)
    return num(p, 0 if p == int(p) else 1)


def color_entrega(p: float, color_materia: str) -> str:
    """Barra de 'rindieron': rojo si lo rindió menos del 30 %, ámbar si menos del 50 %."""
    return comp.CRITICO if p < 30 else comp.ATENCION if p < 50 else color_materia


def estilo_entrega(p: float) -> str:
    if p < 30:
        return f"font-weight:600;color:{comp.ROJO}"
    if p < 50:
        return f"color:{comp.AMBAR}"
    return f"font-weight:600;color:{comp.VERDE}" if p > 75 else ""


def color_aprobada(p: float) -> str:
    return comp.VERDE if p >= 85 else comp.AMBAR if p >= 60 else comp.ROJO


def caja(valores: pd.Series, color: str) -> str:
    """Mini boxplot en SVG (sobre 100): bigotes de mínimo a máximo, caja del 25 % al
    75 %, línea en la mediana y punto en el promedio."""
    if valores.empty:
        return '<span class="tc-chico">—</span>'
    mn, q1, me, q3, mx = valores.quantile([0, .25, .5, .75, 1]).tolist()
    prom = valores.mean()
    x = lambda v: 2 + v / 100 * 216  # noqa: E731
    ancho = max(x(q3) - x(q1), 3)
    texto = (f"mín {num(mn, 1)} · 25 % {num(q1, 1)} · mediana {num(me, 1)} · 75 % {num(q3, 1)} · "
             f"máx {num(mx, 1)} · promedio {num(prom, 1)}")
    return (f'<svg viewBox="0 0 220 22" width="220" height="22" role="img" aria-label="{texto}" style="display:block">'
            f"<title>{texto}</title>"
            f'<line x1="2" y1="11" x2="218" y2="11" stroke="#F1EFEA"/>'
            f'<line x1="{x(mn):.1f}" y1="11" x2="{x(mx):.1f}" y2="11" stroke="#A8A49B" stroke-width="1.2"/>'
            f'<line x1="{x(mn):.1f}" y1="5" x2="{x(mn):.1f}" y2="17" stroke="#A8A49B" stroke-width="1.2"/>'
            f'<line x1="{x(mx):.1f}" y1="5" x2="{x(mx):.1f}" y2="17" stroke="#A8A49B" stroke-width="1.2"/>'
            f'<rect x="{min(x(q1), 218 - ancho):.1f}" y="4" width="{ancho:.1f}" height="14" rx="2" '
            f'fill="{comp.aclarar(color)}" stroke="{color}" stroke-width="1.2"/>'
            f'<line x1="{x(me):.1f}" y1="4" x2="{x(me):.1f}" y2="18" stroke="{color}" stroke-width="2"/>'
            f'<circle cx="{x(prom):.1f}" cy="11" r="3" fill="{comp.TEXTO}"/></svg>')


def tabla_html(encabezados: list[str], filas: list[str]) -> str:
    th = "".join(f'<th scope="col">{h}</th>' for h in encabezados)
    return f'<div class="tc-tabla"><table><thead><tr>{th}</tr></thead><tbody>{"".join(filas)}</tbody></table></div>'


# ---------------------------------------------------------------------------
# Lectura principal: ¿pesan más las notas o las entregas?
# ---------------------------------------------------------------------------
cuentan = instrumentos[~instrumentos["es_recuperatorio"]]
con_rendidos = cuentan[cuentan["rindieron"] > 0]
tasa_entrega = cuentan["rindieron"].sum() / cuentan["base"].sum() * 100
con_nota = notas[notas["rendidos"] > 0]
nota_todos, nota_rindieron = notas["nota_pct"].mean(), con_nota["nota_pct"].mean()
sin_rendir = int(((notas["rendidos"] == 0) & notas["nota_pct"].notna()).sum())
aprobada = ((con_rendidos["pct_aprobada"] * con_rendidos["rindieron"]).sum()
            / con_rendidos.loc[con_rendidos["pct_aprobada"].notna(), "rindieron"].sum())
brecha = nota_rindieron - nota_todos
if con_rendidos.empty:
    st.info("Ya se tomaron evaluaciones, pero todavía nadie las rindió.", icon=":material/event_busy:")
    st.stop()
mas_flojo = con_rendidos.nsmallest(1, "promedio_pct").iloc[0]

if brecha >= 5 and aprobada >= 80:
    titular = "El problema no son las notas, son las entregas."
elif aprobada < 70:
    titular = "Además de las entregas, cuesta aprobar."
else:
    titular = ""
lectura = (f"Entre quienes los rinden, los instrumentos promedian entre {num(con_rendidos['promedio_pct'].min(), 0)} "
           f"y {num(con_rendidos['promedio_pct'].max(), 0)}, y se aprueba el {pct_corto(aprobada, 0)} de lo entregado.")
if sin_rendir:
    lectura += (f" Los {num(brecha, 1)} puntos que separan las dos notas son los {num(sin_rendir)} alumnos que no "
                "rindieron nada y tienen 0.")
if titular:
    titular = f'<strong style="font-weight:600">{titular}</strong> '
color_tasa = comp.VERDE if tasa_entrega >= 75 else comp.AMBAR if tasa_entrega >= 60 else comp.ROJO

total_base = int(dist["alumnos"].sum())
segmentos, filas_cond = "", ""
for i, cond in enumerate(CONDICIONES):
    n_cond = int(dist.loc[dist["condicion"] == cond, "alumnos"].sum())
    p_cond = n_cond / total_base * 100 if total_base else 0
    segmentos += (f'<div style="width:{p_cond:.2f}%;background:{comp.COLORES_CONDICION[cond]}" '
                  f'title="{cond}: {num(n_cond)} alumnos ({comp.pct(p_cond)})"></div>')
    borde = f"border-top:1px solid {comp.BORDE_SUAVE};" if i else ""
    filas_cond += (f'<div style="display:flex;align-items:baseline;justify-content:space-between;padding:7px 0;{borde}">'
                   f'<span style="display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:500;'
                   f'color:{comp.TEXTO_CONDICION[cond]}">{comp.forma(cond)}{cond}</span>'
                   f'<span class="num" style="font-size:13px;font-weight:600">{comp.pct(p_cond)} '
                   f'<span class="tc-chico" style="color:{comp.TEXTO_4}">· {num(n_cond)}</span></span></div>')
ayuda_base = ("Alumnos de la base de cada materia a la fecha de corte, con 0 en lo no rendido."
              + (" Un alumno que cursa dos materias cuenta dos veces." if len(materias) > 1 else ""))

comp.pintar(f"""
<section class="tc-fila" aria-label="Lectura principal">
  <div class="tc-card" style="flex:1 1 460px">
    <p class="tc-etiqueta">Lo que explica la nota</p>
    <div style="display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start;margin-bottom:14px">
      <div title="Promedio de toda la base (sobre 100), con 0 en lo no rendido.">
        <p class="tc-grande">{num(nota_todos, 1)}</p><p class="tc-texto">nota promedio de todos</p></div>
      <div style="align-self:center;color:{comp.TEXTO_4}"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
        <path d="M4 12h15m0 0l-5-5m5 5l-5 5" fill="none" stroke="currentColor" stroke-width="1.6"
        stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      <div title="Solo los {num(len(con_nota))} alumnos con al menos una evaluación rendida (sobre 100).">
        <p class="tc-grande" style="color:{comp.VERDE}">{num(nota_rindieron, 1)}</p>
        <p class="tc-texto">nota de quienes sí rindieron</p></div>
      <div style="align-self:center;padding-left:20px;border-left:1px solid {comp.BORDE_SUAVE}"
        title="Evaluaciones rendidas / (alumnos de la base × evaluaciones tomadas). No cuenta el recuperatorio.">
        <p class="tc-grande" style="color:{color_tasa}">{comp.pct(tasa_entrega)}</p>
        <p class="tc-texto">tasa de entrega</p></div>
    </div>
    <p class="tc-aviso">{titular}{lectura}</p>
  </div>
  <div class="tc-card" style="flex:1 1 280px">
    <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;justify-content:space-between;margin-bottom:12px">
      <p class="tc-etiqueta" style="margin:0">Condición al corte</p>
      <span class="num tc-chico" style="color:{comp.TEXTO_4}" title="{ayuda_base}">base: {num(total_base)}</span>
    </div>
    <div style="display:flex;height:32px;border-radius:8px;overflow:hidden;margin-bottom:12px">{segmentos}</div>
    {filas_cond}
  </div>
</section>
""")

# ---------------------------------------------------------------------------
# Nota por materia + instrumento más flojo
# ---------------------------------------------------------------------------
tarjetas_materia = ""
for materia in materias:
    n_m = notas[notas["asignatura"] == materia]
    prom, prom_r = n_m["nota_pct"].mean(), n_m.loc[n_m["rendidos"] > 0, "nota_pct"].mean()
    color = comp.COLORES_MATERIA[materia]
    tarjetas_materia += f"""
    <div class="tc-card chica" title="{esc(materia)}: nota promedio sobre 100 de toda la base (con 0 en lo no rendido)
    y de quienes rindieron al menos una evaluación.">
      <p style="margin:0 0 10px;display:flex;align-items:center;gap:8px;font-size:12px;font-weight:600">
        {comp.swatch(materia)}{esc(comp.nombre_materia_corto(materia))}</p>
      <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:8px">
        <span class="tc-medio">{num(prom, 0)}</span>
        <span class="num" style="font-size:13px;font-weight:500;color:{comp.VERDE}">{num(prom_r, 0)} si rindió</span></div>
      {comp.barra(prom, color, ancho='100%')}
    </div>"""
aprobo_flojo = mas_flojo["pct_aprobada"]
frase_aprobo = ("" if pd.isna(aprobo_flojo) else
                f" — y aun así lo aprobó el {pct_corto(aprobo_flojo, 0)}." if aprobo_flojo >= 60 else
                f" — lo aprobó el {pct_corto(aprobo_flojo, 0)}.")
comp.pintar(f"""
<section class="tc-grilla" aria-label="Nota por materia">{tarjetas_materia}
  <div class="tc-card chica alerta" title="El instrumento con el promedio más bajo (sobre 100, solo quienes lo rindieron).">
    <p class="tc-etiqueta" style="margin:0 0 10px;color:#8A3A31">Instrumento más flojo</p>
    <p class="tc-medio" style="margin:0 0 4px;color:{comp.ROJO}">{num(mas_flojo['promedio_pct'], 1)}</p>
    <p class="tc-texto" style="color:#7A3028">{esc(mas_flojo['nombre'])} ({comp.SIGLAS[mas_flojo['asignatura']]})
      {frase_aprobo} Lo rindió el {pct_corto(mas_flojo['pct_rindio'], 0)}.</p>
  </div>
</section>
""")

tab_inst, tab_dist, tab_cond, tab_tabla = st.tabs(["Por instrumento", "Distribución", "Condición", "Tabla"])

# ---------------------------------------------------------------------------
# Por instrumento: una tabla por materia con la caja de cada instrumento
# ---------------------------------------------------------------------------
with tab_inst:
    leyenda_caja = ('<svg viewBox="0 0 28 14" width="28" height="14" aria-hidden="true">'
                    '<line x1="1" y1="7" x2="27" y2="7" stroke="#A8A49B" stroke-width="1.2"/>'
                    f'<rect x="8" y="2" width="12" height="10" rx="2" fill="{comp.aclarar(comp.ACCION)}" '
                    f'stroke="{comp.ACCION}" stroke-width="1.2"/>'
                    f'<line x1="15" y1="2" x2="15" y2="12" stroke="{comp.ACCION}" stroke-width="2"/></svg>')
    comp.pintar(f"""
    <div class="tc-nota" style="display:flex;flex-wrap:wrap;gap:12px 20px;align-items:flex-start;margin-bottom:16px">
      <p style="margin:0;flex:1 1 460px">Cada fila es un instrumento, en el orden en que se tomó. La barra de la
      izquierda es cuánta gente lo rindió; la caja de la derecha, cómo se repartieron esas notas sobre 100: los
      extremos son el mínimo y el máximo, la caja el 50 % del medio, la línea la mediana y el punto el promedio.
      Solo cuentan quienes lo rindieron.</p>
      <div class="tc-leyenda" style="font-size:11px">
        <span style="font-size:11px">{leyenda_caja}mín · 25 % · mediana · 75 % · máx</span>
        <span style="font-size:11px"><span class="tc-swatch" style="background:{comp.TEXTO};border-radius:999px;
        width:8px;height:8px"></span>promedio</span>
      </div>
    </div>""")

    for materia in materias:
        prom = instrumentos[instrumentos["asignatura"] == materia]
        notas_m = rendidas[rendidas["asignatura"] == materia]
        color = comp.COLORES_MATERIA[materia]
        normales = prom[~prom["es_recuperatorio"]]
        n_rec = int(prom["es_recuperatorio"].sum())
        meta = (f"{len(normales)} instrumento{'s' if len(normales) != 1 else ''}"
                + (f" + {n_rec} recuperatorio{'s' if n_rec > 1 else ''}" if n_rec else "")
                + f" · {num(prom['base'].max())} alumnos")

        # Lectura de la materia, armada con los números.
        rinden = normales[normales["rindieron"] > 0]
        primero, ultimo = normales.iloc[0], normales.iloc[-1]
        p_min, p_max = num(rinden["promedio_pct"].min(), 0), num(rinden["promedio_pct"].max(), 0)
        cae = len(normales) > 1 and primero["pct_rindio"] - ultimo["pct_rindio"] >= 30
        if cae and rinden["promedio_pct"].min() >= 70:
            texto = (f"Las notas se sostienen ({p_min} a {p_max}) mientras la entrega se desploma "
                     f"({pct_corto(primero['pct_rindio'], 0)} → {pct_corto(ultimo['pct_rindio'], 0)}). "
                     "No es que les cueste; es que dejan de presentarse.")
        elif cae:
            texto = (f"La entrega cae del {pct_corto(primero['pct_rindio'], 0)} al "
                     f"{pct_corto(ultimo['pct_rindio'], 0)} y, entre quienes rinden, el promedio va de {p_min} a {p_max}.")
        elif len(normales) > 1:
            alto, bajo = normales.loc[normales["pct_rindio"].idxmax()], normales.loc[normales["pct_rindio"].idxmin()]
            texto = (f"La entrega va del {pct_corto(bajo['pct_rindio'], 0)} ({esc(bajo['nombre'])}) al "
                     f"{pct_corto(alto['pct_rindio'], 0)} ({esc(alto['nombre'])}); entre quienes rinden, "
                     f"el promedio va de {p_min} a {p_max}.")
        else:
            texto = (f"Por ahora hay un solo instrumento: lo rindió el {pct_corto(primero['pct_rindio'], 0)} "
                     f"con promedio {num(primero['promedio_pct'], 1)}.")
        if n_rec:
            rec = prom[prom["es_recuperatorio"]].iloc[0]
            texto += (f" El recuperatorio lo rindió el {pct_corto(rec['pct_rindio'], 0)} de la base: "
                      "su nota reemplaza a la original en la condición.")
        estilo_texto = f"font-weight:500;color:{comp.ROJO}" if cae else ""

        con_aprobada = prom["pct_aprobada"].notna().any()
        filas = []
        for fila in prom.itertuples():
            en_puntos = pd.notna(fila.puntaje_maximo) and fila.puntaje_maximo != 100
            sub = [comp.fmt_fecha(fila.fecha_instrumento)[:5] if pd.notna(fila.fecha_instrumento) else "sin fecha"]
            if en_puntos:
                sub.append(f"{num(fila.puntaje_maximo, 0)} pts")
            if fila.es_recuperatorio:
                sub.append("reemplaza a la original")
            if fila.rindieron:
                promedio = num(fila.promedio_pct, 1) + (
                    f' <span class="tc-chico" style="color:{comp.TEXTO_4}">· '
                    f'{puntos(fila.promedio_pct, fila.puntaje_maximo)}/{num(fila.puntaje_maximo, 0)}</span>'
                    if en_puntos else "")
            else:
                promedio = "—"
            rojo = f"color:{comp.ROJO};" if fila.id_instrumento == mas_flojo["id_instrumento"] else ""
            celdas = [
                f'<strong style="font-weight:600">{esc(fila.nombre)}</strong><br>'
                f'<span class="tc-chico">{" · ".join(sub)}</span>',
                f'<span style="display:flex;align-items:center;gap:9px">'
                f'{comp.barra(fila.pct_rindio, color_entrega(fila.pct_rindio, color), ancho=72)}'
                f'<span class="num" style="font-size:12px;font-weight:500;{estilo_entrega(fila.pct_rindio)}">'
                f'{num(fila.rindieron)} · {pct_corto(fila.pct_rindio, 0)}</span></span>',
                f'<span style="font-size:14px;font-weight:600;{rojo}">{promedio}</span>',
            ]
            if con_aprobada:
                celdas.append("—" if pd.isna(fila.pct_aprobada) else
                              f'<span style="font-weight:600;color:{color_aprobada(fila.pct_aprobada)}">'
                              f'{pct_corto(fila.pct_aprobada)}</span>')
            valores = notas_m.loc[notas_m["id_instrumento"] == fila.id_instrumento, "nota_pct_instrumento"]
            celdas.append(caja(valores, color))
            clase = ' class="tenue"' if fila.es_recuperatorio else ""
            filas.append(f"<tr{clase}>" + "".join(f"<td>{c}</td>" for c in celdas) + "</tr>")
        encabezados = ["Instrumento", "Rindieron", "Promedio"] + (["Aprobó"] if con_aprobada else []) + \
            ["Distribución de las notas (sobre 100)"]

        comp.pintar(f"""
        <div class="tc-card" style="padding:18px;margin-bottom:14px">
          <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:6px">
            {comp.swatch(materia, 10)}<h3 style="flex:1 1 auto">{esc(materia)}</h3>
            <span class="num" style="font-size:12px;color:{comp.TEXTO_3}">{meta}</span></div>
          <p class="tc-texto" style="margin:0 0 16px;max-width:86ch;{estilo_texto}">{texto}</p>
          {tabla_html(encabezados, filas)}
        </div>""")

# ---------------------------------------------------------------------------
# Distribución: histograma en la escala de la materia, por condición
# ---------------------------------------------------------------------------
LEYENDA_CONDICION = "".join(
    f'<span style="color:{comp.TEXTO_CONDICION[c]}">{comp.forma(c, tam=11)}{c}</span>'
    for c in ["Libre", "Regular", "Promociona"])  # en el orden del eje: de 0 al máximo


def histograma(h: pd.DataFrame, materia: str) -> str:
    """Histograma HTML de 20 barras en la escala de la materia, apiladas por condición,
    con líneas en los cortes de Regular (punteada) y Promociona (guiones)."""
    escala = ESQUEMA[materia]["total_max"]
    cortes = ESQUEMA[materia]["cortes"]
    ancho = escala / 20
    h = h.assign(barra=(h["nota_final"].clip(0, escala - 1e-6) // ancho).astype(int))
    conteo = h.groupby(["barra", "condicion"]).size().unstack(fill_value=0)
    maximo = conteo.sum(axis=1).max() if len(conteo) else 1
    barras = ""
    for i in range(20):
        desde = i * ancho
        fila = conteo.loc[i] if i in conteo.index else pd.Series(dtype=int)
        total = int(fila.sum())
        partes = [(c, int(fila.get(c, 0))) for c in ["Libre", "Regular", "Promociona"] if fila.get(c, 0)]
        detalle = ", ".join(f"{n} {c}" for c, n in partes)
        segs = "".join(f'<div style="height:{n / total * 100:.2f}%;background:{comp.COLORES_CONDICION[c]}"></div>'
                       for c, n in reversed(partes)) if total else ""
        barras += (f'<div title="Nota de {num(desde, 0)} a {num(desde + ancho, 0)}: {total} alumnos'
                   f'{" (" + detalle + ")" if detalle else ""}" style="flex:1 1 0;height:{total / maximo * 100:.2f}%;'
                   f'display:flex;flex-direction:column">{segs}</div>')
    lineas = "".join(
        f'<div title="Corte de {nombre}: {corte}" style="position:absolute;top:0;bottom:0;left:{corte / escala * 100:.2f}%;'
        f'border-left:2px {"dotted" if nombre == "Regular" else "dashed"} {comp.TEXTO_2}"></div>'
        for nombre, corte in cortes.items())
    marcas = [(0, "left:0"), *[(c, f"left:{c / escala * 100:.2f}%;transform:translateX(-50%)") for c in cortes.values()]]
    if max(cortes.values()) < escala * 0.88:  # si un corte queda pegado al final, el máximo se omite
        marcas.append((escala, "right:0"))
    eje = "".join(f'<span class="num tc-chico" style="position:absolute;{pos}">{v}</span>' for v, pos in marcas)
    stats = (f"Mediana {num(h['nota_final'].median(), 1)} · promedio {num(h['nota_final'].mean(), 1)} · "
             f"desvío {num(h['nota_final'].std(), 1)}" if len(h) else "Sin alumnos para mostrar.")
    return f"""
    <div>
      <p style="margin:0 0 10px;display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600">
        {comp.swatch(materia)}{esc(comp.nombre_materia_corto(materia))}
        <span class="num tc-chico">{num(len(h))} alumnos · sobre {escala}</span></p>
      <div style="position:relative;display:flex;align-items:flex-end;gap:2px;height:140px;
        border-bottom:1px solid #D9D6CF;margin-bottom:7px">{barras}{lineas}</div>
      <div style="position:relative;height:16px;margin-bottom:8px">{eje}</div>
      <p class="tc-texto num">{stats}</p>
    </div>"""


with tab_dist:
    hist = notas[notas["nota_final"].notna()]
    n_sin_rendir = int((hist["rendidos"] == 0).sum())
    with st.container(key="tarjeta_distribucion"):
        izq, der = st.columns([3, 2], vertical_alignment="center")
        with izq:
            comp.pintar('<h4 style="margin:0 0 4px;font:600 15px \'Space Grotesk\',Inter,sans-serif">'
                        'Dónde cae cada alumno</h4><p class="tc-texto" style="max-width:78ch">Cada materia en su '
                        'propia escala (Álgebra sobre 120). El color de la barra ya dice en qué condición queda '
                        'esa nota; las líneas solo marcan dónde cambia: punteada, Regular; de guiones, '
                        'Promociona. Pasá el mouse por una barra para ver cuántos alumnos tiene.</p>')
        with der, st.container(key="opcion_excluir"):
            excluir = st.checkbox(f"Excluir a los {num(n_sin_rendir)} que no rindieron nada", value=True,
                                  help="Tienen 0 por no rendir, no por rendir mal: suelen ser alumnos que "
                                       "abandonaron.")
        if excluir:
            hist = hist[hist["rendidos"] > 0]

        cerca = []
        for materia in materias:
            h_m = hist[hist["asignatura"] == materia]
            reg = ESQUEMA[materia]["cortes"]["Regular"]
            n_cerca = int(((h_m["condicion"] == "Libre") & (h_m["nota_final"] >= reg - 10)).sum())
            cerca.append(f"{num(n_cerca)} en {comp.nombre_materia_corto(materia)}")
        comp.pintar(f"""
        <div class="tc-leyenda" style="margin:6px 0 16px">{LEYENDA_CONDICION}</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px">
          {''.join(histograma(hist[hist['asignatura'] == m], m) for m in materias)}
        </div>
        <p class="tc-nota" style="margin-top:18px"><strong style="font-weight:600;color:{comp.TEXTO}">Para leer:
        </strong> a menos de 10 puntos del corte de Regular, todavía libres, hay {', '.join(cerca)}. Son los
        alumnos más cerca de cambiar de condición con el próximo instrumento.</p>""")

    resumen = (hist.groupby("asignatura")["nota_final"]
                   .agg(alumnos="size", promedio="mean", desvio="std", minimo="min",
                        p25=lambda s: s.quantile(0.25), mediana="median", p75=lambda s: s.quantile(0.75),
                        maximo="max")
                   .reindex(materias))
    filas = [
        "<tr>" + f'<td><span style="display:inline-flex;align-items:center;gap:8px">{comp.swatch(m)}'
        f'<strong style="font-weight:600">{esc(m)}</strong></span></td>'
        f'<td style="color:{comp.TEXTO_4}">{ESQUEMA[m]["total_max"]}</td><td>{num(r.alumnos)}</td>'
        f'<td style="font-weight:600">{num(r.promedio, 1)}</td>'
        + "".join(f"<td>{num(v, 1)}</td>" for v in [r.desvio, r.minimo, r.p25, r.mediana, r.p75, r.maximo])
        + "</tr>"
        for m, r in resumen.iterrows()]
    alcance = ("los alumnos que rindieron al menos una evaluación" if excluir
               else "toda la base, incluidos los que no rindieron nada (0)")
    comp.pintar(f"""
    <div class="tc-card" style="padding:0;overflow:hidden;margin-top:14px">
      <div style="padding:15px 16px 13px"><h4>Resumen estadístico</h4>
        <p class="tc-texto" style="color:{comp.TEXTO_3}">Sobre {alcance}, cada materia en su escala.</p></div>
      {tabla_html(["Materia", "Escala", "Alumnos", "Promedio", "Desvío", "Mínimo", "P25", "Mediana", "P75",
                   "Máximo"], filas)}
    </div>""")

# ---------------------------------------------------------------------------
# Condición: hoy y evolución
# ---------------------------------------------------------------------------
def linea_evolucion(e: pd.DataFrame, materia: str) -> str:
    """Pequeño gráfico de escalones (SVG): % de alumnos en cada condición después
    de cada evaluación. Pasando el mouse por un punto se ve el detalle."""
    fechas = sorted(e["fecha"].unique())
    d0, d1 = pd.Timestamp(fechas[0]), pd.Timestamp(fechas[-1])
    x = (lambda d: 20 + (pd.Timestamp(d) - d0) / (d1 - d0) * 215) if d1 > d0 else (lambda d: 127.5)
    y = lambda p: 160 - p * 1.4  # noqa: E731
    grilla = "".join(f'<line x1="20" y1="{y(v)}" x2="235" y2="{y(v)}" stroke="{"#D9D6CF" if v == 0 else "#F1EFEA"}"/>'
                     f'<text x="14" y="{y(v) + 4}" text-anchor="end" font-size="10" fill="{comp.TEXTO_3}">{v}</text>'
                     for v in (100, 50, 0))
    trazos = ""
    for cond in ["Promociona", "Regular", "Libre"]:
        c = e[e["condicion"] == cond].sort_values("fecha")
        if c.empty:
            continue
        pts, puntos_svg, prev = [], "", None
        for r in c.itertuples():
            if prev is not None:
                pts.append(f"{x(r.fecha):.1f},{y(prev):.1f}")
            pts.append(f"{x(r.fecha):.1f},{y(r.pct):.1f}")
            prev = r.pct
            instr = " + ".join(comp.nombre_corto(s) for s in r.instrumentos.split(" + "))
            puntos_svg += (f'<circle cx="{x(r.fecha):.1f}" cy="{y(r.pct):.1f}" r="3" '
                           f'fill="{comp.COLORES_CONDICION[cond]}"><title>{pd.Timestamp(r.fecha):%d/%m} · {cond} '
                           f'{comp.pct(r.pct)} ({r.alumnos} alumnos) · después de: {esc(instr)}</title></circle>')
        trazos += (f'<polyline points="{" ".join(pts)}" fill="none" stroke="{comp.COLORES_CONDICION[cond]}" '
                   f'stroke-width="2.2" stroke-linejoin="round"/>{puntos_svg}')
    etiquetas = (f'<text x="20" y="180" font-size="10" fill="{comp.TEXTO_3}">{d0:%d/%m}</text>'
                 + (f'<text x="235" y="180" text-anchor="end" font-size="10" fill="{comp.TEXTO_3}">{d1:%d/%m}</text>'
                    if d1 > d0 else ""))
    return (f'<svg viewBox="0 0 240 190" width="100%" height="190" role="img" font-family="Inter, sans-serif" '
            f'aria-label="Evolución de la condición en {esc(materia)}" style="display:block">'
            f"{grilla}{trazos}{etiquetas}</svg>")


with tab_cond:
    filas_barras = ""
    for materia in materias:
        d_m = dist[dist["asignatura"] == materia]
        segs = ""
        for cond in CONDICIONES:
            r = d_m[d_m["condicion"] == cond]
            p = float(r["pct"].iloc[0]) if len(r) else 0
            n_c = int(r["alumnos"].iloc[0]) if len(r) else 0
            texto = (f'<span class="num" style="font-size:12px;font-weight:600;color:#FFFFFF">{comp.pct(p, 0)}</span>'
                     if p >= 8 else "")
            segs += (f'<span title="{cond}: {num(n_c)} alumnos ({comp.pct(p)})" style="width:{p:.2f}%;'
                     f'background:{comp.COLORES_CONDICION[cond]};display:flex;align-items:center;'
                     f'justify-content:center">{texto}</span>')
        filas_barras += (f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'
                         f'<span style="flex:0 0 110px;font-size:12px;font-weight:600" title="{esc(materia)}">'
                         f'{esc(comp.nombre_materia_corto(materia))}</span>'
                         f'<span style="flex:1 1 auto;display:flex;height:30px;border-radius:7px;overflow:hidden">'
                         f'{segs}</span></div>')
    leyenda = "".join(f'<span style="font-size:11px;color:{comp.TEXTO_CONDICION[c]}">{comp.forma(c, tam=10)}{c}</span>'
                      for c in CONDICIONES)
    cortes_txt = "; ".join(f"{comp.nombre_materia_corto(m)} {ESQUEMA[m]['cortes']['Regular']} / "
                           f"{ESQUEMA[m]['cortes']['Promociona']}" for m in materias)
    comp.pintar(f"""
    <div class="tc-card" style="padding:18px;margin-bottom:14px">
      <h4>Condición al {corte_txt}</h4>
      <p class="tc-texto" style="margin:0 0 18px">De mejor a peor, con 0 en lo no rendido. El orden de los colores es
      el mismo en toda la app: promociona, regular, libre. Cortes de Regular / Promociona: {cortes_txt}.</p>
      {filas_barras}
      <div class="tc-leyenda" style="padding-top:14px;border-top:1px solid {comp.BORDE_SUAVE}">{leyenda}</div>
    </div>""")

    evo = comp.metrica("evolucion_condicion")
    graficos = ""
    for materia in materias:
        e = evo[(evo["asignatura"] == materia) & evo["condicion"].isin(["Promociona", "Regular", "Libre"])]
        if e.empty:
            continue
        ini, fin = e[e["fecha"] == e["fecha"].min()], e[e["fecha"] == e["fecha"].max()]
        val = lambda df, c: float(df.loc[df["condicion"] == c, "pct"].iloc[0])  # noqa: E731
        promo_i, promo_f, libre_i, libre_f = (val(ini, "Promociona"), val(fin, "Promociona"),
                                              val(ini, "Libre"), val(fin, "Libre"))
        alarma = promo_i - promo_f >= 15 or libre_f - libre_i >= 15
        texto = (f"Promociona pasó del {comp.pct(promo_i, 0)} al {comp.pct(promo_f, 0)} y Libre, del "
                 f"{comp.pct(libre_i, 0)} al {comp.pct(libre_f, 0)}."
                 if e["fecha"].nunique() > 1 else "Una sola evaluación hasta ahora.")
        estilo = f"font-weight:500;color:{comp.ROJO}" if alarma else ""
        graficos += (f'<div><p style="margin:0 0 8px;display:flex;align-items:center;gap:8px;font-size:13px;'
                     f'font-weight:600">{comp.swatch(materia)}{esc(materia)}</p>{linea_evolucion(e, materia)}'
                     f'<p class="tc-texto" style="margin-top:6px;{estilo}">{texto}</p></div>')
    comp.pintar(f"""
    <div class="tc-card" style="padding:18px">
      <h4>Cómo se fue moviendo</h4>
      <p class="tc-texto" style="margin:0 0 18px;max-width:84ch">Un punto por cada fecha de evaluación ya tomada: qué
      condición tenía cada alumno ese día, con los instrumentos que había hasta entonces y 0 en lo no rendido. Las
      caídas de Promociona después de un parcial o un recuperatorio son las que conviene mirar.</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px">{graficos}</div>
    </div>""")

# ---------------------------------------------------------------------------
# Tabla: todos los instrumentos (ordenable) y descargas
# ---------------------------------------------------------------------------
with tab_tabla:
    with st.container(key="tarjeta_tabla"):
        izq, der = st.columns([3, 1], vertical_alignment="bottom")
        with izq:
            comp.pintar('<h4 style="margin:0 0 3px;font:600 15px \'Space Grotesk\',Inter,sans-serif">Todos los '
                        'instrumentos</h4><p class="tc-texto" style="color:#6B6861">Promedio, mediana, mínimo y '
                        'máximo sobre 100, solo entre quienes rindieron. Hacé clic en una columna para ordenar.</p>')
        with der, st.container(horizontal=True, horizontal_alignment="right"):
            comp.boton_csv(tabla, f"rendimiento_por_instrumento_{f.fecha_corte:%Y%m%d}", "Descargar CSV")
        vista = tabla.assign(Materia=tabla["Materia"].map(comp.SIGLAS))
        st.dataframe(vista, hide_index=True, width="stretch", column_config={
            "Fecha": st.column_config.DateColumn(format="DD/MM"),
            "Puntaje máximo": st.column_config.NumberColumn("Pts", format="%d"),
            "% de la base": st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100),
            **{c: st.column_config.NumberColumn(format="%.1f") for c in
               ["Promedio", "Mediana", "Mínimo", "Máximo", "% aprobada"]}})
        st.caption("La fecha es la mediana de los intentos registrados en la trazabilidad. \"% aprobada\" sale de "
                   "la columna Observaciones del Excel. El recuperatorio aparece aparte, con su propia nota.",
                   help="Decisiones: D18 (fecha del instrumento), D20 (recuperatorio), D22 (solo quienes rindieron).")
