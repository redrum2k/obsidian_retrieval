"""Codex UserPromptSubmit entry point. Unknown event provenance fails closed."""

import argparse
import json
import os
import re
import shlex
import sys
import uuid
from pathlib import Path

from .common import VaultError, canonical, digest, now
from .config import Config
from .hook_approval import command_id, record_event
from .hook_host import HOST_CONTRACT, verify_host
from .service import Service


def is_probe(event):
    """Allow chat's Markdown formatting only for this non-authorizing diagnostic."""
    prompt = event.get("prompt")
    if event.get("hook_event_name") != "UserPromptSubmit" or not isinstance(prompt, str):
        return False
    prompt = prompt.strip()
    if prompt.startswith("`") and prompt.endswith("`"):
        prompt = prompt[1:-1]
    return re.sub(r"\\+_", "_", prompt) == "VAULT_HOOK_PROBE"


def probe(event, folder):
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fields = (
        "hook_event_name",
        "session_id",
        "turn_id",
        "source",
        "origin",
        "submission_origin",
        "is_automation",
        "is_subagent",
        "agent_id",
    )
    metadata = {k: event[k] for k in fields if isinstance(event.get(k), (str, bool))}
    metadata["field_names"] = sorted(event)[:100]
    path = folder / (uuid.uuid4().hex + ".json")
    with path.open("x") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(canonical(metadata))
    if is_probe(event):
        return {
            "systemMessage": "Vault hook probe received. No approval or vault write occurred. Metadata: "
            + str(path)
        }
    return None


def check(config_path):
    config = Config.load(config_path)
    settings = config.data.get("hook_approval", {})
    if (
        config.data.get("approval_scheme") != "codex-hook"
        or settings.get("enabled") is not True
        or not settings.get("session_id")
    ):
        raise VaultError("hook_disabled", "Chat approval is not configured.")
    verify_host(settings)
    policy = config.data.get("policy")
    if policy and digest(config.read(policy["path"])) != policy["sha256"]:
        raise VaultError("policy_changed", "Review current vault policy before continuing.")
    return {
        "configured": True,
        "host_contract": HOST_CONTRACT,
        "session_id": settings["session_id"],
        "approval_recorded": False,
        "note": "Host hook trust and a real approval reply still require a live test.",
    }


def handle(event, config_path):
    if is_probe(event):
        config = Config.load(config_path)
        if event.get("session_id") != config.data.get("hook_approval", {}).get("session_id"):
            return None
        status = {
            "checked_at": now(),
            "session_id": event.get("session_id"),
            "turn_id": event.get("turn_id"),
            "approval_recorded": False,
        }
        failure = None
        try:
            check(config_path)
            status["status"] = "ready"
        except VaultError as exc:
            status.update(status="blocked", error=exc.code)
            failure = exc
        # A durable, content-free receipt makes probe delivery observable even if
        # the model replies with a generic acknowledgment. This is not approval.
        config.state.mkdir(parents=True, exist_ok=True)
        receipt = config.state / "hook-probe-status.json"
        temporary = config.state / (".hook-probe-" + uuid.uuid4().hex)
        with temporary.open("x") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(canonical(status))
        os.replace(temporary, receipt)
        if failure:
            raise failure
        message = (
            "Vault production approval hook ran; configuration and host build checks passed. "
            "This probe approved nothing and changed no vault files. Status receipt: "
            + str(receipt)
        )
        return {
            "systemMessage": message,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": message + ". Report this readiness result to the owner.",
            },
        }
    if command_id(event) is None:
        return None
    config = Config.load(config_path)
    if event.get("session_id") != config.data.get("hook_approval", {}).get("session_id"):
        return None
    service = Service(config)
    try:
        result = record_event(service, event)
    finally:
        service.store.close()
    if result is None:
        return None
    command = f"{shlex.quote(sys.executable)} -m vault_retrieval.cli --config {shlex.quote(str(Path(config_path).resolve()))} apply-hook --id {result['proposal_id']}"
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "Explicit approval recorded for this immutable proposal. No files applied yet. "
            "Run the existing local CLI now: " + command + ". "
            "Report the actual result. Do not draft or apply any additional changes.",
        }
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.local.json")
    parser.add_argument(
        "--probe-dir", type=Path, help="Record metadata only; never authorize or write vault files"
    )
    parser.add_argument(
        "--probe-session",
        help="Limit metadata capture to this session or an explicit VAULT_HOOK_PROBE message",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check configuration and host build without reading stdin or approving",
    )
    args = parser.parse_args()
    try:
        if args.check:
            print(canonical(check(args.config)))
            return 0
        raw = sys.stdin.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise VaultError("invalid_event", "Hook payload exceeds the input limit.")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise VaultError("invalid_event", "Hook input must be a JSON object.")
        if args.probe_dir:
            explicit_probe = is_probe(event)
            if (
                args.probe_session
                and event.get("session_id") != args.probe_session
                and not explicit_probe
            ):
                return 0
            result = probe(event, args.probe_dir)
        else:
            result = handle(event, args.config)
        if result:
            print(canonical(result))
        return 0
    except (VaultError, OSError, ValueError, TypeError) as exc:
        reason = (
            exc.message
            if isinstance(exc, VaultError)
            else "Invalid hook input or inaccessible configuration."
        )
        print(canonical({"decision": "block", "reason": reason}))
        return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
