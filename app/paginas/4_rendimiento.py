"""Dashboard 2 (del plan): Rendimiento académico.

Pregunta principal, a la fecha de corte: ¿la condición se explica por las notas o
por las entregas?, y ¿a quién conviene intervenir?

  Encabezado          título, "Notas y condición al dd/mm · materia" y el menú Descargar
                      (resumen por instrumento y notas por alumno, en CSV).
  Mensaje             franja con el titular armado con los números: cuánto sacan los que
                      entregan vs. cuánto baja la nota por los 0 de lo no entregado y por
                      los que no rindieron nada.
  KPIs                Tasa de entrega (con la caída del primer instrumento al último
                      cerrado), Dejaron de entregar y Libres recuperables (las dos con la
                      lista de alumnos y su CSV: a quién intervenir) y Sin ninguna entrega.
  Por materia         nota de quienes rindieron en la escala de la materia (Álgebra,
                      proyectada), barra de condición y entrega primero -> último cerrado.
  Pestañas
    Por instrumento            una tabla por materia con un título que dice lo principal:
                               barra de entrega (gris / ámbar / rojo; los abiertos, rayados),
                               promedio, % con nota >= 60 y caja con las notas sobre 100.
    Distribución               histograma en la escala de cada materia, por condición, con
                               los cortes, y el resumen estadístico.
    Evolución de la condición  % por condición en cada fecha de evaluación (escalones).

Reglas: instrumento cerrado = su fecha pasó hace DIAS_CIERRE días o más (D82); aprobado =
nota >= APROBADO_PCT sobre 100 (D81); libres recuperables a menos de MARGEN_RECUPERABLE
puntos del corte de Regular (D83). El umbral de inactividad no se usa: Inicio.py lo oculta.
Diseño: componentes_rendimiento.py (clases tc-*). Los textos se arman con los números.
Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo agrega y dibuja.
"""
import pandas as pd
import streamlit as st

import componentes_rendimiento as comp
from componentes_rendimiento import esc, num
from src.config import APROBADO_PCT, DIAS_CIERRE, ESQUEMA, MARGEN_RECUPERABLE, ULTIMOS_CERRADOS
from src.textos import enumerar

f = comp.filtros()
notas = comp.metrica("nota_final")
instrumentos = comp.metrica("promedio_por_instrumento")
rendidas = comp.metrica("notas_rendidas")
dist = comp.metrica("distribucion_condicion")
caida = comp.metrica("caida_entrega").set_index("asignatura")
dejaron = comp.metrica("dejaron_de_entregar")
recuperables = comp.metrica("libres_recuperables")

instrumentos["nombre"] = instrumentos["instrumento"].map(comp.nombre_corto)
rendidas["nombre"] = rendidas["instrumento"].map(comp.nombre_corto)
corte_txt = pd.Timestamp(f.fecha_corte).strftime("%d/%m")
SIGLAS = comp.SIGLAS
GRIS = comp.NEUTRO   # barras de entrega que están bien: gris, para no confundirse con los colores de materia
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]

# Tablas para descargar (menú Descargar del encabezado).
COLUMNAS_TABLA = {
    "asignatura": "Materia", "nombre": "Instrumento", "fecha_instrumento": "Fecha", "cerrado": "Cerrado",
    "puntaje_maximo": "Puntaje máximo", "rindieron": "Rindieron", "pct_rindio": "% de la base",
    "promedio_pct": "Promedio", "mediana_pct": "Mediana", "minimo_pct": "Mínimo", "maximo_pct": "Máximo",
    "pct_aprobada": f"% con nota >= {APROBADO_PCT}", "pct_aprobada_lms": "% aprobada (LMS)",
}
tabla = instrumentos[list(COLUMNAS_TABLA)].rename(columns=COLUMNAS_TABLA)
detalle_alumnos = rendidas.drop(columns=["orden", "instrumento"]).rename(columns={"nombre": "instrumento"})


def descargas() -> None:
    if instrumentos.empty:
        return
    with st.popover("Descargar", icon=":material/download:"):
        comp.boton_csv(tabla, f"rendimiento_por_instrumento_{f.fecha_corte:%Y%m%d}", "Resumen por instrumento")
        comp.boton_csv(detalle_alumnos, f"notas_por_alumno_{f.fecha_corte:%Y%m%d}", "Notas por alumno")


comp.encabezado("Rendimiento académico", f"Notas y condición al {corte_txt} · {esc(f.materia)}",
                acciones=descargas)

if instrumentos.empty:
    st.info(f"Al {comp.fmt_fecha(f.fecha_corte)} todavía no se tomó ninguna evaluación en "
            f"{f.materia.lower()}. Mové la fecha de corte para ver notas.", icon=":material/event_busy:")
    st.stop()

materias = [m for m in f.materias if m in set(instrumentos["asignatura"])]
_presentes = set(dist.loc[(dist["alumnos"] > 0) & dist["asignatura"].isin(materias), "condicion"])
CONDICIONES = [c for c in comp.COLORES_CONDICION if c in _presentes]


# ---------------------------------------------------------------------------
# Formatos y reglas de color (el semáforo evalúa; el color de materia identifica)
# ---------------------------------------------------------------------------
def pct_corto(v, decimales: int = 1) -> str:
    """'100 %' en vez de '100,0 %'; '—' si no hay dato."""
    if v is None or pd.isna(v):
        return "—"
    return comp.pct(v, 0 if float(v).is_integer() else decimales)


def pp(v) -> str:
    """Diferencia en puntos porcentuales con signo: '−59 pp', '+3 pp', '0 pp'."""
    if v is None or pd.isna(v):
        return "—"
    r = round(float(v))
    return ("−" if r < 0 else "+" if r > 0 else "") + f"{num(abs(r))} pp"


