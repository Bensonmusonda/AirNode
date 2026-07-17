import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parent / ".airnode-auth.json"
COOKIE_NAME = "airnode_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

# --- Login lockout (brute-force protection) ---
# In-memory only: a fresh process starts with a clean slate, which is fine
# since the PIN itself only changes when .airnode-auth.json is deleted.
MAX_FAILURES_BEFORE_LOCKOUT = 5
BASE_LOCKOUT_SECONDS = 30
MAX_LOCKOUT_SECONDS = 300

_login_attempts_lock = threading.Lock()
_login_attempts: dict[str, dict[str, float]] = {}


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


def check_login_lockout(client_key: str) -> float:
    """Returns seconds remaining if `client_key` (e.g. an IP) is currently
    locked out from login attempts, or 0.0 if it may try now."""
    with _login_attempts_lock:
        record = _login_attempts.get(client_key)
        if not record:
            return 0.0
        remaining = record["locked_until"] - time.time()
        return remaining if remaining > 0 else 0.0


def register_login_failure(client_key: str) -> None:
    """Records a failed PIN attempt and escalates a lockout once the
    failure count crosses MAX_FAILURES_BEFORE_LOCKOUT."""
    with _login_attempts_lock:
        record = _login_attempts.setdefault(client_key, {"failures": 0, "locked_until": 0.0})
        record["failures"] += 1
        if record["failures"] >= MAX_FAILURES_BEFORE_LOCKOUT:
            extra_strikes = record["failures"] - MAX_FAILURES_BEFORE_LOCKOUT
            lockout = min(BASE_LOCKOUT_SECONDS * (2 ** extra_strikes), MAX_LOCKOUT_SECONDS)
            record["locked_until"] = time.time() + lockout


def register_login_success(client_key: str) -> None:
    """Clears any failure/lockout record for `client_key` after a good PIN."""
    with _login_attempts_lock:
        _login_attempts.pop(client_key, None)


def reset_pin() -> str:
    """Generates a fresh PIN and salt while preserving the existing session
    secret, so any browser/device that's already logged in stays logged in —
    only new logins need the new PIN. Returns the new plaintext PIN, which
    (like on first creation) is shown exactly once; only its salted hash is
    persisted to disk."""
    config = ensure_auth_config()
    new_pin = f"{secrets.randbelow(1_000_000):06d}"
    new_salt = secrets.token_urlsafe(24)
    CONFIG_PATH.write_text(
        json.dumps({
            "pin_hash": _hash_pin(new_pin, new_salt),
            "pin_salt": new_salt,
            "session_secret": config.session_secret,
        }, indent=2),
        encoding="utf-8",
    )
    with _login_attempts_lock:
        _login_attempts.clear()
    return new_pin


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