"""Normalización y clasificación de errores de descarga."""
import re

from .runtime import find_js_runtimes

PAUSED_MSG = '__PAUSED__'
_LOCK_HINTS = ('winerror 5', 'winerror 32', 'acceso denegado', 'access is denied',
               'permission denied', 'used by another process', 'otro proceso',
               'unable to rename file', 'unable to remove file')

class PauseRequested(Exception):
    """Señala al worker que debe pausar y conservar el archivo parcial."""

def _raw_err(e):
    msg = re.sub(r'\x1b\[[0-9;]*m', '', str(e)).strip()
    return re.sub(r'^(ERROR:\s*)+', '', msg)

def clean_err(e):
    """Quita los códigos de color ANSI y agrega pistas útiles."""
    msg = _raw_err(e)
    low = msg.lower()
    if any(k in low for k in ('httpsconnectionpool', 'httpconnectionpool', 'read timed out',
                              'connection aborted', 'connection reset', 'remote end closed',
                              'incompleteread', 'getaddrinfo', 'timed out')):
        return ('Se interrumpió la conexión con YouTube. Pulsa «Reintentar»: '
                'continúa desde donde quedó.\n' + msg)
    if '416' in low and 'range' in low:
        return ('YouTube rechazó reanudar el archivo parcial. Se intentó reiniciar la '
                'descarga desde cero; pulsa «Reintentar» si volvió a fallar.\n' + msg)
    unavailable = ('not available' in low or 'requested format' in low
                   or 'n challenge' in low or 'signature' in low)
    if unavailable and not find_js_runtimes():
        msg += ('\n→ Falta el motor JavaScript (Deno) que YouTube exige ahora. '
                'Pulsa «Actualizar»: lo instala automáticamente.')
    elif 'not available' in low and 'format' not in low:
        msg += ('\n→ Si el video abre en tu navegador, pulsa «Actualizar» y reintenta. '
                'Si tampoco abre allí, es privado, fue eliminado o está bloqueado '
                'en tu país.')
    elif 'format is not available' in low or 'requested format' in low:
        msg += '\n→ Pulsa «Actualizar» (yt-dlp desactualizado) y reinicia.'
    elif is_file_lock_error(e):
        msg += ('\n→ Otro programa (antivirus, OneDrive, reproductor) tiene el archivo '
                'bloqueado. Pulsa «Reintentar»; si se repite, excluye la carpeta de '
                'descargas en Windows Defender.')
    elif 'private video' in low:
        msg += '\n→ El video es privado: solo su dueño puede descargarlo.'
    elif 'members-only' in low or 'members only' in low:
        msg += '\n→ Es contenido para miembros del canal: requiere cookies.txt de una cuenta con acceso.'
    return msg

def is_file_lock_error(e):
    if isinstance(e, PermissionError):
        return True
    return any(h in _raw_err(e).lower() for h in _LOCK_HINTS)

def is_http_416_error(e):
    """Un 416 al reanudar suele indicar que el .part no coincide con el archivo remoto."""
    if getattr(e, 'code', None) == 416 or getattr(e, 'status', None) == 416:
        return True
    msg = _raw_err(e).lower()
    return '416' in msg and ('range' in msg or 'requested range' in msg)

def is_bot_error(e):
    m = _raw_err(e).lower()
    return 'not a bot' in m or 'sign in' in m or '403' in m

def is_unavailable_error(e):
    m = _raw_err(e).lower()
    return any(k in m for k in ('not available', 'requested format',
                                'n challenge', 'signature', 'unable to extract'))
