"""
Plugin: AGIF - Zoom
Usuwa tło i generuje animowany GIF z efektem zoomu na obiekcie.
"""

METADATA = {
    "id": "agif_zoom",
    "name": "🎬 AGIF Zoom",
    "description": "Animowany GIF - usuwa tło i generuje efekt zoomu in/out",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🔎",
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
        "frames": {
            "type": "select",
            "label": "Liczba klatek",
            "choices": {
                "4": "4 klatki",
                "8": "8 klatek",
                "16": "16 klatek",
                "20": "20 klatek",
                "24": "24 klatki",
                "50": "50 klatek",
                "75": "75 klatek",
                "100": "100 klatek",
            },
            "default": "12",
        },
        "zoom_range": {
            "type": "select",
            "label": "Zakres zoomu",
            "choices": {
                "0.2": "100% - 120% (subtleny)",
                "0.4": "100% - 140% (średni)",
                "0.6": "100% - 160% (dynamiczny)",
            },
            "default": "0.4",
        },
        "speed": {
            "type": "select",
            "label": "Szybkość (ms na klatkę)",
            "choices": {
                "50": "Szybka (50ms)",
                "100": "Normalna (100ms)",
                "150": "Wolna (150ms)",
            },
            "default": "100",
        },
        "background": {
            "type": "select",
            "label": "Tło",
            "choices": {
                "original": "Oryginalne tło",
                "white": "Białe",
                "gray": "Szare",
                "transparent": "Przezroczyste (checkerboard)",
            },
            "default": "original",
        },
        "edge_feather": {
            "type": "select",
            "label": "Alpha-blending na krawędziach",
            "choices": {
                "0": "Brak (ostre)",
                "2": "Delikatne (2px)",
                "5": "Średnie (5px)",
                "10": "Miękkie (10px)",
                "15": "Bardzo miękkie (15px)",
            },
            "default": "5",
        },
    },
}

import io
import threading
from PIL import Image
from plugin_utils import prepare_background, feather_alpha_mask

try:
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_sessions: dict = {}
_lock = threading.Lock()


def is_available() -> bool:
    return _AVAILABLE


def _get_session(model_name: str):
    with _lock:
        if model_name not in _sessions:
            _sessions[model_name] = new_session(model_name)
        return _sessions[model_name]


def process(image_bytes: bytes, options: dict) -> bytes:
    """
    Generuje animowany GIF z efektem zoomu.
    """
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", METADATA["options"]["model"]["default"])
    num_frames = int(options.get("frames", METADATA["options"]["frames"]["default"]))
    zoom_range = float(options.get("zoom_range", METADATA["options"]["zoom_range"]["default"]))
    frame_duration = int(options.get("speed", METADATA["options"]["speed"]["default"]))
    background = options.get("background", METADATA["options"]["background"]["default"])
    edge_feather = int(options.get("edge_feather", METADATA["options"]["edge_feather"]["default"]))

    # Wczytaj obraz i usuń tło
    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_original_rgba = img_original.convert("RGBA")
    session = _get_session(model_name)
    img_removed = remove(img_original_rgba, session=session)
    if img_removed.mode != "RGBA":
        img_removed = img_removed.convert("RGBA")

    # Rozsplituj kanały
    r, g, b, a = img_removed.split()
    a_base = feather_alpha_mask(a, edge_feather)

    original_size = img_original.size

    # Przygotuj tło RAZ - to jest kosztowne (inpaint)!
    bg = prepare_background(original_size, background, img_original, a_base)

    # Generuj klatki z zoomem
    frames = []
    for i in range(num_frames):
        progress = i / (num_frames - 1) if num_frames > 1 else 0
        # Zoom od 1.0 (100%) do 1.0+zoom_range
        zoom = 1.0 + zoom_range * abs(((progress * 2 - 1) ** 2) - 1)
        
        # Oblicz nową wielkość
        new_w = int(original_size[0] * zoom)
        new_h = int(original_size[1] * zoom)
        
        # Resize kanały
        r_resized = r.resize((new_w, new_h), Image.LANCZOS)
        g_resized = g.resize((new_w, new_h), Image.LANCZOS)
        b_resized = b.resize((new_w, new_h), Image.LANCZOS)
        a_resized = a_base.resize((new_w, new_h), Image.LANCZOS)
        
        # Stwórz klatkę z centrowaniem
        frame = Image.new("RGBA", original_size, (0, 0, 0, 0))
        offset_x = (original_size[0] - new_w) // 2
        offset_y = (original_size[1] - new_h) // 2
        
        # Wklej każdy kanał
        for y in range(new_h):
            for x in range(new_w):
                px_x = offset_x + x
                px_y = offset_y + y
                if 0 <= px_x < original_size[0] and 0 <= px_y < original_size[1]:
                    r_val = r_resized.getpixel((x, y))
                    g_val = g_resized.getpixel((x, y))
                    b_val = b_resized.getpixel((x, y))
                    a_val = a_resized.getpixel((x, y))
                    frame.putpixel((px_x, px_y), (r_val, g_val, b_val, a_val))
        
        # Nałóż frame z alpha na tło
        bg_frame = bg.copy()
        _, _, _, alpha_channel = frame.split()
        bg_frame.paste(frame, mask=alpha_channel)
        frames.append(bg_frame)

    # Zapisz jako AGIF
    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,
        loop=0,
        optimize=False,
    )
    return buf.getvalue()
