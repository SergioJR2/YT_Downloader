"""Actualización de la propia aplicación desde GitHub Releases."""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from .config import APP_VERSION, GITHUB_REPO, UPDATE_DIR

RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
# Solo se descargan archivos publicados en las releases de ESTE repositorio.
_DOWNLOAD_PREFIX = f"https://github.com/{GITHUB_REPO}/releases/download/"
_HEADERS = {'User-Agent': 'YT_Downloader-updater',
            'Accept': 'application/vnd.github+json'}
PORTABLE_TMP_NAME = 'YT_Downloader_update.exe'


class UpdateCancelled(Exception):
    """El usuario canceló la descarga."""


# ── Versiones ────────────────────────────────────────────────────────────

def _ver_tuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', v or ''))


def _is_newer(remote, local):
    n = max(len(remote), len(local))
    pad = lambda t: t + (0,) * (n - len(t))
    return pad(remote) > pad(local)


# ── Consulta a GitHub ────────────────────────────────────────────────────

def _http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _is_frozen():
    return bool(getattr(sys, 'frozen', False))


def _exe_dir():
    return os.path.dirname(sys.executable)


def is_installed_by_setup():
    """True si el .exe en ejecución vive en una carpeta creada por el instalador."""
    return os.path.isfile(os.path.join(_exe_dir(), 'unins000.exe'))


def _can_write(folder):
    probe = os.path.join(folder, '.yt_write_test')
    try:
        with open(probe, 'wb'):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def _pick_assets(assets):
    exes = [a for a in assets if str(a.get('name', '')).lower().endswith('.exe')]
    setup = next((a for a in exes if 'setup' in a['name'].lower()), None)
    others = [a for a in exes if a is not setup]
    portable = next((a for a in others if a['name'].lower() == 'yt_downloader.exe'),
                    others[0] if others else None)
    return setup, portable


def _asset_sha256(asset, assets):
    """SHA-256 publicado por GitHub (campo digest) o en un .sha256 hermano."""
    digest = str(asset.get('digest') or '')
    if digest.lower().startswith('sha256:'):
        return digest.split(':', 1)[1].strip().lower()
    sibling = next((a for a in assets
                    if a.get('name', '').lower() == asset['name'].lower() + '.sha256'), None)
    if sibling and str(sibling.get('browser_download_url', '')).startswith(_DOWNLOAD_PREFIX):
        m = re.search(r'\b[0-9a-fA-F]{64}\b',
                      _http_get(sibling['browser_download_url']).decode('utf-8', 'ignore'))
        if m:
            return m.group(0).lower()
    return None


def check_for_update():
    """Consulta la última release publicada.

    Devuelve un dict: tag, version, notes, page, newer y asset
    (None si no hay nada que instalar automáticamente)."""
    info = {'tag': '', 'version': '', 'notes': '', 'page': RELEASES_URL,
            'newer': False, 'asset': None}
    try:
        rel = json.loads(_http_get(_API_LATEST))
    except urllib.error.HTTPError as e:
        if e.code == 404:          # el repositorio todavía no tiene releases
            return info
        if e.code in (403, 429):   # límite de consultas anónimas de la API (60 por hora)
            raise RuntimeError("GitHub limitó temporalmente las consultas. "
                               "Inténtalo de nuevo en unos minutos.")
        raise
    if rel.get('draft') or rel.get('prerelease'):
        return info
    ver = _ver_tuple(rel.get('tag_name'))
    info.update(tag=rel.get('tag_name') or '',
                version='.'.join(str(x) for x in ver),
                notes=(rel.get('body') or '').strip(),
                page=rel.get('html_url') or RELEASES_URL,
                newer=bool(ver) and _is_newer(ver, _ver_tuple(APP_VERSION)))
    if not info['newer'] or not _is_frozen():
        return info

    assets = rel.get('assets') or []
    setup, portable = _pick_assets(assets)
    order = ([('setup', setup), ('portable', portable)] if is_installed_by_setup()
             else [('portable', portable), ('setup', setup)])
    for kind, a in order:
        if not a:
            continue
        url = str(a.get('browser_download_url', ''))
        if not url.startswith(_DOWNLOAD_PREFIX):
            continue
        # Reemplazar el .exe directamente solo si su carpeta admite escritura.
        if kind == 'portable' and not _can_write(_exe_dir()):
            continue
        info['asset'] = {'kind': kind, 'name': a['name'], 'url': url,
                         'size': int(a.get('size') or 0),
                         'sha256': _asset_sha256(a, assets)}
        break
    return info


