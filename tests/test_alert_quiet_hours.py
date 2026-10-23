"""ALR-19: los avisos que no son urgentes esperan a las 07:00 de Chile; el urgente sale siempre."""
from datetime import datetime, timezone

from backend.alerts import age_phrase, aplazable, en_silencio, refresh_age_line, silencio_nota, vencida

# 02:00 y 12:00 en America/Santiago (UTC-3 en verano) = 05:00Z / 15:00Z
NOCHE = datetime(2026, 10, 22, 5, 0, tzinfo=timezone.utc)
DIA = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)
LIMITE_7AM = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)   # 07:00 Chile
LIMITE_23H = datetime(2026, 10, 23, 2, 0, tzinfo=timezone.utc)    # 23:00 Chile


def test_aviso_en_la_noche_se_aplaza():
    assert en_silencio(NOCHE) is True
    assert aplazable({"level": "aviso"}) is True


def test_urgente_nunca_se_retrasa():
    assert aplazable({"level": "urgente"}) is False
    assert aplazable({}) is False


def test_los_bordes_son_07_y_23():
    assert en_silencio(LIMITE_7AM) is False   # 07:00 ya entrega
    assert en_silencio(DIA) is False
    assert en_silencio(LIMITE_23H) is True    # 23:00 comienza el silencio


def test_nota_dice_por_que_llego_tarde():
    nota = silencio_nota("2026-10-22T04:30:00Z")  # 01:30 en Chile
    assert "no quisimos despertarte" in nota
    assert "01:30" in nota


def test_age_phrase():
    now = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    assert age_phrase("2026-10-22T11:58:00Z", now) == "hace menos de 5 minutos"
    assert age_phrase("2026-10-22T11:48:00Z", now) == "hace 12 minutos"
    assert age_phrase("2026-10-22T09:00:00Z", now) == "hace 3 horas"


def test_frase_de_edad_se_recompone_al_entregar():
    body = "Detección satelital al este. Detectado hace menos de 5 minutos. Fuente: VIIRS."
    nueva = refresh_age_line(body, "2026-10-22T02:00:00Z", datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc))
    assert "hace 8 horas" in nueva
    assert "menos de 5 minutos" not in nueva


def test_aplazada_con_expires_vencido_no_sale():
    assert vencida({"expires": "2026-10-22T09:00:00Z"}, datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)) is True
    assert vencida({"expires": "2026-10-23T09:00:00Z"}, datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)) is False
    assert vencida({}, datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)) is False
