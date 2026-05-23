# Tasks: issue-158-non-deterministic-safety-block-on-get-me

- [ ] 1. Add `PEER_FLOOD` to `mtprotoTransientCatalog` in `internal/mcp/errorcatalog.go`
  — DoD: `mtprotoErrResult` returns a structured JSON envelope
  `{"error":"RISK_GATED","message":"...","retry_after_seconds":60,"action":"..."}` for
  any `*tgerr.Error` whose `Message == "PEER_FLOOD"`. Existing behavior for
  `FLOOD_WAIT_X`, `SLOWMODE_WAIT_X`, and the permanent catalog is unchanged.
  Unit test in `errorcatalog_test.go` passes.

- [ ] 2. Extend `borrowWithRetry` in `internal/mcp/tools.go` to retry on `PEER_FLOOD`
  (depends on 1)
  — DoD: A new `retryPolicy(err error) (bool, int)` helper returns `(true, 60)`
  for `PEER_FLOOD` and `(true, N)` for `FLOOD_WAIT_N`. `borrowWithRetry` uses
  `retryPolicy` in place of the direct `FloodWaitSeconds` call. Metrics label
  `"peer_flood"` is incremented on each `PEER_FLOOD` retry via
  `TelegramFloodWaitEventsTotal`. Context cancellation during sleep still exits
  immediately. Existing `floodwait_test.go` and `tools_test.go` pass; new test
  covers `PEER_FLOOD` retry and gives up after `maxFloodWaitRetries`.

- [ ] 3. Add `ResolvePeer` fallback to `GetMessages` in `internal/telegram/messages.go`
  — DoD: When the dialog-scan loop completes without finding the peer, the
  function calls `ResolvePeer(ctx, c, peerSpec)`. On success it calls
  `MessagesGetHistory` with the resolved `InputPeerClass` and returns the
  decoded messages. On `ResolvePeer` failure it returns a combined error:
  `"peer %q not found in dialogs and direct resolution failed: %w"`. Existing
  behavior (dialog-scan success path) is unchanged. Unit/integration test added
  in `messages_test.go` (or new file) covering the fallback path with a mock
  that returns an empty dialog list.

- [ ] 4. Improve `GetUnreadMessages` error message for missing explicit peer
  (depends on 3)
  — DoD: When `peerSpec != ""` and the peer is not found in the top-100 dialog
  list, `GetUnreadMessages` returns a non-nil error:
  `"peer %q not found in recent dialogs — use get_messages for this peer's full history"`.
  Previously it returned `(nil, nil)` (empty result), which was silent and
  confusing. Audit log entry in `tools.go` captures this as `status="error"`.
  Existing behavior (peerSpec=="" returns all unread across all dialogs) is
  unchanged.

- [ ] 5. Implement `PeerCache` in `internal/telegram/peercache.go`
  — DoD: New file defines `PeerCache` struct with `Get(userID int64, peerSpec
  string) (tg.InputPeerClass, bool)`, `Set(userID int64, peerSpec string, peer
  tg.InputPeerClass)`, `Evict(userID int64, peerSpec string)`, and `Sweep()`.
  Default TTL is 10 minutes (overridable via `WithTTL`). Thread-safe. Unit tests
  cover TTL expiry, eviction, and `Sweep`. No external dependencies beyond
  `sync` and `time`.

- [ ] 6. Wire `PeerCache` into `SendMessage` and `GetMessages` fallback path
  (depends on 5, 3)
  — DoD: `mcp.Server` gains an optional `PeerCache *telegram.PeerCache` field.
  `toolGetMessages` and `toolSendMessage` pass the cache to a new
  `ResolvePeerCached(ctx, c, peerSpec, cache, userID)` wrapper in
  `internal/telegram/peers.go`. The wrapper checks the cache first; on miss it
  calls `ResolvePeer` and stores the result. On `PEER_ID_INVALID` the caller
  evicts the entry. When `PeerCache` is nil (existing deployments), behavior is
  identical to current. Integration test in `tools_test.go` verifies cache is
  consulted before the Telegram API.

- [ ] 7. Promote MTProto error code to dedicated slog field
  (depends on 1)
  — DoD: `mtprotoErrResult` in `errorcatalog.go` emits `slog.Warn("mcp mtproto
  error", "tool", tool, "mtproto_code", rpcErr.Message, "http_code",
  rpcErr.Code)` for all matched paths — transient catalog, permanent catalog,
  and flood-wait. The existing line at `errorcatalog.go:103` is updated; no new
  log call is added. `redact_test.go` and `errorcatalog_test.go` verify no
  peer/user data leaks through this field.

## Tests

- [ ] T1. `internal/mcp/errorcatalog_test.go` — `PEER_FLOOD` returns `RISK_GATED`
  envelope with `retry_after_seconds=60`; `FLOOD_WAIT_30` still returns
  `flood_wait` envelope with `retry_after_seconds=30`; unknown code returns nil
  (existing).

- [ ] T2. `internal/mcp/tools_test.go` — `borrowWithRetry` with a stub that returns
  `PEER_FLOOD` twice then succeeds: verifies exactly 2 retries, sleep calls, and
  final success. Also verifies that `PEER_FLOOD` on the 4th attempt (after
  `maxFloodWaitRetries`) surfaces the error rather than retrying again.

- [ ] T3. `internal/telegram/messages_test.go` (new or extended) — `GetMessages`
  with a mock API that returns empty dialog list: verifies fallback to
  `ResolvePeer` + `MessagesGetHistory`. Also verify original path (peer in
  dialog list) is unchanged.

- [ ] T4. `internal/telegram/messages_test.go` — `GetUnreadMessages` with explicit
  `peerSpec` and empty dialog response: verifies a non-nil error with the
  actionable message, not a silent empty slice.

- [ ] T5. `internal/telegram/peercache_test.go` (new) — TTL expiry, `Evict`,
  `Sweep`, concurrent access (race detector via `go test -race`).

- [ ] T6. `internal/mcp/tools_test.go` — `toolGetMessages` with `PeerCache` set:
  second call with same peer does not invoke `ContactsResolveUsername` (mock
  verifies call count). Also verify nil-cache path is unchanged.

- [ ] T7. Run `go vet ./...` and `golangci-lint run ./...` — no new warnings
  introduced.

## Rollback

1. The peer cache (`PeerCache`) is in-memory and stateless. Disabling it by
   setting `Server.PeerCache = nil` (or not calling `WithPeerCache`) reverts to
   current behavior without any data migration.

2. The error catalog change (`PEER_FLOOD` -> structured envelope) is a response
   content change only. Reverting `internal/mcp/errorcatalog.go` to remove the
   `mtprotoTransientCatalog` and its check in `mtprotoErrResult` restores the
   previous opaque error string. No database state is affected.

3. The `GetMessages` fallback path is purely additive: it runs only when the
   dialog-scan loop finds no match. Removing the fallback (revert the else-branch
   in `internal/telegram/messages.go`) restores the previous "peer not found in
   dialogs" hard error.

4. `borrowWithRetry` retry extension: revert `retryPolicy` to the original
   `FloodWaitSeconds` call in `internal/mcp/tools.go`. No state is affected.

All four changes are independent at the Git level: each can be reverted with a
single-file diff and no database migration is required.
