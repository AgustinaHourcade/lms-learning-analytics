"""Dashboard 6 (del plan): Ficha individual. Diseño "Analítica académica" (D59).

Responde, para UN alumno y a la fecha de corte: ¿cómo le va en cada materia?,
¿cuánto entra al aula comparado con su curso?, ¿qué hace cuando entra? y
¿qué conviene hacer con él?

  Selector        un desplegable con búsqueda (apellido, nombre, ID o nivel de
                  riesgo); muestra al primero por defecto. Lista solo a los
                  alumnos de la base (D11) de la materia de la barra lateral
                  (D56). Botones anterior / siguiente / siguiente en riesgo.
  Cabecera        nombre, chips (días sin entrar, interacciones, rendidos) y el
                  riesgo de abandono más alto entre sus materias (D58) contra el
                  promedio del curso.
  Estado          tabla con una fila por materia, ordenada por riesgo: condición
                  (semáforo con forma + texto), nota al corte contra el curso,
                  rendidos, actividad de las últimas 8 semanas y riesgo.
  Qué hacer       las alertas de D37 agrupadas por situación (si es la misma en
                  varias materias, es una sola tarjeta), con gravedad y sugerencia.
  Notas           cada instrumento contra el promedio de quienes lo rindieron
                  (D22): Libreta (tarjetas) o Barras; y la tabla con el
                  recuperatorio (D34).
  Actividad       percentil en su curso, evolución semanal contra el promedio
                  por alumno y el reporte de participación (D36).
  Trazabilidad    qué tipo de interacciones hace (contra el curso) y todos sus
                  eventos hasta la fecha de corte, con CSV.

La ficha muestra todas las materias del alumno aunque la barra lateral tenga
una elegida: el filtro de materia solo acota el buscador.
Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
"""
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import componentes as comp
from componentes import esc
from src.config import ESQUEMA

ab = comp.ml_abandono   # constantes del predictor (estados, niveles y horizonte)
GRIS = "#D9D6CF"

# Orden de gravedad del riesgo (para ordenar la tabla y elegir el "peor" de cada alumno).
PRIORIDAD_RIESGO = {ab.YA_ABANDONO: 4, ab.ALTO: 3, ab.MEDIO: 2, ab.BAJO: 1, ab.SIN_ACTIVIDAD: 0}
TEXTO_RIESGO = {ab.YA_ABANDONO: "ya abandonó una materia", ab.ALTO: "riesgo alto", ab.MEDIO: "riesgo medio",
                ab.BAJO: "riesgo bajo", ab.SIN_ACTIVIDAD: "sin actividad"}
EN_RIESGO = {ab.ALTO, ab.YA_ABANDONO}

# Alertas (D37): cómo se agrupan, qué tan graves son y qué conviene hacer.
ORDEN_ALERTAS = ["sin_actividad", "sin_notas", "libre", "inactivo", "no_inscripto"]
GRAVEDAD = {"sin_actividad": "critico", "sin_notas": "critico", "libre": "critico",
            "inactivo": "atencion", "no_inscripto": "neutro"}
NOMBRE_GRAVEDAD = {"critico": "urgente", "atencion": "atención", "neutro": "aviso"}
TITULO_ALERTA = {
    "sin_actividad": "Está inscripto, pero nunca entró ni rindió",
    "sin_notas": "Entra a la plataforma pero no rinde nada",
    "libre": "Queda Libre a la fecha de corte",
    "inactivo": "Dejó de entrar",
    "no_inscripto": "Cursa sin estar inscripto",
}
SUGERENCIA = {
    "sin_actividad": "Sugerido: contactarlo para confirmar si sigue cursando la materia.",
    "sin_notas": "Sugerido: confirmar si tuvo algún problema para acceder a las evaluaciones antes de darlo "
                 "por perdido.",
    "libre": "Sugerido: revisar qué instrumentos no rindió, porque cuentan 0 en la nota final (D15).",
    "inactivo": "Sugerido: un mensaje corto para que vuelva a entrar antes de la próxima evaluación.",
    "no_inscripto": "Sugerido: avisar a la secretaría: cursa y rinde sin figurar en Matriculados.",
}

