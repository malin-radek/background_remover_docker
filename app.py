import sys
import os
import shutil
from pathlib import Path
import importlib
import subprocess
import uuid
from datetime import datetime, timedelta

# ── Czyszczenie cache na starcie ───────────────────────────────────────────────
# WYŁĄCZ cache PRZED każdym importem
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True

# Agresywne czyszczenie wszystkich __pycache__ rekurencyjnie
print("[startup] Czyszczę cache...")
for cache_dir in Path(".").rglob("__pycache__"):
    try:
        shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"[startup] Usunięto cache: {cache_dir}")
    except:
        pass

# Invalidate all import caches
importlib.invalidate_caches()
sys.path_importer_cache.clear()

import io
import json
import time
import threading
import hashlib
from collections import defaultdict
from flask import Flask, request, jsonify, send_file, render_template, make_response
from PIL import Image
import plugin_loader

# Clear Jinja2 template cache
import shutil as _sh
jinja_cache_dir = Path(".").resolve() / ".jinja2_cache" 
if jinja_cache_dir.exists():
    _sh.rmtree(jinja_cache_dir, ignore_errors=True)

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.config['DEBUG'] = False
app.jinja_env.cache = None

# ── Token wersji (unikalny na każdy start procesu) ─────────────────────────────
# Wymusza przeładowanie frontendu po każdym restarcie serwera / kontenera.
_STARTUP_VERSION = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
print(f"[startup] Version token: {_STARTUP_VERSION}")

# ── Persistent cache na dysku ─────────────────────────────────────────────────
CACHE_DIR = Path(os.getenv("CACHE_DIR", "./cache"))
CACHE_DIR.mkdir(exist_ok=True, parents=True)
CACHE_METADATA_FILE = CACHE_DIR / "metadata.json"
print(f"[startup] Cache directory: {CACHE_DIR.absolute()}")

_cache_lock = threading.Lock()

def _load_cache_metadata() -> dict:
    """Załaduj metadane cache z dysku."""
    try:
        if CACHE_METADATA_FILE.exists():
            return json.loads(CACHE_METADATA_FILE.read_text())
    except Exception as e:
        print(f"[cache] ERROR loading metadata: {e}")
    return {}

def _save_cache_metadata(data: dict):
    """Zapisz metadane cache na dysk."""
    try:
        CACHE_METADATA_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"[cache] ERROR saving metadata: {e}")

def _cleanup_old_cache(max_age_days: int = 7):
    """Usuń cache'ę starszą niż max_age_days."""
    metadata = _load_cache_metadata()
    now = time.time()
    max_age_seconds = max_age_days * 86400
    
    deleted = 0
    for image_id, info in list(metadata.items()):
        created_at = info.get("created_at", 0)
        if now - created_at > max_age_seconds:
            cache_file = CACHE_DIR / f"{image_id}.cache"
            try:
                if cache_file.exists():
                    cache_file.unlink()
                    deleted += 1
            except Exception as e:
                print(f"[cache] ERROR deleting {image_id}: {e}")
            del metadata[image_id]
    
    if deleted > 0:
        _save_cache_metadata(metadata)
        print(f"[cache] Cleaned {deleted} old files")

# Wyczyść stary cache na starcie
_cleanup_old_cache()
_cache_metadata = _load_cache_metadata()

@app.after_request
def add_no_cache_headers(response):
    """Dodaj nagłówki no-cache do wszystkich odpowiedzi HTML i JS."""
    ct = response.content_type or ""
    if "text/html" in ct or "application/json" in ct:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ── Konfiguracja rozdzielczości ────────────────────────────────────────────────
# Czytaj MAX_IMAGE_RESOLUTION z env (domyślnie 4K: 3840x2160)
max_res_str = os.getenv("MAX_IMAGE_RESOLUTION", "3840x2160")
try:
    MAX_RES_WIDTH, MAX_RES_HEIGHT = map(int, max_res_str.split("x"))
except:
    MAX_RES_WIDTH, MAX_RES_HEIGHT = 3840, 2160
