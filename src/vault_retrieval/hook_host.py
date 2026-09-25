"""Verified local desktop dispatch contract; see docs/hook-host-evidence.md."""

import hashlib
from pathlib import Path

from .common import VaultError

HOST_CONTRACT = "codex-desktop-input-v1"
HOST_FILES = {
    "/Applications/ChatGPT.app/Contents/Resources/codex": "93169e745735930598e867ad837abf3fdc50774a3ad7e7aa89c0d0c51b0189a5",
    "/Applications/ChatGPT.app/Contents/Resources/app.asar": "03108a728bdb1616958ab89587c5495cab0cf4cd1bbe109bdfb186df0a113804",
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
