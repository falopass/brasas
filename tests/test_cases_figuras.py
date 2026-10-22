"""Guarda de las cifras de Historia: fuente, unidad, cámara y fechas imposibles.

`test_casos_catalogo.py` valida la región, el bbox, la ventana de fechas de cada cifra,
el `scope` y la cadencia GOES, y delega aquí el valor, la fuente y la URL https de cada
revisión, el contenido de `context`/`references`/`lessons` y el resto del contrato:
slug del caso, título, fechas del caso, cámara, satélite GOES, fuentes FIRMS, unicidad
de key/label, tipo de fuente, fechas futuras y unidades (ha, fallecidas, viviendas).

No corrige datos: audita `web/data/cases.json` y devuelve la lista de problemas.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parent.parent / "web" / "data" / "cases.json"
CHILE_TZ = ZoneInfo("America/Santiago")
KINDS = {"oficial", "prensa", "estudio"}
SLUG = re.compile(r"[a-z0-9-]+")
SATELITE = re.compile(r"G\d{2}")
ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
FECHA_DIA = re.compile(r"\d{4}-\d{2}-\d{2}")
FECHA_MES = re.compile(r"\d{4}-\d{2}")
FECHA_ANIO = re.compile(r"\d{4}")
NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


def _lista_numeros(value, n: int) -> bool:
    return isinstance(value, list) and len(value) == n and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)


def _fecha_utc(value) -> datetime | None:
    if not isinstance(value, str) or not ISO_UTC.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _numeros(value: str) -> list[float]:
    """Números en formato chileno: punto de miles y coma decimal."""
    out = []
    for token in NUMERO.findall(value):
        try:
            out.append(float(token.replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    return out


def _es_futura(value, hoy: date) -> bool:
    try:
        if FECHA_DIA.fullmatch(value):
            return date.fromisoformat(value) > hoy
        if FECHA_MES.fullmatch(value):
            return tuple(map(int, value.split("-"))) > (hoy.year, hoy.month)
        if FECHA_ANIO.fullmatch(value):
            return int(value) > hoy.year
    except (TypeError, ValueError):
        return False
    return False


def _unidades(texto: str, value: str, ctx: str, out: list[str]) -> None:
    numeros = _numeros(value)
    if "superficie" in texto:
        if not re.search(r"\bha\b", value, re.IGNORECASE):
            out.append(f"{ctx}: superficie sin unidad «ha»")
        if "m²" in value.lower() or re.search(r"\bm2\b", value, re.IGNORECASE):
            out.append(f"{ctx}: superficie en m²; el catálogo publica hectáreas")
        if not numeros:
            out.append(f"{ctx}: superficie sin número")
        for n in numeros:
            if not 1 <= n <= 1_000_000:
                out.append(f"{ctx}: superficie {n:g} fuera del rango 1–1.000.000 ha")
    if "fallecidas" in texto:
        if not numeros:
            out.append(f"{ctx}: fallecidas sin número")
        for n in numeros:
            if not n.is_integer():
                out.append(f"{ctx}: fallecidas {n:g} no es un entero")
            if n >= 1_000:
                out.append(f"{ctx}: fallecidas {n:g} ≥ 1.000")
    if "viviendas" in texto:
        if not numeros:
            out.append(f"{ctx}: viviendas sin número")
        for n in numeros:
            if n >= 100_000:
                out.append(f"{ctx}: viviendas {n:g} ≥ 100.000")


def problemas(cases, hoy: date | None = None) -> list[str]:
    """Problemas que no cubren las otras guardas del catálogo; lista vacía si todo calza."""
    hoy = hoy or datetime.now(CHILE_TZ).date()
    out, vistos = [], set()
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            out.append(f"caso #{i + 1}: no es un objeto")
            continue
        cid = case.get("id")
        ctx = f"caso {cid!r}" if cid else f"caso #{i + 1}"
        if not isinstance(cid, str) or not SLUG.fullmatch(cid):
            out.append(f"{ctx}: id debe ser un slug [a-z0-9-]+")
        elif cid in vistos:
            out.append(f"{ctx}: id duplicado")
        else:
            vistos.add(cid)

        if not isinstance(case.get("title"), str) or not case["title"].strip():
            out.append(f"{ctx}: title vacío")
        start, end = _fecha_utc(case.get("start_utc")), _fecha_utc(case.get("end_utc"))
        if start is None:
            out.append(f"{ctx}: start_utc no es ISO con Z")
        if end is None:
            out.append(f"{ctx}: end_utc no es ISO con Z")
        if start and end and start >= end:
            out.append(f"{ctx}: start_utc debe ser anterior a end_utc")

        camera = case.get("camera")
        if not _lista_numeros(camera, 3):
            out.append(f"{ctx}: camera debe tener 3 números")
        else:
            lon, lat, altura = camera
            if _lista_numeros(case.get("bbox"), 4):
                west, south, east, north = case["bbox"]
                if not (west <= lon <= east and south <= lat <= north):
                    out.append(f"{ctx}: camera fuera del bbox")
            if altura <= 0:
                out.append(f"{ctx}: camera con altura no positiva")

        goes = case.get("goes")
        if goes is None:
            if not isinstance(case.get("goes_note"), str) or not case["goes_note"].strip():
                out.append(f"{ctx}: goes null exige goes_note")
        elif not isinstance(goes, dict) or not isinstance(goes.get("satellite"), str) or not SATELITE.fullmatch(goes["satellite"]):
            out.append(f"{ctx}: goes.satellite debe tener forma G##")

        firms = case.get("firms_sources")
        if not isinstance(firms, list) or not firms:
            out.append(f"{ctx}: firms_sources no puede estar vacío")
        else:
            for fuente in firms:
                if not isinstance(fuente, str) or not fuente.endswith(("_SP", "_NRT")):
                    out.append(f"{ctx}: firms_sources con id inválido {fuente!r}")

        figures = case.get("figures")
        if not isinstance(figures, list) or not figures:
            out.append(f"{ctx}: figures no puede estar vacío")
            continue
        keys, labels = set(), set()
        for fig in figures:
            if not isinstance(fig, dict):
                continue
            key, label = fig.get("key"), fig.get("label")
            fctx = f"{ctx} cifra {key!r}"
            if not isinstance(key, str) or not key.strip():
                out.append(f"{ctx} figura sin key")
            elif key in keys:
                out.append(f"{fctx}: key duplicada")
            else:
                keys.add(key)
            if not isinstance(label, str) or not label.strip():
                out.append(f"{fctx}: label vacío")
            elif label in labels:
                out.append(f"{fctx}: label duplicado")
            else:
                labels.add(label)
            texto = f"{key} {label}".lower()
            revisions = fig.get("revisions")
            if not isinstance(revisions, list) or not revisions:
                out.append(f"{fctx}: sin revisiones")
                continue
            for rev in revisions:
                if not isinstance(rev, dict):
                    out.append(f"{fctx}: revisión no es un objeto")
                    continue
                value = rev.get("value")
                if not isinstance(value, str) or not value.strip():
                    out.append(f"{fctx}: value vacío")
                    continue
                if not isinstance(rev.get("source"), str) or not rev["source"].strip():
                    out.append(f"{fctx}: source vacío")
                if not isinstance(rev.get("url"), str) or not rev["url"].startswith("https://"):
                    out.append(f"{fctx}: url debe empezar con https://")
                if rev.get("kind") not in KINDS:
                    out.append(f"{fctx}: kind debe ser uno de {sorted(KINDS)}")
                if _es_futura(rev.get("date"), hoy):
                    out.append(f"{fctx}: date futura {rev['date']!r}")
                _unidades(texto, value, fctx, out)

        for campo in ("context", "lessons", "references"):
            items = case.get(campo)
            if items is None:
                continue
            if not isinstance(items, list):
                out.append(f"{ctx}: {campo} debe ser una lista")
                continue
            for j, item in enumerate(items):
                ictx = f"{ctx} {campo} #{j + 1}"
                if not isinstance(item, dict):
                    out.append(f"{ictx}: no es un objeto")
                    continue
                if campo in ("context", "lessons") and (not isinstance(item.get("text"), str) or not item["text"].strip()):
                    out.append(f"{ictx}: text vacío")
                if campo == "context" and not isinstance(item.get("verified"), bool):
                    out.append(f"{ictx}: verified debe ser booleano")
                if campo == "lessons" and (not isinstance(item.get("source"), str) or not item["source"].strip()):
                    out.append(f"{ictx}: source vacío")
                if campo in ("lessons", "references") and (not isinstance(item.get("url"), str) or not item["url"].startswith("https://")):
                    out.append(f"{ictx}: url debe empezar con https://")
    return out


def _catalogo() -> list:
    return json.loads(DATA.read_text(encoding="utf-8"))["cases"]


def test_catalogo_sin_problemas():
    assert problemas(_catalogo()) == []


def test_roturas_detectadas():
    cases = copy.deepcopy(_catalogo())
    cases[0]["title"] = ""
    cases[0]["camera"] = [999.0, 999.0, -1.0]  # fuera del bbox y sin altura
    cases[0]["figures"][0]["revisions"][-1]["kind"] = "blog"
    cases[0]["figures"][0]["revisions"][-1]["date"] = "2099-01-01"
    del cases[0]["figures"][0]["revisions"][-1]["source"]
    cases[0]["context"][0]["verified"] = "sí"
    superficie = next(f for c in cases for f in c["figures"] if "superficie" in f.get("label", "").lower())
    superficie["revisions"][-1]["value"] = "12000000 m²"

    encontrados = problemas(cases)
    for esperado in ("title vacío", "camera fuera del bbox", "altura no positiva", "kind", "futura", "source vacío", "verified", "m²"):
        assert any(esperado in p for p in encontrados), f"no se detectó «{esperado}»: {encontrados}"
