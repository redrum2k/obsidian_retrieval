"""Isolated extraction-bound latency experiment; never opens the live vault."""

import argparse
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from vault_retrieval.common import canonical
from vault_retrieval.config import Config
from vault_retrieval.coordinator import Coordinator
from vault_retrieval.extract import Extractor
from vault_retrieval.output import page
from vault_retrieval.service import Service


def run(output, documents=12, delay=0.05):
    results = {}
    original = Extractor.extract
    calls = 0

    def slow_extract(self, data, suffix):
        nonlocal calls
        calls += 1
        time.sleep(delay)
        return original(self, data, suffix)

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        vault = root / "vault"
        (vault / "Study/Raw").mkdir(parents=True)
        for i in range(documents):
            (vault / f"Study/Raw/{i}.md").write_text(f"# Capture {i}\nEvidence {i}.\n")
        for mode in ("eager_baseline", "discovery_intake"):
            config = Config(
                {
                    "enabled": True,
                    "vault": str(vault),
                    "state": str(root / mode),
                    "roots": [{"path": "Study", "role": "study", "project": "Study"}],
                    "outputs": ["Study/Notes"],
                    "exclude": [],
                    "processing_log": "Planning/log.json",
                }
            )
            calls = 0
            started = time.perf_counter()
            service = Service(config)
            try:
                with patch.object(Extractor, "extract", slow_extract):
                    refresh = service.refresh(
                        extraction_paths=None if mode == "eager_baseline" else set()
                    )
                pending = Coordinator(service).pending()
                ready = time.perf_counter()
                response = page(
                    [{"refresh": refresh, "pending_count": len(pending)}],
                    service.snapshot(),
                    {"command": "intake"},
                )
                serialized = canonical(response)
                done = time.perf_counter()
                results[mode] = {
                    "before_json_ms": round((ready - started) * 1000, 2),
                    "json_ms": round((done - ready) * 1000, 2),
                    "total_ms": round((done - started) * 1000, 2),
                    "extractor_calls": calls,
                    "pending": len(pending),
                    "response_bytes": len(serialized.encode()),
                }
            finally:
                service.store.close()
    report = {
        "fixture": "isolated Markdown with simulated per-file extraction delay",
        "documents": documents,
        "simulated_delay_ms": delay * 1000,
        "results": results,
        "limitation": "Not a live-corpus benchmark or an accuracy/token-savings evaluation.",
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
