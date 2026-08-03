#!/usr/bin/env python3
"""Convenience build script for creating the AirNode standalone executable.

This wraps PyInstaller so you don't have to remember the spec file name.

Usage:
    python build.py                     # single-file dist/AirNode-<version>.exe
    python build.py --onedir            # folder build (faster startup, dev testing)
    python build.py --version 1.1.0     # override the version from version.py

Prerequisites:
    pip install -r requirements-dev.txt
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Import the version constant (works both from source and when frozen)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from version import VERSION  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "build.spec"
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"


def check_dependencies() -> None:
    """Verify every package in requirements.txt is importable before building.

    This gives a clear error message instead of a cryptic PyInstaller failure
    when a new dependency was added to requirements.txt but not installed.
    """
    missing = []
    with open(REQUIREMENTS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip version specifiers: fastapi==0.138.1 -> fastapi
            pkg = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
            # Strip extras: uvicorn[standard] -> uvicorn
            if '[' in pkg:
                pkg = pkg.split('[')[0]
            # Normalize package name (e.g. python-multipart -> python_multipart)
            module_name = pkg.replace('-', '_')
            # Known package-name -> import-module mappings
            import_aliases = {
                "Pillow": "PIL",
                "python-dotenv": "dotenv",
                "python-multipart": "multipart",
            }
            try:
                __import__(module_name)
            except ImportError:
                # Try known aliases first
                alias = import_aliases.get(pkg)
                if alias:
                    try:
                        __import__(alias)
                        continue
                    except ImportError:
                        pass
                # Fallback: try last part of hyphenated name
                alias = pkg.split('-')[-1] if '-' in pkg else None
                if alias and alias != module_name:
                    try:
                        __import__(alias)
                        continue
                    except ImportError:
                        pass
                missing.append(pkg)

    if missing:
        print("Missing dependencies detected. Install them first:")
        for pkg in missing:
            print(f"  pip install {pkg}")
        sys.exit(1)


def generate_version_info(version: str) -> Path:
    """Generate a PyInstaller version-info file for Windows exe metadata.

    This makes the version visible in Windows Explorer:
    right-click AirNode.exe -> Properties -> Details.
    """
    parts = version.split(".")
    # Pad to 4 parts: 1.0.0 -> 1,0,0,0
    while len(parts) < 4:
        parts.append("0")
    major, minor, build, revision = (int(p) for p in parts[:4])

    version_info = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {build}, {revision}),
    prodvers=({major}, {minor}, {build}, {revision}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'AirNode'),
         StringStruct(u'FileDescription', u'AirNode - Local Network File Explorer'),
         StringStruct(u'FileVersion', u'{version}'),
         StringStruct(u'InternalName', u'AirNode'),
         StringStruct(u'LegalCopyright', u'MIT License'),
         StringStruct(u'OriginalFilename', u'AirNode-{version}.exe'),
         StringStruct(u'ProductName', u'AirNode'),
         StringStruct(u'ProductVersion', u'{version}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    info_path = BUILD_DIR / "version_info.txt"
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(version_info, encoding="utf-8")
    return info_path


def write_sha256(exe_path: Path) -> Path:
    """Write a .sha256 checksum file next to the built executable."""
    sha = hashlib.sha256(exe_path.read_bytes()).hexdigest()
    checksum_path = exe_path.with_suffix(".exe.sha256")
    checksum_path.write_text(f"{sha}  {exe_path.name}\n", encoding="utf-8")
    return checksum_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the AirNode executable.")
    parser.add_argument(
        "--version",
        default=VERSION,
        help=f"Version to build (default: {VERSION} from version.py)",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build a folder instead of a single file (faster startup for dev testing).",
    )
    parser.add_argument(
        "--no-icon",
        action="store_true",
        help="Build without the app icon.",
    )
    args = parser.parse_args()

    version = args.version

    # Check that PyInstaller is installed
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed.")
        print("Install build dependencies with:  pip install -r requirements-dev.txt")
        sys.exit(1)

    # Verify all production dependencies are importable
    check_dependencies()

    # Clean previous build artifacts for a fresh build
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            print(f"Cleaning {d.name}/ ...")
            shutil.rmtree(d)

    # Generate Windows version metadata
    version_info_path = generate_version_info(version)
    print(f"Version: {version}")

    # Set environment variables for the spec file
    # (PyInstaller does not allow --onefile/--version-file when using a .spec file)
    os.environ["AIRNODE_VERSION_FILE"] = str(version_info_path)
    os.environ["AIRNODE_ONEFILE"] = "0" if args.onedir else "1"

    # Build with PyInstaller using the spec file
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
    ]
    if args.onedir:
        print("Building AirNode (folder mode) with PyInstaller ...")
    else:
        print("Building AirNode.exe with PyInstaller ...")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print("\nBuild failed. Check the output above for errors.")
        sys.exit(1)

    # Locate the built executable
    if args.onedir:
        exe_path = DIST_DIR / "AirNode" / "AirNode.exe"
    else:
        exe_path = DIST_DIR / "AirNode.exe"

    if not exe_path.exists():
        print("\nBuild completed but AirNode.exe was not found in dist/. Check for errors.")
        sys.exit(1)

    # Rename to versioned filename
    versioned_exe = DIST_DIR / f"AirNode-{version}.exe"
    if args.onedir:
        # For onedir, rename the folder instead
        versioned_dir = DIST_DIR / f"AirNode-{version}"
        if versioned_dir.exists():
            shutil.rmtree(versioned_dir)
        exe_path.parent.rename(versioned_dir)
        versioned_exe = versioned_dir / "AirNode.exe"
    else:
        exe_path.rename(versioned_exe)

    # Write SHA-256 checksum
    checksum_path = write_sha256(versioned_exe)

    size_mb = versioned_exe.stat().st_size / (1024 * 1024)
    print(f"\nBuild successful!")
    print(f"  Output:   {versioned_exe}")
    print(f"  Size:     {size_mb:.1f} MB")
    print(f"  Checksum: {checksum_path.name}")
    print(f"\nShare AirNode-{version}.exe with your friend. No Python installation needed.")


if __name__ == "__main__":
    main()