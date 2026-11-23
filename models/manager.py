"""Cola de descargas: estado de cada tarea y control de los hilos, sin interfaz.

La ventana solo crea tarjetas y reacciona a las señales; aquí vive todo lo demás
(cola, límite de descargas simultáneas, pausa, reintento y quitar de la lista).
"""
import os
import re
from collections import deque
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal

from .config import DEFAULT_CONCURRENT, MAX_CONCURRENT
from .downloads import download_name_key
from .errors import PAUSED_MSG
from .runtime import kill_child_processes
from .workers import DownloadThread


class TaskState(Enum):
    QUEUED = 'queued'        # en cola, esperando un hueco
    RUNNING = 'running'      # descargando (hilo activo)
    PAUSING = 'pausing'      # se pidió pausa; el hilo aún no se detuvo
    REMOVING = 'removing'    # se pidió quitar; se quitará al detenerse el hilo
    PAUSED = 'paused'
    ERROR = 'error'
    DONE = 'done'


# Estados con un hilo vivo.
_LIVE = (TaskState.RUNNING, TaskState.PAUSING, TaskState.REMOVING)


@dataclass
class DownloadTask:
    id: str
    title: str
    url: str
    fmt: str
    quality: str             # bitrate (MP3) o calidad de video, según el formato
    video_quality: str
    audio_quality: int
    output_dir: str
    speed_limit: int
    use_ffmpeg: bool
    embed_meta: bool = True   # incrustar carátula y metadatos (solo MP3 con ffmpeg)
    state: TaskState = TaskState.QUEUED

    @property
    def media_kind(self):
        return 'video' if self.fmt == 'mp4' else 'audio'


def _make_thread(task, allow_browser_cookies):
    return DownloadThread(
        task.id, task.url, task.fmt, task.video_quality, task.output_dir,
        task.audio_quality, task.speed_limit, task.use_ffmpeg,
        allow_browser_cookies=allow_browser_cookies, embed_meta=task.embed_meta)


