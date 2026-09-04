# Design: issue-484-feat-local-bridge-local-activate-cli-dev

## Current state

**Server side is done and ahead of the client.** Reading the clone in order
of the flow:

- `internal/db/local_bridge_devices.go` — `local_bridge_devices` rows carry
  `device_pubkey`/`device_pubkey_algo` (Ed25519, written once at
  registration, `RegisterDevice`), `current_jti`/`credential_issued_at`
  (claimed atomically at first issuance by `ClaimDeviceCredentialLineage`,
  carried forward unchanged by every refresh), and `revoked_at`/
  `revoked_reason` (`RevokeDevice`, `RevokeDeviceAndDenylist`).
- `internal/oauth/local_bridge_activate.go` — `POST /api/local-bridge/
  activate/start` (`handleActivateStart`, line 631) now *requires*
  `device_pubkey`: a base64-encoded 32-byte Ed25519 public key, rejected with
  a named `devicePubkeyRequiredMessage` if absent or malformed
  (line 654-658). The rest of the flow (browser `user_code` entry, Telegram
  OIDC-gated consent screen, `POST /api/local-bridge/activate/poll`) is
  unchanged from #482 and already consumed correctly by `cmd/local/
  activate.go`'s poll loop.
- `internal/oauth/local_bridge_credential.go` — three endpoints scoped by
  `device_id` and gated by Ed25519 proof-of-possession, not by a bearer
  token: `POST /api/local-bridge/devices/{device_id}/nonce` mints a
  single-use nonce; `POST .../credential` is first issuance — verifies a
  signature over `device_id + "." + nonce`, atomically claims the device's
  one credential lineage slot, and mints an **always read-only** hours-scale
  worker token via `workertoken.Minter.MintForDevice`; `POST .../refresh` is
  every later call — same PoP check, but re-derives scopes from a **live**
  `IsSendEnabled` read every time (line 408-420) and carries the *original*
  `jti`/`credential_issued_at` forward unchanged, which is what lets a single
  `RevokeDeviceAndDenylist` call kill every credential the device has ever
  held (design comment, `local_bridge_devices.go:211-243`).
- `internal/workertoken/minter.go` — `MintForDevice` stamps
  `aud=[workerDeviceAudience("mcp-worker-bridge"), mcpAudience]` and
  `Claims.DeviceID`. That audience is **not** `"bridge"`, so a device
  credential cannot dial `/bridge` directly.
- `internal/bridge/tokenhandler.go` — `POST /api/bridge/token`
  (`NewBridgeTokenHandler`) is the exchange step: takes any credential the
  auth middleware accepts (including a `mcp-worker-bridge`-audience device
  credential — `derivedAudiences`/`workerBridgeAudience` in
  `internal/auth/localjwt/issuer.go:311-333`) and mints a 1-hour `aud=bridge`
  token, explicitly forwarding `DeviceID`/`Jti`/`OriginalIssuedAt` from the
  presented credential into the child (comment at `tokenhandler.go:86-95`) —
  this is precisely so a device revocation reaches the bridge token too, not
  just the worker token.
- `internal/bridge/server.go` / `hub.go` — the websocket handler registers a
  connecting daemon by `(userID, deviceID)`; `Hub.EvictDevice(userID,
  deviceID)` force-closes a live connection for that device, which is what
  gives revocation an immediate effect on an already-connected daemon rather
  than waiting out the 1-hour bridge-token TTL.
- `internal/mcp/tools.go` — `set_send_consent` (owner-callable, gated on
  `account:manage`, *not* an admin-only tool — see
  `internal/mcp/local_bridge_owner_tools_test.go:43-98`) and
  `revoke_local_bridge_device` (owner-callable with the same gate,
  `local_bridge_owner_tools_test.go:100-201`) are both already shipped. The
  old admin-only `set_account_send` (`tools.go:1080`) still exists
  side-by-side — this proposal does not touch either.

**Client side has not caught up**, and in one place is outright broken
against the server code in this same clone:

- `cmd/local/config.go:66-158` — `deviceKeyFile{DeviceRegistrationKey
  string}` and `loadOrCreateDeviceKey()` generate and persist a 32-byte
  **opaque** random value, used only as an idempotency key. There is no
  Ed25519 keypair anywhere in `cmd/local` today: no private key generation,
  no signing capability, no public key to send.
- `cmd/local/activate.go:193-201` — `activateStartRequest`'s JSON body sends
  `telegram_id`, `device_registration_key`, `device_label`. It does not send
  `device_pubkey`. Given `handleActivateStart` above, every real call from
  today's client returns HTTP 400 with `devicePubkeyRequiredMessage`.
  `cmd/local/activate_test.go` exercises `runActivateFlow` only against an
  `httptest` fake that does not enforce the field, so the test suite is
  green while the feature is broken end to end — this is exactly the gap
  #484 exists to close.
- `cmd/local/activate.go:106-119` (`runActivate`) — on a successful poll it
  prints `"Device activated (device_id=%s)."` followed by `"An operator
  still needs to issue this device a token..."` and exits. It never calls
  `/nonce` or `/credential`. The whole self-service credential path #483
  built is unused by the CLI.
