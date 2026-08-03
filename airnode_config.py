"""Configuration file management for AirNode.

Reads and writes ``airnode-config.json`` in the data directory, providing
persistent settings (port, host, mDNS enabled, autostart) that can be
changed from the web settings page or tray icon without editing CLI args.
"""

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from paths import get_data_dir


CONFIG_PATH = get_data_dir() / "airnode-config.json"

_lock = threading.Lock()

# Default values used when no config file exists
DEFAULTS = {
    "port": 8000,
    "host": "0.0.0.0",
    "mdns_enabled": True,
    "autostart": False,
    "last_visited": "/",
}


@dataclass
class AirNodeConfig:
    """Runtime view of the persisted configuration."""
    port: int = DEFAULTS["port"]
    host: str = DEFAULTS["host"]
    mdns_enabled: bool = DEFAULTS["mdns_enabled"]
    autostart: bool = DEFAULTS["autostart"]
    last_visited: str = DEFAULTS["last_visited"]

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "host": self.host,
            "mdns_enabled": self.mdns_enabled,
            "autostart": self.autostart,
            "last_visited": self.last_visited,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AirNodeConfig":
        return cls(
            port=int(data.get("port", DEFAULTS["port"])),
            host=str(data.get("host", DEFAULTS["host"])),
            mdns_enabled=bool(data.get("mdns_enabled", DEFAULTS["mdns_enabled"])),
            autostart=bool(data.get("autostart", DEFAULTS["autostart"])),
            last_visited=str(data.get("last_visited", DEFAULTS["last_visited"])),
        )


def load_config() -> AirNodeConfig:
    """Load the config file from disk, falling back to defaults."""
    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                return AirNodeConfig.from_dict(json.load(f))
    except (OSError, ValueError, TypeError):
        pass
    return AirNodeConfig()


def save_config(config: AirNodeConfig) -> None:
    """Persist the config to disk."""
    try:
        with _lock:
            with CONFIG_PATH.open("w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2)
    except OSError:
        pass


def update_config(**kwargs) -> AirNodeConfig:
    """Load, apply the given updates, and save. Returns the new config."""
    config = load_config()
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    save_config(config)
    return config