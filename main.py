# /markbook/main.py
"""Start Markbook: python main.py   (add --sample to load the sample class on first run)"""
import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from backend import log, migrate, paths, seed
from backend.services import drafts


def _prepare_database(logger):
    """Migrate the database. On a fresh install with no .env, ask for the connection first."""
    from sqlalchemy.exc import OperationalError

    from backend import db
    from backend.paths import install_dir
    try:
        return migrate.upgrade()
    except OperationalError as e:
        logger.warning("could not reach the database: %s", str(e).splitlines()[0])
        from frontend.db_setup import ask
        url = ask(f"Markbook could not reach the database set in {install_dir() / '.env'}.")
        if not url:
            raise
        db.init_engine(url)                     # use the connection just entered, without a restart
        return migrate.upgrade()


def main() -> int:
    log.setup()
    log.install_excepthook()
    logger = log.get("app")
    app = QApplication(sys.argv)
    app.setApplicationName("Markbook")
    app.setOrganizationName("Markbook")
    icon = paths.icon_path()
    if icon:
        app.setWindowIcon(QIcon(str(icon)))         # title bar, taskbar and every dialog
    if os.name == "nt":                             # without this Windows groups the app under python.exe
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Markbook.Desktop")
        except Exception:  # noqa: BLE001
            pass
    from frontend import theme
    theme.apply(app)
    try:
        revision = _prepare_database(logger)    # creates the schema, or brings an older one up to date
        logger.info("started at database revision %s", revision)
    except migrate.MigrationError as e:         # already written for the person reading it
        logger.error("could not prepare the database: %s", e)
        QMessageBox.critical(None, "Markbook", f"{e}\n\nDetails were written to {log.log_path()}")
        return 1
    except KeyboardInterrupt:
        logger.warning("startup interrupted before the database was ready")
        return 1
    except Exception as e:  # noqa: BLE001
        logger.exception("could not prepare the database")
        QMessageBox.critical(None, "Markbook", f"Could not open the database.\n\n{e}\n\n"
                                               f"Check that PostgreSQL is running and DATABASE_URL in your .env file is correct.\n"
                                               f"Details were written to {log.log_path()}")
        return 1
    drafts.prune()
    from backend.services.terms import assign_missing
    moved = assign_missing()
    if moved:
        logger.info("placed %d assessment(s)/register(s) into a term", moved)
    if "--sample" in sys.argv:
        seed.add_sample()
    from frontend.main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())