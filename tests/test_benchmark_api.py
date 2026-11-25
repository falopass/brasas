"""REND-02: el benchmark reproducible de la API (scripts/local/benchmark_api.py) sin red.

Se prueba lo puro: percentiles por rango más cercano, gate (p95 <= 2 500 ms, sin errores,
mínimo 20 muestras), contadores de SQL y de externos (sin parámetros ni URLs sensibles),
congelamiento de reloj/uuid, siembra determinista, huella estable, veredictos de cuerpos
y el contrato CLI padre/hijo (bandera ``--samples``, dest ``samples``).
Ninguna prueba arranca servidores ni procesos: el hijo del benchmark corre solo en CI manual.
"""

from __future__ import annotations

import inspect
import json
import re
import sys
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import benchmark_api  # noqa: E402


# ------------------------------------------------------------------ estadística

def test_percentil_por_rango_mas_cercano():
    assert benchmark_api.percentil([], 95) is None
    assert benchmark_api.percentil([123.4], 95) == 123.4
    assert benchmark_api.percentil([200.0, 100.0], 50) == 100.0
    # Con 20 muestras, el p95 por rango más cercano es la muestra 19 (la peor queda para el máx).
    veinte = [float(i) for i in range(1, 21)]
    assert benchmark_api.percentil(veinte, 50) == 10.0
    assert benchmark_api.percentil(veinte, 95) == 19.0
    assert benchmark_api.percentil(veinte, 100) == 20.0


def test_resumen_conserva_errores_y_excluye_su_latencia():
    muestras = [
        {"ms": 100.0, "estado": 200},
        {"ms": 3000.0, "estado": 500},
        {"ms": 120.0, "estado": 200, "sql": 8},
        {"ms": 140.0, "estado": 200, "sql": 8},
    ]
    resumen = benchmark_api.resumen_muestras(muestras)
    assert resumen["n"] == 4
    assert resumen["errores"] == 1  # el 500 queda a la vista, no se promedia como si valiera
    assert resumen["p50"] == 120.0
    assert resumen["p95"] == 140.0
    assert resumen["max"] == 140.0
    assert resumen["sql_por_llamada"] == 8.0
    assert "500" in resumen["estados"]


def test_gate_aprobado_y_reprobado_con_motivos():
    buena = {"salud": {"caliente": {"resumen": {"n": 20, "errores": 0, "p95": 100.0}}}}
    ok, motivos = benchmark_api.evaluar_gate(buena, 2500, 20)
    assert ok and motivos == []

    casos = [
        ({}, "sin rutas"),
        ({"salud": {"caliente": {"resumen": {"n": 20, "errores": 0, "p95": 3000.0}}}}, "p95"),
        ({"salud": {"caliente": {"resumen": {"n": 20, "errores": 2, "p95": 100.0}}}}, "error"),
        ({"salud": {"caliente": {"resumen": {"n": 19, "errores": 0, "p95": 100.0}}}}, "muestras"),
        ({"salud": {}}, "sin escenario caliente"),
    ]
    for resultados, texto in casos:
        ok, motivos = benchmark_api.evaluar_gate(resultados, 2500, 20)
        assert not ok
        assert any(texto in motivo for motivo in motivos), (texto, motivos)


# -------------------------------------------------------------- cuerpos/huella

def test_huella_estable_ignora_tiempos_no_los_datos():
    cuerpo_a = json.dumps({
        "startup_ms": 10, "process": {"territory_ms": 2, "work_db_bytes": 500},
        "count": 3, "items": [1, 2],
    }).encode()
    cuerpo_b = json.dumps({
        "startup_ms": 999, "process": {"territory_ms": 88, "work_db_bytes": 900},
        "count": 3, "items": [1, 2],
    }).encode()
    cuerpo_c = json.dumps({
        "startup_ms": 10, "process": {"territory_ms": 2, "work_db_bytes": 500},
        "count": 4, "items": [1, 2],
    }).encode()
    assert benchmark_api.huella_json(cuerpo_a) == benchmark_api.huella_json(cuerpo_b)
    assert benchmark_api.huella_json(cuerpo_a) != benchmark_api.huella_json(cuerpo_c)
    assert benchmark_api.hash_bytes(b"hola") == benchmark_api.hash_bytes(b"hola")
    assert benchmark_api.hash_bytes(b"hola") != benchmark_api.hash_bytes(b"chao")
    # Si el cuerpo no es JSON, la huella es el hash directo.
    assert benchmark_api.huella_json(b"<html>ok</html>") == benchmark_api.hash_bytes(b"<html>ok</html>")


