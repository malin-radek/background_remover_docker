"""
Plugin: Remove Background
Usuwa tło ze zdjęcia używając modeli AI (rembg + ONNX).
"""

METADATA = {
    "id": "remove_background",
    "name": "Usuń tło",
    "description": "Usuwa tło ze zdjęcia przy użyciu modeli AI. Obsługuje kilka modeli o różnej jakości i szybkości.",
    "version": "1.2.0",
    "author": "Radek",
    "icon": "🎭",
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
        "scale": {
            "type": "select",
            "label": "Skala wyjściowa",
            "choices": {
                "100": "100%",
                "90": "90%",
                "80": "80%",
                "70": "70%",
                "60": "60%",
                "50": "50%",
                "40": "40%",
                "30": "30%",
                "20": "20%",
            },
            "default": "100",
        },
        "outline_thickness": {
            "type": "slider",
            "label": "Grubość obrysu (px)",
            "min": 0,
            "max": 25,
            "default": 0,
        },
        "outline_color": {
            "type": "select",
            "label": "Kolor obrysu",
            "choices": {
                "none": "Brak",
                "black": "Czarny",
                "white": "Biały",
                "red": "Czerwony",
                "blue": "Niebieski",
                "green": "Zielony",
                "yellow": "Żółty",
                "gold": "Złoty",
                "purple": "Fioletowy",
            },
            "default": "none",
        },
        "shadow_strength": {
            "type": "slider",
            "label": "Siła cienia (0-3)",
            "min": 0,
            "max": 3,
            "default": 0,
        },
        "feather_radius": {
            "type": "slider",
            "label": "Rozmycie krawędzi (px)",
            "min": 0,
            "max": 15,
            "default": 0,
        },
        "corner_curl": {
            "type": "checkbox",
            "label": "Podwinięcie rogu",
            "default": False,
        },
    },
}

import io
import threading
import numpy as np
from PIL import Image, ImageFilter, ImageDraw

try:
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_sessions: dict = {}
_lock = threading.Lock()

def _apply_corner_curl(img: Image.Image) -> Image.Image:
    """
    3. Podwinięcie rogu + 4. cień na linii zgięcia.
    Operuje na już obrysowanej nalepce (inline z obwódką).
    Przytnij do bbox → wytnij trójkąt → narysuj cień zgięcia → wklej z powrotem.
    """
    bbox = img.getbbox()
    if bbox is None:
        return img
    cropped = img.crop(bbox)
    w, h = cropped.size
    result = cropped.copy()

    curl_size = max(20, min(w, h) // 5)

    # Wytnij trójkąt z kanału alpha — wierzchołki: (w,h), (w-curl,h), (w,h-curl)
    alpha_arr = np.array(result.split()[3])
    y_coords, x_coords = np.ogrid[:h, :w]
    dx = x_coords - (w - curl_size)
    dy = y_coords - (h - curl_size)
    triangle_mask = (dx >= 0) & (dy >= 0) & ((dx + dy) >= curl_size)
    alpha_arr[triangle_mask] = 0
    result.putalpha(Image.fromarray(alpha_arr, mode='L'))

    # Cień wzdłuż linii zgięcia (gradient zanikający do środka)
    shadow_depth = max(8, curl_size // 6)
    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, 'RGBA')
    for i in range(shadow_depth):
        a = int(120 * (1 - i / shadow_depth))
        x1 = max(0, w - curl_size - i)
        y2 = max(0, h - curl_size - i)
        draw.line([(x1, h), (w, y2)], fill=(0, 0, 0, a), width=2)
    result = Image.alpha_composite(result, overlay)

    # Wklej z powrotem w oryginalny canvas
    canvas = Image.new('RGBA', img.size, (0, 0, 0, 0))
    canvas.paste(result, (bbox[0], bbox[1]))
    return canvas


def _apply_outline(img: Image.Image, thickness: int, color_name: str) -> Image.Image:
    """
    2. Obwódka — rozszerza maskę obiektu o `thickness` px i maluje ją podanym kolorem.
    Zwraca obraz z obwódką pod obiektem.
    """
    from scipy import ndimage

    color_map = {
        "black":  (0,   0,   0),
        "white":  (255, 255, 255),
        "red":    (255, 0,   0),
        "blue":   (0,   0,   255),
        "green":  (0,   200, 0),
        "yellow": (255, 255, 0),
        "gold":   (255, 215, 0),
        "purple": (128, 0,   128),
    }
    color = color_map.get(color_name, (0, 0, 0))

    alpha = np.array(img.split()[3])
    binary = (alpha > 10).astype(np.uint8)
    dilated = ndimage.binary_dilation(binary, iterations=thickness).astype(np.uint8)
    border = ((dilated - binary) * 255).astype(np.uint8)

    outline_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    outline_layer.paste(color + (255,), (0, 0), Image.fromarray(border, mode='L'))

    result = Image.new('RGBA', img.size, (0, 0, 0, 0))
    result.paste(outline_layer, (0, 0), outline_layer)   # obwódka pod spodem
    result = Image.alpha_composite(result, img)           # obiekt na wierzchu
    return result


def _apply_drop_shadow(img: Image.Image, strength: int) -> Image.Image:
    """
    5. Cień pod całą nalepką (po podwinięciu i obwódce).
    strength: 1-3 → przesunięcie i nieprzezroczystość rosną.
    """
    from PIL.ImageFilter import GaussianBlur

    offset = strength * 6       # px przesunięcia
    blur_r = strength * 4       # promień rozmycia
    shadow_alpha = min(60 + strength * 30, 180)   # 90–180

    alpha = img.split()[3]
    shadow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, shadow_alpha), (0, 0), alpha)
    shadow = shadow.filter(GaussianBlur(radius=blur_r))

    # Canvas powiększony o offset, żeby cień nie uciekał za krawędź
    pad = offset + blur_r * 2
    canvas = Image.new('RGBA', (img.width + pad, img.height + pad), (0, 0, 0, 0))
    canvas.paste(shadow, (offset, offset), shadow)
    canvas.paste(img, (0, 0), img)
    return canvas


