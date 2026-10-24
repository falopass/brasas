"""Edad de los datos versionados de `web/data` (AUTO-16).

Los JSON versionados (censo, normales de lluvia, historia por comuna, temporada, focos fijos,
comunas prioritarias) cambian cada temporada o cada año y los lee el vecino sin que nadie mida
su edad. `inventario` devuelve, por cada archivo que importa, la fecha que el propio JSON declara
(`fetched_at`/`generated_at`, o `source.date` dentro de `source`) —y si no trae ninguna, la fecha
del archivo, dicha como tal (`version_fuente: "mtime"`)—, su edad en días, su estado
(`al_dia` | `viejo` | `falta`), su tamaño y el «qué hacer» concreto.

Las ventanas y las recetas de regeneración son las mismas que revisa la sonda de CI
`scripts/local/revisar_datos_versionados.py` (`CADUCIDAD_DIAS`/`REGENERA`): el contenedor no
embarca `scripts/` (el Dockerfile copia solo `backend` y `web`), así que la tabla vive aquí con
el nombre legible y la fuente oficial de cada archivo. Si una ventana cambia, se cambia en los
dos lados. `persistent_hotspots.json` y `mascara-norte.json` están exentos de caducidad en la
sonda porque cada punto/celda declara su propia vigencia (`valid_from`/`valid_to`, `revisar_el`);
aquí llevan una ventana anual de revisión porque el API solo publica `al_dia`/`viejo`/`falta`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

# La tabla: archivo, nombre legible, fuente oficial, ventana de actualización esperada en días
# y el «qué hacer» en español neutro (la receta para regenerarlo, como la sonda de CI).
DATOS: tuple[dict[str, Any], ...] = (
    {
        "archivo": "censo_2024.json",
        "nombre": "Exposición por comuna (población, viviendas, hogares)",
        "fuente": "INE · Censo 2024 (capa CENSO2024_V2_gdb, CC BY-SA 4.0)",
        "ventana_dias": 365,
        "que_hacer": "vuelve a correr `scripts/local/build_censo.py` con la capa del INE y sube el JSON",
    },
    {
        "archivo": "campamentos.json",
        "nombre": "Campamentos catastrados por comuna (agregado, sin puntos ni nombres)",
        "fuente": "MINVU · Catastro Nacional de Campamentos (capa Catastros_campamentos)",
        "ventana_dias": 365,
        "que_hacer": "vuelve a correr `scripts/local/build_campamentos.py --refresh` con la capa del MINVU y sube el JSON",
    },
    {
        "archivo": "rain_normals.json",
        "nombre": "Normales de lluvia 1991-2020 por celda",
        "fuente": "Open-Meteo archive (ERA5)",
        "ventana_dias": 365,
        "que_hacer": "vuelve a correr `scripts/local/build_rain_normals.py`",
    },
    {
        "archivo": "interfaz.json",
        "nombre": "Zona de interfaz urbano-forestal por comuna",
        "fuente": "CONAF GEPRIF (capa riesgo_dissolve_point)",
        "ventana_dias": 365,
        "que_hacer": "vuelve a correr `scripts/local/build_interfaz.py` con la capa de GEPRIF",
    },
    {
        "archivo": "historia-comunas.json",
        "nombre": "Historia de incendios por comuna",
        "fuente": "CONAF GEPRIF (puntos de inicio 2002-2024)",
        "ventana_dias": 365,
        "que_hacer": "vuelve a correr `scripts/local/build_historia_comunas.py`",
    },
    {
        "archivo": "temporada-2526.json",
        "nombre": "Totales de la temporada 2025-2026",
        "fuente": "CONAF GEPRIF (reporte público de incendios)",
        "ventana_dias": 45,
        "que_hacer": "vuelve a correr `scripts/local/build_temporada_2526.py --refresh` con el CSV de la temporada",
    },
    {
        "archivo": "persistent_hotspots.json",
        "nombre": "Fuentes de calor fijas conocidas (volcanes, industria)",
        "fuente": "BRASA (curada; cada punto declara su propia vigencia)",
        "ventana_dias": 365,
        "que_hacer": "revisa el `valid_from`/`valid_to` de cada punto; se regenera con `scripts/build_persistent_mask.py`",
    },
    {
        "archivo": "mascara-norte.json",
        "nombre": "Máscara regional de falsos positivos del norte (celdas medidas)",
        "fuente": "BRASA (medición propia con medir_falsos_positivos.py; cada celda declara su revisar_el)",
        "ventana_dias": 365,
        "que_hacer": "revisa el `revisar_el` de cada celda; se calibra con `scripts/local/medir_falsos_positivos.py` (INV-25)",
    },
    {
        "archivo": "prioritarias.json",
        "nombre": "Comunas prioritarias de prevención 2026-2027",
        "fuente": "CONAF",
        "ventana_dias": 365,
        "que_hacer": "actualízalo a mano cuando CONAF publique el listado oficial (ver `note` del JSON)",
    },
)


def _marca(data: object) -> datetime | None:
    """Primera fecha legible del payload: `fetched_at`/`generated_at` en la raíz o dentro de
    `source` (donde también se acepta `date`), las convenciones del repo."""
    if not isinstance(data, dict):
        return None
    fuente = data.get("source")
    for d in (data, fuente if isinstance(fuente, dict) else {}):
        for clave in ("fetched_at", "generated_at", "date"):
            valor = d.get(clave)
            if not isinstance(valor, str) or not valor:
                continue
            try:
                m = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            except ValueError:
                continue
            return m if m.tzinfo else m.replace(tzinfo=timezone.utc)
    return None


def inventario(
    data_dir: Path,
    ahora: datetime | None = None,
    tabla: Sequence[Mapping[str, Any]] = DATOS,
) -> list[dict[str, Any]]:
    """Una fila por dato de `tabla`: versión declarada o del archivo, edad, estado y tamaño.

    Si el archivo no existe, `estado` es `falta` y la versión queda en null: nunca se inventa
    una fecha. Un JSON ilegible o sin campo de fecha usa la fecha del archivo y lo dice
    (`version_fuente: "mtime"`); si ni eso se puede leer, la fila sale como `falta` de fecha.
    """
    ahora = ahora or datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for entrada in tabla:
        fila: dict[str, Any] = {
            "archivo": entrada["archivo"],
            "nombre": entrada["nombre"],
            "fuente": entrada["fuente"],
            "ventana_dias": entrada["ventana_dias"],
            "que_hacer": entrada["que_hacer"],
            "version": None,
            "version_fuente": None,
            "edad_dias": None,
            "estado": "falta",
            "tamano_kb": None,
        }
        path = data_dir / entrada["archivo"]
        if not path.is_file():
            out.append(fila)
            continue
        marca: datetime | None = None
        origen = "mtime"
        try:
            marca = _marca(json.loads(path.read_text(encoding="utf-8")))
            if marca is not None:
                origen = "campo"
        except (OSError, json.JSONDecodeError):
            pass
        try:
            stat = path.stat()
        except OSError:
            out.append(fila)
            continue
        if marca is None:
            marca = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        edad = max(0, (ahora - marca).days)
        fila.update(
            version=marca.isoformat(),
            version_fuente=origen,
            edad_dias=edad,
            estado="viejo" if edad > entrada["ventana_dias"] else "al_dia",
            tamano_kb=round(stat.st_size / 1024, 1),
        )
        out.append(fila)
    return out
