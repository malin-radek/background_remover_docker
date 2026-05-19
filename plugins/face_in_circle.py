"""
Plugin: Face in Circle — Profesjonalny efekt twarzy w okręgu z cieniem 3D
Pipeline:
  Zdjęcie → Wykrywanie twarzy → Maskowanie okręgu → Cieniowanie 3D → Tło → Final
"""

import io
import math
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageChops

try:
    import cv2
    _CV_AVAILABLE = True
except ImportError:
    _CV_AVAILABLE = False

try:
    from scipy import ndimage
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False


def is_available() -> bool:
    return _CV_AVAILABLE


# ── Shape generators (extensible for future shapes) ─────────────────────────
def _create_circle_mask(w, h, cx, cy, radius):
    """Tworzy maskę okręgu."""
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (int(cx), int(cy)), int(radius), 255, -1)
    return mask


def _create_square_mask(w, h, cx, cy, size, rotation=0):
    """Tworzy maskę kwadratu (z rotacją)."""
    mask = np.zeros((h, w), dtype=np.uint8)
    half = size / 2
    pts = np.array([
        [-half, -half], [half, -half], [half, half], [-half, half]
    ], dtype=np.float32)
    angle_rad = math.radians(rotation)
    rot_matrix = np.array([
        [math.cos(angle_rad), -math.sin(angle_rad)],
        [math.sin(angle_rad), math.cos(angle_rad)]
    ])
    pts = pts @ rot_matrix.T + np.array([cx, cy])
    pts = pts.astype(np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [pts], 255)
    return mask


def _create_spiky_mask(w, h, cx, cy, radius, spikes=8, spike_depth=0.3):
    """Tworzy maskę z kolcami (gwiazda)."""
    mask = np.zeros((h, w), dtype=np.uint8)
    pts = []
    for i in range(spikes * 2):
        angle = math.pi * i / spikes - math.pi / 2
        r = radius if i % 2 == 0 else radius * (1 - spike_depth)
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        pts.append([int(x), int(y)])
    pts = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [pts], 255)
    return mask


_SHAPE_FUNCS = {
    "circle": _create_circle_mask,
    "square": _create_square_mask,
    "spiky": _create_spiky_mask,
}


# ── Face Detection ──────────────────────────────────────────────────────────
_face_cascade = None

def _load_face_cascade():
    global _face_cascade
    if _face_cascade is None and _CV_AVAILABLE:
        _face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
        )
    return _face_cascade


def _detect_face(image_bytes):
    """Wykrywa twarz i zwraca (cx, cy, radius) lub None."""
    cascade = _load_face_cascade()
    if cascade is None:
        return None
    
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_np = np.array(img)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, 
        minSize=(50, 50), maxSize=(800, 800)
    )
    
    if len(faces) == 0:
        return None
    
    # Wybierz największą twarz
    face = max(faces, key=lambda f: f[2] * f[3])
    fx, fy, fw, fh = face
    
    cx = fx + fw / 2
    cy = fy + fh / 2
    # Promień okręgu: większy niż twarz, żeby zmieścić włosy/szyję
    radius = max(fw, fh) * 0.85
    
    return (cx, cy, radius)


# ── 3D Bevel/Emboss Effect ──────────────────────────────────────────────────
def _apply_3d_bevel(mask, depth, light_angle=135):
    """Tworzy efekt 3D (bevel/emboss) na krawędzi maski."""
    if depth <= 0:
        return np.zeros_like(mask, dtype=np.float32)
    
    # Gradient kierunku światła
    angle_rad = math.radians(light_angle)
    dx = int(math.cos(angle_rad) * depth)
    dy = int(math.sin(angle_rad) * depth)
    
    # Przesunięte maski dla highlight i shadow
    mask_float = mask.astype(np.float32) / 255.0
    
    # Highlight (górna lewa krawędź)
    highlight = ndimage.shift(mask_float, (-dy/2, -dx/2), mode='constant', cval=0)
    highlight = np.clip(highlight - mask_float, 0, 1)
    
    # Shadow (dolna prawa krawędź)
    shadow = ndimage.shift(mask_float, (dy/2, dx/2), mode='constant', cval=0)
    shadow = np.clip(mask_float - shadow, 0, 1)
    
    # Połącz: highlight jaśniejszy, shadow ciemniejszy
    bevel = np.zeros_like(mask_float)
    bevel[highlight > 0.1] = highlight[highlight > 0.1]  # White highlight
    bevel[shadow > 0.1] = -shadow[shadow > 0.1]  # Black shadow
    
    return bevel


# ── Inner/Outer Shadow ──────────────────────────────────────────────────────
def _apply_inner_shadow(mask, blur_radius, opacity):
    """Cień wewnętrzny (vignette wewnątrz okręgu)."""
    if blur_radius <= 0:
        return np.zeros_like(mask, dtype=np.float32)
    
    mask_float = mask.astype(np.float32) / 255.0
    # Odwróć maskę, rozmyj, przytnij do wnętrza
    inverted = 1.0 - mask_float
    blurred = ndimage.gaussian_filter(inverted, sigma=blur_radius)
    inner = np.clip(blurred - inverted, 0, 1) * mask_float * opacity
    return inner


