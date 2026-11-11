"""QA-COB: transiciones y bordes de `backend/incidents.py`.

La agrupación decide qué es un incendio y qué no: un error aquí silencia un
fuego real (fuente fija mal aplicada) o grita por un reflejo (GOES solo). Cada
prueba nombra la regla que protege en su docstring.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend import incidents as incidents_mod
from backend.db import Database

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
KM_LAT = 1 / 111  # ~1 km en latitud
PUNTO = (-35.41, -71.97)  # Pencahue, Maule
ANTUCO = (-37.406, -71.349)  # cráter de persistent_hotspots.json, radio 3 km


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "brasa.db")


def _obs(db: Database, oid: str, observed: datetime, lat: float = PUNTO[0], lon: float = PUNTO[1],
         sensor: str = "VIIRS", satellite: str = "N20", resolution_m: int = 375,
         confidence: str = "alta") -> dict:
    row = {"id": oid, "source": "firms", "sensor": sensor, "satellite": satellite,
           "resolution_m": resolution_m, "lat": lat, "lon": lon, "observed_at": stamp(observed),
           "frp_mw": 20.0, "confidence": confidence, "comuna_code": 7107}
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (oid, "firms", sensor, satellite, resolution_m, lat, lon, stamp(observed), 20.0, confidence,
         7107, stamp(NOW)))
    return row


def _fire(db: Database, fid: str, status: str = "confirmado", lat: float = PUNTO[0],
          lon: float = PUNTO[1], started=None, extinguished_at=None) -> dict:
    started = stamp(started or NOW - timedelta(hours=4))
    raw = {"confirmado": "En combate", "controlado": "Controlado", "extinguido": "Extinguido"}[status]
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, "
        "region, extinguished_at, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (fid, "El Belloto", status, raw, started, lat, lon, "Pencahue", "Maule", extinguished_at,
         started, started))
    return {"id": fid, "name": "El Belloto", "status": status, "status_raw": raw,
            "lat": lat, "lon": lon, "started_at": started, "extinguished_at": extinguished_at}


def _goes(db: Database, oid: str, observed: datetime) -> dict:
    return _obs(db, oid, observed, sensor="ABI", satellite="GOES-19", resolution_m=2000)


# --- familias y fuentes fijas ---


def test_familia_satelital_desconocida_cuenta_como_propia():
    """Un sensor fuera del catálogo es su propia familia — nunca confirma a
    otro ni rompe la cuenta multi-sensor."""
    assert incidents_mod.satellite_family(None) == "?"
    assert incidents_mod.satellite_family("") == "?"
    assert incidents_mod.satellite_family("SAOCOM") == "SAOCOM"
    assert incidents_mod.satellite_family(" goes ") == "GOES"


def test_fuentes_fijas_con_archivo_ausente_o_roto_no_tapan_nada(monkeypatch, tmp_path):
    """Si `persistent_hotspots.json` falta, está roto o no trae «sources», la
    regla deja de silenciar: ante la duda se avisa (mejor ruido que apagar un
    incendio real)."""
    incidents_mod.known_fixed_sources.cache_clear()
    monkeypatch.setattr(incidents_mod, "ROOT", tmp_path)
    assert incidents_mod.known_fixed_sources() == []
    (tmp_path / "web" / "data").mkdir(parents=True)
    roto = tmp_path / "web" / "data" / "persistent_hotspots.json"
    roto.write_text("{roto", encoding="utf-8")
    incidents_mod.known_fixed_sources.cache_clear()
    assert incidents_mod.known_fixed_sources() == []
    roto.write_text("{}", encoding="utf-8")
    incidents_mod.known_fixed_sources.cache_clear()
    assert incidents_mod.known_fixed_sources() == []
    incidents_mod.known_fixed_sources.cache_clear()


def test_mascara_norte_con_archivo_ausente_no_tapa_nada(monkeypatch, tmp_path):
    """Si `mascara-norte.json` no se puede leer, ninguna celda silencia: una
    celda que no existe no puede apagar detecciones."""
    incidents_mod.mascara_norte.cache_clear()
    monkeypatch.setattr(incidents_mod, "ROOT", tmp_path)
    assert incidents_mod.mascara_norte() == []
    incidents_mod.mascara_norte.cache_clear()


def test_mascara_ilegible_o_rara_no_silencia(db, monkeypatch):
    """Una celda con `franja` desconocida o mal formada no silencia nada, y un
    `observed_at` ilegible hace que la franja «dia» no se pueda evaluar — en
    ambos casos la regla no se inventa una condición."""
    celda = {"lat": PUNTO[0], "lon": PUNTO[1], "radio_km": 2.0, "revisar_el": "2030-01-01",
             "franja": "dia", "motivo": "suelo caliente"}
    monkeypatch.setattr(incidents_mod, "mascara_norte", lambda: [celda])
    # Sello ilegible → hora de Chile desconocida → la franja «dia» no aplica.
    assert incidents_mod._mask_reason(PUNTO[0], PUNTO[1], "ABI", "sello-ilegible", NOW) is None
    # Una franja que no existe y una celda mal formada se ignoran, no tumban el ciclo.
    monkeypatch.setattr(incidents_mod, "mascara_norte", lambda: [
        celda | {"franja": "rara"},
        {"mal": "formada"},
    ])
    assert incidents_mod._mask_reason(PUNTO[0], PUNTO[1], "ABI", stamp(NOW - timedelta(hours=3)), NOW) is None
    # Y la celda «siempre» vigente sí silencia: el filtro funciona en ambos sentidos.
    monkeypatch.setattr(incidents_mod, "mascara_norte", lambda: [celda | {"franja": "siempre"}])
    razon = incidents_mod._mask_reason(PUNTO[0], PUNTO[1], "ABI", stamp(NOW - timedelta(hours=3)), NOW)
    assert razon == "máscara del norte: suelo caliente"


def test_fuente_fija_con_fechas_ilegibles_no_silencia(db, monkeypatch):
    """Un `valid_from`/`valid_to` ilegible desactiva el punto: un error de tipeo
    en el archivo no puede tapar un incendio de verdad."""
    monkeypatch.setattr(incidents_mod, "known_fixed_sources", lambda: [
        {"name": "Volcán X", "kind": "volcan", "lat": ANTUCO[0], "lon": ANTUCO[1],
         "radius_km": 3, "valid_from": "no-es-fecha"},
    ])
    assert incidents_mod.fixed_reason(db, ANTUCO[0], ANTUCO[1], NOW) is None


def test_incendio_conaf_cerca_de_un_volcan_no_se_silencia(db):
    """FIX-03: un incendio informado por CONAF a ≤ 5 km invalida la regla entera,
    también para un volcán conocido — un fuego real en la ladera no queda tapado
    por el cráter vecino."""
    _fire(db, "7", lat=ANTUCO[0], lon=ANTUCO[1])
    o = _obs(db, "o1", NOW - timedelta(minutes=30), lat=ANTUCO[0], lon=ANTUCO[1])
    [inc] = incidents_mod.update(db, [o], NOW)
    assert inc["fixed_source"] == 0 and inc["fixed_reason"] is None


# --- transiciones de estado ---


def test_la_evidencia_sola_nunca_llega_a_confirmado(db):
    """Las transiciones por evidencia son anomalia → posible → reportado.
    «Confirmado» y «controlado» son palabras de CONAF: solo entran por
    `link_official`, nunca por calor satelital."""
    a = _obs(db, "a", NOW - timedelta(hours=2))
    [inc] = incidents_mod.update(db, [a], NOW)
    assert inc["status"] == "anomalia"
    b = _obs(db, "b", NOW - timedelta(hours=1))
    [inc] = incidents_mod.update(db, [b], NOW)
    assert inc["status"] == "posible"
    assert inc["status"] not in ("confirmado", "controlado")


def test_reportado_solo_con_reporte_verificado(db):
    """Un reporte ciudadano verificado cerca lleva el incidente a «reportado»:
    la palabra «hay alguien ahí» cuenta, pero solo con la verificación."""
    a = _obs(db, "a", NOW - timedelta(hours=2))
    [inc] = incidents_mod.update(db, [a], NOW)
    db.execute(
        "INSERT INTO reports(id, kind, description, lat, lon, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("r1", "llamas", "Se ve humo del cerro", PUNTO[0], PUNTO[1], "verificado",
         stamp(NOW - timedelta(hours=1))))
    b = _obs(db, "b", NOW - timedelta(minutes=30))
    [inc] = incidents_mod.update(db, [b], NOW)
    assert inc["status"] == "reportado"


def test_confirmado_y_controlado_solo_entran_por_link_official(db):
    """`link_official` es la única vía a los estados oficiales: enlaza al fuego
    de CONAF y lo mueve confirmado → controlado → extinguido con la ficha."""
    a = _obs(db, "a", NOW - timedelta(hours=2))
    [inc] = incidents_mod.update(db, [a], NOW)
    fire = _fire(db, "7", "confirmado")
    assert incidents_mod.link_official(db, [fire], NOW) == 1
    inc = db.one("SELECT * FROM incidents WHERE id = ?", (inc["id"],))
    assert inc["status"] == "confirmado" and inc["official_ref"] == "7"
    assert incidents_mod.link_official(db, [fire | {"status": "controlado"}], NOW) == 1
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc["id"],))["status"] == "controlado"
    assert incidents_mod.link_official(db, [fire | {"status": "extinguido"}], NOW) == 1
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc["id"],))["status"] == "extinguido"


def test_expire_cierra_el_silencio_satellital(db):
    """Un incidente sin calor en EXTINGUISH_HOURS pasa a «extinguido» según
    satélite: el rescoldo del que nadie habla no se declara vivo para siempre."""
    a = _obs(db, "a", NOW - timedelta(hours=30))
    [inc] = incidents_mod.update(db, [a], NOW - timedelta(hours=30))
    assert incidents_mod.expire(db, NOW) == 1
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc["id"],))["status"] == "extinguido"


def test_expire_no_toca_al_incidente_oficial(db):
    """El oficial sin calor reciente no caduca: `expire` excluye cualquier
    incidente con `official_ref`, cierre lo dicta CONAF."""
    a = _obs(db, "a", NOW - timedelta(hours=30))
    [inc] = incidents_mod.update(db, [a], NOW - timedelta(hours=30))
    fire = _fire(db, "7", "confirmado", started=NOW - timedelta(hours=30))
    incidents_mod.link_official(db, [fire], NOW)
    assert incidents_mod.expire(db, NOW) == 0
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc["id"],))["status"] == "confirmado"


# --- la vía lenta de `_status` (recalculo por reporte / enlace) ---


def test_goes_solo_pide_dos_barridos_seguidos_en_el_recalculo(db):
    """GOES barre el disco cada 10 min: dos detecciones del mismo sensor a
    ≤ 30 min son persistencia («posible»); dos momentos lejanos son un
    reflejo posible y se quedan en «anomalia» (también en la vía lenta de
    `refresh_near`, que corre al verificar un reporte)."""
    a = _goes(db, "a", NOW - timedelta(hours=2))
    b = _goes(db, "b", NOW - timedelta(hours=1))
    [inc] = incidents_mod.update(db, [a, b], NOW)
    assert inc["status"] == "anomalia"  # 60 min entre medias: sin par consecutivo
    assert incidents_mod.refresh_near(db, PUNTO[0], PUNTO[1], NOW) == 1
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc["id"],))["status"] == "anomalia"
    c = _goes(db, "c", NOW - timedelta(minutes=40))  # a 20 min de «b»: el par aparece
    [inc] = incidents_mod.update(db, [c], NOW)
    assert inc["status"] == "posible"
    assert incidents_mod.refresh_near(db, PUNTO[0], PUNTO[1], NOW) == 1
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc["id"],))["status"] == "posible"


# --- bordes de la pasada de agrupación ---


def test_la_misma_deteccion_dos_veces_en_la_tanda_no_duplica(db):
    """Un lote con el mismo `id` repetido enlaza una sola vez: la segunda
    aparición cae en `linked_ids` y no cuenta otro miembro."""
    o = _obs(db, "a", NOW - timedelta(hours=1))
    [inc] = incidents_mod.update(db, [o, dict(o)], NOW)
    assert inc["n_obs"] == 1


def test_vinculo_huerfano_sin_fila_de_observacion_frena(db):
    """Un `incident_observations` que apunta a una detección que no está en la
    tabla (retenida o rota) no deja que el ciclo la reasigne: `pr` ausente más
    vínculo presente significa «ya decidida», se omite."""
    a = _obs(db, "a", NOW - timedelta(hours=1))
    [inc] = incidents_mod.update(db, [a], NOW)
    db.execute(
        "INSERT INTO incident_observations(observation_id, incident_id) VALUES ('fantasma', ?)",
        (inc["id"],))
    fantasma = {"id": "fantasma", "source": "firms", "sensor": "VIIRS", "resolution_m": 375,
                "lat": PUNTO[0], "lon": PUNTO[1], "observed_at": stamp(NOW), "confidence": "alta"}
    assert incidents_mod.update(db, [fantasma], NOW) == []
    assert db.one("SELECT n_obs FROM incidents WHERE id = ?", (inc["id"],))["n_obs"] == 1


def test_fusion_por_deteccion_fuera_de_tabla_recalcula_el_agregado(db):
    """Cuando la detección que une dos incidentes aún no está en `observations`
    (llegó en la tanda, no persistió), la fusión del más antiguo recalcula sus
    agregados leyendo las filas — no se queda con el caché vacío."""
    norte = _obs(db, "n", NOW - timedelta(hours=2), lat=PUNTO[0])
    sur = _obs(db, "s", NOW - timedelta(hours=2), lat=PUNTO[0] - 4 * KM_LAT)
    inc_n, inc_s = incidents_mod.update(db, [norte, sur], NOW - timedelta(hours=2))
    assert inc_n["id"] != inc_s["id"]  # 4 km: cada uno su incidente
    fantasma = {"id": "m", "source": "firms", "sensor": "VIIRS", "resolution_m": 375,
                "lat": PUNTO[0] - 2 * KM_LAT, "lon": PUNTO[1],
                "observed_at": stamp(NOW - timedelta(minutes=30)), "confidence": "nominal"}
    [fusionado] = incidents_mod.update(db, [fantasma], NOW)
    assert fusionado["n_obs"] == 2  # la fantasma no está en la tabla: no cuenta
    assert fusionado["id"] in (inc_n["id"], inc_s["id"])
    muerto = inc_s["id"] if fusionado["id"] == inc_n["id"] else inc_n["id"]
    assert db.one("SELECT live_id FROM incident_merges WHERE dead_id = ?",
                  (muerto,))["live_id"] == fusionado["id"]
