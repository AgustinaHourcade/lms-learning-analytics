# Conclusiones del dashboard de Trazabilidad (material para el informe)

Estas interpretaciones estaban escritas en la pantalla del dashboard de Trazabilidad y se sacaron con el rediseño
(D80): el dashboard muestra datos y las lecturas van al informe. Valores con corte al **24/10/2025**, las tres
materias, toda la cursada (05/08 al 24/10/2025, 81 días), salvo que se indique otra cosa. Las horas son las del
servidor del LMS (ver "Zona horaria" al final).

## Cuándo entran
- **El aula se usa de noche.** El 47 % de las interacciones cae entre las 18 y las 24 h; el 17 %, entre las 6 y las
  12 h, y el 19 %, en sábado o domingo. El pico es el **miércoles de 20 a 21 h** (5.715 interacciones), y la hora
  más fuerte de las tres materias son las 20 h.
  - Lectura que estaba en pantalla: es el horario en el que conviene publicar material o avisos, y el que más
    aprovecharía una consulta en línea.
- **Cada materia tiene su día fuerte:** Álgebra el lunes (29,5 % de sus clics), Probabilidad el miércoles (29,7 %)
  y Algoritmos el martes (36,3 %). Entre el 30 % y el 36 % en un solo día es mucho para un reparto parejo (14,3 %).
  - Lectura que estaba en pantalla: probablemente sea el día de la clase o el de la publicación del material; el aula
    se usa como complemento de la cursada y no de forma pareja durante la semana. Los días no aparecen la misma
    cantidad de veces en el período, así que diferencias chicas entre días no son significativas.
- **Frecuencia de ingreso (KPI nuevo):** la mediana es de 1,6 días con ingreso por semana entre los 630
  alumno-materia que entraron, con 10,7 interacciones por día de ingreso. En las últimas 2 semanas (11/10 al 24/10)
  bajó a 1,5 días por semana (2,0 en las dos semanas anteriores) y a 6,7 interacciones por día de ingreso (7,2).

## Qué hacen
- **Probabilidad es la que más peso le da a Evaluación** (10,6 % de sus clics), seguida de Álgebra (9,6 %);
  **Algoritmos, la que menos** (5,7 %). En las tres, Contenido (37-46 %) y Navegación (39-47 %) juntan más del 80 %.
  - Lectura que estaba en pantalla: en Algoritmos se entra, se navega y se lee mucho más de lo que se rinde.
- La acción que más alumnos hicieron es **Acceder a Inicio**: el 98,6 % de la base. Hay 66 acciones distintas.
  "Acceder" a Inicio y a Programa son filas distintas: la acción sola no dice dónde pasó.
- Una acción con muchas interacciones y pocos alumnos la usa un grupo chico muy intensamente.

## Evolución
- El pico semanal es de **Probabilidad, la semana del 22/09** (13.748 interacciones), y coincide con la Evaluación
  Semanal Nº1, su recuperatorio y el Parcial 1. El pico diario es de Algoritmos el 05/08 (primer día de datos,
  5.012 interacciones) y el mensual, Probabilidad en septiembre (27.471).
- En los períodos de evaluación crece la parte de Evaluación; el resto del tiempo domina leer contenido y navegar.
  Evaluación nunca pasa del 16 % de los clics de una semana (máximo: semana del 15/09) ni del 21 % de un día (11/10).

## Alrededor de las evaluaciones
Actividad de la materia en los días cercanos a cada evaluación, relativa a un día típico (promedio diario de la
cursada); promedio de las evaluaciones de cada materia, ventana de −7 a +3 días.
- **Álgebra:** el pico es el mismo día de la evaluación, 2,4 veces un día típico.
  Lectura que estaba en pantalla: se entra a rendir más que a prepararse.
- **Algoritmos:** el pico llega 2 días antes, 1,6 veces un día típico.
  Lectura que estaba en pantalla: suben desde antes, estudian para la evaluación.
- **Probabilidad:** el pico llega 3 días después, 1,9 veces un día típico.
  Lectura que estaba en pantalla: la evaluación queda abierta varios días o las ventanas se superponen con la
  siguiente (las evaluaciones semanales de PyE están a pocos días entre sí).
- Criterio que usaba la pantalla: menos de 1,2 veces un día típico = actividad casi plana (las evaluaciones no
  mueven el uso del aula).

## Zona horaria
Las fechas de la trazabilidad vienen como texto (`YYYY-MM-DD HH:MM:SS`) sin zona horaria, tanto en los Excel como en
silver. Evidencia de que es la hora local (Argentina, UTC−3) y no UTC:
- El último evento de cada archivo cae entre 30 segundos y 3 minutos antes de la hora de exportación del nombre del
  archivo (por ejemplo, 11:53:27 en `reporte_trazabilidad_20251024_115443.xlsx`): eventos y exportación usan el
  mismo reloj.
- Los coordinadores no registran actividad entre las 22 y las 6 h y su pico es a las 11 h (horario de oficina); los
  alumnos tienen el mínimo a las 5 h (0,2 %) y el pico a las 20 h. Si fuera UTC, en hora argentina los coordinadores
  trabajarían de 4 a 18 h y el mínimo de los alumnos sería a las 2 h.
Queda como supuesto (no confirmado por la cátedra) y por eso la pantalla dice "hora del servidor del LMS".
