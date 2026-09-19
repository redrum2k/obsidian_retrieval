# Conversation approval → approved vault batch

Status: implemented with a verified build-specific host contract; awaiting owner hook trust and live pilot. Owner: Nikita. September 19, 2026.

## Problem and outcome

The owner already reviews processing proposals in the existing Obsidian conversation. Requiring a second app, key enrollment and a receipt file adds unnecessary steps. One explicit reply should start creating/updating the reviewed notes and processing log, while silence and scheduled checks never authorize writes.

## MVP workflow

1. Scheduled intake discovers changed inputs without extraction. The host selectively extracts relevant inputs, drafts one concrete batch, and delivers its complete review artifact with a proposal ID.
2. The owner sends exactly `IMPLEMENT <proposal-id>` in that conversation.
3. A trusted `UserPromptSubmit` hook binds that event to the previously delivered immutable proposal, then starts its application once.
4. Existing eligibility, source/target hash, provenance, link and recovery checks run. Only approved Markdown outputs and the processing registry change. The host reports completion or a specific conflict; the next unchanged check stays quiet.

“Generation” here means executing the reviewed concrete batch. This command does not authorize new topics, additional sources, or changes beyond the approved diff.

## Requirements and acceptance

- Match the entire trimmed message, case-sensitive; ignore quoted commands, longer messages, assistant/tool output, other conversations, and scheduler prompts. Use the host event, not transcript scraping or model interpretation.
- Bind the configured conversation, proposal ID, exact body/configuration digest and host turn ID. Require a recorded delivery for that proposal. Unknown, changed, superseded or undelivered proposals produce no writes.
- Duplicate events/replies must not apply twice. Persist approval and execution outcome across restart; interrupted work resumes under the existing conflict/recovery rules. Never claim success before log completion.
- Keep intake read-only with respect to vault files. Preserve exclusions, originals, source grounding, bounded responses, single-batch approval and no-change silence.
- Remove the native-app/signing requirement from this workflow; do not introduce another approval UI, secret-signing service, or agent-set `approved: true` bypass. Existing enrolled users must receive an explicit migration path.
- Tests: valid owner command applies exactly one reviewed batch; wrong conversation/ID, quotation, scheduled input, changed hash/configuration and replay create no unauthorized writes; crash/retry and unchanged next intake create no duplicate batch.
- Target: acknowledgment within 2 seconds on the reference machine, excluding actual batch execution. The hook must not run OCR or draft new content before acknowledging. Measure actual apply duration separately.

## Proposed implementation and release gate

Use Codex's documented [UserPromptSubmit event](https://learn.chatgpt.com/docs/hooks#userpromptsubmit), which supplies prompt/session/turn context. Keep matching and approval recording in a small host adapter; reuse the coordinator's existing application path. Use an exact command with ID in MVP; bare `IMPLEMENT`, natural-language approval, chat transcript parsing, and a new scheduler are out of scope.

The installed host contract is now established from matching release source and
local event evidence; see [host evidence](hook-host-evidence.md). Root input events
need no invented origin field. Child events carry agent markers; heartbeat tool
outputs and Stop continuations bypass this hook on the verified build. Build
changes stop approval until reviewed. Follow [activation](hook-approval-setup.md)
for owner trust, fresh proposal migration and the live approved-batch pilot.
