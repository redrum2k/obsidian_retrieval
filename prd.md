# Local Obsidian retrieval and scheduled processing — product requirements

Status: implementation in progress; local CLI and isolated-vault tests exist. Live indexing remains disabled pending review of the proposed access configuration. Live processing requires an explicitly approved batch and a trusted approval integration.

Date: September 18, 2026. Product owner and primary user: Nikita Afanaskin.

Original design: [architecture-proposal.md](architecture-proposal.md), preserved unchanged. Requirements below define observable behavior; the implementation section identifies proposed ways to meet them.

## 1. Problem and intended outcome

AI agents repeatedly receive whole notes, policy files, processing histories, and PDF/OCR extracts to answer questions or identify new research work. This repeats reading and analysis, consumes context, and obscures which source supports a claim. Filesystem inspection and hashing do not themselves consume model tokens; returning large tool responses does.

The product should let an agent discover and retrieve the smallest sufficient authoritative evidence, reuse prior extraction, and identify changed eligible inputs. Savings must not come from dropping policy, hiding missing evidence, or substituting summaries for sources. Obsidian files remain authoritative; every index, extraction, and indexed relationship is derived and rebuildable. Separately, the existing scheduled intake workflow must retain unprocessed work, request approval once for new actionable material, and complete only the approved note and processing-log changes. Approval and completion history are durable workflow records, not disposable search data.

### What exists today

Inspection of this project found only the original `prd.md`: no application code, dependency manifest, index, cache, tests, or runtime configuration. No applicable `AGENTS.md` was found in the project or its ancestor directories. The proposal says a research-folder setup exists separately; that setup, the actual vault, its policies, corpus size, and agent integrations were not available for inspection. At that initial inspection no implementation existed. Local CLI code and isolated-vault tests now exist; see [implementation status](docs/implementation-status.md) for verified behavior and remaining release gates. The owner confirms an existing external automation can provide scheduled triggers; its integration and notification channel have not been inspected.

### Users and jobs

- **Vault owner:** ask research questions, inspect citations, find newly changed inputs, and control what agents may access or edit.
- **AI agent:** find supporting sections, follow provenance to original evidence, and distinguish unprocessed raw input from generated or context-only material.
- **Local operator (initially the same owner):** configure eligibility, refresh or rebuild derived data, inspect failures, and measure quality and cost.

## 2. Scope and assumptions

### MVP

One user, one local vault, explicit allowlisted study roots plus an explicitly configured shared Research glossary. The MVP provides incremental inventory, cached extraction for corpus-essential formats, section retrieval, provenance/link navigation, processing status, and a read-only local retrieval interface, plus a separate diff-review and explicitly approved vault-write path. SQLite FTS5 is the required initial search engine. No hosted indexing or embedding service is required.

Discovery must cover Markdown, Word documents, PDFs including scans, and lecture slides. M0 must identify actual extensions and representative files, including legacy formats. Formats essential to the approved corpus require usable cached extraction and a visual-review fallback before release; merely listing them as unsupported is insufficient. Nonessential unsupported variants remain visible with an actionable blocked status. See R3 for format-specific behavior.

The existing external scheduler triggers intake Monday, Wednesday, Friday, and Sunday at 12:10 p.m. in the `America/New_York` time zone, respecting daylight saving time. A new scheduler is not required. Each intake run refreshes the index before discovery; manual refresh and on-demand full reconciliation remain available. Continuous watching is optional. The agent must still receive applicable policy and detailed formats when needed. Search cannot replace instruction discovery or permission checks.

**Confirmed scope decision:** MVP includes scheduled discovery, one concrete processing proposal and notification for new actionable material, and explicitly approved creation/update of derived Markdown notes, related links, and processing-log records. Multi-file proposals are supported because this workflow spans notes and logs. Retrieval operations remain read-only; scheduled execution and silence confer no writing permission. Terminology is recorded in [CONTEXT.md](CONTEXT.md).

### Non-goals

A new scheduler, multi-user access, remote hosting, Obsidian plugin UI, autonomous note writing, source moves, automatic broken-link repair, code-project indexing or editing, semantic embeddings, vector databases, autonomous study/mastery judgments, and broad agent orchestration. Generated summaries are optional later routing aids, never primary evidence. Huyen is deferred from the initial live configuration at the owner’s request; no Huyen onboarding or corpus work is required for this release.

