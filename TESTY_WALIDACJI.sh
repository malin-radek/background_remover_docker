#!/bin/bash
# 🧪 Testy Walidacji Napraw - Background Remover Docker

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 WALIDACJA NAPRAW"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PROJECT_DIR="${1:-.}"

if [ ! -f "$PROJECT_DIR/Dockerfile" ]; then
    echo "❌ ERROR: Dockerfile nie znaleziony w $PROJECT_DIR"
    exit 1
fi

echo ""
echo "📋 TEST 1: Sprawdzenie Dockerfile"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Sprawdzenie ca-certificates
if grep -q "ca-certificates" "$PROJECT_DIR/Dockerfile"; then
    echo "✅ ca-certificates jest zainstalowany w Docker"
else
    echo "❌ BŁĄD: ca-certificates brakuje w Dockerfile"
    exit 1
fi

# Sprawdzenie pip upgrade
if grep -q "pip install --upgrade pip" "$PROJECT_DIR/Dockerfile"; then
    echo "✅ pip upgrade jest obecny"
else
    echo "❌ BŁĄD: pip upgrade brakuje"
    exit 1
fi

# Sprawdzenie timeout
if grep -q "default-timeout=1000" "$PROJECT_DIR/Dockerfile"; then
    echo "✅ timeout=1000s jest ustawiony"
else
    echo "❌ BŁĄD: timeout brakuje lub ma złą wartość"
    exit 1
fi

echo ""
echo "📋 TEST 2: Sprawdzenie requirements.txt"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Sprawdzenie duplikatów
DUPLICATES=$(grep -v "^#" "$PROJECT_DIR/requirements.txt" | \
             grep -v "^$" | \
             sort | uniq -d | \
             wc -l)

if [ "$DUPLICATES" -eq 0 ]; then
    echo "✅ Brak duplikatów w requirements.txt"
else
    echo "❌ BŁĄD: Znaleziono $DUPLICATES duplikatów:"
    grep -v "^#" "$PROJECT_DIR/requirements.txt" | \
    grep -v "^$" | \
    sort | uniq -d
    exit 1
fi

# Sprawdzenie moviepy wersji
if grep -q "moviepy>=1.0.3" "$PROJECT_DIR/requirements.txt"; then
    echo "✅ moviepy ma prawidłową wersję (>=1.0.3)"
else
    echo "❌ BŁĄD: moviepy brakuje lub ma złą wersję"
    exit 1
fi

# Sprawdzenie scipy (powinna być tylko raz)
SCIPY_COUNT=$(grep "scipy" "$PROJECT_DIR/requirements.txt" | wc -l)
if [ "$SCIPY_COUNT" -eq 1 ]; then
    echo "✅ scipy wymieniona dokładnie 1 raz"
else
    echo "❌ BŁĄD: scipy wymieniona $SCIPY_COUNT razy (powinna 1)"
    exit 1
fi

# Sprawdzenie imageio-ffmpeg (powinna być tylko raz)
FFMPEG_COUNT=$(grep "imageio-ffmpeg" "$PROJECT_DIR/requirements.txt" | wc -l)
if [ "$FFMPEG_COUNT" -eq 1 ]; then
    echo "✅ imageio-ffmpeg wymieniona dokładnie 1 raz"
else
    echo "❌ BŁĄD: imageio-ffmpeg wymieniona $FFMPEG_COUNT razy (powinna 1)"
    exit 1
fi

echo ""
echo "📋 TEST 3: Sprawdzenie remove_bg_movie.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PLUGIN_FILE="$PROJECT_DIR/plugins/remove_bg_movie.py"

if [ ! -f "$PLUGIN_FILE" ]; then
    echo "❌ BŁĄD: Plugin remove_bg_movie.py nie znaleziony"
    exit 1
fi

# Sprawdzenie poprawnej inicjalizacji temp_path
if grep -q "temp_path = None" "$PLUGIN_FILE"; then
    echo "✅ temp_path jest inicjalizowany na None"
else
    echo "❌ BŁĄD: temp_path nie jest inicjalizowany"
    exit 1
fi

# Sprawdzenie poprawnej inicjalizacji clip
if grep -q "clip = None" "$PLUGIN_FILE"; then
    echo "✅ clip jest inicjalizowany na None"
else
    echo "❌ BŁĄD: clip nie jest inicjalizowany"
    exit 1
fi

# Sprawdzenie sprawdzenia clip is not None
if grep -q "if clip is not None:" "$PLUGIN_FILE"; then
    echo "✅ Są sprawdzenia 'if clip is not None'"
else
    echo "❌ BŁĄD: Brak sprawdzenia 'if clip is not None'"
    exit 1
fi

# Sprawdzenie obsługi wyjątków przy cleanup
if grep -q "except Exception:" "$PLUGIN_FILE"; then
    echo "✅ Obsługa wyjątków przy cleanup plików"
else
    echo "❌ BŁĄD: Brak obsługi wyjątków przy cleanup"
    exit 1
fi

# Sprawdzenie importu moviepy na górze funkcji
if grep -q "from moviepy.editor import VideoFileClip" "$PLUGIN_FILE"; then
    echo "✅ Import moviepy jest obecny"
else
    echo "❌ BŁĄD: Import moviepy brakuje"
    exit 1
fi

# Sprawdzenie poprawnej składni Python
python_output=$(python -m py_compile "$PLUGIN_FILE" 2>&1)
if [ -z "$python_output" ]; then
    echo "✅ Składnia Python jest poprawna"
else
    echo "❌ BŁĄD: Błąd w składni Python:"
    echo "$python_output"
    exit 1
fi

echo ""
echo "📋 TEST 4: Struktura Projektu"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Sprawdzenie czy wszystkie wymagane pliki istnieją
REQUIRED_FILES=(
    "Dockerfile"
    "requirements.txt"
    "app.py"
    "plugin_loader.py"
    "plugins/remove_bg_movie.py"
    "templates/index.html"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$PROJECT_DIR/$file" ]; then
        echo "✅ $file istnieje"
    else
        echo "❌ BŁĄD: $file brakuje"
        exit 1
    fi
done

# Sprawdzenie liczby pluginów
PLUGIN_COUNT=$(find "$PROJECT_DIR/plugins" -name "*.py" | wc -l)
echo "✅ Znaleziono $PLUGIN_COUNT pluginów"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ WSZYSTKIE TESTY PRZESZŁY POMYŚLNIE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Następnie możesz uruchomić:"
echo "   cd $PROJECT_DIR"
echo "   docker-compose build --no-cache"
echo ""
