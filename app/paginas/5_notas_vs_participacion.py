"""Dashboard 5 (del plan): Notas vs. participación. Diseño: rediseño D56.

Responde, a la fecha de corte: ¿a los alumnos que más usan el aula les va
mejor?, ¿qué forma de participar se asocia más con la nota? y ¿quiénes están
en riesgo (poca actividad y nota baja)?

  Controles       variable de actividad (VARIABLES_CRUCE) y "solo quienes
                  rindieron algo", que saca los 0 por no rendir (D55).
  Titular         ρ de Spearman de la variable elegida en cada materia, con una
                  lectura automática (qué variable acompaña más a la nota), y la
                  tarjeta de alumnos en riesgo (D37).
  Dispersión      un punto por alumno, coloreado por condición, con la
                  tendencia (nota promedio de cada quinto de actividad), los
                  cortes de Regular y Promociona y una conclusión por materia.
  Correlaciones   tabla variable × materia con barras de ρ (D38), qué hacer con
                  esto y cómo leer el número; la tabla con p-valor y n, con CSV.
  Por nivel       los alumnos en 5 grupos iguales según la actividad: % por
                  condición y nota promedio de cada grupo (D55).
  Cuadrante       conteo por cuadrante (mediana de actividad × Libre, D37), qué
                  hacer con cada grupo y la lista de alumnos en riesgo con CSV.

Todo sale de src.metricas vía comp.metrica() (D29, D47): la página solo filtra y dibuja.
Los textos de conclusión se arman con los datos: cambian con la fecha, la materia y la variable.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import componentes as comp
from src.config import CONDICIONES, ESQUEMA, SIN_EVALUACIONES
from src.metricas import SIN_ACTIVIDAD, VARIABLES_CRUCE

f = comp.encabezado(
    "Notas vs. participación",
    "¿A los alumnos que más usan el aula les va mejor? ¿Y quiénes tienen poca actividad y nota baja?",
)

DEL_REPORTE = {"tiempo_uso_min", "avance"}   # foto del reporte de participación (D36)
UNIDAD = {"minutos": "min", "tiempo_uso_min": "min", "avance": "%"}
# Para escribir las conclusiones en castellano corrido.
EN_PROSA = {"minutos": "los minutos en la plataforma", "sesiones": "las sesiones", "eventos": "las interacciones",
            "dias_activos": "los días con actividad", "semanas_activas": "las semanas con actividad",
            "tiempo_uso_min": "el tiempo estimado de uso", "avance": "el avance en el contenido"}
ORIGEN = {"avance": "del reporte de participación", "tiempo_uso_min": "del reporte",
          "minutos": "calculados con las sesiones"}
# Cuadrantes (D37) en el orden de la grilla 2×2: arriba buena nota, abajo nota baja; izquierda poca actividad.
CUADRANTES = {
    "Poca actividad con buena nota": ("atencion", "Poca actividad, buena nota",
                                      "Les alcanza con poco. No requieren acción, pero avisan que el aula no es "
                                      "donde estudian."),
    "Activo con buena nota": ("bien", "Activo y con buena nota",
                              "El grupo sano. Sirve como referencia de cuánta actividad “alcanza”."),
    "Riesgo: poca actividad y nota baja": ("critico", "Poca actividad y nota baja", ""),   # texto con datos, abajo
    "Activo con nota baja": ("serio", "Activo con nota baja",
                             "Están, pero no les rinde. Acá el problema es la consigna o la comprensión, "
                             "no el enganche."),
}
COLOR_CUADRANTE = {  # (fondo, borde, número, texto)
    "atencion": ("#FBF0DC", "#F0E2C4", "#6B4700", "#7A5000"), "bien": ("#E6F2EB", "#CFE3D8", "#0B6B49", "#116040"),
    "critico": ("#FBE9E6", "#F2CFC9", "#93241C", "#7A3028"), "serio": ("#FBEFE6", "#E8D4C4", "#8A4415", "#8A4415"),
}
TONO_FUERZA = {"fuerte": "bien", "moderada": "atencion", "débil": "serio", "nula": "neutro", "sin datos": "neutro"}


def fuerza(rho) -> str:
    if pd.isna(rho):
        return "sin datos"
    r = abs(rho)
    return "nula" if r < 0.1 else "débil" if r < 0.3 else "moderada" if r < 0.5 else "fuerte"


def de_cada_10(p: float) -> str:
    r = round(p / 10)
    return "menos de 1" if r == 0 and p > 0 else "más de 9" if r == 10 and p < 100 else str(r)


def es(sujeto: str) -> str:
    """'los minutos' -> 'son', 'el avance' -> 'es'."""
    return "son" if sujeto.startswith(("los ", "las ")) else "es"


# ---------------------------------------------------------------------------
# Controles de la página
# ---------------------------------------------------------------------------
with st.container(border=True):
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    variable = c1.selectbox("Forma de participar", list(VARIABLES_CRUCE), format_func=VARIABLES_CRUCE.get,
                            key="nvp_variable",
                            help="La variable de participación que se cruza con la nota en toda la página.")
    solo_rindieron = c2.toggle(
        "Solo alumnos que rindieron al menos una evaluación", key="nvp_solo_rindieron",
        help="Quien no rindió nada tiene 0 (D15) y casi siempre también poca actividad: eso solo ya arma "
             "una correlación. Sacarlos muestra si la actividad se asocia con la nota entre los que sí rinden (D55).")
    nombre_var = VARIABLES_CRUCE[variable]
    if variable in DEL_REPORTE:
        st.caption(f":material/info: *{nombre_var}* sale del reporte de participación: es una foto a la fecha de "
                   "exportación y no se recorta con la fecha de corte (D36).")

alumnos = comp.metrica("cuadrante_riesgo", variable=variable)
if alumnos["nota_pct"].isna().all():
    st.info(f"Al {comp.fmt_fecha(f.fecha_corte)} todavía no se tomó ninguna evaluación en "
            f"{f.materia.lower()}: no hay notas para cruzar. Mové la fecha de corte.", icon=":material/event_busy:")
    st.stop()

corr = comp.metrica("correlaciones", solo_rindieron=solo_rindieron)
niveles = comp.metrica("nota_por_nivel_actividad", variable=variable, solo_rindieron=solo_rindieron)
puntos = alumnos[alumnos["rendidos"] > 0] if solo_rindieron else alumnos
materias = [m for m in f.materias if m in set(alumnos["asignatura"])]
riesgo = alumnos[alumnos["en_riesgo"]]

corr = corr[corr["asignatura"].isin(materias)]
matriz = corr.pivot(index="variable", columns="asignatura", values="rho").reindex(columns=materias)
promedio = matriz.mean(axis=1).dropna().sort_values(ascending=False)   # la más asociada primero


def fmt_var(x) -> str:
    return f"{comp.num(x, 0)} {UNIDAD.get(variable, '')}".strip()


def rango(var: str) -> str:
    """ρ de una variable en las materias elegidas: '0,66' o '0,66 a 0,77'."""
    v = matriz.loc[var].dropna() if var in matriz.index else pd.Series(dtype=float)
    if v.empty:
        return "sin datos"
    a, b = comp.num(v.min(), 2), comp.num(v.max(), 2)
    return a if a == b else f"{a} a {b}"


def lectura_titular() -> str:
    """La conclusión del titular, armada con los datos."""
    if promedio.empty:
        return "No hay datos suficientes para calcular la correlación."
    mejor, peor = promedio.index[0], promedio.index[-1]
    if variable == mejor:
        txt = (f"<strong>{EN_PROSA[variable].capitalize()} {es(EN_PROSA[variable])} lo que mejor acompaña a la nota</strong> "
               f"({rango(variable)}), por encima de {EN_PROSA[peor]} ({rango(peor)}).")
    elif variable == peor:
        txt = (f"<strong>{EN_PROSA[variable].capitalize()} {es(EN_PROSA[variable])} lo que menos acompaña a la nota</strong> "
               f"({rango(variable)}); lo que más, {EN_PROSA[mejor]} ({rango(mejor)}).")
    else:
        txt = (f"Con {EN_PROSA[variable]}, ρ = {rango(variable)}. Lo que más acompaña a la nota es "
               f"<strong>{EN_PROSA[mejor]}</strong> ({rango(mejor)}) y lo que menos, {EN_PROSA[peor]} "
               f"({rango(peor)}).")
    return (txt + " <strong>Correlación no es causa:</strong> los alumnos comprometidos entran más <em>y</em> "
                  "estudian más.")


# ---------------------------------------------------------------------------
# Titular: ρ por materia + alumnos en riesgo
# ---------------------------------------------------------------------------
elegida = corr[corr["variable"] == variable].set_index("asignatura")
bloques = []
for materia in materias:
    fila = elegida.loc[materia]
    nota_sig = "" if fila["significativa"] else '<span class="tfi-texto" style="font-size:11px"> · no significativa</span>'
    bloques.append(
        f'<div class="tfi-rho" title="n = {fila["n"]} · p = {comp.num(fila["p_valor"], 4)}">'
        f'<p class="tfi-titulo-materia" style="margin:0 0 6px;font-weight:500;font-size:12px">'
        f'{comp.cuadrito(comp.COLORES_MATERIA[materia])}{materia}</p>'
        f'<p class="tfi-big">{comp.num(fila["rho"], 2)}</p>'
        f'{comp.chip(fila["fuerza"], TONO_FUERZA.get(fila["fuerza"], "neutro"), con_icono=False)}{nota_sig}</div>')

por_materia = " · ".join(f"{comp.SIGLAS[m]} {comp.num((riesgo['asignatura'] == m).sum())}" for m in materias)
comp.html(f"""
<div class="tfi" style="display:flex;flex-wrap:wrap;gap:14px;margin:4px 0 18px">
  <div class="tfi-card" style="flex:1 1 480px;min-width:300px">
    <p class="tfi-label">Qué tan fuerte acompaña a la nota · <span style="text-transform:none">ρ</span> de Spearman</p>
    <div style="display:flex;flex-wrap:wrap;gap:30px;margin-bottom:14px">{''.join(bloques)}</div>
    <p class="tfi-nota">{lectura_titular()}</p>
  </div>
  <div class="tfi-card critico" style="flex:1 1 260px;min-width:240px">
    <p class="tfi-label" style="color:#8A3A31">Poca actividad y nota baja</p>
    <p class="tfi-big tfi-riesgo" style="font-size:38px;color:#93241C;letter-spacing:-.02em">{comp.num(len(riesgo))}</p>
    <p class="num" style="margin:0 0 14px;font:500 13px Inter,sans-serif;color:#7A3028">
      {comp.pct(len(riesgo) / len(alumnos) * 100)} de la base · {por_materia}</p>
    <p style="margin:0;font:400 12.5px Inter,sans-serif;line-height:1.55;color:#7A3028">
      Están abajo de la mediana de {EN_PROSA[variable]} de su materia y quedan libres a la fecha de corte.
      Es el grupo al que conviene escribirle primero: la lista está en <strong>Cuadrante de riesgo</strong>.</p>
  </div>