# Estilos propios de la página (van acá para verse apenas se guarda el archivo).
CSS_FICHA = """
<style>
  .fi-cab {display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start; padding:20px;}
  .fi-quien {flex:1 1 340px; min-width:260px; display:flex; gap:16px; align-items:flex-start;}
  .fi-avatar {width:54px; height:54px; flex:0 0 54px; border-radius:999px; background:#EAF0F8; color:#1B4B8F;
              display:flex; align-items:center; justify-content:center; font:600 17px 'Space Grotesk', Inter, sans-serif;}
  .fi-card h2.fi-nombre {margin:0 0 4px !important; font:600 22px 'Space Grotesk', Inter, sans-serif !important;
                          letter-spacing:-.015em;}
  .fi-sub {margin:0 0 10px; font-size:13px; color:#57544C;}
  .fi-chips {display:flex; flex-wrap:wrap; gap:7px;}
  .fi-riesgo {flex:1 1 300px; min-width:260px; border-radius:11px; padding:14px 16px; border:1px solid;}
  .fi-riesgo-fila {display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:8px;}
  .fi-riesgo-valor {display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap;}
  .fi-riesgo-valor b {font:600 24px 'Space Grotesk', Inter, sans-serif;}
  .fi-riesgo-txt {margin:0; font-size:12px; line-height:1.5;}
  .fi-alerta {display:flex; flex-wrap:wrap; gap:14px; padding:15px 16px; border-top:1px solid #EFEDE8;}
  .fi-alerta-ico {flex:0 0 34px; width:34px; height:34px; border-radius:9px; display:flex; align-items:center;
                  justify-content:center;}
  .fi-alerta-txt {flex:1 1 420px; min-width:240px;}
  .fi-alerta-txt .fi-det {margin:4px 0 0; font-size:13px; line-height:1.5; color:#57544C;}
  .fi-alerta-txt .fi-sug {font-size:12px; font-weight:500; color:#6B6861; margin-top:6px;}
  .fi-libreta-cab {display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:14px;}
  .fi-card .fi-libreta-cab h4 {font:600 15px 'Space Grotesk', Inter, sans-serif !important;}
  .fi-libreta {display:grid; grid-template-columns:repeat(auto-fill, minmax(185px, 1fr)); gap:10px;}
  .fi-nota {border:1px solid #E3E1DC; border-radius:11px; padding:12px; background:#FFFFFF;}
  .fi-nota.fi-falta {border-style:dashed; border-color:#D9D6CF; background:#FBFAF8;}
  .fi-nota-nombre {margin:0 0 8px; font-size:11px; font-weight:500; color:#6B6861; white-space:nowrap; overflow:hidden;
                   text-overflow:ellipsis;}
  .fi-nota-valor {margin:0 0 6px; font:600 20px 'Space Grotesk', Inter, sans-serif; color:#1A1917;}
  .fi-nota-valor small {font:400 12px Inter, sans-serif; color:#8A867C; margin-left:4px;}
  .fi-nota-estado {margin:0 0 10px; font-size:12px; font-weight:600;}
  .fi-nota-curso {margin:7px 0 0; font-size:11px; color:#6B6861;}
  .fi-vacio {display:flex; align-items:center; gap:14px; flex-wrap:wrap; padding:14px 16px; border:1px dashed #D9D6CF;
             border-radius:11px; background:#FBFAF8; font-size:13px; font-weight:500; color:#57544C;}
  .fi-grilla {display:grid; grid-template-columns:repeat(auto-fit, minmax(270px, 1fr)); gap:22px; padding:0 16px 18px;}
  .fi-grilla-titulo {margin:0 0 10px; display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600;
                     color:#1A1917;}
  .fi-pct {display:flex; align-items:center; gap:10px; margin-bottom:10px;}
  .fi-pct-et {flex:0 0 92px; font-size:12px; color:#57544C;}
  .fi-pct-bar {flex:1 1 auto;}
  .fi-pct-val {flex:0 0 96px; text-align:right; line-height:1.25;}
  .fi-pct-val b {font-size:12px; font-weight:600; color:#1A1917;}
  .fi-pct-val span {display:block; font-size:11px; color:#6B6861;}
  .fi-tipo {display:flex; align-items:center; gap:8px; margin-bottom:9px;}
  .fi-tipo-et {flex:0 0 92px; font-size:11px; color:#57544C;}
  .fi-tipo-val {flex:0 0 40px; text-align:right; font-size:11px; font-weight:500;}
  .fi-aviso-rojo {margin:10px 0 0; padding:8px 10px; border-radius:8px; background:#FBE9E6; font-size:11px;
                  font-weight:500; line-height:1.5; color:#93241C;}
</style>
"""


def nombre_corto(instrumento: str) -> str:
    """'👉  Actividad Rápida 1' -> 'Actividad Rápida 1' (saca los emojis del LMS)."""
    return re.sub(r"^[^\wÁÉÍÓÚáéíóúÑñ°]+", "", str(instrumento)).strip()


def en_dos_lineas(texto: str, largo: int = 14) -> str:
    """Parte los nombres largos en dos renglones para el eje x (sin rotar las etiquetas)."""
    if len(texto) <= largo or " " not in texto:
        return texto
    palabras = texto.split(" ")
    corte = min(range(1, len(palabras)), key=lambda i: abs(len(" ".join(palabras[:i])) - len(texto) / 2))
    return " ".join(palabras[:corte]) + "<br>" + " ".join(palabras[corte:])


def signo(x, decimales: int = 1) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + comp.num(abs(x), decimales)


def nota_texto(fila) -> str:
    return "–" if fila.instrumentos == 0 else f"{comp.num(fila.nota_final, 1)}"


def sparkline(valores, color: str, tope: float, ancho: int = 84, alto: int = 24) -> str:
    """Mini línea SVG de las últimas semanas. `tope` es el mismo para todas las materias del
    alumno, así se pueden comparar entre sí."""
    v = [float(x) for x in valores]
    if not v:
        return "–"
    tope, n = max(tope, 1.0), len(v)
    puntos = " ".join(f"{i * (ancho - 2) / max(n - 1, 1) + 1:.1f},{alto - 2 - x / tope * (alto - 4):.1f}"
                      for i, x in enumerate(v))
    detalle = ", ".join(comp.num(x) for x in v)
    return (f'<svg viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" role="img" '
            f'aria-label="Interacciones por semana: {detalle}" style="display:block">'
            f'<title>Interacciones por semana: {detalle}</title>'
            f'<polyline points="{puntos}" fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def texto_riesgo_html(r) -> str:
    """'■ Alto · 43 %' con el color del nivel (D58)."""
    nivel = r["nivel_riesgo"]
    _, color, solido = comp.TONOS_ESTADO[comp.TONO_RIESGO_ESTADO.get(nivel, "neutro")]
    prob = f' · <span class="tfi-num">{comp.pct(r["probabilidad"], 0)}</span>' if pd.notna(r["probabilidad"]) else ""
    return (f'<span style="display:inline-flex;align-items:center;gap:6px;font-weight:600;color:{color};'
            f'white-space:nowrap">{comp.cuadro(solido, 9)}{esc(nivel)}{prob}</span>')


# ---------------------------------------------------------------------------
# Encabezado y selector de alumno
# ---------------------------------------------------------------------------
st.markdown(CSS_FICHA, unsafe_allow_html=True)
cab_izq, cab_der = st.columns([5, 1.4], vertical_alignment="center")
with cab_izq:
    f = comp.encabezado(
        "Ficha individual",
        "Un alumno de un vistazo: en qué condición está en cada materia, qué alertas tiene abiertas "
        "y qué conviene hacer hoy.",
    )

alumnos = comp.metrica("buscar_alumnos", texto="", solo_base=True)
if alumnos.empty:
    st.warning(f"No hay alumnos en la base de {f.materia.lower()}.", icon=":material/person_off:")
    st.stop()

# Riesgo de todos (D58): para el desplegable y el botón "siguiente en riesgo".
riesgo_todos = comp.metrica("riesgo_abandono", asignatura=None)
peor = (riesgo_todos.assign(p=riesgo_todos["nivel_riesgo"].map(PRIORIDAD_RIESGO))
        .sort_values("p").groupby("id_alumno")["nivel_riesgo"].last())
nombres = dict(zip(alumnos["id_alumno"], alumnos["nombre_completo"]))
ids = list(nombres)


def etiqueta(i: str) -> str:
    nivel = peor.get(i)
    return f"{nombres[i]} · {i}" + (f" — {TEXTO_RIESGO[nivel]}" if nivel in TEXTO_RIESGO else "")


def mover(paso: int, solo_riesgo: bool = False) -> None:
    """Anterior / siguiente (o el siguiente en riesgo alto o que ya abandonó), dando la vuelta."""
    actual = st.session_state.get("fi_alumno", ids[0])
    i = ids.index(actual) if actual in ids else -1
    for k in range(1, len(ids) + 1):
        candidato = ids[(i + paso * k) % len(ids)]
        if not solo_riesgo or peor.get(candidato) in EN_RIESGO:
            st.session_state["fi_alumno"] = candidato
            return


if st.session_state.get("fi_alumno") not in ids:   # cambió la materia de la barra
    st.session_state.pop("fi_alumno", None)

with st.container(border=True, key="tarjeta_selector"):
    c_sel, c_ant, c_sig, c_riesgo = st.columns([6, 0.6, 0.6, 2.1], vertical_alignment="bottom")
    id_alumno = c_sel.selectbox(
        f"Alumno · {comp.num(len(alumnos))} en la base", ids, format_func=etiqueta, key="fi_alumno",
        help="Escribí parte del apellido, nombre o ID (ej.: ALU_1263), o «riesgo alto», para filtrar. "
             "Ordenados por apellido; por defecto se muestra el primero.")
    c_ant.button(":material/chevron_left:", key="fi_anterior", help="Alumno anterior", width="stretch",
                 on_click=mover, args=(-1,))
    c_sig.button(":material/chevron_right:", key="fi_siguiente", help="Alumno siguiente", width="stretch",
                 on_click=mover, args=(1,))
    c_riesgo.button("Siguiente en riesgo", key="fi_sig_riesgo", icon=":material/priority_high:", width="stretch",
                    on_click=mover, args=(1, True),
                    help="Salta al próximo alumno de la lista con riesgo alto o que ya abandonó alguna materia.")

ficha = comp.metrica("ficha_alumno", id_alumno=id_alumno)
materias = ficha["materias"]
if materias.empty:  # no pasa con solo_base=True, pero por las dudas
    st.info("Este alumno no está en la base de ninguna materia (D11).", icon=":material/person_off:")
    st.stop()
orden = {m: i for i, m in enumerate(ESQUEMA)}
materias = materias.sort_values("asignatura", key=lambda s: s.map(orden)).reset_index(drop=True)
riesgo = comp.metrica("riesgo_alumno", id_alumno=id_alumno).set_index("asignatura")
datos = ficha["datos"]
n_materias = len(materias)

with cab_der:
    resumen = materias.assign(riesgo=materias["asignatura"].map(riesgo["nivel_riesgo"]),
                              prob_abandono=materias["asignatura"].map(riesgo["probabilidad"]))[
        ["asignatura", "condicion", "nota_final", "escala", "promedio_nota_final", "rendidos", "instrumentos",
         "estado_actividad", "dias_sin_actividad", "eventos", "minutos", "riesgo", "prob_abandono", "inscripto"]]
    comp.boton_csv(resumen, f"ficha_{id_alumno}", "Descargar ficha")

if f.asignatura:
    st.caption(f"El buscador lista solo alumnos de {f.asignatura}, pero la ficha muestra todas sus materias.")

# ---------------------------------------------------------------------------
# Cabecera del alumno: quién es y su riesgo de abandono
# ---------------------------------------------------------------------------
iniciales = "".join(str(x).strip()[:1] for x in (datos["apellido"], datos["nombre"])).upper()
inscripto_en = int(materias["inscripto"].sum())
sub = f"{esc(id_alumno)} · en la base de {n_materias} {'materia' if n_materias == 1 else 'materias'}"
if inscripto_en < n_materias:
    sub += f" · inscripto en {inscripto_en}"

chips = []
con_eventos = materias[materias["eventos"] > 0]
if con_eventos.empty:
    chips.append(comp.chip_estado("Nunca entró al aula", "critico", con_icono=True))
else:
    dias = int(con_eventos["dias_sin_actividad"].min())
    tono = "atencion" if dias > f.umbral else "neutro"
    chips.append(comp.chip_estado(f"Sin entrar hace {dias} {'día' if dias == 1 else 'días'}" if dias else "Entró hoy",
                           tono, con_icono=tono != "neutro"))
chips.append(comp.chip_estado(f"{comp.num(materias['eventos'].sum())} interacciones"))
chips.append(comp.chip_estado(f"{materias['rendidos'].sum()} de {materias['instrumentos'].sum()} instrumentos rendidos"))
for m in materias.loc[~materias["inscripto"], "asignatura"]:
    chips.append(comp.chip_estado(f"No inscripto en {esc(comp.SIGLAS[m])}", "atencion", con_icono=True))

# Riesgo: el más alto entre las materias que viene cursando; si no cursa ninguna, su estado.
cursando = riesgo[riesgo["estado_abandono"] == ab.CURSANDO]
otros = []
if not cursando.empty:
    m_r = cursando["probabilidad"].idxmax()
    r = cursando.loc[m_r]
    tono = comp.TONO_RIESGO_ESTADO[r["nivel_riesgo"]]
    curso = riesgo_todos.loc[(riesgo_todos["asignatura"] == m_r)
                             & (riesgo_todos["estado_abandono"] == ab.CURSANDO), "probabilidad"].mean()
    valor = (f'<b class="tfi-num">{esc(r["nivel_riesgo"])}</b><b class="tfi-num">{comp.pct(r["probabilidad"], 0)}</b>'
             f'<span class="tfi-num" style="font-size:12px;font-weight:500">'
             f'{signo(r["probabilidad"] - curso, 0)} pts vs. curso</span>')
    kicker_der = f"curso {comp.pct(curso, 0)}"
    titulo_r = f"Riesgo de abandono · {esc(comp.SIGLAS[m_r])}"
    barra_r = comp.barra(r["probabilidad"], comp.TONOS_ESTADO[tono][2], alto=9, marca=curso)
    explica = (f"Probabilidad de que no entre en los próximos {ab.ABANDONO_HORIZONTE_DIAS} días. "
               + (f"Pesan más: {esc(r['motivos'])}." if r["motivos"] else ""))
    otros = [m for m in riesgo.index if m != m_r]
    nivel_txt = f"Nivel {r['nivel_riesgo']}"
else:
    estado = riesgo["estado_abandono"].iloc[0] if not riesgo.empty else ab.SIN_ACTIVIDAD
    nivel = ab.YA_ABANDONO if (riesgo["estado_abandono"] == ab.YA_ABANDONO).any() else estado
    tono = comp.TONO_RIESGO_ESTADO.get(nivel, "neutro")
    valor, kicker_der, barra_r = f"<b>{esc(nivel)}</b>", "", ""
    titulo_r, nivel_txt = "Riesgo de abandono", nivel
    explica = ("No entra a ninguna de sus materias hace 14 días o más: ya cumple la definición de abandono. "
               "Conviene contactarlo." if nivel == ab.YA_ABANDONO else "Nunca entró al aula hasta la fecha de corte.")
for m in otros:
    o = riesgo.loc[m]
    if o["estado_abandono"] == ab.YA_ABANDONO:
        explica += f" En {esc(comp.SIGLAS[m])} ya abandonó ({comp.num(o['dias_sin_actividad'])} días sin entrar)."
    elif o["estado_abandono"] == ab.SIN_ACTIVIDAD:
        explica += f" En {esc(comp.SIGLAS[m])} nunca entró."
fondo, color, solido = comp.TONOS_ESTADO[tono]
comp.html(f"""
<section class="fi-card" aria-label="Resumen del alumno"><div class="fi-cab">
  <div class="fi-quien">
    <div class="fi-avatar" aria-hidden="true">{esc(iniciales)}</div>
    <div style="min-width:0">
      <h2 class="fi-nombre">{esc(datos['nombre_completo'])}</h2>
      <div class="fi-sub tfi-num">{sub}</div>
      <div class="fi-chips">{''.join(chips)}</div>
    </div>
  </div>
  <div class="fi-riesgo" style="background:{fondo};border-color:{solido}33;color:{color}">
    <div class="fi-riesgo-fila"><span class="tfi-kicker" style="color:{color};margin:0">{titulo_r}</span>
      <span class="tfi-num" style="font-size:11px">{kicker_der}</span></div>
    <div class="fi-riesgo-valor">{comp.icono_estado(tono, 18, etiqueta=nivel_txt)}{valor}</div>
    {f'<div style="margin-bottom:8px">{barra_r}</div>' if barra_r else ''}
    <div class="fi-riesgo-txt">{explica}</div>
  </div>
</div></section>""")

# ---------------------------------------------------------------------------
# Estado por materia (ordenado por riesgo)
# ---------------------------------------------------------------------------
semanal = ficha["semanal"]
ultimas_8 = semanal.groupby("asignatura").tail(8)
tope_spark = ultimas_8["eventos"].max() if not ultimas_8.empty else 1
tabla_estado = materias.assign(
    _p=materias["asignatura"].map(riesgo["nivel_riesgo"]).map(PRIORIDAD_RIESGO).fillna(-1),
    _prob=materias["asignatura"].map(riesgo["probabilidad"]).fillna(0),
).sort_values(["_p", "_prob"], ascending=False)
filas = []
for fila in tabla_estado.itertuples():
    m, color_m = fila.asignatura, comp.COLORES_MATERIA[fila.asignatura]
    if fila.instrumentos:
        dif = fila.nota_final - fila.promedio_nota_final
        tono_dif = "#116040" if dif >= 0 else "#93241C"
        nota = (f'<span style="font-size:15px;font-weight:600">{comp.num(fila.nota_final, 1)}</span> '
                f'<span style="font-size:12px;color:{comp.TENUE}">/ {fila.escala}</span>')
        vs = f'<span style="color:{tono_dif};font-weight:600">{signo(dif)}</span>'
    else:
        nota, vs = f'<span style="color:{comp.TENUE}">–</span>', ""
    ultimas = ultimas_8.loc[ultimas_8["asignatura"] == m, "eventos"]
    if fila.eventos:
        cuando = f"hace {fila.dias_sin_actividad} {'día' if fila.dias_sin_actividad == 1 else 'días'}"
    else:
        cuando = "nunca entró"
    actividad = (f'{sparkline(ultimas, color_m, tope_spark)}<span style="font-size:11px;color:{comp.TINTA_3}">'
                 f'{esc(fila.estado_actividad)} · {cuando}</span>')
    celda_riesgo = texto_riesgo_html(riesgo.loc[m]) if m in riesgo.index else "–"
    filas.append(f"""<tr>
      <td><span style="display:inline-flex;align-items:center;gap:9px">{comp.cuadro(color_m)}
        <span><strong style="font-weight:600">{esc(m)}</strong><br>
        <span style="font-size:11px;color:{comp.TINTA_3}">{esc(comp.SIGLAS[m])}</span></span></span></td>
      <td>{comp.pastilla_condicion(fila.condicion)}</td>
      <td>{nota}</td><td>{vs}</td>
      <td>{fila.rendidos} de {fila.instrumentos}</td>
      <td>{actividad}</td><td>{celda_riesgo}</td></tr>""")
leyenda = "".join(
    f'<span style="display:inline-flex;align-items:center;gap:6px;font-weight:500;color:{comp.TONOS_ESTADO[t][1]}">'
    f'{comp.icono_estado(t)}{esc(c)}</span>' for c, t in comp.TONO_CONDICION.items())
comp.html(f"""
<section class="fi-card" aria-label="Estado por materia">
  <div class="fi-card-cab"><h3 class="fi-h3">Estado por materia</h3>
    <div class="tfi-nota-al-pie">Ordenado por riesgo. La nota al corte incluye con 0 lo que no rindió (D15).</div></div>
  <div style="overflow-x:auto"><table class="fi-tabla">
    <thead><tr><th scope="col">Materia</th><th scope="col">Condición</th><th scope="col">Nota al corte</th>
      <th scope="col">vs. curso</th><th scope="col">Rendidos</th><th scope="col">Actividad 8 sem.</th>
      <th scope="col">Riesgo de abandono</th></tr></thead>
    <tbody>{''.join(filas)}</tbody></table></div>
  <div class="fi-card-pie"><span style="font-weight:500;font-size:11px;letter-spacing:.05em;
    text-transform:uppercase">Semáforo</span>{leyenda}</div>
</section>""")

# ---------------------------------------------------------------------------
# Qué hacer con este alumno: alertas (D37) agrupadas por situación
# ---------------------------------------------------------------------------
alertas = ficha["alertas"]
if alertas.empty:
    comp.html(f"""<section class="fi-card" aria-label="Alertas"><div class="fi-alerta" style="border-top:none">
      <div class="fi-alerta-ico" style="background:{comp.TONOS_ESTADO['bien'][0]};color:{comp.TONOS_ESTADO['bien'][2]}">
        {comp.icono_estado('bien', 16, 'Sin alertas')}</div>
      <div class="fi-alerta-txt"><h4>Sin alertas a la fecha de corte</h4>
        <div class="fi-det">Entra con regularidad, rinde y no queda Libre en ninguna materia.</div></div></div></section>""")
else:
    # Si en una materia "entra pero no rinde", el "queda Libre" es consecuencia: va en la misma tarjeta.
    no_rinde = set(alertas.loc[alertas["tipo"] == "sin_notas", "asignatura"])
    agrupadas = alertas[~((alertas["tipo"] == "libre") & alertas["asignatura"].isin(no_rinde))]
    por_materia = materias.set_index("asignatura")
    tarjetas_alerta, conteo = [], {}
    for tipo in ORDEN_ALERTAS:
        g = agrupadas[agrupadas["tipo"] == tipo].sort_values("asignatura", key=lambda s: s.map(orden))
        if g.empty:
            continue
        tono = GRAVEDAD[tipo]
        conteo[tono] = conteo.get(tono, 0) + 1
        titulo = TITULO_ALERTA[tipo]
        if tipo == "inactivo" and len(g) > 1:
            titulo = "Dejó de entrar a todas sus materias" if len(g) == n_materias else f"Dejó de entrar a {len(g)} materias"
        partes = []
        for a in g.itertuples():
            texto = esc(a.detalle)
            fm = por_materia.loc[a.asignatura]
            if tipo == "libre":   # mismo dato que el detalle, con coma decimal
                texto = (f"Nota {comp.num(fm.nota_final, 1)} / {fm.escala} con {fm.rendidos} de "
                         f"{fm.instrumentos} instrumentos rendidos")
            if tipo == "sin_notas":
                texto += f": la nota al corte queda en {comp.num(fm.nota_final, 1)} / {fm.escala} y la condición es {esc(fm.condicion)}"
            partes.append((f"{esc(comp.SIGLAS[a.asignatura])}: " if len(g) > 1 else "") + texto)
        detalle = " · ".join(partes) + "."
        if tipo == "inactivo":
            detalle += f" El umbral configurado son {f.umbral} días."
        etiquetas = (comp.chip_estado(f"Sus {n_materias} materias", "neutro", chico=True) if len(g) == n_materias > 1
                     else "".join(comp.sigla(m) for m in g["asignatura"]))
        fondo, _, solido = comp.TONOS_ESTADO[tono]
        tarjetas_alerta.append(f"""<article class="fi-alerta">
          <div class="fi-alerta-ico" style="background:{fondo};color:{solido}">
            {comp.icono_estado(tono, 16, NOMBRE_GRAVEDAD[tono].capitalize())}</div>
          <div class="fi-alerta-txt">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">{etiquetas}<h4>{titulo}</h4></div>
            <div class="fi-det tfi-num">{detalle}</div><div class="fi-sug">{SUGERENCIA[tipo]}</div></div></article>""")
    resumen_chips = "".join(
        comp.chip_estado(f"{conteo[t]} {NOMBRE_GRAVEDAD[t]}{'s' if conteo[t] > 1 and t == 'critico' else ''}", t, chico=True)
        for t in ("critico", "atencion", "neutro") if t in conteo)
    n_al, n_gr = len(alertas), len(tarjetas_alerta)
    comp.html(f"""
<section class="fi-card" aria-label="Alertas">
  <div class="fi-card-cab">
    <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap"><h3 class="fi-h3">Qué hacer con este alumno</h3>
      <span class="tfi-nota-al-pie">{n_al} {'alerta' if n_al == 1 else 'alertas'} a la fecha de corte (D37)
      {f', agrupadas en {n_gr} situaciones' if n_gr < n_al else ''}</span></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">{resumen_chips}</div></div>
  {''.join(tarjetas_alerta)}
</section>""")

# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------
tab_notas, tab_act, tab_traz = st.tabs(["Notas", "Actividad", "Trazabilidad"])


def tarjeta_nota(t, color: str) -> str:
    """Una tarjeta de la libreta: nota, si aprobó y el promedio del curso (fila de ficha['instrumentos'])."""
    nombre = esc(nombre_corto(t.instrumento))
    if not t.rindio:
        estado = "No lo rindió" if t.es_recuperatorio else "No rindió · cuenta 0"
        curso = f"Curso {comp.pct(t.promedio_curso_pct, 0)}" if pd.notna(t.promedio_curso_pct) else "Curso –"
        return (f'<div class="fi-nota fi-falta"><div class="fi-nota-nombre" title="{nombre}">{nombre}</div>'
                f'<div class="fi-nota-valor" style="color:{comp.TENUE}">—</div>'
                f'<div class="fi-nota-estado" style="color:{comp.TINTA_3};font-weight:500">{estado}</div>'
                f'<div class="fi-nota-curso tfi-num">{curso}</div></div>')
    aprobada = str(t.observaciones).strip().lower() == "aprobada"
    tono = "bien" if aprobada else "critico"
    estado = "Aprobada" if aprobada else "No aprobada"
    if t.recuperatorio_aplicado:
        estado += " · la reemplaza el recuperatorio"
    curso = "Curso –"
    if pd.notna(t.promedio_curso_pct):
        dif = t.nota_pct - t.promedio_curso_pct
        curso = (f"Curso {comp.pct(t.promedio_curso_pct, 0)} · "
                 f"{signo(round(dif), 0)} {'pt' if abs(round(dif)) == 1 else 'pts'}")
    color_barra = color if aprobada else comp.TONOS_ESTADO["critico"][2]
    return (f'<div class="fi-nota"><div class="fi-nota-nombre" title="{nombre}">{nombre}</div>'
            f'<div class="fi-nota-valor tfi-num">{comp.pct(t.nota_pct, 0)}'
            f'<small>{comp.num(t.nota_obtenida, 2)} / {comp.num(t.puntaje_maximo, 0)}</small></div>'
            f'<div class="fi-nota-estado" style="color:{comp.TONOS_ESTADO[tono][1]}">{estado}</div>'
            f'{comp.barra(t.nota_pct, color_barra, alto=6)}'
            f'<div class="fi-nota-curso tfi-num">{curso}</div></div>')


# ---------------------------------------------------------------------------
# Notas
# ---------------------------------------------------------------------------
with tab_notas:
    inst = ficha["instrumentos"]
    if inst.empty:
        st.info(f"Al {comp.fmt_fecha(f.fecha_corte)} todavía no se tomó ninguna evaluación en sus materias.",
                icon=":material/event_busy:")
    else:
        inst = inst.assign(nombre=inst["instrumento"].map(nombre_corto),
                           nota_pct=(inst["nota_obtenida"] / inst["puntaje_maximo"] * 100).round(1))  # la original
        inst["eje"] = inst["nombre"].map(en_dos_lineas)
        presentes_notas = [m for m in materias["asignatura"] if m in set(inst["asignatura"])]
        c_txt, c_vista = st.columns([4, 1.3], vertical_alignment="center")
        c_txt.markdown(
            '<div class="tfi-desc" style="margin:0">Una tarjeta por instrumento, en el orden en que se tomaron. '
            "Lo que no rindió cuenta 0 para la nota final (D15); si rindió el recuperatorio, esa nota reemplaza "
            "a la original (D34). El curso es el promedio de quienes lo rindieron (D22).</div>",
            unsafe_allow_html=True)
        vista = c_vista.segmented_control("Vista", ["Libreta", "Barras"], default="Libreta", key="fi_vista_notas",
                                          label_visibility="collapsed") or "Libreta"

        if vista == "Libreta":
            for materia in presentes_notas:
                fila = materias[materias["asignatura"] == materia].iloc[0]
                q = inst[inst["asignatura"] == materia]
                color_m = comp.COLORES_MATERIA[materia]
                if fila.rendidos == 0:
                    cuerpo = (f'<div class="fi-vacio tfi-num">Ningún instrumento rendido entre el '
                              f'{q["fecha_instrumento"].min():%d/%m} y el {q["fecha_instrumento"].max():%d/%m}: '
                              f'los {fila.instrumentos} cuentan 0.</div>')
                    resumen_m = f"{nota_texto(fila)} / {fila.escala} · no rindió ninguno de los {fila.instrumentos}"
                else:
                    cuerpo = f'<div class="fi-libreta">{"".join(tarjeta_nota(t, color_m) for t in q.itertuples())}</div>'
                    resumen_m = f"{nota_texto(fila)} / {fila.escala} · rindió {fila.rendidos} de {fila.instrumentos}"
                comp.html(f"""<section class="fi-card" style="padding:16px" aria-label="Notas de {esc(materia)}">
                  <div class="fi-libreta-cab">{comp.cuadro(color_m)}<h4>{esc(materia)}</h4>
                    {comp.pastilla_condicion(fila.condicion, chico=True)}
                    <span class="tfi-num" style="font-size:12px;color:{comp.TINTA_3}">{resumen_m}</span></div>
                  {cuerpo}</section>""")
        else:
            with st.container(border=True, key="tarjeta_barras"):
                st.caption("Cada barra es su nota en el instrumento (en % del máximo). En gris, lo que no rindió. "
                           "El rombo ◆ es el promedio de quienes sí lo rindieron.")
                for materia in presentes_notas:
                    q = inst[inst["asignatura"] == materia]
                    rindio = q["rindio"]
                    fig = go.Figure()
                    fig.add_bar(x=q["eje"], y=q["nota_pct"].where(rindio, 1.5), showlegend=False,
                                marker_color=[comp.COLORES_MATERIA[materia] if r else GRIS for r in rindio],
                                text=[comp.pct(v, 0) if r else "no rindió" for v, r in zip(q["nota_pct"], rindio)],
                                textposition="outside", cliponaxis=False,
                                textfont=dict(color=comp.TINTA_2, size=11),
                                customdata=q[["nombre", "nota_obtenida", "puntaje_maximo"]].fillna(0),
                                hovertemplate="%{customdata[0]}<br>Nota: %{customdata[1]:g} / %{customdata[2]:g}"
                                              "<extra></extra>")
                    fig.add_scatter(x=q["eje"], y=q["promedio_curso_pct"], mode="markers", showlegend=False,
                                    marker=dict(symbol="diamond", size=11, color=comp.TINTA,
                                                line=dict(color="#FFFFFF", width=1.5)),
                                    customdata=q[["nombre", "rindieron"]],
                                    hovertemplate="%{customdata[0]}<br>Promedio de quienes lo rindieron: %{y:.1f} %"
                                                  "<br>(%{customdata[1]} alumnos)<extra></extra>")
                    fig.update_yaxes(range=[0, 118], ticksuffix=" %", showgrid=True)
                    fig.update_xaxes(tickangle=0)
                    fig.update_layout(title=materia, height=290, bargap=0.4)
                    comp.grafico(fig)

        tabla = inst.assign(
            Materia=inst["asignatura"], Instrumento=inst["nombre"], Fecha=inst["fecha_instrumento"].dt.date,
            Rindió=inst["rindio"].map({True: "Sí", False: "No"}),
            Nota=[f"{comp.num(n, 2)} / {comp.num(m_, 0)}" if r else "–"
                  for n, m_, r in zip(inst["nota_obtenida"], inst["puntaje_maximo"], inst["rindio"])],
            **{"Nota (%)": inst["nota_pct"].where(inst["rindio"]),
               "Cuenta para la final (%)": inst["nota_pct_corte"].where(inst["cuenta_en_final"]),
               "Promedio del curso (%)": inst["promedio_curso_pct"],
               "Observaciones": inst["observaciones"].fillna(""),
               "Recuperatorio aplicado": inst["recuperatorio_aplicado"].map({True: "Sí", False: ""})},
        )[["Materia", "Instrumento", "Fecha", "Rindió", "Nota", "Nota (%)", "Cuenta para la final (%)",
           "Promedio del curso (%)", "Observaciones", "Recuperatorio aplicado"]]
        with st.container(border=True, key="tarjeta_detalle_notas"):
            c_t, c_b = st.columns([4, 1.3], vertical_alignment="center")
            c_t.markdown('<h4 class="fi-h3">Detalle de notas</h4>', unsafe_allow_html=True)
            with c_b:
                comp.boton_csv(tabla, f"notas_{id_alumno}", "Descargar CSV")
            st.dataframe(tabla, hide_index=True, width="stretch",
                         column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                        **{c: st.column_config.NumberColumn(format="%.1f")
                                           for c in ["Nota (%)", "Cuenta para la final (%)",
                                                     "Promedio del curso (%)"]}})
            st.caption("*Cuenta para la final* es lo que entra en la nota al corte: 0 si no rindió y, si rindió el "
                       "recuperatorio, la nota del recuperatorio. Los recuperatorios no suman un instrumento más al "
                       "promedio, por eso esa columna queda vacía en ellos.")

