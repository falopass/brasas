"""AUTO-43: la guarda `--check-informe` de scripts/local/chequeo_enlaces.py.

Valida el informe ya escrito (docs/ENLACES.md) sin tocar la red: falla si hay una
fila `roto`, si la fecha declarada tiene más de 30 días o si el informe no la
declara. Las pruebas usan informes sintéticos en tmp_path.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import chequeo_enlaces  # noqa: E402


def escribir_informe(tmp_path: Path, fecha: str | None, filas: list[str]) -> Path:
    """Informe sintético con la misma forma que docs/ENLACES.md."""
    lineas = ["# Estado de los enlaces externos", ""]
    if fecha is not None:
        lineas.append(f"Generado el {fecha} por `scripts/local/chequeo_enlaces.py`.")
    lineas += [
        "",
        "**Resumen:** 1 enlaces · 1 ok",
        "",
        "| URL | Estado | Código | Apariciones | Reemplazo propuesto |",
        "|---|---|---|---|---|",
        *filas,
    ]
    ruta = tmp_path / "ENLACES.md"
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


FILA_OK = "| https://senapred.cl/ | ok | 200 | `web/index.html:1` | — |"
FILA_ROTA = "| https://conaf.cl/muerta | roto | 404 | `docs/x.md:1` | sin reemplazo conocido |"


def test_informe_limpio_y_fresco_da_0(tmp_path, capsys):
    ruta = escribir_informe(tmp_path, date.today().isoformat(), [FILA_OK])
    assert chequeo_enlaces.main(["--check-informe", "--salida", str(ruta)]) == 0
    assert "sin enlaces rotos" in capsys.readouterr().out


def test_informe_con_fila_rota_da_1_y_nombra_la_url(tmp_path, capsys):
    ruta = escribir_informe(tmp_path, date.today().isoformat(), [FILA_OK, FILA_ROTA])
    assert chequeo_enlaces.main(["--check-informe", "--salida", str(ruta)]) == 1
    salida = capsys.readouterr().out
    assert "enlace roto" in salida
    assert "https://conaf.cl/muerta" in salida


def test_informe_de_hace_45_dias_da_1_y_dice_su_edad(tmp_path, capsys):
    fecha = (date.today() - timedelta(days=45)).isoformat()
    ruta = escribir_informe(tmp_path, fecha, [FILA_OK])
    assert chequeo_enlaces.main(["--check-informe", "--salida", str(ruta)]) == 1
    salida = capsys.readouterr().out
    assert "45" in salida
    assert "30" in salida  # menciona el máximo tolerado


def test_informe_sin_fecha_da_1(tmp_path, capsys):
    ruta = escribir_informe(tmp_path, None, [FILA_OK])
    assert chequeo_enlaces.main(["--check-informe", "--salida", str(ruta)]) == 1
    assert "fecha" in capsys.readouterr().out


def test_informe_inexistente_da_1(tmp_path, capsys):
    ruta = tmp_path / "no-existe" / "ENLACES.md"
    assert chequeo_enlaces.main(["--check-informe", "--salida", str(ruta)]) == 1
    assert "no se pudo leer" in capsys.readouterr().out


def test_revisar_informe_no_cuenta_otros_estados_como_rotos(tmp_path):
    filas = [
        "| https://a.cl/ | bloqueado | 403 | `docs/x.md:1` | — |",
        "| https://b.cl/ | error | — | `docs/x.md:2` | — |",
    ]
    ruta = escribir_informe(tmp_path, date.today().isoformat(), filas)
    codigo, problemas = chequeo_enlaces.revisar_informe(ruta)
    assert codigo == 0
    assert problemas == []
