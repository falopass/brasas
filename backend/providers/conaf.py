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
import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from shapely import unary_union
from shapely.geometry import Polygon

from backend.geo import territory

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
    """Superficie en hectáreas, decidiendo el formato en cada fila.

    CONAF publica coma decimal y punto de miles («1.234,50»), pero si algún día publica
    «1234.5» hay que leerlo como decimal y no como 12.345 ha. Reglas:
    - con los dos separadores, el último es el decimal;
    - si la parte entera es cero («0.500»), el separador es decimal aunque le sigan 3 dígitos:
      media hectárea no puede convertirse en quinientas;
    - un solo separador seguido de 3 dígitos es de miles;
    - un solo separador seguido de 1 o 2 dígitos es decimal.
    """
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace(" ", "").replace("\u00a0", "")
    try:
        if "." in text and "," in text:
            decimal = "," if text.rfind(",") > text.rfind(".") else "."
            thousands = "." if decimal == "," else ","
            return float(text.replace(thousands, "").replace(decimal, "."))
        for separator in (".", ","):
            if separator in text:
                left, _, right = text.rpartition(separator)
                if not left or separator * 2 in text:
                    continue
                if left.lstrip("+-").strip("0") == "":     # 0.500 es media hectárea, no quinientas
                    return float(text.replace(",", "."))
                if len(right) == 3:
                    return float(text.replace(separator, ""))
                return float(text.replace(",", "."))
        return float(text)
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
            # FIX-14: con la detección y el aviso de CONAF se puede medir cuántos minutos antes llega BRASA.
            "detected_at": _local(row.get("f_deteccion")), "alerted_at": _local(row.get("f_aviso")),
            "dispatched_at": _local(row.get("f_despacho")), "season": (row.get("temporada") or "").strip()[:20] or None,
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


async def fetch_fires(client: httpx.AsyncClient, etag: str | None = None) -> dict[str, Any]:
    """Descarga el CSV de incendios de CONAF con solicitud condicional.

    El archivo se descargaba entero en cada ciclo (cada 30 minutos) sin necesidad: si no cambió,
    ``If-None-Match`` devuelve 304 y no hay nada que parsear ni guardar. Devuelve un diccionario con
    ``fires``, el ``etag`` vigente (para el ciclo siguiente) y ``not_modified``.
    """
    headers = {"If-None-Match": etag} if etag else {}
    try:
        response = await client.get(FIRES_CSV_URL, headers=headers, timeout=30)
        if response.status_code == 304:
            return {"fires": [], "etag": etag, "not_modified": True}
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise ConafError(f"El reporte de incendios de CONAF no respondió ({type(exc).__name__}).") from exc
    if "id,temporada,nombre,estado" not in response.text[:200]:
        raise ConafError("El reporte de incendios de CONAF cambió de formato.")
    return {"fires": parse_fires(response.text), "etag": response.headers.get("etag") or etag, "not_modified": False}


# ------------------------------------------- condiciones oficiales del «Pronóstico de Riesgo» (GEPRIF)
#
# Los cinco servicios de condiciones del tablero «Pronóstico de Riesgo» de GEPRIF publican
# cada día cinco capas (día 0 a 4) con el territorio disuelto por clase en una grilla de
# ~2 km: cada fila es un polígono que junta `count_` celdas de la misma clase (`label`).
# El significado de la clase cambia por variable: en PI es el techo del rango porcentual y
# en las demás un número de clase; los textos los muestra la interfaz.
#
# El resumen por comuna guarda la peor clase presente dentro de la comuna —la más alta en
# probabilidad de ignición, viento y temperatura; la más seca en humedad del aire y del
# combustible— junto a cuántas celdas la alcanzan. La geometría se pide simplificada (~2 km),
# así que los bordes de clase pueden moverse una celda: es un resumen, no la grilla.
CONDICIONES_VARS = ("PI", "HC", "VV", "HR", "TP")
CONDICIONES_SOURCE = "CONAF · condiciones de pronóstico (GEPRIF)"
CONDICIONES_CATALOG_URL = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services"
CONDICIONES_DASHBOARD_URL = "https://www.arcgis.com/apps/dashboards/06a31e138f5c40efbd577c1993154ce5"
# La clase que más favorece al fuego: máxima en ignición, viento y temperatura; mínima en
# humedad relativa y del combustible fino muerto.
CONDICIONES_WORST: dict[str, Any] = {"PI": max, "HC": min, "VV": max, "HR": min, "TP": max}
CONDICIONES_SIMPLIFY_DEG = 0.02   # ~2 km, como la celda de la grilla
CONDICIONES_MAX_PAGES = 50


def _condiciones_url(var: str, layer_id: int | None = None) -> str:
    url = f"{CONDICIONES_CATALOG_URL}/{var}/FeatureServer"
    return url if layer_id is None else f"{url}/{layer_id}/query"


