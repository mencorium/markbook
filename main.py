# /markbook/main.py
"""Start Markbook: python main.py   (add --sample to load the sample class on first run)"""
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from backend import log, migrate, seed
from backend.services import drafts


def main() -> int:
    log.setup()
    log.install_excepthook()
    logger = log.get("app")
    app = QApplication(sys.argv)
    app.setApplicationName("Markbook")
    from frontend import theme
    theme.apply(app)
    try:
        revision = migrate.upgrade()            # creates the schema, or brings an older one up to date
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