def _apply_outer_shadow(mask, blur_radius, opacity, offset_x=0, offset_y=0):
    """Cień zewnętrzny (drop shadow za okręgiem)."""
    if blur_radius <= 0:
        return np.zeros_like(mask, dtype=np.float32)
    
    mask_float = mask.astype(np.float32) / 255.0
    # Przesuń maskę
    shifted = ndimage.shift(mask_float, (offset_y, offset_x), mode='constant', cval=0)
    # Rozmyj
    blurred = ndimage.gaussian_filter(shifted, sigma=blur_radius)
    # Tylko zewnętrzna część
    outer = np.clip(blurred - mask_float, 0, 1) * opacity
    return outer


# ── Background Handling ─────────────────────────────────────────────────────
def _create_background(size, bg_type, original_img=None):
    """Tworzy tło na podstawie typu."""
    w, h = size
    if bg_type == "white":
        return Image.new("RGB", (w, h), (255, 255, 255))
    elif bg_type == "black":
        return Image.new("RGB", (w, h), (0, 0, 0))
    elif bg_type == "dark_gray":
        return Image.new("RGB", (w, h), (40, 40, 40))
    elif bg_type == "light_gray":
        return Image.new("RGB", (w, h), (220, 220, 220))
    elif bg_type == "transparent":
        return Image.new("RGBA", (w, h), (0, 0, 0, 0))
    elif bg_type == "original" and original_img:
        return original_img.convert("RGB")
    else:
        return Image.new("RGB", (w, h), (255, 255, 255))


# ── METADATA ─────────────────────────────────────────────────────────────────
METADATA = {
    "id": "face_in_circle",
    "name": "👤 Twarz w Okręgu",
    "description": "Profesjonalny efekt twarzy w okręgu z cieniem 3D. Wykrywa twarz automatycznie, tworzy okrągły portret z efektem głębi.",
    "version": "1.0.0",
    "icon": "👤",
    "divider_param": "circle_3d_depth",
    "disable_scaling": False,
    "options": {
        "face_model": {
            "type": "select",
            "label": "Model wykrywania twarzy",
            "choices": {
                "haarcascade": "Haar Cascade (szybki, CPU)",
                "manual": "Ręczny (środek obrazu)",
            },
            "default": "haarcascade",
        },
        "circle_size": {
            "type": "slider",
            "label": "Rozmiar okręgu (% twarzy)",
            "min": 50, "max": 200, "step": 1,
            "default": 100,
        },
        "circle_offset_x": {
            "type": "slider",
            "label": "Przesunięcie okręgu X",
            "min": -200, "max": 200, "step": 1,
            "default": 0,
        },
        "circle_offset_y": {
            "type": "slider",
            "label": "Przesunięcie okręgu Y",
            "min": -200, "max": 200, "step": 1,
            "default": 0,
        },
        "circle_3d_depth": {
            "type": "slider",
            "label": "Efekt 3D (głębokość)",
            "min": 0, "max": 50, "step": 1,
            "default": 15,
        },
        "circle_3d_light_angle": {
            "type": "slider",
            "label": "Kąt światła 3D",
            "min": 0, "max": 360, "step": 1,
            "default": 135,
        },
        "inner_shadow": {
            "type": "slider",
            "label": "Cień wewnętrzny",
            "min": 0, "max": 100, "step": 1,
            "default": 30,
        },
        "outer_shadow": {
            "type": "slider",
            "label": "Cień zewnętrzny",
            "min": 0, "max": 100, "step": 1,
            "default": 40,
        },
        "outer_shadow_distance": {
            "type": "slider",
            "label": "Dystans cienia zewnętrznego",
            "min": 0, "max": 50, "step": 1,
            "default": 10,
        },
        "border_thickness": {
            "type": "slider",
            "label": "Grubość obramowania",
            "min": 0, "max": 20, "step": 1,
            "default": 3,
        },
        "border_color": {
            "type": "color",
            "label": "Kolor obramowania",
            "default": "#ffffff",
        },
        "background": {
            "type": "select",
            "label": "Tło",
            "choices": {
                "white": "Białe",
                "black": "Czarne",
                "dark_gray": "Ciemno szare",
                "light_gray": "Jasno szare",
                "transparent": "Przezroczyste",
                "original": "Oryginalne",
            },
            "default": "white",
        },
        "shape": {
            "type": "select",
            "label": "Kształt (beta)",
            "choices": {
                "circle": "Okrąg",
                "square": "Kwadrat",
                "spiky": "Gwiazda (8 kolców)",
            },
            "default": "circle",
        },
    },
}


