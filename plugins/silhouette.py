"""
Plugin: Silhouette na czarno-białym tle
Usuwa tło ze zdjęcia i nakłada je na czarno-białą wersję oryginalnego zdjęcia.
"""

METADATA = {
    "id": "silhouette",
    "name": "Sylwetka",
    "description": "Usuwa tło i nakłada obiekt na czarno-białą wersję oryginalnego zdjęcia",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🎨",
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
        "scale": {
            "type": "select",
            "label": "Skala wyjściowa",
            "choices": {
                "100": "100%",
                "90": "90%",
                "80": "80%",
                "70": "70%",
                "60": "60%",
                "50": "50%",
                "40": "40%",
                "30": "30%",
                "20": "20%",
            },
            "default": "100",
        },
        "bg_blur": {"type": "slider", "label": "Rozmycie tła (Gaussian)", "min": 0, "max": 30, "step": 1, "default": 0},
        "bg_contrast": {"type": "slider", "label": "Kontrast tła (%)", "min": 20, "max": 250, "step": 1, "default": 100},
        "subject_contrast": {"type": "slider", "label": "Kontrast postaci (%)", "min": 20, "max": 250, "step": 1, "default": 100},
        "bg_brightness": {"type": "slider", "label": "Jasność tła (%)", "min": 20, "max": 250, "step": 1, "default": 100},
        "subject_brightness": {"type": "slider", "label": "Jasność postaci (%)", "min": 20, "max": 250, "step": 1, "default": 100},
        "subject_saturation": {"type": "slider", "label": "Nasycenie postaci (%)", "min": 0, "max": 250, "step": 1, "default": 100},
        "dof_strength": {"type": "slider", "label": "DOF tła (%)", "min": 0, "max": 100, "step": 1, "default": 0},
    },
}

import io
import threading
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    from rembg import remove, new_session
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_sessions: dict = {}
_lock = threading.Lock()

SCALES = {
    "100": 1.0, "90": 0.9, "80": 0.8, "70": 0.7,
    "60": 0.6, "50": 0.5, "40": 0.4, "30": 0.3, "20": 0.2,
}


def is_available() -> bool:
    return _AVAILABLE


def _get_session(model_name: str):
    with _lock:
        if model_name not in _sessions:
            _sessions[model_name] = new_session(model_name)
        return _sessions[model_name]


def process(image_bytes: bytes, options: dict) -> bytes:
    """
    Przetwarza obraz — usuwa tło i nakłada na czarno-białą wersję.

    Args:
        image_bytes: surowe bajty wejściowego obrazu
        options: słownik opcji z METADATA['options']
            - model: nazwa modelu rembg
            - scale: skala wyjściowa (string "100", "80" itd.)

    Returns:
        bajty wynikowego obrazu PNG (kolor na czarno-białym tle)
    """
    if not _AVAILABLE:
        raise RuntimeError("rembg nie jest zainstalowane")

    model_name = options.get("model", METADATA["options"]["model"]["default"])
    scale_str = str(options.get("scale", METADATA["options"]["scale"]["default"]))
    scale = SCALES.get(scale_str, 1.0)
    bg_blur = float(options.get("bg_blur", METADATA["options"]["bg_blur"]["default"]))
    bg_contrast = float(options.get("bg_contrast", METADATA["options"]["bg_contrast"]["default"])) / 100.0
    subject_contrast = float(options.get("subject_contrast", METADATA["options"]["subject_contrast"]["default"])) / 100.0
    bg_brightness = float(options.get("bg_brightness", METADATA["options"]["bg_brightness"]["default"])) / 100.0
    subject_brightness = float(options.get("subject_brightness", METADATA["options"]["subject_brightness"]["default"])) / 100.0
    subject_saturation = float(options.get("subject_saturation", METADATA["options"]["subject_saturation"]["default"])) / 100.0
    dof_strength = float(options.get("dof_strength", METADATA["options"]["dof_strength"]["default"])) / 100.0

    # imgA - obraz wejściowy
    imgA = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    
    # imgB - obraz z usuniętym tłem
    session = _get_session(model_name)
    imgB = remove(imgA, session=session)
    if imgB.mode != "RGBA":
        imgB = imgB.convert("RGBA")
    subj_alpha = imgB.getchannel("A")
    
    # imgC - czarno-biała wersja oryginalnego zdjęcia (tło)
    imgC_bw = Image.open(io.BytesIO(image_bytes)).convert("L")
    imgC = imgC_bw.convert("RGBA")
    if bg_blur > 0:
        imgC = imgC.filter(ImageFilter.GaussianBlur(radius=bg_blur))
    if bg_contrast != 1.0:
        imgC = ImageEnhance.Contrast(imgC).enhance(bg_contrast)
    if bg_brightness != 1.0:
        imgC = ImageEnhance.Brightness(imgC).enhance(bg_brightness)
    if dof_strength > 0:
        dof_blur_radius = 2.0 + (18.0 * dof_strength)
        falloff_radius = 20.0 + (80.0 * dof_strength)
        bg_blurred_dof = imgC.filter(ImageFilter.GaussianBlur(radius=dof_blur_radius))
        proximity = subj_alpha.filter(ImageFilter.GaussianBlur(radius=falloff_radius))
        far_mask = ImageOps.invert(proximity).point(lambda p: int(p * dof_strength))
        imgC = Image.composite(bg_blurred_dof, imgC, far_mask)

    # Korekcje postaci (RGB), alpha pozostaje bez zmian
    subj_rgb = imgB.convert("RGB")
    if subject_contrast != 1.0:
        subj_rgb = ImageEnhance.Contrast(subj_rgb).enhance(subject_contrast)
    if subject_brightness != 1.0:
        subj_rgb = ImageEnhance.Brightness(subj_rgb).enhance(subject_brightness)
    if subject_saturation != 1.0:
        subj_rgb = ImageEnhance.Color(subj_rgb).enhance(subject_saturation)
    imgB = subj_rgb.convert("RGBA")
    imgB.putalpha(subj_alpha)
    
    # imgD - nałożenie imgB na imgC
    imgD = Image.new("RGBA", imgB.size, (0, 0, 0, 255))
    imgD.paste(imgC, (0, 0))
    imgD.paste(imgB, (0, 0), imgB)
    
    # Stosuj skalę
    if scale != 1.0:
        w, h = imgD.size
        imgD = imgD.resize(
            (int(w * scale), int(h * scale)), Image.LANCZOS
        )
    
    # Zapis do bajtów
    buf = io.BytesIO()
    imgD.save(buf, format="PNG")
    return buf.getvalue()
