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

## D79 · Rediseño del dashboard Participación
- **Decisión:** la página responde "quién sigue entrando, quién se está yendo y en qué materia". Hero con el % de
  activos, su Δ contra el mismo % medido 7 días antes (ventana móvil) y la referencia al cierre de la semana 2
  (primer dato + 13 días), y la lista de los que se están enfriando. Cuatro KPIs con su base temporal:
  sesiones y minutos por alumno **por semana** (período; semanas = días / 7; Δ contra el período anterior de igual
  duración solo si entra entero en los datos), avance (foto del LMS) y **retención semanal** (al corte:
  de los que entraron en [corte−13, corte−7], qué % entró en [corte−6, corte]). Funciones `ritmo_semanal`,
  `retencion_semanal`, `acceso_semanal` y `semanas_sin_actividad` en `src/metricas.py`. Se quitan "Qué se movió
  esta semana", "Resumen por materia", "Uso de foros" y el control de calidad, que pasa a
  `analysis/validacion_sesiones.py` (guarda gráfico y ρ en `reports/`).
- **Avance al corte (descartado):** la trazabilidad trae el recurso (nombre entre comillas en Descripción) pero no su
  fecha de publicación; con denominador = recursos abiertos por al menos un alumno de la materia hasta el corte, la
  validación al 24/10 contra el avance del LMS dio ρ = 0,993 en AED, 0,986 en PyE y 0,852 en Álgebra (diferencia
  media −0,9, +3,7 y −17,6 pts). Álgebra queda debajo de 0,9, así que se mantiene la foto del LMS en las tres
  materias, con el chip "Foto LMS 24/10" y la tarjeta atenuada cuando la fecha de corte es otra (D36, D76).
- **Por qué:** los totales por alumno no se comparan entre períodos de distinto largo; por semana sí. La retención
  dice si los que venían entrando siguen, que el % de activos solo no muestra.
- **Estado:** vigente.

## D80 · KPIs y rediseño del dashboard Trazabilidad
- **Decisión:** cuatro tarjetas, calculadas en `resumen_trazabilidad` (período y período anterior de igual largo, solo
  si entra entero en los datos; Δ en las tres primeras cuando el período no es toda la cursada):
  - **Días con ingreso por semana:** mediana, entre los alumno-materia de la base que entraron al menos una vez en el
    período, de días distintos con interacciones / (días del período / 7). Días del período = de `desde` (o el primer
    dato) a la fecha de corte, inclusive.
  - **Interacciones por día de ingreso:** mediana de interacciones / días con ingreso entre esos mismos alumnos; abajo,
    el total y el total / días calendario (interacciones promedio por día de la consigna).
  - **Clics en Evaluación:** % de las interacciones de tipo Evaluación (interacciones por tipo de la consigna).
  - **Clics entre 18 y 24 h:** % de las interacciones con hora 18 a 23 (distribución temporal; hora del servidor).
  `frecuencia_ingreso` reparte a los que entraron en tramos de días con ingreso por semana (0–1, 1–2, 2–3, 3–4, 4 o
  más) o por mes (días / (días del período / 30): 1–3, 4–7, 8–11, 12–15, 16 o más), que es la frecuencia de ingreso
  semanal/mensual de la consigna. Las franjas noche / mañana / fin de semana pasan a `franjas_horarias`.
- **Por qué:**
  - *Días con ingreso y no sesiones:* la sesión depende del corte de 30 minutos sin eventos (D25) y el LMS registra
    clics de navegación muy seguidos; "entró ese día" no depende de ese parámetro y se explica en una frase.
  - *Mediana y no promedio:* la distribución de interacciones por alumno tiene cola larga (unos pocos alumnos con
    cientos de clics por día); la mediana describe al alumno típico y no se mueve por un caso extremo.
  - *Denominador = alumnos que entraron:* "Sin actividad" ya se mide en Participación y Matrícula; sumarlos con 0
    mezclaría "cuánto entran los que cursan" con "cuántos no entran nunca".
  - *Por semana y no totales:* los totales dependen del largo del período; normalizados por semana se comparan
    "Últimas 2 semanas" con "Toda la cursada" y con el período anterior.
- **Pantalla:** el dashboard muestra datos, no explica. Los títulos dicen el dato principal calculado con los datos, el
  subtítulo solo cómo leer el gráfico y las limitaciones (hora del servidor, períodos incompletos, superposición de
  las evaluaciones de PyE, qué acciones entran en cada tipo) van en el (?) de cada tarjeta. Las interpretaciones que
  estaban en pantalla se guardaron con sus valores al 24/10/2025 en `docs/conclusiones_trazabilidad.md`. Pestañas:
  Cuándo y cada cuánto entran · Qué hacen · Evolución (siempre por alumno; períodos cortados con marcador hueco,
  `evolucion_interacciones` suma `dias`, `dias_periodo` y `completo`) · Alrededor de las evaluaciones. Números en
  es-AR también en plotly (`separators=",."`) y en las tablas (Styler, que se sigue ordenando como número).
- **Zona horaria:** las fechas vienen sin zona; la evidencia (último evento de cada archivo minutos antes de la hora de
  exportación, coordinadores de 7 a 21 h) apunta a hora local. Se deja como está, rotulado "hora del servidor del LMS",
  hasta que lo confirme la cátedra.
- **Estado:** vigente.
