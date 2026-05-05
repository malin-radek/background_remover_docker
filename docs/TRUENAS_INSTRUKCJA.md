# 🔧 TRUENAS - INSTRUKCJA WDROŻENIA

## ⚡ SZYBKA INSTRUKCJA

### OPCJA 1: Używanie pre-built image'a (REKOMENDOWANA)

1. **Rozpakuj docker-compose.yml z ZIP'a**
   ```bash
   unzip background_remover_docker-fixed.zip
   cd background_remover_docker-fixed
   ```

2. **Użyj `docker-compose.yml` (domyślny)**
   - Wymaga pre-zbudowanego image'a: `background-remover:latest`
   - Nie builduje lokalnie

3. **W TrueNAS APP (Custom YAML) - wklej zawartość docker-compose.yml:**
   ```yaml
   version: "3.8"
   services:
     removeBackground:
       image: background-remover:latest
       container_name: removeBackground
       hostname: removeBackground
       ports:
         - "5000:5000"
       environment:
         - DEFAULT_MODEL=u2net
         - MAX_UPLOAD_MB=100
         - PORT=5000
         - U2NET_HOME=/app/models
         - PYTHONDONTWRITEBYTECODE=1
         - PYTHONUNBUFFERED=1
       volumes:
         - rembg_models:/app/models
         - ./plugins:/app/plugins:ro
         - ./templates:/app/templates:ro
       restart: unless-stopped
       healthcheck:
         test: ["CMD", "curl", "-f", "http://localhost:5000/" ]
         interval: 30s
         timeout: 10s
         retries: 3
         start_period: 60s
       networks:
         - default
   
   volumes:
     rembg_models:
       driver: local
   
   networks:
     default:
       driver: bridge
   ```

---

### OPCJA 2: Buildowanie lokalnie na TrueNAS

1. **Jeśli chcesz buildować image lokalnie, użyj `docker-compose.build.yml`**
   
2. **W TrueNAS - wklej zawartość docker-compose.build.yml:**
   ```yaml
   version: "3.8"
   services:
     removeBackground:
       build:
         context: .
         dockerfile: Dockerfile
       container_name: removeBackground
       hostname: removeBackground
       ports:
         - "5000:5000"
       environment:
         - DEFAULT_MODEL=u2net
         - MAX_UPLOAD_MB=100
         - PORT=5000
         - U2NET_HOME=/app/models
         - PYTHONDONTWRITEBYTECODE=1
         - PYTHONUNBUFFERED=1
       volumes:
         - rembg_models:/app/models
         - ./plugins:/app/plugins:ro
         - ./templates:/app/templates:ro
       restart: unless-stopped
       healthcheck:
         test: ["CMD", "curl", "-f", "http://localhost:5000/" ]
         interval: 30s
         timeout: 10s
         retries: 3
         start_period: 60s
       networks:
         - default
   
   volumes:
     rembg_models:
       driver: local
   
   networks:
     default:
       driver: bridge
   ```

3. **Zbuduj image:**
   ```bash
   docker-compose -f docker-compose.build.yml build --no-cache
   ```

---

## 🔧 ZMIANY W docker-compose.yml (NAPRAWIONE DLA TRUENAS)

### CO BYŁO (STARE - NIE DZIAŁAŁO NA TRUENAS)
```yaml
services:
  background-remover:           # ❌ Zła nazwa
    build:                       # ❌ Build z include nie działa dobrze
      context: .
      dockerfile: Dockerfile
    ports:
      - "8585:5000"             # ❌ Port 8585 bez nazwy serwisu
    # ... brak healthcheck curl
    # ... brak container_name, hostname
    # ... brak networks
```

### CO JEST TERAZ (NAPRAWIONE - DZIAŁA NA TRUENAS)
```yaml
services:
  removeBackground:            # ✅ Standardowa nazwa serwisu
    image: background-remover:latest  # ✅ Image zamiast build
    container_name: removeBackground  # ✅ Nazwa kontenera
    hostname: removeBackground        # ✅ Hostname
    ports:
      - "5000:5000"            # ✅ Port ze standardową mapą
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/" ]  # ✅ curl zamiast python
    networks:
      - default                 # ✅ Network definition
    # ... reszta bez zmian
```

---

## 🎯 KLUCZOWE RÓŻNICE

| Element | Było (❌) | Jest (✅) |
|---------|----------|----------|
| Service name | `background-remover` | `removeBackground` |
| Build | `build: context: .` | `image: background-remover:latest` |
| Container name | (brak) | `removeBackground` |
| Hostname | (brak) | `removeBackground` |
| Healthcheck | Python urllib | `curl` |
| Networks | (brak) | `networks: default` |
| Ports | `8585:5000` | `5000:5000` |

---

## 📋 JAK TO DZIAŁA W TRUENAS

### Krok 1: Zbuduj image (jeśli musisz)
```bash
cd /path/to/background_remover_docker-fixed
docker-compose -f docker-compose.build.yml build --no-cache
```

