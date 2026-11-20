"""Hilos de trabajo para actualizar, analizar y descargar."""
import os
import platform
import subprocess
import sys

from PyQt6.QtCore import QThread, pyqtSignal

from .appupdate import (
    UpdateCancelled,
    check_for_update,
    cleanup_update_files,
    download_update,
)
from .config import LOCK_RETRIES, LOCK_RETRY_DELAY
from .errors import (
    PAUSED_MSG,
    PauseRequested,
    clean_err,
    is_file_lock_error,
    is_http_416_error,
)
from .runtime import find_ffmpeg, get_cookie_option
from .services import (
    _pkg_version,
    ensure_js_runtime,
    portable_update_ytdlp,
    run_with_auth_fallback,
)

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

class AppUpdateCheckThread(QThread):
    """Consulta en GitHub si hay una versión nueva de la aplicación."""
    done = pyqtSignal(object, str)   # info (dict) | None, error

    def run(self):
        try:
            cleanup_update_files()
            self.done.emit(check_for_update(), '')
        except Exception as e:
            self.done.emit(None, clean_err(e))

class AppDownloadThread(QThread):
    """Descarga y verifica el instalador / .exe de la versión nueva."""
    progress = pyqtSignal(int, int)   # descargado, total (bytes)
    done = pyqtSignal(bool, str)      # ok, ruta del archivo | mensaje de error

    def __init__(self, asset):
        super().__init__()
        self.asset = asset
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            path = download_update(
                self.asset,
                progress=lambda d, t: self.progress.emit(d, t),
                cancelled=lambda: self._cancel)
            self.done.emit(True, path)
        except UpdateCancelled:
            self.done.emit(False, '')
        except Exception as e:
            self.done.emit(False, clean_err(e))

