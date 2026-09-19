# Resolved: chat approval integration

The implementation is complete for the pinned desktop build. Follow
[the activation and pilot steps](hook-approval-setup.md), then use the
[full heartbeat prompt](heartbeat-prompt.md). See [host evidence](hook-host-evidence.md)
for the matching release source and test boundaries. Owner trust and the live
approved-batch pilot remain manual; no live batch was applied during implementation.

The original plan below is retained as history, not current activation instructions.

---

# Fix chat approval without another receipt handoff

Status: implementation plan, September 19, 2026. Production approval remains on P-256; no live settings or vault files changed.

## Intended result

The existing heartbeat prepares and delivers one exact diff. Nikita replies
`IMPLEMENT <full proposal ID>` in the existing conversation. A trusted hook
records that approval and instructs the same turn to run `apply-hook`. There is
no second chat confirmation, receipt-path exchange, new scheduler, or automatic
approval during intake. Application executes the reviewed content; it does not
license drafting additional changes after approval.

## What actually needs fixing

`hook_approval.record_event` currently requires `origin_field` and
`human_origin_value`. Neither is present in the observed desktop payload. The
fixture's `test_origin` proves only our validation logic. It does not establish a
real integration. Conversely, the automatic apply handoff in `hook.handle`
already exists and must be retained.

The installed app has a separate heartbeat tool-output submission path, which
explains the absent scheduled probe. That finding does not establish that every
`UserPromptSubmit` is human-authored. Official documentation says subagent hooks
share the parent session ID and Stop hooks can create continuation user prompts.
See https://learn.chatgpt.com/docs/hooks. Session plus exact text is not yet a
verified replacement for origin checks.

## Bounded implementation plan

1. **Establish the actual host boundary before changing the guard.** In an isolated
   test conversation, record metadata for a direct owner message, heartbeat Run
   now, a scheduled heartbeat, a subagent prompt, and a Stop-hook continuation.
   Use the same harmless exact-command shape for adversarial cases with no real
   proposal or production config. Verify which events reach UserPromptSubmit
   and whether a supported host field identifies the original owner submission.
   Record the host version and results. This is a one-time integration test, not
   repeated waiting for a field to appear in ordinary intake.
2. **Choose the smallest evidence-supported adapter.** If the host guarantees
   UserPromptSubmit only for direct owner submissions on this path, replace the
   fictional field requirement with an explicit documented host-contract version.
   If synthetic submissions also reach it, require a supported host-provided
   origin/turn classification and validate it. If neither is available, the host
   needs a user-submit event/metadata extension; this repository alone cannot
   manufacture that provenance. Keep signed approval working in that case.
   Do not scrape transcript prose, infer origin from missing fields, or insert
   `human: true` in a wrapper.
3. **Update `hook_approval.py` and configuration together.** Keep exact command,
   conversation, turn ID, recorded delivery, proposal/config digest, current
   source/target hashes, and durable replay protection. Reject synthetic origins.
   Validate the new contract both when recording and applying approval. Remove
   obsolete origin placeholders from docs only when their replacement is tested.
4. **Keep `hook.py` fast and automatic.** Record approval, then return the existing
   `additionalContext` apply instruction. The agent executes `apply-hook` in that
   same turn and reports the actual result. If interrupted, the durable approval
   permits retry of only the same immutable batch. No OCR, drafting, or long-running
   apply process belongs inside the synchronous hook.
5. **Test the full entry point.** Replay captured event shapes through hook stdin
   against an isolated vault, then exercise a real manual approval in a disposable
   host conversation. Assert no writes for automation/subagent/continuation,
   quoted or wrong-session commands, undelivered IDs, changed config/files, and
   forged receipts. Assert exactly one completed batch and registry update for
   approval plus retry; unchanged next intake remains quiet. Run the existing
   test and lint suites. Unit fixtures do not substitute for the host test.
6. **Migrate once those checks pass.** Back up the local config and hook definition;
   preserve the enrolled public key. Select the new hook contract for the verified
   conversation, replace only this project's diagnostic hook with production,
   and have the owner review/trust that definition in Hooks settings. Configuration
   changes invalidate existing proposals: regenerate and deliver a fresh exact
   proposal, rather than applying the previously signed-mode proposal under new
   settings. Use the full prompt in `heartbeat-prompt.md`. Test one owner-approved
   live batch, then verify unchanged intake is quiet. Retain backups for rollback;
   switching approval schemes also requires fresh proposals.

## Completion evidence

- Real owner command records approval and starts apply in the same turn without
  a second approval interaction.
- Negative host-origin cases create zero approval records and zero vault writes.
- New/updated note hashes and the processing registry match the approved diff.
- Replay/restart does not duplicate application; failed work remains pending.
- Live hook trust, configuration migration, and heartbeat instructions agree.

The production guard has deliberately not been removed: the missing host
classification is still an integration question, not a passing test. The owner
can continue using the native signed flow for the existing proposal meanwhile.
