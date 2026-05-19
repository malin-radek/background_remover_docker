"""
Plugin: Sketch & Embroidery Pipeline — 18 Sketch Styles
Pełny pipeline przetwarzania zdjęcia na szkic:
  Zdjęcie → Preprocessing → Edge detection → Color segmentation → Stylizacja → Overlay + postprocessing

18 stylów: Pencil, Charcoal, Ink, Colored Pencil, Watercolor, Ballpoint Pen,
Pastel, Fine Detail, Da Vinci Manuscript, Bold, Minimalist Line, Figure Quick,
Cartoon, Concept, Manga, Aesthetic, Graffiti, Ink Wash
"""

import io
import math
import threading
import random
from PIL import Image, ImageFilter, ImageOps, ImageEnhance, ImageChops, ImageDraw
import numpy as np
import cv2

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


def _color_dodge_blend(base, blend):
    base_np = np.array(base, dtype=np.float32)
    blend_np = np.array(blend, dtype=np.float32)
    denom = 255.0 - blend_np
    denom = np.maximum(denom, 1.0)
    result = (base_np * 255.0) / denom
    result = np.clip(result, 0, 255).astype(np.uint8)
    return Image.fromarray(result, mode="L")


# ── 18 Sketch Styles ─────────────────────────────────────────────────────────
SKETCH_STYLES = {
    "pencil_sketch":       {"label": "✏️ Pencil Sketch",        "desc": "Klasyczny szkic ołówkiem"},
    "charcoal_sketch":     {"label": "🖤 Charcoal Sketch",      "desc": "Rysunek węglem, ciemny, teksturowany"},
    "ink_sketch":          {"label": "🪶 Ink Sketch",           "desc": "Czyste czarne linie, wysoki kontrast"},
    "colored_pencil":      {"label": "️ Colored Pencil",      "desc": "Kolorowe ołówki, warstwowe"},
    "watercolor_sketch":   {"label": "💧 Watercolor Sketch",    "desc": "Akwarelowe plamy, miękkie krawędzie"},
    "ballpoint_pen":       {"label": "🖊️ Ballpoint Pen",       "desc": "Długopis, crosshatching, niebieski/czarny"},
    "pastel_sketch":       {"label": "🌸 Pastel Sketch",        "desc": "Pastelowe, kredkowe, miękkie"},
    "fine_detail":         {"label": "🔍 Fine Detail Sketch",   "desc": "Bardzo ostre, cienkie linie, wysoki detal"},
    "da_vinci_manuscript": {"label": "📜 Da Vinci Manuscript",  "desc": "Sepia, staropapierny, kreskowanie renesansowe"},
    "bold_sketch":         {"label": "💪 Bold Sketch",          "desc": "Grube, dramatyczne linie"},
    "minimalist_line":     {"label": "〰️ Minimalist Line",     "desc": "Minimalistyczny, bardzo mało linii"},
    "figure_quick":        {"label": "⚡ Figure Quick Sketch",  "desc": "Gesturalny, luźny, szybkie kreski"},
    "cartoon_sketch":      {"label": "🎭 Cartoon Sketch",       "desc": "Grube kontury, uproszczony, cel-shaded"},
    "concept_sketch":      {"label": "📐 Concept Sketch",       "desc": "Architektoniczny, techniczny, siatka"},
    "manga_sketch":        {"label": "🎌 Manga Sketch",         "desc": "Anime styl, screentones, czyste linie"},
    "aesthetic_sketch":    {"label": "✨ Aesthetic Sketch",     "desc": "Miękki, marzycielski, pastelowe tony, sparkles"},
    "graffiti_sketch":     {"label": "🎨 Graffiti Sketch",      "desc": "Street art, spray paint, bold colors"},
    "ink_wash_sketch":     {"label": "🏮 Ink Wash Sketch",      "desc": "Azjatycki tusz, washes, sumi-e styl"},
}


# ── Pipeline Step 1: Preprocessing ──────────────────────────────────────────
def _preprocess(img_rgb, denoise_strength, contrast_boost, brightness_adj):
    arr = np.array(img_rgb, dtype=np.uint8)
    if denoise_strength > 0:
        d = int(denoise_strength * 2)
        arr = cv2.bilateralFilter(arr, d, d * 10, d * 10)
    if contrast_boost != 1.0:
        arr = cv2.convertScaleAbs(arr, alpha=contrast_boost, beta=0)
    if brightness_adj != 0:
        arr = cv2.convertScaleAbs(arr, alpha=1.0, beta=brightness_adj)
    return Image.fromarray(arr, mode="RGB")


