"""
Textos de lectura armados con los datos (D77).

Funciones puras, sin Streamlit ni pandas, para que los títulos dinámicos de los
dashboards se puedan probar: "La mitad entró en los últimos 7 días", "el doble
que", "Álgebra, AED y PyE". No calculan métricas: reciben los números ya hechos.
"""
from __future__ import annotations

import math

# Fracciones que se dicen en palabras, de la más simple a la menos (la primera que
# entra en la tolerancia gana). "La mitad" tiene su propio margen (45-55 %).
FRACCIONES = [
    (1, 3, "Uno de cada tres"), (2, 3, "Dos de cada tres"),
    (1, 4, "Uno de cada cuatro"), (3, 4, "Tres de cada cuatro"),
    (1, 5, "Uno de cada cinco"), (2, 5, "Dos de cada cinco"), (3, 5, "Tres de cada cinco"),
    (4, 5, "Cuatro de cada cinco"),
    (1, 10, "Uno de cada diez"), (9, 10, "Nueve de cada diez"),
]
TOLERANCIA_PP = 3


def _vacio(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def numero(x: float, decimales: int = 0) -> str:
    """1234.5 -> '1.234,5' (formato es-AR). Sin dato -> '–'."""
    if _vacio(x):
        return "–"
    return f"{x:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def proporcion_en_palabras(p: float) -> str:
    """p en porcentaje (0-100) -> 'La mitad', 'Dos de cada tres', ... si está a
    3 pp o menos de esa fracción; si no, '52 %'. Sin dato -> ''."""
    if _vacio(p):
        return ""
    if 45 <= p <= 55:
        return "La mitad"
    for num, den, texto in FRACCIONES:
        if abs(p - num / den * 100) <= TOLERANCIA_PP:
            return texto
    if p <= 0.5:
        return "Nadie"
    if p >= 99.5:
        return "Todos"
    return f"{numero(p)} %"


def comparacion_veces(mayor: float, menor: float) -> str | None:
    """Cuántas veces es `mayor` respecto de `menor`, en palabras: 'el doble que',
    'el triple que', '2,4 veces más que'. Si la razón es menor que 1,8 (o no se
    puede calcular) devuelve None y el que llama usa 'frente a X en'."""
    if _vacio(mayor) or _vacio(menor) or menor <= 0:
        return None
    r = mayor / menor
    if r < 1.8:
        return None
    if r < 2.2:
        return "el doble que"
    if 2.8 <= r < 3.2:
        return "el triple que"
    return f"{numero(r, 1)} veces más que"


def enumerar(items: list[str], conjuncion: str = "y") -> str:
    """['a', 'b', 'c'] -> 'a, b y c'."""
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {conjuncion} " + items[-1]
