"""Caducidad por tipo de reporte (QA-39 sobre FIX-21/MOD-01).

Humo 6 h, llamas 24 h, quema 72 h, otro 24 h. La cola de moderación itera
`EXPIRE_HOURS_BY_KIND` y los avisos vecinales usan el mismo plazo con `EXPIRE_HOURS`
como respaldo para un tipo desconocido. Estas pruebas fijan la regla completa:
el plazo efectivo por tipo, el borde exacto, el respaldo y el corte ISO.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend import alerts, reports as reports_mod

STAMP = "%Y-%m-%dT%H:%M:%SZ"
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def _db(tmp_path):
    """Base mínima con un lugar a 2,8 km del reporte, como en test_alert_report."""
    from backend.db import Database

    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.05,-71.55,10,'2026-10-01T00:00:00Z')")
    return db


def _report(**kw):
    return {"id": "r1", "created_at": NOW.strftime(STAMP),
            "lat": -33.05, "lon": -71.52, "kind": "humo", "status": "verificado",
            "description": "x", "photo": None, "subscriber_id": "s9", "moderator_note": None, **kw}


@pytest.mark.parametrize("kind,hours", [("humo", 6), ("llamas", 24), ("quema", 72), ("otro", 24)])
def test_each_kind_has_its_own_expiry_window(kind: str, hours: int):
    """El plazo efectivo es el del diccionario; ni el plazo por defecto ni otro tipo."""
    assert reports_mod.EXPIRE_HOURS_BY_KIND[kind] == hours
    almost = (NOW - timedelta(hours=hours) + timedelta(seconds=1)).strftime(STAMP)
    past = (NOW - timedelta(hours=hours)).strftime(STAMP)
    assert reports_mod.expired(almost, NOW, hours=hours) is False
    assert reports_mod.expired(past, NOW, hours=hours) is True


@pytest.mark.parametrize("kind", ["un-tipo-nuevo", None])
def test_alerts_treat_an_unknown_kind_with_the_default_window(tmp_path, kind):
    """Verificado a las 7 h ya no avisa (pasó el respaldo de 6 h); a las 5 h sí.
    El respaldo `EXPIRE_HOURS` ya está fijado por esta prueba; no hace falta
    comprobar `dict.get` por separado."""
    db = _db(tmp_path)
    old = _report(kind=kind, created_at=(NOW - timedelta(hours=7)).strftime(STAMP))
    fresh = _report(kind=kind, created_at=(NOW - timedelta(hours=5)).strftime(STAMP))
    assert alerts.evaluate_report(db, old, now=NOW) == []
    assert len(alerts.evaluate_report(db, fresh, now=NOW)) == 1


def test_a_kind_without_a_window_never_expires_in_the_queue(make_client):
    """`_expire_stale` solo toca los tipos del diccionario: un tipo nuevo espera al humano."""
    admin = {"X-Admin-Token": "admin-secret-token-999"}
    with make_client(ADMIN_TOKEN=admin["X-Admin-Token"]) as client:
        svc = client.app.state.services
        old = (NOW - timedelta(days=30)).strftime(STAMP)
        svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       ("tipo-raro", old, -33.05, -71.55, 5109, "un-tipo-nuevo", "x", "no_verificado"))
        queue = client.get("/api/admin/reports", headers=admin).json()
        assert queue["expired_now"] == 0
        assert [r["id"] for r in queue["reports"]] == ["tipo-raro"]


def test_a_naive_created_at_is_assumed_utc_instead_of_crashing():
    """Filas viejas o importadas llegan sin zona: la base guarda UTC y así se leen."""
    naive_old = (NOW - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S")
    naive_fresh = (NOW - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S")
    assert reports_mod.expired(naive_old, NOW, hours=6) is True
    assert reports_mod.expired(naive_fresh, NOW, hours=6) is False


def test_an_offset_created_at_is_compared_in_absolute_time():
    """`-03:00` (Chile) y `Z` nombran el mismo instante: la edad no depende del formato."""
    chile = timezone(timedelta(hours=-3))
    old = (NOW - timedelta(hours=7)).astimezone(chile).isoformat(timespec="seconds")
    fresh = (NOW - timedelta(hours=5)).astimezone(chile).isoformat(timespec="seconds")
    assert old.endswith("-03:00")
    assert reports_mod.expired(old, NOW, hours=6) is True
    assert reports_mod.expired(fresh, NOW, hours=6) is False


def test_an_unparseable_created_at_does_not_expire():
    """Basura en la marca no tumba la cola ni da el aviso por caducado."""
    assert reports_mod.expired("no es fecha", NOW) is False
    assert reports_mod.expired("2026-13-40T99:99", NOW) is False


def test_expire_cutoff_marks_exactly_the_boundary_that_expired_uses():
    """Corte y comparación coherentes: en el corte (con `Z`) ya caducó; un segundo adentro, no."""
    cutoff = reports_mod.expire_cutoff(now=NOW, hours=6)
    assert reports_mod.expired(cutoff, NOW, hours=6) is True
    inside = (NOW - timedelta(hours=6) + timedelta(seconds=1)).strftime(STAMP)
    assert reports_mod.expired(inside, NOW, hours=6) is False


def test_expire_cutoff_returns_the_expected_iso_stamp():
    assert reports_mod.expire_cutoff(now=NOW, hours=72) == "2026-10-15T12:00:00Z"
    # Sin `hours`, el plazo por defecto (6 h).
    assert reports_mod.expire_cutoff(now=NOW) == "2026-10-18T06:00:00Z"


def test_every_window_is_positive_and_distinct_from_the_duplicate_window():
    """Caducidad y deduplicación son conceptos distintos: mezclarlos sería un error mudo."""
    assert reports_mod.EXPIRE_HOURS_BY_KIND
    for kind, hours in reports_mod.EXPIRE_HOURS_BY_KIND.items():
        assert hours > 0, kind
        assert hours != reports_mod.DUPLICATE_HOURS, kind
    assert set(reports_mod.EXPIRE_HOURS_BY_KIND) <= set(reports_mod.KINDS)