def puntos(pct_valor: float, maximo: float) -> str:
    """Nota sobre 100 -> puntos del instrumento (75 sobre 100 con máximo 10 -> '7,5')."""
    p = round(pct_valor * maximo / 100, 1)
    return num(p, 0 if p == int(p) else 1)


def plural(n: int, singular: str, plural_: str | None = None) -> str:
    return f"{num(n)} {singular if n == 1 else (plural_ or singular + 's')}"


def color_entrega(p: float) -> str:
    """Barra de 'rindieron': rojo si lo rindió menos del 30 %, ámbar si menos del 50 %, si no gris."""
    return comp.CRITICO if p < 30 else comp.ATENCION if p < 50 else GRIS


def estilo_entrega(p: float) -> str:
    if p < 30:
        return f"font-weight:600;color:{comp.ROJO}"
    return f"color:{comp.AMBAR}" if p < 50 else ""


def barra_entrega(p: float, abierto: bool, recuperatorio: bool = False) -> str:
    """Barra de entrega de 72 px; los instrumentos abiertos van rayados y en gris, y el
    recuperatorio en gris (lo rinden solo quienes lo necesitan: que sea bajo no es alarma)."""
    v = max(0.0, min(100.0, float(p)))
    if abierto:
        fondo = f"repeating-linear-gradient(135deg,{GRIS} 0 3px,{comp.aclarar(GRIS, .6)} 3px 6px)"
    else:
        fondo = GRIS if recuperatorio else color_entrega(p)
    return (f'<span class="tc-barra" style="width:72px;height:8px">'
            f'<span style="width:{v:.1f}%;background:{fondo}"></span></span>')


def color_aprobada(p: float) -> str:
    return comp.ROJO if p < 60 else comp.AMBAR if p < 85 else comp.TEXTO


def caja(valores: pd.Series, color: str = comp.ACCION) -> str:
    """Mini boxplot en SVG (sobre 100): bigotes de mínimo a máximo, caja del 25 % al
    75 %, línea en la mediana y punto en el promedio."""
    if valores.empty:
        return '<span class="tc-chico">—</span>'
    mn, q1, me, q3, mx = valores.quantile([0, .25, .5, .75, 1]).tolist()
    prom = valores.mean()
    x = lambda v: 2 + v / 100 * 216  # noqa: E731
    ancho = max(x(q3) - x(q1), 3)
    texto = (f"mín {num(mn, 1)} · 25 % {num(q1, 1)} · mediana {num(me, 1)} · 75 % {num(q3, 1)} · "
             f"máx {num(mx, 1)} · promedio {num(prom, 1)} (sobre 100)")
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


def barra_condicion(materia: str, alto: int = 24) -> str:
    """Barra apilada Promociona / Regular / Libre de una materia. El % va adentro si el
    segmento tiene 8 % o más; si no, al lado de la barra, con su forma y su color."""
    d_m = dist[dist["asignatura"] == materia]
    segs, afuera = "", []
    for cond in CONDICIONES:
        r = d_m[d_m["condicion"] == cond]
        p = float(r["pct"].iloc[0]) if len(r) else 0
        n_c = int(r["alumnos"].iloc[0]) if len(r) else 0
        if not n_c:
            continue
        adentro = p >= 8
        texto = (f'<span class="num" style="font-size:11px;font-weight:600;color:#FFFFFF">{comp.pct(p, 0)}</span>'
                 if adentro else "")
        segs += (f'<span title="{cond}: {num(n_c)} alumnos ({comp.pct(p)})" style="width:{p:.2f}%;'
                 f'background:{comp.COLORES_CONDICION[cond]};display:flex;align-items:center;'
                 f'justify-content:center">{texto}</span>')
        if not adentro:
            afuera.append(f'<span class="num" title="{cond}: {num(n_c)} alumnos" style="display:inline-flex;'
                          f'align-items:center;gap:4px;font-size:11px;font-weight:600;'
                          f'color:{comp.TEXTO_CONDICION[cond]}">{comp.forma(cond, tam=10)}{comp.pct(p, 0)}</span>')
    return (f'<div style="display:flex;align-items:center;gap:8px">'
            f'<span style="flex:1 1 auto;display:flex;height:{alto}px;border-radius:6px;overflow:hidden">{segs}</span>'
            + (f'<span style="display:flex;gap:8px;flex:none">{"".join(afuera)}</span>' if afuera else "")
            + "</div>")


def lista_alumnos(df: pd.DataFrame, columnas: dict, archivo: str, decimales: dict | None = None) -> None:
    """Tabla de alumnos (Styler es-AR) y su CSV, para los expanders de los KPIs."""
    vista = df.assign(asignatura=df["asignatura"].map(SIGLAS),
                      inscripto=df["inscripto"].map({True: "Sí", False: "No"}))
    for col in vista.columns:
        if pd.api.types.is_datetime64_any_dtype(vista[col]):
            vista[col] = vista[col].dt.strftime("%d/%m")
    vista = vista[list(columnas)].rename(columns=columnas)
    st.dataframe(comp.estilo_tabla(vista, decimales), hide_index=True, width="stretch",
                 height=min(36 * len(vista) + 40, 330))
    comp.boton_csv(df, f"{archivo}_{f.fecha_corte:%Y%m%d}", "Descargar CSV")


def nombre_breve(materia: str) -> str:
    """'Álgebra' completo; las otras, por la sigla (AED, PYE)."""
    return materia if len(materia) <= 10 else SIGLAS[materia]


# ---------------------------------------------------------------------------
# Mensaje: ¿pesan más las notas o las entregas?
# ---------------------------------------------------------------------------
cuentan = instrumentos[~instrumentos["es_recuperatorio"]]
con_rendidos = cuentan[cuentan["rindieron"] > 0]
if con_rendidos.empty:
    st.info("Ya se tomaron evaluaciones, pero todavía nadie las rindió.", icon=":material/event_busy:")
    st.stop()
