# Tasks: issue-484-feat-local-bridge-local-activate-cli-dev

- [ ] 1. Generate and persist an Ed25519 device identity in `cmd/local`.
      Extend the device-identity file (`cmd/local/config.go`) with
      `private_key`/`public_key` (base64) alongside the existing
      `device_registration_key`, generated together via
      `ed25519.GenerateKey` on first use and written atomically at `0600`
      through the existing `writeFileAtomic` helper. Reused verbatim on
      every later `activate` run, exactly like the existing
      `device_registration_key` reuse. — DoD: a fresh config directory
      produces a keypair on first `activate` invocation; a second
      invocation loads the same keypair (public key bytes identical) rather
      than generating a new one; the file is `0600` on disk.

- [ ] 2. Send `device_pubkey` on activation start (depends on 1).
      `cmd/local/activate.go`'s `activateStartRequest` JSON body gains
      `"device_pubkey": base64.StdEncoding.EncodeToString(pub)`. —
      DoD: a real (non-fake) server round trip against
      `handleActivateStart` no longer returns `devicePubkeyRequiredMessage`;
      a unit test asserts the field is present and correctly encoded in the
      outgoing request body.

- [ ] 3. Implement the post-activation credential bootstrap (depends on 1,
      2). Add `bootstrapDeviceCredential(ctx, server, deviceID, priv)` to
      `cmd/local/activate.go`: `POST .../nonce` → sign
      `deviceID + "." + nonce` with `ed25519.Sign` → base64 (standard)
      encode → `POST .../credential` with `{nonce, signature}` → on `200`
      persist `{device_id, worker_token, expires_at, jti}` to a new file
      (see design.md, "Alternatives", for why not `bridge_token.json`); on
      `409` treat as already-activated success; on any other failure exit
      non-zero with a message naming the device as activated and the
      credential step as retryable. Wire it into `runActivate` after a
      successful `runActivateFlow`, replacing the "an operator still needs
      to issue this device a token" message. — DoD: `activate` run against
      a server implementing #482+#483 ends with a device credential file on
      disk and a success message that does not mention an operator; a
      second `activate` run after full success exits 0 without re-minting.

- [ ] 4. Implement device-signed daemon refresh (depends on 3). Add
      `refreshDeviceCredential(ctx, cfg, deviceID, priv)` to
      `cmd/local/daemon.go`: nonce → sign → `POST .../refresh` → exchange
      the returned `worker_token` via the existing `POST /api/bridge/token`
      call to obtain the `aud=bridge` token `daemonSession` dials with. —
      DoD: given a valid device credential file, `daemon` connects to
      `/bridge` without any `bridge_token.json`/`MCPToken` on disk.

- [ ] 5. Branch `runDaemon` and `runDaemonCmd` on which credential files are
      present (depends on 4). The branch is on the DEVICE CREDENTIAL, not on
      the device identity: a usable device credential file present →
      device-signed refresh path; otherwise → existing bearer-only
      `refreshBridgeToken`, unchanged. A legacy user who tries the new
      `activate` and does not finish it ends up with a device identity file
      AND their working `bridge_token.json`; branching on the identity would
      send that daemon down a path with no credential to refresh and break a
      setup that worked five minutes earlier. The identity file alone means
      "activation was attempted", never "the device is provisioned". —
      DoD: a config directory containing only legacy files behaves exactly
      as before this change (existing daemon tests pass unmodified); a
      config directory with a device identity but NO device credential still
      uses the legacy path and keeps working; a config directory with a
      device credential uses the new path exclusively. Covered by T16.

- [ ] 6. Rewrite `docs/local-bridge.md` (depends on 1-5). Split **Client /
      owner actions** (`init`, `login`, `activate`, `daemon`,
      `set_send_consent`) from **Operator: support and recovery only**
      (`connect --token`, `mint_worker_token`/`POST /api/mcp/worker-token`,
      `set_account_mode`, `revoke_local_bridge_device`). Document
      read-only-by-default first issuance, scope-derived-fresh-per-refresh
      send consent, device binding, hours-scale TTL + auto-refresh,
      revocation behavior, and the legacy worker-token path as
      compatibility-only. Update every command example and flag to match
      what `cmd/local` actually accepts after tasks 1-5. — DoD: no sentence
      in the file describes a step this proposal made self-service as an
      operator step; every CLI example matches actual flags (feeds T11).

- [ ] 6b. Mirror the rewritten guide into the package the site serves:
      `cp docs/local-bridge.md internal/web/local-bridge.md` (depends on 6) —
      DoD: `TestLocalBridgeMarkdownMatchesDocs` passes. `go:embed` cannot
      reach outside the package, which is why the copy exists at all.
