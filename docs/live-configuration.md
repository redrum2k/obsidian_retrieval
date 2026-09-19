# Proposed live configuration — disabled

The owner requested isolated-vault implementation first and an exact configuration proposal before live indexing. [The machine-readable proposal](../examples/live-config.proposed.json) therefore has `enabled: false` and no approval public key. Validation reads only named operational files and directory names needed for future-CS discovery; it does not index sources or create a live state directory.

## Included study roots

- `Fall_2026/RN103`, `EC204`, `EC422`, `CS132`, `CS330`
- `Leetcode`, `Research`, `Engineering`, and eligible `Daily` captures
- Future `CS<number>` course folders beneath `Fall_YYYY`, `Spring_YYYY`, `Summer_YYYY`, or `Winter_YYYY`, with identical protections. Other semester naming patterns require configuration review.
- Research filters distinguish King, CheYu Lee, and Van Alstyn.

Huyen is deferred and excluded from the initial configuration. Nothing in Huyen was modified.

Raw folders receive intake priority. Explicit glossary inputs are `Research/Shared/Glossary inbox.md` and `Research/CheYu Lee/Raw/DNA glossary inbox.md`. The registry's known generated outputs and workspace scaffolding do not become new raw sources; empty known glossary placeholders are reconsidered after their content changes.

## Outputs after batch approval

- `Leetcode/Problems`
- `Fall_2026/<listed course>/Notes` and `Concepts`; corresponding folders for future CS courses
- `Research/<King|CheYu Lee|Van Alstyn>/Notes`
- `Engineering/Weeks`, `Engineering/Code Archaeology`, `Engineering/Concepts`
- New faithful Markdown companions in the listed Raw folders only when the exact approved plan labels them `derived_companion: true`, records the original source, and adds their generated-output mapping. Original captures cannot be replaced.

New output folders are created only as needed by an approved file action. Empty concept notes are rejected. Existing structured-note destinations outside these folders need an explicit configured role/destination before an update; this proposal does not silently authorize dashboard, global task, or unrelated note changes.

## Operational reads and registry

The policy is the current `AGENTS.md`, pinned by hash in the proposal. A changed policy requires review rather than automatic widening of access.

`Planning/Processing log.json` is read for source hashes, user-note provenance, context-only restrictions, generated outputs, and completion state. Approved writes preserve its schema and unknown fields. `Planning/Task attachment lifecycle.json` contributes attachment exclusions; this retrieval service does not execute its separately authorized move lifecycle. `Planning/Vault convention changes.md` is available for operational context, not ingestion.

Proposal/diff artifacts and execution journals currently live outside the vault. The existing dated Planning proposal/report files are not automatically written by this implementation; the conversation host can reference the external full diff. Selecting a compatible dated report writer remains an integration decision, not blanket permission to rewrite Planning.

## Exclusions and grounding

Denied: sensitive professional/legal files; `.obsidian`, Templates, Planning as study input, policy/infrastructure Markdown, code/scripts/notebooks/datasets, environments, dependencies, caches/build output, IDE/VCS metadata, the entirety of `Fall_2026/EC204/Data/Starting set`, and task attachments including `Daily/nikita-evo2.pdf`. Sensitive-name matching is conservative; it cannot prove an ambiguously named file is harmless. Ambiguous files must remain outside approved ingestion until reviewed.

CS study-document access is allowed within project trees; code/infrastructure subtrees still remain excluded. Other marked code projects are excluded in full. Links do not confer access; all symlink and hardlink paths are rejected in this first version.

`input_rules` admit new filenames automatically inside eligible Raw, documents, slides, lectures, assignments, and labs folders for the listed Markdown, PDF, Word, and slide formats. Explicit glossary paths and dated Daily Markdown captures are also admitted. Patterns are case-sensitive vault-relative shell patterns (`*` includes nested paths); they never widen allowed roots or override exclusions. Huyen remains excluded.

Admission allows cached extraction and evidence retrieval, not an authorship claim or permission to generate notes. Known context-only restrictions still win unless a named-source integration permission exists. Generated outputs remain excluded from fresh intake. New unconfigured shapes stay metadata-only under `require_grounding_for_index`; unsupported formats remain excluded. No individual filename update is needed for new files matching existing rules. Proposals still require user-note grounding or named-source authorization, followed by exact-batch approval. Previously blocked inputs become pending after admission and refresh.

## Before enabling

1. Review the exact JSON roots, exclusions, output destinations, and conservative grounding rule.
2. Validate representative permitted corpus files and required local converters/renderers. Tesseract is installed; LibreOffice was not found on this machine during implementation. Office text extraction works, but Office visual processing remains blocked until rendering is available and verified.
3. Wire the existing conversation's trusted approval event to signed receipts without giving the agent a signing key. That bridge is not installed or assumed to exist.
4. Run the owner-labeled baseline and held-out evaluation before declaring the PRD's release targets met.

The existing `review-incoming-vault-notes` heartbeat is unchanged. No duplicate scheduler, notification channel, live index, or live study-note write has been created.
