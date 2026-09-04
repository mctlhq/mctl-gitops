# Design: issue-495-fix-bridge-hub-call-can-send-on-a-channe

## Current state

`internal/bridge/hub.go` defines `daemonConn` (hub.go:38-49):

```go
type daemonConn struct {
	send         chan Envelope
	pending      sync.Map
	pendingCount atomic.Int64
	deviceID     string
}
```

`Hub.conn map[int64]*daemonConn` holds at most one connection per user,
guarded by `h.mu sync.Mutex`.

Three teardown paths remove the map entry and close `dc.send` while
holding `h.mu`:

- `Unregister(userID)` (hub.go:120-130) — called by `server.go:191` from
  the websocket handler's cleanup, on every disconnect for any reason.
- `UnregisterSend(userID, send)` (hub.go:137-154) — same as `Unregister`
  but only acts if `dc.send == send`, to avoid evicting a connection that
  already replaced this one via `Register`.
- `EvictDevice(userID, deviceID)` (hub.go:169-185, issue-483) — same
  identity guard, keyed on `dc.deviceID` instead of the channel value.

`Hub.Call` (hub.go:193-228) is the one path that reads `dc` and then
*sends* on `dc.send` after releasing the lock:

```go
h.mu.Lock()
dc, ok := h.conn[userID]
h.mu.Unlock()
...
select {
case dc.send <- env:
case <-ctx.Done():
	return Envelope{}, ctx.Err()
}
```

If any of the three teardown paths closes `dc.send` in the gap between the
unlock and the send, this `select` panics with "send on closed channel".
`Hub.Deliver` (hub.go:234-255) has the same lock-then-release pattern but
never sends on `dc.send` — it only touches `dc.pending`, a `sync.Map`
that nothing closes — so it is not affected.

The consumer of `dc.send` is the writer goroutine in
`internal/bridge/server.go:153-183`, which detects teardown via the
closed-channel signal:

```go
case env, ok := <-send:
	if !ok {
		// Channel closed by Hub.Unregister or a newer Register.
		return
	}
```

`internal/bridge/server_test.go:76-114` contains a hand-rolled copy of
this same writer loop (a fake daemon endpoint for HTTP-level tests) and
relies on the identical closed-channel signal.

`hub_test.go` has three tests that assert teardown by reading from `send`
and checking `ok == false`: `TestHub_RegisterAndUnregister` (line 30),
`TestHub_NewRegisterEvictsPrevious` (line 42), and
`TestHub_EvictDevice_MatchingDeviceIsEvicted` (line 252). These assert an
implementation detail (`send` closes) rather than the actual contract
(no more envelopes get through, further `Call`s fail cleanly), so they
need to change along with the production code.

## Proposed solution

Stop overloading `dc.send`'s closedness as the teardown signal. Add a
dedicated `done` field to `daemonConn`:

```go
type daemonConn struct {
	send         chan Envelope
	done         chan struct{}
	pending      sync.Map
	pendingCount atomic.Int64
	deviceID     string
}
```

`Register` (hub.go:93-116) allocates `done: make(chan struct{})` alongside
`send` for every new `daemonConn`.

Each of the three teardown paths closes `dc.done` under `h.mu` instead of
(or in addition to, see below) `dc.send`:

- `Register`'s eviction branch (hub.go:96-101): `close(prev.done)`.
- `Unregister` (hub.go:120-130): `close(dc.done)`.
- `UnregisterSend` (hub.go:137-154): `close(dc.done)`, still gated on
  `dc.send == send` — the identity check is unchanged, only the channel
  that gets closed changes.
- `EvictDevice` (hub.go:169-185): `close(dc.done)`, still gated on
  `dc.deviceID == deviceID`.

Each of these call sites already holds `h.mu` and already established
"only touch this entry if it is still the one we mean" — that guard is
exactly what keeps `close(dc.done)` single-fire per `daemonConn`, the
same way it already keeps `close(dc.send)` single-fire today. No new
locking or `sync.Once` is needed.

`Hub.Call` selects on `dc.done` alongside the send:

```go
select {
case dc.send <- env:
case <-dc.done:
	return Envelope{}, ErrNoDaemonConnected
case <-ctx.Done():
	return Envelope{}, ctx.Err()
}
```

