"""Orquesta dos servidores reproducibles y un navegador, exclusivamente en CI/Cloud.

No construye ni despliega. El workflow prepara dos checkouts minificados. Los
servidores usan datos sintéticos aislados, sin credenciales ni servicios externos.
La espera de disponibilidad usa /ping, nunca calienta una ruta API del benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def revision(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


# Rutas medidas por defecto en cada job del workflow de rendimiento (REND-02): portada,
# listado de riesgo, mapa solo, mapa con capas en el encuadre de país, mapa con capas
# acercado a Santiago (lat/lon/z: teselas de infraestructura reales del encuadre) y
# páginas de contenido. Cualquier otra ruta de medir_rendimiento.RUTAS requiere --ruta.
RUTAS_CI_PREDETERMINADAS = "mi-zona,riesgo,mapa,mapa-capas,mapa-capas-santiago,temporada,preparate,quehago,mas"


def esperar_servidor(proceso: subprocess.Popen, url: str, timeout: float = 60) -> None:
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if proceso.poll() is not None:
            raise RuntimeError(f"Servidor terminado con código {proceso.returncode}")
        try:
            with urllib.request.urlopen(url + "/ping", timeout=1) as respuesta:
                if respuesta.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.2)
    raise TimeoutError("Servidor sin respuesta en /ping; no se calentó la API")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-repo", type=Path, required=True)
    p.add_argument("--candidate-repo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--network", required=True)
    p.add_argument("--cpu", required=True)
    p.add_argument("--cache", required=True)
    p.add_argument("--retraso-config-ms", type=int, default=0)
    p.add_argument("--verificar-config", action="store_true")
    p.add_argument("--ruta", default=RUTAS_CI_PREDETERMINADAS)
    args = p.parse_args(argv)
    if not 0 <= args.retraso_config_ms <= 10000:
        p.error("--retraso-config-ms debe estar entre 0 y 10000")
    args.out.mkdir(parents=True, exist_ok=True)
    harness = args.candidate_repo / "scripts" / "local"
    procesos, logs = [], []
    epoch = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        with tempfile.TemporaryDirectory(prefix="brasa-perf-ci-") as tmp:
            for etiqueta, repo, port in (
                ("base", args.base_repo, 8001), ("candidata", args.candidate_repo, 8002)
            ):
                log = (args.out / f"servidor-{etiqueta}.log").open("w")
                logs.append(log)
                proceso = subprocess.Popen(
                    [sys.executable, str(harness / "perf_server.py"),
                     "--repo", str(repo), "--data", str(Path(tmp) / etiqueta), "--port", str(port)],
                    cwd=repo, stdout=log, stderr=subprocess.STDOUT,
                    env={**os.environ, "BRASA_SCHEDULER": "0", "BRASA_BENCH_EPOCH": epoch,
                         "BRASA_BENCH_CONFIG_DELAY_MS": str(args.retraso_config_ms),
                         # Clave de sitio de prueba documentada por Cloudflare, igual en ambos servidores.
                         "BRASA_BENCH_TURNSTILE_SITE_KEY": "1x00000000000000000000AA"},
                )
                procesos.append(proceso)
                esperar_servidor(proceso, f"http://127.0.0.1:{port}")
            hashes = {}
            for etiqueta, repo in (("base", args.base_repo), ("candidata", args.candidate_repo)):
                h = hashlib.sha256()
                for path in sorted((repo / "web" / "data").rglob("*")):
                    if path.is_file():
                        h.update(str(path.relative_to(repo)).encode())
                        h.update(path.read_bytes())
                hashes[etiqueta] = h.hexdigest()
            (args.out / "revisiones.json").write_text(json.dumps({
                "base": revision(args.base_repo), "candidata": revision(args.candidate_repo),
                "hashDatosVersionados": hashes,
                "fechaFixture": epoch,
            }, indent=2))
            resultado = subprocess.call([
                sys.executable, str(harness / "comparar_rendimiento.py"),
                "--base", "http://127.0.0.1:8001", "--candidate", "http://127.0.0.1:8002",
                "--out", str(args.out), "--device", args.device, "--network", args.network,
                "--cpu", args.cpu, "--cache", args.cache, "--ruta", args.ruta, "--samples", "5",
                "--retraso-config-ms", str(args.retraso_config_ms),
                "--revision-base", revision(args.base_repo),
                "--revision-candidata", revision(args.candidate_repo),
                "--hash-datos", "base:" + hashes["base"],
                "--hash-datos", "candidata:" + hashes["candidata"],
            ], env={**os.environ, "BRASA_BENCH_CLIENT_IPS": "1",
                    "BRASA_BENCH_CONFIG_SERVER": "1"})
            if args.verificar_config and args.retraso_config_ms:
                comprobacion = subprocess.call([
                    sys.executable, str(harness / "config_check.py"),
                    "--url", "http://127.0.0.1:8002", "--out", str(args.out / "config"),
                    "--device", args.device, "--retraso-config-ms", str(args.retraso_config_ms),
                    "--exigir-no-bloqueante",
                ])
                resultado = resultado or comprobacion
            return resultado
    finally:
        for proceso in procesos:
            proceso.terminate()
        for proceso in procesos:
            try:
                proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    sys.exit(main())
