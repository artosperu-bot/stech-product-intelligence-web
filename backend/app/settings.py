from __future__ import annotations
import os
from pathlib import Path

APP_NAME = 'STECH Product Intelligence Web'
APP_VERSION = 'web-v7-worker'
WORKFLOWS = ['characteristics', 'prices', 'images', 'videos']
BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / 'static'
RUNTIME_DIR = Path(os.getenv('STECH_RUNTIME_DIR', '/tmp/stech-product-intelligence'))


def get_port() -> int:
    try:
        port = int(os.getenv('PORT', '8080'))
        return port if 1 <= port <= 65535 else 8080
    except Exception:
        return 8080
