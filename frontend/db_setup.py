# /markbook/frontend/db_setup.py
"""First-run database setup.

An installed copy on a new computer has no .env yet, so instead of an error the app asks for the
PostgreSQL connection, tests it, and writes the .env beside markbook.exe.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QSpinBox, QVBoxLayout)
from sqlalchemy import create_engine, text

from backend.paths import install_dir


def url_for(host: str, port: int, database: str, user: str, password: str) -> str:
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


class DatabaseDialog(QDialog):
    def __init__(self, parent=None, problem: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Connect Markbook to PostgreSQL")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        intro = QLabel("Markbook keeps your marks in a PostgreSQL database. Enter the connection here — "
                       "it is saved next to the program, so you are only asked once."
                       + (f"\n\n{problem}" if problem else ""))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.host = QLineEdit("localhost")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(5432)
        self.database = QLineEdit("markbook")
        self.user = QLineEdit("markbook")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        for text_, widget in [("Server", self.host), ("Port", self.port), ("Database", self.database),
                              ("User", self.user), ("Password", self.password)]:
            form.addRow(text_, widget)
        lay.addLayout(form)
        hint = QLabel("On this computer the defaults usually work once you have created the database:\n"
                      "  CREATE USER markbook WITH PASSWORD 'markbook';\n"
                      "  CREATE DATABASE markbook OWNER markbook;")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        lay.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Test and save")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def url(self) -> str:
        return url_for(self.host.text().strip() or "localhost", self.port.value(), self.database.text().strip(),
                       self.user.text().strip(), self.password.text())

    def _save(self) -> None:
        url = self.url()
        try:
            engine = create_engine(url, connect_args={"connect_timeout": 5})
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            engine.dispose()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Markbook", f"Could not connect.\n\n{e}")
            return
        write_env(url)
        self.accept()


def write_env(url: str) -> Path:
    path = install_dir() / ".env"
    lines = [f"DATABASE_URL={url}", "DEFAULT_COUNTRY_CODE=255", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def ask(problem: str = "") -> str | None:
    """Show the dialog; returns the working URL, or None if the person cancelled."""
    d = DatabaseDialog(problem=problem)
    return d.url() if d.exec() else None