"""
Plugin: AGIF - Pulsowanie
Usuwa tło i generuje animowany GIF z pulsującą przezroczystością obiektu.
"""

METADATA = {
    "id": "agif_pulsing",
    "name": "🎬 AGIF Pulsowanie",
    "description": "Animowany GIF - usuwa tło i generuje efekt pulsowania obiektu",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "💫",
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
        "speed": {
            "type": "select",
            "label": "Szybkość (ms na klatkę)",
            "choices": {
                "50": "Szybka (50ms)",
                "100": "Normalna (100ms)",
                "200": "Wolna (200ms)",
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
    Generuje animowany GIF z pulsującym obiektem.
    """
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", METADATA["options"]["model"]["default"])
    num_frames = int(options.get("frames", METADATA["options"]["frames"]["default"]))
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

    # Rozsplituj kanały (RGB + Alpha)
    r, g, b, a = img_removed.split()
    
    # Aplikuj feathering do alpha mask (rozmycie krawędzi)
    a_base = feather_alpha_mask(a, edge_feather)

    # Generuj klatki z pulsowaniem alpha
    # Przygotuj tło RAZ - to jest kosztowne (inpaint)!
    bg = prepare_background(img_original.size, background, img_original, a_base)
    
    frames = []
    for i in range(num_frames):
        # Wartość alpha od 100% do 40% i z powrotem
        progress = i / (num_frames - 1) if num_frames > 1 else 0
        alpha_factor = 0.4 + 0.6 * abs(((progress * 2 - 1) ** 2) - 1)
        
        # Modyfikuj kanał alpha z featheringiem
        a_pulsing = a_base.point(lambda x: int(x * alpha_factor))
        
        # Stwórz klatkę
        frame = Image.merge("RGBA", (r, g, b, a_pulsing))
        
        # Nałóż z alpha mask
        frame_with_bg = bg.copy()
        frame_with_bg.paste(frame, mask=a_pulsing)
        frames.append(frame_with_bg)

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
