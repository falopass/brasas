"""DET-23: el ciclo de ingesta baja los destellos GLM recientes por su cuenta.

Sin red: S3 simulado con el `FakeWeb` de `tests/conftest.py`. Antes la tabla `lightning`
solo se llenaba cuando alguien pedía `/api/opendata/lightning.geojson`, así que la marca
«rayos cerca del inicio» dependía del tráfico; ahora `_ingest_glm` corre dentro de
`ingest_cycle`, antes de agrupar los incidentes, con cadencia `glm_at` y una sola
descarga por archivo (dedup por `ingest_runs`).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from backend.providers import glm
from tests.test_glm import key_for
from tests.test_incidents import obs

SAMPLE = Path(__file__).parent / "data" / "glm_lcfa_sample.nc"


def _listing(*keys: str) -> httpx.Response:
    body = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    return httpx.Response(200, text=f"<ListBucketResult>{body}</ListBucketResult>")


def s3_glm(web, *keys: str) -> None:
    """S3 con LCFA recientes: el listado GLM entrega las claves y la descarga, el fixture."""
    web.add(lambda r: "list-type" in r.url.params and r.url.params["prefix"].startswith("GLM"),
            lambda r: _listing(*keys))
    web.add(lambda r: r.url.path.endswith(".nc"),
            lambda r: httpx.Response(200, content=SAMPLE.read_bytes()))


def glm_requests(web) -> list[httpx.Request]:
    """Pedidos al producto GLM (listado o descarga): el FDCF usa el mismo bucket simulado."""
    return [r for r in web.requests
            if r.url.params.get("prefix", "").startswith("GLM") or r.url.path.startswith("/GLM")]


def test_the_cycle_saves_recent_flashes_and_records_the_run(make_client, web):
    key = key_for(datetime.now(timezone.utc))
    s3_glm(web, key)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        result = asyncio.run(svc.ingest_cycle())
        assert result["glm_flashes"] == 2, "los dos destellos chilenos del fixture"
        assert svc.db.one("SELECT COUNT(*) AS n FROM lightning")["n"] == 2
        run = svc.db.one("SELECT product, ok, n_new FROM ingest_runs WHERE source_ref = ?", (key,))
        assert run["product"] == "GOES19_GLM" and run["ok"] == 1 and run["n_new"] == 2


def test_the_incident_mark_uses_the_flashes_of_the_same_cycle(make_client, web):
    """La pasada corre antes de agrupar: un foco nuevo ya sale con la marca calculada."""
    key = key_for(datetime.now(timezone.utc))
    s3_glm(web, key)
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        flash = glm.parse_lcfa(SAMPLE.read_bytes(), "G19", key)[0]
        # Detección recién llegada (pendiente de evaluar) un minuto después del destello:
        # cae dentro de la ventana [first_seen - 2 h, first_seen] de la marca.
        obs(svc.db, "v1", flash["lat"], flash["lon"], when=datetime.now(timezone.utc) + timedelta(minutes=1))
        asyncio.run(svc.ingest_cycle())
        inc = svc.db.one("SELECT lightning_count, lightning_km FROM incidents")
        assert inc["lightning_count"] >= 1 and inc["lightning_km"] is not None


def test_a_second_cycle_inside_the_cadence_does_not_touch_s3(make_client, web):
    s3_glm(web, key_for(datetime.now(timezone.utc)))
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        assert asyncio.run(svc.ingest_cycle())["glm_flashes"] == 2
        asked = len(glm_requests(web))
        result = asyncio.run(svc.ingest_cycle())
        assert result["glm_flashes"] == 0
        assert len(glm_requests(web)) == asked, "dentro de GLM_EVERY_MIN no vuelve a S3"


def test_a_processed_file_is_not_downloaded_again(make_client, web):
    """Pasada la cadencia, la dedup por `ingest_runs` evita bajar dos veces el mismo LCFA."""
    s3_glm(web, key_for(datetime.now(timezone.utc)))
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        asyncio.run(svc.ingest_cycle())
        svc.db.execute("DELETE FROM kv WHERE key = 'glm_at'")  # como si hubieran pasado los 5 min
        downloads = [r for r in web.requests if r.url.path.endswith(".nc")]
        assert asyncio.run(svc.ingest_cycle())["glm_flashes"] == 0
        assert [r for r in web.requests if r.url.path.endswith(".nc")] == downloads
        assert svc.db.one("SELECT COUNT(*) AS n FROM lightning")["n"] == 2, "tampoco duplica"


def test_a_glm_failure_does_not_stop_the_cycle(make_client, web):
    """S3 caído: el ciclo sigue igual y el fallo del listado queda en `ingest_runs`."""
    web.add(lambda r: True, lambda r: httpx.Response(500))
    with make_client(GOES_ENABLED="1") as client:
        svc = client.app.state.services
        result = asyncio.run(svc.ingest_cycle())
        assert result["glm_flashes"] == 0 and "glm_error" not in result
        failed = svc.db.query("SELECT source_ref FROM ingest_runs WHERE ok = 0 AND product = ?", (glm.PRODUCT,))
        assert [r["source_ref"] for r in failed] == ["listado S3"]
