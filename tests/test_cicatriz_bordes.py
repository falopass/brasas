"""QA-COB: bordes de `backend/scars.py` y `backend/lluvia.py` — los 365 días
exactos del cruce de aluvión, el disco que apenas toca el radio de 5 km, las
series con huecos y las fuentes corruptas.

El cruce de aluvión decide si se despierta a alguien por lluvia sobre suelo
quemado: un error de borde aquí avisa un año y un día después —o deja de avisar
el día 365— y eso es daño real. Cada prueba nombra su regla en el docstring.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend import lluvia
from backend import scars as scars_mod
from backend.db import Database

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
PUNTO = (-35.42, -71.60)  # Talca


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "brasa.db")


def _incident(db: Database, iid: str, pixels: list[tuple], comuna_code: int | None = 7101,
              seen: datetime | None = None, status: str = "posible", fixed_source: int = 0) -> None:
    """Incidente con sus observaciones enlazadas (mismo molde que test_scars).

    `pixels` son (lat, lon, confidence) y aceptan valores rotos a propósito:
    la fila `incidents` usa solo las numéricas para centro y caja."""
    seen = seen or NOW - timedelta(days=1)
    at = stamp(seen)
    nums = [(p[0], p[1]) for p in pixels if isinstance(p[0], (int, float)) and isinstance(p[1], (int, float))]
    lats, lons = [p[0] for p in nums] or [-35.42], [p[1] for p in nums] or [-71.60]
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, "
        "lat, lon, min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, "
        "fixed_source, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (iid, status, at, stamp(seen - timedelta(hours=2)), at, sum(lats) / len(lats),
         sum(lons) / len(lons), min(lats), max(lats), min(lons), max(lons), len(pixels), len(pixels),
         "VIIRS", comuna_code, fixed_source, at))
    for j, (plat, plon, conf) in enumerate(pixels):
        oid = f"{iid}-o{j}"
        db.execute(
            "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, "
            "observed_at, frp_mw, confidence, comuna_code, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (oid, "gen", "VIIRS", "GEN", 375, plat, plon, at, 10.0, conf, comuna_code, at))
        db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES (?,?)",
                   (oid, iid))


def _cicatriz(db: Database, cid: str, lat: float, lon: float, ha: float, inicio: str,
              nombre: str = "El Corte") -> None:
    db.execute(
        "INSERT INTO conaf_cicatrices(id, nombre, comuna, region, lat, lon, ha, inicio, temporada, "
        "fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, nombre, "Talca", "Maule", lat, lon, ha, inicio, "2025-2026", stamp(NOW)))


# --- lectura defensiva de fuentes ---


def test_miembro_con_coordenadas_rotas_no_deforma_la_huella(db):
    """Una observación con lat/lon ilegible o fuera del mundo no puede llevar
    la cicatriz fuera de EPSG:4326: se excluye del píxel, no se rompe la unión."""
    _incident(db, "i1", pixels=[(-35.42, -71.60, "alta"), ("no-es-lat", -71.60, "alta")])
    scars_mod.snapshot_footprints(db, stamp(NOW - timedelta(days=2)))
    fila = db.one("SELECT * FROM scar_footprints WHERE incident_id = 'i1'")
    assert fila is not None and fila["ha"] > 0  # la huella queda con el píxel bueno
    # Y si TODOS los miembros están rotos, el incidente no siembra huella.
    _incident(db, "i2", pixels=[("mal", "mal", "alta")])
    scars_mod.snapshot_footprints(db, stamp(NOW - timedelta(days=2)))
    assert db.one("SELECT 1 AS x FROM scar_footprints WHERE incident_id = 'i2'") is None


def test_incidente_sin_pixeles_confiables_no_deja_huella(db):
    """La cicatriz es suelo donde el satélite vio calor confiable: un incidente
    con solo detecciones «baja» no siembra huella (no es suelo quemado medido)."""
    _incident(db, "i1", pixels=[(-35.42, -71.60, "baja"), (-35.42, -71.61, "baja")])
    assert scars_mod.snapshot_footprints(db, stamp(NOW - timedelta(days=2))) == 0
    assert db.one("SELECT 1 AS x FROM scar_footprints") is None


def test_huella_guardada_rota_se_reemplaza_por_la_recalculada(db):
    """Un `geojson` corrupto en `scar_footprints` no tumba el recálculo ni
    pierde la huella: queda la recién calculada y la fila se repara sola."""
    _incident(db, "i1", pixels=[(-35.42, -71.60, "alta"), (-35.421, -71.60, "alta")])
    db.execute(
        "INSERT INTO scar_footprints(incident_id, first_seen_at, last_seen_at, min_lat, max_lat, "
        "min_lon, max_lon, ha, geojson) VALUES ('i1', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', "
        "-36, -35, -72, -71, 0.0, 'no es geojson')")
    assert scars_mod.snapshot_footprints(db, stamp(NOW - timedelta(days=2))) == 1
    fila = db.one("SELECT ha, geojson FROM scar_footprints WHERE incident_id = 'i1'")
    assert fila["ha"] > 0 and "no es geojson" not in fila["geojson"]


def test_dias_desde_inicio_ilegible_no_inventa(db):
    """Un `inicio` de CONAF ilegible devuelve `dias_desde` en None — no se
    fabrica una edad para el incendio."""
    _cicatriz(db, "c1", PUNTO[0], PUNTO[1], 500.0, "basura")
    cerca = scars_mod.cicatriz_cerca(db, PUNTO[0], PUNTO[1])
    assert cerca["incendio"]["id"] == "c1" and cerca["dias_desde"] is None


def test_coordenadas_o_radios_invalidos_no_cruzan_nada(db):
    """Un punto fuera del mundo o un radio de cero devuelven la lectura vacía:
    el cruce no se inventa una cicatriz."""
    assert scars_mod.scar_ha_cerca(db, float("nan"), -71.0) == 0.0
    assert scars_mod.scar_ha_cerca(db, -35.42, -71.60, radio_km=0) == 0.0
    assert scars_mod.conaf_ha_cerca(db, float("nan"), -71.0)["ha"] == 0.0
    assert scars_mod.conaf_ha_cerca(db, -35.42, -71.60, radio_km=0)["ha"] == 0.0


# --- los bordes del cruce: 365 días exactos y el disco de 5 km ---


def _congelado(fijado: datetime):
    class _Fecha(datetime):
        @classmethod
        def now(cls, tz=None):
            return fijado if tz is None else fijado.astimezone(tz)
    return _Fecha


def test_cicatriz_justo_a_365_dias_cuenta_y_una_mas_vieja_no(db, monkeypatch):
    """CICATRIZ_DIAS = 365: el incendio que empezó exactamente hace 365 días
    sigue dentro del primer año post-incendio (el aluvión llega con meses de
    retraso); el de hace 365 días y 1 s ya quedó fuera."""
    monkeypatch.setattr(scars_mod, "datetime", _congelado(NOW))
    inicio_borde = stamp(NOW - timedelta(days=365))
    inicio_fuera = stamp(NOW - timedelta(days=365, seconds=1))
    _cicatriz(db, "borde", PUNTO[0], PUNTO[1], 500.0, inicio_borde)
    _cicatriz(db, "fuera", PUNTO[0] - 0.01, PUNTO[1], 500.0, inicio_fuera, nombre="El Viejo")
    cerca = scars_mod.cicatriz_cerca(db, PUNTO[0], PUNTO[1])
    assert cerca["fuente"] == "conaf" and cerca["incendio"]["id"] == "borde"
    assert cerca["dias_desde"] == 365
    assert db.one("SELECT nombre FROM conaf_cicatrices WHERE id = 'fuera'")["nombre"] == "El Viejo"


def test_disco_conaf_que_toca_el_borde_cuenta(db):
    """La cicatriz CONAF cuenta si su disco de área equivalente toca el disco de
    5 km del punto: apenas dentro sí, apenas fuera no — el borde es el del área,
    no el del centro del incendio."""
    r_km = (1000.0 / 100.0 / 3.14159265) ** 0.5  # ha → radio del disco equivalente
    km_grado = 110.57
    lejos = PUNTO[0] + (5.0 + r_km + 0.5) / km_grado  # el disco más cercano queda a 0,5 km
    _cicatriz(db, "lejos", lejos, PUNTO[1], 1000.0, stamp(NOW - timedelta(days=30)))
    assert scars_mod.conaf_ha_cerca(db, PUNTO[0], PUNTO[1])["ha"] == 0.0
    tocando = PUNTO[0] + (5.0 + r_km - 0.5) / km_grado  # el borde del disco entra 0,5 km
    _cicatriz(db, "toca", tocando, PUNTO[1], 1000.0, stamp(NOW - timedelta(days=30)))
    cerca = scars_mod.conaf_ha_cerca(db, PUNTO[0], PUNTO[1])
    assert cerca["ha"] > 0 and cerca["incendio"]["id"] == "toca"


def test_comuna_desconocida_no_rompe_la_temporada(db):
    """Un incidente con `comuna_code` que no está en el territorio se salta del
    FeatureCollection — la respuesta no inventa una comuna ni rompe."""
    _incident(db, "i1", pixels=[(-35.42, -71.60, "alta")], comuna_code=999999)
    _incident(db, "i2", pixels=[(-35.42, -71.60, "alta")], comuna_code=7101)
    salida = scars_mod.season_scars(db, 365)
    assert [f["properties"]["comuna_code"] for f in salida["features"]] == [7101]
    assert salida["incidents_examined"] == 2


# --- lluvia: el cuarto dato del criterio y las series con huecos ---


def test_criterio_aviso_sin_elevacion_maxima_no_suena():
    """El criterio del aluvión exige las cuatro condiciones medidas; sin
    `elev_max_m` la isoterma no se puede comparar y el cruce calla (la excepción
    es solo la isoterma ausente, no la ladera)."""
    senal = {"mm_3h": 12.0, "isoterma_m": 2800.0}
    relieve = {"slope_max_deg": 15.0}  # sin elev_max_m
    assert lluvia.criterio_aviso(senal, relieve, {"ha": 50.0}) is False
    # Con todos los datos, sí.
    assert lluvia.criterio_aviso(senal, relieve | {"elev_max_m": 2700.0}, {"ha": 50.0}) is True
    # Y con isoterma por debajo de la cota, no.
    assert lluvia.criterio_aviso(senal | {"isoterma_m": 2000.0}, relieve | {"elev_max_m": 2700.0},
                                 {"ha": 50.0}) is False


def test_ventana_con_una_sola_hora_no_existe():
    """La señal mide ventanas de 3 h: una serie de una sola hora no tiene con
    qué evaluar una y sale todo en None, nunca una lectura a medias."""
    hourly = {"time": ["2026-10-20T14:00"], "precipitation": [12.0],
              "freezing_level_height": [2800.0]}
    assert lluvia.ventana(hourly) is None
    s = lluvia.senal(hourly)
    assert s == {"mm_3h": None, "isoterma_m": None, "isoterma_alta": None,
                 "intensa": False, "ventana": None, "horas_hasta": None}


def test_ventana_que_cruza_medianoche_utc_sigue_siendo_una():
    """La peor ventana puede cruzar la medianoche UTC: 23:00-02:00 es una sola
    ventana de 3 h y su inicio es la hora del día anterior."""
    hourly = {
        "time": ["2026-10-20T22:00", "2026-10-20T23:00", "2026-10-21T00:00",
                 "2026-10-21T01:00", "2026-10-21T02:00"],
        "precipitation": [0.0, 5.0, 5.0, 5.0, 0.0],
        "freezing_level_height": [1800.0] * 5,
    }
    mejor = lluvia.ventana(hourly)
    assert mejor["mm_3h"] == 15.0 and mejor["inicio"] == "2026-10-20T23:00"
    # La isoterma se lee en la hora central: la del 00:00 del día siguiente.
    hourly["freezing_level_height"] = [1800.0, 1800.0, 3000.0, 1800.0, 1800.0]
    assert lluvia.ventana(hourly)["isoterma_m"] == 3000.0
