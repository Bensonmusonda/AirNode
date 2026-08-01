#!/usr/bin/env python3
"""Convenience build script for creating the AirNode standalone executable.

This wraps PyInstaller so you don't have to remember the spec file name.

Usage:
    python build.py

Prerequisites:
    pip install -r requirements-dev.txt
"""

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "build.spec"


def main() -> None:
    # Check that PyInstaller is installed
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed.")
        print("Install build dependencies with:  pip install -r requirements-dev.txt")
        sys.exit(1)

    # Clean previous build artifacts for a fresh build
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            print(f"Cleaning {d.name}/ ...")
            shutil.rmtree(d)

    print("Building AirNode.exe with PyInstaller ...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm"],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        print("\nBuild failed. Check the output above for errors.")
        sys.exit(1)

    exe_path = DIST_DIR / "AirNode.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\nBuild successful!")
        print(f"  Output: {exe_path}")
        print(f"  Size:   {size_mb:.1f} MB")
        print(f"\nShare AirNode.exe with your friend. No Python installation needed.")
    else:
        print("\nBuild completed but AirNode.exe was not found in dist/. Check for errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()