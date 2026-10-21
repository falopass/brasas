"""OPS-19: publica la cobertura de FWI, DMC y lluvia que trae /api/status.

Lee el JSON de /api/status por stdin y escribe anotaciones de GitHub. No falla el workflow:
el diagnóstico informa; la decisión de corregir o volver atrás es humana.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    data = json.load(sys.stdin)
    coverage = data.get("coverage")
    sin_cobertura = None
    if not isinstance(coverage, dict):
        sin_cobertura = "la respuesta no trae la clave coverage" if coverage is None else "coverage no es un objeto"
        coverage = {}
    open_meteo = data.get("open_meteo") or {}
    errors = (data.get("errors") or {}).get("cycle_errors") or []
    last_cycle = data.get("last_cycle")
    if not isinstance(last_cycle, dict):
        last_cycle = {}
    print("cobertura:", json.dumps(coverage, ensure_ascii=False))
    print("open_meteo:", json.dumps(open_meteo, ensure_ascii=False))
    print("errores del ciclo:", ", ".join(errors) or "ninguno")
    print("::notice title=cobertura::" + json.dumps(coverage, ensure_ascii=False))
    print("::notice title=open_meteo::" + json.dumps(open_meteo, ensure_ascii=False))
    if sin_cobertura:
        print(f"::warning title=Sin cobertura::{sin_cobertura}; no se revisó FWI, DMC ni lluvia")
    if coverage.get("fwi_comunas") is not None and coverage.get("fwi_comunas") != coverage.get("comunas"):
        print("::warning title=FWI incompleto::{} de {} comunas".format(coverage.get("fwi_comunas"), coverage.get("comunas")))
    if open_meteo.get("rate_limited"):
        print("::warning title=Open-Meteo 429::{} respuestas".format(open_meteo["rate_limited"]))
    if errors:
        print("::warning title=Errores del ciclo::" + ", ".join(errors))
    incompleto = [nombre for nombre, clave in (("FWI", "fwi_error"), ("lluvia", "rain_error")) if last_cycle.get(clave)]
    if incompleto:
        print("::warning title=Ciclo incompleto::" + ", ".join(incompleto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
