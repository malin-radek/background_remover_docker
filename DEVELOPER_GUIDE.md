# Developer Guide - Instrukcje dla Copilot

## 📋 OBOWIĄZKOWE ZASADY

### 1. CACHE ZARZĄDZANIE - ZAWSZE!
**Problem:** Python bytecode cache (`__pycache__`) powoduje że stare zmiany się nie ładują.

**ZAWSZE gdy modyfikujesz pluginy:**
1. Po każdej zmianie w `/plugins` - restart serwera
2. Zawsze zabij procesy Python **NAJPIERW**: `Get-Process python | Stop-Process -Force`
3. Czyszczenie cache przed startem:
```powershell
Get-ChildItem -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -EA SilentlyContinue
Get-ChildItem -Recurse -Filter "*.pyc" | Remove-Item -Force -EA SilentlyContinue
```
4. **WERYFIKACJA:** Po `python app.py` sprawdzam endpoint `/plugins` aby potwierdzić że zmiany są widoczne

**Automatyczne czyszczenie:**
- `app.py` ma agresywne czyszczenie cache na starcie (linie 11-26)
- `plugin_loader.py` invaliduje cache przy każdym loadzie pluginów

### 2. WERYFIKACJA ZMIAN W SERWERZE

**Nigdy nie mów "zrobione" bez weryfikacji!**

Po każdej zmianie w pluginach:
```powershell
$resp = Invoke-RestMethod -Uri "http://localhost:5000/plugins"
$plugin = $resp.PLUGIN_NAME
# Sprawdź czy zmiana jest widoczna:
$plugin.options.PROPERTY_NAME | ConvertTo-Json
```

### 3. STRUKTURA KATALOGÓW

```
remove_bg_docker/
├── app.py                 (główny Flask app)
├── plugin_loader.py       (loader pluginów)
├── plugin_utils.py        (shared utilities)
├── requirements.txt
├── Dockerfile
├── README.md
├── DEVELOPER_GUIDE.md     ← TEN PLIK
├── plugins/
│   ├── silhouette.py
│   ├── agif_pulsing.py
│   ├── agif_zoom.py
│   ├── agif_rotation.py
│   ├── cartoon_effect.py
│   ├── neon_glow.py
│   ├── parallax_3d.py
│   ├── pixel_art.py
│   ├── remove_background.py
│   └── sketch_effect.py
├── tests/                 ← TUTAJ DEBUG, TESTY
│   ├── test_plugins.py
│   └── test_*.py
├── docs/                  ← TUTAJ INSTRUKCJE, NOTATKI
│   └── DEVELOPMENT.md
├── models/                ← CACHE (gitignore)
│   └── .gitkeep
└── __pycache__/           ← NIGDY! (gitignore)
```

**NIGDY nie umieszczaj w głównym dir:**
- test_*.py, debug_*.py, check_*.py
- notatki, instrukcje
- pliki tymczasowe (.zip, .json z testów)

### 4. WORKFLOW: Modyfikacja Pluginu

1. **Edytuj plik pluginu** (np. `plugins/parallax_3d.py`)
2. **Sprawdzenie składni** (jeśli Python):
   ```powershell
   python -m py_compile plugins/parallax_3d.py
   ```
3. **Kill procesy + czyszczenie cache:**
   ```powershell
   Get-Process python -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
   Start-Sleep -Seconds 1
   Get-ChildItem -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -EA SilentlyContinue
   ```
4. **Restart serwera:**
   ```powershell
   cd "C:\Users\new Radek\Documents\_vsc\_vsc_code\remove_bg_docker"
   python app.py
   ```
5. **Weryfikacja HTTP:**
   ```powershell
   $resp = Invoke-RestMethod -Uri "http://localhost:5000/plugins"
   $plugin = $resp.PLUGIN_NAME
   # Sprawdź zmianę
   ```
6. **Raportuj tylko gdy widzisz zmianę w API**

### 5. MODYFIKACJE PLUGINÓW - CHECKLIST

Gdy dodajesz nową opcję do pluginu:

- [ ] METADATA ma nową opcję (type, label, choices, default)
- [ ] W `process()` pobieraš opcję: `var = options.get("key", METADATA["options"]["key"]["default"])`
- [ ] Logika pluginu używa zmiennej
- [ ] Restart + czyszczenie cache
- [ ] Weryfikacja HTTP endpoint `/plugins` pokazuje nową opcję

### 6. PLUGIN ARCHITECTURE

**Każdy plugin musi mieć:**

```python
METADATA = {
    "id": "plugin_name",
    "name": "Nazwa Pluginu",
    "description": "Opis...",
    "version": "1.0.0",
    "options": {
        "key": {
            "type": "select",
            "label": "Label",
            "choices": {"val": "Label", ...},
            "default": "val",
        }
    }
}

def is_available() -> bool:
    return _AVAILABLE

def process(image_bytes: bytes, options: dict) -> bytes:
    # ZAWSZE pobierz opcje z METADATA defaults
    var = options.get("key", METADATA["options"]["key"]["default"])
    # Process...
    return output_bytes
```

