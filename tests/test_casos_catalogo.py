"""Guarda del catálogo curado de la Historia: cada caso cae en Chile y dice lo que dice.

Lee `web/data/cases.json` y `web/data/regiones.geojson` sin red. Para cada caso
comprueba que la región exista en el catálogo de las 16 regiones, que el `bbox`
quede dentro del encuadre continental/insular de Chile, que `start_utc < end_utc`
en ISO con `Z`, que cada cifra traiga valor, fuente, enlace https y una fecha
coherente con el caso, que la cadencia GOES sea un múltiplo de 5 entre 5 y 60 y
que el caso traiga todas las claves que la ficha necesita (CASE-03).

Criterios que conviene saber:

- El encuadre `-109,5 <= w < e <= -66,0` y `-56,0 <= s < n <= -17,0` incluye
  Isla de Pascua (-109,45) y deja fuera el Pacífico abierto. Es un poco más
  estricto que el `-110..-66` de `test_datos_publicados.py`. Como el encuadre
  solo no distingue un rectángulo entero en Argentina, además al menos una
  esquina o el centro del `bbox` debe caer en una comuna chilena (el mismo
  criterio de puntos de `test_territorio.py`).
- Las fechas parciales (`AAAA`, `AAAA-MM`) se comparan por su primer día.
  «s. f.» y «posterior» son marcas editoriales del catálogo y no se pueden
  situar en el calendario: se aceptan solo esas dos cadenas exactas.
- La ventana posterior al cierre es de 730 días, no 400: un balance consolidado
  puede publicarse más de un año después del incendio (la cifra de la Fiscalía
  para Viña 2024 es del 2025-05-22, 472 días después; el total de la temporada
  2022-2023 se publicó en 2024-11, 625 días después). Con 400 días el catálogo
  real no pasaría y habría que falsear fechas; la cota sigue rechazando una
  fecha muy posterior (por ejemplo, 2026 en un caso de 2023).
"""

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from backend.geo import territory

DATA = Path(__file__).resolve().parent.parent / "web" / "data"

# Encuadre continental/insular de Chile: incluye Rapa Nui y excluye el Pacífico abierto.
LON_MIN, LON_MAX = -109.5, -66.0
LAT_MIN, LAT_MAX = -56.0, -17.0

# 400 días antes del inicio; después se admite un balance consolidado tardío.
DIAS_ANTES = 400
DIAS_DESPUES = 730

_FECHA_COMPLETA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FECHA_PARCIAL = re.compile(r"^\d{4}(-\d{2})?$")
_MARCAS_SIN_FECHA = {"s. f.", "posterior"}


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


CASOS = _load("cases.json")["cases"]
REGIONES = {f["properties"]["name"] for f in _load("regiones.geojson")["features"]}
COMUNAS = {c["name"] for c in _load("comunas-index.json")}
IDS = [c.get("id", f"caso-{i}") for i, c in enumerate(CASOS)]

# Casos que no ocurrieron en una comuna concreta y cuyo `subtitle` no puede
# nombrar ninguna: id → motivo. Hoy está vacío porque los seis casos nombran al
# menos una comuna; si un caso nuevo no cae en comuna, se declara aquí con su
# motivo en vez de bajar la guarda para todos (HIST-02).
SIN_LUGAR_EN_SUBTITULO: dict[str, str] = {}

# Claves que la ficha de `web/js/views/casos.js` usa sin defensa. Un caso nuevo que
# omita una de ellas compila igual y rompe la vista; la guarda lo detiene antes.
CLAVES = (
    "id",
    "title",
    "subtitle",
    "region",
    "scope",
    "start_utc",
    "end_utc",
    "bbox",
    "camera",
    "figures",
    "context",
    "references",
    "lessons",
    "goes",
    "firms_sources",
)
SCOPES = {"fire", "complex", "episode", "season"}


def _fail(caso, campo, mensaje):
    raise AssertionError(f"{caso.get('id', 'caso sin id')}: {campo}: {mensaje}")


def _partes_region(texto):
    """Descompone «A, B y C» en regiones conocidas; None si no calza.

    Se prueban los dos separadores porque «Arica y Parinacota» contiene « y »
    dentro del propio nombre. La coincidencia exacta con una región gana.
    """
    if texto in REGIONES:
        return [texto]
    for separador in (", ", " y "):
        desde = 0
        while (corte := texto.find(separador, desde)) != -1:
            izquierda, derecha = texto[:corte], texto[corte + len(separador) :]
            if izquierda and derecha:
                a, b = _partes_region(izquierda), _partes_region(derecha)
                if a is not None and b is not None:
                    return a + b
            desde = corte + 1
    return None


