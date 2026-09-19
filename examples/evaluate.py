"""Reproducible synthetic retrieval smoke benchmark; not the owner's release evaluation."""

import argparse
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path

from vault_retrieval.common import canonical
from vault_retrieval.config import Config
from vault_retrieval.output import ENCODING, page
from vault_retrieval.service import Service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vault-evaluation-") as temporary:
        root = Path(temporary)
        vault = root / "vault"
        (vault / "Study/Raw").mkdir(parents=True)
        (vault / "Planning").mkdir()
        source = "\n".join(
            f"# Topic {i:02d}\nThe marker term{i:02d} identifies evidence for topic {i:02d}.\n"
            + "Background detail unrelated to the marker. " * 60
            + "\n"
            for i in range(30)
        )
        (vault / "Study/Raw/Handbook.md").write_text(source)
        (vault / "Planning/Processing log.json").write_text('{"sources":[]}')
        config = Config(
            {
                "enabled": True,
                "vault": str(vault),
                "state": str(root / "state"),
                "roots": [{"path": "Study", "role": "study", "project": "sample"}],
                "exclude": [],
                "outputs": ["Study/Notes"],
                "processing_log": "Planning/Processing log.json",
            }
        )
        service = Service(config)
        refresh = service.refresh()
        rows, latency = [], []
        baseline_tokens = len(ENCODING.encode(source, disallowed_special=()))
        for i in range(30):
            query = f"term{i:02d}"
            start = time.perf_counter()
            results = service.search(query)
            latency.append((time.perf_counter() - start) * 1000)
            search = page(results, service.snapshot(), {"query": query}, 2000, 8)
            reads = page(
                service.read_sections([r["id"] for r in search["items"]]),
                service.snapshot(),
                {"operation": "read-sections"},
                4000,
                20,
            )
            rows.append(
                {
                    "task": i,
                    "gold_heading": f"Topic {i:02d}",
                    "gold_found": any(r["heading"] == f"Topic {i:02d}" for r in reads["items"]),
                    "baseline_tool_tokens": baseline_tokens,
                    "retrieval_tool_tokens": search["output_tokens"] + reads["output_tokens"],
                }
            )
        unchanged = service.refresh(full=True)
        baseline = sum(r["baseline_tool_tokens"] for r in rows)
        actual = sum(r["retrieval_tool_tokens"] for r in rows)
        report = {
            "kind": "synthetic_smoke_not_release_evaluation",
            "tasks": len(rows),
            "corpus_files": 1,
            "corpus_bytes": len(source.encode()),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "baseline": "one full source read per lookup; policy/agent costs not modeled",
            "tool_output_reduction_percent": round(100 * (1 - actual / baseline), 2),
            "exact_lookup_recall": sum(r["gold_found"] for r in rows) / len(rows),
            "warm_search_p95_ms": round(sorted(latency)[28], 2),
            "warm_search_median_ms": round(statistics.median(latency), 2),
            "unchanged_extractor_executions": unchanged["extracted"],
            "cold_refresh_ms": refresh["duration_ms"],
            "limitations": [
                "Synthetic exact matches only; not owner-labeled held-out tasks",
                "No answer-quality or paraphrase evaluation",
                "No production latency/token savings claim",
            ],
            "results": rows,
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(canonical({k: v for k, v in report.items() if k != "results"}))
        service.store.close()


if __name__ == "__main__":
    main()
