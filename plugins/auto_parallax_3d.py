import io
import numpy as np
import PIL.Image as Image
from PIL import ImageFilter, ImageDraw

# Sprawdzenie dostępności bibliotek
try:
    import cv2
    import torch
    import torch.nn.functional as F
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

METADATA = {
    "id": "auto_parallax_3d",
    "name": "🚀 Auto-Parallax Turbo",
    "description": "Zoptymalizowana paralaksa 3D - szybkie generowanie na CPU",
    "version": "2.5.0",
    "author": "Radek & Gemini",
    "icon": "⚡",
    "options": {
        "depth_layers": {
            "type": "select",
            "label": "Warstwy głębi",
            "choices": {
                "auto": "Auto (sam określa)",
                "2": "2 warstwy",
                "3": "3 warstwy",
                "4": "4 warstwy",
                "5": "5 warstw"
            },
            "default": "auto",
        },
        "feather_radius": {
            "type": "select",
            "label": "Feather (rozmycie krawędzi)",
            "choices": {
                "0": "Brak",
                "2": "Subtelny",
                "4": "Normalny",
                "6": "Średni",
                "10": "Duży",
                "15": "Bardzo duży"
            },
            "default": "4",
        },
        "outline_thickness": {
            "type": "select",
            "label": "Grubość obrysu",
            "choices": {
                "0": "Bez obrysu",
                "1": "1px (cienki)",
                "2": "2px",
                "3": "3px",
                "5": "5px (grubszy)",
                "8": "8px (shadow puppet)"
            },
            "default": "3",
        },
        "outline_color": {
            "type": "select",
            "label": "Kolor obrysu",
            "choices": {
                "black": "Czarny",
                "white": "Biały",
                "red": "Czerwony",
                "blue": "Niebieski",
                "green": "Zielony",
                "yellow": "Żółty",
                "gold": "Złoty",
                "purple": "Purpura"
            },
            "default": "black",
        },
        "shadow_strength": {
            "type": "select",
            "label": "Siła cienia",
            "choices": {
                "0": "Bez cienia",
                "1": "Słaby",
                "2": "Średni (Recommended)",
                "3": "Silny"
            },
            "default": "2",
        },
        "depth_model": {
            "type": "select",
            "label": "Model głębi",
            "choices": {
                "small": "MiDaS Small (szybko, 150MB)",
                "large": "MiDaS Large (dokładnie, 500MB)"
            },
            "default": "large",
        },
        "bg_model": {
            "type": "select",
            "label": "Model tła",
            "choices": {
                "u2net": "U2Net (szybko)",
                "birefnet-general": "BiRefNet (medium)",
                "isnet-general-use": "ISNet (najlepsze)",
                "u2net_human_seg": "U2Net Human (tylko ludzie)"
            },
            "default": "isnet-general-use",
        },
        "intensity": {
            "type": "select",
            "label": "Moc ruchu",
            "choices": {"2": "Minimalna", "5": "Normalna", "10": "Mocna"},
            "default": "5",
        },
        "steps": {
            "type": "select",
            "label": "Liczba klatek",
            "choices": {"12": "Bardzo szybko", "24": "Standard", "48": "Super płynnie"},
            "default": "24",
        },
        "zoom_range": {
            "type": "select",
            "label": "Zoom in/out",
            "choices": {
                "0": "0% (bez zoomu)",
                "2": "2% (lekki)",
                "5": "5% (średni)",
                "10": "10% (mocny)"
            },
            "default": "2",
        },
        "zoom_target": {
            "type": "select",
            "label": "Zoom obejmuje",
            "choices": {
                "all": "Cały kadr",
                "people": "Tylko osoby"
            },
            "default": "all",
        }
    },
}

def is_available() -> bool:
    """Sprawdź dostępność pluginu."""
    return _AVAILABLE

