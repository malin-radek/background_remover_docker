"""
Plugin: Pixel Art
Konwertuje zdjęcie na pixel art - pixelizacja z konturami.
"""

METADATA = {
    "id": "pixel_art",
    "name": "🎬 Pixel Art",
    "description": "Animowany GIF - konwertuje zdjęcie na styl pixel art z efektem tętnienia",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🎮",
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
        "pixel_size": {
            "type": "select",
            "label": "Rozmiar pixela",
            "choices": {
                "4": "4px (drobny)",
                "6": "6px (średni)",
                "8": "8px (normalny)",
                "12": "12px (duży)",
                "16": "16px (retro)",
            },
            "default": "8",
        },
        "colors": {
            "type": "select",
            "label": "Paleta kolorów",
            "choices": {
                "4": "4 kolory (ekstremalnie retro)",
                "8": "8 kolorów (klasyk)",
                "16": "16 kolorów (NES)",
                "256": "256 kolorów (pełna paleta)",
            },
            "default": "16",
        },
        "outline": {
            "type": "select",
            "label": "Kontur",
            "choices": {
                "no": "Bez konturu",
                "yes": "Dodaj kontur",
            },
            "default": "no",
        },
        "animation": {
            "type": "select",
            "label": "Animacja",
            "choices": {
                "no": "Brak (statyczne)",
                "pulse": "Tętnienie (pulse)",
                "flicker": "Błysk retro (flicker)",
            },
            "default": "pulse",
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


def _get_session(model_name: str):
    with _lock:
        if model_name not in _sessions:
            _sessions[model_name] = new_session(model_name)
        return _sessions[model_name]


def is_available() -> bool:
    return _AVAILABLE


def process(image_bytes: bytes, options: dict) -> bytes:
    """
    Generuje pixel art z opcjonalną animacją na wyciętym obiekcie.
    """
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")
    
    pixel_size = int(options.get("pixel_size", METADATA["options"]["pixel_size"]["default"]))
    num_colors = int(options.get("colors", METADATA["options"]["colors"]["default"]))
    add_outline = options.get("outline", METADATA["options"]["outline"]["default"]) == "yes"
    animation = options.get("animation", METADATA["options"]["animation"]["default"])
    background = options.get("background", METADATA["options"]["background"]["default"])
    edge_feather = int(options.get("edge_feather", METADATA["options"]["edge_feather"]["default"]))
    model_name = options.get("model", METADATA["options"]["model"]["default"])
    
    # Wczytaj obraz i usuń tło
    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_original_rgba = img_original.convert("RGBA")
    session = _get_session(model_name)
    img_removed = remove(img_original_rgba, session=session)
    if img_removed.mode != "RGBA":
        img_removed = img_removed.convert("RGBA")
    
    # Rozsplituj kanały
    r, g, b, alpha_mask = img_removed.split()
    
    # Aplikuj feathering
    alpha_mask = feather_alpha_mask(alpha_mask, edge_feather)

    def _create_pixelated_frame(img_in, pix_size, colors, outline):
        """Tworzy pojedynczą klatkę pixel art - na RGB (bez alfa)."""
        # Pixelizacja
        small = img_in.resize(
            (max(1, img_in.width // pix_size), max(1, img_in.height // pix_size)),
            Image.NEAREST
        )
        pixelated = small.resize(img_in.size, Image.NEAREST)
        
        # Posteryzacja
        if colors < 256:
            pixelated = pixelated.quantize(colors=colors)
            pixelated = pixelated.convert("RGB")
        
        # Kontur
        if outline:
            gray = pixelated.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edges = edges.point(lambda x: 255 if x > 30 else 0)
            for _ in range(2):
                edges = edges.filter(ImageFilter.MaxFilter(3))
            edge_mask = edges.convert("L")
            black_edges = Image.new("RGB", pixelated.size, (0, 0, 0))
            pixelated = Image.composite(black_edges, pixelated, ImageOps.invert(edge_mask))
        
        return pixelated.convert("RGB")

    # Konwertuj removed image do RGB (bez alpha)
    rgb_removed = img_removed.convert("RGB")
    
    if animation == "no":
        result = _create_pixelated_frame(rgb_removed, pixel_size, num_colors, add_outline)
        bg = prepare_background(img_original.size, background, img_original, alpha_mask)
        bg.paste(result, mask=alpha_mask)
        buf = io.BytesIO()
        bg.save(buf, format="PNG")
        return buf.getvalue()
    
    # Animacja - przygotuj tło RAZ (inpaint jest kosztowny!)
    bg = prepare_background(img_original.size, background, img_original, alpha_mask)
    
    # Generuj klatki
    num_frames = 8
    frames = []
    
    if animation == "pulse":
        # Tętnienie - zmiana jasności
        for i in range(num_frames):
            progress = i / (num_frames - 1) if num_frames > 1 else 0
            brightness = 0.7 + 0.3 * abs(((progress * 2 - 1) ** 2) - 1)
            
            frame = _create_pixelated_frame(rgb_removed, pixel_size, num_colors, add_outline)
            # Zmień jasność
            frame_array = np.array(frame, dtype=np.float32)
            frame_array[:, :, :3] = frame_array[:, :, :3] * brightness
            frame_rgb = Image.fromarray(np.uint8(np.clip(frame_array, 0, 255))).convert("RGB")
            
            # Nałóż na tło
            bg_frame = bg.copy()
            bg_frame.paste(frame_rgb, mask=alpha_mask)
            frames.append(bg_frame)
    
    else:  # flicker - retro efekt
        for i in range(num_frames):
            frame = _create_pixelated_frame(rgb_removed, pixel_size, num_colors, add_outline)
            
            # Losowy flicker - zmiana kontrastu
            if i % 2 == 0:
                frame_array = np.array(frame, dtype=np.float32)
                frame_array[:, :, :3] = np.clip(frame_array[:, :, :3] * 0.85, 0, 255)
                frame = Image.fromarray(np.uint8(frame_array))
            
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