# ─ Pipeline Step 2: Edge Detection ─────────────────────────────────────────
def _edge_detection(img_rgb, method, low_thresh, high_thresh, aperture):
    gray = cv2.cvtColor(np.array(img_rgb), cv2.COLOR_RGB2GRAY)
    if method == "canny":
        edges = cv2.Canny(gray, low_thresh, high_thresh, apertureSize=aperture)
    elif method == "sobel":
        sx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=aperture)
        sy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=aperture)
        edges = cv2.magnitude(sx, sy)
        edges = np.clip(edges, 0, 255).astype(np.uint8)
        _, edges = cv2.threshold(edges, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif method == "laplacian":
        edges = cv2.Laplacian(gray, cv2.CV_64F, ksize=aperture)
        edges = np.uint8(np.absolute(edges))
        _, edges = cv2.threshold(edges, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        edges_canny = cv2.Canny(gray, low_thresh, high_thresh, apertureSize=aperture)
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        adaptive_inv = cv2.bitwise_not(adaptive)
        edges = cv2.bitwise_and(edges_canny, adaptive_inv)
    return Image.fromarray(edges, mode="L")


# ── Pipeline Step 3: Color Segmentation (K-means) ───────────────────────────
def _color_segmentation(img_rgb, k_clusters, max_iter, compactness):
    arr = np.array(img_rgb, dtype=np.float32).reshape((-1, 3))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, max_iter, compactness)
    _, labels, centers = cv2.kmeans(arr, k_clusters, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
    centers = np.uint8(centers)
    segmented = centers[labels.flatten()].reshape(img_rgb.size[1], img_rgb.size[0], 3)
    return Image.fromarray(segmented, mode="RGB")


# ── 18 Sketch Style Implementations ─────────────────────────────────────────

def _pencil_sketch(img_rgb, intensity):
    gray = img_rgb.convert("L")
    blur_r = 1.0 + intensity * 5.0
    blurred = gray.filter(ImageFilter.GaussianBlur(radius=blur_r))
    inverted = ImageOps.invert(blurred)
    result = _color_dodge_blend(gray, inverted)
    result = ImageEnhance.Contrast(result).enhance(1.0 + intensity * 0.5)
    paper = Image.new("L", img_rgb.size, 248)
    result = ImageChops.lighter(result, paper)
    return result.convert("RGB")


def _charcoal_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    smudge = Image.fromarray(gray, "L")
    smudge = smudge.filter(ImageFilter.GaussianBlur(radius=2.0 + intensity * 3.0))
    edges = cv2.Canny(gray, 50, 150)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    edges_inv = ImageEnhance.Contrast(edges_inv).enhance(2.0)
    rng = random.Random(42)
    grain_data = [min(255, max(0, 210 + rng.randint(-25, 25))) for _ in range(img_rgb.size[0] * img_rgb.size[1])]
    grain = Image.new("L", img_rgb.size)
    grain.putdata(grain_data)
    result = ImageChops.darker(grain, edges_inv)
    result = ImageChops.multiply(result, smudge)
    result = ImageEnhance.Contrast(result).enhance(1.3 + intensity * 0.4)
    return result.convert("RGB")


def _ink_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges1 = cv2.Canny(gray, 30, 120)
    edges1 = cv2.dilate(edges1, np.ones((2, 2), np.uint8), iterations=1)
    edges1_img = Image.fromarray(edges1, "L")
    edges1_inv = ImageOps.invert(edges1_img)
    edges1_inv = ImageEnhance.Contrast(edges1_inv).enhance(2.5 + intensity)

    gray_img = Image.fromarray(gray, "L")
    edges2 = gray_img.filter(ImageFilter.CONTOUR)
    edges2 = ImageOps.invert(edges2)
    result = ImageChops.darker(edges1_inv, edges2)
    threshold = int(180 - intensity * 60)
    result = result.point(lambda p: 255 if p > threshold else 0)
    bg = Image.new("RGB", img_rgb.size, (255, 255, 255))
    result = ImageChops.multiply(bg, result.convert("RGB"))
    return result


def _colored_pencil(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    blurred = Image.fromarray(smooth, "RGB")
    blurred = blurred.filter(ImageFilter.GaussianBlur(radius=1.0 + intensity * 2.0))
    color_enhanced = ImageEnhance.Color(blurred).enhance(1.3 + intensity * 0.5)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 60, 180)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img).convert("RGB")
    result = Image.blend(color_enhanced, edges_inv, 0.15 + intensity * 0.15)
    result = ImageEnhance.Contrast(result).enhance(1.1)
    paper = Image.new("RGB", img_rgb.size, (250, 248, 240))
    result = Image.blend(paper, result, 0.85)
    return result


def _watercolor_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    blurred = Image.fromarray(smooth, "RGB")
    blurred = blurred.filter(ImageFilter.GaussianBlur(radius=4.0 + intensity * 8.0))
    color_boost = ImageEnhance.Color(blurred).enhance(1.6 + intensity * 0.8)
    brightness = ImageEnhance.Brightness(color_boost).enhance(1.15)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 40, 140)
    edges_img = Image.fromarray(edges, "L")
    edges_blur = edges_img.filter(ImageFilter.GaussianBlur(radius=2.0))
    edges_inv = ImageOps.invert(edges_blur)
    edge_rgb = edges_inv.convert("RGB")
    result = Image.blend(brightness, edge_rgb, 0.12)
    result = ImageEnhance.Contrast(result).enhance(0.85)
    paper = Image.new("RGB", img_rgb.size, (252, 248, 242))
    result = Image.blend(paper, result, 0.9)
    return result


