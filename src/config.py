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
REPORTS = ROOT / "reports"  # Reporte de calidad de datos, capturas, informe
REFERENCIA = DATA / "referencia"  # Tablas armadas a mano (sí van a GitHub)
CATEGORIAS_ACCIONES = REFERENCIA / "categorias_acciones.csv"

MATRICULADOS_DIR = RAW / "Matriculados"

# --- Asignaturas -----------------------------------------------------------
# Clave = nombre de la carpeta. "codigo" = comisión que figura en Matriculados.
ASIGNATURAS = {
    "Álgebra": {"codigo": "2319", "sigla": "ALG"},
    "Algoritmos y Estructuras de Datos": {"codigo": "2320", "sigla": "AED"},
    "Probabilidad y Estadística": {"codigo": "2321", "sigla": "PYE"},
}

# --- Tipos de archivo (ingesta) --------------------------------------------
# Cada Excel se reconoce por su CONTENIDO, no por el nombre del archivo:
#   "firma"       -> texto que aparece en las primeras filas (título o celda A3)
#   "encabezado"  -> columnas que tiene que tener la fila de encabezado. La
#                    ingesta busca la primera fila que las contiene todas, en
#                    vez de usar un número de fila fijo.
#   "requeridas"  -> columnas mínimas para que el archivo sea válido.
FILAS_A_INSPECCIONAR = 15   # hasta qué fila se buscan la firma y el encabezado

TIPOS_ARCHIVO = {
    "calificaciones": {
        "firma": "Calificación:",
        "encabezado": ["Usuario", "Nota"],
        "requeridas": ["Usuario", "Apellido", "Nombre", "Nota", "Observaciones"],
    },
    "trazabilidad": {
        "firma": "Reporte de Trazabilidad",
        "encabezado": ["Fecha", "Usuario", "Acción"],
        "requeridas": ["Fecha", "Usuario", "Perfil", "Sección", "Acción"],
    },
    "participacion": {
        "firma": "Reporte de lectura y participación",
        "encabezado": ["Usuario", "Avance", "Interacciones"],
        "requeridas": ["Usuario", "Perfil", "Avance", "Interacciones", "Tiempo estimado de uso",
                       "Primera interacción", "Última interacción"],
    },
    "matriculados": {
        "firma": None,  # el título es '(2319) Álgebra': se reconoce por el encabezado
        "encabezado": ["Identificación", "Estado Insc."],
        "requeridas": ["Alumno", "Identificación", "Estado Insc.", "Fecha inscripción"],
    },
}

# --- Identificadores -------------------------------------------------------
# Formato válido de `Usuario` / `Identificación` después de normalizar.
# Alumnos ALU_####, Tutores DOC_##, Coordinadores e Invitados STAFF_##.
FORMATO_ID = r"ALU_\d{4}|DOC_\d{2}|STAFF_\d{2}"
PREFIJO_ALUMNO = "ALU_"

# --- Modelo (silver -> gold) ----------------------------------------------
SESION_MINUTOS = 30          # D25: más de 30 min sin eventos -> sesión nueva
PERFIL_ALUMNO = "Alumnos"    # D10: los KPIs de alumnos usan solo este perfil
ESTADO_INSCRIPTO = "Aceptada"
CATEGORIA_SIN_MAPEO = "Otros"  # acciones nuevas que no están en el CSV

# --- Métricas (gold -> KPIs, dependen de la fecha de corte) -----------------
FECHA_CORTE_DEFECTO = "2025-10-24"   # fecha de exportación de los Excel
UMBRAL_INACTIVIDAD_DIAS = 7          # D35: más de 7 días sin entrar -> inactivo
CONDICIONES = ["Libre", "Regular", "Promociona"]
SIN_EVALUACIONES = "Sin evaluaciones"  # todavía no hay instrumentos a la fecha de corte

# --- ML: grupos de alumnos con K-Means (Etapa 7, D57) -----------------------
# Variables de `tabla_alumnos` que usa el K-Means. Las de GRUPOS_LOG pasan por
# log(1 + x) antes de estandarizar: son muy asimétricas (pocos alumnos con
# muchísimas sesiones dominarían las distancias).
GRUPOS_VARIABLES = ["sesiones", "minutos", "semanas_activas", "avance", "nota_pct"]
GRUPOS_LOG = ["sesiones", "minutos"]
GRUPOS_K = range(3, 7)       # k candidatos; se elige el de mayor silhouette
GRUPOS_SEMILLA = 42          # misma semilla -> mismos grupos en cada corrida

# --- ML: predictor de abandono (Etapa 7, D58) --------------------------------
# Abandono = un alumno que venía entrando (al menos una interacción en los
# últimos ABANDONO_HORIZONTE_DIAS) y NO entra en los próximos
# ABANDONO_HORIZONTE_DIAS. Se entrena con "fotos" de la cursada tomadas cada
# ABANDONO_PASO_DIAS días (desde el día ABANDONO_HORIZONTE_DIAS de la cursada).
ABANDONO_HORIZONTE_DIAS = 14
ABANDONO_PASO_DIAS = 3       # no múltiplo de 7: las fotos caen en distintos días de la semana
ABANDONO_REGLA_DIAS = 7      # regla simple de referencia: "más de 7 días sin entrar"
# Costo de equivocarse (como en la clase 10): no detectar a quien abandona
# (falso negativo) cuesta 5 veces más que contactar a alguien que iba a seguir
# (falso positivo). El umbral del modelo es el que minimiza el costo total.
ABANDONO_COSTO_FN = 5
ABANDONO_COSTO_FP = 1
ABANDONO_SEMILLA = 42
ABANDONO_ARCHIVO = "modelo_abandono.joblib"   # se guarda junto a gold (se regenera con los datos)

# --- Esquema académico (sección 5 de la consigna) --------------------------
# metodo:
#   "acumulativo" -> se suman puntos. Como todavía no están todos los
#                    instrumentos, se proyecta: (puntos / max_rendido) * total_max
#   "promedio"    -> promedio de instrumentos (cada uno sobre 100)
# recuperatorio:
#   "reemplaza"   -> si el alumno lo rindió, su nota reemplaza a la del
#                    instrumento que recupera, aunque sea más baja (D20)
#   "suma"        -> es un instrumento más que suma puntos al total (D21)
# Un instrumento es recuperatorio si su nombre contiene "Recuperatorio"; el
# instrumento que recupera es el que tiene el mismo nombre sin esa palabra.
PALABRA_RECUPERATORIO = "recuperatorio"
ESQUEMA = {
    "Álgebra": {
        "metodo": "acumulativo",
        "total_max": 120,
        "cortes": {"Regular": 60, "Promociona": 85},
        "recuperatorio": "suma",
    },
    "Probabilidad y Estadística": {
        "metodo": "promedio",
        "total_max": 100,
        "cortes": {"Regular": 60, "Promociona": 85},
        "recuperatorio": "reemplaza",
    },
    "Algoritmos y Estructuras de Datos": {
        "metodo": "promedio",
        "total_max": 100,
        "cortes": {"Regular": 60, "Promociona": 90},
        "recuperatorio": "reemplaza",
    },
}