def test_veredicto_de_cuerpos():
    base = {"muestras": [{"estado": 200, "hash": "x", "hash_huella": "h"}]}
    igual = {"muestras": [{"estado": 200, "hash": "x", "hash_huella": "h"}]}
    salvo_tiempos = {"muestras": [{"estado": 200, "hash": "otro", "hash_huella": "h"}]}
    distinta = {"muestras": [{"estado": 200, "hash": "otro", "hash_huella": "otra"}]}
    otro_estado = {"muestras": [{"estado": 404, "hash": "x", "hash_huella": "h"}]}
    assert benchmark_api.veredicto_cuerpos(base, igual) == "equivalentes"
    assert benchmark_api.veredicto_cuerpos(base, salvo_tiempos) == "equivalentes salvo tiempos"
    assert benchmark_api.veredicto_cuerpos(base, distinta) == "distintos"
    assert benchmark_api.veredicto_cuerpos(base, otro_estado) == "estados distintos"
    assert benchmark_api.veredicto_cuerpos(base, base, "contienda") == "no comparables (escrituras en curso)"
    assert benchmark_api.veredicto_cuerpos(base, {"error": "x"}) == "no comparables"


# -------------------------------------------------------------------- contadores

def test_contador_sql_cuenta_y_clasifica_sin_guardar_texto():
    contador = benchmark_api.ContadorSQL()
    contador.registrar("SELECT * FROM incidents WHERE id = 'secreto-personal'")
    contador.registrar("INSERT INTO observations(id) VALUES ('no-debe-guardarse')")
    contador.registrar("  UPDATE kv SET value = 'x'")
    contador.registrar("PRAGMA journal_mode = WAL")
    foto = contador.instantanea()
    assert foto["sql"] == 4
    assert foto["sql_escrituras"] == 2
    # Nunca se guarda el texto de la sentencia ni sus parámetros.
    assert "secreto-personal" not in json.dumps(foto)
    assert "no-debe-guardarse" not in json.dumps(foto)
    contador.reiniciar()
    assert contador.instantanea()["sql"] == 0


def test_contador_sql_separa_el_hilo_de_fondo():
    contador = benchmark_api.ContadorSQL()
    hilo_fondo = threading.Thread()
    contador.excluir(hilo_fondo)
    contador.registrar("SELECT 1")
    contador.registrar("INSERT INTO observations(id) VALUES (?)", hilo=hilo_fondo)
    foto = contador.instantanea()
    assert foto["sql"] == 1
    assert foto["sql_fondo"] == 1
    assert foto["sql_fondo_escrituras"] == 1
    assert foto["sql_escrituras"] == 0


def test_contador_externo_bloquea_cuenta_y_no_guarda_la_url():
    contador = benchmark_api.ContadorExterno()
    with httpx.Client(transport=contador.transporte()) as cliente:
        respuesta = cliente.get("https://proveedor.example/datos?token=SECRETO-SUPER")
        assert respuesta.status_code == 503
        assert respuesta.headers["Retry-After"] == "0"
        cliente.put("http://almacen.bench/storage/db/brasa.db", content=b"x")
    foto = contador.instantanea()
    assert foto["externos"] == 2
    assert foto["externos_put"] == 1
    assert foto["externos_por_host"] == {"proveedor.example": 1, "almacen.bench": 1}
    # Solo el host: la consulta con el token no aparece por ningún lado.
    assert "SECRETO-SUPER" not in json.dumps(foto)
    totales = contador.totales()
    assert totales["put"] == 1
    contador.reiniciar()
    assert contador.instantanea()["externos"] == 0
    assert contador.totales()["total"] == 2  # los acumulados del proceso no se reinician


