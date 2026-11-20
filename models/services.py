"""Servicios de yt-dlp, autenticación, actualización y runtime JavaScript."""
import hashlib
import io
import json
import os
import platform
import re
import shutil
import sys
import zipfile

from .config import (
    ALT_CLIENTS,
    BROWSERS,
    DENO_DIR,
    DENO_SHA256,
    DENO_VERSION,
    LIBS_META,
    LIBS_ROOT,
)
from .errors import (
    PauseRequested,
    _raw_err,
    is_bot_error,
    is_unavailable_error,
)
from .runtime import _activate_updated_libs, find_js_runtimes

# El usuario puede actualizar las bibliotecas desde el EXE; actívalas antes de
# importar yt-dlp para que el módulo cargue desde la versión actualizada.
_activate_updated_libs()
import yt_dlp

def has_ejs():
    try:
        import yt_dlp_ejs  # noqa: F401
        return True
    except Exception:
        return False

def youtube_opts():
    """Opciones de yt-dlp para que YouTube funcione: runtime JS + solver EJS."""
    opts = {}
    runtimes = find_js_runtimes()
    if runtimes:
        opts['js_runtimes'] = runtimes
    if not has_ejs():
        # Sin el paquete yt-dlp-ejs, permite bajar el solver desde GitHub
        opts['remote_components'] = ['ejs:github']
    return opts

def run_with_auth_fallback(opts, action, allow_browser_cookies=False):
    """Ejecuta action(ydl). Orden de intentos:
      1) normal (con motor JS)
      2) otros clientes de YouTube (si el video "no está disponible" / 403)
      3) con cookies.txt, si existe
      4) cookies leidas del navegador: SOLO si el usuario lo activó en Ajustes
         (allow_browser_cookies), porque implica leer datos sensibles del navegador.
    Si todo falla, se informa el error del PRIMER intento (el más útil)."""
    clean = {k: v for k, v in opts.items()
             if k not in ('cookiefile', 'cookiesfrombrowser')}
    base = {**clean, **youtube_opts()}
    steps = [('base', base),
             ('clients', {**base, 'extractor_args':
                          {'youtube': {'player_client': list(ALT_CLIENTS)}}})]
    if 'cookiefile' in opts:
        steps.append(('cookiefile', {**base, 'cookiefile': opts['cookiefile']}))
    if allow_browser_cookies:
        steps += [('browser', {**base, 'cookiesfrombrowser': (br,)}) for br in BROWSERS]

    def should_try(kind, err):
        if err is None:
            return True
        if kind in ('clients', 'cookiefile'):
            return is_unavailable_error(err) or is_bot_error(err)
        return is_bot_error(err) or 'cookie' in _raw_err(err).lower()   # browser

    first = last = None
    for kind, o in steps:
        if not should_try(kind, last):
            continue
        try:
            with yt_dlp.YoutubeDL(o) as ydl:
                return action(ydl)
        except Exception as e:
            if isinstance(e, PauseRequested):
                raise
            if first is None:
                first = e
                if not (is_unavailable_error(e) or is_bot_error(e)):
                    raise                     # error real (red, URL...): no insistir
            last = e
    raise first

def ytdlp_version():
    try:
        import yt_dlp.version as v
        return v.__version__
    except Exception:
        return '?'

def _http_get(url, timeout=60):
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'YT_Downloader-updater'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _ver_tuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', v or ''))

def _pypi_wheel(pkg):
    """(última versión, info del wheel py3-none-any) de un paquete en PyPI."""
    data = json.loads(_http_get(f'https://pypi.org/pypi/{pkg}/json'))
    wheel = next(u for u in data['urls']
                 if u['packagetype'] == 'bdist_wheel' and u['filename'].endswith('py3-none-any.whl'))
    return data['info']['version'], wheel

def ejs_version():
    try:
        import yt_dlp_ejs._version as v
        return v.__version__
    except Exception:
        return None

