# Implementation status

Updated September 19, 2026. This is a working personal deployment, not a completed general release. The owner reports that the connected heartbeat/chat-approval workflow appears to work. That report is distinct from automated fixture verification and does not establish all PRD release gates.

## Implemented

- Local SQLite FTS5 retrieval, provenance, bounded JSON output, and continuation cursors.
- Incremental inventory, reconciliation, stale-source checks, extraction caching, and rebuilds that retain workflow state.
- Explicit eligibility, code/privacy exclusions, source grounding, and policy-change checks.
- Discovery-only intake, explicit selected-document extraction, durable pending work, and proposal delivery deduplication.
- Exact proposals for note creation/update and compatible processing-registry changes.
- Signed-receipt approval and a native macOS Secure Enclave review/signing app.
- Desktop UserPromptSubmit approval, same-turn `apply-hook` handoff, exact-batch binding, replay protection, and build compatibility checks.
- Backups, conflict capture, and interrupted-application recovery with the limitations described in [write safety](write-safety.md).

The personal configuration is enabled locally, with Huyen deferred. It and all enrolled keys/runtime state are excluded from Git. The existing heartbeat prompt was updated; no duplicate scheduler was created. The production probe passed configuration and build checks, and the owner subsequently reported a working trial. Follow [hook setup](hook-approval-setup.md) for current deployment instructions.

## Verification

- **70 Python tests passed.** Ruff lint and formatting checks passed.
- Native Swift review-parser checks passed, including Unicode, canonical messages, tampered content, and malformed input.
- Isolated tests exercise hook stdin → recorded approval → returned CLI command → note/log application → quiet unchanged intake, plus invalid origins, conflicts, retries and host upgrades.
- Source inspection for the matching desktop release establishes hook dispatch behavior; [host evidence](hook-host-evidence.md) records that boundary. Fixture tests are not a claim of live host testing for every synthetic origin.
- PyMuPDF emits dependency deprecation warnings; these do not fail the suite.

Automated tests generate disposable keys and notes. They do not enroll owner keys or approve real batches.

## Performance evidence

The [synthetic retrieval report](synthetic-evaluation.json) uses 30 exact-term tasks on a synthetic document. Its roughly 93% tool-output reduction is a smoke result, not a production savings claim. The [intake benchmark](intake-benchmark.json) demonstrates that avoiding simulated extraction delays speeds discovery responses; it does not measure real scans, cold startup, or retrieval accuracy.

## Still to validate or complete

1. Owner-labeled real-corpus evaluation: held-out paraphrases, answer quality, complete-task tokens, repeated evidence, and reference-machine latency.
2. Essential live document-format coverage, especially scans, visual evidence, and Office renderers.
3. Independent capture of complete live apply/retry/unchanged-run evidence; the owner's successful trial is useful but is not a recorded full release evaluation.
4. Real Obsidian/sync behavior during publication and hardware/power-loss recovery. File operations are not a transaction across independent editors.
5. Dated Planning report integration, precise completion-time conventions, and any additional registry consumers beyond the implemented schema support.
6. Retention/expiry defaults and a dedicated human recovery interface. Keep existing recovery state until conflicts are resolved.
7. Host compatibility review after desktop updates. Unknown builds stop chat approval and application until reviewed.

Embeddings remain deferred. Accuracy, provenance, exclusions, and exact approval cannot be traded for token savings. See the [PRD](../prd.md) and [evaluation procedure](connection-and-evaluation.md#measure-actual-benefit).
