# /markbook_desktop/main.py
"""Start Markbook: python main.py   (add --sample to load the sample class on first run)"""
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from backend import seed
from backend.db import create_schema


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Markbook")
    from frontend import theme
    theme.apply(app)
    try:
        create_schema()
    except Exception as e:  # noqa: BLE001
        QMessageBox.critical(None, "Markbook", f"Could not connect to PostgreSQL.\n\n{e}\n\nCheck DATABASE_URL in your .env file.")
        return 1
    if "--sample" in sys.argv:
        seed.add_sample()
    from frontend.main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())