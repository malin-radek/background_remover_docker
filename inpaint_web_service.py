"""
Inpaint Web Service - Headless inpainting logic
Obsługuje SAM selection, mask management, inpainting
Wyizolowany od app.py - można testować niezależnie
"""

import io
import os
import json
import uuid
import tempfile
import urllib.request
import threading
import numpy as np
from PIL import Image, ImageFilter
from pathlib import Path
import torch

# SAM imports
try:
    from mobile_sam import sam_model_registry, SamPredictor
    SAM_AVAILABLE = True
except ImportError:
    try:
        from segment_anything import sam_model_registry, SamPredictor
        SAM_AVAILABLE = True
    except ImportError:
        SAM_AVAILABLE = False
        print("[inpaint_web_service] SAM not available")

# Device setup - force CPU (PyTorch without CUDA support)
_DEVICE = torch.device("cpu")
torch.set_num_threads(os.cpu_count() or 4)
print("[inpaint_web_service] Using CPU")

# Locks for model loading
_dl_lock = threading.Lock()
_model_cache = {}

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "plugins", "models")

# SAM checkpoint paths
MOBILE_SAM_URL = "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"
MOBILE_SAM_PATH = os.path.join(MODELS_DIR, "mobile_sam.pt")

# Inpainting model paths - use same as Tkinter
LAMA_URL = "https://huggingface.co/smartscaleai/big-lama/resolve/main/big-lama.pt"
LAMA_PATH = os.path.join(MODELS_DIR, "big-lama.pt")

MAT_URL = "https://github.com/Sanster/models/releases/download/add_mat/Places_512_FullData_G.pth"
MAT_PATH = os.path.join(MODELS_DIR, "mat_places512.pth")

print(f"[inpaint_web_service] BASE_DIR: {BASE_DIR}")
print(f"[inpaint_web_service] MODELS_DIR: {MODELS_DIR}")
print(f"[inpaint_web_service] MOBILE_SAM_PATH: {MOBILE_SAM_PATH} (exists: {os.path.exists(MOBILE_SAM_PATH)})")
print(f"[inpaint_web_service] LAMA_PATH: {LAMA_PATH} (exists: {os.path.exists(LAMA_PATH)})")
print(f"[inpaint_web_service] MAT_PATH: {MAT_PATH} (exists: {os.path.exists(MAT_PATH)})")

# Set inpainting availability
INPAINTING_AVAILABLE = os.path.exists(LAMA_PATH) or os.path.exists(MAT_PATH)

def _ensure_sam_checkpoint():
    """Download SAM checkpoint if not present"""
    if os.path.exists(MOBILE_SAM_PATH):
        return
    
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"[inpaint_web_service] Downloading MobileSAM checkpoint to {MOBILE_SAM_PATH}...")
    try:
        urllib.request.urlretrieve(MOBILE_SAM_URL, MOBILE_SAM_PATH)
        print(f"[inpaint_web_service] SAM checkpoint downloaded")
    except Exception as e:
        print(f"[inpaint_web_service] Failed to download SAM: {e}")


def _get_lama():
    """Load big-LaMa model (same as Tkinter)"""
    with _dl_lock:
        if "lama" not in _model_cache:
            try:
                from simple_lama_inpainting import SimpleLama
                obj = SimpleLama()
                _model_cache["lama"] = ("simple", obj)
                print("[inpaint_web_service] SimpleLama loaded")
            except ImportError:
                if not os.path.exists(LAMA_PATH):
                    raise RuntimeError(f"LaMa model not found at {LAMA_PATH}")
                print(f"[inpaint_web_service] Loading big-LaMa from {LAMA_PATH}...")
                # Force CPU to avoid CUDA issues with old JIT model
                model = torch.jit.load(LAMA_PATH, map_location='cpu')
                model = model.to('cpu')
                model.eval()
                _model_cache["lama"] = ("raw", model)
                print(f"[inpaint_web_service] big-LaMa loaded on CPU")
    return _model_cache["lama"]


