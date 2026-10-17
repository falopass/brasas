"""Reportes ciudadanos: procesamiento seguro de fotos y reglas de publicación.

Un reporte nunca se publica sin revisión humana. La foto se re-codifica (sin EXIF ni GPS
del archivo original) y se reduce a un tamaño razonable.
"""
from __future__ import annotations

import io
from pathlib import Path

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SIDE = 1600
KINDS = {"humo": "Humo visible", "llamas": "Llamas visibles", "quema": "Quema o fogata", "otro": "Otro"}
STATUSES = {"no_verificado", "verificado", "descartado"}


class PhotoError(ValueError):
    pass


def sanitize_photo(content: bytes, dest: Path) -> None:
    """Valida la imagen, elimina metadatos y la guarda como JPEG."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(content) > MAX_UPLOAD_BYTES:
        raise PhotoError("La foto supera 8 MB.")
    try:
        with Image.open(io.BytesIO(content)) as img:
            img = ImageOps.exif_transpose(img)  # respeta la orientación antes de descartar EXIF
            img = img.convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            clean = Image.new("RGB", img.size)
            clean.paste(img)
    except (UnidentifiedImageError, OSError) as exc:
        raise PhotoError("El archivo no es una imagen válida.") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean.save(dest, "JPEG", quality=82, optimize=True)
