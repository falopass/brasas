"""Datos de ejemplo para desarrollar sin esperar un incendio real. Uso: python scripts/local/seed_demo.py data/demo

Crea (o rehace) una base en la carpeta indicada con:
- un incidente «posible incendio» en Quilpué: 14 detecciones GOES/VIIRS de las últimas 3 h (ids «demo:»);
- un incendio informado por CONAF, marcado «(DEMO)», unido a ese incidente → estado «confirmado»;
- Botón Rojo de CONAF para 5 comunas en los próximos 3 días;
- riesgo 30-30-30: el real de Open-Meteo si hay internet; si no, valores de ejemplo.

NUNCA usar esta carpeta como datos de producción: todo lo sembrado lleva «demo» en su id o nombre.
Las horas se calculan desde ahora: vuelve a ejecutarlo si pasó más de media hora (aviso de datos atrasados).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(target: Path) -> None:
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    os.environ["BRASA_DATA_DIR"] = str(target)
    os.environ["BRASA_SCHEDULER"] = "0"
    from backend import incidents, settings
    from backend.geo import territory
    from backend.services import Services

    svc = Services(settings.load())
    db = svc.db
    now = datetime.now(timezone.utc).replace(microsecond=0)
    t = territory()

    # 1) Incidente: un frente que avanza hacia el sureste, visto por GOES cada ~14 min y dos pasadas VIIRS.
    rows = []
    for i in range(14):
        when = now - timedelta(minutes=200 - i * 14)
        sensor = "VIIRS" if i in (3, 9) else "ABI"
        lat, lon = -33.06 - i * 0.004, -71.42 + i * 0.003
        comuna = t.locate(lat, lon)
        obs = {"id": f"demo:{sensor}:{i}", "source": "GOES19_FDCF" if sensor == "ABI" else "VIIRS_NOAA20_NRT", "sensor": sensor,
               "satellite": "GOES-19" if sensor == "ABI" else "NOAA-20", "resolution_m": 2000 if sensor == "ABI" else 375,
               "lat": lat, "lon": lon, "observed_at": stamp(when), "frp_mw": round(20 + i * 9.5, 1),
               "confidence": "alta" if sensor == "ABI" else "nominal", "comuna_code": comuna.code if comuna else None}
        db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, frp_mw, confidence, "
                   "comuna_code, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (obs["id"], obs["source"], sensor, obs["satellite"], obs["resolution_m"], lat, lon, obs["observed_at"], obs["frp_mw"],
                    obs["confidence"], obs["comuna_code"], stamp(when + timedelta(minutes=12 if sensor == "ABI" else 95))))
        rows.append(obs)
    [incident] = incidents.update(db, rows, now)

    # 2) Incendio informado por CONAF (ficticio, con «DEMO» en el nombre) junto al incidente.
    fire = {"id": "demo-1", "name": "(DEMO) EL BELLOTO", "status": "confirmado", "status_raw": "En combate",
            "started_at": stamp(now - timedelta(hours=3, minutes=10)), "controlled_at": None, "extinguished_at": None,
            "area_ha": 35.5, "lat": -33.07, "lon": -71.41, "comuna": "Quilpué", "region": "Valparaíso", "ambito": "CONAF", "fuel": "Pastizal"}
    db.execute("INSERT INTO official_fires(id, name, status, status_raw, started_at, controlled_at, extinguished_at, area_ha, lat, lon, "
               "comuna, region, ambito, fuel, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (*fire.values(), stamp(now), stamp(now)))
    incidents.link_official(db, [fire], now)

    # 3) Botón Rojo para algunas comunas (Quilpué, Viña del Mar, Villa Alemana, Santiago, Curicó).
    today = datetime.now(ZoneInfo("America/Santiago")).date()
    for k, code in enumerate([5801, 5109, 5804, 13101, 7301]):
        for d in range(3):
            db.execute("INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
                       (code, (today + timedelta(days=d)).isoformat(), 4 - k % 3, 1500.0 * (k + 1), 0.05 * (k + 1), stamp(now)))
    db.kv_set("boton_rojo_at", stamp(now))

    # 3b) Condiciones oficiales de CONAF (PI/HC/VV/HR/TP) para las mismas comunas y días.
    cond_labels = {"PI": 70, "HC": 3, "VV": 6, "HR": 2, "TP": 8}
    with db.connect() as conn:
        for code in [5801, 5109, 5804, 13101, 7301]:
            for d in range(3):
                for var, label in cond_labels.items():
                    conn.execute("INSERT OR REPLACE INTO conaf_condiciones(comuna_code, date, var, label, cells, cells_total, "
                                 "fetched_at) VALUES (?,?,?,?,?,?,?)",
                                 (code, (today + timedelta(days=d)).isoformat(), var, label, 40, 120, stamp(now)))
    db.kv_set("conaf_cond_at", stamp(now))

    # 4) Riesgo: real si hay internet; si no, un patrón de ejemplo (alto en el centro, bajo en el sur).
    try:
        n = asyncio.run(asyncio.wait_for(svc.compute_risk(), 120))
        print(f"Riesgo 30-30-30 real (Open-Meteo) para {n} comunas")
    except Exception as exc:  # sin conexión: valores de ejemplo, solo para ver la interfaz
        levels = ["bajo", "moderado", "alto", "extremo"]
        with db.connect() as conn:
            for c in t.comunas:
                for d in range(7):
                    central = -40 < c.center[1] < -30  # zona central y centro-sur: más peligro en el ejemplo
                    level = levels[min(3, 1 + d % 3)] if central else levels[d % 2]
                    conn.execute("INSERT OR REPLACE INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, tmax, rhmin, "
                                 "windmax, gustmax, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (c.code, (today + timedelta(days=d)).isoformat(), level, levels.index(level) * 3, 0, levels.index(level) * 2,
                                  24 + 3 * levels.index(level), 50 - 8 * levels.index(level), 15 + 6 * levels.index(level), 30, stamp(now)))
        db.kv_set("risk_computed_at", stamp(now))
        print(f"Sin Open-Meteo ({type(exc).__name__}): riesgo de EJEMPLO para {len(t.comunas)} comunas")

    db.kv_set("last_ingest_at", stamp(now))
    print(f"Incidente {incident['id']} ({incident['n_obs']} detecciones) → http://127.0.0.1:8000/#/incendio/{incident['id']}")
    print("Para ver el modo emergencia: en «Mi zona» guarda un lugar con «Usar mi ubicación» cerca de Quilpué (-33.075, -71.405).")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "demo").resolve())
