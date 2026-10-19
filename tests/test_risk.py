"""Nivel de condiciones: 30-30-30 solo y combinado con el FWI.

La regla que se prueba aquí es la que se explica en la interfaz: manda el índice más alto, y si
los dos coinciden en «alto» o más se sube un paso. Nunca se pasa de «extremo».

También se cubren las piezas del índice 30-30-30 que deciden el nivel: los umbrales hora a hora
(`hour_flags`), el puntaje continuo (`hour_score`), la clasificación del día (`classify_day`),
el recorte de días con pocas horas válidas (`evaluate`) y la conversión UTC → día de Chile
(`local_day`).
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


# --- hour_flags: los umbrales son estrictos (>30 °C, <30 %, >30 km/h) ---


def test_hour_flags_at_exact_thresholds_do_not_trigger() -> None:
    assert risk.hour_flags(30.0, 30.0, 30.0) == (False, False, False)


def test_hour_flags_just_past_thresholds_trigger() -> None:
    assert risk.hour_flags(30.1, 29.9, 30.1) == (True, True, True)


def test_hour_flags_none_never_triggers() -> None:
    assert risk.hour_flags(None, None, None) == (False, False, False)
    assert risk.hour_flags(35.0, None, 40.0) == (True, False, True)


# --- hour_score: continuo 0-100, 0 si falta una variable ---


def test_hour_score_is_zero_when_a_variable_is_missing() -> None:
    assert risk.hour_score(None, 20.0, 40.0) == 0.0
    assert risk.hour_score(35.0, None, 40.0) == 0.0
    assert risk.hour_score(35.0, 20.0, None) == 0.0


def test_hour_score_grows_toward_the_thresholds() -> None:
    mild = risk.hour_score(20.0, 50.0, 10.0)
    close = risk.hour_score(29.0, 31.0, 29.0)
    past = risk.hour_score(33.0, 25.0, 35.0)
    assert mild < close < past


def test_hour_score_stays_within_0_and_100() -> None:
    assert risk.hour_score(-10.0, 100.0, 0.0) == 0.0
    extreme = risk.hour_score(45.0, 5.0, 120.0)
    assert 0.0 <= extreme <= 100.0


def test_hour_score_is_low_on_a_mild_day() -> None:
    assert risk.hour_score(18.0, 60.0, 8.0) < 30.0


# --- classify_day: la regla que fija el nivel del día ---


def test_classify_day_one_hour_3of3_is_extremo() -> None:
    assert risk.classify_day(1, 1, 34.0, 18.0, 95.0) == "extremo"


def test_classify_day_three_hours_2of3_is_alto() -> None:
    assert risk.classify_day(0, 3, 33.0, 35.0, 60.0) == "alto"


def test_classify_day_one_hour_2of3_is_moderado() -> None:
    assert risk.classify_day(0, 1, 32.0, 45.0, 60.0) == "moderado"


def test_classify_day_shortcut_27_and_40_is_moderado() -> None:
    assert risk.classify_day(0, 0, 27.0, 40.0, 20.0) == "moderado"


def test_classify_day_nothing_is_bajo() -> None:
    assert risk.classify_day(0, 0, 22.0, 55.0, 30.0) == "bajo"


def test_classify_day_extremo_wins_over_anything_else() -> None:
    assert risk.classify_day(2, 10, 40.0, 10.0, 100.0) == "extremo"


# --- evaluate: días con pocas horas válidas no se clasifican ---


def _hourly(n: int, t: float = 33.0, rh: float = 20.0, wind: float = 35.0) -> dict[str, list]:
    """Un día de Chile con `n` horas (12-23 UTC: mediodía a 20 h en Chile, mismo día local)."""
    return {
        "time": [f"2027-01-15T{h:02d}:00" for h in range(12, 12 + n)],
        "temperature_2m": [t] * n,
        "relative_humidity_2m": [rh] * n,
        "wind_speed_10m": [wind] * n,
        "wind_gusts_10m": [wind + 10] * n,
        "wind_direction_10m": [240] * n,
    }


def test_evaluate_day_with_too_few_valid_hours_is_dropped() -> None:
    result = risk.evaluate(_hourly(risk.MIN_VALID_HOURS - 1))
    assert result["days"] == []


def test_evaluate_incomplete_day_is_not_disguised_as_bajo() -> None:
    calm = _hourly(3, t=15.0, rh=80.0, wind=5.0)
    assert all(day["level"] != "bajo" for day in risk.evaluate(calm)["days"])


def test_evaluate_full_day_appears_with_level_score_and_extremes() -> None:
    result = risk.evaluate(_hourly(12))
    (day,) = result["days"]
    assert day["date"] == "2027-01-15"
    assert day["level"] == "extremo"
    assert day["score"] == int(round(day["max_score"]))
    assert day["tmax"] == 33.0
    assert day["rhmin"] == 20.0


def test_evaluate_hours_keep_order_and_z_suffix() -> None:
    result = risk.evaluate(_hourly(8))
    stamps = [hour["time"] for hour in result["hours"]]
    assert stamps == sorted(stamps)
    assert all(stamp.endswith("Z") for stamp in stamps)


# --- local_day: la fecha es la de Chile, no la UTC ---


def test_local_day_early_utc_falls_on_previous_chilean_day() -> None:
    assert risk.local_day("2027-01-15T02:00") == "2027-01-14"
    assert risk.local_day("2027-01-15T02:00Z") == "2027-01-14"


def test_local_day_afternoon_utc_stays_on_same_chilean_day() -> None:
    assert risk.local_day("2027-01-15T20:00") == "2027-01-15"
