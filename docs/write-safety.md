# Registry review and concurrent-write behavior

## Registry review

Read-only inspection of the live operational registry on September 18, 2026 found schema version 1 with 56 source records, 41 generated-file records, and 5 completed-batch records. No live log or study content was edited. Fixtures use synthetic values, not copied personal records.

The writer now retains the `processed_at` field and preserves custom fields on updated generated-file records as well as source records. Known provenance mappings are refreshed from the approved source mapping. Existing unrelated records, batch history, intake checks, pending-proposal fields, and other top-level fields remain unchanged. Unsupported schema versions, duplicate record paths and malformed known collections fail before writing rather than silently merging or discarding records.

Timestamps in the exact registry diff are frozen when the proposal is prepared and are not published until its action executes. They are not a precise wall-clock application-completion measurement. The writer does not dynamically change approved bytes to stamp the actual commit time. Existing completed-batch history is preserved, but new CLI batch records use the documented CLI fields; dated Planning proposal/report integration and a precise compatible completion-time convention remain to be designed. This is not a claim of full compatibility with every external consumer.

## Write protocol

The old check-hash → unconditional `os.replace` sequence could silently discard a save occurring between those two operations. It has been removed.

For each existing destination, under the service lock:

1. Preflight all batch targets and require vault/external recovery storage to share a filesystem. Preserve the approved baseline backup and durable action intent.
2. Stage approved bytes outside the vault. Atomically capture the current destination inode into an external per-action recovery directory, then hash that captured file. This preserves the actual version at the mutation boundary, not merely the earlier baseline.
3. If its hash differs, restore it only if the original path is empty. If another save occupies that path, preserve both versions and report conflict. Never replace the occupant.
4. Publish approved content with exclusive `link`, which fails if another writer created the destination. Retain the captured inode; verify it again for writes made through an already-open editor handle. Inspect captured versions again before batch completion.
5. Publish the registry action last. Mark the batch complete only after the approved output hashes pass verification. Source originals are not write targets.

New-file creation also uses exclusive publication. Conflicts leave the batch incomplete. Tests inject a save immediately before capture, a save during the missing-path window, a crash after capture, and a crash immediately after publication linking. The last two resume with the same approved batch when all hashes still match.

## Limits that still matter

This prevents blind replacement and retains racing inode content; it does **not** provide an atomic transaction across independent editors or files. The destination is briefly absent between capture and publication. Obsidian/sync watchers may observe that gap. An editor holding the captured inode can write to it even after publication; those bytes remain in recovery, and detected changes halt completion, but there is no perpetual monitoring after the call returns. Ordinary future edits to the published note remain possible.

Cross-filesystem recovery is rejected before any batch writes. Hardware/power-loss durability and actual Obsidian/sync behavior are not proven by the process-interruption fixtures. Validate them before live release. Never advertise the tests as a guarantee against arbitrary concurrent software or power failure.

## Recovery

External state contains `backups/<proposal-id>/` for approved baselines and `write-recovery/<action-digest>/` with `action.json`, retained `captured` content, and any remaining `staged` file. The manifest identifies the vault-relative destination and expected/output hashes. These files may contain private note/log content and remain in private local state.

If an ordinary interrupted batch has no divergent hashes, retry its original `apply` with the original receipt; the journal resumes completed or captured actions. If a hash differs, stop: inspect the current destination and the captured version without replacing either. Reconcile into a newly reviewed proposal or restore the captured version only into an absent destination. Never use unconditional `mv -f`, `cp` overwrite, or automatic rollback over newer user edits. Do not delete recovery directories while an interrupted/conflicted batch is unresolved. There is not yet a dedicated human recovery UI or recovery CLI command.
