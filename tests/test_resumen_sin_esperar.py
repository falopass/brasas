"""MZ-RESUMEN: el estado de un lugar no espera más de unos segundos a Open-Meteo.

`build_summary` pedía el viento y el 30-30-30 del punto en serie; si el proveedor no
contestaba, `GET /api/shared/{token}` y `GET /api/places/{id}/summary` podían tardar
~80 s (dos timeouts de 40 s del cliente) — eso hacía expirar el e2e «compartir con la
familia» del PR #888. Ahora ambas consultas corren en paralelo con un plazo propio
(`METEO_ESPERA_RESUMEN_S`): al cumplirse, el dato que falta vale None y el resumen
sale con el lugar, los focos cercanos y su estado igual que antes.
"""

from __future__ import annotations

import asyncio
import time

from backend.routes import personal as personal_mod
from backend.routes.personal import METEO_ESPERA_RESUMEN_S


def _share_link(client) -> str:
    """Un dispositivo con un lugar compartido; devuelve el token del enlace."""
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    pid = client.post("/api/places", json={"name": "Casa", "lat": -33.05, "lon": -71.55}, headers=headers).json()["id"]
    return client.post(f"/api/places/{pid}/share", headers=headers).json()["token"]


async def _colgado(*_args, **_kwargs):
    """Una consulta a Open-Meteo que nunca contesta dentro del plazo."""
    await asyncio.sleep(30)
    return None  # el plazo la cancela antes de llegar aquí


def test_el_enlace_compartido_responde_aunque_open_meteo_no_conteste(make_client, monkeypatch):
    with make_client() as client:
        share = _share_link(client)
        svc = client.app.state.services
        monkeypatch.setattr(svc, "wind_at", _colgado)
        monkeypatch.setattr(personal_mod, "risk_point_at", _colgado)
        start = time.monotonic()
        res = client.get(f"/api/shared/{share}")
        elapsed = time.monotonic() - start
    assert res.status_code == 200
    assert elapsed < METEO_ESPERA_RESUMEN_S + 2
    body = res.json()
    assert body["place"]["name"] == "Casa"
    assert body["wind"] is None and body["risk_point"] is None
    assert body["status"]  # el resto del resumen se arma igual


def test_el_dato_que_llega_a_tiempo_se_usa(make_client, monkeypatch):
    """El viento llega y el 30-30-30 no: el resumen sale con viento y sin risk_point."""
    viento = {"speed": 12.0, "gust": 20.0, "direction": 200.0, "time": "2027-01-15T15:00"}

    async def _viento_ok(*_args, **_kwargs):
        return viento

    with make_client() as client:
        share = _share_link(client)
        svc = client.app.state.services
        monkeypatch.setattr(svc, "wind_at", _viento_ok)
        monkeypatch.setattr(personal_mod, "risk_point_at", _colgado)
        start = time.monotonic()
        res = client.get(f"/api/shared/{share}")
        elapsed = time.monotonic() - start
    assert res.status_code == 200
    assert elapsed < METEO_ESPERA_RESUMEN_S + 2
    body = res.json()
    assert body["wind"] == viento
    assert body["risk_point"] is None