## 3. Success measures and evaluation

The first implementation milestone establishes a reproducible baseline before optimization. The following are proposed release targets, not measured results or claims of guaranteed savings. Record any target revision and its reason before running the held-out evaluation.

Use a frozen, approved corpus snapshot and at least 30 representative tasks: direct term/alias lookup, cross-note provenance, paraphrases, ambiguous questions, missing evidence, and changed-input intake. Include Word documents, scanned/text PDFs, lecture slides, glossary edits, and multi-source questions. Evaluate retrieval cost separately from scheduled proposal generation and approved processing cost; report both so savings cannot hide displaced work. The owner labels relevant sections and valid answers or abstentions. Reserve at least 10 tasks as held-out cases; tune only on the remainder. Test change detection separately with controlled edits, renames, deletions, exclusions, and failures.

Compare the existing whole-file/manual workflow with retrieval on identical tasks, corpus, agent/model settings, applicable policy, and tokenizer. Measure cold indexing separately from warm unchanged reruns and changed-file runs. Record per-task results and aggregate totals; do not let a few large-document wins hide accuracy losses.

| Measure | Definition | Proposed release gate |
| --- | --- | --- |
| Tool-output tokens | All text returned to the agent across the complete task, including searches, expansions, errors, policy, and fallback reads | At least 40% aggregate reduction versus baseline |
| Repeated evidence delivery | Tokens from source spans already delivered earlier in the same task, plus duplicate full-document reads | At least 50% fewer repeated span tokens on tasks with baseline repetition; zero unnecessary full-document reads on repeat lookup fixtures |
| Evidence recall | Gold relevant sections obtained by completion of retrieval, including explicit expansions | At least 95% overall and no lower than baseline; report initial recall at 8 separately |
| Answer quality | Owner-scored correctness, supported claims, and appropriate abstention using a fixed rubric | No lower task pass rate than baseline; no unsupported answer on missing-evidence fixtures |
| Provenance correctness | Returned text matches the identified revision and locator | 100% on evaluation fixtures |
| Duplicate processing | Successful extractor executions on unchanged content with unchanged extractor settings/version | Zero during unchanged reruns, including restart |
| Warm search latency | End-to-end local search response time, excluding agent reasoning | p95 at most 500 ms on the recorded reference machine and corpus |
| Scheduled workflow correctness | Missed-run recovery, proposal deduplication, and approval-to-completion tests | All pass; zero duplicate proposals/notifications for unchanged pending or completed work |
| Safety and output limits | Exclusion, read-only, approval, stale-source, and response-budget tests | All pass; cannot trade these for savings |

Record total model input/output tokens as a secondary metric where the host exposes them; tool-output tokens alone are not total inference cost. If a baseline metric is zero, report an absolute count rather than an undefined percentage. Record corpus file/byte/chunk counts, hardware, extraction duration, cache size, failures, and per-format coverage. Corpus scale and the reference machine remain unresolved; validate the latency target in milestone 0.

## 4. User workflows

1. **Configure and establish trust.** The owner names allowlisted roots, Raw/glossary inputs, eligible study documents outside Raw, protected sources, designated output folders, and the existing processing log. Validate eligibility and format coverage without changing vault files. Confirm the existing trigger and notification integration.
2. **Scheduled discovery.** On the configured external trigger, refresh the index, then check Raw/glossary inputs first and eligible study documents outside Raw second. Combine newly changed inputs with retained unprocessed work. Retrieve only changed or still-unprocessed source material and relevant existing notes, using cached extraction and bounded sections; do not dump unchanged documents or log history.
3. **Propose and notify.** For newly actionable material not already covered by an unchanged pending proposal, produce one concrete processing proposal for the run's selected work, with source revisions, derived-note creations, note/link updates, and intended log records. Notify the owner through the existing configured channel. Stay quiet when there are no changes or only an unchanged pending proposal. Blocked/unselected inputs remain pending. Silence never means approval.
4. **Approve and process.** The owner reviews the full proposal and explicitly approves its exact revision. Recheck source hashes, existing target hashes, new-path absence, and eligibility. Create derived Markdown notes only in designated output folders, update approved notes/links, and record source hashes, output mappings, and completion status in the existing processing log. Preserve original source documents.
5. **Resume after interruption.** Failed or missed runs leave work pending for the next successful check. An indexed, extracted, proposed, notified, or partially applied input is not completed. Retry the same approved operation idempotently or surface a conflict; do not create duplicate notes or proposals.
6. **Answer with evidence.** Independent of intake, search returns ranked excerpts and locators. The agent reads selected sections or original-source context, cites evidence, and states missing or ambiguous evidence. No processing proposal or vault write is implied by a search.
7. **Inspect lineage and recover.** Follow source/output mappings and relevant processing records. Rebuild derived search state without losing pending work, approval history, or completion records. A navigation hub routes discovery but does not establish grounding or permission.

