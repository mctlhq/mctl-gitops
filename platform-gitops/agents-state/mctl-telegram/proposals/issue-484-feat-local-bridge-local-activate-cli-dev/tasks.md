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
      present (depends on 4). Device identity + device credential file
      present → device-signed refresh path; only legacy `bridge_token.json`
      present → existing bearer-only `refreshBridgeToken`, unchanged. —
      DoD: a config directory containing only legacy files behaves exactly
      as before this change (existing daemon tests pass unmodified); a
      config directory containing device files uses the new path
      exclusively.

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

- [ ] T7. End-to-end (new): fresh install → `init` → local Telegram
      `login` → `activate` → a read call succeeds → explicit
      `set_send_consent` grant → a send call succeeds → credential refresh
      (forced, e.g. by shortening TTL in test config) → daemon reconnects
      with the refreshed credential. Assert `telegram_accounts
      .session_encrypted IS NULL` throughout.
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
- [ ] T11. Docs regression: every command and flag shown in
      `docs/local-bridge.md` matches `cmd/local`'s actual flag set (a
      table-driven or scripted check against `flag.NewFlagSet` definitions
      is acceptable), and the zero-admin sequence documented there is the
      one T7 exercises.
- [ ] T12. Device-signed refresh picks up a `set_send_consent` change: grant
      send consent, force a refresh, and assert the daemon's next
      credential carries `telegram:messages:send`/`telegram:messages:pin`
      without re-running `activate`.
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
