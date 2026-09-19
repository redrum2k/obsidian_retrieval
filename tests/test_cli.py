import json
import subprocess
import sys

from vault_retrieval.common import canonical
from vault_retrieval.output import ENCODING


def call(config, *args):
    return subprocess.run(
        [sys.executable, "-m", "vault_retrieval.cli", "--config", str(config), *args],
        capture_output=True,
        text=True,
    )


def test_cli_help_errors_search_and_quiet(env, tmp_path):
    service, _, data = env
    config = tmp_path / "config.json"
    config.write_text(json.dumps(data))
    for name in ["search", "intake", "propose", "apply", "pending", "notifications"]:
        result = call(config, name, "--help")
        assert result.returncode == 0 and "Examples:" in result.stdout
    missing = call(config, "search")
    assert missing.returncode == 2 and json.loads(missing.stdout)["error"] == "invalid_input"
    assert call(config, "refresh").returncode == 0
    search = call(config, "search", "--query", "Gaussian", "--budget", "1000")
    payload = json.loads(search.stdout)
    assert payload["items"]
    assert payload["output_tokens"] == len(ENCODING.encode(search.stdout, disallowed_special=()))
    assert canonical(payload) + "\n" == search.stdout
    assert call(config, "search", "--query", "Gaussian", "--limit", "200").returncode == 2
    data["enabled"] = False
    config.write_text(json.dumps(data))
    assert json.loads(call(config, "refresh").stdout)["error"] == "disabled"


def test_policy_change_prevents_service(env, tmp_path):
    _, _, data = env
    from pathlib import Path

    from vault_retrieval.common import digest

    policy = Path(data["vault"]) / "AGENTS.md"
    policy.write_text("Approved policy")
    data["policy"] = {"path": "AGENTS.md", "sha256": digest(policy.read_bytes())}
    config = tmp_path / "config.json"
    config.write_text(json.dumps(data))
    assert call(config, "health").returncode == 0
    policy.write_text("Changed policy")
    assert json.loads(call(config, "health").stdout)["error"] == "policy_changed"
