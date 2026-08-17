"""Automated Local Certificate Authority (CA) and TLS certificate management for AirNode.

Generates:
1. AirNode Local Root CA (4096-bit RSA, 10-year validity)
2. AirNode Server Certificate (2048-bit RSA, signed by Root CA, SANs covering
   localhost, airnode.local, and all local network IPv4 addresses)
3. Windows Certificate Store auto-registration via PowerShell Import-Certificate
   (non-interactive, no dialog, no elevation needed for CurrentUser store)
4. Apple .mobileconfig profile generator for 1-tap iOS certificate enrollment
"""

import datetime
import ipaddress
import os
import plistlib
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from logging_config import get_logger
from paths import get_data_dir

logger = get_logger(__name__)

CA_NAME = "AirNode Local Root CA"
SERVER_CN = "airnode.local"


def get_certs_dir() -> Path:
    """Return directory where certificates and private keys are stored."""
    certs_dir = get_data_dir() / "certs"
    certs_dir.mkdir(parents=True, exist_ok=True)
    return certs_dir


def _generate_private_key(bits: int = 2048) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=bits,
    )


def _save_key(key: rsa.RSAPrivateKey, path: Path) -> None:
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem)


def _load_key(path: Path) -> rsa.RSAPrivateKey:
    return serialization.load_pem_private_key(
        path.read_bytes(),
        password=None,
    )


def _save_cert(cert: x509.Certificate, path: Path) -> None:
    pem = cert.public_bytes(serialization.Encoding.PEM)
    path.write_bytes(pem)


def _load_cert(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def ensure_root_ca() -> tuple[Path, Path]:
    """Generate the AirNode Local Root CA certificate and key if they don't exist.

    Returns:
        (ca_cert_path, ca_key_path)
    """
    certs_dir = get_certs_dir()
    ca_cert_path = certs_dir / "ca.crt"
    ca_key_path = certs_dir / "ca.key"

    if ca_cert_path.exists() and ca_key_path.exists():
        return ca_cert_path, ca_key_path

    logger.info("Generating AirNode Local Root CA...")
    ca_key = _generate_private_key(bits=4096)
    _save_key(ca_key, ca_key_path)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, CA_NAME),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AirNode"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Security"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))  # 10 years
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    _save_cert(ca_cert, ca_cert_path)
    logger.info("AirNode Local Root CA generated successfully at %s", ca_cert_path)
    # NOTE: We do NOT auto-install here. Certificate installation is a user-facing
    # action triggered from Settings → "Install Certificate". Silently attempting
    # it at startup with CREATE_NO_WINDOW was suppressing the dialog on most configs.

    return ca_cert_path, ca_key_path


def _get_ca_thumbprint(ca_cert_path: Path) -> str:
    """Return the SHA-1 thumbprint (hex, uppercase, no separators) of the CA cert on disk."""
    cert = _load_cert(ca_cert_path)
    return cert.fingerprint(hashes.SHA1()).hex().upper()


def is_ca_installed_in_windows_store() -> bool:
    """Check if the Root CA is installed in the current user's Root store AND matches the on-disk cert.

    Matching on thumbprint prevents false-positives when the CA was regenerated but
    an old version is still sitting in the store.
    """
    if sys.platform != "win32":
        return False
    try:
        # Check if the name exists at all first
        check = subprocess.run(
            ["certutil", "-user", "-verifystore", "Root", CA_NAME],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=0x08000000,
        )
        if check.returncode != 0 or CA_NAME not in check.stdout:
            return False

        # Verify the on-disk CA thumbprint matches what's in the store
        certs_dir = get_certs_dir()
        ca_cert_path = certs_dir / "ca.crt"
        if not ca_cert_path.exists():
            return False
        disk_thumb = _get_ca_thumbprint(ca_cert_path)
        # certutil output contains the hash like: Cert Hash(sha1): 0c2a3635...
        store_thumb = ""
        for line in check.stdout.splitlines():
            if "Cert Hash(sha1)" in line:
                store_thumb = line.split(":", 1)[1].strip().replace(" ", "").upper()
                break
        if store_thumb and disk_thumb != store_thumb:
            logger.info(
                "CA thumbprint mismatch: store=%s disk=%s — treating as not installed.",
                store_thumb,
                disk_thumb,
            )
            return False
        return True
    except Exception:
        return False


