import sys
import os
import re
import subprocess
import platform
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar,
    QScrollArea, QFrame, QCheckBox, QSizePolicy, QSpinBox, QMessageBox,
    QComboBox, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer, QSettings
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QPixmap, QIcon, QPainter,
    QBrush, QImage, QPolygon
)
from PyQt6.QtCore import QPoint
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import json
import io
import shutil
import hashlib
import zipfile
import tempfile
import sqlite3

# ─── Dependencias actualizables (funciona también dentro del .exe) ───────────
# El botón "Actualizar" descarga el yt-dlp más reciente a esta carpeta y la app
# la usa en lugar de la versión empaquetada en el .exe.
LIBS_ROOT = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'YT_Downloader')
LIBS_META = os.path.join(LIBS_ROOT, 'libs_meta.json')

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

_activate_updated_libs()
import yt_dlp

def get_cookie_option():
    """Usa cookies.txt (junto al ejecutable) si existe."""
    base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
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

BROWSERS = ('firefox', 'edge', 'chrome', 'brave')

# ─── Motor JavaScript (necesario para YouTube desde yt-dlp 2025.11) ──────────
# YouTube obliga a resolver un desafío en JavaScript. Sin un runtime JS (Deno,
# Node, Bun o QuickJS) yt-dlp se queda con un solo cliente y muchos videos
# fallan con un engañoso "This video is not available".
DENO_DIR = os.path.join(LIBS_ROOT, 'deno')
JS_RUNTIMES = ('deno', 'node', 'bun', 'quickjs')        # orden de prioridad
_JS_BINARY  = {'deno': 'deno', 'node': 'node', 'bun': 'bun', 'quickjs': 'qjs'}

def _app_dir():
    return os.path.dirname(sys.executable if getattr(sys, 'frozen', False)
                           else os.path.abspath(__file__))

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

def _raw_err(e):
    msg = re.sub(r'\x1b\[[0-9;]*m', '', str(e)).strip()
    return re.sub(r'^(ERROR:\s*)+', '', msg)     # evita "ERROR: ERROR: ..."

def clean_err(e):
    """Quita los códigos de color ANSI y agrega pistas útiles."""
    msg = _raw_err(e)
    low = msg.lower()
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
    elif 'private video' in low:
        msg += '\n→ El video es privado: solo su dueño puede descargarlo.'
    elif 'members-only' in low or 'members only' in low:
        msg += '\n→ Es contenido para miembros del canal: requiere cookies.txt de una cuenta con acceso.'
    return msg

def is_bot_error(e):
    m = _raw_err(e).lower()
    return 'not a bot' in m or 'sign in' in m or '403' in m

def is_unavailable_error(e):
    m = _raw_err(e).lower()
    return any(k in m for k in ('not available', 'requested format',
                                'n challenge', 'signature', 'unable to extract'))

# Clientes de YouTube a probar si el intento normal falla
ALT_CLIENTS = ('default', 'tv', 'web_safari', 'mweb')

def run_with_auth_fallback(opts, action):
    """Ejecuta action(ydl). Orden de intentos:
      1) normal (con motor JS)
      2) otros clientes de YouTube (si el video "no está disponible" / 403)
      3) con cookies.txt, si existe
      4) cookies leidas del navegador (solo si YouTube pide login / bot)
    Si todo falla, se informa el error del PRIMER intento (el más útil)."""
    clean = {k: v for k, v in opts.items()
             if k not in ('cookiefile', 'cookiesfrombrowser')}
    base = {**clean, **youtube_opts()}
    steps = [('base', base),
             ('clients', {**base, 'extractor_args':
                          {'youtube': {'player_client': list(ALT_CLIENTS)}}})]
    if 'cookiefile' in opts:
        steps.append(('cookiefile', {**base, 'cookiefile': opts['cookiefile']}))
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

# ─── Config ───────────────────────────────────────────────────────────────────
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Descargas_YouTube")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Máximo de descargas simultáneas (ajustable por el usuario, default: 2)
DEFAULT_CONCURRENT = 2
MAX_CONCURRENT     = 5

C_BG      = "#0d0d14"
C_SURFACE = "#14141f"
C_SURF2   = "#1c1c2e"
C_SURF3   = "#22223a"
C_BORDER  = "#2a2a40"
C_ACCENT  = "#e63d3d"
C_ACCENT2 = "#ff6b35"
C_GOLD    = "#f5c842"
C_TEXT    = "#f0f0f8"
C_MUTED   = "#6060a0"
C_SUCCESS = "#3dba7a"


