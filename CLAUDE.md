# Contexto del proyecto para Claude Code

## Qué es
Trabajo Final Integrador de "Business Intelligence & Analytics" (Universidad de Palermo).
El objetivo es construir una herramienta de BI sobre datos anonimizados de un LMS para tres materias:
Álgebra, Algoritmos y Estructuras de Datos (AED) y Probabilidad y Estadística (PyE).
Es un trabajo en grupo; el repositorio se comparte por GitHub.
Se pide: integrar y limpiar los datos, definir KPIs, armar 7 dashboards en **Streamlit** y escribir un informe técnico.
La consigna completa está en `docs/consigna.pdf` (si existe).

## Forma de trabajo
- Responder en español rioplatense.
- Avanzar paso a paso: escribir el código, probarlo sobre los datos reales y explicarlo para que el usuario pueda contárselo al equipo.
- Se ejecuta siempre desde la raíz con `python -m src.<modulo>`. El pipeline completo: `python -m src.pipeline` (o `procesar()` desde la app). Tests: `python -m pytest`.
- Las rutas y las reglas de negocio están en `src/config.py`: no se escriben a mano en otros archivos.

## Arquitectura de datos (medallion)
- `data/raw/` contiene los Excel originales. **Nunca se modifican.** Hay una carpeta por materia más `Matriculados/`.
- `data/bronze/` tiene los Excel pasados a Parquet tal cual, todo como texto, con columnas `asignatura` y `archivo_origen`. Lo genera `src/ingesta.py` ✅.
  - Cada Excel se reconoce por su contenido (tipo y materia), no por el nombre ni la carpeta; la fila de encabezado se busca. Reglas en `TIPOS_ARCHIVO` de `config.py` (D31).
  - Participación y calificaciones son "fotos": si hay dos del mismo instrumento o materia, vale la exportación más reciente (D32). Trazabilidad y matriculados se acumulan (D33).
- Archivos nuevos: `src/pipeline.py` tiene `procesar()` y `agregar_archivo(bytes, nombre)` (valida con `src/validacion.py`, copia a raw, reprocesa y, si falla, vuelve atrás) ✅ Etapa 1. Por terminal: `python -m src.pipeline agregar <archivo.xlsx>`.
- `data/silver/` tiene los datos limpios y tipados. Lo genera `src/limpieza.py` ✅, que también escribe `reports/calidad_datos.md`.
  - Las columnas mantienen el nombre del Excel. Si un valor necesita otra forma, se agrega una columna nueva al lado (por ej. `Nota obtenida`, `Nota máxima`, `Nota (%)` y `Tiempo estimado de uso (min)`).
  - Silver no aplica reglas de negocio: el 0 por no rendido, el recuperatorio y el filtro por perfil van en el modelo.
- `data/gold/` tiene el modelo estrella. Lo genera `src/modelo.py` ✅ (Etapa 2), enganchado en `procesar()`, que también escribe `reports/modelo.md`.
  - Dimensiones: `dim_alumno`, `dim_asignatura`, `dim_instrumento` (con `fecha_instrumento` = mediana de "Realizar evaluación", `recupera_a`, `cuenta_en_final`), `dim_accion` (categorías en `data/referencia/categorias_acciones.csv`), `dim_fecha`.
  - Hechos: `fact_interaccion` (con `id_sesion`), `fact_sesion`, `fact_calificacion` (base × instrumento, 0 si no rindió; `puntos` con recuperatorio y `puntos_sin_recuperatorio`), `fact_participacion`, `fact_matricula` (último estado, `inscripto`, `en_base`). No alumnos: `otros_perfiles_interaccion` y `otros_perfiles_participacion`.
  - Gold no depende de la fecha de corte: lo que depende de ella va en `src/metricas.py` (D29). Columnas en minúsculas y sin tildes.
- `src/metricas.py` ✅ (Etapa 3): gold -> KPIs. `d = cargar()` una vez y después funciones `f(d, fecha_corte, asignatura, umbral)`; `asignatura=None` = todas. Tests en `tests/test_metricas.py` (el pipeline de los tests corre una vez, en `tests/conftest.py`).
  - Centrales: `nota_final` (nota y condición a la fecha, D34), `actividad_alumnos` (Activo / Inactivo / Sin actividad, D35) y `tabla_alumnos` (una fila por alumno de la base con todo: la usan Notas vs. Participación, Ficha, Alertas y el ML).
  - Por dashboard: `kpis_generales`, `evolucion_actividad` (D/W/M), `resumen_participacion`, `reporte_participacion` (foto al 24/10, D36), `interacciones_por_categoria`, `mapa_calor`, `fechas_evaluaciones`, `promedio_por_instrumento`, `distribucion_condicion`, `correlaciones` (Spearman, D38; `solo_rindieron`, D55), `cuadrante_riesgo` (D37), `nota_por_nivel_actividad` (quintiles, D55), `resumen_matricula`, `alertas`, `situacion_academica`, `buscar_alumnos`, `ficha_alumno`.
  - Defaults en `config.py`: `FECHA_CORTE_DEFECTO` (24/10/2025) y `UMBRAL_INACTIVIDAD_DIAS` (7).
