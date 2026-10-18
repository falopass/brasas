"""Nivel de condiciones: 30-30-30 solo y combinado con el FWI.

La regla que se prueba aquí es la que se explica en la interfaz: manda el índice más alto, y si
los dos coinciden en «alto» o más se sube un paso. Nunca se pasa de «extremo».
"""
from __future__ import annotations

from backend import risk


def test_combine_keeps_the_highest_of_the_two() -> None:
    assert risk.combine("bajo", "moderado")[0] == "moderado"
    assert risk.combine("alto", "bajo")[0] == "alto"


def test_combine_escalates_one_step_when_both_are_high() -> None:
    level, reasons = risk.combine("alto", "alto")
    assert level == "extremo"
    assert any("coinciden" in reason for reason in reasons)


def test_combine_does_not_escalate_with_only_one_index_high() -> None:
    assert risk.combine("alto", "moderado")[0] == "alto"
    assert risk.combine("bajo", "alto")[0] == "alto"


def test_combine_never_goes_past_extremo() -> None:
    assert risk.combine("extremo", "extremo")[0] == "extremo"


def test_combine_without_fwi_keeps_the_3030_level_and_says_so() -> None:
    level, reasons = risk.combine("moderado", None)
    assert level == "moderado"
    assert any("sin dato" in reason for reason in reasons)


def test_combine_explains_both_indices() -> None:
    _, reasons = risk.combine("moderado", "alto")
    assert reasons[0].startswith("30-30-30:")
    assert reasons[1].startswith("FWI:")