# ─── Hilos ────────────────────────────────────────────────────────────────────

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
    name = f'deno-{arch}-pc-windows-msvc.zip'
    base = 'https://github.com/denoland/deno/releases/latest/download/'
    m = re.search(r'\b[0-9a-fA-F]{64}\b', _http_get(base + name + '.sha256sum').decode('utf-8', 'ignore'))
    if not m:
        raise RuntimeError("No se pudo obtener el SHA-256 de Deno.")
    blob = _http_get(base + name, 300)
    if hashlib.sha256(blob).hexdigest().lower() != m.group(0).lower():
        raise RuntimeError("La descarga de Deno está corrupta (el SHA-256 no coincide).")
    os.makedirs(DENO_DIR, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as z, \
            open(os.path.join(DENO_DIR, 'deno.exe'), 'wb') as dst:
        shutil.copyfileobj(z.open('deno.exe'), dst)
    return True, "Motor JavaScript (Deno) instalado."

def _pkg_version(name):
    try:
        import importlib, importlib.metadata as md
        importlib.invalidate_caches()
        return md.version(name)
    except Exception:
        return None


class UpdateThread(QThread):
    done = pyqtSignal(bool, str, bool)   # ok, mensaje, requiere_reinicio

    def run(self):
        try:
            if getattr(sys, 'frozen', False):
                changed, msg = portable_update_ytdlp()
                js_changed, js_msg = ensure_js_runtime()
                self.done.emit(True, msg + "\n" + js_msg
                               + "\nffmpeg: ya va incluido en la app.",
                               changed or js_changed)
                return
            pkgs   = ['yt-dlp', 'yt-dlp-ejs', 'imageio-ffmpeg']
            before = {p: _pkg_version(p) for p in pkgs}
            flags  = 0x08000000 if platform.system() == 'Windows' else 0  # sin ventana
            base   = [sys.executable, '-m', 'pip', 'install', '-U', '--quiet']
            r = subprocess.run(base + ['yt-dlp[default]', 'imageio-ffmpeg'],
                               capture_output=True, text=True,
                               timeout=300, creationflags=flags)
            if r.returncode != 0:   # imageio-ffmpeg es opcional: reintenta sin él
                r = subprocess.run(base + ['yt-dlp[default]'], capture_output=True,
                                   text=True, timeout=300, creationflags=flags)
            if r.returncode != 0:
                self.done.emit(False, (r.stderr or r.stdout or 'Error desconocido')[-400:], False)
                return
            lines, changed = [], False
            for p in pkgs:
                a = _pkg_version(p)
                if a is None:
                    continue
                if before[p] is None:
                    lines.append(f"{p}: instalado (v{a})"); changed = True
                elif a != before[p]:
                    lines.append(f"{p}: v{before[p]} → v{a}"); changed = True
                else:
                    lines.append(f"{p}: ya está al día (v{a})")
            js_changed, js_msg = ensure_js_runtime()
            lines.append(js_msg)
            self.done.emit(True, "\n".join(lines), changed or js_changed)
        except Exception as e:
            self.done.emit(False, str(e), False)


class FetchThread(QThread):
    result = pyqtSignal(dict)
    error  = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            opts = {
                'quiet': True, 'no_warnings': True, 'no_color': True,
                'extract_flat': 'in_playlist',
                **get_cookie_option(),
            }
            info = run_with_auth_fallback(
                opts, lambda ydl: ydl.extract_info(self.url, download=False))

            if info.get('_type') == 'playlist':
                entries = info.get('entries', [])
                self.result.emit({
                    'type': 'playlist',
                    'title': info.get('title', 'Playlist'),
                    'count': len(entries),
                    'items': [
                        {
                            'title':    e.get('title', 'Sin título'),
                            'url':      e.get('url') or f"https://youtube.com/watch?v={e.get('id')}",
                            'duration': e.get('duration', 0),
                        }
                        for e in entries[:200]
                    ]
                })
            else:
                formats = info.get('formats', [])
                heights = sorted(
                    set(f.get('height') for f in formats if f.get('height')),
                    reverse=True
                )
                self.result.emit({
                    'type':      'video',
                    'url':       self.url,
                    'title':     info.get('title', 'Sin título'),
                    'duration':  info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'channel':   info.get('uploader', ''),
                    'views':     info.get('view_count', 0),
                    'qualities': [str(h) for h in heights[:5]],
                })
        except Exception as e:
            self.error.emit(clean_err(e))


PAUSED_MSG = '__PAUSED__'

class PauseRequested(Exception):
    """Se lanza desde el hook de progreso para detener (pausar) una descarga."""


class DownloadThread(QThread):
    progress = pyqtSignal(str, float, str, str)
    finished = pyqtSignal(str, bool, str)

    def __init__(self, task_id, url, fmt, quality, output_dir, audio_quality, speed_limit):
        super().__init__()
        self.task_id = task_id
        self.url     = url
        self.fmt     = fmt
        self.quality = quality
        self.output_dir = output_dir
        self.audio_quality = audio_quality
        self.speed_limit = speed_limit
        self._pause  = False

    def request_pause(self):
        """Pausa = detener la descarga conservando el archivo .part.
        Al reanudar, yt-dlp continúa desde donde quedó."""
        self._pause = True

    def _hook(self, d):
        if self._pause:
            raise PauseRequested()
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            dl    = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0) or 0
            pct   = (dl / total * 100) if total else 0
            self.progress.emit(self.task_id, pct, self._fmt_speed(speed), 'downloading')
        elif d['status'] == 'finished':
            self.progress.emit(self.task_id, 100, '', 'processing')

    @staticmethod
    def _fmt_speed(s):
        if not s: return ''
        if s > 1024**2: return f"{s/1024**2:.1f} MB/s"
        if s > 1024:    return f"{s/1024:.1f} KB/s"
        return f"{s:.0f} B/s"

    def run(self):
        try:
            base = {
                'progress_hooks': [self._hook],
                'quiet': True, 'no_warnings': True, 'no_color': True, 'noprogress': True,
                # Limitar fragmentos simultáneos para reducir uso de red/CPU
                'concurrent_fragment_downloads': 3,
                # Títulos larguísimos rompen el límite de ruta de Windows
                'trim_file_name': 150,
                **get_cookie_option(),
            }
            if self.speed_limit > 0:
                base['ratelimit'] = self.speed_limit * 1024
            ffmpeg = find_ffmpeg()
            outtmpl = os.path.join(self.output_dir, '%(title)s.%(ext)s')

            if self.fmt in ('m4a', 'opus'):
                # Descarga la pista original sin conversión ni ffmpeg.
                # Mantener el selector estricto para respetar el formato elegido.
                selector = ('bestaudio[ext=m4a]' if self.fmt == 'm4a'
                            else 'bestaudio[acodec^=opus]')
                base.update({
                    'format': selector,
                    'outtmpl': outtmpl,
                    'postprocessors': [],
                })
            elif self.fmt == 'mp3':
                if ffmpeg:
                    # Con ffmpeg: conversión real a MP3
                    base.update({
                        'format': 'bestaudio/best',
                        'outtmpl': outtmpl,
                        'ffmpeg_location': ffmpeg,
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': str(self.audio_quality)
                        }],
                    })
                else:
                    # Sin ffmpeg: se descarga el audio original (m4a, suena
                    # en cualquier reproductor) sin ningún post-procesado
                    base.update({
                        'format': 'bestaudio[ext=m4a]/bestaudio/best',
                        'outtmpl': outtmpl,
                    })
            else:
                h = {'1080': 1080, '720': 720, '480': 480}.get(self.quality)
                hf = f'[height<={h}]' if h else ''
                if ffmpeg:
                    # Con ffmpeg: video + audio por separado y se unen
                    base.update({
                        'format': f'bv*{hf}+ba/b{hf}/bv*+ba/b',
                        'outtmpl': outtmpl,
                        'ffmpeg_location': ffmpeg,
                        'merge_output_format': 'mp4',
                    })
                else:
                    # Sin ffmpeg: se prefiere un archivo único (video+audio).
                    # Se probaron varias opciones; la última es "lo mejor que haya".
                    base.update({
                        'format': f'b{hf}[ext=mp4]/b{hf}/b[ext=mp4]/b',
                        'outtmpl': outtmpl,
                    })

            run_with_auth_fallback(base, lambda ydl: ydl.download([self.url]))
            self.finished.emit(self.task_id, True, '')
        except Exception as e:
            if self._pause:
                self.finished.emit(self.task_id, False, PAUSED_MSG)
            else:
                self.finished.emit(self.task_id, False, clean_err(e))


