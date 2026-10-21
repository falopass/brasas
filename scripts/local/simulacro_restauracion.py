#!/usr/bin/env python3
"""Simulacro de restauración de un respaldo de BRASA (OPS-10) — versión de escritorio.

    python scripts/local/simulacro_restauracion.py --url URL
    BRASA_BACKUP_URL=URL python scripts/local/simulacro_restauracion.py

ESTE es el simulacro de escritorio: baja el respaldo por URL. El que corre cada mes en
CI (.github/workflows/simulacro-restauracion.yml, día 3) es scripts/simulacro_restauracion.py,
que baja de R2 con wrangler: mismo nombre, otro contrato.

Descarga un respaldo .db o .db.gz a un directorio temporal fuera del repositorio,
comprueba que el SQLite esté íntegro, cuenta las tablas observations, incidents,
places y alerts y compara max(observed_at) con la frescura esperada (--max-edad-h).
Escribe docs/SIMULACRO.md y borra el temporal. Sin URL no abre conexiones y explica
el uso.

La URL puede ser http(s) o file://; también acepta una ruta local. Nunca se imprime
la query ni las credenciales de la URL. Para credenciales usa una variable de entorno
o una URL firmada temporal: nada de secretos en el repositorio.
"""

from __future__ import annotations

import argparse
import gzip
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INFORME = ROOT / "docs" / "SIMULACRO.md"
TABLAS = ("observations", "incidents", "places", "alerts")
TIMEOUT_S = 120
UA = {"User-Agent": "BRASA-Chile simulacro de restauracion"}

SIN_URL = """No hay URL de respaldo: el simulacro no abre conexiones ni toca archivos.

  python scripts/local/simulacro_restauracion.py --url URL
  BRASA_BACKUP_URL=URL python scripts/local/simulacro_restauracion.py

La URL apunta a un respaldo de BRASA (.db o .db.gz). No pongas credenciales en el
repositorio: usa una URL firmada temporal o una variable de entorno."""


@dataclass
class Revision:
    archivo: str
    bytes_descargados: int
    bytes_sqlite: int
    integridad: str = "no verificada"
    tablas: dict[str, int | None] = field(default_factory=lambda: {tabla: None for tabla in TABLAS})
    ultimo_observado: str | None = None
    edad_h: float | None = None
    problemas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problemas


def url_visible(url: str) -> str:
    """URL sin usuario, contraseña, query ni fragmento: lo único que se puede imprimir."""
    partes = urllib.parse.urlsplit(url)
    try:
        puerto = partes.port
    except ValueError:
        puerto = None
    host = partes.hostname or ""
    if puerto:
        host = f"{host}:{puerto}"
    return urllib.parse.urlunsplit((partes.scheme, host, partes.path, "", ""))


def _como_url(valor: str) -> str:
    """Acepta http(s)/file:// y también una ruta local (incluidas las de Windows)."""
    partes = urllib.parse.urlsplit(valor)
    if partes.scheme and len(partes.scheme) > 1:
        return valor
    return Path(valor).expanduser().resolve().as_uri()


def _nombre(url: str) -> str:
    nombre = Path(urllib.parse.urlsplit(url).path).name
    return nombre if nombre and nombre not in {".", ".."} else "respaldo.db"


def descargar(url: str, destino: Path) -> int:
    solicitud = urllib.request.Request(_como_url(url), headers=UA, method="GET")
    with urllib.request.urlopen(solicitud, timeout=TIMEOUT_S) as respuesta, destino.open("wb") as archivo:
        shutil.copyfileobj(respuesta, archivo, 1024 * 1024)
    return destino.stat().st_size


def _es_gzip(ruta: Path) -> bool:
    with ruta.open("rb") as archivo:
        return archivo.read(2) == b"\x1f\x8b"


def preparar(descargado: Path, destino: Path) -> tuple[Path, int]:
    """Descomprime si el archivo es .gz; devuelve la ruta del SQLite y su tamaño."""
    if descargado.suffix != ".gz" and not _es_gzip(descargado):
        return descargado, descargado.stat().st_size
    with gzip.open(descargado, "rb") as origen, destino.open("wb") as salida:
        shutil.copyfileobj(origen, salida, 1024 * 1024)
    return destino, destino.stat().st_size


