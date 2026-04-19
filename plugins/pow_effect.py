"""
Plugin: POW Effect
Usuwa tło i opakowuje pierwszy plan w animowaną obwolutę w stylu komiksu POW!
Kształt obwoluty jest dopasowany do kształtu pierwszego planu.
"""

METADATA = {
    "id": "pow_effect",
    "name": "💥 POW! Effect",
    "description": "Animowany GIF - usuwa tło i opakowuje pierwszy plan w komiksową obwolutę POW! dopasowaną do kształtu obiektu",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "💥",
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
        "pow_style": {
            "type": "select",
            "label": "Styl POW",
            "choices": {
                "classic": "💥 Classic POW (czerwono-żółty)",
                "electric": "⚡ Electric (niebieskobiały)",
                "toxic": "☢️ Toxic (zielony)",
                "inferno": "🔥 Inferno (pomarańczowo-czerwony)",
            },
            "default": "classic",
        },
        "spike_count": {
            "type": "select",
            "label": "Liczba kolców",
            "choices": {
                "8": "8 kolców (spokojny)",
                "12": "12 kolców (standard)",
                "16": "16 kolców (dynamiczny)",
                "24": "24 kolców (agresywny)",
            },
            "default": "12",
        },
        "spike_size": {
            "type": "select",
            "label": "Wielkość kolców",
            "choices": {
                "small": "Małe",
                "medium": "Średnie",
                "large": "Duże",
                "xlarge": "Gigantyczne",
            },
            "default": "medium",
        },
        "frames": {
            "type": "select",
            "label": "Liczba klatek",
            "choices": {
                "8": "8 klatek",
                "12": "12 klatek",
                "16": "16 klatek",
                "24": "24 klatki",
            },
            "default": "12",
        },
        "speed": {
            "type": "select",
            "label": "Szybkość animacji",
            "choices": {
                "50": "Bardzo szybka (50ms)",
                "80": "Szybka (80ms)",
                "120": "Normalna (120ms)",
                "200": "Wolna (200ms)",
            },
            "default": "80",
        },
        "background": {
            "type": "select",
            "label": "Tło",
            "choices": {
                "white": "Białe",
                "black": "Czarne",
                "gray": "Szare",
                "original": "Oryginalne",
                "transparent": "Przezroczyste",
            },
            "default": "white",
        },
        "outline_width": {
            "type": "select",
            "label": "Grubość obrysu",
            "choices": {
                "2": "Cienki",
                "4": "Normalny",
                "6": "Gruby",
                "8": "Bardzo gruby",
            },
            "default": "4",
        },
    },
}

import io
import math
import threading
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

try:
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_sessions: dict = {}
_lock = threading.Lock()

# ── Style POW ────────────────────────────────────────────────────────────────

POW_STYLES = {
    "classic": {
        "colors": [
            (255, 30, 0),    # intensywna czerwień
            (255, 60, 0),
            (220, 0, 0),
        ],
        "inner_color": (255, 220, 0),   # żółty środek
        "outline_color": (0, 0, 0),
        "spike_color_cycle": [
            (255, 30, 0), (255, 80, 0), (220, 0, 0), (255, 50, 30),
        ],
    },
    "electric": {
        "colors": [
            (0, 100, 255),
            (30, 150, 255),
            (0, 60, 200),
        ],
        "inner_color": (200, 240, 255),
        "outline_color": (255, 255, 255),
        "spike_color_cycle": [
            (0, 100, 255), (100, 200, 255), (0, 150, 255), (50, 50, 200),
        ],
    },
    "toxic": {
        "colors": [
            (0, 180, 0),
            (50, 220, 0),
            (0, 140, 0),
        ],
        "inner_color": (180, 255, 100),
        "outline_color": (0, 40, 0),
        "spike_color_cycle": [
            (0, 180, 0), (80, 255, 0), (0, 220, 50), (100, 200, 0),
        ],
    },
    "inferno": {
        "colors": [
            (255, 80, 0),
            (255, 140, 0),
            (200, 40, 0),
        ],
        "inner_color": (255, 240, 100),
        "outline_color": (80, 0, 0),
        "spike_color_cycle": [
            (255, 80, 0), (255, 200, 0), (220, 60, 0), (255, 120, 0),
        ],
    },
}

