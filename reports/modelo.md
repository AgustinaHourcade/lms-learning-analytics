# Modelo (silver -> gold)

Generado por el pipeline (`python -m src.pipeline`). No editar a mano.

| Tabla | Filas |
|---|---|
| dim_alumno | 319 |
| dim_asignatura | 3 |
| dim_instrumento | 17 |
| dim_accion | 95 |
| dim_fecha | 143 |
| fact_interaccion | 149,458 |
| fact_sesion | 20,657 |
| fact_calificacion | 3,615 |
| fact_participacion | 957 |
| fact_matricula | 642 |
| otros_perfiles_interaccion | 9,660 |
| otros_perfiles_participacion | 29 |

## Base de alumnos por materia (D11)

| Materia | Base | Inscriptos | Inscriptos sin nota | Con nota sin estar inscriptos |
|---|---|---|---|---|
| Algoritmos y Estructuras de Datos | 204 | 165 | 58 | 39 |
| Probabilidad y Estadística | 216 | 164 | 22 | 52 |
| Álgebra | 217 | 163 | 21 | 54 |

## Instrumentos (fecha = mediana de los eventos 'Realizar evaluación', D18)

| ID | Materia | Instrumento | Máx. | Notas | Fecha | Recupera a |
|---|---|---|---|---|---|---|
| AED-01 | Algoritmos y Estructuras de Datos | Autoevaluación - Módulo 1 | 100 | 145 | 2025-08-14 |  |
| AED-02 | Algoritmos y Estructuras de Datos | Autoevaluación - Unidad 2 | 100 | 106 | 2025-09-02 |  |
| AED-03 | Algoritmos y Estructuras de Datos | Autoevaluación - Unidad 3 | 100 | 80 | 2025-09-17 |  |
| AED-04 | Algoritmos y Estructuras de Datos | Autoevaluación - Unidad 4 | 100 | 64 | 2025-10-02 |  |
| AED-05 | Algoritmos y Estructuras de Datos | Autoevaluación - Unidad 5 | 100 | 24 | 2025-10-21 |  |
| PYE-01 | Probabilidad y Estadística | 👉  Actividad Rápida 1 | 100 | 147 | 2025-08-17 |  |
| PYE-02 | Probabilidad y Estadística | 👉  Actividad Rápida 2 | 100 | 137 | 2025-08-24 |  |
| PYE-03 | Probabilidad y Estadística | 👉  Actividad Rápida 3 | 100 | 112 | 2025-09-14 |  |
| PYE-04 | Probabilidad y Estadística | 👉  Actividad Rápida 4 | 100 | 108 | 2025-09-21 |  |
| PYE-05 | Probabilidad y Estadística | 🚀Evaluación Semanal Nº1 | 100 | 136 | 2025-09-23 |  |
| PYE-06 | Probabilidad y Estadística | 🚀Recuperatorio: Evaluación Semanal Nº1 | 100 | 21 | 2025-09-24 | 🚀Evaluación Semanal Nº1 |
| PYE-07 | Probabilidad y Estadística | 🧠 PARCIAL 1 | 100 | 167 | 2025-09-27 |  |
| PYE-08 | Probabilidad y Estadística | 👉  Actividad Rápida 5 | 100 | 54 | 2025-10-15 |  |
| PYE-09 | Probabilidad y Estadística | 🚀Evaluación Semanal Nº2 | 100 | 13 | 2025-10-23 |  |
| ALG-01 | Álgebra | AUTOEVALUACION1 | 10 | 165 | 2025-08-21 |  |
| ALG-02 | Álgebra | AUTOEVALUACION2 | 10 | 152 | 2025-09-18 |  |
| ALG-03 | Álgebra | 1° Parcial | 25 | 162 | 2025-10-11 |  |

## Sesiones (corte a 30 minutos sin eventos, D25)

- 20,657 sesiones de alumnos; duración mediana 0.9 min.
