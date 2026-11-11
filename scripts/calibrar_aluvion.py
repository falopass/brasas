"""Calibración del aviso de aluvión post-incendio con lluvia real de los últimos 180 días.

Cruza tres insumos, todos públicos y reproducibles:

1. **Huella de calor**: los incendios de la temporada 2025-26 del reporte público de CONAF
   (GEPRIF, el mismo CSV que BRASA ya ingiere) con `sup_total` >= `--min-ha`. Se usan como
   cicatriz porque la huella satelital propia de BRASA solo guarda 45 días de observaciones
   (`RETENTION_DAYS`) y no alcanza a cubrir la ventana de 180 días.
2. **Lluvia e isoterma 0 °C**: el archivo del pronóstico horario de Open-Meteo
   (historical-forecast-api, `precipitation` y `freezing_level_height`), en la misma celda de
   0,1° que usa `/api/climate/lluvia`. Es el producto que BRASA habría leído, no una estación.
3. **Ladera**: la grilla 3×3 de Horn de `backend/providers/elevation.py` sobre Copernicus
   GLO-90 vía Open-Meteo, con paso de 1 km alrededor del punto de inicio del incendio (pendiente
   a escala de ladera o cuenca chica) y la cota máxima de esas 9 muestras.

Para cada incendio y cada día local posterior a su inicio dentro de la ventana, guarda la peor
ventana de 3 h y su isoterma, con la misma suma de 3 horas seguidas que `backend.lluvia.ventana`.
Con eso cuenta, por combinación de umbrales (lluvia, ladera y lluvia líquida sobre la cota), cuántos
incendios habrían generado avisos, cuántos días y cuántos temporales (días seguidos = uno), y si la
combinación habría marcado el aluvión de Quebrada Honda (Las Condes, 8-oct-2026, incendio «Plaza
Sur» del 29-dic-2025). El análisis está en `docs/aluvion-calibracion.md`.

Uso (pesado y con cupo de Open-Meteo: corre en una máquina remota, no en el notebook):

    python scripts/calibrar_aluvion.py --fin 2026-11-09 --out out/calib.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import lluvia  # noqa: E402
from backend.providers.elevation import slope_aspect_from_grid  # noqa: E402

CONAF_CSV = "https://raw.githubusercontent.com/deigeprif/public/main/reporte/incendios_totales_25_26.csv"
HIST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
ELEV_URL = "https://api.open-meteo.com/v1/elevation"
CHILE = ZoneInfo("America/Santiago")
UMBRALES_MM_3H = (8.0, 10.0, 12.0, 15.0, 20.0)
# Evento de control: el aluvión de Quebrada Honda del 8-oct-2026 (CR2, análisis del 9-oct-2026).
EVENTO = {"nombre": "PLAZA SUR", "comuna": "Las Condes", "fecha": "2026-10-08"}


def _ha(texto: str) -> float:
    try:
        return float((texto or "0").replace(".", "").replace(",", ".")) if texto.count(",") else float(texto or 0)
    except ValueError:
        return 0.0


def _get(client: httpx.Client, url: str, params: dict) -> dict:
    for intento in range(6):
        try:
            r = client.get(url, params=params, timeout=180)
        except httpx.TransportError:
            time.sleep(15 * (intento + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(20 * (intento + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Open-Meteo no respondió tras 6 intentos: {url}")


def incendios(client: httpx.Client, min_ha: float) -> list[dict]:
    texto = client.get(CONAF_CSV, timeout=60).text
    out = []
    for row in csv.DictReader(io.StringIO(texto)):
        ha = _ha(row.get("sup_total", ""))
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
            inicio = datetime.strptime(row["f_inicio"][:16], "%Y-%m-%d %H:%M").replace(tzinfo=CHILE)
        except (KeyError, ValueError):
            continue
        if ha >= min_ha:
            out.append({"id": row["id"], "nombre": row["nombre"], "comuna": row["comuna"], "ha": ha,
                        "lat": lat, "lon": lon, "inicio": inicio.date().isoformat()})
    return out


PASO_RELIEVE_M = 1000.0


def relieve(client: httpx.Client, fires: list[dict], cache: Path) -> None:
    """Pendiente de ladera y cota máxima del entorno de cada incendio.

    Es la grilla 3×3 de Horn de producción (`slope_aspect_from_grid`) con paso de 1 km en
    vez de 90 m: mide la pendiente a escala de ladera o cuenca chica (~2×2 km), no la del
    punto. El punto de CONAF es el inicio del fuego y suele quedar en el borde urbano
    (Plaza Sur: 6,6° con paso de 90 m). Nueve coordenadas por incendio, 11 incendios por llamada.
    """
    import math
    cache.mkdir(parents=True, exist_ok=True)
    faltan = []
    for f in fires:
        archivo = cache / f"relieve1k_{f['id']}.json"
        if archivo.exists():
            f.update(json.loads(archivo.read_text(encoding="utf-8")))
        else:
            faltan.append(f)
    for i in range(0, len(faltan), 11):
        lote = faltan[i:i + 11]
        pts = []
        for f in lote:
            dlat = PASO_RELIEVE_M / 111320.0
            dlon = PASO_RELIEVE_M / (111320.0 * math.cos(math.radians(f["lat"])))
            pts += [(f["lat"] + dy * dlat, f["lon"] + dx * dlon) for dy in (1, 0, -1) for dx in (-1, 0, 1)]
        z = _get(client, ELEV_URL, {"latitude": ",".join(f"{a:.5f}" for a, _ in pts),
                                    "longitude": ",".join(f"{b:.5f}" for _, b in pts)})["elevation"]
        for n, f in enumerate(lote):
            zz = z[9 * n:9 * n + 9]
            dato = {"slope_max_deg": round(slope_aspect_from_grid(zz, PASO_RELIEVE_M)[0], 1),
                    "elev_max_m": max(zz), "elev_centro_m": zz[4]}
            (cache / f"relieve1k_{f['id']}.json").write_text(json.dumps(dato), encoding="utf-8")
            f.update(dato)
        time.sleep(1.0)


def series(client: httpx.Client, celdas: list[tuple[float, float]], inicio: date, fin: date, cache: Path) -> dict:
    """Serie horaria por celda de 0,1°: {celda: {"time", "precipitation", "freezing_level_height"}}.

    Cada celda queda en `cache` al bajarla: una corrida cortada retoma donde quedó.
    """
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    archivo = {c: cache / f"{c[0]:.1f}_{c[1]:.1f}_{inicio}_{fin}.json" for c in celdas}
    for c in celdas:
        if archivo[c].exists():
            out[c] = json.loads(archivo[c].read_text(encoding="utf-8"))
    faltan = [c for c in celdas if c not in out]
    for i in range(0, len(faltan), 5):
        lote = faltan[i:i + 5]
        data = _get(client, HIST_URL, {
            "latitude": ",".join(f"{a:.1f}" for a, _ in lote),
            "longitude": ",".join(f"{b:.1f}" for _, b in lote),
            "hourly": "precipitation,freezing_level_height",
            "start_date": inicio.isoformat(), "end_date": fin.isoformat(), "timezone": "UTC",
        })
        data = data if isinstance(data, list) else [data]
        for celda, d in zip(lote, data):
            out[celda] = d["hourly"]
            archivo[celda].write_text(json.dumps(d["hourly"]), encoding="utf-8")
        time.sleep(1.5)
    return out


def peores_por_dia(hourly: dict) -> dict[str, dict]:
    """Peor ventana de 3 h que empieza en cada día local de Chile: {fecha: {mm_3h, isoterma_m, inicio}}."""
    t, mm, iso = hourly["time"], hourly["precipitation"], hourly.get("freezing_level_height") or []
    dias: dict[str, dict] = {}
    for i in range(len(t) - lluvia.VENTANA_HORAS + 1):
        tramo = mm[i:i + lluvia.VENTANA_HORAS]
        if any(v is None for v in tramo):
            continue
        total = round(sum(tramo), 1)
        c = i + lluvia.VENTANA_HORAS // 2
        dia = datetime.fromisoformat(t[i]).replace(tzinfo=timezone.utc).astimezone(CHILE).date().isoformat()
        if dia not in dias or total > dias[dia]["mm_3h"]:
            dias[dia] = {"mm_3h": total, "isoterma_m": iso[c] if c < len(iso) else None, "inicio": t[i]}
    return dias


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-ha", type=float, default=10.0)
    ap.add_argument("--dias", type=int, default=180)
    ap.add_argument("--fin", default=None, help="último día (AAAA-MM-DD), por defecto ayer")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    fin = date.fromisoformat(args.fin) if args.fin else datetime.now(CHILE).date() - timedelta(days=1)
    inicio = fin - timedelta(days=args.dias - 1)

    with httpx.Client(headers={"User-Agent": "brasa-calibracion/1.0"}) as client:
        fires = incendios(client, args.min_ha)
        relieve(client, fires, Path(args.out).parent / "cache")
        celdas = sorted({(round(f["lat"], 1), round(f["lon"], 1)) for f in fires})
        horas = series(client, celdas, inicio, fin, Path(args.out).parent / "cache")

    por_celda = {c: peores_por_dia(h) for c, h in horas.items()}
    filas = []  # un registro por incendio y día posterior al fuego
    for f in fires:
        dias = por_celda[(round(f["lat"], 1), round(f["lon"], 1))]
        for dia, v in dias.items():
            if dia > f["inicio"] and inicio.isoformat() <= dia <= fin.isoformat():
                filas.append({"fire": f["id"], "dia": dia, "slope": f["slope_max_deg"],
                              "elev_max": f["elev_max_m"], **v})

    def regla(fila: dict, umbral: float, pendiente_min: float | None, liquida: bool) -> bool:
        """Lluvia >= umbral; pendiente máxima del entorno >= pendiente_min; con `liquida`, isoterma
        0 °C sobre la cota máxima del entorno (llueve en líquido sobre toda la ladera)."""
        if fila["mm_3h"] < umbral or (pendiente_min is not None and fila["slope"] < pendiente_min):
            return False
        return not liquida or (fila["isoterma_m"] is not None and fila["isoterma_m"] >= fila["elev_max"])

    def episodios(dias: set[str]) -> int:
        """Días seguidos cuentan como un solo temporal."""
        orden = sorted(date.fromisoformat(d) for d in dias)
        return sum(1 for i, d in enumerate(orden) if i == 0 or (d - orden[i - 1]).days > 1)

    evento_ids = {f["id"] for f in fires if f["nombre"] == EVENTO["nombre"] and f["comuna"] == EVENTO["comuna"]}
    tabla = []
    for umbral in UMBRALES_MM_3H:
        for pmin in (None, 8.0, 12.0, 16.0, 20.0):
            for liquida in (False, True):
                hits = [x for x in filas if regla(x, umbral, pmin, liquida)]
                por_fire = defaultdict(set)
                for x in hits:
                    por_fire[x["fire"]].add(x["dia"])
                ep = {k: episodios(v) for k, v in por_fire.items()}
                tabla.append({
                    "mm_3h": umbral, "pendiente_max_min_deg": pmin, "isoterma_sobre_cota": liquida,
                    "incendios_con_aviso": len(por_fire), "dias_aviso": sum(len(v) for v in por_fire.values()),
                    "episodios": sum(ep.values()), "max_episodios_un_incendio": max(ep.values(), default=0),
                    "mediana_episodios": sorted(ep.values())[len(ep) // 2] if ep else 0,
                    "dias_distintos": len({x["dia"] for x in hits}),
                    "max_dias_un_incendio": max((len(v) for v in por_fire.values()), default=0),
                    "marca_quebrada_honda": any(EVENTO["fecha"] in por_fire.get(i, set()) for i in evento_ids),
                })

    evento = [f for f in fires if f["nombre"] == EVENTO["nombre"] and f["comuna"] == EVENTO["comuna"]]
    control = None
    if evento:
        f = evento[0]
        dias = por_celda[(round(f["lat"], 1), round(f["lon"], 1))]
        d0 = date.fromisoformat(EVENTO["fecha"])
        control = {"incendio": f, "dias": {(d0 + timedelta(days=k)).isoformat(): dias.get((d0 + timedelta(days=k)).isoformat())
                                           for k in range(-3, 2)}}

    salida = {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ventana": {"desde": inicio.isoformat(), "hasta": fin.isoformat(), "dias": args.dias},
        "fuentes": {"incendios": CONAF_CSV, "lluvia": HIST_URL, "pendiente": ELEV_URL},
        "min_ha": args.min_ha, "incendios": len(fires), "celdas": len(celdas), "incendio_dias": len(filas),
        "relieve": [{k: f[k] for k in ("id", "nombre", "comuna", "ha", "inicio", "slope_max_deg", "elev_max_m")} for f in fires],
        "umbrales": tabla, "control_quebrada_honda": control,
        "top_dias": sorted(filas, key=lambda x: -x["mm_3h"])[:40],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: salida[k] for k in ("ventana", "incendios", "celdas", "incendio_dias")}, ensure_ascii=False))
    for t in tabla:
        print(t)
    print(json.dumps(control, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
