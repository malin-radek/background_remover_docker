"""
Plugin: Cinematic Drop Shadow + Depth
Profesjonalny efekt cienia z perspektywą 3D - jak w programach do retuszu i motion design.
Cień jest rzutowany z uwzględnieniem kąta światła, rozmycia i głębokości (perspektywy).
Opcjonalny efekt depth-of-field: bokeh blur tła.
Używany w: reklama produktowa, e-commerce, okładki.
"""

METADATA = {
    "id": "depth_shadow",
    "name": "🎭 Cinematic Shadow",
    "description": "Profesjonalny cień 3D + depth-of-field - jak w Photoshop/After Effects",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🌑",
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
        "shadow_angle": {
            "type": "select",
            "label": "Kąt światła",
            "choices": {
                "135": "Lewy górny (135°)",
                "180": "Górny (180°)",
                "225": "Prawy górny (225°)",
                "270": "Prawy (270°)",
                "315": "Prawy dolny (315°)",
                "0":   "Dolny (0°)",
                "45":  "Lewy dolny (45°)",
                "90":  "Lewy (90°)",
            },
            "default": "225",
        },
        "shadow_distance": {
            "type": "select",
            "label": "Odległość cienia",
            "choices": {
                "5":  "Blisko (5%)",
                "10": "Umiarkowanie (10%)",
                "20": "Daleko (20%)",
                "35": "Bardzo daleko (35%)",
            },
            "default": "10",
        },
        "shadow_blur": {
            "type": "select",
            "label": "Rozmycie cienia",
            "choices": {
                "3":  "Ostre (mocne światło)",
                "8":  "Normalne",
                "15": "Miękkie (zachmurzone)",
                "25": "Bardzo miękkie",
            },
            "default": "8",
        },
        "shadow_opacity": {
            "type": "select",
            "label": "Opacity cienia",
            "choices": {
                "50":  "Delikatny (50%)",
                "70":  "Normalny (70%)",
                "90":  "Ciemny (90%)",
                "100": "Pełny (100%)",
            },
            "default": "70",
        },
        "shadow_color": {
            "type": "select",
            "label": "Kolor cienia",
            "choices": {
                "black":  "Czarny (klasyczny)",
                "blue":   "Niebieski (chłodny)",
                "warm":   "Ciepły (brąz)",
                "purple": "Fioletowy (dramatyczny)",
            },
            "default": "black",
        },
        "perspective": {
            "type": "select",
            "label": "Perspektywa cienia",
            "choices": {
                "none":   "Brak (prosty cień)",
                "mild":   "Łagodna (lekki kąt)",
                "strong": "Mocna (leżący na podłodze)",
            },
            "default": "mild",
        },
        "dof_blur": {
            "type": "select",
            "label": "Rozmycie tła (Depth of Field)",
            "choices": {
                "0": "Brak",
                "3": "Delikatne",
                "6": "Umiarkowane",
                "12": "Mocne bokeh",
            },
            "default": "0",
        },
        "background": {
            "type": "select",
            "label": "Tło",
            "choices": {
                "white":       "Białe",
                "light_gray":  "Jasno szare",
                "dark_gray":   "Ciemno szare",
                "black":       "Czarne",
                "original":    "Oryginalne",
            },
            "default": "white",
        },
    },
}

import io
import math
import threading
from PIL import Image, ImageFilter
import numpy as np
try:
    from scipy import ndimage
except ImportError:
    ndimage = None
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


