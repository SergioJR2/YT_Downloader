import sys
import os
import re
import subprocess
import platform

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar,
    QScrollArea, QFrame, QCheckBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QPixmap, QIcon, QPainter,
    QBrush, QImage, QPolygon
)
from PyQt6.QtCore import QPoint
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import yt_dlp

# ─── Config ───────────────────────────────────────────────────────────────────
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Descargas_YouTube")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
class FetchThread(QThread):
    result = pyqtSignal(dict)
    error  = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            opts = {
                'quiet': True, 'no_warnings': True,
                'extract_flat': 'in_playlist',
                'extractor_args': {'youtube': ['player_client=android,web']},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)

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
                heights = sorted(set(f.get('height') for f in formats if f.get('height')), reverse=True)
                self.result.emit({
                    'type':      'video',
                    'title':     info.get('title', 'Sin título'),
                    'duration':  info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'channel':   info.get('uploader', ''),
                    'views':     info.get('view_count', 0),
                    'qualities': [str(h) for h in heights[:5]],
                })
        except Exception as e:
            self.error.emit(str(e))


class DownloadThread(QThread):
    progress = pyqtSignal(str, float, str, str)
    finished = pyqtSignal(str, bool, str)

    def __init__(self, task_id, url, fmt, quality):
        super().__init__()
        self.task_id = task_id
        self.url     = url
        self.fmt     = fmt
        self.quality = quality

    def _hook(self, d):
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
                'quiet': True, 'no_warnings': True,
                'extractor_args': {'youtube': ['player_client=android,web']},
            }
            if self.fmt == 'mp3':
                base.update({
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
                    'postprocessors': [{'key': 'FFmpegExtractAudio',
                                        'preferredcodec': 'mp3',
                                        'preferredquality': '192'}],
                })
            else:
                qmap = {
                    '1080': 'bestvideo[height<=1080]+bestaudio/best',
                    '720':  'bestvideo[height<=720]+bestaudio/best',
                    '480':  'bestvideo[height<=480]+bestaudio/best',
                    'best': 'bestvideo+bestaudio/best',
                }
                base.update({
                    'format': qmap.get(self.quality, 'bestvideo+bestaudio/best'),
                    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
                    'merge_output_format': 'mp4',
                })
            with yt_dlp.YoutubeDL(base) as ydl:
                ydl.download([self.url])
            self.finished.emit(self.task_id, True, '')
        except Exception as e:
            self.finished.emit(self.task_id, False, str(e))


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

        # Checkbox
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

        # Número
        num = QLabel(f"{index}")
        num.setFixedWidth(30)
        num.setFont(QFont("Consolas", 8))
        num.setStyleSheet(f"color: {C_MUTED};")
        num.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Título
        short = title if len(title) <= 65 else title[:63] + "…"
        self.lbl = QLabel(short)
        self.lbl.setFont(QFont("Segoe UI", 9))
        self.lbl.setStyleSheet(f"color: {C_TEXT};")
        self.lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Duración
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

    def is_checked(self):  return self.chk.isChecked()
    def set_checked(self, v): self.chk.setChecked(v)

    @staticmethod
    def _fmt_dur(secs):
        if not secs: return ''
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ─── Tarjeta de descarga ──────────────────────────────────────────────────────
class DownloadCard(QFrame):
    def __init__(self, task_id, title, parent=None):
        super().__init__(parent)
        self.task_id = task_id
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
        self.lbl_status = QLabel("Iniciando…")
        self.lbl_status.setFont(QFont("Consolas", 8))
        self.lbl_status.setStyleSheet(f"color: {C_GOLD}; background: transparent; border: none;")
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
        bot.addWidget(self.lbl_speed, 1)
        bot.addWidget(self.lbl_pct)
        lay.addLayout(bot)

    def update_progress(self, pct, speed, status):
        self.bar.setValue(int(pct))
        self.lbl_pct.setText(f"{pct:.0f}%")
        self.lbl_speed.setText(speed)
        color = C_GOLD if status == 'downloading' else C_ACCENT2
        text  = "Descargando" if status == 'downloading' else "Procesando…"
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def set_done(self):
        self.bar.setValue(100); self.lbl_pct.setText("100%"); self.lbl_speed.setText("")
        self.lbl_status.setText("✓  Listo")
        self.lbl_status.setStyleSheet(f"color: {C_SUCCESS}; background: transparent; border: none;")
        self.bar.setStyleSheet(f"""
            QProgressBar {{ background: {C_BORDER}; border-radius: 2px; border: none; }}
            QProgressBar::chunk {{ background: {C_SUCCESS}; border-radius: 2px; }}
        """)

    def set_error(self, msg):
        self.lbl_status.setText("✗  Error")
        self.lbl_status.setStyleSheet(f"color: {C_ACCENT}; background: transparent; border: none;")
        self.lbl_speed.setText(msg[:70])
        self.lbl_speed.setStyleSheet(f"color: {C_ACCENT}; background: transparent; border: none;")


