"""FIX-33: una foto que declara cientos de megapíxeles se rechaza antes de decodificar."""
import io
import struct
import zlib

import pytest
from PIL import Image

from backend.reports import MAX_SIDE, PhotoError, sanitize_photo


def png_with_dimensions(width: int, height: int) -> bytes:
    """PNG mínimo: firma + IHDR + IEND. Cabecera válida sin datos de píxeles (IDAT)."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    data = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr)) + chunk + struct.pack(">I", zlib.crc32(chunk))
        + struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    )
    return data


def test_rechaza_foto_gigante_sin_decodificar(tmp_path):
    # 20.000 × 20.000 = 400 MP: el archivo pesa bytes pero decodificarlo pediría ~1,2 GB.
    with pytest.raises(PhotoError, match="máximo 40 megapíxeles"):
        sanitize_photo(png_with_dimensions(20_000, 20_000), tmp_path / "foto.jpg")
    assert not (tmp_path / "foto.jpg").exists()


def test_foto_normal_se_guarda_sin_exif(tmp_path):
    img = Image.new("RGB", (2000, 1500), (30, 120, 60))
    exif = Image.Exif()
    exif[0x010F] = "CamaraDePrueba"
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())

    dest = tmp_path / "foto.jpg"
    sanitize_photo(buf.getvalue(), dest)

    with Image.open(dest) as saved:
        assert max(saved.size) <= MAX_SIDE
        assert not saved.getexif()


def test_archivo_que_no_es_imagen(tmp_path):
    with pytest.raises(PhotoError, match="El archivo no es una imagen válida."):
        sanitize_photo(b"not an image", tmp_path / "foto.jpg")