# ── Plugin Interface ────────────────────────────────────────────────────────
def _hex_to_rgb(hex_color):
    """Konwertuje kolor hex do RGB."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def process(image_bytes: bytes, options: dict) -> bytes:
    if not _CV_AVAILABLE:
        raise RuntimeError("OpenCV (cv2) nie jest zainstalowane")
    
    # Parse options
    face_model = options.get("face_model", "haarcascade")
    circle_size_pct = float(options.get("circle_size", 100)) / 100.0
    offset_x = int(options.get("circle_offset_x", 0))
    offset_y = int(options.get("circle_offset_y", 0))
    depth_3d = int(options.get("circle_3d_depth", 15))
    light_angle = int(options.get("circle_3d_light_angle", 135))
    inner_shadow_str = float(options.get("inner_shadow", 30)) / 100.0
    outer_shadow_str = float(options.get("outer_shadow", 40)) / 100.0
    outer_shadow_dist = int(options.get("outer_shadow_distance", 10))
    border_thickness = int(options.get("border_thickness", 3))
    border_color = _hex_to_rgb(options.get("border_color", "#ffffff"))
    bg_type = options.get("background", "white")
    shape_type = options.get("shape", "circle")
    
    # Load image
    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = src.size
    src_rgb = src.convert("RGB")
    src_arr = np.array(src_rgb)
    
    # Detect face
    face_center = None
    if face_model == "haarcascade":
        face_center = _detect_face(image_bytes)
    
    if face_center is None:
        # Fallback: center of image
        face_center = (w / 2, h / 2, min(w, h) * 0.35)
    
    cx, cy, base_radius = face_center
    cx += offset_x
    cy += offset_y
    radius = base_radius * circle_size_pct
    
    # Create shape mask
    shape_func = _SHAPE_FUNCS.get(shape_type, _create_circle_mask)
    if shape_type == "square":
        mask = shape_func(w, h, cx, cy, radius * 2)
    elif shape_type == "spiky":
        mask = shape_func(w, h, cx, cy, radius, spikes=8, spike_depth=0.3)
    else:
        mask = shape_func(w, h, cx, cy, radius)
    
    # Apply mask to image
    mask_3d = np.stack([mask] * 3, axis=-1)
    masked_img = Image.fromarray(np.where(mask_3d > 0, src_arr, 0).astype(np.uint8), "RGB")
    masked_rgba = masked_img.convert("RGBA")
    
    # Create alpha from mask
    alpha = Image.fromarray(mask, "L")
    masked_rgba.putalpha(alpha)
    
    # 3D Bevel effect
    bevel = _apply_3d_bevel(mask, depth_3d, light_angle)
    
    # Inner shadow
    inner_shadow = _apply_inner_shadow(mask, blur_radius=radius * 0.15, opacity=inner_shadow_str)
    
    # Outer shadow
    outer_shadow = _apply_outer_shadow(
        mask, 
        blur_radius=radius * 0.2, 
        opacity=outer_shadow_str,
        offset_x=outer_shadow_dist,
        offset_y=outer_shadow_dist
    )
    
    # Create background
    bg = _create_background((w, h), bg_type, src_rgb)
    bg_rgba = bg.convert("RGBA")
    
    # Composite layers
    # 1. Background
    result = bg_rgba.copy()
    
    # 2. Outer shadow (behind circle)
    if outer_shadow_str > 0:
        shadow_rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shadow_arr = np.array(shadow_rgba)
        shadow_arr[:, :, 3] = (outer_shadow * 255).astype(np.uint8)
        shadow_img = Image.fromarray(shadow_arr, "RGBA")
        result = Image.alpha_composite(result, shadow_img)
    
    # 3. Main image (circle with face)
    result = Image.alpha_composite(result, masked_rgba)
    
    # 4. Inner shadow (inside circle)
    if inner_shadow_str > 0:
        inner_rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        inner_arr = np.array(inner_rgba)
        inner_arr[:, :, 3] = (inner_shadow * 255).astype(np.uint8)
        inner_img = Image.fromarray(inner_arr, "RGBA")
        result = Image.alpha_composite(result, inner_img)
    
    # 5. 3D Bevel overlay
    if depth_3d > 0:
        bevel_rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bevel_arr = np.array(bevel_rgba)
        
        # Highlight (white)
        highlight_mask = bevel > 0
        bevel_arr[highlight_mask, 0:3] = 255
        bevel_arr[highlight_mask, 3] = (bevel[highlight_mask] * 128).astype(np.uint8)
        
        # Shadow (black)
        shadow_mask = bevel < 0
        bevel_arr[shadow_mask, 0:3] = 0
        bevel_arr[shadow_mask, 3] = (-bevel[shadow_mask] * 128).astype(np.uint8)
        
        bevel_img = Image.fromarray(bevel_arr, "RGBA")
        result = Image.alpha_composite(result, bevel_img)
    
    # 6. Border
    if border_thickness > 0:
        # Dilate mask for border
        mask_uint8 = mask.astype(np.uint8)
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(mask_uint8, kernel, iterations=border_thickness)
        border_mask = cv2.subtract(dilated, mask_uint8)
        
        border_rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        border_arr = np.array(border_rgba)
        border_arr[border_mask > 0, 0:3] = border_color
        border_arr[border_mask > 0, 3] = 255
        border_img = Image.fromarray(border_arr, "RGBA")
        result = Image.alpha_composite(result, border_img)
    
    # Save
    buf = io.BytesIO()
    if bg_type == "transparent":
        result.save(buf, format="PNG")
    else:
        result.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
