"""CONAF Botón Rojo: pronóstico oficial a 5 días de condiciones favorables para incendios, por comuna.

Capa pública de ArcGIS Online del Departamento de Desarrollo e Investigación (Gerencia de Protección contra
Incendios Forestales) de CONAF, la misma que alimenta su tablero «Botón Rojo». Cada fila es una comuna, un día y una
cantidad de horas en condición Botón Rojo, con la superficie que la cumple. Aquí se resume por comuna y día:
máximo de horas, hectáreas y proporción de la comuna.

Botón Rojo indica CONDICIONES favorables para que un incendio se inicie y propague, nunca un incendio detectado.
La información es propiedad de CONAF: se muestra con su nombre y enlace, sin presentarla como propia.
"""
from __future__ import annotations

from typing import Any

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
