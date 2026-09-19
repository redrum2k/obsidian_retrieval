"""Verified local desktop dispatch contract; see docs/hook-host-evidence.md."""

import hashlib
from pathlib import Path

from .common import VaultError

HOST_CONTRACT = "codex-desktop-input-v1"
HOST_FILES = {
    "/Applications/ChatGPT.app/Contents/Resources/codex": "9280c0754e8f1f6b72f495d30c8c82a006dbc4995bf0492916fa0901f6bfd1f9",
    "/Applications/ChatGPT.app/Contents/Resources/app.asar": "1f7939c1c781887c167043c4d1d307af3400d324685cfc315dfe2f80e634f483",
}


def verify_host(settings):
    if settings.get("host_contract") != HOST_CONTRACT:
        raise VaultError(
            "unverified_host", "Select the verified desktop hook contract before approval."
        )
    for name, expected in HOST_FILES.items():
        try:
            with Path(name).open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as exc:
            raise VaultError(
                "unverified_host", "Verified desktop installation is unavailable."
            ) from exc
        if actual != expected:
            raise VaultError(
                "unverified_host",
                "Desktop build changed; revalidate hook compatibility before approving or applying. "
                "Do not update fingerprints without reviewing the new dispatch behavior.",
            )
