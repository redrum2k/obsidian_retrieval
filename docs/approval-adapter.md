# Local approval adapter

Implemented: a native macOS review app, Secure Enclave P-256 signer, `vault approval-request`, and CLI receipt verification. The app displays complete before/after contents plus all source/grounding metadata from the exact body being signed. It never writes vault files. The CLI remains the only application path.

This is a local build, not a notarized release. Automated tests cover parsing, altered requests, canonical-message interoperability, wrong keys, replay against another proposal, and isolated apply/retry. Real owner authentication, cancellation at the macOS authentication prompt, and end-to-end use with Obsidian/sync still require manual validation. No live approval key has been enrolled by the implementation task.

## One-time setup

From the project directory:

```sh
./approval-app/build.sh
open -n "approval-app/build/Vault Approval.app" --args --enroll "$HOME/Library/Application Support/VaultApproval/public-key.json"
```

The owner checks the enrollment box and chooses **Enroll and export public key**. The app creates a Secure Enclave key whose signing operation requires macOS user presence (Touch ID or the OS's permitted fallback). There is no software-key fallback. Enrollment exports only public configuration values; it does not approve a batch or change the vault. If the export file already exists, inspect/use it instead of overwriting it. Re-export using a different filename if necessary; enrollment reuses the existing device key.

Copy the two exported values into `config.local.json`:

```json
{
  "approval_scheme": "p256-sha256",
  "approval_public_key": "PUBLIC_X963_KEY_FROM_THE_EXPORT"
}
```

These are two fields within the existing configuration, not a replacement configuration. Keep its roots/exclusions/policy and other values. The new public key/configuration revision invalidates old proposals. Run intake and regenerate the final proposal after configuring the key. Do not bypass this by modifying a stored proposal.

The protected key envelope is at `~/Library/Application Support/VaultApproval/approval-key.enclave`. It is device-bound, not an exportable private key. Do not delete it casually: replacing the key requires updating configuration and reviewing fresh proposals.

## Per-batch workflow

1. The heartbeat discovers changes and posts one concrete proposal in the existing conversation.
2. Export its current review request:

```sh
uv run vault --config config.local.json approval-request --id PROPOSAL_ID
```

The bounded result contains `request_file`, `proposal_id`, and `proposal_digest`. The command rechecks policy, current proposal/configuration, sources and target baseline; it cannot sign approval. The complete request artifact lives outside the vault.

3. Open it in the owner-facing app, using the returned absolute path and a fresh receipt filename:

```sh
open -n "approval-app/build/Vault Approval.app" --args --review "/absolute/path/to/approval-requests/PROPOSAL_ID.json" --receipt "/absolute/path/to/PROPOSAL_ID.receipt.json"
```

Use an existing private external directory for the receipt, such as the same `approval-requests` directory. No output is overwritten. Review the vault path, proposal/configuration fingerprints, every complete before/after file, source grounding, output mapping and uncertainties. Check **I reviewed every affected file…**, then **Approve this exact batch…**. Authenticate when macOS prompts. Closing/canceling the window creates no receipt; a failed or canceled authentication does not approve. The app also refuses an enrollment-key mismatch or a request changed after the window opened.

4. After the receipt is saved, the conversation host can apply it:

```sh
uv run vault --config config.local.json apply --id PROPOSAL_ID --receipt "/absolute/path/to/PROPOSAL_ID.receipt.json"
uv run vault --config config.local.json intake --quiet
```

The verifier chooses the algorithm from owner configuration, not from the receipt. Approval binds to the exact proposal ID/body digest and its configuration/source/target baselines. Changed content/configuration requires a new proposal and new approval. Retrying a completed apply returns its recorded outcome. No changed inputs means no duplicate proposal.

## Add to the existing heartbeat instructions

After one-time setup and manual authentication validation, replace only the old “adapter is unimplemented” instruction with:

```text
After delivering the complete proposal, call approval-request --id PROPOSAL_ID.
Give me its request path, proposal digest, and the command to open Vault Approval.
Wait for my owner approval in that app. A chat reply alone is not a receipt.
After I supply the resulting receipt path, call apply for that same proposal ID.
Verify the result and report actual changes. Never enroll/replace keys, fabricate
receipts, or interpret silence/timeout as approval. Preserve all existing intake,
policy, no-duplicate, scheduler and attachment-lifecycle instructions.
```

Notifications remain in your existing conversation. The final approval action occurs in the local window; this does not implement chat-only approval or a new scheduler. The task has not been changed automatically.

## Trust boundary and limitations

The private key operation is protected by Secure Enclave access control requiring user presence. The UI checkbox alone is not authorization. Signature generation is bound to a fresh authentication context and the immutable loaded request. Message bytes match Python's canonical JSON; signatures are DER ECDSA/SHA-256 and public keys are X9.63 uncompressed P-256 points. Existing Ed25519 test/config integrations remain supported; there is no algorithm negotiation from untrusted receipts.

The app builds with a local ad-hoc hardened-runtime signature. That verifies its build integrity at launch, but does not make editable local source, configuration or binaries a protected security boundary against a malicious same-user process. This project is not an OS sandbox: an agent with unrestricted filesystem permissions can already bypass the CLI and write vault files directly. Never claim receipt verification prevents that. For an enforced deployment, restrict the agent's filesystem access, install the reviewed app/configuration under a protected deployment boundary, and validate the host's actual shell/UI capabilities. Do not authenticate an unexpected signing prompt triggered by automation.

Secure Enclave signing does not prove the user read every line, establish source truth, or eliminate file-write races. Source grounding, current eligibility, exact hashes, and [write recovery](write-safety.md) are independently enforced by the CLI. The brief missing-path and sync limitations remain.

Apple documents [Secure Enclave key protection](https://developer.apple.com/documentation/security/protecting-keys-with-the-secure-enclave) and [user-presence access control](https://developer.apple.com/documentation/security/secaccesscontrolcreateflags/userpresence).

## Verification

```sh
uv run pytest -q
./approval-app/test.sh /tmp/vault-approval-check
./approval-app/build.sh
```

The Swift test harness uses only in-memory software keys for interoperability fixtures; it never calls the production signer or enrolls a key. The full Xcode XCTest framework is not present in the inspected command-line toolchain, so the native parser checks use a standalone compiled harness.

Owner validation before live writes: enroll the key, generate an isolated proposal, cancel once and verify no receipt, approve with OS authentication, verify the receipt/apply result, attempt a changed proposal and wrong key, and run unchanged intake twice. Review the first production diff separately; test approval is not permission for a live batch.