MAX_PIXELS = MAX_RES_WIDTH * MAX_RES_HEIGHT
print(f"[app] MAX_IMAGE_RESOLUTION: {MAX_RES_WIDTH}x{MAX_RES_HEIGHT} ({MAX_PIXELS:,} px)")

# ── Pluginy ───────────────────────────────────────────────────────────────────
PLUGINS = plugin_loader.load_all()  # id -> metadata
print(f"[app] Zaloadowane {len(PLUGINS)} pluginow")
for pid in sorted(PLUGINS.keys()):
    print(f"  - {pid}")

# CRITICAL: Fail if no plugins loaded (indicates missing plugins/ directory or loading error)
if not PLUGINS:
    print("\n[ERROR] NO PLUGINS LOADED! This is a critical configuration error.")
    print("[ERROR] Check that:")
    print("  1. The 'plugins/' directory exists in the image")
    print("  2. It contains .py files with METADATA")
    print("  3. plugin_loader.py can access the directory")
    sys.exit(1)

DEFAULT_PLUGIN = os.getenv("DEFAULT_PLUGIN", "remove_background")
if DEFAULT_PLUGIN not in PLUGINS:
    print(f"[WARN] DEFAULT_PLUGIN '{DEFAULT_PLUGIN}' not found. Falling back to 'remove_background'")
    DEFAULT_PLUGIN = "remove_background"

# ── Liczniki per-IP (persistent) ─────────────────────────────────────────────
COUNTERS_FILE = Path(os.getenv("U2NET_HOME", "/app/models")) / "counters.json"
_counters_lock = threading.Lock()

def _load_counters() -> dict:
    try:
        if COUNTERS_FILE.exists():
            return json.loads(COUNTERS_FILE.read_text())
    except Exception:
        pass
    return {}

def _save_counters(data: dict):
    try:
        COUNTERS_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

_counters: dict = defaultdict(int, _load_counters())

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/bmp", "image/gif", "image/tiff", "image/webp"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()


def _rescale_image_if_needed(image_bytes: bytes) -> tuple[bytes, str]:
    """
    Przeskaluj obraz jeśli ma więcej pixeli niż MAX_PIXELS.
    Zwraca (image_bytes, scale_info_str).
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        orig_w, orig_h = img.size
        orig_pixels = orig_w * orig_h
        
        if orig_pixels <= MAX_PIXELS:
            return image_bytes, f"{orig_w}x{orig_h}"
        
        # Oblicz nowy rozmiar (zachowaj aspect ratio)
        aspect_ratio = orig_w / orig_h
        new_h = int((MAX_PIXELS / aspect_ratio) ** 0.5)
        new_w = int(new_h * aspect_ratio)
        
        # Upewnij się że nie przekroczymy limitu
        while new_w * new_h > MAX_PIXELS:
            new_h -= 1
            new_w = int(new_h * aspect_ratio)
        
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Zachowaj format (JPEG dla RGB, PNG dla RGBA)
        buf = io.BytesIO()
        save_format = "JPEG" if img_resized.mode == "RGB" else "PNG"
        img_resized.save(buf, format=save_format, quality=95)
        
        scale_info = f"{orig_w}x{orig_h} → {new_w}x{new_h}"
        print(f"[rescale] {scale_info}", flush=True)
        
        return buf.getvalue(), scale_info
    except Exception as e:
        print(f"[rescale] ERROR: {e}", flush=True)
        return image_bytes, "error"


def _scale_input_to_size(image_bytes: bytes, target_size: int) -> bytes:
    """
    Przeskaluj obraz wejściowy do podanego rozmiaru (max dimension).
    target_size: maksymalny wymiar (width lub height)
    Zachowuje proporcje (aspect ratio).
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        orig_w, orig_h = img.size
        
        max_dim = max(orig_w, orig_h)
        if max_dim <= target_size:
            return image_bytes  # już mały
        
        # Skaluj proporczjonalnie
        scale_factor = target_size / max_dim
        new_w = int(orig_w * scale_factor)
        new_h = int(orig_h * scale_factor)
        
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Zachowaj format
        buf = io.BytesIO()
        save_format = "JPEG" if img_resized.mode == "RGB" else "PNG"
        if save_format == "JPEG":
            img_resized.save(buf, format=save_format, quality=95)
        else:
            img_resized.save(buf, format=save_format)
        
        print(f"[input_scale] {orig_w}x{orig_h} → {new_w}x{new_h} (target: {target_size}px)", flush=True)
        return buf.getvalue()
    except Exception as e:
        print(f"[input_scale] ERROR: {e}", flush=True)
        return image_bytes