class DownloadManager(QObject):
    progress = pyqtSignal(str, float, str, str)   # id, %, velocidad, estado
    state_changed = pyqtSignal(str, object, str)  # id, TaskState, mensaje (errores)
    task_removed = pyqtSignal(str)                # id (la tarjeta debe desaparecer)
    queue_changed = pyqtSignal()                  # cambió la cola o los activos

    def __init__(self, max_concurrent=DEFAULT_CONCURRENT, parent=None,
                 cookies_allowed=lambda: False, thread_factory=_make_thread):
        super().__init__(parent)
        self.tasks = {}                    # id → DownloadTask (en orden de creación)
        self.closing = False
        self._queue = deque()              # ids en espera
        self._threads = {}                 # id → hilo activo
        self._finished_threads = []        # hilos terminados pendientes de liberar
        self._seq = 0
        self._max_concurrent = self._clamp(max_concurrent)
        self._cookies_allowed = cookies_allowed
        self._thread_factory = thread_factory

        # Limpieza periódica de hilos terminados
        self._gc_timer = QTimer(self)
        self._gc_timer.setInterval(5000)
        self._gc_timer.timeout.connect(self.collect_threads)
        self._gc_timer.start()

    # ── Consulta ─────────────────────────────────────────────────────────

    @staticmethod
    def _clamp(value):
        return max(1, min(MAX_CONCURRENT, int(value)))

    @property
    def max_concurrent(self):
        return self._max_concurrent

    @max_concurrent.setter
    def max_concurrent(self, value):
        self._max_concurrent = self._clamp(value)
        self.pump()          # puede haber huecos libres si se subió el límite

    @property
    def active_count(self):
        return len(self._threads)

    def queued_ids(self):
        return list(self._queue)

    def has_pending(self):
        """True si hay descargas activas o en cola."""
        return bool(self._threads or self._queue)

    def reserved_names(self, output_dir):
        """(tipo, clave de nombre) de las tareas no terminadas de esa carpeta, para
        que dos archivos del mismo tipo con el mismo título no colisionen."""
        folder = os.path.normcase(os.path.abspath(output_dir))
        return {
            (t.media_kind, download_name_key(t.title))
            for t in self.tasks.values()
            if t.state is not TaskState.DONE
            and os.path.normcase(os.path.abspath(t.output_dir)) == folder
        }

    def is_busy(self, url, fmt, quality):
        """True si esa combinación de video, formato y calidad ya está en curso,
        en cola, pausada o lista para reintentar."""
        return any(t.url == url and t.fmt == fmt and t.quality == quality
                   and t.state is not TaskState.DONE
                   for t in self.tasks.values())

    # ── Alta y control ───────────────────────────────────────────────────

    def add_task(self, title, url, fmt, quality, video_quality, audio_quality,
                 output_dir, speed_limit, use_ffmpeg, embed_meta=True):
        """Crea la tarea y la deja en cola. Después hay que llamar a pump()."""
        self._seq += 1
        task = DownloadTask(
            id=f"{re.sub(r'[^a-zA-Z0-9]', '_', url)[:30]}_{fmt}_{quality}_{self._seq}",
            title=title, url=url, fmt=fmt, quality=quality,
            video_quality=video_quality, audio_quality=audio_quality,
            output_dir=output_dir, speed_limit=speed_limit, use_ffmpeg=use_ffmpeg,
            embed_meta=embed_meta)
        self.tasks[task.id] = task
        self._queue.append(task.id)
        return task

    def toggle(self, task_id):
        """Pausar (si descarga o espera) o reanudar/reintentar (si está detenida)."""
        task = self.tasks.get(task_id)
        if task is None:
            return
        if task.state is TaskState.RUNNING:
            self._threads[task_id].request_pause()
            self._set(task, TaskState.PAUSING)
        elif task.state is TaskState.QUEUED:
            self._queue.remove(task_id)
            self._set(task, TaskState.PAUSED)
        elif task.state in (TaskState.PAUSED, TaskState.ERROR):
            self._queue.appendleft(task_id)
            self._set(task, TaskState.QUEUED)
            self.pump()

    def remove(self, task_id):
        """Quita la tarea de la lista (nunca borra archivos). Si está activa, la
        pausa primero y se quita cuando el hilo se detiene."""
        task = self.tasks.get(task_id)
        if task is None or task.state is TaskState.REMOVING:
            return
        if task_id in self._threads:
            self._threads[task_id].request_pause()
            self._set(task, TaskState.REMOVING)
            return
        if task.state is TaskState.QUEUED:
            self._queue.remove(task_id)
        self._discard(task_id)
        self.pump()

    def pause_all(self):
        """Pausa todas las descargas activas y las que esperan en la cola."""
        for task in list(self.tasks.values()):
            if task.state in (TaskState.RUNNING, TaskState.QUEUED):
                self.toggle(task.id)

    def resume_all(self):
        """Reanuda todas las pausadas, en el orden en que se crearon."""
        for task in list(self.tasks.values()):
            if task.state is TaskState.PAUSED:
                self._queue.append(task.id)
                self._set(task, TaskState.QUEUED)
        self.pump()

    def cancel_all(self):
        """Quita de la lista todo lo que no terminó (nunca borra archivos). Las
        activas se detienen primero y se quitan al parar su hilo."""
        ids = [t.id for t in self.tasks.values() if t.state is not TaskState.DONE]
        self._queue.clear()          # que no arranque nada nuevo mientras se quita
        for task_id in ids:
            if task_id in self._threads:
                self.remove(task_id)
            else:
                self._discard(task_id)
        self.pump()

    def pump(self):
        """Lanza descargas hasta llenar los huecos disponibles."""
        if self.closing:
            return
        while self._queue and len(self._threads) < self._max_concurrent:
            task = self.tasks[self._queue.popleft()]
            self._set(task, TaskState.RUNNING)
            try:
                thread = self._thread_factory(task, self._cookies_allowed())
            except Exception as e:      # no dejar la tarea "descargando" sin hilo
                self._set(task, TaskState.ERROR, str(e))
                continue
            thread.progress.connect(self.progress)
            thread.task_finished.connect(self._on_finished)
            self._threads[task.id] = thread
            thread.start()
        self.queue_changed.emit()

    # ── Interno ──────────────────────────────────────────────────────────

    def _set(self, task, state, message=''):
        task.state = state
        self.state_changed.emit(task.id, state, message)
        self.queue_changed.emit()

    def _discard(self, task_id):
        self.tasks.pop(task_id, None)
        self.task_removed.emit(task_id)
        self.queue_changed.emit()

    def _on_finished(self, task_id, ok, message):
        thread = self._threads.pop(task_id, None)
        if thread is not None:
            self.retire_thread(thread)
        task = self.tasks.get(task_id)
        if task is not None:
            if task.state is TaskState.REMOVING:
                self._discard(task_id)
            elif ok:
                self._set(task, TaskState.DONE)
            elif message == PAUSED_MSG:
                self._set(task, TaskState.PAUSED)
            else:
                self._set(task, TaskState.ERROR, message)
        self.pump()

    # ── Hilos ────────────────────────────────────────────────────────────

    def retire_thread(self, thread):
        """Guarda un hilo ya terminado (o por terminar) hasta poder liberarlo; soltar
        un QThread en marcha haría que Qt aborte."""
        self._finished_threads.append(thread)

    def collect_threads(self):
        """Libera los hilos que ya terminaron para no acumularlos en memoria."""
        alive = []
        for t in self._finished_threads:
            if t.isFinished():
                t.deleteLater()
            else:
                alive.append(t)
        self._finished_threads = alive

    def shutdown(self):
        """Pausa todo y espera a que los hilos terminen (para cerrar la app)."""
        self.closing = True
        threads = list(self._threads.values())
        for t in threads:
            t.request_pause()
        # No destruir la ventana mientras un QThread sigue usando la aplicación.
        waited = 0
        for t in threads:
            while not t.wait(100):
                QCoreApplication.processEvents()
                waited += 100
                # Una conversión (ffmpeg) no se puede pausar: pasados 3 s se cierra
                # el proceso para que la app termine limpia.
                if waited >= 3000 and waited % 1000 == 0:
                    kill_child_processes()
        kill_child_processes()
