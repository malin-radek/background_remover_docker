"""
Plugin: Upscale AI Pro (SwinIR/ESRGAN Edition)
Wersja z modelami SwinIR (JingyunLiang official), Real-ESRGAN i wariantem anime.
"""

METADATA = {
    "id": "upscale_ai",
    "name": "Powiększanie AI Pro+",
    "description": "Najwyższa jakość SwinIR/ESRGAN. Zoptymalizowany pod pełną rozdzielczość.",
    "version": "1.7.0",
    "author": "Radek",
    "icon": "💎",
    "disable_scaling": True,
    "options": {
        "model_type": {
            "type": "select",
            "label": "Silnik AI",
            "choices": {
                "SwinIR_x4":        "SwinIR-M GAN (Najlepsza tekstura, realworld)",
                "SwinIR_x4_Large":  "SwinIR-L GAN (Jeszcze lepsza - więcej VRAM)",
                "RealESRGAN_x4plus":        "Real-ESRGAN 4x (Gładszy, fotografie)",
                "RealESRGAN_x4plus_anime":  "Real-ESRGAN Anime 4x (Ilustracje/anime)",
                "RealESRNet_x4plus":        "Real-ESRNet 4x (Ostrzejszy, lżejszy)",
                "RealESRGAN_x2plus":        "Real-ESRGAN 2x (Tylko 2x, szybki)",
            },
            "default": "SwinIR_x4",
        },
        "target_scale": {
            "type": "select",
            "label": "Skala docelowa",
            "choices": {
                "2": "2x",
                "4": "4x",
            },
            "default": "4",
        },
        "sharpness": {
            "type": "slider",
            "label": "Wyostrzenie (%)",
            "min": 0,
            "max": 100,
            "default": 35,
        },
        "tile_size": {
            "type": "select",
            "label": "Pamięć (Tiling)",
            "choices": {
                "0":   "Auto",
                "256": "256x256 (mało VRAM)",
                "512": "512x512 (zalecane)",
                "768": "768x768 (dużo VRAM)",
            },
            "default": "512",
        },
    },
}

import io
import os
import math
import urllib.request
import threading
import torch
import numpy as np
from PIL import Image, ImageFilter

try:
    from spandrel import ModelLoader
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

# ---------------------------------------------------------------------------
# LINKI DO MODELI — zweryfikowane, oficjalne źródła
# ---------------------------------------------------------------------------
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
MODEL_URLS = {
    # SwinIR — oficjalne release'y repozytorium JingyunLiang/SwinIR
    "SwinIR_x4": (
        "https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/"
        "003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x4_GAN.pth"
    ),
    "SwinIR_x4_Large": (
        "https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/"
        "003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth"
    ),
    # Real-ESRGAN — oficjalne release'y xinntao/Real-ESRGAN
    "RealESRGAN_x4plus": (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/"
        "RealESRGAN_x4plus.pth"
    ),
    "RealESRGAN_x4plus_anime": (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/"
        "RealESRGAN_x4plus_anime_6B.pth"
    ),
    "RealESRNet_x4plus": (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.1/"
        "RealESRNet_x4plus.pth"
    ),
    "RealESRGAN_x2plus": (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/"
        "RealESRGAN_x2plus.pth"
    ),
}

# Natywna skala każdego modelu (spandrel powinien to wykryć, ale mamy fallback)
MODEL_NATIVE_SCALE = {
    "SwinIR_x4":              4,
    "SwinIR_x4_Large":        4,
    "RealESRGAN_x4plus":      4,
    "RealESRGAN_x4plus_anime": 4,
    "RealESRNet_x4plus":      4,
    "RealESRGAN_x2plus":      2,
}

_models_cache: dict = {}
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Urządzenie
# ---------------------------------------------------------------------------
if torch.cuda.is_available():
    _device = torch.device("cuda")
    _is_cpu = False
    print(f"[upscale_ai] GPU: {torch.cuda.get_device_name(0)}")
else:
    _device = torch.device("cpu")
    _is_cpu = True
    torch.set_num_threads(os.cpu_count() or 4)
    print("[upscale_ai] CUDA niedostępna — tryb CPU")