def add_outline_and_shadow(layer_img: Image.Image, layer_mask: np.ndarray, outline_px: int, shadow_strength: int, outline_color: str = "black") -> Image.Image:
    """
    Dodaj obrysu i cienia do warstwy.
    
    Args:
        layer_img: RGBA image warstwy (z alpha)
        layer_mask: Binary mask (0-255) gdzie są piksele (numpy array H x W)
        outline_px: Grubość obrysu w px
        shadow_strength: Siła cienia (0-3)
        outline_color: Kolor obrysu (black, white, red, blue, green, yellow, gold, purple)
    
    Returns:
        RGBA image z obrysem i cieniem
    """
    # Mapa kolorów obrysu
    color_map = {
        "black": (0, 0, 0, 255),
        "white": (255, 255, 255, 255),
        "red": (255, 0, 0, 255),
        "blue": (0, 0, 255, 255),
        "green": (0, 255, 0, 255),
        "yellow": (255, 255, 0, 255),
        "gold": (255, 215, 0, 255),
        "purple": (128, 0, 128, 255),
    }
    outline_rgba = color_map.get(outline_color, (0, 0, 0, 255))
    
    H, W = layer_mask.shape[:2]  # numpy: (height, width)
    result = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # PIL: (width, height)
    
    # Jeśli brak efektów, zwróć orginalną
    if outline_px == 0 and shadow_strength == 0:
        return layer_img
    
    # 1. Dodaj cień (jeśli shadow_strength > 0)
    if shadow_strength > 0:
        shadow_blur = 1 + (shadow_strength * 0.5)
        shadow_offset = int(1 + (shadow_strength * 0.3))
        
        shadow_mask = Image.fromarray(layer_mask, mode='L')
        shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
        
        shadow_color = (20, 20, 20, int(3 * shadow_strength))
        shadow_img = Image.new("RGBA", (W, H), shadow_color)
        
        result.paste(shadow_img, (shadow_offset, shadow_offset), shadow_mask)
    
    # 2. Paste oryginalna warstwa NA ŚRODEK
    result.paste(layer_img, (0, 0), layer_img)
    
    # 3. Dodaj obrysu NA TOP (jeśli outline_px > 0)
    if outline_px > 0:
        # Wyciągnij mask i rozszerz go
        mask_cv = (layer_mask > 10).astype(np.uint8) * 255
        
        # Dilate żeby powiększyć mask dokładnie o outline_px pikseli
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (outline_px * 2 + 1, outline_px * 2 + 1))
        dilated = cv2.dilate(mask_cv, kernel, iterations=1)
        
        # Obrysu = dilated - original (tylko krawędzież!)
        outline_mask = dilated - mask_cv
        
        # Narysuj obrysu w wybranym kolorze NA TOP (bez clippingu!)
        outline_img = Image.new("RGBA", (W, H), outline_rgba)
        outline_alpha = Image.fromarray(outline_mask, mode='L')
        result.paste(outline_img, (0, 0), outline_alpha)
    
    return result