cerrados = cuentan[cuentan["cerrado"]]
base_tasa = cerrados if len(cerrados) else cuentan
tasa_entrega = base_tasa["rindieron"].sum() / base_tasa["base"].sum() * 100

con_condicion = notas[notas["nota_final"].notna()]
con_nota = con_condicion[con_condicion["rendidos"] > 0]
total_base, n_rindieron = len(con_condicion), len(con_nota)
sin_rendir = total_base - n_rindieron
nota_todos, nota_rindieron = con_condicion["nota_pct"].mean(), con_nota["nota_pct"].mean()
aprobada = (con_rendidos["pct_aprobada"] * con_rendidos["rindieron"]).sum() / con_rendidos["rindieron"].sum()
p_min, p_max = con_rendidos["promedio_pct"].min(), con_rendidos["promedio_pct"].max()

rango = num(p_min, 0) if round(p_min) == round(p_max) else f"{num(p_min, 0)}–{num(p_max, 0)}"
promedian = "los instrumentos promedian" if len(con_rendidos) > 1 else "el instrumento promedia"


def cola(preposicion: str) -> str:
    """', y a 48,9 si se suman los 101 que no rindieron nada' (vacío si no hay ninguno)."""
    if not sin_rendir:
        return ""
    los_que = ("se suma el alumno que no rindió nada" if sin_rendir == 1
               else f"se suman los {num(sin_rendir)} que no rindieron nada")
    return f", y {preposicion}{num(nota_todos, 1)} si {los_que}"


pesan_entregas = nota_rindieron <= p_min - 5   # los 0 por no entregar bajan la nota debajo del peor instrumento
if aprobada >= 80 and pesan_entregas:
    titular = "El problema no son las notas, son las entregas."
    lectura = (f"Quien entrega aprueba ({promedian} {rango} y el {pct_corto(aprobada, 0)} de lo entregado tiene "
               f"{APROBADO_PCT} o más), pero los 0 por no entregar bajan la nota a {num(nota_rindieron, 1)}{cola('a ')}.")
elif aprobada < 70:
    titular = "Además de las entregas, cuesta aprobar."
    lectura = (f"Solo el {pct_corto(aprobada, 0)} de lo entregado tiene {APROBADO_PCT} o más ({promedian} {rango}). "
               f"Con los 0 por no entregar, la nota de quienes rindieron algo queda en "
               f"{num(nota_rindieron, 1)}{cola('en ')}.")
else:
    titular = ""
    lectura = (f"Entre quienes {'los' if len(con_rendidos) > 1 else 'lo'} rinden, {promedian} {rango} y el "
               f"{pct_corto(aprobada, 0)} de lo entregado tiene {APROBADO_PCT} o más. "
               + ("Con los 0 por no entregar, la nota de quienes rindieron algo es " if len(con_rendidos) > 1
                  else "La nota de quienes lo rindieron es ")
               + f"{num(nota_rindieron, 1)}{cola('')}.")
ayuda_mensaje = (f"Todo sobre 100 (Álgebra también, para comparar materias). Promedio de cada instrumento: solo quienes "
                 f"lo rindieron, sin recuperatorios. Aprobado: nota de {APROBADO_PCT} o más sobre 100. Nota de "
                 f"quienes rindieron: promedio de los {num(n_rindieron)} alumnos con al menos una evaluación rendida, con "
                 f"0 en las que no rindieron. La última cifra suma a toda la base ({num(total_base)}).")
comp.pintar(f"""
<section aria-label="Mensaje principal" style="margin:4px 0 14px">
  <p class="tc-aviso" style="font-size:14px;display:flex;gap:8px;align-items:flex-start">
    <span style="flex:1 1 auto">{f'<strong style="font-weight:600">{titular}</strong> ' if titular else ''}{lectura}</span>
    {comp.ayuda(ayuda_mensaje)}</p>
</section>
""")

# ---------------------------------------------------------------------------
# KPIs: tasa de entrega, dejaron de entregar, libres recuperables, sin ninguna entrega
# ---------------------------------------------------------------------------
con_caida = caida[caida["diferencia_pp"].notna()]
if len(con_caida):
    pct_ini = con_caida["rindieron_primero"].sum() / con_caida["base_primero"].sum() * 100
    pct_fin = con_caida["rindieron_ultimo"].sum() / con_caida["base_ultimo"].sum() * 100
    por_materia = " · ".join(f"{SIGLAS[m]} {pct_corto(r.pct_primero, 0)} → {pct_corto(r.pct_ultimo, 0)}"
                             for m, r in con_caida.iterrows())
    detalle_tasa = (f'<span class="tc-delta" title="{esc(por_materia)}">primera → última: {pp(pct_fin - pct_ini)}'
                    f'</span><br>{num(base_tasa["rindieron"].sum())} de {num(base_tasa["base"].sum())} entregas posibles')
else:
    detalle_tasa = (f'{num(base_tasa["rindieron"].sum())} de {num(base_tasa["base"].sum())} entregas posibles. '
                    + ("Todavía no hay dos instrumentos cerrados para comparar." if len(cerrados)
                       else "Ningún instrumento cerrado: incluye los que siguen abiertos."))
tip_tasa = (f"Evaluaciones rendidas / (alumnos de la base × instrumentos cerrados), sin recuperatorios. Cerrado = su "
            f"fecha pasó hace {DIAS_CIERRE} días o más; los abiertos todavía reciben entregas y no cuentan. "
            "La variación compara el % de la base que rindió el primer instrumento con el que rindió el último "
            "cerrado, sumando las materias.")

con_dejaron = caida[caida["dejaron"].notna()]
tip_dejaron = (f"Alumnos de la base que rindieron al menos un instrumento cerrado (sin contar recuperatorios) y "
               f"ninguno de los {ULTIMOS_CERRADOS} últimos cerrados ni de los que siguen abiertos. Solo en las materias "
               f"con {ULTIMOS_CERRADOS + 1} o más instrumentos cerrados.")
