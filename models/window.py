"""Ventana principal y coordinación de la interfaz."""
import os
import platform
import re
import subprocess
import sys
from collections import deque

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtNetwork import QNetworkAccessManager
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .config import DEFAULT_CONCURRENT, DOWNLOAD_DIR, MAX_CONCURRENT
from .downloads import download_name_key, existing_download_names
from .errors import PAUSED_MSG
from .runtime import find_ffmpeg, find_js_runtimes, kill_child_processes
from .services import set_browser_cookies, ytdlp_version
from .theme import C_BG, C_BORDER
from .widgets import DownloadCard
from .view import WindowViewMixin
from .workers import DownloadThread, FetchThread, UpdateThread

class MainWindow(WindowViewMixin, QMainWindow):
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
        self.browser_cookies = self.settings.value("browser_cookies", False, type=bool)
        set_browser_cookies(self.browser_cookies)
        self._ffmpeg_available = bool(find_ffmpeg())
        self.use_ffmpeg = self.settings.value(
            "use_ffmpeg", self._ffmpeg_available, type=bool) and self._ffmpeg_available

        # ── Cola de descargas (throttled) ──────────────────────────────
        self._download_queue:   deque = deque()   # task_id en espera
        self._tasks:            dict  = {}        # task_id → {title,url,fmt,quality}
        self._stopped:          set   = set()     # task_id en pausa o con error
        self._remove_when_stopped: set = set()    # tareas activas que se quitarán al pausar
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

    def _on_ffmpeg_mode_change(self, omit_ffmpeg):
        self.use_ffmpeg = self._ffmpeg_available and not omit_ffmpeg
        self.settings.setValue("use_ffmpeg", self.use_ffmpeg)
        self._select_fmt(self.selected_fmt)

    def _on_browser_cookies_change(self, enabled):
        self.browser_cookies = enabled
        self.settings.setValue("browser_cookies", enabled)
        set_browser_cookies(enabled)

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
        use_ffmpeg = self.use_ffmpeg and self._ffmpeg_available
        if fmt == 'mp3':
            tag = 'MP3' if use_ffmpeg else 'AUDIO ORIGINAL'
        elif fmt in ('m4a', 'opus'):
            tag = fmt.upper()
        else:
            tag = 'MP4' + ('' if q == 'best' else f' {q}p')

        media_kind = 'video' if fmt == 'mp4' else 'audio'
        try:
            existing_names = existing_download_names(self.output_dir, media_kind)
        except OSError as e:
            QMessageBox.warning(
                self, "No se pudo revisar la carpeta",
                f"No se puede comprobar si ya existen esos archivos:\n\n{e}")
            return

        # Reserva nombres de tareas activas, en cola, pausadas o fallidas para que
        # dos archivos del mismo tipo con el mismo título no colisionen.
        active_ids = set(self._active_threads) | set(self._download_queue) | self._stopped
        output_dir_key = os.path.normcase(os.path.abspath(self.output_dir))
        reserved_names = {
            (('video' if task['fmt'] == 'mp4' else 'audio'),
             download_name_key(task['title']))
            for task_id, task in self._tasks.items()
            if task_id in active_ids
            and os.path.normcase(os.path.abspath(task['output_dir'])) == output_dir_key
        }
        skipped_existing = []
        skipped_reserved = []
        enqueued = 0
        for title, u in items:
            name_key = download_name_key(title)
            existing_file = existing_names.get(name_key)
            if existing_file:
                skipped_existing.append(existing_file)
                continue
            reservation = (media_kind, name_key)
            if reservation in reserved_names:
                skipped_reserved.append(title)
                continue

            # Evita encolar de nuevo la misma combinación de video, formato y
            # calidad si su tarjeta sigue activa, en cola o pausada.
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
                'use_ffmpeg': use_ffmpeg,
            }
            card = DownloadCard(task_id, title, tag)
            card.action_clicked.connect(self.toggle_task)
            card.remove_clicked.connect(self.remove_download)
            self.download_cards[task_id] = card
            self.dl_list_layout.insertWidget(0, card)
            self._download_queue.append(task_id)
            reserved_names.add(reservation)
            enqueued += 1

        if enqueued:
            self.dl_panel.show()
        self._pump_queue()
        self._update_queue_label()

        if skipped_existing or skipped_reserved:
            details = []
            if skipped_existing:
                examples = '\n'.join(f"• {name}" for name in skipped_existing[:5])
                more = (f"\n… y {len(skipped_existing) - 5} más"
                        if len(skipped_existing) > 5 else "")
                details.append(
                    f"{len(skipped_existing)} omitido(s): ya existe un archivo del "
                    f"mismo tipo con ese nombre.\n{examples}{more}")
            if skipped_reserved:
                details.append(
                    f"{len(skipped_reserved)} omitido(s): ya hay una descarga con "
                    "ese nombre activa, en cola, pausada o lista para reintentar.")
            QMessageBox.information(
                self, "Descargas omitidas",
                "\n\n".join(details) + f"\n\nCarpeta revisada:\n{self.output_dir}")

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

    def remove_download(self, task_id):
        """Quita una tarea de la lista; si está activa, la pausa primero."""
        card = self.download_cards.get(task_id)
        if not card:
            return
        if task_id in self._active_threads:
            self._remove_when_stopped.add(task_id)
            card.set_removing()
            self._active_threads[task_id].request_pause()
            return
        if task_id in self._download_queue:
            self._download_queue.remove(task_id)
        self._discard_download(task_id)
        self._pump_queue()

    def _discard_download(self, task_id):
        """Elimina solo la tarjeta y el estado en memoria, nunca el archivo."""
        self._remove_when_stopped.discard(task_id)
        self._stopped.discard(task_id)
        self._tasks.pop(task_id, None)
        card = self.download_cards.pop(task_id, None)
        if card:
            self.dl_list_layout.removeWidget(card)
            card.deleteLater()
        if not self.download_cards:
            self.dl_panel.hide()

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
                task['output_dir'], task['audio_quality'], task['speed_limit'],
                task.get('use_ffmpeg', self.use_ffmpeg))
            t.progress.connect(self._on_dl_progress)
            t.done.connect(self._on_dl_finished)
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
        if task_id in self._remove_when_stopped:
            self._discard_download(task_id)
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
        waited = 0
        for t in threads:
            while not t.wait(100):
                QApplication.processEvents()
                waited += 100
                # Una conversión (ffmpeg) no se puede pausar: pasados 3 s se cierra
                # el proceso para que la app termine limpia.
                if waited >= 3000 and waited % 1000 == 0:
                    kill_child_processes()
        kill_child_processes()
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

    def open_folder(self):
        folder = os.path.abspath(os.path.expanduser(self.output_dir))
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "Carpeta no disponible", str(e))
            return

        sn = platform.system()
        try:
            if sn == 'Windows':
                os.startfile(folder)
            elif sn == 'Darwin':
                subprocess.Popen(['open', folder])
            else:
                subprocess.Popen(['xdg-open', folder])
        except OSError as e:
            QMessageBox.warning(self, "No se pudo abrir la carpeta", str(e))



    def _select_fmt(self, fmt):
        self.selected_fmt = fmt
        self.settings.setValue("format", fmt)
        self.btn_mp4.setStyleSheet(self._pill_ss(fmt=='mp4', gold=False))
        self.btn_mp3.setStyleSheet(self._pill_ss(fmt=='mp3', gold=False))
        self.btn_m4a.setStyleSheet(self._pill_ss(fmt=='m4a', gold=False))
        self.btn_opus.setStyleSheet(self._pill_ss(fmt=='opus', gold=False))
        can_convert = self.use_ffmpeg and self._ffmpeg_available
        self.combo_audio_quality.setEnabled(fmt == 'mp3' and can_convert)
        if fmt == 'mp3' and not can_convert:
            self.combo_audio_quality.setToolTip(
                "Sin conversión: se guarda el audio original (normalmente M4A).")
        else:
            self.combo_audio_quality.setToolTip("Bitrate de conversión MP3.")
        if not self._ffmpeg_available:
            self.ffmpeg_mode_hint.setText("Sin ffmpeg: MP4 usa un formato directo; MP3 guarda el audio original.")
        elif self.use_ffmpeg:
            self.ffmpeg_mode_hint.setText("MP4 puede combinar video y audio; MP3 se convierte al bitrate elegido.")
        else:
            self.ffmpeg_mode_hint.setText("MP4 usa un formato directo (hasta 720p); MP3 guarda audio M4A original.")
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