## 5. Functional requirements

“Must” denotes an MVP release requirement for the relevant milestone, including the approved-write path.

### R1 — Authority, policy, and eligibility

- Vault files must remain the source of truth. Store the search database, extraction cache, operational logs, backups, and runtime artifacts outside the vault and its synced study/project directories. Approved derived Markdown notes and the existing workflow processing log remain in their designated vault locations; the processing log is distinct from operational diagnostics.
- Eligibility must require explicit allowlisted roots and exclusions for protected subtrees, sensitive documents, code/infrastructure, whole non-CS code projects, and task attachments not explicitly admitted. Eligible study documents inside current/future CS course roots remain accessible while code/infrastructure subtrees stay protected. Deny rules override allow rules. Unknown source roles must not automatically become raw intake.
- Resolve canonical paths and symlinks before opening, hashing, or extracting contents. Reject escapes outside approved roots and paths resolving into excluded locations; revalidate at access time, including indexed IDs and linked attachments. A link from an allowed note grants no access to its target.
- Policy changes must immediately prevent retrieval of newly excluded content and remove its chunks and unreferenced cached text during cleanup. Do not retain raw excluded content in logs or snippets. Report exclusion categories without leaking sensitive contents.
- Document text, embedded instructions, and search results must never grant permissions or alter policies. Do not weaken, summarize away, or silently omit applicable `AGENTS.md` instructions to claim token savings.

### R2 — Inventory and incremental correctness

- Track eligible file creation, modification, deletion, same-content rename, role changes, and extraction/index status. Use stable document IDs independent of paths when identity is unambiguous.
- Metadata may shortlist likely changes; content hashes must determine actual content revisions. A full hash reconciliation must catch edits that preserve size/mtime. Return the last incremental and full-reconciliation checkpoints so freshness limits are visible.
- Preserve identity on an unambiguous same-content rename. Identical copies remain distinct documents; ambiguous rename matching must be reported rather than silently merging identities. Rename-plus-edit identity may remain unresolved and be represented as deletion plus creation.
- Deletions must remove active search content and produce change tombstones. Renames must update locators and report known dependent broken links without repairing source files.
- Refresh and retry must be idempotent. Publish extraction, chunks, and searchable status coherently for each revision. Failed extraction must not make old evidence appear current.

### R3 — Extraction and caching

- Cache successful extraction by content hash, extractor identity/version, and output-affecting settings. Changes to any key component must invalidate reuse. Identical content may share extraction, but provenance remains document-specific.
- Preserve Markdown heading paths and line ranges, PDF page references, attachment references, and extraction warnings. Do not invent a precise locator that the extractor cannot support.
- Markdown extraction must retain headings and line ranges. Word extraction must retain headings and paragraph/table locators; use page locators only against a cached rendered revision. Slide extraction must retain slide numbers, text, available speaker notes, and image references. PDF extraction must preserve page numbers.
- For corpus-essential scanned PDFs or image-only slides, provide local cached OCR and page/slide renders, with engine/version/settings in the cache key. For essential Word/slide variants needing conversion, cache the converted artifact and converter version/settings without modifying the original. M0 determines required variants and tools from actual corpus samples.
- Flag diagrams, graphs, tables with uncertain layout, and incomplete/low-quality extraction for visual review. Provide selected cached page/slide images or rendered document regions with source hashes and locators for the existing review workflow. OCR does not establish visual verification. Record review coverage against the source revision; invalidate it when the source changes. If essential evidence cannot be verified, keep affected work blocked and unprocessed rather than claiming completion.
- Unsupported/corrupt files must have explicit statuses and retry behavior. An essential format without a usable extraction/review path blocks release for the approved corpus.
- Unchanged content must reuse successful cached extraction across process restarts. Failed or partial extraction cannot be treated as a successful complete cache entry. Source-role changes may require reindexing without re-extraction.

