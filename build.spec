# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building AirNode into a standalone Windows executable.

Usage:
    pyinstaller build.spec
    # or: python build.py

Environment variables (set by build.py):
    AIRNODE_VERSION_FILE  - path to the version-info file for Windows metadata
    AIRNODE_ONEFILE       - set to "1" for single-file exe, "0" for onedir
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# Import the version constant from version.py
sys.path.insert(0, str(Path(SPECPATH).resolve()))
from version import VERSION  # noqa: E402

block_cipher = None

# Collect all uvicorn/zeroconf submodules that are loaded dynamically
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("zeroconf")
    + [
        # FastAPI / Starlette dynamic deps
        "multipart",
        "aiofiles",
        "jinja2",
        # QR code image factory
        "qrcode",
        "qrcode.image.svg",
        # Our own modules
        "main",
        "airnode_auth",
        "audit",
        "logging_config",
        "paths",
        "version",
    ]
)

a = Analysis(
    ["airnode_server.py"],
    pathex=[],
    binaries=[],
    datas=[
        # Templates and static files are bundled as read-only resources
        ("templates", "templates"),
        ("static", "static"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude dev-only modules to reduce exe size
        "pytest",
        "pip",
        "setuptools",
        "distutils",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Read version info file path from environment (set by build.py)
version_file = os.environ.get("AIRNODE_VERSION_FILE", "")

# Determine onefile vs onedir from environment (set by build.py)
onefile = os.environ.get("AIRNODE_ONEFILE", "1") == "1"

if onefile:
    # Single-file executable: everything bundled into one .exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="AirNode",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,  # Keep console so the user can see URLs and startup messages
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,  # Add an .ico path here if you have one
        version=version_file if version_file else None,
    )
else:
    # Folder build: faster startup, useful for development
    exe = EXE(
        pyz,
        a.scripts,
        [],
        [],
        [],
        [],
        name="AirNode",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
        version=version_file if version_file else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="AirNode",
    )