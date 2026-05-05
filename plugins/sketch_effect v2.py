"""
Plugin: Sketch Effect v2
"""

METADATA = {
    "id": "sketch_effect_pro",
    "name": "✏️ Szkic Pro",
    "description": "Szkic osobno dla postaci i tła (ołówek/węgiel/kredki/manga)",
    "version": "2.1.0",
    "author": "Radek",
    "icon": "📝",
    "options": {
        "preset": {"type": "select", "label": "Preset", "choices": {"custom": "Custom", "manga_hero": "Manga Hero", "charcoal_drama": "Charcoal Drama", "color_crayon_portrait": "Color Crayon Portrait"}, "default": "custom"},
        "model": {"type": "select", "label": "Maska postaci (AI)", "choices": {"u2net": "u2net (szybki)", "birefnet-general": "birefnet-general (jakość)", "isnet-general-use": "isnet-general-use", "u2net_human_seg": "u2net_human_seg (ludzie)"}, "default": "u2net"},
        "fg_style": {"type": "select", "label": "Postać: styl", "choices": {"original": "Oryginał", "pencil": "Ołówek", "charcoal": "Węgiel", "crayon": "Kredki", "manga": "Manga line"}, "default": "manga"},
        "bg_style": {"type": "select", "label": "Tło: styl", "choices": {"original": "Oryginał", "pencil": "Ołówek", "charcoal": "Węgiel", "crayon": "Kredki", "manga": "Manga line"}, "default": "pencil"},
        "fg_pattern": {"type": "select", "label": "Postać: wypełnienie", "choices": {"line": "Kreska", "cross": "Krzyżyki", "grid": "Kratka", "spiral": "Spirala"}, "default": "line"},
        "bg_pattern": {"type": "select", "label": "Tło: wypełnienie", "choices": {"line": "Kreska", "cross": "Krzyżyki", "grid": "Kratka", "spiral": "Spirala"}, "default": "line"},
        "fg_intensity": {"type": "slider", "label": "Postać: intensywność", "min": 0, "max": 100, "step": 1, "default": 75},
        "bg_intensity": {"type": "slider", "label": "Tło: intensywność", "min": 0, "max": 100, "step": 1, "default": 55},
        "fg_line": {"type": "slider", "label": "Postać: grubość linii", "min": 1, "max": 6, "step": 1, "default": 2},
        "bg_line": {"type": "slider", "label": "Tło: grubość linii", "min": 1, "max": 6, "step": 1, "default": 2},
        "fg_color": {"type": "checkbox", "label": "Postać: zachowaj kolor", "default": "true"},
        "bg_color": {"type": "checkbox", "label": "Tło: zachowaj kolor", "default": "false"},
    },
}

import io
import threading
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


def _to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "yes", "on")


def _pattern_layer(size, kind: str):
    w, h = size
    p = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(p)
    step = 10
    if kind == "cross":
        for y in range(0, h, step):
            for x in range(0, w, step):
                d.line((x - 2, y - 2, x + 2, y + 2), fill=200, width=1)
                d.line((x - 2, y + 2, x + 2, y - 2), fill=200, width=1)
    elif kind == "grid":
        for x in range(0, w, step):
            d.line((x, 0, x, h), fill=215, width=1)
        for y in range(0, h, step):
            d.line((0, y, w, y), fill=215, width=1)
    elif kind == "spiral":
        for y in range(0, h, step):
            for x in range(0, w, step):
                d.arc((x - 4, y - 4, x + 4, y + 4), 0, 300, fill=205, width=1)
    else:
        for y in range(0, h, step):
            d.line((0, y, w, y), fill=210, width=1)
    return p


def _stylize(base_rgb: Image.Image, style: str, intensity: float, line_w: int, keep_color: bool, pattern: str) -> Image.Image:
    if style == "original":
        return base_rgb.copy()
    gray = base_rgb.convert("L")
    edge = gray.filter(ImageFilter.FIND_EDGES)
    if line_w > 1:
        for _ in range(line_w - 1):
            edge = edge.filter(ImageFilter.MaxFilter(3))
    edge = ImageOps.invert(edge)
    edge = ImageEnhance.Contrast(edge).enhance(1.2 + intensity * 1.4)

    if style == "manga":
        hatch = gray.filter(ImageFilter.CONTOUR)
        hatch = ImageOps.invert(hatch)
        edge = ImageChops.multiply(edge, hatch)
    elif style == "charcoal":
        noise = gray.filter(ImageFilter.GaussianBlur(radius=1.8))
        edge = ImageChops.darker(edge, ImageOps.invert(noise))
    elif style == "crayon":
        edge = edge.filter(ImageFilter.GaussianBlur(radius=0.8))

    if keep_color:
        color_base = ImageEnhance.Color(base_rgb).enhance(1.15 if style == "crayon" else 0.9)
        merged = ImageChops.multiply(color_base, edge.convert("RGB"))
    else:
        merged = ImageChops.multiply(gray.convert("RGB"), edge.convert("RGB"))

    merged = ImageEnhance.Contrast(merged).enhance(1.0 + intensity * 0.6)
    merged = ImageChops.multiply(merged, _pattern_layer(merged.size, pattern).convert("RGB"))
    return merged


def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model = options.get("model", METADATA["options"]["model"]["default"])
    preset = options.get("preset", "custom")
    fg_style = options.get("fg_style", METADATA["options"]["fg_style"]["default"])
    bg_style = options.get("bg_style", METADATA["options"]["bg_style"]["default"])
    fg_pattern = options.get("fg_pattern", "line")
    bg_pattern = options.get("bg_pattern", "line")
    fg_int = float(options.get("fg_intensity", 75)) / 100.0
    bg_int = float(options.get("bg_intensity", 55)) / 100.0
    fg_line = int(options.get("fg_line", 2))
    bg_line = int(options.get("bg_line", 2))
    fg_color = _to_bool(options.get("fg_color", "true"))
    bg_color = _to_bool(options.get("bg_color", "false"))

    if preset == "manga_hero":
        fg_style, bg_style = "manga", "pencil"
        fg_pattern, bg_pattern = "line", "grid"
        fg_int, bg_int = 0.95, 0.35
        fg_line, bg_line = 4, 1
        fg_color, bg_color = False, False
    elif preset == "charcoal_drama":
        fg_style, bg_style = "charcoal", "charcoal"
        fg_pattern, bg_pattern = "cross", "line"
        fg_int, bg_int = 0.98, 0.72
        fg_line, bg_line = 5, 3
        fg_color, bg_color = False, False
    elif preset == "color_crayon_portrait":
        fg_style, bg_style = "crayon", "pencil"
        fg_pattern, bg_pattern = "spiral", "line"
        fg_int, bg_int = 0.82, 0.30
        fg_line, bg_line = 2, 1
        fg_color, bg_color = True, False

    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    src_rgb = src.convert("RGB")
    mask = remove(src, session=_get_session(model)).convert("RGBA").getchannel("A").filter(ImageFilter.GaussianBlur(1.2))

    fg_st = _stylize(src_rgb, fg_style, fg_int, fg_line, fg_color, fg_pattern).convert("RGBA")
    bg_st = _stylize(src_rgb, bg_style, bg_int, bg_line, bg_color, bg_pattern).convert("RGBA")
    out = Image.composite(fg_st, bg_st, mask)

    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()