def test_contador_externo_sirve_el_fixture_solo_en_get():
    fixture = {"db/brasa.db": b"SQLite format 3\x00cuerpo", "db/work.db.gz": b"\x1f\x8bcomprimido"}
    contador = benchmark_api.ContadorExterno(fixture)
    with httpx.Client(transport=contador.transporte()) as cliente:
        brasa = cliente.get("http://almacen.bench/storage/db/brasa.db")
        assert brasa.status_code == 200 and brasa.content == fixture["db/brasa.db"]
        gz = cliente.get("http://almacen.bench/storage/db/work.db.gz")
        assert gz.status_code == 200 and gz.content == fixture["db/work.db.gz"]
        subida = cliente.put("http://almacen.bench/storage/db/brasa.db", content=b"nuevo")
        assert subida.status_code == 200  # las subidas se aceptan y se cuentan
    assert contador.instantanea()["externos_put"] == 1


def test_aislar_proveedores_bloquea_solo_los_refugios_de_clientes():
    import asyncio

    contador = benchmark_api.ContadorExterno()
    restaurar = benchmark_api.aislar_proveedores(contador.transporte())
    try:
        from backend.providers import firms
        assert firms.httpx.Response is httpx.Response  # el resto de httpx se ve igual

        async def _trae():
            # El refugio de firms crea su propio AsyncClient: debe nacer ya bloqueado.
            async with firms.httpx.AsyncClient() as cliente:
                return await cliente.get("https://proveedor.example/dato")

        respuesta = asyncio.run(_trae())
        assert respuesta.status_code == 503
        assert contador.totales()["por_host"] == {"proveedor.example": 1}
    finally:
        restaurar()
    import httpx as modulo
    assert firms.httpx is modulo  # restaurado: el módulo global nunca se tocó


# ---------------------------------------------------------------- reloj y uuid

def test_congelar_reloj_fija_now_y_hoy():
    restaurar = benchmark_api.congelar_reloj(benchmark_api.EPOCA)
    try:
        import datetime as modulo
        assert modulo.datetime.now(timezone.utc) == benchmark_api.EPOCA
        # 1-11-2026: verano de Chile, UTC-3.
        santiago = modulo.datetime.now(ZoneInfo("America/Santiago"))
        assert santiago.utcoffset() == timedelta(hours=-3)
        assert modulo.date.today() == benchmark_api.EPOCA.date()
        assert isinstance(modulo.datetime.now(timezone.utc), modulo.datetime)
    finally:
        restaurar()
    import datetime as modulo
    # Restaurado: la clase del módulo vuelve a ser la real de stdlib.
    assert modulo.datetime is datetime and modulo.date is date


def test_congelar_uuid_secuencial():
    restaurar = benchmark_api.congelar_uuid()
    try:
        primero, segundo = uuid.uuid4(), uuid.uuid4()
        assert primero.int == 1 << 80 and segundo.int == 2 << 80
        assert uuid.uuid4().hex[:12] == "000000000003"
    finally:
        restaurar()
    assert uuid.uuid4().int not in (1, 2, 3)


def test_siembra_no_precalienta_el_proceso_de_medicion():
    source = (Path(__file__).resolve().parents[1] / "scripts/local/benchmark_api.py").read_text()
    medicion = source.split("def _correr_hijo(args)", 1)[1].split("def hijo(args)", 1)[0]
    assert medicion.count("sembrar(") == 1  # únicamente el rol que crea el fixture
    assert 'if args.rol == "fixture"' in medicion
    assert 'respaldos = _leer_fixture' in medicion


def test_aislamiento_no_deja_reponer_secretos_y_fixture_gzip_es_estable():
    source = (Path(__file__).resolve().parents[1] / "scripts/local/benchmark_api.py").read_text()
    assert "INTERNAL_TOKEN" in benchmark_api.CLAVES_ENV_LIMPIAS
    assert "TELEGRAM_WEBHOOK_SECRET" in benchmark_api.CLAVES_ENV_LIMPIAS
    assert 'os.environ[clave] = ""' in source
    assert "gzip.compress(db.snapshot_work(), 6, mtime=0)" in source


# ---------------------------------------------------------------------- siembra

