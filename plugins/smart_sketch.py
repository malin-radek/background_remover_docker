"""
Plugin: Smart Sketch v2
Osobne style szkicowania dla postaci (FG) i tła (BG).
10 styli szkicu + opcja wymiany tła na 8 predefiniowanych typów.
"""

import io
import os
import math
import threading
import random
from PIL import Image, ImageFilter, ImageOps, ImageEnhance, ImageChops, ImageDraw

try:
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_sessions = {}
_lock = threading.Lock()


def is_available() -> bool:
    return _AVAILABLE


def _get_session(model_name: str):
    with _lock:
        if model_name not in _sessions:
            _sessions[model_name] = new_session(model_name)
        return _sessions[model_name]


# ── 10 Sketch Styles ─────────────────────────────────────────────────────────
SKETCH_STYLES = {
    "pencil":       {"label": "✏️ Ołówek",         "desc": "Klasyczny szkic ołówkiem"},
    "manga":        {"label": "🖌️ Manga",           "desc": "Line art w stylu manga"},
    "comic_bw":     {"label": "📰 Komiks B&W",      "desc": "Czarno-biały komiks z halftone"},
    "comic_color":  {"label": "🎨 Komiks Kolor",    "desc": "Kolorowy komiks z grubym konturem"},
    "charcoal":     {"label": "🖤 Węgiel",          "desc": "Rysunek węglem na papierze"},
    "ink":          {"label": "🪶 Tusz",            "desc": "Rysunek piórem / tuszem"},
    "watercolor":   {"label": "💧 Akwarela",        "desc": "Efekt akwarelowy z rozmyciami"},
    "crosshatch":   {"label": "✖️ Crosshatch",      "desc": "Kreskowanie krzyżowe"},
    "layers":       {"label": "🔬 Layers (Dodge)",  "desc": "Photoshop: Color Dodge + Gaussian Blur"},
    "blueprint":    {"label": "📐 Blueprint",       "desc": "Architektoniczny blueprint"},
}


# ── 8 Background Replacement Types ───────────────────────────────────────────
BG_REPLACE_TYPES = {
    "transparent":  {"label": "🔲 Przezroczyste",       "desc": "Brak tła (alpha)"},
    "white":        {"label": "⬜ Białe",               "desc": "Czyste białe tło"},
    "black":        {"label": "⬛ Czarne",              "desc": "Czarne tło"},
    "gray":         {"label": "🔘 Szare",               "desc": "Neutralne szare"},
    "gradient":     {"label": "🌈 Gradient",           "desc": "Gradient poziomy"},
    "checkerboard": {"label": "♟️ Szachownica",         "desc": "Szachownica (przezroczystość)"},
    "sepia":        {"label": "🟤 Sepia",              "desc": "Ciepłe brązowe retro"},
    "vintage":      {"label": "📜 Vintage paper",      "desc": "Tekstura starego papieru"},
}


def _to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "yes", "on")


# ──────────────────────────────────────────────────────────────────────────────
# Background replacement generators
# ──────────────────────────────────────────────────────────────────────────────

def _bg_transparent(size):
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _bg_white(size):
    return Image.new("RGB", size, (255, 255, 255))


def _bg_black(size):
    return Image.new("RGB", size, (0, 0, 0))


def _bg_gray(size):
    return Image.new("RGB", size, (180, 180, 180))


def _bg_gradient(size):
    w, h = size
    img = Image.new("RGB", (w, h))
    for x in range(w):
        ratio = x / w
        r = int(240 - ratio * 60)
        g = int(238 - ratio * 50)
        b = int(230 - ratio * 40)
        for y in range(h):
            img.putpixel((x, y), (r, g, b))
    return img


