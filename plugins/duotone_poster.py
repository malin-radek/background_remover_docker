"""
Plugin: Duotone Poster
Efekt duotone jak w druku sitodrukowym / Spotify-style.
Mapuje luminancję na gradient między dwoma kolorami.
Opcjonalnie: efekt halftone (rastrowanie jak prawdziwy druk), grain filmowy.
Używany w: plakaty, okładki albumów, branding, editorial design.
"""

METADATA = {
    "id": "duotone_poster",
    "name": "🎨 Duotone Poster",
    "description": "Efekt duotone / sitodruk - jak Spotify, plakaty, editorial design",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🖼️",
    "options": {
        "model": {
            "type": "select",
            "label": "Model AI do ekstrakcji",
            "choices": {
                "u2net": "u2net (szybki, domyślny)",
                "birefnet-general": "birefnet-general (najlepsza jakość)",
                "isnet-general-use": "isnet-general-use (wysoka jakość)",
                "u2net_human_seg": "u2net_human_seg (tylko ludzie)",
            },
            "default": "u2net",
        },
        "palette": {
            "type": "select",
            "label": "Paleta kolorów",
            "choices": {
                "spotify":   "Spotify (zielony / czarny)",
                "sunset":    "Sunset (pomarańczowy / fioletowy)",
                "ocean":     "Ocean (niebieski / teal)",
                "fire":      "Ogień (czerwony / żółty)",
                "noir":      "Noir (biały / grafit)",
                "neon_pink": "Neon (różowy / ciemny granat)",
                "custom":    "Custom (zielony / granat)",
            },
            "default": "spotify",
        },
        "contrast": {
            "type": "select",
            "label": "Kontrast",
            "choices": {
                "low":    "Niski (delikatny)",
                "normal": "Normalny",
                "high":   "Wysoki (dramatyczny)",
            },
            "default": "normal",
        },
        "halftone": {
            "type": "select",
            "label": "Efekt halftone (rastrowanie)",
            "choices": {
                "none":   "Brak",
                "fine":   "Drobny (6px)",
                "medium": "Średni (10px)",
                "coarse": "Gruby (16px)",
            },
            "default": "none",
        },
        "grain": {
            "type": "select",
            "label": "Ziarno filmowe",
            "choices": {
                "0":  "Brak",
                "10": "Delikatne",
                "25": "Normalne",
                "40": "Mocne",
            },
            "default": "0",
        },
        "vignette": {
            "type": "select",
            "label": "Winietowanie",
            "choices": {
                "none":   "Brak",
                "mild":   "Delikatne",
                "strong": "Mocne",
            },
            "default": "none",
        },
        "background": {
            "type": "select",
            "label": "Tło (kolor ciemny z palety)",
            "choices": {
                "dark_color": "Ciemny kolor palety",
                "black":      "Czarne",
                "white":      "Białe",
                "original":   "Oryginalne (rozmyte)",
            },
            "default": "dark_color",
        },
    },
}

import io
import threading
from PIL import Image, ImageFilter, ImageDraw
import numpy as np
try:
    from plugin_utils import prepare_background
except ImportError:
    prepare_background = None

try:
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_sessions: dict = {}
_lock = threading.Lock()


def is_available() -> bool:
    """Sprawdź dostępność pluginu."""
    return _AVAILABLE


def _get_session(model_name):
    with _lock:
        if model_name not in _sessions:
            _sessions[model_name] = new_session(model_name)
        return _sessions[model_name]


PALETTES = {
    "spotify":   ((30, 215, 96),    (0, 0, 0)),
    "sunset":    ((255, 100, 30),   (100, 20, 130)),
    "ocean":     ((30, 120, 255),   (0, 180, 180)),
    "fire":      ((220, 50, 20),    (255, 220, 0)),
    "noir":      ((255, 255, 255),  (40, 40, 40)),
    "neon_pink": ((255, 30, 120),   (10, 15, 60)),
    "custom":    ((60, 200, 80),    (20, 30, 90)),
}


def _apply_duotone(
    img_gray: np.ndarray,
    color_shadow: tuple,
    color_highlight: tuple,
    contrast: str,
) -> np.ndarray:
    """
    Mapuj luminancję [0-255] na gradient między color_shadow (ciemny) i color_highlight (jasny).
    """
    lum = img_gray.astype(np.float32) / 255.0

    if contrast == "low":
        lum = np.clip(lum * 0.6 + 0.2, 0, 1)
    elif contrast == "high":
        # S-curve: zwiększ kontrast
        lum = np.clip((lum - 0.5) * 1.5 + 0.5, 0, 1)

    cs = np.array(color_shadow,    dtype=np.float32)
    ch = np.array(color_highlight, dtype=np.float32)

    lum3 = lum[:, :, np.newaxis]
    result = cs * (1.0 - lum3) + ch * lum3
    return np.clip(result, 0, 255).astype(np.uint8)