def _make_perspective_shadow(
    alpha_mask: np.ndarray,
    W: int,
    H: int,
    angle_deg: int,
    distance_pct: int,
    blur_radius: int,
    opacity: int,
    shadow_rgb: tuple,
    perspective: str,
) -> Image.Image:
    """
    Stwórz cień z opcjonalną perspektywą (skew/shear transformacja).
    """
    # Offset cienia
    angle_rad = math.radians(angle_deg)
    dist_px   = int((W + H) / 2 * distance_pct / 100)
    dx = int(math.cos(angle_rad) * dist_px)
    dy = int(math.sin(angle_rad) * dist_px)

    # Stwórz warstwę cienia
    shadow_layer = np.zeros((H, W), dtype=np.float32)
    # Przesuń maskę
    shifted = ndimage.shift(alpha_mask.astype(np.float32), (dy, dx), mode='constant', cval=0)
    shadow_layer = np.clip(shifted, 0, 255)

    if perspective != "none":
        # Shear transformacja: dolna część cienia rozciąga się bardziej (perspektywa)
        shear_strength = 0.3 if perspective == "mild" else 0.7
        y_coords = np.linspace(0, 1, H)
        # Dla każdego wiersza przesuń poziomo proporcjonalnie do y
        result = np.zeros((H, W), dtype=np.float32)
        for row_idx in range(H):
            row_shift = int(shear_strength * y_coords[row_idx] * dist_px * 1.5)
            result[row_idx, :] = np.roll(shadow_layer[row_idx, :], row_shift)
        shadow_layer = result

        # Skaluj cień pionowo (dolna część rozciągnięta)
        if perspective == "strong":
            from scipy.ndimage import zoom as sp_zoom
            scale_y = 1.4
            zoomed = sp_zoom(shadow_layer, (scale_y, 1.0), mode='constant', cval=0)
            # Przytnij do oryginalnego rozmiaru (od góry)
            if zoomed.shape[0] > H:
                shadow_layer = zoomed[:H, :W]
            else:
                shadow_layer[:zoomed.shape[0], :zoomed.shape[1]] = zoomed

    # Blur cienia
    shadow_img = Image.fromarray(np.clip(shadow_layer, 0, 255).astype(np.uint8))
    for _ in range(blur_radius // 5 + 1):
        shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(radius=min(blur_radius, 10)))

    # Stwórz RGBA cień
    shadow_alpha = np.array(shadow_img, dtype=np.float32) * (opacity / 255.0)
    shadow_rgba  = np.zeros((H, W, 4), dtype=np.uint8)
    shadow_rgba[:, :, 0] = shadow_rgb[0]
    shadow_rgba[:, :, 1] = shadow_rgb[1]
    shadow_rgba[:, :, 2] = shadow_rgb[2]
    shadow_rgba[:, :, 3] = np.clip(shadow_alpha, 0, 255).astype(np.uint8)

    return Image.fromarray(shadow_rgba, "RGBA")


def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name      = options.get("model",           "u2net")
    angle_deg       = int(options.get("shadow_angle",    225))
    distance_pct    = int(options.get("shadow_distance",  10))
    blur_radius     = int(options.get("shadow_blur",       8))
    opacity         = int(options.get("shadow_opacity",   70))
    shadow_color    = options.get("shadow_color",    "black")
    perspective     = options.get("perspective",      "mild")
    dof_blur        = int(options.get("dof_blur",          0))
    background      = options.get("background",      "white")

    shadow_color_map = {
        "black":  (0, 0, 0),
        "blue":   (30, 50, 120),
        "warm":   (80, 40, 20),
        "purple": (60, 0, 90),
    }
    shadow_rgb = shadow_color_map.get(shadow_color, (0, 0, 0))

    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    W, H = img_original.size
    session      = _get_session(model_name)
    img_removed  = remove(img_original.convert("RGBA"), session=session).convert("RGBA")
    _, _, _, alpha_mask_img = img_removed.split()
    alpha_array  = np.array(alpha_mask_img, dtype=np.uint8)

    # Przygotuj tło
    bg_color_map = {
        "white":      (255, 255, 255),
        "light_gray": (220, 220, 220),
        "dark_gray":  (60, 60, 60),
        "black":      (0, 0, 0),
    }

    if background == "original" or (isinstance(background, str) and background.startswith("data:image")):
        bg = prepare_background(img_original.size, background, img_original, alpha_mask_img)
    else:
        bg_color = bg_color_map.get(background, (255, 255, 255))
        bg = Image.new("RGB", (W, H), bg_color)

    # Depth of Field: rozmyj tło
    if dof_blur > 0:
        bg = bg.filter(ImageFilter.GaussianBlur(radius=dof_blur))

    # Stwórz cień
    shadow_layer = _make_perspective_shadow(
        alpha_array, W, H,
        angle_deg, distance_pct, blur_radius,
        int(opacity * 2.55),  # % → 0-255
        shadow_rgb, perspective,
    )

    # Złóż: tło + cień + postać
    bg_rgba = bg.convert("RGBA")
    bg_rgba = Image.alpha_composite(bg_rgba, shadow_layer)
    bg_rgba.paste(img_removed, mask=img_removed.split()[3])
    result = bg_rgba.convert("RGB")

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()
