"""Windows autostart management via the HKCU Run registry key.

Using the current-user Run key avoids the ``schtasks`` permission problems
(which require the user to be a local admin or triggered Application
Control policy denials). This works for all standard users.
"""

import subprocess
import sys
import winreg

from airnode_config import load_config, save_config


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AirNode"


def get_exe_path() -> str:
    """The command used to launch AirNode at logon."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # Development mode: run with the venv python
    return f'"{sys.executable}" "{sys.argv[0]}"'


def is_autostart_enabled() -> bool:
    """Check if the AirNode Run key currently exists."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def enable_autostart() -> bool:
    """Add the Run key. Returns True on success."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, get_exe_path())
        # Sync config flag
        cfg = load_config()
        cfg.autostart = True
        save_config(cfg)
        return True
    except OSError:
        return False


def disable_autostart() -> bool:
    """Remove the Run key. Returns True on success."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        # Sync config flag
        cfg = load_config()
        cfg.autostart = False
        save_config(cfg)
        return True
    except OSError:
        return False


def toggle_autostart() -> tuple[bool, str]:
    """Toggle autostart. Returns (new_state, message)."""
    if is_autostart_enabled():
        if disable_autostart():
            return False, "Autostart disabled."
        return True, "Failed to disable autostart."
    else:
        if enable_autostart():
            return True, "Autostart enabled."
        return False, "Failed to enable autostart."