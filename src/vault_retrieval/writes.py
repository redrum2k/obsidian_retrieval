"""Recoverable publication without replacing an occupied destination.

Existing destinations are captured on the same filesystem before validation.
There is a brief missing-path window. Competing saves are retained, never replaced.
This is not a filesystem-wide transaction or a lock on external editors.
"""

import json
import os
import stat

from .common import VaultError, canonical, digest


def recovery_dir(config, action):
    return config.state / "write-recovery" / digest(canonical(action).encode())


def captured_hash(config, action):
    path = recovery_dir(config, action) / "captured"
    if not path.exists():
        return None
    if not stat.S_ISREG(path.lstat().st_mode):
        raise VaultError(
            "conflict", "Captured destination is not a regular file; inspect recovery."
        )
    return digest(path.read_bytes())


def check_filesystem(config, action):
    path = config.check(action["path"], write=True).parent
    while not path.exists():
        path = path.parent
    if path.stat().st_dev != config.state.stat().st_dev:
        raise VaultError(
            "unsupported_write", "Vault and external recovery storage must share a filesystem."
        )


def recover_publication(config, action):
    """Finish unlinking our staging alias after a crash following successful link()."""
    staged = recovery_dir(config, action) / "staged"
    target = config.check(action["path"], write=True)
    if staged.exists() and target.exists() and os.path.samestat(staged.stat(), target.stat()):
        if digest(staged.read_bytes()) != action["output_hash"]:
            raise VaultError("conflict", "Published content changed during recovery.")
        staged.unlink()


def publish(config, action):
    check_filesystem(config, action)
    folder = recovery_dir(config, action)
    folder.mkdir(parents=True, exist_ok=True)
    for directory in (config.state, folder.parent):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    manifest = folder / "action.json"
    if not manifest.exists():
        with manifest.open("x") as f:
            json.dump(action, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    parent, leaf = config.open_parent(action["path"], write=True, create=True)
    recovery = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    staged = folder / "staged"
    try:
        if not staged.exists():
            with staged.open("xb") as f:
                os.fchmod(f.fileno(), 0o600)
                f.write(action["content"].encode())
                f.flush()
                os.fsync(f.fileno())
        if digest(staged.read_bytes()) != action["output_hash"]:
            raise VaultError("conflict", "Staged content differs from approval; inspect recovery.")
        os.fsync(recovery)
        capture = folder / "captured"
        if action["expected_hash"] is not None:
            if not capture.exists():
                # Capture the actual inode, including a competing save after preflight.
                # The private recovery slot is only used under the service lock.
                os.rename(leaf, "captured", src_dir_fd=parent, dst_dir_fd=recovery)
                os.fsync(recovery)
                os.fsync(parent)
            if captured_hash(config, action) != action["expected_hash"]:
                # Restore only into an empty slot. Never replace a subsequent save.
                try:
                    os.link(
                        "captured",
                        leaf,
                        src_dir_fd=recovery,
                        dst_dir_fd=parent,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    pass
                else:
                    os.unlink("captured", dir_fd=recovery)
                    os.fsync(recovery)
                    os.fsync(parent)
                raise VaultError("conflict", f"Competing edit preserved; inspect {folder}.")
        try:
            os.link("staged", leaf, src_dir_fd=recovery, dst_dir_fd=parent, follow_symlinks=False)
        except FileExistsError as exc:
            raise VaultError(
                "conflict", f"Destination appeared during publication; inspect {folder}."
            ) from exc
        os.unlink("staged", dir_fd=recovery)
        os.fsync(parent)
        os.fsync(recovery)
        if (
            action["expected_hash"] is not None
            and captured_hash(config, action) != action["expected_hash"]
        ):
            raise VaultError(
                "conflict",
                f"Editor changed the captured inode; newer content retained in {folder}.",
            )
    finally:
        os.close(recovery)
        os.close(parent)