# ── Descarga ─────────────────────────────────────────────────────────────

def cleanup_update_files():
    """Borra restos de actualizaciones anteriores (ignora lo que siga en uso)."""
    leftovers = [os.path.join(_exe_dir(), PORTABLE_TMP_NAME),
                 os.path.join(_exe_dir(), PORTABLE_TMP_NAME + '.part')] if _is_frozen() else []
    if os.path.isdir(UPDATE_DIR):
        leftovers += [os.path.join(UPDATE_DIR, n) for n in os.listdir(UPDATE_DIR)]
    for p in leftovers:
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


def download_update(asset, progress=None, cancelled=None):
    """Descarga y verifica el archivo. progress(descargado, total); cancelled() -> bool.
    Devuelve la ruta del archivo listo para aplicar."""
    if not asset['url'].startswith(_DOWNLOAD_PREFIX):
        raise RuntimeError("La dirección de descarga no pertenece al repositorio oficial.")
    if asset['kind'] == 'portable':
        dest = os.path.join(_exe_dir(), PORTABLE_TMP_NAME)
    else:
        os.makedirs(UPDATE_DIR, exist_ok=True)
        dest = os.path.join(UPDATE_DIR, os.path.basename(asset['name']))
    tmp = dest + '.part'
    sha = hashlib.sha256()
    done = 0
    try:
        req = urllib.request.Request(asset['url'], headers={'User-Agent': _HEADERS['User-Agent']})
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp, 'wb') as f:
            total = int(r.headers.get('Content-Length') or asset['size'] or 0)
            while True:
                if cancelled and cancelled():
                    raise UpdateCancelled()
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if asset['size'] and done != asset['size']:
            raise RuntimeError("La descarga quedó incompleta. Inténtalo de nuevo.")
        if asset['sha256'] and sha.hexdigest() != asset['sha256']:
            raise RuntimeError("La descarga está corrupta (el SHA-256 no coincide).")
        with open(tmp, 'rb') as f:
            if f.read(2) != b'MZ':
                raise RuntimeError("El archivo descargado no es un ejecutable válido.")
        os.replace(tmp, dest)
        return dest
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# ── Aplicar ──────────────────────────────────────────────────────────────

def _q(path):
    return path.replace('%', '%%')


def apply_update(path, kind):
    """Lanza un script que espera a que esta app cierre, instala la versión nueva y
    la vuelve a abrir. Después de llamarla hay que cerrar la aplicación."""
    if os.name != 'nt':
        raise RuntimeError("La actualización automática solo funciona en Windows.")
    if not _is_frozen():
        raise RuntimeError("La actualización automática solo funciona con el .exe.")
    os.makedirs(UPDATE_DIR, exist_ok=True)
    target = sys.executable
    bat = os.path.join(UPDATE_DIR, 'apply_update.bat')
    if kind == 'portable':
        lines = [
            '@chcp 65001 >nul', '@echo off', 'set N=0', ':retry',
            'ping -n 3 127.0.0.1 >nul',
            f'move /y "{_q(path)}" "{_q(target)}" >nul 2>&1',
            'if not errorlevel 1 goto ok',
            'set /a N+=1',
            'if %N% lss 30 goto retry',
            f'start "" "{_q(target)}"',          # no se pudo reemplazar: abre la versión actual
            'exit /b 1', ':ok',
            f'start "" "{_q(target)}"',
            '(goto) 2>nul & del "%~f0"',
        ]
    else:
        lines = [
            '@chcp 65001 >nul', '@echo off',
            'ping -n 4 127.0.0.1 >nul',
            f'start "" /wait "{_q(path)}" /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS',
            f'if errorlevel 1 start "" "{_q(target)}"',   # el instalador falló: reabre la actual
            f'del "{_q(path)}" >nul 2>&1',
            '(goto) 2>nul & del "%~f0"',
        ]
    with open(bat, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write('\n'.join(lines) + '\n')
    env = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
    # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP: sigue vivo cuando esta app se cierra
    subprocess.Popen(['cmd', '/c', bat], env=env, close_fds=True,
                     creationflags=0x08000000 | 0x00000200)
