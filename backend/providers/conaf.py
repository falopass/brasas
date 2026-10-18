"""CONAF: Botón Rojo (pronóstico oficial de condiciones) e incendios informados (reporte público de GEPRIF).

Botón Rojo: pronóstico oficial a 5 días de condiciones favorables para incendios, por comuna.

Capa pública de ArcGIS Online del Departamento de Desarrollo e Investigación (Gerencia de Protección contra
Incendios Forestales) de CONAF, la misma que alimenta su tablero «Botón Rojo». Cada fila es una comuna, un día y una
cantidad de horas en condición Botón Rojo, con la superficie que la cumple. Aquí se resume por comuna y día:
máximo de horas, hectáreas y proporción de la comuna.

Botón Rojo indica CONDICIONES favorables para que un incendio se inicie y propague, nunca un incendio detectado.
La información es propiedad de CONAF: se muestra con su nombre y enlace, sin presentarla como propia.

Incendios: CSV que la Gerencia de Protección contra Incendios Forestales de CONAF publica en GitHub (lo usa, por
ejemplo, el tablero de MINSAL). Es la única evidencia con la que BRASA marca un incidente como «confirmado».
El repositorio no declara licencia: se cita siempre a CONAF con enlace y se debe pedir autorización formal.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

LAYER_URL = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/Boton_Rojo/FeatureServer/0/query"
DASHBOARD_URL = "https://www.arcgis.com/apps/dashboards/41ee3c691359437aa9df2a09d7f6124e"
SOURCE = "CONAF · Botón Rojo"
PAGE = 2000


class ConafError(Exception):
    pass


async def fetch_boton_rojo(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Filas crudas de la capa (paginadas): date, com_id, horas, SUM_br_ha, proportion."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {"where": "1=1", "outFields": "date,com_id,horas,SUM_br_ha,proportion", "returnGeometry": "false",
                  "orderByFields": "FID", "resultOffset": offset, "resultRecordCount": PAGE, "f": "json"}
        try:
            response = await client.get(LAYER_URL, params=params, timeout=40)
            response.raise_for_status()
            data = response.json()
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            raise ConafError(f"CONAF Botón Rojo no respondió ({type(exc).__name__}).") from exc
        if "error" in data:
            raise ConafError(f"CONAF Botón Rojo devolvió un error ({data['error'].get('code')}).")
        batch = [f.get("attributes") or {} for f in data.get("features", [])]
        rows += batch
        if not data.get("exceededTransferLimit") or not batch or offset > 50 * PAGE:
            return rows
        offset += len(batch)


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Una fila por comuna y día: horas máximas en condición Botón Rojo, hectáreas y proporción de la comuna."""
    out: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        try:
            code, day = int(row["com_id"]), str(row["date"])[:10]
            hours = int(row.get("horas") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if len(day) != 10 or hours <= 0:
            continue
        item = out.setdefault((code, day), {"comuna_code": code, "date": day, "hours": 0, "area_ha": 0.0, "proportion": 0.0})
        item["hours"] = max(item["hours"], hours)
        item["area_ha"] += float(row.get("SUM_br_ha") or 0)
        item["proportion"] += float(row.get("proportion") or 0)
    for item in out.values():
        item["area_ha"] = round(item["area_ha"])
        item["proportion"] = round(min(item["proportion"], 1.0), 3)
    return sorted(out.values(), key=lambda i: (i["date"], i["comuna_code"]))


# ------------------------------------------------------------------ incendios informados por CONAF
FIRES_CSV_URL = "https://raw.githubusercontent.com/deigeprif/public/refs/heads/main/reporte/incendios.csv"
FIRES_PAGE_URL = "https://github.com/deigeprif/public"
FIRES_SOURCE = "CONAF · reporte público de incendios (GEPRIF)"
CHILE_TZ = ZoneInfo("America/Santiago")
# Estados de CONAF → estado del incidente en BRASA.
STATUS_MAP = {"en combate": "confirmado", "activo": "confirmado", "bajo observacion": "confirmado", "bajo observación": "confirmado",
              "controlado": "controlado", "extinguido": "extinguido"}


def _local(value: str | None) -> str | None:
    """«2026-07-07 10:15» (hora de Chile) → ISO UTC. Nada si viene vacío o mal formado."""
    if not value or not value.strip():
        return None
    try:
        moment = datetime.strptime(value.strip()[:16], "%Y-%m-%d %H:%M").replace(tzinfo=CHILE_TZ)
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _number(value: str | None) -> float | None:
    try:
        return float(str(value).replace(".", "").replace(",", ".")) if value not in (None, "") else None
    except ValueError:
        return None


def parse_fires(text: str) -> list[dict[str, Any]]:
    fires = []
    for row in csv.DictReader(io.StringIO(text)):
        lat, lon = _number_plain(row.get("lat")), _number_plain(row.get("lon"))
        started = _local(row.get("f_inicio"))
        if lat is None or lon is None or not started or not row.get("id"):
            continue
        estado = (row.get("estado") or "").strip()
        fires.append({
            "id": str(row["id"]).strip(), "name": (row.get("nombre") or "").strip()[:120], "status_raw": estado[:40],
            "status": STATUS_MAP.get(estado.lower(), "confirmado"),
            "started_at": started, "controlled_at": _local(row.get("f_control")), "extinguished_at": _local(row.get("f_extincion")),
            "area_ha": _number(row.get("sup_total")), "lat": lat, "lon": lon,
            "comuna": (row.get("comuna") or "").strip()[:60] or None, "region": (row.get("region") or "").strip()[:60] or None,
            "ambito": (row.get("ambito") or "").strip()[:30] or None, "fuel": (row.get("comb_inicial") or "").strip()[:40] or None,
        })
    return fires


def _number_plain(value: str | None) -> float | None:
    """Coordenadas: vienen con punto decimal (a diferencia de la superficie, que usa coma)."""
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


async def fetch_fires(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    try:
        response = await client.get(FIRES_CSV_URL, timeout=30)
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise ConafError(f"El reporte de incendios de CONAF no respondió ({type(exc).__name__}).") from exc
    if "id,temporada,nombre,estado" not in response.text[:200]:
        raise ConafError("El reporte de incendios de CONAF cambió de formato.")
    return parse_fires(response.text)
