"""JSON files and safe paths."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

# The API and the pipeline thread read and write job.json at the same time.
_lock = threading.Lock()
# On Windows another process (a virus scanner, the search indexer, an editor that has the file open) can hold
# the file for a moment, and the replace is refused ("Access is denied"). That failed a whole render at its
# voice step on 2026-11-16, so the replace is tried again a few times before it gives up.
REPLACE_ATTEMPTS = 10
REPLACE_WAIT_SECONDS = 0.1


def read_json(path: Path) -> Any:
    with _lock:
        return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with _lock:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        for attempt in range(1, REPLACE_ATTEMPTS + 1):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS:
                    raise
                time.sleep(REPLACE_WAIT_SECONDS * attempt)


def safe_join(base: Path, relative: str) -> Path:
    """Join a user-supplied relative path, refusing anything that escapes base."""
    base = base.resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"Path escapes its folder: {relative}")
    return target