</div>""")

tab_disp, tab_corr, tab_nivel, tab_cuad = st.tabs(
    ["Dispersión", "Correlaciones", "Por nivel de actividad", "Cuadrante de riesgo"])

# ---------------------------------------------------------------------------
# Dispersión con tendencia
# ---------------------------------------------------------------------------
with tab_disp, st.container(border=True):
    c1, c2 = st.columns([3, 1.3], vertical_alignment="center")
    comp.html(f'<p class="tfi tfi-texto" style="font-size:12.5px">Cada punto es un alumno: {nombre_var.lower()} '
              "contra su nota al corte, en la escala de la materia. El color es la condición. La línea negra une la "
              "<strong>nota promedio de cada quinto</strong> de alumnos, del 20 % con menos actividad al que más: "
              "si sube, a más actividad, más nota.</p>", c1)
    escala_log = c2.toggle("Eje horizontal logarítmico", key="nvp_log",
                           help="Separa a los alumnos con poca actividad, que en escala lineal quedan "
                                "amontonados a la izquierda. Los que tienen 0 no se ven en esta escala.")
    presentes = [c for c in [*CONDICIONES, SIN_EVALUACIONES] if c in set(puntos["condicion"])]
    comp.html(comp.leyenda([(c, comp.COLORES_CONDICION[c], "punto") for c in presentes]
                           + [("Promedio por quinto", comp.TEXTO, "linea")]))
    cols = st.columns(len(materias)) if len(materias) > 1 else [st.container()]
    for col, materia in zip(cols, materias):
        datos_m = puntos[puntos["asignatura"] == materia]
        tend = niveles[niveles["asignatura"] == materia].sort_values("orden")
        esq = ESQUEMA[materia]
        comp.html(comp.titulo_materia(materia, f"nota sobre {esq['total_max']}"), col)
        fig = go.Figure()
        for cond in [*CONDICIONES, SIN_EVALUACIONES]:
            q = datos_m[datos_m["condicion"] == cond]
            if q.empty:
                continue
            fig.add_trace(go.Scatter(
                x=q[variable], y=q["nota_final"], mode="markers", name=cond,
                marker=dict(color=comp.COLORES_CONDICION[cond], size=7, opacity=0.75,
                            line=dict(width=0.6, color="white")),
                customdata=q[["nombre_completo", "id_alumno"]],
                hovertemplate="%{customdata[0]} (%{customdata[1]})<br>" + nombre_var + ": %{x:,.0f}"
                              "<br>Nota: %{y:.1f}<extra>" + cond + "</extra>"))
        fig.add_trace(go.Scatter(
            x=tend["mediana_actividad"], y=tend["nota_final"], mode="lines+markers", name="Promedio por quinto",
            line=dict(color=comp.TEXTO, width=2), marker=dict(size=7, color=comp.TEXTO),
            customdata=tend[["nivel", "alumnos"]],
            hovertemplate="Actividad %{customdata[0]} (%{customdata[1]} alumnos)<br>"
                          "Nota promedio: %{y:.1f}<extra></extra>"))
        for nombre, corte in esq["cortes"].items():
            fig.add_hline(y=corte, line_dash="dash", line_color=comp.COLORES_CONDICION[nombre], line_width=1.2,
                          annotation_text=nombre, annotation_position="top right",
                          annotation_font=dict(color=comp.TONOS[comp.TONO_CONDICION[nombre]][2], size=11))
        fig.update_layout(height=300, showlegend=False, margin=dict(t=8, l=4, r=4, b=4))
        fig.update_xaxes(title_text=nombre_var, type="log" if escala_log else "linear", showgrid=False)
        fig.update_yaxes(title_text=None, range=[-4, esq["total_max"] + 4])
        col.plotly_chart(fig, width="stretch", key=f"disp_{materia}")

        # Conclusión de la materia, con los datos.
        med = datos_m[variable].median()
        no_rinden = int(((datos_m["rendidos"] == 0) & (datos_m[variable] > med)).sum())
        if no_rinden >= max(3, 0.05 * len(datos_m)):
            comp.html(f'<p class="tfi tfi-texto num" style="font-size:12px;font-weight:500;color:#93241C">'
                      f"{no_rinden} alumnos no rindieron nada aunque su actividad está sobre la mediana: "
                      "entran, pero no rinden.</p>", col)
        elif len(tend) >= 2 and tend["nota_final"].notna().all():
            a, b = tend["nota_final"].iloc[0], tend["nota_final"].iloc[-1]
            comp.html(f'<p class="tfi tfi-texto num" style="font-size:12px">Del quinto con menos actividad al '
                      f"que más, la nota promedio va de {comp.num(a, 1)} a {comp.num(b, 1)}"
                      f"{'.' if b > a else ': más actividad no se traduce en más nota.'}</p>", col)

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


with tab_corr:
    sig = corr.pivot(index="variable", columns="asignatura", values="significativa").reindex(columns=materias)
    filas = []
    for var in promedio.index:
        nombre = VARIABLES_CRUCE[var].replace(" (reporte)", "").replace(" (sesiones)", "")
        origen = f'<br><span class="sub">{ORIGEN[var]}</span>' if var in ORIGEN else ""
        elegida_css = ' style="background:#F4F8FC"' if var == variable else ""
        celdas = "".join(f"<td>{barrita(matriz.loc[var, m], bool(sig.loc[var, m]))}</td>" for m in materias)
        p = promedio[var]
        filas.append(f'<tr{elegida_css}><td><strong style="font-weight:600">{nombre}</strong>{origen}</td>{celdas}'
                     f'<td class="num" style="font-weight:600">{comp.num(p, 2)} '
                     f'{comp.chip(fuerza(p), TONO_FUERZA[fuerza(p)], con_icono=False)}</td></tr>')
    encabezados = "".join(f'<th scope="col">{comp.SIGLAS[m]}</th>' for m in materias)
    comp.html(f"""
<div class="tfi tfi-card" style="margin-bottom:14px">
  <p class="tfi-h3">Qué forma de participar acompaña mejor a la nota</p>
  <p class="tfi-desc">Correlación de Spearman entre cada variable y la nota sobre 100, dentro de cada materia.
    Va de 0 (ninguna relación) a 1 (el orden por actividad coincide con el orden por nota). Ordenadas de mayor
    a menor; la fila resaltada es la elegida arriba.{' Solo con quienes rindieron al menos una evaluación.' if solo_rindieron else ''}</p>
  <div style="overflow-x:auto"><table class="tfi-tabla">
    <thead><tr><th scope="col">Forma de participar</th>{encabezados}<th scope="col">Promedio</th></tr></thead>
    <tbody>{''.join(filas)}</tbody></table></div>
</div>""")

    # Qué hacer con esto (con los datos) y cómo leer el número.
    puntos_clave = []
    if not promedio.empty:
        mejor = promedio.index[0]
        puntos_clave.append((comp.ACCION, f"<strong>Usar {EN_PROSA[mejor]} para detectar temprano.</strong> Es la "
                                          f"señal más fuerte en promedio (ρ {comp.num(promedio[mejor], 2)})."))
        celdas = matriz.stack().dropna()
        if not celdas.empty:
            v_floja, m_floja = celdas.idxmin()   # índice (variable, materia)
            puntos_clave.append((comp.ATENCION, f"<strong>Lo más flojo es {EN_PROSA[v_floja]} en {m_floja}</strong> "
                                                f"(ρ {comp.num(celdas.min(), 2)}): con esa variable sola no alcanza "
                                                "para anticipar la nota."))
        regularidad = promedio.reindex(["dias_activos", "semanas_activas"]).mean()
        intensidad = promedio.reindex(["minutos", "tiempo_uso_min"]).mean()
        if pd.notna(regularidad) and pd.notna(intensidad):
            if regularidad >= intensidad:
                txt = (f"<strong>La regularidad vale más que la intensidad.</strong> Días y semanas con actividad "
                       f"(ρ {comp.num(regularidad, 2)}) acompañan más a la nota que los minutos acumulados "
                       f"(ρ {comp.num(intensidad, 2)}).")
            else:
                txt = (f"<strong>La intensidad pesa más que la regularidad.</strong> Los minutos acumulados "
                       f"(ρ {comp.num(intensidad, 2)}) acompañan más a la nota que los días y semanas con actividad "
                       f"(ρ {comp.num(regularidad, 2)}).")
            puntos_clave.append((comp.BIEN, txt))
    items = "".join(f'<div style="display:flex;gap:11px;margin-bottom:12px">'
                    f'<span style="flex:0 0 8px;height:8px;margin-top:6px;border-radius:2px;background:{c}"></span>'
                    f'<p class="tfi-texto">{t}</p></div>' for c, t in puntos_clave)

    n_min, n_max = corr["n"].min(), corr["n"].max()
    n_txt = f"n = {n_min}" if n_min == n_max else f"n entre {n_min} y {n_max}"
    k_sig, total = int(corr["significativa"].sum()), int(corr["rho"].notna().sum())
    if k_sig == total:
        sig_txt = (f"Todas dan p &lt; 0,05 con {n_txt}, así que ninguna es casualidad. Pero <strong>significativa no "
                   "quiere decir importante</strong>: con muestras grandes, hasta una relación chica da significativa.")
    else:
        sig_txt = (f"{k_sig} de {total} dan p &lt; 0,05 ({n_txt}); las que no, están marcadas con «n.s.». Y "
                   "<strong>significativa no quiere decir importante</strong>: mirá también el tamaño de ρ.")
    escala = "".join(f'<div style="display:flex;gap:12px;margin-bottom:8px"><span class="num" style="flex:0 0 64px;'
                     f'font:600 12px Inter,sans-serif">{a}</span><span class="tfi-texto" style="font-size:12px">{b}'
                     f"</span></div>" for a, b in [("&lt; 0,10", "sin relación"), ("&lt; 0,30", "débil"),
                                                   ("&lt; 0,50", "moderada"), ("≥ 0,50", "fuerte")])
    comp.html(f"""
