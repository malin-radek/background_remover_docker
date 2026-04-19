"""
Plugin: Inpaint AI Pro v2
- Czerwona kreska = zaznacz do usunięcia
- Zielona kreska = chroń obszar
- Tryb AI: linia czerwona → MobileSAM segmentuje obiekt pod linią → podgląd → zatwierdzasz
- Inpainting: big-LaMa (generuje tło, nie tylko blend) lub MAT
- GPU/CPU auto
"""

METADATA = {
    "id": "inpaint_ai_v2",
    "name": "Usuwanie obiektów AI",
    "description": "Inteligentne zaznaczanie przez SAM + usuwanie obiektów przez LaMa/MAT.",
    "version": "2.0.0",
    "author": "Radek",
    "icon": "🎨",
    "disable_scaling": True,
    "dropzone": False,
    "options": {
        "inpaint_model": {
            "type": "select",
            "label": "Model inpaintingu",
            "choices": {
                "lama": "big-LaMa (szybki, świetny do tła i tekstur)",
                "mat":  "MAT Places512 (lepszy dla złożonych scen)",
            },
            "default": "lama",
        },
        "smart_select": {
            "type": "select",
            "label": "Tryb zaznaczania",
            "choices": {
                "on":  "AI (SAM) — linia zaznacza cały obiekt",
                "off": "Ręczny — klasyczne malowanie pędzlem",
            },
            "default": "on",
        },
        "brush_size": {
            "type": "slider",
            "label": "Grubość pędzla",
            "min": 5,
            "max": 80,
            "default": 20,
        },
        "mask_dilation": {
            "type": "slider",
            "label": "Rozszerzenie maski (px)",
            "min": 0,
            "max": 40,
            "default": 12,
        },
    },
}

import io
import os
import threading
import urllib.request
import tkinter as tk
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk
import torch
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Urządzenie
# ---------------------------------------------------------------------------
_CUDA = torch.cuda.is_available()
_DEVICE = torch.device("cuda" if _CUDA else "cpu")
if not _CUDA:
    torch.set_num_threads(os.cpu_count() or 4)

# ---------------------------------------------------------------------------
# Ścieżki modeli
# ---------------------------------------------------------------------------
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

MOBILE_SAM_URL  = "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"
MOBILE_SAM_PATH = os.path.join(MODELS_DIR, "mobile_sam.pt")

LAMA_URL  = "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"
LAMA_PATH = os.path.join(MODELS_DIR, "big-lama.pt")

MAT_URL   = "https://github.com/Sanster/models/releases/download/add_mat/Places_512_FullData_G.pth"
MAT_PATH  = os.path.join(MODELS_DIR, "mat_places512.pth")

_model_cache: dict = {}
_dl_lock = threading.Lock()
_sam_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Pobieranie modeli
# ---------------------------------------------------------------------------
def _download(url: str, path: str, label: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(MODELS_DIR, exist_ok=True)
    print(f"[inpaint_ai] Pobieranie {label}…")
    tmp = path + ".tmp"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
        ("Accept", "*/*"),
    ]
    try:
        with opener.open(url) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        os.rename(tmp, path)
        print(f"[inpaint_ai] Pobrano {label} ({os.path.getsize(path)//1024//1024} MB).")
    except Exception as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(f"Błąd pobierania {label}: {exc}\nURL: {url}") from exc


# ---------------------------------------------------------------------------
# MobileSAM
# ---------------------------------------------------------------------------
def _get_sam_predictor():
    with _dl_lock:
        if "sam" not in _model_cache:
            _download(MOBILE_SAM_URL, MOBILE_SAM_PATH, "MobileSAM")
            try:
                from mobile_sam import sam_model_registry, SamPredictor
                sam_type = "vit_t"
            except ImportError:
                from segment_anything import sam_model_registry, SamPredictor
                sam_type = "vit_b"
            sam = sam_model_registry[sam_type](checkpoint=MOBILE_SAM_PATH)
            sam.to(_DEVICE)
            sam.eval()
            _model_cache["sam"] = SamPredictor(sam)
    return _model_cache["sam"]