def _ballpoint_pen(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, 40, 150)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    w, h = img_rgb.size
    spacing = max(3, int(8 - intensity * 5))
    
    # Szybki crosshatching - użyj downscaled gray do obliczeń
    scale = max(1, spacing // 2)
    gray_small = cv2.resize(gray, (w // scale, h // scale), interpolation=cv2.INTER_AREA)
    sh, sw = gray_small.shape
    
    crosshatch = Image.new("L", (w, h), 255)
    d_draw = ImageDraw.Draw(crosshatch)
    
    # Iteruj po mniejszej siatce - znacznie szybciej
    for y in range(0, sh, 1):
        for x in range(0, sw, 1):
            px = gray_small[y, x]
            darkness = 255 - px
            if darkness > 40:
                # Mapuj z powrotem do pełnej rozdzielczości
                fx, fy = x * scale, y * scale
                length = int(spacing * 0.7 * (darkness / 255.0))
                d_draw.line((fx, fy, fx + length, fy + length), fill=255 - darkness, width=1)
                d_draw.line((fx + length, fy, fx, fy + length), fill=255 - darkness, width=1)
    
    result = ImageChops.multiply(crosshatch, edges_inv)
    result = result.point(lambda p: 255 if p > 160 else 0)
    blue_tint = Image.new("RGB", img_rgb.size, (20, 30, 80))
    result_rgb = result.convert("RGB")
    result_rgb = ImageChops.screen(result_rgb, blue_tint)
    bg = Image.new("RGB", img_rgb.size, (255, 255, 255))
    result_rgb = ImageChops.multiply(bg, result_rgb)
    return result_rgb


def _pastel_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    blurred = Image.fromarray(smooth, "RGB")
    blurred = blurred.filter(ImageFilter.GaussianBlur(radius=3.0 + intensity * 4.0))
    color_soft = ImageEnhance.Color(blurred).enhance(1.4 + intensity * 0.4)
    brightness = ImageEnhance.Brightness(color_soft).enhance(1.2)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 50, 160)
    edges_img = Image.fromarray(edges, "L")
    edges_soft = edges_img.filter(ImageFilter.GaussianBlur(radius=3.0))
    edges_inv = ImageOps.invert(edges_soft)
    edge_rgb = edges_inv.convert("RGB")
    result = Image.blend(brightness, edge_rgb, 0.1)
    chalk = Image.new("RGB", img_rgb.size, (245, 240, 235))
    rng = random.Random(77)
    data = list(chalk.getdata())
    data = [(min(255, r + rng.randint(-10, 10)), min(255, g + rng.randint(-8, 8)), min(255, b + rng.randint(-6, 6))) for r, g, b in data]
    chalk.putdata(data)
    result = Image.blend(chalk, result, 0.75 + intensity * 0.15)
    return result


def _fine_detail(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(3 + intensity * 3)
    smooth = cv2.bilateralFilter(arr, d, 30, 30)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, 20, 80, apertureSize=5)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    edges_inv = ImageEnhance.Contrast(edges_inv).enhance(1.5 + intensity * 0.5)
    detail = Image.fromarray(gray, "L")
    detail = detail.filter(ImageFilter.DETAIL)
    detail_edges = cv2.Canny(np.array(detail), 30, 100)
    detail_img = Image.fromarray(detail_edges, "L")
    detail_inv = ImageOps.invert(detail_img)
    result = ImageChops.darker(edges_inv, detail_inv)
    result = result.point(lambda p: 255 if p > 200 else p)
    bg = Image.new("RGB", img_rgb.size, (255, 255, 255))
    result = ImageChops.multiply(bg, result.convert("RGB"))
    return result


def _da_vinci_manuscript(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, 40, 140)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    w, h = img_rgb.size
    hatching = Image.new("L", (w, h), 255)
    d_draw = ImageDraw.Draw(hatching)
    spacing = max(4, int(10 - intensity * 6))
    for y in range(0, h, spacing):
        for x in range(0, w, spacing):
            px = gray[y, x]
            darkness = 255 - px
            if darkness > 30:
                length = int(spacing * 0.8 * (darkness / 255.0))
                d_draw.line((x, y, x + length, y + length), fill=255 - darkness, width=1)
    result = ImageChops.multiply(hatching, edges_inv)
    
    # Szybka winieta - operacje wektorowe zamiast pixel-by-pixel
    sepia_bg = Image.new("RGB", img_rgb.size, (180, 160, 120))
    rng = random.Random(55)
    data = list(sepia_bg.getdata())
    data = [(min(255, r + rng.randint(-15, 10)), min(255, g + rng.randint(-12, 8)), min(255, b + rng.randint(-10, 5))) for r, g, b in data]
    sepia_bg.putdata(data)
    
    # Winieta przez numpy - szybko!
    sepia_arr = np.array(sepia_bg, dtype=np.float32)
    y_coords, x_coords = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    max_dist = math.hypot(cx, cy)
    dist = np.sqrt((x_coords - cx)**2 + (y_coords - cy)**2) / max_dist
    vignette_mask = np.ones((h, w), dtype=np.float32)
    darken_region = dist > 0.4
    darken_factor = 1 - (dist[darken_region] - 0.4) * 0.5
    vignette_mask[darken_region] = darken_factor
    sepia_arr = sepia_arr * vignette_mask[..., np.newaxis]
    sepia_bg = Image.fromarray(np.clip(sepia_arr, 0, 255).astype(np.uint8), "RGB")
    
    result_rgb = result.convert("RGB")
    result_rgb = ImageChops.multiply(sepia_bg, result_rgb)
    return result_rgb


def _bold_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, 30, 100)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    edges_inv = ImageEnhance.Contrast(edges_inv).enhance(2.0 + intensity)
    result = edges_inv.point(lambda p: 255 if p > 150 else 0)
    bg = Image.new("RGB", img_rgb.size, (255, 255, 255))
    result = ImageChops.multiply(bg, result.convert("RGB"))
    return result


def _minimalist_line(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(7 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 75, 75)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    edges = cv2.Canny(gray, 80, 200)
    edges = cv2.erode(edges, np.ones((2, 2), np.uint8), iterations=1)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    result = edges_inv.point(lambda p: 255 if p > 220 else 0)
    bg = Image.new("RGB", img_rgb.size, (255, 255, 255))
    result = ImageChops.multiply(bg, result.convert("RGB"))
    return result


def _figure_quick(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, 40, 140)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    rng = np.random.RandomState(42)
    edges_arr = np.array(edges_inv)
    edges_arr = np.clip(edges_arr.astype(np.int16) + rng.randint(-20, 20, edges_arr.shape), 0, 255).astype(np.uint8)
    result = Image.fromarray(edges_arr, "L")
    result = ImageEnhance.Contrast(result).enhance(1.3)
    result = result.point(lambda p: 255 if p > 170 else 0)
    paper = Image.new("RGB", img_rgb.size, (250, 245, 235))
    result = ImageChops.multiply(paper, result.convert("RGB"))
    return result


def _cartoon_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    blurred = Image.fromarray(smooth, "RGB")
    levels = max(4, int(12 - intensity * 6))
    posterized = blurred.quantize(colors=levels, method=Image.Quantize.MEDIANCUT).convert("RGB")
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 30, 100)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img).point(lambda p: 0 if p > 120 else 255)
    result = posterized.copy()
    result.paste(Image.new("RGB", result.size, (0, 0, 0)), mask=edges_inv)
    result = ImageEnhance.Contrast(result).enhance(1.3)
    return result


