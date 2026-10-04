"""Verified local desktop dispatch contract; see docs/hook-host-evidence.md."""

import hashlib
from pathlib import Path

from .common import VaultError

HOST_CONTRACT = "codex-desktop-input-v1"
HOST_FILES = {
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex": "50ab38ba21d0d9f8346f32f41848382f15b556190f3c7a07e885a4fb73e379c8",
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex": "1180e2d56ea06ec583092acd933345685da3441cb1769a436d76dbf320613e75",
    "/Applications/ChatGPT.app/Contents/Resources/app.asar": "c662897ab25e819cd97a7981cf34d10eefcb9243095d527d27adff71bc18af0a",
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
                "unverified_host",
                f"Verified desktop installation is unavailable: {name} ({exc.strerror}). "
                "The app may have moved or changed its bundle layout; review the installed "
                "build and dispatch behavior before updating pinned paths or fingerprints.",
            ) from exc
        if actual != expected:
            raise VaultError(
                "unverified_host",
                f"Desktop build changed: {name}; revalidate hook compatibility before approving or applying. "
                "Do not update fingerprints without reviewing the new dispatch behavior.",
            )
