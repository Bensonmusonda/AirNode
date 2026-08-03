"""Audit logging for sensitive file operations.

Records delete, rename, upload, and folder-creation actions to a dedicated
audit log file (separate from the main application log) so users can review
what happened and when. Useful for support and trust.
"""

import json
import threading
import time
from pathlib import Path

from paths import get_data_dir


_AUDIT_FILE = get_data_dir() / "airnode-audit.log"
_lock = threading.Lock()


def _write(entry: dict) -> None:
    """Append a single JSON line to the audit log."""
    entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _lock:
            with _AUDIT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def log_delete(path: str, item_type: str, client_ip: str = "") -> None:
    """Log a file or directory deletion."""
    _write({
        "action": "delete",
        "path": path,
        "item_type": item_type,
        "client_ip": client_ip,
    })


def log_batch_delete(paths: list[str], client_ip: str = "") -> None:
    """Log a batch deletion."""
    _write({
        "action": "batch_delete",
        "paths": paths,
        "count": len(paths),
        "client_ip": client_ip,
    })


def log_rename(old_path: str, new_path: str, item_type: str, client_ip: str = "") -> None:
    """Log a file or directory rename."""
    _write({
        "action": "rename",
        "old_path": old_path,
        "new_path": new_path,
        "item_type": item_type,
        "client_ip": client_ip,
    })


def log_upload(path: str, filename: str, client_ip: str = "") -> None:
    """Log a file upload."""
    _write({
        "action": "upload",
        "path": path,
        "filename": filename,
        "client_ip": client_ip,
    })


def log_new_folder(path: str, client_ip: str = "") -> None:
    """Log a folder creation."""
    _write({
        "action": "new_folder",
        "path": path,
        "client_ip": client_ip,
    })