# ---------------------------------------------------------------------------
# Actividad
# ---------------------------------------------------------------------------
with tab_act:
    VARIABLES = {"nota_final": ("Nota", 1, ""), "minutos": ("Minutos", 0, ""),
                 "eventos": ("Interacciones", 0, ""), "avance": ("Avance", 0, " %")}
    bloques = []
    for fila in materias.itertuples():
        color_m = comp.COLORES_MATERIA[fila.asignatura]
        renglones = []
        for col, (et, dec, suf) in VARIABLES.items():
            p, v, prom = (getattr(fila, f"percentil_{col}"), getattr(fila, col), getattr(fila, f"promedio_{col}"))
            renglones.append(
                f'<div class="fi-pct"><span class="fi-pct-et">{et}</span>'
                f'<div class="fi-pct-bar">{comp.barra(p, color_m)}</div>'
                f'<div class="fi-pct-val tfi-num"><b>p{comp.num(p)} · {comp.num(v, dec)}{suf}</b>'
                f'<span>curso {comp.num(prom, dec)}{suf}</span></div></div>')
        bloques.append(f'<div><div class="fi-grilla-titulo">{comp.cuadro(color_m, 9)}{esc(fila.asignatura)}</div>'
                       f'{"".join(renglones)}</div>')
    comp.html(f"""<section class="fi-card" aria-label="Percentiles">
      <div class="fi-card-cab" style="display:block"><h3 class="fi-h3">Dónde queda dentro de su curso</h3>
        <div class="tfi-nota-al-pie" style="margin-top:4px;max-width:80ch">La barra es el percentil: qué parte de la
        base de la materia tiene un valor igual o menor (p80 = está por encima del 80 % de sus compañeros). Abajo,
        el promedio del curso. <em>Avance</em> sale del reporte de participación: es una foto a la fecha de
        exportación y no se recorta con la fecha de corte (D36).</div></div>
      <div class="fi-grilla">{''.join(bloques)}</div></section>""")

    with st.container(border=True, key="tarjeta_semanal"):
        c_t, c_v = st.columns([3, 2], vertical_alignment="center")
        c_t.markdown('<h3 class="fi-h3">Evolución semanal</h3><div class="tfi-nota-al-pie">Semanas de lunes a '
                     'domingo. Las líneas verticales son evaluaciones ya tomadas.</div>', unsafe_allow_html=True)
        if semanal.empty or semanal["eventos"].sum() == 0:
            st.info("No tiene interacciones registradas hasta la fecha de corte.", icon=":material/visibility_off:")
        else:
            ver = c_v.segmented_control("Ver", ["Interacciones", "Minutos", "Sesiones"], default="Interacciones",
                                        key="fi_ver_semanal", label_visibility="collapsed") or "Interacciones"
            columna = {"Interacciones": "eventos", "Minutos": "minutos", "Sesiones": "sesiones"}[ver]
            evaluaciones = ficha["evaluaciones"]
            presentes = [m for m in materias["asignatura"] if m in set(semanal["asignatura"])]
            tope = semanal[columna].max()
            if columna == "eventos":
                tope = max(tope, semanal["curso_eventos"].max())
            cols = st.columns(len(presentes))
            for col, materia in zip(cols, presentes):
                q = semanal[semanal["asignatura"] == materia]
                color = comp.COLORES_MATERIA[materia]
                fig = go.Figure()
                for ev in evaluaciones[evaluaciones["asignatura"] == materia].itertuples():
                    fig.add_vline(x=ev.fecha_instrumento, line=dict(color=GRIS, width=1, dash="dash"))
                if columna == "eventos":
                    fig.add_scatter(x=q["periodo"], y=q["curso_eventos"], mode="lines", name="Promedio del curso",
                                    line=dict(color=color, width=1.4, dash="dot"), opacity=0.65,
                                    hovertemplate="Semana del %{x|%d/%m}: %{y:.1f} por alumno<extra>Curso</extra>")
                fig.add_scatter(x=q["periodo"], y=q[columna], mode="lines+markers", name="El alumno",
                                line=dict(color=color, width=2.2), marker=dict(size=5),
                                hovertemplate=f"Semana del %{{x|%d/%m}}: %{{y:,.0f}} {ver.lower()}"
                                              "<extra>El alumno</extra>")
                fig.update_yaxes(range=[0, tope * 1.1 if tope else 1])   # misma escala en todas
                fig.update_xaxes(tickformat="%d/%m", nticks=5)
                fig.update_layout(title=materia, height=230, showlegend=False, margin=dict(t=36, l=4, r=4, b=4))
                comp.grafico(fig, col)
            st.caption("Línea llena: el alumno · punteada: promedio por alumno de la base en esa semana"
                       + ("." if columna == "eventos" else " (solo para interacciones)."))

    filas_rep = []
    for fila in materias.itertuples():
        color_m = comp.COLORES_MATERIA[fila.asignatura]
        avance = (f'<span style="display:flex;align-items:center;gap:8px"><span style="flex:1 1 90px">'
                  f'{comp.barra(fila.avance, color_m, alto=7)}</span>'
                  f'<span style="font-size:12px;font-weight:500;white-space:nowrap">{comp.pct(fila.avance, 0)}</span></span>')
        filas_rep.append(
            f"<tr><td>{comp.sigla(fila.asignatura)}</td><td>{comp.num(fila.sesiones)}</td>"
            f"<td>{comp.num(fila.minutos)}</td><td>{comp.num(fila.dias_activos)}</td>"
            f"<td>{comp.num(fila.semanas_activas)}</td><td style='min-width:150px'>{avance}</td>"
            f"<td>{comp.num(fila.tiempo_uso_min)}</td><td>{comp.num(fila.intervenciones_foros)}</td>"
            f"<td>{comp.num(fila.encuestas_respondidas)}</td><td>{comp.num(fila.emails_enviados)}</td></tr>")
    comp.html(f"""<section class="fi-card" aria-label="Reporte de participación">
      <div class="fi-card-cab" style="display:block"><h3 class="fi-h3">Reporte de participación</h3>
        <div class="tfi-nota-al-pie" style="margin-top:3px">Sesiones y minutos salen de la trazabilidad (sesiones
        cortadas a los 30 min sin eventos, D25). El resto es una foto a la fecha de exportación del LMS: no se
        recorta con la fecha de corte (D36).</div></div>
      <div style="overflow-x:auto"><table class="fi-tabla"><thead><tr>
        <th scope="col">Materia</th><th scope="col">Sesiones</th><th scope="col">Minutos</th>
        <th scope="col">Días con actividad</th><th scope="col">Semanas</th><th scope="col">Avance</th>
        <th scope="col">Tiempo de uso (min)</th><th scope="col">Foros</th><th scope="col">Encuestas</th>
        <th scope="col">Correos</th></tr></thead><tbody>{''.join(filas_rep)}</tbody></table></div></section>""")

