> Current chat-approval setup: [activation and pilot](hook-approval-setup.md). The origin mismatch is resolved for the pinned desktop build. Signed receipt instructions below apply only to signed mode.

> For the requested chat-command workflow, use [hook approval setup](hook-approval-setup.md). The hook adapter is implemented but live activation requires owner hook trust and the approved-batch pilot. Native signing below remains an optional existing path, not a prerequisite for the proposed conversation flow.

# Connect the existing heartbeat and evaluate the workflow

## Current boundary

The existing manual conversation workflow remains separate. This CLI has tested proposal, create/update, registry, and recovery operations, and now has a local macOS review/signing adapter awaiting owner enrollment and manual authentication validation. A chat reply alone cannot currently invoke its approved-write path. Do not install an agent-accessible signing key as a shortcut. Live configuration remains a disabled review draft.

## Connection plan: intake first, approval second

There are two connections. The first is a configuration/prompt change. The second uses the newly implemented native review adapter and requires owner enrollment plus a manual authentication check. The signature requirement is this project's implementation choice, not an OpenAI requirement. No hidden Codex setting turns a chat reply into a receipt.

### 1. Prepare the local installation

From a terminal:

```sh
cd /Users/nikitaafanaskin/Documents/Developer/obsidian_retrieval
uv sync
uv run pytest -q
uv run vault --config examples/live-config.proposed.json validate
```

`validate` checks the disabled proposal without indexing study content. Review the exact roots, input rules, exclusions, output folders and policy pin in `examples/live-config.proposed.json`. Keep Huyen deferred. After the owner's configuration review, copy it to ignored `config.local.json` and set `enabled` to `true`. Leave `approval_public_key` unset for retrieval-only rollout. Do not copy a test signing key into the live configuration.

Check the current vault AGENTS.md against the pinned hash before enabling. If changed, review its meaning and configuration implications; do not blindly update the hash. Vault and external state must be on the same filesystem for approved writes. Neither the live configuration nor the heartbeat has been enabled/changed by this guide.

### 2. Run one manual intake check

After configuration review and enabling:

```sh
uv run vault --config config.local.json intake --quiet
uv run vault --config config.local.json pending
uv run vault --config config.local.json health
# Select relevant IDs from pending; this operation may run OCR/converters:
uv run vault --config config.local.json extract --ids DOCUMENT_ID
```

Intake discovers/hashes eligible files without extraction; `extract` indexes only selected documents. These commands update external state and do not write notes. An optional `refresh --full` deliberately extracts the whole eligible corpus and can be slow. Inspect failures and pending entries, page every continuation, and verify Raw/glossary priority. New filenames matching configured shapes need no filename-by-filename admission. Grounding for note creation remains separate. For production proposal processing, validate essential Office/scan renderers and representative corpus coverage first.

Have the existing conversation retrieve a small changed capture, draft one grounded plan following `docs/host-integration.md`, and submit `propose --plan FILE`. Verify its full diff, source revisions, output destinations and registry action. This demonstrates discovery → proposal without applying it. Failed/missed checks retain work.

### 3. Update the existing heartbeat

In the desktop app's **Scheduled** area, select **Review incoming vault notes**, ID `review-incoming-vault-notes`. Update that task rather than creating another. Preserve its existing target conversation and the complete task-attachment lifecycle instructions. Keep Monday/Wednesday/Friday/Sunday at 12:10 p.m. **America/New_York**. Verify the displayed timezone; the recurrence string alone does not establish timezone behavior. Local scheduled work requires the computer on, the app running, and project files accessible.

Append these instructions to its existing prompt:

```text
Use the local retrieval CLI for intake. Preserve all existing vault policy,
source-grounding, privacy, attachment lifecycle, and explicit-approval rules.
Read /Users/nikitaafanaskin/Documents/Developer/obsidian_retrieval/docs/host-integration.md
and use its plan schema and bounded retrieval protocol. Run:

uv run --project /Users/nikitaafanaskin/Documents/Developer/obsidian_retrieval vault --config /Users/nikitaafanaskin/Documents/Developer/obsidian_retrieval/config.local.json intake --quiet

Page pending work. For selected needs_extraction document IDs, call extract
--ids before retrieval; never substitute refresh --full for a scheduled check.
Retrieve changed Raw/glossary inputs first, then eligible
study documents, plus relevant existing notes. Submit one concrete grounded
plan using propose --plan FILE. Deliver its complete review artifact in this
conversation; acknowledge its proposal ID only after delivery. Stay quiet for
no changes or an unchanged already-delivered proposal. Preserve failed work.
Never treat silence, a timeout, or a scheduled invocation as approval.
Do not call apply until the trusted approval adapter is enrolled/validated and the
exact batch has explicit human approval. A chat reply alone is not currently
a usable CLI approval receipt. Report that limitation rather than bypass it.
Keep the existing separately authorized attachment lifecycle in this prompt.
```