def _run_lama(image_pil: Image.Image, mask_pil: Image.Image) -> Image.Image:
    """Run LaMa inpainting"""
    kind, model = _get_lama()
    if kind == "simple":
        return model(image_pil, mask_pil)
    # raw jit - use _DEVICE (global)
    img_t = torch.from_numpy(np.array(image_pil).astype(np.float32)/255.0).permute(2,0,1).unsqueeze(0).to(_DEVICE)
    m_np = (np.array(mask_pil) > 127).astype(np.float32)
    mask_t = torch.from_numpy(m_np).unsqueeze(0).unsqueeze(0).to(_DEVICE)
    with torch.no_grad():
        out_t = model(torch.cat([img_t*(1-mask_t), mask_t], dim=1))
    out = out_t.squeeze().clamp(0,1).cpu().numpy().transpose(1,2,0)
    return Image.fromarray((out*255).astype(np.uint8))


def _get_mat():
    """Load MAT model (same as Tkinter)"""
    with _dl_lock:
        if "mat" not in _model_cache:
            if not os.path.exists(MAT_PATH):
                raise RuntimeError(f"MAT model not found at {MAT_PATH}")
            try:
                from spandrel import ModelLoader
                m = ModelLoader().load_from_file(MAT_PATH)
            except Exception:
                m = torch.load(MAT_PATH, map_location=_DEVICE, weights_only=False)
            if hasattr(m, "to"):
                m.to(_DEVICE)
            if hasattr(m, "eval"):
                m.eval()
            _model_cache["mat"] = m
            print("[inpaint_web_service] MAT loaded from file")
    return _model_cache["mat"]


def _run_mat(image_pil: Image.Image, mask_pil: Image.Image) -> Image.Image:
    """Run MAT inpainting"""
    ow, oh = image_pil.size
    img512 = image_pil.resize((512, 512), Image.Resampling.LANCZOS)
    msk512 = mask_pil.resize((512, 512), Image.Resampling.NEAREST)
    
    model = _get_mat()
    # Determine device - MAT model is OrderedDict, not a nn.Module
    model_device = _DEVICE
    
    img_t = torch.from_numpy(np.array(img512).astype(np.float32)/255.0).permute(2,0,1).unsqueeze(0).to(model_device)
    m_np = (np.array(msk512) > 127).astype(np.float32)
    mask_t = torch.from_numpy(m_np).unsqueeze(0).unsqueeze(0).to(model_device)
    try:
        with torch.no_grad():
            out = model(img_t, mask_t)
        out_t = out.image if hasattr(out, "image") else out
    except TypeError:
        with torch.no_grad():
            out_t = model(img_t*(1-mask_t), mask_t)
    out_np = out_t.squeeze().clamp(0,1).cpu().numpy().transpose(1,2,0)
    return Image.fromarray((out_np*255).astype(np.uint8)).resize((ow, oh), Image.Resampling.LANCZOS)


def _dilate_mask(mask_np: np.ndarray, px: int) -> np.ndarray:
    """Dilate binary mask (same as Tkinter)"""
    if px <= 0:
        return mask_np
    pil = Image.fromarray((mask_np*255).astype(np.uint8))
    pil = pil.filter(ImageFilter.MaxFilter(size=px*2+1))
    return (np.array(pil) > 127).astype(np.float32)


