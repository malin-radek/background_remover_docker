"""
Plugin: Text on Image
Renderuje tekst na obrazkach z 15 profesjonalnie wyglądającymi stylami:
- Logo (outline + shadow)
- Speech bubble (dymek ze wskaźnikiem)
- Comic (grube, puste litery)
- Neon (glow efekt)
- Invert (przezroczysty tekst, opaque tło)
- 3D perspective
- Metallic (gradient + refleksje)
- Watercolor (miękkie, rozmyte krawędzie)
- Glitch (distorsja cyfrowa)
- Gold emboss (wytłoczenie złoto)
- Shadow deep (głębokie cienie 3D)
- Retro (bold + wibrantne kolory)
- Striped (paskowany tekst)
- Electric spark (animowany efekt)
- Comic stripes (pasek komiksowy)
"""

METADATA = {
    "id": "text_on_image",
    "name": "📝 Text on Image",
    "description": "Renderuj tekst na obrazku z 15 profesjonalnymi stylami",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "📝",
    "options": {
        "text": {
            "type": "textarea",
            "label": "Tekst (multiline)",
            "default": "YOUR TEXT HERE",
            "rows": 5,
        },
        "style": {
            "type": "select",
            "label": "Styl tekstu",
            "choices": {
                "logo": "🏆 Logo (outline + shadow)",
                "speech_bubble": "💬 Speech Bubble (dymek)",
                "comic": "💥 Comic (grube, puste)",
                "neon": "⚡ Neon (glow)",
                "invert": "◼️ Invert (przezr. tekst)",
                "perspective_3d": "🎭 3D Perspective",
                "metallic": "🥇 Metallic (gradient + refleksje)",
                "watercolor": "🌊 Watercolor (miękkie krawędzie)",
                "glitch": "📡 Glitch (distorsja cyfrowa)",
                "gold_emboss": "✨ Gold Emboss",
                "shadow_deep": "🕳️ Shadow Deep (3D)",
                "retro": "🎨 Retro (vibrant)",
                "striped": "📊 Striped (paskowany)",
                "electric_spark": "⚙️ Electric Spark",
                "comic_stripes": "📰 Comic Stripes",
            },
            "default": "logo",
        },
        "font": {
            "type": "select",
            "label": "Czcionka",
            "choices": {},  # Będzie wypełnione dynamicznie
            "default": "DejaVuSans-Bold.ttf",
        },
        "font_size": {
            "type": "slider",
            "label": "Rozmiar czcionki",
            "min": 20,
            "max": 300,
            "step": 5,
            "default": 80,
        },
        "position_x": {
            "type": "slider",
            "label": "Pozycja X (piksel)",
            "min": 0,
            "max": 2000,
            "step": 1,
            "default": 100,
        },
        "position_y": {
            "type": "slider",
            "label": "Pozycja Y (piksel)",
            "min": 0,
            "max": 2000,
            "step": 1,
            "default": 100,
        },
        "position_z": {
            "type": "slider",
            "label": "Skala (Z)",
            "min": 0.1,
            "max": 3.0,
            "step": 0.1,
            "default": 1.0,
        },
        "bubble_point_x": {
            "type": "slider",
            "label": "Dymek: punkt X (dla speech_bubble)",
            "min": 0,
            "max": 2000,
            "step": 1,
            "default": 500,
        },
        "bubble_point_y": {
            "type": "slider",
            "label": "Dymek: punkt Y (dla speech_bubble)",
            "min": 0,
            "max": 2000,
            "step": 1,
            "default": 500,
        },
        "bubble_irregularity": {
            "type": "slider",
            "label": "Dymek: nieregularność (0-100)",
            "min": 0,
            "max": 100,
            "step": 1,
            "default": 45,
        },
        "bubble_mode": {
            "type": "select",
            "label": "Dymek: tryb",
            "choices": {"speech": "Mowa", "thought": "Myśl"},
            "default": "speech",
        },
        "thought_count": {
            "type": "slider",
            "label": "Myśl: liczba elips",
            "min": 2,
            "max": 8,
            "step": 1,
            "default": 4,
        },
        "rotation": {
            "type": "slider",
            "label": "Rotacja (stopnie)",
            "min": -180,
            "max": 180,
            "step": 1,
            "default": 0,
        },
        "color_r": {
            "type": "slider",
            "label": "Kolor R",
            "min": 0,
            "max": 255,
            "step": 1,
            "default": 255,
        },
        "color_g": {
            "type": "slider",
            "label": "Kolor G",
            "min": 0,
            "max": 255,
            "step": 1,
            "default": 0,
        },
        "color_b": {
            "type": "slider",
            "label": "Kolor B",
            "min": 0,
            "max": 255,
            "step": 1,
            "default": 0,
        },
        "outline_r": {"type": "slider", "label": "Obwódka R", "min": 0, "max": 255, "step": 1, "default": 0},
        "outline_g": {"type": "slider", "label": "Obwódka G", "min": 0, "max": 255, "step": 1, "default": 0},
        "outline_b": {"type": "slider", "label": "Obwódka B", "min": 0, "max": 255, "step": 1, "default": 0},
        "glow_r": {"type": "slider", "label": "Poświata R", "min": 0, "max": 255, "step": 1, "default": 255},
        "glow_g": {"type": "slider", "label": "Poświata G", "min": 0, "max": 255, "step": 1, "default": 255},
        "glow_b": {"type": "slider", "label": "Poświata B", "min": 0, "max": 255, "step": 1, "default": 0},
        "shadow_r": {"type": "slider", "label": "Cień R", "min": 0, "max": 255, "step": 1, "default": 80},
        "shadow_g": {"type": "slider", "label": "Cień G", "min": 0, "max": 255, "step": 1, "default": 80},
        "shadow_b": {"type": "slider", "label": "Cień B", "min": 0, "max": 255, "step": 1, "default": 80},
        "bubble_bg_r": {"type": "slider", "label": "Dymek tło R", "min": 0, "max": 255, "step": 1, "default": 255},
        "bubble_bg_g": {"type": "slider", "label": "Dymek tło G", "min": 0, "max": 255, "step": 1, "default": 255},
        "bubble_bg_b": {"type": "slider", "label": "Dymek tło B", "min": 0, "max": 255, "step": 1, "default": 255},
        "invert_bg_r": {"type": "slider", "label": "Invert tło R", "min": 0, "max": 255, "step": 1, "default": 0},
        "invert_bg_g": {"type": "slider", "label": "Invert tło G", "min": 0, "max": 255, "step": 1, "default": 255},
        "invert_bg_b": {"type": "slider", "label": "Invert tło B", "min": 0, "max": 255, "step": 1, "default": 255},
        "opacity": {
            "type": "slider",
            "label": "Przezroczystość",
            "min": 0,
            "max": 100,
            "step": 1,
            "default": 100,
        },
    },
}