if len(con_dejaron):
    n_dej, n_emp = int(con_dejaron["dejaron"].sum()), int(con_dejaron["empezaron"].sum())
    valor_dejaron = num(n_dej)
    detalle_dejaron = f"{pct_corto(n_dej / n_emp * 100 if n_emp else 0, 1)} de los {num(n_emp)} que habían empezado"
    faltan = [SIGLAS[m] for m in materias if m not in con_dejaron.index]
    if faltan:
        detalle_dejaron += f" · sin dato en {enumerar(faltan)} (menos de {ULTIMOS_CERRADOS + 1} cerrados)"
else:
    valor_dejaron = "—"
    detalle_dejaron = f"Hace falta que la materia tenga {ULTIMOS_CERRADOS + 1} instrumentos cerrados."

por_materia_rec = recuperables.groupby("asignatura").size().reindex(materias, fill_value=0)
detalle_rec = (" · ".join(f"{num(n)} {SIGLAS[m]}" for m, n in por_materia_rec.items()) + "<br>"
               if len(materias) > 1 else "") + f"a menos de {MARGEN_RECUPERABLE} puntos de Regular"
tip_rec = (f"Alumnos Libres con al menos una evaluación rendida y nota a menos de {MARGEN_RECUPERABLE} puntos del corte "
           "de Regular, en la escala de cada materia. Son los que pueden cambiar de condición con el próximo "
           "instrumento.")
tip_sin = ("Alumnos de la base sin ninguna evaluación rendida a la fecha de corte: tienen 0 en todo y quedan Libres. "
           + ("Un alumno que cursa dos materias cuenta dos veces." if len(materias) > 1 else ""))

COLUMNAS_DEJARON = {"asignatura": "Materia", "id_alumno": "ID", "nombre": "Alumno", "inscripto": "Inscripto",
                    "ultimo_rendido": "Último rendido", "fecha_ultimo_rendido": "Fecha", "rendidos_txt": "Rendidos",
                    "nota_final": "Nota", "escala": "Sobre", "condicion": "Condición"}
COLUMNAS_RECUPERABLES = {"asignatura": "Materia", "id_alumno": "ID", "nombre": "Alumno", "inscripto": "Inscripto",
                         "nota_final": "Nota", "escala": "Sobre", "faltan": "Le faltan", "rendidos_txt": "Rendidos"}


