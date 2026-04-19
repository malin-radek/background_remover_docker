# Production Deployment Checklist

## Pre-Build Verification

- [x] `plugins/` directory exists and contains all 16 plugin files
- [x] `.dockerignore` does NOT exclude `plugins/` or `templates/` directories
- [x] `templates/` directory exists with `index.html`
- [x] `requirements.txt` contains all production dependencies
- [x] `Dockerfile` explicitly copies all required files

## Build Phase

The Docker build process:

1. **Copy critical files** (Dockerfile lines 26-34):
   ```dockerfile
   COPY requirements.txt requirements.txt
   COPY plugin_loader.py plugin_loader.py
   COPY plugin_utils.py plugin_utils.py
   COPY app.py app.py
   COPY run_server.py run_server.py
   COPY index.html index.html
   COPY templates/ templates/
   COPY plugins/ plugins/
   ```

2. **Verify files are present** (Dockerfile lines 36-42):
   - Fails immediately if `plugins/`, `app.py`, or `templates/` are missing
   - Prints exact plugin count during build

3. **Download base model** (Dockerfile lines 44-48):
   - Pre-caches the u2net model during build
   - Ensures first request after deployment is fast

## Runtime Verification

On container start, the app:

1. **Cleans Python cache** (`app.py` lines 10-25):
   - Removes all `__pycache__` directories recursively
   - Clears import caches to prevent stale bytecode

2. **Loads plugins** (`plugin_loader.py` lines 42-73):
   - Scans `plugins/` directory
   - Loads each `.py` file with METADATA
   - Returns count and list of available plugins

3. **Health checks** (`app.py` lines 122-135):
   - **CRITICAL**: If no plugins load, app exits with status 1
   - Prevents broken deployments from starting
   - Logs all loaded plugins on startup

4. **Startup diagnostics** (`app.py` lines 481-502):
   ```
   [STARTUP] Background Remover API - Production Ready
   [STARTUP] Python version: 3.11.x
   [STARTUP] Plugins loaded: 16
   [STARTUP] Default plugin: remove_background
   [STARTUP] Max upload: 100 MB
   [STARTUP] Max resolution: 3840x2160
   [STARTUP] Plugins directory: /app/plugins (16 files)
   ```

## Deployment Commands

### Local (Development)
```bash
python app.py
```

### Docker Build
```bash
docker compose build --no-cache
```

### Docker Run (TrueNAS / Production)
```bash
docker compose up -d
```

Check logs:
```bash
docker compose logs -f background-remover
```

Health check:
```bash
curl http://localhost:8585/health
```

List plugins:
```bash
curl http://localhost:8585/plugins | jq '.[] | .id'
```

## Troubleshooting Production Issues

### Error: "No plugins directory" or "NO PLUGINS LOADED"

**Cause**: Docker build excluded plugins/ directory

**Fix**:
1. Check `.dockerignore` does NOT contain `plugins/` or `templates/`
2. Rebuild with `docker compose build --no-cache`
3. Verify in running container:
   ```bash
   docker compose exec background-remover ls -la /app/plugins/
   docker compose exec background-remover python -c "from plugin_loader import load_all; print(load_all())"
   ```

### Error: "Failed to find plugin 'remove_background'"

**Cause**: `remove_background.py` is missing or malformed

**Fix**:
1. Verify file exists: `ls -la plugins/remove_background.py`
2. Check syntax: `python -m py_compile plugins/remove_background.py`
3. Verify METADATA: `grep "METADATA" plugins/remove_background.py`

### Container exits immediately

**Cause**: Plugin loading failed during startup health check

**Fix**:
1. Check logs: `docker compose logs background-remover`
2. Look for `[ERROR]` or `[plugin_loader]` messages
3. Rebuild and verify plugins are included

### Stale bytecode causing old code to run

**Fix**:
1. Kill container: `docker compose down -v`
2. Rebuild: `docker compose build --no-cache`
3. Restart: `docker compose up -d`

## Files Critical for Production

| File | Purpose | Status |
|------|---------|--------|
| `Dockerfile` | Container definition with explicit file copies | ✓ Updated |
| `.dockerignore` | Excludes unnecessary files (NOT plugins/templates) | ✓ Fixed |
| `docker-compose.yml` | Orchestration and volume mounts | ✓ Updated |
| `app.py` | Flask app with startup validation | ✓ Enhanced |
| `plugin_loader.py` | Dynamic plugin discovery | ✓ Verified |
| `plugins/*.py` | 16 effect plugins | ✓ All present |
| `requirements.txt` | Python dependencies | ✓ Complete |

## Environment Variables (Production)

```bash
DEFAULT_MODEL=u2net              # AI model for background removal
MAX_UPLOAD_MB=100                # Maximum upload file size
MAX_IMAGE_RESOLUTION=3840x2160   # Maximum output resolution
PORT=5000                        # Internal port
U2NET_HOME=/app/models           # Model cache directory (persistent volume)
PYTHONDONTWRITEBYTECODE=1        # Disable .pyc generation
PYTHONUNBUFFERED=1               # Unbuffered stdout (required for logs)
```

## API Endpoints Ready for Production

- `GET /health` - Health check and model info
- `GET /plugins` - List all available effect plugins
- `POST /remove-background` - Core background removal
- `POST /[plugin-id]` - Apply effect with plugin-specific options
- `GET /result/<image_id>` - Retrieve processed image
- `GET /result/<image_id>/info` - Get image metadata

## Final Production Sign-Off

Before deploying to production:

- [x] Dockerfile build succeeds with no warnings
- [x] All 16 plugins are present in container at `/app/plugins/`
- [x] Container starts and loads all plugins
- [x] Health endpoint returns `status: "ok"`
- [x] Sample test image processes successfully
- [x] Performance is acceptable for target load

---

**Last Updated**: 2026-04-12
**Status**: Production Ready ✓