- `app/` ✅ (Etapa 4) tiene la app de Streamlit: `streamlit run app/Inicio.py` (también es el archivo principal en Streamlit Cloud). Tests de humo en `tests/test_app.py` (AppTest).
  - `app/Inicio.py` arma el menú con `st.navigation`, dibuja la barra lateral global (fecha de corte, materia, umbral; D46) y corre la página. Las páginas están en `app/paginas/` (no `pages/`): para sumar una, crear el archivo y agregarlo a `PAGINAS`.
  - `app/componentes.py`: `metrica("nombre", ...)` llama a `src.metricas` con caché y completa fecha/materia/umbral desde la barra (D47); `filtros()`, `encabezado()`, `tarjetas()`, `semaforo()`, `boton_csv()`, `num()`/`pct()`/`fmt_fecha()` y la paleta (`COLORES_MATERIA`, `COLORES_CONDICION`, `COLORES_ACTIVIDAD`, `SECUENCIAL`; D48). Plotly usa la plantilla `plotly_white+tfi`. Las páginas no leen parquet ni llaman a `src.metricas` directo.
  - Si gold no existe, la app corre el pipeline sola (D49). `LMS_GOLD` cambia la carpeta de gold (solo para tests).
  - `paginas/cargar_archivo.py`: valida y muestra qué reconoció, y al confirmar llama a `agregar_archivo()` y limpia el caché (D50). Tema en `.streamlit/config.toml`.
- bronze, silver y gold están en `.gitignore`: cada persona los regenera corriendo el pipeline.

## Estado actual de los datos (bronze)
- `trazabilidad`: 159.804 eventos. Columnas: Fecha (`YYYY-MM-DD HH:MM:SS`), IP, Usuario, Perfil, Sección, Acción y Descripción.
  - Perfiles: Alumnos (`ALU_####`), Tutores (`DOC_##`) y Coordinadores (`STAFF_##`).
  - Hay 686 filas duplicadas exactas y 19 sin `Acción`.
- `participacion`: 986 filas, con el encabezado de 2 niveles ya aplanado (por ej. `Foros - Cantidad de intervenciones del usuario`).
  - `Tiempo estimado de uso` viene como texto `"hh:mm"`.
  - Hay alumnos con 0 interacciones.
  - También aparecen Invitados, Tutores y Coordinadores.
- `calificaciones`: 1.793 filas, una por alumno y por instrumento.
  - `Nota` viene como `"24.00/25.00"`: el denominador es el puntaje máximo del instrumento.
  - Columnas: `instrumento` (con los emojis HTML ya decodificados) y `desactivado`, que sale del color de la celda. Hoy ninguna celda está coloreada.
  - `Observaciones` vale "aprobada" o "no aprobada".
