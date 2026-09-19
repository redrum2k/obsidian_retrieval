# Code-quality review — September 19, 2026

Scope: tracked diff against `main`, the untracked native approval implementation, and the intake path implicated by the reported delay. Applied deslop and thermo-nuclear-code-quality-review. No live vault writes, live indexing, hook installation, or approval-key changes were performed.

## High-conviction findings

| Priority | Finding | Resolution |
| --- | --- | --- |
| P1 | Intake owns discovery, extraction, OCR/rendering, index publication and pending reporting in one blocking operation. JSON cannot appear until every eligible extraction finishes. | Fixed the boundary: intake only reconciles discovery; an explicit `extract --ids` indexes selected documents. Eager `refresh --full` remains available. No background queue, worker daemon, second scheduler or new transport. |
| P1 | Every service construction creates an extractor and probes external tools even when the command only needs inventory/status. | Extractor and its heavy module import are lazy. Discovery uses stored extractor metadata; extraction/retrieval still validate the actual extractor version. |
| P2 | Full reconciliation rebuilds unchanged sections/FTS entries, while work-state logic mixes completion, content emptiness and extraction readiness. | Hash-identical eligible revisions retain sections. Work state has one owner; completed revisions no longer get demoted merely because a section is empty. Changed/denied revisions remove active evidence. |
| P2 | Signature algorithms live in the already-large processing coordinator; current-source checks parse the registry twice. | Moved receipt verification to the existing approval boundary and reused the loaded registry. No additional signer abstraction or dispatcher. |
| P1, future scope | A Swift app, protected-key enrollment and two signature modes are disproportionate to the desired conversation approval workflow. | Do not extend that architecture. Specify the simpler host-hook path in a separate one-page PRD; retain existing behavior until the replacement is implemented and validated. Deleting it now would silently break enrolled configurations. |

## Evidence

`uv run pytest -q`: 43 tests pass, including discovery with extractor construction prohibited, explicit selected extraction, restart/cache reuse, failure visibility, registry revocation, old evidence removal, and discovery → extraction → proposal → approval → apply → quiet rerun.

Reproduce the isolated latency experiment:

```sh
uv run python examples/benchmark_intake.py --output /tmp/intake-benchmark.json
```

The committed [report](intake-benchmark.json) uses 12 small Markdown files with a simulated 50 ms extraction delay per file: eager reconciliation took 749.36 ms to serialized bounded JSON versus 18.20 ms for discovery, with 12 pending inputs in both and extractor calls reduced from 12 to zero. JSON serialization/token-budget work itself took under 1 ms in both runs. This establishes the architectural bottleneck without pretending that faster JSON encoding solves OCR latency. It does not measure cold process imports, real scans, live vault size, accuracy, or token savings.

## Remaining concerns / approval bar

- `Service.refresh` still combines filesystem reconciliation and revision publication, and extraction during an explicit refresh remains inside its database transaction. That is acceptable for this single-writer prototype, not a justification for extending it with hook orchestration. A per-revision publisher is the next boundary to extract if concurrent readers/writers become necessary.
- Pending/search results are still materialized before bounded output pagination. Very large corpora will need snapshot-aware database pagination; this work makes no large-corpus complexity claim.
- The existing file writer is recoverable, not a cross-application transaction. Keep the documented missing-path/sync caveats and require real owner authentication testing for the retained native adapter.
- Discovery can still take time for filesystem traversal and hashing. Initial completeness and exclusions cannot be traded for apparent speed. No undocumented automatic background extraction was introduced.
- No Python module crosses 1,000 lines. Merely splitting files would not resolve the blocking ownership problem; the meaningful change is removing extraction from intake's critical path.

Verdict: the intake performance defect is fixed with targeted regression coverage. Do not mark the entire live MVP or native approval integration production-ready on that evidence. The hook is specified, not implemented.
