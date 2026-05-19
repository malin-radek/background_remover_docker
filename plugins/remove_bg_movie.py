"""
Plugin: Video to Transparent GIF / Replace Background
Konwertuje wideo na GIF, usuwając tło z każdej klatki i opcjonalnie podmieniając je na inne.
Obsługuje: przezroczyste tło, kolory, obraz z projektu, statyczny obraz, wideo jako tło, klatkę z wideo jako tło.
"""

METADATA = {
    "id": "remove_bg_movie",
    "name": "Wideo na GIF (bez tła / z nowym tłem)",
    "description": "Usuwa tło z wideo i generuje GIF. Może podmienić tło na przezroczyste, kolor, obraz, inne wideo lub wybraną klatkę.",
    "version": "2.0.0",
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
        },
        "background": {
            "type": "select",
            "label": "Typ tła",
            "choices": {
                "transparent": "Przezroczyste (checkerboard)",
                "white": "Białe",
                "black": "Czarne",
                "gray": "Szare",
                "original": "Oryginalne tło z wideo",
                "project": "Wynik z innego projektu",
                "static_image": "Statyczny obraz z pliku",
                "movie": "Wideo jako tło",
                "frame": "Wybrana klatka z wideo jako tło",
            },
            "default": "transparent",
        },
        "bg_frame_number": {
            "type": "slider",
            "label": "Numer klatki do użycia jako tło (0 = pierwsza)",
            "min": 0,
            "max": 500,
            "default": 0,
        },
        "bg_movie_fps": {
            "type": "slider",
            "label": "FPS tła wideo (0 = dopasuj do głównego)",
            "min": 0,
            "max": 30,
            "default": 0,
        },
        "bg_blur": {
            "type": "slider",
            "label": "Rozmycie tła (px)",
            "min": 0,
            "max": 30,
            "default": 0,
        },
    },
}

import io
import tempfile
import os
import base64
import numpy as np
from PIL import Image, ImageFilter

try:
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_sessions = {}


def is_available() -> bool:
    return _AVAILABLE

def _get_session(model_name):
    if model_name not in _sessions:
        _sessions[model_name] = new_session(model_name)
    return _sessions[model_name]


def _apply_outline_simple(img, thickness, color_name):
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


