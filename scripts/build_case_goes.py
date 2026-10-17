"""Precalcula las detecciones GOES-16/19 FDC de un caso histórico y las guarda como JSON estático.

Descarga cada barrido de disco completo del período del caso (AWS Open Data, sin clave),
extrae los píxeles de fuego dentro de la caja del caso y descarta el archivo original.

Uso:  python scripts/build_case_goes.py vina-del-mar-2024
Salida: web/data/cases/<id>.goes.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.providers.goes import GoesError, download, key_start, list_keys, parse_fdc  # noqa: E402

FIELDS = ["minute", "lat", "lon", "frp_mw", "brightness_k", "confidence"]
CONF_CODE = {"alta": 2, "media": 1, "baja": 0}


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def build(case: dict, concurrency: int) -> dict:
    goes = case["goes"]
    satellite, cadence = goes["satellite"], int(goes["cadence_min"])
    start, end = parse_utc(case["start_utc"]), parse_utc(case["end_utc"])
    west, south, east, north = case["bbox"]
    window = (west - 0.1, south - 0.1, east + 0.1, north + 0.1)
    async with httpx.AsyncClient(timeout=60.0) as client:
        keys: list[str] = []
        hour = start.replace(minute=0, second=0)
        while hour < end:
            for key in await list_keys(client, satellite, hour):
                moment = key_start(key)
                if moment and start <= moment < end and moment.minute % cadence < 10:
                    keys.append(key)
            hour += timedelta(hours=1)
        print(f"{case['id']}: {len(keys)} barridos a procesar", flush=True)
        semaphore = asyncio.Semaphore(concurrency)
        scans: list[dict] = []
        rows: list[list] = []
        done = 0

        async def one(key: str) -> None:
            nonlocal done
            async with semaphore:
                for attempt in range(3):
                    try:
                        content = await download(client, satellite, key)
                        break
                    except GoesError:
                        await asyncio.sleep(2 ** attempt)
                else:
                    scans.append({"t": key_start(key).strftime("%Y-%m-%dT%H:%M:%SZ"), "n": None, "error": True})
                    return
            points = await asyncio.to_thread(parse_fdc, content, satellite, window)
            stamp = key_start(key).strftime("%Y-%m-%dT%H:%M:%SZ")
            scans.append({"t": stamp, "n": len(points)})
            minute = int((key_start(key) - start).total_seconds() // 60)
            for p in points:
                rows.append([minute, round(p["lat"], 4), round(p["lon"], 4), p["frp_mw"],
                             round(p["brightness_k"]) if p["brightness_k"] else None, CONF_CODE[p["confidence"]]])
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(keys)}", flush=True)

        await asyncio.gather(*(one(k) for k in keys))
    scans.sort(key=lambda s: s["t"])
    rows.sort(key=lambda r: r[0])
    return {
        "case_id": case["id"],
        "source": f"NOAA GOES-{satellite[1:]} ABI L2 FDCF (AWS Open Data, bucket noaa-goes{satellite[1:]})",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cadence_min": cadence,
        "bbox": case["bbox"],
        "resolution_note": "Píxel de ~2 km en el nadir; en Chile central es mayor. La posición es el centro del píxel.",
        "start_utc": case["start_utc"],
        "fields": FIELDS,
        "fields_note": "minute = minutos desde start_utc (inicio del barrido); confidence: 2 alta, 1 media, 0 baja.",
        "scans": scans,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case_id")
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()
    catalog = json.loads((ROOT / "web" / "data" / "cases.json").read_text(encoding="utf-8"))
    case = next((c for c in catalog["cases"] if c["id"] == args.case_id), None)
    if case is None or not case.get("goes"):
        raise SystemExit(f"El caso {args.case_id} no existe o no tiene GOES disponible.")
    payload = asyncio.run(build(case, args.concurrency))
    out = ROOT / "web" / "data" / "cases" / f"{case['id']}.goes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(payload['rows'])} detecciones en {len(payload['scans'])} barridos → {out}")


if __name__ == "__main__":
    main()
