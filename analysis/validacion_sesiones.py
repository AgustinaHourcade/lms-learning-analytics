"""
Validación de las sesiones armadas con la trazabilidad (D25), para el informe.

Antes era el bloque "Control de calidad del dato" del dashboard de Participación.
Compara, por alumno, los minutos que salen de las sesiones (eventos cortados a los
30 minutos sin actividad) contra el tiempo estimado de uso que informa el LMS en el
reporte de participación. Como el reporte es una foto, se compara a su fecha
(FECHA_CORTE_DEFECTO). El cálculo es src.metricas.concordancia_tiempo.

Ejecutar desde la raíz:
    python -m analysis.validacion_sesiones

Guarda en reports/:
    validacion_sesiones.html   dispersión por alumno (plotly, interactiva)
    validacion_sesiones.csv    ρ de Spearman, p-valor, n y totales por materia
    validacion_sesiones.md     la misma tabla, lista para pegar en el informe
"""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go

from src import metricas
from src.config import FECHA_CORTE_DEFECTO, REPORTS


def calcular(d: metricas.Datos | None = None):
    d = d or metricas.cargar()
    rho = metricas.concordancia_tiempo(d)
    rho["pct_minutos_sobre_lms"] = (rho["minutos_total"] / rho["tiempo_uso_total"] * 100).round(1)
    puntos = metricas.participacion_alumnos(d, FECHA_CORTE_DEFECTO).dropna(subset=["tiempo_uso_min"])
    return rho, puntos


def grafico(puntos) -> go.Figure:
    fig = px.scatter(puntos, x="tiempo_uso_min", y="minutos", color="asignatura", hover_name="nombre_completo",
                     opacity=0.75, labels={"tiempo_uso_min": "Minutos informados por el LMS",
                                           "minutos": "Minutos según las sesiones", "asignatura": ""},
                     title=f"Minutos por sesiones vs. tiempo de uso del LMS (al {FECHA_CORTE_DEFECTO})")
    tope = float(max(puntos["tiempo_uso_min"].max(), puntos["minutos"].max()))
    fig.add_trace(go.Scatter(x=[0, tope], y=[0, tope], mode="lines", name="Iguales",
                             line=dict(color="#A8A49B", dash="dash", width=1.4), hoverinfo="skip"))
    fig.update_layout(template="plotly_white")
    return fig


def main() -> None:
    rho, puntos = calcular()
    REPORTS.mkdir(parents=True, exist_ok=True)
    grafico(puntos).write_html(REPORTS / "validacion_sesiones.html", include_plotlyjs="cdn")
    rho.to_csv(REPORTS / "validacion_sesiones.csv", index=False)
    filas = "\n".join(f"| {r.asignatura} | {r.rho:.3f} | {r.p_valor:.2g} | {r.n} | {r.pct_minutos_sobre_lms:.0f} % |"
                      for r in rho.itertuples())
    (REPORTS / "validacion_sesiones.md").write_text(
        f"# Validación de las sesiones (al {FECHA_CORTE_DEFECTO})\n\n"
        "Spearman entre los minutos por sesiones (corte a los 30 min sin eventos) y el tiempo de uso del LMS, "
        "por alumno.\n\n| Materia | ρ | p-valor | n | Minutos por sesiones / tiempo LMS |\n|---|---|---|---|---|\n"
        f"{filas}\n\nLos minutos propios quedan por debajo porque no cuentan el rato posterior al último clic.\n",
        encoding="utf-8")
    print(rho.to_string(index=False))
    print(f"Guardado en {REPORTS}")


if __name__ == "__main__":
    main()