def _create_checkerboard(size, tile=16):
    bg = Image.new("RGB", size, (64, 64, 64))
    for y in range(0, size[1], tile):
        for x in range(0, size[0], tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                bg.paste((200, 200, 200), (x, y, x + tile, y + tile))
    return bg


def _load_background(bg_type, options, frame_size, first_frame_no_bg=None, project_bg_data=None, static_image_data=None, movie_bg_clip=None):
    """Tworzy tło na podstawie wybranego typu."""
    w, h = frame_size
    
    if bg_type == "transparent":
        return _create_checkerboard((w, h))
    elif bg_type == "white":
        return Image.new("RGB", (w, h), (255, 255, 255))
    elif bg_type == "black":
        return Image.new("RGB", (w, h), (0, 0, 0))
    elif bg_type == "gray":
        return Image.new("RGB", (w, h), (128, 128, 128))
    elif bg_type == "original" and first_frame_no_bg is not None:
        return first_frame_no_bg.convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
    elif bg_type == "project" and project_bg_data is not None:
        try:
            _, b64 = project_bg_data.split(",", 1)
            bg_img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            return bg_img.resize((w, h), Image.Resampling.LANCZOS)
        except Exception:
            return _create_checkerboard((w, h))
    elif bg_type == "static_image" and static_image_data is not None:
        try:
            _, b64 = static_image_data.split(",", 1)
            bg_img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            return bg_img.resize((w, h), Image.Resampling.LANCZOS)
        except Exception:
            return _create_checkerboard((w, h))
    else:
        return _create_checkerboard((w, h))


def _get_movie_bg_frame(movie_bg_clip, current_time, target_size):
    """Pobiera klatkę z wideo-tła w danym czasie."""
    try:
        movie_bg_clip = movie_bg_clip.set_fps(10)
        frame = movie_bg_clip.get_frame(current_time)
        pil_frame = Image.fromarray(frame).convert("RGB")
        return pil_frame.resize(target_size, Image.Resampling.LANCZOS)
    except Exception:
        return Image.new("RGB", target_size, (64, 64, 64))


def process_video_to_gif(video_bytes: bytes, options: dict) -> bytes:
    """
    Główna funkcja przetwarzająca wideo na GIF z opcją podmiany tła.
    """
    try:
        from moviepy.editor import VideoFileClip
    except ImportError as e:
        raise ImportError(f"moviepy is required. Install: pip install moviepy imageio-ffmpeg. Error: {e}") from e
    
    model_name = options.get("model", "u2net")
    target_width = int(options.get("max_width", 400))
    target_fps = int(options.get("fps", 10))
    outline_thickness = int(options.get("outline_thickness", 0))
    outline_color = options.get("outline_color", "none")
    bg_type = options.get("background", "transparent")
    bg_frame_number = int(options.get("bg_frame_number", 0))
    bg_movie_fps = int(options.get("bg_movie_fps", 0))
    bg_blur = int(options.get("bg_blur", 0))
    
    session = _get_session(model_name)

    temp_path = None
    clip = None
    movie_bg_clip = None
    movie_bg_temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            temp_video.write(video_bytes)
            temp_path = temp_video.name

        clip = VideoFileClip(temp_path)
        
        if clip.w > target_width:
            clip = clip.resize(width=target_width)
        
        clip = clip.set_fps(target_fps)

        first_frame_no_bg = None
        frame_size = (clip.w, clip.h)

        # ── Przygotowanie tła statycznego (project, static_image, frame) ──
        project_bg_data = options.get("background") if isinstance(options.get("background"), str) and options["background"].startswith("data:image") else None
        static_image_data = options.get("static_image") if isinstance(options.get("static_image"), str) and options.get("static_image", "").startswith("data:image") else None
        
        # Sprawdź czy background to project: (data:image z resolveProjectBackdrops)
        if bg_type == "project":
            project_bg_data = options.get("background")
            if project_bg_data and not project_bg_data.startswith("data:image"):
                project_bg_data = None

        if bg_type == "static_image":
            static_image_data = options.get("static_image")

        # ── Wideo jako tło ──
        movie_bg_data = options.get("movie_background")
        if bg_type == "movie" and movie_bg_data and movie_bg_data.startswith("data:video"):
            # Zapisz wideo z base64 do pliku tymczasowego
            _, b64 = movie_bg_data.split(",", 1)
            movie_bg_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            movie_bg_temp.write(base64.b64decode(b64))
            movie_bg_temp_path = movie_bg_temp.name
            movie_bg_temp.close()
            try:
                movie_bg_clip = VideoFileClip(movie_bg_temp_path)
                if bg_movie_fps > 0:
                    movie_bg_clip = movie_bg_clip.set_fps(bg_movie_fps)
            except Exception:
                movie_bg_clip = None
                os.unlink(movie_bg_path)

        # ── Przetwarzanie klatek ──
        processed_frames = []
        frame_idx = 0
        
        for frame in clip.iter_frames(fps=target_fps, dtype="uint8"):
            pil_frame = Image.fromarray(frame).convert("RGBA")
            no_bg_frame = remove(pil_frame, session=session)
            
            # Zapisz pierwszą klatkę bez tła dla opcji "original"
            if frame_idx == 0:
                first_frame_no_bg = no_bg_frame.copy()
            
            # Aplikacja obrysu
            if outline_thickness > 0 and outline_color != "none":
                no_bg_frame = _apply_outline_simple(no_bg_frame, outline_thickness, outline_color)
            
            # ── Przygotowanie tła dla tej klatki ──
            if bg_type == "movie" and movie_bg_clip is not None:
                bg_frame = _get_movie_bg_frame(movie_bg_clip, frame_idx / target_fps, frame_size)
            elif bg_type == "frame":
                # Użyj wybranej klatki jako tła - będzie przetworzona w drugiej pętli
                bg_frame = None  # placeholder, wypełnione później
            else:
                bg_frame = _load_background(bg_type, options, frame_size, first_frame_no_bg, project_bg_data, static_image_data, movie_bg_clip)
            
            # Rozmycie tła
            if bg_blur > 0 and bg_frame is not None:
                bg_frame = bg_frame.filter(ImageFilter.GaussianBlur(radius=bg_blur))
            
            # Composite: tło + obiekt bez tła
            if bg_frame is not None:
                final_frame = bg_frame.convert("RGBA")
                final_frame.alpha_composite(no_bg_frame)
            else:
                final_frame = no_bg_frame
            
            processed_frames.append(final_frame)
            frame_idx += 1

        # ── Obsługa tła z klatki (frame) ──
        if bg_type == "frame" and processed_frames:
            bg_frame_idx = min(bg_frame_number, len(processed_frames) - 1)
            bg_candidate = processed_frames[bg_frame_idx]
            
            # Stwórz tło z wybranej klatki: weź oryginalną klatkę, ale zamień obiekt na inpainted
            # Dla uproszczenia: użyj klatki bez obiektu (no_bg_frame z alpha=0) jako tła
            # Najpierw ekstrakcja oryginalnej klatki z wideo
            clip_for_bg = VideoFileClip(temp_path)
            if clip_for_bg.w > target_width:
                clip_for_bg = clip_for_bg.resize(width=target_width)
            clip_for_bg = clip_for_bg.set_fps(target_fps)
            
            orig_bg_frame = None
            for i, orig_frame in enumerate(clip_for_bg.iter_frames(fps=target_fps, dtype="uint8")):
                if i == bg_frame_idx:
                    orig_bg_frame = Image.fromarray(orig_frame).convert("RGB")
                    break
            clip_for_bg.close()
            
            if orig_bg_frame is not None:
                # Inpaint: zamaluj obszar obiektu
                obj_alpha = np.array(processed_frames[bg_frame_idx].split()[3])
                mask = (obj_alpha > 10).astype(np.uint8)
                
                from scipy import ndimage
                mask_dilated = ndimage.binary_dilation(mask, iterations=15).astype(np.uint8) * 255
                
                try:
                    import cv2
                    bg_array = np.array(orig_bg_frame, dtype=np.uint8)
                    bg_inpainted = cv2.inpaint(bg_array, mask_dilated, 10, cv2.INPAINT_TELEA)
                    final_bg = Image.fromarray(bg_inpainted)
                except (ImportError, AttributeError):
                    final_bg = orig_bg_frame
                
                if bg_blur > 0:
                    final_bg = final_bg.filter(ImageFilter.GaussianBlur(radius=bg_blur))
                
                # Zamień wszystkie klatki na composite z tym tłem
                new_frames = []
                for fg_frame in processed_frames:
                    composite = final_bg.copy().convert("RGBA")
                    composite.alpha_composite(fg_frame)
                    new_frames.append(composite)
                processed_frames = new_frames

        # ── Tworzenie GIF ──
        out_buf = io.BytesIO()
        
        if processed_frames:
            processed_frames[0].save(
                out_buf,
                format="GIF",
                save_all=True,
                append_images=processed_frames[1:],
                duration=int(1000 / target_fps),
                loop=0,
                disposal=2
            )
        
        return out_buf.getvalue()

    finally:
        if clip is not None:
            clip.close()
        if movie_bg_clip is not None:
            movie_bg_clip.close()
        if temp_path is not None and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        if movie_bg_temp_path is not None and os.path.exists(movie_bg_temp_path):
            try:
                os.remove(movie_bg_temp_path)
            except Exception:
                pass


def process(file_bytes: bytes, options: dict) -> bytes:
    return process_video_to_gif(file_bytes, options)