def _extract_wheel(wheel, target):
    blob = _http_get(wheel['url'], 180)
    if hashlib.sha256(blob).hexdigest() != wheel['digests']['sha256']:
        raise RuntimeError("La descarga está corrupta (el SHA-256 no coincide).")
    root = os.path.realpath(target) + os.sep
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for n in z.namelist():   # evita rutas fuera de la carpeta destino
            if not os.path.realpath(os.path.join(target, n)).startswith(root):
                raise RuntimeError("El paquete descargado no es válido.")
        z.extractall(target)

def portable_update_ytdlp():
    """Actualiza yt-dlp y yt-dlp-ejs SIN pip (para el .exe): descarga los wheels
    oficiales desde PyPI, verifica su SHA-256 y los extrae en LIBS_ROOT.
    Devuelve (cambió, mensaje)."""
    ytv, ytw = _pypi_wheel('yt-dlp')
    ejv, ejw = _pypi_wheel('yt-dlp-ejs')
    cur_yt, cur_ej = ytdlp_version(), ejs_version()
    need_yt = _ver_tuple(ytv) > _ver_tuple(cur_yt)
    need_ej = cur_ej is None or _ver_tuple(ejv) > _ver_tuple(cur_ej)
    if not (need_yt or need_ej):
        return False, f"yt-dlp ya está al día (v{cur_yt}, ejs v{cur_ej})."
    os.makedirs(LIBS_ROOT, exist_ok=True)
    target = os.path.join(LIBS_ROOT, f'libs_{ytv}_{ejv}')
    shutil.rmtree(target, ignore_errors=True)
    _extract_wheel(ytw, target)      # se extraen ambos: la carpeta queda completa
    _extract_wheel(ejw, target)
    with open(LIBS_META, 'w', encoding='utf-8') as f:
        json.dump({'version': ytv, 'ejs': ejv, 'dir': target,
                   'exe_mtime': int(os.path.getmtime(sys.executable))}, f)
    for d in os.listdir(LIBS_ROOT):   # borra versiones anteriores
        p = os.path.join(LIBS_ROOT, d)
        if d.startswith('libs_') and p != target:
            shutil.rmtree(p, ignore_errors=True)
    parts = []
    if need_yt: parts.append(f"yt-dlp: v{cur_yt} → v{ytv}")
    if need_ej: parts.append(f"yt-dlp-ejs: {'v'+cur_ej if cur_ej else 'no estaba'} → v{ejv}")
    return True, "Actualizado — " + ";  ".join(parts) + "."

def ensure_js_runtime():
    """Si no hay ningún motor JavaScript, instala Deno (Windows) en LIBS_ROOT
    verificando su SHA-256. Devuelve (instalado_ahora, mensaje)."""
    if find_js_runtimes():
        return False, "Motor JavaScript: ya disponible."
    if platform.system() != 'Windows':
        return False, ("Falta un motor JavaScript. Instala Deno (https://deno.com) "
                       "o Node 20+ y reinicia la app.")
    arch = 'aarch64' if platform.machine().upper() in ('ARM64', 'AARCH64') else 'x86_64'
    expected = DENO_SHA256[arch]       # hash fijo en config.py, no el del servidor
    name = f'deno-{arch}-pc-windows-msvc.zip'
    url = f'https://github.com/denoland/deno/releases/download/{DENO_VERSION}/{name}'
    blob = _http_get(url, 300)
    if hashlib.sha256(blob).hexdigest().lower() != expected.lower():
        raise RuntimeError("La descarga de Deno está corrupta o no es la esperada "
                           "(el SHA-256 no coincide).")
    os.makedirs(DENO_DIR, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as z, \
            open(os.path.join(DENO_DIR, 'deno.exe'), 'wb') as dst:
        shutil.copyfileobj(z.open('deno.exe'), dst)
    return True, f"Motor JavaScript (Deno {DENO_VERSION}) instalado."

def _pkg_version(name):
    try:
        import importlib, importlib.metadata as md
        importlib.invalidate_caches()
        return md.version(name)
    except Exception:
        return None
