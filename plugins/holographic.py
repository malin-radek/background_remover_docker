"""
Plugin: Holographic Foil
Efekt holograficznej folii - jak naklejki holograficzne, karty kolekcjonerskie (Pokemon!),
bilety koncertowe. Tęczowy metaliczny połysk który animuje się wraz z "obrotem".
Profesjonalnie używany w: packaging design, security printing, collectibles.

Technika:
- Mapa gradientu z noise'em pokrywa sylwetkę
- Gradient mapuje się na hue (tęcza) z saturacją i lightness metalicznego połysku
- Animacja: hue rotate + reflection highlight sweep
- Specular highlights: jasne refleksy w różnych miejscach per klatka
"""

METADATA = {
    "id": "holographic",
    "name": "✨ Holographic Foil",
    "description": "Efekt holograficznej folii - jak karty Pokemon, bilety, naklejki",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🌊",
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
        "foil_pattern": {
            "type": "select",
            "label": "Wzór folii",
            "choices": {
                "diagonal": "Diagonalny (klasyczny)",
                "radial":   "Radialny (od środka)",
                "wave":     "Falowy",
                "noise":    "Noise (losowy)",
            },
            "default": "diagonal",
        },
        "intensity": {
            "type": "select",
            "label": "Intensywność efektu",
            "choices": {
                "30": "Subtelny (30%)",
                "60": "Normalny (60%)",
                "85": "Mocny (85%)",
                "100": "Maksymalny",
            },
            "default": "60",
        },
        "specular": {
            "type": "select",
            "label": "Połysk specular",
            "choices": {
                "none":   "Brak",
                "mild":   "Delikatny",
                "strong": "Mocny",
            },
            "default": "mild",
        },
        "animation": {
            "type": "select",
            "label": "Animacja",
            "choices": {
                "no":     "Brak (statyczne)",
                "rotate": "Obrót widoku (klasyczny)",
                "sweep":  "Sweep (przesuwający się blask)",
            },
            "default": "rotate",
        },
        "speed": {
            "type": "select",
            "label": "Szybkość animacji",
            "choices": {
                "60":  "Szybka",
                "100": "Normalna",
                "150": "Wolna",
            },
            "default": "100",
        },
        "background": {
            "type": "select",
            "label": "Tło",
            "choices": {
                "black":    "Czarne",
                "white":    "Białe",
                "original": "Oryginalne",
                "dark":     "Ciemnoszare",
            },
            "default": "black",
        },
    },
}

import io
import math
import colorsys
import threading
from PIL import Image, ImageFilter
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


def _make_foil_gradient(W: int, H: int, pattern: str) -> np.ndarray:
    """
    Stwórz mapę bazową [0, 1] używaną do mapowania hue.
    Różne wzory: diagonal, radial, wave, noise.
    """
    y_n = np.linspace(0, 1, H)
    x_n = np.linspace(0, 1, W)
    xv, yv = np.meshgrid(x_n, y_n)

    if pattern == "diagonal":
        base = (xv + yv) / 2.0
    elif pattern == "radial":
        base = np.sqrt((xv - 0.5) ** 2 + (yv - 0.5) ** 2)
        base = base / base.max()
    elif pattern == "wave":
        base = (np.sin(xv * np.pi * 6) + np.cos(yv * np.pi * 4)) / 2.0
        base = (base + 1.0) / 2.0
    else:  # noise: kombinacja sinusów na różnych skalach
        n = (
            np.sin(xv * 17.3 + yv * 5.7) * 0.4 +
            np.cos(xv * 8.1 - yv * 12.3) * 0.3 +
            np.sin((xv + yv) * 23.7) * 0.3
        )
        base = (n + 1.0) / 2.0

    return np.clip(base, 0.0, 1.0)


