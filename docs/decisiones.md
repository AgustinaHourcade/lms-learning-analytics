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

## D81 · "Aprobó" un instrumento = nota ≥ 60 sobre 100
- **Decisión:** `promedio_por_instrumento.pct_aprobada` es el % de quienes rindieron el instrumento con nota ≥
  `APROBADO_PCT` (60) sobre 100. La columna Observaciones del Excel queda como `pct_aprobada_lms`, solo para
  comparar. El titular de Rendimiento ("el X % de lo entregado tiene 60 o más") usa esta definición.
- **Por qué:** Observaciones ("aprobada" / "no aprobada") no es un corte fijo de la nota. Al 24/10/2025, de 1.793
  notas: en Álgebra y AED "aprobada" es casi cualquier entrega (27 "aprobada" con menos de 60, desde 12 %: ALG-03
  15 casos, ALG-01 6, ALG-02 4, AED-03 2 con 30 y 50; los únicos "no aprobada" son notas de 0 y 50). En PyE sí
  depende de la nota, pero con un corte propio de cada instrumento y más alto que 60 (27 notas ≥ 60 marcadas "no
  aprobada"; en Actividad Rápida 4, "aprobada" empieza en 87,5). Con un corte único los instrumentos se comparan.
- **Efecto:** en el total casi no cambia (95,5 % con los dos criterios); por instrumento sí: PyE Actividad Rápida 4
  pasa de 67,6 % a 87,0 %, Álgebra 1° Parcial de 99,4 % a 90,1 %.
- **Estado:** vigente.

## D82 · Instrumentos cerrados, caída de la entrega y "dejaron de entregar"
- **Decisión:** un instrumento está **cerrado** si `fecha_instrumento <= fecha de corte − DIAS_CIERRE` (7 días);
  si no, está **abierto** (todavía recibe entregas). Sin fecha inferida = cerrado. Sobre los cerrados, sin
  recuperatorios:
  - `caida_entrega`: por materia, % de la base que rindió el primer instrumento y el último cerrado y la diferencia
    en puntos porcentuales; también `empezaron` y `dejaron`.
  - `dejaron_de_entregar`: alumnos de la base que rindieron al menos un instrumento cerrado y ninguno de los
    `ULTIMOS_CERRADOS` (2) últimos cerrados ni de los abiertos. Solo en materias con 3 o más cerrados.
  - La **tasa de entrega** de Rendimiento se calcula sobre los cerrados (si todavía no hay ninguno, sobre todos).
- **Por qué:** la fecha del instrumento es la mediana de los intentos (D18), así que justo después de esa fecha
  falta la mitad de las entregas. Al 24/10/2025 los datos terminan ese día (no hay intentos posteriores para
  medir), pero AED Unidad 5 (21/10) tenía sus 24 intentos en los últimos 7 días y PyE Evaluación Semanal Nº2
  (23/10) sus 13: comparados con instrumentos cerrados exageran la caída (AED daba 71 % → 12 %; cerrado, 71 % →
  31 %). Los que rindieron un abierto no "dejaron": todavía están entregando. Se excluye al que solo rindió un
  recuperatorio: no empezó la cursada normal.
- **Límite conocido:** las autoevaluaciones de AED y las actividades de PyE reciben entregas tardías (≈30 % de los
  intentos después de la semana de la mediana); con 7 días PyE Actividad Rápida 5 (15/10, 9 días) ya cuenta como
  cerrada aunque tuvo 18 de sus 54 intentos en la última semana. Si se quiere más prudencia, subir `DIAS_CIERRE`.
- **Valores al 24/10/2025:** tasa de entrega 58,2 % (1.735 de 2.979, antes 52,1 % con los abiertos); primera →
  última −28 pp; dejaron de entregar 109 (66 AED, 23 PyE, 20 Álgebra) = 20,4 % de los 534 que habían empezado.
- **Estado:** vigente.

## D83 · Libres recuperables
- **Decisión:** `libres_recuperables` = alumnos con condición Libre, al menos un instrumento rendido y nota final ≥
  corte de Regular − `MARGEN_RECUPERABLE` (10 puntos en la escala de la materia: Álgebra de 50 a 60 sobre 120, AED y
  PyE de 50 a 60 sobre 100). `faltan` = puntos hasta Regular.
- **Por qué:** son los que pueden cambiar de condición con el próximo instrumento: la lista a quién intervenir
  primero. Es el mismo cálculo que hacía el bloque "Para leer" de la Distribución, ahora como métrica con test.
- **Valores al 24/10/2025:** 28 (5 Álgebra, 12 AED, 11 PyE).
- **Estado:** vigente.

## D84 · Rediseño del dashboard Rendimiento académico
- **Decisión:** la página tiene que leerse en 5 segundos ("quedan libres porque dejan de entregar, no porque les vaya
  mal") y mostrar a quién intervenir. Orden: encabezado ("Notas y condición al dd/mm · materia", menú Descargar con
  los dos CSV) → mensaje armado con los números (nota de lo entregado vs. nota con los 0 por no entregar y con los
  que no rindieron nada) → 4 KPIs (Tasa de entrega con la caída primera → última; Dejaron de entregar y Libres
  recuperables, con la lista y su CSV; Sin ninguna entrega) → tarjeta por materia (nota de quienes rindieron en su
  escala, Álgebra "proyectada"; barra de condición; entrega primero → último cerrado) → pestañas Por instrumento ·
  Distribución · Evolución de la condición.
- **Se quitó:** la pestaña Tabla (el CSV sigue en Descargar), la tarjeta "Instrumento más flojo" y su resaltado, la
  "nota promedio de todos" como cifra grande (mezcla escalas y duplica alumnos: queda en la frase), la tarjeta
  agregada "Condición al corte" (reemplazada por las barras por materia) y el bloque "Para leer" (pasó a KPI). El
  umbral de inactividad no cambia nada en esta página: `barra_lateral(sin_umbral=True)` lo oculta.
- **Colores:** las barras de entrega van en gris si están bien, ámbar con menos de 50 % y rojo con menos de 30 %
  (no se confunden con el naranja de AED ni el verde de PyE); los abiertos, rayados; el recuperatorio, gris. Las
  cajas van en azul de acción. Los números grandes no llevan semáforo; el verde queda para Promociona.
- **Textos:** los títulos de cada materia en Por instrumento y de Evolución se arman con los datos ("AED: la entrega
  cae de 71 % a 31 % con promedios de 92 a 96", "Promociona cae en las tres materias desde agosto"). Las definiciones
  van en el (?) de cada pieza, sin códigos D (lo controla `test_sin_codigos_de_decision_visibles`).
- **Estado:** vigente.

## D85 · Rediseño del dashboard Notas vs. participación
- **Decisión:** la página se lee de arriba abajo así: subtítulo → **lectura principal** armada con
  `nota_por_nivel_actividad` ("Del 20 % con menos minutos quedan libres 8 de cada 10 en ALG...; del 20 % con más,
  menos de 1, 5 y 3", `textos.lectura_quintiles`; reemplaza al recuadro "Dicho sin estadística" de Por nivel) →
  controles → **4 KPIs** → pestañas **Dispersión · Por nivel de actividad · Cuadrante de riesgo · Correlaciones**,
  cada una con un título que es la conclusión, calculado con los datos.
- **KPIs y métricas nuevas** (en `src/metricas.py`, con tests):
  1. *Casos en riesgo* (`casos_en_riesgo`): casos alumno–materia debajo de la mediana y libres (D37), los alumnos
     distintos detrás (fila `Todas`), cuántos no rindieron nada y la misma cuenta a la fecha de corte − 7 días (con
     la mediana y la condición de esa fecha). Tarjeta roja con el botón "Prioridad de contacto →", que abre la
     pestaña del cuadrante (`st.tabs(key="nvp_pestana")`).
  2. *Brecha de libres* (`brecha_libres`): %Libre del quinto con menos actividad − %Libre del quinto con más, por
     materia, en puntos porcentuales. Sigue el interruptor "solo quienes rindieron".
  3. *Activos que igual quedan libres* (`activos_libres`): libres / alumnos con la variable igual o por encima de la
     mediana de su materia.
  4. *ρ de la variable elegida*: los dos valores (todos / solo quienes rindieron) y la comparación con la variable
     de mayor ρ promedio.
- **Correcciones de credibilidad:** Spearman va de −1 a 1 (el texto decía de 0 a 1); "regularidad vs. minutos"
  compara promedio con promedio (días y semanas contra minutos de sesiones, ya no contra el promedio de minutos y
  tiempo del reporte) y dice "acompaña algo más"; "220 alumnos" pasa a "220 casos · 125 alumnos distintos" (al
  24/10/2025, 63 alumnos en una materia, 29 en dos y 33 en las tres) y la lista suma "Materias en riesgo"; el
  título "Usar el avance para detectar temprano" se reemplazó (la ρ es al corte y no prueba anticipación: se enlaza
  al Predictor de abandono).
- **Redondeo único:** `textos.numero` redondea "de escuela" (`textos.redondear`, 144,5 → 145), como los tooltips y
  las tablas del navegador. Antes la mediana de minutos de Álgebra (144,5) se veía 144 en el cuadrante y 145 en la
  lista. `componentes_notas.num` usa esa función.
- **Diseño:** cada color significa una sola cosa. Materias con la paleta de General (D78: ALG #1E4FA8, AED #7C3AED,
  PYE #0891B2); el cuadrante usa rojo solo para "debajo de la mediana y libre" y neutros para el resto; la
  dispersión, forma por condición (● Promociona, ▲ Regular, ⬣ Libre, opacidad 0,6), cuántos alumnos hay en (0, 0)
  y tooltips con coma decimal y escala ("78,0 / 120 (65,0 / 100)"); Álgebra se muestra "94,8/120 (79,0/100)" bajo
  los paneles, igual que Por nivel (sobre 100). En Por nivel, Libre va a la izquierda, se rotulan los segmentos
  ≥ 8 % y los rangos no se pisan (`textos.rangos_quintiles`: "hasta 59 · 60–116 · 117–186..."; con empates se
  repite el valor). Los cuadrantes se llaman "Debajo/Sobre la mediana, libre/no libre" (en `src/metricas.py`
  siguen las etiquetas de D37: solo cambia el nombre en pantalla). Se quitaron las pastillas de fuerza del
  promedio, la columna "Mediana de la materia" de la lista y las anotaciones encima de los puntos del gráfico de
  cuadrantes.
- **Textos:** "Cómo leer el número" (umbrales de Cohen) pasó al (?) de ρ; la nota "significativa no quiere decir
  importante" a la primera línea del expansor de la tabla con p-valor; ninguna explicación de más de 2 líneas fuera
  del (?) o de los expansores. El (?) del selector aclara que el *tiempo de conexión* de la consigna es "Minutos en
  la plataforma (sesiones)" y en qué se diferencia del "Tiempo estimado de uso (reporte)". Al pie, enlaces a Grupos
  de alumnos y Predictor de abandono. Sin códigos D en pantalla, tampoco en el (?) (`test_sin_codigos_de_decision_visibles`).
- **Estado:** vigente.

## D86 · El "Avance (%)" del reporte cuenta las evaluaciones realizadas
- **Hallazgo:** el Excel no define la columna, pero en las tres materias el avance se reconstruye casi exacto
  (R² entre 0,97 y 0,999) como la cantidad de ítems distintos que el alumno abrió (textos, archivos, temas) **más
  las evaluaciones que realizó**, cada una con el mismo peso que un texto. Las evaluaciones explican en promedio el
  5 % del avance en AED, el 10 % en PyE y el 20 % en Álgebra.
- **Efecto:** la correlación del avance con la nota es en parte circular (rendir sube el avance y la nota). Al
  24/10/2025, sin la parte de las evaluaciones, ρ baja de 0,76 a 0,72 en AED, de 0,77 a 0,70 en PyE y de 0,66 a 0,50
  en Álgebra (con solo quienes rindieron: 0,73 → 0,68, 0,70 → 0,60 y 0,56 → 0,38).
- **Decisión:** el avance se sigue mostrando (es un dato del LMS y la consigna pide cruzar participación con
  notas), pero se avisa en el (?) del selector y de Correlaciones y en la fila de la tabla ("cuenta las
  evaluaciones hechas"). La conclusión "el avance es lo que más acompaña a la nota" hay que leerla con ese límite;
  entre las variables de trazabilidad, la que más acompaña es semanas con actividad.
- **Estado:** vigente.
