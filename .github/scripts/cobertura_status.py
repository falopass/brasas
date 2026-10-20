"""OPS-19: publica la cobertura de FWI, DMC y lluvia que trae /api/status.

Lee el JSON de /api/status por stdin y escribe anotaciones de GitHub. No falla el workflow:
el diagnóstico informa; la decisión de corregir o volver atrás es humana.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    data = json.load(sys.stdin)
    coverage = data.get("coverage") or {}
    open_meteo = data.get("open_meteo") or {}
    errors = (data.get("errors") or {}).get("cycle_errors") or []
    print("cobertura:", json.dumps(coverage, ensure_ascii=False))
    print("open_meteo:", json.dumps(open_meteo, ensure_ascii=False))
    print("errores del ciclo:", ", ".join(errors) or "ninguno")
    print("::notice title=cobertura::" + json.dumps(coverage, ensure_ascii=False))
    print("::notice title=open_meteo::" + json.dumps(open_meteo, ensure_ascii=False))
    if coverage.get("fwi_comunas") is not None and coverage.get("fwi_comunas") != coverage.get("comunas"):
        print("::warning title=FWI incompleto::{} de {} comunas".format(coverage.get("fwi_comunas"), coverage.get("comunas")))
    if open_meteo.get("rate_limited"):
        print("::warning title=Open-Meteo 429::{} respuestas".format(open_meteo["rate_limited"]))
    if errors:
        print("::warning title=Errores del ciclo::" + ", ".join(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
