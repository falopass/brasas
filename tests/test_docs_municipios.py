"""La guía para municipios no puede quedarse atrás de la licencia del repo.

SEC-14 se resolvió en el PR #143: `LICENSE` es AGPL-3.0 para el código y
`README.md` declara los datos propios bajo CC BY 4.0. Esta guarda fija que
`docs/MUNICIPIOS.md` y `docs/ROADMAP.md` no vuelvan a decir que la licencia
está pendiente ni que los datos propios no se pueden redistribuir.
"""

from __future__ import annotations

from backend import settings

ROOT = settings.ROOT
LICENSE = ROOT / "LICENSE"
README = ROOT / "README.md"
MUNICIPIOS = ROOT / "docs" / "MUNICIPIOS.md"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
BACKLOG = ROOT / "docs" / "BACKLOG_MAESTRO.md"

# Una línea con «licencia» más una de estas palabras declara la licencia como no decidida.
PENDING_WORDS = ("pendiente", "por decidir", "a decidir", "revisión", "elegir", "sin decidir")
STALE_PHRASES = ("pendiente de decisión", "no se autoriza")


def _stale_lines(doc) -> list[str]:
    problems = []
    for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1):
        low = line.lower()
        if any(phrase in low for phrase in STALE_PHRASES):
            problems.append(f"{doc.name}:{number}: {line.strip()}")
        elif "licencia" in low and any(word in low for word in PENDING_WORDS):
            problems.append(f"{doc.name}:{number}: {line.strip()}")
    return problems


def test_license_es_agpl3() -> None:
    text = LICENSE.read_text(encoding="utf-8")
    assert "AFFERO GENERAL PUBLIC LICENSE" in text and "Version 3" in text, "LICENSE debe seguir siendo GNU AGPL-3.0 (SEC-14)."


def test_readme_declara_las_dos_licencias() -> None:
    text = README.read_text(encoding="utf-8")
    assert "AGPL-3.0" in text and "CC BY 4.0" in text, "README.md debe declarar AGPL-3.0 para el código y CC BY 4.0 para los datos propios."


def test_backlog_registra_sec14_como_decidido() -> None:
    lines = [l for l in BACKLOG.read_text(encoding="utf-8").splitlines() if "SEC-14" in l]
    assert lines and any("AGPL-3.0" in l for l in lines), "BACKLOG_MAESTRO.md debe registrar SEC-14 como decidido (AGPL-3.0 + CC BY 4.0)."


def test_guia_municipios_menciona_cc_by_4() -> None:
    assert "CC BY 4.0" in MUNICIPIOS.read_text(encoding="utf-8"), (
        "docs/MUNICIPIOS.md debe indicar que los datos propios se publican bajo CC BY 4.0."
    )


def test_guia_y_roadmap_no_declaran_licencia_pendiente() -> None:
    problems = _stale_lines(MUNICIPIOS) + _stale_lines(ROADMAP)
    assert not problems, (
        "La licencia ya está decidida (SEC-14): AGPL-3.0 código, CC BY 4.0 datos propios. "
        "Estas líneas la siguen declarando pendiente o prohíben redistribuir los datos:\n" + "\n".join(problems)
    )