def con_rendidos_txt(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(rendidos_txt=df["rendidos"].astype(str) + " de " + df["instrumentos"].astype(str))


# Las 4 tarjetas en una grilla HTML (mismo alto); las listas, en una fila aparte debajo.
comp.kpis([
    comp.kpi("Tasa de entrega", comp.pct(tasa_entrega), detalle_tasa, tip_tasa),
    comp.kpi("Dejaron de entregar", valor_dejaron, detalle_dejaron, tip_dejaron, alerta=True),
    comp.kpi("Libres recuperables", num(len(recuperables)), detalle_rec, tip_rec),
    comp.kpi("Sin ninguna entrega", num(sin_rendir),
             f"{pct_corto(sin_rendir / total_base * 100 if total_base else 0, 1)} de la base "
             f"({num(total_base)} alumnos)", tip_sin),
])
if not dejaron.empty or not recuperables.empty:
    izq, der = st.columns(2)
    if not dejaron.empty:
        with izq.expander(f"Ver quiénes dejaron de entregar ({num(len(dejaron))})", icon=":material/person_off:"):
            lista_alumnos(con_rendidos_txt(dejaron), COLUMNAS_DEJARON, "dejaron_de_entregar", {"Nota": 1})
    if not recuperables.empty:
        with der.expander(f"Ver libres recuperables ({num(len(recuperables))})", icon=":material/trending_up:"):
            lista_alumnos(con_rendidos_txt(recuperables), COLUMNAS_RECUPERABLES, "libres_recuperables",
                          {"Nota": 1, "Le faltan": 1})

# ---------------------------------------------------------------------------
# Por materia: nota en su escala, condición y caída de la entrega
# ---------------------------------------------------------------------------
tarjetas_materia = ""
for materia in materias:
    n_m = con_condicion[con_condicion["asignatura"] == materia]
    r_m = n_m[n_m["rendidos"] > 0]
    escala = ESQUEMA[materia]["total_max"]
    proyectada = (f'<span class="tc-proyectada">proyectada'
                  f'{comp.ayuda(f"Puntos obtenidos / puntos posibles al corte × {escala}.")}</span>'
                  if ESQUEMA[materia]["metodo"] == "acumulativo" else "")
    if materia in caida.index:
        c = caida.loc[materia]
        abiertos = f" · {plural(int(c['abiertos']), 'abierto')}" if c["abiertos"] else ""
        titulo_c = esc(f"Primer instrumento: {comp.nombre_corto(c['primero'])} · último cerrado: "
                       f"{comp.nombre_corto(c['ultimo'])}")
        if pd.notna(c["diferencia_pp"]):
            entrega = (f'<span title="{titulo_c}">Entrega {pct_corto(c["pct_primero"], 0)} → '
                       f'{pct_corto(c["pct_ultimo"], 0)} ({pp(c["diferencia_pp"])})</span>{abiertos}')
        else:
            entrega = f'Entrega {pct_corto(c["pct_primero"], 0)}: un solo instrumento cerrado{abiertos}'
    else:
        entrega = "Entrega: todavía no hay instrumentos cerrados"
    nota_txt = (f'{num(r_m["nota_final"].mean(), 0)} <small>/ {escala}</small>' if len(r_m)
                else f'— <small>/ {escala}</small>')
    tarjetas_materia += f"""
    <div class="tc-card chica">
      <div style="display:flex;align-items:center;gap:8px;margin:0 0 10px">
        {comp.swatch(materia)}<span style="flex:1 1 auto;font-size:12px;font-weight:600">{esc(materia)}</span>
        <span class="num tc-chico">base {num(len(n_m))}</span></div>
      <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:8px">
        <p class="tc-kpi-num" style="font-size:26px">{nota_txt}</p>{proyectada}</div>
      <p class="tc-texto" style="margin:2px 0 12px">nota de los {num(len(r_m))} que rindieron algo</p>
      {barra_condicion(materia)}
      <p class="tc-texto num" style="margin-top:10px">{entrega}</p>
    </div>"""

leyenda_cond = "".join(f'<span style="font-size:11px;color:{comp.TEXTO_CONDICION[c]}">{comp.forma(c, tam=10)}{c}</span>'
                       for c in CONDICIONES)
cortes_txt = " · ".join(f"{nombre_breve(m)} {ESQUEMA[m]['cortes']['Regular']}/{ESQUEMA[m]['cortes']['Promociona']}"
                        for m in materias)
ayuda_base = ("Alumnos de la base de cada materia a la fecha de corte, con 0 en lo no rendido."
              + (" Un alumno que cursa dos materias cuenta dos veces." if len(materias) > 1 else ""))
comp.pintar(f"""
<section aria-label="Por materia" style="margin-top:14px">
  <div style="display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;justify-content:space-between;margin-bottom:10px">
    <p class="tc-etiqueta" style="margin:0">Por materia · condición al {corte_txt}</p>
    <span class="num tc-chico" style="display:inline-flex;align-items:center;gap:5px">base total:
      {plural(total_base, 'alumno')}{comp.ayuda(ayuda_base)}</span></div>
  <div class="tc-grilla" style="margin-bottom:8px">{tarjetas_materia}</div>
  <div style="display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;margin-bottom:18px">
    <div class="tc-leyenda" style="gap:12px">{leyenda_cond}</div>
    <span class="tc-chico">Cortes Regular / Promociona: {cortes_txt}</span></div>
</section>
""")

tab_inst, tab_dist, tab_cond = st.tabs(["Por instrumento", "Distribución", "Evolución de la condición"])

# ---------------------------------------------------------------------------
# Por instrumento: una tabla por materia con la caja de cada instrumento
# ---------------------------------------------------------------------------
with tab_inst:
    leyenda_caja = ('<svg viewBox="0 0 28 14" width="28" height="14" aria-hidden="true">'
                    '<line x1="1" y1="7" x2="27" y2="7" stroke="#A8A49B" stroke-width="1.2"/>'
                    f'<rect x="8" y="2" width="12" height="10" rx="2" fill="{comp.aclarar(comp.ACCION)}" '
                    f'stroke="{comp.ACCION}" stroke-width="1.2"/>'
                    f'<line x1="15" y1="2" x2="15" y2="12" stroke="{comp.ACCION}" stroke-width="2"/></svg>')
    rayada = (f'<span class="tc-barra" style="width:22px;height:8px"><span style="width:100%;background:'
              f'repeating-linear-gradient(135deg,{GRIS} 0 3px,{comp.aclarar(GRIS, .6)} 3px 6px)"></span></span>')
    comp.pintar(f"""
    <div class="tc-nota" style="display:flex;flex-wrap:wrap;gap:10px 20px;align-items:center;margin-bottom:16px">
      <p style="margin:0;flex:1 1 380px">Barra: % de la base que lo rindió. Caja: notas sobre 100 de quienes lo
      rindieron.</p>
      <div class="tc-leyenda" style="font-size:11px;gap:14px">
        <span style="font-size:11px">{leyenda_caja}mín · 25 % · mediana · 75 % · máx</span>
        <span style="font-size:11px"><span class="tc-swatch" style="background:{comp.TEXTO};border-radius:999px;
        width:8px;height:8px"></span>promedio</span>
        <span style="font-size:11px">{rayada}abierto</span>
      </div>
    </div>""")

    ayuda_aprobo = (f"% de quienes lo rindieron con nota de {APROBADO_PCT} o más sobre 100. No sale de la "
                    "columna Observaciones del Excel: el LMS marca \"aprobada\" con un criterio distinto en cada "
                    "instrumento (en Álgebra y AED, casi cualquier entrega). Pasá el mouse por un valor para ver "
                    "el del LMS.")
    for materia in materias:
        prom = instrumentos[instrumentos["asignatura"] == materia]
        notas_m = rendidas[rendidas["asignatura"] == materia]
        normales = prom[~prom["es_recuperatorio"]]
        rinden = normales[normales["rindieron"] > 0]
        n_rec = int(prom["es_recuperatorio"].sum())
        sigla = SIGLAS[materia]
        meta = (plural(len(normales), "instrumento")
                + (f" + {plural(n_rec, 'recuperatorio')}" if n_rec else "")
                + f" · {plural(int(prom['base'].max()), 'alumno')} en la base")

        # Título: lo principal de la materia, armado con los números.
        if rinden.empty:
            promedios = ""
        elif round(rinden["promedio_pct"].min()) == round(rinden["promedio_pct"].max()):
            promedios = f" con promedio {num(rinden['promedio_pct'].min(), 0)}"
        else:
            promedios = (f" con promedios de {num(rinden['promedio_pct'].min(), 0)} a "
                         f"{num(rinden['promedio_pct'].max(), 0)}")
        c = caida.loc[materia] if materia in caida.index else None
        if c is not None and pd.notna(c["diferencia_pp"]):
            ini, fin = pct_corto(c["pct_primero"], 0), pct_corto(c["pct_ultimo"], 0)
            if c["diferencia_pp"] <= -10:
                titulo = f"{sigla}: la entrega cae de {ini} a {fin}{promedios}"
            elif c["diferencia_pp"] >= 10:
                titulo = f"{sigla}: la entrega sube de {ini} a {fin}{promedios}"
            else:
                titulo = f"{sigla}: la entrega se mantiene ({ini} → {fin}){promedios}"
        elif c is not None:
            titulo = f"{sigla}: un solo instrumento cerrado, lo rindió el {pct_corto(c['pct_primero'], 0)}{promedios}"
        elif len(normales) == 1:
            titulo = (f"{sigla}: el primer instrumento sigue abierto; por ahora lo rindió el "
                      f"{pct_corto(normales['pct_rindio'].iloc[0], 0)}{promedios}")
        else:
            titulo = f"{sigla}: todavía no hay instrumentos cerrados ({plural(len(normales), 'abierto')})"
        secundario = f"{esc(materia)} · {meta}"
        if n_rec:
            rec = prom[prom["es_recuperatorio"]].iloc[0]
            secundario += (f". El recuperatorio lo rindió el {pct_corto(rec['pct_rindio'], 0)} de la base: su nota "
                           "reemplaza a la original en la condición.")

        con_aprobada = prom["pct_aprobada"].notna().any()
        filas = []
        for fila in prom.itertuples():
            en_puntos = pd.notna(fila.puntaje_maximo) and fila.puntaje_maximo != 100
            abierto = not fila.cerrado
            sub = [comp.fmt_fecha(fila.fecha_instrumento)[:5] if pd.notna(fila.fecha_instrumento) else "sin fecha"]
            if en_puntos:
                sub.append(f"{num(fila.puntaje_maximo, 0)} pts")
            if fila.es_recuperatorio:
                sub.append("reemplaza a la original")
            marca = (f' <span class="tc-abierto" title="Su fecha es de hace menos de {DIAS_CIERRE} días: todavía '
                     f'recibe entregas y no entra en la caída de la entrega.">abierto</span>' if abierto else "")
            if fila.rindieron:
                promedio = num(fila.promedio_pct, 1) + (
                    f' <span class="tc-chico" style="color:{comp.TEXTO_4}">· '
                    f'{puntos(fila.promedio_pct, fila.puntaje_maximo)}/{num(fila.puntaje_maximo, 0)}</span>'
                    if en_puntos else "")
            else:
                promedio = "—"
            estilo_txt = "" if abierto or fila.es_recuperatorio else estilo_entrega(fila.pct_rindio)
            celdas = [
                f'<strong style="font-weight:600">{esc(fila.nombre)}</strong><br>'
                f'<span class="tc-chico">{" · ".join(sub)}</span>{marca}',
                f'<span style="display:flex;align-items:center;gap:9px">{barra_entrega(fila.pct_rindio, abierto, fila.es_recuperatorio)}'
                f'<span class="num" style="font-size:12px;font-weight:500;{estilo_txt}">'
                f'{num(fila.rindieron)} · {pct_corto(fila.pct_rindio, 0)}</span></span>',
                f'<span style="font-size:14px;font-weight:600">{promedio}</span>',
            ]
            if con_aprobada:
                celdas.append("—" if pd.isna(fila.pct_aprobada) else
                              f'<span title="Con nota de {APROBADO_PCT} o más: {pct_corto(fila.pct_aprobada)}. '
                              f'Marcadas &quot;aprobada&quot; por el LMS: {pct_corto(fila.pct_aprobada_lms)}." '
                              f'style="font-weight:600;color:{color_aprobada(fila.pct_aprobada)}">'
                              f'{pct_corto(fila.pct_aprobada)}</span>')
            valores = notas_m.loc[notas_m["id_instrumento"] == fila.id_instrumento, "nota_pct_instrumento"]
            celdas.append(caja(valores))
            clase = ' class="tenue"' if fila.es_recuperatorio else ""
            filas.append(f"<tr{clase}>" + "".join(f"<td>{c_}</td>" for c_ in celdas) + "</tr>")
        encabezados = (["Instrumento", "Rindieron", "Promedio"]
                       + ([f'<span style="display:inline-flex;align-items:center;gap:5px">Aprobó'
                           f'{comp.ayuda(ayuda_aprobo)}</span>'] if con_aprobada else [])
                       + ["Distribución de las notas (sobre 100)"])

        comp.pintar(f"""
        <div class="tc-card" style="padding:18px;margin-bottom:14px">
          <h3 style="margin:0 0 4px">{esc(titulo)}</h3>
          <p class="tc-texto" style="margin:0 0 14px;display:flex;align-items:center;gap:7px;color:{comp.TEXTO_3}">
            {comp.swatch(materia)}<span>{secundario}</span></p>
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
    con líneas en los cortes de Regular (punteada) y Promociona (guiones). La barra más
    alta lleva su total arriba; el resto, en el tooltip."""
    escala = ESQUEMA[materia]["total_max"]
    cortes = ESQUEMA[materia]["cortes"]
    ancho = escala / 20
    h = h.assign(barra=(h["nota_final"].clip(0, escala - 1e-6) // ancho).astype(int))
    conteo = h.groupby(["barra", "condicion"]).size().unstack(fill_value=0)
    totales = conteo.sum(axis=1)
    maximo = totales.max() if len(conteo) else 1
    i_max = int(totales.idxmax()) if len(conteo) else -1
    barras = ""
    for i in range(20):
        desde = i * ancho
        fila = conteo.loc[i] if i in conteo.index else pd.Series(dtype=int)
        total = int(fila.sum())
        partes = [(c, int(fila.get(c, 0))) for c in ["Libre", "Regular", "Promociona"] if fila.get(c, 0)]
        detalle = ", ".join(f"{n} {c}" for c, n in partes)
        segs = "".join(f'<div style="height:{n / total * 100:.2f}%;background:{comp.COLORES_CONDICION[c]}"></div>'
                       for c, n in reversed(partes)) if total else ""
        etiqueta = (f'<span class="num" style="position:absolute;bottom:100%;left:50%;transform:translateX(-50%);'
                    f'margin-bottom:2px;font-size:10px;font-weight:600;color:{comp.TEXTO_2};white-space:nowrap">'
                    f'{num(total)}</span>' if i == i_max else "")
        barras += (f'<div title="Nota de {num(desde, 0)} a {num(desde + ancho, 0)}: {plural(total, "alumno")}'
                   f'{" (" + detalle + ")" if detalle else ""}" style="position:relative;flex:1 1 0;'
                   f'height:{total / maximo * 100:.2f}%;display:flex;flex-direction:column">{etiqueta}{segs}</div>')
    lineas = "".join(
        f'<div title="Corte de {nombre}: {corte}" style="position:absolute;top:0;bottom:0;left:{corte / escala * 100:.2f}%;'
        f'border-left:2px {"dotted" if nombre == "Regular" else "dashed"} {comp.TEXTO_2}"></div>'
        for nombre, corte in cortes.items())
    # El máximo de la escala va siempre; un corte pegado al final se corre a la izquierda de su línea.
    marcas = [(0, "left:0")]
    for corte in cortes.values():
        mover = "translateX(-100%);padding-right:3px" if corte > escala * 0.88 else "translateX(-50%)"
        marcas.append((corte, f"left:{corte / escala * 100:.2f}%;transform:{mover}"))
    marcas.append((escala, "right:0"))
    eje = "".join(f'<span class="num tc-chico" style="position:absolute;{pos}">{v}</span>' for v, pos in marcas)
    stats = (f"Mediana {num(h['nota_final'].median(), 1)} · promedio {num(h['nota_final'].mean(), 1)} · "
             f"desvío {num(h['nota_final'].std(), 1)} (sobre {escala})" if len(h) else "Sin alumnos para mostrar.")
    return f"""
    <div>
      <p style="margin:0 0 10px;display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600">
        {comp.swatch(materia)}{esc(comp.nombre_materia_corto(materia))}
        <span class="num tc-chico">{plural(len(h), 'alumno')} · sobre {escala}</span></p>
      <div style="position:relative;display:flex;align-items:flex-end;gap:2px;height:140px;margin-top:18px;
        border-bottom:1px solid #D9D6CF;margin-bottom:7px">{barras}{lineas}</div>
      <div style="position:relative;height:16px;margin-bottom:8px">{eje}</div>
      <p class="tc-texto num">{stats}</p>
    </div>"""


with tab_dist:
    hist = con_condicion
    escalas_txt = enumerar([f"{m} sobre {ESQUEMA[m]['total_max']}"
                            + (", proyectada" if ESQUEMA[m]["metodo"] == "acumulativo" else "")
                            for m in materias if ESQUEMA[m]["total_max"] != 100])
    with st.container(key="tarjeta_distribucion"):
        izq, der = st.columns([3, 2], vertical_alignment="center")
        with izq:
            comp.pintar('<h4 style="margin:0 0 4px;font:600 15px \'Space Grotesk\',Inter,sans-serif">'
                        'Dónde cae cada alumno</h4><p class="tc-texto" style="max-width:78ch">Cada materia en su '
                        f'escala{f" ({esc(escalas_txt)})" if escalas_txt else ""}. Líneas: corte de Regular '
                        '(punteada) y de Promociona (guiones).</p>')
        excluir = False
        if sin_rendir:
            with der, st.container(key="opcion_excluir"):
                etiqueta = ("Excluir al alumno que no rindió nada" if sin_rendir == 1
                            else f"Excluir a los {num(sin_rendir)} que no rindieron nada")
                excluir = st.checkbox(etiqueta, value=True,
                                      help="Tienen 0 por no rendir, no por rendir mal: suelen ser alumnos que "
                                           "abandonaron.")
        if excluir:
            hist = hist[hist["rendidos"] > 0]
            alcance_txt = (f"{num(n_rindieron)} de {plural(total_base, 'alumno')}: "
                           + ("excluido el que no tiene entregas." if sin_rendir == 1
                              else f"excluidos los {num(sin_rendir)} sin entregas."))
        else:
            alcance_txt = (f"{plural(total_base, 'alumno')}"
                           + (f", incluidos los {num(sin_rendir)} sin entregas (con 0)." if sin_rendir > 1 else
                              ", incluido el que no tiene entregas (con 0)." if sin_rendir == 1 else "."))
        if len(materias) > 1:
            alcance_txt += " Un alumno que cursa dos materias cuenta dos veces."
        comp.pintar(f"""
        <div style="display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;justify-content:space-between;
          margin:6px 0 10px">
          <div class="tc-leyenda">{LEYENDA_CONDICION}</div>
          <span class="num tc-chico">{alcance_txt}</span></div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px">
          {''.join(histograma(hist[hist['asignatura'] == m], m) for m in materias)}
        </div>""")

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
               else "toda la base, incluidos los que no rindieron nada (0)" if sin_rendir else "toda la base")
    comp.pintar(f"""
    <div class="tc-card" style="padding:0;overflow:hidden;margin-top:14px">
      <div style="padding:15px 16px 13px"><h4>Resumen estadístico</h4>
        <p class="tc-texto" style="color:{comp.TEXTO_3}">Sobre {alcance}, cada materia en su escala.</p></div>
      {tabla_html(["Materia", "Escala", "Alumnos", "Promedio", "Desvío", "Mínimo", "P25", "Mediana", "P75",
                   "Máximo"], filas)}
    </div>""")


# ---------------------------------------------------------------------------
# Evolución de la condición
# ---------------------------------------------------------------------------
def linea_evolucion(e: pd.DataFrame, materia: str) -> str:
    """Gráfico de escalones (SVG): % de alumnos en cada condición después de cada
    evaluación, con el valor final al lado del último punto. Pasando el mouse por un
    punto se ve el detalle."""
    fechas = sorted(e["fecha"].unique())
    d0, d1 = pd.Timestamp(fechas[0]), pd.Timestamp(fechas[-1])
    x0, x1 = 38, 222
    x = (lambda d: x0 + (pd.Timestamp(d) - d0) / (d1 - d0) * (x1 - x0)) if d1 > d0 else (lambda d: (x0 + x1) / 2)
    y = lambda p: 160 - p * 1.4  # noqa: E731
    grilla = "".join(f'<line x1="{x0}" y1="{y(v)}" x2="{x1}" y2="{y(v)}" stroke="{"#D9D6CF" if v == 0 else "#F1EFEA"}"/>'
                     f'<text x="{x0 - 5}" y="{y(v) + 4}" text-anchor="end" font-size="10" fill="{comp.TEXTO_3}">'
                     f'{v} %</text>' for v in (100, 50, 0))
    trazos, finales = "", []
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
        finales.append([y(prev), prev, cond])
    # Etiquetas del valor final, separadas al menos 11 px para que no se pisen.
    finales.sort()
    for i in range(1, len(finales)):
        finales[i][0] = max(finales[i][0], finales[i - 1][0] + 11)
    etiquetas_fin = "".join(
        f'<text x="{x1 + 6}" y="{yy + 4:.1f}" font-size="10" font-weight="600" '
        f'fill="{comp.TEXTO_CONDICION[cond]}">{comp.pct(p, 0)}</text>' for yy, p, cond in finales)
    etiquetas = (f'<text x="{x0}" y="180" font-size="10" fill="{comp.TEXTO_3}">{d0:%d/%m}</text>'
                 + (f'<text x="{x1}" y="180" text-anchor="end" font-size="10" fill="{comp.TEXTO_3}">{d1:%d/%m}</text>'
                    if d1 > d0 else ""))
    return (f'<svg viewBox="0 0 260 190" width="100%" height="190" role="img" font-family="Inter, sans-serif" '
            f'aria-label="Evolución de la condición en {esc(materia)}" style="display:block">'
            f"{grilla}{trazos}{etiquetas_fin}{etiquetas}</svg>")


with tab_cond:
    evo = comp.metrica("evolucion_condicion")
    graficos, cambios = "", {}
    for materia in materias:
        e = evo[(evo["asignatura"] == materia) & evo["condicion"].isin(["Promociona", "Regular", "Libre"])]
        if e.empty:
            continue
        ini, fin = e[e["fecha"] == e["fecha"].min()], e[e["fecha"] == e["fecha"].max()]
        val = lambda df, c: float(df.loc[df["condicion"] == c, "pct"].iloc[0])  # noqa: E731
        promo_i, promo_f, libre_i, libre_f = (val(ini, "Promociona"), val(fin, "Promociona"),
                                              val(ini, "Libre"), val(fin, "Libre"))
        varias = e["fecha"].nunique() > 1
        if varias:
            cambios[materia] = (promo_i, promo_f, pd.Timestamp(e["fecha"].min()))
        alarma = promo_i - promo_f >= 15 or libre_f - libre_i >= 15
        texto = (f"Promociona pasó del {comp.pct(promo_i, 0)} al {comp.pct(promo_f, 0)} y Libre, del "
                 f"{comp.pct(libre_i, 0)} al {comp.pct(libre_f, 0)}."
                 if varias else "Una sola fecha de evaluación hasta ahora.")
        estilo = f"font-weight:500;color:{comp.ROJO}" if alarma else ""
        graficos += (f'<div><p style="margin:0 0 8px;display:flex;align-items:center;gap:8px;font-size:13px;'
                     f'font-weight:600">{comp.swatch(materia)}{esc(materia)}</p>{linea_evolucion(e, materia)}'
                     f'<p class="tc-texto" style="margin-top:6px;{estilo}">{texto}</p></div>')

    # Título: qué pasa con Promociona, armado con los datos.
    caen = [m for m, (i, f_, _) in cambios.items() if i - f_ >= 5]
    suben = [m for m, (i, f_, _) in cambios.items() if f_ - i >= 5]
    if not cambios:
        titulo_evo = "Una sola fecha de evaluación por materia hasta ahora"
    elif len(caen) == len(cambios):
        desde = min(cambios[m][2] for m in caen)
        todas = len(caen) == len(materias) and len(caen) > 1   # "las tres materias" solo si son todas las que se ven
        donde = ({2: "las dos materias", 3: "las tres materias"}.get(len(caen)) if todas
                 else enumerar([nombre_breve(m) for m in caen]))
        titulo_evo = f"Promociona cae en {donde} desde {MESES[desde.month - 1]}"
    elif caen:
        resto = [m for m in cambios if m not in caen]
        como = "sube" if all(m in suben for m in resto) else "se mantiene" if not any(m in suben for m in resto) \
            else "se mantiene o sube"
        titulo_evo = (f"Promociona cae en {enumerar([nombre_breve(m) for m in caen])}; en "
                      f"{enumerar([nombre_breve(m) for m in resto])} {como}")
    elif len(suben) == len(cambios):
        titulo_evo = f"Promociona sube en {enumerar([nombre_breve(m) for m in suben])}"
    else:
        titulo_evo = "Promociona se mantiene: ninguna materia cae 5 puntos porcentuales o más"
    leyenda_evo = "".join(
        f'<span style="font-size:11px;color:{comp.TEXTO_CONDICION[c]}"><span style="display:inline-block;width:16px;'
        f'height:3px;border-radius:2px;background:{comp.COLORES_CONDICION[c]}"></span>{comp.forma(c, tam=10)}{c}</span>'
        for c in ["Promociona", "Regular", "Libre"])
    comp.pintar(f"""
    <div class="tc-card" style="padding:18px">
      <h4>{esc(titulo_evo)}</h4>
      <p class="tc-texto" style="margin:0 0 12px;max-width:84ch">Condición de cada alumno en cada fecha de evaluación,
      con 0 en lo no rendido. Eje: % de la base de la materia.</p>
      <div class="tc-leyenda" style="gap:14px;margin-bottom:14px">{leyenda_evo}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px">{graficos}</div>
    </div>""")
