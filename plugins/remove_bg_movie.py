"""
Plugin: Video to Transparent GIF
Konwertuje wideo na przezroczysty GIF, usuwając tło z każdej klatki.
"""

METADATA = {
    "id": "remove_bg_movie",
    "name": "Wideo na GIF (bez tła)",
    "description": "Usuwa tło z wideo i generuje przezroczysty plik GIF.",
    "version": "1.0.0",
    "author": "Radek & Gemini",
    "icon": "🎞️",
    "accept": ".mp4,.mov,.avi,.mkv,.webm,video/*",
    "disable_scaling": True,
    "options": {
        "model": {
            "type": "select",
            "label": "Model AI",
            "choices": {
                "u2net": "u2net (szybki)",
                "birefnet-general": "birefnet-general (najlepszy)",
                "isnet-general-use": "isnet-general-use",
                "u2net_human_seg": "tylko ludzie",
            },
            "default": "u2net",
        },
        "max_width": {
            "type": "slider",
            "label": "Szerokość wyjściowa (px)",
            "min": 100,
            "max": 800,
            "default": 400,
        },
        "fps": {
            "type": "slider",
            "label": "Klatki na sekundę (FPS)",
            "min": 5,
            "max": 30,
            "default": 10,
        },
        "outline_thickness": {
            "type": "slider",
            "label": "Grubość obrysu (px)",
            "min": 0,
            "max": 15,
            "default": 0,
        },
        "outline_color": {
            "type": "select",
            "label": "Kolor obrysu",
            "choices": {
                "none": "Brak",
                "white": "Biały",
                "black": "Czarny",
                "yellow": "Żółty",
            },
            "default": "none",
        }
    },
}

import io
import tempfile
import os
import numpy as np
from PIL import Image
# moviepy imported lazily inside process_video_to_gif() to avoid import-time failures
# If moviepy is missing, plugin will raise ImportError when executed.
from rembg import remove, new_session

# Importujemy logikę Twoich funkcji (zakładając, że są w tym samym pliku lub wklejone poniżej)
# Dla zwięzłości wklejam kluczowe mechanizmy przetwarzania klatki

_sessions = {}

def _get_session(model_name):
    if model_name not in _sessions:
        _sessions[model_name] = new_session(model_name)
    return _sessions[model_name]

def process_video_to_gif(video_bytes: bytes, options: dict) -> bytes:
    """
    Główna funkcja przetwarzająca wideo na GIF.
    """
    model_name = options.get("model", "u2net")
    target_width = int(options.get("max_width", 400))
    target_fps = int(options.get("fps", 10))
    outline_thickness = int(options.get("outline_thickness", 0))
    outline_color = options.get("outline_color", "none")
    
    session = _get_session(model_name)

    # 1. Zapisz bajty do pliku tymczasowego (MoviePy tego wymaga)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
        temp_video.write(video_bytes)
        temp_path = temp_video.name

    try:
        try:
            from moviepy.editor import VideoFileClip
        except ImportError as e:
            raise ImportError("moviepy is required for remove_bg_movie plugin: install 'moviepy' and 'imageio-ffmpeg'") from e
        clip = VideoFileClip(temp_path)
        
        # Zmniejszenie rozdzielczości dla szybkości przetwarzania GIF
        if clip.w > target_width:
            clip = clip.resize(width=target_width)
        
        # Ograniczenie liczby klatek
        clip = clip.set_fps(target_fps)

        processed_frames = []

        # 2. Przetwarzanie klatek
        for frame in clip.iter_frames(fps=target_fps, dtype="uint8"):
            # Konwersja numpy array (RGB) na PIL Image
            pil_frame = Image.fromarray(frame).convert("RGBA")
            
            # 3. Usuwanie tła
            no_bg_frame = remove(pil_frame, session=session)
            
            # Aplikacja Twojej logiki obramowania (jeśli wybrana)
            if outline_thickness > 0 and outline_color != "none":
                # Tutaj używamy Twojej funkcji _apply_outline z poprzedniego kodu
                from scipy import ndimage # zakładając dostępność
                no_bg_frame = _apply_outline_simple(no_bg_frame, outline_thickness, outline_color)

            processed_frames.append(no_bg_frame)

        # 4. Tworzenie GIF-a z przezroczystością
        out_buf = io.BytesIO()
        
        # Pierwsza klatka definiuje paletę i parametry
        processed_frames[0].save(
            out_buf,
            format="GIF",
            save_all=True,
            append_images=processed_frames[1:],
            duration=int(1000 / target_fps),
            loop=0,
            disposal=2 # Ważne: usuwa poprzednią klatkę (zapobiega "duchom" przy przezroczystości)
        )
        
        return out_buf.getvalue()

    finally:
        clip.close()
        if os.path.exists(temp_path):
            os.remove(temp_path)

def _apply_outline_simple(img, thickness, color_name):
    # Uproszczona wersja Twojej funkcji dla wydajności wideo
    from scipy import ndimage
    color_map = {"white": (255, 255, 255), "black": (0, 0, 0), "yellow": (255, 255, 0)}
    color = color_map.get(color_name, (255, 255, 255))
    
    alpha = np.array(img.split()[3])
    mask = (alpha > 10).astype(np.uint8)
    dilated = ndimage.binary_dilation(mask, iterations=thickness).astype(np.uint8)
    border = ((dilated - mask) * 255).astype(np.uint8)
    
    outline_layer = Image.new('RGBA', img.size, color + (255,))
    result = Image.new('RGBA', img.size, (0, 0, 0, 0))
    result.paste(outline_layer, (0, 0), Image.fromarray(border, mode='L'))
    result.alpha_composite(img)
    return result

# Funkcja wejściowa dla systemu pluginów
def process(file_bytes: bytes, options: dict) -> bytes:
    return process_video_to_gif(file_bytes, options)