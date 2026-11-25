"""REND-02 (tanda 4): contabilidad diaria de Open-Meteo atómica y local por operación.

La verdad del cupo vive en la tabla `om_day` de brasa.db, respaldada con todo lo demás:
la suma es una sola sentencia SQL
(dos tareas a la vez no pierden ubicaciones), la reserva hace chequeo y suma atómicos con la
línea base del `kv` incluida en el mismo WHERE, y cada operación liquida exactamente lo que
Open-Meteo le sirvió, separado por día local de Chile (una respuesta que cruza medianoche
reparte su gasto). El `kv` «open_meteo_day» queda como espejo para las rutas viejas y las
siembras de las pruebas: nunca decide una cuota, y `_om_refresh` lo migra a filas de la
tabla sin contar doble. El gasto global (`weather.served()`) es solo diagnóstico: los
deltas globales mezclaban operaciones y un `asyncio.gather` o una ruta intercalada podía
quedar atribuido a la tarea que medía.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta

import httpx
import pytest

from backend import rain as rain_mod
from backend import services
from backend.db import Database
from backend.geo import territory
from backend.providers import weather
from backend.risk import CHILE_TZ
from backend.routes import climate as climate_mod
from backend.routes.personal import risk_point_at
from backend.routes.public import air_for_comuna, atmosphere_for_point
from tests.conftest import json_response
from tests.test_aluvion_aviso import _svc_con_lugar
from tests.test_pendientes import _deteccion_reciente

COMUNAS = len(territory().comunas)


def _dia_lleno(svc, total: int | None = None) -> None:
    """Siembra el ledger del día con un gasto sin tarea propia (fila interna `_base`)."""
    svc.db.execute("DELETE FROM om_day")
    svc.db.kv_set(
        "open_meteo_day",
        json.dumps({"date": svc._om_today(), "total": total or weather.DAILY_LOCATIONS_CAP, "tasks": {}}),
    )


@pytest.fixture(autouse=True)
def _contadores_en_cero(monkeypatch):
    """Los contadores de Open-Meteo son estado global del proceso: cada prueba arranca en cero."""
    monkeypatch.setattr(
        weather,
        "_calls",
        {"since": None, "day": None, "calls": 0, "locations": 0, "by_endpoint": {}, "by_endpoint_locations": {}, "rate_limited": 0},
    )
    monkeypatch.setattr(weather, "_served", {"day": None, "locations": 0})


def _forecast(request: httpx.Request) -> httpx.Response:
    """Pronóstico horario válido: un elemento por ubicación pedida, con todas las variables."""
    n = request.url.params["latitude"].count(",") + 1
    fila = {
        "hourly": {
            "time": ["2027-01-15T12:00"],
            "temperature_2m": [20.0],
            "relative_humidity_2m": [40.0],
            "wind_speed_10m": [12.0],
            "wind_gusts_10m": [30.0],
            "wind_direction_10m": [200.0],
            "precipitation": [0.0],
            "freezing_level_height": [3000.0],
        }
    }
    return json_response([fila for _ in range(n)])


def _current(request: httpx.Request) -> httpx.Response:
    return json_response(
        {
            "current": {"time": "2027-01-15T12:00", "temperature_2m": 20.0, "wind_speed_10m": 12.0, "wind_gusts_10m": 30.0, "wind_direction_10m": 200.0},
            "current_units": {},
        }
    )


def _meteo_handler(request: httpx.Request) -> httpx.Response:
    """Un solo handler para api.open-meteo.com: `current` para el viento, `hourly` para el resto."""
    return _current(request) if "current" in request.url.params else _forecast(request)


def _local_stamp(day_offset: int, hour: int = 12) -> str:
    base = datetime.now(CHILE_TZ) + timedelta(days=day_offset)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def _air_payload(request: httpx.Request) -> httpx.Response:
    return json_response(
        {
            "hourly": {
                "time": [_local_stamp(0, 9), _local_stamp(0, 18), _local_stamp(1)],
                "pm2_5": [11.0, 22.5, 8.0],
                "pm10": [27.5, 44.0, 13.0],
                "carbon_monoxide": [225.0, 400.0, 80.0],
                "aerosol_optical_depth": [0.2, 0.6, 0.08],
                "dust": [11.0, 5.0, 4.0],
            }
        }
    )


# --- topes y límites heredados (REND-02 no los sube) ---


def test_los_topes_no_cambian():
    assert weather.DAILY_LOCATIONS_CAP == 9000
    assert services.OPEN_METEO_RESERVE == 500
    assert weather.BATCH_SIZE == 50
    assert services.RISK_POINTS_PER_PASS == 550
    assert weather.FWI_PAUSE_S == 4  # pausa entre peticiones: el límite por minuto cuenta volumen
    assert weather.FWI_RETRY_WAIT_S == 65  # lo que pide Open-Meteo tras un 429


# --- contabilidad local: ni gather ni rutas intercaladas contaminan el gasto ---


def test_el_gasto_de_la_lluvia_no_absorbe_el_viento_intercalado(make_client, web):
    """Dos respuestas (señal de lluvia + viento de avisos) anotan 2 ubicaciones, no 3.

    Antes de la contabilidad local, el `current` del viento que llegaba entre el inicio y el
    fin de la lluvia quedaba absorbido por su delta global de `served()`: 2 respuestas
    anotaban 3. Cada operación mide solo lo suyo, aunque corran juntas en un gather.
    """
    web.add(lambda r: r.url.host == "api.open-meteo.com", _meteo_handler)
    with make_client() as client:
        svc = client.app.state.services

        async def consulta_de_lluvia():
            # el mismo patrón del endpoint /api/climate/lluvia: contabilidad local por operación
            op = weather.start_op()
            try:
                await climate_mod.senal_celda(svc, -35.4, -71.6)
            finally:
                svc._om_record("lluvia", weather.end_op(op).by_day)

        async def correr():
            await asyncio.gather(consulta_de_lluvia(), svc.wind_at(-35.42, -71.61))

        asyncio.run(correr())
        day = svc.open_meteo_day()
    assert day["tasks"]["lluvia"]["today"] == 1
    assert day["tasks"]["viento"]["today"] == 1
    assert day["total"] == 2, "dos respuestas exitosas: ni una ubicación de más ni de menos"


def test_dos_reservas_intercaladas_no_se_llevan_el_gasto_ajeno(make_client):
    """Cada reserva liquida exactamente lo que su propia operación sirvió."""
    with make_client() as client:
        svc = client.app.state.services

        async def pasada(n: int) -> None:
            day = svc._om_reserve("grilla", n, 9000)
            assert day
            op = weather.start_op()
            try:
                await asyncio.sleep(0)  # deja que la otra pasada intercale su conteo
                weather._count(weather.FORECAST_URL, n // 2)  # Open-Meteo sirvió la mitad
            finally:
                svc._om_settle("grilla", day, n, weather.end_op(op).by_day)

        async def correr():
            await asyncio.gather(pasada(60), pasada(80))

        asyncio.run(correr())
        day = svc.open_meteo_day()
    assert day["tasks"]["grilla"]["today"] == 70, "30 + 40: el gasto ajeno nunca se absorbe"
    assert day["total"] == 70


def test_las_sumas_de_tareas_concurrentes_no_se_pierden(make_client):
    """El registro desde hilos (rutas + ciclo) suma en SQL: 6 tareas × 40 = 240 exactos."""
    with make_client() as client:
        svc = client.app.state.services

        async def tarea(nombre: str) -> None:
            for _ in range(40):
                await asyncio.to_thread(svc._om_record, nombre, 1)

        async def correr():
            await asyncio.gather(*[tarea(f"tarea{i}") for i in range(6)])

        asyncio.run(correr())
        view = svc.open_meteo_day()
        espejo = json.loads(svc.db.kv_get("open_meteo_day"))
    assert view["total"] == 240
    assert {t: e["today"] for t, e in view["tasks"].items()} == {f"tarea{i}": 40 for i in range(6)}
    assert espejo["total"] == 240, "el espejo del kv publica la misma suma que la tabla"


def test_el_ledger_legado_de_work_migra_a_main_sin_rebobinar(tmp_path):
    """El ledger de work.db pasa al mismo archivo que kv y conserva el mayor respaldo."""
    path = tmp_path / "brasa.db"
    work_path = tmp_path / "work.db"
    anterior = Database(path, work_path)
    with anterior.connect() as conn:
        conn.execute(
            "CREATE TABLE work.om_day (day TEXT NOT NULL, task TEXT NOT NULL, used INTEGER NOT NULL, "
            "last INTEGER, at TEXT, PRIMARY KEY(day, task))"
        )
        conn.execute(
            "INSERT INTO work.om_day(day, task, used, last, at) VALUES (?,?,?,?,?)",
            ("2027-01-15", "risk", 300, 100, "2027-01-15T12:00:00Z"),
        )
    anterior.close_all()

    migrada = Database(path, work_path)
    assert migrada.one("SELECT used FROM om_day WHERE day = ? AND task = ?", ("2027-01-15", "risk"))["used"] == 300
    with migrada.connect() as conn:
        # Una copia de work más vieja no hace retroceder el valor que ya llegó a main.
        conn.execute(
            "INSERT INTO main.om_day(day, task, used) VALUES (?,?,?) "
            "ON CONFLICT(day, task) DO UPDATE SET used = excluded.used",
            ("2027-01-15", "risk", 350),
        )
        from backend.db import _migrate_om_day

        _migrate_om_day(conn)
    fila = migrada.one("SELECT used FROM om_day WHERE day = ? AND task = ?", ("2027-01-15", "risk"))
    assert fila["used"] == 350
    migrada.close_all()


def test_registro_sin_reserva_conserva_el_dia_de_cada_respuesta(make_client, monkeypatch):
    """Las operaciones largas FWI/lluvia no trasladan a mañana lo servido antes de medianoche."""
    fase = [datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fase[0].astimezone(tz) if tz is not None else fase[0]

    monkeypatch.setattr(services, "datetime", Clock)
    with make_client() as client:
        svc = client.app.state.services
        svc._om_record("fwi", {"2027-04-03": 3})
        fase[0] = datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ)
        svc._om_record("fwi", {"2027-04-04": 2})
        rows = svc.db.query("SELECT day, used FROM om_day WHERE task = 'fwi' ORDER BY day")
    assert [(row["day"], row["used"]) for row in rows] == [("2027-04-03", 3), ("2027-04-04", 2)]


def test_el_espejo_del_kv_no_retrocede_con_escrituras_intercaladas(make_client):
    """Reflejar el espejo era leer-modificar-escribir: dos escrituras a la vez perdían sumas.

    Ahora cada reflejo sale de la tabla en una transacción serializada: el espejo nunca
    muestra menos que la verdad.
    """
    with make_client() as client:
        svc = client.app.state.services

        async def registrar(nombre: str, n: int) -> None:
            for _ in range(n):
                await asyncio.to_thread(svc._om_record, nombre, 1)

        async def correr():
            await asyncio.gather(registrar("a", 20), registrar("b", 20))

        asyncio.run(correr())
        view = svc.open_meteo_day()
        espejo = json.loads(svc.db.kv_get("open_meteo_day"))
    assert view["total"] == espejo["total"] == 40
    assert espejo["tasks"]["a"]["today"] == 20 and espejo["tasks"]["b"]["today"] == 20


# --- reserva atómica: el cupo no se sobregira ---


def test_las_reservas_concurrentes_reparten_el_cupo_sin_sobregirar(make_client):
    """96 reservas de 100 contra un tope de 9000: entran exactamente 90, ni una más."""
    with make_client() as client:
        svc = client.app.state.services

        async def reserva(i: int):
            return await asyncio.to_thread(svc._om_reserve, f"tarea{i % 3}", 100, 9000)

        async def correr():
            return await asyncio.gather(*[reserva(i) for i in range(96)])

        resultados = asyncio.run(correr())
        assert sum(1 for r in resultados if r) == 90
        assert svc._om_spent() == 9000
        assert not svc._om_reserve("una_mas", 1, 9000), "con el día lleno ni una ubicación extra"


def test_la_reserva_que_excede_el_tope_cede_sin_escribir_gasto(make_client):
    with make_client() as client:
        svc = client.app.state.services
        assert svc._om_reserve("grilla", 10, 12)
        assert svc._om_reserve("fina", 5, 12) is None, "10 + 5 no caben en el tope de 12"
        day = svc.open_meteo_day()
        assert day["total"] == 10 and "fina" not in day["tasks"]
        assert svc._om_reserve("fina", 2, 12)
        assert svc.open_meteo_day()["total"] == 12


def test_riesgo_sin_un_punto_por_comuna_no_deja_reserva_abierta(make_client, monkeypatch):
    """La pasada de riesgo cede antes de reservar si no puede cubrir los centros de todas las comunas."""
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_spent", lambda: weather.DAILY_LOCATIONS_CAP - 600)
        with pytest.raises(RuntimeError, match="Sin cupo diario"):
            asyncio.run(svc.compute_risk())
        assert svc.open_meteo_day()["total"] == 0


def test_un_valor_sembrado_en_el_kv_migra_a_la_tabla_sin_contarse_dos_veces(make_client):
    """La siembra manual del `kv` (pruebas, kv legado) se descuenta desde la primera reserva
    y migra a filas de la tabla exactamente una vez."""
    with make_client() as client:
        svc = client.app.state.services
        hoy = svc._om_today()
        svc.db.kv_set("open_meteo_day", json.dumps({"date": hoy, "total": 100, "tasks": {"risk": {"today": 60}}}))
        # la reserva la descuenta en el mismo chequeo atómico, sin migrar antes
        assert svc._om_reserve("grilla", 50, 150)
        day = svc.open_meteo_day()  # la lectura migra la siembra a filas y publica el espejo
        assert day["total"] == 150
        assert day["tasks"]["risk"]["today"] == 60 and day["tasks"]["grilla"]["today"] == 50
        assert svc.open_meteo_day() == day, "releer no cuenta la siembra otra vez"
        assert svc._om_reserve("una_mas", 1, 150) is None, "el día quedó en el tope exacto"
        filas = svc.db.query("SELECT task, used FROM om_day WHERE day = ?", (hoy,))
        usos = {f["task"]: f["used"] for f in filas}
        assert usos["_base"] == 40, "lo sembrado sin tarea propia va a la fila interna _base"


# --- solo lo servido descuenta: 429 y red caída devuelven la reserva ---


def test_un_429_deja_el_dia_en_cero_porque_la_reserva_se_devuelve(make_client, web, monkeypatch):
    monkeypatch.setattr(weather, "FWI_RETRY_WAIT_S", 0)
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(429))
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)  # el plan real varía con la fecha
        with pytest.raises(weather.WeatherRateLimited):
            asyncio.run(svc.windgrid_cycle())
        day = svc.open_meteo_day()
    assert day["total"] == 0
    assert "windgrid" not in day["tasks"]
    assert weather.counts()["rate_limited"] == 4, "el 429 queda en el diagnóstico, no en el cupo"


def test_una_excepcion_de_red_devuelve_la_reserva(make_client, monkeypatch):
    async def boom(client_, puntos, days=2, extra_vars=None, models=None):
        raise weather.WeatherError("red caída")

    monkeypatch.setattr(weather, "forecast_hourly", boom)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        with pytest.raises(weather.WeatherError):
            asyncio.run(svc.windgrid_cycle())
        assert svc.open_meteo_day()["total"] == 0


def test_el_429_y_el_fallo_de_red_no_cuentan_como_gasto():
    """A nivel proveedor: solo la respuesta exitosa suma al gasto; el resto es diagnóstico."""

    respuestas = iter([httpx.Response(429), httpx.ConnectError("sin red"), json_response({"hourly": {}})])

    def handler(request: httpx.Request) -> httpx.Response:
        resultado = next(respuestas)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(weather.WeatherError):
                await weather._get(http, weather.ARCHIVE_URL, {})
            with pytest.raises(weather.WeatherError):
                await weather._get(http, weather.ARCHIVE_URL, {})
            assert await weather._get(http, weather.ARCHIVE_URL, {})

    asyncio.run(run())
    c = weather.counts()
    assert c["calls"] == 3 and c["locations"] == 3 and c["rate_limited"] == 1
    assert weather.served() == 1, "solo la respuesta exitosa gasta el día"


# --- medianoche (con el borde DST de Chile): la liquidación respeta los días ---


def test_la_liquidacion_cruzando_la_medianoche_no_toca_la_reserva_nueva(make_client, monkeypatch):
    """Reserva en D, respuesta en D+1 (cruzando el cambio de hora del 4-abr-2027):
    la reserva se libera en D, el gasto queda contabilizado en D+1 una sola vez y la
    reserva nueva de la misma tarea en D+1 no se descuenta.

    Es el registro directo con mapa por día (`_count` simula la respuesta sin despacho):
    una petición DESPACHADA en D se cobra a D aunque responda en D+1 (re-revisión G3, test
    de la tercera ronda); aquí se prueba que la liquidación respeta los días del mapa."""
    _fase = [datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return _fase[0].astimezone(tz) if tz is not None else _fase[0]

    monkeypatch.setattr(services, "datetime", Clock)
    monkeypatch.setattr(weather, "datetime", Clock)
    with make_client() as client:
        svc = client.app.state.services
        # 23:50 del 3-abr es -03; 00:10 del 4-abr ya es -04: el día local cambió con el DST.
        assert datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ).utcoffset() == timedelta(hours=-3)
        assert datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ).utcoffset() == timedelta(hours=-4)
        day_d = svc._om_reserve("grilla", 9, 9000)
        assert day_d == "2027-04-03"
        op = weather.start_op()
        _fase[0] = datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ)  # la respuesta cruzó la medianoche
        weather._count(weather.FORECAST_URL, 5)  # 5 ubicaciones servidas ya en D+1
        svc._om_settle("grilla", day_d, 9, weather.end_op(op).by_day)
        # la pasada nueva del día D+1 reserva aparte y sirve aparte
        day_nuevo = svc._om_reserve("grilla", 9, 9000)
        assert day_nuevo == "2027-04-04"
        op = weather.start_op()
        weather._count(weather.FORECAST_URL, 4)
        svc._om_settle("grilla", day_nuevo, 9, weather.end_op(op).by_day)
        filas = svc.db.query("SELECT day, used, last FROM om_day WHERE task = 'grilla' ORDER BY day")
        assert [(f["day"], f["used"], f["last"]) for f in filas] == [("2027-04-03", 0, 0), ("2027-04-04", 9, 4)]
        day = svc.open_meteo_day()
        assert day["date"] == "2027-04-04" and day["total"] == 9
        assert day["tasks"]["grilla"]["today"] == 9, "5 de la pasada vieja + 4 de la nueva"


def test_el_contador_se_reinicia_al_cambiar_el_dia_de_chile(make_client, monkeypatch):
    """El día local de America/Santiago manda (borde DST del 4-abr-2027) y las filas del día
    cerrado se conservan: una liquidación cruzando medianoche aún puede soltar su reserva."""
    _fase = [datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return _fase[0].astimezone(tz) if tz is not None else _fase[0]

    monkeypatch.setattr(services, "datetime", Clock)
    monkeypatch.setattr(weather, "datetime", Clock)
    with make_client() as client:
        svc = client.app.state.services
        svc._om_record("risk", 5)
        assert svc._om_today() == "2027-04-03" and svc._om_spent() == 5
        _fase[0] = datetime(2027, 4, 4, 6, 0, tzinfo=CHILE_TZ)  # ya cruzó medianoche y el DST (-04)
        assert svc._om_today() == "2027-04-04"
        assert svc._om_spent() == 0, "el día nuevo arranca el contador en cero"
        svc._om_record("risk", 3)
        day = svc.open_meteo_day()
        assert day["total"] == 3 and day["tasks"]["risk"]["today"] == 3
        # sin poda: la fila del día cerrado sigue ahí (nadie borra un historial pendiente)
        filas = svc.db.query("SELECT day, used FROM om_day WHERE task = 'risk' ORDER BY day")
        assert [(f["day"], f["used"]) for f in filas] == [("2027-04-03", 5), ("2027-04-04", 3)]


# --- restaurar un respaldo no rebobina el contador ---


def test_restaurar_no_rebobina_el_contador_del_dia(make_client, tmp_path):
    with make_client() as client:
        svc = client.app.state.services
        svc._om_record("risk", 100)
        svc._om_record("risk", 200)  # el día sigue avanzando: total 300
        dia, total = svc._om_today(), svc._om_spent()
        assert total == 300
        vacia = Database(tmp_path / "vacia.db")
        svc.db.restore(vacia.snapshot())
        svc.db.restore_work(vacia.snapshot_work())
        assert svc._om_spent() == 0, "sin la guarda, la restauración rebobinaría el día"
        svc._om_no_rewind(dia, total)  # la guarda que corren start() y tick() tras restaurar
        assert svc._om_spent() == 300
        filas = svc.db.query("SELECT task, used FROM om_day WHERE day = ?", (dia,))
        assert {f["task"]: f["used"] for f in filas}["_base"] == 300
        assert json.loads(svc.db.kv_get("open_meteo_day"))["total"] == 300


def test_restaurar_no_rebobina_un_gasto_que_el_espejo_no_alcanzo_a_ver(make_client, tmp_path):
    """La captura lee la tabla, no el espejo: un gasto registrado justo antes de una caída,
    sin reflejar en el `kv`, también se conserva tras restaurar un respaldo vacío."""
    with make_client() as client:
        svc = client.app.state.services
        hoy = svc._om_today()
        with svc.db.connect() as conn:
            conn.execute("INSERT INTO om_day(day, task, used, last, at) VALUES (?,?,?,?,?)", (hoy, "risk", 100, 100, "2027-01-01T00:00:00Z"))
        assert svc.db.kv_get("open_meteo_day") is None, "la caída llegó antes del reflejo"
        total = svc._om_spent()
        assert total == 100, "la captura lee la tabla aunque el kv diga otra cosa"
        vacia = Database(tmp_path / "vacia.db")
        svc.db.restore(vacia.snapshot())
        svc.db.restore_work(vacia.snapshot_work())
        svc._om_no_rewind(hoy, total)
        day = svc.open_meteo_day()
    assert day["total"] == 100
    assert json.loads(svc.db.kv_get("open_meteo_day"))["total"] == 100


# --- consumidores de ruta: fallo 0, éxito exacto, caché 0, concurrencia con tope ---


def test_el_aire_y_la_atmosfera_fallados_no_gastan_el_dia(make_client, web, monkeypatch):
    """429, red caída y JSON roto liberan la reserva: nada queda anotado como gasto."""
    respuestas = iter(
        [
            httpx.Response(429),
            httpx.ConnectError("red caída"),
            httpx.Response(200, content=b"{no es json", headers={"content-type": "application/json"}),
            httpx.Response(503),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        resultado = next(respuestas)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    web.add(lambda r: "open-meteo" in r.url.host, handler)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        comuna = territory().by_code[5109]
        assert asyncio.run(air_for_comuna(svc, comuna)) is None  # 429
        assert asyncio.run(air_for_comuna(svc, comuna)) is None  # red caída
        assert asyncio.run(air_for_comuna(svc, comuna)) is None  # JSON roto
        assert asyncio.run(atmosphere_for_point(svc, comuna.center[1], comuna.center[0], "prueba")) is None
        day = svc.open_meteo_day()
    assert day["total"] == 0 and day["tasks"] == {}, "los fallos devuelven la reserva entera"


def test_cancelar_el_aire_o_la_atmosfera_devuelve_la_reserva(make_client, monkeypatch):
    async def bloqueada(*_args, **_kwargs):
        await asyncio.Event().wait()

    async def cancelar(awaitable):
        task = asyncio.create_task(awaitable)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        monkeypatch.setattr(weather, "air_quality", bloqueada)
        monkeypatch.setattr(weather, "forecast_hourly", bloqueada)
        comuna = territory().by_code[5109]

        async def run():
            await cancelar(air_for_comuna(svc, comuna))
            await cancelar(atmosphere_for_point(svc, comuna.center[1], comuna.center[0], "cancelada"))

        asyncio.run(run())
        day = svc.open_meteo_day()
    assert day["total"] == 0 and day["tasks"] == {}, "la cancelación no deja reservas huérfanas"


def test_el_aire_y_la_atmosfera_exitosos_cuentan_1_y_2(make_client, web, monkeypatch):
    web.add(lambda r: "air-quality" in r.url.host, _air_payload)
    web.add(lambda r: r.url.host == "api.open-meteo.com", _forecast)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        comuna = territory().by_code[5109]
        asyncio.run(air_for_comuna(svc, comuna))
        asyncio.run(atmosphere_for_point(svc, comuna.center[1], comuna.center[0], "prueba:exito"))
        day = svc.open_meteo_day()
    assert day["tasks"]["air"]["today"] == 1
    # 14 variables horarias (>10): Open-Meteo pondera >1 crédito fraccional; se contabilizan 2.
    assert day["tasks"]["atmos"]["today"] == 2
    assert day["total"] == 3


def test_las_fichas_concurrentes_respetan_el_tope_opcional(make_client, web):
    """Cuatro fichas piden el aire a la vez con tope 3: entran tres, la cuarta cede."""
    web.add(lambda r: "air-quality" in r.url.host, _air_payload)
    with make_client() as client:
        svc = client.app.state.services
        comunas = list(territory().comunas)[:4]

        async def pedir(comuna):
            return await air_for_comuna(svc, comuna, room=3)

        async def correr():
            return await asyncio.gather(*[pedir(c) for c in comunas])

        resultados = asyncio.run(correr())
        day = svc.open_meteo_day()
    assert sum(1 for r in resultados if r is not None) == 3
    assert day["tasks"]["air"]["today"] == 3, "el tope opcional no se atraviesa en paralelo"


def test_el_punto_de_riesgo_registra_solo_el_exito_y_la_cache_no_gasta(make_client, web):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["latitude"].startswith("-40"):
            return httpx.Response(503)  # la celda que falla
        return _forecast(request)

    web.add(lambda r: r.url.host == "api.open-meteo.com", handler)
    with make_client() as client:
        svc = client.app.state.services
        asyncio.run(risk_point_at(svc, -35.42, -71.61))  # éxito: una ubicación
        asyncio.run(risk_point_at(svc, -35.42, -71.61))  # misma celda 0,1°: caché
        asyncio.run(risk_point_at(svc, -40.10, -72.20))  # fallo del proveedor: cero
        day = svc.open_meteo_day()
    assert day["tasks"]["risk_point"]["today"] == 1
    assert day["total"] == 1


def test_la_lluvia_del_punto_registra_su_gasto_y_la_cache_no_descuenta(make_client, web):
    web.add(lambda r: r.url.host == "api.open-meteo.com", _forecast)
    with make_client() as client:
        svc = client.app.state.services
        primero = client.get("/api/climate/lluvia?lat=-35.4&lon=-71.6").json()
        client.get("/api/climate/lluvia?lat=-35.41&lon=-71.59")  # la misma celda 0,1°
        day = svc.open_meteo_day()
    assert "senal" in primero
    assert day["tasks"]["lluvia"]["today"] == 1, "la segunda consulta de la celda sale de la caché"


def test_el_viento_de_avisos_y_el_clima_de_casos_registran_su_gasto(make_client, web):
    web.add(lambda r: r.url.host == "api.open-meteo.com", _meteo_handler)
    web.add(lambda r: r.url.host == "archive-api.open-meteo.com", lambda r: json_response({"hourly": {}}))
    with make_client() as client:
        svc = client.app.state.services
        asyncio.run(svc.wind_at(-35.423, -71.614))  # viento de los avisos: una ubicación
        asyncio.run(svc.wind_at(-35.421, -71.613))  # la misma celda de 0,01°: caché, no gasta
        asyncio.run(weather.archive_hourly(svc.client, -33.5, -70.8, "2025-01-01", "2025-01-02"))  # casos
        day = svc.open_meteo_day()
    assert day["tasks"]["viento"]["today"] == 1
    assert day["tasks"]["casos"]["today"] == 1
    assert day["total"] == 2


def test_medidores_de_clientes_open_meteo_no_se_pisan():
    """Dos instancias de Services conservan el medidor asociado a su propio cliente HTTP."""
    vistos: list[str] = []
    a = httpx.AsyncClient(transport=httpx.MockTransport(_current))
    b = httpx.AsyncClient(transport=httpx.MockTransport(_current))

    def medidor_a(task, n):
        vistos.append(f"a:{task}:{n}")

    def medidor_b(task, n):
        vistos.append(f"b:{task}:{n}")

    weather.set_day_meter(a, medidor_a)
    weather.set_day_meter(b, medidor_b)

    async def run():
        try:
            await weather.current(a, -35.4, -71.6)
            await weather.current(b, -33.4, -70.6)
        finally:
            weather.clear_day_meter(a, medidor_a)
            weather.clear_day_meter(b, medidor_b)
            await a.aclose()
            await b.aclose()

    asyncio.run(run())
    assert vistos == ["a:viento:1", "b:viento:1"]


def test_la_anomalia_de_lluvia_registra_su_gasto(make_client, monkeypatch):
    """La anomalía (~2 ubicaciones por comuna) registra solo las respuestas servidas."""
    monkeypatch.setattr(rain_mod, "season_window", lambda today: (date(2027, 6, 1), date(2027, 11, 25)))
    with make_client() as client:
        svc = client.app.state.services
        svc._sync_territory_centers()
        with svc.db.connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO rain_normal(comuna_code, days, daily_normals, computed_at) VALUES (?,?,?,?)",
                [(c.code, 30, json.dumps({"06-01": 5.0}), "2027-01-01T00:00:00Z") for c in territory().comunas],
            )

        async def fake_rain(client_, points, **kwargs):
            weather._count(weather.ARCHIVE_URL if "start_date" in kwargs else weather.FORECAST_URL, len(points))
            return [{} for _ in points]

        monkeypatch.setattr(weather, "daily_rain", fake_rain)
        assert asyncio.run(svc.compute_rain_anomaly()) == COMUNAS
        day = svc.open_meteo_day()
    assert day["tasks"]["rain"]["today"] == 2 * COMUNAS
    assert day["total"] == 2 * COMUNAS


# --- hallazgos de revisión (tanda 4): fallo 0 en aluvión/pendiente, rutas que reservan,
# --- tandas con el día lleno, cancelación tras despachar y throttle del ledger ---


def test_el_fallo_del_proveedor_en_la_pasada_de_aluvion_cuesta_cero(make_client, web):
    """Señal y relieve caídos dentro de `aluvion_pass` devuelven la reserva entera.

    El hueco se declara (`senal` null, relieve null) y el aviso no sale; el gasto del
    respaldo que cobraba el fallback silencioso ya no se cobra.
    """
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    with make_client() as client:
        svc = client.app.state.services
        _svc_con_lugar(svc)
        assert asyncio.run(svc.aluvion_pass()) == 0
        day = svc.open_meteo_day()
    assert day["tasks"] == {} and day["total"] == 0, "un fallo del proveedor no gasta el día"


def test_la_pendiente_del_ciclo_con_el_dem_caido_cuesta_cero(make_client, web):
    """El calentamiento de relieve del ciclo con el DEM caído devuelve la reserva: 0 gastado."""
    web.add(lambda r: "/v1/elevation" in r.url.path, lambda r: httpx.Response(503))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        _deteccion_reciente(svc.db)
        asyncio.run(svc.ingest_cycle())
        day = svc.open_meteo_day()
    assert "pendiente" not in day["tasks"]
    assert day["total"] == 0, "el escenario queda en terreno plano y la reserva se devuelve"


def test_api_weather_reserva_antes_de_pedir_y_cede_con_el_dia_lleno(make_client, web, monkeypatch):
    """/api/weather reserva su ubicación antes de la red; con el día lleno degrada con el
    mismo 502 de cuando el proveedor falla, sin salir a la red ni gastar nada."""
    web.add(lambda r: r.url.host == "api.open-meteo.com", _current)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        primero = client.get("/api/weather", params={"lat": -35.42, "lon": -71.60})
        assert primero.status_code == 200
        assert svc.open_meteo_day()["tasks"]["viento"]["today"] == 1
        _dia_lleno(svc)
        segundo = client.get("/api/weather", params={"lat": -33.45, "lon": -70.66})
        day = svc.open_meteo_day()
    assert segundo.status_code == 502 and segundo.json()["detail"]
    assert len([r for r in web.requests if r.url.host == "api.open-meteo.com"]) == 1, "sin cupo no se sale a la red"
    assert day["total"] == weather.DAILY_LOCATIONS_CAP


def test_el_punto_de_riesgo_reserva_antes_de_pedir_y_cede_sin_cupo(make_client, web, monkeypatch):
    """El punto de riesgo reserva antes de la red: con coordenadas distintas el tope opcional
    no se atraviesa y la segunda celda cede como cuando el proveedor falla (None)."""
    web.add(lambda r: r.url.host == "api.open-meteo.com", _forecast)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        # queda cupo para exactamente una celda: la primera entra, la segunda cede.
        _dia_lleno(svc, weather.DAILY_LOCATIONS_CAP - services.OPEN_METEO_RESERVE - 1)
        asyncio.run(risk_point_at(svc, -35.42, -71.61))
        asyncio.run(risk_point_at(svc, -33.45, -70.66))
        day = svc.open_meteo_day()
    assert day["tasks"]["risk_point"]["today"] == 1
    assert day["total"] == weather.DAILY_LOCATIONS_CAP - services.OPEN_METEO_RESERVE
    assert len([r for r in web.requests if r.url.host == "api.open-meteo.com"]) == 1


def test_la_lluvia_del_punto_cede_sin_cupo_y_sigue_respondiendo(make_client, web):
    """Sin tope opcional, /api/climate/lluvia responde igual que ante un fallo del proveedor:
    señal y terreno sin dato, sin tocar la red y sin gastar el día."""
    web.add(lambda r: r.url.host == "api.open-meteo.com", _forecast)
    with make_client() as client:
        svc = client.app.state.services
        _dia_lleno(svc)
        body = client.get("/api/climate/lluvia", params={"lat": -35.4, "lon": -71.6}).json()
        day = svc.open_meteo_day()
    assert body["senal"] is None and body["terreno"]["nivel"] == "sin_dato"
    assert "computed_at" in body and "source" in body
    assert not [r for r in web.requests if r.url.host == "api.open-meteo.com"]
    assert day["tasks"] == {} and day["total"] == weather.DAILY_LOCATIONS_CAP


def test_el_clima_del_caso_reserva_antes_de_pedir_y_cede_con_el_dia_lleno(make_client, web, monkeypatch):
    """El reanálisis del caso reserva su ubicación antes del archivo; con el día lleno
    degrada con el mismo 502 y la caché de un año sirve sin reservar."""
    web.add(lambda r: r.url.host == "archive-api.open-meteo.com", lambda r: json_response({"hourly": {}}))
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        primero = client.get("/api/cases/vina-del-mar-2024/weather")
        assert primero.status_code == 200
        assert svc.open_meteo_day()["tasks"]["casos"]["today"] == 1
        svc.db.execute("DELETE FROM cache WHERE key = ?", ("case-weather:vina-del-mar-2024",))
        _dia_lleno(svc)
        segundo = client.get("/api/cases/vina-del-mar-2024/weather")
        day = svc.open_meteo_day()
    assert segundo.status_code == 502 and segundo.json()["detail"]
    assert len([r for r in web.requests if r.url.host == "archive-api.open-meteo.com"]) == 1
    assert day["total"] == weather.DAILY_LOCATIONS_CAP and "casos" not in day["tasks"]


def test_la_tanda_del_fwi_no_pide_cuando_el_dia_no_da(make_client, monkeypatch):
    """Con el ledger lleno, la tanda del FWI cede antes de pedir: marca de reintento y 0 gastado."""
    with make_client() as client:
        svc = client.app.state.services
        _dia_lleno(svc)
        pedidos: list[int] = []

        async def fake_inputs(client_, points, **_kwargs):
            pedidos.append(len(points))
            return [({}, {}) for _ in points]

        monkeypatch.setattr(weather, "fwi_inputs", fake_inputs)
        with pytest.raises(RuntimeError, match="Sin cupo"):
            asyncio.run(svc.compute_fwi())
        reintento = svc.db.kv_get("fwi_try_at")
        day = svc.open_meteo_day()
    assert pedidos == []
    assert reintento, "la misma tanda retoma en 30 min, como ante un fallo"
    assert day["total"] == weather.DAILY_LOCATIONS_CAP and "fwi" not in day["tasks"]


def test_las_normales_de_lluvia_ceden_por_cupo_sin_gastar(make_client, monkeypatch):
    """Sin cupo para otra celda, las normales guardan lo avanzado y el resto espera a la
    próxima vuelta, igual que cuando se agota el presupuesto de tiempo del ciclo."""
    with make_client() as client:
        svc = client.app.state.services
        _dia_lleno(svc)
        llamadas: list[int] = []

        async def fake_rain(**_kwargs):
            llamadas.append(1)
            return [{}]

        monkeypatch.setattr(weather, "daily_rain", fake_rain)
        assert asyncio.run(svc.build_rain_normals(limit=3)) == 0
        day = svc.open_meteo_day()
    assert llamadas == []
    assert day["total"] == weather.DAILY_LOCATIONS_CAP and "rain" not in day["tasks"]


def test_la_anomalia_de_lluvia_cede_con_el_dia_lleno(make_client, monkeypatch):
    """La anomalía reserva su costo real (~2 por comuna) antes del archivo; sin cupo cede
    como cuando el archivo falla y no gasta nada."""
    monkeypatch.setattr(rain_mod, "season_window", lambda today: (date(2027, 6, 1), date(2027, 11, 25)))
    with make_client() as client:
        svc = client.app.state.services
        svc._sync_territory_centers()
        with svc.db.connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO rain_normal(comuna_code, days, daily_normals, computed_at) VALUES (?,?,?,?)",
                [(c.code, 30, json.dumps({"06-01": 5.0}), "2027-01-01T00:00:00Z") for c in territory().comunas],
            )
        _dia_lleno(svc)
        with pytest.raises(RuntimeError, match="Sin cupo"):
            asyncio.run(svc.compute_rain_anomaly())
        day = svc.open_meteo_day()
    assert day["total"] == weather.DAILY_LOCATIONS_CAP and "rain" not in day["tasks"]


def test_cancelar_el_aire_tras_despachar_conserva_lo_despachado(make_client, monkeypatch):
    """La cancelación después de que la petición salió conserva lo despachado como gasto.

    Un fallo con respuesta cierta (429, red caída) cuesta cero; un corte sin respuesta no
    sabe si Open-Meteo sirvió la ubicación, así que lo despachado se queda gastado y la
    cancelación se re-lanza.
    """
    salio = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        salio.set()
        await asyncio.Event().wait()  # nunca contesta: la respuesta queda incierta
        return _air_payload(_request)

    colgado = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def aire_colgada(client_, lat, lon):
        return await weather._get(colgado, weather.AIR_QUALITY_URL, {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}"})

    monkeypatch.setattr(weather, "air_quality", aire_colgada)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        comuna = territory().by_code[5109]

        async def run():
            try:
                task = asyncio.create_task(air_for_comuna(svc, comuna))
                await salio.wait()  # la petición ya salió a la red
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                await colgado.aclose()

        asyncio.run(run())
        day = svc.open_meteo_day()
    assert day["tasks"]["air"]["today"] == 1, "lo despachado sin respuesta se conserva como gastado"
    assert day["total"] == 1


def test_el_ledger_avisa_al_respaldo_a_lo_sumo_una_vez_por_ventana(make_client, monkeypatch):
    """Un flujo sostenido de registros no dispara una subida del respaldo por cada escritura:
    el aviso sale a lo sumo una vez por `OM_LEDGER_DIRTY_WINDOW_S`."""
    import types

    reloj = types.SimpleNamespace(monotonic=lambda: 0.0)
    avisos = []

    class Respaldo:
        def mark_dirty(self):
            avisos.append(len(avisos) + 1)

        async def stop(self):
            pass  # el cierre de la app lo llama; aquí no hay respaldo real

    monkeypatch.setattr(services, "time", reloj)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "persistence", Respaldo())
        svc._om_ledger_dirty()
        svc._om_ledger_dirty()
        assert avisos == [1], "dentro de la ventana no vuelve a avisar"
        reloj.monotonic = lambda: services.OM_LEDGER_DIRTY_WINDOW_S - 1
        svc._om_ledger_dirty()
        assert avisos == [1]
        reloj.monotonic = lambda: float(services.OM_LEDGER_DIRTY_WINDOW_S)
        svc._om_ledger_dirty()
        assert avisos == [1, 2], "pasada la ventana, el próximo gasto vuelve a avisar"


# --- re-revisión (segunda ronda): medianoche en el despacho, timeouts, reservas de los
# --- avisos, liquidación común y borde final del throttle del ledger ---


# Los escenarios de medianoche usan cupos a escala 1:100 (60 de 85 en vez de 6.000 de
# 8.500): una sola petición de 6.000 ubicaciones supera el largo máximo de URL de httpx
# (`InvalidURL`) y nunca llegaría al transporte.


def _reloj_medianoche(monkeypatch, fase: list):
    """Un reloj de pruebas que cruza la medianoche chilena del 3-abr-2027 (borde DST)."""

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fase[0].astimezone(tz) if tz is not None else fase[0]

    monkeypatch.setattr(services, "datetime", Clock)
    monkeypatch.setattr(weather, "datetime", Clock)


def test_el_despacho_tras_medianoche_cede_cuando_el_dia_nuevo_no_da(make_client, monkeypatch):
    """Re-revisión G1: la reserva de A en D no cubre despachos en D+1.

    A reserva 6.000 en D, la medianoche cae, B reserva 6.000 en D+1 antes de que A
    despache o liquide y ambos pedían 6.000 contra un tope de 8.500: antes D+1 quedaba
    en 12.000. Ahora el despacho de A pide cobertura en D+1 antes de salir a la red; sin
    cupo no se despacha y la tarea degrada como «sin cupo», con D+1 quedando solo en B.
    """
    fase = [datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ)]
    _reloj_medianoche(monkeypatch, fase)
    salieron: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        salieron.append(request)
        return json_response({})

    with make_client() as client:
        svc = client.app.state.services
        day_a = svc._om_reserve("grilla", 6000, 8500)
        assert day_a == "2027-04-03"
        op_a = svc._om_open_op("grilla", day_a, lambda: 8500)
        fase[0] = datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ)  # la medianoche cayó (y el DST)
        # B se lleva 6.000 del día nuevo antes de que A despache o liquide.
        assert svc._om_reserve("ajena", 6000, 8500) == "2027-04-04"

        async def despachar_a():
            http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                with pytest.raises(weather.WeatherError, match="cambió el día"):
                    await weather._get(
                        http,
                        weather.FORECAST_URL,
                        {"latitude": ",".join(["-35.4"] * 6000), "longitude": ",".join(["-71.6"] * 6000)},
                    )
            finally:
                await http.aclose()
            svc._om_settle_op("grilla", weather.end_op(op_a), day_a, 6000, 0)

        asyncio.run(despachar_a())
        weather.end_op(op_a)  # higiene: el cierre dentro de asyncio.run no tocó el contexto externo
        filas = svc.db.query("SELECT day, SUM(used) AS total FROM om_day WHERE day >= '2027-04-03' GROUP BY day")
        usos = {f["day"]: f["total"] for f in filas}
    assert salieron == [], "sin cobertura en el día nuevo, la petición no se despacha"
    assert usos["2027-04-03"] == 0, "la reserva de A en D se devuelve: nunca despachó"
    assert usos["2027-04-04"] == 6000, "solo lo de B: el día nuevo no queda en 12.000"


def test_el_despacho_tras_medianoche_queda_cubierto_y_contado_una_vez(make_client, monkeypatch):
    """Re-revisión G1, rama con cupo: la cobertura traslada la reserva al día nuevo.

    El despacho queda cubierto con una reserva de D+1, lo servido se cuenta una sola vez
    allí (la reserva de D se libera entera) y lo que A gastó de verdad le sigue
    perteneciendo: B solo puede llevarse lo que sobra del tope.
    """
    fase = [datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ)]
    _reloj_medianoche(monkeypatch, fase)

    def handler(_request: httpx.Request) -> httpx.Response:
        return json_response({"hourly": {}})

    with make_client() as client:
        svc = client.app.state.services
        day_a = svc._om_reserve("grilla", 60, 85)
        op_a = svc._om_open_op("grilla", day_a, lambda: 85)
        fase[0] = datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ)

        async def despachar_a():
            http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                await weather._get(
                    http,
                    weather.FORECAST_URL,
                    {"latitude": ",".join(["-35.4"] * 60), "longitude": ",".join(["-71.6"] * 60)},
                )
            finally:
                await http.aclose()
            svc._om_settle_op("grilla", weather.end_op(op_a), day_a, 60, 0)

        asyncio.run(despachar_a())
        weather.end_op(op_a)  # higiene: el cierre dentro de asyncio.run no tocó el contexto externo
        # lo servido de A quedó contado una sola vez en D+1 y le sigue perteneciendo.
        assert svc._om_reserve("ajena", 25, 85) == "2027-04-04"
        assert svc._om_reserve("ajena", 1, 85) is None, "el tope del día nuevo se respeta"
        filas = svc.db.query("SELECT day, SUM(used) AS total FROM om_day WHERE day >= '2027-04-03' GROUP BY day")
        usos = {f["day"]: f["total"] for f in filas}
    assert usos["2027-04-03"] == 0, "la reserva de D se libera entera"
    assert usos["2027-04-04"] == 85, "60 de A + 25 de B: ni una ubicación de más"


def test_un_corte_en_el_dia_nuevo_no_le_imputa_a_la_reserva_del_dia_viejo(make_client, monkeypatch):
    """Re-revisión G2: lo despachado sin respuesta queda en el día del despacho.

    Reservar en D y despachar en D+1: al cortar, D queda en cero (su reserva se libera)
    y lo despachado queda gastado en D+1 —antes todo se imputaba al día de la reserva—.
    """
    fase = [datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ)]
    _reloj_medianoche(monkeypatch, fase)
    salio = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        salio.set()
        await asyncio.Event().wait()  # nunca contesta: la respuesta queda incierta
        return json_response({})

    colgado = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with make_client() as client:
        svc = client.app.state.services
        day_a = svc._om_reserve("grilla", 1, 8500)
        op_a = svc._om_open_op("grilla", day_a, lambda: 8500)
        fase[0] = datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ)

        async def despachar_y_cortar():
            try:
                tarea = asyncio.create_task(
                    weather._get(colgado, weather.FORECAST_URL, {"latitude": "-35.4", "longitude": "-71.6"})
                )
                await salio.wait()  # la petición ya salió en D+1
                tarea.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await tarea
            finally:
                await colgado.aclose()
            svc._om_settle_op("grilla", weather.end_op(op_a), day_a, 1, 0)

        asyncio.run(despachar_y_cortar())
        weather.end_op(op_a)  # higiene: el cierre dentro de asyncio.run no tocó el contexto externo
        filas = svc.db.query("SELECT day, SUM(used) AS total FROM om_day WHERE day >= '2027-04-03' GROUP BY day")
        usos = {f["day"]: f["total"] for f in filas}
    assert usos["2027-04-03"] == 0, "D libera su reserva: nada del corte se le imputa"
    assert usos["2027-04-04"] == 1, "lo despachado queda gastado en el día del despacho"


def test_un_read_timeout_tras_enviar_conserva_y_un_connect_timeout_no(make_client, monkeypatch):
    """Re-revisión S2: `TimeoutException` es subclase de `RequestError` y caía en el reembolso.

    Un ReadTimeout tras despachar deja la respuesta incierta y conserva lo despachado; un
    ConnectTimeout nunca llegó a enviar la petición y sigue valiendo cero.
    """
    with make_client() as client:
        svc = client.app.state.services

        async def correr():
            respuestas = iter([httpx.ReadTimeout("leyó a medias"), httpx.ConnectTimeout("ni conectó")])

            def handler(_request: httpx.Request) -> httpx.Response:
                raise next(respuestas)

            http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                for lat in ("-35.4", "-33.4"):
                    day = svc._om_reserve("prueba", 1, 8500)
                    op = svc._om_open_op("prueba", day, lambda: 8500)
                    with pytest.raises(weather.WeatherError):
                        await weather._get(http, weather.FORECAST_URL, {"latitude": lat, "longitude": "-71.6"})
                    svc._om_settle_op("prueba", weather.end_op(op), day, 1, 0)
            finally:
                await http.aclose()

        asyncio.run(correr())
        day = svc.open_meteo_day()
    assert day["tasks"]["prueba"]["today"] == 1, "el ReadTimeout conserva lo despachado; el ConnectTimeout vale cero"
    assert day["total"] == 1


def test_cancelar_la_tanda_del_fwi_tras_despachar_conserva_lo_despachado(make_client, monkeypatch):
    """Re-revisión S3: el FWI liquidaba con `by_day` y una cancelación (apagado o despliegue)
    devolvía la reserva de una tanda ya despachada. Con la liquidación común, lo que salió
    a la red queda gastado y la cancelación se re-lanza."""
    salio = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        salio.set()
        await asyncio.Event().wait()  # el archivo nunca contesta
        return json_response({})

    colgado = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fwi_colgada(client_, points, **_kwargs):
        return await weather._get(
            colgado,
            weather.ARCHIVE_URL,
            {"latitude": ",".join(["-35.4"] * len(points)), "longitude": ",".join(["-71.6"] * len(points))},
        )

    monkeypatch.setattr(weather, "fwi_inputs", fwi_colgada)
    with make_client() as client:
        svc = client.app.state.services
        tanda = min(COMUNAS, services.FWI_COMUNAS_PER_RUN)

        async def correr():
            try:
                tarea = asyncio.create_task(svc.compute_fwi())
                await salio.wait()  # la tanda ya salió a la red
                tarea.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await tarea
            finally:
                await colgado.aclose()

        asyncio.run(correr())
        day = svc.open_meteo_day()
    assert day["tasks"]["fwi"]["today"] == tanda, "lo despachado de la tanda queda gastado"
    assert day["total"] == tanda


def test_cancelar_el_viento_de_avisos_tras_despachar_lo_registra(make_client, monkeypatch):
    """Re-revisión S3: el viento de avisos no gana bloqueos nuevos (no reserva), pero su
    liquidación también usa el camino común: un corte tras despachar conserva lo que salió
    a la red en vez de registrarlo en cero."""
    salio = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        salio.set()
        await asyncio.Event().wait()  # nunca contesta
        return _current(_request)

    colgado = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def current_colgado(client_, lat, lon):
        return await weather._get(
            colgado, weather.FORECAST_URL, {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "current": "wind_speed_10m"}
        )

    monkeypatch.setattr(weather, "current", current_colgado)
    with make_client() as client:
        svc = client.app.state.services

        async def correr():
            try:
                tarea = asyncio.create_task(svc.wind_at(-35.423, -71.614))
                await salio.wait()  # la petición del viento ya salió
                tarea.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await tarea
            finally:
                await colgado.aclose()

        asyncio.run(correr())
        day = svc.open_meteo_day()
    assert day["tasks"]["viento"]["today"] == 1, "lo despachado del viento queda registrado"
    assert day["total"] == 1


def test_api_weather_no_se_come_la_reserva_de_los_avisos(make_client, web, monkeypatch):
    """Re-revisión S1: la sonda pública admite contra `9.000 − 500 − plan` (ledger en 8.499
    con plan pendiente 0): entra exactamente una ubicación más y el 502 llega antes de
    tocar la reserva de 500, que es del viento de los avisos."""
    web.add(lambda r: r.url.host == "api.open-meteo.com", _current)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        _dia_lleno(svc, weather.DAILY_LOCATIONS_CAP - services.OPEN_METEO_RESERVE - 1)
        primero = client.get("/api/weather", params={"lat": -35.42, "lon": -71.60})
        assert primero.status_code == 200
        day = svc.open_meteo_day()
        # el tope opcional quedó lleno: ni esta sonda ni otra celda pueden comerse los 500.
        segundo = client.get("/api/weather", params={"lat": -33.45, "lon": -70.66})
        day2 = svc.open_meteo_day()
    assert day["tasks"]["viento"]["today"] == 1
    assert day["total"] == weather.DAILY_LOCATIONS_CAP - services.OPEN_METEO_RESERVE
    assert segundo.status_code == 502 and segundo.json()["detail"]
    assert len([r for r in web.requests if r.url.host == "api.open-meteo.com"]) == 1, "sin cupo no se sale a la red"
    assert day2["total"] == weather.DAILY_LOCATIONS_CAP - services.OPEN_METEO_RESERVE


def test_el_clima_del_caso_no_se_come_la_reserva_de_los_avisos(make_client, web, monkeypatch):
    """Re-revisión S1: el reanálisis de casos admite contra `9.000 − 500 − plan` (ledger en
    8.499, plan 0): una visita anónima no puede recorrer casos comiéndose la reserva de 500."""
    web.add(lambda r: r.url.host == "archive-api.open-meteo.com", lambda r: json_response({"hourly": {}}))
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        _dia_lleno(svc, weather.DAILY_LOCATIONS_CAP - services.OPEN_METEO_RESERVE - 1)
        primero = client.get("/api/cases/vina-del-mar-2024/weather")
        assert primero.status_code == 200
        svc.db.execute("DELETE FROM cache WHERE key = ?", ("case-weather:vina-del-mar-2024",))
        segundo = client.get("/api/cases/vina-del-mar-2024/weather")
        day = svc.open_meteo_day()
    assert segundo.status_code == 502 and segundo.json()["detail"]
    assert day["tasks"]["casos"]["today"] == 1
    assert day["total"] == weather.DAILY_LOCATIONS_CAP - services.OPEN_METEO_RESERVE


def test_la_escritura_callada_marca_sucio_al_vencer_la_ventana(make_client, monkeypatch):
    """Re-revisión S4: la escritura suprimida por el throttle no se olvida. Al vencer la
    ventana, la marca pendiente se emite sin que llegue una escritura nueva; antes de
    vencer, no."""
    import types

    reloj = types.SimpleNamespace(monotonic=lambda: 0.0)
    avisos = []

    class Respaldo:
        def mark_dirty(self):
            avisos.append(len(avisos) + 1)

        async def stop(self):
            pass

    monkeypatch.setattr(services, "time", reloj)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "persistence", Respaldo())
        svc._om_ledger_dirty()  # arranca la ventana: avisos [1]
        svc._om_ledger_dirty()  # escritura suprimida: queda pendiente
        assert avisos == [1]
        reloj.monotonic = lambda: 100.0
        svc._om_ledger_flush_pending()  # la ventana aún no vence: no avisa
        assert avisos == [1]
        reloj.monotonic = lambda: float(services.OM_LEDGER_DIRTY_WINDOW_S)
        svc._om_ledger_flush_pending()  # vencida: la marca sale sin nueva escritura
        assert avisos == [1, 2]
        # la marca pendiente quedó consumida: una ventana nueva vuelve a empezar limpio.
        reloj.monotonic = lambda: float(services.OM_LEDGER_DIRTY_WINDOW_S) + 1
        svc._om_ledger_flush_pending()
        assert avisos == [1, 2]


def test_el_cierre_respalda_el_ledger_callado_por_la_ventana(make_client, monkeypatch):
    """Re-revisión S4: al cerrar el proceso con una escritura aún pendiente, la marca se
    emite antes de `Persistence.stop`: el respaldo final sube el ledger al día."""
    import types

    reloj = types.SimpleNamespace(monotonic=lambda: 0.0)
    avisos = []

    class Respaldo:
        def mark_dirty(self):
            avisos.append(len(avisos) + 1)

        async def stop(self):
            pass

    monkeypatch.setattr(services, "time", reloj)
    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(svc, "persistence", Respaldo())
        svc._om_ledger_dirty()  # avisos [1]: arranca la ventana
        svc._om_record("risk", 5)  # gasto real del ledger, callado por la ventana
        assert avisos == [1]
    # al salir del `with`, la app se cierra: la marca pendiente sale antes del respaldo final
    assert avisos == [1, 2], "el cierre emite la marca aunque el throttle hubiera callado el gasto"


# --- re-revisión (tercera ronda): la respuesta que cruza la medianoche se cobra al día del
# --- despacho (G3) y las coberturas del día nuevo se reembolsan en lo no servido (S5) ---


def test_la_respuesta_que_cruza_la_medianoche_se_cobra_al_dia_del_despacho(make_client, monkeypatch):
    """Re-revisión G3: una petición despachada en D y respondida en D+1 se cobra a D.

    La carrera exacta: A reserva 60 en D y despacha; la respuesta queda retenida; cae la
    medianoche de Chile; B reserva 60 de D+1; la respuesta de A se libera y A liquida.
    Antes, `by_day` usaba el día de la respuesta y D+1 quedaba en 120 contra un tope de
    85. Ahora lo servido se imputa al día del DESPACHO —el día que `in_flight` anotó al
    enviar y cuya reserva cubrió la petición—: D queda con lo de A y D+1 solo con lo de B.
    """
    fase = [datetime(2027, 4, 3, 23, 55, tzinfo=CHILE_TZ)]
    _reloj_medianoche(monkeypatch, fase)

    class Retencion(httpx.AsyncBaseTransport):
        """Transporte que retiene la respuesta hasta que el test la libere."""

        def __init__(self) -> None:
            self.llego = asyncio.Event()
            self.liberar = asyncio.Event()

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.llego.set()  # la petición salió a la red: ya está despachada en D
            await self.liberar.wait()  # la respuesta queda retenida
            return httpx.Response(200, json={})

    with make_client() as client:
        svc = client.app.state.services
        day_a = svc._om_reserve("grilla", 60, 85)
        assert day_a == "2027-04-03"
        op_a = svc._om_open_op("grilla", day_a, lambda: 85)

        async def main():
            transporte = Retencion()
            http = httpx.AsyncClient(transport=transporte)
            try:
                tarea = asyncio.create_task(
                    weather._get(
                        http,
                        weather.FORECAST_URL,
                        {"latitude": ",".join(["-35.4"] * 60), "longitude": ",".join(["-71.6"] * 60)},
                    )
                )
                # con tope: si `_get` falla antes de despachar, la prueba no cuelga
                await asyncio.wait_for(transporte.llego.wait(), 5)  # A despachó en D; su reserva de D lo cubre
                fase[0] = datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ)  # la medianoche cayó (y el DST)
                # B se lleva 60 del día nuevo antes de que la respuesta de A llegue.
                assert svc._om_reserve("ajena", 60, 85) == "2027-04-04"
                transporte.liberar.set()
                await tarea  # la respuesta de A llega ya en D+1
            finally:
                await http.aclose()
            svc._om_settle_op("grilla", weather.end_op(op_a), day_a, 60, 0)

        asyncio.run(main())
        weather.end_op(op_a)  # higiene: el cierre dentro de asyncio.run no tocó el contexto externo
        filas = svc.db.query("SELECT day, SUM(used) AS total FROM om_day WHERE day >= '2027-04-03' GROUP BY day")
        usos = {f["day"]: f["total"] for f in filas}
        # la respuesta de A no infló el día nuevo: B tomó 60 y todavía entra lo que
        # falta del tope; si lo servido de A hubiera caído en D+1, ni 25 cabrían.
        assert svc._om_reserve("sonda", 25, 85) == "2027-04-04"
        assert svc._om_reserve("sonda", 1, 85) is None, "el tope del día nuevo se respeta"
    assert usos["2027-04-03"] == 60, "lo servido por A se cobra a D, el día que lo cubrió"
    assert usos["2027-04-04"] == 60, "D+1 queda solo con lo de B: no recibe gasto sin reserva"


def test_la_cobertura_del_dia_nuevo_se_devuelve_cuando_todo_falla(make_client, monkeypatch):
    """Re-revisión S5, fallo total: lo cubierto en el día nuevo se reembolsa como la reserva.

    A reserva 60 en D; cae la medianoche; su despacho en D+1 queda cubierto con 60
    (la cobertura de G1) y el proveedor responde 503. La cobertura se devuelve entera y la
    reserva de D también: sin ese reembolso, cada reintento fallido fugaba su cobertura y
    podía bloquear las tareas del día nuevo. El reembolso además no hunde la fila por
    debajo de lo ya servido ese día: otra pasada de la misma tarea había servido 4.
    """
    fase = [datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ)]
    _reloj_medianoche(monkeypatch, fase)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with make_client() as client:
        svc = client.app.state.services
        day_a = svc._om_reserve("grilla", 60, 85)
        op_a = svc._om_open_op("grilla", day_a, lambda: 85)
        fase[0] = datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ)
        svc._om_record("grilla", 4)  # otra pasada ya sirvió 4 ubicaciones en D+1

        async def despachar_a():
            http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                with pytest.raises(weather.WeatherError):
                    await weather._get(
                        http,
                        weather.FORECAST_URL,
                        {"latitude": ",".join(["-35.4"] * 60), "longitude": ",".join(["-71.6"] * 60)},
                    )
            finally:
                await http.aclose()
            svc._om_settle_op("grilla", weather.end_op(op_a), day_a, 60, 0)

        asyncio.run(despachar_a())
        weather.end_op(op_a)  # higiene: el cierre dentro de asyncio.run no tocó el contexto externo
        fila_nueva = svc.db.one("SELECT used FROM om_day WHERE day = '2027-04-04' AND task = 'grilla'")
        filas = svc.db.query("SELECT day, SUM(used) AS total FROM om_day WHERE day >= '2027-04-03' GROUP BY day")
        usos = {f["day"]: f["total"] for f in filas}
    assert usos["2027-04-03"] == 0, "la reserva de D se devuelve: no sirvió nada"
    assert usos["2027-04-04"] == 4, "la cobertura de D+1 se devuelve entera"
    assert fila_nueva["used"] == 4, "el reembolso no baja de lo efectivamente servido ese día"


def test_la_cobertura_del_dia_nuevo_se_ajusta_a_lo_servido(make_client, monkeypatch):
    """Re-revisión S5, fallo parcial: la cobertura no usada se reembolsa tras medianoche.

    A despacha ya en D+1 dos peticiones cubiertas (50 + 10); la primera la sirve
    Open-Meteo y la segunda responde 503. D+1 queda en 50 —lo servido— y no en 60:
    la cobertura del fallo se devuelve con el mismo delta con signo que la reserva de D,
    que también se libera entera (nada de A despachó en D).
    """
    fase = [datetime(2027, 4, 3, 23, 50, tzinfo=CHILE_TZ)]
    _reloj_medianoche(monkeypatch, fase)
    pedidos = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        pedidos["n"] += 1
        return json_response({}) if pedidos["n"] == 1 else httpx.Response(503)

    def _params(n: int) -> dict:
        return {"latitude": ",".join(["-35.4"] * n), "longitude": ",".join(["-71.6"] * n)}

    with make_client() as client:
        svc = client.app.state.services
        day_a = svc._om_reserve("grilla", 60, 85)
        op_a = svc._om_open_op("grilla", day_a, lambda: 85)
        fase[0] = datetime(2027, 4, 4, 0, 10, tzinfo=CHILE_TZ)

        async def despachar_a():
            http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                await weather._get(http, weather.FORECAST_URL, _params(50))  # la sirve
                with pytest.raises(weather.WeatherError):
                    await weather._get(http, weather.FORECAST_URL, _params(10))  # 503
            finally:
                await http.aclose()
            svc._om_settle_op("grilla", weather.end_op(op_a), day_a, 60, 0)

        asyncio.run(despachar_a())
        weather.end_op(op_a)  # higiene: el cierre dentro de asyncio.run no tocó el contexto externo
        filas = svc.db.query("SELECT day, SUM(used) AS total FROM om_day WHERE day >= '2027-04-03' GROUP BY day")
        usos = {f["day"]: f["total"] for f in filas}
        # D+1 quedó en 50: lo no servido no ocupa cupo y B puede llevarse lo que falta.
        assert svc._om_reserve("ajena", 35, 85) == "2027-04-04"
        assert svc._om_reserve("ajena", 1, 85) is None, "lo no servido no ocupa cupo"
    assert usos["2027-04-03"] == 0, "la reserva de D se libera: nada despachó allí"
    assert usos["2027-04-04"] == 50, "solo lo servido: la cobertura del 503 se devolvió"


# --- re-revisión (cuarta ronda): una cancelación con la petición ya despachada liquida
# --- igual y propaga la CancelledError intacta (sin UnboundLocalError en el finally) ---


def test_cancelar_el_punto_de_riesgo_liquida_y_propaga_la_cancelacion(make_client, monkeypatch):
    """Re-revisión (cuarta ronda): cancelar `risk_point_at` con la ubicación ya despachada.

    Antes, `point` solo se asignaba dentro del try/except: una cancelación (u otra
    excepción) dejaba un UnboundLocalError al evaluar el `finally` —`1 if point is not
    None else 0`—, enmascaraba la CancelledError y la reserva quedaba sin liquidar.
    Ahora el `finally` corre igual —la operación cortada conserva lo despachado como
    gasto del día, vía `_om_served_by_day`— y la CancelledError se propaga intacta.
    """
    class Retencion(httpx.AsyncBaseTransport):
        """Mantiene la respuesta en espera para siempre: la ubicación queda despachada."""

        def __init__(self) -> None:
            self.llego = asyncio.Event()

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.llego.set()  # la petición salió a la red
            await asyncio.Event().wait()  # nunca contesta: la respuesta queda retenida
            return httpx.Response(200, json={})

    with make_client() as client:
        svc = client.app.state.services
        # plan pendiente 0: aquí se prueba la cancelación, no el apretón del plan del día.
        monkeypatch.setattr(svc, "_om_plan_pending", lambda _day=None: 0)
        transporte = Retencion()
        retenido = httpx.AsyncClient(transport=transporte)
        monkeypatch.setattr(svc, "client", retenido)

        async def main():
            tarea = asyncio.create_task(risk_point_at(svc, -35.42, -71.61))
            await transporte.llego.wait()  # la ubicación ya salió a la red
            tarea.cancel()
            try:
                with pytest.raises(asyncio.CancelledError):
                    await tarea  # sin el fix, aquí llegaba el UnboundLocalError del finally
            finally:
                await retenido.aclose()

        asyncio.run(main())
        day = svc.open_meteo_day()
    assert day["tasks"]["risk_point"]["today"] == 1, "lo despachado queda como gasto, sin liquidar la reserva en limbo"
    assert day["total"] == 1
