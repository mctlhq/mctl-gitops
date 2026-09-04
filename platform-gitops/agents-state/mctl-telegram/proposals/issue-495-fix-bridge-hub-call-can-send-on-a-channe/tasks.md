# Tasks: issue-495-fix-bridge-hub-call-can-send-on-a-channe

- [ ] 1. Add `done chan struct{}` to `daemonConn` (hub.go:38-49) and
      allocate it in `Register` (hub.go:113) alongside `send`.
      — DoD: `daemonConn` has the new field; `go build ./...` compiles
      with `Register` still returning only `chan Envelope` at this point
      (field added but not yet wired into teardown/Call).

- [ ] 2. Change every teardown path to close `dc.done` instead of
      `dc.send`, keeping each path's existing identity guard unchanged
      (depends on 1):
      - `Register`'s eviction branch (hub.go:96-101): `close(prev.done)`.
      - `Unregister` (hub.go:120-130): `close(dc.done)`.
      - `UnregisterSend` (hub.go:137-154): `close(dc.done)`, still gated
        on `dc.send == send`.
      - `EvictDevice` (hub.go:169-185): `close(dc.done)`, still gated on
        `dc.deviceID == deviceID`.
      — DoD: `grep -n "close(" internal/bridge/hub.go` shows `done` being
      closed at all four sites and `send` closed at none of them.

- [ ] 3. Update `Hub.Call` (hub.go:193-228) to select on `dc.done` and
      return `ErrNoDaemonConnected` when it fires, per the issue's
      suggested shape (depends on 2).
      — DoD: `Call`'s send `select` has three cases: `dc.send <- env`,
      `<-dc.done` -> `ErrNoDaemonConnected`, `<-ctx.Done()` -> `ctx.Err()`.

- [ ] 4. Change `Register`'s signature to
      `func (h *Hub) Register(userID int64, deviceID string) (chan Envelope, <-chan struct{})`
      returning `(dc.send, dc.done)`, and update its doc comment
      (depends on 1).
      — DoD: signature matches; doc comment describes both return values.

- [ ] 5. Update `internal/bridge/server.go`'s websocket handler
      (server.go:94, 153-183) to capture the new `done` return value and
      have the writer goroutine select on it instead of relying on `ok`
      from `<-send` (depends on 4).
      — DoD: writer goroutine has a `case <-done:` branch that returns;
      the `case env, ok := <-send:` branch drops the `!ok` teardown check
      (an open, never-closed `send` channel makes `ok` always true going
      forward).

- [ ] 6. Update `internal/bridge/server_test.go`'s fake-daemon writer
      loop (server_test.go:76-114) to match the same `done`-select shape
      as task 5, so the test double stays behaviorally identical to
      production (depends on 4).
      — DoD: fake daemon's `hub.Register(...)` call site and writer loop
      compile and mirror `server.go`'s pattern.

- [ ] 7. Update the three `hub_test.go` tests that currently assert
      teardown via a closed `send` channel to assert the real contract
      instead (depends on 3, 4):
      - `TestHub_RegisterAndUnregister` (hub_test.go:16-33): assert
        `dc.done` closes (via the two-value `Register` return) and/or
        that a subsequent `Call` returns `ErrNoDaemonConnected`.
      - `TestHub_NewRegisterEvictsPrevious` (hub_test.go:35-46): assert
        the first connection's `done` closes on the second `Register`.
      - `TestHub_EvictDevice_MatchingDeviceIsEvicted` (hub_test.go:243-255):
        assert `done` closes after a matching `EvictDevice`.
      — DoD: all three tests compile against the new `Register` signature
      and pass, asserting `done`/`ErrNoDaemonConnected` instead of a
      closed `send`.

- [ ] 8. Write the interleaving regression test described in T1 below
      (depends on 3).
      — DoD: test exists in `hub_test.go`, passes under
      `go test ./internal/bridge/... -race -run TestHub_CallRacesTeardown`.

- [ ] 9. Run the full verification pass (depends on 5, 6, 7, 8).
      — DoD: `go build ./...`, `go vet ./...`, `gofmt -l .` (no output),
      and `go test ./... -race` all pass locally.

## Tests

- [ ] T1. `TestHub_CallRacesUnregister` (new, hub_test.go): register a
      daemon, start many goroutines that concurrently call `Hub.Call`
      for that `userID` while another goroutine repeatedly calls
      `Unregister` then re-`Register`s the same `userID` in a tight loop
      for a bounded number of iterations. Assert the whole test completes
      without panicking and every `Call` that returns an error returns
      one of `ErrNoDaemonConnected`, `ErrCallTimeout`, or `ctx.Err()` —
      never an unrecovered panic. Run with `-race`.

- [ ] T2. `TestHub_CallRacesEvictDevice` (new, hub_test.go): same shape as
      T1 but the teardown goroutine calls `EvictDevice(userID, deviceID)`
      with the matching `deviceID` instead of `Unregister`, covering the
      issue-483 path explicitly named in the issue. Run with `-race`.

- [ ] T3. Mutation check (manual, not committed): temporarily revert
      `Unregister`/`UnregisterSend`/`EvictDevice`/`Register`'s eviction
      branch to `close(dc.send)` (the pre-fix behavior) while keeping
      `Call`'s new `select` on `dc.done`/`ErrNoDaemonConnected`, and
      confirm T1 or T2 now panics or fails. This is the "reverting the
      fix breaks the test" check the issue asks for — perform it once
      during implementation review, then discard the revert; it does not
      ship as a repo file.

- [ ] T4. Re-run the existing suite unmodified in intent —
      `TestHub_CallReturnsResponse`, `TestHub_CallNoDaemonConnected`,
      `TestHub_CallTimeoutWhenDaemonSilent`, `TestHub_CallOverloadedReturnsError`,
      `TestHub_ConnectionsTotal_CountsEveryRegistration`,
      `TestHub_EvictDevice_MismatchedDeviceIsRefused`,
      `TestHub_EvictDevice_Idempotent`,
      `TestHub_EvictDevice_EmptyDeviceIDNeverMatches`,
      `TestHub_EvictDevice_NoConnection` — to confirm none of them relied
      on `send` closing (they don't, per design.md's audit) and all still
      pass unchanged apart from any `Register` call-site signature update.

- [ ] T5. `go test ./internal/bridge/... -race` (whole package, including
      `server_test.go` and `server_reconnect_test.go`) to confirm the
      writer-goroutine change in task 5/6 does not leak a goroutine or
      hang on disconnect/reconnect.

## Rollback

This is a single, self-contained internal-package change (`internal/bridge`
only) with no schema, wire-protocol, or external-API change. Rollback is a
plain `git revert` of the merge commit — no data migration, no coordinated
deploy with the Local Bridge daemon side (the websocket frames on the wire
are unchanged; only in-process Go synchronization inside the relay
changes). If a revert is needed after deploy, redeploy the previous image
tag via the standard release pipeline; no Hub state persists across process
restarts, so there is nothing to reconcile.