### 7. BEST PRACTICES

#### Pobieranie opcji
```python
# ✓ PRAWIDŁOWO - zawsze z defaults
value = options.get("key", METADATA["options"]["key"]["default"])

# ✗ ŹLE - hardcoded default
value = options.get("key", "u2net")
```

#### rembg z wieloma modelami
```python
# ✓ PRAWIDŁOWO
model_name = options.get("model", METADATA["options"]["model"]["default"])
session = _get_session(model_name)

# ✗ ŹLE - hardcoded model
session = _get_session("u2net")
```

#### Obsługa animacji z ramkami
```python
num_frames = int(options.get("frames", METADATA["options"]["frames"]["default"]))
for i in range(num_frames):
    progress = i / (num_frames - 1) if num_frames > 1 else 0
    # progress: 0.0 -> 1.0
```

#### 🚨 KRYTYCZNE: prepare_background NIGDY w pętli!
```python
# ✗ ŹLE - prepare_background za każdą klatkę = N inpaint operacji! (WOLNE)
for i in range(num_frames):
    frame = create_frame(...)
    bg = prepare_background(...)  # 2-5 sekund × num_frames = KATASTROFA!
    frames.append(bg)

# ✓ PRAWIDŁOWO - prepare_background RAZ przed pętlą, reuse za każdą klatkę
bg = prepare_background(...)  # 2-5 sekund, 1 raz!
for i in range(num_frames):
    frame = create_frame(...)
    bg_frame = bg.copy()  # Shallow copy, szybkie
    bg_frame.paste(frame, mask=alpha_mask)
    frames.append(bg_frame)
```

**Dlaczego?** `prepare_background()` zawiera `cv2.inpaint()` (2-5s). Jeśli 20 klatek × inpaint = 40-100 sekund! Jeden inpaint poza pętlą = ~3-5 sekund dla 20 klatek.

**Checklist dla animacji:**
- [ ] `prepare_background()` POZA pętlą `for i in range(num_frames)`
- [ ] Wewnątrz pętli: `bg_frame = bg.copy()` + operacje na ramce
- [ ] Test: 20-frame GIF powinien mieć ~3-5 sekund, nie 40+ sekund

#### 🌌 Aurora Borealis Effect (neon_glow plugin)
```python
# Wielokolorowa aura dookoła pierwszego planu
# Użyj w neon_glow: animation="aurora"

# Parametry aurory:
# - Obszar: alpha_mask -5% (erosion) do +5% (dilation)
# - Efekt: wielokolorowy RGB cycling (cyan->magenta->green)
# - Animacja: ruchome fale + Perlin-like noise dla naturalności
# - Pierwszy plan: NIEZMIENIONY (tylko postać RGB)
# - Performance: ~3.2s na 8-frame GIF
```

**Ważne:** Aurora nie zmienia RGB pierwszego planu - tylko dodaje RGBA warstwę dookoła!

### 8. GIT COMMIT MESSAGES

Format:
```
[component] brief description

Detailed explanation if needed.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

Przykłady:
```
[plugins] Add object_zoom to parallax_3d

Added configurable zoom intensity (0-5%) for foreground object
- New "object_zoom" option in METADATA
- Controlled via sine wave animation
- Default: 3%

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

### 9. ENVIRONMENT VARIABLES

W `app.py`:
```python
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # Disable cache writes
sys.dont_write_bytecode = True                # Additional safety
```

W Dockerfile:
```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
```

### 10. DOKUMENTACJA ZMIAN

Po każdej istotnej zmianie update'uj plan.md w session state:
```
C:\Users\new Radek\.copilot\session-state\{session_id}\plan.md
```

Format:
```markdown
## Zmiany
- [x] Dodano option_zoom do parallax_3d (0-5%)
- [x] Rozszerzone frames w AGIF (4, 8, 16, 20, 24, 50, 75, 100)
- [x] Naprawiono cache management w app.py i plugin_loader.py

## Status
✓ Wszystkie zmiany weryfikowane na http://localhost:5000/plugins
✓ Cache automatycznie czyszczony na starcie
```

---

## ⚡ QUICK REFERENCE

### Restart z czyszczeniem
```powershell
Get-Process python -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }; Start-Sleep 1; cd "remove_bg_docker"; gci -Recurse -Filter "__pycache__" | rm -Recurse -Force -EA SilentlyContinue; python app.py
```

### Test zmian
```powershell
$r = Invoke-RestMethod -Uri "http://localhost:5000/plugins"; $r.parallax_3d.options | ConvertTo-Json
```

### Check stderr
```powershell
$r = Invoke-RestMethod -Uri "http://localhost:5000/plugins"  # See [plugins] errors
```

---

## 📝 NOTES

- Python cache problem rozwiązany z `importlib.invalidate_caches()` + `sys.path_importer_cache.clear()`
- Plugin loader zawsze invaliduje cache przed loadem
- API zawsze zwraca świeże metadane dzięki `PYTHONDONTWRITEBYTECODE=1`
- Weryfikacja HTTP to JEDYNA wiarygodna metoda potwierdzenia zmian