def _concept_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, 40, 140)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    w, h = img_rgb.size
    grid = Image.new("L", (w, h), 0)
    d_draw = ImageDraw.Draw(grid)
    grid_spacing = 25
    for x in range(0, w, grid_spacing):
        d_draw.line((x, 0, x, h), fill=30, width=1)
    for y in range(0, h, grid_spacing):
        d_draw.line((0, y, w, y), fill=30, width=1)
    grid_rgb = Image.merge("RGB", (grid, grid, grid))
    blueprint_bg = Image.new("RGB", img_rgb.size, (220, 215, 200))
    blueprint_bg = ImageChops.lighter(blueprint_bg, grid_rgb)
    result = ImageChops.multiply(blueprint_bg, edges_inv.convert("RGB"))
    result = ImageEnhance.Contrast(result).enhance(1.2 + intensity * 0.3)
    return result


def _manga_sketch(img_rgb, intensity, fg_mask=None):
    w, h = img_rgb.size
    arr = np.array(img_rgb)

    # Krok 1: Strong smoothing
    d = int(7 + intensity * 7)
    smooth = cv2.bilateralFilter(arr, d, 80, 80)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    line_canvas = np.zeros((h, w), dtype=np.uint8)
    line_thickness = max(1, int(3 - intensity * 2))

    # Krok 2: Jeśli mamy maskę postaci - wyciągnij DOKŁADNY kontur
    if fg_mask is not None:
        mask_arr = np.array(fg_mask, dtype=np.uint8)
        # Binarizacja maski
        _, mask_bin = cv2.threshold(mask_arr, 128, 255, cv2.THRESH_BINARY)
        # Morphological cleanup
        kernel = np.ones((5, 5), np.uint8)
        mask_clean = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_OPEN, kernel, iterations=1)
        
        # Znajdź kontur postaci - to jest DOKŁADNY outline!
        contours, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 1000:  # Tylko główne kontury
                # Smooth contour - wygładź ale zachowaj kształt
                epsilon = 0.002 + (1 - intensity) * 0.008
                approx = cv2.approxPolyDP(cnt, epsilon * cv2.arcLength(cnt, True), True)
                # Narysuj ciągłą linię konturu
                cv2.polylines(line_canvas, [approx], True, 255, line_thickness + 1)
                
                # Wewnętrzne detale - edge detection TYLKO wewnątrz maski
                edges = cv2.Canny(gray, 50, 150)
                edges_masked = cv2.bitwise_and(edges, edges, mask=mask_clean // 255)
                # Usuń krawędzie przy brzegu maski (to już jest kontur)
                edge_kernel = np.ones((5, 5), np.uint8)
                mask_dilated = cv2.dilate(mask_clean, edge_kernel, iterations=3)
                mask_eroded = cv2.erode(mask_clean, edge_kernel, iterations=3)
                border = cv2.subtract(mask_dilated, mask_eroded)
                edges_inner = cv2.bitwise_and(edges_masked, cv2.bitwise_not(border))
                
                # Narysuj wewnętrzne detale
                inner_contours, _ = cv2.findContours(edges_inner, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for ic in inner_contours:
                    if cv2.arcLength(ic, False) > 30:
                        cv2.polylines(line_canvas, [ic], False, 255, line_thickness)

    else:
        # Fallback: edge detection bez maski
        block_size = int(15 - intensity * 10)
        if block_size < 3: block_size = 3
        if block_size % 2 == 0: block_size += 1
        c = max(2, int(8 - intensity * 5))
        edges = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV, block_size, c
        )
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
        edges = cv2.morphologyEx(edges, cv2.MORPH_OPEN, kernel, iterations=1)
        
        try:
            skel = cv2.ximgproc.thinning(edges)
        except AttributeError:
            skel = edges.copy()
        
        contours, _ = cv2.findContours(skel, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for cnt in contours:
            if cv2.arcLength(cnt, False) > 20:
                cv2.polylines(line_canvas, [cnt], False, 255, line_thickness)

    # Krok 3: Screentone - zoptymalizowany
    screentone = np.ones((h, w), dtype=np.uint8) * 255
    dot_spacing = max(4, int(8 - intensity * 4))
    
    # Użyj downscaled gray do szybkich obliczeń
    scale = max(1, dot_spacing // 3)
    gray_small = cv2.resize(gray, (w // scale, h // scale), interpolation=cv2.INTER_AREA)
    sh, sw = gray_small.shape
    
    for y in range(0, sh, 1):
        for x in range(0, sw, 1):
            px = gray_small[y, x]
            if px < 120:
                darkness = (120 - px) / 120.0
                if darkness > 0.3:
                    fx, fy = x * scale, y * scale
                    radius = max(1, int(dot_spacing * 0.15 * darkness))
                    cv2.circle(screentone, (fx, fy), radius, 0, -1)

    # Krok 4: Połącz
    lines_inv = 255 - line_canvas
    result_arr = np.minimum(lines_inv, screentone)
    result = Image.fromarray(result_arr, mode="L")
    return Image.merge("RGB", (result, result, result))


def _aesthetic_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    blurred = Image.fromarray(smooth, "RGB")
    color_soft = ImageEnhance.Color(blurred).enhance(1.2)
    brightness = ImageEnhance.Brightness(color_soft).enhance(1.1)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 50, 160)
    edges_img = Image.fromarray(edges, "L")
    edges_soft = edges_img.filter(ImageFilter.GaussianBlur(radius=2.0))
    edges_inv = ImageOps.invert(edges_soft)
    edge_rgb = edges_inv.convert("RGB")
    result = Image.blend(brightness, edge_rgb, 0.08)
    result = ImageEnhance.Contrast(result).enhance(0.9)
    pastel_bg = Image.new("RGB", img_rgb.size, (252, 245, 250))
    rng = random.Random(99)
    data = list(pastel_bg.getdata())
    data = [(min(255, r + rng.randint(-5, 5)), min(255, g + rng.randint(-3, 8)), min(255, b + rng.randint(-5, 5))) for r, g, b in data]
    pastel_bg.putdata(data)
    result = Image.blend(pastel_bg, result, 0.8)
    w, h = img_rgb.size
    sparkle = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(sparkle)
    rng2 = random.Random(123)
    for _ in range(int(20 + intensity * 30)):
        x = rng2.randint(0, w - 1)
        y = rng2.randint(0, h - 1)
        px = gray[y, x]
        if px > 180:
            alpha = rng2.randint(80, 180)
            size = rng2.randint(1, 3)
            d.ellipse((x - size, y - size, x + size, y + size), fill=(255, 255, 255, alpha))
    result_rgba = result.convert("RGBA")
    result_rgba = Image.alpha_composite(result_rgba, sparkle)
    return result_rgba.convert("RGB")


def _graffiti_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    blurred = Image.fromarray(smooth, "RGB")
    color_boost = ImageEnhance.Color(blurred).enhance(1.8 + intensity * 0.6)
    contrast = ImageEnhance.Contrast(color_boost).enhance(1.4)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 30, 100)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    result = ImageChops.multiply(contrast, edges_inv.convert("RGB"))
    result = ImageEnhance.Contrast(result).enhance(1.3)
    w, h = img_rgb.size
    concrete = Image.new("RGB", (w, h), (80, 80, 85))
    rng = random.Random(42)
    data = list(concrete.getdata())
    data = [(min(255, max(0, r + rng.randint(-20, 20))), min(255, max(0, g + rng.randint(-18, 18))), min(255, max(0, b + rng.randint(-15, 15)))) for r, g, b in data]
    concrete.putdata(data)
    result = Image.blend(concrete, result, 0.7 + intensity * 0.2)
    return result


def _ink_wash_sketch(img_rgb, intensity):
    arr = np.array(img_rgb)
    d = int(5 + intensity * 5)
    smooth = cv2.bilateralFilter(arr, d, 50, 50)
    gray = cv2.cvtColor(smooth, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    wash = Image.fromarray(gray, "L")
    wash = wash.filter(ImageFilter.GaussianBlur(radius=5.0 + intensity * 8.0))
    wash = ImageEnhance.Brightness(wash).enhance(1.2)
    edges = cv2.Canny(gray, 30, 120)
    edges_img = Image.fromarray(edges, "L")
    edges_inv = ImageOps.invert(edges_img)
    edges_blur = edges_inv.filter(ImageFilter.GaussianBlur(radius=1.5))
    ink_dark = edges_blur.point(lambda p: int(p * 0.6))
    wash_arr = np.array(wash)
    ink_arr = np.array(ink_dark)
    combined = np.minimum(wash_arr, ink_arr)
    result = Image.fromarray(combined, "L")
    rice_paper = Image.new("RGB", img_rgb.size, (248, 242, 232))
    result_rgb = Image.merge("RGB", (result, result, result))
    result_rgb = ImageChops.multiply(rice_paper, result_rgb)
    result_rgb = ImageEnhance.Contrast(result_rgb).enhance(1.1 + intensity * 0.3)
    return result_rgb


_STYLE_FUNCS = {
    "pencil_sketch":       _pencil_sketch,
    "charcoal_sketch":     _charcoal_sketch,
    "ink_sketch":          _ink_sketch,
    "colored_pencil":      _colored_pencil,
    "watercolor_sketch":   _watercolor_sketch,
    "ballpoint_pen":       _ballpoint_pen,
    "pastel_sketch":       _pastel_sketch,
    "fine_detail":         _fine_detail,
    "da_vinci_manuscript": _da_vinci_manuscript,
    "bold_sketch":         _bold_sketch,
    "minimalist_line":     _minimalist_line,
    "figure_quick":        _figure_quick,
    "cartoon_sketch":      _cartoon_sketch,
    "concept_sketch":      _concept_sketch,
    "manga_sketch":        None,  # Special handling - needs mask
    "aesthetic_sketch":    _aesthetic_sketch,
    "graffiti_sketch":     _graffiti_sketch,
    "ink_wash_sketch":     _ink_wash_sketch,
}


# ─ Pipeline Step 5+6: Overlay + Postprocessing ─────────────────────────────
def _postprocess(result, style, paper_texture, vignette_strength, sharpen_amount):
    no_paper_styles = {"graffiti_sketch", "aesthetic_sketch"}
    if style not in no_paper_styles:
        if paper_texture:
            w, h = result.size
            texture = Image.new("L", (w, h), 245)
            rng = random.Random(123)
            data = list(texture.getdata())
            data = [min(255, max(0, v + rng.randint(-15, 15))) for v in data]
            texture.putdata(data)
            texture_rgb = Image.merge("RGB", (texture, texture, texture))
            result = ImageChops.multiply(result, texture_rgb)

    if vignette_strength > 0:
        w, h = result.size
        cx, cy = w / 2, h / 2
        max_dist = math.hypot(cx, cy)
        vignette = Image.new("L", (w, h), 255)
        for y in range(h):
            for x in range(w):
                dist = math.hypot(x - cx, y - cy) / max_dist
                if dist > 0.5:
                    val = int(255 * (1 - (dist - 0.5) * vignette_strength * 2))
                    vignette.putpixel((x, y), max(0, val))
        vignette_rgb = Image.merge("RGB", (vignette, vignette, vignette))
        result = ImageChops.multiply(result, vignette_rgb)

    if sharpen_amount > 0:
        result = result.filter(ImageFilter.UnsharpMask(radius=1.5, percent=int(sharpen_amount * 150), threshold=0))

    return result


# ── METADATA ─────────────────────────────────────────────────────────────────
METADATA = {
    "id": "sketch_embroidery_pipeline",
    "name": "🎨 18 Sketch Styles",
    "description": "18 stylów szkicu: Pencil, Charcoal, Ink, Colored Pencil, Watercolor, Ballpoint Pen, Pastel, Fine Detail, Da Vinci Manuscript, Bold, Minimalist Line, Figure Quick, Cartoon, Concept, Manga, Aesthetic, Graffiti, Ink Wash",
    "version": "2.0.0",
    "icon": "",
    "divider_param": "sketch_style",
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
        "sketch_style": {
            "type": "select",
            "label": "Styl szkicu (18 stylów)",
            "choices": {sid: s["label"] for sid, s in SKETCH_STYLES.items()},
            "default": "pencil_sketch",
        },
        "intensity": {
            "type": "slider",
            "label": "Intensywność stylu",
            "min": 0, "max": 100, "step": 1,
            "default": 60,
        },
        "denoise": {
            "type": "slider",
            "label": "Preprocessing: Denoise",
            "min": 0, "max": 100, "step": 1,
            "default": 20,
        },
        "contrast": {
            "type": "slider",
            "label": "Preprocessing: Kontrast",
            "min": 50, "max": 200, "step": 1,
            "default": 120,
        },
        "brightness": {
            "type": "slider",
            "label": "Preprocessing: Jasność",
            "min": -100, "max": 100, "step": 1,
            "default": 0,
        },
        "edge_method": {
            "type": "select",
            "label": "Edge detection: Metoda",
            "choices": {
                "canny": "Canny (klasyczny)",
                "sobel": "Sobel (gradient)",
                "laplacian": "Laplacian (druga pochodna)",
                "combined": "Canny + Adaptive (najlepszy)",
            },
            "default": "combined",
        },
        "edge_low": {
            "type": "slider",
            "label": "Edge: Low threshold",
            "min": 10, "max": 200, "step": 1,
            "default": 50,
        },
        "edge_high": {
            "type": "slider",
            "label": "Edge: High threshold",
            "min": 50, "max": 300, "step": 1,
            "default": 150,
        },
        "edge_aperture": {
            "type": "select",
            "label": "Edge: Aperture size",
            "choices": {"3": "3 (standard)", "5": "5 (detale)", "7": "7 (maksymalny)"},
            "default": "3",
        },
        "k_clusters": {
            "type": "slider",
            "label": "Segmentacja: Liczba kolorów (K-means)",
            "min": 2, "max": 32, "step": 1,
            "default": 8,
        },
        "paper_texture": {
            "type": "checkbox",
            "label": "Postprocessing: Tekstura papieru",
            "default": "true",
        },
        "vignette": {
            "type": "slider",
            "label": "Postprocessing: Vignette",
            "min": 0, "max": 100, "step": 1,
            "default": 20,
        },
        "sharpen": {
            "type": "slider",
            "label": "Postprocessing: Sharpen",
            "min": 0, "max": 100, "step": 1,
            "default": 30,
        },
        "colorize_regions": {
            "type": "checkbox",
            "label": "Koloruj obszary (paleta K-means)",
            "default": "false",
        },
        "color_palette_size": {
            "type": "select",
            "label": "Rozmiar palety kolorów",
            "choices": {
                "8": "8 kolorów",
                "16": "16 kolorów",
                "32": "32 kolory",
                "64": "64 kolory",
                "128": "128 kolorów",
                "256": "256 kolorów",
            },
            "default": "16",
        },
        "use_fg_mask": {
            "type": "checkbox",
            "label": "Użyj maski FG (separacja postaci)",
            "default": "false",
        },
        "bg_replace": {
            "type": "select",
            "label": "Tło po usunięciu",
            "choices": {
                "original": "Oryginalne",
                "white": "Białe",
                "black": "Czarne",
                "transparent": "Przezroczyste",
            },
            "default": "white",
        },
    },
}


# -- Plugin interface --
_COLOR_STYLES = {
    "colored_pencil", "watercolor_sketch", "pastel_sketch",
    "aesthetic_sketch", "graffiti_sketch", "cartoon_sketch",
}


def process(image_bytes: bytes, options: dict, progress_callback=None) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", METADATA["options"]["model"]["default"])
    sketch_style = options.get("sketch_style", METADATA["options"]["sketch_style"]["default"])
    intensity = float(options.get("intensity", 60)) / 100.0
    denoise = float(options.get("denoise", 20)) / 100.0
    contrast = float(options.get("contrast", 120)) / 100.0
    brightness = float(options.get("brightness", 0))
    edge_method = options.get("edge_method", METADATA["options"]["edge_method"]["default"])
    edge_low = int(options.get("edge_low", 50))
    edge_high = int(options.get("edge_high", 150))
    edge_aperture = int(options.get("edge_aperture", 3))
    k_clusters = int(options.get("k_clusters", 8))
    paper_texture = _to_bool(options.get("paper_texture", "true"))
    vignette = float(options.get("vignette", 20)) / 100.0
    sharpen = float(options.get("sharpen", 30)) / 100.0
    colorize_regions = _to_bool(options.get("colorize_regions", "false"))
    color_palette_size = int(options.get("color_palette_size", 16))
    use_fg_mask = _to_bool(options.get("use_fg_mask", "false"))
    bg_replace = options.get("bg_replace", METADATA["options"]["bg_replace"]["default"])

    def _progress(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    _progress(0, "Ładowanie obrazu...")

    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    src_rgb = src.convert("RGB")
    size = src.size

    # Zawsze generuj maskę dla manga_sketch
    fg_mask = None
    if sketch_style == "manga_sketch":
        _progress(5, "Generowanie maski postaci...")
        session = _get_session(model_name)
        fg_mask = remove(src, session=session).convert("RGBA").getchannel("A")
        fg_mask = fg_mask.filter(ImageFilter.GaussianBlur(radius=1.5))

    _progress(15, "Preprocessing...")
    preprocessed = _preprocess(src_rgb, denoise, contrast, brightness)
    
    _progress(25, "Wykrywanie krawędzi...")
    edges = _edge_detection(preprocessed, edge_method, edge_low, edge_high, edge_aperture)
    
    _progress(35, "Segmentacja kolorów...")
    segmented = _color_segmentation(preprocessed, k_clusters, 30, 1.0)

    # Special handling for manga_sketch - pass mask
    if sketch_style == "manga_sketch":
        _progress(45, "Stylizacja Manga...")
        result = _manga_sketch(preprocessed, intensity, fg_mask=fg_mask)
    else:
        _progress(45, f"Stylizacja: {sketch_style}...")
        style_func = _STYLE_FUNCS.get(sketch_style, _pencil_sketch)
        result = style_func(preprocessed, intensity)

    # Kolorowanie obszarów - jeśli włączone
    if colorize_regions:
        _progress(70, "Kolorowanie obszarów...")
        # Użyj palety z opcji, nie z k_clusters
        palette_clusters = color_palette_size
        segmented_colors = _color_segmentation(preprocessed, palette_clusters, 30, 1.0)
        
        # Konwertuj wynik do tablicy
        result_arr = np.array(result.convert("L"), dtype=np.float32)
        segmented_arr = np.array(segmented_colors, dtype=np.float32)
        
        # Im ciemniejszy piksel w szkicu (linia), tym mniej koloru
        # Linie (ciemne) = mało koloru, obszary (jasne) = dużo koloru
        line_mask = 1.0 - (result_arr / 255.0)  # 1 = linia, 0 = tło
        color_strength = 0.7  # Siła kolorowania
        
        # Mieszaj: kolor * (1 - line_mask * color_strength)
        blended = segmented_arr * (1.0 - line_mask[..., np.newaxis] * color_strength)
        
        # Dodaj czarne linie z powrotem
        line_color = np.array([20, 20, 20], dtype=np.float32)
        final = blended * (1.0 - line_mask[..., np.newaxis]) + line_color * line_mask[..., np.newaxis]
        
        result = Image.fromarray(np.clip(final, 0, 255).astype(np.uint8), mode="RGB")

    _progress(80, "Postprocessing...")
    result = _postprocess(result, sketch_style, paper_texture, vignette, sharpen)

    _progress(90, "Łączenie z maską...")
    if use_fg_mask:
        if fg_mask is None:
            session = _get_session(model_name)
            fg_mask = remove(src, session=session).convert("RGBA").getchannel("A")
            fg_mask = fg_mask.filter(ImageFilter.GaussianBlur(radius=1.5))

        if bg_replace == "white":
            bg = Image.new("RGB", size, (255, 255, 255))
        elif bg_replace == "black":
            bg = Image.new("RGB", size, (0, 0, 0))
        elif bg_replace == "transparent":
            bg = Image.new("RGBA", size, (0, 0, 0, 0))
            out = Image.new("RGBA", size, (0, 0, 0, 0))
            result_rgba = result.convert("RGBA")
            out = Image.alpha_composite(bg, result_rgba)
            buf = io.BytesIO()
            out.save(buf, format="PNG")
            return buf.getvalue()
        else:
            bg = src_rgb.copy()

        out = bg.convert("RGBA")
        result_rgba = result.convert("RGBA")
        out.paste(result_rgba, mask=fg_mask)
    else:
        out = result.convert("RGBA")

    _progress(100, "Gotowe!")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
