"""
Plugin: Neon Glow
Dodaje efekt neonowego świecenia + elektryczna otoczka (comic-book style).
"""

METADATA = {
    "id": "neon_glow",
    "name": "🎬 Neon Glow",
    "description": "Animowany GIF - usuwa tło i dodaje skrzący się efekt neonowego świecenia",
    "version": "2.0.0",
    "author": "Radek",
    "icon": "⚡",
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
        "glow_intensity": {
            "type": "select",
            "label": "Intensywność świecenia",
            "choices": {
                "1": "Subtelne",
                "2": "Normalne",
                "3": "Mocne",
                "4": "Ekstremalne",
            },
            "default": "2",
        },
        "glow_color": {
            "type": "select",
            "label": "Kolor świecenia",
            "choices": {
                "cyan": "Cyan (niebieski)",
                "pink": "Pink (różowy)",
                "green": "Green (zielony)",
                "purple": "Purple (purpurowy)",
                "original": "Złoty",
            },
            "default": "cyan",
        },
        "blur_radius": {
            "type": "select",
            "label": "Rozmycie glow",
            "choices": {
                "3": "Ostre",
                "5": "Normalne",
                "7": "Mękkie",
                "10": "Bardzo mękkie",
            },
            "default": "5",
        },
        "animation": {
            "type": "select",
            "label": "Animacja",
            "choices": {
                "no": "Brak (statyczne)",
                "pulse": "Tętnięcie (pulsowanie)",
                "glow_shift": "Skrzący się neon (zmiana intensity)",
                "aurora_borealis": "⚡ Aurora Borealis (elektryczna otoczka)",
                "pow_effect": "💥 POW Effect! (komiksowe wybuchy z kolcami)",
            },
            "default": "glow_shift",
        },
        "anim_speed": {
            "type": "select",
            "label": "Szybkość animacji",
            "choices": {
                "fast": "Szybka (50ms)",
                "normal": "Normalna (100ms)",
                "slow": "Wolna (200ms)",
            },
            "default": "normal",
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
        "spike_height": {
            "type": "select",
            "label": "⚡ Wysokość kolców [Aurora]",
            "choices": {
                "2":  "Miniaturowe (2%)",
                "4":  "Małe (4%)",
                "8":  "Normalne (8%)",
                "14": "Duże (14%)",
                "22": "Ogromne (22%)",
                "35": "Monstrualne (35%)",
            },
            "default": "8",
        },
        "spike_density": {
            "type": "select",
            "label": "⚡ Częstość kolców [Aurora]",
            "choices": {
                "0.5": "Bardzo rzadkie (wielkie obszary)",
                "1.0": "Rzadkie",
                "2.0": "Normalne",
                "4.0": "Gęste",
                "8.0": "Bardzo gęste (drobne kolce)",
            },
            "default": "2.0",
        },
        "spike_irregularity": {
            "type": "select",
            "label": "⚡ Nieregularność kolców [Aurora]",
            "choices": {
                "0.0": "Równomierne (gładka obwódka)",
                "0.3": "Lekko nieregularne",
                "0.6": "Nieregularne (komiks)",
                "0.9": "Bardzo chaotyczne",
                "1.0": "Maksymalny chaos",
            },
            "default": "0.6",
        },
    },
}

import io
import math
import threading
from PIL import Image, ImageFilter
import numpy as np
from scipy import ndimage
from plugin_utils import prepare_background

try:
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_sessions: dict = {}
_lock = threading.Lock()


def is_available() -> bool:
    return _AVAILABLE


def _get_session(model_name: str):
    with _lock:
        if model_name not in _sessions:
            _sessions[model_name] = new_session(model_name)
        return _sessions[model_name]


def _apply_color_tint(img: Image.Image, color: str) -> Image.Image:
    color_map = {
        "cyan": (0, 255, 255),
        "pink": (255, 0, 255),
        "green": (0, 255, 0),
        "purple": (128, 0, 255),
    }
    if color not in color_map or color == "original":
        return img

    img_array = np.array(img.convert("RGB"), dtype=np.float32)
    r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]

    if color == "cyan":
        g = np.minimum(g * 1.3, 255)
        b = np.minimum(b * 1.3, 255)
    elif color == "pink":
        r = np.minimum(r * 1.3, 255)
        b = np.minimum(b * 1.3, 255)
    elif color == "green":
        g = np.minimum(g * 1.4, 255)
    elif color == "purple":
        r = np.minimum(r * 1.2, 255)
        b = np.minimum(b * 1.2, 255)

    img_array[:, :, 0] = r
    img_array[:, :, 1] = g
    img_array[:, :, 2] = b
    return Image.fromarray(np.uint8(img_array))


