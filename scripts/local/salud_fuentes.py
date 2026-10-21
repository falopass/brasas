"""Informe de salud de las fuentes de BRASA (AUTO-15, AUTO-39).

Lee la base local y dice, por fuente, cuándo llegó el último dato, cuándo fue la última
corrida, qué error quedó y qué hacer. Con `--produccion` hace lo mismo sobre el
`/api/status` del sitio desplegado (solo lectura), y agrega dos chequeos que solo existen
allí: el respaldo a R2 y la consulta del cupo de FIRMS.

    python scripts/local/salud_fuentes.py                       tabla para personas (base local)
    python scripts/local/salud_fuentes.py --json                objeto JSON para máquinas
    python scripts/local/salud_fuentes.py --db data/brasa.db
    python scripts/local/salud_fuentes.py --produccion          /api/status del sitio en producción
    python scripts/local/salud_fuentes.py --produccion URL      otro despliegue (preview, local)
    python scripts/local/salud_fuentes.py --desde-archivo x.json   /api/status ya guardado, sin red

Veredictos:

- `al día`: la última corrida terminó bien y está dentro de la cadencia de la fuente.
- `atrasada`: hay un éxito reciente, pero la última corrida falló o la fuente se pasó de
  su cadencia.
- `caída`: la última corrida falló y no hay un éxito dentro de la cadencia.
- `nunca corrió`: la fuente no tiene corridas (ni datos) en la base.

Sale 1 si alguna fuente programada no está al día, o si algún chequeo del sistema
(respaldo, cupo FIRMS) no está al día; 0 si todo está bien. GLM y humo ADPF se sirven a
pedido y no dejan corridas: se informan como `nunca corrió`, pero no deciden el código de
salida porque no tienen cadencia que cumplir.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import tempfile
import textwrap
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.db import Database  # noqa: E402
from backend.freshness import STALE_AFTER_S, age_seconds  # noqa: E402
from backend.settings import load as cargar_settings  # noqa: E402

URL_PRODUCCION = "https://brasa-chile.ddiegosebastianbb.workers.dev"

# Cada fuente declara cómo se busca en la base: `runs` es el filtro sobre ingest_runs,
# `observaciones` el filtro sobre observations y `actividad` la marca de kv de las fuentes que
# no registran corridas. `limite_min` es la cadencia tolerada (dos ciclos, con holgura).
FUENTES = (
    {
        "fuente": "NASA FIRMS",
        "tipo": "ingesta",
        "runs": ("provider = ?", ("NASA FIRMS",)),
        "observaciones": "(source LIKE 'VIIRS%' OR source LIKE 'MODIS%')",
        "limite_min": STALE_AFTER_S // 60,
        "arreglo": "revisar la respuesta de NASA FIRMS y el cron de ingesta",
    },
    {
        "fuente": "NOAA GOES",
        "tipo": "ingesta",
        "runs": ("provider = ?", ("NOAA GOES",)),
        "observaciones": "source LIKE 'GOES%FDCF%'",
        "limite_min": STALE_AFTER_S // 60,
        "arreglo": "revisar el bucket público de NOAA (S3) y el reloj del servidor",
    },
    {
        "fuente": "CONAF",
        "tipo": "ingesta",
        "runs": ("provider LIKE ?", ("CONAF%",)),
        "observaciones": None,
        "limite_min": 60,
        "arreglo": "revisar `backend/providers/conaf.py` y el tablero de CONAF (GEPRIF)",
    },
    {
        "fuente": "DMC",
        "tipo": "ingesta",
        "runs": ("provider LIKE ?", ("%DMC%",)),
        "observaciones": None,
        "limite_min": 180,
        "arreglo": "revisar `backend/providers/dmc.py` y el RSS de avisos de la DMC",
    },
    {
        "fuente": "Open-Meteo",
        "tipo": "ingesta",
        "runs": None,
        "observaciones": None,
        "actividad": "risk_computed_at",
        "limite_min": 360,
        "arreglo": "revisar `api.open-meteo.com` y el cálculo de riesgo (`compute_risk`)",
    },
    {
        "fuente": "GLM",
        "tipo": "a pedido",
        "runs": None,
        "observaciones": "source LIKE '%GLM%'",
        "limite_min": 60,
        "arreglo": (
            "es a pedido y no deja corridas: si `/api/opendata/lightning.geojson` responde 503, "
            "revisar el bucket S3; el workflow semanal lo sondea"
        ),
    },
    {
        "fuente": "humo ADPF",
        "tipo": "a pedido",
        "runs": None,
        "observaciones": "source LIKE '%ADPF%'",
        "limite_min": 60,
        "arreglo": (
            "es a pedido y no deja corridas: si `/api/opendata/smoke.geojson` responde 503, "
            "revisar el bucket S3; el workflow semanal lo sondea"
        ),
    },
)


def _edad_min(marca: str | None, ahora: datetime) -> int | None:
    """Minutos desde una marca ISO; None si falta o no se puede leer."""
    segundos = age_seconds(marca, ahora)
    return None if segundos is None else segundos // 60


def _veredicto(ultima: dict | None, ultimo_ok: dict | None, dato_min: int | None, limite_min: int, ahora: datetime) -> str:
    """Estado de la fuente según su última corrida, su último éxito y el último dato."""
    if ultima is None:
        if dato_min is None:
            return "nunca corrió"
        return "al día" if dato_min <= limite_min else "atrasada"
    if not ultima["ok"]:
        ok_min = _edad_min(ultimo_ok.get("finished_at") or ultimo_ok.get("started_at"), ahora) if ultimo_ok else None
        return "atrasada" if ok_min is not None and ok_min <= limite_min else "caída"
    corrida_min = _edad_min(ultima["started_at"], ahora)
    return "al día" if corrida_min is not None and corrida_min <= limite_min else "atrasada"


def _arreglo(spec: dict, veredicto: str, ultimo_error: str | None) -> str:
    """Acción concreta para la fuente; vacía cuando está al día."""
    if veredicto == "al día":
        return ""
    if veredicto == "nunca corrió":
        return "la ingesta no está encolando: revisar el cron" if spec["tipo"] == "ingesta" else spec["arreglo"]
    error = (ultimo_error or "").lower()
    if spec["fuente"] == "NASA FIRMS" and any(k in error for k in ("429", "too many", "quota", "cupo", "limit")):
        return "revisar `FIRMS_MAP_KEY` en secretos y esperar el reinicio del cupo"
    if spec["fuente"] == "CONAF" and any(k in error for k in ("formato", "columna", "csv", "campo", "keyerror", "parse")):
        return "el formato del tablero cambió: revisar `backend/providers/conaf.py`"
    if spec["fuente"] == "NOAA GOES" and any(k in error for k in ("s3", "listado", "bucket")):
        return "revisar el bucket público de NOAA (S3) y el reloj del servidor"
    return spec["arreglo"]


def _fila(
    spec: dict,
    ultima: dict | None,
    ultimo_ok: dict | None,
    error: tuple[str, str | None] | None,
    dato: str | None,
    ahora: datetime,
) -> dict[str, Any]:
    dato_min = _edad_min(dato, ahora)
    veredicto = _veredicto(ultima, ultimo_ok, dato_min, spec["limite_min"], ahora)
    mensaje, error_at = error or (None, None)
    return {
        "fuente": spec["fuente"],
        "tipo": spec["tipo"],
        "ultimo_dato": dato,
        "dato_min": dato_min,
        "ultima_corrida": ultima["started_at"] if ultima else None,
        "corrida_ok": bool(ultima["ok"]) if ultima else None,
        "ultimo_error": mensaje,
        "error_min": _edad_min(error_at, ahora) if mensaje else None,
        "atraso_min": _edad_min(ultima["started_at"], ahora) if ultima else None,
        "veredicto": veredicto,
        "arreglo": _arreglo(spec, veredicto, mensaje),
    }


def _ultimo_dato(db: Database, spec: dict) -> str | None:
    if not spec["observaciones"]:
        return None
    return db.one(f"SELECT MAX(observed_at) AS t FROM observations WHERE {spec['observaciones']}")["t"]


def _evaluar_ingesta(db: Database, spec: dict, ahora: datetime) -> dict[str, Any]:
    where, params = spec["runs"]
    ultima = db.one(f"SELECT started_at, ok FROM ingest_runs WHERE {where} ORDER BY id DESC LIMIT 1", params)
    ultimo_ok = db.one(f"SELECT started_at, finished_at FROM ingest_runs WHERE {where} AND ok = 1 ORDER BY id DESC LIMIT 1", params)
    error = db.one(
        f"SELECT started_at, message FROM ingest_runs WHERE {where} AND ok = 0 AND message != '' ORDER BY id DESC LIMIT 1", params
    )
    return _fila(
        spec,
        ultima,
        ultimo_ok,
        (error["message"], error["started_at"]) if error else None,
        _ultimo_dato(db, spec),
        ahora,
    )


def _evaluar_actividad(db: Database, spec: dict, ahora: datetime) -> dict[str, Any]:
    """Fuente sin ingest_runs: su última marca de kv (si la tiene) y el error del último ciclo."""
    marca = db.kv_get(spec["actividad"]) if spec.get("actividad") else None
    error = error_at = None
    if spec.get("actividad"):
        try:
            ciclo = json.loads(db.kv_get("last_cycle") or "{}")
        except ValueError:
            ciclo = {}
        error = ciclo.get("risk_error") or ciclo.get("fwi_error")
        error_at = ciclo.get("finished_at")
    ultima = {"started_at": marca, "ok": 0 if error else 1} if marca else None
    ultimo_ok = {"finished_at": marca} if marca else None
    return _fila(spec, ultima, ultimo_ok, (error, error_at) if error else None, _ultimo_dato(db, spec), ahora)


def _resumen(filas: list[dict]) -> dict[str, Any]:
    """Cuentas del informe y el ok que decide el código de salida.

    `ok` exige al día a las fuentes programadas (tipo `ingesta`) y a los chequeos del
    sistema (tipo `sistema`, solo existen con --produccion); las fuentes a pedido se
    informan pero no deciden.
    """
    cuentas = {v: sum(1 for f in filas if f["veredicto"] == v) for v in ("al día", "atrasada", "caída", "nunca corrió")}
    decisivas = [f for f in filas if f["tipo"] in ("ingesta", "sistema")]
    return {
        "ok": all(f["veredicto"] == "al día" for f in decisivas),
        "total": len(filas),
        "al_dia": cuentas["al día"],
        "atrasadas": cuentas["atrasada"],
        "caidas": cuentas["caída"],
        "nunca_corrio": cuentas["nunca corrió"],
    }


def evaluar(db: Database, ahora: datetime | None = None) -> dict[str, Any]:
    """Informe completo: una fila por fuente y el resumen que decide el código de salida."""
    momento = ahora or datetime.now(timezone.utc)
    filas = [_evaluar_ingesta(db, spec, momento) if spec["runs"] else _evaluar_actividad(db, spec, momento) for spec in FUENTES]
    return {
        "generado_at": momento.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fuentes": filas,
        "resumen": _resumen(filas),
    }


# --- Modo producción: los mismos veredictos, leídos del /api/status del sitio ---


def _hora_status(status: dict) -> datetime | None:
    """Reloj del servidor (`time_utc`); las edades se miden contra él, no contra la VM."""
    marca = status.get("time_utc")
    if not marca:
        return None
    try:
        return datetime.fromisoformat(str(marca).replace("Z", "+00:00"))
    except ValueError:
        return None


def _corre_con(spec: dict, provider: str) -> bool:
    """El filtro SQL de la fuente (`provider = ?` / `provider LIKE ?`) aplicado al texto."""
    where, params = spec["runs"]
    if where == "provider = ?":
        return provider == params[0]
    patron = params[0].replace("%", "*").replace("_", "?")
    return fnmatch.fnmatchcase(provider, patron)


def _corridas_status(status: dict, spec: dict) -> tuple[dict | None, dict | None, tuple[str, str | None] | None]:
    """Última corrida, último éxito y último error de la fuente, según runs[]/failures_24h."""
    corridas = [r for r in status.get("runs") or [] if _corre_con(spec, r.get("provider") or "")]
    ultima = None
    reciente = max(corridas, key=lambda r: r.get("started_at") or "", default=None)
    if reciente:
        ultima = {"started_at": reciente.get("started_at"), "ok": 1 if reciente.get("ok") else 0}
    exitos = [r["last_ok_at"] for r in corridas if r.get("last_ok_at")]
    ultimo_ok = {"finished_at": max(exitos)} if exitos else None
    fallas = status.get("failures_24h") or {}
    errores = [
        (fallas[r.get("product")].get("last_failed_at"), fallas[r.get("product")].get("last_error"))
        for r in corridas
        if r.get("product") in fallas and fallas[r["product"]].get("last_error")
    ]
    if errores:
        fecha, mensaje = max(errores, key=lambda e: e[0] or "")
        error = (mensaje, fecha)
    elif ultima and not ultima["ok"]:
        error = (reciente.get("message") or "la corrida falló", ultima["started_at"])
    else:
        error = None
    return ultima, ultimo_ok, error


def _dato_status(status: dict, spec: dict) -> str | None:
    """Último dato de la fuente según `newest_observation` (patrones LIKE de `observaciones`)."""
    if not spec["observaciones"]:
        return None
    patrones = [p.replace("%", "*").replace("_", "?") for p in re.findall(r"'([^']+)'", spec["observaciones"])]
    marcas = [
        marca for fuente, marca in (status.get("newest_observation") or {}).items() if any(fnmatch.fnmatchcase(fuente, p) for p in patrones)
    ]
    return max(marcas) if marcas else None


def _evaluar_status_fuente(status: dict, spec: dict, ahora: datetime) -> dict[str, Any]:
    if spec["runs"]:
        ultima, ultimo_ok, error = _corridas_status(status, spec)
    elif spec.get("actividad"):
        marca = status.get(spec["actividad"])
        ciclo = status.get("last_cycle") or {}
        mensaje = ciclo.get("risk_error") or ciclo.get("fwi_error")
        if mensaje and not isinstance(mensaje, str):
            mensaje = "risk_error" if ciclo.get("risk_error") else "fwi_error"
        ultima = {"started_at": marca, "ok": 0 if mensaje else 1} if marca else None
        ultimo_ok = {"finished_at": marca} if marca else None
        error = (mensaje, ciclo.get("finished_at")) if mensaje else None
    else:
        ultima = ultimo_ok = error = None
    return _fila(spec, ultima, ultimo_ok, error, _dato_status(status, spec), ahora)


def _fila_sistema(
    fuente: str,
    veredicto: str,
    arreglo: str,
    ahora: datetime,
    ultimo_error: str | None = None,
    dato: str | None = None,
) -> dict[str, Any]:
    """Fila de un chequeo del sistema (tipo `sistema`): misma forma que las de fuente."""
    return {
        "fuente": fuente,
        "tipo": "sistema",
        "ultimo_dato": dato,
        "dato_min": _edad_min(dato, ahora) if dato else None,
        "ultima_corrida": None,
        "corrida_ok": None,
        "ultimo_error": ultimo_error,
        "error_min": None,
        "atraso_min": None,
        "veredicto": veredicto,
        "arreglo": arreglo,
    }


def _chequeo_respaldo(status: dict, ahora: datetime) -> dict[str, Any]:
    """El respaldo a R2 del último ciclo (`backup`, `work_backup`, `backup_error`)."""
    ciclo = status.get("last_cycle") or {}
    respaldo = status.get("backup") or {}
    error = ciclo.get("backup_error") or None
    if ciclo.get("backup") and ciclo.get("work_backup") and not error:
        return _fila_sistema("Respaldo", "al día", "", ahora, dato=respaldo.get("updated_at"))
    detalle = (error or "el último ciclo no completó el respaldo (backup/work_backup)")[:160]
    return _fila_sistema(
        "Respaldo",
        "caída",
        "revisar el respaldo a R2 del Worker (`_internal/storage`) y el cron de backup",
        ahora,
        ultimo_error=detalle,
    )


def _chequeo_cupo(status: dict, ahora: datetime) -> dict[str, Any]:
    """La consulta del cupo de FIRMS desde el servidor (`firms_quota.error`)."""
    quota = status.get("firms_quota")
    if not isinstance(quota, dict):
        return _fila_sistema("Cupo FIRMS", "nunca corrió", "el servidor no publica `firms_quota`: revisar /api/status", ahora)
    if quota.get("error"):
        return _fila_sistema(
            "Cupo FIRMS",
            "caída",
            "revisar la consulta del cupo de FIRMS en el servidor (red hacia FIRMS o `FIRMS_MAP_KEY`)",
            ahora,
            ultimo_error="la consulta del cupo está fallando",
            dato=quota.get("checked_at"),
        )
    return _fila_sistema("Cupo FIRMS", "al día", "", ahora, dato=quota.get("checked_at"))


def evaluar_status(status: dict, ahora: datetime | None = None) -> dict[str, Any]:
    """Informe desde el JSON de /api/status: mismos veredictos y arreglos que evaluar(),
    más los chequeos de sistema que solo el sitio publica (respaldo, cupo FIRMS)."""
    momento = ahora or _hora_status(status) or datetime.now(timezone.utc)
    filas = [_evaluar_status_fuente(status, spec, momento) for spec in FUENTES]
    filas += [_chequeo_respaldo(status, momento), _chequeo_cupo(status, momento)]
    return {
        "generado_at": momento.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fuentes": filas,
        "resumen": _resumen(filas),
    }


def descargar_status(url_base: str, timeout: float = 20) -> dict:
    """GET a `<url_base>/api/status` con urllib (sin dependencias nuevas)."""
    url = url_base.rstrip("/") + "/api/status"
    req = Request(url, headers={"User-Agent": "BRASA-salud-fuentes/1.0"})
    with urlopen(req, timeout=timeout) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _corto(marca: str | None) -> str:
    if not marca:
        return "—"
    try:
        return datetime.fromisoformat(marca.replace("Z", "+00:00")).strftime("%d-%m %H:%M")
    except ValueError:
        return marca[:14]


def _duracion(minutos: int | None) -> str:
    if minutos is None:
        return "—"
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    return f"{horas} h {resto} min" if resto else f"{horas} h"


def _celdas(fila: dict) -> list[str]:
    corrida = "—" if fila["ultima_corrida"] is None else f"{_corto(fila['ultima_corrida'])} {'ok' if fila['corrida_ok'] else 'falló'}"
    dato = "—" if fila["ultimo_dato"] is None else f"{_corto(fila['ultimo_dato'])} · {_duracion(fila['dato_min'])}"
    error = "—" if not fila["ultimo_error"] else f"{_duracion(fila['error_min'])} · {fila['ultimo_error']}"
    return [
        fila["fuente"],
        fila["veredicto"],
        dato,
        corrida,
        _duracion(fila["atraso_min"]),
        error,
        fila["arreglo"] or "—",
    ]


def _tabla(filas: list[dict]) -> None:
    cabecera = ["FUENTE", "VEREDICTO", "ÚLTIMO DATO", "ÚLTIMA CORRIDA", "ATRASO", "ERROR", "ARREGLO"]
    datos = [_celdas(f) for f in filas]
    anchos = [max(len(cabecera[i]), *(len(d[i]) for d in datos)) for i in range(5)] + [26, 38]
    total = sum(anchos) + 2 * (len(anchos) - 1)
    sangria = sum(anchos[:5]) + 2 * 5

    def emitir(cells: list[str]) -> None:
        partes = [cells[i].ljust(anchos[i]) for i in range(5)]
        error = textwrap.wrap(cells[5], anchos[5]) or [""]
        arreglo = textwrap.wrap(cells[6], anchos[6]) or [""]
        for i in range(max(len(error), len(arreglo))):
            cola = f"{error[i] if i < len(error) else ''}".ljust(anchos[5]) + "  " + (arreglo[i] if i < len(arreglo) else "")
            print("  ".join(partes) + "  " + cola if i == 0 else " " * sangria + cola)

    emitir(cabecera)
    print("-" * total)
    for fila in datos:
        emitir(fila)


def imprimir(informe: dict) -> None:
    print(f"Salud de las fuentes · {informe['generado_at']} UTC\n")
    _tabla(informe["fuentes"])
    programadas = [f for f in informe["fuentes"] if f["tipo"] == "ingesta"]
    if informe["resumen"]["ok"]:
        print("\nRESULTADO: todas las fuentes programadas están al día.")
        return
    cuentas = {v: sum(1 for f in programadas if f["veredicto"] == v) for v in ("al día", "atrasada", "caída", "nunca corrió")}
    partes = [
        f"{cuentas['al día']} al día",
        f"{cuentas['atrasada']} {'atrasada' if cuentas['atrasada'] == 1 else 'atrasadas'}",
        f"{cuentas['caída']} {'caída' if cuentas['caída'] == 1 else 'caídas'}",
    ]
    if cuentas["nunca corrió"]:
        partes.append(f"{cuentas['nunca corrió']} nunca corrió")
    sistema = [f["fuente"] for f in informe["fuentes"] if f["tipo"] == "sistema" and f["veredicto"] != "al día"]
    if sistema:
        partes.append("sistema: " + ", ".join(sistema))
    print("\nRESULTADO: " + ", ".join(partes) + ". Revisa la columna Arreglo.")


@contextmanager
def _abrir(ruta: Path) -> Iterator[Database]:
    """Abre la base sin crearla cuando no existe: un repo recién clonado se informa vacío."""
    if ruta.is_file():
        db = Database(ruta)
        try:
            yield db
        finally:
            db.close_all()
        return
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "brasa.db")
        try:
            yield db
        finally:
            db.close_all()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Salud de las fuentes de BRASA: última corrida, atraso y arreglo.")
    parser.add_argument("--json", action="store_true", help="salida JSON para máquinas")
    parser.add_argument("--db", type=Path, help="base a leer (por defecto, la de backend.settings)")
    parser.add_argument(
        "--produccion",
        nargs="?",
        const=URL_PRODUCCION,
        metavar="URL",
        help="lee /api/status del sitio (por omisión, el de producción)",
    )
    parser.add_argument("--desde-archivo", type=Path, help="JSON de /api/status ya guardado (sin red)")
    args = parser.parse_args(argv)
    if args.desde_archivo:
        informe = evaluar_status(json.loads(args.desde_archivo.read_text(encoding="utf-8")))
    elif args.produccion:
        informe = evaluar_status(descargar_status(args.produccion))
    else:
        with _abrir(args.db or cargar_settings().db_path) as db:
            informe = evaluar(db)
    if args.json:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
    else:
        imprimir(informe)
    return 0 if informe["resumen"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
