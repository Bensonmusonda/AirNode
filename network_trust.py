"""Network fingerprinting and trusted-network management for AirNode.

Networks are identified by stable signals that survive DHCP/IP changes:
  - Wi-Fi / Hotspot: SSID (via `netsh wlan show interfaces`)
  - Ethernet / unknown: default gateway MAC (via `arp -a` + `ipconfig`)

Trusted network records and enforcement state are stored in
`airnode-trusted-networks.json` in the data directory.
"""

import json
import re
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Optional

from logging_config import get_logger
from paths import get_data_dir

logger = get_logger(__name__)

_TRUST_PATH: Path | None = None
_trust_lock = threading.Lock()


def _get_trust_path() -> Path:
    global _TRUST_PATH
    if _TRUST_PATH is None:
        _TRUST_PATH = get_data_dir() / "airnode-trusted-networks.json"
    return _TRUST_PATH


# ---------------------------------------------------------------------------
# Network detection
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 3) -> str:
    """Run a subprocess and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=0x08000000,  # CREATE_NO_WINDOW on Windows
        )
        return result.stdout
    except Exception:
        return ""


def _get_ssid() -> Optional[str]:
    """Return the current Wi-Fi SSID, or None if not on Wi-Fi."""
    out = _run(["netsh", "wlan", "show", "interfaces"])
    for line in out.splitlines():
        line = line.strip()
        if line.lower().startswith("ssid") and not line.lower().startswith("bssid"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                ssid = parts[1].strip()
                if ssid:
                    return ssid
    return None


def _get_default_gateway() -> Optional[str]:
    """Return the default gateway IPv4 address."""
    out = _run(["ipconfig"])
    for line in out.splitlines():
        line = line.strip()
        if "default gateway" in line.lower():
            parts = line.split(":", 1)
            if len(parts) == 2:
                gw = parts[1].strip()
                if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", gw) and gw != "0.0.0.0":
                    return gw
    return None


def _get_gateway_mac(gateway_ip: str) -> Optional[str]:
    """Return the MAC address of the gateway from the ARP table."""
    out = _run(["arp", "-a"])
    for line in out.splitlines():
        if gateway_ip in line:
            # Line format:  192.168.1.1     aa-bb-cc-dd-ee-ff     dynamic
            parts = line.split()
            if len(parts) >= 2:
                mac = parts[1].lower()
                if re.match(r"^([0-9a-f]{2}[-:]){5}[0-9a-f]{2}$", mac):
                    return mac.replace("-", ":")
    return None


def get_current_network() -> Optional[dict]:
    """Detect the current network.

    Returns a dict with keys: ssid, gateway_ip, gateway_mac, fingerprint, display.
    Returns None if no network could be detected.
    """
    try:
        ssid = _get_ssid()
        gateway_ip = _get_default_gateway()
        gateway_mac = _get_gateway_mac(gateway_ip) if gateway_ip else None

        if not ssid and not gateway_mac:
            return None

        fp = _make_fingerprint(ssid, gateway_mac)
        if ssid:
            display = f"Wi-Fi: {ssid}"
        elif gateway_mac:
            display = f"Ethernet (gateway {gateway_mac})"
        else:
            display = "Unknown network"

        return {
            "ssid": ssid,
            "gateway_ip": gateway_ip,
            "gateway_mac": gateway_mac,
            "fingerprint": fp,
            "display": display,
        }
    except Exception:
        logger.exception("Network detection failed")
        return None


def _make_fingerprint(ssid: Optional[str], gateway_mac: Optional[str]) -> str:
    """Produce a stable fingerprint string. Prefers SSID over MAC."""
    if ssid:
        return f"ssid:{ssid}"
    if gateway_mac:
        return f"mac:{gateway_mac}"
    return "unknown"


# ---------------------------------------------------------------------------
# Trust storage
# ---------------------------------------------------------------------------

def _load_trust_data() -> dict:
    path = _get_trust_path()
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"enforcement": False, "networks": []}


def _save_trust_data(data: dict) -> None:
    path = _get_trust_path()
    try:
        with _trust_lock:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception:
        logger.exception("Failed to save trusted networks")


def get_trusted_networks() -> list[dict]:
    return _load_trust_data().get("networks", [])


def is_enforcement_enabled() -> bool:
    return _load_trust_data().get("enforcement", False)


def set_enforcement(enabled: bool) -> None:
    data = _load_trust_data()
    # Do not allow enforcement if there are no trusted networks
    if enabled and not data.get("networks"):
        return
    data["enforcement"] = enabled
    _save_trust_data(data)


def add_trusted_network(ssid: Optional[str], gateway_mac: Optional[str], label: str) -> dict:
    fp = _make_fingerprint(ssid, gateway_mac)
    data = _load_trust_data()
    # Deduplicate
    for existing in data["networks"]:
        if existing["fingerprint"] == fp:
            return existing
    entry = {
        "id": str(uuid.uuid4()),
        "fingerprint": fp,
        "ssid": ssid,
        "gateway_mac": gateway_mac,
        "label": label or (ssid or gateway_mac or "Unknown"),
    }
    data["networks"].append(entry)
    _save_trust_data(data)
    return entry


def remove_trusted_network(fingerprint: str) -> bool:
    data = _load_trust_data()
    before = len(data["networks"])
    data["networks"] = [n for n in data["networks"] if n["fingerprint"] != fingerprint]
    if len(data["networks"]) < before:
        # Auto-disable enforcement if list is now empty
        if not data["networks"]:
            data["enforcement"] = False
        _save_trust_data(data)
        return True
    return False


def is_network_trusted(network: Optional[dict]) -> bool:
    """Return True if the given network fingerprint is in the trusted list."""
    if not network:
        return False
    fp = network.get("fingerprint", "")
    trusted = get_trusted_networks()
    return any(n["fingerprint"] == fp for n in trusted)
