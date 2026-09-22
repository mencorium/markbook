# /markbook/backend/services/drafts.py
"""Marks being typed are autosaved to a small file per assessment, so a crash, a flat battery
or a power cut does not lose a morning's entry. The draft is deleted once the marks are saved.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from ..log import get
from ..paths import drafts_dir

log = get("drafts")


def _path(assessment_id: int) -> Path:
    return drafts_dir() / f"assessment-{assessment_id}.json"


def save_draft(assessment_id: int, kind: str, values: dict) -> Path:
    """values: {student_id: score} for a total, or {student_id: {question_id: score}} for a paper."""
    payload = {"assessment_id": assessment_id, "kind": kind, "saved_at": dt.datetime.now().isoformat(timespec="seconds"),
               "values": {str(sid): ({str(q): v for q, v in row.items()} if isinstance(row, dict) else row) for sid, row in values.items()}}
    p = _path(assessment_id)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(p)                      # written then renamed, so a draft is never half-written
    return p


def load_draft(assessment_id: int) -> dict | None:
    """Returns {'kind', 'saved_at' (datetime), 'values' with integer keys} or None."""
    p = _path(assessment_id)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        values = {int(sid): ({int(q): v for q, v in row.items()} if isinstance(row, dict) else row)
                  for sid, row in raw.get("values", {}).items()}
        return {"kind": raw.get("kind", "total"), "saved_at": dt.datetime.fromisoformat(raw["saved_at"]), "values": values}
    except (ValueError, KeyError, OSError) as e:
        log.warning("ignoring unreadable draft %s: %s", p.name, e)
        return None


def delete_draft(assessment_id: int) -> None:
    _path(assessment_id).unlink(missing_ok=True)


def prune(days: int = 60) -> int:
    """Drafts left behind by deleted assessments eventually go."""
    cutoff, n = time.time() - days * 86400, 0
    for f in drafts_dir().glob("assessment-*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            n += 1
    return n