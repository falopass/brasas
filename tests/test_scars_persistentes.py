"""AGUA-01 — cicatrices persistentes para el cruce de aluvión.

El riesgo de aluvión post-incendio dura más de un año (Quebrada Honda aluvionó 283
días después del incendio Plaza Sur), pero la retención de observaciones es de 45
días: la huella queda guardada en `scar_footprints` antes de borrarse, y los
incendios cerrados de la temporada anterior de CONAF llegan por
`conaf_cicatrices` —nunca por el ciclo de avisos—.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend import incidents as incidents_mod
from backend.db import Database
from backend.providers.conaf import parse_cicatrices
from backend.scars import cicatriz_cerca, conaf_ha_cerca, scar_ha_cerca, snapshot_footprints
from tests.test_scars import seed_incident

NOW = datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


CSV_CICATRICES = (
    "id,temporada,nombre,estado,f_inicio,f_control,f_extincion,sup_total,lat,lon,ambito,comb_inicial,comuna,provincia,region\n"
    '798094924,2025,PLAZA SUR,Extinguido,2025-12-29 15:06,2026-01-01 19:16,2026-01-02 18:41,"907,69",-33.4044,-70.4945,CONAF,Pastizal,Las Condes,Santiago,Metropolitana\n'
    '900,2025,CHICA,Extinguido,2026-01-05 10:00,,,"2,50",-33.5,-70.5,CONAF,Pastizal,Las Condes,Santiago,Metropolitana\n'
    '901,2025,SIN COORDENADAS,Extinguido,2026-01-05 10:00,,,"20,00",,-70.5,CONAF,Pastizal,Las Condes,Santiago,Metropolitana\n'
)


def _seed_cicatriz(db: Database) -> None:
    """La fila de «Plaza Sur» (CONAF, 29-dic-2025, 907,69 ha) tal como la deja la ingesta."""
    db.execute(
        "INSERT INTO conaf_cicatrices(id, nombre, comuna, region, lat, lon, ha, inicio, temporada, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("798094924", "PLAZA SUR", "Las Condes", "Metropolitana", -33.4044, -70.4945, 907.69,
         "2025-12-29T18:06:00Z", "2025", _stamp(NOW)),
    )


def test_la_huella_sobrevive_a_la_retencion(tmp_path):
    """Snapshot, luego la retención de 45 días borra observaciones e incidentes, y
    `scar_ha_cerca` sigue encontrando la cicatriz desde `scar_footprints`."""
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1", days_ago=50)
    snapshot_footprints(db, _stamp(NOW - timedelta(days=60)))
    assert db.one("SELECT incident_id FROM scar_footprints WHERE incident_id = 'inc-1'")
    cutoff = _stamp(NOW - timedelta(days=45))
    db.execute("DELETE FROM observations WHERE observed_at < ?", (cutoff,))
    incidents_mod.prune(db, cutoff)
    assert db.one("SELECT id FROM incidents WHERE id = 'inc-1'") is None
    assert scar_ha_cerca(db, -35.42, -71.60, 180) > 0


@pytest.mark.parametrize("sentencia", ["status = 'descartado'", "fixed_source = 1"])
def test_un_incidente_descartado_o_de_fuente_fija_sale_de_scar_footprints(tmp_path, sentencia):
    """Si el incidente pasa a descartado o a fuente de calor fija, su fila se borra:
    un volcán o una quema industrial no es suelo quemado."""
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1")
    snapshot_footprints(db, _stamp(NOW - timedelta(days=60)))
    assert db.one("SELECT incident_id FROM scar_footprints WHERE incident_id = 'inc-1'")
    db.execute(f"UPDATE incidents SET {sentencia} WHERE id = 'inc-1'")
    snapshot_footprints(db, _stamp(NOW - timedelta(days=60)))
    assert db.one("SELECT incident_id FROM scar_footprints WHERE incident_id = 'inc-1'") is None


def test_el_parser_de_la_temporada_anterior_con_coma_decimal_y_fila_invalida():
    """«907,69» son 907,69 ha; una fila sin coordenadas y otra bajo las 10 ha no entran.
    `f_inicio` viene en hora de Chile continental (UTC-3 en verano) y sale en UTC."""
    cicatrices = parse_cicatrices(CSV_CICATRICES)
    assert [c["id"] for c in cicatrices] == ["798094924"]
    plaza = cicatrices[0]
    assert plaza["ha"] == 907.69
    assert plaza["inicio"] == "2025-12-29T18:06:00Z"
    assert plaza["comuna"] == "Las Condes" and plaza["temporada"] == "2025"


def test_refresh_conaf_cicatrices_no_crea_alertas(make_client, web):
    """Con un lugar guardado al lado del incendio: la tabla queda llena y `alerts` vacía."""
    web.add(lambda r: "incendios_totales_25_26" in r.url.path, lambda r: httpx.Response(200, text=CSV_CICATRICES))
    with make_client() as client:
        svc = client.app.state.services
        db = svc.db
        db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
        db.execute(
            "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, older_adult, created_at) "
            "VALUES ('p1','s1','Casa','casa',-33.40,-70.49,10,13110,0,'2026-10-01T00:00:00Z')"
        )
        assert asyncio.run(svc.refresh_conaf_cicatrices()) == 1
        row = db.one("SELECT * FROM conaf_cicatrices WHERE id = '798094924'")
        assert row["ha"] == 907.69 and row["nombre"] == "PLAZA SUR"
        assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 0
        # La marca de 7 días en la caché de la base impide una segunda descarga.
        assert asyncio.run(svc.refresh_conaf_cicatrices()) == 0
        assert len(web.requests) == 1


def test_el_disco_equivalente_de_907_ha_tiene_radio_de_1_7_km():
    """sqrt(ha / 100 / π) km: la aproximación del punto de inicio de CONAF."""
    assert math.isclose(math.sqrt(907.69 / 100 / math.pi), 1.70, abs_tol=0.01)


def test_un_lugar_a_2_km_de_plaza_sur_recibe_conaf_y_uno_a_30_km_no(tmp_path):
    """El aluvión de Quebrada Honda cayó a 2 km del punto de inicio de «Plaza Sur»."""
    db = Database(tmp_path / "t.db")
    _seed_cicatriz(db)
    cerca = cicatriz_cerca(db, -33.3863, -70.4945)  # ~2 km al norte del punto de inicio
    assert cerca["ha"] > 0 and cerca["fuente"] == "conaf"
    assert cerca["incendio"]["id"] == "798094924" and cerca["incendio"]["nombre"] == "PLAZA SUR"
    assert cerca["dias_desde"] is not None and cerca["dias_desde"] > 0
    lejos = cicatriz_cerca(db, -33.1331, -70.4945)  # ~30 km al norte
    assert lejos["ha"] == 0 and lejos["fuente"] is None and lejos["incendio"] is None


def test_cicatriz_cerca_devuelve_el_maximo_no_la_suma(tmp_path):
    """El mismo incendio visto por satélite y por CONAF no se cuenta dos veces."""
    db = Database(tmp_path / "t.db")
    seed_incident(db, "inc-1", lat=-33.4044, lon=-70.4945)
    _seed_cicatriz(db)
    satelite = scar_ha_cerca(db, -33.3863, -70.4945, 365)
    conaf = conaf_ha_cerca(db, -33.3863, -70.4945)
    assert satelite > 0 and conaf["ha"] > 0
    cruce = cicatriz_cerca(db, -33.3863, -70.4945)
    assert cruce["ha_satelite"] == satelite and cruce["ha_conaf"] == conaf["ha"]
    assert cruce["ha"] == max(satelite, conaf["ha"]) < satelite + conaf["ha"]
