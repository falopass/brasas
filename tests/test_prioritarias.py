"""OFI-05: estructura de web/data/prioritarias.json (comunas prioritarias CONAF)."""

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "web" / "data" / "prioritarias.json").read_text(encoding="utf-8"))
INDEX = json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text(encoding="utf-8"))
CODIGOS = {c["code"] for c in INDEX}

# Dominios donde CONAF/GEPRIF publican documentos oficiales. Se aceptan
# subdominios (www.conaf.cl, avisoenlinea.conaf.cl, sit.conaf.cl...).
HOSTS_OFICIALES = ("conaf.cl", "conaf.gob.cl", "geprif.maps.arcgis.com", "deigeprif.com")


def _es_fuente_oficial(url):
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    host = urlsplit(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in HOSTS_OFICIALES)


def test_json_parseable_y_verified_booleano():
    assert isinstance(DATA, dict)
    assert isinstance(DATA["verified"], bool)
    assert isinstance(DATA["comunas"], list)


def test_sin_verificar_lista_vacia():
    if not DATA["verified"]:
        assert DATA["comunas"] == [], "una lista sin verificar no puede publicar comunas"
        assert str(DATA.get("note") or "").strip(), "una lista sin verificar debe explicar qué falta en 'note'"


def test_verificada_exige_fecha_valida():
    if not DATA["verified"]:
        return
    fecha = DATA.get("fetched_at")
    assert isinstance(fecha, str), f"verified exige fetched_at con fecha: {fecha!r}"
    date.fromisoformat(fecha)


def test_comunas_verificadas_validas():
    if not DATA["verified"]:
        return
    assert DATA["comunas"], "verified en true exige al menos una comuna"
    vistos = set()
    for comuna in DATA["comunas"]:
        cod = comuna["cod_comuna"]
        assert re.fullmatch(r"\d{5}", cod), f"cod_comuna inválido: {cod!r}"
        assert cod not in vistos, f"cod_comuna duplicado: {cod}"
        vistos.add(cod)
        assert comuna["nombre"].strip(), f"nombre vacío para {cod}"
        assert int(cod) in CODIGOS, f"cod_comuna {cod} no existe en comunas-index.json"


def test_verificada_exige_fuente_oficial():
    if not DATA["verified"]:
        return
    assert _es_fuente_oficial(DATA.get("source_url")), (
        f"source_url no es https ni apunta a un dominio oficial ({', '.join(HOSTS_OFICIALES)}): {DATA.get('source_url')!r}"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://ejemplo.com/lista",
        "http://www.conaf.cl/inseguro",
        "https://conaf.cl.evil.com/lista",
        "https://evilconaf.cl/lista",
        "",
        None,
    ],
)
def test_fuente_no_oficial_se_rechaza(url):
    assert not _es_fuente_oficial(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://conaf.cl/documento.pdf",
        "https://www.conaf.cl/noticia/",
        "https://avisoenlinea.conaf.cl/documentos/plan.pdf",
        "https://conaf.gob.cl/resolucion.pdf",
        "https://geprif.maps.arcgis.com/home/item.html?id=abc123",
        "https://deigeprif.com/listado",
    ],
)
def test_fuente_oficial_se_acepta(url):
    assert _es_fuente_oficial(url)
