"""Registro de errores en archivo y captura global de excepciones.

La app se compila con console=False, así que sin esto cualquier fallo desaparece.
Además, en PyQt6 una excepción sin capturar dentro de un slot cierra la aplicación:
con un sys.excepthook propio se registra y la app sigue funcionando."""
import logging
import logging.handlers
import os
import sys
import threading

from .config import LIBS_ROOT, LOG_FILE

log = logging.getLogger("yt_downloader")
_showing = False


def setup_logging():
    """Configura el archivo de registro (rotativo) y los manejadores globales."""
    log.setLevel(logging.INFO)
    if not log.handlers:
        try:
            os.makedirs(LIBS_ROOT, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                LOG_FILE, maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(handler)
        except OSError:
            log.addHandler(logging.NullHandler())   # sin carpeta de logs: no romper la app
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook


def _excepthook(exc_type, exc, tb):
    global _showing
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    log.error("Excepción no controlada", exc_info=(exc_type, exc, tb))
    if _showing or threading.current_thread() is not threading.main_thread():
        return
    _showing = True            # evita una cascada de diálogos si el error se repite
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None, "Error inesperado",
                f"Ocurrió un error inesperado, pero la aplicación sigue abierta.\n\n"
                f"{exc_type.__name__}: {exc}\n\nDetalles guardados en:\n{LOG_FILE}")
    except Exception:
        pass
    finally:
        _showing = False


def _thread_excepthook(args):
    if args.exc_type is SystemExit:
        return
    log.error("Excepción no controlada en un hilo",
              exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