### R4 — Retrieval and grounding

- Return relevant sections rather than entire large documents by default. Search must support project and source-role filters, titles/aliases, headings, and body text. Label generated/context-only evidence; expose its original-source relationships when available.
- Every snippet and section must identify document and revision, path, source role, heading/page/line locator, and relevant warnings. Stable document identity must not imply that an old section ID is valid after editing.
- Before returning cached evidence, verify eligibility and source revision against current local content. Return a stale/deleted response or refresh when they differ; never cite old text as current. Capture a consistent read so mutation during verification cannot mix revisions.
- Bound every response, including metadata, errors, neighborhoods, and change lists. Truncation must be explicit and preserve valid JSON and usable provenance. Pagination/continuation must not skip records because an output budget was reached.
- Empty results mean no evidence found under the stated scope, not proof that no evidence exists. Return effective filters and partial-coverage/staleness warnings. No hidden unbounded expansion or whole-log dump is allowed.

### R5 — Processing context and relationships

- Distinguish raw sources, user-authored structured notes, generated outputs, reference inboxes, navigation scaffolding, and explicitly configured glossary inputs.
- Represent links/backlinks and original-source/output relationships separately from text ranking. Preserve known author/provenance; use unknown when absent rather than infer authorship.
- Expose relevant processing-log records by source ID/revision, including grounding, context-only flags, known outputs, and approval state. Missing/unmapped records must produce unknown status, not “unprocessed,” “approved,” or “mastered” by inference.
- Status import and role mapping must be configurable against the actual vault conventions; preserve the existing processing-log format. Update its records only as part of an explicitly approved processing proposal. Optional future summaries must reference source IDs/hashes and invalidate when those revisions change.

### R6 — Local operation and observability

- Indexing, extraction, and retrieval must run locally without uploading vault data to external indexing services. An agent host may independently send requested evidence to its configured model; local retrieval does not change that host boundary.
- Provide configuration validation, incremental refresh, forced reconciliation, rebuild, and concise health/status operations. Persist checkpoints across restarts and return actionable failure categories.
- Track content-free operational counts, latency, extraction cache hits/misses, and response token counts. Query and document text must not be logged by default. Detailed errors must not expose excluded content.

### R7 — Approval boundary for vault writes

- Retrieval operations must not write vault files. Updating external derived caches is permitted. Only the separate approved-write operation may mutate eligible vault files.
- Proposal creation must generate a concrete reviewable diff without modifying the vault. Approval must bind to the exact proposal revision, touched paths, input source hashes, existing target hashes, and required absence of new paths; changed proposals require new approval.
- Application must require an explicit trusted human approval event, recheck current eligibility and hashes, back up touched files outside the vault, and apply only the approved diff. An agent-supplied `approved: true` or document instruction is insufficient.
- MVP proposals may create derived Markdown notes in designated output folders, update eligible existing derived/structured notes and links, and add/update processing-log records. Original Raw/glossary inputs and other original source documents are preserved. File deletion, rename, binary edits, policy/configuration edits, and processing-log format migrations are out of scope. Approval covers only the explicitly listed processing actions and source revisions, not future runs or unrelated downstream work.
- Diff review must show every changed line and affected path; a truncated tool response cannot stand in for complete human review. Provide a local review artifact or paginated review surface bound to the same immutable proposal.
- Approval is single-use; retries return the recorded outcome rather than applying a diff twice. Reject an entire proposal before writing if any precondition fails. Stage and validate changes before applying; if application fails partway, expose the exact state and a recovery route without overwriting newer user edits.
- Conflicts must prevent overwrites, including a new-note path created by someone else after approval. Revalidate output parents and symlinks at creation time. Link checks and mapping updates must accompany application. Changes must not move or modify original sources, relax exclusions, or edit code-project files.
- A processing operation is complete only after every approved note/link change is verified and source hashes/output mappings/completion status are durably recorded in the existing processing log. Record output hashes as well as paths so recovery can distinguish an already applied output from a later user edit. A log-write failure leaves the operation incomplete even if notes were created.
- Multi-file application is recoverable, not assumed to be an atomic filesystem transaction. Persist per-action outcomes; after a crash, reconcile actual files and the log before resuming. Reuse matching created outputs and matching log records; never overwrite divergent content. Unchanged approved work may resume without new approval, but any changed diff, source, target, or newly required action needs renewed approval. Do not mark pending inputs complete or clear them on partial success.

