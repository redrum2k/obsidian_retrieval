# Local vault retrieval

A Python CLI for local SQLite FTS5 retrieval, cached document extraction, durable intake proposals, and explicitly approved note/log updates. The retrieval service and processing coordinator are separate modules. The existing external automation remains the scheduler.

**Current status:** implemented and tested against isolated vaults. Live indexing is disabled. The proposed live configuration excludes Huyen for now. A real-corpus evaluation and trusted conversation-approval adapter are required before live release; see [implementation status](docs/implementation-status.md).

## Install and verify

Requires Python 3.12+ and `uv`. Dependencies are pinned in `uv.lock`.

```sh
uv sync --locked
uv run vault --help
uv run pytest -q
uv run ruff check src tests examples
uv run python examples/evaluate.py --output docs/synthetic-evaluation.json
```

The tokenizer is `cl100k_base`, supplied by the pinned tiktoken dependency. Its first use downloads tokenizer data if absent from the local cache; no vault content is sent. Bootstrap it before offline use:

```sh
uv run python -c 'import tiktoken; tiktoken.get_encoding("cl100k_base")'
```

Markdown, DOCX and PPTX text extraction use local libraries. PDFs use PyMuPDF; scan OCR uses the locally installed `tesseract` executable and configured language data. Office rendering and legacy DOC/PPT/ODT/ODP conversion require `soffice` (LibreOffice). Missing render/OCR dependencies are visible and block processing of affected visual evidence. Extraction never modifies originals. PyMuPDF is AGPL/commercial licensed; review that dependency before redistributing this application.

## Configuration and access

Copy [examples/config.json](examples/config.json), set an existing vault path and a separate state directory, define explicit roots/exclusions/output folders, and review the result. Configuration remains disabled until `enabled` is deliberately set to `true`.

```sh
uv run vault --config config.local.json validate --budget 8000
uv run vault --config config.local.json refresh
uv run vault --config config.local.json refresh --full
```

The live proposal is [examples/live-config.proposed.json](examples/live-config.proposed.json); its scope and remaining decisions are explained in [docs/live-configuration.md](docs/live-configuration.md). Do not enable it before the owner's configuration review. No live index was created during implementation.

State contains a private SQLite database, extraction/render caches, immutable proposal artifacts, and backups. Keep it outside the vault, synced directories, and agent-accessible approval key storage. Root selection is explicit; sensitive-name filters and protected infrastructure exclusions always apply. All symlinks and hardlinks are conservatively rejected. Eligible CS study documents can coexist with protected code directories; other marked code projects are excluded in full.

The current vault `AGENTS.md` hash can be pinned in `policy`. A policy change blocks operations until its meaning is reviewed and configuration updated. This check does not replace the agent's duty to read and follow policy and relevant conventions.

## Evidence retrieval

```sh
uv run vault --config config.local.json search --query 'row operations' --project CS132
uv run vault --config config.local.json read-sections --ids SECTION_ID --budget 4000
uv run vault --config config.local.json neighbors --id SECTION_ID --relation adjacent
uv run vault --config config.local.json changes --since 0
uv run vault --config config.local.json processing-status --ids DOCUMENT_ID
uv run vault --config config.local.json visual --id DOCUMENT_ID
uv run vault --config config.local.json health
```

Responses are JSON. Every accepted response fits its requested token budget, including metadata and the final newline. Defaults: 2,000 tokens, 4,000 for section reads, up to 8 items. Limits: 256–8,000 tokens, 1–20 items/IDs. Metadata-heavy items may require a larger budget. Errors return concise JSON and exit code 2; success returns 0.

Use the returned opaque `continuation` with the same operation/filters. Section spans include exact character offsets within their located extracted section. Changed results invalidate continuations explicitly. `changes --since` uses the event sequence shown as `seq`; store it only after consuming its event. Pending processing work is independent of that cursor.

Titles and aliases receive higher FTS ranking weights than body text. Queries are treated as literal terms, not executable FTS syntax. Source hashes are checked before evidence is returned; stale results are withheld and flagged. Context-only sources are metadata-only unless a named integration permission is configured. No embeddings or hosted index is used.

## Scheduled processing

```sh
uv run vault --config config.local.json intake --quiet
uv run vault --config config.local.json pending
uv run vault --config config.local.json notifications
```

The existing heartbeat invokes `intake` Monday, Wednesday, Friday, Sunday at 12:10 p.m. `America/New_York`. `schedule` computes the next time for inspection; it creates no timer. Intake refreshes before reporting retained work, with Raw/glossary priority. It does not synthesize arbitrary study notes: the existing agent prepares a concrete grounded plan using bounded evidence and relevant existing notes.

```sh
uv run vault --config config.local.json propose --plan plan.json
uv run vault --config config.local.json notifications
uv run vault --config config.local.json acknowledge --id PROPOSAL_ID
```

`--plan -` accepts JSON on stdin. `intake --plan plan.json` can refresh and submit a prepared plan in one operation. Plans contain exact full output contents, expected target hashes (null for new files), input revisions, source/output mappings, grounding, visual-review coverage where needed, and uncertainties. The service generates the matching JSON-registry change while preserving unknown existing fields. See [the host integration contract](docs/host-integration.md).

Proposal artifacts outside the vault include the complete diff and source provenance. The host posts one proposal to the existing conversation, then acknowledges delivery using its stable ID. An unchanged delivered pending proposal stays quiet. Failed/ambiguous delivery remains retryable; the host must deduplicate by proposal ID. Do not acknowledge before delivery or treat delivery/silence as approval.

Application requires a signed approval receipt from a trusted owner/host boundary:

```sh
uv run vault --config config.local.json apply --id PROPOSAL_ID --receipt receipt.json
```

There is intentionally no `--approved`, `--yes`, or agent-accessible signer. The configured public key verifies a receipt bound to the exact proposal digest. The existing conversation approval bridge is not connected; live writes remain unavailable until it is. Test keys exist only in temporary test fixtures.

Notes remain drafts. Processing completion means verified output files plus the approved processing-log update, not learning/mastery. Failed or missed checks retain work; source changes supersede stale proposals. Writes retain backups and durable per-file intent so retries reuse matching outputs. Original sources, code, settings, and task attachments remain protected.

## Recovery and limits

- Run `refresh --full` to reconcile content hashes even when size/mtime match; run `rebuild` to reconstruct search sections while preserving identity/work/approval records.
- Never delete the entire state directory to rebuild search. Back it up securely: it includes non-rebuildable pending proposals and application history. No automatic history/backup expiry is currently configured.
- A failed multi-file application remains incomplete. Retry the same signed receipt only if sources and targets still match; divergent user edits require a new reviewed plan. Do not blindly restore backups over newer content.
- Writes use staged files, no-follow path access, source/target checks, and exclusive coordination between this tool's processes. Ordinary filesystems do not offer atomic compare-and-swap against unrelated editors. A noncooperating editor can still race the final check/replacement; this is a live-release limitation, not a claim of cross-application transactional isolation.
- No production token-saving, recall, or latency target is claimed from synthetic tests. No Obsidian rendering or existing scheduler connection has been verified.

Implementation references: [SQLite FTS5 ranking](https://www.sqlite.org/fts5.html), [PyMuPDF page extraction/rendering](https://pymupdf.readthedocs.io/en/latest/page.html).
