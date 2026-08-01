"""Path resolution helpers that work both in development and when frozen
with PyInstaller.

When PyInstaller bundles the app into a single executable:
- **Resources** (templates, static files) are extracted to a temporary
  directory at runtime, accessible via ``sys._MEIPASS``.
- **Data files** (auth config, cache, upload temp, logs) must persist between
  runs, so they live next to the executable itself.

In normal development mode both resolve to the project directory.
"""

import sys
from pathlib import Path


def is_frozen() -> bool:
    """Return True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_resource_dir() -> Path:
    """Directory containing bundled read-only resources (templates, static).

    In a frozen exe this is the temporary extraction directory (``_MEIPASS``).
    In development it is the project root (the directory of this file).
    """
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    """Directory for persistent runtime data (auth config, cache, uploads).

    In a frozen exe this is the folder containing the executable, so state
    survives restarts. In development it is the project root.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent