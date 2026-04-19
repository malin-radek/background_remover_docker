#!/usr/bin/env python
"""
Start server with cache disabled
"""
import os
import sys
import shutil
from pathlib import Path

# Wyłącz cache PRZED importem czegokolwiek
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True

# Czyszczenie cache directoriów
for cache_dir in ['__pycache__', 'plugins/__pycache__']:
    if Path(cache_dir).exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
        
print("[startup] Cache directories cleaned")

# Teraz import app
from app import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
