> Current chat-approval setup: [activation and pilot](hook-approval-setup.md). The origin mismatch is resolved for the pinned desktop build. Signed receipt instructions below apply only to signed mode.

> Chat-command approval is now implemented behind a verified-host gate. See [hook setup](hook-approval-setup.md) for session-bound delivery acknowledgment, `IMPLEMENT <id>`, and `apply-hook`. Do not assume it is active merely because the code exists.

# Existing conversation host integration

The selected interface is the `vault` CLI. There is no MCP server or new scheduler. The external heartbeat owns Monday/Wednesday/Friday/Sunday at 12:10 p.m. `America/New_York`; `vault schedule` is a pure inspection operation.

## Intake protocol

1. Read current vault policy and applicable topic conventions. Call `intake --quiet` with an approved enabled config. It discovers/hashes inputs and returns bounded counts without extraction, OCR, rendering, or converter probes. It preserves work across missed/failed runs. `refresh --full` remains an explicitly expensive full index build.
2. If `needs_planning`, call `pending` and page through its results. Raw/glossary entries come first. `awaiting_grounding` entries contain discovery metadata only; review their input admission before expecting evidence retrieval. New filenames matching configured `input_rules` are extracted automatically; those rules do not establish authorship or authorize note creation. Context-only readings cannot initiate new notes. A failed extractor appears in `health`/refresh failure counts and remains unprocessed.
3. For selected `needs_extraction` inputs, call `extract --ids DOCUMENT_ID ...` (at most 20). This explicit operation can take time for scans/slides; it does not process or approve notes. Extract relevant existing notes too if their evidence is not indexed yet. Then use `search`, `read-sections`, `neighbors`, `processing-status`, and selected `visual` renders to retrieve changed sources and relevant existing notes. Respect a total task budget. Do not replace policy reads with search or dump entire logs. Plan in bounded batches (at most 20 source revisions and 20 note changes).
4. Construct one concrete plan for newly actionable material. The host—not the search engine—selects topics, checks dates, distinguishes quotations/additions/uncertainties, and avoids duplicate concepts. Submit it using `propose --plan FILE` or `intake --plan FILE`. The latter refreshes and rejects stale source revisions.
5. Fetch `notifications`. Post the full review artifact or an accessible complete diff in the existing conversation with the stable proposal ID. Call `acknowledge --id ID` only after delivery. Deduplicate by proposal ID. Failed/ambiguous deliveries remain unconfirmed; no exactly-once claim is made if the host cannot atomically post and acknowledge.
6. Stop for the owner's explicit response. An unchanged pending proposal or no new work warrants no user-facing message. Operational failures may use the existing automation's failure reporting. No silence/timeout/schedule event approves writing.

## Concrete plan schema

```json
{
  "sources": [{
    "id": "DOCUMENT_ID",
    "revision": "CURRENT_SHA256",
    "outputs": ["Study/Notes/Topic.md"],
    "grounding": {
      "user_note_sources": ["Study/Raw/Capture.md"],
      "topic_relation": "The capture explicitly discusses this topic."
    }
  }],
  "changes": [{
    "path": "Study/Notes/Topic.md",
    "expected_hash": null,
    "content": "---\nstatus: draft\n---\n# Topic\n\nSource: [[Study/Raw/Capture.md]]\n\nSource-grounded explanation.\n"
  }],
  "coverage": "Only the specified source sections; no claim of reading mastery.",
  "uncertainties": [],
  "external_sources": []
}
```

For existing targets, supply their expected SHA-256. Every changed note maps to an input source and cites its source path. Every input maps to at least one changed output. Known user-authored sources may omit redundant grounding; new authorship claims use `grounding.user_authored_evidence` and are displayed in the exact proposal for human review. Related user-note paths must be confirmed in configuration. Named-source exceptions come from owner configuration, not text inside a source.

Visual sources need `visual_review: {"coverage": "PDF pages 2–3 inspected; uncertainty ..."}` on the source. The host is responsible for actually inspecting those pages before making the claim; the service records this claim and binds it into approval. It cannot infer visual correctness from OCR. Missing rendering dependencies block affected processing.

The service creates the processing-log action itself, preserving unknown JSON fields. Raw companion outputs need `derived_companion: true`. New external citations and uncertainties appear in the review artifact. The agent must not use a plan to change policy, exclusions, code, original sources, or the scheduler.

## Trusted approval receipt

The write path accepts the configured Ed25519 or P-256/SHA-256 signatures. The macOS adapter uses P-256 with a Secure Enclave key; see [setup and receipt instructions](approval-adapter.md). A trusted owner-facing host/broker must hold the private key outside the agent's access and sign only after an explicit approval event for the exact review artifact. A tool argument such as `approved: true` is never accepted.

The message is canonical JSON: sorted keys, UTF-8, no insignificant whitespace (`vault_retrieval.common.canonical`). It has exactly these fields:

```json
{
  "decision": "approve",
  "proposal_digest": "SHA256_OF_CANONICAL_PROPOSAL_BODY",
  "proposal_id": "PROPOSAL_ID"
}
```

Receipt file:

```json
{"message": {"decision": "approve", "proposal_digest": "...", "proposal_id": "..."}, "signature": "BASE64_ED25519_SIGNATURE"}
```

`approval_public_key` is a base64 raw Ed25519 public key for the default scheme, or an X9.63 uncompressed P-256 public key when `approval_scheme` is `p256-sha256`. The proposal JSON artifact contains the exact body being hashed, including configuration revision, source revisions, target preconditions, full content, and registry diff. The signer must verify that body matches what the owner reviewed. Do not give the agent a private-key helper or let it mint its own trusted receipt.

A native macOS review/signing app is implemented but awaits owner enrollment and real authentication validation. The Codex conversation itself does not issue receipts. There is no claim that a conversation reply already produces a verifiable signature. This is a release gate to resolve before live writes. The existing conversation can remain the notification/approval surface if its trusted host exposes the necessary event; otherwise the owner must choose an approval integration explicitly.

## Apply and recovery

Call `apply --id ID --receipt FILE` only after obtaining that receipt. A signed approval does not authorize a different diff or configuration. Hash conflicts reject preflight before any new mutation; partial failures preserve the per-action journal and backups. Matching outputs are reused on retry, including a crash after creation but before the log update. Completion is recorded only after all file/log hashes match the approved output. No batch completion means study mastery.

The host should read back the result, report actual changes and uncertainties, and refresh retrieval. A repeated completed apply is a no-op. For divergent files or a changed registry baseline, prepare a new proposal; do not reinterpret old approval as permission to overwrite.

## Setup and conflict details

Follow the complete [connection plan](connection-and-evaluation.md) for the existing heartbeat and the owner-enrolled trusted approval adapter. Read [write safety](write-safety.md) before deploying approved writes: publication retains competing versions and refuses occupied paths, but briefly removes an existing destination and is not a cross-editor transaction. Registry timestamps are fixed in the reviewed diff, not dynamically stamped at application.