def _precompute_distances(
    alpha_array: np.ndarray,
) -> tuple:
    """
    Oblicz distance transformy RAZ przed pętlą klatek.
    Zwraca (binary, dist_outside, dist_inside, avg_dim).
    """
    binary       = alpha_array > 128
    dist_outside = ndimage.distance_transform_edt(~binary)
    dist_inside  = ndimage.distance_transform_edt(binary)
    return binary, dist_outside, dist_inside


def _generate_electric_aura_frame(
    dist_outside: np.ndarray,
    dist_inside: np.ndarray,
    width: int,
    height: int,
    frame_idx: int,
    num_frames: int,
    glow_color: str,
    spike_height_pct: float = 8.0,
    spike_density: float = 2.0,
    spike_irregularity: float = 0.6,
) -> Image.Image:
    """
    Elektryczna otoczka komiksowa - animowane 'spikes' na krawędzi konturu.
    Przyjmuje preobliczone dist_outside / dist_inside (stałe dla wszystkich klatek).

    Parametry użytkownika:
      spike_height_pct  – max wysokość kolca jako % avg_dim (np. 8 → 8%)
      spike_density     – skala przestrzenna szumu; wyżej = drobniejsze, gęstsze kolce
      spike_irregularity – 0.0 = równomierna obwódka, 1.0 = pełny chaos kształtu
    """
    rng = np.random.default_rng(frame_idx * 1337 + 42)
    avg_dim = (width + height) / 2.0

    # Wysokość kolców w pikselach
    spike_max  = max(4, int(avg_dim * spike_height_pct / 100.0))
    # Minimalna grubość: 25% maksymalnej (żeby zawsze była widoczna otoczka)
    spike_min  = max(2, int(spike_max * 0.25))
    inner_glow = max(2, int(spike_max * 0.2))

    # Wieloskalowy szum – skala bazowa skaluje się przez spike_density
    # Wyższa density → krótszy okres fali → drobniejsze, gęstsze wzorce
    y_c, x_c = np.mgrid[0:height, 0:width]
    phase = (frame_idx / num_frames) * 2 * math.pi

    off0 = rng.uniform(0, 2 * math.pi)
    off1 = rng.uniform(0, 2 * math.pi)
    off2 = rng.uniform(0, 2 * math.pi)

    # Bazowe okresy szumu: mnożone przez density (density=1 → oryginalne wartości)
    base_scale = avg_dim / spike_density

    n0 = (np.sin(x_c / (base_scale * 0.04) + phase * 3.7 + off0) *
          np.cos(y_c / (base_scale * 0.05) - phase * 2.3))
    n1 = (np.sin(x_c / (base_scale * 0.02) - phase * 5.1 + off1) *
          np.cos(y_c / (base_scale * 0.03) + phase * 4.2))
    n2 = (np.sin(x_c / (base_scale * 0.08) + phase * 1.8 + off2) *
          np.cos(y_c / (base_scale * 0.06) - phase * 2.9))

    # Nieregularność: jak bardzo n1 i n2 (wysokoczęstotliwościowe) dominują nad n0
    # irregularity=0 → tylko n0 (gładka sinusoida, równa obwódka)
    # irregularity=1 → równe wagi wszystkich + dodatkowy chaos
    irr = spike_irregularity
    w0 = 1.0 - irr * 0.6          # waga składowej niskiej częstotliwości
    w1 = irr * 0.5                 # waga średniej
    w2 = irr * 0.4                 # waga wysokiej
    total_w = w0 + w1 + w2 + 1e-6

    noise = (n0 * w0 + n1 * w1 + n2 * w2) / total_w

    # Dla wysokiej nieregularności dodaj ostry nieliniowy kształt (spiky peaks)
    if irr > 0.5:
        # Podnieś szum do potęgi < 1 → wyostrza szczyty, zagłębia doliny
        noise_pos = (noise + 1.0) / 2.0  # [0,1]
        sharpness = 1.0 - (irr - 0.5) * 0.8   # [0.6 .. 1.0] → bardziej szpiczaste przy max irr
        noise = noise_pos ** sharpness * 2.0 - 1.0  # z powrotem do [-1, 1]

    noise = (noise + 1.0) / 2.0  # normalizuj do [0, 1]

    # Lokalna grubość kolca per-piksel
    spike_thickness = spike_min + noise * (spike_max - spike_min)

    # Maska elektryczna
    electric_outer = (dist_outside > 0) & (dist_outside <= spike_thickness)
    electric_inner = (dist_inside  > 0) & (dist_inside  <= inner_glow)
    electric_mask  = electric_outer | electric_inner

    # Gradient intensywności
    outer_int = np.where(electric_outer,
                         1.0 - dist_outside / np.maximum(spike_thickness, 1.0),
                         0.0)
    inner_int = np.where(electric_inner,
                         1.0 - dist_inside / float(inner_glow + 1),
                         0.0)
    intensity = np.clip(outer_int + inner_int * 0.6, 0.0, 1.0)

    # Kolory
    color_presets = {
        "cyan":     ((0, 180, 255),   (160, 255, 255)),
        "pink":     ((255, 30, 180),  (255, 160, 255)),
        "green":    ((0, 220, 60),    (180, 255, 120)),
        "purple":   ((160, 0, 255),   (220, 120, 255)),
        "original": ((255, 180, 0),   (255, 255, 180)),
    }
    c_dark, c_bright = color_presets.get(glow_color, color_presets["cyan"])

    brightness = 0.75 + 0.25 * math.sin(phase * 2.5)

    r_out = np.clip((c_dark[0] + (c_bright[0] - c_dark[0]) * intensity) * brightness, 0, 255).astype(np.uint8)
    g_out = np.clip((c_dark[1] + (c_bright[1] - c_dark[1]) * intensity) * brightness, 0, 255).astype(np.uint8)
    b_out = np.clip((c_dark[2] + (c_bright[2] - c_dark[2]) * intensity) * brightness, 0, 255).astype(np.uint8)
    a_out = np.clip(intensity * 240 * brightness, 0, 255).astype(np.uint8)
    a_out = a_out * electric_mask.astype(np.uint8)

    aura_rgba = np.zeros((height, width, 4), dtype=np.uint8)
    aura_rgba[:, :, 0] = r_out
    aura_rgba[:, :, 1] = g_out
    aura_rgba[:, :, 2] = b_out
    aura_rgba[:, :, 3] = a_out

    aura_img = Image.fromarray(aura_rgba, "RGBA")
    # Blur glow – lekko większy gdy kolce są duże
    blur_r = max(1.0, min(3.0, spike_max / avg_dim * 20))
    aura_img = aura_img.filter(ImageFilter.GaussianBlur(radius=blur_r))
    return aura_img