class InpaintSession:
    """Zarządza sesją edycji inpainting'u"""
    
    def __init__(self, image_bytes: bytes):
        self.session_id = str(uuid.uuid4())[:8]
        self.image_bytes = image_bytes
        self.pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        self.width, self.height = self.pil_image.size
        
        # Maski
        self.red_mask = Image.new("L", (self.width, self.height), 0)
        self.green_mask = Image.new("L", (self.width, self.height), 0)
        
        # SAM cache
        self.sam_mask = None
        self.sam_preview = None
        
        # Historia
        self.history = []
        
        # Modele
        self.sam = None
        self.inpaint_model = None
        
        print(f"[inpaint_web_service] Session {self.session_id} created: {self.width}x{self.height}")
    
    def get_preview(self, scale: float = 1.0) -> bytes:
        """Zwróć preview z nałożonymi maskami"""
        w, h = int(self.width * scale), int(self.height * scale)
        img = self.pil_image.resize((w, h), Image.Resampling.LANCZOS)
        
        # Red mask overlay
        red_np = np.array(self.red_mask.resize((w, h), Image.Resampling.LANCZOS))
        red_overlay = np.zeros((h, w, 3), dtype=np.uint8)
        red_overlay[red_np > 0] = [255, 0, 0]
        
        # Green mask overlay
        grn_np = np.array(self.green_mask.resize((w, h), Image.Resampling.LANCZOS))
        grn_overlay = np.zeros((h, w, 3), dtype=np.uint8)
        grn_overlay[grn_np > 0] = [0, 255, 0]
        
        # Blend
        img_np = np.array(img)
        img_np = np.clip(img_np.astype(np.float32) * 0.7 + red_overlay.astype(np.float32) * 0.3, 0, 255).astype(np.uint8)
        img_np = np.clip(img_np.astype(np.float32) * 0.7 + grn_overlay.astype(np.float32) * 0.3, 0, 255).astype(np.uint8)
        
        result = Image.fromarray(img_np)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()
    
    def get_preview_with_sam(self, scale: float = 1.0) -> bytes:
        """Zwróć preview z SAM mask podglądem"""
        if self.sam_preview is None:
            return self.get_preview(scale)
        
        w, h = int(self.width * scale), int(self.height * scale)
        img = self.pil_image.resize((w, h), Image.Resampling.LANCZOS)
        sam_np = np.array(self.sam_preview.resize((w, h), Image.Resampling.LANCZOS))
        
        # SAM preview - semi-transparent overlay
        sam_overlay = np.zeros((h, w, 3), dtype=np.uint8)
        sam_overlay[sam_np > 0] = [255, 200, 0]  # Złoty kolor dla SAM
        
        img_np = np.array(img)
        img_np = np.clip(img_np.astype(np.float32) * 0.6 + sam_overlay.astype(np.float32) * 0.4, 0, 255).astype(np.uint8)
        
        result = Image.fromarray(img_np)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()
    
    def set_red_mask_from_bytes(self, mask_bytes: bytes):
        """Ustaw red_mask z bajtów (PNG grayscale)"""
        mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
        self.red_mask = mask_img.resize((self.width, self.height), Image.Resampling.LANCZOS)
        print(f"[inpaint_web_service] Red mask set from bytes: {mask_img.size} -> {self.red_mask.size}")
    
    def set_green_mask_from_bytes(self, mask_bytes: bytes):
        """Ustaw green_mask z bajtów"""
        mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
        self.green_mask = mask_img.resize((self.width, self.height), Image.Resampling.LANCZOS)
        print(f"[inpaint_web_service] Green mask set from bytes")
    
    def predict_sam(self, points: list, mode: str = "red") -> dict:
        """
        Predict SAM mask z punktów/linii
        points: lista [x, y] współrzędnych
        mode: "red" (usuń) lub "green" (chroń)
        """
        if not SAM_AVAILABLE:
            return {"error": "SAM not available"}
        
        if self.sam is None:
            print("[inpaint_web_service] Loading MobileSAM...")
            try:
                _ensure_sam_checkpoint()
                # Load SAM model and wrap in SamPredictor (same as Tkinter)
                sam = sam_model_registry["vit_t"](checkpoint=MOBILE_SAM_PATH).to(_DEVICE)
                sam.eval()
                self.sam = SamPredictor(sam)
                print(f"[inpaint_web_service] SAM (vit_t + SamPredictor) loaded on {_DEVICE}")
            except Exception as e:
                print(f"[inpaint_web_service] SAM load error: {e}")
                import traceback
                traceback.print_exc()
                return {"error": f"Failed to load SAM: {e}"}
        
        try:
            # Set image for SAM
            self.sam.set_image(np.array(self.pil_image))
            
            # Convert points to SAM format
            input_point = np.array(points, dtype=np.float32)
            input_label = np.ones(len(points), dtype=np.int32)
            
            # Predict
            masks, scores, logits = self.sam.predict(
                point_coords=input_point,
                point_labels=input_label,
                multimask_output=True
            )
            
            # Pick best mask
            mask_np = (masks[int(np.argmax(scores))] > 0).astype(np.uint8) * 255
            self.sam_mask = mask_np
            self.sam_preview = Image.fromarray(mask_np, mode="L")
            
            # Apply to appropriate color mask
            if mode == "red":
                # Add SAM to red (to remove)
                red_np = np.array(self.red_mask, dtype=np.int32)
                red_np = np.clip(red_np + mask_np.astype(np.int32), 0, 255).astype(np.uint8)
                self.red_mask = Image.fromarray(red_np, mode="L")
            else:  # mode == "green"
                # Add SAM to green (to protect)
                grn_np = np.array(self.green_mask, dtype=np.int32)
                grn_np = np.clip(grn_np + mask_np.astype(np.int32), 0, 255).astype(np.uint8)
                self.green_mask = Image.fromarray(grn_np, mode="L")
            
            return {
                "success": True,
                "mode": mode,
                "preview": self._image_to_base64(self.sam_preview)
            }
        except Exception as e:
            return {"error": f"SAM prediction failed: {e}"}
    
    def run_inpainting(self, model_name: str = "lama", dilation: int = 12) -> dict:
        """Uruchom inpainting z aktualnym maskami (same logic as Tkinter)"""
        if not INPAINTING_AVAILABLE:
            return {"error": "Inpainting models not available"}
        
        try:
            # Prepare mask
            red_np = (np.array(self.red_mask) > 0).astype(np.float32)
            grn_np = (np.array(self.green_mask) > 0).astype(np.float32)
            
            # Dilate red mask
            mask_np = _dilate_mask(red_np, dilation)
            # Remove green-protected areas
            mask_np = np.clip(mask_np - (grn_np > 0.5).astype(np.float32), 0, 1)
            
            # Convert mask to PIL Image
            mask_pil = Image.fromarray((mask_np * 255).astype(np.uint8))
            
            # Run inpainting
            print(f"[inpaint_web_service] Running {model_name} inpainting...")
            if model_name == "mat":
                result_img = _run_mat(self.pil_image, mask_pil)
            else:
                try:
                    result_img = _run_lama(self.pil_image, mask_pil)
                except RuntimeError as e:
                    if "CUDA" in str(e) or "aten::" in str(e):
                        print(f"[inpaint_web_service] LaMa failed with device error, falling back to MAT: {e}")
                        result_img = _run_mat(self.pil_image, mask_pil)
                    else:
                        raise
            
            # Save result to bytes
            buf = io.BytesIO()
            result_img.save(buf, format="PNG")
            result_bytes = buf.getvalue()
            
            # Store result
            self.pil_image = result_img
            
            print(f"[inpaint_web_service] Inpainting done: {len(result_bytes)} bytes")
            return {
                "success": True,
                "image_base64": self._image_to_base64(result_img),
                "size_bytes": len(result_bytes)
            }
        except Exception as e:
            print(f"[inpaint_web_service] Inpainting error: {e}")
            import traceback
            traceback.print_exc()
            return {"error": f"Inpainting failed: {e}"}
    
    def get_result_bytes(self) -> bytes:
        """Zwróć final result jako PNG bytes"""
        buf = io.BytesIO()
        self.pil_image.save(buf, format="PNG")
        return buf.getvalue()
    
    @staticmethod
    def _has_cuda() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False
    
    @staticmethod
    def _dilate_mask(mask: np.ndarray, kernel_size: int) -> np.ndarray:
        """Dilate mask z kernel_size"""
        from scipy import ndimage
        if kernel_size <= 0:
            return mask
        kernel = np.ones((kernel_size, kernel_size))
        return ndimage.binary_dilation(mask, structure=kernel).astype(np.float32)
    
    @staticmethod
    def _image_to_base64(img: Image.Image) -> str:
        import base64
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()


# Global session store (w produkcji to byłaby Redis/database)
_sessions = {}

def create_session(image_bytes: bytes) -> str:
    """Utwórz nową sesję edycji"""
    session = InpaintSession(image_bytes)
    _sessions[session.session_id] = session
    return session.session_id

def get_session(session_id: str) -> InpaintSession:
    """Pobierz sesję"""
    return _sessions.get(session_id)

def delete_session(session_id: str):
    """Usuń sesję"""
    if session_id in _sessions:
        del _sessions[session_id]
        print(f"[inpaint_web_service] Session {session_id} deleted")
