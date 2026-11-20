# Registro de decisiones

> Nota: este archivo no estaba en el repositorio (CLAUDE.md y `docs/estado_y_pendientes.md` lo citan, pero no
> aparece en ninguna rama). Se crea con las decisiones nuevas desde D72; las D1-D71 hay que copiarlas acá desde
> donde las tenga el equipo. Los números no se reutilizan porque el código los cita.

Formato: número, decisión, por qué, estado.

---

## D72 · KPI "Alcanzan Regular"
- **Decisión:** % de alumnos × materia con condición Regular o Promociona sobre los que tienen condición a la fecha
  (los que ya tienen nota; "Sin evaluaciones" queda afuera). Usa el corte de cada materia (Álgebra 60/120, el resto
  60/100). Función `alcanzan_regular` en `src/metricas.py`. Reemplaza al KPI "Nota promedio" del dashboard General.
- **Por qué:** la nota promedio mezcla escalas y está arrastrada por los 0 de quienes no rinden; "cuántos llegan a
  regularizar" es la pregunta que se hace la cátedra y se lee igual en las tres materias.
- **Estado:** vigente.

## D73 · KPI "Alumnos en riesgo"
- **Decisión:** alumno × materia con condición Libre a la fecha de corte y que no entró en los últimos `umbral` días
  (estado Inactivo o Sin actividad). Función `alumnos_en_riesgo`.
- **Por qué:** junta las dos señales que ya usan las alertas (académica y de actividad) en un número accionable.
  Es más estricto que la alerta "Libre" sola: deja afuera a los libres que siguen entrando.
- **Estado:** vigente.

## D74 · Tasa de rendición
- **Decisión:** Σ instrumentos rendidos / Σ instrumentos disponibles a la fecha, sumando todos los alumnos de la base
  (alumno × instrumento). Rendido = tiene nota en el instrumento o en su recuperatorio (como en `nota_final`).
  El recuperatorio no suma un instrumento. Función `tasa_rendicion`.
- **Por qué:** separa "no se presentan" de "se presentan y les va mal", que la nota promedio confunde.
- **Estado:** vigente.

## D75 · Evaluaciones de la semana
- **Decisión:** son los instrumentos que cuentan para la nota final con fecha (D18) en (corte − 7 días, corte].
  Los recuperatorios no se cuentan (no rendirlos no da 0). "No rindieron alguna" = alumno × materia con al menos uno
  de esos instrumentos sin nota. Funciones `evaluaciones_en_periodo` y `no_rindieron_periodo`.
- **Por qué:** explica las caídas bruscas de la condición proyectada en el aviso semanal del dashboard General.
- **Estado:** vigente.

## D76 · Fecha del reporte de participación
- **Decisión:** la fecha de exportación del Excel de participación no llega a gold; se usa la última interacción que
  registra el reporte (`fecha_reporte_participacion`, hoy 24/10/2025). Si la fecha de corte es otra, el avance se
  muestra atenuado con "foto al dd/mm".
- **Por qué:** el avance no se puede recortar por fecha (D36); hay que avisarlo en vez de mostrarlo como si fuera
  de la fecha de corte. Pendiente opcional: llevar `fecha_exportacion` de participación a silver/gold.
- **Estado:** vigente.

## D77 · Textos dinámicos
- **Decisión:** los títulos que dicen conclusiones ("La mitad entró en los últimos 7 días", "el doble que") se arman
  con funciones puras en `src/textos.py` (`proporcion_en_palabras`, `comparacion_veces`, `enumerar`), con tests.
  Una proporción se dice en palabras si está a 3 pp o menos de la fracción (la mitad: 45-55 %).
- **Por qué:** que el texto nunca contradiga al número y se pueda probar sin levantar la app.
- **Estado:** vigente.

## D78 · Rediseño del dashboard General
- **Decisión:** una sola página sin pestañas (contexto, aviso de la semana, 4 KPIs, por materia, actividad,
  distribución, integridad). Materias como "Nombre completo (SIGLA)"; la sigla sola solo en desgloses.
  Paleta de materias fuera del semáforo: Álgebra `#1E4FA8` (azul), AED `#7C3AED` (violeta), PyE `#0891B2` (cian),
  elegida simulando deuteranopía y protanopía (ΔE CIELAB mínimo ≈ 27 entre materias y contra el semáforo).
  Texto oscuro sobre el ámbar del semáforo (blanco daba 2,9:1; oscuro da 6,0:1). Sin referencias D* en la interfaz.
  Por ahora la paleta nueva vale solo en General (`app/componentes_general.py`); el resto de las páginas sigue con la
  anterior.
- **Por qué:** los 4 pedidos de la consigna tienen que verse sin clicks y el verde/naranja de las materias chocaba
  con Promociona/Activo y Regular.
- **Estado:** vigente.