Use absolute paths so the heartbeat may keep its existing vault working directory. The CLI runs locally via `uv`; no MCP server, new scheduler, webhook, or email service is needed. If `uv` is unavailable to that host, resolve/install it in the host environment and retest; do not infer connection from a successful command in a different terminal.

Run the updated prompt manually against an isolated sample first, then inspect the first actual scheduled run. Confirm one delivered proposal, acknowledgment only after delivery, and silence on the next unchanged invocation. Keep the current lifecycle behavior intact. Official management guidance: [Scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app).

### 4. Set up and validate the approval adapter

The macOS adapter is now implemented. Follow [approval-adapter.md](approval-adapter.md) for exact build, owner enrollment, public-key configuration, review-request export, receipt generation and apply commands. This supersedes the earlier instruction to build a signer from scratch.

It keeps proposal delivery in the conversation and uses a native local review window plus macOS owner authentication for final approval. A chat reply alone still does not generate a receipt. Native authentication and the real host boundary require manual validation before live release; do not treat automated fixture signatures as owner approval.

After that validation, use the heartbeat amendment in the adapter guide, preserving the existing schedule and attachment lifecycle. No automation settings have been changed by this implementation.

### 5. Rehearse end to end, then release

Use a disposable representative vault copy: new capture → intake → one delivered proposal → owner review/approval via the real adapter → note creation/update → compatible registry update → next unchanged run and restart produce no duplicate proposal. Include a missed run, failed delivery, interrupted application, and concurrent save. Verify hashes, source preservation, existing custom log fields, links, and incomplete-work retention.

Then run the owner-labeled accuracy/token evaluation below. A live batch still requires its own concrete approval. Connecting intake does not grant autonomous writing, enable Huyen, or approve all discoverable readings.

## Run the existing checks

From this project:

```sh
uv run pytest -q
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run pytest -q tests/test_processing.py::test_scheduled_end_to_end
uv run python examples/evaluate.py --output /tmp/obsidian-retrieval-smoke.json
```

The end-to-end test uses an isolated vault and test-only signer. The synthetic evaluation is an exact-term smoke test; it cannot establish production savings or accuracy.

## Measure actual benefit

1. Freeze an approved evaluation corpus or isolated copy with hashes and policy. Select at least 30 representative questions: exact terms, aliases, paraphrases, cross-note provenance, ambiguous/no-evidence cases, PDF/scan/slide tasks, and changed-input intake. Label relevant source sections, valid answers, and expected abstentions. Reserve at least 10 held-out tasks; tune only on the others.
2. Run each task twice in separate fresh sessions with the same model, instructions, corpus and policy: existing whole-file workflow, then retrieval. Save all tool responses across the whole task, including errors, expansions, policy, and fallback reads. Record model input/output usage separately where available. Do not compare one search call with an entire baseline task.
3. For each task record: baseline/retrieval tool-output tokens using the pinned tokenizer; repeatedly delivered source-span tokens; retrieved versus gold sections; correctness/support/abstention pass; provenance errors; latency; extraction executions. Report per-task and aggregate results, including regressions. Owner scoring uses a fixed rubric chosen before held-out execution.
4. Apply PRD gates: at least 40% aggregate tool-output reduction, 50% fewer repeated evidence tokens where baseline repetition exists, at least 95% evidence recall and no worse than baseline, no worse answer pass rate, 100% fixture provenance correctness, zero unchanged successful re-extractions, and p95 warm search at most 500 ms on recorded hardware/corpus. Safety checks must all pass. The complete-task trace collection/scoring harness is still to be implemented; the synthetic script is not that harness.
5. Once the approval integration and the documented write-recovery limitations are validated, run an owner-approved batch against a disposable representative vault copy: add a capture, trigger intake, deliver one exact proposal, confirm no writes before approval, approve via the real adapter, verify created/updated note hashes and registry mappings/completion, then rerun unchanged and after restart. Both reruns must create no new proposal. Repeat with a missed trigger and a failure before log completion; unfinished work must survive. Only then exercise an explicitly approved live batch.
