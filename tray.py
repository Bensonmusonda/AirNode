"""System tray icon integration for AirNode.

Provides a background tray icon (Windows notification area) with quick
actions: Open Settings (default on left-click), Open Browser, Show QR Code,
Reset PIN, Toggle Autostart, Restart, and Exit.

Requires ``pystray`` and ``Pillow``. If either is unavailable, tray
functionality is gracefully skipped (the app still runs normally).
"""

import sys
import threading
import webbrowser

from airnode_auth import delete_auth_config, has_auth_config
from airnode_config import load_config
from autostart import is_autostart_enabled, toggle_autostart as toggle_autostart_registry


def get_tray_image():
    """Create a simple tray icon image. Returns None if Pillow is missing."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (4, 4, 60, 60),
        radius=14,
        fill=(59, 130, 246, 255),
    )
    draw.polygon(
        [
            (32, 14),
            (22, 50),
            (28, 50),
            (32, 36),
            (36, 50),
            (42, 50),
        ],
        fill=(255, 255, 255, 255),
    )
    draw.polygon(
        [(30, 32), (32, 24), (34, 32)],
        fill=(255, 255, 255, 255),
    )
    return img


def run_tray(on_restart=None, on_exit=None):
    """Run the system tray icon in a background thread.

    Args:
        on_restart: Optional callback invoked when the user selects Restart.
        on_exit: Optional callback invoked when the user selects Exit.
    """
    try:
        import pystray
        from pystray import MenuItem as item
    except ImportError:
        return None

    image = get_tray_image()
    if image is None:
        return None

    def base_url() -> str:
        return f"http://localhost:{load_config().port}"

    def open_settings(icon, menu_item=None):
        webbrowser.open(f"{base_url()}/settings")

    def open_browser(icon, menu_item=None):
        webbrowser.open(base_url())

    def show_qr(icon, menu_item=None):
        webbrowser.open(f"{base_url()}/connect")

    def reset_pin(icon, menu_item=None):
        if has_auth_config():
            delete_auth_config()
        webbrowser.open(f"{base_url()}/setup")

    def restart_app(icon, menu_item=None):
        icon.stop()
        if on_restart:
            on_restart()

    def exit_app(icon, menu_item=None):
        icon.stop()
        if on_exit:
            on_exit()

    def toggle_autostart(icon, menu_item=None):
        new_state, _ = toggle_autostart_registry()
        _refresh_menu(icon)

    def _refresh_menu(icon):
        """Rebuild the icon's menu so labels reflect live config state."""
        try:
            icon.menu = build_menu()
            icon.update_menu()
            icon.visible = True
        except Exception:
            pass

    def build_menu():
        """Construct the menu based on live config state."""
        cfg = load_config()
        autostart_state = "On" if is_autostart_enabled() else "Off"
        port = cfg.port

        return pystray.Menu(
            # Default item (single left-click opens Settings in the browser)
            item(f"Open Settings (:{port})", open_settings, default=True),
            item(f"Open Browser (:{port})", open_browser),
            item("Show QR Code", show_qr),
            item("Reset PIN", reset_pin),
            item(f"Autostart: {autostart_state}", toggle_autostart),
            item("Restart", restart_app),
            item("Exit", exit_app),
        )

    try:
        icon = pystray.Icon(
            "AirNode",
            image,
            f"AirNode - :{load_config().port}",
            build_menu(),
        )
        # Keep a ref so pystray doesn't GC the icon unexpectedly
        threading.current_thread().airnode_icon = icon
        icon.run()
    except Exception:
        return None
    return icon


def start_tray_thread(on_restart=None, on_exit=None):
    """Start the tray icon in a daemon thread. Returns the thread or None."""
    try:
        import pystray  # noqa: F401 - import check
    except ImportError:
        return None

    if not get_tray_image():
        return None

    def _runner():
        return run_tray(on_restart=on_restart, on_exit=on_exit)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return thread