# /markbook/backend/services/backup.py
"""Backups with pg_dump / pg_restore, so a teacher never needs a terminal.

A backup is a single compressed .dump file. Restoring replaces everything currently
in the database with the contents of that file.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
from dataclasses import dataclass
from glob import glob
from pathlib import Path

from sqlalchemy.engine import make_url

from ..db import engine
from ..log import get
from ..paths import backups_dir

log = get("backup")
SUFFIX = ".dump"


class BackupError(RuntimeError):
    """Message is written for the person using the app."""


@dataclass
class BackupFile:
    path: Path
    when: dt.datetime
    size: int

    @property
    def size_text(self) -> str:
        kb = self.size / 1024
        return f"{kb:.0f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"


def find_tool(name: str) -> str | None:
    """pg_dump/pg_restore from PATH, or the usual install locations on Linux and Windows."""
    found = shutil.which(name)
    if found:
        return found
    patterns = [f"/usr/lib/postgresql/*/bin/{name}", f"/usr/local/pgsql/bin/{name}", f"/opt/homebrew/bin/{name}",
                rf"C:\Program Files\PostgreSQL\*\bin\{name}.exe", rf"C:\Program Files (x86)\PostgreSQL\*\bin\{name}.exe"]
    for pattern in patterns:
        hits = sorted(glob(pattern))
        if hits:
            return hits[-1]
    return None


def tools_available() -> bool:
    return bool(find_tool("pg_dump") and find_tool("pg_restore"))


def _conn() -> tuple[list[str], dict, str]:
    """Always the database this app is connected to — not whatever the config file says."""
    url = make_url(str(engine().url.render_as_string(hide_password=False)))
    args = ["-h", url.host or "localhost", "-p", str(url.port or 5432), "-U", url.username or "markbook"]
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = url.password
    return args, env, url.database or "markbook"


def _run(tool: str, args: list[str], env: dict, what: str) -> None:
    try:
        r = subprocess.run([tool, *args], env=env, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as e:
        raise BackupError(f"{Path(tool).name} could not be started.") from e
    except subprocess.TimeoutExpired as e:
        raise BackupError(f"{what} took too long and was stopped.") from e
    if r.returncode != 0:
        detail = (r.stderr or "").strip().splitlines()
        log.error("%s failed: %s", what, " | ".join(detail[-5:]))
        raise BackupError(f"{what} failed.\n\n{detail[-1] if detail else 'No details were reported.'}")


def backup(folder: str | Path | None = None, label: str = "") -> Path:
    """Write a timestamped backup and return its path."""
    tool = find_tool("pg_dump")
    if not tool:
        raise BackupError("pg_dump was not found. It comes with PostgreSQL — add its bin folder to PATH, then try again.")
    folder = Path(folder) if folder else backups_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"markbook-{dt.datetime.now():%Y-%m-%d-%H%M%S}{('-' + label) if label else ''}"
    target = folder / f"{stem}{SUFFIX}"
    n = 2
    while target.exists():                   # two backups in the same second must not overwrite each other
        target = folder / f"{stem}-{n}{SUFFIX}"
        n += 1
    args, env, database = _conn()
    _run(tool, [*args, "-d", database, "-F", "c", "-f", str(target)], env, "Backup")
    log.info("backup written: %s (%d bytes)", target, target.stat().st_size)
    return target


def restore(path: str | Path) -> None:
    """Replace the current contents of the database with this backup."""
    tool = find_tool("pg_restore")
    if not tool:
        raise BackupError("pg_restore was not found. It comes with PostgreSQL — add its bin folder to PATH, then try again.")
    path = Path(path)
    if not path.exists():
        raise BackupError(f"{path.name} no longer exists.")
    args, env, database = _conn()
    _run(tool, [*args, "-d", database, "--clean", "--if-exists", "--no-owner", "--single-transaction", str(path)], env, "Restore")
    log.info("restored from %s", path)


def list_backups(folder: str | Path | None = None) -> list[BackupFile]:
    folder = Path(folder) if folder else backups_dir()
    if not folder.exists():
        return []
    out = []
    for f in folder.glob(f"*{SUFFIX}"):
        st = f.stat()
        out.append(BackupFile(f, dt.datetime.fromtimestamp(st.st_mtime), st.st_size))
    return sorted(out, key=lambda b: b.when, reverse=True)


def prune(keep: int = 20, folder: str | Path | None = None) -> int:
    """Keep the newest few backups; delete the rest."""
    old = list_backups(folder)[keep:]
    for b in old:
        b.path.unlink(missing_ok=True)
    if old:
        log.info("pruned %d old backups", len(old))
    return len(old)