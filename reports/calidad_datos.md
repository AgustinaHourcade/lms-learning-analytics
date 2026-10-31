# Calidad de datos (bronze -> silver)

Generado por `python -m src.limpieza`. No editar a mano.

| Tabla | Filas bronze | Filas silver | Columnas |
|---|---|---|---|
| trazabilidad | 159,804 | 159,118 | 12 |
| participacion | 986 | 986 | 33 |
| calificaciones | 1,793 | 1,793 | 17 |
| matriculados | 516 | 513 | 10 |

## trazabilidad
- 686 filas duplicadas exactas eliminadas (mismo usuario, segundo, acción).
- 19 filas sin `Acción` (descargas de adjuntos en Foros). Se conservan con `Acción` vacía.
- Rango de fechas: 2025-06-04 14:19:41 a 2025-10-24 11:53:27.
- Eventos por perfil: Alumnos 149,458, Tutores 9,277, Coordinadores 383.

## participacion
- `Avance` = 'no aplica' en 29 filas (solo perfiles no alumno: Invitados 15, Tutores 11, Coordinadores 3). Quedan vacías.
- 156 usuarios sin ninguna interacción (sin `Primera/Última interacción`).
- `Email` viene vacío en todas las filas (anonimizado). Se conserva la columna.
- Usuarios por perfil: Alumnos 957, Invitados 15, Tutores 11, Coordinadores 3.

## calificaciones
- `Nota` separada en `Nota obtenida`, `Nota máxima` y `Nota (%)`. Ninguna fuera de rango.
- Usuarios desactivados (celda coloreada): 0.
- `Detalle` viene vacío en todas las filas. Se conserva la columna.
- Instrumentos por asignatura: Algoritmos y Estructuras de Datos 5; Probabilidad y Estadística 9; Álgebra 3.

## matriculados
- 3 filas de pie de tabla ('Cantidad de filas:') eliminadas.
- 11 alumnos con más de una fila (altas y bajas). Se conservan todas; el último estado se toma en el modelo.
- Estados: Aceptada 492, Baja 21.
