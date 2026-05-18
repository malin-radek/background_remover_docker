"""
Smart Crop — inteligentne kadrowanie z detekcją twarzy i composition styles.
"""

import io
import math
import numpy as np
from PIL import Image

# ── Dependencies ──────────────────────────────────────────────────────────────
try:
    import cv2
    FACE_DETECTION_AVAILABLE = True
except ImportError:
    FACE_DETECTION_AVAILABLE = False

try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False

_AVAILABLE = FACE_DETECTION_AVAILABLE and REMBG_AVAILABLE

# ── OpenCV Haar cascades (lazy load) ─────────────────────────────────────────
_face_cascade = None
_eye_cascade = None

def _load_cascades():
    global _face_cascade, _eye_cascade
    if _face_cascade is None:
        _face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
        )
    if _eye_cascade is None:
        _eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )


# ── Composition styles ───────────────────────────────────────────────────────
# Każdy styl definiuje:
#   - aspect_ratio: docelowa proporcja (width / height)
#   - focal_points: lista (x, y) w zakresie [0, 1] — gdzie ma być "mocny punkt"
#   - icon, label, description

COMPOSITION_STYLES = {
    "golden_ratio": {
        "aspect_ratio": 1.618,
        "focal_points": [(0.382, 0.382), (0.618, 0.382), (0.382, 0.618), (0.618, 0.618)],
        "icon": "✨",
        "label": "Złoty podział",
        "description": "Klasyczny złoty podział (1.618), punkty mocy na przecięciach",
    },
    "rule_of_thirds": {
        "aspect_ratio": 1.5,
        "focal_points": [(0.333, 0.333), (0.667, 0.333), (0.333, 0.667), (0.667, 0.667)],
        "icon": "📐",
        "label": "Trójpodział",
        "description": "Reguła trójpodziału, punkty mocy na przecięciach linii",
    },
    "square": {
        "aspect_ratio": 1.0,
        "focal_points": [(0.5, 0.5)],
        "icon": "⬜",
        "label": "Kwadrat (1:1)",
        "description": "Idealny kwadrat, centrum jako punkt mocy",
    },
    "classic_3_2": {
        "aspect_ratio": 1.5,
        "focal_points": [(0.5, 0.5)],
        "icon": "📷",
        "label": "Klasyczny 3:2",
        "description": "Proporcja klasycznego aparatu 35mm",
    },
    "portrait_4_5": {
        "aspect_ratio": 0.8,
        "focal_points": [(0.5, 0.4)],
        "icon": "📱",
        "label": "Portret (4:5)",
        "description": "Idealny na Instagram — portretowy format",
    },
    "cinematic_21_9": {
        "aspect_ratio": 2.333,
        "focal_points": [(0.5, 0.5)],
        "icon": "🎬",
        "label": "Cinematic (21:9)",
        "description": "Szeroki, filmowy format kinowy",
    },
    "youtube_16_9": {
        "aspect_ratio": 1.778,
        "focal_points": [(0.5, 0.5)],
        "icon": "📺",
        "label": "YouTube (16:9)",
        "description": "Standardowy format YouTube thumbnail",
    },
    "polaroid_4_3": {
        "aspect_ratio": 1.333,
        "focal_points": [(0.5, 0.45)],
        "icon": "🖼️",
        "label": "Polaroid (4:3)",
        "description": "Klasyczny format Polaroid / kompakt",
    },
}


