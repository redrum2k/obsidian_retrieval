# Existing conversation host integration

The selected interface is the `vault` CLI. There is no MCP server or new scheduler. The external heartbeat owns Monday/Wednesday/Friday/Sunday at 12:10 p.m. `America/New_York`; `vault schedule` is a pure inspection operation.

## Intake protocol

1. Read current vault policy and applicable topic conventions. Call `intake --quiet` with an approved enabled config. It refreshes inventory and returns bounded counts, preserving work across missed/failed runs.
2. If `needs_planning`, call `pending` and page through its results. Raw/glossary entries come first. `awaiting_grounding` entries contain discovery metadata only; resolve their role/authorship before expecting evidence retrieval. Context-only readings cannot initiate new notes. A failed extractor appears in `health`/refresh failure counts and remains unprocessed.
3. Use `search`, `read-sections`, `neighbors`, `processing-status`, and selected `visual` renders to retrieve changed sources and relevant existing notes. Respect a total task budget. Do not replace policy reads with search or dump entire logs. Plan in bounded batches (at most 20 source revisions and 20 note changes).
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

The write path accepts Ed25519 signatures. A trusted owner-facing host/broker must hold the private key outside the agent's access and sign only after an explicit approval event for the exact review artifact. A tool argument such as `approved: true` is never accepted.

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

`approval_public_key` is the base64 raw Ed25519 public key in owner configuration. The proposal JSON artifact contains the exact body being hashed, including configuration revision, source revisions, target preconditions, full content, and registry diff. The signer must verify that body matches what the owner reviewed. Do not give the agent a private-key helper or let it mint its own trusted receipt.

The real Codex conversation-to-receipt bridge is **not connected**. There is no claim that a conversation reply already produces a verifiable signature. This is a release gate to resolve before live writes. The existing conversation can remain the notification/approval surface if its trusted host exposes the necessary event; otherwise the owner must choose an approval integration explicitly.

## Apply and recovery

Call `apply --id ID --receipt FILE` only after obtaining that receipt. A signed approval does not authorize a different diff or configuration. Hash conflicts reject preflight before any new mutation; partial failures preserve the per-action journal and backups. Matching outputs are reused on retry, including a crash after creation but before the log update. Completion is recorded only after all file/log hashes match the approved output. No batch completion means study mastery.

The host should read back the result, report actual changes and uncertainties, and refresh retrieval. A repeated completed apply is a no-op. For divergent files or a changed registry baseline, prepare a new proposal; do not reinterpret old approval as permission to overwrite.
