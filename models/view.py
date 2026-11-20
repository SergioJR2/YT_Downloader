"""Construcción y representación visual de la ventana principal."""
from PyQt6.QtCore import QPoint, Qt, QUrl
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QImage, QPainter, QPalette, QPixmap, QPolygon
from PyQt6.QtNetwork import QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import APP_VERSION, MAX_CONCURRENT, PLAYLIST_PAGE
from .services import ytdlp_version
from .theme import (
    C_ACCENT,
    C_BG,
    C_BORDER,
    C_GOLD,
    C_MUTED,
    C_SURF2,
    C_SURF3,
    C_SURFACE,
    C_TEXT,
)
from .widgets import PlaylistRow


class WindowViewMixin:
    """Métodos de dibujo compartidos por la ventana principal."""

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
        self.main_layout.addLayout(row)

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

    def _build_options_card(self):
        card = self._card(); lay = card.layout()
        self._sec_lbl(lay, "FORMATO  &  CALIDAD")
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
        lay.addLayout(fp)
        # Calidad de video (solo aplica a MP4)
        self.quality_row = QWidget()
        self.quality_row.setStyleSheet("background: transparent; border: none;")
        self.qc = QHBoxLayout(self.quality_row)
        self.qc.setContentsMargins(0, 0, 0, 0); self.qc.setSpacing(7)
        ql = QLabel("Calidad de video"); ql.setFont(QFont("Segoe UI", 8))
        ql.setStyleSheet(f"color: {C_MUTED}; border: none; background: transparent;")
        self.qc.addWidget(ql); self.qc.addSpacing(6)
        self.quality_pills = []
        for label, val in [("Mejor", "best"), ("1080p", "1080"), ("720p", "720"), ("480p", "480")]:
            b = self._pill(label, active=(val == self.selected_quality), gold=True)
            b.setProperty("quality", val)
            b.clicked.connect(self._on_quality)
            self.quality_pills.append(b); self.qc.addWidget(b)
        self.qc.addStretch()
        lay.addWidget(self.quality_row)
        self.ffmpeg_mode_hint = QLabel("")
        self.ffmpeg_mode_hint.setFont(QFont("Segoe UI", 7))
        self.ffmpeg_mode_hint.setStyleSheet(f"color: {C_MUTED}; border: none; background: transparent;")
        self.ffmpeg_mode_hint.setWordWrap(True)
        lay.addWidget(self.ffmpeg_mode_hint)
        dest = QHBoxLayout(); dest.setSpacing(8)
        dest_lbl = QLabel("Destino:"); dest_lbl.setFont(QFont("Segoe UI", 8))
        dest_lbl.setStyleSheet(f"color: {C_MUTED}; border: none; background: transparent;")
        self.lbl_output_dir = QLabel(self.output_dir)
        self.lbl_output_dir.setFont(QFont("Segoe UI", 8))
        self.lbl_output_dir.setStyleSheet(f"color: {C_TEXT}; border: none; background: transparent;")
        self.lbl_output_dir.setWordWrap(True)
        self.lbl_output_dir.setToolTip(self.output_dir)
        self.lbl_output_dir.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dest.addWidget(dest_lbl); dest.addWidget(self.lbl_output_dir, 1)
        lay.addLayout(dest)
        self.main_layout.addWidget(card)
        # Calidad MP3, velocidad, descargas simultáneas y ffmpeg: menú Ajustes
        self._build_settings_dialog()
        self._select_fmt(self.selected_fmt)

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
        self.btn_pl_more = self._btn_sel("")
        self.btn_pl_more.clicked.connect(lambda: self._add_playlist_rows(PLAYLIST_PAGE))
        self.btn_pl_more.hide()
        lay.addWidget(self.btn_pl_more)
        act = QHBoxLayout(); act.setSpacing(10)
        self.btn_dl_pl = self._btn_primary("↓  Descargar seleccionados")
        self.btn_dl_pl.setFixedHeight(40)
        self.btn_dl_pl.clicked.connect(self.start_download)
        btn_clear_pl = self._btn_ghost("Limpiar")
        btn_clear_pl.setFixedHeight(40); btn_clear_pl.clicked.connect(self.reset)
        act.addWidget(self.btn_dl_pl); act.addWidget(btn_clear_pl); act.addStretch()
        lay.addLayout(act)
        self.pl_card.hide(); self.main_layout.addWidget(self.pl_card)

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

    def _render_video(self, data):
        self.lbl_badge.setText("▶  VIDEO")
        self.lbl_badge.setStyleSheet(f"""
            color: #5b8aff; background: rgba(91,138,255,0.12);
            border: 1px solid rgba(91,138,255,0.3); border-radius: 4px; padding: 0 8px;
        """)
        self.thumb_label.setText("🎬"); self.thumb_label.setPixmap(QPixmap())
        self.lbl_vid_title.setText(data['title'])
        v = data.get('views') or 0   # puede venir None (directos, vistas ocultas)
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
        self._pl_items = data['items']
        self._pl_total = data['count']
        self._add_playlist_rows(PLAYLIST_PAGE)

    def _add_playlist_rows(self, amount):
        """Muestra `amount` videos más de la playlist (se cargan por páginas)."""
        start = len(self.playlist_rows)
        for i, item in enumerate(self._pl_items[start:start + amount], start):
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
        shown, loaded = len(self.playlist_rows), len(self._pl_items)
        text = f"{self._pl_total} videos"
        if self._pl_total > loaded:
            text += f" · se cargaron los primeros {loaded}"
        if shown < loaded:
            text += f" · mostrando {shown}"
        self.lbl_pl_count.setText(text)
        remaining = loaded - shown
        self.btn_pl_more.setVisible(remaining > 0)
        if remaining > 0:
            self.btn_pl_more.setText(f"⌄  Mostrar {min(PLAYLIST_PAGE, remaining)} más  ({remaining} sin mostrar)")
        self._update_sel_count()

    def _show_all_playlist_rows(self):
        remaining = len(self._pl_items) - len(self.playlist_rows)
        if remaining > 0:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self._add_playlist_rows(remaining)
            finally:
                QApplication.restoreOverrideCursor()

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
        if value: self._show_all_playlist_rows()   # «Todos» incluye lo aún no mostrado
        for r in self.playlist_rows: r.set_checked(value)
        self._update_sel_count()

    def _invert(self):
        self._show_all_playlist_rows()
        for r in self.playlist_rows: r.set_checked(not r.is_checked())
        self._update_sel_count()

    def reset(self):
        self.url_input.clear()
        self.info_card.hide(); self.pl_card.hide(); self.lbl_error.hide()
        self.current_info = None; self.playlist_rows.clear(); self._pl_items = []
        self.thumb_label.setText("🎬"); self.thumb_label.setPixmap(QPixmap())

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