def _holo_frame(
    fg_rgba: np.ndarray,
    alpha_array: np.ndarray,
    base_gradient: np.ndarray,
    frame_idx: int,
    num_frames: int,
    pattern: str,
    intensity: int,
    specular: str,
    animation: str,
) -> np.ndarray:
    """
    Stwórz jedną klatkę efektu holograficznego.
    """
    H, W = alpha_array.shape
    progress = frame_idx / max(num_frames - 1, 1)

    # ── Hue rotation per klatka ───────────────────────────────────────────
    if animation == "rotate":
        hue_offset = progress  # pełny obrót przez wszystkie klatki
    elif animation == "sweep":
        # Sweep: jasna linia przesuwa się przez obraz
        hue_offset = progress * 0.3  # mniejszy obrót
    else:
        hue_offset = 0.0

    # ── Gradient + hue offset → tęczowy kolor per piksel ─────────────────
    hue_map = (base_gradient + hue_offset) % 1.0

    # Saturation i Lightness: metaliczny połysk
    # Wysokie S, L ok 0.55-0.70
    sat = 0.85
    lig_base = 0.60

    # Skonwertuj HSL → RGB per piksel
    H_flat = hue_map.ravel()
    rgb_flat = np.array([colorsys.hls_to_rgb(h, lig_base, sat) for h in H_flat])
    foil_rgb = (rgb_flat.reshape(H, W, 3) * 255).astype(np.uint8)

    # ── Specular highlights ───────────────────────────────────────────────
    if specular != "none":
        # Mapa specular: jasna strefa przesuwa się co klatke
        spec_x = 0.2 + 0.6 * math.sin(progress * 2 * math.pi)
        spec_y = 0.3 + 0.4 * math.cos(progress * 2 * math.pi)
        xv = np.linspace(0, 1, W)
        yv = np.linspace(0, 1, H)
        xxv, yyv = np.meshgrid(xv, yv)
        dist_spec = np.sqrt((xxv - spec_x) ** 2 + (yyv - spec_y) ** 2)
        spec_size = 0.25 if specular == "mild" else 0.15
        spec_intensity = 0.5 if specular == "mild" else 0.8
        spec_map = np.clip(1.0 - dist_spec / spec_size, 0, 1) * spec_intensity
        # Dodaj specular do RGB (rozjaśnij w stronę białego)
        spec_3ch = spec_map[:, :, np.newaxis]
        foil_rgb = np.clip(foil_rgb.astype(np.float32) + spec_3ch * 255, 0, 255).astype(np.uint8)

    # ── Blenduj foil z oryginalnym kolorem ───────────────────────────────
    blend = intensity / 100.0
    fg_rgb = fg_rgba[:, :, :3].astype(np.float32)
    foil_f = foil_rgb.astype(np.float32)
    blended = (fg_rgb * (1 - blend) + foil_f * blend).astype(np.uint8)

    # ── Sweep: jasna linia skaluje się po obrazie ─────────────────────────
    if animation == "sweep":
        sweep_pos = (progress + 0.0) % 1.0
        # Gradient skośny od lewej-góry do prawej-dołu
        xv = np.linspace(0, 1, W)
        yv = np.linspace(0, 1, H)
        xxv, yyv = np.meshgrid(xv, yv)
        diag = (xxv + yyv) / 2.0
        sweep_dist = np.abs(diag - sweep_pos)
        sweep_width = 0.15
        sweep_alpha = np.clip(1.0 - sweep_dist / sweep_width, 0, 1) * 0.6
        sw3 = sweep_alpha[:, :, np.newaxis]
        blended = np.clip(blended.astype(np.float32) + sw3 * 255, 0, 255).astype(np.uint8)

    # ── Zastosuj alpha maską ──────────────────────────────────────────────
    result = np.zeros((H, W, 4), dtype=np.uint8)
    result[:, :, :3] = blended
    result[:, :, 3] = alpha_array
    return result


def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name  = options.get("model", "u2net")
    pattern     = options.get("foil_pattern", "diagonal")
    intensity   = int(options.get("intensity", 60))
    specular    = options.get("specular", "mild")
    animation   = options.get("animation", "rotate")
    speed       = int(options.get("speed", 100))
    background  = options.get("background", "black")

    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    W, H = img_original.size
    session      = _get_session(model_name)
    img_removed  = remove(img_original.convert("RGBA"), session=session).convert("RGBA")
    _, _, _, alpha_mask_img = img_removed.split()
    alpha_array  = np.array(alpha_mask_img, dtype=np.uint8)
    fg_rgba      = np.array(img_removed, dtype=np.uint8)

    bg_map = {
        "black": (0, 0, 0),
        "white": (255, 255, 255),
        "dark":  (30, 30, 30),
    }

    def make_bg():
        if background == "original":
            return prepare_background(img_original.size, "original", img_original, alpha_mask_img).convert("RGBA")
        return Image.new("RGBA", (W, H), (*bg_map.get(background, (0,0,0)), 255))

    base_gradient = _make_foil_gradient(W, H, pattern)

    if animation == "no":
        frame_arr = _holo_frame(fg_rgba, alpha_array, base_gradient, 0, 1, pattern, intensity, specular, animation)
        frame_img  = Image.fromarray(frame_arr, "RGBA")
        bg = make_bg()
        bg = Image.alpha_composite(bg, frame_img)
        buf = io.BytesIO()
        bg.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()

    num_frames = 14
    frames = []
    for fi in range(num_frames):
        frame_arr = _holo_frame(fg_rgba, alpha_array, base_gradient, fi, num_frames, pattern, intensity, specular, animation)
        frame_img  = Image.fromarray(frame_arr, "RGBA")
        bg = make_bg()
        composed = Image.alpha_composite(bg, frame_img).convert("RGB")
        frames.append(composed)

    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        duration=speed, loop=0, optimize=False,
    )
    return buf.getvalue()