def install_ca_to_windows_store(ca_cert_path: Path, force: bool = False) -> bool:
    """Register the Root CA into the current user's Trusted Root Certification Authorities store.

    Uses PowerShell's ``Import-Certificate`` cmdlet which is silent, non-interactive,
    and does not require elevation for the CurrentUser store — unlike ``certutil -addstore``
    which can silently fail when the parent process has no window (CREATE_NO_WINDOW).

    Args:
        ca_cert_path: Path to the CA certificate file (PEM or DER).
        force: If True, re-import even when already installed (e.g. after CA regeneration).
    """
    if sys.platform != "win32":
        return False

    if not force and is_ca_installed_in_windows_store():
        logger.info("Root CA is already installed in Windows CurrentUser Root store.")
        return True

    # Use .NET X509Store API directly via PowerShell — this is fully programmatic,
    # never triggers a UI dialog, and doesn't need elevation for CurrentUser\Root.
    try:
        cert = _load_cert(ca_cert_path)
        der_bytes = cert.public_bytes(serialization.Encoding.DER)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".cer", delete=False) as tmp:
            tmp.write(der_bytes)
            tmp_path = tmp.name
    except Exception as exc:
        logger.warning("Failed to prepare CA cert for import: %s", exc)
        return False

    try:
        # PowerShell using .NET X509Store directly — no UI, no dialog, no elevation.
        # Note: CurrentUser\Root on Windows 10/11 does NOT require admin rights.
        ps_cmd = (
            "$store = New-Object System.Security.Cryptography.X509Certificates.X509Store("
            "'Root','CurrentUser'); "
            "$store.Open('ReadWrite'); "
            f"$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2('{tmp_path}'); "
            "$store.Add($cert); "
            "$store.Close(); "
            "Write-Output 'OK'"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=0x08000000,  # CREATE_NO_WINDOW: .NET API needs no window
        )
        if result.returncode == 0 and "OK" in result.stdout:
            logger.info("Successfully installed AirNode Root CA via .NET X509Store.")
            return True
        else:
            logger.warning(
                ".NET X509Store install failed (rc=%s): %s",
                result.returncode,
                result.stderr.strip() or result.stdout.strip(),
            )
            return _install_ca_certutil_fallback(ca_cert_path)
    except subprocess.TimeoutExpired:
        logger.warning("PowerShell X509Store timed out — trying certutil fallback.")
        return _install_ca_certutil_fallback(ca_cert_path)
    except Exception as exc:
        logger.warning("PowerShell X509Store raised: %s — trying certutil fallback.", exc)
        return _install_ca_certutil_fallback(ca_cert_path)
    finally:
        try:
            import os as _os
            _os.unlink(tmp_path)
        except Exception:
            pass


def _install_ca_certutil_fallback(ca_cert_path: Path) -> bool:
    """Fallback: install via certutil -addstore without CREATE_NO_WINDOW."""
    try:
        add_res = subprocess.run(
            ["certutil", "-user", "-addstore", "Root", str(ca_cert_path)],
            capture_output=True,
            text=True,
            timeout=30,
            # Intentionally no CREATE_NO_WINDOW so the confirmation dialog can appear.
        )
        if add_res.returncode == 0:
            logger.info("Root CA installed via certutil fallback.")
            return True
        logger.warning("certutil -addstore returned code %s: %s", add_res.returncode, add_res.stderr)
        return False
    except subprocess.TimeoutExpired:
        logger.warning("certutil -addstore timed out.")
        return False
    except Exception as exc:
        logger.warning("certutil fallback failed: %s", exc)
        return False


