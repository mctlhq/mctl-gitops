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
      sequence true: the daemon performs an out-of-band `/refresh` on
      observing a send refused for want of scope, and retries — see
      design.md's consent section, which specifies the same mechanism. Revoking consent already needs no such step: the live
      `evaluateSendGate` read refuses the next send outright.
- [ ] T16. Branch selection is on the credential, not the identity: a config
      directory holding a device identity file but no device credential (an
      `activate` that was interrupted) still refreshes through the legacy
      bearer path and the daemon keeps working. Validate by mutation:
      branching on the identity file makes this test fail with a daemon that
      cannot start.
- [ ] T17. Device identity files that are not usable are repaired in place,
      table-driven over: #482's shape (opaque registration key only, no
      Ed25519 halves), an empty `private_key`, a truncated one, an
      over-long one, and one that is not valid base64. Each must end with a
      working signature and no panic. Validate by mutation twice, because
      these are two different bugs: generating only when the FILE is absent
      makes the #482 case panic, and checking only that the field is
      non-empty makes the truncated and undecodable cases panic.
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
- [ ] T15. `activate` repairs a half-claimed lineage, table-driven over a
      stored credential that is absent, empty, truncated, invalid JSON,
      missing `device_id`, unusable-but-carrying-a-later `expires_at`, and
      usable but naming a DIFFERENT device with a later `expires_at` (the
      last two prove the freshness guard can veto neither a repair nor a
      post-rotation write): claim the lineage server-side, put the
      file in each of those states, re-run `activate` — it must obtain a
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
      what makes this true); granting it makes a send succeed promptly,
      without the owner waiting for the scheduled refresh — the daemon
      performs an out-of-band `/refresh` on observing a scope refusal and
      retries. Validate by mutation: removing the out-of-band refresh leaves
      the send a dry-run until the scheduled refresh, which is the wait this
      test exists to prevent.
- [ ] T22. Identity and credential cannot disagree: run the interleavings
      that used to produce a mismatch — two `activate` runs, and a daemon
      refresh completing after `activate` rotated the identity — and assert
      the record on disk always names one device consistently, whichever run
      wrote last. Validate by mutation: splitting the record back into two
      files reproduces the mismatch in both interleavings, which is the class
      the single record exists to remove.
- [ ] T21. `activate` is serialised where it touches files and NOWHERE else:
      a lock held briefly by a daemon refresh makes `activate` WAIT and then
      succeed, not fail; a lock held past the timeout makes it exit non-zero
      naming the concurrent run; and an `activate` parked in its browser wait
      does NOT block a daemon credential refresh. Validate by mutation twice:
      holding the lock across the browser wait blocks the daemon behind a
      human who walked away, and failing fast instead of waiting makes a
      routine refresh abort an activation for a reason the user cannot act
      on.
      And the pairing it protects: with the lock in place, a run that
      regenerates the identity cannot leave a credential from another run
      beside it. Validate by mutation: dropping the lock lets an interleaved
      pair write private key B next to a credential for device_id A, and the
      daemon then signs with a key the server does not hold for that device.
- [ ] T23. The daemon refuses a corrupt identity instead of panicking or
      rotating: corrupt `private_key` and start `daemon` — it exits with a
      message naming `activate` as the fix, does not reach `ed25519.Sign`,
      and does NOT register a new device. Validate by mutation: loading
      without the usable check panics; rotating in the daemon silently
      re-registers the machine as a new device.
- [ ] T25. A seed round-trips through its own check: run `activate` twice
      with no corruption in between and assert the second run REUSES the
      stored identity — same `device_registration_key`, same device row, no
      rotation. Validate by mutation: validating the seed against
      `ed25519.PrivateKeySize` (64) instead of `ed25519.SeedSize` (32)
      rejects the value this design stores, so every run regenerates,
      rotates, and orphans a device row.
- [ ] T24. Half-matching key material is treated as corrupt: an identity file
      whose `private_key` and `public_key` are both well-formed and correctly
      sized but do NOT belong to each other is regenerated (and the
      registration key rotated with it), rather than being used to sign.
      Validate by mutation: checking only the lengths accepts the mismatched
      pair, and every signature it makes is then rejected by the server
      forever.
- [ ] T18. The out-of-band refresh is bounded: with consent OFF, a send
      refused for want of scope triggers at most ONE `/refresh` and is then
      reported as a dry-run; repeated refusals do not each trigger another.
      Validate by mutation: refreshing and retrying unconditionally loops
      forever, and the loop is reachable by anyone who can make the daemon
      attempt a send.
- [ ] T19. The 409 repair flow fails loudly: make `/refresh` answer 500
      during the repair — `activate` must exit non-zero, write no credential
      file, and name the failure. Validate by mutation: persisting the
      response body regardless of status writes an error payload into the
      credential file and exits 0.
- [ ] T20. Regenerating a corrupted keypair rotates the registration key:
      corrupt `private_key` on an already-activated device, re-run
      `activate`, and assert a NEW device row is registered rather than the
      old one being returned by idempotency. Validate by mutation: keeping
      the old registration key returns the existing row with the old public
      key, and every later PoP signature fails against it permanently.
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