SPIKE_SIZES = {
    "small":  0.08,
    "medium": 0.14,
    "large":  0.22,
    "xlarge": 0.32,
}


def _get_session(model_name: str):
    with _lock:
        if model_name not in _sessions:
            _sessions[model_name] = new_session(model_name)
        return _sessions[model_name]


def _get_fg_bounds(alpha_mask: Image.Image) -> tuple:
    """Znajdź bounding box pierwszego planu."""
    alpha_arr = np.array(alpha_mask)
    rows = np.any(alpha_arr > 30, axis=1)
    cols = np.any(alpha_arr > 30, axis=0)
    if not np.any(rows) or not np.any(cols):
        return (0, 0, alpha_mask.width, alpha_mask.height)
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    return (int(cmin), int(rmin), int(cmax), int(rmax))


def _compute_fg_silhouette(alpha_mask: Image.Image, dilation_px: int) -> Image.Image:
    """Dylatuj maskę alpha o dilation_px pikseli — tworzy rozszerzoną sylwetkę."""
    # Użyj prostego GaussianBlur + threshold jako aproksymacja dylatacji
    dilated = alpha_mask.filter(ImageFilter.MaxFilter(dilation_px * 2 + 1))
    return dilated


def _polar_to_cart(cx: float, cy: float, r: float, angle_rad: float) -> tuple:
    return (cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad))


def _build_pow_polygon(
    alpha_arr: np.ndarray,
    W: int, H: int,
    num_spikes: int,
    spike_amplitude: float,
    phase_offset: float,
    irregularity_seed: float,
) -> list:
    """
    Buduje wielokąt POW dopasowany do kształtu alfa maski.
    
    Algorytm:
    1. Dla każdego z num_spikes * 2 kątów - wyznacz odległość od centrum fg do krawędzi maski
    2. Przemień to w nieregularne kolce o różnych długościach
    3. Dodaj animowaną fazę
    """
    # Centrum masy pierwszego planu
    fg_pixels = alpha_arr > 30
    if not np.any(fg_pixels):
        cx, cy = W / 2, H / 2
    else:
        ys, xs = np.where(fg_pixels)
        cx = float(xs.mean())
        cy = float(ys.mean())

    # Wyznacz odległości od centrum do krawędzi maski dla każdego kąta
    total_points = num_spikes * 2
    points = []

    # Nieregularność amplitud (seed-based pseudo-random per klatkę)
    rng = np.random.RandomState(int(irregularity_seed * 1000) % 9999)
    # Każdy kolec ma swoją "bazową" amplitudę (nieregularność kształtu)
    spike_amps = rng.uniform(0.7, 1.3, num_spikes)
    # Każdy kolec ma swój "fazowy" offset (różne tempo wzrostu)
    spike_phases = rng.uniform(0, math.pi * 2, num_spikes)

    # Precompute numpy grids raz dla wszystkich kątów (szybki raycast)
    ys_grid, xs_grid = np.mgrid[0:H, 0:W]
    dx_all = xs_grid.astype(np.float32) - cx
    dy_all = ys_grid.astype(np.float32) - cy
    dist_grid = np.sqrt(dx_all ** 2 + dy_all ** 2)
    fg_bool = alpha_arr > 30

    for i in range(total_points):
        angle = (2 * math.pi * i / total_points) + phase_offset
        is_spike = (i % 2 == 0)
        spike_idx = i // 2

        # Szybki raycast numpy: piksele fg w wąskim stożku kąta ±~8.6°
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dot   = dx_all * cos_a + dy_all * sin_a
        cross = np.abs(dx_all * sin_a - dy_all * cos_a)
        with np.errstate(invalid='ignore', divide='ignore'):
            sin_ang = np.where(dist_grid > 0.5, cross / dist_grid, 1.0)
        on_ray = fg_bool & (dot > 0) & (sin_ang < 0.15)
        base_r = float(dist_grid[on_ray].max()) if np.any(on_ray) else 0.0

        if base_r < 1:
            base_r = min(W, H) * 0.1

        if is_spike:
            # Kolec: wychodzi POZA krawędź maski
            # Animacja: każdy kolec puluje ze swoją fazą
            anim_factor = 0.5 + 0.5 * math.sin(phase_offset * 2 + spike_phases[spike_idx])
            amp_mult = spike_amps[spike_idx]
            spike_start_offset = W * 0.01  # 1% szerokości obrazu za obwiedni
            r = base_r + spike_start_offset + spike_amplitude * amp_mult * (0.6 + 0.4 * anim_factor)
            # Dodaj trochę "zaokrąglenia" — kolce nie są idealnymi trójkątami
            noise = 1.0 + 0.08 * math.sin(angle * 7 + phase_offset * 3)
            r *= noise
        else:
            # Dolina: trochę wciśnięta do środka kształtu
            valley_depth = 0.15
            r = base_r * (1.0 - valley_depth * (0.5 + 0.5 * math.sin(phase_offset + spike_idx)))
            r = max(r, base_r * 0.5)

        pt = _polar_to_cart(cx, cy, r, angle)
        points.append(pt)

    return points


