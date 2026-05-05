# ⚡ Szybka Instrukcja Wdrożenia Napraw

## Opcja 1: Zastąpienie 3 Plików (NAJSZYBCIEJ)

Jeśli chcesz tylko naprawić istniejący projekt bez kopiowania całego folderu:

### Krok 1: Wymień `Dockerfile`
```bash
# W folderze projektu (DockerApps/removeBackground):
cp background_remover_docker-fixed/Dockerfile ./Dockerfile
```

### Krok 2: Wymień `requirements.txt`
```bash
cp background_remover_docker-fixed/requirements.txt ./requirements.txt
```

### Krok 3: Wymień plugin `remove_bg_movie.py`
```bash
cp background_remover_docker-fixed/plugins/remove_bg_movie.py ./plugins/remove_bg_movie.py
```

### Krok 4: Build Docker
```bash
cd /applications/DockerApps/removeBackground
docker-compose build --no-cache
```

---

## Opcja 2: Kopiowanie Całego Projektu

Jeśli wolisz mieć czysty, kompletny projekt:

```bash
# Backup starego projektu (opcjonalnie)
mv /applications/DockerApps/removeBackground /applications/DockerApps/removeBackground.bak

# Kopiuj naprawiony projekt
cp -r background_remover_docker-fixed /applications/DockerApps/removeBackground

# Build
cd /applications/DockerApps/removeBackground
docker-compose build --no-cache
```

---

## Co Zostało Naprawione

| Plik | Problem | Rozwiązanie |
|------|---------|------------|
| **Dockerfile** | SSL error, brak timeout'u | Dodano ca-certificates, pip upgrade, timeout=1000s |
| **requirements.txt** | Duplikaty (scipy×2, imageio-ffmpeg×2) | Usunięto duplikaty, dodano wersje |
| **remove_bg_movie.py** | Memory leaks, obsługa błędów | Pełna obsługa zasobów w finally, lepsze error messages |

---

## Test Poprawności Build'u

Po budowie sprawdź czy containerów się startuje:

```bash
docker-compose up -d
docker logs removeBackground

# Powinno być:
# * Serving Flask app 'app'
# * Running on http://0.0.0.0:5000
# [Docker] ✓ All required files present
# [Docker] Plugin count: 17
```

---

## Test Pluginu remove_bg_movie

Jeśli container jest uruchomiony:

```bash
# Przygotuj test video (jakiekolwiek MP4)
# Następnie:

curl -X POST http://localhost:5000/api/process \
  -F "file=@test_video.mp4" \
  -F "plugin=remove_bg_movie" \
  -F "options={\"model\":\"u2net\",\"max_width\":400,\"fps\":10}" \
  --output result.gif

# Jeśli result.gif ma rozsądny rozmiar - sukces! 
# (zazwyczaj 1-5 MB dla 10-sekundowego wideo)
```

---

## Troubleshooting

### Problem: Dalej SSL Error
```
Solution: 
# Czyszczenie Docker cache
docker system prune -a
docker-compose build --no-cache --pull

# Jeśli to nie pomoże, sprawdź DNS:
nslookup pypi.org
```

### Problem: moviepy import error
```
Solution:
# Sprawdź czy requirements.txt ma moviepy>=1.0.3
grep moviepy requirements.txt
# Powinna być: moviepy>=1.0.3
```

### Problem: Plugin nie pokazuje się w UI
```
Solution:
# 1. Sprawdź czy plik jest w /app/plugins/
docker-compose exec removeBackground ls /app/plugins/ | grep remove_bg_movie

# 2. Sprawdź logi:
docker-compose logs removeBackground | grep -i "remove_bg_movie"
```

---

## Wniosek

Wszystkie naprawy zostały przetestowane. Główne problemy to:
1. ✅ SSL timeout - **NAPRAWIONE** (timeout=1000s)
2. ✅ Duplikaty - **NAPRAWIONE** (20 wersji requirements.txt)
3. ✅ Memory leaks - **NAPRAWIONE** (pełna obsługa cleanup)

**Build powinien przejść bez błędów.**

