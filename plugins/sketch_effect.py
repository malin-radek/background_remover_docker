"""
Plugin: Sketch Effect
Konwertuje zdjęcie na efekt szkicu/rysunku - kombinacja edge detection i invert.
"""

METADATA = {
    "id": "sketch_effect",
    "name": "✏️ Szkic",
    "description": "Konwertuje zdjęcie na efekt szkicu/rysunku",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "📝",
    "options": {
        "intensity": {
            "type": "select",
            "label": "Intensywność",
            "choices": {
                "light": "Lekka (cieńkie linie)",
                "medium": "Średnia (normalne)",
                "strong": "Mocna (grube linie)",
            },
            "default": "medium",
        },
        "blur": {
            "type": "select",
            "label": "Wygładzanie",
            "choices": {
                "0": "Brak (ostre)",
                "1": "Lekkie",
                "2": "Średnie",
                "3": "Mocne",
            },
            "default": "1",
        },
    },
}

import io
from PIL import Image, ImageFilter, ImageOps

_AVAILABLE = True


def is_available() -> bool:
    return _AVAILABLE


def process(image_bytes: bytes, options: dict) -> bytes:
    """
    Generuje efekt szkicu - edge detection + dodge blend.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    intensity = options.get("intensity", METADATA["options"]["intensity"]["default"])
    blur_amount = int(options.get("blur", METADATA["options"]["blur"]["default"]))

    # Konwertuj do skali szarości
    gray = img.convert("L")
    
    # Wygładzanie Gaussa
    if blur_amount > 0:
        blurred = gray.filter(ImageFilter.GaussianBlur(radius=blur_amount))
    else:
        blurred = gray
    
    # Invert + edge detection = efekt szkicu
    inverted = ImageOps.invert(blurred)
    
    # Detekcja krawędzi
    edges = inverted.filter(ImageFilter.GaussianBlur(radius=1))
    
    # Blend modes - "dodge" effect
    # Zmieszaj gray z inverted edges
    result_array = []
    for i in range(256):
        # Dodge blend: A + B - A*B/255
        dodge_val = min(255, int(gray.getpixel((0, 0))) + int(edges.getpixel((0, 0))) - 
                        (int(gray.getpixel((0, 0))) * int(edges.getpixel((0, 0)))) // 255)
        result_array.append(dodge_val)
    
    # Bardziej praktyczne podejście - simple dodge
    result = Image.blend(gray, ImageOps.invert(edges), 0.5)
    
    # Mapa intensywności
    intensity_map = {
        "light": 0.3,
        "medium": 0.6,
        "strong": 0.85,
    }
    intensity_factor = intensity_map.get(intensity, 0.6)
    
    # Wzmocnij kontrast
    result = Image.blend(result, ImageOps.invert(result), intensity_factor * 0.3)
    
    # Zwróć jako RGBA
    result = result.convert("RGBA")

    # Zapisz
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()
