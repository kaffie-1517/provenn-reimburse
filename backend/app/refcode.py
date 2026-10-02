"""Reference codes: 8 chars of RFC 4648 base32 (A–Z, 2–7) = 40 random bits.

Shown to people as PNN-XXXXXXXX. Uniqueness is guaranteed by the database's
UNIQUE constraint; callers retry on collision.
"""

import base64
import re
import secrets

DISPLAY_PREFIX = "PNN-"
CODE_RE = re.compile(r"^[A-Z2-7]{8}$")


def new_code() -> str:
    return base64.b32encode(secrets.token_bytes(5)).decode()


def normalize(raw: str) -> str | None:
    """Accepts 'pnn-abcd2345', ' ABCD2345 ' etc. Returns the bare code or None."""
    code = raw.strip().upper().removeprefix(DISPLAY_PREFIX)
    return code if CODE_RE.match(code) else None


def display(code: str) -> str:
    return DISPLAY_PREFIX + code
