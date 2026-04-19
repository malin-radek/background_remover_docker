"""
Plugin: Parallax 3D
Efekt paralaksy 3D - obiekt w centrum z subtlym zoomem, tło obraca się w perspektywie 3D.
Jak przechylanie telefonu wokół osi pionowej (Y-axis).
"""

METADATA = {
    "id": "parallax_3d",
    "name": "🎬 Parallax 3D",
    "description": "Animowany GIF - efekt paralaksy 3D iPhone'a - tło obraca się, obiekt zoom",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "📱",
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
                "12": "12 klatek",
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
        "parallax_intensity": {
            "type": "select",
            "label": "Intensywność paralaksy",
            "choices": {
                "0.017": "Minimalna (2°)",
                "0.05": "Subtelna (5°)",
                "0.1": "Średnia (10°)",
                "0.15": "Mocna (15°)",
                "0.2": "Ekstrema (20°)",
            },
            "default": "0.1",
        },
        "object_zoom": {
            "type": "select",
            "label": "Zoom obiektu pierwszego planu",
            "choices": {
                "0": "Brak (0%)",
                "1": "Minimalny (1%)",
                "1.5": "Subtelny (1.5%)",
                "2": "Średni (2%)",
                "3": "Mocny (3%)",
                "5": "Ekstremalny (5%)",
            },
            "default": "3",
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
from PIL import Image, ImageDraw
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
    Generuje animowany GIF z efektem paralaksy 3D.
    """
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", METADATA["options"]["model"]["default"])
    num_frames = int(options.get("frames", METADATA["options"]["frames"]["default"]))
    frame_duration = int(options.get("speed", METADATA["options"]["speed"]["default"]))
    parallax_intensity = float(options.get("parallax_intensity", METADATA["options"]["parallax_intensity"]["default"]))
    object_zoom_pct = float(options.get("object_zoom", METADATA["options"]["object_zoom"]["default"]))
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
    r, g, b, alpha_mask = img_removed.split()
    alpha_mask = feather_alpha_mask(alpha_mask, edge_feather)
    
    rgb_removed = Image.merge("RGB", (r, g, b))
    
    original_size = img_original.size
    
    # Przygotuj tło RAZ - to jest kosztowne (inpaint)!
    bg = prepare_background(original_size, background, img_original, alpha_mask)
    
    # Generuj klatki z paralaksą
    frames = []
    for i in range(num_frames):
        # Liniowy progress 0->1
        progress = i / (num_frames - 1) if num_frames > 1 else 0
        import math
        # Ping-pong: 0->1->0 smoothly
        sine_val = math.sin(progress * math.pi)  # 0 do 1 i z powrotem
        
        # Oblicz dynamiczny zoom tła - musi być wystarczająco duży aby podczas przesunięcia
        # nie pojawiły się czarne pasy. Przesunięcie max to parallax_intensity * 70% szerokości
        max_shift_pixels = int(original_size[0] * parallax_intensity * 0.7)
        # Zoom musi pokryć: (original + 2*max_shift) / original
        min_zoom_needed = 1.0 + (2.0 * max_shift_pixels / original_size[0])
        # Dodaj buffer 10% dla bezpieczeństwa
        bg_zoom = min_zoom_needed * 1.1
        
        bg_enlarged = bg.resize((int(original_size[0] * bg_zoom), int(original_size[1] * bg_zoom)), Image.LANCZOS)
        
        # Aplikuj efekt paralaksy na tło - obrót wokół osi Y
        # Przesunięcie w lewo/prawo
        horizontal_shift = int(max_shift_pixels * (2 * sine_val - 1))  # -max_shift do +max_shift
        
        # Stwórz kopię tła z przesunięciem (efekt paralaksy)
        bg_enlarged_w = bg_enlarged.width
        crop_left = (bg_enlarged_w - original_size[0]) // 2 + horizontal_shift
        crop_top = (bg_enlarged.height - original_size[1]) // 2
        
        bg_cropped = bg_enlarged.crop((
            crop_left,
            crop_top,
            crop_left + original_size[0],
            crop_top + original_size[1]
        ))
        bg_shifted = bg_cropped
        
        # Zoom obiektu - kontrolowany przez parametr
        # object_zoom_pct to maksymalny zoom w procentach (0-5)
        object_zoom = 1.0 + (object_zoom_pct / 100.0) * sine_val  # np. 1.0 - 1.03 dla 3%
        obj_width = int(original_size[0] * object_zoom)
        obj_height = int(original_size[1] * object_zoom)
        
        # Resizeuj wycięty obiekt
        rgb_zoomed = rgb_removed.resize((obj_width, obj_height), Image.LANCZOS)
        alpha_zoomed = alpha_mask.resize((obj_width, obj_height), Image.LANCZOS)
        
        # Stwórz layer obiektu ze zoomem (centered)
        obj_layer = Image.new("RGBA", original_size, (0, 0, 0, 0))
        offset_x = (original_size[0] - obj_width) // 2
        offset_y = (original_size[1] - obj_height) // 2
        r_z, g_z, b_z = rgb_zoomed.split()
        obj_rgba = Image.merge("RGBA", (r_z, g_z, b_z, alpha_zoomed))
        obj_layer.paste(obj_rgba, (offset_x, offset_y), alpha_zoomed)
        
        # Złóż tło ze zoomowanym obiektem
        bg_shifted = bg_shifted.convert("RGBA")
        result = Image.alpha_composite(bg_shifted, obj_layer)
        
        frames.append(result.convert("RGB"))

    # Zapisz jako GIF
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
