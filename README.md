# TFI – Business Intelligence & Analytics (LMS)

## Estructura
```
lms-learning-analytics/
├── data/
│   ├── raw/        Excel originales (no se tocan)
│   ├── bronze/     Excel -> Parquet tal cual (todo texto)          <- src/ingesta.py
│   ├── silver/     Datos limpios y tipados                          <- src/limpieza.py   (paso 3)
│   └── gold/       Modelo estrella + KPIs                           <- src/modelo.py     (paso 4-6)
├── src/
│   ├── config.py     Rutas, asignaturas, tipos de archivo y esquema académico
│   ├── ingesta.py    raw -> bronze (reconoce cada Excel por su contenido)
│   ├── limpieza.py   bronze -> silver + reporte de calidad
│   ├── validacion.py Controles de un Excel nuevo antes de usarlo
│   └── pipeline.py   procesar() y agregar_archivo(): todo el pipeline en una llamada
├── tests/          python -m pytest
├── app/            Dashboard Streamlit                              (paso 7)
└── reports/        Reporte de calidad de datos, capturas, informe
```

## Cómo correr
Requiere **Python 3.12 o superior** (las versiones de `requirements.txt` no se instalan en versiones anteriores).
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |  Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m src.pipeline       # raw -> bronze -> silver + reports/calidad_datos.md (siempre desde la raíz)
python -m pytest             # tests

streamlit run app/Inicio.py  # dashboards (se abre en el navegador)
```

Para agregar un archivo nuevo (por ej., el 2° parcial de Álgebra):
```bash
python -m src.pipeline agregar ruta/al/archivo.xlsx
```
Lo valida, lo copia a la carpeta de su materia en `data/raw/` y recalcula todo. Si el archivo
tiene un problema, muestra el motivo y no toca nada. El archivo se reconoce por su contenido,
así que no importa cómo se llame. No hay que tocar código.