def test_sembrar_es_determinista(tmp_path):
    resultados = []
    for nombre in ("a", "b"):
        restaurar = benchmark_api.congelar_uuid()
        try:
            siembra = benchmark_api.sembrar(tmp_path / nombre, benchmark_api.EPOCA, "demo")
        finally:
            restaurar()
        db = siembra["db"]
        resultados.append((
            db.query("SELECT * FROM observations ORDER BY id"),
            db.query("SELECT id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, n_obs, "
                     "official_ref FROM incidents ORDER BY id"),
            db.query("SELECT id, name, status, started_at, lat, lon FROM official_fires ORDER BY id"),
            db.query("SELECT comuna_code, date, hours FROM boton_rojo ORDER BY comuna_code, date"),
            db.query("SELECT comuna_code, date, level, score, level_combined FROM risk_daily "
                     "ORDER BY comuna_code, date"),
        ))
        db.close_all()
    for columna, (primera, segunda) in zip(("obs", "inc", "ofi", "boton", "riesgo"), zip(*resultados)):
        assert primera == segunda, f"la siembra no fue determinista en {columna}"


def test_sembrar_volumen_mil_detecciones_doscientos_incidentes(tmp_path):
    restaurar = benchmark_api.congelar_uuid()
    try:
        siembra = benchmark_api.sembrar(tmp_path / "volumen", benchmark_api.EPOCA, "volumen")
    finally:
        restaurar()
    assert siembra["observaciones"] == 2000
    assert siembra["incidentes"] == 200
    ruta = benchmark_api.resolver_ruta(benchmark_api.plantilla_de("ficha"), siembra["db"])
    assert ruta.startswith("/api/incidents/") and len(ruta.split("/")[-1]) == 12
    siembra["db"].close_all()


def test_resolver_ruta_falla_sin_incidentes(tmp_path):
    from backend.db import Database

    db = Database(tmp_path / "vacia" / "brasa.db")
    try:
        with pytest.raises(RuntimeError, match="no dejó incidentes"):
            benchmark_api.resolver_ruta(benchmark_api.plantilla_de("ficha"), db)
    finally:
        db.close_all()


def test_las_rutas_medidas_son_publicas_y_sin_datos_personales():
    ids = [ruta["id"] for ruta in benchmark_api.RUTAS]
    assert len(ids) == len(set(ids))
    for ruta in benchmark_api.RUTAS:
        plantilla = ruta["plantilla"]
        assert plantilla.startswith("/api/")
        assert "token" not in plantilla.lower()
        assert "lugar" not in plantilla.lower()
        assert "reports" not in plantilla.lower()
    with pytest.raises(ValueError, match="ruta desconocida"):
        benchmark_api.plantilla_de("no-existe")


# ------------------------------------------------------- medición en proceso

def test_medir_llamada_cuenta_sql_y_guarda_solo_hashes(make_client, tmp_path):
    contador = benchmark_api.ContadorSQL()
    restaurar_traza = benchmark_api.instalar_traza_sqlite(contador)
    restaurar_uuid = benchmark_api.congelar_uuid()
    siembra = None
    try:
        siembra = benchmark_api.sembrar(tmp_path / "data", benchmark_api.EPOCA, "demo")
    finally:
        restaurar_uuid()
    try:
        with make_client() as cliente:
            muestra = benchmark_api.medir_llamada(cliente, "/api/incidents?hours=48", contador)
    finally:
        restaurar_traza()
        if siembra is not None:
            siembra["db"].close_all()
    assert muestra["estado"] == 200
    assert muestra["ms"] >= 0
    assert muestra["sql"] >= 1  # la ruta consultó la base y quedó contada
    assert muestra["sql_fondo"] == 0
    assert muestra["bytes_decodificados"] > 0
    assert len(muestra["hash"]) == 64
    assert len(muestra["hash_huella"]) == 64
    # El contenido del cuerpo no viaja en la muestra: solo hashes.
    assert "incidents" not in json.dumps(muestra)


# ------------------------------------------------------------------ CLI/informe

def test_parser_con_los_valores_del_contrato():
    args = benchmark_api._parser().parse_args(["--repo", "/x", "--out", "/y"])
    assert args.samples == 20
    assert args.escala == "volumen"
    assert args.gate_ms == 2500.0
    assert args.hijo is False
    for rid in args.rutas.split(","):
        benchmark_api.plantilla_de(rid)
    args2 = benchmark_api._parser().parse_args(["--muestras", "5", "--escala", "demo"])
    assert args2.samples == 5