def _apply_halftone(img_rgb: np.ndarray, dot_size: int) -> np.ndarray:
    """
    Halftone: rastrowanie kropkami (CMYK-style uproszczony).
    Dla każdego 'cela' wielkości dot_size × dot_size:
    - oblicz średnią luminancję
    - narysuj kółko o promieniu proporcjonalnym do luminancji
    Zwraca RGB.
    """
    H, W = img_rgb.shape[:2]
    result = np.zeros_like(img_rgb)

    # Dla uproszczenia: jeden kanał (luminancja) → czarno-biały halftone nałożony na kolor
    lum = (0.299 * img_rgb[:,:,0] + 0.587 * img_rgb[:,:,1] + 0.114 * img_rgb[:,:,2])

    # Kopiuj bazowe kolory
    result = img_rgb.copy()

    half = dot_size // 2
    for y in range(0, H - dot_size, dot_size):
        for x in range(0, W - dot_size, dot_size):
            cell_lum = lum[y:y+dot_size, x:x+dot_size].mean() / 255.0
            radius = cell_lum * half * 0.9
            cy, cx = y + half, x + half
            # Narysuj kółko wokół (cx, cy) z danym promieniem
            y_range = np.arange(max(0, cy - half), min(H, cy + half + 1))
            x_range = np.arange(max(0, cx - half), min(W, cx + half + 1))
            yy, xx = np.meshgrid(y_range, x_range, indexing='ij')
            dist = np.sqrt((yy - cy)**2 + (xx - cx)**2)
            in_dot = dist <= radius
            # W kółku: kolor oryginalny * 1.2 (jaśniej)
            # Poza kółkiem w celi: przyciemnij
            in_y = y_range[:, np.newaxis] - y
            in_x = x_range[np.newaxis, :] - x
            for c in range(3):
                cell_slice = result[y:y+dot_size, x:x+dot_size, c].astype(np.float32)
                cell_slice[in_y, in_x] = np.where(
                    in_dot,
                    np.clip(cell_slice[in_y, in_x] * 1.3, 0, 255),
                    np.clip(cell_slice[in_y, in_x] * 0.3, 0, 255),
                )
                result[y:y+dot_size, x:x+dot_size, c] = cell_slice.astype(np.uint8)

    return result


def _apply_vignette(img_rgb: np.ndarray, strength: str) -> np.ndarray:
    H, W = img_rgb.shape[:2]
    cx, cy = W / 2.0, H / 2.0
    y_n = (np.arange(H) - cy) / cy
    x_n = (np.arange(W) - cx) / cx
    xv, yv = np.meshgrid(x_n, y_n)
    dist = np.sqrt(xv**2 + yv**2)
    factor = 0.7 if strength == "mild" else 1.3
    vignette = np.clip(1.0 - dist * factor, 0, 1)
    result = (img_rgb.astype(np.float32) * vignette[:, :, np.newaxis]).astype(np.uint8)
    return result


def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", "u2net")
    palette    = options.get("palette", "spotify")
    contrast   = options.get("contrast", "normal")
    halftone   = options.get("halftone", "none")
    grain      = int(options.get("grain", 0))
    vignette   = options.get("vignette", "none")
    background = options.get("background", "dark_color")

    color_highlight, color_shadow = PALETTES.get(palette, PALETTES["spotify"])

    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    W, H = img_original.size
    session     = _get_session(model_name)
    img_removed = remove(img_original.convert("RGBA"), session=session).convert("RGBA")
    _, _, _, alpha_mask_img = img_removed.split()

    # Konwertuj foreground do grayscale
    fg_rgb   = np.array(img_removed.convert("RGB"), dtype=np.uint8)
    fg_gray  = np.array(img_removed.convert("L"),   dtype=np.uint8)
    alpha_arr = np.array(alpha_mask_img, dtype=np.uint8)

    # Duotone na postaci
    dt_rgb = _apply_duotone(fg_gray, color_shadow, color_highlight, contrast)

    # Halftone
    halftone_size_map = {"fine": 6, "medium": 10, "coarse": 16}
    if halftone != "none":
        dot = halftone_size_map.get(halftone, 10)
        dt_rgb = _apply_halftone(dt_rgb, dot)

    # Grain
    if grain > 0:
        noise = np.random.randint(-grain, grain + 1, dt_rgb.shape).astype(np.int16)
        dt_rgb = np.clip(dt_rgb.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Złóż z alpha
    dt_rgba = np.zeros((H, W, 4), dtype=np.uint8)
    dt_rgba[:, :, :3] = dt_rgb
    dt_rgba[:, :, 3]  = alpha_arr
    fg_duotone = Image.fromarray(dt_rgba, "RGBA")

    # Przygotuj tło
    if isinstance(background, str) and background.startswith("data:image"):
        bg = prepare_background(img_original.size, background, img_original, alpha_mask_img)
    elif background == "dark_color":
        bg = Image.new("RGB", (W, H), color_shadow)
    elif background == "black":
        bg = Image.new("RGB", (W, H), (0, 0, 0))
    elif background == "white":
        bg = Image.new("RGB", (W, H), (255, 255, 255))
    else:  # original rozmyte
        bg = prepare_background(img_original.size, "original", img_original, alpha_mask_img)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=8))
        # Też duotone na tle
        bg_gray = np.array(bg.convert("L"), dtype=np.uint8)
        bg_rgb = _apply_duotone(bg_gray, color_shadow, color_highlight, contrast)
        bg = Image.fromarray(bg_rgb, "RGB")

    bg_rgba = bg.convert("RGBA")
    composed = Image.alpha_composite(bg_rgba, fg_duotone)
    result_rgb = composed.convert("RGB")
    result_arr = np.array(result_rgb)

    # Winietowanie po złożeniu
    if vignette != "none":
        result_arr = _apply_vignette(result_arr, vignette)

    result_img = Image.fromarray(result_arr, "RGB")
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    return buf.getvalue()
