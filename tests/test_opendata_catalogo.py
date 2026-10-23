"""DAT-08: el catálogo /api/opendata/catalog es legible por máquina y nunca miente:
cada capa declara fuente, licencia y campos, y cada `path` responde 200."""
from backend.routes import opendata


def test_catalog_lista_todas_las_capas(make_client):
    with make_client() as client:
        body = client.get("/api/opendata/catalog").json()
    assert body["datasets"], "catálogo vacío"
    for d in body["datasets"]:
        for clave in ("id", "title", "path", "format", "source", "license", "cadence", "fields", "description"):
            assert d.get(clave) not in (None, "", []), f"{d['id']}.{clave} vacío"
        assert d["format"] in ("geojson", "json")


def test_cada_path_del_catalogo_responde(make_client):
    with make_client() as client:
        for d in client.get("/api/opendata/catalog").json()["datasets"]:
            r = client.get(d["path"])
            assert r.status_code == 200, f"{d['path']} → {r.status_code}"


def test_ninguna_capa_sin_licencia():
    """Guarda contra la desincronización: una entrada nueva sin license rompe la suite."""
    for d in opendata.DATASETS:
        assert d.get("license"), f"{d['id']} sin licencia declarada"
        assert d.get("source"), f"{d['id']} sin fuente"


def test_catalogo_cubre_las_mismas_capas_que_el_indice(make_client):
    with make_client() as client:
        idx = {d["id"] for d in client.get("/api/opendata").json()["datasets"]}
        cat = {d["id"] for d in client.get("/api/opendata/catalog").json()["datasets"]}
    assert idx == cat, f"desincronizados: índice {idx ^ cat}"
