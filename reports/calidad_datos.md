# Calidad de datos (bronze -> silver)

Generado por el pipeline (`python -m src.pipeline`). No editar a mano.

| Tabla | Filas bronze | Filas silver | Columnas |
|---|---|---|---|
| trazabilidad | 159,804 | 159,118 | 12 |
| participacion | 986 | 986 | 33 |
| calificaciones | 1,887 | 1,887 | 17 |
| matriculados | 516 | 513 | 10 |

## Archivos usados (27)

Cada Excel se reconoce por su contenido (tipo y materia), no por el nombre.

- calificaciones_alumnos_20251024_115518.xlsx
- calificaciones_alumnos_20251024_115523.xlsx
- calificaciones_alumnos_20251024_115528.xlsx
- calificaciones_alumnos_20251024_115533.xlsx
- calificaciones_alumnos_20251024_115538.xlsx
- calificaciones_alumnos_20251024_115041.xlsx
- calificaciones_alumnos_20251024_115045.xlsx
- calificaciones_alumnos_20251024_115049.xlsx
- calificaciones_alumnos_20251024_115055.xlsx
- calificaciones_alumnos_20251024_115059.xlsx
- calificaciones_alumnos_20251024_115102.xlsx
- calificaciones_alumnos_20251024_115105.xlsx
- calificaciones_alumnos_20251024_115127.xlsx
- calificaciones_alumnos_20251024_115130.xlsx
- calificaciones_alumnos_20251107_102000.xlsx
- calificaciones_alumnos_20251024_114929.xlsx
- calificaciones_alumnos_20251024_114941.xlsx
- calificaciones_alumnos_20251024_114944.xlsx
- Algoritmos y Estructuras de Datos.xlsx
- Probabilidad y Estadística.xlsx
- Álgebra.xlsx
- reporte_participacion_20251024_115446.xlsx
- reporte_participacion_20251024_115203.xlsx
- reporte_participacion_20251024_115228.xlsx
- reporte_trazabilidad_20251024_115443.xlsx
- reporte_trazabilidad_20251024_115157.xlsx
- reporte_trazabilidad_20251024_115226.xlsx

## trazabilidad
- `Usuario` normalizado (sin espacios, en mayúsculas): 0 valores corregidos. Todos respetan el formato ALU_####, DOC_## o STAFF_##.
- 686 filas duplicadas exactas eliminadas (mismo usuario, segundo, acción).
- 19 filas sin `Acción` (descargas de adjuntos en Foros). Se conservan con `Acción` vacía.
- Rango de fechas: 2025-06-04 14:19:41 a 2025-10-24 11:53:27.
- Eventos por perfil: Alumnos 149,458, Tutores 9,277, Coordinadores 383.

## participacion
- `Usuario` normalizado (sin espacios, en mayúsculas): 0 valores corregidos. Todos respetan el formato ALU_####, DOC_## o STAFF_##.
- `Avance` = 'no aplica' en 29 filas (solo perfiles no alumno: Invitados 15, Tutores 11, Coordinadores 3). Quedan vacías.
- 156 usuarios sin ninguna interacción (sin `Primera/Última interacción`).
- `Email` viene vacío en todas las filas (anonimizado). Se conserva la columna.
- Usuarios por perfil: Alumnos 957, Invitados 15, Tutores 11, Coordinadores 3.

## calificaciones
- `Usuario` normalizado (sin espacios, en mayúsculas): 0 valores corregidos. Todos respetan el formato ALU_####, DOC_## o STAFF_##.
- `Nota` separada en `Nota obtenida`, `Nota máxima` y `Nota (%)`. Ninguna fuera de rango.
- Usuarios desactivados (celda coloreada): 0.
- `Detalle` viene vacío en todas las filas. Se conserva la columna.
- Instrumentos por asignatura: Algoritmos y Estructuras de Datos 5; Probabilidad y Estadística 10; Álgebra 3.

## matriculados
- 3 filas de pie de tabla ('Cantidad de filas:') eliminadas.
- `Identificación` normalizado (sin espacios, en mayúsculas): 0 valores corregidos. Todos respetan el formato ALU_####, DOC_## o STAFF_##.
- 11 alumnos con más de una fila (altas y bajas). Se conservan todas; el último estado se toma en el modelo.
- Estados: Aceptada 492, Baja 21.