def _scale_output_image(image_bytes: bytes, scale_percent: int) -> bytes:
    if scale_percent >= 100:
        return image_bytes
    
    try:
        is_gif = image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a")
        
        if is_gif:
            # GIF animation - przeskaluj każdą klatkę
            from PIL import Image as PILImage
            img = PILImage.open(io.BytesIO(image_bytes))
            
            # Oblicz nowy rozmiar
            orig_w, orig_h = img.size
            new_w = max(1, int(orig_w * scale_percent / 100.0))
            new_h = max(1, int(orig_h * scale_percent / 100.0))
            
            # Przeskaluj każdą klatkę
            frames = []
            durations = []
            try:
                while True:
                    frame = img.convert("RGB")
                    frame_resized = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    frames.append(frame_resized)
                    durations.append(img.info.get('duration', 100))
                    img.seek(img.tell() + 1)
            except EOFError:
                pass
            
            # Zapisz GIF z przeskalowanymi klatkami
            buf = io.BytesIO()
            if frames:
                frames[0].save(
                    buf, format="GIF", save_all=True, append_images=frames[1:],
                    duration=durations, loop=0, optimize=False
                )
            return buf.getvalue()
        else:
            # PNG lub inny format
            img = Image.open(io.BytesIO(image_bytes))
            orig_w, orig_h = img.size
            new_w = max(1, int(orig_w * scale_percent / 100.0))
            new_h = max(1, int(orig_h * scale_percent / 100.0))
            
            img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            buf = io.BytesIO()
            save_format = "JPEG" if img_resized.mode == "RGB" else "PNG"
            quality = 95 if save_format == "JPEG" else None
            if quality:
                img_resized.save(buf, format=save_format, quality=quality)
            else:
                img_resized.save(buf, format=save_format)
            
            print(f"[output_scale] {orig_w}x{orig_h} → {new_w}x{new_h} ({scale_percent}%)", flush=True)
            return buf.getvalue()
    except Exception as e:
        print(f"[output_scale] ERROR: {e}", flush=True)
        return image_bytes


# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    try:
        html = render_template("index.html", _v=_STARTUP_VERSION)
        print(f"[index] Rendered template successfully, size={len(html)} bytes")
        resp = make_response(html)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    except Exception as e:
        print(f"[index] ERROR rendering template: {e}")
        raise


@app.route("/plugins", methods=["GET"])
def list_plugins():
    import json
    # Build result by copying only serializable parts
    result = {}
    for pid, meta in PLUGINS.items():
        try:
            # Try to serialize this metadata
            json.dumps(meta)
            result[pid] = meta
        except TypeError:
            pass  # Skip non-serializable
    
    return json.dumps(result), 200, {'Content-Type': 'application/json'}


@app.route("/counter", methods=["GET"])
def counter():
    ip = get_client_ip()
    with _counters_lock:
        return jsonify({"ip": ip, "count": _counters[ip]})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "plugins": list(PLUGINS.keys())})