# ── Face / eye detection ─────────────────────────────────────────────────────
def _detect_face_and_eyes(image_bytes: bytes) -> dict | None:
    """
    Wykrywa twarz i oczy za pomocą OpenCV Haar Cascades.
    Szybki, działa na CPU, nie wymaga dodatkowych modeli.
    """
    if not FACE_DETECTION_AVAILABLE:
        return None

    _load_cascades()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_np = np.array(img)
    h, w = img_np.shape[:2]

    # Konwertuj do grayscale dla detekcji
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # Detekcja twarzy
    faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(faces) == 0:
        return None

    # Weź największą twarz (zazwyczaj najbliższa kamery)
    best = max(faces, key=lambda f: f[2] * f[3])
    fx1, fy1, fw, fh = best
    fx2, fy2 = fx1 + fw, fy1 + fh
    face_center = ((fx1 + fx2) / 2, (fy1 + fy2) / 2)

    # Detekcja oczu wewnątrz twarzy
    roi_gray = gray[fy1:fy2, fx1:fx2]
    eyes = _eye_cascade.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=5, minSize=(10, 10))
    eye_center = None
    if len(eyes) >= 2:
        # Weź 2 największe oczy
        sorted_eyes = sorted(eyes, key=lambda e: e[2] * e[3], reverse=True)[:2]
        # Sortuj po X żeby lewe było pierwsze
        sorted_eyes.sort(key=lambda e: e[0])
        left_eye = sorted_eyes[0]
        right_eye = sorted_eyes[1]
        eye_center = (
            (left_eye[0] + left_eye[2] // 2 + fx1 + right_eye[0] + right_eye[2] // 2 + fx1) / 2,
            (left_eye[1] + left_eye[3] // 2 + fy1 + right_eye[1] + right_eye[3] // 2 + fy1) / 2,
        )

    return {
        "face_center": face_center,
        "eye_center": eye_center,
        "face_box": (fx1, fy1, fx2, fy2),
        "confidence": 1.0,
    }


# ── Salience detection (rembg fallback) ──────────────────────────────────────
def _detect_salience(image_bytes: bytes) -> dict | None:
    """
    Używa rembg do znalezienia foreground maski.
    Zwraca centroid foreground jako punkt salience.
    """
    if not REMBG_AVAILABLE:
        return None

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        # rembg zwraca PNG z alpha = foreground
        fg = remove(img, session=None)
        fg_np = np.array(fg)
        alpha = fg_np[:, :, 3]  # Alpha channel
        mask = alpha > 128

        if not np.any(mask):
            return None

        # Centroid foreground
        ys, xs = np.where(mask)
        cx = int(np.mean(xs))
        cy = int(np.mean(ys))

        # Bounding box foreground
        x1, y1 = int(xs.min()), int(ys.min())
        x2, y2 = int(xs.max()), int(ys.max())

        return {
            "salience_center": (cx, cy),
            "salience_box": (x1, y1, x2, y2),
            "coverage": np.sum(mask) / (mask.shape[0] * mask.shape[1]),
        }
    except Exception:
        return None


# ── Crop calculation ─────────────────────────────────────────────────────────
def _compute_crop(
    img_w: int,
    img_h: int,
    target_aspect: float,
    focal_point: tuple,       # (x, y) w pikselach — gdzie jest obiekt
    composition_ratio: tuple, # (rx, ry) w [0,1] — gdzie ma być w kadrze
    padding: float = 0.1,
) -> tuple:
    """
    Oblicza crop tak, by focal_point znalazł się w composition_ratio wewnątrz kadru.
    Nigdy nie wychodzi poza kanwas.
    """
    fx, fy = focal_point
    rx, ry = composition_ratio

    # Padding: wymuś minimalny margines od krawędzi kadru
    rx = max(padding, min(rx, 1.0 - padding))
    ry = max(padding, min(ry, 1.0 - padding))

    # 1. Oblicz MAKSYMALNY crop o docelowym aspect ratio, który mieści się w obrazie
    if img_w / img_h > target_aspect:
        # Obraz szerszy niż target → crop ograniczony przez height
        crop_h = img_h
        crop_w = int(crop_h * target_aspect)
    else:
        # Obraz węższy niż target → crop ograniczony przez width
        crop_w = img_w
        crop_h = int(crop_w / target_aspect)

    # 2. Pozycjonuj crop tak, by focal_point był na composition_ratio wewnątrz kadru
    #    x1 + crop_w * rx = fx  →  x1 = fx - crop_w * rx
    x1 = int(fx - crop_w * rx)
    y1 = int(fy - crop_h * ry)

    # 3. Clamp do granic obrazu
    x1 = max(0, min(x1, img_w - crop_w))
    y1 = max(0, min(y1, img_h - crop_h))

    x2 = x1 + crop_w
    y2 = y1 + crop_h

    return (x1, y1, x2, y2)


def _select_composition_ratio(
    focal_points: list,
    img_w: int,
    img_h: int,
    target_point: tuple,
) -> tuple:
    """
    Wybiera najbliższy punkt kompozycji (jako ratio 0-1) do wykrytego punktu.
    """
    tx, ty = target_point
    best = focal_points[0]
    best_dist = float("inf")
    for fp in focal_points:
        fx, fy = fp[0] * img_w, fp[1] * img_h
        dist = math.hypot(fx - tx, fy - ty)
        if dist < best_dist:
            best_dist = dist
            best = fp
    return best


# ── METADATA ─────────────────────────────────────────────────────────────────
METADATA = {
    "id": "smart_crop",
    "name": "✂️ Smart Crop",
    "description": "Inteligentne kadrowanie z detekcją twarzy/oczu i composition styles. Automatycznie pozycjonuje osobę w mocnym punkcie wybranego stylu.",
    "version": "1.0.0",
    "icon": "✂️",
    "disable_scaling": True,
    "options": {
        "style": {
            "type": "select",
            "label": "Styl kompozycji",
            "choices": {
                sid: f"{s['icon']} {s['label']}"
                for sid, s in COMPOSITION_STYLES.items()
            },
            "default": "golden_ratio",
        },
        "face_detection": {
            "type": "select",
            "label": "Detekcja",
            "choices": {
                "auto": "🤖 Auto (twarz → salience → center)",
                "face_only": "👤 Tylko twarz",
                "salience_only": "🎯 Tylko salience (rembg)",
                "center": "📍 Center (bez detekcji)",
            },
            "default": "auto",
        },
        "padding": {
            "type": "select",
            "label": "Margines wokół obiektu",
            "choices": {
                "0.05": "Bardzo ciasno (5%)",
                "0.1": "Ciasno (10%)",
                "0.15": "Normalnie (15%)",
                "0.2": "Luźno (20%)",
                "0.3": "Bardzo luźno (30%)",
            },
            "default": "0.15",
        },
    },
}


# ── Plugin interface ─────────────────────────────────────────────────────────
def is_available() -> bool:
    return _AVAILABLE


def process(image_bytes: bytes, options: dict) -> bytes:
    """
    Przycina obraz zgodnie z wybranym stylem kompozycji.
    """
    style_id = options.get("style", METADATA["options"]["style"]["default"])
    face_mode = options.get("face_detection", METADATA["options"]["face_detection"]["default"])
    padding = float(options.get("padding", METADATA["options"]["padding"]["default"]))

    style = COMPOSITION_STYLES.get(style_id, COMPOSITION_STYLES["golden_ratio"])
    target_aspect = style["aspect_ratio"]
    focal_points = style["focal_points"]

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img_w, img_h = img.size

    # ── Detekcja punktu kadrowania ───────────────────────────────────────
    focal_pixel = None  # (x, y) w pikselach

    if face_mode in ("auto", "face_only"):
        face_data = _detect_face_and_eyes(image_bytes)
        if face_data:
            # Priorytet: oczy → środek twarzy
            if face_data["eye_center"]:
                focal_pixel = face_data["eye_center"]
                print(f"[smart_crop] Eyes detected at {focal_pixel}", flush=True)
            else:
                focal_pixel = face_data["face_center"]
                print(f"[smart_crop] Face detected at {focal_pixel}", flush=True)

            if face_mode == "face_only" and focal_pixel is None:
                # Face-only mode i nie wykryto — fallback do center
                focal_pixel = (img_w / 2, img_h / 2)
                print("[smart_crop] No face detected, using center", flush=True)

    if focal_pixel is None and face_mode in ("auto", "salience_only"):
        salience = _detect_salience(image_bytes)
        if salience:
            focal_pixel = salience["salience_center"]
            print(f"[smart_crop] Salience at {focal_pixel}", flush=True)

    if focal_pixel is None:
        # Ostateczny fallback — center
        focal_pixel = (img_w / 2, img_h / 2)
        print("[smart_crop] Using center as fallback", flush=True)

    # ── Wybór punktu kompozycji i obliczenie cropu ─────────────────────────
    comp_ratio = _select_composition_ratio(focal_points, img_w, img_h, focal_pixel)
    print(f"[smart_crop] Style={style_id} aspect={target_aspect} focal={focal_pixel} comp_ratio={comp_ratio}", flush=True)

    x1, y1, x2, y2 = _compute_crop(img_w, img_h, target_aspect, focal_pixel, comp_ratio, padding)
    print(f"[smart_crop] Crop: ({x1},{y1})→({x2},{y2}) size={x2-x1}x{y2-y1} (orig {img_w}x{img_h})", flush=True)

    # Sanity check
    if x2 - x1 < 10 or y2 - y1 < 10:
        print(f"[smart_crop] WARNING: crop too small, fallback to center", flush=True)
        x1, y1, x2, y2 = _compute_crop(img_w, img_h, target_aspect, (img_w/2, img_h/2), (0.5, 0.5), padding)

    # ── Wykonanie cropu ──────────────────────────────────────────────────
    cropped = img.crop((x1, y1, x2, y2))
    print(f"[smart_crop] Result: {cropped.size}", flush=True)

    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()
