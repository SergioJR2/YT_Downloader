"""Descubrimiento de dependencias y rutas del entorno de ejecución."""
import json
import os
import shutil
import sys

from .config import DENO_DIR, JS_RUNTIMES, LIBS_META, _JS_BINARY

def _activate_updated_libs():
    if not getattr(sys, 'frozen', False):
        return
    try:
        with open(LIBS_META, encoding='utf-8') as f:
            m = json.load(f)
        # Solo vale si fue creada para ESTA versión del .exe (si instalas un .exe
        # nuevo, se descarta y se usa el yt-dlp que trae)
        if (m.get('exe_mtime') == int(os.path.getmtime(sys.executable))
                and (os.path.isdir(os.path.join(m['dir'], 'yt_dlp'))
                     or os.path.isdir(os.path.join(m['dir'], 'yt_dlp_ejs')))):
            sys.path.insert(0, m['dir'])
    except Exception:
        pass

def get_cookie_option():
    """Usa cookies.txt (junto al ejecutable) si existe."""
    base = _app_dir()
    cookies_path = os.path.join(base, 'cookies.txt')
    if os.path.exists(cookies_path):
        return {'cookiefile': cookies_path}
    return {}

def find_ffmpeg():
    """ffmpeg es OPCIONAL. Devuelve su ruta si existe (PATH o paquete
    imageio-ffmpeg); si no, devuelve None y la app usa formatos nativos."""
    path = shutil.which('ffmpeg')
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def _app_dir():
    """Carpeta de la app: la del .exe, o la raíz del proyecto en modo desarrollo
    (la que contiene main.py, no la carpeta superior)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def find_js_runtimes():
    """Devuelve {nombre: {'path': ruta}} de los runtimes JS encontrados:
    carpeta de la app, Deno instalado por la app, y PATH del sistema."""
    found = {}
    exe_ext = '.exe' if os.name == 'nt' else ''
    local_deno = os.path.join(DENO_DIR, 'deno' + exe_ext)
    if os.path.isfile(local_deno):
        found['deno'] = {'path': local_deno}
    for name in JS_RUNTIMES:
        if name in found:
            continue
        exe = (shutil.which(_JS_BINARY[name], path=_app_dir())
               or shutil.which(_JS_BINARY[name]))
        if exe:
            found[name] = {'path': exe}
    return found

# PIDs de procesos auxiliares que deben sobrevivir al cierre de la app
# (por ejemplo, el script que reemplaza el .exe al actualizar).
_PROTECTED_PIDS = set()


def protect_pid(pid):
    """Evita que kill_child_processes() termine este proceso ni sus descendientes."""
    _PROTECTED_PIDS.add(int(pid))


def kill_child_processes():
    """Termina los procesos hijos de la app (ffmpeg, deno...). Si uno sigue vivo al
    cerrar, bloquea la carpeta temporal _MEI del .exe y Windows muestra
    "Failed to remove temporary directory". Requiere psutil (opcional).
    Se respetan los procesos registrados con protect_pid() (el actualizador)."""
    try:
        import psutil
        kids = psutil.Process().children(recursive=True)
        if _PROTECTED_PIDS:
            keep = set(_PROTECTED_PIDS)
            for pid in _PROTECTED_PIDS:
                try:
                    keep.update(c.pid for c in psutil.Process(pid).children(recursive=True))
                except Exception:
                    pass
            kids = [k for k in kids if k.pid not in keep]
        for k in kids:
            try: k.terminate()
            except Exception: pass
        _, alive = psutil.wait_procs(kids, timeout=2)
        for k in alive:
            try: k.kill()
            except Exception: pass
        return len(kids)
    except Exception:
        return 0