# ---------------------------------------------------------------------------
# Pobieranie i ładowanie modeli
# ---------------------------------------------------------------------------
def _download_model(model_id: str, model_path: str) -> None:
    url = MODEL_URLS.get(model_id)
    if not url:
        raise RuntimeError(f"Nieznany model: {model_id}")

    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"[upscale_ai] Pobieranie modelu: {model_id} …")

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
        ("Accept", "*/*"),
    ]

    tmp_path = model_path + ".tmp"
    try:
        with opener.open(url) as resp, open(tmp_path, "wb") as fout:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fout.write(chunk)
        os.rename(tmp_path, model_path)
        print(f"[upscale_ai] Pobrano {model_id} ({os.path.getsize(model_path) // (1024*1024)} MB).")
    except Exception as exc:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise RuntimeError(
            f"Błąd pobierania '{model_id}': {exc}\n"
            f"Pobierz ręcznie z: {url}\n"
            f"i umieść jako: {model_path}"
        ) from exc


def _get_model(model_id: str):
    with _lock:
        if model_id not in _models_cache:
            model_path = os.path.join(MODELS_DIR, f"{model_id}.pth")

            if not os.path.exists(model_path):
                _download_model(model_id, model_path)

            print(f"[upscale_ai] Ładowanie {model_id} …")
            loader = ModelLoader()
            model = loader.load_from_file(model_path)
            model.to(_device)
            model.eval()
            _models_cache[model_id] = model

        return _models_cache[model_id]


# ---------------------------------------------------------------------------
# Tiling — podział obrazu na kafelki, żeby nie wysadzić VRAM
# ---------------------------------------------------------------------------
def _infer_tiled(model, img_t: torch.Tensor, tile: int, overlap: int = 32) -> torch.Tensor:
    """Przetwarza obraz kafelek po kafelku i skleja wynik."""
    b, c, h, w = img_t.shape

    # Wykryj skalę z modelu (spandrel ustawia .scale) lub fallback 4
    scale = getattr(model, "scale", 4)

    out_h, out_w = h * scale, w * scale
    output = torch.zeros(b, c, out_h, out_w, device=img_t.device)
    weight = torch.zeros(b, 1, out_h, out_w, device=img_t.device)

    step = tile - overlap
    xs = list(range(0, w, step))
    ys = list(range(0, h, step))

    for y in ys:
        for x in xs:
            x_end = min(x + tile, w)
            y_end = min(y + tile, h)
            patch = img_t[:, :, y:y_end, x:x_end]

            with torch.no_grad():
                patch_out = model(patch)

            oy, ox = y * scale, x * scale
            oy_end, ox_end = y_end * scale, x_end * scale
            output[:, :, oy:oy_end, ox:ox_end] += patch_out
            weight[:, :, oy:oy_end, ox:ox_end] += 1.0

    output /= weight.clamp(min=1e-8)
    return output


# ---------------------------------------------------------------------------
# Główna funkcja przetwarzania
# ---------------------------------------------------------------------------
def process(image_bytes: bytes, options: dict) -> bytes:
    if not _AVAILABLE:
        raise RuntimeError(
            "Brak wymaganych bibliotek.\n"
            "Zainstaluj: pip install spandrel torch torchvision"
        )

    model_name   = options.get("model_type", "SwinIR_x4")
    target_scale = int(options.get("target_scale", 4))
    sharp_pct    = float(options.get("sharpness", 35))
    tile_size    = int(options.get("tile_size", 512))

    orig_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    img_t = (
        torch.from_numpy(np.array(orig_img))
        .permute(2, 0, 1)
        .float()
        .div(255.0)
        .unsqueeze(0)
        .to(_device)
    )

    model = _get_model(model_name)
    native_scale = getattr(model, "scale", MODEL_NATIVE_SCALE.get(model_name, 4))

    try:
        if tile_size > 0:
            output_t = _infer_tiled(model, img_t, tile=tile_size, overlap=32)
        else:
            with torch.no_grad():
                output_t = model(img_t)
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            torch.cuda.empty_cache()
            raise RuntimeError(
                "Błąd VRAM! Zmniejsz 'Pamięć (Tiling)' lub użyj mniejszego zdjęcia."
            ) from exc
        raise

    res_np = output_t.squeeze().clamp(0, 1).cpu().numpy().transpose(1, 2, 0)
    output_img = Image.fromarray((res_np * 255).astype(np.uint8))

    # Wyostrzanie
    if sharp_pct > 0:
        output_img = output_img.filter(
            ImageFilter.UnsharpMask(radius=1, percent=int(sharp_pct * 2), threshold=3)
        )

    # Skalowanie do target_scale jeśli różni się od natywnej skali modelu
    if target_scale != native_scale:
        new_w = int(orig_img.width * target_scale)
        new_h = int(orig_img.height * target_scale)
        output_img = output_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    output_img.save(buf, format="PNG")
    return buf.getvalue()
