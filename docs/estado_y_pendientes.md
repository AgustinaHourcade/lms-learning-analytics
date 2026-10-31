# Estado del proyecto y pendientes

Última actualización: 30/10/2026. Este documento resume cómo correr el proyecto, qué está hecho, qué falta y qué preguntas hay que responder para seguir avanzando.
Las reglas y decisiones detalladas están en [`CLAUDE.md`](../CLAUDE.md).

---

## 0. Cómo están organizados los datos: raw, bronze, silver y gold

Los datos pasan por 4 capas. Cada capa es una carpeta dentro de `data/` y la genera un script. Cada script lee **solo** la capa anterior.

| Capa | Qué tiene | Ejemplo con una nota | La genera | ¿Va a git? |
|---|---|---|---|---|
| **raw** | Los Excel originales, **sin tocar nunca**. | Celda `"24.00/25.00"` en el Excel, con filas de título arriba. | Nadie: los entrega la cátedra. | Sí |
| **bronze** | Lo mismo que los Excel pero en Parquet: sin filas de título, con encabezados planos, **todo como texto** y con la materia y el archivo de origen de cada fila. | `Nota = "24.00/25.00"` (texto). | `src/ingesta.py` | No |
| **silver** | Datos **limpios y tipados**: fechas como fechas, números como números, sin duplicados ni filas basura. Mismas columnas que el Excel. | `Nota = "24.00/25.00"`, `Nota obtenida = 24`, `Nota máxima = 25`, `Nota (%) = 96`. | `src/limpieza.py` | No |
| **gold** | Datos **listos para el dashboard**: modelo estrella, reglas académicas aplicadas (0 por no rendido, recuperatorio, solo alumnos), nota final, condición y KPIs. | Alumno ALU_1004 en Álgebra: nota final 78, condición **Regular**. | `src/modelo.py`, `src/kpis.py` | No |

**Por qué separar en capas y no hacer todo en un solo script:**
- **Si algo sale mal, se rehace solo esa parte.** Leer los Excel es lo lento (unos 25 s). Si cambiamos una regla de negocio, por ejemplo la del recuperatorio, se vuelve a correr gold y tarda un segundo.
- **Cada capa responde una sola pregunta.** Bronze: "¿leímos bien el Excel?". Silver: "¿los datos están limpios?". Gold: "¿aplicamos bien las reglas de la materia?". Si un número del dashboard da raro, se revisa capa por capa hasta encontrar dónde cambió.
- **Los Excel nunca se modifican.** Siempre se puede volver al original y comparar.
- **El dashboard solo lee gold.** Las páginas de Streamlit no limpian ni calculan nada: muestran. Así dos personas que hacen dashboards distintos ven exactamente los mismos números.

**Por qué bronze, silver y gold no se suben a git:** se generan a partir de raw con dos comandos. Subirlos duplicaría los datos y daría conflictos cada vez que alguien corre el pipeline. Cada uno los genera en su compu (ver sección 1).

Los nombres bronze, silver y gold vienen de la **arquitectura medallion**, un estándar en ingeniería de datos (Databricks). Sirve citarlo así en el informe técnico.

---

## 1. Cómo levantar el proyecto y ver los datos

