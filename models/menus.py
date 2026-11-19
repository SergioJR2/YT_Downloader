"""Barra de menú (Archivo, Ajustes, Herramientas, Ayuda) y diálogo de Ajustes."""
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from .config import APP_VERSION, GITHUB_REPO, MAX_CONCURRENT
from .runtime import find_ffmpeg
from .services import ytdlp_version
from .theme import C_BG, C_BORDER, C_MUTED, C_SURF2, C_SURF3, C_SURFACE, C_TEXT

_GITHUB_URL = f"https://github.com/{GITHUB_REPO}"


class WindowMenuMixin:
    """Menús de la ventana principal y ventana de Ajustes."""

    # ── Barra de menú ────────────────────────────────────────────────────
    def _build_menu_bar(self):
        bar = self.menuBar()
        bar.setNativeMenuBar(False)
        bar.setStyleSheet(f"""
            QMenuBar {{ background: {C_SURFACE}; color: {C_TEXT};
                border-bottom: 1px solid {C_BORDER}; padding: 2px 6px; }}
            QMenuBar::item {{ background: transparent; padding: 5px 12px; border-radius: 5px; }}
            QMenuBar::item:selected {{ background: {C_SURF3}; }}
            QMenu {{ background: {C_SURFACE}; color: {C_TEXT}; border: 1px solid {C_BORDER};
                padding: 4px; }}
            QMenu::item {{ padding: 6px 28px 6px 20px; border-radius: 5px; }}
            QMenu::item:selected {{ background: {C_SURF3}; }}
            QMenu::item:disabled {{ color: {C_MUTED}; }}
            QMenu::separator {{ height: 1px; background: {C_BORDER}; margin: 4px 8px; }}
        """)

        def act(text, slot, shortcut=None, tip=None):
            a = QAction(text, self)
            a.triggered.connect(lambda _checked=False: slot())
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setStatusTip(tip); a.setToolTip(tip)
            return a

        m = bar.addMenu("Archivo")
        m.addAction(act("Cambiar carpeta de descarga…", self._choose_output_dir, "Ctrl+O"))
        m.addAction(act("Abrir carpeta de descargas", self.open_folder, "Ctrl+D"))
        m.addSeparator()
        m.addAction(act("Salir", self.close, "Ctrl+Q"))

        m = bar.addMenu("Ajustes")
        m.addAction(act("Opciones de descarga…", self.show_settings, "Ctrl+,"))

        m = bar.addMenu("Herramientas")
        self.act_update_ytdlp = act(
            f"Actualizar yt-dlp  (v{ytdlp_version()})", self.update_ytdlp,
            tip="Actualiza yt-dlp y sus componentes. Soluciona la mayoría de errores de YouTube.")
        self.act_app_update = act(
            f"Buscar actualización de la app  (v{APP_VERSION})",
            lambda: self.check_app_update(manual=True),
            tip="Busca una versión nueva de YT Downloader en GitHub (Releases) y la instala.")
        m.addAction(self.act_update_ytdlp)
        m.addAction(self.act_app_update)

        m = bar.addMenu("Ayuda")
        m.addAction(act("Ver versiones en GitHub",
                        lambda: QDesktopServices.openUrl(QUrl(_GITHUB_URL + "/releases"))))
        m.addAction(act("Reportar un problema",
                        lambda: QDesktopServices.openUrl(QUrl(_GITHUB_URL + "/issues"))))
        m.addSeparator()
        m.addAction(act("Acerca de YT Downloader", self.show_about))

    def show_about(self):
        ff = "sí" if find_ffmpeg() else "no"
        QMessageBox.about(
            self, "Acerca de YT Downloader",
            f"<b>YT Downloader</b> v{APP_VERSION}<br>"
            f"yt-dlp v{ytdlp_version()} · ffmpeg disponible: {ff}<br><br>"
            f"<a href='{_GITHUB_URL}'>{_GITHUB_URL}</a>")

    # ── Ajustes ──────────────────────────────────────────────────────────
    def show_settings(self):
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def _build_settings_dialog(self):
        """Crea (una sola vez) la ventana de Ajustes. Los controles conservan los
        mismos nombres que antes, así la lógica de la ventana no cambia."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Ajustes · Opciones de descarga")
        dlg.setMinimumWidth(430)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {C_BG}; }}
            QLabel {{ color: {C_TEXT}; }}
            QCheckBox {{ color: {C_TEXT}; }}
            QSpinBox, QComboBox {{ background: {C_SURF2}; border: 1px solid {C_BORDER};
                border-radius: 7px; color: {C_TEXT}; padding: 0 8px; min-height: 30px; }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 18px; border: none; background: {C_SURF3}; }}
            QComboBox QAbstractItemView {{ background: {C_SURF2}; color: {C_TEXT};
                selection-background-color: {C_SURF3}; }}
        """)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(22, 18, 22, 18); root.setSpacing(14)
        form = QFormLayout(); form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        def hint(text):
            h = QLabel(text); h.setFont(QFont("Segoe UI", 7))
            h.setStyleSheet(f"color: {C_MUTED};"); h.setWordWrap(True)
            return h

        def field(widget, note):
            box = QVBoxLayout(); box.setSpacing(3)
            box.addWidget(widget); box.addWidget(hint(note))
            return box

        # Calidad MP3
        self.combo_audio_quality = QComboBox()
        for bitrate in (128, 192, 320):
            self.combo_audio_quality.addItem(f"{bitrate} kbps", bitrate)
        self.combo_audio_quality.setCurrentIndex(
            max(0, self.combo_audio_quality.findData(self.audio_quality)))
        self.combo_audio_quality.currentIndexChanged.connect(self._on_audio_quality)
        form.addRow("Calidad MP3", field(self.combo_audio_quality, "Requiere ffmpeg."))

        # Descargas a la vez
        self.spin_concurrent = QSpinBox()
        self.spin_concurrent.setRange(1, MAX_CONCURRENT)
        self.spin_concurrent.setValue(self._max_concurrent)
        self.spin_concurrent.valueChanged.connect(self._on_concurrent_change)
        form.addRow("Descargas a la vez",
                    field(self.spin_concurrent, f"De 1 a {MAX_CONCURRENT}. Menos = menos carga en PC y red."))

        # Límite de velocidad
        self.spin_speed = QSpinBox()
        self.spin_speed.setRange(0, 102400)
        self.spin_speed.setValue(self.speed_limit)
        self.spin_speed.setSuffix(" KB/s")
        self.spin_speed.setSpecialValueText("Sin límite")
        self.spin_speed.valueChanged.connect(self._on_speed_change)
        form.addRow("Límite de velocidad",
                    field(self.spin_speed, "0 = sin límite. El valor se aplica a cada descarga."))

        # ffmpeg
        self.chk_no_ffmpeg = QCheckBox("Omitir ffmpeg")
        self.chk_no_ffmpeg.setChecked(not self.use_ffmpeg)
        self.chk_no_ffmpeg.setEnabled(self._ffmpeg_available)
        self.chk_no_ffmpeg.toggled.connect(self._on_ffmpeg_mode_change)
        form.addRow("ffmpeg", field(
            self.chk_no_ffmpeg,
            "MP4 usará un formato directo (hasta 720p) y MP3 guardará el audio original M4A. "
            "M4A y Opus siempre se descargan sin ffmpeg."
            + ("" if self._ffmpeg_available else "  (ffmpeg no está disponible.)")))

        root.addLayout(form)
        row = QHBoxLayout(); row.addStretch()
        btn = self._btn_ghost("Cerrar"); btn.setFixedHeight(34)
        btn.clicked.connect(dlg.close)
        row.addWidget(btn)
        root.addLayout(row)
        self._settings_dlg = dlg
