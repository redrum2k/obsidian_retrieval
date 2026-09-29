# Desktop approval event contract

Verified September 29, 2026 for bundled `codex-cli 0.158.0-alpha.2.1` (revalidated after an app update).
The executable and Electron app bundle hashes are pinned in
`src/vault_retrieval/hook_host.py`. This is a local workflow boundary, not
cryptographic authentication against an unrestricted same-user process.

## Evidence that resolves the origin-field mismatch

The manual desktop probe reached the expected session
`01a08699-7b7c-77f3-b634-390cb23b0be8`. Its payload includes prompt/session/turn
fields and no human-origin label. None is required by the new contract.

The following links use the source release matching the installed binary,
**not the moving main branch**:

- [Hook input dispatch](https://github.com/openai/codex/blob/rust-v0.158.0-alpha.2.1/codex-rs/core/src/hook_runtime.rs):
  `inspect_pending_input` invokes UserPromptSubmit for `TurnInput::UserInput`.
  Response items, function outputs, and inter-agent communication bypass it.
- [Subagent event serialization](https://github.com/openai/codex/blob/rust-v0.158.0-alpha.2.1/codex-rs/hooks/src/events/user_prompt_submit.rs):
  the host supplies `agent_id` and `agent_type` for child submissions. Root
  payloads omit them. The adapter rejects either field's presence, including
  malformed empty/null values; session matching alone is not the child guard.
- [Stop-hook continuation](https://github.com/openai/codex/blob/rust-v0.158.0-alpha.2.1/codex-rs/core/src/session/turn.rs):
  a blocking Stop hook builds a response item, records it directly, and continues
  the current turn. It does not resubmit it through `inspect_pending_input`.
  Therefore it cannot create a new approval event, even if its text is an exact
  approval command. An already-recorded approval retains its normal retry scope.

Read-only inspection of the updated `app.asar` found heartbeat submission now
uses text input wrapped in `<heartbeat>` with automation ID, timestamp and
instructions, for both scheduled and Run now triggers. The whole-message
approval matcher rejects that wrapper, even if its instructions contain an exact
approval command. Unlike the prior build, this path can fire UserPromptSubmit;
the approval adapter must not depend on the absence of a scheduled hook event.
The earlier 0.154 build used tool-output submission. Both forms are covered by
negative adapter fixtures; the currently pinned files are the reviewed 0.158 build.

The earlier documentation overstated the uncertainty: generic docs describe a
Stop continuation as a user prompt, but the matching runtime implementation
shows that it bypasses this hook. Requiring an invented origin field was wrong.

## What is enforced

Exact whole-message `IMPLEMENT <64 lowercase hex ID>`, configured conversation,
nonempty host turn ID, no subagent markers, verified desktop build, delivered
immutable proposal/config digest, current policy/source/target preconditions,
and durable idempotent application. A host update blocks recording **and**
application until compatibility is reviewed. Neither stdin nor file fingerprints
are a cryptographic attestation of the sender; the trusted hook invocation and
local owner-controlled app/configuration remain the trust boundary. Another
client submitting arbitrary root user turns is outside this integration contract.

## Validation and remaining pilot

Automated tests use isolated vaults and fixture build files. They exercise the
actual stdin hook entry point, returned apply command, CLI application, log
completion, quiet unchanged intake, wrong-session/subagent inputs, upgrades,
conflicts, replay and recovery. Source inspection establishes the host dispatch
paths; these tests do not pretend to have run new live subagent or Stop-hook
turns. The original manual diagnostic is the observed real desktop event.

The owner still needs to trust the replacement hook definition, run the harmless
production probe, then approve one freshly delivered test batch. No live batch
was approved or applied during implementation. That pilot tests the app's hook
loading/trust and same-turn agent handoff end to end.

## Probe investigation after the app update

The installed app-server's read-only `hooks/list` response reported the production
command enabled and trusted for the vault working directory. A direct readiness
check found that the old build fingerprints blocked the updated installation.
The screenshot's generic assistant reply does not establish whether the hook ran
in the already-open conversation. No new diagnostic artifact established that.
Production probes now write `hook-probe-status.json` in external state with time,
session/turn ID and ready/blocked status (no prompt text or approval). A fresh
receipt distinguishes delivery from an assistant acknowledgment. Reload the app
and repeat the real probe after this compatibility update; do not fake a probe
receipt by manually invoking the production hook on synthetic events.

## September 25 recovery

Reviewed the installed 0.155.0-alpha.16.4 release's `hook_runtime.rs`,
`hooks/src/events/user_prompt_submit.rs`, `hooks/src/schema.rs`, and
`core/src/session/turn.rs`. UserInput dispatch, omitted root agent fields,
subagent markers, and Stop continuation bypass remain as described above.
Read-only ASAR inspection of `.vite/build/main-C-Mhak1n.js` confirmed that
`Ms` constructs the heartbeat through `Sae`, and `Eae` submits that complete
wrapper as text for scheduled and Run now triggers. The exact command matcher
therefore still rejects automated instructions. Updated both fingerprints only
after this review. Future unknown builds still fail closed.

The local `--check` passes. This is source/build validation, not a new live human
approval test. No production approval event or probe receipt was synthesized.
Tokenizer data is now packaged and hash-checked so a cleared temporary cache
cannot trigger an unbounded network download during CLI or hook startup.

## September 29 bundle-layout recovery

The readiness failure was reproduced: the pinned `Resources/codex` no longer
exists. The app now ships `Resources/codex-cli/bin/codex`, a shell launcher that
executes `../CodexCLI.app/Contents/MacOS/codex`. Both launcher and actual binary
are pinned, along with `app.asar`; checking only the launcher would miss binary
updates. The executable reports `0.158.0-alpha.2.1`.

Reviewed the matching release's four Rust files linked/described above.
`inspect_pending_input` still dispatches UserInput only; child submissions retain
agent markers, root fields are omitted, and Stop continuation records a response
item directly. In `.vite/build/main-C5425b_s.js`, scheduled `Eae` and Run now
`Dae` both reach `Ps`, which builds the complete heartbeat via `jae` and passes
it to `Fae` as text input. The `lae` template retains the outer `<heartbeat>`
wrapper. Exact whole-message approval matching therefore still rejects it.

Updated the reviewed paths and fingerprints. Missing/unreadable files and hash
mismatches now identify the affected path. Regression coverage checks that both
missing and modified host files block recording and application. The production
readiness check passes; this does not establish live hook delivery or UI trust.
No proposal approval, application, or synthetic production probe was performed.