<div class="tfi" style="display:flex;flex-wrap:wrap;gap:14px;margin-bottom:14px">
  <div class="tfi-card" style="flex:1 1 340px;min-width:280px">
    <p class="tfi-h3" style="margin-bottom:12px">Qué hacer con esto</p>{items}
  </div>
  <div class="tfi-card" style="flex:1 1 340px;min-width:280px">
    <p class="tfi-h3" style="margin-bottom:12px">Cómo leer el número</p>{escala}
    <p class="tfi-nota" style="background:#FBF0DC;color:#6B4700;margin-top:8px">{sig_txt}</p>
  </div>
</div>""")

    vista = corr.assign(
        Materia=corr["asignatura"], Variable=corr["descripcion"], ρ=corr["rho"],
        **{"p-valor": corr["p_valor"], "Alumnos (n)": corr["n"], "Fuerza": corr["fuerza"],
           "Significativa (p < 0,05)": corr["significativa"]},
    )[["Materia", "Variable", "ρ", "p-valor", "Alumnos (n)", "Fuerza", "Significativa (p < 0,05)"]]
    with st.expander("Ver la tabla con p-valor y n", icon=":material/table:"):
        st.dataframe(vista, hide_index=True, width="stretch",
                     column_config={"ρ": st.column_config.NumberColumn(format="%.2f"),
                                    "p-valor": st.column_config.NumberColumn(format="%.4f")})
        comp.boton_csv(vista, "correlaciones_notas_participacion")

# ---------------------------------------------------------------------------
# Por nivel de actividad (quintiles)
# ---------------------------------------------------------------------------
with tab_nivel:
    columnas_cond = {"Promociona": "pct_promociona", "Regular": "pct_regular", "Libre": "pct_libre",
                     SIN_EVALUACIONES: "pct_sin_evaluaciones"}
    con_datos = [c for c, col in columnas_cond.items() if not niveles.empty and niveles[col].sum() > 0]
    bloques, frases = [], []
    for materia in materias:
        n_m = niveles[niveles["asignatura"] == materia].sort_values("orden")
        if n_m.empty:
            continue
        filas = []
        for fila in n_m.itertuples():
            segmentos = "".join(
                f'<span style="width:{getattr(fila, columnas_cond[c]):.1f}%;background:{comp.COLORES_CONDICION[c]}"'
                f' title="{c}: {comp.pct(getattr(fila, columnas_cond[c]), 0)}">'
                f'{comp.pct(getattr(fila, columnas_cond[c]), 0) if getattr(fila, columnas_cond[c]) >= 12 else ""}</span>'
                for c in con_datos)
            filas.append(f'<div class="tfi-apilada"><span class="izq num">{fila.nivel} '
                         f'<span>{comp.num(fila.desde)}–{fmt_var(fila.hasta)}</span></span>'
                         f'<span class="barra">{segmentos}</span>'
                         f'<span class="der num" title="Nota promedio sobre 100">{comp.num(fila.nota_pct, 1)}</span></div>')
        bloques.append(f'{comp.titulo_materia(materia, "nota promedio")}{"".join(filas)}<div style="height:14px"></div>')
        if n_m["nota_pct"].notna().any() and len(n_m) >= 2:
            lo, hi = n_m["pct_libre"].iloc[0], n_m["pct_libre"].iloc[-1]
            frases.append(f"<strong>{comp.SIGLAS[materia]}:</strong> del 20 % con menos actividad, "
                          f"{de_cada_10(lo)} de cada 10 quedan libres; del 20 % con más, {de_cada_10(hi)}.")

    leyenda = comp.leyenda([(c, comp.COLORES_CONDICION[c], "cuadro") for c in con_datos])
    resumen = comp.aviso("<strong>Dicho sin estadística:</strong><br>" + "<br>".join(frases)) if frases else ""
    comp.html(f"""
