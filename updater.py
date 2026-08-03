"""Auto-update check for AirNode.

Queries the GitHub Releases API for the latest published release and
compares it with the running version. AirNode never downloads or
installs updates automatically — it only tells the user when a new
version is available and links to the download page.
"""

import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from logging_config import get_logger
from paths import get_data_dir
from version import VERSION


logger = get_logger(__name__)

REPO = "Bensonmusonda/AirNode"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
# Version prefixes to strip before comparing (e.g. "v1.0.0" -> "1.0.0")
_VERSION_PREFIXES = ("v", "V")

_CACHE_FILE = get_data_dir() / ".airnode_update_cache.json"
_CACHE_TTL = 6 * 60 * 60  # 6 hours — don't hammer the GitHub API on every page load


@dataclass
class UpdateInfo:
    """Result of an update check."""
    available: bool
    latest_version: str = ""
    current_version: str = VERSION
    url: str = ""
    notes: str = ""
    published_at: str = ""
    error: str = ""
    from_cache: bool = False


def _normalize_version(version: str) -> str:
    """Strip leading 'v'/'V' so 'v1.2.3' compares as '1.2.3'."""
    version = version.strip()
    for prefix in _VERSION_PREFIXES:
        if version.startswith(prefix):
            version = version[1:]
            break
    return version


def _version_tuple(version: str) -> tuple:
    """Convert a dotted version string into a comparable tuple."""
    parts = []
    for part in _normalize_version(version).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        try:
            parts.append(int(digits) if digits else 0)
        except ValueError:
            parts.append(0)
    # Pad to at least 3 parts so 1.0 == 1.0.0
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _read_cache() -> dict:
    try:
        if _CACHE_FILE.exists() and (time.time() - _CACHE_FILE.stat().st_mtime) < _CACHE_TTL:
            with _CACHE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _write_cache(data: dict) -> None:
    try:
        with _CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("Failed to write update cache: %s", e)


def check_for_update(force: bool = False, timeout: float = 5.0) -> UpdateInfo:
    """Check GitHub Releases for a newer AirNode version.

    Results are cached for 6 hours. Pass ``force=True`` to bypass the cache
    (used by an explicit "Check for updates" button).
    """
    if not force:
        cached = _read_cache()
        if cached:
            try:
                return UpdateInfo(**cached)
            except TypeError:
                pass

    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"AirNode/{VERSION}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        info = UpdateInfo(
            available=False,
            error=f"Could not reach GitHub: {e}",
        )
        _write_cache({
            "available": False,
            "error": info.error,
            "from_cache": False,
        })
        return info

    latest_tag = str(data.get("tag_name", ""))
    latest_version = _normalize_version(latest_tag)
    url = str(data.get("html_url", f"https://github.com/{REPO}/releases/latest"))
    notes = str(data.get("body", ""))[:500]
    published_at = str(data.get("published_at", ""))

    available = bool(latest_version) and _version_tuple(latest_version) > _version_tuple(VERSION)

    info = UpdateInfo(
        available=available,
        latest_version=latest_version,
        current_version=VERSION,
        url=url,
        notes=notes,
        published_at=published_at,
        error="",
        from_cache=False,
    )
    _write_cache({
        "available": available,
        "latest_version": latest_version,
        "current_version": VERSION,
        "url": url,
        "notes": notes,
        "published_at": published_at,
        "error": "",
        "from_cache": False,
    })
    return info