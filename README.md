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
│   ├── config.py   Rutas, asignaturas y esquema académico
│   └── ingesta.py  Paso 2
├── app/            Dashboard Streamlit                              (paso 7)
└── reports/        Reporte de calidad de datos, capturas, informe
```

## Cómo correr
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |  Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m src.ingesta        # siempre desde la raíz del repo
```

Para agregar archivos nuevos (por ej., el 2° parcial de Álgebra) se copian a
`data/raw/<Asignatura>/` y se vuelve a correr el pipeline. No hay que tocar código.