@app.route("/process", methods=["POST"])
@app.route("/remove-background", methods=["POST"])
def process():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided."}), 400

    file = request.files["image"]
    plugin_id = request.form.get("plugin", DEFAULT_PLUGIN)
    plugin_mod = plugin_loader.get_plugin(plugin_id)
    if not plugin_mod:
        return jsonify({"error": f"Unknown plugin '{plugin_id}'."}), 400

    # Zbierz opcje: opt_model, opt_scale → {model: ..., scale: ...}
    options = {}
    for key, val in request.form.items():
        if key.startswith("opt_"):
            options[key[4:]] = val
    
    # Sprawdź czy plugin wyłącza skalowanie
    plugin_meta = PLUGINS.get(plugin_id, {})
    disable_scaling = plugin_meta.get("disable_scaling", False)
    
    # Czytaj mode: preview (szybki) vs download (wysoka jakość)
    mode = request.form.get("mode", "download")  # default: download
    
    # Docelowy rozmiar: 
    # - None jeśli wyłączone skalowanie
    # - 256px dla preview (miniaturki wariantów)
    # - 1024px dla download (standard)
    if disable_scaling:
        target_size = None
    elif mode == "preview":
        target_size = 512  # Średni rozmiar dla miniatur wariantów (szybki ale wystarczający dla edge detection)
    else:
        target_size = 1024

    try:
        t0 = time.time()
        image_bytes = file.read()
        
        # Przeskaluj jeśli trzeba (limity rozdzielczości)
        image_bytes, scale_info = _rescale_image_if_needed(image_bytes)
        
        print(f"[process] START mode={mode} plugin={plugin_id} size={scale_info} target_size={target_size} disable_scaling={disable_scaling}", flush=True)
        
        # SKALUJ INPUT do docelowego rozmiaru PRZED pluginem (chyba że disable_scaling)
        if target_size is not None:
            image_bytes = _scale_input_to_size(image_bytes, target_size)
            print(f"[process] Scaled input to {target_size}px max dimension", flush=True)
        else:
            print(f"[process] Scaling disabled by plugin", flush=True)
        
        result_bytes = plugin_mod.process(image_bytes, options)
        
        elapsed = round(time.time() - t0, 2)
        print(f"[process] DONE mode={mode} plugin={plugin_id} elapsed={elapsed}s size={len(result_bytes)/1024/1024:.1f}MB", flush=True)
    except Exception as e:
        print(f"[process] ERROR plugin={plugin_id} error={str(e)}", flush=True)
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

    ip = get_client_ip()
    with _counters_lock:
        _counters[ip] += 1
        _save_counters(dict(_counters))

    stem = Path(file.filename or "image").stem
    
    # Detektuj format na podstawie bajów
    is_gif = result_bytes.startswith(b"GIF87a") or result_bytes.startswith(b"GIF89a")
    file_ext = "gif" if is_gif else "png"
    mime_type = "image/gif" if is_gif else "image/png"
    
    # ── Zapisz w persistent cache ──────────────────────────────────────────────
    image_id = str(uuid.uuid4())
    cache_file = CACHE_DIR / f"{image_id}.cache"
    
    with _cache_lock:
        try:
            cache_file.write_bytes(result_bytes)
            _cache_metadata[image_id] = {
                "created_at": time.time(),
                "client_ip": ip,
                "plugin": plugin_id,
                "filename": f"{stem}_out.{file_ext}",
                "mime_type": mime_type,
                "size_bytes": len(result_bytes),
                "elapsed_seconds": elapsed,
            }
            _save_cache_metadata(_cache_metadata)
            print(f"[cache] Saved {image_id}: {file_ext} ({len(result_bytes)/1024/1024:.1f}MB)", flush=True)
        except Exception as e:
            print(f"[cache] ERROR saving {image_id}: {e}", flush=True)
    
    # Zwróć link do cache'a zamiast bezpośrednio pliku
    return jsonify({
        "image_id": image_id,
        "download_url": f"/result/{image_id}",
        "mime_type": mime_type,
        "file_extension": file_ext,
        "size_bytes": len(result_bytes),
        "elapsed_seconds": elapsed,
    }), 200