def _draw_pow_frame(
    W: int, H: int,
    alpha_arr: np.ndarray,
    alpha_mask: Image.Image,
    fg_rgba: Image.Image,
    bg_frame: Image.Image,
    frame_idx: int,
    num_frames: int,
    style: dict,
    num_spikes: int,
    spike_amplitude: float,
    outline_width: int,
    fg_silhouette_cached: Image.Image = None,
) -> Image.Image:
    """Renderuje pojedynczą klatkę POW."""

    # Faza animacji (0..2π)
    phase = (2 * math.pi * frame_idx / num_frames)

    # Buduj polygon POW
    polygon = _build_pow_polygon(
        alpha_arr, W, H,
        num_spikes=num_spikes,
        spike_amplitude=spike_amplitude,
        phase_offset=phase,
        irregularity_seed=0.42,  # stały seed = stały kształt, tylko faza się zmienia
    )

    # Wybierz kolor na tę klatkę (cyklicznie)
    color_idx = frame_idx % len(style["spike_color_cycle"])
    pow_color = style["spike_color_cycle"][color_idx]
    inner_color = style["inner_color"]
    outline_color = style["outline_color"]

    # Stwórz warstwę POW (RGBA)
    pow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(pow_layer)

    # Zewnętrzna warstwa (kolce) — grubsza
    polygon_int = [(int(p[0]), int(p[1])) for p in polygon]

    # 1. Obrys (czarny) - grubszy polygon
    draw.polygon(polygon_int, fill=(*outline_color, 255))

    # 2. Główne wypełnienie (kolor POW) — polygon trochę mniejszy
    inner_polygon = _shrink_polygon(polygon, W / 2, H / 2, alpha_arr, shrink_px=outline_width)
    inner_polygon_int = [(int(p[0]), int(p[1])) for p in inner_polygon]
    draw.polygon(inner_polygon_int, fill=(*pow_color, 255))

    # 3. Wewnętrzny gradient/fill (jaśniejszy kolor) — wokół samej sylwetki fg + margin
    # Używamy dylatowanej maski fg (zwrócona z cache'a!)
    sil_arr = np.array(fg_silhouette_cached)
    inner_mask = Image.fromarray((sil_arr > 30).astype(np.uint8) * 255, mode="L")

    # Paste inner_color na pow_layer tam gdzie fg_silhouette
    inner_fill = Image.new("RGBA", (W, H), (*inner_color, 255))
    pow_layer.paste(inner_fill, mask=inner_mask)

    # Składanie kompozycji: tło + POW + fg
    canvas = bg_frame.copy().convert("RGBA")
    canvas = Image.alpha_composite(canvas, pow_layer)
    # Naklejamy pierwszy plan
    canvas.paste(fg_rgba, mask=alpha_mask)

    return canvas.convert("RGB")


