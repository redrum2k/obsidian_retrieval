import base64
import hashlib
import json
from datetime import datetime, timezone


class VaultError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def cursor_encode(value):
    return base64.urlsafe_b64encode(canonical(value).encode()).decode()


def cursor_decode(value):
    try:
        return json.loads(base64.urlsafe_b64decode(value))
    except (ValueError, TypeError) as exc:
        raise VaultError(
            "invalid_cursor", "Use the continuation returned by this operation."
        ) from exc
