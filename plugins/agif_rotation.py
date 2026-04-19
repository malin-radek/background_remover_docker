"""
Plugin: AGIF - Obrot
Usuwa tło i generuje animowany GIF z efektem obrotu obiektu.
"""

METADATA = {
    "id": "agif_rotation",
    "name": "🎬 AGIF Obrót",
    "description": "Animowany GIF - usuwa tło i generuje efekt obracania obiektu",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🌀",
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
                "12": "12 klatek (30°/klatka)",
                "16": "16 klatek (22.5°/klatka)",
                "20": "20 klatek",
                "24": "24 klatki (15°/klatka)",
                "36": "36 klatek (10°/klatka)",
                "50": "50 klatek",
                "75": "75 klatek",
                "100": "100 klatek",
            },
            "default": "24",
        },
        "rotation": {
            "type": "select",
            "label": "Typ obrotu",
            "choices": {
                "360": "Pełny obrót (360°)",
                "back": "Tam i z powrotem (720°)",
            },
            "default": "360",
        },
        "speed": {
            "type": "select",
            "label": "Szybkość (ms na klatkę)",
            "choices": {
                "30": "Szybka (30ms)",
                "50": "Normalna (50ms)",
                "100": "Wolna (100ms)",
            },
            "default": "50",
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
    Generuje animowany GIF z obrotem obiektu.
    """
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", METADATA["options"]["model"]["default"])
    num_frames = int(options.get("frames", METADATA["options"]["frames"]["default"]))
    rotation_type = options.get("rotation", METADATA["options"]["rotation"]["default"])
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
    alpha_mask = a_base

    original_size = img_original.size
    
    # Przygotuj tło RAZ - to jest kosztowne (inpaint)!
    bg = prepare_background(original_size, background, img_original, alpha_mask)

    # Generuj klatki z obrotem i płynnym zoomem
    frames = []
    total_rotation = 720 if rotation_type == "back" else 360
    
    for i in range(num_frames):
        progress = i / (num_frames - 1) if num_frames > 1 else 0
        angle = progress * total_rotation
        
        # Płynny zoom aby obiekt nie został uciięty na krawędziach
        # Max zoom: 15% (1.15) w połowie animacji, 1.0 na początku i końcu
        zoom_progress = abs(progress * 2 - 1)  # 1.0 -> 0.0 -> 1.0
        zoom = 1.0 + (1.0 - zoom_progress) * 0.15  # 1.15 -> 1.0 -> 1.15
        
        # Obróć
        rotated = img_removed.rotate(angle, expand=False, resample=Image.BICUBIC)
        
        # Przeskaluj (zoom)
        if zoom != 1.0:
            new_size = (int(rotated.width * zoom), int(rotated.height * zoom))
            rotated = rotated.resize(new_size, Image.LANCZOS)
            
            # Wycentruj (paste na środku oryginalnego rozmiaru)
            centered = Image.new("RGBA", img_removed.size, (0, 0, 0, 0))
            offset_x = (img_removed.width - rotated.width) // 2
            offset_y = (img_removed.height - rotated.height) // 2
            centered.paste(rotated, (offset_x, offset_y), rotated)
            rotated = centered
        
        # Nałóż obraz na tło
        bg_frame = bg.copy()
        _, _, _, alpha = rotated.split()
        bg_frame.paste(rotated, mask=alpha)
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