@app.route("/result/<image_id>", methods=["GET"])
def get_result(image_id: str):
    """Pobierz wcześniej wygenerowany obraz z cache'a."""
    # Validacja ID (UUID format)
    try:
        uuid.UUID(image_id)
    except ValueError:
        return jsonify({"error": "Invalid image ID."}), 400
    
    with _cache_lock:
        if image_id not in _cache_metadata:
            return jsonify({"error": "Image not found or expired."}), 404
        
        metadata = _cache_metadata[image_id]
        cache_file = CACHE_DIR / f"{image_id}.cache"
        
        if not cache_file.exists():
            return jsonify({"error": "Image file not found."}), 404
        
        try:
            result_bytes = cache_file.read_bytes()
            mime_type = metadata.get("mime_type", "image/png")
            filename = metadata.get("filename", f"image.{mime_type.split('/')[-1]}")
            
            # Sanitize filename for HTTP header (ASCII only)
            import unicodedata
            safe_filename = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
            safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in "._- ")
            
            response = make_response(result_bytes)
            response.headers["Content-Type"] = mime_type
            response.headers["Content-Disposition"] = f'inline; filename="{safe_filename}"'
            response.headers["X-Elapsed-Seconds"] = str(metadata.get("elapsed_seconds", 0))
            response.headers["X-Plugin"] = metadata.get("plugin", "unknown")
            return response
        except Exception as e:
            print(f"[result] ERROR reading {image_id}: {e}", flush=True)
            return jsonify({"error": f"Failed to retrieve image: {str(e)}"}), 500


@app.route("/result/<image_id>/info", methods=["GET"])
def get_result_info(image_id: str):
    """Pobierz metadane o wygenerowanym obrazie."""
    try:
        uuid.UUID(image_id)
    except ValueError:
        return jsonify({"error": "Invalid image ID."}), 400
    
    with _cache_lock:
        if image_id not in _cache_metadata:
            return jsonify({"error": "Image not found or expired."}), 404
        
        metadata = _cache_metadata[image_id].copy()
        metadata["image_id"] = image_id
        metadata["download_url"] = f"/result/{image_id}"
        return jsonify(metadata), 200


@app.route("/gif-to-mp4", methods=["POST"])
def gif_to_mp4():
    """Konwertuje GIF na MP4."""
    if "gif" not in request.files:
        return jsonify({"error": "No GIF file provided."}), 400

    gif_file = request.files["gif"]
    gif_bytes = gif_file.read()
    
    # Sprawdź czy to GIF
    if not (gif_bytes.startswith(b"GIF87a") or gif_bytes.startswith(b"GIF89a")):
        return jsonify({"error": "File is not a valid GIF."}), 400
    
    try:
        import plugin_utils
        t0 = time.time()
        mp4_bytes = plugin_utils.gif_to_mp4(gif_bytes)
        elapsed = round(time.time() - t0, 2)
        print(f"[gif-to-mp4] Converted GIF to MP4 in {elapsed}s, size={len(mp4_bytes)/1024/1024:.1f}MB", flush=True)
    except ImportError as e:
        return jsonify({"error": f"MP4 conversion not available: {str(e)}"}), 501
    except Exception as e:
        print(f"[gif-to-mp4] ERROR: {str(e)}", flush=True)
        return jsonify({"error": f"Conversion failed: {str(e)}"}), 500

    stem = Path(gif_file.filename or "animation").stem
    response = send_file(
        io.BytesIO(mp4_bytes),
        mimetype="video/mp4",
        as_attachment=True,
        download_name=f"{stem}.mp4",
    )
    response.headers["X-Elapsed-Seconds"] = str(elapsed)
    return response


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": f"File too large. Max {MAX_UPLOAD_MB} MB."}), 413


# ────────────────────────────────────────────────────────────────────────────────
# Inpainting Web Editor
# ────────────────────────────────────────────────────────────────────────────────
try:
    from inpaint_web_service import create_session, get_session, delete_session
    INPAINT_WEB_AVAILABLE = True
except ImportError as e:
    INPAINT_WEB_AVAILABLE = False
    print(f"[app] Inpaint web service not available: {e}")

@app.route("/inpaint-editor", methods=["GET"])
def inpaint_editor():
    """Serwuje HTML UI dla web-based inpaint editora"""
    if not INPAINT_WEB_AVAILABLE:
        return jsonify({"error": "Inpaint web service not available"}), 503
    
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
    
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    return render_template("inpaint-editor.html")

