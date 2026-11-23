"""RISK-07: la grilla 1° del bbox, el parseo de Open-Meteo, la caché y el cupo."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from backend import risk, services, windgrid
from backend.providers import weather

AHORA = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def test_grilla_dentro_del_bbox_continental():
    puntos = windgrid.grid_points()
    w, s, e, n = windgrid.CHILE_BBOX
    assert 300 <= len(puntos) <= 450  # ~380 celdas a 1°
    for lat, lon in puntos:
        assert s <= lat <= n and w <= lon <= e
        # centros de celda: siempre en .5
        assert abs(lat - round(lat)) == 0.5 and abs(lon - round(lon)) == 0.5


def test_build_grid_toma_la_hora_mas_cercana_y_respeta_la_convencion():
    puntos = [(lat, lon) for lat, lon in windgrid.grid_points()[:3]]
    filas = [{"time": ["2026-10-23T10:00", "2026-10-23T12:00", "2026-10-23T14:00"],
              "wind_speed_10m": [10, 25, 40], "wind_direction_10m": [90, 180, 270]} for _ in puntos]
    grid = windgrid.build_grid(puntos, filas, AHORA)
    assert grid["computed_at"] == "2026-10-23T12:00:00Z"
    assert grid["speed"] == [25.0, 25.0, 25.0]
    assert grid["dir"] == [180, 180, 180]
    assert len(grid["points"]) == 3


def test_build_grid_sin_datos_no_rompe():
    grid = windgrid.build_grid([(-35.5, -71.5)], [{"time": [], "wind_speed_10m": [], "wind_direction_10m": []}], AHORA)
    assert grid["speed"] == [None] and grid["dir"] == [None]


def test_cache_fresca_no_repide():
    assert windgrid.necesita_refresco("2026-10-23T11:00:00Z", AHORA) is False
    assert windgrid.necesita_refresco("2026-10-23T05:00:00Z", AHORA) is True
    assert windgrid.necesita_refresco(None, AHORA) is True


def test_la_grilla_cede_ante_el_cupo():
    n = len(windgrid.grid_points())
    assert windgrid.cabe_en_cupo(n, cap=n + 100, gastado=50) is True
    assert windgrid.cabe_en_cupo(n, cap=n + 100, gastado=150) is False
    assert windgrid.cabe_en_cupo(0, cap=100, gastado=0) is False


def test_hora_mas_cercana_con_tiempos_naive():
    """Open-Meteo devuelve `time` sin offset: se lee como UTC, no da siempre el índice 0."""
    assert windgrid._hora_mas_cercana(
        ["2026-10-23T09:00", "2026-10-23T12:00", "2026-10-23T15:00"], AHORA) == 1


def test_grilla_llega_a_la_columna_oeste():
    lons = [lon for _, lon in windgrid.grid_points()]
    assert min(lons) == -75.5  # floor(-75,8) + 0,5: sin floor se perdía la columna
    assert len(windgrid.grid_points()) == 380


def test_cupo_al_borde():
    """`cabe_en_cupo` compara contra lo que quede; la reserva (OPEN_METEO_RESERVE = 500)
    la descuenta `windgrid_cycle` antes de llamar: aquí solo el límite."""
    n = len(windgrid.grid_points())
    assert windgrid.cabe_en_cupo(n, cap=1000, gastado=1000 - n) is True   # justo en el tope
    assert windgrid.cabe_en_cupo(n, cap=1000, gastado=1000 - n + 1) is False  # una de más: cede


def _fila_horaria(base=AHORA, horas=48, speed=10.0, direc=90, gust=20.0):
    """Pronóstico horario desde `base - 12 h`; velocidad = `speed + índice` para ubicar la hora."""
    t0 = base - timedelta(hours=12)
    tiempos = [(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(horas)]
    return {
        "time": tiempos,
        "wind_speed_10m": [speed + i for i in range(horas)],
        "wind_direction_10m": [(direc + i) % 360 for i in range(horas)],
        "wind_gusts_10m": [gust + i for i in range(horas)],
    }


def test_grilla_fina_cubre_la_franja_centro_sur_a_un_cuarto_de_grado():
    pts = windgrid.fine_grid_points()
    w, s, e, n = windgrid.FINE_BBOX
    assert len(pts) == 390
    shape = windgrid.grid_shape(pts, windgrid.FINE_STEP_DEG)
    assert shape == (-39.5, -73.5, 30, 13)
    lat0, lon0, rows, cols = shape
    assert rows * cols == len(pts)
    for r in range(rows):
        for c in range(cols):
            assert pts[r * cols + c] == (round(lat0 + r * 0.25, 2), round(lon0 + c * 0.25, 2))
    assert pts[0] == (s, w) and pts[-1] == (n, e)  # (lat, lon): bordes incluidos


def test_grid_shape_reconoce_la_grilla_base_y_rechaza_subconjuntos():
    base = windgrid.grid_points()
    assert windgrid.grid_shape(base, windgrid.STEP_DEG) == (-55.5, -75.5, 38, 10)
    assert windgrid.grid_shape(base[:3], windgrid.STEP_DEG) is None
    assert windgrid.grid_shape([], windgrid.STEP_DEG) is None
    # Con el paso equivocado no es regular.
    assert windgrid.grid_shape(base, windgrid.FINE_STEP_DEG) is None
    # Un hueco rompe la regularidad aunque la cuenta cuadre.
    roto = list(windgrid.fine_grid_points())
    roto[5] = (roto[5][0], roto[5][1] + 0.1)
    assert windgrid.grid_shape(roto, windgrid.FINE_STEP_DEG) is None


def test_build_grid_expone_rafagas_fuente_y_pasos_horarios():
    pts = windgrid.grid_points()
    grid = windgrid.build_grid(pts, [_fila_horaria() for _ in pts], AHORA)
    assert (grid["lat0"], grid["lon0"], grid["rows"], grid["cols"]) == (-55.5, -75.5, 38, 10)
    assert grid["step"] == 1.0 and "fine" not in grid
    assert grid["source"]["name"].startswith("Open-Meteo") and grid["source"]["url"].startswith("https://")
    assert list(grid["steps"]) == ["0", "3", "6", "12"]
    # +0 h es el índice 12; +3, +6 y +12 h, los índices 15, 18 y 24.
    for h, idx in (("0", 12), ("3", 15), ("6", 18), ("12", 24)):
        paso = grid["steps"][h]
        assert paso["speed"][0] == 10.0 + idx
        assert paso["dir"][0] == (90 + idx) % 360
        assert paso["gust"][0] == 20.0 + idx
        assert len(paso["speed"]) == len(pts)
    assert grid["steps"]["12"]["at"] == "2026-10-24T00:00:00Z"
    # Los campos de nivel superior son el paso +0 h.
    assert grid["speed"] == grid["steps"]["0"]["speed"]
    assert grid["dir"] == grid["steps"]["0"]["dir"]
    assert grid["gust"] == grid["steps"]["0"]["gust"]


def test_build_grid_subconjunto_irregular_no_publica_forma():
    pts = windgrid.grid_points()[:3]
    grid = windgrid.build_grid(pts, [_fila_horaria() for _ in pts], AHORA)
    assert not {"lat0", "lon0", "rows", "cols"} & grid.keys()
    assert len(grid["points"]) == 3


def test_pasos_sin_cobertura_ni_rafaga_quedan_en_null():
    pts = windgrid.grid_points()[:2]
    corta = _fila_horaria(horas=14)  # llega hasta +1 h: no cubre +3, +6 ni +12 h
    sin_rafaga = _fila_horaria()
    del sin_rafaga["wind_gusts_10m"]
    con_nan = _fila_horaria()
    con_nan["wind_speed_10m"][12] = float("nan")
    con_nan["wind_gusts_10m"][12] = None
    grid = windgrid.build_grid(pts, [corta, sin_rafaga], AHORA)
    assert grid["steps"]["0"]["speed"] == [22.0, 22.0]
    assert grid["steps"]["0"]["gust"] == [32.0, None]
    for h in ("3", "6", "12"):
        assert grid["steps"][h]["speed"][0] is None
        assert grid["steps"][h]["dir"][0] is None
        assert grid["steps"][h]["gust"][0] is None
        assert grid["steps"][h]["speed"][1] is not None  # la otra fila sí cubre
    nan = windgrid.build_grid(pts[:1], [con_nan], AHORA)
    assert nan["speed"] == [None] and nan["gust"] == [None]
    assert nan["dir"] == [102]
    json.dumps(nan, allow_nan=False)  # nunca NaN en la respuesta


def test_un_paso_a_mas_de_90_minutos_no_se_inventa():
    fila = {"time": ["2026-10-23T09:00"], "wind_speed_10m": [5], "wind_direction_10m": [10],
            "wind_gusts_10m": [9]}
    grid = windgrid.build_grid([(-35.5, -71.5)], [fila], AHORA)  # la hora está a 3 h
    assert grid["speed"] == [None] and grid["gust"] == [None]
    cerca = {"time": ["2026-10-23T13:00"], "wind_speed_10m": [5], "wind_direction_10m": [370],
             "wind_gusts_10m": [9]}  # a 60 min: dentro de la tolerancia
    grid = windgrid.build_grid([(-35.5, -71.5)], [cerca], AHORA)
    assert grid["speed"] == [5.0] and grid["dir"] == [10] and grid["gust"] == [9.0]


def test_build_fine_grid_es_compacta_e_indexable():
    pts = windgrid.fine_grid_points()
    fine = windgrid.build_fine_grid(pts, [_fila_horaria() for _ in pts], AHORA)
    assert fine["step"] == 0.25
    assert (fine["lat0"], fine["lon0"], fine["rows"], fine["cols"]) == (-39.5, -73.5, 30, 13)
    assert fine["bbox"] == list(windgrid.FINE_BBOX)
    assert "points" not in fine
    assert len(fine["speed"]) == len(fine["dir"]) == len(fine["gust"]) == 390
    assert list(fine["steps"]) == ["0", "3", "6", "12"]
    assert fine["gust"][0] == 32.0 and fine["steps"]["6"]["gust"][389] == 38.0


def test_build_grid_adjunta_el_bloque_fino():
    pts = windgrid.grid_points()
    fpts = windgrid.fine_grid_points()
    fine = windgrid.build_fine_grid(fpts, [_fila_horaria() for _ in fpts], AHORA)
    grid = windgrid.build_grid(pts, [_fila_horaria() for _ in pts], AHORA, fine=fine)
    assert grid["fine"] is fine
    assert len(grid["points"]) == 380  # `points` solo de la base


def _cupo(svc, restante):
    """Deja justo `restante` ubicaciones de cupo para la grilla de viento."""
    tope = weather.DAILY_LOCATIONS_CAP - services.OPEN_METEO_RESERVE - svc._om_plan_pending()
    hoy = datetime.now(risk.CHILE_TZ).date().isoformat()
    svc.db.kv_set("open_meteo_day", json.dumps({"date": hoy, "total": tope - restante, "tasks": {}}))


def test_windgrid_cycle_adjunta_la_subgrilla_si_el_cupo_alcanza(make_client, monkeypatch):
    with make_client() as client:
        svc = client.app.state.services
        n_base, n_fine = len(windgrid.grid_points()), len(windgrid.fine_grid_points())
        _cupo(svc, n_base + n_fine)
        llamadas = []

        async def fake_forecast(client_, puntos, days=1, extra_vars=None):
            llamadas.append((len(puntos), days))
            return [_fila_horaria(datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0))
                    for _ in puntos]

        monkeypatch.setattr(weather, "forecast_hourly", fake_forecast)
        out = asyncio.run(svc.windgrid_cycle())
        assert out == {"celdas": n_base, "celdas_finas": n_fine}
        assert llamadas == [(n_base, 2), (n_fine, 2)]
        grid = json.loads(svc.db.kv_get("windgrid"))
        assert grid["fine"]["rows"] == 30 and grid["fine"]["cols"] == 13
        assert "points" not in grid["fine"]
        tareas = svc.open_meteo_day()["tasks"]
        assert tareas["windgrid"]["today"] == n_base and tareas["windgrid_fine"]["today"] == n_fine


def test_windgrid_cycle_degrada_a_un_grado_si_solo_cabe_la_base(make_client, monkeypatch):
    with make_client() as client:
        svc = client.app.state.services
        n_base, n_fine = len(windgrid.grid_points()), len(windgrid.fine_grid_points())
        _cupo(svc, n_base + n_fine - 1)
        llamadas = []

        async def fake_forecast(client_, puntos, days=1, extra_vars=None):
            llamadas.append(len(puntos))
            return [{} for _ in puntos]

        monkeypatch.setattr(weather, "forecast_hourly", fake_forecast)
        out = asyncio.run(svc.windgrid_cycle())
        assert out == {"celdas": n_base, "celdas_finas": 0}
        assert llamadas == [n_base]
        grid = json.loads(svc.db.kv_get("windgrid"))
        assert "fine" not in grid and len(grid["points"]) == n_base


def test_windgrid_cycle_conserva_la_base_si_falla_la_subgrilla(make_client, monkeypatch):
    with make_client() as client:
        svc = client.app.state.services
        n_base, n_fine = len(windgrid.grid_points()), len(windgrid.fine_grid_points())
        _cupo(svc, n_base + n_fine)

        async def fake_forecast(client_, puntos, days=1, extra_vars=None):
            if len(puntos) == n_fine:
                raise weather.WeatherError("sin respuesta")
            return [{} for _ in puntos]

        monkeypatch.setattr(weather, "forecast_hourly", fake_forecast)
        out = asyncio.run(svc.windgrid_cycle())
        assert out == {"celdas": n_base, "celdas_finas": 0}
        assert "fine" not in json.loads(svc.db.kv_get("windgrid"))
        assert "windgrid_fine" not in svc.open_meteo_day()["tasks"]


def test_build_grid_guarda_hora_valida_del_pronostico():
    """`steps[h].at` refleja la hora UTC válida de Open-Meteo, no minutos arbitrarios de `now`."""
    pts = windgrid.grid_points()[:2]
    ahora_min = datetime(2026, 10, 23, 12, 37, 12, tzinfo=timezone.utc)
    grid = windgrid.build_grid(pts, [_fila_horaria(AHORA) for _ in pts], ahora_min)
    assert grid["steps"]["0"]["at"] == "2026-10-23T13:00:00Z"
    assert grid["steps"]["3"]["at"] == "2026-10-23T16:00:00Z"


def test_windgrid_cycle_anota_lotes_parciales_si_subgrilla_falla_a_mitad(make_client, monkeypatch):
    """Si la subgrilla fina falla tras 2 lotes (100 ubicaciones), ese gasto igual queda anotado."""
    with make_client() as client:
        svc = client.app.state.services
        n_base, n_fine = len(windgrid.grid_points()), len(windgrid.fine_grid_points())
        _cupo(svc, n_base + n_fine)
        total_antes = svc.open_meteo_day()["total"]
        llamadas_get = {"n": 0}

        async def fake_get(client_, url, params):
            llamadas_get["n"] += 1
            n_lote = len(str(params.get("latitude", "")).split(","))
            # 8 lotes de la base (380) + 2 lotes de la fina (100) pasan; el 3° lote fino falla.
            if llamadas_get["n"] == 11:
                raise weather.WeatherError("fallo a mitad de subgrilla")
            weather._count(url, n_lote)
            fila = {"hourly": _fila_horaria(datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0))}
            return [fila for _ in range(n_lote)] if n_lote > 1 else fila

        monkeypatch.setattr(weather, "_get", fake_get)
        out = asyncio.run(svc.windgrid_cycle())
        assert out == {"celdas": n_base, "celdas_finas": 0}
        day = svc.open_meteo_day()
        assert day["tasks"]["windgrid"]["today"] == n_base
        assert day["tasks"]["windgrid_fine"]["today"] == 100
        assert day["total"] == total_antes + n_base + 100