# ─── Fila de playlist con checkbox ───────────────────────────────────────────
class PlaylistRow(QWidget):
    toggled = pyqtSignal()

    def __init__(self, index, title, duration, url, parent=None):
        super().__init__(parent)
        self.url        = url
        self.title_full = title
        self.setFixedHeight(38)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 16, 0)
        layout.setSpacing(10)

        self.chk = QCheckBox()
        self.chk.setChecked(True)
        self.chk.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 15px; height: 15px;
                border: 1px solid {C_BORDER};
                border-radius: 4px;
                background: {C_SURF2};
            }}
            QCheckBox::indicator:checked {{
                background: {C_ACCENT};
                border-color: {C_ACCENT};
            }}
            QCheckBox::indicator:unchecked:hover {{
                border-color: {C_ACCENT};
            }}
        """)
        self.chk.stateChanged.connect(self._on_toggle)

        num = QLabel(f"{index}")
        num.setFixedWidth(30)
        num.setFont(QFont("Consolas", 8))
        num.setStyleSheet(f"color: {C_MUTED};")
        num.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        short = title if len(title) <= 65 else title[:63] + "…"
        self.lbl = QLabel(short)
        self.lbl.setFont(QFont("Segoe UI", 9))
        self.lbl.setStyleSheet(f"color: {C_TEXT};")
        self.lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        dur_lbl = QLabel(self._fmt_dur(duration))
        dur_lbl.setFont(QFont("Consolas", 8))
        dur_lbl.setStyleSheet(f"color: {C_MUTED};")
        dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dur_lbl.setFixedWidth(46)

        layout.addWidget(self.chk)
        layout.addWidget(num)
        layout.addWidget(self.lbl, 1)
        layout.addWidget(dur_lbl)

    def _on_toggle(self):
        checked = self.chk.isChecked()
        self.lbl.setStyleSheet(f"color: {'#f0f0f8' if checked else C_MUTED};")
        self.toggled.emit()

    def is_checked(self):     return self.chk.isChecked()
    def set_checked(self, v): self.chk.setChecked(v)

    @staticmethod
    def _fmt_dur(secs):
        if not secs: return ''
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ─── Tarjeta de descarga ──────────────────────────────────────────────────────
class DownloadCard(QFrame):
    action_clicked = pyqtSignal(str)   # pausar / reanudar / reintentar

    def __init__(self, task_id, title, tag='', parent=None):
        super().__init__(parent)
        self.task_id = task_id
        if tag:
            title = f"[{tag}]  {title}"
        self.setStyleSheet(f"""
            QFrame {{
                background: {C_SURF2};
                border: 1px solid {C_BORDER};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(5)

        top = QHBoxLayout()
        self.lbl_title  = QLabel(title[:74] + ('…' if len(title) > 74 else ''))
        self.lbl_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.lbl_title.setStyleSheet(f"color: {C_TEXT}; background: transparent; border: none;")
        self.lbl_status = QLabel("En cola…")
        self.lbl_status.setFont(QFont("Consolas", 8))
        self.lbl_status.setStyleSheet(f"color: {C_MUTED}; background: transparent; border: none;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.lbl_title, 1)
        top.addWidget(self.lbl_status)
        lay.addLayout(top)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100); self.bar.setValue(0)
        self.bar.setTextVisible(False); self.bar.setFixedHeight(4)
        self.bar.setStyleSheet(f"""
            QProgressBar {{ background: {C_BORDER}; border-radius: 2px; border: none; }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {C_ACCENT}, stop:1 {C_ACCENT2});
                border-radius: 2px;
            }}
        """)
        lay.addWidget(self.bar)

        bot = QHBoxLayout()
        self.lbl_speed = QLabel("")
        self.lbl_speed.setFont(QFont("Consolas", 8))
        self.lbl_speed.setStyleSheet(f"color: {C_MUTED}; background: transparent; border: none;")
        self.lbl_pct = QLabel("0%")
        self.lbl_pct.setFont(QFont("Consolas", 8))
        self.lbl_pct.setStyleSheet(f"color: {C_MUTED}; background: transparent; border: none;")
        self.lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.btn_action = QPushButton("⏸  Pausar")
        self.btn_action.setFont(QFont("Segoe UI", 8))
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setFixedHeight(22)
        self.btn_action.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C_TEXT}; padding: 0 10px;
                           border: 1px solid {C_BORDER}; border-radius: 6px; }}
            QPushButton:hover {{ background: {C_SURF3}; border-color: {C_MUTED}; }}
            QPushButton:disabled {{ color: {C_MUTED}; }}
        """)
        self.btn_action.clicked.connect(lambda: self.action_clicked.emit(self.task_id))
        bot.addWidget(self.lbl_speed, 1)
        bot.addWidget(self.lbl_pct)
        bot.addWidget(self.btn_action)
        lay.addLayout(bot)

    def set_queued(self, position):
        self.lbl_status.setText(f"En cola #{position}")
        self.lbl_status.setStyleSheet(f"color: {C_MUTED}; background: transparent; border: none;")

    def set_running(self):
        self.btn_action.setText("⏸  Pausar"); self.btn_action.setEnabled(True)
        self.btn_action.show()

    def set_pausing(self):
        self.btn_action.setEnabled(False)
        self.lbl_status.setText("Pausando…")
        self.lbl_status.setStyleSheet(f"color: {C_GOLD}; background: transparent; border: none;")

    def set_paused(self):
        self.lbl_status.setText("⏸  En pausa")
        self.lbl_status.setStyleSheet(f"color: {C_GOLD}; background: transparent; border: none;")
        self.lbl_speed.setText("")
        self.btn_action.setText("▶  Reanudar"); self.btn_action.setEnabled(True)
        self.btn_action.show()

    def set_starting(self):
        self.lbl_status.setText("Iniciando…")
        self.lbl_status.setStyleSheet(f"color: {C_GOLD}; background: transparent; border: none;")

    def update_progress(self, pct, speed, status):
        self.bar.setValue(int(pct))
        self.lbl_pct.setText(f"{pct:.0f}%")
        self.lbl_speed.setText(speed)
        color = C_GOLD if status == 'downloading' else C_ACCENT2
        text  = "Descargando" if status == 'downloading' else "Procesando…"
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def set_done(self):
        self.btn_action.hide()
        self.bar.setValue(100); self.lbl_pct.setText("100%"); self.lbl_speed.setText("")
        self.lbl_status.setText("✓  Listo")
        self.lbl_status.setStyleSheet(f"color: {C_SUCCESS}; background: transparent; border: none;")
        self.bar.setStyleSheet(f"""
            QProgressBar {{ background: {C_BORDER}; border-radius: 2px; border: none; }}
            QProgressBar::chunk {{ background: {C_SUCCESS}; border-radius: 2px; }}
        """)

    def set_error(self, msg):
        self.btn_action.setText("↻  Reintentar"); self.btn_action.setEnabled(True)
        self.btn_action.show()
        self.lbl_status.setText("✗  Error")
        self.lbl_status.setStyleSheet(f"color: {C_ACCENT}; background: transparent; border: none;")
        self.lbl_speed.setText(msg[:70])
        self.lbl_speed.setStyleSheet(f"color: {C_ACCENT}; background: transparent; border: none;")


# ─── Ventana principal ────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YT Downloader")
        self.setMinimumSize(750, 560)
        self.resize(750, 720)
        self._set_icon()
        self._apply_palette()

        self.settings = QSettings("YTDownloader", "YTDownloader")
        saved_dir = self.settings.value("output_dir", DOWNLOAD_DIR, type=str)
        self.output_dir = saved_dir if os.path.isdir(saved_dir) else DOWNLOAD_DIR
        os.makedirs(self.output_dir, exist_ok=True)

        self.current_info     = None
        self.download_cards   = {}
        self.playlist_rows    = []
        self.selected_fmt     = self.settings.value("format", "mp4", type=str)
        if self.selected_fmt not in ('mp4', 'mp3', 'm4a', 'opus'):
            self.selected_fmt = 'mp4'
        self.selected_quality = self.settings.value("video_quality", "best", type=str)
        if self.selected_quality not in ('best', '1080', '720', '480'):
            self.selected_quality = 'best'
        self.audio_quality = self.settings.value("audio_quality", 192, type=int)
        if self.audio_quality not in (128, 192, 320):
            self.audio_quality = 192

        # ── Cola de descargas (throttled) ──────────────────────────────
        self._download_queue:   deque = deque()   # task_id en espera
        self._tasks:            dict  = {}        # task_id → {title,url,fmt,quality}
        self._stopped:          set   = set()     # task_id en pausa o con error
        self._seq               = 0
        self._active_threads:   dict  = {}        # task_id → DownloadThread
        self._finished_threads: list  = []        # threads terminados para liberar
        self._max_concurrent    = self.settings.value(
            "max_concurrent", DEFAULT_CONCURRENT, type=int)
        self._max_concurrent = max(1, min(MAX_CONCURRENT, self._max_concurrent))
        self.speed_limit = self.settings.value("speed_limit_kbps", 0, type=int)
        self.speed_limit = max(0, min(102400, self.speed_limit))
        self._closing           = False

        # Limpieza periódica de threads terminados (cada 5 s)
        self._gc_timer = QTimer(self)
        self._gc_timer.setInterval(5000)
        self._gc_timer.timeout.connect(self._gc_threads)
        self._gc_timer.start()

        # Un solo QNetworkAccessManager reutilizable para thumbnails
        self._net_mgr = QNetworkAccessManager(self)
        self._net_mgr.finished.connect(self._on_thumb)

        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet(f"background: {C_BG};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {C_BORDER}; border-radius: 3px; }}
        """)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setStyleSheet(f"background: {C_BG};")
        scroll.setWidget(inner)
        self.main_layout = QVBoxLayout(inner)
        self.main_layout.setContentsMargins(28, 24, 28, 24)
        self.main_layout.setSpacing(14)

        self._build_header()
        self._build_url_card()
        self._build_options_card()
        self._build_info_card()
        self._build_playlist_card()
        self._build_downloads_panel()
        self.main_layout.addStretch()

        # Si falta el motor JavaScript que YouTube exige, ofrecer instalarlo
        QTimer.singleShot(600, self._check_js_runtime)

    # ── Icono ──────────────────────────────────────────────────────────────
    def _set_icon(self):
        sz = 64
        img = QImage(sz, sz, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor("#0a0a0f"))); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, sz, sz, 14, 14)
        p.setBrush(QBrush(QColor(C_ACCENT)))
        p.drawEllipse(6, 6, sz-12, sz-12)
        p.setBrush(QBrush(QColor("white")))
        cx, cy, h = sz//2, sz//2, 13
        p.drawPolygon(QPolygon([QPoint(cx-h+3,cy-h), QPoint(cx-h+3,cy+h), QPoint(cx+h+3,cy)]))
        p.end()
        self.setWindowIcon(QIcon(QPixmap.fromImage(img)))

    def _apply_palette(self):
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window,     QColor(C_BG))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(C_TEXT))
        pal.setColor(QPalette.ColorRole.Base,       QColor(C_SURFACE))
        pal.setColor(QPalette.ColorRole.Text,       QColor(C_TEXT))
        self.setPalette(pal)

    # ── Encabezado ─────────────────────────────────────────────────────────
    def _build_header(self):
        row = QHBoxLayout(); row.setSpacing(14)
        sz = 44
        img = QImage(sz, sz, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor("#0a0a0f"))); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, sz, sz, 11, 11)
        p.setBrush(QBrush(QColor(C_ACCENT)))
        p.drawEllipse(5, 5, sz-10, sz-10)
        p.setBrush(QBrush(QColor("white")))
        cx, cy, h = sz//2, sz//2, 10
        p.drawPolygon(QPolygon([QPoint(cx-h+2,cy-h), QPoint(cx-h+2,cy+h), QPoint(cx+h+2,cy)]))
        p.end()
        logo = QLabel(); logo.setPixmap(QPixmap.fromImage(img)); logo.setFixedSize(sz, sz)
        row.addWidget(logo)
        col = QVBoxLayout(); col.setSpacing(2)
        t1 = QLabel("YT Downloader")
        t1.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        t1.setStyleSheet(f"color: {C_TEXT};")
        t2 = QLabel("// videos · audios · playlists completas")
        t2.setFont(QFont("Consolas", 9)); t2.setStyleSheet(f"color: {C_MUTED};")
        col.addWidget(t1); col.addWidget(t2)
        row.addLayout(col); row.addStretch()
        self.btn_update = self._btn_ghost(f"⟳  Actualizar  (v{ytdlp_version()})")
        self.btn_update.setFixedHeight(34)
        self.btn_update.setToolTip("Actualiza las dependencias del programa (yt-dlp y ffmpeg).\nSoluciona la mayoría de errores de YouTube.")
        self.btn_update.clicked.connect(self.update_ytdlp)
        row.addWidget(self.btn_update)
        self.main_layout.addLayout(row)

    # ── URL ────────────────────────────────────────────────────────────────
    def _build_url_card(self):
        card = self._card(); lay = card.layout()
        self._sec_lbl(lay, "URL DE YOUTUBE")
        row = QHBoxLayout(); row.setSpacing(10)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://youtube.com/watch?v=...  o  playlist...")
        self.url_input.setFont(QFont("Consolas", 9))
        self.url_input.setFixedHeight(40)
        self.url_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C_SURF2}; border: 1px solid {C_BORDER};
                border-radius: 9px; color: {C_TEXT}; padding: 0 14px;
            }}
            QLineEdit:focus {{ border-color: {C_ACCENT}; }}
        """)
        self.url_input.returnPressed.connect(self.fetch_info)
        row.addWidget(self.url_input)
        self.btn_fetch = self._btn_primary("Analizar")
        self.btn_fetch.setFixedSize(110, 40)
        self.btn_fetch.clicked.connect(self.fetch_info)
        row.addWidget(self.btn_fetch)
        lay.addLayout(row)
        self.lbl_error = QLabel("")
        self.lbl_error.setFont(QFont("Segoe UI", 8)); self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet(f"""
            color: #ff8080; background: rgba(230,61,61,0.12);
            border: 1px solid rgba(230,61,61,0.3); border-radius: 7px; padding: 6px 12px;
        """)
        self.lbl_error.hide(); lay.addWidget(self.lbl_error)
        self.main_layout.addWidget(card)

    # ── Formato + Calidad ──────────────────────────────────────────────────
    def _build_options_card(self):
        card = self._card(); lay = card.layout()
        self._sec_lbl(lay, "FORMATO  &  CALIDAD")
        inner = QHBoxLayout(); inner.setSpacing(20)

        # Formato
        fc = QVBoxLayout(); fc.setSpacing(7)
        fl = QLabel("Formato"); fl.setFont(QFont("Segoe UI", 8))
        fl.setStyleSheet(f"color: {C_MUTED};"); fc.addWidget(fl)
        fp = QHBoxLayout(); fp.setSpacing(7)
        self.btn_mp4 = self._pill("MP4", active=self.selected_fmt == 'mp4')
        self.btn_mp3 = self._pill("MP3", active=self.selected_fmt == 'mp3')
        self.btn_m4a = self._pill("M4A", active=self.selected_fmt == 'm4a')
        self.btn_opus = self._pill("Opus", active=self.selected_fmt == 'opus')
        self.btn_mp4.clicked.connect(lambda: self._select_fmt('mp4'))
        self.btn_mp3.clicked.connect(lambda: self._select_fmt('mp3'))
        self.btn_m4a.clicked.connect(lambda: self._select_fmt('m4a'))
        self.btn_opus.clicked.connect(lambda: self._select_fmt('opus'))
        fp.addWidget(self.btn_mp4); fp.addWidget(self.btn_mp3)
        fp.addWidget(self.btn_m4a); fp.addWidget(self.btn_opus); fp.addStretch()
        fc.addLayout(fp); inner.addLayout(fc)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {C_BORDER};"); inner.addWidget(sep)

        # Calidad
        self.qc = QVBoxLayout(); self.qc.setSpacing(7)
        ql = QLabel("Calidad de video"); ql.setFont(QFont("Segoe UI", 8))
        ql.setStyleSheet(f"color: {C_MUTED};"); self.qc.addWidget(ql)
        qp = QHBoxLayout(); qp.setSpacing(7)
        self.quality_pills = []
        for label, val in [("Mejor","best"),("1080p","1080"),("720p","720"),("480p","480")]:
            b = self._pill(label, active=(val == self.selected_quality), gold=True)
            b.setProperty("quality", val)
            b.clicked.connect(self._on_quality)
            self.quality_pills.append(b); qp.addWidget(b)
        qp.addStretch(); self.qc.addLayout(qp)
        inner.addLayout(self.qc)

        # ── Descargas simultáneas ──────────────────────────────────────
        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet(f"color: {C_BORDER};"); inner.addWidget(sep2)

        cc = QVBoxLayout(); cc.setSpacing(7)
        cl = QLabel("Descargas a la vez"); cl.setFont(QFont("Segoe UI", 8))
        cl.setStyleSheet(f"color: {C_MUTED};"); cc.addWidget(cl)
        self.spin_concurrent = QSpinBox()
        self.spin_concurrent.setRange(1, MAX_CONCURRENT)
        self.spin_concurrent.setValue(self._max_concurrent)
        self.spin_concurrent.setFixedWidth(60)
        self.spin_concurrent.setFixedHeight(30)
        self.spin_concurrent.setStyleSheet(f"""
            QSpinBox {{
                background: {C_SURF2}; border: 1px solid {C_BORDER};
                border-radius: 7px; color: {C_TEXT}; padding: 0 8px;
                font-family: Consolas; font-size: 10pt;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 18px; border: none; background: {C_SURF3};
            }}
        """)
        self.spin_concurrent.valueChanged.connect(self._on_concurrent_change)
        hint = QLabel("(1–5)")
        hint.setFont(QFont("Segoe UI", 7))
        hint.setStyleSheet(f"color: {C_MUTED};")
        cc.addWidget(self.spin_concurrent)
        cc.addWidget(hint)
        inner.addLayout(cc)

        # Preferencias adicionales persistentes
        prefs = QHBoxLayout(); prefs.setSpacing(14)

        folder_box = QVBoxLayout(); folder_box.setSpacing(5)
        folder_lbl = QLabel("Carpeta de destino"); folder_lbl.setFont(QFont("Segoe UI", 8))
        folder_lbl.setStyleSheet(f"color: {C_MUTED};")
        self.lbl_output_dir = QLabel(self.output_dir)
        self.lbl_output_dir.setFont(QFont("Segoe UI", 8))
        self.lbl_output_dir.setStyleSheet(f"color: {C_TEXT};")
        self.lbl_output_dir.setMaximumWidth(280)
        self.lbl_output_dir.setWordWrap(True)
        self.lbl_output_dir.setToolTip(self.output_dir)
        self.lbl_output_dir.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.btn_folder = self._btn_ghost("Cambiar carpeta")
        self.btn_folder.clicked.connect(self._choose_output_dir)
        folder_box.addWidget(folder_lbl)
        folder_box.addWidget(self.lbl_output_dir)
        folder_box.addWidget(self.btn_folder)
        prefs.addLayout(folder_box, 2)

        audio_box = QVBoxLayout(); audio_box.setSpacing(5)
        audio_lbl = QLabel("Calidad MP3"); audio_lbl.setFont(QFont("Segoe UI", 8))
        audio_lbl.setStyleSheet(f"color: {C_MUTED};")
        self.combo_audio_quality = QComboBox()
        self.combo_audio_quality.setFixedHeight(30)
        self.combo_audio_quality.setStyleSheet(f"""
            QComboBox {{ background: {C_SURF2}; border: 1px solid {C_BORDER};
                border-radius: 7px; color: {C_TEXT}; padding: 0 8px; }}
            QComboBox QAbstractItemView {{ background: {C_SURF2}; color: {C_TEXT};
                selection-background-color: {C_SURF3}; }}
        """)
        for bitrate in (128, 192, 320):
            self.combo_audio_quality.addItem(f"{bitrate} kbps", bitrate)
        audio_index = self.combo_audio_quality.findData(self.audio_quality)
        self.combo_audio_quality.setCurrentIndex(max(0, audio_index))
        self.combo_audio_quality.currentIndexChanged.connect(self._on_audio_quality)
        audio_hint = QLabel("Requiere ffmpeg")
        audio_hint.setFont(QFont("Segoe UI", 7)); audio_hint.setStyleSheet(f"color: {C_MUTED};")
        audio_box.addWidget(audio_lbl); audio_box.addWidget(self.combo_audio_quality)
        audio_box.addWidget(audio_hint)
        prefs.addLayout(audio_box)

        speed_box = QVBoxLayout(); speed_box.setSpacing(5)
        speed_lbl = QLabel("Límite de velocidad"); speed_lbl.setFont(QFont("Segoe UI", 8))
        speed_lbl.setStyleSheet(f"color: {C_MUTED};")
        self.spin_speed = QSpinBox()
        self.spin_speed.setRange(0, 102400)
        self.spin_speed.setValue(self.speed_limit)
        self.spin_speed.setSuffix(" KB/s")
        self.spin_speed.setFixedHeight(30)
        self.spin_speed.setStyleSheet(f"""
            QSpinBox {{ background: {C_SURF2}; border: 1px solid {C_BORDER};
                border-radius: 7px; color: {C_TEXT}; padding: 0 8px; }}
        """)
        self.spin_speed.setSpecialValueText("Sin límite")
        self.spin_speed.setToolTip("0 significa sin límite. El valor se aplica a cada descarga.")
        self.spin_speed.valueChanged.connect(self._on_speed_change)
        speed_hint = QLabel("0 = sin límite")
        speed_hint.setFont(QFont("Segoe UI", 7)); speed_hint.setStyleSheet(f"color: {C_MUTED};")
        speed_box.addWidget(speed_lbl); speed_box.addWidget(self.spin_speed); speed_box.addWidget(speed_hint)
        prefs.addLayout(speed_box)

        inner.addStretch()
        lay.addLayout(inner)
        lay.addLayout(prefs)
        self.main_layout.addWidget(card)
        self._select_fmt(self.selected_fmt)

    # ── Info video único ───────────────────────────────────────────────────
    def _build_info_card(self):
        self.info_card = self._card(); lay = self.info_card.layout()
        row = QHBoxLayout(); row.setSpacing(14)
        self.thumb_label = QLabel("🎬")
        self.thumb_label.setFixedSize(148, 84)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFont(QFont("Segoe UI", 22))
        self.thumb_label.setStyleSheet(f"background: {C_SURF2}; border-radius: 8px;")
        col = QVBoxLayout(); col.setSpacing(5)
        self.lbl_badge = QLabel("VIDEO")
        self.lbl_badge.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self.lbl_badge.setFixedHeight(20)
        self.lbl_badge.setStyleSheet(f"""
            color: #5b8aff; background: rgba(91,138,255,0.12);
            border: 1px solid rgba(91,138,255,0.3); border-radius: 4px; padding: 0 8px;
        """)
        self.lbl_vid_title = QLabel("")
        self.lbl_vid_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        self.lbl_vid_title.setStyleSheet(f"color: {C_TEXT};"); self.lbl_vid_title.setWordWrap(True)
        self.lbl_vid_meta = QLabel("")
        self.lbl_vid_meta.setFont(QFont("Consolas", 8))
        self.lbl_vid_meta.setStyleSheet(f"color: {C_MUTED};")
        col.addWidget(self.lbl_badge); col.addWidget(self.lbl_vid_title)
        col.addWidget(self.lbl_vid_meta); col.addStretch()
        row.addWidget(self.thumb_label); row.addLayout(col, 1); lay.addLayout(row)
        act = QHBoxLayout(); act.setSpacing(10)
        self.btn_dl_single = self._btn_primary("↓  Descargar")
        self.btn_dl_single.setFixedHeight(38)
        self.btn_dl_single.clicked.connect(self.start_download)
        self.btn_clear = self._btn_ghost("Limpiar")
        self.btn_clear.setFixedHeight(38); self.btn_clear.clicked.connect(self.reset)
        act.addWidget(self.btn_dl_single); act.addWidget(self.btn_clear); act.addStretch()
        lay.addLayout(act)
        self.info_card.hide(); self.main_layout.addWidget(self.info_card)

    # ── Panel playlist ─────────────────────────────────────────────────────
    def _build_playlist_card(self):
        self.pl_card = self._card(); lay = self.pl_card.layout()

        head = QHBoxLayout()
        self.lbl_pl_title = QLabel("Playlist")
        self.lbl_pl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        self.lbl_pl_title.setStyleSheet(f"color: {C_TEXT};")
        self.lbl_pl_count = QLabel("")
        self.lbl_pl_count.setFont(QFont("Consolas", 8))
        self.lbl_pl_count.setStyleSheet(f"color: {C_MUTED};")
        head.addWidget(self.lbl_pl_title, 1); head.addWidget(self.lbl_pl_count)
        lay.addLayout(head)

        sel_bar = QHBoxLayout(); sel_bar.setSpacing(8)
        self.btn_sel_all    = self._btn_sel("☑  Todos")
        self.btn_sel_none   = self._btn_sel("☐  Ninguno")
        self.btn_sel_invert = self._btn_sel("⇌  Invertir")
        self.btn_sel_all.clicked.connect(lambda: self._set_all(True))
        self.btn_sel_none.clicked.connect(lambda: self._set_all(False))
        self.btn_sel_invert.clicked.connect(self._invert)
        self.lbl_sel_count = QLabel("0 seleccionados")
        self.lbl_sel_count.setFont(QFont("Consolas", 8))
        self.lbl_sel_count.setStyleSheet(f"color: {C_GOLD};")
        self.lbl_sel_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sel_bar.addWidget(self.btn_sel_all); sel_bar.addWidget(self.btn_sel_none)
        sel_bar.addWidget(self.btn_sel_invert); sel_bar.addStretch()
        sel_bar.addWidget(self.lbl_sel_count)
        lay.addLayout(sel_bar)

        self.pl_scroll = QScrollArea()
        self.pl_scroll.setFixedHeight(280)
        self.pl_scroll.setWidgetResizable(True)
        self.pl_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {C_BORDER}; border-radius: 8px; background: {C_SURF2};
            }}
            QScrollBar:vertical {{ width: 5px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {C_BORDER}; border-radius: 2px; }}
        """)
        self.pl_inner = QWidget()
        self.pl_inner.setStyleSheet(f"background: {C_SURF2};")
        self.pl_rows_layout = QVBoxLayout(self.pl_inner)
        self.pl_rows_layout.setContentsMargins(0, 4, 0, 4)
        self.pl_rows_layout.setSpacing(0)
        self.pl_rows_layout.addStretch()
        self.pl_scroll.setWidget(self.pl_inner)
        lay.addWidget(self.pl_scroll)

        act = QHBoxLayout(); act.setSpacing(10)
        self.btn_dl_pl = self._btn_primary("↓  Descargar seleccionados")
        self.btn_dl_pl.setFixedHeight(40)
        self.btn_dl_pl.clicked.connect(self.start_download)
        btn_clear_pl = self._btn_ghost("Limpiar")
        btn_clear_pl.setFixedHeight(40); btn_clear_pl.clicked.connect(self.reset)
        act.addWidget(self.btn_dl_pl); act.addWidget(btn_clear_pl); act.addStretch()
        lay.addLayout(act)

        self.pl_card.hide(); self.main_layout.addWidget(self.pl_card)

    # ── Panel descargas ─────────────────────────────────────────────────────
    def _build_downloads_panel(self):
        self.dl_panel = self._card(); lay = self.dl_panel.layout()

        dl_head = QHBoxLayout()
        self._sec_lbl_widget = QLabel("DESCARGAS")
        self._sec_lbl_widget.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        self._sec_lbl_widget.setStyleSheet(
            f"color: {C_MUTED}; letter-spacing: 2px; border: none; background: transparent;"
        )
        self.lbl_queue_info = QLabel("")
        self.lbl_queue_info.setFont(QFont("Consolas", 8))
        self.lbl_queue_info.setStyleSheet(f"color: {C_GOLD}; background: transparent; border: none;")
        self.lbl_queue_info.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dl_head.addWidget(self._sec_lbl_widget, 1)
        dl_head.addWidget(self.lbl_queue_info)
        lay.addLayout(dl_head)

        self.dl_list_layout = QVBoxLayout(); self.dl_list_layout.setSpacing(8)
        lay.addLayout(self.dl_list_layout)
        btn_f = self._btn_ghost("📁  Abrir carpeta de descargas")
        btn_f.setFixedHeight(36); btn_f.clicked.connect(self.open_folder)
        lay.addWidget(btn_f)
        self.dl_panel.hide(); self.main_layout.addWidget(self.dl_panel)

    # ─── Actualizar yt-dlp ───────────────────────────────────────────────
    def update_ytdlp(self):
        self.btn_update.setEnabled(False)
        self.btn_update.setText("Actualizando…")
        self._upd = UpdateThread()
        self._upd.done.connect(self._on_update_done)
        self._upd.start()

    def _on_update_done(self, ok, msg, restart):
        self.btn_update.setEnabled(True)
        self.btn_update.setText(f"⟳  Actualizar  (v{ytdlp_version()})")
        if not ok:
            QMessageBox.warning(self, "Actualización", "No se pudo actualizar:\n\n" + msg)
            return
        if not restart:
            QMessageBox.information(self, "Actualización", msg)
            return
        r = QMessageBox.question(
            self, "Actualización",
            msg + "\n\nPara aplicar los cambios hay que reiniciar la app. ¿Reiniciar ahora?")
        if r == QMessageBox.StandardButton.Yes:
            env = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
            args = ([sys.executable] + sys.argv[1:]) if getattr(sys, 'frozen', False) \
                   else ([sys.executable] + sys.argv)
            subprocess.Popen(args, env=env)
            self.close()
            QApplication.quit()

    # ─── Lógica de fetch ──────────────────────────────────────────────────

    def fetch_info(self):
        url = self.url_input.text().strip()
        if not url: return
        self.lbl_error.hide()
        self._clear_result()
        self.btn_fetch.setEnabled(False); self.btn_fetch.setText("…")
        self.fetch_thread = FetchThread(url)
        self.fetch_thread.result.connect(self._on_fetch_ok)
        self.fetch_thread.error.connect(self._on_fetch_err)
        self.fetch_thread.start()

    def _on_fetch_ok(self, data):
        self.btn_fetch.setEnabled(True); self.btn_fetch.setText("Analizar")
        self.current_info = data
        if data['type'] == 'playlist':
            self._render_playlist(data)
            self.info_card.hide(); self.pl_card.show()
        else:
            self._render_video(data)
            self.pl_card.hide(); self.info_card.show()

    def _clear_result(self):
        """Oculta el resultado anterior para no descargar un video equivocado."""
        self.current_info = None
        self.info_card.hide(); self.pl_card.hide()

    def _on_fetch_err(self, msg):
        self.btn_fetch.setEnabled(True); self.btn_fetch.setText("Analizar")
        self._clear_result()
        self.lbl_error.setText("Error: " + msg); self.lbl_error.show()

    def _check_js_runtime(self):
        """Al abrir: si falta el motor JavaScript, ofrece instalarlo."""
        if find_js_runtimes():
            return
        r = QMessageBox.question(
            self, "Falta un componente",
            "YouTube ahora exige un motor JavaScript (Deno) y sin él muchos "
            "videos fallan con «This video is not available».\n\n"
            "¿Descargarlo e instalarlo ahora? (≈ 43 MB, se hace una sola vez)")
        if r == QMessageBox.StandardButton.Yes:
            self.update_ytdlp()

    def _render_video(self, data):
        self.lbl_badge.setText("▶  VIDEO")
        self.lbl_badge.setStyleSheet(f"""
            color: #5b8aff; background: rgba(91,138,255,0.12);
            border: 1px solid rgba(91,138,255,0.3); border-radius: 4px; padding: 0 8px;
        """)
        self.thumb_label.setText("🎬"); self.thumb_label.setPixmap(QPixmap())
        self.lbl_vid_title.setText(data['title'])
        v = data.get('views', 0)
        vs = f"{v/1e6:.1f}M vistas" if v>1e6 else (f"{v/1e3:.0f}K vistas" if v>1e3 else f"{v} vistas")
        self.lbl_vid_meta.setText(
            f"{data.get('channel','')}   ·   {self._fmt_dur(data.get('duration',0))}   ·   {vs}"
        )
        if data.get('thumbnail'):
            self._load_thumb(data['thumbnail'])

    def _render_playlist(self, data):
        self.playlist_rows.clear()
        while self.pl_rows_layout.count() > 1:
            item = self.pl_rows_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        self.lbl_pl_title.setText(data['title'])
        shown = len(data['items'])
        suffix = f" · mostrando {shown} primeros" if data['count'] > shown else ""
        self.lbl_pl_count.setText(f"{data['count']} videos{suffix}")

        for i, item in enumerate(data['items']):
            row_w = PlaylistRow(i+1, item['title'], item.get('duration', 0), item['url'])
            row_w.toggled.connect(self._update_sel_count)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background: {C_BORDER}; border: none;")

            wrap = QWidget(); wrap.setStyleSheet("background: transparent;")
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(0,0,0,0); wl.setSpacing(0)
            wl.addWidget(row_w); wl.addWidget(sep)

            self.pl_rows_layout.insertWidget(self.pl_rows_layout.count()-1, wrap)
            self.playlist_rows.append(row_w)

        self._update_sel_count()

    def _update_sel_count(self):
        n     = sum(1 for r in self.playlist_rows if r.is_checked())
        total = len(self.playlist_rows)
        self.lbl_sel_count.setText(f"{n} / {total} seleccionados")
        self.btn_dl_pl.setEnabled(n > 0)
        self.btn_dl_pl.setText(
            f"↓  Descargar {n} seleccionado{'s' if n!=1 else ''}" if n > 0
            else "↓  Descargar seleccionados"
        )

    def _set_all(self, value: bool):
        for r in self.playlist_rows: r.set_checked(value)
        self._update_sel_count()

    def _invert(self):
        for r in self.playlist_rows: r.set_checked(not r.is_checked())
        self._update_sel_count()

    # ─── Cola de descargas throttled ──────────────────────────────────────

    def _on_concurrent_change(self, value):
        self._max_concurrent = value
        self.settings.setValue("max_concurrent", value)
        self._pump_queue()  # Puede haber slots libres si se sube el límite

    def _on_speed_change(self, value):
        self.speed_limit = value
        self.settings.setValue("speed_limit_kbps", value)

    def _on_audio_quality(self, _index):
        self.audio_quality = int(self.combo_audio_quality.currentData())
        self.settings.setValue("audio_quality", self.audio_quality)

    def _choose_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Elegir carpeta de descarga", self.output_dir)
        if not folder:
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "Carpeta no disponible", str(e))
            return
        self.output_dir = folder
        self.settings.setValue("output_dir", folder)
        self.lbl_output_dir.setText(folder)
        self.lbl_output_dir.setToolTip(folder)

    def start_download(self):
        if not self.current_info: return
        url = self.url_input.text().strip()
        if self.current_info['type'] == 'playlist':
            items = [(r.title_full, r.url) for r in self.playlist_rows if r.is_checked()]
        else:
            # Usa la URL que se ANALIZÓ, no lo que haya en la caja ahora mismo
            items = [(self.current_info['title'], self.current_info.get('url') or url)]
        if not items: return

        fmt = self.selected_fmt
        q = str(self.audio_quality) if fmt == 'mp3' else self.selected_quality
        if fmt == 'mp3':
            tag = 'MP3' if find_ffmpeg() else 'AUDIO ORIGINAL'
        elif fmt in ('m4a', 'opus'):
            tag = fmt.upper()
        else:
            tag = 'MP4' + ('' if q == 'best' else f' {q}p')

        self.dl_panel.show()
        for title, u in items:
            # Solo se ignora si ESTA misma descarga (mismo video + formato +
            # calidad) sigue activa, en cola o pausada. Una ya terminada, o el
            # mismo video en otro formato (ej. MP4 y luego MP3), sí se permite.
            busy = any(
                t['url'] == u and t['fmt'] == fmt and t['quality'] == q
                and (tid in self._active_threads or tid in self._download_queue
                     or tid in self._stopped)
                for tid, t in self._tasks.items()
            )
            if busy:
                continue
            self._seq += 1
            task_id = f"{re.sub(r'[^a-zA-Z0-9]', '_', u)[:30]}_{fmt}_{q}_{self._seq}"
            self._tasks[task_id] = {
                'title': title, 'url': u, 'fmt': fmt, 'quality': q,
                'video_quality': self.selected_quality,
                'audio_quality': self.audio_quality,
                'output_dir': self.output_dir,
                'speed_limit': self.speed_limit,
            }
            card = DownloadCard(task_id, title, tag)
            card.action_clicked.connect(self.toggle_task)
            self.download_cards[task_id] = card
            self.dl_list_layout.insertWidget(0, card)
            self._download_queue.append(task_id)

        self._pump_queue()
        self._update_queue_label()

    def toggle_task(self, task_id):
        """Botón de la tarjeta: pausar (si descarga o espera) o reanudar/reintentar."""
        card = self.download_cards.get(task_id)
        if not card: return
        if task_id in self._active_threads:
            self._active_threads[task_id].request_pause()
            card.set_pausing()
        elif task_id in self._download_queue:
            self._download_queue.remove(task_id)
            self._stopped.add(task_id)
            card.set_paused()
            self._update_queue_label()
        elif task_id in self._stopped:
            self._stopped.discard(task_id)
            card.set_running()
            self._download_queue.appendleft(task_id)
            self._pump_queue()

    def _pump_queue(self):
        """Lanza descargas hasta llenar los slots disponibles."""
        if self._closing:
            return
        while self._download_queue and len(self._active_threads) < self._max_concurrent:
            task_id = self._download_queue.popleft()
            task = self._tasks[task_id]
            card = self.download_cards.get(task_id)
            if card:
                card.set_running()
                card.set_starting()
            t = DownloadThread(
                task_id, task['url'], task['fmt'], task['video_quality'],
                task['output_dir'], task['audio_quality'], task['speed_limit'])
            t.progress.connect(self._on_dl_progress)
            t.finished.connect(self._on_dl_finished)
            t.start()
            self._active_threads[task_id] = t
        self._update_queue_label()

    def _update_queue_label(self):
        active = len(self._active_threads)
        queued = len(self._download_queue)
        if active == 0 and queued == 0:
            self.lbl_queue_info.setText("")
            return
        parts = []
        if active:  parts.append(f"{active} activa{'s' if active!=1 else ''}")
        if queued:  parts.append(f"{queued} en cola")
        self.lbl_queue_info.setText("  ·  ".join(parts))
        # Actualizar etiqueta de posición en cola
        for i, tid in enumerate(self._download_queue):
            c = self.download_cards.get(tid)
            if c: c.set_queued(i + 1)

    def _on_dl_progress(self, task_id, pct, speed, status):
        card = self.download_cards.get(task_id)
        if card: card.update_progress(pct, speed, status)

    def _on_dl_finished(self, task_id, ok, msg):
        card = self.download_cards.get(task_id)
        if card:
            if ok:
                card.set_done()
            elif msg == PAUSED_MSG:
                self._stopped.add(task_id); card.set_paused()
            else:
                self._stopped.add(task_id); card.set_error(msg)
        # Mover el thread a la lista de limpieza
        t = self._active_threads.pop(task_id, None)
        if t:
            self._finished_threads.append(t)
        # Lanzar siguiente en cola
        self._pump_queue()

    def closeEvent(self, event):
        self._closing = True
        threads = list(self._active_threads.values())
        for t in threads: t.request_pause()
        # No destruir la ventana mientras un QThread sigue usando la aplicación.
        for t in threads:
            while not t.wait(100):
                QApplication.processEvents()
        event.accept()

    def _gc_threads(self):
        """Libera threads que ya terminaron para no acumularlos en memoria."""
        still_alive = []
        for t in self._finished_threads:
            if t.isFinished():
                t.deleteLater()
            else:
                still_alive.append(t)
        self._finished_threads = still_alive

    # ─── Resto de lógica ──────────────────────────────────────────────────

    def reset(self):
        self.url_input.clear()
        self.info_card.hide(); self.pl_card.hide(); self.lbl_error.hide()
        self.current_info = None; self.playlist_rows.clear()
        self.thumb_label.setText("🎬"); self.thumb_label.setPixmap(QPixmap())

    def open_folder(self):
        folder = os.path.abspath(self.output_dir)
        try:
            os.makedirs(folder, exist_ok=True)
            sn = platform.system()
            if sn == 'Windows':
                os.startfile(folder)
            elif sn == 'Darwin':
                subprocess.Popen(['open', folder])
            else:
                subprocess.Popen(['xdg-open', folder])
        except (OSError, AttributeError) as e:
            QMessageBox.warning(self, "No se pudo abrir la carpeta", f"{folder}\n\n{e}")

    def _load_thumb(self, url):
        """Un solo net_mgr reutilizable — sin memory leaks."""
        self._net_mgr.get(QNetworkRequest(QUrl(url)))

    def _on_thumb(self, reply):
        pix = QPixmap(); pix.loadFromData(bytes(reply.readAll()))
        if not pix.isNull():
            pix = pix.scaled(148, 84, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
            self.thumb_label.setPixmap(pix); self.thumb_label.setText("")
        reply.deleteLater()

    def _select_fmt(self, fmt):
        self.selected_fmt = fmt
        self.settings.setValue("format", fmt)
        self.btn_mp4.setStyleSheet(self._pill_ss(fmt=='mp4', gold=False))
        self.btn_mp3.setStyleSheet(self._pill_ss(fmt=='mp3', gold=False))
        self.btn_m4a.setStyleSheet(self._pill_ss(fmt=='m4a', gold=False))
        self.btn_opus.setStyleSheet(self._pill_ss(fmt=='opus', gold=False))
        self.combo_audio_quality.setEnabled(fmt == 'mp3' and find_ffmpeg() is not None)
        if fmt == 'mp3' and find_ffmpeg() is None:
            self.combo_audio_quality.setToolTip("Instala ffmpeg para convertir y elegir bitrate MP3.")
        else:
            self.combo_audio_quality.setToolTip("Bitrate de conversión MP3.")
        show = (fmt == 'mp4')
        for i in range(self.qc.count()):
            item = self.qc.itemAt(i)
            if item.widget(): item.widget().setVisible(show)
            elif item.layout():
                for j in range(item.layout().count()):
                    wi = item.layout().itemAt(j)
                    if wi and wi.widget(): wi.widget().setVisible(show)

    def _on_quality(self):
        self.selected_quality = self.sender().property("quality")
        self.settings.setValue("video_quality", self.selected_quality)
        for p in self.quality_pills:
            p.setStyleSheet(self._pill_ss(p == self.sender(), gold=True))

    # ─── Helpers UI ───────────────────────────────────────────────────────

    def _card(self):
        f = QFrame()
        f.setStyleSheet(f"""
            QFrame {{
                background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 14px;
            }}
        """)
        l = QVBoxLayout(f); l.setContentsMargins(20,16,20,16); l.setSpacing(12)
        return f

    def _sec_lbl(self, layout, text):
        l = QLabel(text)
        l.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        l.setStyleSheet(f"color: {C_MUTED}; letter-spacing: 2px; border: none; background: transparent;")
        layout.addWidget(l)

    def _pill_ss(self, active, gold=False):
        if active:
            c = C_GOLD if gold else C_ACCENT
            t = "#111" if gold else "white"
            return f"""
                QPushButton {{
                    background:{c}; color:{t}; border:1px solid {c};
                    border-radius:7px; padding:5px 14px;
                    font-family:Consolas; font-size:8pt; font-weight:bold;
                }}
            """
        return f"""
            QPushButton {{
                background:{C_SURF2}; color:{C_MUTED}; border:1px solid {C_BORDER};
                border-radius:7px; padding:5px 14px;
                font-family:Consolas; font-size:8pt; font-weight:bold;
            }}
            QPushButton:hover {{ border-color:{C_MUTED}; color:{C_TEXT}; }}
        """

    def _pill(self, text, active=False, gold=False):
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(self._pill_ss(active, gold))
        return b

    def _btn_primary(self, text):
        b = QPushButton(text)
        b.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"""
            QPushButton {{
                background:{C_ACCENT}; color:white; border:none;
                border-radius:9px; padding:0 20px;
            }}
            QPushButton:hover {{ background:#c42929; }}
            QPushButton:pressed {{ background:#a82020; }}
            QPushButton:disabled {{ background:{C_BORDER}; color:{C_MUTED}; }}
        """)
        return b

    def _btn_ghost(self, text):
        b = QPushButton(text)
        b.setFont(QFont("Segoe UI", 9))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{C_TEXT};
                border:1px solid {C_BORDER}; border-radius:9px; padding:0 20px;
            }}
            QPushButton:hover {{ background:{C_SURF2}; border-color:{C_MUTED}; }}
        """)
        return b

    def _btn_sel(self, text):
        b = QPushButton(text)
        b.setFont(QFont("Segoe UI", 8))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(28)
        b.setStyleSheet(f"""
            QPushButton {{
                background:{C_SURF2}; color:{C_TEXT};
                border:1px solid {C_BORDER}; border-radius:6px; padding:0 12px;
            }}
            QPushButton:hover {{ background:{C_SURF3}; border-color:{C_MUTED}; }}
            QPushButton:pressed {{ background:{C_BORDER}; }}
        """)
        return b

    @staticmethod
    def _fmt_dur(secs):
        if not secs: return ''
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