async def list_condicion_layers(client: httpx.AsyncClient) -> dict[str, list[tuple[int, str]]]:
    """Capas de cada servicio (id y nombre, que lleva la fecha): la firma barata de «cambió algo»."""
    layers: dict[str, list[tuple[int, str]]] = {}
    for var in CONDICIONES_VARS:
        try:
            response = await client.get(_condiciones_url(var), params={"f": "json"}, timeout=30)
            response.raise_for_status()
            data = response.json()
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            raise ConafError(f"El servicio {var} de CONAF no respondió ({type(exc).__name__}).") from exc
        if "error" in data:
            raise ConafError(f"El servicio {var} de CONAF devolvió un error ({data['error'].get('code')}).")
        layers[var] = [(int(layer["id"]), str(layer["name"])) for layer in data.get("layers", [])]
    return layers


def condiciones_signature(layers: dict[str, list[tuple[int, str]]]) -> str:
    """Texto comparable de las capas vigentes: cambia cuando CONAF publica un día nuevo."""
    return json.dumps(layers, separators=(",", ":"))


async def fetch_condicion_layer(client: httpx.AsyncClient, var: str, layer_id: int) -> list[dict[str, Any]]:
    """Una capa diaria completa, en páginas: atributos y geometría simplificada (~2 km)."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {"where": "1=1", "outFields": "date,var,label,count_", "returnGeometry": "true",
                  "outSR": "4326", "maxAllowableOffset": CONDICIONES_SIMPLIFY_DEG, "geometryPrecision": "4",
                  "orderByFields": "FID", "resultOffset": offset, "resultRecordCount": PAGE, "f": "json"}
        try:
            response = await client.get(_condiciones_url(var, layer_id), params=params, timeout=120)
            response.raise_for_status()
            data = response.json()
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            raise ConafError(f"La capa {var}/{layer_id} de CONAF no respondió ({type(exc).__name__}).") from exc
        if "error" in data:
            raise ConafError(f"La capa {var}/{layer_id} de CONAF devolvió un error ({data['error'].get('code')}).")
        batch = data.get("features", [])
        rows += batch
        if not data.get("exceededTransferLimit") or not batch or offset > CONDICIONES_MAX_PAGES * PAGE:
            return rows
        offset += len(batch)


def _polygon_from_rings(rings: list) -> Any | None:
    """Anillos Esri → geometría, por la regla par-impar (dentro = cubierto por un número impar de anillos).

    Los polígonos llegan disueltos con partes, agujeros e islas, y el giro de sus anillos no
    sigue el convenio (hay exteriores en ambos sentidos). En vez de fiarse del giro se mide la
    profundidad de cada anillo —en cuántos anillos mayores está contenido—: profundidad par es
    parte, impar es agujero. El resultado es unión(partes) menos unión(agujeros).
    """
    polys = []
    for ring in rings:
        if len(ring) < 4:
            continue
        try:
            poly = Polygon(ring)
        except (ValueError, TypeError):
            continue
        if poly.is_empty:
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
            if poly.is_empty:
                continue
        polys.append(poly)
    if not polys:
        return None
    ordered = sorted(polys, key=lambda p: -abs(p.area))
    exteriors, holes = [], []
    for i, poly in enumerate(ordered):
        if not i:
            exteriors.append(poly)
            continue
        point = poly.representative_point()
        depth = sum(1 for outer in ordered[:i] if outer.covers(point))
        (exteriors if depth % 2 == 0 else holes).append(poly)
    geom = unary_union(exteriors)
    if holes:
        geom = geom.difference(unary_union(holes))
    return None if geom.is_empty else geom


def summarize_condiciones(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filas por comuna, día y variable: la peor clase presente en la comuna y cuántas celdas la tienen.

    `cells_total` suma las celdas de todos los polígonos que tocan la comuna, así que en los
    bordes puede contar de más (un polígono a caballo entre dos comunas cuenta sus celdas en
    las dos). Sirve para decir «en parte de la comuna», no como superficie exacta.
    """
    t = territory()
    out: dict[tuple[int, str, str], dict[str, Any]] = {}
    for feature in features:
        attrs = feature.get("attributes") or {}
        rings = (feature.get("geometry") or {}).get("rings")
        try:
            day, var, label = str(attrs["date"])[:10], str(attrs["var"]).strip().upper(), int(attrs["label"])
            cells = max(1, int(attrs.get("count_") or 1))
        except (KeyError, TypeError, ValueError):
            continue
        if len(day) != 10 or var not in CONDICIONES_WORST or not rings:
            continue
        geom = _polygon_from_rings(rings)
        if geom is None:
            continue
        for comuna in t.comunas_in(geom):
            item = out.setdefault((comuna.code, day, var), {"comuna_code": comuna.code, "date": day, "var": var,
                                                            "label": label, "cells": 0, "cells_total": 0})
            item["cells_total"] += cells
            if label == item["label"]:
                item["cells"] += cells
            elif CONDICIONES_WORST[var](label, item["label"]) == label:
                item["label"], item["cells"] = label, cells
    return sorted(out.values(), key=lambda i: (i["date"], i["comuna_code"], i["var"]))
