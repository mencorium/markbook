# /markbook_desktop/markbook.spec
"""PyInstaller build.  Run:  pyinstaller markbook.spec --noconfirm

Produces dist/Markbook/markbook.exe (a folder build: faster to start and easier for the
installer to ship than a single file). The migrations, alembic.ini and the icon travel with it,
so a built copy can create and upgrade its own database.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
ICON = ROOT / "assets" / "markbook.ico"

datas = [
    (str(ROOT / "migrations"), "migrations"),        # schema history: needed on every start
    (str(ROOT / "alembic.ini"), "."),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "README.md"), "."),
]
datas += collect_data_files("reportlab")             # the built-in PDF fonts
datas += collect_data_files("matplotlib", subdir="mpl-data")

hiddenimports = [
    # migrations/env.py ships as data, so PyInstaller cannot see what it imports
    "logging.config", "logging.handlers", "backend.models", "backend.config",
    "psycopg", "psycopg_binary", "psycopg.pq",
    "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_agg",
    *collect_submodules("alembic"),                  # migration scripts are imported by name
]

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6", "PyQt5", "IPython", "jupyter", "pytest", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="markbook",
    icon=str(ICON) if ICON.exists() else None,
    console=False,                                   # no black console window behind the app
    debug=False,
    strip=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Markbook",
)