- [ ] 6c. Correct the two public pages that state this mode is not
      self-serve (depends on 1-5): `internal/web/landing.html:411` ("an
      operator enables it per account — it is not self-serve yet") and
      `internal/web/docs.html:263` ("an operator has to enable it per
      account ... what the operator still does"). Keep only what stays
      true — a machine that stays on, and `set_account_mode` for migrating
      an EXISTING hosted account — DoD: T14 passes.
- [ ] 7. Update `internal/bridge/DESIGN.md` (depends on 1-6, same PR as the
      code per the issue's constraint). Close "No self-serve enablement";
      revise "No long-lived MCP token to hand to `connect`" to distinguish
      the closed self-service path from the still-open legacy path; add the
      device-bound credential lifecycle section (bootstrap trust boundary,
      first-issuance-vs-refresh, one-lineage-per-device, revocation SLA);
      mark the legacy worker-token path compatibility-only. — DoD: the
      "Status in one line" and "Remaining gaps" sections no longer
      contradict what `cmd/local` does after this proposal ships.

## Tests

- [ ] T7. End-to-end (new), in exactly this order, because it is the
      issue's Definition of Done and the product promise it encodes: fresh
      install → `init` → local Telegram `login` → `activate` → a read call
      succeeds → explicit `set_send_consent` grant → **a send call
      succeeds** → credential refresh (forced, e.g. by shortening TTL in
      test config) → daemon reconnects with the refreshed credential.
      Assert `telegram_accounts.session_encrypted IS NULL` throughout.

      The send step comes BEFORE the forced refresh on purpose. If a grant
      cannot take effect until the daemon's next scheduled refresh, an owner
      who has just granted consent waits hours before their first message
      leaves — which is not "zero-admin onboarding", it is a slower kind of
      waiting. Do not reorder the test to accommodate that; make the
      sequence true. The daemon acquires the granted scope promptly (an
      immediate refresh on observing that a send was refused for want of
      scope, or an equivalent mechanism), and the docs describe whichever is
      built. Revoking consent already needs no such step: the live
      `evaluateSendGate` read refuses the next send outright.
- [ ] T16. Branch selection is on the credential, not the identity: a config
      directory holding a device identity file but no device credential (an
      `activate` that was interrupted) still refreshes through the legacy
      bearer path and the daemon keeps working. Validate by mutation:
      branching on the identity file makes this test fail with a daemon that
      cannot start.
- [ ] T17. A device identity file written by #482's `activate` — opaque
      registration key only, no Ed25519 halves — is completed in place on
      the next `activate` run, and signing works afterwards. Validate by
      mutation: generating only when the file is absent makes this test
      panic in `ed25519.Sign`.
- [ ] T8. Regression: existing hosted fresh-user flow and hosted→local
      migration (`set_account_mode`) pass unmodified — no behavior change
      for either.
- [ ] T9. Regression: a manually minted legacy worker token (
      `mint_worker_token`/`POST /api/mcp/worker-token`) still authenticates
      `connect`, and `daemon` still self-renews it via the unchanged
      bearer-only path, through and past this change's migration window.
- [ ] T10. `activate` idempotency: run `activate` to completion twice
      against the same config directory. Second run reuses the same
      keypair and device_id, and the credential-issuance 409 is handled as
      success (not surfaced as an error).
- [ ] T14. No shipped page claims an operator gate that no longer exists:
      assert the rendered `/` and `/docs` pages contain neither "not
      self-serve" nor an "operator enables it per account" claim for Local
      Bridge. This is a content assertion on purpose — the same class of
      staleness `internal/web/localbridge.go`'s comment records for
      `/security`, which asserted `session_encrypted` was NULL long after
      that stopped being true. Validate by mutation: restoring either
      sentence fails the test.
- [ ] T15. `activate` repairs a half-claimed lineage: claim the lineage
      server-side, delete the client's credential file to simulate the crash
      between the claim and the write, re-run `activate` — it must obtain a
      credential through `/refresh` and persist it, and `daemon` must then
      start. Validate by mutation: exiting 0 on the 409 without checking the
      file leaves `daemon` unable to start, which is the bricked state this
      test exists to catch.
- [ ] T11. Docs regression: every command and flag shown in
      `docs/local-bridge.md` matches `cmd/local`'s actual flag set (a
      table-driven or scripted check against `flag.NewFlagSet` definitions
      is acceptable), and the zero-admin sequence documented there is the
      one T7 exercises.
- [ ] T12. Consent changes take effect in the right direction and at the
      right moment: revoking `set_send_consent` makes the very NEXT send from
      an already-connected daemon a dry-run preview, with no refresh,
      reconnect or restart in between (the live `evaluateSendGate` read is
      what makes this true); granting it adds send/pin scope on the device's
      next scheduled refresh.
- [ ] T13. Private key file permissions: assert the persisted device
      identity file is `0600` immediately after creation on a
      POSIX-permission-respecting filesystem (mirrors the existing
      `perms_test.go`/`umask_test.go` pattern already in `cmd/local`).

## Rollback

Every change in this proposal is additive at the protocol level — no server
endpoint, schema, or existing file format is modified, only `cmd/local` and
two markdown files. Rolling back means reverting the PR:

- A previously-activated device (one that already has a device identity
  file and a device credential on disk) simply stops working with the
  reverted binary, since the old binary never wrote those files and does
  not know how to read them; the user re-runs `connect --token` with an
  operator-minted legacy token as an immediate workaround, or waits for a
  fixed build.
- A device that never completed activation under the new code is
  unaffected — nothing was written that the old binary needs to clean up.
- No database rows need to be reverted: `local_bridge_devices` rows created
  by the new `activate` flow are ordinary rows the pre-existing
  `revoke_local_bridge_device` tool can already revoke if a rollback needs
  to also disable devices that activated during the affected window.
- Documentation reverts with the same PR revert; no separate doc-only
  rollback step is needed.