def _texto_region(partes):
    """Formato canónico: comas y « y » antes de la última; comas si un nombre trae « y »."""
    if len(partes) == 1:
        return partes[0]
    if any(" y " in parte for parte in partes):
        return ", ".join(partes)
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def _parse_utc(caso, campo):
    valor = caso.get(campo)
    if not isinstance(valor, str) or not valor.endswith("Z"):
        _fail(caso, campo, f"debe ser ISO con Z: {valor!r}")
    try:
        return datetime.fromisoformat(valor[:-1] + "+00:00")
    except ValueError:
        _fail(caso, campo, f"no es ISO válido: {valor!r}")


def _fecha_revision(caso, campo, valor):
    if valor in _MARCAS_SIN_FECHA:
        return None
    if not isinstance(valor, str):
        _fail(caso, campo, f"fecha no es texto: {valor!r}")
    if _FECHA_COMPLETA.match(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            _fail(caso, campo, f"fecha inválida: {valor!r}")
    if _FECHA_PARCIAL.match(valor):
        partes = valor.split("-")
        try:
            return date(int(partes[0]), int(partes[1]) if len(partes) == 2 else 1, 1)
        except ValueError:
            _fail(caso, campo, f"fecha inválida: {valor!r}")
    _fail(
        caso,
        campo,
        f"fecha no reconocida: {valor!r}; se aceptan AAAA-MM-DD, AAAA-MM, AAAA, «s. f.» o «posterior»",
    )


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_region_existe_y_esta_bien_escrita(caso):
    texto = caso.get("region")
    if not isinstance(texto, str) or not texto.strip():
        _fail(caso, "region", f"vacía o no es texto: {texto!r}")
    texto = texto.strip()
    partes = _partes_region(texto)
    if partes is None:
        _fail(caso, "region", f"{texto!r} no nombra solo regiones de Chile: {', '.join(sorted(REGIONES))}")
    if len(partes) != len(set(partes)):
        _fail(caso, "region", f"región repetida en {texto!r}")
    esperado = _texto_region(partes)
    if texto != esperado:
        _fail(caso, "region", f"formato no canónico: {texto!r}; se esperaba {esperado!r}")


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_bbox_dentro_de_chile(caso):
    bbox = caso.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        _fail(caso, "bbox", f"debe ser [oeste, sur, este, norte]: {bbox!r}")
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in bbox):
        _fail(caso, "bbox", f"con valores no numéricos: {bbox!r}")
    oeste, sur, este, norte = bbox
    if not (LON_MIN <= oeste < este <= LON_MAX):
        _fail(caso, "bbox", f"longitudes fuera de Chile ({LON_MIN}..{LON_MAX}) o invertidas: {bbox!r}")
    if not (LAT_MIN <= sur < norte <= LAT_MAX):
        _fail(caso, "bbox", f"latitudes fuera de Chile ({LAT_MIN}..{LAT_MAX}) o invertidas: {bbox!r}")
    puntos = [
        (sur, oeste),
        (sur, este),
        (norte, oeste),
        (norte, este),
        ((sur + norte) / 2, (oeste + este) / 2),
    ]
    if not any(territory().locate(lat, lon) for lat, lon in puntos):
        _fail(caso, "bbox", f"ninguna esquina ni el centro cae en una comuna de Chile: {bbox!r}")


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_fechas_del_caso(caso):
    inicio = _parse_utc(caso, "start_utc")
    fin = _parse_utc(caso, "end_utc")
    if inicio >= fin:
        _fail(caso, "start_utc", f"{inicio.isoformat()} no es anterior a end_utc ({fin.isoformat()})")


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_cifras_con_fuente_y_fecha(caso):
    desde = _parse_utc(caso, "start_utc").date() - timedelta(days=DIAS_ANTES)
    hasta = _parse_utc(caso, "end_utc").date() + timedelta(days=DIAS_DESPUES)
    figuras = caso.get("figures", [])
    if not isinstance(figuras, list):
        _fail(caso, "figures", f"debe ser lista: {figuras!r}")
    for figura in figuras:
        if not isinstance(figura, dict):
            _fail(caso, "figures[]", f"debe ser objeto: {figura!r}")
        clave = figura.get("key", "?")
        revisiones = figura.get("revisions")
        if not isinstance(revisiones, list) or not revisiones:
            _fail(caso, f"figures[{clave}].revisions", f"debe ser lista no vacía: {revisiones!r}")
        for i, revision in enumerate(revisiones):
            campo = f"figures[{clave}].revisions[{i}]"
            if not isinstance(revision, dict):
                _fail(caso, campo, f"debe ser objeto: {revision!r}")
            valor = revision.get("value")
            if not isinstance(valor, str) or not valor.strip():
                _fail(caso, f"{campo}.value", f"vacío o no es texto: {valor!r}")
            fuente = revision.get("source")
            if not isinstance(fuente, str) or not fuente.strip():
                _fail(caso, f"{campo}.source", f"vacío o no es texto: {fuente!r}")
            url = revision.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                _fail(caso, f"{campo}.url", f"debe empezar con https://: {url!r}")
            fecha = _fecha_revision(caso, f"{campo}.date", revision.get("date"))
            if fecha is not None and not (desde <= fecha <= hasta):
                _fail(
                    caso,
                    f"{campo}.date",
                    f"{revision.get('date')!r} ({fecha}) fuera de la ventana {desde}..{hasta} del caso "
                    f"({DIAS_ANTES} días antes del inicio, {DIAS_DESPUES} después del cierre)",
                )