- `matriculados`: 516 filas.
  - Columnas: `Identificación` (ALU_####, que corresponde a `Usuario` del LMS), `Estado Insc.` (Aceptada o Baja), `Fecha inscripción`, `codigo_asignatura` (2319, 2320 o 2321).
  - Hay alumnos con varias filas (Baja y Aceptada): hay que quedarse con el último estado según la fecha.

## Reglas académicas (ver ESQUEMA en config.py)
- **Álgebra** es acumulativa (máximo 120). Libre < 60, Regular de 60 a < 85, Promociona ≥ 85.
  - Por ahora solo hay Autoevaluación 1, Autoevaluación 2 y 1° Parcial. Más adelante llegan archivos nuevos.
  - DECISIÓN: nota proyectada = puntos / suma de los máximos de los instrumentos disponibles × 120. Cuando estén todos, la suma da 120 sola. No hay que tocar código.
- **PyE**: promedio de instrumentos (cada uno sobre 100). Mismos cortes que Álgebra (60 y 85).
  - Hay un "Recuperatorio: Evaluación Semanal Nº1".
- **AED**: promedio de las autoevaluaciones (sobre 100). Regular desde 60, Promociona ≥ 90.

## Decisiones TOMADAS
El registro completo, con justificación y estado, está en `docs/decisiones.md` (es la base del informe). Si se toma una decisión nueva, se agrega ahí con el número siguiente (hoy, D56); los números no se reutilizan porque el código los cita.
Ojo: la lista de abajo está numerada 1-7 y NO son los números D del registro; en el código se citan siempre los D (por ej., nota final = D16-D17, promedio por instrumento = D22).

1. Instrumento no rendido = 0 para la nota final y la condición. En los Excel no rendir no aparece como nota vacía: directamente no hay fila, así que hay que completar alumno × instrumento con 0.
   Más adelante llegan archivos con las notas que faltan: se copian a `data/raw/` y se vuelve a correr el pipeline, que recalcula todo.
   El KPI "promedio por instrumento" usa solo a quienes rindieron.
2. Base de alumnos por materia = inscriptos (último estado Aceptada) ∪ alumnos con al menos una nota. Sobre esa base se completan los 0.
   - Inscriptos sin ninguna nota (AED 58, PyE 22, Álg 21): todo en 0 → Libre. Alimentan la alerta "inscriptos sin actividad".
   - Con nota pero sin estar en Matriculados (AED 39, PyE 52, Álg 52): se incluyen, con una columna `inscripto = False`. Alimentan el KPI "activos no inscriptos".
3. Recuperatorio (hoy solo PyE, "Recuperatorio: Evaluación Semanal Nº1"): si el alumno lo rindió, su nota REEMPLAZA a la original aunque sea más baja. Si no lo rindió, queda la original.
   No cuenta como un instrumento extra en el promedio. Hoy afecta a 21 alumnos; 3 tienen 0 en el recuperatorio (ALU_1020, ALU_1035, ALU_1105, este último con 93,75 en la original).
   Confirmado también para los recuperatorios con 0: vale el 0.
4. Docentes, staff e invitados: los KPIs de alumnos usan solo `Perfil == "Alumnos"` (en trazabilidad y participación). El resto (Tutores, Coordinadores, Invitados) va a una tabla aparte.
   Ojo: participación lista 319 alumnos por materia (parece toda la cohorte), pero hay ~163 inscriptos por materia. La base sigue siendo la de la decisión 2.
5. Recuperatorio de Álgebra (20 puntos): SUMA al total de 120, no reemplaza a ningún parcial (la regla de reemplazo de la decisión 3 es solo para PyE). Hoy no hay datos de ese instrumento.
6. Normalización (indicación del profesor): nota final = Σ puntos obtenidos / Σ puntaje máximo de los instrumentos disponibles a la fecha de corte × 100. Álgebra se expresa sobre 120. Los instrumentos con pocas entregas (AED Unidad 5, PyE Semanal Nº2) se incluyen.
7. Se usan todos los Excel. La ficha individual tiene buscador por nombre o ID y muestra al primero por defecto. Se tiene que poder agregar un archivo nuevo (por ej., notas de un parcial) y recalcular.

## Próximos pasos (plan por etapas)
- Etapa 1: ingesta preparada para archivos nuevos (`pipeline.py`, `validacion.py`, tests en `tests/`).
- Etapa 2 ✅: `src/modelo.py` (silver -> gold) con tests en `tests/test_modelo.py`.
- Etapa 3 ✅: `src/metricas.py`: funciones que reciben fecha de corte, materia y umbral de inactividad (D29, D34-D38).
- Etapa 4 ✅: base de la app (barra lateral global, componentes, página "Cargar archivo"). Falta el deploy de prueba en Streamlit Cloud (recomendado).
- Etapas 5 y 6: los 7 dashboards. Se trabaja una rama por dashboard (`dashboard/<nombre>`).
  - Dashboard Notas vs. participación ✅ (rama `dashboard/notas-participacion`, `app/paginas/5_notas_vs_participacion.py`, D55): selector de variable de actividad e interruptor "solo quienes rindieron algo", tarjetas (ρ por materia y alumnos en riesgo), pestañas Dispersión (por condición, con tendencia por quintiles y cortes) / Correlaciones (mapa de calor y tabla con CSV) / Por nivel de actividad (% por condición en 5 grupos iguales) / Cuadrante de riesgo (D37, lista con CSV). Métrica nueva: `nota_por_nivel_actividad`; `correlaciones` suma `solo_rindieron`.
- Etapa 7: ML (K-Means y predictor de abandono). Etapa 8: hosting. Etapa 9: informe y defensa.