def is_available() -> bool:
    return _AVAILABLE


SCALES = {
    "100": 1.0, "90": 0.9, "80": 0.8, "70": 0.7,
    "60": 0.6, "50": 0.5, "40": 0.4, "30": 0.3, "20": 0.2,
}


def _get_session(model_name: str):
    with _lock:
        if model_name not in _sessions:
            _sessions[model_name] = new_session(model_name)
        return _sessions[model_name]


def process(image_bytes: bytes, options: dict) -> bytes:
    """
    Przetwarza obraz — usuwa tło.

    Args:
        image_bytes: surowe bajty wejściowego obrazu
        options: słownik opcji z METADATA['options']
            - model: nazwa modelu rembg
            - scale: skala wyjściowa (string "100", "80" itd.)
            - outline_thickness: grubość obrysu (0 = off)
            - outline_color: kolor obrysu
            - shadow_strength: siła cienia (0-3, 0 = off)
            - feather_radius: rozmycie krawędzi (0 = off)

    Returns:
        bajty wynikowego obrazu PNG z przezroczystym tłem
    """
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", METADATA["options"]["model"]["default"])
    scale_str = str(options.get("scale", METADATA["options"]["scale"]["default"]))
    scale = SCALES.get(scale_str, 1.0)
    outline_thickness = int(options.get("outline_thickness", 0))
    outline_color = options.get("outline_color", "none")
    shadow_strength = int(options.get("shadow_strength", 0))
    feather_radius = int(options.get("feather_radius", 0))

    # 1. Usuń tło (rembg)
    input_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    session = _get_session(model_name)
    output_img = remove(input_img, session=session)
    if output_img.mode != "RGBA":
        output_img = output_img.convert("RGBA")

    if scale != 1.0:
        w, h = output_img.size
        output_img = output_img.resize(
            (int(w * scale), int(h * scale)), Image.LANCZOS
        )

    # 2. Rozmycie krawędzi (feather) — przed obwódką, żeby granica była miękka
    if feather_radius > 0:
        alpha_channel = output_img.split()[3]
        alpha_channel = alpha_channel.filter(ImageFilter.GaussianBlur(radius=feather_radius))
        output_img.putalpha(alpha_channel)

    # 3. Obwódka (outline wokół kształtu nalepki)
    if outline_thickness > 0 and outline_color != "none":
        output_img = _apply_outline(output_img, outline_thickness, outline_color)

    # 4. Podwinięcie rogu (cut trójkąt + cień zgięcia)
    corner_curl = options.get("corner_curl", "false")
    if corner_curl in (True, "true", "True", "1", 1):
        output_img = _apply_corner_curl(output_img)

    # 5. Cień pod całą nalepką (drop shadow za obwódką i podwinięciem)
    if shadow_strength > 0:
        output_img = _apply_drop_shadow(output_img, shadow_strength)

    buf = io.BytesIO()
    output_img.save(buf, format="PNG")
    return buf.getvalue()