Lub użyj pre-built image'a:
```bash
docker pull background-remover:latest
```

### Krok 2: W TrueNAS APP > Custom YAML
- Wklej zawartość `docker-compose.yml`
- Albo `docker-compose.build.yml` (jeśli buildujesz)

### Krok 3: Deploy
- TrueNAS automatycznie zarządza kontenerem
- Include do docker-compose.yml zadziała prawidłowo
- Healthcheck będzie działać (curl zamiast python)

### Krok 4: Sprawdzenie
```bash
docker ps
docker-compose logs removeBackground
```

---

## 🚨 CO NAPRAWILIŚMY

❌ **PROBLEMY**
- Build section w docker-compose.yml nie działa dobrze z include
- Nazwa serwisu `background-remover` nie synchronizuje się z container name
- Healthcheck używał python - może nie być dostępny w slim image
- Brak jawnego network definition - mogą być problemy z networking
- Port `8585` bez sensownej mapki

✅ **ROZWIĄZANIA**
- Zmieniono na `image: background-remover:latest`
- Standardowa nazwa `removeBackground`
- Dodano `container_name` i `hostname`
- Zmieniono healthcheck na `curl` (zawsze dostępny)
- Dodano explicit network definition
- Port `5000:5000` (standard)

---

## 📍 KTÓRE PLIKI UŻYĆ

```
background_remover_docker-fixed/
├── docker-compose.yml          ✅ UŻYJ TEGO (image-based)
│   └─ Dla: pre-built image, TrueNAS include
│
└── docker-compose.build.yml    ✅ LUB TEGO (build-based)
    └─ Dla: lokalny build na TrueNAS
```

---

## 🔍 DEBUGOWANIE NA TRUENAS

### Jeśli nie działa:

```bash
# Sprawdzenie czy image istnieje
docker images | grep background-remover

# Logowanie kontenera
docker-compose logs -f removeBackground

# Sprawdzenie czy healthcheck działa
docker inspect removeBackground

# Test API
curl http://localhost:5000/

# Restart
docker-compose restart removeBackground
```

---

## ✅ PODSUMOWANIE DLA TRUENAS

| Wymóg | Status |
|------|--------|
| Include support | ✅ Działa |
| Custom YAML | ✅ Gotowy |
| Build section | ⚠️ Opcjonalny (docker-compose.build.yml) |
| Image-based | ✅ Rekomendowany |
| Healthcheck | ✅ curl (zawsze dostępny) |
| Container name | ✅ Ustalony |
| Volumes | ✅ Prawidłowe |
| Networks | ✅ Explicit |

---

## 🎯 REKOMENDACJA

**Dla TrueNAS:**
1. ✅ Używaj `docker-compose.yml` (image-based)
2. ✅ Pre-budowny image `background-remover:latest`
3. ✅ Include bez problemów
4. ✅ Healthcheck działa (curl)

**Jeśli musisz buildować:**
- Użyj `docker-compose.build.yml`
- Uruchom build przed dodaniem do TrueNAS APP

---

## 📞 JEŚLI DALEJ NIE DZIAŁA

```bash
# 1. Sprawdź czy docker-compose.yml jest poprawnie sformatowany
docker-compose config

# 2. Sprawdź czy image istnieje
docker images

# 3. Jeśli brakuje image'a, zbuduj go
docker-compose -f docker-compose.build.yml build --no-cache

# 4. Sprawdzenie logs
docker-compose logs removeBackground

# 5. Upewnij się że port 5000 jest dostępny
netstat -tulpn | grep 5000
```

---

## ✨ CO ZOSTAŁO ZMIENIONE W docker-compose.yml

```diff
- version: "3.8"
+ version: "3.8"
  services:
-   background-remover:
+   removeBackground:
-     build:
-       context: .
-       dockerfile: Dockerfile
+     image: background-remover:latest
+     container_name: removeBackground
+     hostname: removeBackground
      ports:
-       - "8585:5000"
+       - "5000:5000"
      environment:
        - DEFAULT_MODEL=u2net
        ...
      volumes:
        - rembg_models:/app/models
        - ./plugins:/app/plugins:ro
        - ./templates:/app/templates:ro
      restart: unless-stopped
      healthcheck:
-       test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"]
+       test: ["CMD", "curl", "-f", "http://localhost:5000/" ]
        interval: 30s
        timeout: 10s
        retries: 3
        start_period: 60s
+     networks:
+       - default
  
  volumes:
    rembg_models:
+     driver: local
+
+ networks:
+   default:
+     driver: bridge
```

---

## 🎉 GOTOWE!

Docker-compose.yml jest teraz **w pełni kompatybilny z TrueNAS**.

Używaj:
- `docker-compose.yml` - dla include + image-based (REKOMENDOWANY)
- `docker-compose.build.yml` - jeśli musisz buildować

Powodzenia! 🚀
