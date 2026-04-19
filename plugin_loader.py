"""
Plugin loader — skanuje katalog plugins/ i ładuje wszystkie moduły z METADATA.
"""

import importlib.util
import importlib
import sys
import traceback
from pathlib import Path

PLUGINS_DIR = Path(__file__).parent / "plugins"

# Fallback - jeśli nie istnieje, sprawdź /app/plugins (Docker)
if not PLUGINS_DIR.exists():
    alt_dir = Path("/app/plugins")
    if alt_dir.exists():
        PLUGINS_DIR = alt_dir
PROJECT_DIR = str(Path(__file__).parent.resolve())

# ── KLUCZOWE: dodaj katalog projektu do sys.path żeby pluginy mogły importować
# plugin_utils i inne moduły z katalogu głównego projektu.
# Bez tego spec_from_file_location ładuje plugin w izolacji bez CWD w path.
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
    print(f"[plugin_loader] Dodano do sys.path: {PROJECT_DIR}")

_loaded: dict = {}  # id -> (module, metadata)


def _load_plugin(path: Path):
    """Ładuje pojedynczy plik pluginu."""
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    meta = getattr(mod, "METADATA", None)
    if not meta or "id" not in meta:
        return None
    return mod, meta


def load_all():
    """Skanuje plugins/ i ładuje wszystkie pluginy. Zwraca dict id->metadata."""
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)

    importlib.invalidate_caches()
    sys.path_importer_cache.clear()

    _loaded.clear()
    if not PLUGINS_DIR.exists():
        print(f"[plugin_loader] BRAK katalogu plugins/: {PLUGINS_DIR}")
        return {}

    plugin_files = sorted(PLUGINS_DIR.glob("*.py"))
    print(f"[plugin_loader] Znaleziono {len(plugin_files)} plikow w plugins/")

    for path in plugin_files:
        if path.name.startswith("_"):
            continue
        try:
            result = _load_plugin(path)
            if result:
                mod, meta = result
                _loaded[meta["id"]] = (mod, meta)
                print(f"[plugin_loader] OK    {meta['id']} <- {path.name}")
            else:
                print(f"[plugin_loader] SKIP  {path.name} (brak METADATA)")
        except Exception as e:
            print(f"[plugin_loader] ERROR {path.name}: {e}")
            traceback.print_exc()

    return {pid: m for pid, (_, m) in _loaded.items()}


def get_plugin(plugin_id: str):
    entry = _loaded.get(plugin_id)
    return entry[0] if entry else None


def get_metadata(plugin_id: str) -> dict | None:
    entry = _loaded.get(plugin_id)
    return entry[1] if entry else None


def list_plugins() -> list[dict]:
    return [m for _, m in _loaded.values()]


def list_plugins_dict() -> dict:
    return {pid: m for pid, (_, m) in _loaded.items()}