def _sam_segment(image_np: np.ndarray, points_xy: list) -> np.ndarray:
    """
    image_np: H×W×3 uint8
    points_xy: lista (x,y) w pikselach full-res
    Zwraca H×W bool mask
    """
    with _sam_lock:
        predictor = _get_sam_predictor()
        predictor.set_image(image_np)

        pts = np.array(points_xy, dtype=np.float32)
        lbs = np.ones(len(pts), dtype=np.int32)

        masks, scores, _ = predictor.predict(
            point_coords=pts,
            point_labels=lbs,
            multimask_output=True,
        )
    return masks[int(np.argmax(scores))]


# ---------------------------------------------------------------------------
# big-LaMa
# ---------------------------------------------------------------------------
def _get_lama():
    with _dl_lock:
        if "lama" not in _model_cache:
            try:
                # Preferowane: simple_lama_inpainting — auto-GPU, czyste API
                from simple_lama_inpainting import SimpleLama
                obj = SimpleLama()
                _model_cache["lama"] = ("simple", obj)
            except ImportError:
                _download(LAMA_URL, LAMA_PATH, "big-LaMa")
                model = torch.jit.load(LAMA_PATH, map_location=_DEVICE)
                model.eval()
                _model_cache["lama"] = ("raw", model)
    return _model_cache["lama"]


def _run_lama(image_pil: Image.Image, mask_pil: Image.Image) -> Image.Image:
    kind, model = _get_lama()
    if kind == "simple":
        return model(image_pil, mask_pil)
    # raw jit
    img_t  = torch.from_numpy(np.array(image_pil).astype(np.float32)/255.0).permute(2,0,1).unsqueeze(0).to(_DEVICE)
    m_np   = (np.array(mask_pil) > 127).astype(np.float32)
    mask_t = torch.from_numpy(m_np).unsqueeze(0).unsqueeze(0).to(_DEVICE)
    with torch.no_grad():
        out_t = model(torch.cat([img_t*(1-mask_t), mask_t], dim=1))
    out = out_t.squeeze().clamp(0,1).cpu().numpy().transpose(1,2,0)
    return Image.fromarray((out*255).astype(np.uint8))


# ---------------------------------------------------------------------------
# MAT
# ---------------------------------------------------------------------------
def _get_mat():
    with _dl_lock:
        if "mat" not in _model_cache:
            _download(MAT_URL, MAT_PATH, "MAT Places512")
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
    return _model_cache["mat"]