def _bg_checkerboard(size):
    w, h = size
    img = Image.new("RGB", size, (200, 200, 200))
    d = ImageDraw.Draw(img)
    sq = 16
    for y in range(0, h, sq):
        for x in range(0, w, sq):
            if ((x // sq) + (y // sq)) % 2 == 0:
                d.rectangle([x, y, x + sq - 1, y + sq - 1], fill=(235, 235, 235))
    return img


def _bg_sepia(size):
    w, h = size
    img = Image.new("RGB", size, (112, 66, 20))
    rng = random.Random(77)
    data = list(img.getdata())
    data = [(min(255, r + rng.randint(-8, 8)),
             min(255, g + rng.randint(-8, 8)),
             min(255, b + rng.randint(-8, 8))) for r, g, b in data]
    img.putdata(data)
    return img


def _bg_vintage(size):
    w, h = size
    img = Image.new("RGB", size, (235, 225, 205))
    rng = random.Random(55)
    data = list(img.getdata())
    data = [(min(255, max(0, r + rng.randint(-20, 15))),
             min(255, max(0, g + rng.randint(-18, 12))),
             min(255, max(0, b + rng.randint(-15, 10)))) for r, g, b in data]
    img.putdata(data)
    cx, cy = w / 2, h / 2
    max_dist = math.hypot(cx, cy)
    for y in range(h):
        for x in range(w):
            dist = math.hypot(x - cx, y - cy) / max_dist
            if dist > 0.5:
                darken = int(255 * (1 - (dist - 0.5) * 0.4))
                r, g, b = img.getpixel((x, y))
                img.putpixel((x, y), (int(r * darken / 255), int(g * darken / 255), int(b * darken / 255)))
    return img


_BG_REPLACE_FUNCS = {
    "transparent":  _bg_transparent,
    "white":        _bg_white,
    "black":        _bg_black,
    "gray":         _bg_gray,
    "gradient":     _bg_gradient,
    "checkerboard": _bg_checkerboard,
    "sepia":        _bg_sepia,
    "vintage":      _bg_vintage,
}


# ──────────────────────────────────────────────────────────────────────────────
# Sketch style implementations
# ──────────────────────────────────────────────────────────────────────────────

def _sketch_pencil(img_rgb, intensity, line_w, keep_color):
    gray = img_rgb.convert("L")
    blur_r = 1.0 + intensity * 4.0
    blurred = gray.filter(ImageFilter.GaussianBlur(radius=blur_r))
    inverted = ImageOps.invert(blurred)
    result = _color_dodge_blend(gray, inverted)
    result = ImageEnhance.Contrast(result).enhance(1.0 + intensity * 0.8)
    if line_w > 1:
        for _ in range(line_w - 1):
            result = result.filter(ImageFilter.MaxFilter(3))
    if keep_color:
        color = img_rgb.convert("RGB")
        color = ImageEnhance.Color(color).enhance(0.7)
        result = ImageChops.multiply(color, result.convert("RGB"))
    return result


def _sketch_manga(img_rgb, intensity, line_w, keep_color):
    gray = img_rgb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.invert(edges)
    contour = gray.filter(ImageFilter.CONTOUR)
    contour = ImageOps.invert(contour)
    result = ImageChops.multiply(edges, contour)
    result = ImageEnhance.Contrast(result).enhance(1.5 + intensity)
    result = result.point(lambda p: 255 if p > 180 else 0)
    if line_w > 1:
        for _ in range(line_w - 1):
            result = result.filter(ImageFilter.MaxFilter(3))
    if keep_color:
        color = img_rgb.convert("RGB")
        result = ImageChops.multiply(color, result.convert("RGB"))
    return result


def _sketch_comic_bw(img_rgb, intensity, line_w, keep_color):
    gray = img_rgb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.invert(edges)
    edges = ImageEnhance.Contrast(edges).enhance(2.0)
    w, h = img_rgb.size
    halftone = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(halftone)
    dot_spacing = max(4, int(8 - intensity * 4))
    for y in range(0, h, dot_spacing):
        for x in range(0, w, dot_spacing):
            px = gray.getpixel((x, y))
            radius = max(1, int((255 - px) / 255.0 * dot_spacing * 0.45))
            d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=0)
    result = ImageChops.multiply(edges, halftone)
    result = result.point(lambda p: 255 if p > 128 else 0)
    if line_w > 1:
        for _ in range(line_w - 1):
            result = result.filter(ImageFilter.MaxFilter(3))
    return result


def _sketch_comic_color(img_rgb, intensity, line_w, keep_color):
    levels = max(3, int(8 - intensity * 4))
    posterized = img_rgb.quantize(colors=levels, method=Image.Quantize.MEDIANCUT).convert("RGB")
    gray = img_rgb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.invert(edges)
    edges = edges.point(lambda p: 0 if p > 100 else 255)
    if line_w > 1:
        for _ in range(line_w):
            edges = edges.filter(ImageFilter.MaxFilter(3))
    result = posterized.copy()
    result.paste(Image.new("RGB", result.size, (0, 0, 0)), mask=edges)
    result = ImageEnhance.Contrast(result).enhance(1.3)
    return result


def _sketch_charcoal(img_rgb, intensity, line_w, keep_color):
    gray = img_rgb.convert("L")
    smudge = gray.filter(ImageFilter.GaussianBlur(radius=2.0 + intensity * 2.0))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.invert(edges)
    edges = ImageEnhance.Contrast(edges).enhance(1.5 + intensity)
    paper = Image.new("L", img_rgb.size, 200)
    result = ImageChops.darker(paper, edges)
    result = ImageChops.multiply(result, smudge)
    result = ImageEnhance.Contrast(result).enhance(1.2)
    w, h = img_rgb.size
    grain = Image.new("L", (w, h), 128)
    rng = random.Random(42)
    grain_data = list(grain.getdata())
    grain_data = [min(255, max(0, v + rng.randint(-30, 30))) for v in grain_data]
    grain.putdata(grain_data)
    result = ImageChops.multiply(result, grain)
    if keep_color:
        color = img_rgb.convert("RGB")
        color = ImageEnhance.Color(color).enhance(0.5)
        result = ImageChops.multiply(color, result.convert("RGB"))
    return result


def _sketch_ink(img_rgb, intensity, line_w, keep_color):
    gray = img_rgb.convert("L")
    edges1 = gray.filter(ImageFilter.FIND_EDGES)
    edges1 = ImageOps.invert(edges1)
    edges1 = ImageEnhance.Contrast(edges1).enhance(2.0 + intensity)
    edges2 = gray.filter(ImageFilter.CONTOUR)
    edges2 = ImageOps.invert(edges2)
    edges2 = ImageEnhance.Contrast(edges2).enhance(1.5)
    result = ImageChops.darker(edges1, edges2)
    threshold = int(160 - intensity * 40)
    result = result.point(lambda p: 255 if p > threshold else 0)
    if line_w > 1:
        for _ in range(line_w - 1):
            result = result.filter(ImageFilter.MaxFilter(3))
    return result


def _sketch_watercolor(img_rgb, intensity, line_w, keep_color):
    blurred = img_rgb.filter(ImageFilter.GaussianBlur(radius=3.0 + intensity * 5.0))
    gray = img_rgb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.invert(edges)
    edges = edges.filter(ImageFilter.GaussianBlur(radius=2.0))
    edges = edges.point(lambda p: 255 if p > 200 else p)
    color = ImageEnhance.Color(blurred).enhance(1.5 + intensity)
    color = ImageEnhance.Brightness(color).enhance(1.1)
    edge_rgb = edges.convert("RGB")
    result = Image.blend(color, edge_rgb, 0.15)
    result = ImageEnhance.Contrast(result).enhance(0.9)
    return result


def _sketch_crosshatch(img_rgb, intensity, line_w, keep_color):
    gray = img_rgb.convert("L")
    w, h = img_rgb.size
    canvas = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(canvas)
    spacing = max(3, int(8 - intensity * 4))
    for angle_idx in range(3):
        angle = angle_idx * 45
        for y in range(0, h, spacing):
            for x in range(0, w, spacing):
                px = gray.getpixel((x, y))
                darkness = 255 - px
                if darkness > 30:
                    length = int(spacing * 0.8 * (darkness / 255.0))
                    if angle == 0:
                        d.line((x, y, x + length, y), fill=255 - darkness, width=1)
                    elif angle == 45:
                        d.line((x, y, x + length, y + length), fill=255 - darkness, width=1)
                    else:
                        d.line((x + length, y, x, y + length), fill=255 - darkness, width=1)
    if keep_color:
        color = img_rgb.convert("RGB")
        color = ImageEnhance.Color(color).enhance(0.6)
        return ImageChops.multiply(color, canvas.convert("RGB"))
    return canvas.convert("RGB")


def _sketch_layers(img_rgb, intensity, line_w, keep_color):
    gray = img_rgb.convert("L")
    inverted = ImageOps.invert(gray)
    blur_r = 1.0 + intensity * 10.0
    blurred_inverted = inverted.filter(ImageFilter.GaussianBlur(radius=blur_r))
    result = _color_dodge_blend(gray, blurred_inverted)
    result = ImageEnhance.Contrast(result).enhance(1.2 + intensity * 0.5)
    result = ImageEnhance.Brightness(result).enhance(0.9 + intensity * 0.2)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.invert(edges)
    edges = edges.point(lambda p: 255 if p > 200 else p)
    result = ImageChops.darker(result, edges)
    if line_w > 1:
        for _ in range(line_w - 1):
            result = result.filter(ImageFilter.MaxFilter(3))
    if keep_color:
        color = img_rgb.convert("RGB")
        color = ImageEnhance.Color(color).enhance(0.8)
        result = ImageChops.multiply(color, result.convert("RGB"))
    return result


def _sketch_blueprint(img_rgb, intensity, line_w, keep_color):
    gray = img_rgb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.invert(edges)
    edges = ImageEnhance.Contrast(edges).enhance(1.5 + intensity)
    edges = edges.point(lambda p: 255 if p > 140 else 0)
    if line_w > 1:
        for _ in range(line_w - 1):
            edges = edges.filter(ImageFilter.MaxFilter(3))
    blue_bg = Image.new("RGB", img_rgb.size, (30, 60, 140))
    w, h = img_rgb.size
    grid = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(grid)
    grid_spacing = 20
    for x in range(0, w, grid_spacing):
        d.line((x, 0, x, h), fill=40, width=1)
    for y in range(0, h, grid_spacing):
        d.line((0, y, w, y), fill=40, width=1)
    grid_rgb = Image.merge("RGB", (grid, grid, grid))
    blue_bg = ImageChops.lighter(blue_bg, grid_rgb)
    white_edges = Image.merge("RGB", (edges, edges, edges))
    result = ImageChops.screen(blue_bg, white_edges)
    return result


_STYLE_FUNCS = {
    "pencil":       _sketch_pencil,
    "manga":        _sketch_manga,
    "comic_bw":     _sketch_comic_bw,
    "comic_color":  _sketch_comic_color,
    "charcoal":     _sketch_charcoal,
    "ink":          _sketch_ink,
    "watercolor":   _sketch_watercolor,
    "crosshatch":   _sketch_crosshatch,
    "layers":       _sketch_layers,
    "blueprint":    _sketch_blueprint,
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _color_dodge_blend(base, blend):
    import numpy as np
    base_np = np.array(base, dtype=np.float32)
    blend_np = np.array(blend, dtype=np.float32)
    denom = 255.0 - blend_np
    denom = np.maximum(denom, 1.0)
    result = (base_np * 255.0) / denom
    result = np.clip(result, 0, 255).astype(np.uint8)
    return Image.fromarray(result, mode="L")


# ── METADATA ─────────────────────────────────────────────────────────────────
METADATA = {
    "id": "smart_sketch",
    "name": "🎨 Smart Sketch",
    "description": "Inteligentny szkic z osobnymi stylami dla postaci i tła. 10 styli szkicu + opcja wymiany tła na 8 predefiniowanych typów.",
    "version": "2.0.0",
    "icon": "🎨",
    "options": {
        "model": {
            "type": "select",
            "label": "Model AI (maska postaci)",
            "choices": {
                "u2net": "u2net (szybki)",
                "birefnet-general": "birefnet-general (jakość)",
                "isnet-general-use": "isnet-general-use",
                "u2net_human_seg": "u2net_human_seg (ludzie)",
            },
            "default": "u2net",
        },
        "fg_style": {
            "type": "select",
            "label": "Postać: styl szkicu",
            "choices": {sid: s["label"] for sid, s in SKETCH_STYLES.items()},
            "default": "layers",
        },
        "fg_intensity": {
            "type": "slider",
            "label": "Postać: intensywność",
            "min": 0, "max": 100, "step": 1,
            "default": 60,
        },
        "fg_line": {
            "type": "slider",
            "label": "Postać: grubość linii",
            "min": 1, "max": 8, "step": 1,
            "default": 2,
        },
        "fg_color": {
            "type": "checkbox",
            "label": "Postać: zachowaj kolor",
            "default": "false",
        },
        "bg_style": {
            "type": "select",
            "label": "Tło: styl szkicu",
            "choices": {sid: s["label"] for sid, s in SKETCH_STYLES.items()},
            "default": "pencil",
        },
        "bg_intensity": {
            "type": "slider",
            "label": "Tło: intensywność szkicu",
            "min": 0, "max": 100, "step": 1,
            "default": 40,
        },
        "bg_line": {
            "type": "slider",
            "label": "Tło: grubość linii szkicu",
            "min": 1, "max": 8, "step": 1,
            "default": 1,
        },
        "bg_color": {
            "type": "checkbox",
            "label": "Tło: szkic w kolorze",
            "default": "false",
        },
        "bg_replace": {
            "type": "checkbox",
            "label": "🔄 Wymień tło",
            "default": "false",
        },
        "bg_replace_type": {
            "type": "select",
            "label": "Typ nowego tła",
            "choices": {bid: b["label"] for bid, b in BG_REPLACE_TYPES.items()},
            "default": "white",
        },
    },
}


# ── Plugin interface ─────────────────────────────────────────────────────────
def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", METADATA["options"]["model"]["default"])
    fg_style = options.get("fg_style", METADATA["options"]["fg_style"]["default"])
    bg_style = options.get("bg_style", METADATA["options"]["bg_style"]["default"])
    fg_intensity = float(options.get("fg_intensity", 60)) / 100.0
    bg_intensity = float(options.get("bg_intensity", 40)) / 100.0
    fg_line = int(options.get("fg_line", 2))
    bg_line = int(options.get("bg_line", 1))
    fg_color = _to_bool(options.get("fg_color", "false"))
    bg_color = _to_bool(options.get("bg_color", "false"))

    # Wymiana tła
    bg_replace = _to_bool(options.get("bg_replace", "false"))
    bg_replace_type = options.get("bg_replace_type", METADATA["options"]["bg_replace_type"]["default"])

    # Load image
    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    src_rgb = src.convert("RGB")
    size = src.size

    # Extract foreground mask
    session = _get_session(model_name)
    fg_mask = remove(src, session=session).convert("RGBA").getchannel("A")
    fg_mask = fg_mask.filter(ImageFilter.GaussianBlur(radius=1.5))

    # ── Generate foreground sketch ───────────────────────────────────────
    fg_func = _STYLE_FUNCS.get(fg_style, _sketch_pencil)
    fg_result = fg_func(src_rgb, fg_intensity, fg_line, fg_color)

    # ── Generate background ──────────────────────────────────────────────
    if bg_replace:
        # Wymiana tła — użyj predefiniowanego typu
        bg_gen = _BG_REPLACE_FUNCS.get(bg_replace_type, _bg_white)
        bg = bg_gen(size)
    else:
        # Szkic tła z oryginalnego zdjęcia
        bg_func = _STYLE_FUNCS.get(bg_style, _sketch_pencil)
        bg = bg_func(src_rgb, bg_intensity, bg_line, bg_color)

    # ── Composite FG on BG ───────────────────────────────────────────────
    fg_rgba = fg_result.convert("RGBA")
    if bg.mode == "RGBA":
        out = Image.alpha_composite(bg, fg_rgba)
    else:
        out = bg.convert("RGBA")
        out.paste(fg_rgba, mask=fg_mask)

    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