def _nombra_comuna(texto):
    """Alguna comuna del índice (345 comunas) aparece como palabra completa."""
    return any(re.search(rf"(?<!\w){re.escape(nombre)}(?!\w)", texto) for nombre in COMUNAS)


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_subtitle_nombra_un_lugar(caso):
    """El subtítulo es lo que ve el vecino: debe nombrar al menos un lugar
    reconocible (una comuna del índice), no solo la región (HIST-02)."""
    if caso.get("id") in SIN_LUGAR_EN_SUBTITULO:
        return
    subtitulo = caso.get("subtitle")
    if not isinstance(subtitulo, str) or not subtitulo.strip():
        _fail(caso, "subtitle", f"vacío o no es texto: {subtitulo!r}")
    if not _nombra_comuna(subtitulo):
        _fail(caso, "subtitle", f"{subtitulo!r} no nombra ninguna comuna de comunas-index.json")


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_caso_completo_para_la_ficha(caso):
    """Todas las claves de la ficha, con el tipo y el contenido que la vista espera."""
    faltan = [clave for clave in CLAVES if clave not in caso]
    if faltan:
        _fail(caso, "claves", f"faltan {', '.join(faltan)}")

    for campo in ("context", "references", "lessons", "firms_sources"):
        if not isinstance(caso[campo], list) or not caso[campo]:
            _fail(caso, campo, f"debe ser lista no vacía: {caso[campo]!r}")

    if caso["scope"] not in SCOPES:
        _fail(caso, "scope", f"{caso['scope']!r} no es uno de {', '.join(sorted(SCOPES))}")

    camara = caso["camera"]
    if not isinstance(camara, list) or len(camara) != 3:
        _fail(caso, "camera", f"debe ser [lon, lat, altura]: {camara!r}")
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in camara):
        _fail(caso, "camera", f"con valores no numéricos: {camara!r}")

    for i, item in enumerate(caso["context"]):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            _fail(caso, f"context[{i}]", f"falta un text no vacío: {item!r}")
        if not isinstance(item.get("verified"), bool):
            _fail(caso, f"context[{i}].verified", f"debe ser booleano: {item.get('verified')!r}")

    for i, item in enumerate(caso["references"]):
        if not isinstance(item, dict) or not isinstance(item.get("label"), str) or not item["label"].strip():
            _fail(caso, f"references[{i}]", f"falta un label no vacío: {item!r}")
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            _fail(caso, f"references[{i}].url", f"debe empezar con https://: {url!r}")

    for i, item in enumerate(caso["lessons"]):
        for campo in ("text", "source"):
            if not isinstance(item, dict) or not isinstance(item.get(campo), str) or not item[campo].strip():
                _fail(caso, f"lessons[{i}]", f"falta un {campo} no vacío: {item!r}")
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            _fail(caso, f"lessons[{i}].url", f"debe empezar con https://: {url!r}")


def test_la_guarda_detecta_un_caso_incompleto():
    """Sin las claves de la ficha, la guarda falla; no solo pasa con los seis casos reales."""
    incompleto = {
        "id": "sin-claves",
        "context": [],
        "references": [],
        "lessons": [],
        "firms_sources": [],
        "camera": [1, 2],
        "scope": "otro",
    }
    with pytest.raises(AssertionError, match="faltan"):
        test_caso_completo_para_la_ficha(incompleto)


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_goes_cadence(caso):
    goes = caso.get("goes")
    if goes is None:
        return
    if not isinstance(goes, dict):
        _fail(caso, "goes", f"debe ser objeto o null: {goes!r}")
    cadencia = goes.get("cadence_min")
    if not isinstance(cadencia, int) or isinstance(cadencia, bool):
        _fail(caso, "goes.cadence_min", f"debe ser entero: {cadencia!r}")
    if not (5 <= cadencia <= 60 and cadencia % 5 == 0):
        _fail(caso, "goes.cadence_min", f"debe estar entre 5 y 60 y ser divisible por 5: {cadencia!r}")
