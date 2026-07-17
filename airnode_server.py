import argparse
import socket
from contextlib import AbstractContextManager

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
except ImportError:  # pragma: no cover - exercised only when deps are missing
    IPVersion = None
    ServiceInfo = None
    Zeroconf = None


SERVICE_TYPE = "_http._tcp.local."
SERVICE_NAME = "AirNode._http._tcp.local."
HOSTNAME = "airnode.local."


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AirNode with LAN discovery.")
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind.")
    parser.add_argument("--port", default=8000, type=int, help="Port to listen on.")
    parser.add_argument(
        "--no-mdns",
        action="store_true",
        help="Disable mDNS/Bonjour advertisement.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import uvicorn

    with MdnsAdvertisement(port=args.port, enabled=not args.no_mdns) as advertisement:
        print_access_urls(advertisement)
        uvicorn.run("main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