import io
import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import glob

_FONT_CACHE = {}
_AVAILABLE_FONTS = []

def _load_available_fonts():
    """Skanuj katalog czcionek i załaduj listę TTF."""
    global _AVAILABLE_FONTS, _FONT_CACHE
    if _AVAILABLE_FONTS:
        return
    
    # Spróbuj kilka ścieżek
    font_dirs = [
        "/app/fonts",
        "./fonts",
        "../fonts",
        os.path.join(os.path.dirname(__file__), "fonts"),
        os.path.join(os.path.dirname(__file__), "..", "fonts"),
    ]
    
    font_paths = []
    for font_dir in font_dirs:
        if os.path.isdir(font_dir):
            print(f"[TEXT_ON_IMAGE] Znaleziono katalog czcionek: {font_dir}")
            font_paths.extend(glob.glob(os.path.join(font_dir, "**/*.ttf"), recursive=True))
            font_paths.extend(glob.glob(os.path.join(font_dir, "**/*.otf"), recursive=True))
    
    if not font_paths:
        print(f"[TEXT_ON_IMAGE] UWAGA: Nie znaleziono czcionek w: {font_dirs}")
        print(f"[TEXT_ON_IMAGE] CWD: {os.getcwd()}")
        _AVAILABLE_FONTS = ["DejaVuSans-Bold.ttf"]
        return
    
    print(f"[TEXT_ON_IMAGE] Znaleziono {len(font_paths)} czcionek")
    
    # Weź tylko nazwę pliku
    for path in sorted(font_paths):
        fname = os.path.basename(path)
        if fname not in _FONT_CACHE:
            _FONT_CACHE[fname] = path
            _AVAILABLE_FONTS.append(fname)
    
    print(f"[TEXT_ON_IMAGE] Dostępne czcionki: {_AVAILABLE_FONTS[:5]}...")


