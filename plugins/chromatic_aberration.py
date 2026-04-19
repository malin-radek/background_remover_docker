"""
Plugin: Chromatic Aberration + Glitch
Efekt aberracji chromatycznej (jak tanie soczewki/holografia) z opsjonalnym efektem glitch.
Rozdziela kanały RGB i przesuwa je, tworząc halo i efekt 3D-ish.
Używany w: motion graphics, cyberpunk aesthetics, VFX, okładki albumów.
"""

try:
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

METADATA = {
    "id": "chromatic_aberration",
    "name": "🌈 Chromatic Aberration",
    "description": "Efekt aberracji chromatycznej + glitch - jak przez złą soczewkę lub hologram",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🔴",
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
        "intensity": {
            "type": "select",
            "label": "Intensywność aberracji",
            "choices": {
                "1": "Subtelna (1px)",
                "3": "Umiarkowana (3px)",
                "6": "Mocna (6px)",
                "12": "Ekstremalna (12px)",
                "20": "Max - psychodeliczna (20px)",
            },
            "default": "6",
        },
        "mode": {
            "type": "select",
            "label": "Tryb efektu",
            "choices": {
                "radial": "Radialny (od środka)",
                "horizontal": "Poziomy (lewo/prawo)",
                "diagonal": "Diagonalny",
                "zoom": "Zoom Blur (od środka)",
            },
            "default": "radial",
        },
        "glitch": {
            "type": "select",
            "label": "Efekt glitch",
            "choices": {
                "none": "Brak",
                "mild": "Łagodny (kilka linii)",
                "heavy": "Mocny (wiele bloków)",
            },
            "default": "mild",
        },
        "animation": {
            "type": "select",
            "label": "Animacja",
            "choices": {
                "no": "Brak (statyczne)",
                "flicker": "Migotanie aberracji",
                "glitch_anim": "Animowany glitch",
            },
            "default": "flicker",
        },
        "speed": {
            "type": "select",
            "label": "Szybkość animacji",
            "choices": {
                "50": "Szybka (50ms)",
                "80": "Normalna (80ms)",
                "120": "Wolna (120ms)",
            },
            "default": "80",
        },
        "background": {
            "type": "select",
            "label": "Tło",
            "choices": {
                "black": "Czarne",
                "white": "Białe",
                "original": "Oryginalne",
                "gray": "Szare",
            },
            "default": "black",
        },
    },
}

import io
import math
import threading
import random
from PIL import Image, ImageFilter, ImageChops
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


