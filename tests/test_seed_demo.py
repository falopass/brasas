"""El sembrador de la base demo (scripts/local/seed_demo.py).

De él cuelgan las capturas, axe y la regresión visual del E2E: si siembra distinto o sin la
marca «demo», el fallo se esconde dentro de un job de cinco minutos. Y como borra la carpeta
destino antes de sembrar, un destino mal pasado destruiría datos: la guarda aborta con código
2 si el destino es la raíz del repo, data/ o una base que él no marcó («seed_demo_at» en kv).

Sin red: `compute_risk` se simula caído y el script toma su camino de valores de ejemplo.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import seed_demo  # noqa: E402

from backend.services import Services  # noqa: E402


async def _sin_red(self):
    raise RuntimeError("sin red en la prueba")


def _sembrar(target: Path) -> None:
    """Corre el sembrador con Open-Meteo caído, sin ensuciar el entorno del proceso."""
    with patch.dict(os.environ), patch.object(Services, "compute_risk", _sin_red):
        seed_demo.main(target)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    target = tmp_path_factory.mktemp("demo")
    _sembrar(target)
    _sembrar(target)  # la guarda debe dejar resembrar sobre una base marcada por él mismo
    return target


def _query(target: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(target / "brasa.db")
    conn.execute("ATTACH DATABASE ? AS work", (str(target / "work.db"),))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


# --- lo que siembra: de esto dependen las capturas del E2E ---


def test_crea_las_dos_bases(demo):
    assert (demo / "brasa.db").is_file()
    assert (demo / "work.db").is_file()


def test_las_14_detecciones_llevan_marca_demo(demo):
    rows = _query(demo, "SELECT id FROM observations")
    assert len(rows) == 14
    assert all(row[0].startswith("demo:") for row in rows)


def test_incendio_oficial_dice_demo_en_el_nombre(demo):
    rows = _query(demo, "SELECT name FROM official_fires")
    assert rows and all("(DEMO)" in row[0] for row in rows)


def test_boton_rojo_cubre_los_proximos_dias(demo):
    hoy = datetime.now(ZoneInfo("America/Santiago")).date()
    limite = (hoy + timedelta(days=3)).isoformat()
    (n,) = _query(demo, "SELECT COUNT(*) FROM boton_rojo WHERE date BETWEEN ? AND ?", (hoy.isoformat(), limite))[0]
    assert n >= 5


def test_ninguna_fila_queda_sin_marca_demo(demo):
    assert _query(demo, "SELECT COUNT(*) FROM observations WHERE id NOT LIKE 'demo:%'")[0][0] == 0
    assert _query(demo, "SELECT COUNT(*) FROM official_fires WHERE id NOT LIKE 'demo%' AND name NOT LIKE '%DEMO%'")[0][0] == 0
    # Un incidente es demo si lo reclamó un incendio «demo» (official_ref) o si toda su
    # evidencia es «demo:». Los ids de incidente son uuid, no llevan la marca en el texto.
    assert (
        _query(
            demo,
            "SELECT COUNT(*) FROM incidents i "
            "WHERE (i.official_ref IS NULL OR i.official_ref NOT LIKE 'demo%') "
            "AND EXISTS (SELECT 1 FROM incident_observations io "
            "            JOIN observations o ON o.id = io.observation_id "
            "            WHERE io.incident_id = i.id AND o.id NOT LIKE 'demo:%')",
        )[0][0]
        == 0
    )


def test_la_deteccion_mas_reciente_es_fresca(demo):
    (stamp,) = _query(demo, "SELECT MAX(observed_at) FROM observations")[0]
    momento = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    # La siembra ancla la última detección ~18 min atrás (200 - 13·14) y promete avisar si
    # pasó media hora: fresca = menos de 30 min, nunca en el futuro.
    assert timedelta(0) <= datetime.now(timezone.utc) - momento < timedelta(minutes=30)


# --- la guarda: aborta con código 2 sin borrar nada ---


def test_guarda_no_borra_la_raiz_del_repo(monkeypatch):
    rmtree = Mock(side_effect=AssertionError("rmtree no debe ejecutarse"))
    monkeypatch.setattr(seed_demo.shutil, "rmtree", rmtree)
    with pytest.raises(SystemExit) as exc:
        seed_demo.main(seed_demo.ROOT)
    assert exc.value.code == 2
    rmtree.assert_not_called()


def test_guarda_no_borra_data_del_repo(monkeypatch):
    rmtree = Mock(side_effect=AssertionError("rmtree no debe ejecutarse"))
    monkeypatch.setattr(seed_demo.shutil, "rmtree", rmtree)
    with pytest.raises(SystemExit) as exc:
        seed_demo.main(seed_demo.ROOT / "data")
    assert exc.value.code == 2
    rmtree.assert_not_called()


def test_guarda_no_borra_una_base_ajena(tmp_path):
    ajena = tmp_path / "datos"
    ajena.mkdir()
    conn = sqlite3.connect(ajena / "brasa.db")  # una base real, sin la marca seed_demo_at
    conn.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit) as exc:
        seed_demo.main(ajena)
    assert exc.value.code == 2
    assert (ajena / "brasa.db").is_file()


def test_guarda_rechaza_un_brasa_que_no_es_base(tmp_path):
    raro = tmp_path / "raro"
    raro.mkdir()
    (raro / "brasa.db").write_text("no es sqlite")
    with pytest.raises(SystemExit) as exc:
        seed_demo.main(raro)
    assert exc.value.code == 2
    assert (raro / "brasa.db").read_text() == "no es sqlite"