# ─── Ventana principal ────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YT Downloader")
        self.setMinimumSize(700, 560)
        self.resize(750, 720)
        self._set_icon()
        self._apply_palette()

        self.current_info   = None
        self.download_cards = {}
        self.active_threads = []
        self.playlist_rows  = []
        self.selected_fmt     = 'mp4'
        self.selected_quality = 'best'

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
        outer.setContentsMargins(0,0,0,0)
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
        p.drawRoundedRect(0,0,sz,sz,11,11)
        p.setBrush(QBrush(QColor(C_ACCENT)))
        p.drawEllipse(5,5,sz-10,sz-10)
        p.setBrush(QBrush(QColor("white")))
        cx,cy,h=sz//2,sz//2,10
        p.drawPolygon(QPolygon([QPoint(cx-h+2,cy-h),QPoint(cx-h+2,cy+h),QPoint(cx+h+2,cy)]))
        p.end()
        logo = QLabel(); logo.setPixmap(QPixmap.fromImage(img)); logo.setFixedSize(sz,sz)
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
        self.btn_mp4 = self._pill("MP4 — Video", active=True)
        self.btn_mp3 = self._pill("MP3 — Audio", active=False)
        self.btn_mp4.clicked.connect(lambda: self._select_fmt('mp4'))
        self.btn_mp3.clicked.connect(lambda: self._select_fmt('mp3'))
        fp.addWidget(self.btn_mp4); fp.addWidget(self.btn_mp3); fp.addStretch()
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
            b = self._pill(label, active=(val=="best"), gold=True)
            b.setProperty("quality", val)
            b.clicked.connect(self._on_quality)
            self.quality_pills.append(b); qp.addWidget(b)
        qp.addStretch(); self.qc.addLayout(qp)
        inner.addLayout(self.qc); inner.addStretch()
        lay.addLayout(inner)
        self.main_layout.addWidget(card)

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

    # ── Panel playlist con selección ───────────────────────────────────────
    def _build_playlist_card(self):
        self.pl_card = self._card(); lay = self.pl_card.layout()

        # Título de playlist
        head = QHBoxLayout()
        self.lbl_pl_title = QLabel("Playlist")
        self.lbl_pl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        self.lbl_pl_title.setStyleSheet(f"color: {C_TEXT};")
        self.lbl_pl_count = QLabel("")
        self.lbl_pl_count.setFont(QFont("Consolas", 8))
        self.lbl_pl_count.setStyleSheet(f"color: {C_MUTED};")
        head.addWidget(self.lbl_pl_title, 1); head.addWidget(self.lbl_pl_count)
        lay.addLayout(head)

        # ── Barra de selección ─────────────────────────────────────────
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

        sel_bar.addWidget(self.btn_sel_all)
        sel_bar.addWidget(self.btn_sel_none)
        sel_bar.addWidget(self.btn_sel_invert)
        sel_bar.addStretch()
        sel_bar.addWidget(self.lbl_sel_count)
        lay.addLayout(sel_bar)

        # ── Lista scrollable ───────────────────────────────────────────
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

        # ── Botones acción ─────────────────────────────────────────────
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
        self._sec_lbl(lay, "DESCARGAS")
        self.dl_list_layout = QVBoxLayout(); self.dl_list_layout.setSpacing(8)
        lay.addLayout(self.dl_list_layout)
        btn_f = self._btn_ghost("📁  Abrir carpeta de descargas")
        btn_f.setFixedHeight(36); btn_f.clicked.connect(self.open_folder)
        lay.addWidget(btn_f)
        self.dl_panel.hide(); self.main_layout.addWidget(self.dl_panel)

    # ─── Lógica ───────────────────────────────────────────────────────────

    def fetch_info(self):
        url = self.url_input.text().strip()
        if not url: return
        self.lbl_error.hide()
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

    def _on_fetch_err(self, msg):
        self.btn_fetch.setEnabled(True); self.btn_fetch.setText("Analizar")
        self.lbl_error.setText("Error: " + msg); self.lbl_error.show()

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
        self.lbl_vid_meta.setText(f"{data.get('channel','')}   ·   {self._fmt_dur(data.get('duration',0))}   ·   {vs}")
        if data.get('thumbnail'): self._load_thumb(data['thumbnail'])

    def _render_playlist(self, data):
        # Limpiar
        self.playlist_rows.clear()
        while self.pl_rows_layout.count() > 1:
            item = self.pl_rows_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        self.lbl_pl_title.setText(data['title'])
        self.lbl_pl_count.setText(f"{data['count']} videos")

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
        n = sum(1 for r in self.playlist_rows if r.is_checked())
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

    def start_download(self):
        if not self.current_info: return
        url = self.url_input.text().strip()
        if self.current_info['type'] == 'playlist':
            items = [(r.title_full, r.url) for r in self.playlist_rows if r.is_checked()]
        else:
            items = [(self.current_info['title'], url)]
        if not items: return

        self.dl_panel.show()
        for title, u in items:
            task_id = re.sub(r'[^a-zA-Z0-9]', '_', u)[:40]
            if task_id in self.download_cards: continue
            card = DownloadCard(task_id, title)
            self.download_cards[task_id] = card
            self.dl_list_layout.insertWidget(0, card)
            t = DownloadThread(task_id, u, self.selected_fmt, self.selected_quality)
            t.progress.connect(self._on_dl_progress)
            t.finished.connect(self._on_dl_finished)
            t.start(); self.active_threads.append(t)

    def _on_dl_progress(self, task_id, pct, speed, status):
        card = self.download_cards.get(task_id)
        if card: card.update_progress(pct, speed, status)

    def _on_dl_finished(self, task_id, ok, msg):
        card = self.download_cards.get(task_id)
        if card:
            if ok: card.set_done()
            else:  card.set_error(msg)

    def reset(self):
        self.url_input.clear()
        self.info_card.hide(); self.pl_card.hide(); self.lbl_error.hide()
        self.current_info = None; self.playlist_rows.clear()
        self.thumb_label.setText("🎬"); self.thumb_label.setPixmap(QPixmap())

    def open_folder(self):
        sn = platform.system()
        if sn == 'Darwin':    subprocess.run(['open', DOWNLOAD_DIR])
        elif sn == 'Windows': subprocess.run(['explorer', DOWNLOAD_DIR])
        else:                 subprocess.run(['xdg-open', DOWNLOAD_DIR])

    def _load_thumb(self, url):
        self.net_mgr = QNetworkAccessManager(self)
        self.net_mgr.finished.connect(self._on_thumb)
        self.net_mgr.get(QNetworkRequest(QUrl(url)))

    def _on_thumb(self, reply):
        pix = QPixmap(); pix.loadFromData(bytes(reply.readAll()))
        if not pix.isNull():
            pix = pix.scaled(148, 84, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
            self.thumb_label.setPixmap(pix); self.thumb_label.setText("")

    def _select_fmt(self, fmt):
        self.selected_fmt = fmt
        self.btn_mp4.setStyleSheet(self._pill_ss(fmt=='mp4', gold=False))
        self.btn_mp3.setStyleSheet(self._pill_ss(fmt=='mp3', gold=False))
        # Mostrar/ocultar calidad
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