def _shift_channel(channel: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Przesuń kanał o (dx, dy) pikseli z interpolacją."""
    from scipy.ndimage import shift
    return np.clip(shift(channel.astype(np.float32), (dy, dx), mode='constant', cval=0), 0, 255).astype(np.uint8)


def _apply_chromatic_aberration(
    fg_rgba: np.ndarray,
    intensity: int,
    mode: str,
) -> np.ndarray:
    """
    Rozdziel kanały RGB i przesuń je w różnych kierunkach.
    Zwraca RGBA z efektem.
    """
    H, W = fg_rgba.shape[:2]
    cx, cy = W / 2.0, H / 2.0

    r = fg_rgba[:, :, 0].astype(np.float32)
    g = fg_rgba[:, :, 1].astype(np.float32)
    b = fg_rgba[:, :, 2].astype(np.float32)
    a = fg_rgba[:, :, 3].astype(np.float32)

    if mode == "horizontal":
        r_shift = (-intensity, 0)
        b_shift = (intensity, 0)
        g_shift = (0, 0)
    elif mode == "diagonal":
        r_shift = (-intensity, -intensity // 2)
        b_shift = (intensity, intensity // 2)
        g_shift = (0, 0)
    elif mode == "zoom":
        # Zoom blur: każdy kanał skalowany o różną ilość
        def zoom_channel(ch, zoom_factor):
            from scipy.ndimage import zoom as sp_zoom
            zoomed = sp_zoom(ch, zoom_factor, mode='constant', cval=0)
            zh, zw = zoomed.shape
            # Przytnij/dopełnij do oryginalnego rozmiaru
            result = np.zeros((H, W), dtype=np.float32)
            if zoom_factor > 1.0:
                oy = (zh - H) // 2
                ox = (zw - W) // 2
                result = zoomed[oy:oy+H, ox:ox+W]
            else:
                oy = (H - zh) // 2
                ox = (W - zw) // 2
                result[oy:oy+zh, ox:ox+zw] = zoomed
            return np.clip(result, 0, 255)
        zoom_r = 1.0 + intensity / 300.0
        zoom_b = 1.0 - intensity / 400.0
        r = zoom_channel(r, zoom_r)
        b = zoom_channel(b, max(0.5, zoom_b))
        r_shift = g_shift = b_shift = (0, 0)
    else:  # radial - od środka
        r_shift = (-intensity, 0)
        b_shift = (intensity, 0)
        g_shift = (0, int(intensity * 0.3))

    if mode != "zoom":
        from scipy.ndimage import shift as sp_shift
        r = sp_shift(r, (r_shift[1], r_shift[0]), mode='constant', cval=0)
        g = sp_shift(g, (g_shift[1], g_shift[0]), mode='constant', cval=0)
        b = sp_shift(b, (b_shift[1], b_shift[0]), mode='constant', cval=0)

    result = np.zeros((H, W, 4), dtype=np.uint8)
    result[:, :, 0] = np.clip(r, 0, 255).astype(np.uint8)
    result[:, :, 1] = np.clip(g, 0, 255).astype(np.uint8)
    result[:, :, 2] = np.clip(b, 0, 255).astype(np.uint8)
    result[:, :, 3] = a.astype(np.uint8)
    return result


def _apply_glitch(img_array: np.ndarray, seed: int, strength: str) -> np.ndarray:
    """
    Dodaje efekt glitch: przesunięte bloki wierszy.
    """
    rng = np.random.default_rng(seed)
    H, W = img_array.shape[:2]
    result = img_array.copy()

    num_slices = 4 if strength == "mild" else 14
    for _ in range(num_slices):
        y0 = rng.integers(0, H - 1)
        h  = rng.integers(1, max(2, H // 20))
        y1 = min(y0 + h, H)
        dx = rng.integers(-W // 8, W // 8)
        if dx == 0:
            continue
        slice_data = result[y0:y1, :, :].copy()
        # Przesuń wycinek poziomo z zawijaniem
        result[y0:y1, :, :] = np.roll(slice_data, dx, axis=1)

    # Losowe bloki z kolorem
    num_color_blocks = 1 if strength == "mild" else 4
    for _ in range(num_color_blocks):
        y0 = rng.integers(0, H - 2)
        h  = rng.integers(1, max(2, H // 30))
        y1 = min(y0 + h, H)
        glitch_color = rng.choice([
            [255, 0, 100, 180],
            [0, 255, 200, 180],
            [200, 0, 255, 180],
        ])
        result[y0:y1, :, :3] = np.clip(
            result[y0:y1, :, :3].astype(int) + (np.array(glitch_color[:3]) * 0.4).astype(int),
            0, 255
        )

    return result


def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", "u2net")
    intensity  = int(options.get("intensity", 6))
    mode       = options.get("mode", "radial")
    glitch     = options.get("glitch", "mild")
    animation  = options.get("animation", "flicker")
    speed      = int(options.get("speed", 80))
    background = options.get("background", "black")

    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    session      = _get_session(model_name)
    img_removed  = remove(img_original.convert("RGBA"), session=session).convert("RGBA")
    _, _, _, alpha_mask = img_removed.split()

    bg_map = {"black": (0,0,0), "white": (255,255,255), "gray": (128,128,128)}

    def make_frame(frame_idx: int, total: int) -> Image.Image:
        # Intensywność fluktuuje per-klatka
        if animation == "flicker":
            t = math.sin((frame_idx / total) * 2 * math.pi)
            cur_intensity = max(1, int(intensity * (0.6 + 0.4 * abs(t))))
        else:
            cur_intensity = intensity

        fg_arr = np.array(img_removed, dtype=np.uint8)
        ca_arr = _apply_chromatic_aberration(fg_arr, cur_intensity, mode)

        if glitch != "none":
            glitch_seed = frame_idx * 77 + 13 if animation == "glitch_anim" else 42
            ca_arr = _apply_glitch(ca_arr, glitch_seed, glitch)

        ca_img = Image.fromarray(ca_arr, "RGBA")

        if background == "original":
            bg = prepare_background(img_original.size, "original", img_original, alpha_mask)
        else:
            color = bg_map.get(background, (0, 0, 0))
            bg = Image.new("RGB", img_original.size, color)

        bg.paste(ca_img, mask=ca_img.split()[3])
        return bg

    if animation == "no":
        frame = make_frame(0, 1)
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        return buf.getvalue()

    num_frames = 10
    frames = [make_frame(i, num_frames) for i in range(num_frames)]
    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        duration=speed, loop=0, optimize=False,
    )
    return buf.getvalue()
