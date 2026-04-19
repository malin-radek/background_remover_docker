# Background Remover API

REST API do usuwania tła z obrazów. CPU-only, oparty na `rembg` + Flask + Gunicorn.

## Szybki start

```bash
# Build + uruchom
docker compose up --build

# Lub bez compose:
docker build -t bg-remover .
docker run -p 5000:5000 -v rembg_models:/app/models bg-remover
```

Pierwsze uruchomienie pobiera model (~170 MB dla `u2net`). Kolejne starty są natychmiastowe dzięki volumeowi.

---

## Endpointy

### `GET /health`
Status serwisu.

```bash
curl http://localhost:5000/health
```

```json
{
  "status": "ok",
  "models": ["birefnet-general", "isnet-general-use", "u2net", "u2net_human_seg", "silueta"],
  "default_model": "u2net"
}
```

---

### `GET /models`
Lista dostępnych modeli.

```bash
curl http://localhost:5000/models
```

---

### `POST /process`
Przetwarza obraz za pomocą pluginu (główny endpoint).

**Parametry (multipart/form-data):**

| Pole          | Typ     | Wymagane | Opis                                          |
|---------------|---------|----------|-----------------------------------------------|
| `image`       | file    | ✅        | Plik obrazu (JPG, PNG, BMP, GIF, TIFF, WEBP) |
| `plugin`      | string  | ❌        | ID pluginu (domyślnie: `remove_background`)  |
| `opt_*`       | string  | ❌        | Opcje pluginu (np. `opt_model=birefnet-general`) |
| `target_size` | string  | ❌        | Rozmiar docelowy: `256`, `512`, `768`, `1024`, `1536`, `2048`, `original` (domyślnie: `original`) |

**`target_size` — skalowanie wejściowe:**
- Przeskaluje obraz **PRZED** pluginem dla szybkości
- Zachowuje proporcje (aspect ratio)
- Dla każdego pluginu — niezależnie od rodzaju efektu
- Domyślnie: `original` (bez skalowania)

**Odpowiedź (JSON):**
```json
{
  "image_id": "550e8400-e29b-41d4-a716-446655440000",
  "download_url": "/result/550e8400-e29b-41d4-a716-446655440000",
  "mime_type": "image/gif",
  "file_extension": "gif",
  "size_bytes": 1024000,
  "elapsed_seconds": 12.45
}
```

**Przykład z skalowaniem:**
```bash
curl -X POST http://localhost:5000/process \
  -F "image=@photo.jpg" \
  -F "plugin=pow_effect" \
  -F "target_size=512" \
  -F "opt_spike_count=12" \
  -F "opt_pow_style=classic"
```

---

### `GET /result/<image_id>`
Pobierz wcześniej wygenerowany obraz z cache'a. **Obrazy pozostają dostępne po refreshu przeglądarki!**

```bash
curl http://localhost:5000/result/550e8400-e29b-41d4-a716-446655440000 --output result.gif
```

**Nagłówki odpowiedzi:**
- `X-Plugin` – ID użytego pluginu
- `X-Elapsed-Seconds` – czas przetwarzania

---

### `GET /result/<image_id>/info`
Pobierz metadane o wygenerowanym obrazie.

```bash
curl http://localhost:5000/result/550e8400-e29b-41d4-a716-446655440000/info
```

**Odpowiedź:**
```json
{
  "image_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": 1712950200.123,
  "client_ip": "192.168.1.100",
  "plugin": "pow_effect",
  "filename": "photo_out.gif",
  "mime_type": "image/gif",
  "size_bytes": 1024000,
  "elapsed_seconds": 12.45,
  "download_url": "/result/550e8400-e29b-41d4-a716-446655440000"
}
```

---

### `POST /remove-background`
Usuwa tło z obrazu (kompatybilny endpoint dla starego API).

**Parametry (multipart/form-data):**

| Pole          | Typ     | Wymagane | Opis                                          |
|---------------|---------|----------|-----------------------------------------------|
| `image`       | file    | ✅        | Plik obrazu (JPG, PNG, BMP, GIF, TIFF, WEBP) |
| `model`       | string  | ❌        | Model AI (domyślnie: `u2net`)                 |
| `scale`       | int     | ❌        | Skala wyniku: 20–100 (domyślnie: `100`)       |
| `return_json` | string  | ❌        | `"1"` → JSON z base64 zamiast pliku PNG       |

**Przykłady:**

```bash
# Zwróć PNG bezpośrednio
curl -X POST http://localhost:5000/remove-background \
  -F "image=@photo.jpg" \
  --output result.png

# Z konkretnym modelem i skalą
curl -X POST http://localhost:5000/remove-background \
  -F "image=@photo.jpg" \
  -F "model=birefnet-general" \
  -F "scale=80" \
  --output result.png

# Odpowiedź JSON z base64
curl -X POST http://localhost:5000/remove-background \
  -F "image=@photo.jpg" \
  -F "return_json=1"
```

**Odpowiedź JSON (gdy `return_json=1`):**
```json
{
  "image_base64": "<base64 PNG>",
  "format": "png",
  "model": "u2net",
  "scale": 100,
  "elapsed_s": 2.34
}
```

---

## Modele

| Model              | Jakość       | Prędkość | Opis                    |
|--------------------|--------------|----------|-------------------------|
| `birefnet-general` | ⭐⭐⭐⭐⭐    | Wolny    | Najlepsza jakość        |
| `isnet-general-use`| ⭐⭐⭐⭐      | Średni   | Wysoka jakość           |
| `u2net`            | ⭐⭐⭐        | Szybki   | Domyślny, dobry balans  |
| `u2net_human_seg`  | ⭐⭐⭐⭐      | Szybki   | Zoptymalizowany dla ludzi|
| `silueta`          | ⭐⭐⭐        | Szybki   | Sylwetki                |

---

## Zmienne środowiskowe

| Zmienna          | Domyślna   | Opis                              |
|------------------|------------|-----------------------------------|
| `DEFAULT_PLUGIN` | `remove_background` | Plugin domyślny            |
| `MAX_UPLOAD_MB`  | `100`      | Maks. rozmiar uploadu w MB        |
| `PORT`           | `5000`     | Port nasłuchiwania                |
| `U2NET_HOME`     | `/app/models` | Katalog cache modeli           |
| `CACHE_DIR`      | `./cache`  | Katalog cache wyników             |

---

## Cache i persistence

Wszystkie wygenerowane obrazy są automatycznie przechowywane w `CACHE_DIR` z metadanymi. Obrazy pozostają dostępne nawet po:
- Refreshu przeglądarki
- Restarcie serwera
- Zamknięciu i otwarciu przeglądarki

**Automatyczne czyszczenie:** Obrazy starsze niż 7 dni są automatycznie usuwane przy starcie aplikacji.

---

## Python client (przykład)

```python
import requests

with open("photo.jpg", "rb") as f:
    resp = requests.post(
        "http://localhost:5000/process",
        files={"image": ("photo.jpg", f, "image/jpeg")},
        data={
            "plugin": "pow_effect",
            "opt_spike_count": "12",
            "opt_pow_style": "classic"
        },
    )

resp.raise_for_status()
result = resp.json()
image_id = result["image_id"]

# Pobierz obraz za pomocą image_id
download_resp = requests.get(f"http://localhost:5000/result/{image_id}")
with open("result.gif", "wb") as out:
    out.write(download_resp.content)
```
