# Local Bridge: finish zero-admin onboarding, resilient refresh, and bridge lifecycle safety

## Context

Issue #479 split the Local Bridge zero-admin work into #481-#484. #481-#483 shipped the device registry, browser-driven activation, owner send consent/revocation, and device-bound credential issuance/refresh. #484 is the final integration issue: make the local CLI use that server-side path end to end, make the daemon refresh itself without operator help, update the product/docs surface, and close the remaining bridge lifecycle defect that survived the #483 merge.

The current repository is in a mixed state:

- Server-side activation requires an Ed25519 `device_pubkey` on `POST /api/local-bridge/activate/start`.
- Device credential issuance/refresh exists at `/api/local-bridge/devices/{device_id}/{nonce,credential,refresh}` and refresh derives scopes from live consent state.
- `set_send_consent` and `revoke_local_bridge_device` are owner-callable tools.
- `cmd/local` still persists only an opaque registration key, does not send `device_pubkey`, does not bootstrap a device credential, and daemon refresh still knows only the legacy bearer path.
- `docs/local-bridge.md` and `internal/bridge/DESIGN.md` still describe operator token minting/send enablement as normal setup.
- The merged #483 implementation still leaves a real connection-lifecycle race in `internal/bridge/hub.go`: `Hub.Call` can retain a `daemonConn` after the hub lock is released while `EvictDevice`/replacement/unregister closes `dc.send`, allowing `send on closed channel` and process panic.

This proposal closes all of those gaps together because #484 is the final gate before #479 can close.

## User stories

- AS a new Local Bridge user I WANT `init -> login -> activate -> daemon` to complete onboarding with zero operator actions SO THAT a read-only daemon can run immediately after owner approval.
- AS a Local Bridge user I WANT the daemon to refresh device-bound credentials with proof-of-possession even after its previous access JWT has expired SO THAT expiry never forces an operator/manual token recovery path.
- AS a Local Bridge user I WANT send permission to remain a separate owner-controlled consent and have refreshed credentials reflect the current DB state SO THAT activation and send authorization stay distinct.
- AS a Local Bridge user I WANT device revocation/replacement to terminate live bridge connections safely SO THAT concurrent RPC traffic cannot crash the service.
- AS an existing customer I WANT manually minted legacy worker tokens to continue working SO THAT migration is additive and non-breaking.
- AS a visitor to the Local Bridge landing/connect/onboarding surface I WANT the self-service path presented first SO THAT the product does not teach a legacy operator-first flow that is no longer required.
- AS a documentation reader I WANT `docs/local-bridge.md`, `internal/bridge/DESIGN.md`, and the actual CLI behavior to agree.

## Acceptance criteria (EARS)

### Activation and device identity

- WHEN `mctl-telegram-local activate --telegram-id <id>` runs for the first time THE SYSTEM SHALL generate an Ed25519 keypair locally, persist the private material at `0600`, retain the existing idempotency registration key, and send the base64-encoded public key as `device_pubkey` on activation start.
- WHEN activation polling reports `status: "done"` THE SYSTEM SHALL obtain a nonce, sign `device_id + "." + nonce`, call the first-issuance credential endpoint, and persist the resulting device credential metadata before returning success.
- IF credential bootstrap fails after browser activation succeeded THEN THE SYSTEM SHALL report that the device is already activated, preserve the local identity, exit non-zero, and make retry possible without creating an orphaned/new device identity.
- WHEN `activate` is re-run with the same local identity THE SYSTEM SHALL reuse the same registration key and Ed25519 keypair. A server response indicating the credential lineage already exists SHALL be treated as an already-activated condition and the client SHALL proceed through the refresh path rather than requiring operator recovery.
- THE private key SHALL never leave the machine; only the public key and signatures SHALL cross the network.

### Device-signed daemon refresh

- WHEN `daemon` starts or the current device credential approaches expiry, AND a device identity/device credential are present THE SYSTEM SHALL obtain a fresh PoP nonce, sign it locally, call the device refresh endpoint, and exchange the returned worker credential for an `aud=bridge` token.
- WHEN the previous device access JWT is already expired THE SYSTEM SHALL still be able to obtain the PoP nonce, complete device-signed refresh, and reconnect without any operator/admin action. The refresh bootstrap SHALL NOT require presentation of the expired access JWT as a prerequisite.
- IF a Local Bridge config contains only the legacy manually-minted token artifacts THEN THE SYSTEM SHALL retain the current bearer-only bridge-token refresh behavior unchanged.
- IF device files are present but the device path is revoked/corrupt/broken THEN THE SYSTEM SHALL fail that device path explicitly and SHALL NOT silently downgrade to a legacy bearer credential.
- WHEN `set_send_consent` changes account send state THE SYSTEM SHALL derive the device's scopes from current DB state on the next device refresh without reactivation.

