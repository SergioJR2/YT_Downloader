"""Registro de eventos en un archivo rotativo para facilitar el soporte."""
import logging
import os
from logging.handlers import RotatingFileHandler

from .config import LIBS_ROOT

LOG_PATH = os.path.join(LIBS_ROOT, "app.log")


def setup_logging():
    """Configura un log de hasta 3 × 512 KB en %LOCALAPPDATA%\\YT_Downloader.
    Si la carpeta no es escribible, la app sigue sin registro."""
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    try:
        os.makedirs(LIBS_ROOT, exist_ok=True)
        handler = RotatingFileHandler(LOG_PATH, maxBytes=512 * 1024,
                                      backupCount=2, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
