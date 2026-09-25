"""Exercise a fresh process: warm imports must not hide a network dependency."""

import os
import subprocess
import sys


def test_startup_without_tokenizer_cache_or_network(tmp_path):
    script = """
import socket

def blocked(*args, **kwargs):
    raise AssertionError("Tokenizer attempted network access")

socket.socket = blocked
from vault_retrieval.output import ENCODING, measured
from vault_retrieval import cli, hook
assert ENCODING.encode("hello world") == [15339, 1917]
assert ENCODING.n_vocab == 100277
assert measured({"ok": True})["output_tokens"] > 0
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "TIKTOKEN_CACHE_DIR": str(tmp_path / "empty-cache")},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
