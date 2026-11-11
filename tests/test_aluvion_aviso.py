"""AGUA-04: el criterio calibrado del aviso de aluvión y su entrega por lugar guardado.

`criterio_aviso` es puro: cicatriz a ≤ 5 km en 365 días, ladera ≥ 8° a paso de 1000 m,
≥ 10 mm en la peor ventana de 3 h e isoterma 0 °C sobre la cota máxima (una isoterma sin
dato se da por cumplida). `evaluate_aluvion` recorre los lugares con `aluvion_alerts`,
filtra primero por cicatriz en la base y pide relieve y señal solo a quienes pasan,
memoizados en la pasada; `aluvion:<fecha local de la ventana>` deduplica y un aviso en
las últimas 36 h frena al siguiente. Ningún texto dice «va a haber un aluvión».

Los números de referencia son los del aluvión de Quebrada Honda (Las Condes, 8-oct-2026,
incendio «Plaza Sur» de CONAF del 29-dic-2025): 12,6 mm/3 h, 9,7° de ladera, isoterma
2.610 m y cota máxima 1.375 m (docs/aluvion-calibracion.md).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx

from backend import alerts, lluvia, services
from backend.db import Database, _migrate_user
from backend.providers import weather
from tests.conftest import json_response
from tests.test_scars import seed_incident

NOW = datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)   # 17:00 en Chile continental

# El aluvión documentado: Quebrada Honda (Las Condes), 8-oct-2026. La ventana 18:00-21:00
# UTC sigue abierta a la hora de la pasada (NOW): una cerrada no gatilla el aviso.
SENAL_QH = {"mm_3h": 12.6, "isoterma_m": 2610.0, "isoterma_alta": True, "intensa": True,
            "ventana": "2026-10-08T18:00", "horas_hasta": 0}
RELIEVE_QH = {"slope_max_deg": 9.7, "elev_max_m": 1375.0}
CICATRIZ_QH = {"ha": 42.0, "ha_satelite": 42.0, "ha_conaf": 0.0, "incendio": None,
               "dias_desde": 283, "fuente": "satelite"}


def test_criterio_aviso_con_los_numeros_de_quebrada_honda_avisa():
    assert lluvia.criterio_aviso(SENAL_QH, RELIEVE_QH, CICATRIZ_QH) is True


def test_criterio_aviso_exige_ladera_de_8_grados():
    relieve = {**RELIEVE_QH, "slope_max_deg": 6.6}
    assert lluvia.criterio_aviso(SENAL_QH, relieve, CICATRIZ_QH) is False
    assert lluvia.criterio_aviso(SENAL_QH, {**RELIEVE_QH, "slope_max_deg": 8.0}, CICATRIZ_QH) is True


def test_criterio_aviso_exige_cicatriz():
    assert lluvia.criterio_aviso(SENAL_QH, RELIEVE_QH, None) is False
    assert lluvia.criterio_aviso(SENAL_QH, RELIEVE_QH, {**CICATRIZ_QH, "ha": 0.0}) is False


def test_criterio_aviso_exige_isoterma_sobre_la_cota():
    senal = {**SENAL_QH, "isoterma_m": 1300.0}
    assert lluvia.criterio_aviso(senal, RELIEVE_QH, CICATRIZ_QH) is False


def test_criterio_aviso_sin_isoterma_avisa_igual():
    """La lluvia es el factor principal: un hueco de isoterma no esconde el aviso."""
    senal = {**SENAL_QH, "isoterma_m": None}
    assert lluvia.criterio_aviso(senal, RELIEVE_QH, CICATRIZ_QH) is True


def test_criterio_aviso_exige_10_mm_en_3_horas():
    assert lluvia.criterio_aviso({**SENAL_QH, "mm_3h": 9.9}, RELIEVE_QH, CICATRIZ_QH) is False
    assert lluvia.criterio_aviso(None, RELIEVE_QH, CICATRIZ_QH) is False
    assert lluvia.criterio_aviso({**SENAL_QH, "mm_3h": None}, RELIEVE_QH, CICATRIZ_QH) is False


def _db(tmp_path, aluvion: int = 1) -> Database:
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at, "
        "aluvion_alerts) VALUES ('p1','s1','Parcela','parcela',-35.42,-71.60,10,7101,'2026-01-01T00:00:00Z',?)",
        (aluvion,),
    )
    return db


def _lookups(senal=SENAL_QH, relieve=RELIEVE_QH):
    calls = {"senal": 0, "relieve": 0}

    async def senal_lookup(_lat, _lon):
        calls["senal"] += 1
        return senal

    async def relieve_lookup(_lat, _lon):
        calls["relieve"] += 1
        return relieve

    return senal_lookup, relieve_lookup, calls


def test_evaluate_aluvion_crea_un_aviso_y_no_repite(tmp_path):
    db = _db(tmp_path)
    seed_incident(db, "inc-1", lat=-35.42, lon=-71.60, days_ago=10)
    senal_lookup, relieve_lookup, _ = _lookups()
    created = asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW))
    assert len(created) == 1 and created[0]["level"] == "aviso"
    payload = created[0]["payload"]
    assert payload["kind"] == "aluvion" and payload["url"] == "/#/mi-zona"
    assert payload["title"] == "Lluvia intensa sobre zona quemada cerca de «Parcela»"
    assert "12.6 mm de lluvia en 3 horas" in payload["body"]
    assert "hora de Chile continental" in payload["body"]
    assert "cauce de las quebradas" in payload["body"] and "ruido" in payload["body"]
    assert payload["footer"] == alerts.OFFICIAL_FOOTER
    assert lluvia.ETIQUETA in payload["body"] and lluvia.SENAPRED in payload["body"]
    al = payload["aluvion"]
    assert al["mm_3h"] == 12.6 and al["isoterma_m"] == 2610.0 and al["ventana"] == "2026-10-08T18:00"
    assert al["slope_max_deg"] == 9.7 and al["scar_ha"] > 0
    row = db.one("SELECT * FROM alerts")
    assert row["observation_id"] == "aluvion:2026-10-08" and row["level"] == "aviso"
    # La misma pasada no duplica (UNIQUE) y tampoco una ventana del día siguiente dentro
    # de las 36 h: un temporal de dos días es un solo aviso.
    assert asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW)) == []
    otra = {**SENAL_QH, "ventana": "2026-10-09T17:00"}
    senal_lookup2, relieve_lookup2, _ = _lookups(senal=otra)
    assert asyncio.run(alerts.evaluate_aluvion(db, senal_lookup2, relieve_lookup2, now=NOW + timedelta(hours=5))) == []
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1


def test_evaluate_aluvion_respeta_el_interruptor(tmp_path):
    db = _db(tmp_path, aluvion=0)
    seed_incident(db, "inc-1", lat=-35.42, lon=-71.60, days_ago=10)
    senal_lookup, relieve_lookup, calls = _lookups()
    assert asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW)) == []
    assert calls == {"senal": 0, "relieve": 0}
    assert db.one("SELECT id FROM alerts") is None


def test_evaluate_aluvion_sin_cicatriz_no_pide_nada(tmp_path):
    """Sin suelo quemado cerca el lugar no paga relieve ni pronóstico."""
    db = _db(tmp_path)
    senal_lookup, relieve_lookup, calls = _lookups()
    assert asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW)) == []
    assert calls == {"senal": 0, "relieve": 0}
    assert db.one("SELECT id FROM alerts") is None


def test_evaluate_aluvion_sin_ladera_o_lluvia_no_avisa(tmp_path):
    db = _db(tmp_path)
    seed_incident(db, "inc-1", lat=-35.42, lon=-71.60, days_ago=10)
    senal_lookup, relieve_lookup, _ = _lookups(relieve={**RELIEVE_QH, "slope_max_deg": 6.6})
    assert asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW)) == []
    senal_lookup, relieve_lookup, _ = _lookups(senal={**SENAL_QH, "mm_3h": 4.0})
    assert asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_la_migracion_deja_aluvion_alerts_encendido_en_los_lugares_existentes(tmp_path):
    """Un lugar guardado antes de la columna queda con el aviso encendido (DEFAULT 1)."""
    db = _db(tmp_path)
    with db.connect() as conn:
        conn.execute("ALTER TABLE places DROP COLUMN aluvion_alerts")
        _migrate_user(conn)
    assert db.one("SELECT aluvion_alerts FROM places WHERE id = 'p1'")["aluvion_alerts"] == 1


def _web_lluvia(web):
    """Open-Meteo simulado: pronóstico con la ventana de Quebrada Honda y un DEM de ladera."""
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/elevation"):
            # Grilla 3×3 a 1000 m: 342→171→0 m de norte a sur ≈ 9,7°; cota máxima 342 m.
            return json_response({"elevation": [342.0] * 3 + [171.0] * 3 + [0.0] * 3})
        return json_response({"hourly": {
            # El pronóstico llega desde la hora siguiente a la consulta, como Open-Meteo.
            "time": [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(1, 9)],
            "precipitation": [0.0, 4.0, 5.0, 3.6, 1.0, 0.0, 0.0, 0.0],
            "freezing_level_height": [2610.0] * 8,
        }})

    web.add(lambda r: "open-meteo" in r.url.host, handler)


def test_el_endpoint_devuelve_cicatriz_relieve_y_aviso(make_client, web):
    lat, lon = -35.42, -71.60
    _web_lluvia(web)
    with make_client() as client:
        seed_incident(client.app.state.services.db, "cerca", lat=lat, lon=lon, days_ago=10)
        body = client.get(f"/api/climate/lluvia?lat={lat}&lon={lon}").json()
    terreno = body["terreno"]
    assert terreno["aviso"] is True and terreno["nivel"] == "alto"
    assert terreno["cicatriz"]["ha"] > 0 and terreno["cicatriz"]["fuente"] == "satelite"
    assert terreno["relieve"]["slope_max_deg"] >= 8.0 and terreno["relieve"]["elev_max_m"] == 342.0
    assert "moderado" not in terreno["explicacion"]
    assert "BRASA avisa a los lugares guardados" in body["note"]


def test_el_endpoint_sin_criterio_no_marca_aviso(make_client, web):
    """Sin ladera suficiente (DEM plano) el aviso queda apagado aunque llueva sobre cicatriz."""
    lat, lon = -35.42, -71.60
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/elevation"):
            return json_response({"elevation": [500.0] * 9})
        return json_response({"hourly": {
            "time": [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(1, 9)],
            "precipitation": [0.0, 4.0, 5.0, 3.6, 1.0, 0.0, 0.0, 0.0],
            "freezing_level_height": [2610.0] * 8,
        }})

    web.add(lambda r: "open-meteo" in r.url.host, handler)
    with make_client() as client:
        seed_incident(client.app.state.services.db, "cerca", lat=lat, lon=lon, days_ago=10)
        body = client.get(f"/api/climate/lluvia?lat={lat}&lon={lon}").json()
    assert body["terreno"]["aviso"] is False
    assert body["terreno"]["cicatriz"]["ha"] > 0 and body["terreno"]["relieve"]["slope_max_deg"] < 8.0


def test_el_texto_del_aviso_nunca_dice_va_a_haber(tmp_path):
    """Ni el aviso ni la explicación del terreno afirman que un aluvión va a ocurrir."""
    db = _db(tmp_path)
    seed_incident(db, "inc-1", lat=-35.42, lon=-71.60, days_ago=10)
    senal_lookup, relieve_lookup, _ = _lookups()
    created = asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW))
    assert created
    payload = created[0]["payload"]
    for texto in (payload["title"], payload["body"], payload["footer"]):
        assert "va a haber" not in texto.lower()
    terreno = lluvia.evaluar_terreno(SENAL_QH, None, CICATRIZ_QH["ha"], relieve=RELIEVE_QH, cicatriz=CICATRIZ_QH)
    assert terreno["aviso"] is True and terreno["nivel"] == "alto"
    assert "va a haber" not in terreno["explicacion"].lower()
    assert "moderado" not in terreno["explicacion"]


def test_el_aviso_nombra_el_incendio_de_conaf(tmp_path):
    """Con cicatriz informada por CONAF el cuerpo trae el incendio y su fecha."""
    db = _db(tmp_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, area_ha, "
        "first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("f1", "Plaza Sur", "controlado", "Controlado", "2025-12-29T00:00:00Z", -35.42, -71.60, 900.0, now, now),
    )
    senal_lookup, relieve_lookup, _ = _lookups()
    created = asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW))
    assert len(created) == 1
    payload = created[0]["payload"]
    assert "«Plaza Sur»" in payload["body"] and "29-12-2025" in payload["body"] and "CONAF" in payload["body"]
    assert payload["aluvion"]["fuente_url"] == "https://github.com/deigeprif/public"
    # La cifra oficial se puede verificar: el enlace viaja en el cuerpo, que es lo que
    # entregan Telegram y la bandeja (QA-57).
    assert "https://github.com/deigeprif/public" in payload["body"]
    assert payload["aluvion"]["fuente"] == "conaf"
    # La entrega no la frena ni el tope anti-fatiga ni es «urgente»: pasa por el silencio
    # nocturno como cualquier «aviso».
    assert alerts.aplazable(payload)
    assert json.dumps(payload, ensure_ascii=False)


def test_evaluate_aluvion_no_avisa_con_la_ventana_ya_cerrada(tmp_path):
    """Una señal cacheada cuya ventana de 3 h ya terminó no gatilla el aviso."""
    db = _db(tmp_path)
    seed_incident(db, "inc-1", lat=-35.42, lon=-71.60, days_ago=10)
    # La ventana 15:00-18:00 UTC cerró dos horas antes de la pasada (NOW = 20:00).
    senal_vencida = {**SENAL_QH, "ventana": "2026-10-08T15:00"}
    senal_lookup, relieve_lookup, _ = _lookups(senal=senal_vencida)
    assert asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None
    # Sin marca de ventana tampoco: la vigencia solo se declara cuando se puede leer.
    senal_lookup, relieve_lookup, _ = _lookups(senal={**SENAL_QH, "ventana": None})
    assert asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW)) == []


def test_el_aviso_vence_con_el_fin_de_la_ventana(tmp_path):
    """`expires` es el cierre de la ventana de 3 h: el aplazo nocturno no entrega un
    pronóstico que ya pasó (`vencida` lo descarta al entregar) y el registro queda."""
    db = _db(tmp_path)
    seed_incident(db, "inc-1", lat=-35.42, lon=-71.60, days_ago=10)
    senal_lookup, relieve_lookup, _ = _lookups()
    created = asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW))
    payload = created[0]["payload"]
    assert payload["expires"] == "2026-10-08T21:00:00Z"   # ventana 18:00 + 3 h
    assert alerts.vencida(payload, datetime(2026, 10, 8, 22, 0, tzinfo=timezone.utc)) is True
    assert alerts.vencida(payload, NOW) is False


def test_el_aviso_satelital_cita_firms_en_el_cuerpo(tmp_path):
    """La cicatriz satelital también lleva su fuente con enlace en el texto entregado."""
    db = _db(tmp_path)
    seed_incident(db, "inc-1", lat=-35.42, lon=-71.60, days_ago=10)
    senal_lookup, relieve_lookup, _ = _lookups()
    created = asyncio.run(alerts.evaluate_aluvion(db, senal_lookup, relieve_lookup, now=NOW))
    payload = created[0]["payload"]
    assert alerts.FIRMS_URL in payload["body"] and "NASA FIRMS" in payload["body"]
    assert payload["aluvion"]["fuente"] == "satelite" and payload["aluvion"]["fuente_url"] == alerts.FIRMS_URL


def _svc_con_lugar(svc):
    """Un lugar con `aluvion_alerts` y cicatriz satelital en la base del servicio."""
    db = svc.db
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at, "
        "aluvion_alerts) VALUES ('p1','s1','Parcela','parcela',-35.42,-71.60,10,7101,'2026-01-01T00:00:00Z',1)"
    )
    seed_incident(db, "inc-1", lat=-35.42, lon=-71.60, days_ago=10)


def test_la_pasada_anota_su_gasto_en_el_cupo_del_dia(make_client, monkeypatch):
    """Cada celda y grilla nuevas se descuentan en `open_meteo_day` (Devin Review #840)."""
    with make_client() as client:
        svc = client.app.state.services
        _svc_con_lugar(svc)

        async def fake_senal_celda(svc_, lat, lon):
            weather._count("https://api.open-meteo.com/v1/forecast", 1)
            return {"senal": dict(SENAL_QH), "computed_at": "2026-10-08T20:00:00Z"}

        async def fake_relieve(db_, client_, lat, lon):
            weather._count("https://api.open-meteo.com/v1/elevation", 9)
            return dict(RELIEVE_QH)

        monkeypatch.setattr("backend.routes.climate.senal_celda", fake_senal_celda)
        monkeypatch.setattr("backend.providers.elevation.relieve", fake_relieve)
        assert asyncio.run(svc.aluvion_pass(NOW)) == 1
        day = json.loads(svc.db.kv_get("open_meteo_day"))
        assert day["tasks"]["aluvion"]["today"] == 10 and day["total"] == 10


def test_la_pasada_cede_cuando_el_cupo_del_dia_esta_comprometido(make_client, monkeypatch):
    """Sin saldo tras reserva y plan, los lookups no se piden y no se crea el aviso."""
    with make_client() as client:
        svc = client.app.state.services
        _svc_con_lugar(svc)
        plan = svc._om_plan_pending()
        today = datetime.now(services.risk_mod.CHILE_TZ).date().isoformat()
        spent = weather.DAILY_LOCATIONS_CAP - plan - services.OPEN_METEO_RESERVE
        svc.db.kv_set("open_meteo_day", json.dumps({"date": today, "total": spent, "tasks": {}}))
        llamadas = []

        async def fake_senal_celda(svc_, lat, lon):
            llamadas.append("senal")
            return {"senal": dict(SENAL_QH), "computed_at": "2026-10-08T20:00:00Z"}

        async def fake_relieve(db_, client_, lat, lon):
            llamadas.append("relieve")
            return dict(RELIEVE_QH)

        monkeypatch.setattr("backend.routes.climate.senal_celda", fake_senal_celda)
        monkeypatch.setattr("backend.providers.elevation.relieve", fake_relieve)
        assert asyncio.run(svc.aluvion_pass(NOW)) == 0
        assert llamadas == []
        assert svc.db.one("SELECT id FROM alerts") is None