def test_contrato_del_hijo_solo_toca_atributos_que_el_parser_define():
    """Regresión: el hijo accede a ``args.<dest>`` del parser, nunca a la bandera cruda.

    El parser define ``--samples`` con dest ``samples``; un ``args.muestras`` en el hijo
    hacía fallar la creación del fixture con AttributeError (el ``errorFixture`` del CI).
    """
    fuente = inspect.getsource(benchmark_api._correr_hijo)
    usados = sorted(set(re.findall(r"args\.(\w+)", fuente)))
    assert usados, "el hijo dejó de leer args: revisar este test"
    dests = {accion.dest for accion in benchmark_api._parser()._actions}
    for nombre in usados:
        assert nombre in dests, f"el hijo usa args.{nombre} pero el parser no lo define"
    assert "samples" in usados  # el dest real de --samples/--muestras


def test_padre_invoca_al_hijo_con_la_bandera_canonica_de_samples():
    """El padre (``correr_repo``) pasa ``--samples`` al hijo: el dest del parser, no el alias."""
    fuente = inspect.getsource(benchmark_api.correr_repo)
    assert '"--samples", str(muestras)' in fuente
    assert '"--muestras"' not in fuente


def test_las_invocaciones_del_hijo_parsean_con_el_contrato_real():
    """Las líneas que el padre arma para el hijo existen en el parser, con o sin --samples."""
    parser = benchmark_api._parser()
    # El fixture no recibe --samples: el dest tiene default y el hijo no puede explotar.
    args = parser.parse_args(["--hijo", "--repo", "/repo", "--rol", "fixture",
                              "--escala", "demo", "--fixture-dir", "/f"])
    assert args.hijo and args.rol == "fixture" and args.samples == 20
    # Restauración y medición: tal como las arma correr_repo, con la bandera canónica.
    args = parser.parse_args(["--hijo", "--repo", "/repo", "--rol", "restauracion",
                              "--ruta", "estado", "--samples", "20", "--escala", "demo",
                              "--fixture-dir", "/f"])
    assert args.ruta == "estado" and args.samples == 20
    for rol in benchmark_api.ROLES:
        args = parser.parse_args(["--hijo", "--repo", "/repo", "--rol", rol, "--ruta", "salud",
                                  "--samples", "20", "--escala", "demo", "--fixture-dir", "/f"])
        assert args.rol == rol and args.samples == 20
    # El alias --muestras sigue vigente para uso manual: cae en el mismo dest, sin atributo propio.
    args = parser.parse_args(["--muestras", "7"])
    assert args.samples == 7 and not hasattr(args, "muestras")


def test_unir_url():
    assert benchmark_api.unir_url("http://127.0.0.1:8001/", "/api/health") == "http://127.0.0.1:8001/api/health"
    assert benchmark_api.unir_url("http://a.b", "/api/status") == "http://a.b/api/status"


def test_informe_markdown_deja_constatados_los_limites():
    datos = {
        "repo": "/x", "python": "3.12", "escala": "demo", "muestras": 20, "reloj": benchmark_api.EPOCA.isoformat(),
        "gate_ms": 2500.0, "min_muestras": 20,
        "rutas": {"salud": {"caliente": {"resumen": {"n": 20, "errores": 0, "p50": 10.0, "p95": 20.0, "max": 30.0},
                                             "externos_total": {"total": 0}}}},
        "restauracion": {"medido": False, "motivo": "el fixture no se pudo crear"},
        "gate": {"ok": False, "motivos": ["salud: p95 3000 ms > 2500 ms"]},
        "limites": benchmark_api.LIMITES,
    }
    informe = benchmark_api.informe_markdown(datos)
    assert "`salud`" in informe and "p95" in informe and "REPROBADO" in informe
    assert "No medido: el fixture no se pudo crear" in informe
    assert "gzip" in informe  # los límites declaran qué no se midió
    assert "no se modifica ni aumenta sus repeticiones" in informe


def test_informe_comparacion_marca_lo_no_comparable():
    comparacion = {
        "base": "/base", "candidata": "/cand",
        "por_ruta": {"salud": {"caliente": {"cuerpos": "distintos", "p95_base_ms": 10.0,
                                            "p95_candidata_ms": 20.0, "delta_p95_ms": 10.0, "comparable": False}}},
        "gate_candidata": {"ok": True, "motivos": []},
        "limites": benchmark_api.LIMITES,
    }
    informe = benchmark_api.informe_comparacion_markdown(comparacion)
    assert "distintos" in informe
    assert "| no |" in informe  # el delta de p95 queda marcado como no comparable