def _generate_pow_effect_frame(
    alpha_array: np.ndarray,
    width: int,
    height: int,
    frame_idx: int,
    num_frames: int,
    glow_color: str,
    pow_intensity: float = 1.2,
) -> Image.Image:
    """
    POW! efekt komiksowy - komiksowe wybuchy z animowanymi kolcami.
    Kolce nieregularnie rosną i zmniejszają się przez animację.
    
    Parametry:
      pow_intensity – siła efektu (1.0-2.0), jak bardzo duże są kolce
    """
    rng = np.random.default_rng(42)  # Stały seed dla spójności
    avg_dim = (width + height) / 2.0
    
    # Faza animacji: 0-1 (pulsuje: rosnące kolce)
    progress = (frame_idx / (num_frames - 1)) if num_frames > 1 else 0
    
    # Animacja kolców - nieregularne pulsowanie
    # Każda klatka ma inny szum, co daje wrażenie chaosu
    frame_noise = rng.random() * 0.3
    pulse = 0.4 + 0.6 * math.sin(progress * math.pi * 2) + frame_noise
    pulse = max(0.2, min(1.0, pulse))  # Clamp [0.2 - 1.0]
    
    # Wysokość kolców - rosnące i malejące
    max_spike = int(avg_dim * 0.12 * pow_intensity)
    min_spike = int(avg_dim * 0.04 * pow_intensity)
    current_spike = min_spike + int((max_spike - min_spike) * pulse)
    
    # Distance transform
    binary = alpha_array > 128
    dist_outside = ndimage.distance_transform_edt(~binary)
    dist_inside = ndimage.distance_transform_edt(binary)
    
    # Generuj szpiczaste kolce (POW style)
    y_c, x_c = np.mgrid[0:height, 0:width]
    
    # Liczne szumy dla bardzo nieregularnych kolców
    n_freq1 = np.sin(x_c / (avg_dim * 0.15) + frame_idx * 0.8) * np.cos(y_c / (avg_dim * 0.15) - frame_idx * 0.6)
    n_freq2 = np.sin(x_c / (avg_dim * 0.08) - frame_idx * 1.2) * np.cos(y_c / (avg_dim * 0.08) + frame_idx * 0.9)
    n_freq3 = np.sin(x_c / (avg_dim * 0.25) + frame_idx * 0.4) * np.cos(y_c / (avg_dim * 0.25) - frame_idx * 0.3)
    
    # Mieszaj szumy dla chaosu
    noise = (n_freq1 * 0.5 + n_freq2 * 0.35 + n_freq3 * 0.15)
    noise = (noise + 1.0) / 2.0  # [0, 1]
    
    # Wyostrz szumy dla bardziej spiczastych kolców
    noise = noise ** 0.65  # Bardziej spiczaste szczyty
    
    # Grubość kolców per-piksel
    spike_thickness = min_spike + noise * (current_spike - min_spike)
    
    # Zewnętrzna i wewnętrzna część efektu
    outer = (dist_outside > 0) & (dist_outside <= spike_thickness)
    inner = (dist_inside > 0) & (dist_inside <= max(2, int(current_spike * 0.15)))
    
    # Intensywność - bardziej agresywna niż aurora
    outer_intensity = np.where(outer, 1.0 - dist_outside / np.maximum(spike_thickness, 1.0), 0.0)
    inner_intensity = np.where(inner, 1.0 - dist_inside / float(max(3, int(current_spike * 0.15)) + 1), 0.0)
    intensity = np.clip(outer_intensity + inner_intensity * 0.8, 0.0, 1.0)
    
    # Kolory POW - agresywne i żywe
    color_presets = {
        "cyan":     ((0, 220, 255),   (180, 255, 255)),
        "pink":     ((255, 50, 200),  (255, 180, 255)),
        "green":    ((50, 255, 100),  (200, 255, 150)),
        "purple":   ((200, 50, 255),  (240, 160, 255)),
        "original": ((255, 200, 0),   (255, 255, 100)),
    }
    c_dark, c_bright = color_presets.get(glow_color, color_presets["cyan"])
    
    # Pulsujący brightness - bardziej dramatyczny
    brightness = 0.8 + 0.4 * pulse + 0.1 * math.sin(frame_idx * 0.5)
    brightness = min(1.5, brightness)
    
    r_out = np.clip((c_dark[0] + (c_bright[0] - c_dark[0]) * intensity) * brightness, 0, 255).astype(np.uint8)
    g_out = np.clip((c_dark[1] + (c_bright[1] - c_dark[1]) * intensity) * brightness, 0, 255).astype(np.uint8)
    b_out = np.clip((c_dark[2] + (c_bright[2] - c_dark[2]) * intensity) * brightness, 0, 255).astype(np.uint8)
    a_out = np.clip(intensity * 250 * brightness, 0, 255).astype(np.uint8)
    a_out = a_out * (outer | inner).astype(np.uint8)
    
    pow_rgba = np.zeros((height, width, 4), dtype=np.uint8)
    pow_rgba[:, :, 0] = r_out
    pow_rgba[:, :, 1] = g_out
    pow_rgba[:, :, 2] = b_out
    pow_rgba[:, :, 3] = a_out
    
    pow_img = Image.fromarray(pow_rgba, "RGBA")
    # Mniejsze rozmycie dla bardziej ostrych kolców
    pow_img = pow_img.filter(ImageFilter.GaussianBlur(radius=1.5))
    return pow_img