- `cmd/local/daemon.go:57-138` — `refreshBridgeToken`/`runDaemon` only know
  one refresh mechanism: re-POST the stored `bt.MCPToken` (a bearer JWT
  obtained once via `connect --token`, itself sourced from an operator
  running `mint_worker_token`) to `/api/bridge/token`. Nothing signs a nonce
  or calls `/refresh`.
- `docs/local-bridge.md` and `internal/bridge/DESIGN.md` both already
  mention `activate` (#482 shipped first), but both describe it exactly as
  the current, unfixed code behaves: activation alone, then an operator
  step for the token, then another operator step (`set_account_send`) for
  send. `DESIGN.md`'s "Remaining gaps" item 5 ("No self-serve enablement")
  and item 4 ("No long-lived MCP token to hand to `connect`") are both
  already partially stale — #483 closed the long-lived-token problem for
  the self-service path — but nothing in the client exercises that closure
  yet, so the docs are not wrong so much as describing the wrong half of a
  now-mixed system.

## Proposed solution

### 1. `cmd/local activate` (task 9)

Replace the opaque `device_registration_key`-only scheme with a real device
identity, persisted alongside (not instead of) the existing idempotency key,
since the server's `RegisterDevice` still treats them as separate concepts
(`device_registration_key` for idempotent re-registration, `device_pubkey`
for PoP). Concretely, in `cmd/local/config.go`:

- Extend the persisted device-identity file (rename the concept from
  "device key" to "device identity" internally, keep the JSON file at the
  same path for a smooth upgrade) to hold `device_registration_key`
  (unchanged), `private_key` (Ed25519 seed, base64), and `public_key`
  (Ed25519 public key, base64). Generate the key halves with
  `ed25519.GenerateKey(rand.Reader)` when the file does not carry a USABLE
  pair — not merely when the file is absent, and not merely when the fields
  are empty. Usable means: present, base64-decodable, and exactly
  `ed25519.PrivateKeySize` / `ed25519.PublicKeySize` bytes after decoding.
  A field that is present but truncated, over-long or not valid base64 —
  a half-written file, a hand-edited one, a partially synced directory —
  passes a mere presence check and then panics inside `ed25519.Sign`, which
  validates length by panicking rather than returning an error. Anything that
  fails the check is treated exactly as absent: regenerated in place and the
  file rewritten.

  **Regenerating the keypair MUST also rotate `device_registration_key`.**
  The two are not independent: that key is `RegisterDevice`'s idempotency
  key, so re-running `activate` with the old one returns the EXISTING device
  row — the one holding the OLD public key — and every PoP signature made
  with the new private key fails against it, permanently, with no way to
  re-register. Keeping the registration key while replacing the keys it
  identifies produces a device that can never authenticate. Rotating it makes
  `activate` register a genuinely new device, which is the honest outcome:
  the old key material is gone, so the old device is gone, and its row stays
  revocable by its owner. Anyone who ran `activate` from #482
  already has this file, holding only the opaque
  `device_registration_key`; keying generation on the file's existence would
  skip it for exactly those users and then hand an empty seed to
  `ed25519.Sign`, which panics on a wrong-length key rather than returning an
  error. The check is on the fields, and a file missing either half is
  completed in place and rewritten. Otherwise generation happens exactly
  where `loadOrCreateDeviceKey` generates the opaque key today, and write the file atomically at `0600` via the existing
  `writeFileAtomic` helper — no new file-permission code path.
- A device identity, once generated, is loaded and reused on every later
  `activate` run, mirroring the existing idempotency-key reuse rationale
  (`config.go:115-120`): a retried `activate` must resolve to the *same*
  device row and the *same* keypair, or the server's first-issuance-then-
  refresh distinction (`ClaimDeviceCredentialLineage`) sees a second,
  unrelated public key show up for a device_id it already trusts.

In `cmd/local/activate.go`:

- `activateStartRequest`'s JSON body gains
  `"device_pubkey": base64.StdEncoding.EncodeToString(pub)`.
- After `runActivateFlow` returns a `device_id` (poll status `"done"`), add a
  bootstrap step, `bootstrapDeviceCredential(ctx, server, deviceID,
  privateKey)`, that:
  1. `POST /api/local-bridge/devices/{device_id}/nonce` (unauthenticated,
     device_id-scoped — no credential needed yet).
  2. Signs `deviceID + "." + nonce` with `ed25519.Sign(priv, msg)`, base64
     (standard) encodes it, matching `verifyDevicePoP`'s exact expected wire
     format (`local_bridge_credential.go:266-267`).
  3. `POST /api/local-bridge/devices/{device_id}/credential` with
     `{nonce, signature}`.
  4. On `200`, persists `{device_id, worker_token, expires_at, jti}` to a
     new file (see "Alternatives" for why not reusing `bridge_token.json`).
  5. On `409` (lineage already claimed), do NOT simply exit 0 — check
     whether the credential file is on disk first, and only then decide.

     The 409 has two causes that look identical from here and end very
     differently. Either the credential really was issued and persisted USABLY —
     present, parseable, carrying the fields the daemon needs — and
     re-running `activate` should be a no-op; or the server claimed the
     lineage and the client has nothing usable to show for it — a timeout, a crash, a
     closed lid between the claim and the write. In that second case the
     device row is claimed, the disk has no credential, and there is no way
     back: first issuance cannot re-run (the slot is taken, by construction —
     see #483's atomic claim), `daemon` has no device credential to refresh
     from, and its legacy fallback needs a `bridge_token.json` that a
     self-service onboarding never produced. Exiting 0 would report success
     over a machine that can never connect, recoverable only by wiping the
     config directory — which also orphans the device row.

     So: if the credential file is USABLE, print that the device is already
     activated and exit 0. Present-but-unusable — truncated, empty, invalid
     JSON, missing `device_id` — counts as absent, for the same reason a
     present-but-malformed key does: the daemon cannot start from it either
     way, and the only thing a presence check achieves is that `activate`
     declines to repair the one case it could have. If it is not usable, run
     the PoP refresh flow
     (`/nonce` → sign → `/refresh`, which needs no existing credential).
     Persist only a `200` whose body parses into the expected credential
     shape; on any other status, or an unparseable body, exit NON-ZERO
     naming what failed. Writing an error body into the credential file and
     exiting 0 would report a repair that did not happen and hide the real
     failure behind a daemon that cannot connect — the same "success over a
     broken machine" this step exists to prevent, one level down. Only a
     genuine repair exits 0.
     Refresh is the only path that can, and it is available precisely because
     it authenticates by possession of the device key rather than by any
     credential. Covered by T15.

     **`activate` serialises itself.** The device identity and the device
     credential live in two files, and the credential names the `device_id`
     the identity's key must sign for. Two concurrent runs can therefore
     leave the pair mismatched: one run regenerates the identity (a corrupt
     key, per the rule above) while the other is mid-flight with the old
     one, and the disk ends up holding the new private key next to a
     credential issued for the old device. Nothing rejects that combination
     at write time; `daemon` simply signs with a key the server does not
     have for that `device_id` and can never connect.

     Take an exclusive lock on a lockfile in the config directory for the
     whole of `activate` — acquire it before reading the identity, hold it
     past the credential write — and exit with a clear "another activation is
     already running" if it is held. `activate` is an interactive setup
     command; serialising it costs nothing and removes the whole class.
     There is no lock helper in `cmd/local` today, so this is new — and it
     must be **build-tagged, not `syscall.Flock`**. `Flock` does not exist in
     `syscall` on Windows, and `windows/amd64` is one of the five targets
     release-please cross-compiles (`release-please.yml:91`), so naming it
     directly breaks the build for a platform this CLI ships to. Two small
     files next to `writeFileAtomic`: `syscall.Flock` under
     `//go:build !windows`, and `LockFileEx` from `golang.org/x/sys/windows`
     under `//go:build windows` — that module is already in `go.mod` as an
     indirect dependency, so this promotes it rather than adding one.
     Covered by T21, and by the cross-compile the release workflow runs.

     **`daemon` takes the same lock around its credential write.** The lock
     is not only about two `activate` runs. A daemon refresh in flight while
     the user re-runs `activate` finishes afterwards and writes a credential
     carrying the OLD `device_id` over the new one — the same
     identity/credential mismatch, reached from the other side. The daemon
     holds it only across the read-modify-write of the credential file, not
     for its whole run, so a long-lived daemon never blocks an `activate` for
     more than that window. Covered by T22.

     With that lock held, two `activate` runs cannot corrupt the server
     state either: the lineage claim is atomic and refresh reuses the same `jti`, so
     neither run's credential invalidates the other's and both stay valid to
     their own expiry. The only exposure is on disk, where a slower process
     can write an older credential over a newer one — costing an earlier
     refresh and nothing else, and self-healing because refresh needs no
     credential. Write through the existing `writeFileAtomic` helper so a
     reader never sees a half-written file, and do not overwrite a credential
     whose `expires_at` is later than the one being written.
  6. On any other failure, exit non-zero with a message that names the
     device as already activated (so the user does not re-run `activate`
     from scratch and orphan the device row) and says the credential step
     can be retried by running `activate` again.
- Success message changes from "An operator still needs to issue this device
  a token..." to something reflecting the new reality — the device is fully
  usable, `daemon` is the next command.

### 2. `cmd/local daemon` (task 10)

Add a second refresh mechanism and pick between it and the existing one by
what is present on disk, so the two paths never have to agree on a shared
mutable file:

- The device-signed path deliberately depends on NO live credential. The
  `/nonce`, `/credential` and `/refresh` routes are registered without auth
  middleware (`internal/oauth/server.go:985-987`) and are gated by proof of
  possession alone, so a daemon whose worker token expired while the machine
  was asleep still refreshes normally. Do not add a "refresh only while the
  current credential is valid" guard: it would turn a laptop lid into a
  bootstrap deadlock that only re-running `activate` could clear.
- New helper `refreshDeviceCredential(ctx, cfg, deviceID, priv)` in
  `daemon.go`, structurally parallel to `refreshBridgeToken`: nonce → sign →
  `POST /api/local-bridge/devices/{device_id}/refresh` → gets a fresh
  `worker_token` → immediately exchanges it via the *existing*
  `refreshBridgeToken`-style call to `POST /api/bridge/token` (bearer =
  the fresh `worker_token`) to get the `aud=bridge` token the websocket
  actually dials with. This reuses `POST /api/bridge/token` unchanged — the
  only new code is minting the *input* to that exchange via PoP instead of
  via a static bearer token.
- `runDaemon`'s per-attempt refresh check
  (`daemon.go:106-118`) becomes: if a device identity + device credential
  file exist, refresh via the device-signed path; else fall back to
  `refreshBridgeToken` exactly as today. Both paths converge on the same
  `bridgeTokenFile{BridgeToken, ExpiresAt}` shape that `daemonSession`
  already dials with, so `daemonSession` itself needs no changes.
- `runDaemonCmd`'s startup refresh-if-stale check (`main.go:305-337`) gets
  the same branch.
- This is the concrete mechanism behind the "keeps the existing bearer-only
  renewal path as a legacy fallback" requirement in the issue: the fallback
  is not a flag or a mode switch, it is simply "device files present or
  not," so an account onboarded before this change (only `bridge_token.json`
  on disk, no device identity file) keeps working with zero migration step.

### 2b. The claims the public site makes about this mode

`docs/local-bridge.md` is not the only place that tells users an operator has
to be involved, and the other two are worse because they are the pages a
prospective user reads first:

- `internal/web/landing.html:411` (the FAQ entry for Local Bridge): *"an
  operator enables it per account — it is not self-serve yet."*
- `internal/web/docs.html:263`: *"It costs you a machine that stays on and an
  operator has to enable it per account, so it is not part of the standard
  install path"*, and the sentence after it points at *"what the operator
  still does."*

Both become false the moment this ships. Leaving them is not a documentation
backlog item, it is the site asserting the opposite of the shipped behaviour
to the exact audience the change is for — and this repository has already paid
for that once: `internal/web/localbridge.go`'s own comment records that
`/security` claimed `session_encrypted` was NULL for local-mode accounts long
after it stopped being true, and calls a guide that quietly disagrees with the
repository "the same failure with a longer fuse."

So both pages are edited in this PR, not after it. What replaces them is the
narrow, still-true residue: Local Bridge costs you a machine that stays on,
and migrating an *existing hosted* account still needs `set_account_mode`.
Everything else about operator involvement goes.

`internal/web/local-bridge.md` is a generated mirror of `docs/local-bridge.md`
(`go:embed` cannot reach outside the package), and
`TestLocalBridgeMarkdownMatchesDocs` fails the build when they drift — so the
docs rewrite is followed by `cp docs/local-bridge.md
internal/web/local-bridge.md`. The test catches a forgotten copy; naming the
step here means the implementer does not have to discover that from a red
build.

### 3. `docs/local-bridge.md` (task 12)

Restructure around the split the issue asks for:

- **Client / owner actions**: `init`, `login`, `activate` (now genuinely
  zero-operator, ending in a connected-ready credential), `daemon`, and
  `set_send_consent` as the self-service way to turn sending on (replacing
  the current "operator runs `set_account_send`" framing — `set_send_consent`
  is owner-gated, per `local_bridge_owner_tools_test.go`, not admin-gated).
  Document what actually gates a send, in this order, because getting it
  wrong in either direction is harmful. Turning consent OFF takes effect on
  the daemon's **next send**, not its next refresh: `evaluateSendGate` reads
  `send_enabled` from the account row on every call and is authoritative
  (`internal/mcp/tools.go:387,1702` — "a real send happens only when
  ALLOW_SEND, the send scope, per-account send_enabled, and the per-peer rate
  limit all pass"). The scope carried by the credential is the coarse gate;
  live `send_enabled` is the decisive one, which is the same state-driven
  rule #483 applies at mint, applied at the point of use.

  Turning consent ON is the direction that needs the credential to move
  first, because the gate cannot pass until the credential carries the scope.
  That acquisition is PROMPT, not scheduled: the daemon performs an
  out-of-band `/refresh` as soon as it observes a send refused for want of
  scope, and retries — **at most once per send, and only when the refreshed
  credential actually gained the scope**.

  Both bounds are load-bearing. A refusal for want of scope is reachable by
  anyone who can cause the daemon to attempt a send, and while consent is
  simply off, every refresh returns a credential without the scope: an
  unbounded "refresh then retry" is then an infinite loop against the server,
  driven remotely, for as long as consent stays off. So the daemon compares
  the scopes it got back before retrying, retries only if they changed in the
  way that matters, and otherwise reports the dry-run exactly as it does
  today. Repeated refusals must not each cost another refresh: rate-limit the
  out-of-band refresh per device the way any other self-triggered network
  call is bounded. Waiting for the hours-scale scheduled refresh would
  mean an owner grants consent and then waits hours for their first message —
  which is not zero-admin onboarding, only a slower kind of waiting, and it
  would make the sequence in this issue's own Definition of Done untrue.

  Do not document this the other way round — a revoke that is described as
  waiting for a refresh understates the protection an owner actually has, and
  a grant that is described as instant without the out-of-band refresh
  overstates what the credential can do. And do not "fix" the revoke
  direction by evicting the daemon's websocket: an owner who revokes send
  consent is already protected on the very next call, and revoking a device's
  credential lineage is device revocation's job, which under #483's
  carried-forward `jti` rule would brick the device if used here.
- **Operator: support and recovery only**: `connect --token` fed by a
  manually minted `mint_worker_token`/`POST /api/mcp/worker-token` credential
  (kept, documented as the migration/recovery path — not the default),
  `set_account_mode` (migrating an existing hosted account — activation does
  not do this), `provision_local_account` is removed from the happy path
  entirely since `activate` now provisions the account itself, and
  `revoke_local_bridge_device` as the operator's/owner's device-kill switch,
  with its `EvictDevice`-then-denylist semantics spelled out.
- Read-only-by-default activation: state plainly that first issuance is
  **always** read-only regardless of `send_enabled` (`local_bridge_
  credential.go:352-356`), and that send capability requires the separate
  `set_send_consent` step — mirroring the design rationale that activation
  and consent are deliberately two different actions, not one.
- Hours-scale credential TTL + automatic refresh, device binding (the
  private key never leaves the machine — signature only), revocation
  behavior (denylist stops any new `/refresh` or reconnect; `EvictDevice`
  drops an already-connected daemon immediately), and the legacy
  manually-minted-worker-token path reframed explicitly as "compatibility
  only," matching the issue's constraint that the documented happy path
  never points at behavior that is unavailable.
- Update the "Two things that are no longer operator steps" callout (already
  present, currently describing #468) to add a third: minting the first
  credential and turning on send are no longer operator steps either, for an
  account onboarded through `activate`.

### 4. `internal/bridge/DESIGN.md` (task 13)

- Remove "No self-serve enablement" from "Remaining gaps," and fold its
  substance (self-service issuance existed at the *server* layer since #483
  but had no client) into a short "Closed by #484" note, matching the
  existing pattern for gaps 1 and 2.
- Rewrite gap 4 ("No long-lived MCP token to hand to `connect`") the same
  way: closed for the self-service path (`activate` never hands the user a
  token to paste), explicitly still open for the legacy `connect --token`
  path, which is deliberately retained.
- Add a "Device-bound credential lifecycle" section describing, in order:
  bootstrap trust boundary (device generates the keypair locally; only the
  public key and signatures ever cross the network; the server never
  possesses the private key and cannot forge a signature), first-issuance
  vs. refresh (first issuance is always read-only; refresh re-derives scope
  from live `send_enabled` state every call), the one-lineage-per-device
  invariant (`current_jti` claimed once, carried forward, denylisting it
  kills every credential the device has held), and revocation SLA
  (immediate for an already-connected daemon via `Hub.EvictDevice`; for any
  future connect/refresh attempt, immediate once `RevokeDeviceAndDenylist`'s
  transaction commits, since the denylist is consulted at every
  `needsRevocationCheck` credential verification).
- Note the legacy worker-token path (`mint_worker_token`,
  `POST /api/mcp/worker-token`, 30-90 day TTL, `/renew`) as
  compatibility-only, kept for accounts onboarded before this change and for
  operator-driven recovery, not for new onboarding.

## Alternatives

- **Fold the device-signed credential into `bridge_token.json`** instead of
  a new file. Rejected: `bridge_token.json`'s shape
  (`MCPToken`/`BridgeToken`/`ExpiresAt`) is the legacy path's contract, and
  `refreshBridgeToken` already writes it unconditionally on every legacy
  refresh. Reusing it for the device-signed path means every write from
  either path has to avoid clobbering fields the other path depends on, and
  "does this file mean legacy or device-signed" becomes an inference from
  which fields happen to be populated rather than which file exists. A
  second, purpose-specific file makes "which path is this daemon on" a
  single, unambiguous filesystem check, which is exactly the branch
  `runDaemon` needs to make on every startup and refresh.
- **Have `daemon` always try the device-signed path first and silently swap
  to legacy on any failure**, instead of gating on file presence. Rejected:
  this would mask a broken device-signed refresh (revoked device, corrupted
  private key file) as a silent downgrade to a bearer token that might not
  even exist, producing a confusing failure far from its cause. Gating on
  "which files are actually present" fails loudly and specifically instead.
- **Ship a `rotate-device-key` subcommand as part of this issue** for a
  device whose local private key file is suspected compromised. Rejected as
  out of scope: the issue's task list stops at 9/10/12/13, and the existing
  `revoke_local_bridge_device` + a fresh `activate` run already gets a user
  to a new device_id and a new keypair, just without reusing the old
  device_id. Recorded as a follow-up, not silently dropped — see "Out of
  scope."

## Platform impact

- **Migrations**: none. All schema (`local_bridge_devices.device_pubkey`,
  `current_jti`, etc.) already exists and is populated by server code that
  predates this proposal; this proposal only changes `cmd/local` and the two
  documents.
- **Backward compatibility**: the explicit design goal. An operator-minted
  legacy worker token, exchanged via `connect --token` and refreshed via the
  unchanged bearer-only `refreshBridgeToken`, must keep working (T9). A
  config directory from before this change (no device identity file) falls
  back to the legacy path automatically, with no migration step and no
  behavior change for that user.
- **Resource impact**: negligible — a handful of extra HTTP round trips
  during `activate` (once) and during each `daemon` refresh (already
  happens on the existing bearer path; the device-signed path adds one
  extra round trip, the `/nonce` call, before the refresh call).
- **Risks + mitigations**:
  - *Risk*: a device's private key file leaks. *Mitigation*: unchanged from
    the existing threat model for `bridge_token.json` — `0600` permissions,
    `restrictUmask()` at process start, and `revoke_local_bridge_device`
    (already shipped) as the response, which now also has an immediate
    effect on a live connection via `EvictDevice`.
  - *Risk*: `activate` dies between successful device activation and
    successful credential issuance (network drop, process killed), leaving
    a device row with no usable credential and a user unsure whether to
    re-run `activate`. *Mitigation*: the credential-bootstrap step is
    designed to be safely re-run — a repeat `activate` reuses the same
    persisted keypair and device_registration_key, resolves to the same
    device_id, and a second `/credential` call either succeeds (if the
    first one never landed) or returns 409 (if it did), which the client
    treats as success. No manual recovery step is needed.
  - *Risk*: documentation drift recurs (the exact failure mode that created
    this proposal). *Mitigation*: task 13 explicitly ties `DESIGN.md`'s
    "Remaining gaps" section to what actually shipped in each sub-issue, the
    same pattern the file already uses for gaps 1/2, so the next reader can
    tell a closed gap from an open one without cross-referencing the git
    log.