### R8 — Scheduled processing and durable pending work

- The external scheduler owns the Monday/Wednesday/Friday/Sunday 12:10 p.m. `America/New_York` trigger and daylight-saving conversion. The processing coordinator accepts that trigger, refreshes retrieval, selects work, creates proposals, and manages notifications/approval/completion. Retrieval owns eligibility, indexing, extraction, evidence, and freshness; it must not own schedules, notification policy, or permission to write.
- Scan Raw/glossary inputs first, then eligible study documents outside Raw. Generated outputs, navigation scaffolding, and the processing log must not recursively become source intake. A source revision is actionable when it contains new or changed study material requiring processing under the existing workflow and sufficient evidence is available to propose concrete changes. Unknown relevance/role or inadequate extraction remains unresolved/blocked, not silently completed.
- Keep durable work keyed by source identity and content revision, independent of search pagination cursors and run timestamps. Indexed/extracted, awaiting review, proposed, approved, applying, blocked/failed, and completed are distinct states. Advancing discovery cursors must never discard unprocessed work. Historical completion applies only to its recorded source revision.
- Produce one new concrete proposal per successful check with newly actionable work; a bounded batch may defer excess work without losing it. Reuse unchanged pending proposals without notifying again. Newly changed input covered by an older proposal supersedes the affected proposal and invalidates its approval; unrelated pending proposals need not be recreated. Define proposal identity from its input revisions and planned changes, not the trigger time.
- Persist proposal and notification-delivery state separately. A failed notification remains retryable without regenerating the proposal; use a stable delivery key where the existing channel supports deduplication. Ambiguous delivery must not be reported as confirmed; exact duplicate suppression across delivery crashes depends on the channel and must be resolved in M0.
- No-change and unchanged-pending checks produce no user-facing notification. Failures are retained in concise operational status and surfaced through the existing automation's failure reporting, without treating them as successful empty runs. Neither silence, elapsed time, a schedule trigger, nor a successful notification is approval.
- Missed triggers require no new catch-up scheduler: the next successful trigger checks retained work and current eligible source revisions since the last successful inventory. Retain observed unprocessed revisions; a source edited again supersedes its earlier pending revision rather than authorizing stale processing. Do not promise recovery of intermediate versions never observed and no longer present in the vault.
- Duplicate/overlapping triggers must not create competing proposals or apply approved work twice. Scheduled intake alone never invokes vault mutation. Restart/rebuild must preserve or recover pending work and durable approval/application history, independently of rebuilding the search index.

## 6. Logical data model

These entities express required information, not a prescribed SQL schema. Search-derived records must be rebuildable. Owner configuration and durable run/work/proposal/approval history are separate workflow state; rebuilding the search index must not erase them. Existing vault processing-log records remain authoritative for recorded completion.

| Entity | Minimum information and invariants |
| --- | --- |
| Eligibility configuration | Vault/root IDs, canonical allow roots, deny rules, glossary input, source-role mappings, configuration revision |
| Document | Stable ID, current vault-relative path, project, role, title/aliases, known author/provenance, current revision, lifecycle status; copies have distinct IDs |
| Source revision | Document ID, content hash, size/mtime, observed timestamp, extraction/index state and errors; historical presence does not authorize retrieval |
| Extraction | Content hash + extractor/version/settings key, cached text location, page/attachment mapping, completeness and visual-review warnings |
| Section | Revision-scoped ID, document/revision IDs, heading path, line/page range, text, search fields, order for neighboring sections |
| Relationship | Source and target IDs or unresolved target locator, relation type, establishing source/revision, resolution/broken-link status |
| Processing record | Source/revision, project, source hash, output paths/hashes, grounding/context-only state, approval/proposal reference, completion state, originating log locator; unknown is explicit |
| Change event/checkpoint | Ordered cursor, document ID, event/reason, old/new path or revision, project, observation time; tombstones survive pagination |
| Intake run/work item | Trigger/run identity, last successful discovery checkpoint, source ID/revision, priority group, work state, blocker, proposal association; discovery is not completion |
| Notification delivery | Proposal revision, delivery key/channel, pending/confirmed/failed/unknown status, retry information; delivery is not approval |
| Patch proposal/approval | Immutable proposal revision/diff, input source revisions, created/updated paths and expected hashes/absence, explicit approver/event, per-action outcomes, backup references, application/conflict/completion status |

