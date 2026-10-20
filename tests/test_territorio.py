"""QA-89: guarda de realismo de la frontera de Chile.

Fija con coordenadas reales lo que hasta ahora solo se había comprobado a mano:
`territory().locate` acepta puntos chilenos de punta a punta y rechaza Argentina,
Bolivia, Perú y el mar abierto. Si alguien afloja `tolerance_deg` o invierte lat/lon,
estos casos se ponen rojos y los focos falsos del extranjero no vuelven al mapa.
"""

from __future__ import annotations

import pytest

from backend.geo import territory

# (nombre, lat, lon): puntos reales que no son Chile y no deben tener comuna.
FUERA_DE_CHILE = [
    pytest.param("Mendoza, Argentina", -32.89, -68.84, id="argentina-mendoza"),
    pytest.param("Bariloche, Argentina", -41.13, -71.31, id="argentina-bariloche"),
    pytest.param("Buenos Aires, Argentina", -34.60, -58.40, id="argentina-buenos-aires"),
    pytest.param("La Paz, Bolivia", -16.50, -68.15, id="bolivia-la-paz"),
    pytest.param("Santa Cruz, Bolivia", -17.78, -63.18, id="bolivia-santa-cruz"),
    pytest.param("Lima, Perú", -12.05, -77.04, id="peru-lima"),
    pytest.param("Tacna, Perú", -18.01, -70.25, id="peru-tacna"),
    pytest.param("mar frente a Valparaíso", -33.00, -72.50, id="mar-valparaiso"),
    pytest.param("mar frente a Coquimbo", -29.95, -71.80, id="mar-coquimbo"),
    pytest.param("Pacífico en la latitud de Constitución", -35.33, -72.60, id="mar-constitucion"),
]

# (nombre, lat, lon, comuna esperada): puntos reales de Chile, de Arica a Punta Arenas.
EN_CHILE = [
    pytest.param("Arica", -18.48, -70.31, "Arica", id="arica"),
    pytest.param("Iquique", -20.21, -70.15, "Iquique", id="iquique"),
    pytest.param("La Serena", -29.90, -71.25, "La Serena", id="la-serena"),
    pytest.param("Valparaíso", -33.05, -71.62, "Valparaíso", id="valparaiso"),
    pytest.param("Talca", -35.43, -71.66, "Talca", id="talca"),
    pytest.param("Concepción", -36.83, -73.05, "Concepción", id="concepcion"),
    pytest.param("Valdivia", -39.81, -73.25, "Valdivia", id="valdivia"),
    pytest.param("Coyhaique", -45.57, -72.07, "Coyhaique", id="coyhaique"),
    pytest.param("Punta Arenas", -53.16, -70.91, "Punta Arenas", id="punta-arenas"),
    # ~220 m mar adentro frente a Valparaíso: fuera del polígono, dentro de la tolerancia.
    pytest.param("costa frente a Valparaíso", -33.05, -71.664, "Valparaíso", id="costa-valparaiso"),
]


@pytest.mark.parametrize("nombre,lat,lon", FUERA_DE_CHILE)
def test_puntos_fuera_de_chile_no_tienen_comuna(nombre, lat, lon):
    assert territory().locate(lat, lon) is None, f"{nombre} no es Chile y no debe caer en una comuna"


@pytest.mark.parametrize("nombre,lat,lon,esperada", EN_CHILE)
def test_puntos_chilenos_caen_en_su_comuna(nombre, lat, lon, esperada):
    t = territory()
    comuna = t.locate(lat, lon)
    assert comuna is not None, f"{nombre} es Chile y debe caer en una comuna"
    assert comuna.name == esperada, f"{nombre} cayó en {comuna.name!r}, se esperaba {esperada!r}"
    assert comuna.name.strip()
    assert comuna.region
    assert int(str(comuna.code)[:-3]) == comuna.region_code, f"{nombre}: code {comuna.code} no calza con región {comuna.region_code}"
    assert t.regions[comuna.region_code]["name"] == comuna.region, f"{nombre}: región {comuna.region!r} no calza con el catálogo"


def test_margen_costero_deja_entrar_un_punto_frente_a_la_costa():
    """Un punto ~220 m mar adentro frente a Valparaíso entra por la tolerancia por defecto.

    Los polígonos comunales son generalizados y recortan islas, fiordos y la costa: sin este
    margen (~1 km) la ingesta de FIRMS perdería focos costeros reales. El test fija las dos
    caras: el punto no está en el polígono y, aun así, `locate` lo asigna a Valparaíso.
    """
    t = territory()
    assert t.locate(-33.05, -71.664, tolerance_deg=0) is None
    assert t.locate(-33.05, -71.664).name == "Valparaíso"
