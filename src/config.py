"""
Configuración central del proyecto.
Todas las rutas y reglas de negocio viven acá para no repetirlas en cada script.
"""
from pathlib import Path

# --- Rutas -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"          # Excel originales (NUNCA se modifican)
BRONZE = DATA / "bronze"    # Excel -> Parquet "tal cual" (todo como texto)
SILVER = DATA / "silver"    # Datos limpios, tipados y unificados
GOLD = DATA / "gold"        # Modelo estrella + tablas de KPIs para el dashboard

MATRICULADOS_DIR = RAW / "Matriculados"

# --- Asignaturas -----------------------------------------------------------
# Clave = nombre de la carpeta. "codigo" = comisión que figura en Matriculados.
ASIGNATURAS = {
    "Álgebra": {"codigo": "2319", "sigla": "ALG"},
    "Algoritmos y Estructuras de Datos": {"codigo": "2320", "sigla": "AED"},
    "Probabilidad y Estadística": {"codigo": "2321", "sigla": "PYE"},
}

# --- Esquema académico (sección 5 de la consigna) --------------------------
# metodo:
#   "acumulativo" -> se suman puntos. Como todavía no están todos los
#                    instrumentos, se proyecta: (puntos / max_rendido) * total_max
#   "promedio"    -> promedio de instrumentos (cada uno sobre 100)
ESQUEMA = {
    "Álgebra": {
        "metodo": "acumulativo",
        "total_max": 120,
        "cortes": {"Regular": 60, "Promociona": 85},
    },
    "Probabilidad y Estadística": {
        "metodo": "promedio",
        "total_max": 100,
        "cortes": {"Regular": 60, "Promociona": 85},
    },
    "Algoritmos y Estructuras de Datos": {
        "metodo": "promedio",
        "total_max": 100,
        "cortes": {"Regular": 60, "Promociona": 90},
    },
}