def _shrink_polygon(polygon: list, cx: float, cy: float, alpha_arr, shrink_px: float) -> list:
    """Przeskaluj polygon w kierunku centrum o shrink_px pikseli."""
    result = []
    for px, py in polygon:
        dx = px - cx
        dy = py - cy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1:
            result.append((px, py))
            continue
        new_dist = max(0, dist - shrink_px)
        result.append((cx + dx / dist * new_dist, cy + dy / dist * new_dist))
    return result


def _prepare_bg(W: int, H: int, bg_type: str, original_img: Image.Image) -> Image.Image:
    """Przygotuj tło (bez inpainting — szybko)."""
    if bg_type == "original":
        return original_img.convert("RGBA")
    elif bg_type == "white":
        return Image.new("RGBA", (W, H), (255, 255, 255, 255))
    elif bg_type == "black":
        return Image.new("RGBA", (W, H), (0, 0, 0, 255))
    elif bg_type == "gray":
        return Image.new("RGBA", (W, H), (128, 128, 128, 255))
    else:  # transparent/checkerboard
        bg = Image.new("RGBA", (W, H), (64, 64, 64, 255))
        draw = ImageDraw.Draw(bg)
        for y in range(0, H, 16):
            for x in range(0, W, 16):
                if ((x // 16) + (y // 16)) % 2 == 0:
                    draw.rectangle([x, y, x + 15, y + 15], fill=(200, 200, 200, 255))
        return bg


def is_available() -> bool:
    return _AVAILABLE


def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name  = options.get("model",         METADATA["options"]["model"]["default"])
    pow_style   = options.get("pow_style",     METADATA["options"]["pow_style"]["default"])
    spike_count = int(options.get("spike_count", METADATA["options"]["spike_count"]["default"]))
    spike_size  = options.get("spike_size",    METADATA["options"]["spike_size"]["default"])
    num_frames  = int(options.get("frames",    METADATA["options"]["frames"]["default"]))
    speed_ms    = int(options.get("speed",     METADATA["options"]["speed"]["default"]))
    bg_type     = options.get("background",    METADATA["options"]["background"]["default"])
    outline_w   = int(options.get("outline_width", METADATA["options"]["outline_width"]["default"]))

    style = POW_STYLES.get(pow_style, POW_STYLES["classic"])
    spike_amp_factor = SPIKE_SIZES.get(spike_size, SPIKE_SIZES["medium"])

    # ── 1. Usuń tło ───────────────────────────────────────────────────────────
    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    W, H = img_original.size

    session = _get_session(model_name)
    fg_rgba = remove(img_original, session=session)
    if fg_rgba.mode != "RGBA":
        fg_rgba = fg_rgba.convert("RGBA")

    # Alpha maska
    _, _, _, alpha_mask = fg_rgba.split()

    # ── 2. Dane do animacji (liczymy raz!) ───────────────────────────────────
    alpha_arr = np.array(alpha_mask, dtype=np.uint8)

    # Amplituda kolców jako px (proporcja do rozmiaru obrazu)
    spike_amplitude = spike_amp_factor * max(W, H)

    # Tło (raz przed pętlą!)
    bg_base = _prepare_bg(W, H, bg_type, img_original)

    # Dylatowana maska fg — oblicz RAZ przed pętlą (nie zmienia się!)
    fg_silhouette = _compute_fg_silhouette(alpha_mask, dilation_px=max(4, outline_w))

    # ── 3. Generuj klatki ────────────────────────────────────────────────────
    frames = []
    for i in range(num_frames):
        frame_rgb = _draw_pow_frame(
            W=W, H=H,
            alpha_arr=alpha_arr,
            alpha_mask=alpha_mask,
            fg_rgba=fg_rgba,
            bg_frame=bg_base,
            frame_idx=i,
            num_frames=num_frames,
            style=style,
            num_spikes=spike_count,
            spike_amplitude=spike_amplitude,
            outline_width=outline_w,
            fg_silhouette_cached=fg_silhouette,
        )
        frames.append(frame_rgb)

    # ── 4. Zapisz GIF ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=speed_ms,
        loop=0,
        optimize=False,
    )
    return buf.getvalue()
