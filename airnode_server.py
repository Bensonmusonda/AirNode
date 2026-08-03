import argparse
import json
import os
import socket
import subprocess
import sys
import webbrowser
from contextlib import AbstractContextManager
from pathlib import Path

from airnode_auth import delete_auth_config, has_auth_config
from logging_config import get_logger, setup_logging
from paths import get_resource_dir, get_data_dir, is_frozen
from version import VERSION


logger = get_logger(__name__)

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
except ImportError:  # pragma: no cover - exercised only when deps are missing
    IPVersion = None
    ServiceInfo = None
    Zeroconf = None


SERVICE_TYPE = "_http._tcp.local."
SERVICE_NAME = "AirNode._http._tcp.local."
HOSTNAME = "airnode.local."
GENERATED_STATIC_DIR = get_resource_dir() / "static" / "generated"
QR_FILENAME = "airnode-qr.svg"


def get_lan_ipv4_addresses() -> list[str]:
    """Return non-loopback IPv4 addresses that are useful on the local network."""
    addresses: set[str] = set()
    hostname = socket.gethostname()

    try:
        for result in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = result[4][0]
            if not address.startswith("127."):
                addresses.add(address)
    except socket.gaierror:
        pass

    # This UDP socket does not send packets; connect() only asks the OS which
    # local interface would be used for outbound traffic.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass

    return sorted(addresses)


class MdnsAdvertisement(AbstractContextManager):
    def __init__(self, port: int, enabled: bool = True) -> None:
        self.port = port
        self.enabled = enabled
        self.zeroconf = None
        self.info = None
        self.urls: list[str] = []
        self.mdns_error: str | None = None

    def __enter__(self):
        lan_addresses = get_lan_ipv4_addresses()
        self.urls = [f"http://{address}:{self.port}" for address in lan_addresses]

        if self.enabled and Zeroconf and ServiceInfo and lan_addresses:
            packed_addresses = [socket.inet_aton(address) for address in lan_addresses]
            self.info = ServiceInfo(
                SERVICE_TYPE,
                SERVICE_NAME,
                addresses=packed_addresses,
                port=self.port,
                properties={
                    "path": "/",
                    "name": "AirNode",
                },
                server=HOSTNAME,
            )
            self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            try:
                self.zeroconf.register_service(self.info, allow_name_change=True)
            except Exception as exc:
                self.mdns_error = str(exc) or exc.__class__.__name__
                self.zeroconf.close()
                self.zeroconf = None
                self.info = None

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.zeroconf and self.info:
            self.zeroconf.unregister_service(self.info)
            self.zeroconf.close()
        return False

    @property
    def mdns_url(self) -> str | None:
        if not self.enabled or not self.zeroconf:
            return None
        return f"http://airnode.local:{self.port}"


def print_access_urls(advertisement: MdnsAdvertisement) -> None:
    print("AirNode is starting.")

    if not has_auth_config():
        print("First run detected — open the setup page to create your PIN.")
    else:
        print("Access gate: enabled.")

    if advertisement.mdns_url:
        print(f"Local network name: {advertisement.mdns_url}")
    elif advertisement.mdns_error:
        print(f"Local network name: unavailable ({advertisement.mdns_error}).")
    elif advertisement.enabled and Zeroconf is None:
        print("Local network name: unavailable because zeroconf is not installed.")
    elif advertisement.enabled:
        print("Local network name: unavailable because no LAN IPv4 address was found.")

    if advertisement.urls:
        print("LAN fallback URLs:")
        for url in advertisement.urls:
            print(f"  {url}")
    else:
        print("LAN fallback URLs: none detected yet.")

    if os.environ.get("AIRNODE_QR_URL"):
        print("QR code page: http://localhost:%s/connect" % advertisement.port)
        print("QR target: %s" % os.environ["AIRNODE_QR_URL"])
    elif os.environ.get("AIRNODE_QR_ERROR"):
        print("QR code: unavailable (%s)." % os.environ["AIRNODE_QR_ERROR"])


def generate_qr_svg(url: str) -> str | None:
    """Generate a QR SVG for the URL and return the static asset path."""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        os.environ["AIRNODE_QR_ERROR"] = "qrcode is not installed"
        return None

    GENERATED_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    qr_path = GENERATED_STATIC_DIR / QR_FILENAME
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
    image.save(qr_path)
    return f"/static/generated/{QR_FILENAME}"