# ---------------------------------------------------------------------------
# Trazabilidad
# ---------------------------------------------------------------------------
with tab_traz:
    eventos = ficha["eventos"]
    if eventos.empty:
        st.info("No tiene interacciones registradas hasta la fecha de corte.", icon=":material/visibility_off:")
    else:
        cat = ficha["categorias"]
        presentes = [m for m in materias["asignatura"] if m in set(cat["asignatura"])]
        tipos = sorted(cat["categoria"].unique())
        tope = max(cat["pct_eventos"].max(), cat["pct_curso"].max())   # misma escala en todas
        bloques = []
        for materia in presentes:
            q = cat[cat["asignatura"] == materia].set_index("categoria").reindex(tipos)
            color_m = comp.COLORES_MATERIA[materia]
            total = int(q["eventos"].fillna(0).sum())
            renglones, aviso = [], ""
            for tipo in tipos:
                v, c = q.loc[tipo, "pct_eventos"], q.loc[tipo, "pct_curso"]
                v = 0 if pd.isna(v) else v
                cero_eval = tipo == "Evaluación" and v == 0 and pd.notna(c) and c > 0
                col_b = comp.TONOS_ESTADO["critico"][2] if cero_eval else color_m
                estilo = f"color:{comp.TONOS_ESTADO['critico'][1]};font-weight:600" if cero_eval else ""
                renglones.append(
                    f'<div class="fi-tipo" title="{esc(tipo)}: {comp.pct(v)} (curso {comp.pct(c)})">'
                    f'<span class="fi-tipo-et" style="{estilo}">{esc(tipo)}</span>'
                    f'<span style="flex:1 1 auto">{comp.barra(v, col_b, alto=12, maximo=tope, marca=c)}</span>'
                    f'<span class="fi-tipo-val tfi-num" style="{estilo}">{comp.num(v, 0)} %</span></div>')
                if cero_eval:
                    aviso = (f'<div class="fi-aviso-rojo">Cero interacciones de evaluación en {comp.num(total)} '
                             'registradas: el patrón «entra pero no rinde».</div>')
            bloques.append(f'<div><div class="fi-grilla-titulo">{comp.cuadro(color_m, 9)}{esc(materia)}</div>'
                           f'{"".join(renglones)}{aviso}</div>')
        comp.html(f"""<section class="fi-card" aria-label="Interacciones por tipo">
          <div class="fi-card-cab" style="display:block"><h3 class="fi-h3">Qué hace cuando entra</h3>
            <div class="tfi-nota-al-pie" style="margin-top:4px;max-width:80ch">Sus interacciones por tipo, en % de su
            total en cada materia. La rayita gris es el curso: si su barra de <em>Evaluación</em> o
            <em>Contenido</em> queda muy por debajo, entra pero no estudia ni rinde.</div></div>
          <div class="fi-grilla">{''.join(bloques)}</div></section>""")

        with st.container(border=True, key="tarjeta_eventos"):
            c_t, c_b = st.columns([4, 1.3], vertical_alignment="center")
            c_t.markdown(f'<h3 class="fi-h3">Sus interacciones <span class="tfi-num" style="font:400 12px Inter,'
                         f'sans-serif;color:{comp.TINTA_3}">{comp.num(len(eventos))} hasta la fecha de corte'
                         f'</span></h3>', unsafe_allow_html=True)
            c1, c2 = st.columns([1, 2.2])
            sel_materias = c1.pills("Materia", presentes, default=presentes, selection_mode="multi",
                                    key="fi_traz_materia", format_func=comp.SIGLAS.get)
            sel_tipos = c2.pills("Tipo", tipos, default=tipos, selection_mode="multi", key="fi_traz_tipo")
            filtrados = eventos[eventos["asignatura"].isin(sel_materias) & eventos["categoria"].isin(sel_tipos)]
            tabla = filtrados.rename(columns={"fecha_hora": "Fecha y hora", "asignatura": "Materia",
                                              "categoria": "Tipo", "seccion": "Sección", "accion": "Acción",
                                              "descripcion": "Descripción"})
            with c_b:
                comp.boton_csv(tabla, f"trazabilidad_{id_alumno}", "Descargar CSV")
            st.dataframe(tabla, hide_index=True, width="stretch", height=380,
                         column_config={"Fecha y hora": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
