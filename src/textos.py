"""
Textos de lectura armados con los datos (D77).

Funciones puras, sin Streamlit ni pandas, para que los títulos dinámicos de los
dashboards se puedan probar: "La mitad entró en los últimos 7 días", "el doble
que", "Álgebra, AED y PyE". No calculan métricas: reciben los números ya hechos.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

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


def redondear(x: float, decimales: int = 0) -> float:
    """Redondeo "de escuela" (144,5 -> 145), el mismo que hacen las tablas y los
    tooltips del navegador. El de Python (`round`, `f"{x:.0f}"`) redondea al par
    (144,5 -> 144) y hacía que la misma mediana se viera distinta en dos lugares."""
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP))


def numero(x: float, decimales: int = 0) -> str:
    """1234.5 -> '1.234,5' (formato es-AR, redondeo de escuela). Sin dato -> '–'."""
    if _vacio(x):
        return "–"
    return f"{redondear(x, decimales):,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


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


def de_cada_diez(p: float) -> str:
    """p en porcentaje -> cuántos de cada 10: '8', 'menos de 1', 'más de 9'."""
    if _vacio(p):
        return "–"
    r = int(redondear(p / 10))
    if r == 0 and p > 0:
        return "menos de 1"
    if r == 10 and p < 100:
        return "más de 9"
    return str(r)


def lectura_quintiles(siglas: list[str], libres_menos: list[float], libres_mas: list[float], sujeto: str) -> str:
    """La lectura principal de Notas vs. participación: cuántos de cada 10 quedan
    libres en el quinto con menos `sujeto` y en el quinto con más, por materia.
    'Del 20 % con menos minutos quedan libres 8 de cada 10 en ALG, 9 en AED y más
    de 9 en PYE; del 20 % con más, menos de 1, 5 y 3.' (una materia: sin siglas)."""
    if not siglas:
        return ""
    bajos = [de_cada_diez(p) for p in libres_menos]
    altos = [de_cada_diez(p) for p in libres_mas]
    if len(siglas) == 1:
        return (f"Del 20 % con menos {sujeto} quedan libres {bajos[0]} de cada 10; "
                f"del 20 % con más, {altos[0]}.")
    primero = [f"{bajos[0]} de cada 10 en {siglas[0]}"]
    resto = [f"{b} en {s}" for b, s in zip(bajos[1:], siglas[1:])]
    return (f"Del 20 % con menos {sujeto} quedan libres {enumerar(primero + resto)}; "
            f"del 20 % con más, {enumerar(altos)}.")


def nota_en_escala(nota: float, nota_pct: float, escala: int, decimales: int = 1) -> str:
    """Nota en la escala de la materia y, si no es sobre 100, su equivalente:
    '94,8/120 (79,0/100)'. Sobre 100: '79,0'."""
    if _vacio(nota_pct):
        return "–"
    if escala == 100:
        return numero(nota_pct, decimales)
    return f"{numero(nota, decimales)}/{escala} ({numero(nota_pct, decimales)}/100)"


def rangos_quintiles(hastas: list[float]) -> list[str]:
    """Etiquetas de los grupos de actividad, sin pisarse ni dejar huecos, a partir
    del máximo de cada grupo (de menor a mayor): [59.4, 116, 186] -> ['hasta 59',
    '60–116', '117–186']. Si dos grupos comparten el valor (empates, por ejemplo
    muchos alumnos con 0) se muestra ese valor solo: ['0', '0', '1–12']."""
    enteros = [int(redondear(h)) for h in hastas]
    etiquetas = []
    for i, alto in enumerate(enteros):
        if i == 0:
            etiquetas.append(numero(alto) if alto == 0 else f"hasta {numero(alto)}")
            continue
        bajo = enteros[i - 1] + 1
        etiquetas.append(numero(alto) if bajo >= alto else f"{numero(bajo)}–{numero(alto)}")
    return etiquetas