class FetchThread(QThread):
    result = pyqtSignal(dict)
    error  = pyqtSignal(str)

    def __init__(self, url, allow_browser_cookies=False):
        super().__init__()
        self.url = url
        self.allow_browser_cookies = allow_browser_cookies

    def run(self):
        try:
            opts = {
                'quiet': True, 'no_warnings': True, 'no_color': True,
                'extract_flat': 'in_playlist',
                **get_cookie_option(),
            }
            info = run_with_auth_fallback(
                opts, lambda ydl: ydl.extract_info(self.url, download=False),
                allow_browser_cookies=self.allow_browser_cookies)

            if info.get('_type') == 'playlist':
                # Se descartan entradas vacías y videos privados/eliminados (sin
                # URL ni ID utilizable); yt-dlp los devuelve con título "[Private video]".
                entries = [
                    e for e in (info.get('entries') or [])
                    if e and (e.get('url') or e.get('id'))
                    and (e.get('title') or '') not in ('[Private video]', '[Deleted video]')
                ]
                self.result.emit({
                    'type': 'playlist',
                    'title': info.get('title') or 'Playlist',
                    'count': len(entries),
                    'items': [
                        {
                            'title':    e.get('title') or 'Sin título',
                            'url':      e.get('url') or f"https://youtube.com/watch?v={e.get('id')}",
                            'duration': e.get('duration') or 0,
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
                    # Las claves pueden existir con valor None (directos, vistas
                    # ocultas): "or" evita TypeError al formatearlas en la interfaz.
                    'title':     info.get('title') or 'Sin título',
                    'duration':  info.get('duration') or 0,
                    'thumbnail': info.get('thumbnail') or '',
                    'channel':   info.get('uploader') or '',
                    'views':     info.get('view_count') or 0,
                    'qualities': [str(h) for h in heights[:5]],
                })
        except Exception as e:
            self.error.emit(clean_err(e))

class DownloadThread(QThread):
    progress = pyqtSignal(str, float, str, str)
    # No se llama "finished" para no tapar la señal nativa QThread.finished.
    task_finished = pyqtSignal(str, bool, str)

    def __init__(self, task_id, url, fmt, quality, output_dir, audio_quality, speed_limit,
                 use_ffmpeg=True, allow_browser_cookies=False):
        super().__init__()
        self.task_id = task_id
        self.url     = url
        self.fmt     = fmt
        self.quality = quality
        self.output_dir = output_dir
        self.audio_quality = audio_quality
        self.speed_limit = speed_limit
        self.use_ffmpeg = use_ffmpeg
        self.allow_browser_cookies = allow_browser_cookies
        self._pause  = False
        self._streams_done = 0     # archivos (video, audio...) ya descargados por completo
        self._streams_total = 1    # archivos que bajará yt-dlp para esta tarea

    def request_pause(self):
        """Pausa = detener la descarga conservando el archivo .part.
        Al reanudar, yt-dlp continúa desde donde quedó."""
        self._pause = True

    def _hook(self, d):
        if self._pause:
            raise PauseRequested()
        n = self._streams_total
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            dl    = d.get('downloaded_bytes') or 0
            speed = d.get('speed') or 0
            frac  = min(dl / total, 1.0) if total else 0
            # Progreso global: cada archivo ocupa 1/n de la barra, así no retrocede
            # cuando termina el video y empieza el audio. El total estimado puede
            # quedarse corto; el 100% se reserva para cuando yt-dlp confirme el final.
            pct = min((self._streams_done + frac) / n * 100, 99)
            self.progress.emit(self.task_id, pct, self._fmt_speed(speed), 'downloading')
        elif d['status'] == 'finished':
            self._streams_done += 1
            if self._streams_done >= n:
                self.progress.emit(self.task_id, 100, '', 'processing')

    def _run_download(self, ydl):
        # Cada intento (clientes alternos, cookies...) empieza de cero.
        self._streams_done = 0
        self._streams_total = 1
        # Dentro del hook yt-dlp ya quitó 'requested_formats' de la info de cada
        # stream, así que el total de archivos (video + audio = 2) se obtiene con un
        # postprocesador "before_dl", que sí recibe la información completa.
        from yt_dlp.postprocessor.common import PostProcessor
        thread = self

        class _CountStreams(PostProcessor):
            def run(self, information):
                thread._streams_total = max(
                    1, len(information.get('requested_formats') or []))
                return [], information

        ydl.add_post_processor(_CountStreams(ydl), when='before_dl')
        return ydl.download([self.url])

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
            # Renombrados internos de yt-dlp (.part → final): más intentos y con espera
            base['file_access_retries'] = 10
            # Cortes de red: más reintentos, esperando entre ellos (por defecto yt-dlp
            # reintenta 10 veces SIN pausa y se rinde en segundos)
            base['socket_timeout'] = 30
            base['retries'] = 15
            base['fragment_retries'] = 15
            _wait = lambda n: min(2 * (n + 1), 10)
            base['retry_sleep_functions'] = {'file_access': _wait,
                                             'http': _wait, 'fragment': _wait}
            if self.speed_limit > 0:
                base['ratelimit'] = self.speed_limit * 1024
            ffmpeg = find_ffmpeg() if self.use_ffmpeg else None
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

            fresh_retry_used = False
            lock_retries = 0
            while True:
                try:
                    run_with_auth_fallback(
                        base, self._run_download,
                        allow_browser_cookies=self.allow_browser_cookies)
                    break
                except Exception as e:
                    if (not self._pause and not fresh_retry_used
                            and is_http_416_error(e)):
                        # El enlace o el .part guardado ya no coincide. yt-dlp
                        # volverá a extraer la URL y sobrescribirá el parcial desde cero.
                        base['continuedl'] = False
                        fresh_retry_used = True
                        continue
                    if (self._pause or lock_retries >= LOCK_RETRIES
                            or not is_file_lock_error(e)):
                        raise
                    lock_retries += 1
                    # Archivo bloqueado: espera y reintenta. Lo ya descargado se
                    # conserva, así que el reintento solo repite el último paso.
                    self.progress.emit(self.task_id, 100, '', 'processing')
                    for _ in range(int(LOCK_RETRY_DELAY * lock_retries * 10)):
                        if self._pause:
                            raise
                        self.msleep(100)
            self.task_finished.emit(self.task_id, True, '')
        except Exception as e:
            if self._pause:
                self.task_finished.emit(self.task_id, False, PAUSED_MSG)
            else:
                self.task_finished.emit(self.task_id, False, clean_err(e))
