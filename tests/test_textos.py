"""Tests de src/textos.py: textos dinámicos de los dashboards (D77)."""
import pytest

from src.textos import comparacion_veces, enumerar, numero, proporcion_en_palabras


@pytest.mark.parametrize("p, esperado", [
    (50, "La mitad"), (45, "La mitad"), (55, "La mitad"), (44.9, "45 %"),
    (33.3, "Uno de cada tres"), (31, "Uno de cada tres"), (66, "Dos de cada tres"),
    (75, "Tres de cada cuatro"), (77.9, "Tres de cada cuatro"), (25, "Uno de cada cuatro"),
    (80, "Cuatro de cada cinco"), (90, "Nueve de cada diez"), (10, "Uno de cada diez"),
    (57.4, "Tres de cada cinco"), (56, "56 %"), (71, "71 %"), (0, "Nadie"), (100, "Todos"),
])
def test_proporcion_en_palabras(p, esperado):
    assert proporcion_en_palabras(p) == esperado


def test_proporcion_sin_dato():
    assert proporcion_en_palabras(float("nan")) == "" and proporcion_en_palabras(None) == ""


@pytest.mark.parametrize("mayor, menor, esperado", [
    (40, 20, "el doble que"), (36, 20, "el doble que"), (30, 10, "el triple que"),
    (24, 10, "2,4 veces más que"), (35, 10, "3,5 veces más que"), (30, 20, None), (10, 0, None),
])
def test_comparacion_veces(mayor, menor, esperado):
    assert comparacion_veces(mayor, menor) == esperado


def test_enumerar_y_numero():
    assert enumerar(["a"]) == "a" and enumerar(["a", "b", "c"]) == "a, b y c" and enumerar([]) == ""
    assert numero(1234.56, 1) == "1.234,6" and numero(float("nan")) == "–"
