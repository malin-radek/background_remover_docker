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
import math
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
        # "Papier" zamiast ciemnej bazy, żeby postać nie wpadała w czarną plamę
        paper = Image.new("RGB", base_rgb.size, (236, 236, 236))
        merged = ImageChops.multiply(paper, edge.convert("RGB"))

    merged = ImageEnhance.Contrast(merged).enhance(1.0 + intensity * 0.6)
    merged = ImageChops.multiply(merged, _pattern_layer(merged.size, pattern).convert("RGB"))
    return merged


def _largest_components(mask_l: Image.Image, max_people: int = 3):
    m = mask_l.point(lambda p: 255 if p > 20 else 0).convert("1")
    labels = m.copy().convert("L")
    pix = labels.load()
    w, h = labels.size
    visited = [[False] * h for _ in range(w)]
    comps = []
    for x in range(w):
        for y in range(h):
            if visited[x][y] or pix[x, y] == 0:
                continue
            stack = [(x, y)]
            visited[x][y] = True
            pts = []
            minx = maxx = x
            miny = maxy = y
            while stack:
                cx, cy = stack.pop()
                pts.append((cx, cy))
                minx, maxx = min(minx, cx), max(maxx, cx)
                miny, maxy = min(miny, cy), max(maxy, cy)
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < w and 0 <= ny < h and (not visited[nx][ny]) and pix[nx, ny] != 0:
                        visited[nx][ny] = True
                        stack.append((nx, ny))
            area = len(pts)
            if area > (w * h) * 0.003:
                comps.append((area, (minx, miny, maxx, maxy), pts))
    comps.sort(key=lambda x: x[0], reverse=True)
    return comps[:max_people]


def _mask_from_points(size, pts):
    out = Image.new("L", size, 0)
    d = ImageDraw.Draw(out)
    for x, y in pts:
        d.point((x, y), fill=255)
    return out.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.0))


def _manga_hero_intelligent(src_rgb: Image.Image, person_mask: Image.Image, fg_style: str, fg_pattern: str, fg_int: float, fg_line: int, fg_color: bool):
    w, h = src_rgb.size
    base_style = "manga" if fg_style == "original" else fg_style
    # Jasna baza "papieru" pod postać (eliminuje czarną plamę)
    paper = Image.new("RGBA", (w, h), (246, 246, 246, 255))
    # Background: quieter so characters pop
    bg = _stylize(src_rgb, "pencil", 0.25, 1, False, "grid").convert("RGBA")
    out = bg.copy()

    comps = _largest_components(person_mask, max_people=4)
    if not comps:
        return out

    region_patterns = ["line", "cross", "grid"]
    for _, (minx, miny, maxx, maxy), pts in comps:
        ph = max(1, maxy - miny + 1)
        # Heuristic body parts from silhouette proportions
        head_y = miny + int(ph * 0.20)
        torso_y = miny + int(ph * 0.56)
        legs_y = miny + int(ph * 0.98)
        parts = {"head": [], "torso": [], "legs": []}
        for x, y in pts:
            if y <= head_y:
                parts["head"].append((x, y))
            elif y <= torso_y:
                parts["torso"].append((x, y))
            elif y <= legs_y:
                parts["legs"].append((x, y))

        for i, key in enumerate(("head", "torso", "legs")):
            p = parts[key]
            if not p:
                continue
            part_mask = _mask_from_points((w, h), p)
            # 1) Wypełnienie: jasne, lekko tonowane mapą jasności regionu
            gray = src_rgb.convert("L")
            local_tone = ImageOps.autocontrast(gray.crop((minx, miny, maxx + 1, maxy + 1)))
            local_tone = local_tone.filter(ImageFilter.GaussianBlur(1.0))
            tone_canvas = Image.new("L", (w, h), 220)
            tone_canvas.paste(local_tone, (minx, miny))
            tone_rgb = Image.merge("RGB", (tone_canvas, tone_canvas, tone_canvas))
            fill_rgba = paper.copy()
            fill_rgba = ImageChops.multiply(fill_rgba.convert("RGB"), tone_rgb).convert("RGBA")

            # 2) Hatch jako cieniowanie (nie przyciemnianie całości)
            local_pattern = fg_pattern if fg_pattern in ("line", "cross", "grid", "spiral") else region_patterns[i]
            hatch = _pattern_layer((w, h), local_pattern)
            hatch_alpha = ImageOps.invert(tone_canvas).point(lambda v: int(v * 0.45))
            hatch_rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            hatch_rgba.putalpha(ImageChops.multiply(hatch, hatch_alpha))

            # 3) Kontur części ciała: ciągła, grubsza kreska
            edges = part_mask.filter(ImageFilter.FIND_EDGES)
            for _ in range(max(2, fg_line)):
                edges = edges.filter(ImageFilter.MaxFilter(3))
            edge_alpha = ImageEnhance.Contrast(edges).enhance(2.8).point(lambda v: 255 if v > 26 else 0)
            edge_rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            edge_rgba.putalpha(edge_alpha)

            out = Image.composite(fill_rgba, out, part_mask)
            out = Image.alpha_composite(out, hatch_rgba)
            out = Image.alpha_composite(out, edge_rgba)

    # Globalny kontur sylwetki dla czytelności "manga hero"
    silhouette_edge = person_mask.filter(ImageFilter.FIND_EDGES)
    for _ in range(max(2, fg_line + 1)):
        silhouette_edge = silhouette_edge.filter(ImageFilter.MaxFilter(3))
    sil_alpha = ImageEnhance.Contrast(silhouette_edge).enhance(3.0).point(lambda v: 255 if v > 18 else 0)
    sil_rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sil_rgba.putalpha(sil_alpha)
    out = Image.alpha_composite(out, sil_rgba)

    return out


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

    # Preset traktujemy jako "tryb", ale nie nadpisujemy ręcznych opcji UI.
    # Dzięki temu zmiana stylu/suwaków zawsze działa natychmiast.

    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    src_rgb = src.convert("RGB")
    mask = remove(src, session=_get_session(model)).convert("RGBA").getchannel("A").filter(ImageFilter.GaussianBlur(1.2))

    fg_st = _stylize(src_rgb, fg_style, fg_int, fg_line, fg_color, fg_pattern).convert("RGBA")
    bg_st = _stylize(src_rgb, bg_style, bg_int, bg_line, bg_color, bg_pattern).convert("RGBA")
    out = Image.composite(fg_st, bg_st, mask)
    if preset == "manga_hero" and fg_style != "original":
        # Inteligentny tryb tylko jako warstwa "hero", ale nie kasuje ustawień UI
        out = _manga_hero_intelligent(src_rgb, mask, fg_style, fg_pattern, fg_int, fg_line, fg_color)

    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