def _fecha(valor: str) -> datetime | None:
    try:
        fecha = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def _revisar_frescura(conn: sqlite3.Connection, revision: Revision, max_edad_h: float, ahora: datetime) -> None:
    ultimo = conn.execute("SELECT MAX(observed_at) FROM observations").fetchone()[0]
    revision.ultimo_observado = str(ultimo) if ultimo is not None else None
    if ultimo is None:
        revision.problemas.append("observations está vacía: no hay dato para comprobar la frescura")
        return
    fecha = _fecha(str(ultimo))
    if fecha is None:
        revision.problemas.append(f"max(observed_at) no es una fecha ISO: «{ultimo}»")
        return
    revision.edad_h = (ahora - fecha).total_seconds() / 3600
    if revision.edad_h > max_edad_h:
        revision.problemas.append(f"el dato más reciente tiene {revision.edad_h:.1f} h y la frescura máxima es {max_edad_h:g} h")


def verificar(ruta: Path, max_edad_h: float, ahora: datetime | None = None) -> Revision:
    tamano = ruta.stat().st_size
    revision = Revision(ruta.name, tamano, tamano)
    with ruta.open("rb") as archivo:
        cabecera = archivo.read(16)
    if cabecera != b"SQLite format 3\x00":
        revision.problemas.append("el archivo no es una base SQLite (falta la cabecera «SQLite format 3»)")
        return revision
    try:
        conn = sqlite3.connect(f"{ruta.as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        revision.problemas.append(f"no abre como SQLite ({exc})")
        return revision
    try:
        try:
            revision.integridad = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        except sqlite3.DatabaseError as exc:
            revision.problemas.append(f"el SQLite está dañado o truncado ({exc})")
            return revision
        if revision.integridad != "ok":
            revision.problemas.append(f"integrity_check dice «{revision.integridad}»")
        try:
            presentes = {fila[0] for fila in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError as exc:
            revision.problemas.append(f"no se pudieron leer las tablas ({exc})")
            return revision
        for tabla in TABLAS:
            if tabla in presentes:
                try:
                    revision.tablas[tabla] = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
                except sqlite3.DatabaseError as exc:
                    revision.problemas.append(f"no se pudo contar {tabla} ({exc})")
        if all(filas is None for filas in revision.tablas.values()):
            revision.problemas.append("no contiene ninguna de las tablas de BRASA: " + ", ".join(TABLAS))
        if revision.tablas["observations"] is not None:
            try:
                _revisar_frescura(conn, revision, max_edad_h, ahora or datetime.now(timezone.utc))
            except sqlite3.DatabaseError as exc:
                revision.problemas.append(f"no se pudo leer max(observed_at) ({exc})")
    finally:
        conn.close()
    return revision


def _tamano(bytes_: int) -> str:
    if bytes_ >= 1024 * 1024:
        return f"{bytes_ / (1024 * 1024):.1f} MB"
    return f"{bytes_ / 1024:.0f} KB"


def escribir_informe(revision: Revision, destino: Path, url: str, max_edad_h: float, ahora: datetime) -> None:
    lineas = [
        "# Simulacro de restauración",
        "",
        f"- Fecha: {ahora.strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Respaldo: {url}",
        f"- Descargado: {_tamano(revision.bytes_descargados)}",
        f"- SQLite: {_tamano(revision.bytes_sqlite)}",
        f"- Integridad: {revision.integridad}",
        f"- Frescura máxima: {max_edad_h:g} h",
        "",
        "| Tabla | Filas |",
        "|---|---:|",
    ]
    for tabla in TABLAS:
        filas = revision.tablas.get(tabla)
        lineas.append(f"| {tabla} | {'—' if filas is None else filas} |")
    lineas.extend(["", f"- `max(observed_at)`: {revision.ultimo_observado or '—'}"])
    if revision.edad_h is not None:
        lineas.append(f"- Edad del dato: {revision.edad_h:.1f} h")
    lineas.extend(["", f"**Resultado: {'superado' if revision.ok else 'fallido'}**", ""])
    if revision.problemas:
        lineas.append("## Problemas")
        lineas.append("")
        lineas.extend(f"- {problema}" for problema in revision.problemas)
        lineas.append("")
    lineas.extend(["Generado por `scripts/local/simulacro_restauracion.py`.", ""])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas), encoding="utf-8")


