"""Tests de src/textos.py: textos dinámicos de los dashboards (D77)."""
import pytest

from src.textos import (comparacion_veces, de_cada_diez, enumerar, lectura_quintiles, nota_en_escala, numero,
                        proporcion_en_palabras, rangos_quintiles, redondear)


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


def test_redondeo_de_escuela():
    # la mediana de minutos de Álgebra al 24/10/2025 es 144,5: tiene que verse 145 en todos lados
    assert numero(144.5) == "145" and redondear(144.5) == 145 and numero(2.25, 1) == "2,3"


@pytest.mark.parametrize("p, esperado", [(80, "8"), (85, "9"), (96, "más de 9"), (100, "10"), (4, "menos de 1"),
                                         (0, "0"), (50, "5")])
def test_de_cada_diez(p, esperado):
    assert de_cada_diez(p) == esperado


def test_lectura_quintiles():
    assert lectura_quintiles(["ALG", "AED", "PYE"], [80, 90, 96], [4, 50, 30], "minutos") == (
        "Del 20 % con menos minutos quedan libres 8 de cada 10 en ALG, 9 en AED y más de 9 en PYE; "
        "del 20 % con más, menos de 1, 5 y 3.")
    assert lectura_quintiles(["AED"], [90], [50], "sesiones") == (
        "Del 20 % con menos sesiones quedan libres 9 de cada 10; del 20 % con más, 5.")
    assert lectura_quintiles([], [], [], "x") == ""


def test_nota_en_escala():
    assert nota_en_escala(94.8, 79.0, 120) == "94,8/120 (79,0/100)"
    assert nota_en_escala(56.0, 56.0, 100) == "56,0"


def test_rangos_quintiles():
    assert rangos_quintiles([59.4, 116, 186, 300, 1200]) == ["hasta 59", "60–116", "117–186", "187–300", "301–1.200"]
    assert rangos_quintiles([0, 0, 12, 13, 40]) == ["0", "0", "1–12", "13", "14–40"]


# --- Ficha individual (D87) ---------------------------------------------------
from src.textos import titulo_condiciones, titulo_notas, titulo_participacion, titulo_trazabilidad  # noqa: E402


@pytest.mark.parametrize("condiciones, esperado", [
    ([("ALG", "Promociona"), ("PYE", "Promociona"), ("AED", "Promociona")], "Promociona las 3 materias"),
    ([("PYE", "Regular"), ("AED", "Libre")], "Libre en AED, regular en PYE"),
    ([("ALG", "Promociona"), ("PYE", "Libre"), ("AED", "Libre")], "Libre en PYE y AED, promociona ALG"),
    ([("ALG", "Libre")], "Libre en ALG"),
    ([("ALG", "Sin evaluaciones"), ("PYE", "Sin evaluaciones")], "Sin evaluaciones en las 2 materias"),
])
def test_titulo_condiciones(condiciones, esperado):
    assert titulo_condiciones(condiciones) == esperado


def test_titulo_notas():
    assert (titulo_notas(15, 16, 0, ("Actividad Rápida 4", "PYE", 50.0))
            == "Aprobó 15 de 16 instrumentos; la más baja: Actividad Rápida 4 (PYE, 50 %)")
    assert titulo_notas(0, 5, 5, None) == "No rindió ninguno de los 5 instrumentos"
    assert titulo_notas(0, 0, 0, None).startswith("Todavía no hay evaluaciones")


def test_titulo_participacion():
    assert (titulo_participacion([("Álgebra", 98, 37, 60), ("AED", 50, 45, 55)])
            == "En Álgebra: nota p98 con minutos p37")
    assert titulo_participacion([("Álgebra", 50, 45, 55)]).startswith("Nota y actividad en percentiles parecidos")


def test_titulo_trazabilidad():
    assert (titulo_trazabilidad([("PYE", "Evaluación", 17.0, 10.8), ("ALG", "Contenido", 32.0, 36.5)])
            == "En PYE, Evaluación: 17 % de sus clics vs. 11 % del curso (+6,2 p.p.)")
    assert titulo_trazabilidad([("ALG", "Contenido", 36.0, 36.5)]).startswith("Reparte sus clics como el curso")
