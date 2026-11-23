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
    elif is_webpage_blocked_error(e):
        if not has_impersonation():
            msg += ('\n→ TikTok exige que la app se identifique como un navegador y falta '
                    'el componente curl-cffi. Con «py main.py»: ejecuta dependencias.bat (o '
                    'pip install -U "yt-dlp[default,curl-cffi]") y reinicia. El .exe nuevo ya lo incluye.')
        else:
            msg += ('\n→ El sitio bloqueó la petición. Prueba: Herramientas → Actualizar yt-dlp, '
                    'volver a intentar más tarde, o colocar un cookies.txt (con tu sesión de ese '
                    'sitio) junto a la aplicación.')
    elif is_bot_error(e):
        msg += ('\n→ YouTube pide verificar que no eres un robot. Opciones: coloca un '
                'cookies.txt junto a la aplicación, o activa «Usar cookies del navegador» '
                'en Ajustes (inicia sesión antes en YouTube con ese navegador).')
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

_BOT_HINTS = ('not a bot', 'sign in to confirm', 'login required',
              'http error 403', 'forbidden')


def is_bot_error(e):
    """Frases concretas de YouTube/HTTP. Antes se buscaba '403' o 'sign in' como
    subcadena suelta y un ID de video o una URL podían dar falsos positivos."""
    m = _raw_err(e).lower()
    return any(h in m for h in _BOT_HINTS)

_BLOCKED_HINTS = ('unexpected response from webpage', 'unable to extract webpage video data')


def is_webpage_blocked_error(e):
    """TikTok (y otros) devuelven una página que no es el video cuando bloquean la
    petición o no se la identifica como navegador."""
    m = _raw_err(e).lower()
    return any(h in m for h in _BLOCKED_HINTS)


def has_impersonation():
    """True si curl_cffi está disponible (yt-dlp puede imitar un navegador)."""
    try:
        import curl_cffi  # noqa: F401
        return True
    except Exception:
        return False


def is_unavailable_error(e):
    m = _raw_err(e).lower()
    return any(k in m for k in ('not available', 'requested format',
                                'n challenge', 'signature', 'unable to extract'))
