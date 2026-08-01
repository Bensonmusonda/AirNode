# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building AirNode into a standalone Windows executable.

Usage:
    pyinstaller build.spec
    # or: python build.py
"""

import os
from PyInstaller.utils.hooks import collect_submodules

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
        "paths",
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
)