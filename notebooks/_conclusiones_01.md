## Conclusiones

**Los datos son utilizables y consistentes en lo esencial**, pero hay cosas que hay que tener en cuenta al leer
los indicadores. Cada hallazgo tiene su decisión:

| Hallazgo | Qué decide el proyecto |
|---|---|
| 26 archivos, todos reconocidos por su contenido; ninguno reemplazado. | La ingesta no depende del nombre del archivo (D31-D33). |
| 686 duplicados exactos en la trazabilidad (0,43 %) y 19 filas sin acción. | Los duplicados se borran; las 19 filas se conservan (son descargas en foros). |
| `Email` y `Detalle` vienen vacíos en todas las filas (anonimización). | Se conservan las columnas, no se usan. |
| Los docentes arman el aula desde junio; los alumnos entran desde el 05/08. | Los perfiles no alumno van a tablas aparte (D4); la cursada empieza con el primer evento de un alumno. |
| No hay días sin datos en la cursada; el 24/10 está incompleto (la exportación es de esa mañana). | La fecha de corte por defecto es el 24/10 (D29); las métricas "de la última semana" de ese día subestiman. |
| La mitad de las sesiones dura menos de 1 minuto y unos pocos alumnos tienen 3 a 5 veces la actividad de la mediana. | Se usan medianas y Spearman (D38) y log en los modelos; los atípicos no se borran: no son errores. |
| Las notas están en rango, sin duplicados y con un solo puntaje máximo por instrumento. | La nota se normaliza con ese máximo (D16-D17). |
| `Observaciones` usa un criterio propio de cada instrumento: hay "aprobada" con 12 % y "no aprobada" con 75 %. | **No se usa**: la condición sale de la nota y de los cortes de cada materia. |
| 8 notas no tienen su evento "Realizar evaluación". | Para fecharlas se usa la última realización del instrumento (D64). |
| El reporte de participación lista a los 319 alumnos de la cohorte en las tres materias (34 nunca entraron). | La base de cada materia es inscriptos ∪ con nota (D2), no el reporte. |
| Participación cuenta un 26 % más de interacciones que la trazabilidad, pero ordena igual (ρ = 0,99); el tiempo estimado también concuerda con los minutos de las sesiones (ρ 0,95-1,00). | La actividad se calcula siempre con la trazabilidad (es la que tiene fecha); el reporte sirve de control. |
| 290 de 492 inscriptos entraron al aula antes de su fecha de inscripción. | La fecha de inscripción no marca el inicio de nadie: se usa el primer evento. |
| Hay bajas con actividad posterior y alumnos con nota que no figuran en Matriculados. | La baja formal no se usa como abandono (D67); los no inscriptos con actividad son un KPI aparte (D2). |
| Hay IPs compartidas por hasta 17 alumnos. | La IP no identifica a nadie (redes compartidas): no se usa. |

**Qué quedó en código:** los controles entre fuentes de la sección 4 están en `src/calidad.py`
(`python -m src.calidad`), con sus tests en `tests/test_calidad.py`, para volver a correrlos cuando llegue un
archivo nuevo.
