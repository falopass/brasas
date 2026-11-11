"""ICON-E-01: genera los activos de la marca E en `web/icons/` con Pillow.

El motivo (mapa topográfico cenital, curvas finas naranjas y foco satelital) lo
dibujan las mismas funciones que `backend/og.py` usa en las tarjetas dinámicas:
el campo de alturas es determinista, así que dos corridas dan los mismos bytes.

Uso:

    python scripts/generar_iconos.py [--out web/icons] [--preview DIR]

`--preview` escribe una hoja de contacto (16 px nativo y ampliado, maskable con
recorte circular y redondeado, OG completa y reducida) fuera del repo.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import og  # noqa: E402

BG = "#0d0c0b"
BRASA = "#ff4b1f"
CREMA = "#f4efe7"
BRASA_RGB = (255, 75, 31)
SEED = 31052026

# Por tamaño: cuántas curvas, qué tan grande el foco y qué tan gruesa la línea.
# La OG va mucho más rica en relieve que el ícono de app; el de 16 px, 2-3 curvas
# y un foco grande (dirección del encargo, no un downscale del denso).
ICONOS = {
    16: {"curvas": 3, "foco": 0.16, "linea": 1.0, "alpha": 235, "indice": 255},
    32: {"curvas": 4, "foco": 0.19, "linea": 1.5, "alpha": 210, "indice": 250},
    48: {"curvas": 4, "foco": 0.17, "linea": 1.4, "alpha": 200, "indice": 245},
    180: {"curvas": 5, "foco": 0.12, "linea": 1.3, "alpha": 190, "indice": 240},
    192: {"curvas": 6, "foco": 0.12, "linea": 1.3, "alpha": 185, "indice": 235},
    512: {"curvas": 7, "foco": 0.11, "linea": 1.2, "alpha": 175, "indice": 230},
}
FOCO_XY = (0.57, 0.45)  # el foco no va centrado: marca un lugar, como en el mapa


def _icono(size: int, *, maskable: bool = False, rounded: float = 0.0, cuadrado: bool = False) -> Image.Image:
    """El ícono de `size` px dibujado a 4× y bajado con LANCZOS.

    `maskable`: fondo opaco hasta el borde y todo el motivo dentro del círculo
    seguro (radio 40 % del lado). `rounded`: esquinas redondeadas transparentes
    (fracción del lado). `cuadrado`: fondo opaco sin recorte (apple-touch-icon).
    """
    p = ICONOS[size]
    S = size * 4
    # Pillow mezcla el halo RGBA sobre RGB; sobre RGBA reemplazaría el alfa y
    # convertir después a RGB produciría discos sólidos en Apple y maskable.
    img = Image.new("RGB", (S, S), BG)
    draw = ImageDraw.Draw(img, "RGBA")

    def curvas(d, semilla):
        grid = max(30, min(90, S // 24))
        trazos = og._topo_polylines((0, 0, S, S), semilla, p["curvas"], grid=grid)
        if size == 16:
            trazos = sorted(trazos, key=lambda tramo: len(tramo[1]), reverse=True)[:3]
        for li, pts in trazos:
            a = p["indice"] if li % 4 == 0 else p["alpha"]
            d.line(pts, fill=(*BRASA_RGB, a), width=max(1, round(p["linea"] * 4)), joint="curve")

    if maskable:
        # Todo el motivo (curvas y brillo del foco) queda dentro del círculo
        # seguro de radio 40 % del lado; el fondo queda opaco hasta el borde.
        capa = Image.new("RGB", (S, S), BG)
        dc = ImageDraw.Draw(capa, "RGBA")
        curvas(dc, SEED)
        og._satellite_dot(dc, S * 0.5, S * 0.5, S * p["foco"])
        disco = Image.new("L", (S, S), 0)
        ImageDraw.Draw(disco).ellipse((S * 0.1, S * 0.1, S * 0.9, S * 0.9), fill=255)
        img.paste(capa, (0, 0), disco)
    else:
        curvas(draw, SEED)
        og._satellite_dot(draw, S * FOCO_XY[0], S * FOCO_XY[1], S * p["foco"])
    if rounded and not cuadrado and not maskable:
        forma = Image.new("L", (S, S), 0)
        ImageDraw.Draw(forma).rounded_rectangle((0, 0, S - 1, S - 1), radius=S * rounded, fill=255)
        img = img.convert("RGBA")
        img.putalpha(forma)
    return img.resize((size, size), Image.LANCZOS)


def _svg_icono(size: int, curvas: int, foco: float, linea: float, rounded: float) -> str:
    """La misma marca en vector: curvas reales del campo, no figuras genéricas."""
    radio = round(size * rounded, 1)
    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">',
        f'<clipPath id="c"><rect width="{size}" height="{size}" rx="{radio}"/></clipPath>',
        f'<rect width="{size}" height="{size}" rx="{radio}" fill="{BG}"/>',
        '<g clip-path="url(#c)">',
    ]
    trazos = og._topo_polylines((0, 0, size, size), SEED, curvas, grid=40)
    if size == 16:
        trazos = sorted(trazos, key=lambda tramo: len(tramo[1]), reverse=True)[:3]
    for li, pts in trazos:
        op = 0.95 if li % 4 == 0 else 0.55
        # Muestrear todo el recorrido conserva los extremos y los contornos cerrados.
        n = min(len(pts), 32 if size == 16 else 96)
        puntos = [pts[round(i * (len(pts) - 1) / (n - 1))] for i in range(n)]
        d = "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in puntos)
        partes.append(
            f'<path d="{d}" fill="none" stroke="{BRASA}" stroke-width="{linea:.1f}"'
            f' stroke-opacity="{op}" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    cx, cy, r = size * FOCO_XY[0], size * FOCO_XY[1], size * foco
    partes += [
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 2.6:.1f}" fill="{BRASA}" fill-opacity="0.18"/>',
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 1.5:.1f}" fill="{BRASA}" fill-opacity="0.45"/>',
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{BRASA}"/>',
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.42:.1f}" fill="{CREMA}"/>',
        "</g></svg>",
    ]
    return "".join(partes)


def _og(titulo: str, bajada: str) -> Image.Image:
    """Portada OG 1200×630: relieve rico, marca, titular y el pie de siempre."""
    img = Image.new("RGB", (1200, 630), BG)
    draw = ImageDraw.Draw(img, "RGBA")
    og._draw_topografia(draw, (0, 0, 1200, 630), levels=14, width=2, alpha=24, index_alpha=48)
    og._satellite_dot(draw, 995, 315, 16)
    marca = og._font(96, bold=True)
    draw.text((80, 64), "BRASA", font=marca, fill=BRASA)
    draw.text((80 + draw.textlength("BRASA", font=marca) + 22, 94), "Chile", font=og._font(52), fill=og.MUTED)
    draw.rectangle((80, 200, 172, 208), fill=BRASA)
    y = 246
    for line in og._wrap(titulo, og._font(78, bold=True), 780)[:2]:
        draw.text((80, y), line, font=og._font(78, bold=True), fill=CREMA)
        y += 88
    for line in og._wrap(bajada, og._font(36), 780)[:2]:
        draw.text((80, y + 8), line, font=og._font(36), fill=og.MUTED)
        y += 44
    og._pie(draw)
    return img


def _hoja(fichas: dict[str, Image.Image]) -> Image.Image:
    """La hoja de contacto: 16 px nativo y ampliado, maskable recortado y las OG."""
    hoja = Image.new("RGB", (1260, 980), "#171512")
    d = ImageDraw.Draw(hoja, "RGBA")
    gris, x, y = "#8f8a80", 30, 24
    d.text((x, y), "BRASA · marca E — íconos y tarjetas OG", font=og._font(28, bold=True), fill=CREMA)
    y += 56

    def pega(img, w=None, etiqueta=None):
        nonlocal x, y
        v = img if w is None else img.resize((w, int(img.height * w / img.width)), Image.LANCZOS)
        d.rectangle((x - 1, y - 1, x + v.width + 1, y + v.height + 1), outline="#3a352f")
        hoja.paste(v, (x, y), v if v.mode == "RGBA" else None)
        if etiqueta:
            d.text((x, y + v.height + 6), etiqueta, font=og._font(18), fill=gris)
        x += v.width + 32

    pega(fichas["_f16"], etiqueta="16 nativo")
    pega(fichas["_f16"].resize((128, 128), Image.NEAREST), etiqueta="16 ampliado ×8 (nearest)")
    pega(fichas["_f32"], etiqueta="32 (marco ICO)")
    pega(fichas["_f48"], etiqueta="48 (marco ICO)")
    pega(fichas["apple-touch-icon.png"], 96, "180 apple")
    pega(fichas["icon-192.png"], 96, "192")
    pega(fichas["icon-512.png"], 128, "512")

    mask = fichas["icon-maskable-512.png"].convert("RGBA")
    for nombre, radio in (("círculo", None), ("redondeado", 118)):
        forma = Image.new("L", (512, 512), 0)
        df = ImageDraw.Draw(forma)
        if radio is None:
            df.ellipse((0, 0, 512, 512), fill=255)
        else:
            df.rounded_rectangle((0, 0, 512, 512), radius=radio, fill=255)
        sobre = Image.new("RGBA", (512, 512), (23, 21, 18, 255))
        sobre.paste(mask, (0, 0), forma)
        pega(sobre, 128, f"maskable {nombre}")

    x, y = 30, 300
    pega(fichas["og.png"], 590, "og.png 1200×630")
    pega(fichas["og-focos.png"], 590, "og-focos.png")

    x, y = 30, 660
    pega(fichas["og.png"], 300, "og reducida (vista chat)")
    for clave, etiqueta in (("_comuna", "/og/comuna/5801.png (renderer)"), ("_incidente", "/og/incident/… (renderer)")):
        if fichas.get(clave) is not None:
            pega(fichas[clave], 445, etiqueta)
    return hoja


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera los activos de marca E en web/icons/.")
    ap.add_argument("--out", default="web/icons", help="carpeta de salida (por defecto web/icons)")
    ap.add_argument("--preview", help="carpeta externa al repo para la hoja de contacto")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    fichas: dict[str, Image.Image] = {}

    # Íconos raster por tamaño (cada uno con su propia densidad, no un downscale).
    i16, i32, i48 = _icono(16, rounded=0.2), _icono(32, rounded=0.2), _icono(48, rounded=0.2)
    i48.save(out / "favicon.ico", "ICO", sizes=[(16, 16), (32, 32), (48, 48)],
             append_images=[i16, i32])
    fichas["_f16"], fichas["_f32"], fichas["_f48"] = i16, i32, i48
    apple = _icono(180, cuadrado=True)
    apple.save(out / "apple-touch-icon.png", "PNG", optimize=True)
    fichas["apple-touch-icon.png"] = apple
    for size, nombre in ((192, "icon-192.png"), (512, "icon-512.png")):
        img = _icono(size, rounded=0.18)
        img.save(out / nombre, "PNG", optimize=True)
        fichas[nombre] = img
    maskable = _icono(512, maskable=True)
    maskable.save(out / "icon-maskable-512.png", "PNG", optimize=True)
    fichas["icon-maskable-512.png"] = maskable

    # Íconos vectoriales: el de compatibilidad y el favicon simplificado.
    (out / "icon.svg").write_text(_svg_icono(64, curvas=5, foco=0.11, linea=1.7, rounded=0.22), encoding="utf-8")
    (out / "favicon.svg").write_text(_svg_icono(16, curvas=3, foco=0.16, linea=0.9, rounded=0.19), encoding="utf-8")

    # Tarjetas OG estáticas: portada y página de focos, con copia real del sitio.
    fichas["og.png"] = _og("¿Hay fuego cerca de tu casa?",
                           "Focos de calor satelitales, riesgo por comuna y qué hacer.")
    fichas["og.png"].save(out / "og.png", "PNG", optimize=True)
    fichas["og-focos.png"] = _og("Focos de calor e incendios activos",
                                "Detecciones satelitales GOES-19 y VIIRS, por comuna.")
    fichas["og-focos.png"].save(out / "og-focos.png", "PNG", optimize=True)

    # Muestras del renderer dinámico para la hoja (Quilpué, 5801, existe de verdad).
    t = og.geo.territory()
    comuna = t.by_code.get(5801)
    if comuna is not None:
        fichas["_comuna"] = Image.open(io.BytesIO(og._render_comuna(comuna)))
    fichas["_incidente"] = Image.open(io.BytesIO(og._render(
        lat=-33.45, lon=-70.66, en_chile=True, headline="Ficha de incidente", conaf=None,
        where="Ejemplo de composición",
        detail="Vista de diseño: sin detección ni aviso real.")))

    if args.preview:
        prev = Path(args.preview)
        prev.mkdir(parents=True, exist_ok=True)
        _hoja(fichas).save(prev / "hoja-contacto.png", "PNG", optimize=True)
        for nombre, img in fichas.items():
            if not nombre.startswith("_") or nombre.startswith("_f"):
                continue
            img.convert("RGB").save(prev / f"{nombre[1:]}.png", "PNG", optimize=True)

    for archivo in sorted(out.iterdir()):
        print(archivo.name, archivo.stat().st_size)


if __name__ == "__main__":
    main()
