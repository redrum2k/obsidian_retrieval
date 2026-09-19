# Enable chat approval for the existing heartbeat

The origin mismatch is fixed. The adapter uses the verified installed desktop
contract, not a nonexistent `human_origin` field. See [host evidence](hook-host-evidence.md).
The hook records an exact batch approval and tells the same agent turn to run
`apply-hook`; you do not need another confirmation or receipt file.

## Finish activation and test

1. In the desktop app's Hooks settings, review/trust the replacement
   `UserPromptSubmit` command for this project. It should invoke
   `python -m vault_retrieval.hook --config .../config.local.json`, with no
   `--probe-dir`. New/changed hook definitions require owner trust under the
   [host's hook rules](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks).
   The installer does not change trust hashes. Reload the conversation/app if
   its hook list has not refreshed.
2. In the existing Obsidian conversation, send exactly `VAULT_HOOK_PROBE`.
   Expected: the production hook reports its configuration/build checks passed,
   no approval recorded, no vault writes. A generic assistant acknowledgment is
   insufficient: inspect the hook result if the readiness report is absent.
3. Replace the existing heartbeat's entire prompt with the text in
   [heartbeat-prompt.md](heartbeat-prompt.md). Keep the same conversation. You can
   temporarily move its activation time for your trial; restore Monday,
   Wednesday, Friday, Sunday at 12:10 America/New_York afterward. Do not create a
   duplicate automation. This implementation did not change the schedule/prompt.
4. Add a small user-authored Markdown capture in an already allowed Raw folder
   and let the heartbeat run. Expect one complete proposal/diff and a **new** ID.
5. Review that diff, then reply in that same conversation with exactly
   `IMPLEMENT FULL_64_CHARACTER_PROPOSAL_ID` (substitute its ID, no backticks or
   extra prose). The hook records approval; the agent applies that exact batch
   in the same turn and reports actual note/log changes. No Vault Approval app
   or receipt-path handoff is needed in hook mode.
6. Run intake again unchanged. Expect no duplicate proposal. Preserve any
   conflict/failure report and pending work; do not bypass hash checks.

Existing signed-mode proposals must be regenerated and reviewed after this
configuration migration. Their old IDs/receipts do not carry approval into hook
mode. Intake releases superseded pending work for replanning automatically.

## Local readiness check

```sh
cd /Users/nikitaafanaskin/Documents/Developer/obsidian_retrieval
uv run python -m vault_retrieval.hook --config config.local.json --check
```

This checks configuration, pinned host files and vault policy without approving,
extracting or applying. It cannot determine whether you have trusted the hook in
the desktop UI. To inspect the definition, open `~/.codex/hooks.json`.

Current settings for this installation:

```json
{
  "approval_scheme": "codex-hook",
  "hook_approval": {
    "enabled": true,
    "session_id": "01a08699-7b7c-77f3-b634-390cb23b0be8",
    "host_contract": "codex-desktop-input-v1"
  }
}
```

Keep your existing approval public key; hook mode does not use or replace it.
Configuration and hook backups are recorded in `hook-activation-local.md`
(ignored by Git). Restore those backups for signed-mode rollback, then regenerate
proposals under that configuration. Do not copy old approvals onto new proposals.

## Boundaries and troubleshooting

- Ordinary intake creates proposals; a scheduled run is never approval.
- The command authorizes only the reviewed content. It does not authorize
  further generation, arbitrary rewrites, moves, or changes to original sources.
- Proposal delivery must be acknowledged with the configured `--session-id` only
  after delivery. Undelivered, changed or superseded batches cannot apply.
- On a host upgrade, the build check deliberately stops chat approvals and apply.
  Review the new host's dispatch behavior before updating its pinned contract;
  do not blindly replace fingerprints. Source/target changes require a new diff.
- Approval recording does not itself finish application. If the agent turn stops,
  `apply-hook --id ID` can resume only the batch with an existing valid approval.
- Do not manually feed fake events into the production hook or edit approval rows.
  These are local workflow controls, not an OS sandbox against arbitrary code
  with the same user's filesystem access.

Tests: `uv run pytest -q`; see the host-evidence document for what was actually
observed versus fixture-tested. The real owner-approved batch is the final pilot.

## If the probe gets only a generic acknowledgment

The production probe now writes a content-free receipt at:

`/Users/nikitaafanaskin/Library/Application Support/obsidian-retrieval/hook-probe-status.json`

After sending the message, check that its `checked_at` is new, its `status` is
`ready`, and its session matches this conversation. An absent or old receipt
means the new probe handler has not been confirmed; do not infer success from
chat text. A blocked receipt names the readiness failure. Restart/reopen the
app to load updated hook settings, then retry. The local `--check` command does
not create a receipt, so it cannot be mistaken for a real desktop submission.

The September 19 follow-up found that desktop rich-text input saved the probe
with backticks or escaped underscores (sometimes doubled). The harmless probe
now accepts those observed variants and surrounding whitespace. Approval still
requires the exact unformatted IMPLEMENT command; diagnostic normalization is
never used to authorize a batch. The heartbeat prompt has been saved to the
existing automation file with its schedule/target preserved; desktop UI reload
must still be observed.
