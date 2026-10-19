"""Reportes ciudadanos: procesamiento seguro de fotos, reglas de publicación y caducidad.

Un reporte nunca se publica sin revisión humana. La foto se re-codifica (sin EXIF ni GPS
del archivo original) y se reduce a un tamaño razonable.

Cada aviso caduca en el plazo que el hecho sigue vigente: el humo se disipa en horas; las llamas
de un incendio activo o una quema siguen siendo útiles mucho más tiempo. Si nadie lo revisa en su
ventana, dejarlo en la cola es peor que nada (parece trabajo pendiente y ya no ayuda a decidir).
Caduca como «descartado» con su motivo, no se borra: queda el registro de que llegó y no se revisó.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_SIDE = 1600
KINDS = {"humo": "Humo visible", "llamas": "Llamas visibles", "quema": "Quema o fogata", "otro": "Otro"}
STATUSES = {"no_verificado", "verificado", "descartado"}
STATUS_LABELS = {"no_verificado": "En revisión", "verificado": "Verificado", "descartado": "Descartado"}
EXPIRE_HOURS = 6        # lo que un reporte de humo puede esperar sin perder sentido
# Ventana sin revisar por tipo: humo caduca rápido; llamas y «otro» siguen vigentes al día
# siguiente; una quema puede durar días. Un tipo nuevo sin ventana no caduca (queda para el humano).
EXPIRE_HOURS_BY_KIND = {"humo": EXPIRE_HOURS, "llamas": 24, "quema": 72, "otro": 24}
DUPLICATE_HOURS = 3    # dos avisos del mismo punto en este rango son el mismo hecho
DUPLICATE_KM = 1.5
EXPIRED_NOTE = "Caducó sin revisar: el aviso esperó más tiempo del que el hecho sigue vigente."


def expire_cutoff(now: datetime | None = None, hours: int = EXPIRE_HOURS) -> str:
    """Marca ISO a partir de la cual un reporte sin revisar se considera caducado."""
    moment = (now or datetime.now(timezone.utc)) - timedelta(hours=hours)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def expired(created_at: str, now: datetime | None = None, hours: int = EXPIRE_HOURS) -> bool:
    """True si un reporte esperó demasiado. Sin fecha legible, no se da por caducado."""
    try:
        moment = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    reference = now or datetime.now(timezone.utc)
    return (reference - moment).total_seconds() >= hours * 3600


class PhotoError(ValueError):
    pass


def sanitize_photo(content: bytes, dest: Path) -> None:
    """Valida la imagen, elimina metadatos y la guarda como JPEG."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(content) > MAX_UPLOAD_BYTES:
        raise PhotoError("La foto supera 8 MB.")
    try:
        with Image.open(io.BytesIO(content)) as img:
            # Rechaza por dimensiones antes de decodificar: un JPEG chico puede declarar
            # cientos de megapíxeles y reservar gigas de RAM al convertirse a RGB.
            if img.width * img.height > MAX_PIXELS:
                raise PhotoError("La foto es demasiado grande (máximo 40 megapíxeles).")
            img = ImageOps.exif_transpose(img)  # respeta la orientación antes de descartar EXIF
            img = img.convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            clean = Image.new("RGB", img.size)
            clean.paste(img)
    except Image.DecompressionBombError as exc:
        raise PhotoError("La foto es demasiado grande (máximo 40 megapíxeles).") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise PhotoError("El archivo no es una imagen válida.") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean.save(dest, "JPEG", quality=82, optimize=True)