def imprimir_revision(revision: Revision, max_edad_h: float) -> None:
    print(f"  Archivo: {revision.archivo} ({_tamano(revision.bytes_sqlite)})")
    print(f"  Integridad: {revision.integridad}")
    for tabla in TABLAS:
        filas = revision.tablas.get(tabla)
        print(f"  {tabla}: {'—' if filas is None else filas}")
    if revision.ultimo_observado:
        edad = f" · {revision.edad_h:.1f} h" if revision.edad_h is not None else ""
        print(f"  Último observed_at: {revision.ultimo_observado}{edad} (máximo {max_edad_h:g} h)")
    for problema in revision.problemas:
        print(f"  ✗ {problema}")


def _mensaje(exc: Exception, url: str) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"sin respuesta ({exc.reason})"
    texto = str(exc).strip() or type(exc).__name__
    return texto.replace(url, url_visible(url))


def _cerrar(revision: Revision, destino: Path, url: str, max_edad_h: float, ahora: datetime) -> int:
    imprimir_revision(revision, max_edad_h)
    try:
        escribir_informe(revision, destino, url, max_edad_h, ahora)
        print(f"  Informe: {destino}")
    except OSError as exc:
        print(f"  ✗ No se pudo escribir el informe en {destino}: {exc}")
        print("\nRESULTADO: fallido")
        return 1
    print("\nRESULTADO: superado" if revision.ok else "\nRESULTADO: fallido")
    return 0 if revision.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="URL del respaldo (.db o .db.gz); también se lee de BRASA_BACKUP_URL")
    parser.add_argument("--max-edad-h", type=float, default=24.0, help="antigüedad máxima de max(observed_at) en horas (defecto: 24)")
    parser.add_argument("--informe", type=Path, default=INFORME, help="dónde escribir el informe (defecto: docs/SIMULACRO.md)")
    args = parser.parse_args(argv)

    url = (args.url or os.getenv("BRASA_BACKUP_URL", "")).strip()
    if not url:
        print(SIN_URL)
        return 0
    if not math.isfinite(args.max_edad_h) or args.max_edad_h <= 0:
        parser.error("--max-edad-h debe ser un número mayor que 0")

    visible = url_visible(url)
    ahora = datetime.now(timezone.utc)
    print(f"» Simulacro de restauración de BRASA\n  URL: {visible}")

    with tempfile.TemporaryDirectory(prefix="brasa-simulacro-") as temporal:
        descargado = Path(temporal) / _nombre(url)
        try:
            bytes_descargados = descargar(url, descargado)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            revision = Revision(descargado.name, 0, 0, problemas=[f"no se pudo descargar: {_mensaje(exc, url)}"])
            return _cerrar(revision, args.informe, visible, args.max_edad_h, ahora)
        if bytes_descargados == 0:
            revision = Revision(descargado.name, 0, 0, problemas=["el archivo descargado está vacío (0 bytes)"])
            return _cerrar(revision, args.informe, visible, args.max_edad_h, ahora)
        print(f"  Descargado: {_tamano(bytes_descargados)}")

        try:
            sqlite_path, bytes_sqlite = preparar(descargado, Path(temporal) / "respaldo.db")
        except (OSError, EOFError) as exc:
            revision = Revision(descargado.name, bytes_descargados, 0, problemas=[f"el .gz no descomprime ({exc})"])
            return _cerrar(revision, args.informe, visible, args.max_edad_h, ahora)

        revision = verificar(sqlite_path, args.max_edad_h, ahora)
        revision.archivo = descargado.name
        revision.bytes_descargados = bytes_descargados
        revision.bytes_sqlite = bytes_sqlite
        return _cerrar(revision, args.informe, visible, args.max_edad_h, ahora)


if __name__ == "__main__":
    sys.exit(main())
