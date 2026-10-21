"""Guarda de las cifras de Historia: cada número con su fuente, su fecha y su unidad.

`web/data/cases.json` alimenta la vista Historia y `casos.js` publica la última revisión
de cada cifra. Esta prueba es de solo lectura: audita el catálogo, no lo corrige. Si
encuentra un dato malo, se arregla el dato en otro encargo.

Las fechas conservan la precisión de la fuente: día (`YYYY-MM-DD`), mes (`YYYY-MM`), año
(`YYYY`) o un marcador explícito (`s. f.` = sin fecha, `posterior` = posterior al hecho).
No se inventa un día que la fuente no entrega; la guarda rechaza fechas imposibles o
futuras, no la falta de precisión. La fecha de hoy se calcula en `America/Santiago`.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.og import MAP_BOUNDS

DATA = Path(__file__).resolve().parent.parent / "web" / "data" / "cases.json"
CHILE_TZ = ZoneInfo("America/Santiago")
KINDS = {"oficial", "prensa", "estudio"}
FECHAS_SIN_DIA = {"s. f.", "posterior"}
SLUG = re.compile(r"[a-z0-9-]+")
ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
SATELITE = re.compile(r"G\d{2}")
FECHA_DIA = re.compile(r"\d{4}-\d{2}-\d{2}")
FECHA_MES = re.compile(r"\d{4}-\d{2}")
FECHA_ANIO = re.compile(r"\d{4}")
NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


def _hoy_chile() -> date:
    return datetime.now(CHILE_TZ).date()


def _lista_cases(cases) -> list | None:
    """Acepta la lista de casos o el objeto completo de cases.json."""
    if isinstance(cases, dict):
        cases = cases.get("cases")
    return cases if isinstance(cases, list) else None


def _es_lista_numeros(value, n: int) -> bool:
    return isinstance(value, list) and len(value) == n and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)


def _fecha_utc(value) -> datetime | None:
    if not isinstance(value, str) or not ISO_UTC.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _problema_fecha(value, hoy: date) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "date vacía"
    value = value.strip()
    if value in FECHAS_SIN_DIA:
        return None
    if FECHA_DIA.fullmatch(value):
        try:
            fecha = date.fromisoformat(value)
        except ValueError:
            return f"date inválida {value!r}"
        return None if fecha <= hoy else f"date futura {value!r} (hoy {hoy.isoformat()} en Chile)"
    if FECHA_MES.fullmatch(value):
        anio, mes = map(int, value.split("-"))
        if not 1 <= mes <= 12:
            return f"date con mes inválido {value!r}"
        return None if (anio, mes) <= (hoy.year, hoy.month) else f"date futura {value!r} (hoy {hoy.isoformat()} en Chile)"
    if FECHA_ANIO.fullmatch(value):
        return None if int(value) <= hoy.year else f"date futura {value!r} (hoy {hoy.isoformat()} en Chile)"
    return f"date con forma no reconocida {value!r}"


def _numeros(value: str) -> list[float]:
    """Números en formato chileno: punto de miles y coma decimal."""
    out = []
    for token in NUMERO.findall(value):
        try:
            out.append(float(token.replace(".", "").replace(",", ".")))
        except ValueError:
            continue
    return out


def _tiene_m2(value: str) -> bool:
    return "m²" in value.lower() or bool(re.search(r"\bm2\b", value, re.IGNORECASE))


def _problemas_estructura(cases) -> list[str]:
    out = []
    items = _lista_cases(cases)
    if items is None:
        return ["cases: debe ser una lista"]
    if len(items) != 6:
        out.append(f"cases: se esperan 6 casos, hay {len(items)}")

    vistos = set()
    for i, case in enumerate(items):
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

        for key in ("title", "subtitle", "region"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                out.append(f"{ctx}: {key} vacío")

        start = _fecha_utc(case.get("start_utc"))
        end = _fecha_utc(case.get("end_utc"))
        if start is None:
            out.append(f"{ctx}: start_utc no es ISO con Z")
        if end is None:
            out.append(f"{ctx}: end_utc no es ISO con Z")
        if start and end and start >= end:
            out.append(f"{ctx}: start_utc debe ser anterior a end_utc")

        bbox = case.get("bbox")
        if not _es_lista_numeros(bbox, 4):
            out.append(f"{ctx}: bbox debe tener 4 números")
        else:
            west, south, east, north = bbox
            if west >= east:
                out.append(f"{ctx}: bbox oeste debe ser menor que este")
            if south >= north:
                out.append(f"{ctx}: bbox sur debe ser menor que norte")
            lon_min, lat_min, lon_max, lat_max = MAP_BOUNDS
            if not (lon_min <= west and east <= lon_max and lat_min <= south and north <= lat_max):
                out.append(f"{ctx}: bbox fuera de los márgenes de Chile {MAP_BOUNDS}")
            camera = case.get("camera")
            if not _es_lista_numeros(camera, 3):
                out.append(f"{ctx}: camera debe tener 3 números")
            else:
                lon, lat, altura = camera
                if not (west <= lon <= east and south <= lat <= north):
                    out.append(f"{ctx}: camera fuera del bbox")
                if altura <= 0:
                    out.append(f"{ctx}: camera con altura no positiva")

        goes = case.get("goes")
        if goes is None:
            if not isinstance(case.get("goes_note"), str) or not case["goes_note"].strip():
                out.append(f"{ctx}: goes null exige goes_note")
        elif isinstance(goes, dict):
            satelite = goes.get("satellite")
            if not isinstance(satelite, str) or not SATELITE.fullmatch(satelite):
                out.append(f"{ctx}: goes.satellite debe tener forma G##")
            cadencia = goes.get("cadence_min")
            if not isinstance(cadencia, (int, float)) or isinstance(cadencia, bool) or cadencia <= 0:
                out.append(f"{ctx}: goes.cadence_min debe ser positivo")
        else:
            out.append(f"{ctx}: goes debe ser un objeto o null")

        firms = case.get("firms_sources")
        if not isinstance(firms, list) or not firms:
            out.append(f"{ctx}: firms_sources no puede estar vacío")
        else:
            for fuente in firms:
                if not isinstance(fuente, str) or not fuente.endswith(("_SP", "_NRT")):
                    out.append(f"{ctx}: firms_sources con id inválido {fuente!r}")

    return out


def _problemas_cifras(cases, hoy: date) -> list[str]:
    out = []
    for case in _lista_cases(cases) or []:
        if not isinstance(case, dict):
            continue
        ctx = f"caso {case.get('id', '?')}"
        figures = case.get("figures")
        if not isinstance(figures, list) or not figures:
            out.append(f"{ctx}: figures no puede estar vacío")
            continue

        keys, labels = set(), set()
        for i, fig in enumerate(figures):
            if not isinstance(fig, dict):
                out.append(f"{ctx} figura #{i + 1}: no es un objeto")
                continue
            key, label = fig.get("key"), fig.get("label")
            fctx = f"{ctx} cifra {key!r}"
            if not isinstance(key, str) or not key.strip():
                out.append(f"{ctx} figura #{i + 1}: key vacía")
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

            revisions = fig.get("revisions")
            if not isinstance(revisions, list) or not revisions:
                out.append(f"{fctx}: sin revisiones")
                continue
            for j, rev in enumerate(revisions):
                rctx = f"{fctx} revisión {j + 1}"
                if not isinstance(rev, dict):
                    out.append(f"{rctx}: no es un objeto")
                    continue
                value = rev.get("value")
                if not isinstance(value, str) or not value.strip():
                    out.append(f"{rctx}: value vacío")
                source = rev.get("source")
                if not isinstance(source, str) or not source.strip():
                    out.append(f"{rctx}: source vacío")
                url = rev.get("url")
                if not isinstance(url, str) or not url.startswith("https://"):
                    out.append(f"{rctx}: url debe empezar con https://")
                if not isinstance(rev.get("kind"), str) or rev["kind"] not in KINDS:
                    out.append(f"{rctx}: kind debe ser uno de {sorted(KINDS)}")
                fecha = _problema_fecha(rev.get("date"), hoy)
                if fecha:
                    out.append(f"{rctx}: {fecha}")

    return out


def _problemas_unidades(cases) -> list[str]:
    out = []
    for case in _lista_cases(cases) or []:
        if not isinstance(case, dict):
            continue
        ctx = f"caso {case.get('id', '?')}"
        for fig in case.get("figures") or []:
            if not isinstance(fig, dict):
                continue
            texto = f"{fig.get('key', '')} {fig.get('label', '')}".lower()
            fctx = f"{ctx} cifra {fig.get('key', '?')!r}"
            for j, rev in enumerate(fig.get("revisions") or []):
                if not isinstance(rev, dict):
                    continue
                value = rev.get("value")
                if not isinstance(value, str) or not value.strip():
                    continue  # ya lo reporta _problemas_cifras
                rctx = f"{fctx} revisión {j + 1}"
                numeros = _numeros(value)

                if "superficie" in texto:
                    if not re.search(r"\bha\b", value, re.IGNORECASE):
                        out.append(f"{rctx}: superficie sin unidad «ha»")
                    if _tiene_m2(value):
                        out.append(f"{rctx}: superficie en m²; el catálogo publica hectáreas")
                    if not numeros:
                        out.append(f"{rctx}: superficie sin número")
                    for n in numeros:
                        if not 1 <= n <= 1_000_000:
                            out.append(f"{rctx}: superficie {n:g} fuera del rango 1–1.000.000 ha")

                if "fallecidas" in texto:
                    if not numeros:
                        out.append(f"{rctx}: fallecidas sin número")
                    for n in numeros:
                        if not n.is_integer():
                            out.append(f"{rctx}: fallecidas {n:g} no es un entero")
                        if n >= 1_000:
                            out.append(f"{rctx}: fallecidas {n:g} ≥ 1.000")

                if "viviendas" in texto:
                    if not numeros:
                        out.append(f"{rctx}: viviendas sin número")
                    for n in numeros:
                        if n >= 100_000:
                            out.append(f"{rctx}: viviendas {n:g} ≥ 100.000")

    return out


def _problemas_contexto(cases) -> list[str]:
    out = []
    for case in _lista_cases(cases) or []:
        if not isinstance(case, dict):
            continue
        ctx = f"caso {case.get('id', '?')}"
        for campo in ("context", "lessons", "references"):
            items = case.get(campo)
            if items is None:
                continue
            if not isinstance(items, list):
                out.append(f"{ctx}: {campo} debe ser una lista")
                continue
            for i, item in enumerate(items):
                ictx = f"{ctx} {campo} #{i + 1}"
                if not isinstance(item, dict):
                    out.append(f"{ictx}: no es un objeto")
                    continue
                if campo in ("context", "lessons") and (not isinstance(item.get("text"), str) or not item["text"].strip()):
                    out.append(f"{ictx}: text vacío")
                if campo == "context":
                    if not isinstance(item.get("verified"), bool):
                        out.append(f"{ictx}: verified debe ser booleano")
                if campo == "lessons":
                    if not isinstance(item.get("source"), str) or not item["source"].strip():
                        out.append(f"{ictx}: source vacío")
                    if not isinstance(item.get("url"), str) or not item["url"].startswith("https://"):
                        out.append(f"{ictx}: url debe empezar con https://")
                if campo == "references":
                    if not isinstance(item.get("url"), str) or not item["url"].startswith("https://"):
                        out.append(f"{ictx}: url debe empezar con https://")

    return out


def problemas(cases, hoy: date | None = None) -> list[str]:
    """Todos los problemas del catálogo; lista vacía si cumple el contrato."""
    hoy = hoy or _hoy_chile()
    return [
        *_problemas_estructura(cases),
        *_problemas_cifras(cases, hoy),
        *_problemas_unidades(cases),
        *_problemas_contexto(cases),
    ]


def _catalogo() -> list:
    return json.loads(DATA.read_text(encoding="utf-8"))["cases"]


def test_estructura_minima():
    assert _problemas_estructura(_catalogo()) == []


def test_cifras_con_fuente_fecha_y_tipo():
    assert _problemas_cifras(_catalogo(), _hoy_chile()) == []


def test_unidades_coherentes():
    assert _problemas_unidades(_catalogo()) == []


def test_contexto_lecciones_y_referencias():
    assert _problemas_contexto(_catalogo()) == []


def test_catalogo_sin_problemas():
    assert problemas(_catalogo()) == []


def test_roturas_detectadas():
    cases = copy.deepcopy(_catalogo())

    ultima = cases[0]["figures"][0]["revisions"][-1]
    del ultima["url"]
    ultima["date"] = "2099-01-01"

    superficie = next(f for f in cases[0]["figures"] if "superficie" in f["label"].lower())
    superficie["revisions"][-1]["value"] = "12000000 m²"

    encontrados = problemas(cases)
    assert len(set(encontrados)) >= 3
    assert any("url" in p for p in encontrados)
    assert any("futura" in p for p in encontrados)
    assert any("m²" in p for p in encontrados)
