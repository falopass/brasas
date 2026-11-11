"""ICON-E-01: los activos de marca E existen, tienen sus dimensiones y respetan
la paleta exacta y la zona segura del maskable. Los binarios se generan con
`scripts/generar_iconos.py` (Pillow), no a mano."""

import io
import math
import re
import struct
from statistics import median
from xml.etree import ElementTree

import pytest
from PIL import Image

from backend.settings import ROOT

ICONS = ROOT / "web" / "icons"
BG = (13, 12, 11)
BRASA = (255, 75, 31)
PALETA_HEX = {"#0d0c0b", "#ff4b1f", "#f4efe7"}


def _marcos_ico() -> dict[tuple[int, int], Image.Image]:
    """Los marcos del favicon leídos por estructura ICONDIR: cada entrada es un PNG."""
    data = (ICONS / "favicon.ico").read_bytes()
    reserved, tipo, n = struct.unpack_from("<HHH", data, 0)
    assert (reserved, tipo) == (0, 1), "favicon.ico no es un ICONDIR válido"
    marcos = {}
    for i in range(n):
        w, h, _colores, _res, _planos, _bits, size, off = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        marcos[(w or 256, h or 256)] = Image.open(io.BytesIO(data[off:off + size]))
    return marcos


def test_favicon_ico_tiene_marcos_16_32_48():
    """El .ico trae los tres tamaños, cada uno dibujado para su escala."""
    marcos = _marcos_ico()
    assert set(marcos) == {(16, 16), (32, 32), (48, 48)}
    for size, img in marcos.items():
        assert img.size == size


def test_iconos_png_tienen_sus_dimensiones():
    esperados = {
        "apple-touch-icon.png": (180, 180),
        "icon-192.png": (192, 192),
        "icon-512.png": (512, 512),
        "icon-maskable-512.png": (512, 512),
    }
    for nombre, size in esperados.items():
        assert Image.open(ICONS / nombre).size == size, nombre


def test_tarjetas_og_son_1200x630():
    for nombre in ("og.png", "og-focos.png"):
        assert Image.open(ICONS / nombre).size == (1200, 630), nombre


def _hexes(svg: str) -> set[str]:
    return {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", svg)}


@pytest.mark.parametrize("nombre", ["icon.svg", "favicon.svg"])
def test_svg_usa_la_paleta_exacta_y_el_foco(nombre):
    """Los vectoriales solo usan los tres colores de la marca y traen el foco crema."""
    svg = (ICONS / nombre).read_text(encoding="utf-8")
    assert _hexes(svg) <= PALETA_HEX, f"{nombre} sale de la paleta E: {_hexes(svg) - PALETA_HEX}"
    assert "#ff4b1f" in _hexes(svg) and "#f4efe7" in _hexes(svg)
    ElementTree.fromstring(svg)  # XML válido
    assert "circle" in svg, "el foco satelital debe seguir presente"


def test_icono_16_es_variante_diseñada_no_downscale():
    """El marco de 16 px no es el 512 reducido: con tan pocos píxeles va con menos
    curvas y un foco grande (dirección E), así que no puede ser el mismo render."""
    f16 = _marcos_ico()[(16, 16)]
    grande = Image.open(ICONS / "icon-512.png").convert("RGBA").resize((16, 16), Image.LANCZOS)
    assert list(f16.convert("RGBA").getdata()) != list(grande.getdata())


def test_icono_16_se_lee_fondo_y_foco():
    """A 16 px el ícono conserva fondo oscuro y un foco naranja legible."""
    frame = _marcos_ico()[(16, 16)].convert("RGBA")
    px = Image.alpha_composite(Image.new("RGBA", frame.size, (*BG, 255)), frame).convert("RGB")
    # LANCZOS puede dejar un nivel de alfa en la esquina redondeada al bajar a 16 px.
    assert max(abs(canal - fondo) for canal, fondo in zip(px.getpixel((0, 0)), BG)) <= 1
    brasa = sum(1 for p in px.getdata() if p[0] > 200 and p[1] < 120 and p[2] < 80)
    assert brasa >= 6, "el foco de 16 px quedó demasiado pequeño"


def test_maskable_motivo_dentro_del_circulo_seguro():
    """Fondo opaco hasta el borde y todo el motivo dentro del círculo central de
    radio 40 % del lado: fuera solo queda el fondo."""
    img = Image.open(ICONS / "icon-maskable-512.png").convert("RGB")
    lado = img.size[0]
    centro = lado / 2
    for ang in range(0, 360, 12):
        r = lado * 0.43
        x, y = centro + r * math.cos(math.radians(ang)), centro + r * math.sin(math.radians(ang))
        assert img.getpixel((int(x), int(y))) == BG, f"motivo fuera del círculo seguro a {ang}°"
    for punto in ((2, 2), (lado - 3, 2), (2, lado - 3), (lado - 3, lado - 3)):
        assert img.getpixel(punto) == BG, f"esquina {punto} sin fondo opaco"


@pytest.mark.parametrize("nombre,centro,foco", [
    ("apple-touch-icon.png", (0.57, 0.45), 0.12),
    ("icon-maskable-512.png", (0.5, 0.5), 0.11),
])
def test_halo_opaco_conserva_la_mezcla_con_el_fondo(nombre, centro, foco):
    """Aplanar alfa no puede convertir el halo tenue en un disco naranja sólido."""
    img = Image.open(ICONS / nombre).convert("RGB")
    lado = img.width
    radio = lado * foco * 1.9
    rojos = [
        img.getpixel((round(lado * centro[0] + radio * math.cos(a)),
                      round(lado * centro[1] + radio * math.sin(a))))[0]
        for a in (math.radians(grados) for grados in range(0, 360, 20))
    ]
    assert BG[0] < median(rojos) < 150, nombre
