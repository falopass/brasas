"""Actualiza el snapshot de respaldo de estaciones SINCA (OFI-10).

Descarga `listadomapa2k19` desde el portal público de SINCA (o desde `SINCA_PROXY_URL`
si está definida), parsea las estaciones con `backend.providers.sinca.latest_network`
y guarda un JSON compacto con `fetched_at` (ISO UTC), `source_url` y `stations`
(solo los campos esenciales: código, nombre, comuna/región, lat, lon, mp25,
status/categoría ICAP y `observed_at`).

Uso:
    python scripts/actualizar_sinca_snapshot.py [--output RUTA] [--url URL]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.providers import sinca  # noqa: E402

DEFAULT_OUTPUT = sinca.DEFAULT_SNAPSHOT_PATH


def compactar_estacion(st: dict[str, Any]) -> dict[str, Any]:
    """Conserva solo los campos esenciales de cada estación parseada por `sinca.latest_network`."""
    val = st.get("pm25") if st.get("pm25") is not None else st.get("mp25")
    fila: dict[str, Any] = {
        "code": str(st.get("code") or ""),
        "name": (st.get("name") or "").strip(),
        "comuna": (st.get("comuna") or "").strip(),
        "lat": st["lat"],
        "lon": st["lon"],
        "mp25": val,
        "pm25": val,
        "icap": st.get("icap"),
        "status": (st.get("status") or "").strip(),
        "observed_at": st.get("observed_at"),
    }
    if st.get("region"):
        fila["region"] = str(st["region"]).strip()
    return fila


def build_snapshot(payload: Any, *, fetched_at: datetime | None = None, source_url: str = sinca.RED_URL) -> dict[str, Any]:
    """Construye el diccionario del snapshot a partir del JSON crudo de `listadomapa2k19`."""
    now_utc = (fetched_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    parsed = sinca.latest_network(payload)
    stations = [compactar_estacion(st) for st in parsed]
    return {
        "fetched_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": source_url,
        "stations": stations,
    }


def download_payload(url: str | None = None, *, timeout: float = 30.0) -> tuple[Any, str]:
    """Descarga el listado de SINCA probando primero `url` / `SINCA_PROXY_URL` y luego `RED_URL`."""
    candidates = sinca._candidate_urls(url)
    last_exc: Exception | None = None
    for target in candidates:
        try:
            response = httpx.get(target, headers=sinca._HEADERS, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError("La respuesta de SINCA no es una lista JSON.")
            return data, target
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            last_exc = exc
    raise sinca.SincaError(f"No se pudo descargar el listado SINCA: {last_exc}") from last_exc


def actualizar_snapshot(
    output_path: str | Path | None = None,
    *,
    url: str | None = None,
    payload: Any | None = None,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    """Descarga (o recibe `payload` simulado), construye y guarda el snapshot compacto en disco."""
    destino = Path(output_path) if output_path is not None else Path(
        os.getenv("SINCA_SNAPSHOT_PATH", "").strip() or DEFAULT_OUTPUT
    )
    if payload is None:
        raw_payload, _ = download_payload(url)
    else:
        raw_payload = payload
    if not isinstance(raw_payload, list):
        raise sinca.SincaError("La respuesta de SINCA no tiene el formato esperado.")
    # El JSON sale de listadomapa2k19 aunque el transporte sea un proxy.
    snapshot = build_snapshot(raw_payload, fetched_at=fetched_at, source_url=sinca.RED_URL)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Ruta de salida del snapshot (por defecto: {DEFAULT_OUTPUT.relative_to(ROOT).as_posix()})",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="URL opcional (proxy o relay) para consultar antes de sinca.mma.gob.cl",
    )
    args = parser.parse_args(argv)
    try:
        snap = actualizar_snapshot(args.output, url=args.url)
    except sinca.SincaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Snapshot SINCA actualizado ({len(snap['stations'])} estaciones) en {snap['fetched_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
