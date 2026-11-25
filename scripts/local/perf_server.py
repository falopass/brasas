"""Servidor de rendimiento para el CI de navegador (REND-02): la app real, sin red externa.

Arranca la aplicación del repositorio indicado (``--repo``) con datos sembrados deterministas
(``--data``), el planificador apagado y todo proveedor externo bloqueado: cada llamada hacia
afuera recibe un 503 explícito (``main.HTTP_TRANSPORT`` inyectado con ``httpx.MockTransport``),
incluidos los refugios de firms/overpass que crean su propio cliente. No precalienta la API:
la única sonda de disponibilidad es ``GET /ping``; las rutas se miden tal como arrancan.

Contrato con el workflow del agente principal:

    python scripts/local/perf_server.py --repo <checkout> --data <carpeta> --port 8001

- Queda escuchando en ``http://127.0.0.1:<puerto>`` y sirve la web del propio checkout
  (``/`` y ``/web/…``, que en CI es la versión minificada del build) más toda la API.
- El servidor debe iniciarse uno a la vez y en secuencia (base primero, candidata después),
  nunca en paralelo con builds pesados: es la regla de recursos de AGENTS.md.
- La carpeta ``--data`` se siembra sola la primera vez (escala ``demo`` o ``volumen``).
  Si ya tiene una base marcada ``bench_seed_at`` se reusa tal cual (``--resembrar`` la rehace);
  si tiene una base que este script no sembró, aborta sin tocar nada.

El sembrado usa el mismo ``benchmark_api.sembrar`` del checkout de este script, pero importa
el ``backend`` del repositorio servido: los datos nacen con el código que después los sirve.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

RUTA_SCRIPT = Path(__file__).resolve()

# Los datos sembrados van con «bench» en sus ids y nombres: nunca son datos de personas.
sys.path.insert(0, str(RUTA_SCRIPT.parent))
import benchmark_api  # noqa: E402 (el harness vive en la misma carpeta)


def retrasar_config(app, retraso_ms: int):
    """Retrasa solo /api/config sin detener otras solicitudes ni saltarse el SW."""
    async def atender(scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/api/config" and retraso_ms:
            await asyncio.sleep(retraso_ms / 1000)
        await app(scope, receive, send)
    return atender


def _base_propia(ruta_db: Path) -> bool:
    """¿El brasa.db existente lo sembró el benchmark? La marca «bench_seed_at» vive en kv."""
    try:
        conexion = sqlite3.connect(f"file:{ruta_db}?mode=ro", uri=True)
        try:
            fila = conexion.execute("SELECT 1 FROM kv WHERE key = 'bench_seed_at'").fetchone()
            return fila is not None
        finally:
            conexion.close()
    except sqlite3.Error:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="perf_server.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=str(RUTA_SCRIPT.parents[2]),
                        help="checkout a servir (con backend/ y web/); por defecto, el de este script")
    parser.add_argument("--data", required=True,
                        help="carpeta de datos: se siembra la primera vez; debe ser exclusiva de este servidor")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--escala", choices=benchmark_api.ESCALAS, default="demo",
                        help="dataset: demo (2 incidentes) o volumen (2 000 detecciones / 200 incidentes)")
    parser.add_argument("--resembrar", action="store_true",
                        help="rehace la siembra aunque ya exista una base propia del benchmark")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not (repo / "backend" / "main.py").exists():
        print(f"perf_server: {repo} no es un checkout con backend/main.py", file=sys.stderr)
        return 2
    # El backend importado (y por tanto servido) es el del checkout indicado.
    sys.path.insert(0, str(repo))
    data_dir = Path(args.data).resolve()
    ruta_db = data_dir / "brasa.db"
    if ruta_db.exists() and not _base_propia(ruta_db):
        print(
            f"perf_server: {ruta_db} no lo sembró este script; por seguridad no se toca {data_dir}",
            file=sys.stderr,
        )
        return 2

    # Entorno limpio: sin secretos heredados, sin tareas automáticas.
    for clave in benchmark_api.CLAVES_ENV_LIMPIAS:
        os.environ[clave] = ""  # No permite que load_dotenv reponga credenciales.
    # Clave de sitio pública de prueba (nunca un secreto): permite montar el widget
    # Turnstile, que en el navegador es un mock; TURNSTILE_SECRET sigue vacío.
    os.environ["TURNSTILE_SITE_KEY"] = os.environ.get("BRASA_BENCH_TURNSTILE_SITE_KEY", "")
    os.environ["BRASA_STORAGE_URL"] = ""
    os.environ["BRASA_SCHEDULER"] = "0"
    os.environ["BRASA_DATA_DIR"] = str(data_dir)
    epoch = datetime.fromisoformat(os.environ.get("BRASA_BENCH_EPOCH") or datetime.now(timezone.utc).isoformat())
    restaurar_reloj = benchmark_api.congelar_reloj(epoch)

    if args.resembrar and ruta_db.exists():
        # Es una base propia del benchmark: se rehace desde cero (mismo criterio que seed_demo).
        for sobrante in ("brasa.db", "brasa.db-wal", "brasa.db-shm", "work.db", "work.db-wal", "work.db-shm"):
            (data_dir / sobrante).unlink(missing_ok=True)
    if args.resembrar or not ruta_db.exists():
        restaurar_uuid = benchmark_api.congelar_uuid()  # ids estables: los enlaces sobreviven reinicios
        try:
            siembra = benchmark_api.sembrar(data_dir, epoch, args.escala)
        finally:
            restaurar_uuid()
        siembra["db"].close_all()
        print(
            f"perf_server: sembrado {siembra['observaciones']} detecciones en "
            f"{siembra['incidentes']} incidentes ({args.escala})",
            flush=True,
        )
    else:
        print("perf_server: base sembrada anterior, se reusa (use --resembrar para rehacerla)", flush=True)

    # App real del checkout servido, con todo lo externo bloqueado en 503 explícito.
    from backend import main as modulo_principal

    contador = benchmark_api.ContadorExterno()
    modulo_principal.HTTP_TRANSPORT = contador.transporte()
    restaurar_proveedores = benchmark_api.aislar_proveedores(contador.transporte())
    restaurar_reintentos = benchmark_api.acortar_reintentos()

    import uvicorn

    # Contrato de disponibilidad: solo GET /ping. Ninguna ruta de la API se precalienta.
    print(
        f"perf_server LISTO: http://{args.host}:{args.port} "
        f"(sonda: GET /ping; externos: bloqueados con 503; scheduler: apagado)",
        flush=True,
    )
    try:
        app_medida = retrasar_config(
            modulo_principal.app, int(os.environ.get("BRASA_BENCH_CONFIG_DELAY_MS", "0")))
        uvicorn.run(app_medida, host=args.host, port=args.port, log_level="warning",
                    proxy_headers=True, forwarded_allow_ips="127.0.0.1")
    finally:
        restaurar_proveedores()
        restaurar_reintentos()
        restaurar_reloj()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
