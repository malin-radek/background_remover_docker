"""
Plugin: Cartoon Effect
Konwertuje zdjęcie na styl kreskówki - kombinacja wzmacnienia krawędzi i posteryzacji.
"""

METADATA = {
    "id": "cartoon_effect",
    "name": "🎬 Cartoon",
    "description": "Animowany GIF - konwertuje zdjęcie na styl kreskówki z błyskającymi efektami",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🖍️",
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
            "label": "Intensywność",
            "choices": {
                "light": "Lekka (subtelne)",
                "medium": "Średnia (normalna)",
                "strong": "Mocna (drastyczna)",
            },
            "default": "medium",
        },
        "colors": {
            "type": "select",
            "label": "Liczba kolorów",
            "choices": {
                "8": "8 kolorów (maksymalny efekt)",
                "12": "12 kolorów",
                "16": "16 kolorów",
                "24": "24 kolory (naturalne)",
            },
            "default": "12",
        },
        "keep_bg": {
            "type": "select",
            "label": "Usuń tło",
            "choices": {
                "no": "Zachowaj oryginalne tło",
                "yes": "Usuń tło (przezroczystość)",
            },
            "default": "no",
        },
        "animation": {
            "type": "select",
            "label": "Animacja",
            "choices": {
                "no": "Brak (statyczne)",
                "shine": "Błysk reflektora (shine)",
                "edge_pulse": "Tętnienie konturów (edge pulse)",
            },
            "default": "shine",
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
from PIL import Image, ImageFilter, ImageOps
import numpy as np
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
    Generuje efekt kreskówki z opcjonalną animacją na wyciętym obiekcie.
    """
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")
    
    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_original_rgba = img_original.convert("RGBA")
    
    intensity = options.get("intensity", METADATA["options"]["intensity"]["default"])
    num_colors = int(options.get("colors", METADATA["options"]["colors"]["default"]))
    keep_bg = options.get("keep_bg", METADATA["options"]["keep_bg"]["default"]) == "yes"
    animation = options.get("animation", METADATA["options"]["animation"]["default"])
    background = options.get("background", METADATA["options"]["background"]["default"])
    edge_feather = int(options.get("edge_feather", METADATA["options"]["edge_feather"]["default"]))
    model_name = options.get("model", METADATA["options"]["model"]["default"])
    
    # Usuń tło
    session = _get_session(model_name)
    img_removed = remove(img_original_rgba, session=session)
    if img_removed.mode != "RGBA":
        img_removed = img_removed.convert("RGBA")
    
    # Rozsplituj kanały
    r, g, b, alpha_mask = img_removed.split()
    
    # Aplikuj feathering
    alpha_mask = feather_alpha_mask(alpha_mask, edge_feather)
    
    rgb_removed = img_removed.convert("RGB")

    intensity_map = {
        "light": (1, 0.4),
        "medium": (2, 0.6),
        "strong": (3, 0.8),
    }
    blur_radius, edge_factor = intensity_map.get(intensity, (2, 0.6))

    def _create_cartoon_frame(img_in, blur_rad, colors, edge_fac):
        """Tworzy pojedynczą klatkę cartoon - zwraca RGB."""
        blurred = img_in.filter(ImageFilter.GaussianBlur(radius=blur_rad))
        posterized = ImageOps.posterize(blurred, bits=8 - (16 - colors).bit_length())
        edges = img_in.filter(ImageFilter.FIND_EDGES)
        edges = edges.point(lambda x: 255 if x > 50 else 0)
        result = Image.blend(posterized, Image.new("RGB", img_in.size, (0, 0, 0)), edge_fac * 0.3)
        return result.convert("RGB")

    if animation == "no":
        result = _create_cartoon_frame(rgb_removed, blur_radius, num_colors, edge_factor)
        bg = prepare_background(img_original.size, background, img_original)
        bg.paste(result, mask=alpha_mask)
        buf = io.BytesIO()
        bg.save(buf, format="PNG")
        return buf.getvalue()

    # Animacja - przygotuj tło RAZ (inpaint jest kosztowny!)
    bg = prepare_background(img_original.size, background, img_original, alpha_mask)

    # Generuj klatki
    num_frames = 8
    frames = []
    
    if animation == "shine":
        # Efekt błysku reflektora - Moving gradient shine
        for i in range(num_frames):
            frame = _create_cartoon_frame(rgb_removed, blur_radius, num_colors, edge_factor)
            
            # Dodaj shine - gradient od lewej do prawej
            shine_pos = (i / num_frames) * img_original.width
            shine_layer = Image.new("RGBA", img_original.size, (255, 255, 255, 0))
            
            # Naszkicuj shine area
            for x in range(max(0, int(shine_pos) - 50), min(img_original.width, int(shine_pos) + 50)):
                intensity_shine = 1 - abs(x - shine_pos) / 50
                for y in range(img_original.height):
                    alpha_val = int(50 * intensity_shine)
                    shine_layer.putpixel((x, y), (255, 255, 255, alpha_val))
            
            # Blend shine z frame-m
            frame_rgba = Image.new("RGBA", frame.size)
            frame_rgba.paste(frame)
            frame_blended = Image.alpha_composite(frame_rgba, shine_layer)
            frame_rgb = frame_blended.convert("RGB")
            
            # Nałóż na tło
            bg_frame = bg.copy()
            bg_frame.paste(frame_rgb, mask=alpha_mask)
            frames.append(bg_frame)
    
    else:  # edge_pulse - Tętnienie krawędzi
        for i in range(num_frames):
            progress = i / (num_frames - 1) if num_frames > 1 else 0
            edge_intensity = 0.3 + 0.7 * abs(((progress * 2 - 1) ** 2) - 1)
            
            frame = _create_cartoon_frame(rgb_removed, blur_radius, num_colors, edge_factor * edge_intensity)
            
            # Nałóż na tło
            bg_frame = bg.copy()
            bg_frame.paste(frame, mask=alpha_mask)
            frames.append(bg_frame)
    
    # Zapisz GIF
    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
        optimize=False,
    )
    return buf.getvalue()