def _get_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    """Załaduj czcionkę."""
    _load_available_fonts()
    
    if font_name not in _FONT_CACHE:
        print(f"[TEXT_ON_IMAGE] Czcionka '{font_name}' nie w cache, szukam fallback...")
        # Dopasowanie po nazwie bez rozszerzenia (.ttf/.otf)
        base = font_name.replace(".ttf", "").replace(".otf", "").lower()
        for fname, fpath in _FONT_CACHE.items():
            nbase = fname.replace(".ttf", "").replace(".otf", "").lower()
            if nbase == base:
                _FONT_CACHE[font_name] = fpath
                break
        # Fallback na DejaVu
        for pattern in ("/app/fonts/**/DejaVuSans-Bold.ttf", "/app/fonts/**/DejaVuSans-Bold.otf"):
            for path in glob.glob(pattern, recursive=True):
                _FONT_CACHE[font_name] = path
                break
            if font_name in _FONT_CACHE:
                break
        if font_name not in _FONT_CACHE:
            for pattern in ("./fonts/**/DejaVuSans-Bold.ttf", "./fonts/**/DejaVuSans-Bold.otf"):
                for path in glob.glob(pattern, recursive=True):
                    _FONT_CACHE[font_name] = path
                    break
                if font_name in _FONT_CACHE:
                    break
    
    path = _FONT_CACHE.get(font_name)
    if not path or not os.path.exists(path):
        print(f"[TEXT_ON_IMAGE] ERROR: Czcionka '{font_name}' nie znaleziona. Path: {path}")
        print(f"[TEXT_ON_IMAGE] Cache: {_FONT_CACHE}")
        raise FileNotFoundError(f"Czcionka {font_name} nie znaleziona (path: {path})")
    
    print(f"[TEXT_ON_IMAGE] Ładuję czcionkę: {path} (size: {size})")
    try:
        return ImageFont.truetype(path, size)
    except Exception as e:
        print(f"[TEXT_ON_IMAGE] ERROR ładowania: {e}")
        raise RuntimeError(f"Błąd ładowania czcionki {font_name}: {e}")


