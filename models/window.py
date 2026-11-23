"""Ventana principal y coordinación de la interfaz."""
import os
import platform
import re
import subprocess
import sys

from PyQt6.QtCore import QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtNetwork import QNetworkAccessManager
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .appupdate import RELEASES_URL, apply_update
from .batch_dialog import UrlListDialog
from .config import APP_VERSION, DEFAULT_CONCURRENT, DOWNLOAD_DIR
from .downloads import download_name_key, parse_url_list
from .runtime import find_ffmpeg, find_js_runtimes, kill_child_processes
from .services import ytdlp_version
from .theme import C_BG, C_BORDER
from .manager import DownloadManager, TaskState
from .widgets import DownloadCard
from .menus import WindowMenuMixin
from .view import WindowViewMixin
from .workers import (
    AppDownloadThread,
    AppUpdateCheckThread,
    BatchThread,
    FetchThread,
    ScanThread,
    UpdateThread,
)

class MainWindow(WindowMenuMixin, WindowViewMixin, QMainWindow):
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
        self._pl_items        = []
        self._pl_total        = 0
        self.selected_fmt     = self.settings.value("format", "mp4", type=str)
        if self.selected_fmt not in ('mp4', 'mp3', 'm4a', 'opus'):
            self.selected_fmt = 'mp4'
        self.selected_quality = self.settings.value("video_quality", "best", type=str)
        if self.selected_quality not in ('best', '1080', '720', '480'):
            self.selected_quality = 'best'
        self.audio_quality = self.settings.value("audio_quality", 192, type=int)
        if self.audio_quality not in (128, 192, 320):
            self.audio_quality = 192
        # Cookies del navegador: activadas por defecto (solo se leen si YouTube pide
        # verificación; se pueden desactivar en Ajustes).
        self.use_browser_cookies = self.settings.value(
            "use_browser_cookies", True, type=bool)
        # Incrustar carátula y metadatos (título, artista...) en los MP3
        self.embed_meta = self.settings.value("embed_meta", True, type=bool)
        self._ffmpeg_available = bool(find_ffmpeg())
        self.use_ffmpeg = self.settings.value(
            "use_ffmpeg", self._ffmpeg_available, type=bool) and self._ffmpeg_available

        # ── Cola de descargas ──────────────────────────────────────────
        self.manager = DownloadManager(
            self.settings.value("max_concurrent", DEFAULT_CONCURRENT, type=int),
            parent=self, cookies_allowed=lambda: self.use_browser_cookies)
        self.manager.progress.connect(self._on_dl_progress)
        self.manager.state_changed.connect(self._on_task_state)
        self.manager.task_removed.connect(self._discard_card)
        self.manager.queue_changed.connect(self._update_queue_label)
        self.speed_limit = self.settings.value("speed_limit_kbps", 0, type=int)
        self.speed_limit = max(0, min(102400, self.speed_limit))
        self._scan_thread       = None            # revisión de duplicados en curso
        self._pending_start     = None            # datos de la descarga que espera el escaneo
        self._batch_thread      = None            # lectura de una lista de enlaces
        self._batch_dlg         = None
        self._batch_invalid     = []

        # Un solo QNetworkAccessManager reutilizable para thumbnails
        self._net_mgr = QNetworkAccessManager(self)
        self._net_mgr.finished.connect(self._on_thumb)
        # Otro para las miniaturas de las filas de una playlist
        self._row_net = QNetworkAccessManager(self)
        self._row_net.finished.connect(self._on_row_thumb)
        self._row_replies = {}

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

        self._build_menu_bar()
        self._build_header()
        self._build_url_card()
        self._build_options_card()
        self._build_info_card()
        self._build_playlist_card()
        self._build_downloads_panel()
        self.main_layout.addStretch()

        # Si falta el motor JavaScript que YouTube exige, ofrecer instalarlo
        QTimer.singleShot(600, self._check_js_runtime)

        # Busca en segundo plano una versión nueva de la app (solo con el .exe)
        self.fetch_thread = None
        self._app_check = None
        self._app_check_manual = False
        self._app_dl = None
        self._app_dlg = None
        self._app_asset = None
        if getattr(sys, 'frozen', False):
            QTimer.singleShot(3000, lambda: self.check_app_update(manual=False))

    # ── Icono ──────────────────────────────────────────────────────────────


    # ── Encabezado ─────────────────────────────────────────────────────────

    # ── URL ────────────────────────────────────────────────────────────────

    # ── Formato + Calidad ──────────────────────────────────────────────────

    # ── Info video único ───────────────────────────────────────────────────

    # ── Panel playlist ─────────────────────────────────────────────────────

    # ── Panel descargas ─────────────────────────────────────────────────────

    # ─── Actualizar yt-dlp ───────────────────────────────────────────────
    def update_ytdlp(self):
        self.act_update_ytdlp.setEnabled(False)
        self.act_update_ytdlp.setText("Actualizando yt-dlp…")
        self._upd = UpdateThread()
        self._upd.done.connect(self._on_update_done)
        self._upd.start()

    def _on_update_done(self, ok, msg, restart):
        self.act_update_ytdlp.setEnabled(True)
        self.act_update_ytdlp.setText(f"Actualizar yt-dlp  (v{ytdlp_version()})")
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

    # ─── Actualizar la propia app (GitHub Releases) ──────────────────────
    def check_app_update(self, manual=False):
        if self._app_check is not None and self._app_check.isRunning():
            return
        if self._app_dl is not None and self._app_dl.isRunning():
            return
        self._app_check_manual = manual
        if manual:
            self.act_app_update.setEnabled(False)
            self.act_app_update.setText("Buscando actualización…")
        self._app_check = AppUpdateCheckThread()
        self._app_check.done.connect(self._on_app_check_done)
        self._app_check.start()

    def _on_app_check_done(self, info, err):
        manual = self._app_check_manual
        self.act_app_update.setEnabled(True)
        self.act_app_update.setText(f"Buscar actualización de la app  (v{APP_VERSION})")
        if err or info is None:
            if manual:
                QMessageBox.warning(self, "Actualización de la app",
                                    "No se pudo consultar GitHub:\n\n" + err)
            return
        if not info['newer']:
            if manual:
                QMessageBox.information(
                    self, "Actualización de la app",
                    f"Ya tienes la última versión (v{APP_VERSION}).")
            return
        if (not manual and
                self.settings.value("skipped_app_version", "", type=str) == info['version']):
            return
        self._offer_app_update(info, manual)

    def _offer_app_update(self, info, manual):
        asset = info['asset']
        text = f"Hay una versión nueva: v{info['version']}  (tienes v{APP_VERSION})."
        notes = info['notes']
        if notes:
            text += "\n\nNovedades:\n" + notes[:700] + ("…" if len(notes) > 700 else "")
        if not asset:
            text += ("\n\nEsta copia no se puede actualizar sola"
                     + (" (se está ejecutando desde el código fuente)."
                        if not getattr(sys, 'frozen', False)
                        else " (no hay un archivo compatible con SHA-256 para verificarlo, o la "
                           "carpeta no permite escribir)."))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Actualización disponible")
        box.setText(text)
        b_go = box.addButton("Actualizar ahora" if asset else "Abrir página de descarga",
                             QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Más tarde", QMessageBox.ButtonRole.RejectRole)
        b_skip = None
        if not manual:
            b_skip = box.addButton("Omitir esta versión", QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_skip and b_skip is not None:
            self.settings.setValue("skipped_app_version", info['version'])
        elif clicked is b_go:
            if asset:
                self._download_app_update(info)
            else:
                QDesktopServices.openUrl(QUrl(info.get('page') or RELEASES_URL))

    def _download_app_update(self, info):
        if self.manager.has_pending():
            r = QMessageBox.question(
                self, "Descargas en curso",
                "Hay descargas activas o en cola. Al actualizar se pausarán (lo ya "
                "descargado se conserva) y tendrás que reanudarlas después.\n\n¿Continuar?")
            if r != QMessageBox.StandardButton.Yes:
                return
        self._app_asset = info['asset']
        dlg = QProgressDialog(f"Descargando v{info['version']}…", "Cancelar", 0, 100, self)
        dlg.setWindowTitle("Actualizando YT Downloader")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        th = AppDownloadThread(self._app_asset)
        th.progress.connect(self._on_app_dl_progress)
        th.done.connect(self._on_app_dl_done)
        dlg.canceled.connect(th.cancel)
        self._app_dlg, self._app_dl = dlg, th
        th.start()

    def _on_app_dl_progress(self, done, total):
        if self._app_dlg is None:
            return
        mb = 1024 ** 2
        if total:
            self._app_dlg.setValue(min(99, int(done * 100 / total)))
            self._app_dlg.setLabelText(
                f"Descargando… {done / mb:.1f} / {total / mb:.1f} MB")
        else:
            self._app_dlg.setLabelText(f"Descargando… {done / mb:.1f} MB")

    def _on_app_dl_done(self, ok, result):
        if self._app_dlg is not None:
            self._app_dlg.blockSignals(True)
            self._app_dlg.close()
            self._app_dlg.deleteLater()
            self._app_dlg = None
        if not ok:
            if result:   # texto vacío = canceló el usuario
                QMessageBox.warning(self, "Actualización de la app",
                                    "No se pudo descargar la actualización:\n\n" + result)
            return
        try:
            apply_update(result, self._app_asset['kind'])
        except Exception as e:
            QMessageBox.warning(self, "Actualización de la app",
                                "No se pudo aplicar la actualización:\n\n" + str(e))
            return
        # El script auxiliar espera a que esta app cierre, instala y la reabre.
        self.close()
        QApplication.quit()

    # ─── Lógica de fetch ──────────────────────────────────────────────────

    def fetch_info(self):
        url = self.url_input.text().strip()
        if not url: return
        # Enter en la caja de texto no pasa por el botón (que se deshabilita): sin
        # esta guarda, un segundo Enter reasignaba el hilo en marcha y Qt abortaba
        # con "QThread: Destroyed while thread is still running".
        if self.fetch_thread is not None and self.fetch_thread.isRunning():
            return
        self.lbl_error.hide()
        self._clear_result()
        self.btn_fetch.setEnabled(False); self.btn_fetch.setText("…")
        self.fetch_thread = FetchThread(
            url, allow_browser_cookies=self.use_browser_cookies)
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
        if self.settings.value("js_prompt_declined", False, type=bool):
            return
        r = QMessageBox.question(
            self, "Falta un componente",
            "YouTube ahora exige un motor JavaScript (Deno) y sin él muchos "
            "videos fallan con «This video is not available».\n\n"
            "¿Descargarlo e instalarlo ahora? (≈ 43 MB, se hace una sola vez)\n\n"
            "Si eliges «No», no volveré a preguntar; puedes instalarlo después desde "
            "Herramientas → Actualizar yt-dlp.")
        if r == QMessageBox.StandardButton.Yes:
            self.update_ytdlp()
        else:
            self.settings.setValue("js_prompt_declined", True)






    # ─── Cola de descargas throttled ──────────────────────────────────────

    def _on_concurrent_change(self, value):
        self.manager.max_concurrent = value
        self.settings.setValue("max_concurrent", self.manager.max_concurrent)

    def _on_speed_change(self, value):
        self.speed_limit = value
        self.settings.setValue("speed_limit_kbps", value)

    def _on_audio_quality(self, _index):
        self.audio_quality = int(self.combo_audio_quality.currentData())
        self.settings.setValue("audio_quality", self.audio_quality)

    def _on_browser_cookies_change(self, enabled):
        if enabled:
            r = QMessageBox.question(
                self, "Usar cookies del navegador",
                "Si YouTube pide verificar que no eres un robot, la app leerá las "
                "cookies de tu sesión de YouTube desde Firefox, Edge, Chrome o Brave "
                "(solo para esa petición; no se guardan ni se envían a ningún otro "
                "sitio).\n\nEs información sensible. ¿Activarlo?")
            if r != QMessageBox.StandardButton.Yes:
                self.chk_browser_cookies.blockSignals(True)
                self.chk_browser_cookies.setChecked(False)
                self.chk_browser_cookies.blockSignals(False)
                return
        self.use_browser_cookies = bool(enabled)
        self.settings.setValue("use_browser_cookies", self.use_browser_cookies)

    def _on_embed_meta_change(self, enabled):
        self.embed_meta = enabled
        self.settings.setValue("embed_meta", enabled)

    def _on_ffmpeg_mode_change(self, omit_ffmpeg):
        self.use_ffmpeg = self._ffmpeg_available and not omit_ffmpeg
        self.settings.setValue("use_ffmpeg", self.use_ffmpeg)
        self._select_fmt(self.selected_fmt)

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
        """Prepara la descarga del video o la selección de playlist analizada."""
        if not self.current_info: return
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        url = self.url_input.text().strip()
        if self.current_info['type'] == 'playlist':
            items = [(r.title_full, r.url) for r in self.playlist_rows if r.is_checked()]
        else:
            # Usa la URL que se ANALIZÓ, no lo que haya en la caja ahora mismo
            items = [(self.current_info['title'], self.current_info.get('url') or url)]
        self._queue_items(items)

    def _queue_items(self, items):
        """Revisa duplicados en un hilo aparte con los ajustes de AHORA; el resto
        continúa en _on_scan_done. Lo usan la descarga normal y la de lista .txt.
        Devuelve False si no pudo empezar (no hay nada o hay otra revisión en curso)."""
        if not items: return False
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return False

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
        # Se guardan los valores de AHORA: si el usuario cambia formato o carpeta
        # mientras se revisa, la descarga sigue siendo la que pidió.
        self._pending_start = {
            'items': items, 'fmt': fmt, 'q': q, 'tag': tag,
            'media_kind': media_kind, 'use_ffmpeg': use_ffmpeg,
            'output_dir': self.output_dir, 'embed_meta': self.embed_meta,
        }
        self.btn_dl_single.setEnabled(False)
        self.btn_dl_pl.setEnabled(False)
        th = ScanThread(self.output_dir, media_kind)
        th.done.connect(self._on_scan_done)
        th.failed.connect(self._on_scan_failed)
        self._scan_thread = th
        th.start()
        return True

    # ─── Descarga desde una lista de enlaces (.txt) ───────────────────────

    def load_url_list(self):
        """Archivo → Descargar varios enlaces: abre un cuadro donde pegar la lista."""
        if self._batch_thread is not None and self._batch_thread.isRunning():
            return
        dlg = UrlListDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        urls, invalid = parse_url_list(dlg.text())
        if not urls:
            return
        self._batch_invalid = invalid

        dlg = QProgressDialog(f"Leyendo {len(urls)} enlaces…", "Cancelar", 0, len(urls), self)
        dlg.setWindowTitle("Lista de enlaces")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        self._batch_dlg = dlg
        th = BatchThread(urls, allow_browser_cookies=self.use_browser_cookies)
        th.progress.connect(self._on_batch_progress)
        th.done.connect(self._on_batch_done)
        dlg.canceled.connect(th.cancel)
        self._batch_thread = th
        th.start()

    def _on_batch_progress(self, done, total):
        if self._batch_dlg is not None:
            self._batch_dlg.setValue(done)
            self._batch_dlg.setLabelText(f"Leyendo enlaces… {done} de {total}")

    def _on_batch_done(self, items, errors):
        th, self._batch_thread = self._batch_thread, None
        if th is not None:
            self.manager.retire_thread(th)
        dlg, self._batch_dlg = self._batch_dlg, None
        if dlg is not None:
            dlg.canceled.disconnect()
            dlg.close()
        if self.manager.closing:
            return
        problems = [f"• {u}  (no es un enlace válido)" for u in self._batch_invalid]
        problems += [f"• {u}\n   {msg.splitlines()[0] if msg else 'Error'}" for u, msg in errors]
        started = self._queue_items(items) if items else False
        if items and not started:
            QMessageBox.information(
                self, "Lista de enlaces",
                "Todavía se está revisando la carpeta. Vuelve a cargar la lista en unos segundos.")
            return
        if problems:
            more = f"\n… y {len(problems) - 8} más" if len(problems) > 8 else ""
            QMessageBox.warning(
                self, "Algunos enlaces no se pudieron usar",
                f"{len(items)} video(s) se enviaron a la cola. Estos no:\n\n"
                + "\n".join(problems[:8]) + more)

    def _finish_scan(self):
        th, self._scan_thread = self._scan_thread, None
        if th is not None:
            self.manager.retire_thread(th)      # se libera cuando termine
        self.btn_dl_single.setEnabled(True)
        self._update_sel_count()                # reactiva el botón de playlist si procede

    def _on_scan_failed(self, err):
        self._pending_start = None
        self._finish_scan()
        QMessageBox.warning(
            self, "No se pudo revisar la carpeta",
            f"No se puede comprobar si ya existen esos archivos:\n\n{err}")

    def _on_scan_done(self, existing_names):
        pending, self._pending_start = self._pending_start, None
        self._finish_scan()
        if not pending or self.manager.closing:
            return
        items, fmt, q = pending['items'], pending['fmt'], pending['q']
        tag, media_kind = pending['tag'], pending['media_kind']
        use_ffmpeg, output_dir = pending['use_ffmpeg'], pending['output_dir']
        embed_meta = pending.get('embed_meta', True)

        # Nombres de tareas activas, en cola, pausadas o fallidas: dos archivos del
        # mismo tipo con el mismo título no deben colisionar.
        reserved_names = self.manager.reserved_names(output_dir)
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
            if self.manager.is_busy(u, fmt, q):
                continue
            task = self.manager.add_task(
                title=title, url=u, fmt=fmt, quality=q,
                video_quality=self.selected_quality, audio_quality=self.audio_quality,
                output_dir=output_dir, speed_limit=self.speed_limit,
                use_ffmpeg=use_ffmpeg, embed_meta=embed_meta)
            card = DownloadCard(task.id, title, tag)
            card.action_clicked.connect(self.manager.toggle)
            card.remove_clicked.connect(self.manager.remove)
            self.download_cards[task.id] = card
            self.dl_list_layout.insertWidget(0, card)
            reserved_names.add(reservation)
            enqueued += 1

        if enqueued:
            self.dl_panel.show()
        self.manager.pump()

        if skipped_existing or skipped_reserved:
            details = []
            if skipped_existing:
                examples = '\n'.join(f"• {name}" for name in skipped_existing[:5])
                more = (f"\n… y {len(skipped_existing) - 5} más"
                        if len(skipped_existing) > 5 else "")
                details.append(
                    f"{len(skipped_existing)} omitido(s): ya existe un archivo del "
                    f"mismo tipo con ese nombre (se ignoran etiquetas como «Official "
                    f"Video» o «Lyrics»; un «Remix» o «Live» cuenta como otra versión).\n"
                    f"{examples}{more}")
            if skipped_reserved:
                details.append(
                    f"{len(skipped_reserved)} omitido(s): ya hay una descarga con "
                    "ese nombre activa, en cola, pausada o lista para reintentar.")
            QMessageBox.information(
                self, "Descargas omitidas",
                "\n\n".join(details) + f"\n\nCarpeta revisada:\n{output_dir}")

    # ─── Reacción a la cola (el estado vive en DownloadManager) ───────────

    def _on_task_state(self, task_id, state, message):
        card = self.download_cards.get(task_id)
        if card is None:
            return
        if state is TaskState.RUNNING:
            card.set_running(); card.set_starting()
        elif state is TaskState.QUEUED:
            card.set_running()
        elif state is TaskState.PAUSING:
            card.set_pausing()
        elif state is TaskState.REMOVING:
            card.set_removing()
        elif state is TaskState.PAUSED:
            card.set_paused()
        elif state is TaskState.ERROR:
            card.set_error(message)
        elif state is TaskState.DONE:
            card.set_done()

    def _on_dl_progress(self, task_id, pct, speed, status):
        card = self.download_cards.get(task_id)
        if card: card.update_progress(pct, speed, status)

    def _discard_card(self, task_id):
        """Quita solo la tarjeta, nunca el archivo descargado."""
        card = self.download_cards.pop(task_id, None)
        if card:
            self.dl_list_layout.removeWidget(card)
            card.deleteLater()
        if not self.download_cards:
            self.dl_panel.hide()

    def _pause_all(self):
        self.manager.pause_all()

    def _resume_all(self):
        self.manager.resume_all()

    def _cancel_all(self):
        n = sum(1 for t in self.manager.tasks.values() if t.state is not TaskState.DONE)
        if not n:
            return
        r = QMessageBox.question(
            self, "Cancelar todas",
            f"¿Cancelar {n} descarga{'s' if n != 1 else ''} y quitarla"
            f"{'s' if n != 1 else ''} de la lista?\n\nNo se borran los archivos "
            "ya descargados (los parciales quedan en la carpeta).")
        if r == QMessageBox.StandardButton.Yes:
            self.manager.cancel_all()

    def _update_global_buttons(self):
        states = [t.state for t in self.manager.tasks.values()]
        self.btn_pause_all.setEnabled(
            any(s in (TaskState.RUNNING, TaskState.QUEUED) for s in states))
        self.btn_resume_all.setEnabled(any(s is TaskState.PAUSED for s in states))
        self.btn_cancel_all.setEnabled(any(s is not TaskState.DONE for s in states))

    def _update_queue_label(self):
        self._update_global_buttons()
        active = self.manager.active_count
        queued = self.manager.queued_ids()
        if active == 0 and not queued:
            self.lbl_queue_info.setText("")
            return
        parts = []
        if active:  parts.append(f"{active} activa{'s' if active!=1 else ''}")
        if queued:  parts.append(f"{len(queued)} en cola")
        self.lbl_queue_info.setText("  ·  ".join(parts))
        # Actualizar etiqueta de posición en cola
        for i, tid in enumerate(queued):
            c = self.download_cards.get(tid)
            if c: c.set_queued(i + 1)

    def closeEvent(self, event):
        self.manager.shutdown()
        # Hilos auxiliares: si siguen vivos al destruir la ventana, Qt aborta con
        # "QThread: Destroyed while thread is still running".
        for th in (self.fetch_thread, getattr(self, '_upd', None), self._scan_thread,
                   self._app_check, self._app_dl):
            if th is not None and th.isRunning():
                if hasattr(th, 'cancel'):
                    th.cancel()
                if not th.wait(2000):
                    th.terminate(); th.wait(500)
        kill_child_processes()   # p. ej. el pip de una actualización interrumpida
        event.accept()

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
        self.quality_row.setVisible(fmt == 'mp4')   # la calidad de video solo aplica a MP4

    def _on_quality(self):
        self.selected_quality = self.sender().property("quality")
        self.settings.setValue("video_quality", self.selected_quality)
        for p in self.quality_pills:
            p.setStyleSheet(self._pill_ss(p == self.sender(), gold=True))