### Hub connection lifecycle safety

- WHEN `Hub.Call` races with `EvictDevice`, `Register` replacement, `Unregister`, or `UnregisterSend` THE SYSTEM SHALL NOT send to a closed channel, panic the process, leak a permanently blocked pending call, or route a request to a superseded daemon connection.
- Connection teardown SHALL use a lifecycle primitive safe for concurrent senders (for example a `done`/cancellation signal plus non-closing outbound queue, or an equivalent design). A panic `recover` around sends SHALL NOT be the primary correctness mechanism.
- Device revocation SHALL still evict the targeted live device connection promptly, while preserving exact `(userID, deviceID)` targeting semantics.

### Zero-admin end to end

- WHEN a brand-new Telegram identity completes `init -> login -> activate -> daemon` THE SYSTEM SHALL reach a connected read-only daemon with zero calls to `provision_local_account`, `set_account_mode`, `set_account_send`, manual `mint_worker_token`, or `POST /api/mcp/worker-token`.
- THROUGHOUT that self-service flow `telegram_accounts.session_encrypted` SHALL remain `NULL`.
- WHEN the owner explicitly grants send consent and the daemon refreshes, a send call SHALL succeed with the refreshed send scopes.
- WHEN the device credential is forced past expiry, the daemon SHALL refresh via PoP and reconnect successfully without operator action.
- WHEN the daemon is restarted after successful activation THE SYSTEM SHALL reuse the same persisted device identity and continue self-service refresh.

### Product/docs surface

- WHEN a user visits the Local Bridge landing/connect/onboarding surface THE SYSTEM SHALL present `init -> login -> activate -> daemon` as the primary/default path and SHALL NOT imply that operator provisioning, manual token minting, or `set_account_send` is the normal setup path.
- Legacy/operator actions SHALL be described only as support, recovery, migration, or compatibility paths.
- `docs/local-bridge.md` SHALL split **Client / owner actions** from **Operator: support and recovery only**, document read-only-by-default activation, separate owner send consent, device binding, hours-scale credentials, automatic PoP refresh, expired-access recovery, revocation, and legacy compatibility.
- `internal/bridge/DESIGN.md` SHALL document the final bootstrap trust boundary, one credential lineage per device, live-state scope derivation, bridge token derivation, revocation/eviction semantics, safe connection lifecycle, and the legacy bearer path as compatibility-only.
- Documentation examples SHALL match actual CLI flags/routes and the zero-admin sequence exercised by E2E tests.

## Required tests

- T7 zero-admin E2E: fresh install -> `init` -> local Telegram `login` -> `activate` -> read call -> explicit owner send grant -> send call -> forced device refresh -> daemon reconnect; assert `session_encrypted IS NULL` throughout.
- T8 regression: existing hosted fresh-user flow and hosted->local migration remain working.
- T9 regression: manually minted legacy worker tokens still authenticate, connect, and renew through the legacy path.
- T10 activation idempotency: repeated activation reuses the same local identity/device and recovers cleanly from already-claimed credential lineage.
- T11 docs/UX regression: examples/flags/routes match the executable CLI and product onboarding presents the zero-admin path first.
- T12 lifecycle-race regression: deterministic concurrent `Hub.Call` + eviction/replacement/unregister coverage, plus `go test -race` for the affected bridge package/path.
- T13 expired-access regression: expire the current device access JWT, obtain PoP nonce, refresh, exchange bridge token, and reconnect with no operator/admin action.
- T14 consent refresh regression: changing owner send consent changes scopes on the next device refresh and never retroactively mutates an already-issued credential.
- T15 private-key permissions: persisted device identity/private key remains `0600` on POSIX-permission-respecting filesystems.

## Out of scope

- Re-designing Telegram OIDC/browser consent from #482.
- Re-designing the device credential lineage/audience model from #483 except where required to make expired-access PoP refresh actually work as specified.
- Windows ACL hardening beyond the existing local-file protection model.
- Binary signing/notarization.
- A connected-daemons management UI.
- Removing the legacy `connect --token` path during this issue.
- Device-key rotation as a first-class subcommand.

## Non-negotiable closure gate

#484 SHALL NOT be marked complete, and #479 SHALL NOT close, until the Hub lifecycle race is no longer reproducible, expired-access PoP refresh is proven, the zero-admin E2E is green, and the user-facing onboarding/docs surface presents the self-service path as primary.