def _get_text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple:
    """Zwróć (left, top, right, bottom) tekstu."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox


def _render_logo(img: Image.Image, text: str, font: ImageFont.FreeTypeFont, 
                 pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Logo: outline (czarny 4px) + shadow (szary 6px pod spodem)."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    shadow = globals().get("_FX_SHADOW", (80, 80, 80))
    outline = globals().get("_FX_OUTLINE", (0, 0, 0))
    # Shadow
    for sx in range(-6, 7):
        for sy in range(-6, 7):
            if sx*sx + sy*sy <= 36:
                draw.text((x+sx, y+6+sy), text, font=font, fill=(*shadow, alpha//2))
    
    # Outline (czarny, 4px)
    for ox in range(-4, 5):
        for oy in range(-4, 5):
            if ox*ox + oy*oy <= 16:
                draw.text((x+ox, y+oy), text, font=font, fill=(*outline, alpha))
    
    # Tekst główny
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_speech_bubble(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                          pos: tuple, color: tuple, alpha: int, bubble_point: tuple) -> Image.Image:
    """Dymek: zaokrąglony prostokąt + trójkątny wskaźnik na punkt."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    bx, by = bubble_point[0], bubble_point[1]
    
    # Bbox tekstu
    bbox = _get_text_bbox(draw, text, font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Bubble bounds (wewnętrzny bezpieczny obszar dla tekstu)
    margin = 20
    outline = globals().get("_FX_OUTLINE", (0, 0, 0))
    bubble_bg = globals().get("_FX_BUBBLE_BG", (255, 255, 255))
    irr = max(0, min(100, int(globals().get("_FX_BUBBLE_IRR", 45))))
    amp = (irr / 100.0) * 0.40
    bubble_x1 = x - margin
    bubble_y1 = y - margin
    bubble_x2 = x + text_width + margin
    bubble_y2 = y + text_height + margin

    # Chmurka: 0 => rounded rect, >0 => coraz bardziej nieregularna
    if irr == 0:
        draw.rounded_rectangle(
            [bubble_x1, bubble_y1, bubble_x2, bubble_y2],
            radius=max(12, int(min(text_width, text_height) * 0.35)),
            fill=(*bubble_bg, int(alpha * 0.95)),
            outline=(*outline, alpha),
            width=3
        )
    else:
        # Nierówny kontur TYLKO na zewnątrz (bez "dolin" do środka).
        spikes = 18
        cx = (bubble_x1 + bubble_x2) / 2.0
        cy = (bubble_y1 + bubble_y2) / 2.0
        rx = (bubble_x2 - bubble_x1) / 2.0
        ry = (bubble_y2 - bubble_y1) / 2.0
        pts = []
        for i in range(spikes * 2):
            a = (2 * math.pi * i) / (spikes * 2)
            # Minimum zawsze 1.0 => żadnego wchodzenia do środka
            base = 1.0 + (amp if i % 2 == 1 else amp * 0.15)
            px = int(cx + math.cos(a) * rx * base)
            py = int(cy + math.sin(a) * ry * base)
            pts.append((px, py))
        draw.polygon(pts, fill=(*bubble_bg, int(alpha * 0.95)), outline=(*outline, alpha))
    
    bubble_mode = globals().get("_FX_BUBBLE_MODE", "speech")
    thought_count = max(2, min(8, int(globals().get("_FX_THOUGHT_COUNT", 4))))
    # Wskaźnik dymka: mowa (dziubek) lub myśl (malejące elipsy)
    ccx = (bubble_x1 + bubble_x2) / 2.0
    ccy = (bubble_y1 + bubble_y2) / 2.0
    vx = bx - ccx
    vy = by - ccy
    vlen = math.hypot(vx, vy) or 1.0
    ux, uy = vx / vlen, vy / vlen

    rx = max(1.0, (bubble_x2 - bubble_x1) / 2.0)
    ry = max(1.0, (bubble_y2 - bubble_y1) / 2.0)
    # Punkt wyjścia na obrysie elipsy obszaru dymka
    t = 1.0 / math.sqrt((ux * ux) / (rx * rx) + (uy * uy) / (ry * ry))
    sx = ccx + ux * t
    sy = ccy + uy * t

    # Szerokość podstawy dziubka zależna od odległości
    dist_to_tip = math.hypot(bx - sx, by - sy)
    base_half = max(8.0, min(24.0, dist_to_tip * 0.18))
    nx, ny = -uy, ux  # wektor prostopadły
    p1 = (sx + nx * base_half, sy + ny * base_half)
    p2 = (sx - nx * base_half, sy - ny * base_half)
    p3 = (float(bx), float(by))  # dokładnie punkt kontrolny

    if bubble_mode == "thought":
        for i in range(1, thought_count + 1):
            t2 = i / (thought_count + 1)
            ex = sx + (bx - sx) * t2
            ey = sy + (by - sy) * t2
            # Bardziej "elisowate" bąbelki myśli: poziomo wydłużone + malejące ku punktowi
            rx_e = max(5.0, 20.0 * (1 - t2) + 5.0)
            ry_e = max(3.0, rx_e * 0.58)
            bubble_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            bubble_draw = ImageDraw.Draw(bubble_layer)
            bubble_draw.ellipse(
                [int(ex - rx_e), int(ey - ry_e), int(ex + rx_e), int(ey + ry_e)],
                fill=(*bubble_bg, int(alpha * 0.95)),
                outline=(*outline, alpha),
                width=2
            )
            # Obrót zgodnie z kierunkiem chmurka -> punkt kontrolny
            angle = math.degrees(math.atan2(by - sy, bx - sx))
            bubble_layer = bubble_layer.rotate(angle, center=(ex, ey), resample=Image.BICUBIC)
            txt_layer = Image.alpha_composite(txt_layer, bubble_layer)
    else:
        draw.polygon([(int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (int(p3[0]), int(p3[1]))],
                     fill=(*bubble_bg, int(alpha * 0.95)))
        draw.line([(int(p1[0]), int(p1[1])), (int(p3[0]), int(p3[1]))], fill=(*outline, alpha), width=3)
        draw.line([(int(p2[0]), int(p2[1])), (int(p3[0]), int(p3[1]))], fill=(*outline, alpha), width=3)
    
    # Tekst bardziej centralnie (lekko wyżej niż matematyczny środek)
    tx = int((bubble_x1 + bubble_x2 - text_width) / 2)
    ty = int((bubble_y1 + bubble_y2 - text_height) / 2 - max(6, text_height * 0.08))
    draw.text((tx, ty), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_comic(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                  pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Comic: grube outline (4px) + białe wnętrze (hollow)."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    outline = globals().get("_FX_OUTLINE", (0, 0, 0))
    
    # Grube outline
    for ox in range(-5, 6):
        for oy in range(-5, 6):
            if ox*ox + oy*oy <= 25:
                draw.text((x+ox, y+oy), text, font=font, fill=(*outline, alpha))
    
    # Białe wnętrze
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_neon(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                 pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Neon: glow efekt (blur radialny)."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    glow = globals().get("_FX_GLOW", color)
    
    # Tekst z glow (wielokrotny blur)
    for i in range(5, 0, -1):
        glow_color = tuple(int(c * (1 - i/5)) for c in glow)
        txt_tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_tmp = ImageDraw.Draw(txt_tmp)
        draw_tmp.text((x, y), text, font=font, fill=(*glow_color, alpha // (6-i)))
        txt_tmp = txt_tmp.filter(ImageFilter.GaussianBlur(radius=i*2))
        txt_layer = Image.alpha_composite(txt_layer, txt_tmp)
    
    # Jasny tekst na czołu
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_invert(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                   pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Invert: przezroczysty tekst, opaque tło."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    # Bbox
    bbox = _get_text_bbox(draw, text, font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Tło (opaque, odwrotny kolor)
    inv_color = globals().get("_FX_INVERT_BG", (255-color[0], 255-color[1], 255-color[2]))
    draw.rectangle([x-5, y-5, x+text_width+5, y+text_height+5],
                   fill=(*inv_color, alpha))
    
    # Tekst przezroczysty (tylko obrys)
    for ox in range(-2, 3):
        for oy in range(-2, 3):
            draw.text((x+ox, y+oy), text, font=font, fill=(*color, alpha//3))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_perspective_3d(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                           pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """3D Perspective: skośny tekst z градientem głębi."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    # Cienie (skośne)
    for i in range(10, 0, -1):
        shade = int(100 * (1 - i/10))
        offset_x = i * 0.7
        draw.text((x + offset_x, y + i), text, font=font, 
                 fill=(shade, shade, shade, alpha // 2))
    
    # Tekst główny
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_metallic(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                     pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Metallic: gradient + white highlight."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    # Ciemny kontekst
    for ox in range(-3, 4):
        for oy in range(-3, 4):
            shade = int(50 * (1 - abs(ox) / 3) * (1 - abs(oy) / 3))
            draw.text((x+ox, y+oy), text, font=font, fill=(shade, shade, shade, alpha))
    
    # Metaliczny tekst
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    # Highlight (biały, mały offset)
    draw.text((x-2, y-2), text, font=font, fill=(255, 255, 255, alpha // 3))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_watercolor(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                       pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Watercolor: miękkie, rozmyte krawędzie."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    # Blur
    txt_tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_tmp = ImageDraw.Draw(txt_tmp)
    draw_tmp.text((x, y), text, font=font, fill=(*color, alpha))
    txt_tmp = txt_tmp.filter(ImageFilter.GaussianBlur(radius=3))
    
    # Tekst ostre
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_tmp).convert("RGB")


def _render_glitch(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                   pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Glitch: distorsja cyfrowa (RGB shift)."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    # R channel (shift lewo)
    draw.text((x-3, y), text, font=font, fill=(255, 0, 0, alpha // 2))
    # G channel (normal)
    draw.text((x, y), text, font=font, fill=(0, 255, 0, alpha // 2))
    # B channel (shift prawo)
    draw.text((x+3, y), text, font=font, fill=(0, 0, 255, alpha // 2))
    
    # Main text
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_gold_emboss(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                        pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Gold Emboss: złoty 3D wytłoczony tekst."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    # Ciemny cień
    for i in range(5, 0, -1):
        draw.text((x+i, y+i), text, font=font, fill=(50, 40, 20, alpha // (6-i)))
    
    # Złoty tekst
    gold = (212, 175, 55)
    draw.text((x, y), text, font=font, fill=(*gold, alpha))
    
    # Biały highlight
    draw.text((x-1, y-1), text, font=font, fill=(255, 255, 200, alpha // 3))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_shadow_deep(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                        pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Shadow Deep: głębokie 3D cienie."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    shadow = globals().get("_FX_SHADOW", (80, 80, 80))
    
    # Wielowarstwowe cienie
    for i in range(15, 0, -1):
        shade = tuple(int(ch * (1 - i / 15)) for ch in shadow)
        draw.text((x + i//2, y + i), text, font=font, 
                 fill=(*shade, alpha // 2))
    
    # Tekst
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_retro(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                  pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Retro: bold + outline + vibrant."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    # Kolorowy outline
    outline_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    for idx, oc in enumerate(outline_colors):
        ox, oy = (idx % 2) * 3, (idx // 2) * 3
        draw.text((x + ox, y + oy), text, font=font, fill=(*oc, alpha // 2))
    
    # Main tekst
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_striped(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                    pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Striped: paskowany tekst."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    # Outline
    for ox in range(-3, 4):
        for oy in range(-3, 4):
            draw.text((x+ox, y+oy), text, font=font, fill=(0, 0, 0, alpha))
    
    # Paski
    bbox = _get_text_bbox(draw, text, font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    stripe_colors = [(255, 100, 0), (0, 100, 255), (255, 0, 100)]
    for i in range(0, text_width, 10):
        stripe_color = stripe_colors[(i // 10) % len(stripe_colors)]
        draw.rectangle([x + i, y, x + i + 5, y + text_height], fill=(*stripe_color, alpha))
    
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_electric_spark(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                           pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Electric Spark: żółty glow + niebieskie iskry."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    glow = globals().get("_FX_GLOW", (255, 255, 0))
    
    # Żółty glow
    for i in range(8, 0, -1):
        glow_alpha = int(alpha * (1 - i / 8) / 2)
        draw.text((x, y), text, font=font, fill=(*glow, glow_alpha))
        txt_tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_tmp = ImageDraw.Draw(txt_tmp)
        draw_tmp.text((x, y), text, font=font, fill=(*glow, glow_alpha))
        txt_tmp = txt_tmp.filter(ImageFilter.GaussianBlur(radius=i))
        txt_layer = Image.alpha_composite(txt_layer, txt_tmp)
    
    # Tekst + niebieskie iskry
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    # Iskry
    for i in range(10):
        spark_x = x + (i * 7) % 100
        spark_y = y - 10 + (i * 3) % 20
        draw.point((spark_x, spark_y), fill=(0, 150, 255, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


def _render_comic_stripes(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                          pos: tuple, color: tuple, alpha: int) -> Image.Image:
    """Comic Stripes: pasek komiksowy (żółty + czarny outline)."""
    W, H = img.size
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    x, y = int(pos[0]), int(pos[1])
    
    bbox = _get_text_bbox(draw, text, font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Żółte tło (komiksowy pasek)
    draw.rectangle([x - 10, y - 10, x + text_width + 10, y + text_height + 10],
                   fill=(255, 220, 0, alpha))
    
    # Czarny outline
    draw.rectangle([x - 10, y - 10, x + text_width + 10, y + text_height + 10],
                   outline=(0, 0, 0, alpha), width=3)
    
    # Tekst
    draw.text((x, y), text, font=font, fill=(*color, alpha))
    
    return Image.alpha_composite(img.convert("RGBA"), txt_layer).convert("RGB")


STYLE_RENDERERS = {
    "logo": _render_logo,
    "speech_bubble": _render_speech_bubble,
    "comic": _render_comic,
    "neon": _render_neon,
    "invert": _render_invert,
    "perspective_3d": _render_perspective_3d,
    "metallic": _render_metallic,
    "watercolor": _render_watercolor,
    "glitch": _render_glitch,
    "gold_emboss": _render_gold_emboss,
    "shadow_deep": _render_shadow_deep,
    "retro": _render_retro,
    "striped": _render_striped,
    "electric_spark": _render_electric_spark,
    "comic_stripes": _render_comic_stripes,
}


def is_available() -> bool:
    return True


def get_fonts_for_metadata() -> dict:
    """Zwróć dostępne czcionki dla METADATA."""
    _load_available_fonts()
    if not _AVAILABLE_FONTS:
        return {"DejaVuSans-Bold.ttf": "DejaVuSans-Bold"}
    return {font: font.replace(".ttf", "").replace(".otf", "") for font in _AVAILABLE_FONTS[:20]}


# Aktualizuj METADATA z dostępnymi czcionkami
METADATA["options"]["font"]["choices"] = get_fonts_for_metadata()


def process(image_bytes: bytes, options: dict) -> bytes:
    """Renderuj tekst na obrazku."""
    
    text = options.get("text", METADATA["options"]["text"]["default"])
    style = options.get("style", METADATA["options"]["style"]["default"])
    font_name = options.get("font", METADATA["options"]["font"]["default"])
    font_size = int(options.get("font_size", METADATA["options"]["font_size"]["default"]))
    pos_x = int(options.get("position_x", METADATA["options"]["position_x"]["default"]))
    pos_y = int(options.get("position_y", METADATA["options"]["position_y"]["default"]))
    scale_z = float(options.get("position_z", METADATA["options"]["position_z"]["default"]))
    bubble_px = int(options.get("bubble_point_x", METADATA["options"]["bubble_point_x"]["default"]))
    bubble_py = int(options.get("bubble_point_y", METADATA["options"]["bubble_point_y"]["default"]))
    bubble_irr = int(options.get("bubble_irregularity", METADATA["options"]["bubble_irregularity"]["default"]))
    bubble_mode = options.get("bubble_mode", METADATA["options"]["bubble_mode"]["default"])
    thought_count = int(options.get("thought_count", METADATA["options"]["thought_count"]["default"]))
    rotation = int(options.get("rotation", METADATA["options"]["rotation"]["default"]))
    color_r = int(options.get("color_r", METADATA["options"]["color_r"]["default"]))
    color_g = int(options.get("color_g", METADATA["options"]["color_g"]["default"]))
    color_b = int(options.get("color_b", METADATA["options"]["color_b"]["default"]))
    opacity = int(options.get("opacity", METADATA["options"]["opacity"]["default"]))
    outline_r = int(options.get("outline_r", METADATA["options"]["outline_r"]["default"]))
    outline_g = int(options.get("outline_g", METADATA["options"]["outline_g"]["default"]))
    outline_b = int(options.get("outline_b", METADATA["options"]["outline_b"]["default"]))
    glow_r = int(options.get("glow_r", METADATA["options"]["glow_r"]["default"]))
    glow_g = int(options.get("glow_g", METADATA["options"]["glow_g"]["default"]))
    glow_b = int(options.get("glow_b", METADATA["options"]["glow_b"]["default"]))
    shadow_r = int(options.get("shadow_r", METADATA["options"]["shadow_r"]["default"]))
    shadow_g = int(options.get("shadow_g", METADATA["options"]["shadow_g"]["default"]))
    shadow_b = int(options.get("shadow_b", METADATA["options"]["shadow_b"]["default"]))
    bubble_bg_r = int(options.get("bubble_bg_r", METADATA["options"]["bubble_bg_r"]["default"]))
    bubble_bg_g = int(options.get("bubble_bg_g", METADATA["options"]["bubble_bg_g"]["default"]))
    bubble_bg_b = int(options.get("bubble_bg_b", METADATA["options"]["bubble_bg_b"]["default"]))
    invert_bg_r = int(options.get("invert_bg_r", METADATA["options"]["invert_bg_r"]["default"]))
    invert_bg_g = int(options.get("invert_bg_g", METADATA["options"]["invert_bg_g"]["default"]))
    invert_bg_b = int(options.get("invert_bg_b", METADATA["options"]["invert_bg_b"]["default"]))
    
    # Załaduj obraz
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    W, H = img.size
    
    # Ogranicze pozycje do rozsądnych zakresów
    pos_x = max(0, min(pos_x, W - 50))
    pos_y = max(0, min(pos_y, H - 50))
    
    # Załaduj czcionkę ze skalą
    scaled_font_size = int(font_size * scale_z)
    font = _get_font(font_name, scaled_font_size)
    
    # Kolor
    color = (color_r, color_g, color_b)
    global _FX_OUTLINE, _FX_GLOW, _FX_SHADOW, _FX_BUBBLE_BG, _FX_INVERT_BG, _FX_BUBBLE_IRR, _FX_BUBBLE_MODE, _FX_THOUGHT_COUNT
    _FX_OUTLINE = (outline_r, outline_g, outline_b)
    _FX_GLOW = (glow_r, glow_g, glow_b)
    _FX_SHADOW = (shadow_r, shadow_g, shadow_b)
    _FX_BUBBLE_BG = (bubble_bg_r, bubble_bg_g, bubble_bg_b)
    _FX_INVERT_BG = (invert_bg_r, invert_bg_g, invert_bg_b)
    _FX_BUBBLE_IRR = bubble_irr
    _FX_BUBBLE_MODE = bubble_mode
    _FX_THOUGHT_COUNT = thought_count
    alpha = int(opacity * 255 // 100)
    
    # Renderer
    renderer = STYLE_RENDERERS.get(style, STYLE_RENDERERS["logo"])
    
    if style == "speech_bubble":
        result_img = renderer(img, text, font, (pos_x, pos_y), color, alpha, 
                            (bubble_px, bubble_py))
    else:
        result_img = renderer(img, text, font, (pos_x, pos_y), color, alpha)
    
    # Rotacja
    if rotation != 0:
        result_img = result_img.rotate(rotation, expand=False, fillcolor=(255, 255, 255))
    
    # Zapisz
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    return buf.getvalue()
    outline = globals().get("_FX_OUTLINE", (0, 0, 0))
    glow = globals().get("_FX_GLOW", color)
    shadow = globals().get("_FX_SHADOW", (0, 0, 0))
    glow = globals().get("_FX_GLOW", (255, 255, 0))
