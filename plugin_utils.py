"""
Wspólne narzędzia dla pluginów - przygotowanie tła, compositing, itp.
"""

from PIL import Image, ImageFilter, ImageOps
import numpy as np
import io
import base64


def _inpaint_mask(img_array: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Zamaluj maskę używając edge-aware inpainting (Teledilate + Gaussian blur).
    Lepsze od samej średniej koloru.
    """
    mask_bool = mask > 128
    
    if not np.any(mask_bool):
        return img_array  # Brak maski
    
    # Teledilate - rozszerz tło iteracyjnie
    from scipy import ndimage
    inverted_mask = ~mask_bool
    
    for c in range(min(3, img_array.shape[2])):  # RGB channels
        channel = img_array[:, :, c].astype(np.float32)
        
        # Teledilate: dla każdego maskowanego piksela, weź średnią z najbliższych niezamaskowanych
        for iteration in range(5):
            channel_dilated = np.zeros_like(channel)
            distances, indices = ndimage.distance_transform_edt(~mask_bool, return_distances=True, return_indices=True)
            
            for y in range(channel.shape[0]):
                for x in range(channel.shape[1]):
                    if mask_bool[y, x]:
                        ny, nx = indices[0, y, x], indices[1, y, x]
                        channel_dilated[y, x] = channel[ny, nx]
                    else:
                        channel_dilated[y, x] = channel[y, x]
            
            # Blur nieznacznie dla gładkości
            from scipy.ndimage import gaussian_filter
            channel = gaussian_filter(channel_dilated, sigma=1.0)
            img_array[:, :, c] = channel.astype(np.uint8)
    
    return img_array


def prepare_background(size: tuple, background_type: str = "original", 
                       original_image: Image.Image = None,
                       alpha_mask: Image.Image = None) -> Image.Image:
    """
    Przygotowuje tło na podstawie wybranego typu.
    Jeśli alpha_mask dostarczony, robi inpaint (zamalowuje obszar obiektu).
    
    Args:
        size: (width, height) - rozmiar tła
        background_type: 'original', 'white', 'gray', 'transparent'
        original_image: oryginalne zdjęcie (wymagane dla 'original')
        alpha_mask: opcjonalna maska alpha do inpaintu
    
    Returns:
        Image.Image: Tło w formacie RGB (czyszczony od obiektu jeśli mask dostarczony)
    """
    # Przygotuj podstawowe tło
    if isinstance(background_type, str) and background_type.startswith("data:image"):
        try:
            _, b64 = background_type.split(",", 1)
            bg_img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            bg = ImageOps.fit(bg_img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        except Exception as e:
            raise ValueError(f"Nie udało się wczytać tła z projektu: {e}") from e
    elif background_type == "original":
        if original_image is None:
            raise ValueError("original_image wymagane dla background_type='original'")
        bg = original_image.copy()
    elif background_type == "white":
        bg = Image.new("RGB", size, (255, 255, 255))
    elif background_type == "gray":
        bg = Image.new("RGB", size, (128, 128, 128))
    else:  # transparent - checkerboard
        bg = Image.new("RGB", size, (64, 64, 64))
        for y in range(0, size[1], 16):
            for x in range(0, size[0], 16):
                if ((x // 16) + (y // 16)) % 2 == 0:
                    bg.paste((200, 200, 200), (x, y, x+16, y+16))
    
    # ── Inpaint: zamaluj obszar obiektu (gdzie alpha_mask != 0) ──────────────────
    if alpha_mask is not None:
        # Rób inpaint ZAWSZE gdy mamy maskę - aby oczyścić tło z obiektu
        # (ważne dla parallax gdzie tło się skaluje i się żaden inny obiekt nie powinien być widoczny)
        try:
            # Konwertuj do numpy arrays
            bg_array = np.array(bg, dtype=np.uint8)
            mask_array = np.array(alpha_mask, dtype=np.uint8)
            
            # Dilate maskę aby pewnie pokryć cały obiekt
            from scipy import ndimage
            mask_dilated = ndimage.binary_dilation(mask_array > 128, iterations=15).astype(np.uint8) * 255
            
            # Spróbuj cv2.inpaint jeśli dostępny
            try:
                import cv2
                bg_inpainted = cv2.inpaint(bg_array, mask_dilated, 10, cv2.INPAINT_TELEA)
                bg = Image.fromarray(bg_inpainted)
            except (ImportError, AttributeError):
                # Fallback: custom inpaint
                bg_array = _inpaint_mask(bg_array, mask_dilated)
                bg = Image.fromarray(bg_array)
        except Exception as e:
            # Jeśli inpaint fail, zwróć normalne tło
            pass
    
    return bg



def feather_alpha_mask(alpha_mask: Image.Image, feather_width: int = 5) -> Image.Image:
    """
    Dodaje feathering (alpha-blending) do krawędzi alpha mask.
    
    Args:
        alpha_mask: maska alpha (mode 'L')
        feather_width: szerokość rozmycia w pikselach (0 = brak)
    
    Returns:
        Image.Image: Zmodyfikowana maska alpha z miękką krawędzią
    """
    if feather_width <= 0:
        return alpha_mask.copy()
    
    # Gaussowskie rozmycie dla miękkich krawędzi
    blurred = alpha_mask.filter(ImageFilter.GaussianBlur(radius=feather_width))
    return blurred


def composite_alpha(background: Image.Image, foreground_rgba: Image.Image, 
                   alpha_mask: Image.Image = None) -> Image.Image:
    """
    Nałożyć obraz z alpha na tło.
    
    Args:
        background: RGB tło
        foreground_rgba: RGBA obraz do nałożenia
        alpha_mask: opcjonalna maska alpha (jeśli None, użyj z foreground_rgba)
    
    Returns:
        Image.Image: Scalony obraz RGB
    """
    bg = background.copy()
    
    if alpha_mask is None:
        if foreground_rgba.mode == "RGBA":
            _, _, _, alpha_mask = foreground_rgba.split()
        else:
            alpha_mask = Image.new("L", foreground_rgba.size, 255)
    
    # Konwertuj foreground do RGB jeśli trzeba
    if foreground_rgba.mode == "RGBA":
        fg_rgb = foreground_rgba.convert("RGB")
    else:
        fg_rgb = foreground_rgba.convert("RGB")
    
    bg.paste(fg_rgb, mask=alpha_mask)
    return bg


def gif_to_mp4(gif_bytes: bytes) -> bytes:
    """
    Konwertuje GIF na MP4 (H.264/AVC codec).
    
    Args:
        gif_bytes: Bajty GIF-u
    
    Returns:
        bytes: MP4 w formacie bytes
    
    Raises:
        ImportError: Jeśli imageio-ffmpeg nie jest zainstalowany
    """
    import tempfile
    import os
    
    try:
        import imageio
    except ImportError:
        raise ImportError("imageio required for MP4 conversion")
    
    # imageio z ffmpeg lepiej działa z plikami niż BytesIO
    # Utwórz temp files
    with tempfile.TemporaryDirectory() as tmpdir:
        gif_path = os.path.join(tmpdir, 'temp.gif')
        mp4_path = os.path.join(tmpdir, 'output.mp4')
        
        # Zapisz GIF tymczasowo
        with open(gif_path, 'wb') as f:
            f.write(gif_bytes)
        
        # Wczytaj GIF
        reader = imageio.get_reader(gif_path, format='GIF')
        
        # Pobierz klatki i durations
        frames = []
        durations = []
        for i, frame in enumerate(reader):
            frames.append(frame)
            # GIF durations są w ms per frame
            try:
                meta = reader.get_meta_data(i)
                duration = meta.get('duration', 100)
            except:
                duration = 100
            durations.append(duration)
        
        reader.close()
        
        # Oblicz FPS z duration (średnia)
        avg_duration_ms = np.mean(durations) if durations else 100
        fps = 1000.0 / avg_duration_ms if avg_duration_ms > 0 else 10
        fps = max(1, min(60, fps))  # Clamp 1-60 FPS
        
        # Zapisz jako MP4
        writer = imageio.get_writer(mp4_path, codec='libx264', fps=fps, pixelformat='yuv420p')
        
        for frame in frames:
            writer.append_data(frame)
        
        writer.close()
        
        # Odczytaj MP4 bytes
        with open(mp4_path, 'rb') as f:
            mp4_bytes = f.read()
        
        return mp4_bytes