### Primera vez (una sola vez por compu)
```bash
git clone https://github.com/AgustinaHourcade/lms-learning-analytics.git
cd lms-learning-analytics
python -m venv .venv
.venv\Scripts\activate            # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

### Generar los datos
Los Excel originales ya vienen en el repo (`data/raw/`). Las capas bronze y silver **no** se suben a git: cada uno las genera en su compu con estos comandos, siempre desde la raíz del repo:

```bash
python -m src.ingesta     # Excel -> data/bronze/  (~25 s)
python -m src.limpieza    # bronze -> data/silver/ + reports/calidad_datos.md  (~1 s)
```

Si sale un error, leé el mensaje: el pipeline está hecho para **frenar** cuando encuentra un formato inesperado (una fecha rara, un texto donde va un número), en vez de seguir con datos mal leídos.

### Ver los datos en el navegador (lo recomendado)
```bash
streamlit run app/Inicio.py
```
Se abre en http://localhost:8501. En el menú de la izquierda:
- **Explorar datos**: elegís una tabla (`silver / trazabilidad`, `silver / calificaciones`, etc.), filtrás por asignatura y perfil, y ves la cantidad de filas, los usuarios distintos, un gráfico por materia y perfil, la tabla y los valores vacíos por columna.
- **Los 7 dashboards** de la consigna: por ahora cada uno muestra los requisitos de la consigna y en qué paso se completa.

Para cortar la app: `Ctrl + C` en la terminal. Si volvés a correr el pipeline con la app abierta, alcanza con refrescar la página.

### Ver el reporte de calidad
[`reports/calidad_datos.md`](../reports/calidad_datos.md) lista qué se encontró y qué se corrigió en cada tabla: duplicados, nulos, filas basura. Se regenera solo cada vez que corrés `src.limpieza`.

### Mirar los datos desde Python (opcional)
```python
import pandas as pd
df = pd.read_parquet("data/silver/calificaciones.parquet")
df.head()
```

### Cuando lleguen Excel nuevos
1. Copiarlos en `data/raw/<Asignatura>/` sin cambiarles el nombre ni el formato.
2. Volver a correr `python -m src.ingesta` y `python -m src.limpieza`.

No hay que tocar código: las notas y las condiciones se recalculan solas.

---

## 1.b Cómo trabajamos entre todos

**Idea general:** el dashboard es código que vive en el repo. Cada uno lo modifica **en su compu**, lo prueba con `streamlit run app/Inicio.py` y después lo sube a GitHub. La versión publicada (Streamlit Cloud) muestra siempre lo que está en `main` y se actualiza sola cuando entra un cambio.

```
tu compu (rama propia) ──push──> GitHub (Pull Request) ──merge──> main ──> se actualiza el link público
```

**Antes de empezar (una vez):** la dueña del repo (AgustinaHourcade) agrega a cada integrante como *collaborator* en GitHub: Settings → Collaborators.

**Cada vez que vas a trabajar:**
```bash
git switch main
git pull                          # traer lo último de los demás
git switch -c dashboard-trazabilidad   # una rama por tarea
# ... cambios, probar con streamlit run app/Inicio.py ...
git add app/pages/3_Trazabilidad.py
git commit -m "Trazabilidad: mapa de calor por día y hora"
git push -u origin dashboard-trazabilidad
```
Después se abre un **Pull Request** en GitHub, alguien del equipo lo mira y se hace merge a `main`.

**Reglas para no pisarnos:**
- **Cada integrante toma sus propias páginas** (`app/pages/N_*.py`). Si dos personas tocan el mismo archivo a la vez, hay conflictos.
- **Lo compartido se avisa antes de tocarlo:** `src/config.py`, `src/modelo.py`, `src/kpis.py`. Si cambiás una regla o una tabla de gold, las páginas de los demás pueden romperse.
- **Las páginas leen de gold, no calculan.** Si te falta un KPI, se agrega en `src/kpis.py` para que todos usen el mismo número.
- **No subir datos generados** (bronze, silver y gold ya están en `.gitignore`).
- **Antes del merge, correr el pipeline completo y abrir la app** para comprobar que nada se rompió.

**Para publicar (una vez, cuando haya dashboards con datos):** quien sea dueña del repo entra a share.streamlit.io con GitHub, elige el repo, la rama `main` y el archivo `app/Inicio.py`. Queda un link fijo que todo el equipo y el docente pueden abrir.

---

## 2. Qué está hecho

| Paso | Qué | Estado |
|---|---|---|
| 1 | Estructura del repo, datos en `data/raw/` | ✅ |
| 2 | `src/ingesta.py`: Excel → bronze | ✅ |
| 3 | `src/limpieza.py`: bronze → silver + reporte de calidad | ✅ |
| 7 (base) | App de Streamlit: menú, 7 páginas vacías y *Explorar datos* | ✅ |

**Regla de formato:** en silver las columnas conservan el nombre del Excel. Solo se agregan columnas nuevas cuando hace falta (`Nota obtenida`, `Nota máxima`, `Nota (%)`, `Tiempo estimado de uso (min)`).

**Números después de la limpieza:**

| Tabla | Filas | Qué se limpió |
|---|---|---|
| trazabilidad | 159.118 | Se sacaron 686 duplicados exactos. |
| participacion | 986 | Fechas y números tipados. El texto "no aplica" en `Avance` (solo no alumnos) quedó vacío. |
| calificaciones | 1.793 | `Nota` separada en obtenida y máxima. Sin notas fuera de rango ni repetidas. |
| matriculados | 513 | Se sacaron 3 filas de pie de tabla ("Cantidad de filas:"). |

---

## 3. Decisiones ya tomadas

1. **Instrumento no rendido = 0** para la nota final y la condición. El KPI "promedio por instrumento" usa solo a quienes rindieron.
2. **Base de alumnos = inscriptos (Aceptada) + alumnos con al menos una nota.** Los que tienen nota y no están inscriptos quedan marcados con `inscripto = False`.
3. **Recuperatorio: si se rindió, su nota reemplaza a la original** aunque sea más baja, incluso si es 0. No cuenta como un instrumento extra.
4. **Los KPIs de alumnos usan solo `Perfil = Alumnos`.** Tutores, coordinadores e invitados van a una tabla aparte.

---

## 4. Preguntas a responder (antes del paso 5)

| # | Pregunta | Por qué importa | Propuesta |
|---|---|---|---|
| P1 | **Recuperatorio de Álgebra:** la consigna dice "Recuperatorio: 20 puntos" dentro del total de 120. ¿Suma 20 puntos o reemplaza a un parcial? | Choca con la decisión 3, que pensamos para PyE. Si suma, quien no lo rinde nunca llega a 120. Hoy no hay recuperatorio de Álgebra en los datos. | Consultar al docente. |
| P2 | **Nota proyectada en Álgebra:** hoy solo hay 45 puntos posibles (1° Parcial 25, Autoevaluaciones 1 y 2 de 10 cada una). ¿Proyectamos a 120 o mostramos los puntos reales? | Con los puntos reales, hoy **todos** quedan Libres (máximo 45 < 60). Con la proyección, 45/45 → 120 → Promociona. | Mostrar las dos: los "puntos actuales" y la "condición proyectada". |
| P3 | **Instrumentos que siguen abiertos:** la Autoevaluación Unidad 5 de AED tiene 24 notas (contra 145 de la Unidad 1) y la Evaluación Semanal Nº2 de PyE tiene 13. ¿Les ponemos 0 a todos los que no la tienen? | Con la decisión 1, muchos alumnos bajan de condición por un instrumento que tal vez todavía no cerró. | Ponerles 0 igual (es la regla acordada), pero avisarlo en el dashboard. O excluir los instrumentos con menos del X % de entregas. |
| P4 | **319 alumnos por materia en participación** contra ~163 inscriptos. ¿El reporte de participación incluye a toda la cohorte? | Si usamos participación sin cruzar con la base de alumnos, los KPIs de "inactivos" se inflan. | Usar siempre la base de la decisión 2. |
| P5 | ¿Subimos `reports/calidad_datos.md` a git? | Es un archivo generado, pero sirve para el informe. | Sí, subirlo. |
| P6 | ¿Subimos `.claude/launch.json`? | Solo sirve para levantar la app desde Claude Code. | No, agregarlo al `.gitignore`. |

---

## 5. Qué falta completar

| Paso | Qué | Archivo | Alimenta a |
|---|---|---|---|
| 4 | Modelo estrella: `dim_alumno`, `dim_asignatura`, `dim_instrumento`, `dim_fecha`, `fact_interaccion`, `fact_calificacion`, `fact_participacion`, `fact_matricula`. Último estado de matrícula por alumno. Aplicar las decisiones 1 a 4. | `src/modelo.py` | Todos |
| 5 | Nota final y condición (Libre / Regular / Promociona) según el esquema de cada materia. | `src/modelo.py` o `src/notas.py` | Rendimiento, Individual |
| 6 | Tablas de KPIs: participación, trazabilidad, calificaciones, cruces (correlaciones) y matrícula. | `src/kpis.py` | General, Participación, Trazabilidad, Notas vs. Participación, Matrícula |
| 7 | Completar las 7 páginas de Streamlit (con gráficos de plotly). | `app/pages/*.py` | — |
| 8 | Informe técnico: proceso de limpieza, justificación de los KPIs, explicación de los dashboards y conclusiones. | `reports/` | — |

**Para regularizar** la consigna pide **al menos 3 dashboards funcionales** y un informe de avance con KPIs calculados. Los más rápidos de tener con lo que ya hay son **Trazabilidad**, **Participación** y **Matrícula y Alertas**, porque no dependen de la nota final (P1 a P3).

**Cómo repartir el trabajo:** cada dashboard es un archivo aparte en `app/pages/`, así que cada integrante puede tomar uno sin pisarse con los demás, una vez que estén las tablas de gold del paso 6.

---

## 6. Corregir / tener en cuenta

- **Git:** todo lo hecho hasta ahora está en la rama `paso-1-2-ingesta`, con un Pull Request abierto contra `main` para que el equipo lo revise.
- **Último estado de matrícula:** hay 11 alumnos con varias filas (altas y bajas). En el paso 4 hay que quedarse con la de fecha más reciente, usando la fecha ya parseada en silver, no el texto.
- **19 eventos sin `Acción`** en trazabilidad: son descargas de adjuntos en Foros. Quedan vacíos; se podrían clasificar como "Descargar" si molestan en los gráficos.
- **Eventos de junio y julio** (1.263, antes de la cursada): son todos de tutores y coordinadores armando el aula. El filtro por perfil ya los deja afuera.
- `Email` (participación) y `Detalle` (calificaciones) vienen vacíos en todas las filas. Se conservan para respetar el formato del Excel.