Section locators must resolve against their recorded revision. Re-extraction may replace section IDs without changing document identity. Cache retention and event-history expiry must be explicit; expired cursors return a resync instruction, never an apparently complete empty result.

## 7. Retrieval interface contract

The following operation names are proposed. Their semantics are requirements; MCP versus a command wrapper and exact wire schema remain implementation decisions. Administrative refresh/rebuild operations are separate from ordinary evidence retrieval. The processing operations below belong to the coordinator, not the read-only retrieval service; names and transport remain proposed.

| Operation | Inputs | Required result |
| --- | --- | --- |
| `changes` | `since` cursor, optional `project`, `limit`, `budget` | Eligible input changes and reasons, tombstones, next cursor; initial request gives a bounded current inventory with a checkpoint |
| `search` | Nonempty `query`, optional `project`, `source_role`, `limit`, `budget` | Ranked snippets with document/section IDs, source revision, citation locator, warnings, and effective scope |
| `read_sections` | Revision-scoped `ids`, `budget`, optional continuation | Selected authoritative section text with provenance; explicit stale, deleted, excluded, or not-found items |
| `neighbors` | `id`, `relation`, `limit`, `budget`, optional continuation | Bounded links/backlinks, adjacent sections, original sources or outputs; distinguish confirmed and unresolved edges |
| `processing_status` | `ids`, `budget`, optional continuation | Relevant processing records, grounding/context-only/approval state, unknowns and record provenance |
| `run_intake` (coordinator) | External trigger identity or manual request, configured scope, task budget | Refresh/discovery summary and persisted pending work; one new proposal and notification when actionable; quiet otherwise |
| `propose_patch` (coordinator) | Source revisions, explicit note creations/updates, links, and log changes | Immutable processing proposal ID/revision and complete review artifact; no vault writes |
| `apply_approved_patch` (coordinator) | Proposal ID/revision, expected hashes/absence, trusted approval reference | Per-action outcomes and verified log-backed completion, or incomplete/conflict status with recovery information |

Proposed defaults: search returns up to 8 snippets within 2,000 response tokens; reads default to 4,000; other operations default to 2,000. All operations have a hard ceiling of 8,000 tokens and 20 requested result items/IDs per call. The serialized JSON envelope, metadata, and errors count toward the limit. Use one pinned local tokenizer and expose its identifier and actual output count. Values are initial defaults to validate, not a claim that every model tokenizes identically.

Requests below a documented minimum envelope budget return a bounded validation error under the service ceiling; accepted requests must fit their requested budget. Oversized limits/budgets are rejected explicitly. Large sections can be returned as continuation-addressable spans with precise locators. If a response cannot fit even one evidence item, return a compact budget error rather than dropping provenance. The agent controls a separate total task budget; repeated calls do not imply unlimited task spending.

A common response envelope must expose request/scope, items, snapshot/freshness information, actual token count, truncation, warnings, and an opaque continuation when more items remain. Cursors must tie to a stable snapshot or explicitly signal invalidation after an index change. Errors include invalid input, excluded, missing, stale revision, unsupported extraction, expired cursor, and unavailable index. Scores are ranking signals, not confidence probabilities. Treat query text as data; an invalid search expression must not crash the service.

## 8. Implementation choices and tradeoffs

**Fixed constraints:** local operation, authoritative Obsidian files, external derived storage, read-only retrieval with a separate approved-write path, explicit exclusion policy, bounded output, provenance, and SQLite FTS5 first. These implement the owner's stated direction.

**Selected initial implementation choices:** Python 3.12+, a local CLI, cl100k_base response accounting, and an adapter that preserves `Planning/Processing log.json`. The existing heartbeat is not connected yet. Huyen is excluded from the first live configuration.