@app.route("/api/inpaint/upload", methods=["POST"])
def inpaint_upload():
    """Utwórz sesję inpaint z uploadowanego obrazu"""
    if not INPAINT_WEB_AVAILABLE:
        return jsonify({"error": "Service not available"}), 503
    
    if "image" not in request.files:
        return jsonify({"error": "No image file"}), 400
    
    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    
    try:
        image_bytes = file.read()
        session_id = create_session(image_bytes)
        
        return jsonify({
            "session_id": session_id,
            "editor_url": f"/inpaint-editor?session_id={session_id}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/inpaint/preview", methods=["GET"])
def inpaint_preview():
    """Pobierz podgląd z aktualnym maskami"""
    if not INPAINT_WEB_AVAILABLE:
        return jsonify({"error": "Service not available"}), 503
    
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
    
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    scale = float(request.args.get("scale", 1.0))
    preview_bytes = session.get_preview(scale)
    
    return send_file(
        io.BytesIO(preview_bytes),
        mimetype="image/png",
        as_attachment=False
    )

@app.route("/api/inpaint/run", methods=["POST"])
def inpaint_run():
    """Uruchom inpainting"""
    if not INPAINT_WEB_AVAILABLE:
        return jsonify({"error": "Service not available"}), 503
    
    data = request.get_json() or {}
    session_id = data.get("session_id")
    model_name = data.get("model", "lama")
    dilation = int(data.get("dilation", 12))
    
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
    
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    result = session.run_inpainting(model_name, dilation)
    return jsonify(result)

@app.route("/api/inpaint/sam-predict", methods=["POST"])
def inpaint_sam_predict():
    """SAM prediction - druk maski dla zaznaczonego obiektu"""
    if not INPAINT_WEB_AVAILABLE:
        return jsonify({"error": "Service not available"}), 503
    
    data = request.get_json() or {}
    session_id = data.get("session_id")
    points = data.get("points", [])  # [[x, y, 1/0], ...]
    mode = data.get("mode", "red")  # red or green
    
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
    
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    try:
        result = session.predict_sam(points, mode)
        # result zawiera: {"mask_base64": "...", "preview_url": "/api/inpaint/preview?..."}
        return jsonify(result)
    except Exception as e:
        print(f"[inpaint_sam] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/inpaint/set-masks", methods=["POST"])
def inpaint_set_masks():
    """Ustaw red/green maski z canvas"""
    if not INPAINT_WEB_AVAILABLE:
        return jsonify({"error": "Service not available"}), 503
    
    data = request.get_json() or {}
    session_id = data.get("session_id")
    red_mask_b64 = data.get("red_mask", "")
    green_mask_b64 = data.get("green_mask", "")
    
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
    
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    try:
        import base64
        if red_mask_b64:
            mask_bytes = base64.b64decode(red_mask_b64)
            red_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
            session.red_mask = red_img
        
        if green_mask_b64:
            mask_bytes = base64.b64decode(green_mask_b64)
            green_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
            session.green_mask = green_img
        
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[inpaint_set_masks] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/inpaint/download", methods=["GET"])
def inpaint_download():
    """Pobierz final result"""
    if not INPAINT_WEB_AVAILABLE:
        return jsonify({"error": "Service not available"}), 503
    
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400
    
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    result_bytes = session.get_result_bytes()
    delete_session(session_id)
    
    return send_file(
        io.BytesIO(result_bytes),
        mimetype="image/png",
        as_attachment=True,
        download_name=f"inpaint-{session_id}.png"
    )

# ────────────────────────────────────────────────────────────────────────────────
# Startup diagnostics
print("\n" + "="*80)
print("[STARTUP] Background Remover API - Production Ready")
print("="*80)
print(f"[STARTUP] Python version: {sys.version.split()[0]}")
print(f"[STARTUP] Plugins loaded: {len(PLUGINS)}")
print(f"[STARTUP] Default plugin: {DEFAULT_PLUGIN}")
print(f"[STARTUP] Max upload: {MAX_UPLOAD_MB} MB")
print(f"[STARTUP] Max resolution: {MAX_RES_WIDTH}x{MAX_RES_HEIGHT}")
from pathlib import Path as _Path
plugins_dir = _Path("plugins")
if plugins_dir.exists():
    plugin_files = list(plugins_dir.glob("*.py"))
    print(f"[STARTUP] Plugins directory: {plugins_dir.absolute()} ({len(plugin_files)} files)")
print("="*80 + "\n")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)