<div class="tfi tfi-card">
  <p class="tfi-h3">La misma historia, sin estadística</p>
  <p class="tfi-desc">Los alumnos de cada materia se ordenan por {nombre_var.lower()} y se parten en cinco grupos
    del mismo tamaño. Cada barra muestra cómo queda la condición dentro del grupo; el número de la derecha es la
    nota promedio sobre 100.</p>
  {leyenda}<div style="height:6px"></div>{''.join(bloques)}{resumen}
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
with tab_cuad:
    conteo = alumnos.groupby(["asignatura", "cuadrante"]).size()
    grillas = []
    for materia in materias:
        datos_m = alumnos[alumnos["asignatura"] == materia]
        mediana = datos_m["mediana_actividad"].iloc[0]
        celdas = []
        for cuad, (tono, corto, _) in CUADRANTES.items():
            n = int(conteo.get((materia, cuad), 0))
            fondo, borde, c_num, c_txt = COLOR_CUADRANTE[tono]
            celdas.append(f'<div style="background:{fondo};border-color:{borde}"><p class="n num" style="color:{c_num}">'
                          f'{comp.num(n)}</p><p class="t" style="color:{c_txt}">{corto} '
                          f'<span class="num">· {comp.pct(n / len(datos_m) * 100, 0)}</span></p></div>')
        grillas.append(f'<div>{comp.titulo_materia(materia, "mediana " + fmt_var(mediana))}'
                       f'<div class="tfi-cuadrante">{"".join(celdas)}</div></div>')

    sin_nada = int((riesgo["rendidos"] == 0).sum())
    acciones = []
    for cuad in ["Riesgo: poca actividad y nota baja", "Activo con nota baja", "Poca actividad con buena nota",
                 "Activo con buena nota"]:
        tono, corto, texto = CUADRANTES[cuad]
        if not texto:
            texto = (f"Contactar primero. Son {comp.num(len(riesgo))} en total y {comp.num(sin_nada)} "
                     "no rindieron nada.")
        acciones.append(f'<div><p style="margin:0 0 4px;display:flex;align-items:center;gap:7px;'
                        f'font:600 12px Inter,sans-serif;color:{comp.TONOS[tono][2]}">{comp.icono(tono, 11)}{corto}</p>'
                        f'<p class="tfi-texto" style="font-size:12px">{texto}</p></div>')
    comp.html(f"""
<div class="tfi tfi-card" style="margin-bottom:14px">
  <p class="tfi-h3">Cuatro grupos, cuatro acciones distintas</p>
  <p class="tfi-desc">Se parte a los alumnos según dos preguntas: ¿su {nombre_var.lower()} está por debajo de la
    mediana de su materia? y ¿está libre al corte? Incluye a toda la base, también a quienes no rindieron nada.</p>
  <div class="tfi-grilla" style="grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px">{''.join(grillas)}</div>
  <div class="tfi-grilla" style="margin-top:18px;padding-top:18px;border-top:1px solid #EFEDE8">{''.join(acciones)}</div>
</div>""")

    with st.expander("Ver el gráfico de cuadrantes", icon=":material/scatter_plot:"):
        cols = st.columns(len(materias)) if len(materias) > 1 else [st.container()]
        for col, materia in zip(cols, materias):
            datos_m = alumnos[alumnos["asignatura"] == materia]
            esq = ESQUEMA[materia]
            mediana = datos_m["mediana_actividad"].iloc[0]
            comp.html(comp.titulo_materia(materia, f"nota sobre {esq['total_max']}"), col)
            fig = go.Figure()
            for cuad, (tono, corto, _) in CUADRANTES.items():
                q = datos_m[datos_m["cuadrante"] == cuad]
                fig.add_trace(go.Scatter(
                    x=q[variable], y=q["nota_final"], mode="markers", name=corto,
                    marker=dict(color=comp.TONOS[tono][0], size=7, opacity=0.75, line=dict(width=0.6, color="white"),
                                symbol={"critico": "octagon", "atencion": "triangle-up", "serio": "diamond"}
                                .get(tono, "circle")),
                    customdata=q[["nombre_completo", "id_alumno"]],
                    hovertemplate="%{customdata[0]} (%{customdata[1]})<br>" + nombre_var + ": %{x:,.0f}"
                                  "<br>Nota: %{y:.1f}<extra>" + corto + "</extra>"))
            fig.add_vline(x=mediana, line_dash="dash", line_color=comp.NEUTRO,
                          annotation_text=f"Mediana: {fmt_var(mediana)}", annotation_position="top right",
                          annotation_font=dict(size=11, color=comp.TEXTO_3))
            fig.add_hline(y=esq["cortes"]["Regular"], line_dash="dash", line_color=comp.CRITICO, line_width=1.2,
                          annotation_text="Corte de Regular", annotation_position="bottom right",
                          annotation_font=dict(size=11, color=comp.TONOS["critico"][2]))
            fig.update_layout(height=320, showlegend=False, margin=dict(t=8, l=4, r=4, b=4))
            fig.update_xaxes(title_text=nombre_var, showgrid=False)
            fig.update_yaxes(title_text=None, range=[-4, esq["total_max"] + 4])
            col.plotly_chart(fig, width="stretch", key=f"cuad_{materia}")

    st.write("")
    with st.container(border=True):
        c1, c2 = st.columns([3, 1.4], vertical_alignment="bottom")
        comp.html(f'<p class="tfi tfi-h3">Alumnos en riesgo <span class="num" style="font:400 13px Inter,sans-serif;'
                  f'color:#6B6861">{comp.num(len(riesgo))}</span></p><p class="tfi tfi-texto" style="font-size:12px">'
                  "Ordenados por días sin entrar. Los que nunca entraron van primero.</p>", c1)
        lista = riesgo
        if len(materias) > 1 and not riesgo.empty:
            n_por = riesgo["asignatura"].value_counts()
            opciones = [comp.TODAS, *[m for m in materias if n_por.get(m, 0)]]
            filtro = c2.selectbox("Materia de la lista", opciones, key="nvp_riesgo_materia",
                                  format_func=lambda m: m if m == comp.TODAS else f"{m} ({n_por[m]})")
            if filtro != comp.TODAS:
                lista = riesgo[riesgo["asignatura"] == filtro]
        if riesgo.empty:
            st.success("No hay alumnos con poca actividad y condición Libre a la fecha de corte.")
        else:
            lista = lista.assign(_nunca=lista["estado_actividad"].eq(SIN_ACTIVIDAD)).sort_values(
                ["_nunca", "dias_sin_actividad", "nota_pct"], ascending=[False, False, True])
            tabla = pd.DataFrame({
                "Alumno": lista["nombre_completo"], "ID": lista["id_alumno"],
                "Materia": lista["asignatura"].map(comp.SIGLAS),
                "Actividad": comp.con_icono(lista["estado_actividad"].replace({SIN_ACTIVIDAD: "Nunca entró"}),
                                            {**comp.ICONOS_ACTIVIDAD, "Nunca entró": "■"}),
                "Sin entrar": [("—" if e == SIN_ACTIVIDAD or pd.isna(dias) else f"{dias:.0f} d")
                               for e, dias in zip(lista["estado_actividad"], lista["dias_sin_actividad"])],
                "Nota": [f"{comp.num(n, 1)} / {e}" for n, e in zip(lista["nota_final"], lista["escala"])],
                "Rindió": lista["rendidos"].astype(int).astype(str) + " de " + lista["instrumentos"].astype(int).astype(str),
                nombre_var: lista[variable], "Mediana de la materia": lista["mediana_actividad"],
                "Inscripto": lista["inscripto"].map({True: "Sí", False: "No"}),
            })
            st.dataframe(tabla, hide_index=True, width="stretch", height=min(38 + 35 * len(tabla), 420),
                         column_config={
                             nombre_var: st.column_config.NumberColumn(format="%.0f"),
                             "Mediana de la materia": st.column_config.NumberColumn(format="%.0f"),
                         })
            c1, c2 = st.columns([3, 1], vertical_alignment="center")
            c1.caption(f"Mostrando {comp.num(len(tabla))} de {comp.num(len(riesgo))}. La mediana de la materia está "
                       "para comparar: el valor del alumno queda siempre por debajo, por definición del cuadrante.")
            with c2:
                comp.boton_csv(tabla, f"alumnos_en_riesgo_{variable}")
