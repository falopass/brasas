"""FIX-10: un `work.db` restaurado llega con `official_fires` vacía y eso no puede traducirse
en avisos perdidos para los incendios que CONAF acaba de informar.

La guarda «la primera carga no avisa en masa» se mantiene: nunca se avisa por incendios de
más de 2 h. Con filas en la tabla el comportamiento no cambia en nada.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from backend.db import Database
from tests.test_conaf import CSV_HEAD, fire_row


def place(db: Database) -> None:
    db.execute("INSERT OR IGNORE INTO subscribers(id, created_at) VALUES ('s1', '2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.05,-71.40,10,'2026-01-01T00:00:00Z')")


def local_time(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).astimezone(
        ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")


def test_an_empty_table_still_warns_about_a_fire_that_just_started(make_client, web):
    """(a) Tabla vacía + incendio iniciado hace 1 h → aviso creado."""
    csv = {"body": CSV_HEAD + fire_row("1", "EL BELLOTO", "En combate", local_time(1), -33.06, -71.40)}
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=csv["body"]))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        place(svc.db)
        result = asyncio.run(svc.ingest_official_fires())
        assert result["official_new"] == 1 and result["official_alerts"] == 1
        [row] = svc.db.query("SELECT * FROM alerts WHERE observation_id = 'conaf:1'")
        assert row["place_id"] == "p1"


def test_an_empty_table_does_not_warn_about_an_old_fire(make_client, web):
    """(b) Tabla vacía + incendio iniciado hace 5 h → sin aviso: la guarda contra el aviso en
    masa se mantiene, 5 h ya es historia y no novedad."""
    csv = {"body": CSV_HEAD + fire_row("1", "VIEJO", "En combate", local_time(5), -33.06, -71.40)}
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=csv["body"]))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        place(svc.db)
        result = asyncio.run(svc.ingest_official_fires())
        assert result["official_new"] == 1 and result["official_alerts"] == 0


def test_an_empty_table_ignores_the_saved_etag(make_client, web):
    """(a bis) work.db restaurada vacía, pero `conaf_etag` sigue en `kv` (main, que sí se
    respalda): si se mandara, CONAF respondería 304 y la tabla quedaría vacía para siempre.
    Con la tabla vacía la descarga va sin If-None-Match."""
    seen: list[str | None] = []

    def csv_response(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("if-none-match"))
        if request.headers.get("if-none-match") == 'W/"v1"':
            return httpx.Response(304)
        return httpx.Response(200, headers={"ETag": 'W/"v1"'},
                              text=CSV_HEAD + fire_row("1", "EL BELLOTO", "En combate", local_time(1), -33.06, -71.40))

    web.add(lambda r: "githubusercontent" in r.url.host, csv_response)
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        svc.db.kv_set("conaf_etag", 'W/"v1"')   # la etiqueta sobrevivió en main; la tabla no
        place(svc.db)
        result = asyncio.run(svc.ingest_official_fires())
        assert seen == [None]
        assert result["official_new"] == 1 and result["official_alerts"] == 1


def test_a_populated_table_keeps_the_official_window(make_client, web):
    """(c) Con filas en la tabla no cambia nada: el mismo incendio de hace 5 h sí avisa,
    porque entra en la ventana habitual de OFFICIAL_HOURS (24 h)."""
    csv = {"body": CSV_HEAD + fire_row("1", "VIEJO", "Extinguido", "2026-01-01 10:00", -20.0, -70.0)}
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=csv["body"]))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        place(svc.db)
        asyncio.run(svc.ingest_official_fires())   # puebla `known`
        csv["body"] += fire_row("2", "EL BELLOTO", "En combate", local_time(5), -33.06, -71.40)
        result = asyncio.run(svc.ingest_official_fires())
        assert result["official_new"] == 1 and result["official_alerts"] == 1