class DepthEstimator:
    def __init__(self, model_type: str = "large"):
        self.device = torch.device("cpu")
        # model_type: "small" (150MB) lub "large" (500MB)
        model_name = "MiDaS" if model_type == "large" else "MiDaS_small"
        self.model = torch.hub.load("intel-isl/MiDaS", model_name, trust_repo=True).to(self.device)
        transform_type = "default" if model_type == "large" else "small"
        self.transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True)
        self.transforms = getattr(self.transforms, f"{transform_type}_transform")
        self.model.eval()

    def get_depth(self, img_pil):
        img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        input_batch = self.transforms(img_cv).to(self.device)
        with torch.no_grad():
            prediction = self.model(input_batch)
            prediction = F.interpolate(
                prediction.unsqueeze(1),
                size=img_cv.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()
        return prediction.cpu().numpy()

def process(image_bytes: bytes, options: dict) -> bytes:
    # Parse opcji
    depth_layers_opt = options.get("depth_layers", "auto")
    feather_radius = int(options.get("feather_radius", 4))
    depth_model = options.get("depth_model", "large")
    bg_model = options.get("bg_model", "isnet-general-use")
    output_size = int(options.get("output_size", 1024))
    intensity = int(options.get("intensity", 5))
    num_frames = int(options.get("steps", 24))
    zoom_range_pct = float(options.get("zoom_range", 2))
    zoom_target = options.get("zoom_target", "all")
    outline_thickness = int(options.get("outline_thickness", 3))
    outline_color = options.get("outline_color", "black")
    shadow_strength = int(options.get("shadow_strength", 2))
    
    # 1. Ładowanie i resize
    img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    orig_W, orig_H = img_pil.size
    
    if max(orig_W, orig_H) != output_size:
        ratio = output_size / max(orig_W, orig_H)
        new_W = int(orig_W * ratio)
        new_H = int(orig_H * ratio)
        img_pil = img_pil.resize((new_W, new_H), Image.Resampling.LANCZOS)
    
    W, H = img_pil.size
    session = new_session(bg_model)
    
    # 2. Wytnij foreground
    fg_rgba = remove(img_pil, session=session)
    fg_mask_orig = np.array(fg_rgba.split()[-1])
    
    # Inpaint background
    img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    _, mask_bin = cv2.threshold(fg_mask_orig, 10, 255, cv2.THRESH_BINARY)
    bg_cv = cv2.inpaint(img_cv, mask_bin, 5, cv2.INPAINT_NS)
    bg_cv = cv2.GaussianBlur(bg_cv, (11, 11), 0)
    bg_pil = Image.fromarray(cv2.cvtColor(bg_cv, cv2.COLOR_BGR2RGB)).convert("RGBA")
    
    # Estymuj głębię na BACKGROUND obszarze
    depth_estimator = DepthEstimator(depth_model)
    depth_map = depth_estimator.get_depth(img_pil)
    
    # Normalizuj głębię TYLKO na background
    bg_depth = depth_map.copy()
    bg_depth[fg_mask_orig > 10] = 0
    
    bg_values = bg_depth[fg_mask_orig <= 10]
    if len(bg_values) > 0:
        bg_min = bg_values.min()
        bg_max = bg_values.max()
        bg_depth_normalized = np.zeros_like(depth_map, dtype=np.float32)
        bg_depth_normalized[fg_mask_orig <= 10] = (bg_depth[fg_mask_orig <= 10] - bg_min) / (bg_max - bg_min + 1e-6)
    else:
        bg_depth_normalized = np.zeros_like(depth_map, dtype=np.float32)
    
    # Określ ilość warstw BACKGROUND
    if depth_layers_opt == "auto":
        num_bg_layers = min(5, max(1, len(np.unique(bg_depth_normalized[fg_mask_orig <= 10])) // 20 + 1))
    else:
        num_bg_layers = max(1, int(depth_layers_opt) - 1)
    
    # Segmentacja BACKGROUND na warstwy
    bg_layer_thresholds = np.linspace(0, 1, num_bg_layers + 1)
    
    bg_layers = []
    for i in range(num_bg_layers):
        lower = bg_layer_thresholds[i]
        upper = bg_layer_thresholds[i + 1]
        layer_mask = (
            (bg_depth_normalized >= lower) & 
            (bg_depth_normalized < upper) & 
            (fg_mask_orig <= 10)
        ).astype(np.uint8) * 255
        bg_layers.append(layer_mask)
    
    # 3. Przetworzenie warstw
    processed_layers = []
    
    # WARSTWA 0: CAŁY FOREGROUND - spójna, bez dzielenia na głębię
    fg_layer_img = fg_rgba.copy()
    fg_layer_img.putalpha(Image.fromarray(fg_mask_orig, mode='L'))
    
    # Dodaj efekty do CAŁEGO foreground
    fg_layer_with_effects = add_outline_and_shadow(
        fg_layer_img,
        fg_mask_orig,
        outline_thickness,
        shadow_strength,
        outline_color
    )
    
    # Aplikuj feather
    if feather_radius > 0:
        alpha_channel = fg_layer_with_effects.split()[3]
        alpha_channel = alpha_channel.filter(ImageFilter.GaussianBlur(radius=feather_radius))
        fg_layer_with_effects.putalpha(alpha_channel)
    
    processed_layers.append(fg_layer_with_effects)
    
    # WARSTWY 1+: BACKGROUND podzielony na głębię
    for layer_mask in bg_layers:
        layer_img = bg_pil.copy()
        layer_alpha = Image.fromarray(layer_mask, mode='L')
        layer_img.putalpha(layer_alpha)
        
        # Dodaj efekty do background warstwy
        layer_with_effects = add_outline_and_shadow(
            layer_img,
            layer_mask,
            outline_thickness,
            shadow_strength,
            outline_color
        )
        
        # Aplikuj feather
        if feather_radius > 0:
            alpha_channel = layer_with_effects.split()[3]
            alpha_channel = alpha_channel.filter(ImageFilter.GaussianBlur(radius=feather_radius))
            layer_with_effects.putalpha(alpha_channel)
        
        processed_layers.append(layer_with_effects)
    
    # 6. RENDEROWANIE ANIMACJI
    frames = []
    for frame_idx in range(num_frames):
        t = frame_idx / (num_frames - 1) if num_frames > 1 else 0
        offset_factor = np.sin(t * 2 * np.pi)
        
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        
        # Wklejamy tło (bez paralaksy)
        frame.paste(bg_pil, (0, 0), bg_pil)
        
        # Warstwy background z paralaksą (indices 1+)
        for layer_idx in range(1, len(processed_layers)):
            layer_speed = intensity * (len(processed_layers) - layer_idx) / max(1, len(processed_layers))
            layer_offset = int(offset_factor * layer_speed * 3)
            
            frame.paste(processed_layers[layer_idx], (layer_offset, 0), processed_layers[layer_idx])
        
        # FOREGROUND warstwa na koniec (index 0) - zawsze na wierzchu
        if len(processed_layers) > 0:
            layer_speed = intensity * len(processed_layers) / max(1, len(processed_layers))
            layer_offset = int(offset_factor * layer_speed * 3)
            fg_layer = processed_layers[0]
            if zoom_range_pct > 0 and zoom_target == "people":
                zoom_amp = zoom_range_pct / 100.0
                zoom = 1.0 + zoom_amp * (0.5 - 0.5 * np.cos(t * 2 * np.pi))
                zw = max(1, int(W * zoom))
                zh = max(1, int(H * zoom))
                fg_zoomed = fg_layer.resize((zw, zh), Image.Resampling.LANCZOS)
                x0 = (zw - W) // 2
                y0 = (zh - H) // 2
                fg_layer = fg_zoomed.crop((x0, y0, x0 + W, y0 + H))
            frame.paste(fg_layer, (layer_offset, 0), fg_layer)

        # Globalny zoom in/out (1.0 -> 1+Z -> 1.0)
        if zoom_range_pct > 0 and zoom_target == "all":
            zoom_amp = zoom_range_pct / 100.0
            zoom = 1.0 + zoom_amp * (0.5 - 0.5 * np.cos(t * 2 * np.pi))
            zw = max(1, int(W * zoom))
            zh = max(1, int(H * zoom))
            zoomed = frame.resize((zw, zh), Image.Resampling.LANCZOS)
            x0 = (zw - W) // 2
            y0 = (zh - H) // 2
            frame = zoomed.crop((x0, y0, x0 + W, y0 + H))

        # Konwertuj na RGB
        frame_rgb = Image.new("RGB", (W, H), (0, 0, 0))
        frame_rgb.paste(frame, (0, 0), frame)
        frames.append(frame_rgb)
    
    # 5. Zapis GIF
    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        duration=60, loop=0, optimize=True
    )
    return buf.getvalue()
