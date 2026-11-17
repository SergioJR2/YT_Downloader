"""Punto de entrada de YT Downloader."""
import sys

from PyQt6.QtWidgets import QApplication

from models.logging_setup import setup_logging
from models.window import MainWindow


def main():
    setup_logging()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