def ensure_server_certificate(lan_ips: Optional[list[str]] = None) -> tuple[Path, Path]:
    """Generate or renew the Server Certificate signed by the Local Root CA.

    Args:
        lan_ips: Optional list of LAN IP addresses to include in SANs.

    Returns:
        (server_cert_path, server_key_path)
    """
    ca_cert_path, ca_key_path = ensure_root_ca()
    ca_cert = _load_cert(ca_cert_path)
    ca_key = _load_key(ca_key_path)

    certs_dir = get_certs_dir()
    server_cert_path = certs_dir / "server.crt"
    server_key_path = certs_dir / "server.key"

    # Build SAN entries
    san_entries: set[x509.GeneralName] = {
        x509.DNSName("localhost"),
        x509.DNSName("airnode.local"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.IPAddress(ipaddress.IPv6Address("::1")),
    }

    try:
        hostname = socket.gethostname()
        if hostname:
            san_entries.add(x509.DNSName(hostname))
    except Exception:
        pass

    if lan_ips:
        for ip_str in lan_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str.strip())
                san_entries.add(x509.IPAddress(ip_obj))
            except ValueError:
                pass

    # Check if existing server cert is fresh and valid
    if server_cert_path.exists() and server_key_path.exists():
        try:
            existing_cert = _load_cert(server_cert_path)
            now = datetime.datetime.now(datetime.timezone.utc)
            if existing_cert.not_valid_after_utc > (now + datetime.timedelta(days=30)):
                # Check if all current SAN IPs are in existing cert
                try:
                    ext = existing_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                    existing_sans = set(ext.value)
                    if san_entries.issubset(existing_sans):
                        return server_cert_path, server_key_path
                except x509.ExtensionNotFound:
                    pass
        except Exception:
            pass

    logger.info("Generating AirNode Server Certificate with SANs: %s", [str(s.value) for s in san_entries])
    server_key = _generate_private_key(bits=2048)
    _save_key(server_key, server_key_path)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, SERVER_CN),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AirNode"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    # Apple iOS requires server cert validity <= 825 days for custom roots
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=730))  # 2 years
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName(list(san_entries)),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    _save_cert(server_cert, server_cert_path)
    logger.info("AirNode Server Certificate created successfully at %s", server_cert_path)
    return server_cert_path, server_key_path


def get_ca_cert_pem() -> bytes:
    """Return the PEM-encoded Root CA certificate bytes."""
    ca_cert_path, _ = ensure_root_ca()
    return ca_cert_path.read_bytes()


def get_ca_cert_der() -> bytes:
    """Return the DER-encoded Root CA certificate bytes."""
    ca_cert_path, _ = ensure_root_ca()
    cert = _load_cert(ca_cert_path)
    return cert.public_bytes(serialization.Encoding.DER)


def generate_mobileconfig() -> bytes:
    """Generate an Apple .mobileconfig profile containing the Root CA certificate.

    This enables 1-tap installation on iOS, iPadOS, and macOS devices.
    """
    der_data = get_ca_cert_der()
    payload_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "airnode.local.ca"))
    profile_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "airnode.local.profile"))

    profile_dict = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": "com.airnode.rootca",
        "PayloadUUID": profile_uuid,
        "PayloadDisplayName": "AirNode Local Security Certificate",
        "PayloadDescription": "Installs the AirNode Local Root CA certificate for secure HTTPS access.",
        "PayloadOrganization": "AirNode",
        "PayloadContent": [
            {
                "PayloadType": "com.apple.security.root",
                "PayloadVersion": 1,
                "PayloadIdentifier": "com.airnode.rootca.cert",
                "PayloadUUID": payload_uuid,
                "PayloadDisplayName": "AirNode Local Root CA",
                "PayloadDescription": "AirNode Root Certificate Authority",
                "PayloadCertificateFileName": "airnode-ca.cer",
                "PayloadContent": der_data,
            }
        ],
    }

    return plistlib.dumps(profile_dict, fmt=plistlib.FMT_XML)
