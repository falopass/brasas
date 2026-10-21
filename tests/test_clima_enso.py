"""Contrato de /api/climate/enso: nunca un valor inventado.

La regla delicada que fijan estas pruebas: si la NOAA no contesta, la ruta sirve la
última lectura buena guardada en `kv` con su `updated_at` original; si nunca hubo
lectura, los campos salen en null. Además: caché de 6 h cuando hay dato y reintento
espaciado de 600 s cuando la fuente cae, para no golpear al CPC a cada visita.
"""

from __future__ import annotations

import json
import re
import time


from backend.providers import noaa

CACHE_KEY = "climate:enso"
LAST_KEY = "enso_last"
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")  # UTC, como `stamp()`


def _stub_oni(monkeypatch, oni: float, season: str = "JAS", year: int = 2026):
    """`fetch_oni` simulado: devuelve una lectura con ese ONI y cuenta las llamadas."""
    calls = []

    async def fake(client):
        calls.append(client)
        return noaa.OniReading(season=season, year=year, sst=28.0, oni=oni)

    monkeypatch.setattr(noaa, "fetch_oni", fake)
    return calls


def _stub_down(monkeypatch):
    """`fetch_oni` simulado que siempre falla, como cuando el CPC no contesta."""
    calls = []

    async def fake(client):
        calls.append(client)
        raise noaa.NoaaError("El CPC de la NOAA no respondió (simulado).")

    monkeypatch.setattr(noaa, "fetch_oni", fake)
    return calls


def _get(client):
    response = client.get("/api/climate/enso")
    assert response.status_code == 200
    return response.json()


def test_fase_nino_con_oni_positivo(make_client, monkeypatch):
    _stub_oni(monkeypatch, 0.9)
    with make_client() as client:
        body = _get(client)
    assert body["phase"] == "nino"
    assert body["oni"] == 0.9
    assert (body["season"], body["year"]) == ("JAS", 2026)
    assert STAMP.fullmatch(body["updated_at"])


def test_fase_nina_con_oni_negativo(make_client, monkeypatch):
    _stub_oni(monkeypatch, -0.7)
    with make_client() as client:
        body = _get(client)
    assert body["phase"] == "nina"
    assert body["oni"] == -0.7


def test_fase_neutral_entre_los_umbrales(make_client, monkeypatch):
    _stub_oni(monkeypatch, 0.2)
    with make_client() as client:
        body = _get(client)
    assert body["phase"] == "neutral"
    assert body["oni"] == 0.2


def test_respuesta_siempre_trae_fuente(make_client, monkeypatch):
    _stub_oni(monkeypatch, 0.9)
    with make_client() as client:
        body = _get(client)
    assert body["source"] == noaa.SOURCE
    assert body["source_url"] == noaa.SOURCE_URL
    assert body["source_url"].startswith("https://")


def test_segunda_llamada_sale_de_cache_sin_llamar_a_noaa(make_client, monkeypatch):
    calls = _stub_oni(monkeypatch, 0.9)
    with make_client() as client:
        first = _get(client)
        second = _get(client)
    assert first == second
    assert len(calls) == 1


def test_acierto_cachea_6_horas_y_guarda_ultima_lectura(make_client, monkeypatch):
    _stub_oni(monkeypatch, 0.9)
    with make_client() as client:
        body = _get(client)
        db = client.app.state.services.db
        row = db.one("SELECT expires_at FROM cache WHERE key = ?", (CACHE_KEY,))
        saved = db.kv_get(LAST_KEY)
    assert 6 * 3600 - 120 < row["expires_at"] - time.time() <= 6 * 3600
    assert json.loads(saved) == body  # el respaldo en kv es la misma lectura servida


def test_noaa_caida_devuelve_ultima_lectura_con_su_fecha(make_client, monkeypatch):
    saved = {
        "phase": "nina",
        "oni": -0.9,
        "season": "DJF",
        "year": 2025,
        "updated_at": "2025-12-15T00:00:00Z",
        "source": noaa.SOURCE,
        "source_url": noaa.SOURCE_URL,
    }
    calls = _stub_down(monkeypatch)
    with make_client() as client:
        client.app.state.services.db.kv_set(LAST_KEY, json.dumps(saved))
        body = _get(client)
    assert body == saved  # verbatim: la fecha es la de la lectura, no la del reintento
    assert len(calls) == 1


def test_noaa_caida_sin_lectura_devuelve_nulos_y_no_ensucia_kv(make_client, monkeypatch):
    _stub_down(monkeypatch)
    with make_client() as client:
        body = _get(client)
        db = client.app.state.services.db
        still_empty = db.kv_get(LAST_KEY) is None
    for key in ("phase", "oni", "season", "year", "updated_at"):
        assert body[key] is None
    assert body["source"] == noaa.SOURCE and body["source_url"] == noaa.SOURCE_URL
    assert still_empty  # no se escribe un «null» como si fuera una lectura real


def test_caida_espacia_el_reintento_600_segundos(make_client, monkeypatch):
    calls = _stub_down(monkeypatch)
    with make_client() as client:
        first = _get(client)
        row = client.app.state.services.db.one("SELECT expires_at FROM cache WHERE key = ?", (CACHE_KEY,))
        second = _get(client)
    assert 600 - 120 < row["expires_at"] - time.time() <= 600
    assert second == first  # la respuesta de respaldo también queda en caché
    assert len(calls) == 1  # dentro de la ventana no se vuelve a golpear a la NOAA


def test_lectura_guardada_corrupta_se_trata_como_ausente(make_client, monkeypatch):
    """Un `kv` ilegible no puede tumbar la ruta: equivale a no tener lectura."""
    _stub_down(monkeypatch)
    with make_client() as client:
        client.app.state.services.db.kv_set(LAST_KEY, "{json roto")
        body = _get(client)
    assert body["phase"] is None and body["oni"] is None and body["updated_at"] is None


def test_lectura_guardada_incompleta_conserva_llaves_del_contrato(make_client, monkeypatch):
    """Si el respaldo viejo no tiene todas las llaves, las que faltan salen en null."""
    saved = {"phase": "nino", "oni": 0.9}  # formato anterior, sin season/year/updated_at
    _stub_down(monkeypatch)
    with make_client() as client:
        client.app.state.services.db.kv_set(LAST_KEY, json.dumps(saved))
        body = _get(client)
    assert body["phase"] == "nino" and body["oni"] == 0.9
    assert body["season"] is None and body["year"] is None and body["updated_at"] is None
    assert body["source"] == noaa.SOURCE and body["source_url"] == noaa.SOURCE_URL
