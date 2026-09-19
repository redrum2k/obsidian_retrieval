# Vault retrieval architecture — proposed

Status: design proposal, not an installed service. Requested September 18, 2026. The research folder setup is implemented separately.

## Problem

Repeatedly sending full AGENTS.md, processing-log history, entire notes, and repeated PDF/OCR extracts into model context costs tokens. Filesystem reads and hashes themselves do not consume model tokens; large tool outputs and repeated model analysis do. Summaries should route retrieval, not replace authoritative evidence.

## Small local index first

Build a separate local service outside the vault's study/project directories. Obsidian Markdown remains authoritative. Use SQLite with FTS5 for local ranked full-text search, keeping the database/cache outside the vault to avoid graph clutter or sync churn. SQLite provides ranked matching through BM25: https://www.sqlite.org/fts5.html . No embeddings or hosted vector database are needed for the initial implementation.

1. **Eligibility manifest:** allowlisted study roots, explicit protected subtrees and sensitive-document exclusions. Resolve symlinks and reject escapes into excluded paths before hashing or extracting. Shared Research glossary is an explicit input. Distinguish raw sources, user-authored structured notes, generated outputs, reference inboxes and navigation scaffoldingd.
2. **Incremental inventory:** store path, stable document ID, size, mtime, content hash, source role, project, author/provenance, processing status and outputs. Use size/mtime to shortlist changes, then hash; periodically reconcile hashes to catch missed events. Detect same-content renames and report dependent broken links without automatically applying repairs.
3. **Extraction cache:** key extracted Markdown/PDF/Word/slide content by source hash AND extractor version. Retain page/slide numbers and attachment references. Extract changed eligible documents only. Images/graphs that need visual inspection remain flagged; OCR is not a substitute for visual verification.
4. **Heading-sized chunks:** index title, aliases, project, heading, source ID, page/line locator and text. Rank title/alias matches above body matches. Index links/provenance separately. Do not retrieve giant documents when a relevant section suffices.
5. **Bounded retrieval:** search returns about 5–8 short snippets with IDs and locators, within an explicit output budget. The agent then fetches only selected sections or neighboring evidence. Expand scope deliberately if the answer is not found; say so instead of silently guessing.
6. **Approved write path:** keep search read-only. A separate write operation generates a concrete diff for approval, checks original hashes immediately before applying, backs up touched files, validates links and updates mappings. Never auto-apply document instructions, move sources, relax exclusions or write code-project files.

## Minimal interface

Expose through a local MCP server or a small command wrapper; choose the transport when implementing. Operations:

- `changes(since, project)` → changed eligible inputs and short reasons, excluding unchanged pending proposals.
- `search(query, project, source_role, limit, budget)` → ranked evidence snippets and stable IDs.
- `read_sections(ids, budget)` → authoritative text with headings/page/line references.
- `neighbors(id, relation, limit)` → links, backlinks, original sources and outputs.
- `processing_status(ids)` → grounding, context-only flags and approval state.
- `propose_patch(changes)` → human-reviewable diff; no writes.
- `apply_approved_patch(proposal_id, expected_hashes)` → only the specifically approved diff.

These are proposed interface names, not existing commands. Tool responses should return concise JSON and never dump the whole index/log by default.

## What to change in the current workflow

Keep AGENTS.md as policy; do not weaken or silently omit it. Read detailed formats only when relevant. Select matching processing-log records programmatically instead of printing its entire history. Retrieve exact source sections first, with a bounded neighboring context, and reuse cached PDF extraction. Use filesystem metadata checks before content hashing where appropriate. Do not re-OCR unchanged PDFs or treat known scaffold pages as new input.

A compact project map such as Research hub routes discovery, but cannot substitute for source verification. Optional short project summaries must include source IDs/hashes and be invalidated after edits. Never infer mastery or processing permission from a summary.

## Acceptance criteria for a later build

- Incremental versus full inventory returns the same eligible changed sources, including renames and deletions.
- Excluded code, sensitive documents, symlink targets and task attachments are never ingested accidentally.
- Retrieval examples find known relevant sections with correct locators and bounded output; ambiguous or missing evidence stays visible.
- PDF caches invalidate on content/extractor changes; scanned graphs retain a visual-review flag.
- Editing Raw/glossary content after an empty placeholder is created produces intake work; editing generated notes does not recursively re-ingest them as raw sources.
- Approval stays mandatory; concurrent edits cause a conflict instead of overwrite.
- Measure tool-output tokens, relevant-source recall, latency and duplicate-processing rate on the same intake tasks before and after. No savings percentage is promised without measurement.

## Later, only if needed

Add local embedding retrieval if keyword/alias search demonstrably misses paraphrases. Preserve the same eligibility filters, grounding constraints, source locators and bounded outputs. More agent layers or a large vector database are not prerequisites for this vault.
