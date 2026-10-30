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
- Se ejecuta siempre desde la raíz con `python -m src.<modulo>`.
- Las rutas y las reglas de negocio están en `src/config.py`: no se escriben a mano en otros archivos.

## Arquitectura de datos (medallion)
- `data/raw/` contiene los Excel originales. **Nunca se modifican.** Hay una carpeta por materia más `Matriculados/`.
- `data/bronze/` tiene los Excel pasados a Parquet tal cual, todo como texto, con columnas `asignatura` y `archivo_origen`. Lo genera `src/ingesta.py` ✅.
- `data/silver/` va a tener los datos limpios y tipados. Lo genera `src/limpieza.py` (PASO 3, pendiente).
- `data/gold/` va a tener el modelo estrella y las tablas de KPIs. Lo generan `src/modelo.py` y `src/kpis.py` (pendiente).
- `app/` va a tener la app de Streamlit, con una página por dashboard en `app/pages/` (pendiente).
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
1. Instrumento no rendido = 0 para la nota final y la condición. En los Excel no rendir no aparece como nota vacía: directamente no hay fila, así que hay que completar alumno × instrumento con 0.
   Más adelante llegan archivos con las notas que faltan: se copian a `data/raw/` y se vuelve a correr el pipeline, que recalcula todo.
   El KPI "promedio por instrumento" usa solo a quienes rindieron.

## Decisiones PENDIENTES (preguntar al usuario antes del paso 3)
1. ¿A quién se le completan los 0? Hay alumnos inscriptos (Aceptada) sin ninguna nota (AED 58, PyE 22, Álg 21) y alumnos con notas que no figuran en Matriculados (AED 39, PyE 52, Álg 52).
2. Recuperatorio de PyE: ¿reemplaza la nota o se toma la mejor? Propuesta: la mejor nota, sin contarlo como un instrumento extra.
3. Docentes, staff e invitados: propuesta excluirlos de los KPIs de alumnos y guardarlos en una tabla aparte.

## Próximos pasos
3. `src/limpieza.py`: parsear tipos, normalizar IDs y textos, deduplicar, tratar nulos y generar `reports/calidad_datos.md`.
4. `src/modelo.py`: dimensiones `dim_alumno`, `dim_asignatura`, `dim_instrumento`, `dim_fecha`; hechos `fact_interaccion`, `fact_calificacion`, `fact_participacion`, `fact_matricula`.
5. Nota final y condición según el ESQUEMA.
6. `src/kpis.py`: KPIs de participación, trazabilidad, calificaciones, cruces (correlaciones) y matrícula (activos no inscriptos, inscriptos sin actividad).
7. Streamlit, 7 páginas: General, Participación, Trazabilidad, Rendimiento, Notas vs. Participación, Individual (semáforo) y Matrícula/Alertas.
8. Informe técnico.