**Proposed, replaceable choices:** size/mtime screening followed by hashing and periodic full reconciliation; heading-sized chunks with smaller spans for long sections; FTS5 ranking with title/alias boosts; content-addressed extraction artifacts; transactional revision publication; externally triggered refresh plus manual refresh instead of a watcher. A durable coordinator journal and notification outbox are proposed ways to preserve pending work and retries; exact storage is not prescribed. Choose language, extractor libraries, tokenizer, schema, and transport during implementation after checking the actual host and corpus. No runtime dependency selection is implied here.

**Embedding gate:** evaluate keyword/alias/chunking improvements first. Only propose embeddings if held-out, labeled paraphrase failures persist and prevent the recall gate. A subsequent local comparison must demonstrate improved recall without losing provenance, exclusion safety, bounded output, or the token-savings gate, and report latency/storage costs. Embeddings require a separate scope decision; they are not an automatic MVP fallback.

## 9. Milestones and exit criteria

No dates are committed without a delivery budget. Execute in dependency order; each milestone must produce reviewable evidence.

| Milestone | Deliverable | Exit criteria |
| --- | --- | --- |
| M0 — Scope and baseline | Corpus samples, role/log/output mapping, existing scheduler/notification/approval integration, reference machine, evaluation set and baseline | Confirm essential format extraction/review paths and delivery deduplication; finalize thresholds before tuning |
| M1 — Safe inventory and cache | Local derived store, incremental/full inventory, extraction and failure reporting | R1–R3 pass exclusion, rename/delete, cache, placeholder, reconciliation, and restart fixtures |
| M2 — Agent retrieval | Search/read/neighbors/status/changes contract and host integration | R4–R6 pass provenance, staleness, filter, pagination, budget, and policy-preservation fixtures |
| M3 — Scheduled and approved processing | External trigger adapter, durable pending work, proposal/notification integration, approved note creation/update and log completion | R7–R8 pass schedule, quiet-run, approval, conflict, deduplication, and partial-failure recovery tests |
| M4 — MVP release | Held-out comparison and operational/rebuild instructions | All retrieval and write safety checks and agreed accuracy/token/latency gates pass; pass the full scheduled discovery-to-completion scenario; document actual format coverage and remaining limitations |

If token targets fail, inspect complete task traces before increasing complexity. If accuracy fails, the MVP is not accepted even if token savings are large. Do not describe an unmeasured optimization as a success.

## 10. Testable acceptance scenarios

1. **Exclusion:** place distinctive text in denied code/sensitive files, unapproved task attachments, escaped symlinks, and linked excluded attachments. Across scan, search, direct reads, and neighbors, instrumented content access is zero and text is absent from derived artifacts/responses. Retarget a symlink and revoke a previously allowed root; repeat before cleanup completes.
2. **Incremental parity:** starting from one snapshot, create, edit, rename, copy, delete, and change file roles. After full reconciliation, incremental state and a clean full inventory agree on eligible current documents/revisions; change events retain deletions and distinguish ambiguous copies. A same-size edit with restored mtime is caught by reconciliation and cannot be served as current stale evidence.
3. **Cache and format coverage:** discover fixtures for Markdown, Word, text/scanned PDFs, and lecture slides, including essential actual-corpus variants. Extract/OCR/render once, refresh unchanged, restart, and refresh again: no successful extraction is repeated. Changing source bytes or extractor/converter/OCR settings/version invalidates the relevant cache. Verify paragraph/page/slide locators and selected visual-review fallbacks. Failed or insufficient essential evidence remains blocked, never completed.
4. **Intake:** filling an empty Raw/glossary placeholder emits new candidate work. Editing a generated note updates its searchable revision without raw intake recursion. An unchanged pending proposal does not appear as a new input.
5. **Grounding:** known Markdown/PDF queries return the labeled source section with the correct revision and heading/line/page locator. Generated/context-only records are labeled; unknown processing status stays unknown. Scanned graphs remain flagged for visual review.
6. **Freshness:** modify/delete a source after search but before section read. The old ID returns stale/deleted or an explicit refreshed revision, never old text as current. A rename preserves unambiguous document identity and exposes broken dependent links without vault edits.
7. **Bounds:** test long headings, Unicode, giant sections, many links, errors, and oversized requests. Every accepted response is valid JSON within its requested token budget, preserves provenance, and exposes truncation/continuation. Exhaust pagination without missing or duplicating snapshot items; index changes invalidate cursors explicitly if necessary.
8. **Missing evidence:** unsupported-format and no-match tasks return scope/coverage limitations. The evaluated agent abstains or expands deliberately within task limits; it does not fabricate evidence or permissions.
9. **Read-only and recovery:** hash vault files before and after retrieval, proposal creation, and administrative operations, including failure/restart/rebuild; hashes are unchanged. Interrupted extraction cannot expose partially indexed evidence. A rebuild yields equivalent searchable evidence and locators for current eligible revisions.
10. **Policy and savings:** compare complete traces on the fixed evaluation tasks. Applicable policy remains available in both workflows. Report token reduction, duplicate delivery, recall, answer quality, extraction counts, and latency against every release threshold.
11. **Approved writes:** attempts without trusted approval or with approval for a different diff fail without modification. Concurrent source changes cause conflict. Successful application creates/updates only approved Markdown notes and log records, matches the approved diff, retains backups, validates links, and refreshes mappings. Original sources remain byte-for-byte unchanged. A preexisting new-note target causes conflict. Simulate failure after note creation but before log update: status remains incomplete; retry reuses matching outputs, records completion once, and does not overwrite concurrent edits.

