"""Cast-to-TV support for AirNode (Phase 6.5).

Chromecast support uses `pychromecast` (optional — gracefully degrades if not
installed). DLNA support is limited to format-compatible MP4/WebM URLs that
the cast target fetches directly from AirNode.

All functions are fully guarded and never raise.
"""

import threading
import time

from logging_config import get_logger

logger = get_logger(__name__)

_CAST_LOCK = threading.Lock()
_KNOWN_CHROMECASTS = []

try:
    import pychromecast
    from pychromecast.controllers.media import MediaStatusListener
    _HAS_CHROMECAST = True
except ImportError:
    _HAS_CHROMECAST = False

# ==============================================================================
# Discovery
# ==============================================================================

def discover_chromecasts(timeout: float = 3.0) -> list[dict]:
    """Scan the network for Chromecast-compatible devices.

    Returns a list of dicts:
        [{"id", "name", "host", "port", "model", "type": "chromecast"}, ...]
    """
    global _KNOWN_CHROMECASTS
    if not _HAS_CHROMECAST:
        return []

    try:
        chromecasts, browser = pychromecast.get_chromecasts(timeout=timeout)
        devices = []
        for cc in chromecasts:
            try:
                devices.append({
                    "id": cc.uuid.uuid if cc.uuid else str(cc.cast_info.uuid),
                    "name": cc.cast_info.friendly_name if cc.cast_info else cc.name,
                    "host": cc.cast_info.host if cc.cast_info else "",
                    "port": cc.cast_info.port if cc.cast_info else 8009,
                    "model": cc.cast_info.model_name if cc.cast_info else "",
                    "type": "chromecast",
                })
            except Exception:
                continue
        _KNOWN_CHROMECASTS = chromecasts
        try:
            browser.stop_discovery()
        except Exception:
            pass
        return devices
    except Exception:
        logger.debug("Chromecast discovery failed", exc_info=True)
        return []


# ==============================================================================
# Casting
# ==============================================================================

def play_on_chromecast(device_id: str, media_url: str, title: str = "") -> dict:
    """Play a video URL on a specified Chromecast device.

    Requires a device id from discover_chromecasts(). The media URL should be
    an AirNode /view URL (reachable from the device's network position).
    """
    if not _HAS_CHROMECAST:
        return {"status": "unavailable", "message": "pychromecast is not installed."}

    try:
        # Use a cached instance if we already have it
        cast = None
        for cc in _KNOWN_CHROMECASTS:
            try:
                uuid = cc.uuid.uuid if cc.uuid else str(cc.cast_info.uuid)
            except Exception:
                uuid = ""
            if uuid == device_id:
                cast = cc
                break

        if cast is None:
            # Discover fresh (may take a couple seconds)
            chromecasts, browser = pychromecast.get_chromecasts(timeout=3.0)
            _KNOWN_CHROMECASTS = chromecasts
            for cc in chromecasts:
                try:
                    uuid = cc.uuid.uuid if cc.uuid else str(cc.cast_info.uuid)
                except Exception:
                    uuid = ""
                if uuid == device_id:
                    cast = cc
                    break
            try:
                browser.stop_discovery()
            except Exception:
                pass

        if cast is None:
            return {"status": "not_found", "message": "Chromecast device not found."}

        cast.wait()
        cast.media_controller.play_media(media_url, "video/mp4", title=title)
        cast.media_controller.block_until_active(timeout=10)
        media = cast.media_controller.status
        if media and media.player_state == "PLAYING":
            return {"status": "playing", "message": f"Now playing on {cast.name}."}
        return {"status": "started", "message": f"Casting requested to {cast.name}."}
    except Exception as e:
        logger.warning("Chromecast play failed: %s", e)
        return {"status": "error", "message": f"Cast failed: {e}"}


def get_cast_status() -> dict:
    """Return whether casting is available and what libraries are installed."""
    return {
        "chromecast_available": _HAS_CHROMECAST,
        "chromecast_supported": _HAS_CHROMECAST,
        "dlna_supported": True,  # DLNA is just a URL to a compatible file
        "message": "Chromecast enabled." if _HAS_CHROMECAST else "Install pychromecast for Chromecast support.",
    }