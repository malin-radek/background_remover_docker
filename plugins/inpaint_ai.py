"""
Plugin: Inpaint AI Pro
Rysowanie maski (czerwona = usuń, zielona = zachowaj) w osobnym oknie GUI,
następnie inpainting przy użyciu big-LaMa lub MAT.
"""

METADATA = {
    "id": "inpaint_ai",
    "name": "Usuwanie obiektów AI",
    "description": "Zaznacz obiekt czerwoną kreską (usuń) i zieloną (zachowaj), AI uzupełni tło.",
    "version": "1.0.0",
    "author": "Radek",
    "icon": "🎨",
    "disable_scaling": True,
    "options": {
        "model_type": {
            "type": "select",
            "label": "Model inpaintingu",
            "choices": {
                "big_lama": "big-LaMa (szybki, świetny do tła)",
                "mat":      "MAT Places512 (lepszy dla złożonych scen)",
            },
            "default": "big_lama",
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
from tkinter import ttk
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

import torch
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Modele
# ---------------------------------------------------------------------------
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

MODEL_URLS = {
    "big_lama": (
        "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt"
    ),
    "mat": (
        "https://github.com/Sanster/models/releases/download/add_mat/Places_512_FullData_G.pth"
    ),
}

MODEL_FILES = {
    "big_lama": "big-lama.pt",
    "mat":      "mat_places512.pth",
}

_models_cache: dict = {}
_lock = threading.Lock()

if torch.cuda.is_available():
    _device = torch.device("cuda")
else:
    _device = torch.device("cpu")
    torch.set_num_threads(os.cpu_count() or 4)


# ---------------------------------------------------------------------------
# Pobieranie modelu
# ---------------------------------------------------------------------------
def _download_model(model_id: str) -> str:
    fname = MODEL_FILES[model_id]
    path  = os.path.join(MODELS_DIR, fname)
    if os.path.exists(path):
        return path

    os.makedirs(MODELS_DIR, exist_ok=True)
    url  = MODEL_URLS[model_id]
    tmp  = path + ".tmp"
    print(f"[inpaint_ai] Pobieranie {model_id} …")

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
        ("Accept", "*/*"),
    ]
    try:
        with opener.open(url) as resp, open(tmp, "wb") as fout:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fout.write(chunk)
        os.rename(tmp, path)
        print(f"[inpaint_ai] Pobrano {model_id} ({os.path.getsize(path) // (1024*1024)} MB).")
    except Exception as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(
            f"Błąd pobierania '{model_id}': {exc}\nURL: {url}"
        ) from exc
    return path


# ---------------------------------------------------------------------------
# Ładowanie i cache modeli przez spandrel
# ---------------------------------------------------------------------------
def _get_model(model_id: str):
    with _lock:
        if model_id not in _models_cache:
            path = _download_model(model_id)
            print(f"[inpaint_ai] Ładowanie {model_id} …")
            try:
                from spandrel import ModelLoader
                model = ModelLoader().load_from_file(path)
                model.to(_device)
                model.eval()
            except Exception as exc:
                # Fallback: ładuj surowy torch checkpoint
                model = torch.load(path, map_location=_device, weights_only=False)
                if hasattr(model, "eval"):
                    model.eval()
            _models_cache[model_id] = model
    return _models_cache[model_id]


# ---------------------------------------------------------------------------
# Inpainting
# ---------------------------------------------------------------------------
def _dilate_mask(mask_np: np.ndarray, px: int) -> np.ndarray:
    """Rozszerza maskę binarną o px pikseli (Pillow filter)."""
    if px <= 0:
        return mask_np
    pil = Image.fromarray((mask_np * 255).astype(np.uint8))
    pil = pil.filter(ImageFilter.MaxFilter(size=px * 2 + 1))
    return (np.array(pil) > 127).astype(np.float32)


def _protect_green(mask_np: np.ndarray, green_np: np.ndarray) -> np.ndarray:
    """Usuwa z maski obszary zaznaczone zieloną kreską."""
    protected = (green_np > 0.5).astype(np.float32)
    return np.clip(mask_np - protected, 0, 1)


def _run_lama(model, img_t: torch.Tensor, mask_t: torch.Tensor) -> torch.Tensor:
    """Uruchamia big-LaMa (spandrel lub raw)."""
    # Spandrel InpaintImageModelDescriptor: model(image, mask)
    # Surowy big-lama: model.generator(image * (1-mask), mask)
    try:
        with torch.no_grad():
            out = model(img_t, mask_t)
        if hasattr(out, "image"):
            return out.image
        return out
    except TypeError:
        # próba surowego forward
        with torch.no_grad():
            masked = img_t * (1.0 - mask_t)
            inp    = torch.cat([masked, mask_t], dim=1)
            out    = model(inp)
        return out


def _inpaint(image_np: np.ndarray, mask_np: np.ndarray, model_id: str) -> np.ndarray:
    """
    image_np : H×W×3  float32  [0..1]
    mask_np  : H×W    float32  [0..1]  (1 = obszar do uzupełnienia)
    """
    model = _get_model(model_id)

    img_t  = torch.from_numpy(image_np).permute(2, 0, 1).unsqueeze(0).to(_device)
    mask_t = torch.from_numpy(mask_np).unsqueeze(0).unsqueeze(0).to(_device)

    # MAT wymaga rozmiaru 512×512
    if model_id == "mat":
        orig_h, orig_w = image_np.shape[:2]
        img_t  = F.interpolate(img_t,  size=(512, 512), mode="bilinear",  align_corners=False)
        mask_t = F.interpolate(mask_t, size=(512, 512), mode="nearest")

    try:
        out_t = _run_lama(model, img_t, mask_t)
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            torch.cuda.empty_cache()
            raise RuntimeError("Błąd VRAM. Spróbuj mniejszego zdjęcia.") from exc
        raise

    if model_id == "mat":
        out_t = F.interpolate(out_t, size=(orig_h, orig_w), mode="bilinear", align_corners=False)

    out_np = out_t.squeeze().clamp(0, 1).cpu().numpy()
    if out_np.ndim == 3:
        out_np = out_np.transpose(1, 2, 0)
    return out_np


def _blend_result(
    original_np: np.ndarray,
    inpainted_np: np.ndarray,
    mask_np: np.ndarray,
    feather: int = 6,
) -> np.ndarray:
    """Miękkie łączenie wyniku z oryginałem na krawędziach maski."""
    mask_pil = Image.fromarray((mask_np * 255).astype(np.uint8))
    if feather > 0:
        mask_pil = mask_pil.filter(ImageFilter.GaussianBlur(radius=feather))
    mask_f = np.array(mask_pil).astype(np.float32) / 255.0
    mask_f = mask_f[:, :, np.newaxis]
    result = inpainted_np * mask_f + original_np * (1.0 - mask_f)
    return np.clip(result, 0.0, 1.0)


# ---------------------------------------------------------------------------
# GUI — okno rysowania
# ---------------------------------------------------------------------------
class InpaintWindow:
    MAX_DISPLAY = 900  # max px na dłuższym boku w podglądzie

    def __init__(self, image_bytes: bytes, options: dict):
        self.orig_img  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        self.options   = options
        self.result    = None  # bytes PNG po inpaintingu
        self.error     = None

        self.brush_r   = int(options.get("brush_size", 20)) // 2
        self.model_id  = options.get("model_type", "big_lama")
        self.dilation  = int(options.get("mask_dilation", 12))

        # Maski pełnej rozdzielczości
        ow, oh = self.orig_img.size
        self._red_mask   = Image.new("L", (ow, oh), 0)   # usuń
        self._green_mask = Image.new("L", (ow, oh), 0)   # zachowaj

        # Skala podglądu
        scale = min(self.MAX_DISPLAY / max(ow, oh), 1.0)
        self.scale   = scale
        self.disp_w  = int(ow * scale)
        self.disp_h  = int(oh * scale)
        self.disp_br = max(1, int(self.brush_r * scale))

        self._build_gui()

    # --- GUI -----------------------------------------------------------
    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("Inpaint AI — zaznacz co usunąć")
        self.root.resizable(False, False)

        # Toolbar
        toolbar = tk.Frame(self.root, bg="#1e1e1e", pady=4)
        toolbar.pack(fill="x")

        self.mode = tk.StringVar(value="red")

        btn_red = tk.Radiobutton(
            toolbar, text="🔴 Usuń (czerwona)", variable=self.mode, value="red",
            bg="#1e1e1e", fg="white", selectcolor="#3c0000",
            activebackground="#1e1e1e", font=("Segoe UI", 10, "bold"),
        )
        btn_red.pack(side="left", padx=8)

        btn_green = tk.Radiobutton(
            toolbar, text="🟢 Zachowaj (zielona)", variable=self.mode, value="green",
            bg="#1e1e1e", fg="white", selectcolor="#003c00",
            activebackground="#1e1e1e", font=("Segoe UI", 10),
        )
        btn_green.pack(side="left", padx=8)

        tk.Button(
            toolbar, text="↩ Cofnij", command=self._undo,
            bg="#333", fg="white", relief="flat", padx=8, pady=2,
        ).pack(side="left", padx=8)

        tk.Button(
            toolbar, text="🗑 Wyczyść maskę", command=self._clear,
            bg="#333", fg="white", relief="flat", padx=8, pady=2,
        ).pack(side="left", padx=8)

        # Brush size
        tk.Label(toolbar, text="Pędzel:", bg="#1e1e1e", fg="#aaa",
                 font=("Segoe UI", 9)).pack(side="left", padx=(16, 2))
        self.brush_var = tk.IntVar(value=self.brush_r * 2)
        brush_slider = tk.Scale(
            toolbar, from_=4, to=120, orient="horizontal",
            variable=self.brush_var, bg="#1e1e1e", fg="white",
            troughcolor="#444", highlightthickness=0, length=100,
            command=self._on_brush_change,
        )
        brush_slider.pack(side="left")

        tk.Button(
            toolbar, text="✨ Uruchom inpainting", command=self._run,
            bg="#0078d4", fg="white", relief="flat", padx=12, pady=2,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="right", padx=12)

        # Canvas
        self.canvas = tk.Canvas(
            self.root, width=self.disp_w, height=self.disp_h,
            cursor="crosshair", bg="black",
        )
        self.canvas.pack()

        # Status bar
        self.status_var = tk.StringVar(value="Gotowy. Narysuj czerwoną kreską co usunąć.")
        tk.Label(
            self.root, textvariable=self.status_var,
            bg="#111", fg="#aaa", anchor="w", padx=6, pady=3,
            font=("Segoe UI", 9),
        ).pack(fill="x")

        # Wewnętrzne stany
        self._history = []   # lista (red_mask_copy, green_mask_copy)
        self._drawing = False

        self._update_display()

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def _on_brush_change(self, val):
        self.brush_r  = int(val) // 2
        self.disp_br  = max(1, int(self.brush_r * self.scale))

    def _on_press(self, evt):
        self._save_history()
        self._drawing = True
        self._paint(evt.x, evt.y)

    def _on_drag(self, evt):
        if self._drawing:
            self._paint(evt.x, evt.y)

    def _on_release(self, evt):
        self._drawing = False

    def _paint(self, cx: int, cy: int):
        # Współrzędne pełnej rozdzielczości
        fx = cx / self.scale
        fy = cy / self.scale
        r  = self.brush_r

        draw_red   = ImageDraw.Draw(self._red_mask)
        draw_green = ImageDraw.Draw(self._green_mask)

        if self.mode.get() == "red":
            draw_red.ellipse([fx-r, fy-r, fx+r, fy+r], fill=255)
            # Czerwona kreska usuwa zieloną w tym miejscu
            draw_green.ellipse([fx-r, fy-r, fx+r, fy+r], fill=0)
        else:
            draw_green.ellipse([fx-r, fy-r, fx+r, fy+r], fill=255)
            draw_red.ellipse([fx-r, fy-r, fx+r, fy+r], fill=0)

        self._update_display()

    def _update_display(self):
        disp = self.orig_img.resize((self.disp_w, self.disp_h), Image.Resampling.LANCZOS).convert("RGBA")

        # Nakładka czerwona
        red_disp = self._red_mask.resize((self.disp_w, self.disp_h), Image.Resampling.NEAREST)
        overlay_r = Image.new("RGBA", (self.disp_w, self.disp_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_r)
        red_arr = np.array(red_disp)
        # Zamiast piksel-po-pikselu — użyj masek PIL
        overlay_r_arr = np.zeros((self.disp_h, self.disp_w, 4), dtype=np.uint8)
        overlay_r_arr[red_arr > 0] = [220, 0, 0, 140]
        overlay_r = Image.fromarray(overlay_r_arr, "RGBA")
        disp = Image.alpha_composite(disp, overlay_r)

        # Nakładka zielona
        green_disp = self._green_mask.resize((self.disp_w, self.disp_h), Image.Resampling.NEAREST)
        overlay_g_arr = np.zeros((self.disp_h, self.disp_w, 4), dtype=np.uint8)
        green_arr = np.array(green_disp)
        overlay_g_arr[green_arr > 0] = [0, 200, 0, 140]
        overlay_g = Image.fromarray(overlay_g_arr, "RGBA")
        disp = Image.alpha_composite(disp, overlay_g)

        self._tk_img = ImageTk.PhotoImage(disp.convert("RGB"))
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

    def _save_history(self):
        self._history.append((
            self._red_mask.copy(),
            self._green_mask.copy(),
        ))
        if len(self._history) > 30:
            self._history.pop(0)

    def _undo(self):
        if self._history:
            self._red_mask, self._green_mask = self._history.pop()
            self._update_display()

    def _clear(self):
        self._save_history()
        ow, oh = self.orig_img.size
        self._red_mask   = Image.new("L", (ow, oh), 0)
        self._green_mask = Image.new("L", (ow, oh), 0)
        self._update_display()

    def _run(self):
        red_arr = np.array(self._red_mask)
        if red_arr.max() == 0:
            self.status_var.set("⚠ Brak czerwonej maski — najpierw zaznacz co usunąć.")
            return

        self.status_var.set("⏳ Przetwarzanie AI… (może potrwać chwilę)")
        self.root.update()

        def worker():
            try:
                img_np  = np.array(self.orig_img).astype(np.float32) / 255.0
                red_np  = (np.array(self._red_mask)   > 0).astype(np.float32)
                green_np= (np.array(self._green_mask) > 0).astype(np.float32)

                # Buduj maskę: czerwona - chroniona zieleń, + dilation
                mask_np = _dilate_mask(red_np, self.dilation)
                mask_np = _protect_green(mask_np, green_np)
                mask_np = np.clip(mask_np, 0, 1)

                inpainted_np = _inpaint(img_np, mask_np, self.model_id)
                result_np    = _blend_result(img_np, inpainted_np, mask_np)

                result_img   = Image.fromarray((result_np * 255).astype(np.uint8))
                buf = io.BytesIO()
                result_img.save(buf, format="PNG")
                self.result = buf.getvalue()

                self.root.after(0, self._show_result, result_img)
            except Exception as exc:
                self.error = str(exc)
                self.root.after(0, lambda: self.status_var.set(f"❌ Błąd: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, result_img: Image.Image):
        self.status_var.set("✅ Gotowe! Okno wyniku otwarte. Zamknij to okno by zwrócić wynik.")

        win = tk.Toplevel(self.root)
        win.title("Wynik inpaintingu")

        ow, oh = result_img.size
        scale  = min(self.MAX_DISPLAY / max(ow, oh), 1.0)
        dw, dh = int(ow * scale), int(oh * scale)
        disp   = result_img.resize((dw, dh), Image.Resampling.LANCZOS)

        tk_img = ImageTk.PhotoImage(disp)
        lbl = tk.Label(win, image=tk_img, bg="black")
        lbl.image = tk_img
        lbl.pack()

        tk.Button(
            win, text="✅ Użyj tego wyniku i zamknij",
            command=lambda: (win.destroy(), self.root.destroy()),
            bg="#0078d4", fg="white", relief="flat",
            font=("Segoe UI", 11, "bold"), padx=16, pady=6,
        ).pack(pady=8)

        tk.Button(
            win, text="↩ Wróć do rysowania",
            command=win.destroy,
            bg="#444", fg="white", relief="flat",
            padx=12, pady=4,
        ).pack(pady=(0, 8))

    def run(self):
        self.root.mainloop()
        return self.result, self.error


# ---------------------------------------------------------------------------
# Punkt wejścia pluginu
# ---------------------------------------------------------------------------
def process(image_bytes: bytes, options: dict) -> bytes:
    """
    Otwiera okno Tkinter, czeka na rysowanie maski i inpainting,
    zwraca bytes PNG z wynikiem.
    """
    win = InpaintWindow(image_bytes, options)
    result, error = win.run()

    if error:
        raise RuntimeError(f"Inpaint AI: {error}")
    if result is None:
        # Użytkownik zamknął okno bez uruchamiania — zwróć oryginał
        return image_bytes

    return result