12. **Schedule and missed runs:** drive the existing trigger adapter with Monday/Wednesday/Friday/Sunday events at 12:10 p.m. `America/New_York` on both sides of daylight-saving transitions; verify local time remains fixed. Skip a trigger, fail a refresh, and send duplicate/overlapping triggers. The next successful check retains outstanding work, checks Raw/glossary first and outside-Raw study inputs second, and produces no competing proposal. No trigger alone writes vault files.
13. **End-to-end scheduled processing:** add actionable Raw/glossary material and an eligible outside-Raw study document. A scheduled run refreshes and retrieves changed evidence plus relevant existing notes, persists one concrete proposal covering note creation/update, links, source hashes, output mappings and log completion, and sends one notification. Run again before approval: no new proposal, notification, or vault writes. Explicitly approve the exact proposal; verify designated-folder note creation, existing-note/link updates, preserved originals, and one processing-log completion record with verified source/output hashes. The next unchanged scheduled run creates no duplicate proposal/notification/output/log record. Repeat with notification failure and a crash before log completion; work stays pending and resumes without premature completion.

## 11. Unresolved decisions

| Decision | Working assumption | Required resolution |
| --- | --- | --- |
| Actual roots, exclusions, glossary location, source roles | Explicit configuration; no guessed paths or ingestion | Owner supplies/reviews corpus configuration in M0 |
| Processing-log format, output folders, and provenance conventions | Preserve existing conventions; approved note creation/update and log completion | Inspect representative records and designate writable destinations in M0 |
| Essential format variants and visual-review workflow | Discover Markdown, Word, PDFs including scans, and lecture slides; cache extraction/OCR/renders and block unverifiable evidence | Inspect corpus samples and validate required extraction/review paths in M0 |
| Existing automation and notification adapter | Fixed external schedule; stable proposal identity and quiet unchanged runs | Confirm invocation, failure reporting, delivery deduplication, and channel in M0 |
| Actionability rules and run batch budget | Existing workflow determines useful study inputs; unresolved/overflow work stays pending | Capture representative actionable/nonactionable examples and handling of rejected proposals in M0 |
| Agent host integration | CLI selected; existing conversation/heartbeat remains the host | Connect and verify the existing host after configuration review; MCP is not required |
| Corpus size, hardware, delivery budget | No scale or date promises; initial metric targets above | Record baseline and agree milestone budget in M0 |
| Corpus reconciliation/retention tuning | cl100k_base tokenizer; retained event/work history and backups; manual/full refresh implemented | Validate cadence and retention against the approved corpus before live release |
| Trusted approval mechanism | Owner approval bound to exact diff; no agent self-approval | Resolve in M0; implement before M3 exits |

The owner authorized implementation and read-only inspection of live policy/workflow conventions. Build and test against isolated sample vaults first; propose the exact live eligibility/output configuration before enabling indexing. Setup information does not authorize processing or live note writes. Keep the existing external heartbeat unchanged.