def _run_mat(image_pil: Image.Image, mask_pil: Image.Image) -> Image.Image:
    ow, oh = image_pil.size
    img512  = image_pil.resize((512,512), Image.Resampling.LANCZOS)
    msk512  = mask_pil.resize((512,512),  Image.Resampling.NEAREST)
    img_t   = torch.from_numpy(np.array(img512).astype(np.float32)/255.0).permute(2,0,1).unsqueeze(0).to(_DEVICE)
    m_np    = (np.array(msk512)>127).astype(np.float32)
    mask_t  = torch.from_numpy(m_np).unsqueeze(0).unsqueeze(0).to(_DEVICE)
    model   = _get_mat()
    try:
        with torch.no_grad():
            out = model(img_t, mask_t)
        out_t = out.image if hasattr(out, "image") else out
    except TypeError:
        with torch.no_grad():
            out_t = model(img_t*(1-mask_t), mask_t)
    out_np = out_t.squeeze().clamp(0,1).cpu().numpy().transpose(1,2,0)
    return Image.fromarray((out_np*255).astype(np.uint8)).resize((ow,oh), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
def _inpaint(image_pil: Image.Image, mask_np: np.ndarray, model_id: str) -> Image.Image:
    mask_pil = Image.fromarray((mask_np*255).astype(np.uint8))
    try:
        return _run_mat(image_pil, mask_pil) if model_id == "mat" else _run_lama(image_pil, mask_pil)
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            torch.cuda.empty_cache()
            raise RuntimeError("Błąd VRAM! Zmniejsz obraz lub użyj CPU.") from exc
        raise


def _dilate(mask_np: np.ndarray, px: int) -> np.ndarray:
    if px <= 0:
        return mask_np
    pil = Image.fromarray((mask_np*255).astype(np.uint8))
    pil = pil.filter(ImageFilter.MaxFilter(size=px*2+1))
    return (np.array(pil)>127).astype(np.float32)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
MAX_DISPLAY = 900


class InpaintWindow:

    def __init__(self, image_bytes: bytes, options: dict):
        self.orig_pil      = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        self.options       = options
        self.result        = None
        self.error         = None

        self.inpaint_model = options.get("inpaint_model", "lama")
        self.brush_r       = int(options.get("brush_size", 20)) // 2
        self.dilation      = int(options.get("mask_dilation", 12))
        self.smart_on      = options.get("smart_select", "on") == "on"

        self._update_scale()

        ow, oh = self.orig_pil.size
        self._red_mask   = Image.new("L", (ow, oh), 0)
        self._green_mask = Image.new("L", (ow, oh), 0)
        self._history    = []
        self._ai_stroke  = []      # punkty full-res aktualnej linii AI
        self._confirm_frame = None # ramka z przyciskami zatwierdzenia

        self._build_ui()

    def _update_scale(self):
        ow, oh = self.orig_pil.size
        s = min(MAX_DISPLAY / max(ow, oh), 1.0)
        self.scale = s
        self.dw    = int(ow * s)
        self.dh    = int(oh * s)

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("Inpaint AI Pro v2")
        self.root.configure(bg="#1a1a1a")
        self.root.resizable(False, False)

        # --- Toolbar ---
        tb = tk.Frame(self.root, bg="#252525", pady=5)
        tb.pack(fill="x")

        self.mode_var = tk.StringVar(value="red")
        for val, txt, sel in [("red","🔴 Usuń","#500000"),("green","🟢 Zachowaj","#005000")]:
            tk.Radiobutton(tb, text=txt, variable=self.mode_var, value=val,
                           bg="#252525", fg="white", selectcolor=sel,
                           activebackground="#252525",
                           font=("Segoe UI",10,"bold" if val=="red" else "normal")
                           ).pack(side="left", padx=8)

        tk.Frame(tb, bg="#444", width=1, height=28).pack(side="left", padx=8)

        self.ai_var = tk.BooleanVar(value=self.smart_on)
        tk.Checkbutton(tb, text="🤖 Smart SAM", variable=self.ai_var,
                       bg="#252525", fg="white", selectcolor="#003050",
                       activebackground="#252525", font=("Segoe UI",10),
                       command=self._on_ai_toggle
                       ).pack(side="left", padx=8)

        tk.Frame(tb, bg="#444", width=1, height=28).pack(side="left", padx=8)

        tk.Label(tb, text="Pędzel:", bg="#252525", fg="#aaa", font=("Segoe UI",9)
                 ).pack(side="left")
        self.brush_var = tk.IntVar(value=self.brush_r*2)
        tk.Scale(tb, from_=4, to=120, orient="horizontal",
                 variable=self.brush_var, bg="#252525", fg="white",
                 troughcolor="#555", highlightthickness=0, length=90,
                 command=lambda v: setattr(self,"brush_r",int(v)//2)
                 ).pack(side="left", padx=4)

        tk.Frame(tb, bg="#444", width=1, height=28).pack(side="left", padx=8)

        tk.Button(tb, text="↩ Cofnij", command=self._undo,
                  bg="#333", fg="white", relief="flat", padx=6, pady=2
                  ).pack(side="left", padx=4)
        tk.Button(tb, text="🗑 Wyczyść", command=self._clear,
                  bg="#333", fg="white", relief="flat", padx=6, pady=2
                  ).pack(side="left", padx=4)

        tk.Button(tb, text="✨ Uruchom inpainting", command=self._run_inpaint,
                  bg="#0078d4", fg="white", relief="flat",
                  font=("Segoe UI",10,"bold"), padx=12, pady=2
                  ).pack(side="right", padx=12)

        # --- Canvas ---
        self.canvas = tk.Canvas(self.root, width=self.dw, height=self.dh,
                                cursor="crosshair", bg="#111", highlightthickness=0)
        self.canvas.pack()

        # --- Statusbar ---
        self.status = tk.StringVar(
            value=f"GPU: {'TAK (' + torch.cuda.get_device_name(0) + ')' if _CUDA else 'NIE (CPU)'}  |  "
                  f"Smart SAM: {'włączony' if self.smart_on else 'wyłączony'}"
        )
        tk.Label(self.root, textvariable=self.status,
                 bg="#111", fg="#bbb", anchor="w", padx=6, pady=3,
                 font=("Segoe UI",9)).pack(fill="x")

        # Bindings
        self.canvas.bind("<ButtonPress-1>",   self._press)
        self.canvas.bind("<B1-Motion>",       self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)

        self._refresh()

    def _on_ai_toggle(self):
        self.smart_on = self.ai_var.get()
        self.status.set(f"Smart SAM: {'włączony' if self.smart_on else 'wyłączony'}")

    # -----------------------------------------------------------------------
    # Rysowanie
    # -----------------------------------------------------------------------
    def _press(self, evt):
        self._save_history()
        if self.smart_on and self.mode_var.get() == "red":
            self._ai_stroke = [self._d2f(evt.x, evt.y)]
        else:
            self._paint(evt.x, evt.y)

    def _drag(self, evt):
        if self.smart_on and self.mode_var.get() == "red":
            pt = self._d2f(evt.x, evt.y)
            if not self._ai_stroke or pt != self._ai_stroke[-1]:
                self._ai_stroke.append(pt)
            if len(self._ai_stroke) >= 2:
                p1 = self._f2d(*self._ai_stroke[-2])
                p2 = self._f2d(*self._ai_stroke[-1])
                self.canvas.create_line(p1[0],p1[1],p2[0],p2[1],
                                        fill="#ff5555", width=2, tags="ai_line")
        else:
            self._paint(evt.x, evt.y)

    def _release(self, evt):
        if self.smart_on and self.mode_var.get() == "red" and len(self._ai_stroke) >= 1:
            self.canvas.delete("ai_line")
            pts = self._sample_stroke(self._ai_stroke, max_pts=10)
            self._ai_stroke = []
            self._run_sam(pts)

    def _d2f(self, cx, cy):
        return int(cx/self.scale), int(cy/self.scale)

    def _f2d(self, fx, fy):
        return int(fx*self.scale), int(fy*self.scale)

    def _sample_stroke(self, pts, max_pts=10):
        if len(pts) <= max_pts:
            return pts
        step = max(1, len(pts)//(max_pts-1))
        sampled = pts[::step]
        if sampled[-1] != pts[-1]:
            sampled.append(pts[-1])
        return sampled

    def _paint(self, cx, cy):
        fx, fy = self._d2f(cx, cy)
        r = self.brush_r
        dr = ImageDraw.Draw(self._red_mask)
        dg = ImageDraw.Draw(self._green_mask)
        if self.mode_var.get() == "red":
            dr.ellipse([fx-r,fy-r,fx+r,fy+r], fill=255)
            dg.ellipse([fx-r,fy-r,fx+r,fy+r], fill=0)
        else:
            dg.ellipse([fx-r,fy-r,fx+r,fy+r], fill=255)
            dr.ellipse([fx-r,fy-r,fx+r,fy+r], fill=0)
        self._refresh()

    # -----------------------------------------------------------------------
    # SAM flow
    # -----------------------------------------------------------------------
    def _run_sam(self, pts):
        self.status.set("⏳ MobileSAM segmentuje obiekt…")
        self.root.update()

        def worker():
            try:
                img_np = np.array(self.orig_pil)
                mask   = _sam_segment(img_np, pts)
                self.root.after(0, self._show_sam_preview, mask)
            except Exception as exc:
                self.root.after(0, lambda: self.status.set(f"❌ SAM błąd: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_sam_preview(self, mask_bool: np.ndarray):
        # Nakładka tymczasowa - kolor zależy od trybu
        ow, oh = self.orig_pil.size
        ov = np.zeros((oh, ow, 4), dtype=np.uint8)
        
        # Wybierz kolor na podstawie trybu
        if self.mode_var.get() == "red":
            # Tryb Usuń - pokazuj CZERWONY
            ov[mask_bool] = [255, 80, 80, 170]
        else:
            # Tryb Zachowaj - pokazuj ZIELONY
            ov[mask_bool] = [80, 255, 80, 170]
        
        preview = Image.alpha_composite(
            self.orig_pil.convert("RGBA"),
            Image.fromarray(ov, "RGBA")
        ).convert("RGB")
        disp = preview.resize((self.dw, self.dh), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(disp)
        self.canvas.create_image(0,0, anchor="nw", image=tk_img, tags="sam_ov")
        self.canvas._sam_ref = tk_img

        self.status.set("SAM zaznaczył obiekt. [T] = zatwierdź  [Y] = odrzuć")

        # Ramka zatwierdzenia
        if self._confirm_frame:
            self._confirm_frame.destroy()
        frm = tk.Frame(self.root, bg="#1a1a1a", pady=4)
        frm.pack(fill="x")
        self._confirm_frame = frm

        def accept():
            mode = self.mode_var.get()
            mask_np  = mask_bool.astype(np.float32)
            sam_pil  = Image.fromarray((mask_np*255).astype(np.uint8))
            
            # WAŻNE: Konwertuj do int32 PRZED operacjami arytmetycznymi
            # aby uniknąć overflow'u uint8 przy odejmowaniu!
            red_arr  = np.clip(np.array(self._red_mask, dtype=np.int32)  + np.array(sam_pil, dtype=np.int32), 0, 255).astype(np.uint8)
            grn_arr  = np.clip(np.array(self._green_mask, dtype=np.int32) - np.array(sam_pil, dtype=np.int32), 0, 255).astype(np.uint8)
            
            # DEBUG
            sam_arr = np.array(sam_pil)
            print(f"[SAM] Mode: {mode}, SAM mask sum: {sam_arr.sum()}, Red before: {np.array(self._red_mask).sum()}, Green before: {np.array(self._green_mask).sum()}")
            print(f"[SAM] After compute - Red sum: {red_arr.sum()}, Green sum: {grn_arr.sum()}")
            
            # Jeśli tryb to "green" (Zachowaj), ZAMIEŃ maski
            if mode == "green":
                red_arr, grn_arr = grn_arr, red_arr
                print(f"[SAM] SWAPPED - Red sum: {red_arr.sum()}, Green sum: {grn_arr.sum()}")
            
            self._red_mask   = Image.fromarray(red_arr)
            self._green_mask = Image.fromarray(grn_arr)
            self.canvas.delete("sam_ov")
            frm.destroy()
            self._confirm_frame = None
            self._refresh()
            self.status.set("✅ Zaznaczenie zatwierdzone.")
            self.root.unbind("<t>"); self.root.unbind("<y>")

        def reject():
            self._undo()
            self.canvas.delete("sam_ov")
            frm.destroy()
            self._confirm_frame = None
            self._refresh()
            self.status.set("Zaznaczenie odrzucone.")
            self.root.unbind("<t>"); self.root.unbind("<y>")

        tk.Button(frm, text="✅ Zatwierdź [T]", command=accept,
                  bg="#0a7a0a", fg="white", relief="flat",
                  font=("Segoe UI",10,"bold"), padx=12, pady=4
                  ).pack(side="left", padx=12)
        tk.Button(frm, text="❌ Odrzuć [Y]", command=reject,
                  bg="#7a0a0a", fg="white", relief="flat",
                  padx=10, pady=4
                  ).pack(side="left")

        self.root.bind("<t>", lambda e: accept())
        self.root.bind("<y>", lambda e: reject())

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------
    def _refresh(self):
        disp = self.orig_pil.resize((self.dw, self.dh), Image.Resampling.LANCZOS).convert("RGBA")

        red_d   = np.array(self._red_mask.resize((self.dw, self.dh), Image.Resampling.NEAREST))
        green_d = np.array(self._green_mask.resize((self.dw, self.dh), Image.Resampling.NEAREST))

        ov = np.zeros((self.dh, self.dw, 4), dtype=np.uint8)
        ov[red_d   > 0] = [220,  30,  30, 150]
        ov[green_d > 0] = [ 30, 210,  60, 150]
        disp = Image.alpha_composite(disp, Image.fromarray(ov, "RGBA"))

        self._tk_img = ImageTk.PhotoImage(disp.convert("RGB"))
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

    # -----------------------------------------------------------------------
    # Historia
    # -----------------------------------------------------------------------
    def _save_history(self):
        self._history.append((self._red_mask.copy(), self._green_mask.copy()))
        if len(self._history) > 40:
            self._history.pop(0)

    def _undo(self):
        if self._history:
            self._red_mask, self._green_mask = self._history.pop()
            self._refresh()

    def _clear(self):
        self._save_history()
        ow, oh = self.orig_pil.size
        self._red_mask   = Image.new("L", (ow, oh), 0)
        self._green_mask = Image.new("L", (ow, oh), 0)
        self._refresh()

    # -----------------------------------------------------------------------
    # Inpainting
    # -----------------------------------------------------------------------
    def _run_inpaint(self):
        if np.array(self._red_mask).max() == 0:
            self.status.set("⚠ Brak czerwonej maski — zaznacz co usunąć.")
            return
        self.status.set("⏳ Inpainting AI… (może chwilę potrwać)")
        self.root.update()

        def worker():
            try:
                red_np  = (np.array(self._red_mask)   > 0).astype(np.float32)
                grn_np  = (np.array(self._green_mask) > 0).astype(np.float32)
                mask_np = _dilate(red_np, self.dilation)
                mask_np = np.clip(mask_np - (grn_np > 0.5).astype(np.float32), 0, 1)

                result_pil = _inpaint(self.orig_pil, mask_np, self.inpaint_model)

                buf = io.BytesIO()
                result_pil.save(buf, format="PNG")
                self.result = buf.getvalue()
                self.root.after(0, self._show_result, result_pil)
            except Exception as exc:
                self.error = str(exc)
                self.root.after(0, lambda err=str(exc): self.status.set(f"❌ Błąd: {err}"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, result_pil: Image.Image):
        """Wynik inpaintingu został obliczony - zamknij okno edycji"""
        self.status.set("✅ Gotowe! Zamykam...")
        self.root.after(800, self.root.destroy)  # Czekaj 800ms aby użytkownik widział status, potem zamknij

    # -----------------------------------------------------------------------
    def run(self):
        self.root.mainloop()
        return self.result, self.error


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def process(image_bytes: bytes, options: dict) -> bytes:
    """
    Headless inpaint plugin - returns original image.
    
    Interactive editing is now available through:
    POST /api/inpaint/upload -> create session
    GET /inpaint-editor?session_id=... -> web-based editor
    
    This plugin is kept for API compatibility but users should
    use the web editor instead (better UX, works on Docker).
    """
    print("[inpaint_ai_v2] Plugin deprecated - use web editor instead")
    return image_bytes
