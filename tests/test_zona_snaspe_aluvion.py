"""ZONA-SNASPE-AGUA: área protegida en el resumen y terreno post-incendio en la lluvia.

`evaluar_terreno` es puro. El resumen de un lugar incluye `protected_area` (lo que
devuelve `protected_areas_near`). `GET /api/climate/lluvia` agrega `terreno` sin
quitar la señal, y solo pide el DEM si hay lluvia, cicatriz o relieve ya en caché.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from backend import lluvia
from backend.geo import territory
from backend.providers import elevation
from backend.routes import personal as personal_mod
from tests.conftest import json_response
from tests.test_lluvia import hourly
from tests.test_place_risk import _hourly, _open_meteo, _setup
from tests.test_scars import seed_incident

ROOT = Path(__file__).resolve().parents[1]
CIERRE = f"{lluvia.ETIQUETA} {lluvia.SENAPRED}"


def _senal(mm: float | None, iso: float | None = 1800.0, intensa: bool | None = None) -> dict:
    """Una señal mínima, con `intensa` alineada al umbral de `senal` salvo que se fuerce."""
    return {
        "mm_3h": mm,
        "isoterma_m": iso,
        "isoterma_alta": None if iso is None else iso >= lluvia.ISOTERMA_ALTA_M,
        "intensa": (mm is not None and mm >= lluvia.MM_3H_INTENSA) if intensa is None else intensa,
    }


def _cierra(texto: str) -> None:
    assert texto.endswith(CIERRE)
    assert lluvia.ETIQUETA in texto and "SENAPRED" in texto


@pytest.mark.parametrize(
    "senal, slope, scar, nivel",
    [
        (None, 20.0, 30.0, "sin_dato"),
        (_senal(None), 20.0, 30.0, "sin_dato"),
        (_senal(0.0), 20.0, 100.0, "bajo"),
        (_senal(4.9), 20.0, 100.0, "bajo"),
        (_senal(12.0), 0.0, 0.0, "bajo"),
        (_senal(12.0), None, None, "bajo"),
        (_senal(6.0), 7.9, 20.0, "bajo"),
        (_senal(5.0), 8.0, 1.0, "moderado"),
        (_senal(9.9), 8.0, 12.0, "moderado"),
        (_senal(12.0), 16.0, 0.0, "bajo"),
        (_senal(12.0), 0.0, 4.0, "moderado"),
        (_senal(10.0), 14.9, 1.0, "moderado"),
        (_senal(12.0, iso=3000.0), 10.0, 8.0, "alto"),
        (_senal(12.0), 15.0, 0.1, "alto"),
        (_senal(10.0), 15.0, 1.0, "alto"),
    ],
)
def test_evaluar_terreno_combina_lluvia_pendiente_y_cicatriz(senal, slope, scar, nivel):
    terreno = lluvia.evaluar_terreno(senal, slope, scar)
    assert terreno["nivel"] == nivel
    assert terreno["slope_deg"] == slope and terreno["scar_ha"] == scar
    _cierra(terreno["explicacion"])
    if slope is not None:
        assert f"{float(slope):.1f}°" in terreno["explicacion"]
    if scar is not None and scar > 0:
        assert f"{float(scar):.1f} ha" in terreno["explicacion"]
    else:
        assert "quemad" not in terreno["explicacion"].lower()
    if (
        slope is not None
        and senal
        and isinstance(senal.get("mm_3h"), (int, float))
        and (scar is None or scar <= 0)
    ):
        assert "No se registran huellas de calor recientes cerca de este punto." in terreno["explicacion"]
    if senal and isinstance(senal.get("mm_3h"), (int, float)):
        assert f"{float(senal['mm_3h']):.1f} mm" in terreno["explicacion"]


def test_la_fecha_del_incendio_no_cambia_el_nivel():
    senal = _senal(12.0)
    reciente = lluvia.evaluar_terreno(senal, 16.0, 10.0, dias_desde_incendio=30)
    viejo = lluvia.evaluar_terreno(senal, 16.0, 10.0, dias_desde_incendio=800)
    assert reciente["nivel"] == viejo["nivel"] == "alto"
    assert "Días desde el incendio: 30." in reciente["explicacion"]
    assert "Días desde el incendio: 800." in viejo["explicacion"]
    assert "Días desde el incendio" not in lluvia.evaluar_terreno(senal, 16.0, 10.0)["explicacion"]
    _cierra(reciente["explicacion"])
    _cierra(viejo["explicacion"])


def test_la_senal_real_de_lluvia_intensa_en_ladera_quemada_es_alta():
    """La misma ventana de `senal` (12 mm, isoterma baja) sube a alto con cicatriz y 16°."""
    senal = lluvia.senal(hourly([0.0, 4.0, 5.0, 3.0, 1.0]))
    assert senal["intensa"] is True and senal["mm_3h"] == 12.0
    terreno = lluvia.evaluar_terreno(senal, 16.0, 12.0)
    assert terreno["nivel"] == "alto"
    assert "Isoterma 0 °C: 1800 m." in terreno["explicacion"]
    _cierra(terreno["explicacion"])


def test_el_resumen_del_lugar_incluye_protected_area(make_client, web, monkeypatch):
    """`build_summary` guarda lo que devuelve `protected_areas_near`, también si no hay ninguna."""
    areas = [{
        "name": "Reserva Nacional Altos de Lircay",
        "category": "Reserva Nacional",
        "region": "Maule",
        "inside": False,
        "distance_km": 2.4,
    }]
    monkeypatch.setattr(personal_mod, "protected_areas_near", lambda lat, lon, max_km=5.0: list(areas))
    _open_meteo(web, hourly=_hourly(datetime.now(timezone.utc)))
    with make_client() as client:
        headers, (place_id,) = _setup(client, (-35.42, -71.66))
        body = client.get(f"/api/places/{place_id}/summary", headers=headers).json()
        assert body["protected_area"] == areas and body["status"]
        monkeypatch.setattr(personal_mod, "protected_areas_near", lambda lat, lon, max_km=5.0: [])
        headers, (otro,) = _setup(client, (-33.45, -70.66))
        vacio = client.get(f"/api/places/{otro}/summary", headers=headers).json()
    assert vacio["protected_area"] == []


def test_zona_exporta_la_linea_de_area_protegida_y_vecino_la_usa():
    zona = (ROOT / "web/js/views/zona.js").read_text(encoding="utf-8")
    vecino = (ROOT / "web/js/views/vecino.js").read_text(encoding="utf-8")
    assert "export function protectedAreaLine" in zona
    assert "protectedAreaLine(summary.protected_area)" in zona
    assert "Dentro de un área protegida del Estado:" in zona
    assert "dentro del polígono" in zona
    assert "https://www.conaf.cl/parques-nacionales/" in zona
    assert 'target="_blank" rel="noopener"' in zona
    assert "No se registran huellas de calor recientes cerca de este punto." in zona
    assert "Copernicus DEM GLO-90" in zona
    assert "las alertas oficiales de aluvión las emite SENAPRED" in zona
    funcion = zona.split("export function protectedAreaLine", 1)[1].split("function terrenoNota", 1)[0]
    assert "\u2014" not in funcion and "\u2014" not in zona.split("function terrenoNota", 1)[1].split("export function lluviaLine", 1)[0]
    assert "protectedAreaLine" in vecino
    assert "protectedAreaLine(data.protected_area)" in vecino


def _punto_talca() -> tuple[float, float]:
    centro = territory().by_code[7101].center  # lon, lat
    return centro[1], centro[0]


def _pronostico(web, mm: list[float], iso: float = 1800.0):
    n = len(mm)

    def handler(request):
        assert not request.url.path.endswith("/elevation"), "esta prueba no debe pegarle al DEM"
        return json_response({
            "hourly": {
                "time": [f"2026-10-20T{h:02d}:00" for h in range(n)],
                "precipitation": mm,
                "freezing_level_height": [iso] * n,
            },
        })

    web.add(lambda r: "open-meteo" in r.url.host, handler)


def test_lluvia_agrega_terreno_sin_quitar_la_senal(make_client, web, monkeypatch):
    lat, lon = _punto_talca()
    _pronostico(web, [0.0, 4.0, 5.0, 3.0, 1.0])
    llamadas: list[tuple[float, float]] = []

    async def slope(_db, _client, y, x):
        llamadas.append((y, x))
        return (16.0, 180.0)

    monkeypatch.setattr(elevation, "slope_aspect", slope)
    with make_client() as client:
        seed_incident(client.app.state.services.db, "cerca", lat=lat, lon=lon)
        body = client.get(f"/api/climate/lluvia?lat={lat}&lon={lon}").json()
        guardado = client.app.state.services.db.cache_get(f"lluvia:{round(lat, 1)}:{round(lon, 1)}")
    assert llamadas == [(lat, lon)]
    assert set(guardado) == {"senal", "computed_at"}
    assert body["senal"]["mm_3h"] == 12.0 and body["senal"]["intensa"] is True
    assert body["terreno"]["nivel"] == "alto"
    assert body["terreno"]["slope_deg"] == 16.0 and body["terreno"]["scar_ha"] > 0
    assert body["terreno"]["explicacion"].endswith(CIERRE)
    for clave in ("senal", "computed_at", "source", "source_url", "note"):
        assert clave in body
    assert "Open-Meteo" in body["source"] and "no es un aviso" in body["note"]


def test_sin_lluvia_ni_cicatriz_ni_cache_no_pide_el_dem(make_client, web, monkeypatch):
    lat, lon = _punto_talca()
    _pronostico(web, [0.0, 0.0, 0.0, 0.0])
    llamadas: list[tuple[float, float]] = []

    async def slope(*_args):
        llamadas.append(_args)
        return (20.0, 0.0)

    monkeypatch.setattr(elevation, "slope_aspect", slope)
    with make_client() as client:
        body = client.get(f"/api/climate/lluvia?lat={lat}&lon={lon}").json()
    assert llamadas == []
    assert body["senal"]["mm_3h"] == 0.0
    assert body["terreno"]["nivel"] == "bajo" and body["terreno"]["slope_deg"] is None
    assert body["terreno"]["scar_ha"] == 0.0
    assert body["terreno"]["explicacion"].endswith(CIERRE)


def test_la_cache_de_relieve_se_consulta_aunque_no_llueva(make_client, web, monkeypatch):
    lat, lon = _punto_talca()
    _pronostico(web, [0.0, 0.0, 0.0, 0.0])
    llamadas: list[tuple[float, float]] = []

    async def slope(_db, _client, y, x):
        llamadas.append((y, x))
        return (9.0, 45.0)

    monkeypatch.setattr(elevation, "slope_aspect", slope)
    with make_client() as client:
        client.app.state.services.db.cache_set(elevation.cache_key(lat, lon), [9.0, 45.0], 3600)
        body = client.get(f"/api/climate/lluvia?lat={lat}&lon={lon}").json()
    assert llamadas == [(lat, lon)]
    assert body["terreno"]["slope_deg"] == 9.0
    assert body["senal"]["mm_3h"] == 0.0


def test_si_el_pronostico_cae_el_terreno_queda_sin_dato(make_client, web, monkeypatch):
    lat, lon = _punto_talca()
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503, text="caído"))
    llamadas: list[object] = []

    async def slope(*args):
        llamadas.append(args)
        return (12.0, 0.0)

    monkeypatch.setattr(elevation, "slope_aspect", slope)
    with make_client() as client:
        body = client.get(f"/api/climate/lluvia?lat={lat}&lon={lon}").json()
    assert body["senal"] is None and body["source"]
    assert body["terreno"]["nivel"] == "sin_dato" and body["terreno"]["slope_deg"] is None
    assert body["terreno"]["explicacion"].endswith(CIERRE)
    assert llamadas == []


def test_una_huella_lejana_no_quema_la_ladera(make_client, web, monkeypatch):
    """40 ha a ~33 km, misma comuna, no cuentan: con 12 mm y 16° el nivel sigue en bajo."""
    lat, lon = _punto_talca()
    _pronostico(web, [0.0, 4.0, 5.0, 3.0, 1.0])

    async def slope(_db, _client, y, x):
        return (16.0, 180.0)

    monkeypatch.setattr(elevation, "slope_aspect", slope)
    with make_client() as client:
        seed_incident(client.app.state.services.db, "lejos", lat=lat + 0.30, lon=lon)
        body = client.get(f"/api/climate/lluvia?lat={lat}&lon={lon}").json()
    assert body["terreno"]["scar_ha"] == 0.0 and body["terreno"]["nivel"] == "bajo"
    assert body["terreno"]["slope_deg"] == 16.0
    texto = body["terreno"]["explicacion"]
    assert "No se registran huellas de calor recientes cerca de este punto." in texto
    assert "quemad" not in texto.lower()
    assert texto.endswith(CIERRE)


def test_la_cache_de_la_celda_no_comparte_el_terreno(make_client, web, monkeypatch):
    """Dos puntos de la misma celda de 0,1° comparten la señal, no la pendiente ni la cicatriz."""
    cerca = (-35.41, -71.67)
    lejos = (-35.36, -71.72)
    assert (round(cerca[0], 1), round(cerca[1], 1)) == (round(lejos[0], 1), round(lejos[1], 1))
    pronosticos = {"n": 0}

    def handler(request):
        assert not request.url.path.endswith("/elevation")
        pronosticos["n"] += 1
        return json_response({
            "hourly": {
                "time": [f"2026-10-20T{h:02d}:00" for h in range(5)],
                "precipitation": [0.0, 4.0, 5.0, 3.0, 1.0],
                "freezing_level_height": [1800.0] * 5,
            },
        })

    web.add(lambda r: "open-meteo" in r.url.host, handler)

    async def slope(_db, _client, y, x):
        return (16.0, 180.0) if abs(y - cerca[0]) < 1e-6 and abs(x - cerca[1]) < 1e-6 else (2.0, 0.0)

    monkeypatch.setattr(elevation, "slope_aspect", slope)
    with make_client() as client:
        seed_incident(client.app.state.services.db, "cerca", lat=cerca[0], lon=cerca[1])
        primero = client.get(f"/api/climate/lluvia?lat={cerca[0]}&lon={cerca[1]}").json()
        segundo = client.get(f"/api/climate/lluvia?lat={lejos[0]}&lon={lejos[1]}").json()
    assert pronosticos["n"] == 1
    assert primero["senal"] == segundo["senal"]
    assert primero["terreno"]["nivel"] == "alto" and primero["terreno"]["slope_deg"] == 16.0
    assert primero["terreno"]["scar_ha"] > 0
    assert segundo["terreno"]["nivel"] == "bajo" and segundo["terreno"]["slope_deg"] == 2.0
    assert segundo["terreno"]["scar_ha"] == 0.0
    assert "No se registran huellas de calor recientes cerca de este punto." in segundo["terreno"]["explicacion"]


def test_una_cache_vieja_con_terreno_no_se_repite(make_client, web, monkeypatch):
    """Un payload completo guardado antes del corte solo aporta `senal`; el terreno se recalcula."""
    lat, lon = -35.41, -71.67

    def handler(_request):
        raise AssertionError("la señal ya está en caché")

    web.add(lambda r: "open-meteo" in r.url.host, handler)

    async def slope(_db, _client, y, x):
        return (3.0, 90.0)

    monkeypatch.setattr(elevation, "slope_aspect", slope)
    with make_client() as client:
        client.app.state.services.db.cache_set(
            f"lluvia:{round(lat, 1)}:{round(lon, 1)}",
            {
                "senal": {"mm_3h": 12.0, "intensa": True, "isoterma_m": 1800.0, "isoterma_alta": False},
                "computed_at": "2026-11-04T00:00:00Z",
                "source": "vieja",
                "terreno": {"nivel": "alto", "slope_deg": 16.0, "scar_ha": 40.0, "explicacion": "ladera quemada"},
            },
            1800,
        )
        body = client.get(f"/api/climate/lluvia?lat={lat}&lon={lon}").json()
    assert body["senal"]["mm_3h"] == 12.0 and body["computed_at"] == "2026-11-04T00:00:00Z"
    assert body["terreno"]["nivel"] == "bajo" and body["terreno"]["slope_deg"] == 3.0
    assert body["terreno"]["scar_ha"] == 0.0
    assert "quemad" not in body["terreno"]["explicacion"].lower()
