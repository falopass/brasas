"""ALR-42: una alerta oficial de SENAPRED que nombra la comuna o la región de un lugar
guardado genera un aviso, una sola vez por alerta y lugar.

El nivel sale del título oficial (decisión del dueño, 24-10-2026): «Alerta Roja» u orden
de evacuación → «urgente»; «Alerta Amarilla», «Alerta Temprana Preventiva» y lo que no
calce → «aviso». La deduplicación es por base, no por un `if`: `observation_id`
`senapred:<id>` con el UNIQUE(place_id, observation_id).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from backend import alerts as alerts_mod
from backend.db import Database
from backend.geo import territory
from backend.providers import senapred
from tests.test_senapred import _mock_senapred

NOW = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)

# Ítems ya normalizados por `fetch_alerts` (title/issued_at/url), como los recibe
# `evaluate_senapred` desde la caché `senapred:alertas`.
ALERTA_ROJA_ANGOL = {"id": "roja1",
                     "title": "Se declara Alerta Roja para la comuna de Angol por incendio forestal",
                     "issued_at": "2026-10-24T11:05:00-03:00",
                     "url": "https://senapred.cl/alertas/roja-angol"}
ALERTA_AMARILLA_ANGOL = {"id": "amar1",
                         "title": "Se declara alerta Amarilla para la comuna de Angol por evento meteorológico",
                         "issued_at": "2026-10-22T22:12:30-03:00",
                         "url": "https://senapred.cl/alertas/amarilla-angol"}
ALERTA_ATP_MAULE = {"id": "atp1",
                    "title": "Monitoreo Alerta Temprana Preventiva para la Región del Maule por evento meteorológico",
                    "issued_at": "2026-10-23T16:05:00-03:00",
                    "url": "https://senapred.cl/alertas/atp-maule"}
ALERTA_EVAC_ANGOL = {"id": "evac1",
                     "title": "Se declara Alerta Amarilla y se ordena la evacuación de sectores de la comuna de Angol "
                              "por incendio forestal",
                     "issued_at": "2026-10-24T12:00:00-03:00",
                     "url": "https://senapred.cl/alertas/evac-angol"}


def _db(tmp_path, comuna: int | None = 9201) -> Database:
    """Un lugar guardado en la comuna dada (9201 = Angol, La Araucanía; 7101 = Talca, Maule)."""
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
               "VALUES ('p1','s1','Casa','casa',-37.80,-72.79,10,?,'2026-10-01T00:00:00Z')", (comuna,))
    return db


def test_alerta_roja_sobre_la_comuna_genera_aviso_urgente(tmp_path):
    """(b) «Alerta Roja … por incendio forestal» → «urgente», con el texto oficial exacto."""
    db = _db(tmp_path)
    [created] = asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_ROJA_ANGOL], now=NOW))
    assert created["level"] == "urgente"
    row = db.one("SELECT * FROM alerts")
    assert row["observation_id"] == "senapred:roja1" and row["level"] == "urgente"
    # `observed_at` es la emisión oficial, pasada a UTC (11:05 -03:00 → 14:05Z).
    assert row["observed_at"] == "2026-10-24T14:05:00Z"
    payload = created["payload"]
    assert payload["title"].startswith("URGENTE ·")
    assert ALERTA_ROJA_ANGOL["title"] in payload["body"]          # título oficial exacto
    assert "Emitida el 24-10 11:05 hora de Chile continental" in payload["body"]
    assert "BRASA no emite alertas" in payload["body"]
    assert ALERTA_ROJA_ANGOL["url"] in payload["body"]            # el enlace oficial
    assert payload["footer"] == alerts_mod.SENAPRED_FOOTER        # aquí el mensaje SÍ es oficial
    assert "alerta oficial" not in alerts_mod.SENAPRED_FOOTER.split("SENAPRED, ")[0]
    # El urgente no es aplazable: sale aunque sea de noche.
    assert not alerts_mod.aplazable(payload)


def test_alerta_amarilla_queda_en_aviso(tmp_path):
    """(b) «Alerta Amarilla» → «aviso» (aplazable por el silencio nocturno, con topes)."""
    db = _db(tmp_path)
    [created] = asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_AMARILLA_ANGOL], now=NOW))
    assert created["level"] == "aviso"
    assert not created["payload"]["title"].startswith("URGENTE")
    assert alerts_mod.aplazable(created["payload"])


def test_alerta_regional_avisa_a_la_comuna_de_la_region(tmp_path):
    """«…para la Región del Maule» avisa a un lugar de Talca como «aviso»."""
    db = _db(tmp_path, comuna=7101)
    [created] = asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_ATP_MAULE], now=NOW))
    assert created["level"] == "aviso"
    assert "la región del Maule" in created["payload"]["body"]
    assert created["payload"]["senapred"]["scope"] == "region"


def test_la_misma_alerta_en_dos_ciclos_genera_un_solo_aviso(tmp_path):
    """(a) `senapred:<id>` con el UNIQUE(place_id, observation_id): la segunda pasada no repite."""
    db = _db(tmp_path)
    assert len(asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_ROJA_ANGOL], now=NOW))) == 1
    assert asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_ROJA_ANGOL], now=NOW)) == []
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1


def test_lugar_de_otra_comuna_no_recibe_nada(tmp_path):
    """(c) la alerta es de Angol; un lugar de Talca (y no la nombran) no recibe aviso."""
    db = _db(tmp_path, comuna=7101)
    assert asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_ROJA_ANGOL], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_lugar_sin_comuna_conocida_no_recibe_nada(tmp_path):
    db = _db(tmp_path, comuna=None)
    assert asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_ROJA_ANGOL], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_orden_de_evacuacion_es_urgente_aunque_venga_con_amarilla(tmp_path):
    """La orden de evacuación manda sobre la clase: «evacuación» → «urgente»."""
    db = _db(tmp_path)
    [created] = asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_EVAC_ANGOL], now=NOW))
    assert created["level"] == "urgente"


def test_sin_alertas_o_sin_id_no_se_avisa(tmp_path):
    db = _db(tmp_path)
    assert asyncio.run(alerts_mod.evaluate_senapred(db, [], now=NOW)) == []
    sin_id = {**ALERTA_ROJA_ANGOL, "id": None}
    assert asyncio.run(alerts_mod.evaluate_senapred(db, [sin_id], now=NOW)) == []


@pytest.mark.parametrize("titulo,esperado", [
    ("Se declara Alerta Roja para la comuna de Angol por incendio forestal", "urgente"),
    ("Se declara ALERTA ROJA para la Región del Maule por incendio forestal", "urgente"),
    ("Se ordena la evacuación de sectores de la comuna de Angol", "urgente"),
    ("Evacuar sectores rurales de la comuna de Angol por incendio", "urgente"),
    ("Se declara alerta Amarilla para la comuna de Angol por evento meteorológico", "aviso"),
    ("Monitoreo Alerta Temprana Preventiva para la Región del Maule por viento", "aviso"),
    ("Aviso especial de la autoridad para la comuna de Angol", "aviso"),
    ("", "aviso"),
])
def test_nivel_segun_el_titulo_oficial(titulo, esperado):
    """(b) `senapred.nivel`: Roja o evacuación → urgente; el resto → aviso."""
    assert senapred.nivel(titulo) == esperado


def test_un_aviso_senapred_no_silencia_un_foco_real(tmp_path):
    """El aviso SENAPRED guarda lat/lon del centro comunal (como `dmc:`/`daily:`): si contara
    en la deduplicación satelital, una Alerta Roja silenciaría un foco real a <DEDUPE_KM del
    centro durante 12 h (hallazgo geo-reviewer). Queda fuera de `_recent_alerts`."""
    db = _db(tmp_path)
    asyncio.run(alerts_mod.evaluate_senapred(db, [ALERTA_ROJA_ANGOL], now=NOW))
    centro = territory().by_code[9201].center          # (lon, lat)
    foco = {"id": "firms:1", "source": "firms", "lat": centro[1] + 0.01, "lon": centro[0],
            "frp_mw": 20.0, "confidence": "alta",
            "observed_at": "2026-10-24T14:30:00Z"}
    created = asyncio.run(alerts_mod.evaluate(db, [foco], now=NOW))
    assert len(created) == 1 and created[0]["payload"]["observation"]["id"] == "firms:1"


def test_la_alerta_oficial_no_la_frena_el_tope_de_urgentes(tmp_path):
    """Un urgente satelital entregado en las últimas 24 h agota el tope para otro urgente
    satelital («urgente_24h»), pero no para una Alerta Roja / evacuación oficial: las
    alertas de la autoridad no compiten con el freno anti-fatiga."""
    db = _db(tmp_path)
    db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
               "observed_at, created_at, payload, delivered, delivered_at) "
               "VALUES ('p1','sat:previo','urgente',1,0,0,-37.8,-72.79,'2026-10-24T10:00:00Z',"
               "'2026-10-24T10:01:00Z','{}','[\"push\"]','2026-10-24T10:02:00Z')")
    senapred_nuevo = {"id": None, "place_id": "p1", "level": "urgente",
                      "observation_id": "senapred:roja1", "incident_id": None}
    sat_nuevo = {"id": None, "place_id": "p1", "level": "urgente",
                 "observation_id": "sat:nuevo", "incident_id": None}
    assert alerts_mod.caps_exceeded(db, sat_nuevo, NOW) == "urgente_24h"
    assert alerts_mod.caps_exceeded(db, senapred_nuevo, NOW) is None


def test_un_urgente_senapred_no_alimenta_el_tope(tmp_path):
    """Tampoco al revés: el urgente oficial entregado no es un foco y no consume el cupo
    `urgente_24h` de las detecciones reales que vengan después."""
    db = _db(tmp_path)
    db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
               "observed_at, created_at, payload, delivered, delivered_at) "
               "VALUES ('p1','senapred:roja1','urgente',1,0,0,-37.8024,-72.7934,'2026-10-24T10:00:00Z',"
               "'2026-10-24T10:01:00Z','{}','[\"push\"]','2026-10-24T10:02:00Z')")
    sat_nuevo = {"id": None, "place_id": "p1", "level": "urgente",
                 "observation_id": "sat:nuevo", "incident_id": None}
    assert alerts_mod.caps_exceeded(db, sat_nuevo, NOW) is None


def test_ingest_senapred_crea_el_aviso_una_sola_vez(make_client, web):
    """El camino real (fetch → caché `senapred:alertas` → evaluate → deliver) avisa una vez
    por alerta y lugar; la segunda pasada sirve la caché y no descarga ni duplica."""
    senapred._creds_cache.clear()
    items = [{"id": "roja1", "titulo": ALERTA_ROJA_ANGOL["title"], "fechaHora": "2026-10-24T11:05:00-03:00",
              "urlAccess": "roja-angol", "isActive": True, "isDeleted": False}]
    web.add(lambda r: True, _mock_senapred(items))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        db = svc.db
        db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
        db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
                   "VALUES ('p1','s1','Casa','casa',-37.80,-72.79,10,9201,'2026-10-01T00:00:00Z')")
        assert asyncio.run(svc.ingest_senapred()) == 1
        [row] = db.query("SELECT * FROM alerts")
        assert row["observation_id"] == "senapred:roja1" and row["level"] == "urgente"
        # Segunda pasada con el mismo listado: la caché responde sin nueva descarga
        # y el UNIQUE(place_id, observation_id) impide el duplicado.
        assert asyncio.run(svc.ingest_senapred()) == 1
        assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1
        assert len([r for r in web.requests if "appsync" in r.url.host]) == 1


def test_si_senapred_falla_el_ciclo_sigue_sin_avisos(make_client, web):
    """(d) la fuente caída degrada a `[]`: la corrida queda registrada como fallida,
    no hay avisos y `ingest_senapred` devuelve 0 en vez de propagar la excepción."""
    senapred._creds_cache.clear()
    web.add(lambda r: True, lambda r: httpx.Response(503))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        db = svc.db
        db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
        db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
                   "VALUES ('p1','s1','Casa','casa',-37.80,-72.79,10,9201,'2026-10-01T00:00:00Z')")
        assert asyncio.run(svc.ingest_senapred()) == 0
        assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 0
        run = db.one("SELECT ok, product FROM ingest_runs ORDER BY id DESC")
        assert run["ok"] == 0 and run["product"] == "SENAPRED_ALERTAS"
        # La segunda corrida sirve el «[]» cacheado del fallo (300 s de backpressure):
        # tampoco puede fingir una corrida buena — la racha de fallos se conserva.
        assert asyncio.run(svc.ingest_senapred()) == 0
        assert db.one("SELECT ok FROM ingest_runs ORDER BY id DESC")["ok"] == 0
