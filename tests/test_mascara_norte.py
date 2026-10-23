"""DET-45/INV-25: máscara regional del norte grande, por celda.

Guarda del archivo versionado `web/data/mascara-norte.json` —cada celda exige centro,
radio, franja, motivo, evidencia y fecha de revisión, y debe caer en una comuna de Arica y
Parinacota, Tarapacá, Antofagasta o Atacama— y del comportamiento en `incidents.update`:
solo una detección de GOES (ABI) dentro de una celda vigente y en su `franja` se marca
como fuente fija; VIIRS/MODIS nunca se enmascaran y con la lista vacía nada cambia.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend import incidents
from backend.db import Database
from backend.geo import territory

DATA = Path(__file__).resolve().parent.parent / "web" / "data"

# Norte grande según los códigos de región del territorio BCN.
NORTE = {15, 1, 2, 3}  # Arica y Parinacota, Tarapacá, Antofagasta, Atacama

NOW = datetime(2027, 1, 20, 18, 0, tzinfo=timezone.utc)
DIA_UTC = "2027-01-20T18:00:00Z"     # 15:00 en Chile (verano, UTC-3): dentro de la franja «dia»
NOCHE_UTC = "2027-01-20T04:00:00Z"   # 01:00 en Chile: fuera de «dia», dentro de «siempre»
CELL_LAT, CELL_LON = -24.0, -69.0    # desierto de la región de Antofagasta (comuna 2101)
LEJOS_LAT, LEJOS_LON = -24.4, -69.0  # ~44 km al sur: fuera del radio de la celda de prueba


def _archivo() -> dict:
    return json.loads((DATA / "mascara-norte.json").read_text(encoding="utf-8"))


def _celda(**extra) -> dict:
    """Una celda de prueba completa y vigente sobre (CELL_LAT, CELL_LON)."""
    return {"lat": CELL_LAT, "lon": CELL_LON, "radio_km": 3, "franja": "dia",
            "motivo": "planta solar de prueba",
            "evidencia": {"fecha": "2027-01-15", "conteo": 12},
            "revisar_el": "2027-06-30", **extra}


def _deteccion(db: Database, ident: str, sensor: str, stamp: str,
               lat: float = CELL_LAT, lon: float = CELL_LON) -> dict:
    """Detección guardada y lista para `incidents.update`, como `latest_point` de test_fixed_source."""
    res = 2000 if sensor == "ABI" else 375
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (ident, "goes" if sensor == "ABI" else "firms", sensor, "SAT", res, lat, lon, stamp,
         10.0, "nominal", 2101, stamp),
    )
    return {"id": ident, "lat": lat, "lon": lon, "observed_at": stamp, "sensor": sensor,
            "confidence": "nominal", "resolution_m": res}


# --- guarda del archivo versionado ---


def test_el_archivo_existe_y_declara_su_metodo():
    data = _archivo()
    for campo in ("source", "fetched_at", "metodo", "cells"):
        assert campo in data, f"mascara-norte.json: falta {campo}"
    assert isinstance(data["cells"], list), "`cells` debe ser una lista"
    datetime.fromisoformat(str(data["fetched_at"]).replace("Z", "+00:00"))  # fecha legible


def test_cada_celda_valida_su_esquema_y_cae_en_el_norte():
    """Sin medición no hay celda: cada una exige evidencia, fecha de revisión y una comuna
    de las cuatro regiones del norte grande (la máscara no puede «migrar» al sur)."""
    terr = territory()
    for i, cell in enumerate(_archivo()["cells"]):
        ctx = f"cells[{i}]"
        for campo in ("lat", "lon", "radio_km", "franja", "motivo", "evidencia", "revisar_el"):
            assert campo in cell, f"{ctx}: falta {campo}"
        assert isinstance(cell["lat"], (int, float)) and isinstance(cell["lon"], (int, float)), \
            f"{ctx}: lat/lon no numéricos"
        # Tope de guarda, no de medición: un radio de ciudad ya no es una celda puntual.
        assert isinstance(cell["radio_km"], (int, float)) and 0 < cell["radio_km"] <= 10, \
            f"{ctx}: radio_km {cell['radio_km']} fuera de (0, 10]"
        assert cell["franja"] in ("dia", "siempre"), f"{ctx}: franja {cell['franja']!r} inesperada"
        assert isinstance(cell["motivo"], str) and cell["motivo"].strip(), f"{ctx}: motivo vacío"
        evidencia = cell["evidencia"]
        assert isinstance(evidencia, dict) and evidencia.get("fecha") and \
            isinstance(evidencia.get("conteo"), int) and evidencia["conteo"] >= 1, \
            f"{ctx}: evidencia sin fecha y conteo de la medición"
        datetime.fromisoformat(str(evidencia["fecha"]).replace("Z", "+00:00"))
        date.fromisoformat(str(cell["revisar_el"]))  # fecha ISO AAAA-MM-DD
        comuna = terr.locate(cell["lat"], cell["lon"])
        assert comuna is not None and comuna.region_code in NORTE, (
            f"{ctx}: cae en {comuna.region if comuna else 'fuera de las comunas'}, "
            "no en el norte grande"
        )


# --- comportamiento ---


def test_con_la_lista_vacia_nada_cambia(tmp_path, monkeypatch):
    monkeypatch.setattr(incidents, "mascara_norte", lambda: [])
    db = Database(tmp_path / "brasa.db")
    [incident] = incidents.update(db, [_deteccion(db, "g1", "ABI", DIA_UTC)], NOW)
    assert incident["fixed_source"] == 0 and incident["fixed_reason"] is None


def test_goes_diurna_dentro_de_la_celda_queda_marcada(tmp_path, monkeypatch):
    monkeypatch.setattr(incidents, "mascara_norte", lambda: [_celda()])
    db = Database(tmp_path / "brasa.db")
    [incident] = incidents.update(db, [_deteccion(db, "g1", "ABI", DIA_UTC)], NOW)
    assert incident["fixed_source"] == 1
    assert incident["fixed_reason"] == "máscara del norte: planta solar de prueba"


def test_viirs_en_la_misma_celda_no_se_enmascara(tmp_path, monkeypatch):
    """VIIRS ve con resolución suficiente: la máscara es solo para GOES."""
    monkeypatch.setattr(incidents, "mascara_norte", lambda: [_celda()])
    db = Database(tmp_path / "brasa.db")
    [incident] = incidents.update(db, [_deteccion(db, "v1", "VIIRS", DIA_UTC)], NOW)
    assert incident["fixed_source"] == 0 and incident["fixed_reason"] is None


def test_fuera_de_la_celda_o_de_la_franja_no_se_marca(tmp_path, monkeypatch):
    monkeypatch.setattr(incidents, "mascara_norte", lambda: [_celda()])
    db = Database(tmp_path / "brasa.db")
    lejos = incidents.update(db, [_deteccion(db, "g1", "ABI", DIA_UTC, LEJOS_LAT, LEJOS_LON)], NOW)
    assert lejos[0]["fixed_source"] == 0 and lejos[0]["fixed_reason"] is None
    # Misma celda pero de noche (01:00 en Chile): la franja «dia» no la cubre.
    noche = incidents.update(db, [_deteccion(db, "g2", "ABI", NOCHE_UTC)], NOW)
    assert noche[0]["fixed_source"] == 0 and noche[0]["fixed_reason"] is None


def test_franja_siempre_tambien_cubre_la_noche(tmp_path, monkeypatch):
    monkeypatch.setattr(incidents, "mascara_norte", lambda: [_celda(franja="siempre")])
    db = Database(tmp_path / "brasa.db")
    [incident] = incidents.update(db, [_deteccion(db, "g1", "ABI", NOCHE_UTC)], NOW)
    assert incident["fixed_source"] == 1


def test_celda_vencida_deja_de_silenciar(tmp_path, monkeypatch):
    """`revisar_el` pasado apaga la celda: preferimos avisar de más a tapar con medición vieja."""
    monkeypatch.setattr(incidents, "mascara_norte", lambda: [_celda(revisar_el="2027-01-19")])
    db = Database(tmp_path / "brasa.db")
    [incident] = incidents.update(db, [_deteccion(db, "g1", "ABI", DIA_UTC)], NOW)
    assert incident["fixed_source"] == 0 and incident["fixed_reason"] is None