def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name        = options.get("model",               METADATA["options"]["model"]["default"])
    glow_intensity    = int(options.get("glow_intensity",   METADATA["options"]["glow_intensity"]["default"]))
    glow_color        = options.get("glow_color",           METADATA["options"]["glow_color"]["default"])
    blur_radius       = int(options.get("blur_radius",       METADATA["options"]["blur_radius"]["default"]))
    animation         = options.get("animation",            METADATA["options"]["animation"]["default"])
    anim_speed_str    = options.get("anim_speed",           METADATA["options"]["anim_speed"]["default"])
    background        = options.get("background",           METADATA["options"]["background"]["default"])
    edge_feather      = int(options.get("edge_feather",      METADATA["options"]["edge_feather"]["default"]))
    spike_height_pct  = float(options.get("spike_height",   METADATA["options"]["spike_height"]["default"]))
    spike_density     = float(options.get("spike_density",  METADATA["options"]["spike_density"]["default"]))
    spike_irregularity = float(options.get("spike_irregularity", METADATA["options"]["spike_irregularity"]["default"]))

    anim_speed_map = {"fast": 50, "normal": 100, "slow": 200}
    frame_duration = anim_speed_map.get(anim_speed_str, 100)
    num_frames = 12

    img_original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    session      = _get_session(model_name)
    img_removed  = remove(img_original.convert("RGBA"), session=session)
    if img_removed.mode != "RGBA":
        img_removed = img_removed.convert("RGBA")

    _, _, _, alpha_mask = img_removed.split()
    from plugin_utils import feather_alpha_mask
    alpha_mask = feather_alpha_mask(alpha_mask, edge_feather)

    if glow_color != "original":
        rgb_part = _apply_color_tint(img_removed.convert("RGB"), glow_color)
        img_removed = rgb_part.convert("RGBA")
        img_removed.putalpha(alpha_mask)

    # ── Statyczne ──────────────────────────────────────────────────────────
    if animation == "no":
        bg = prepare_background(img_original.size, background, img_original)
        glow_a = alpha_mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        for _ in range(glow_intensity - 1):
            glow_a = glow_a.filter(ImageFilter.GaussianBlur(radius=1))
        glow_overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        glow_overlay.putalpha(glow_a)
        bg_rgb = bg.convert("RGB")
        bg_rgb.paste(img_removed.convert("RGB"), mask=alpha_mask)
        buf = io.BytesIO()
        bg_rgb.save(buf, format="PNG")
        return buf.getvalue()

    # ── Animacja ───────────────────────────────────────────────────────────
    bg = prepare_background(img_original.size, background, img_original, alpha_mask)
    alpha_array = np.array(alpha_mask, dtype=np.uint8)
    W, H = img_original.size

    # Stałe preobliczenia — poza pętlą klatek
    fg_rgb = img_removed.convert("RGB")            # raz, nie per-klatka
    bg_rgba_base = bg.convert("RGBA")              # raz dla aurora composite

    # distance transformy: kosztowne, stałe dla wszystkich klatek
    _binary, dist_outside, dist_inside = _precompute_distances(alpha_array)

    frames = []
    for frame_idx in range(num_frames):
        progress = frame_idx / (num_frames - 1) if num_frames > 1 else 0
        bg_frame = bg.copy()

        if animation == "aurora_borealis":
            aura = _generate_electric_aura_frame(
                dist_outside, dist_inside, W, H, frame_idx, num_frames, glow_color,
                spike_height_pct=spike_height_pct,
                spike_density=spike_density,
                spike_irregularity=spike_irregularity,
            )
            composed = Image.alpha_composite(bg_rgba_base.copy(), aura)
            bg_frame = composed.convert("RGB")
            bg_frame.paste(fg_rgb, mask=alpha_mask)

        elif animation == "pow_effect":
            pow_aura = _generate_pow_effect_frame(
                alpha_array, W, H, frame_idx, num_frames, glow_color,
                pow_intensity=1.2
            )
            composed = Image.alpha_composite(bg_rgba_base.copy(), pow_aura)
            bg_frame = composed.convert("RGB")
            bg_frame.paste(fg_rgb, mask=alpha_mask)

        elif animation == "pulse":
            factor  = 0.5 + 0.5 * abs(((progress * 2 - 1) ** 2) - 1)
            cur_int = max(1, int(glow_intensity * factor))
            glow_a  = alpha_mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            for _ in range(cur_int - 1):
                glow_a = glow_a.filter(ImageFilter.GaussianBlur(radius=1))
            bg_frame.paste(glow_a, mask=glow_a)   # uproszczone — glow ciemnieje tło
            bg_frame.paste(fg_rgb, mask=alpha_mask)

        else:  # glow_shift
            blur_f   = 0.6 + 0.4 * abs(((progress * 2 - 1) ** 2) - 1)
            cur_blur = max(1, int(blur_radius * blur_f))
            glow_a   = alpha_mask.filter(ImageFilter.GaussianBlur(radius=cur_blur))
            bg_frame.paste(glow_a, mask=glow_a)
            bg_frame.paste(fg_rgb, mask=alpha_mask)

        frames.append(bg_frame)

    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        duration=frame_duration, loop=0, optimize=False,
    )
    return buf.getvalue()
