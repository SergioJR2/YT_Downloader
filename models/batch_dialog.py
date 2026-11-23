"""Cuadro para pegar (o cargar desde un .txt) una lista de enlaces."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .downloads import parse_url_list
from .theme import C_ACCENT, C_BG, C_BORDER, C_MUTED, C_SURF2, C_SURF3, C_TEXT


class UrlListDialog(QDialog):
    """Caja grande donde pegar un enlace por línea. Muestra cuántos son válidos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Descargar varios enlaces")
        self.setMinimumSize(560, 420)
        self.setStyleSheet(f"""
            QDialog {{ background: {C_BG}; }}
            QLabel {{ color: {C_TEXT}; }}
            QPlainTextEdit {{ background: {C_SURF2}; border: 1px solid {C_BORDER};
                border-radius: 9px; color: {C_TEXT}; padding: 8px; }}
            QPlainTextEdit:focus {{ border-color: {C_ACCENT}; }}
            QPushButton {{ background: transparent; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 8px; padding: 0 16px; }}
            QPushButton:hover {{ background: {C_SURF3}; border-color: {C_MUTED}; }}
            QPushButton:disabled {{ color: {C_MUTED}; }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        intro = QLabel("Pega los enlaces, uno por línea. Pueden ser de YouTube, TikTok, "
                       "Instagram, etc.; si alguno es una playlist se agregan sus videos. "
                       "Las líneas que empiezan con # se ignoran.")
        intro.setWordWrap(True)
        intro.setFont(QFont("Segoe UI", 9))
        lay.addWidget(intro)

        self.edit = QPlainTextEdit()
        self.edit.setFont(QFont("Consolas", 9))
        self.edit.setPlaceholderText("https://www.youtube.com/watch?v=...\n"
                                     "https://www.tiktok.com/@usuario/video/...\n"
                                     "https://www.youtube.com/playlist?list=...")
        self.edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.edit.textChanged.connect(self._update_count)
        lay.addWidget(self.edit, 1)

        self.lbl_count = QLabel("")
        self.lbl_count.setFont(QFont("Consolas", 8))
        self.lbl_count.setStyleSheet(f"color: {C_MUTED};")
        lay.addWidget(self.lbl_count)

        row = QHBoxLayout()
        btn_file = QPushButton("📄  Cargar desde .txt…")
        btn_file.setFixedHeight(34)
        btn_file.clicked.connect(self._load_file)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("↓  Agregar a la cola")
        self.btn_ok.setFixedHeight(34)
        self.btn_ok.setDefault(True)
        self.btn_ok.setStyleSheet(
            f"QPushButton {{ background: {C_ACCENT}; color: white; border: none; "
            f"border-radius: 8px; padding: 0 18px; font-weight: bold; }}"
            f"QPushButton:disabled {{ background: {C_BORDER}; color: {C_MUTED}; }}")
        self.btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_file)
        row.addStretch()
        row.addWidget(btn_cancel)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)
        self._update_count()

    def _update_count(self):
        urls, invalid = parse_url_list(self.edit.toPlainText())
        text = f"{len(urls)} enlace{'s' if len(urls) != 1 else ''} válido{'s' if len(urls) != 1 else ''}"
        if invalid:
            text += f"  ·  {len(invalid)} línea{'s' if len(invalid) != 1 else ''} sin http(s):// (se ignorarán)"
        self.lbl_count.setText(text)
        self.btn_ok.setEnabled(bool(urls))

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Archivo con enlaces", "",
            "Archivos de texto (*.txt);;Todos los archivos (*)")
        if not path:
            return
        try:
            with open(path, encoding='utf-8-sig', errors='replace') as f:
                content = f.read()
        except OSError as e:
            QMessageBox.warning(self, "No se pudo leer el archivo", str(e))
            return
        current = self.edit.toPlainText().rstrip()
        self.edit.setPlainText((current + "\n" if current else "") + content)

    def text(self):
        return self.edit.toPlainText()
