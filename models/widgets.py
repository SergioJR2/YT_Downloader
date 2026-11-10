"""Widgets reutilizables para playlists y elementos de descarga."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    C_ACCENT,
    C_ACCENT2,
    C_BORDER,
    C_GOLD,
    C_MUTED,
    C_SUCCESS,
    C_SURF2,
    C_SURF3,
    C_TEXT,
)

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
        self.lbl_speed.setToolTip("")
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
        first = msg.split('\n')[0]
        self.lbl_speed.setText(first if len(first) <= 95 else first[:92] + '…')
        self.lbl_speed.setToolTip(msg)      # el texto completo, al pasar el mouse
        self.lbl_speed.setStyleSheet(f"color: {C_ACCENT}; background: transparent; border: none;")
