import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parent / ".airnode-auth.json"
COOKIE_NAME = "airnode_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


@dataclass(frozen=True)
class AuthConfig:
    pin_hash: str
    pin_salt: str
    session_secret: str
    created_pin: str | None = None


def _hash_pin(pin: str, salt: str) -> str:
    payload = f"{salt}:{pin}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_config() -> AuthConfig | None:
    if not CONFIG_PATH.exists():
        return None

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return AuthConfig(
        pin_hash=data["pin_hash"],
        pin_salt=data["pin_salt"],
        session_secret=data["session_secret"],
    )


def ensure_auth_config() -> AuthConfig:
    existing = _read_config()
    if existing:
        return existing

    pin = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_urlsafe(24)
    config = AuthConfig(
        pin_hash=_hash_pin(pin, salt),
        pin_salt=salt,
        session_secret=secrets.token_urlsafe(48),
        created_pin=pin,
    )
    CONFIG_PATH.write_text(
        json.dumps({
            "pin_hash": config.pin_hash,
            "pin_salt": config.pin_salt,
            "session_secret": config.session_secret,
        }, indent=2),
        encoding="utf-8",
    )
    return config


def verify_pin(pin: str) -> bool:
    config = ensure_auth_config()
    actual = _hash_pin(pin.strip(), config.pin_salt)
    return hmac.compare_digest(actual, config.pin_hash)


def create_session_token() -> str:
    config = ensure_auth_config()
    expires_at = str(int(time.time()) + SESSION_MAX_AGE_SECONDS)
    nonce = secrets.token_urlsafe(16)
    message = f"{expires_at}:{nonce}"
    signature = hmac.new(
        config.session_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{message}:{signature}"


def verify_session_token(token: str | None) -> bool:
    if not token:
        return False

    try:
        expires_at, nonce, signature = token.split(":", 2)
        expires = int(expires_at)
    except (ValueError, TypeError):
        return False

    if expires < int(time.time()):
        return False

    config = ensure_auth_config()
    message = f"{expires_at}:{nonce}"
    expected = hmac.new(
        config.session_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)