This closes the race: even if teardown happens between the unlock and the
send, the send is never issued on a channel that's already closed —
either the send wins (rare, harmless, matches today's happy path) or
`dc.done` wins and `Call` returns `ErrNoDaemonConnected` cleanly. `dc.send`
itself is never closed anymore by any path, so there is nothing left for a
racing `Call` to panic on.

Because `dc.send` is no longer closed, the writer goroutine in
`server.go:153-183` can no longer use `ok` from `<-send` to detect
teardown. It switches to selecting on `dc.done` too:

```go
for {
	select {
	case env := <-send:
		if err := wsjson.Write(ctx, conn, env); err != nil {
			return
		}
	case <-done:
		// Hub torn down this connection (Unregister/UnregisterSend/
		// EvictDevice/replaced by a newer Register).
		return
	case <-ticker.C:
		...
	case <-ctx.Done():
		return
	}
}
```

`server.go`'s handler already calls `hub.Register` and gets back `send`;
it will also need the paired `done` channel. Since `Register`'s current
signature returns only `chan Envelope`, this proposal changes it to
return `(chan Envelope, <-chan struct{})` — the two are always allocated
and torn down together, so handing them back together keeps the pairing
obvious at the call site and avoids a second Hub method just to fetch
`done`. `server.go:94` and `server_test.go:76`'s fake-daemon helper both
update their `hub.Register(...)` call sites accordingly, and the fake
daemon's writer loop mirrors the same `done` select as the real one.

`dc.pending` and `dc.pendingCount` are untouched — `Deliver` and the
overload check do not participate in this race.

## Alternatives

- **`recover()` around the send in `Call`.** The issue explicitly rejects
  this: it stops the crash but hides a real lifecycle bug, and a
  recovered panic can't tell the caller "disconnected" from "sent, then
  the connection died before we could return" — it would still need to
  invent an error to return, at which point it is strictly worse than
  just doing the `done`-channel fix, which gets a real signal for free.
  Dropped.
- **Keep closing `dc.send` for teardown, but have `Call` recheck
  `h.conn[userID]` under the lock immediately before sending.** This
  narrows the race window but does not close it: `Register`/`Unregister`
  can still land between the recheck and the send, since the recheck
  can't hold `h.mu` across the (potentially blocking) channel send
  without serializing all calls and teardowns on one user through a
  single mutex, which would also block the writer goroutine's drain.
  Dropped as unsound.
- **Wrap every send on `dc.send` in a `sync.RWMutex` per `daemonConn`,
  taken for read by `Call` and for write (to exclude concurrent sends)
  by teardown before closing.** Works, but adds a second lock in the hot
  path for every single `Call`, and changes `Deliver`/writer-goroutine
  locking too since they'd need to agree on the same discipline. The
  `done`-channel approach gets the same safety from a `select`, which is
  idiomatic Go for exactly this "stop signal" shape and matches what the
  issue itself suggests. Dropped in favor of the simpler `select`-based
  fix.

## Platform impact

- **Migrations**: none — this is in-process Go state, no schema or
  database change.
- **Backward compatibility**: `Hub.Register`'s return type changes from
  `chan Envelope` to `(chan Envelope, <-chan struct{})`. This is an
  internal package (`internal/bridge`), not part of any external API or
  wire protocol — only `server.go` and `server_test.go` in this repo call
  it, and both are updated in the same change. No websocket wire-format
  change; daemons on the other end of `/bridge` see no difference.
- **Resource impact**: one extra `chan struct{}` (unbuffered, zero
  payload) allocated per `daemonConn`, i.e. per connected daemon. Given
  `maxPendingCalls`-scale concurrency per daemon and typically low daemon
  counts, this is negligible.
- **Risks**:
  - Missing one of the three teardown call sites when swapping
    `close(dc.send)` for `close(dc.done)` would silently reintroduce the
    exact race this fixes. Mitigated by grepping all `close(` call sites
    in `hub.go` as part of the change (there are exactly four:
    `Register`'s eviction branch, `Unregister`, `UnregisterSend`,
    `EvictDevice`) and by the interleaving `-race` test in tasks.md,
    which is designed to fail if any path still panics.
  - Forgetting to update the writer goroutine in `server.go` (or its test
    double in `server_test.go`) to select on `done` would leave the
    writer goroutine blocked forever on `<-send` after teardown, leaking
    it. Mitigated by updating both call sites in the same change and by
    the existing `server_reconnect_test.go` / `server_test.go` suite,
    which already exercises daemon disconnect/reconnect and would hang
    (visible as a test timeout) if the writer goroutine leaked.
  - The three `hub_test.go` tests that currently assert `send` closes
    (`TestHub_RegisterAndUnregister`, `TestHub_NewRegisterEvictsPrevious`,
    `TestHub_EvictDevice_MatchingDeviceIsEvicted`) will fail to compile
    against a `Register` that returns two values / will observe `send`
    staying open forever. They are updated to assert the real contract
    instead (`done` closes, and/or a subsequent `Call` returns
    `ErrNoDaemonConnected`) as part of this change, not left broken.