def publish_connection_details(advertisement: MdnsAdvertisement) -> None:
    primary_url = advertisement.urls[0] if advertisement.urls else ""
    qr_path = generate_qr_svg(primary_url) if primary_url else None

    os.environ["AIRNODE_LAN_URLS"] = json.dumps(advertisement.urls)
    os.environ["AIRNODE_PRIMARY_URL"] = primary_url
    os.environ["AIRNODE_MDNS_URL"] = advertisement.mdns_url or ""
    os.environ["AIRNODE_QR_URL"] = primary_url
    os.environ["AIRNODE_QR_PATH"] = qr_path or ""


# ---------------------------------------------------------------------------
# CLI helper commands
# ---------------------------------------------------------------------------

def do_reset_pin() -> None:
    """Delete the auth config so the next launch shows the /setup page."""
    delete_auth_config()
    print("PIN reset complete.")
    print("Start AirNode again and you'll be asked to choose a new PIN.")
    sys.exit(0)


def do_install_autostart() -> None:
    """Register a Windows Task Scheduler task to start AirNode at logon."""
    exe = sys.executable if is_frozen() else sys.argv[0]
    task_name = "AirNode"

    # Remove any previous registration
    subprocess.run(
        ["schtasks", "/Delete", "/TN", task_name, "/F"],
        capture_output=True,
    )

    result = subprocess.run(
        [
            "schtasks", "/Create",
            "/TN", task_name,
            "/TR", f'"{exe}"',
            "/SC", "ONLOGON",
            "/RL", "LIMITED",
            "/F",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("AirNode autostart registered in Task Scheduler.")
        print("It will start automatically the next time you log in.")
        print("Remove with: AirNode.exe --uninstall-autostart")
    else:
        print(f"Failed to register autostart task: {result.stderr.strip()}")
        sys.exit(1)

    sys.exit(0)


def do_uninstall_autostart() -> None:
    """Remove the AirNode autostart task from Task Scheduler."""
    task_name = "AirNode"
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", task_name, "/F"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("AirNode autostart task removed.")
    else:
        print("No scheduled task named 'AirNode' found.")
    sys.exit(0)


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a TCP port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def find_available_port(preferred: int, host: str = "0.0.0.0") -> int:
    """Return the preferred port if available, otherwise find the next free port."""
    if is_port_available(preferred, host):
        return preferred
    for port in range(preferred + 1, preferred + 100):
        if is_port_available(port, host):
            return port
    return preferred  # give up; uvicorn will report the real error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AirNode with LAN discovery, or perform maintenance tasks."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"AirNode {VERSION}",
        help="Show the AirNode version and exit.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind.")
    parser.add_argument("--port", default=8000, type=int, help="Port to listen on.")
    parser.add_argument(
        "--no-mdns",
        action="store_true",
        help="Disable mDNS/Bonjour advertisement.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    parser.add_argument(
        "--reset-pin",
        action="store_true",
        help="Delete the current PIN so the next launch shows the setup page.",
    )
    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="Register AirNode to start automatically at Windows logon.",
    )
    parser.add_argument(
        "--uninstall-autostart",
        action="store_true",
        help="Remove the AirNode autostart entry from Task Scheduler.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(verbose=args.verbose)
    logger.info("AirNode %s starting", VERSION)

    # Handle CLI helper commands (these exit and never start the server)
    if args.reset_pin:
        do_reset_pin()
    if args.install_autostart:
        do_install_autostart()
    if args.uninstall_autostart:
        do_uninstall_autostart()

    # Check port availability before starting — give a clear error instead
    # of letting uvicorn crash with a cryptic traceback.
    if not is_port_available(args.port, args.host):
        alt_port = find_available_port(args.port, args.host)
        if alt_port != args.port:
            print(f"Port {args.port} is already in use.")
            print(f"AirNode will use port {alt_port} instead.")
            print(f"Open: http://localhost:{alt_port}")
            args.port = alt_port
        else:
            print(f"ERROR: Port {args.port} is already in use and no free port was found.")
            print("Close the application using that port, or specify a different port:")
            print(f"  AirNode.exe --port <port>")
            sys.exit(1)

    # Auto-open browser on first run (no PIN set yet)
    first_run = not has_auth_config()
    if first_run:
        webbrowser.open(f"http://localhost:{args.port}/setup")

    import uvicorn

    with MdnsAdvertisement(port=args.port, enabled=not args.no_mdns) as advertisement:
        publish_connection_details(advertisement)
        print_access_urls(advertisement)

        # Disable reload when frozen (PyInstaller) — reload spawns a new
        # process and doesn't work inside a frozen executable.
        reload = not is_frozen()
        uvicorn.run("main:app", host=args.host, port=args.port, reload=reload)


if __name__ == "__main__":
    main()