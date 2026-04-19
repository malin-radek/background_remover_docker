FROM python:3.11-slim

LABEL maintainer="BackgroundRemover API"
LABEL description="Background removal REST API (CPU-only) using rembg + Flask"


# System deps dla Pillow, rembg, OpenCV, scipy, FFmpeg (MP4 conversion), GIT oraz ca-certificates (SSL fix)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    ffmpeg \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Wyłącz Python cache
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Upgrade pip i certifi (fix SSL issues)
RUN pip install --upgrade pip setuptools certifi

# Install Python deps — CPU-only onnxruntime (no GPU)
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# Copy app source
COPY requirements.txt requirements.txt
COPY plugin_loader.py plugin_loader.py
COPY plugin_utils.py plugin_utils.py
COPY app.py app.py
COPY run_server.py run_server.py
COPY templates/ templates/
COPY plugins/ plugins/

# Verify critical files are in place
RUN test -d /app/plugins || (echo "ERROR: plugins/ dir missing!" && exit 1) && \
    test -f /app/app.py || (echo "ERROR: app.py missing!" && exit 1) && \
    test -d /app/templates || (echo "ERROR: templates/ dir missing!" && exit 1) && \
    ls -la /app/plugins/ | wc -l | grep -q . && \
    echo "[Docker] ✓ All required files present" && \
    echo "[Docker] Plugin count: $(ls /app/plugins/*.py | wc -l)"

# Model cache dir — pobierz u2net już podczas budowania obrazu
# Dzięki temu pierwsze żądanie jest natychmiastowe
ENV U2NET_HOME=/app/models
RUN mkdir -p /app/models && \
    python -c "from rembg import new_session; new_session('u2net')"

# Config
ENV DEFAULT_MODEL=u2net
ENV MAX_UPLOAD_MB=100
ENV MAX_IMAGE_RESOLUTION=3840x2160
ENV PORT=5000

EXPOSE 5000

# gunicorn: 1 worker + 4 threads (bezpiecznie dla CPU + scipy/numpy)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "300", "app:app"]
