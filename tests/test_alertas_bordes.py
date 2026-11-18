"""QA-COB: bordes de `backend/alerts.py` — datos ilegibles, el silencio con
cambio de horario, los topes anti-fatiga y la deduplicación de seguimientos.

Aquí un error despierta a una persona a las 3 de la mañana, le repite un aviso
o la deja sorda frente al cierre de un incendio real: cada prueba nombra la
regla de negocio que protege en su docstring.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend import alerts
# `en_silencio` se importa por nombre porque el fixture de conftest parchea el
# atributo del módulo; la referencia directa conserva la función real (igual que
# en test_alert_quiet_hours.py).
from backend.alerts import en_silencio
from backend import incidents as incidents_mod
from backend.db import Database
from backend.geo import territory

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "brasa.db")
    d.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    return d


def _place(db: Database, pid: str = "p1", sid: str = "s1", **over) -> dict:
    row = {"id": pid, "name": "Casa", "lat": -35.0, "lon": -71.0, "radius_km": 20.0,
           "comuna_code": 7107, "older_adult": 0, "smoke_alerts": 0} | over
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, "
        "created_at, older_adult, smoke_alerts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (row["id"], sid, row["name"], "casa", row["lat"], row["lon"], row["radius_km"],
         row["comuna_code"], "2026-01-01T00:00:00Z", row["older_adult"], row["smoke_alerts"]))
    return row


def _obs(db: Database, oid: str, observed: datetime, lat=-35.41, lon=-71.97) -> dict:
    row = {"id": oid, "source": "firms", "sensor": "VIIRS", "satellite": "N20", "resolution_m": 375,
           "lat": lat, "lon": lon, "observed_at": stamp(observed), "frp_mw": 20.0,
           "confidence": "alta", "comuna_code": 7107}
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (oid, "firms", "VIIRS", "N20", 375, lat, lon, stamp(observed), 20.0, "alta", 7107,
         stamp(NOW)))
    return row


def _incident(db: Database, *obs_ids: str, at: datetime | None = None) -> dict:
    at = at or NOW - timedelta(hours=2)
    rows = [_obs(db, oid, at + timedelta(minutes=30 * i)) for i, oid in enumerate(obs_ids)]
    [inc] = incidents_mod.update(db, rows, at)
    return inc


def _fire(db: Database, fid: str = "7", status: str = "confirmado", name: str = "El Belloto",
          started=None) -> None:
    started = stamp(started or NOW - timedelta(hours=4))
    raw = {"confirmado": "En combate", "controlado": "Controlado", "extinguido": "Extinguido"}[status]
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, "
        "region, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fid, name, status, raw, started, -35.41, -71.97, "Pencahue", "Maule", started, started))


def _follow(db: Database, sid: str = "s1", incident_id=None, official_ref=None, fire_status=None,
            created=None, last_alert_at=None) -> int:
    return db.insert(
        "INSERT INTO incident_follows(subscriber_id, incident_id, official_ref, fire_status, "
        "created_at, last_alert_at) VALUES (?,?,?,?,?,?)",
        (sid, incident_id, official_ref, fire_status, stamp(created or NOW - timedelta(hours=1)),
         stamp(last_alert_at) if last_alert_at else None))


def _run_follows(db: Database, now: datetime | None = None):
    return asyncio.run(alerts.evaluate_follows(db, now or NOW))


# --- ALR-19: el silencio es de Chile, con su cambio de horario ---


def test_silencio_cruza_el_cambio_de_reloj_de_chile():
    """ALR-19: el silencio es 23:00-07:00 en America/Santiago, no un offset fijo.
    La misma hora UTC (02:30) es 23:30 en verano (UTC-3, silencio) y 22:30 en
    invierno (UTC-4, fuera): con «UTC-3 siempre» el borde correría una hora
    medio año y los avisos de las 22:xx de invierno se aplazarían sin razón."""
    verano = datetime(2026, 1, 15, 2, 30, tzinfo=timezone.utc)    # 23:30 Chile (UTC-3)
    invierno = datetime(2026, 7, 15, 2, 30, tzinfo=timezone.utc)  # 22:30 Chile (UTC-4)
    assert en_silencio(verano) is True
    assert en_silencio(invierno) is False
    # Los bordes exactos, en las dos estaciones.
    assert en_silencio(datetime(2026, 1, 15, 1, 59, tzinfo=timezone.utc)) is False   # 22:59 UTC-3
    assert en_silencio(datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)) is True     # 23:00 UTC-4
    assert en_silencio(datetime(2026, 7, 15, 10, 59, tzinfo=timezone.utc)) is True   # 06:59 UTC-4
    assert en_silencio(datetime(2026, 7, 15, 11, 0, tzinfo=timezone.utc)) is False   # 07:00 UTC-4


# --- datos ilegibles: ante la duda se entrega / se omite, nunca se rompe ---


def test_vencida_con_expires_ilegible_no_bloquea():
    """Un `expires` que no se lee trata el aviso como vigente: la duda nunca
    silencia una pendiente de entrega (mismo criterio que `_cap_time`)."""
    assert alerts.vencida({"expires": "basura"}, NOW) is False
    assert alerts.vencida({}, NOW) is False


def test_vencida_con_expires_no_textual_no_reventa():
    """Un `expires` no textual truthy se trata como ilegible y no rompe la cola de pendientes."""
    assert alerts.vencida({"expires": 123}, NOW) is False


def test_is_recent_exige_marca_legible():
    """MAX_AGE_H solo se evalúa con una hora válida: una detección sin
    `observed_at` legible es vieja para siempre y nunca despierta a nadie."""
    assert alerts.is_recent({"observed_at": "basura"}, NOW) is False
    assert alerts.is_recent({}, NOW) is False
    assert alerts.is_recent({"observed_at": stamp(NOW - timedelta(hours=5, minutes=59))}, NOW) is True
    assert alerts.is_recent({"observed_at": stamp(NOW - timedelta(hours=6, minutes=1))}, NOW) is False


def test_escalation_due_exige_created_at_legible():
    """El reenvío de un urgente mide la espera desde `created_at`: sin esa hora
    no se puede afirmar que pasaron los ESCALATE_AFTER_MIN, así que no reenvía."""
    fila = {"level": "urgente", "delivered_at": "x", "reminded_at": None, "created_at": "basura"}
    assert alerts.escalation_due(fila, False, NOW) is False


def test_region_en_palabras_no_duplica_la_palabra():
    """«Región de Los Lagos» ya viene escrita: el texto la respeta y no arma
    «la región de Región de Los Lagos»."""
    assert alerts._region_en_palabras("Región de Los Lagos") == "Región de Los Lagos"
    assert alerts._region_en_palabras("Maule") == "región del Maule"
    assert alerts._region_en_palabras("Valparaíso") == "región de Valparaíso"
    assert alerts._region_en_palabras("Metropolitana") == "región Metropolitana"


def test_donde_comuna_con_nombre_ambiguo_resuelve_por_el_punto():
    """«Maule» nombra 30 comunas: el texto no adivina una — la comuna sale del
    punto del foco, que sí está en el territorio."""
    place = {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "comuna_code": None}
    donde = alerts._donde_comuna(place, comuna="Maule", lat=-35.41, lon=-71.97)
    assert donde == "en la comuna de Pencahue (región del Maule)"


# --- piezas del mensaje: persona mayor, viento y escenario ---


def test_compose_approach_suma_viento_escenario_y_persona_mayor():
    """ALR-43: el aviso de acercamiento lleva la línea de viento cuando sopla
    hacia el lugar, el rumbo del escenario estimado (sin cifras de avance) y la
    nota para quien cuida a una persona mayor."""
    inc = {"id": "i1", "status": "posible", "n_obs": 4,
           "first_seen_at": stamp(NOW - timedelta(hours=3)), "last_seen_at": stamp(NOW - timedelta(minutes=40)),
           "sensors": "VIIRS,MODIS", "lat": -35.3, "lon": -71.3}
    obs = {"id": "o1", "lat": -35.2, "lon": -71.2, "observed_at": stamp(NOW - timedelta(minutes=40)),
           "source": "firms", "sensor": "VIIRS", "confidence": "alta", "frp_mw": 20.0}
    payload = alerts.compose_approach(
        {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "older_adult": 1},
        obs, 8.0, 14.0, 200, True, "aviso", {"speed": 30, "direction": 20},
        inc, spread={"direction_deg": 270})
    body = payload["body"]
    assert "ahora a 8.0 km (antes 14.0 km)" in body
    assert "viento sopla desde esa dirección" in body
    assert "empujaría hacia el oeste" in body and "km/h hacia" not in body
    assert "salgan temprano" in body
    assert payload["kind"] == "acercamiento" and payload["observation"]["id"] == "i1:acerca"


def test_compose_official_recuerda_a_la_persona_mayor():
    """ALR-02: el aviso oficial recuerda confirmar con la persona mayor o quien
    necesita ayuda para salir, en cualquier nivel."""
    fire = {"id": "7", "name": "El Belloto", "status": "confirmado", "status_raw": "En combate",
            "lat": -35.41, "lon": -71.97, "started_at": stamp(NOW - timedelta(hours=4)),
            "comuna": "Pencahue", "region": "Maule"}
    payload = alerts.compose_official(
        {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "older_adult": 1},
        fire, 4.4, 180, "aviso")
    assert "persona mayor o alguien que necesita ayuda" in payload["body"]


def test_compose_report_recuerda_a_la_persona_mayor():
    """ALR-03: el aviso vecinal también lleva la nota de la persona mayor."""
    report = {"id": "r1", "kind": "humo", "lat": -35.02, "lon": -71.02,
              "created_at": stamp(NOW - timedelta(minutes=10))}
    payload = alerts.compose_report(
        {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "older_adult": 1},
        report, 2.4, 60)
    assert "persona mayor o alguien que necesita ayuda" in payload["body"]


def test_evaluate_report_sin_created_at_legible_no_avisa(db):
    """Un reporte verificado sin fecha no puede medir su ventana de vigencia:
    se omite — un «un vecino informó» sin hora podría avisar algo ya pasado."""
    _place(db)
    base = {"status": "verificado", "kind": "humo", "lat": -35.0, "lon": -71.0, "id": "r1"}
    assert alerts.evaluate_report(db, base | {"created_at": "basura"}, NOW) == []
    assert alerts.evaluate_report(db, base, NOW) == []  # sin la llave: KeyError también frena


def test_cierre_conaf_de_lugar_borrado_se_omite(db):
    """ALR-02: si el lugar se borró entre el aviso original y el cierre oficial,
    el cierre no reviva la fila ni rompe la pasada."""
    place = _place(db)
    db.execute(
        "INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, "
        "lat, lon, observed_at, created_at, payload) VALUES (?,'conaf:7','aviso',1,0,0,-35,-71,?,?,?)",
        (place["id"], stamp(NOW), stamp(NOW), "{}"))
    # El borrado en producción quita la alerta por ON DELETE CASCADE; para dejar
    # la fila huérfana que la rama contempla, el DELETE va con la FK apagada.
    with db.connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM places WHERE id = ?", (place["id"],))
        conn.execute("PRAGMA foreign_keys = ON")
    fire = {"id": "7", "status": "controlado", "lat": -35.4, "lon": -71.9}
    assert asyncio.run(alerts.evaluate_status_change(db, [fire], NOW)) == []


# --- seguimientos de incendio (ALR-44) ---


def test_compose_follow_estado_confirmado_dice_que_volvio():
    """Un «confirmado» que llega tras un cierre se anuncia como reactivación,
    no como cambio genérico: el texto que la persona lee existe."""
    fire = {"id": "7", "name": "El Belloto", "status": "confirmado", "status_raw": "En combate",
            "lat": -35.41, "lon": -71.97, "started_at": stamp(NOW - timedelta(days=1))}
    payload = alerts.compose_follow_estado(fire, None)
    assert payload["observation"]["id"] == "conaf:7:estado:confirmado"
    assert "volvió a estar activo" in payload["body"]


def test_caps_exceeded_follow_respeta_topes_apagados(db, monkeypatch):
    """AVISO_TOPES=0 apaga el freno anti-fatiga del seguimiento igual que el de
    los avisos por lugar (INV-09): devuelve None sin mirar el conteo."""
    monkeypatch.setenv("AVISO_TOPES", "0")
    nuevo = {"id": None, "subscriber_id": "s1", "observation_id": "inc:i1:calor:o1"}
    assert alerts.caps_exceeded_follow(db, nuevo, NOW) is None


def test_seguimiento_duplicado_se_funde_en_el_mas_antiguo(db):
    """ALR-44: dos filas del mismo dispositivo convergen al mismo fuego (una
    seguía solo la ficha y la otra ya tenía la pareja completa). El UPDATE OR
    IGNORE absorbe el choque del UNIQUE: queda la más antigua con los avisos y
    el tope heredados, y la borrada no se procesa una segunda vez."""
    inc = _incident(db, "o1")
    viejo = _follow(db, incident_id=inc["id"], created=NOW - timedelta(hours=5))
    nuevo = _follow(db, incident_id=inc["id"], official_ref="7", created=NOW - timedelta(hours=2),
                    last_alert_at=NOW - timedelta(hours=1))
    _fire(db, "7", "confirmado")
    db.execute("UPDATE incidents SET official_ref = '7' WHERE id = ?", (inc["id"],))
    db.execute(
        "INSERT INTO follow_alerts(follow_id, observation_id, level, observed_at, created_at, payload) "
        "VALUES (?,?,?,?,?,?)", (nuevo, "inc:x:calor:o9", "aviso", stamp(NOW), stamp(NOW), "{}"))
    _run_follows(db)
    [seg] = db.query("SELECT * FROM incident_follows WHERE subscriber_id = 's1'")
    assert seg["id"] == viejo and seg["official_ref"] == "7"
    assert seg["last_alert_at"] is not None  # el tope del más nuevo se hereda, no se pierde
    assert db.one("SELECT follow_id FROM follow_alerts")["follow_id"] == viejo


def test_seguimiento_conflicto_sin_pareja_se_omite_sin_reventar(db, monkeypatch):
    """Si el UPDATE OR IGNORE frena por una causa distinta del choque de pareja
    (no hay fila con la pareja canónica), el ciclo omite y sigue: una fila rara
    no puede tumbar la pasada de todos."""
    inc = _incident(db, "o1")
    _follow(db, incident_id=inc["id"])
    _fire(db, "7", "confirmado")
    db.execute("UPDATE incidents SET official_ref = '7' WHERE id = ?", (inc["id"],))
    original = db.execute

    def frenado(sql, params=()):
        if sql.startswith("UPDATE OR IGNORE incident_follows"):
            return 0
        return original(sql, params)

    monkeypatch.setattr(db, "execute", frenado)
    _run_follows(db)
    assert db.one("SELECT id FROM incident_follows WHERE subscriber_id = 's1'")


def test_seguimiento_huerfano_sin_incidente_ni_ficha_cae(db):
    """Un seguimiento cuya ref CONAF ya no existe (sin incidente ni ficha) se
    borra solo: no tiene nada que avisar y contarlo inflaría la lista."""
    fid = _follow(db, official_ref="no-existe")
    _run_follows(db)
    assert db.one("SELECT id FROM incident_follows WHERE id = ?", (fid,)) is None


# --- DMC y humo: borde de vigencia y deduplicación ---


def test_compose_dmc_sin_inicio_dice_solo_la_vigencia():
    """ALR-14: un aviso CAP con `expires` y sin `onset` se anuncia «Vigente
    hasta» — no promete un inicio que la fuente no dio."""
    place = {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "comuna_code": 7107}
    alerta = {"id": "cap-1", "kind": "viento", "headline": "Vientos fuertes",
              "expires": stamp(NOW + timedelta(hours=6)), "web": "https://example.test/aviso"}
    payload = alerts.compose_dmc(place, alerta, NOW)
    assert "Vigente hasta el" in payload["body"] and "Rige" not in payload["body"]


def test_cap_time_ilegible_o_ausente_se_trata_como_vigente():
    """Un `expires`/`onset` ilegible o ausente no vence el aviso CAP: ante la
    duda rige (el mismo criterio que `vencida`)."""
    place = {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "comuna_code": 7107}
    for mal in (None, "", "basura"):
        payload = alerts.compose_dmc(place, {"id": "cap-1", "kind": "viento",
                                             "headline": "x", "expires": mal}, NOW)
        assert "Vigente" not in payload["body"] and "Rige" not in payload["body"]


def test_compose_dmc_cicatriz_sin_inicio_dice_solo_la_vigencia():
    """AGUA-07: el aviso de lluvia sobre suelo quemado también arma «Vigente
    hasta» cuando la fuente no da `onset`."""
    place = {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "comuna_code": 7107}
    comuna = territory().by_code[7107]
    alerta = {"id": "cap-2", "kind": "lluvia", "headline": "Lluvia intensa",
              "expires": stamp(NOW + timedelta(hours=6))}
    payload = alerts.compose_dmc_scar(place, alerta, comuna, NOW)
    assert "Vigente hasta el" in payload["body"] and "Rige" not in payload["body"]


def test_evaluate_dmc_ignora_filas_sin_id_y_vencidas(db):
    """ALR-14: una fila sin `id` de CAP no avisa (sin clave de deduplicación no
    hay forma de no repetirla), y un aviso vencido no despierta a nadie."""
    _place(db)
    sin_id = {"kind": "viento", "comunas": "[7107]", "expires": stamp(NOW + timedelta(hours=6))}
    vencido = {"id": "cap-viejo", "kind": "viento", "comunas": "[7107]",
               "expires": stamp(NOW - timedelta(hours=1))}
    vigente = {"id": "cap-ok", "kind": "viento", "comunas": "[7107]", "expires": "basura"}
    created = asyncio.run(alerts.evaluate_dmc(db, [sin_id, vencido, vigente], NOW))
    assert [a["payload"]["observation"]["id"] for a in created] == ["dmc:cap-ok"]


def test_evaluate_smoke_omite_comuna_desconocida(db):
    """AGUA-207: un `comuna_code` que no está en el territorio no consulta el
    aire ni avisa — el punto no tiene comuna que cruzar."""
    _place(db, comuna_code=999999, smoke_alerts=1)
    llamadas = []

    async def aire(comuna):
        llamadas.append(comuna.code)
        return {"pm25_tomorrow_max": 90.0}

    assert asyncio.run(alerts.evaluate_smoke(db, aire, NOW)) == []
    assert llamadas == []


def test_evaluate_smoke_borde_de_norma_y_una_vez_al_dia(db):
    """AGUA-207: la norma chilena de MP2,5 en 24 h es 50 µg/m³ — justo en el
    borde no avisa, sobre el borde sí, y una sola vez al día por lugar."""
    _place(db, smoke_alerts=1)

    async def sobre(comuna):
        return {"pm25_tomorrow_max": alerts.PM25_NORMA_24H_UGM3 + 0.1}

    created = asyncio.run(alerts.evaluate_smoke(db, sobre, NOW))
    assert len(created) == 1
    assert created[0]["payload"]["observation"]["id"].startswith("humo:")
    assert asyncio.run(alerts.evaluate_smoke(db, sobre, NOW)) == []  # dedup por día

    async def justo(comuna):
        return {"pm25_tomorrow_max": alerts.PM25_NORMA_24H_UGM3}

    async def sin_dato(comuna):
        return {"pm25_tomorrow_max": None}

    otro_dia = NOW + timedelta(days=1)
    assert asyncio.run(alerts.evaluate_smoke(db, justo, otro_dia)) == []
    assert asyncio.run(alerts.evaluate_smoke(db, sin_dato, otro_dia)) == []


# --- aluvión y SENAPRED: fechas duras y persona mayor ---


def test_compose_aluvion_tolera_ventana_e_inicio_ilegibles():
    """AGUA-04: una ventana o fecha de incendio que no se lee sale sin esa
    cifra — el aviso llega igual, nunca con «None» ni roto."""
    place = {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "older_adult": 1}
    dato = {"senal": {"mm_3h": 14.0, "ventana": "basura", "isoterma_m": 2800.0},
            "relieve": {"slope_max_deg": 15.0},
            "cicatriz": {"fuente": "conaf", "ha": 1200.0,
                         "incendio": {"nombre": "El Manzano", "inicio": "también basura", "ha": 1200}},
            "stamp": stamp(NOW)}
    payload = alerts.compose_aluvion(place, dato)
    body = payload["body"]
    assert "incendio «El Manzano»" in body and "None" not in body
    frag = body.split("El Manzano", 1)[1].split("informado por CONAF")[0]
    assert "del" not in frag  # sin fecha legible no se inventa una
    assert "persona mayor" in body
    assert payload["expires"] is None  # sin ventana legible no hay fin que medir


def test_compose_aluvion_inicio_naive_se_lee_como_utc():
    """La fecha del incendio CONAF puede llegar sin zona: se lee como UTC, nunca
    como la hora del servidor, y sale en hora de Chile."""
    place = {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0}
    dato = {"senal": {"mm_3h": 14.0, "ventana": None, "isoterma_m": None},
            "relieve": {"slope_max_deg": 15.0},
            "cicatriz": {"fuente": "conaf", "ha": 1200.0,
                         "incendio": {"nombre": "El Manzano", "inicio": "2025-12-29T03:00:00", "ha": 1200}},
            "stamp": stamp(NOW)}
    assert "del 29-12-2025" in alerts.compose_aluvion(place, dato)["body"]


def test_compose_senapred_recuerda_a_la_persona_mayor():
    """ALR-42: la alerta oficial de SENAPRED también recuerda confirmar con la
    persona mayor del lugar."""
    comuna = territory().by_code[7107]
    alerta = {"id": "a1", "title": "Alerta Roja por incendio", "scope": "comuna",
              "issued_at": stamp(NOW), "url": "https://example.test/alerta"}
    payload = alerts.compose_senapred(
        {"id": "p1", "name": "Casa", "lat": -35.0, "lon": -71.0, "older_adult": 1},
        alerta, comuna, NOW)
    assert "persona mayor" in payload["body"]
    assert payload["kind"] == "senapred" and payload["level"] == "urgente"
