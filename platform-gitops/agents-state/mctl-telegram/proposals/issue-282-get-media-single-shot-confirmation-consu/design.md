# Design: issue-282-get-media-single-shot-confirmation-consu

## Current state

### ConfirmStore (internal/mcp/confirm.go)

`ConfirmStore` is an in-memory mutex-guarded `map[string]*Confirmation`. A
`Confirmation` holds the user ID, action label, SHA-256 payload hash, and
expiry time. It is strictly single-shot: `Consume()` deletes the map entry
under the lock on the very first call regardless of whether the subsequent
check passes (expiry, user, hash). From `confirm.go` lines 82-99:

```go
func (s *ConfirmStore) Consume(id string, userID int64, payloadHash string) (*Confirmation, error) {
    s.mu.Lock()
    defer s.mu.Unlock()
    c, ok := s.m[id]
    if !ok {
        return nil, ErrConfirmationNotFound
    }
    delete(s.m, id)   // <-- deleted here, before expiry/user/hash checks
    ...
}
```

`Consume` is called by the send_message flow (via `confirm_message`) and the
pin_message flow, and by `toolGetMedia`. All three callers receive a
delete-on-first-touch guarantee today.

### MediaStore (internal/mcp/mediastore.go)

`MediaStore` is a parallel in-memory map keyed by the same `confirmation_id`.
`Pop()` (lines 51-63) atomically retrieves and deletes the `MediaDownloadRef`
entry — mirroring `Consume`'s delete-on-first-touch behaviour.

### toolGetMedia (internal/mcp/media_tools.go, lines 158-231)

The handler executes in order:

1. (line 183) `s.Confirms.Consume(confID, id.UserID, hash)` — validates and
   **deletes** the confirmation row.
2. (line 195) `ref := s.MediaStore.Pop(confID)` — retrieves and **deletes**
   the `MediaDownloadRef`.
3. (line 201) Size-cap check against `s.MediaDownloadMaxBytes`.
4. (lines 207-214) `borrowWithRetry(downloadCtx, "get_media", ...)` with a
   60-second deadline, calling `telegram.DownloadMedia(ctx, c, ref.Location, ...)`.

Steps 1 and 2 happen before the network I/O in step 4. If the caller's
transport layer times out during step 4 and retries the call with the same
`confirmation_id`, step 1 of the retry finds no map entry and returns
`ErrConfirmationNotFound`, producing the misleading client error:
`"confirmation_id not found, expired, or already used"`.

---

## Proposed solution

### Principle

Replace the delete-on-first-touch pattern in the `get_media` path with a
claim-then-finalize pattern:

- `Claim()` on `ConfirmStore`: marks the entry as in-flight without deleting
  it. A second concurrent call to `Claim()` on the same ID returns a new
  sentinel `ErrConfirmationInFlight`.
- `Finalize()` on `ConfirmStore`: deletes the entry after the download
  completes (success or terminal failure). Called via `defer` in the handler.
- `Get()` on `MediaStore`: returns the ref without deleting it (analogous to a
  peek). Expiry is still checked.
- `Delete()` on `MediaStore`: removes the entry. Called via `defer` alongside
  `Finalize()`.

`Consume` and `Pop` (used by send/pin flows and their tests) are not changed.

### Changes by file

#### internal/mcp/confirm.go

1. Add `InFlight bool` field to `Confirmation`.

2. Add sentinel:
   ```go
   var ErrConfirmationInFlight = errors.New("download already in progress for this confirmation_id")
   ```

3. Add `Claim(id string, userID int64, payloadHash string) (*Confirmation, error)`:
   - Acquires `s.mu.Lock()`.
   - Returns `ErrConfirmationNotFound` if key is absent.
   - Returns `ErrConfirmationNotFound` if `s.now().After(c.ExpiresAt)` (does
     NOT delete on expiry check, unlike `Consume`; entry remains for `Sweep`).
   - Returns `ErrConfirmationWrongUser` if `c.UserID != userID`.
   - Returns `ErrConfirmationMismatch` if `c.PayloadHash != payloadHash`.
   - Returns `ErrConfirmationInFlight` if `c.InFlight` is already true.
   - Sets `c.InFlight = true` and returns the confirmation.
   - Does NOT delete the entry.

4. Add `Finalize(id string)`:
   - Acquires `s.mu.Lock()`.
   - Deletes `s.m[id]` unconditionally (no-op if already gone via `Sweep`).

   Note: `Sweep()` already iterates over all entries and deletes expired ones
   regardless of `InFlight` state; the `ExpiresAt` field is the hard backstop.

#### internal/mcp/mediastore.go

1. Add `Get(key string) *MediaDownloadRef`:
   - Acquires `ms.mu.Lock()`.
   - Returns nil if key is absent or `ms.now().After(ref.ExpiresAt)`.
   - Returns the ref without deleting it.

2. Add `Delete(key string)`:
   - Acquires `ms.mu.Lock()`.
   - Deletes `ms.m[key]` (no-op if absent).

   `Pop` is unchanged (still used by existing tests and kept for any future
   callers that want the original atomic-retrieve-and-delete semantics).

#### internal/mcp/media_tools.go (toolGetMedia handler)

Replace the current consume/pop sequence with claim/get + deferred
finalize/delete:

```go
// Validate and mark the confirmation in-flight (does not delete).
if _, cerr := s.Confirms.Claim(confID, id.UserID, HashMediaPayload(peer, int64(messageID))); cerr != nil {
    s.audit(ctx, id, "get_media", telegram.RedactPeer(peer), cerr, startedAt)
    switch {
    case errors.Is(cerr, ErrConfirmationMismatch):
        return mcplib.NewToolResultError("confirmation_id was issued for a different (peer, message_id) — re-run prepare_get_media"), nil
    case errors.Is(cerr, ErrConfirmationWrongUser):
        return mcplib.NewToolResultError("confirmation_id belongs to another identity"), nil
    case errors.Is(cerr, ErrConfirmationInFlight):
        return mcplib.NewToolResultError("download already in progress for this confirmation_id — retry shortly"), nil
    default:
        return mcplib.NewToolResultError("confirmation_id not found, expired, or already used"), nil
    }
}
// Unconditionally release after the download terminates (success or error).
defer func() {
    s.Confirms.Finalize(confID)
    s.MediaStore.Delete(confID)
}()

// Retrieve the media ref without deleting it.
ref := s.MediaStore.Get(confID)
if ref == nil {
    s.audit(ctx, id, "get_media", telegram.RedactPeer(peer), fmt.Errorf("media ref expired"), startedAt)
    return toolErr("media reference expired or missing — re-run prepare_get_media"), nil
}
```

The rest of the handler (size-cap check, `borrowWithRetry`, result encoding) is
unchanged.

#### internal/mcp/media_tools.go (tool description)

Update the `mcplib.WithDescription` string for `get_media` to replace
"single-shot" with wording that reflects the in-flight window:

Before: "The confirmation is single-shot and expires in 10 minutes."
After: "The confirmation becomes in-flight on first use and is released when
the download completes. Concurrent retries receive an 'in progress' response."

---

## Alternatives

### A. Defer both Consume and Pop until after the download

Validate all inputs (user, payload hash) before the download, but call
`Consume` and `Pop` only on success. This prevents premature deletion but
re-introduces a window where a second concurrent call passes validation before
the first download finishes, causing a double-download. The send/pin flow
explicitly guards against this by deleting immediately — extending that logic to
media downloads requires the same claim-not-delete approach anyway, so this
alternative provides no simplification.

### B. Cache the download result

Store the base64 result in a short-lived in-memory map after the download
completes so that post-completion retries are served from cache. This solves
a different (less common) problem: a retry that arrives *after* a successful
download. It adds memory pressure (base64 is 33% larger than the raw bytes;
a 15 MB file becomes ~20 MB in cache), requires a separate TTL and eviction
policy, and would return stale data if the Telegram message is edited between
download and replay. The in-flight approach covers the observed failure mode
without these costs.

### C. Increase the 60-second download context timeout

Raising the timeout to 120 or 300 seconds narrows the window but does not
close it — a sufficiently slow download (or a client with an aggressive
timeout) can still trigger the bug. It also increases worst-case resource
holding per request. Not sufficient as a standalone fix.

---

## Platform impact

### Migrations

None. `ConfirmStore` and `MediaStore` are in-memory only; no schema changes.

### Backward compatibility

- `ConfirmStore.Consume` and `MediaStore.Pop` are unchanged. All existing
  callers (send_message, pin_message, and their tests) are unaffected.
- The new `ErrConfirmationInFlight` error is additive; no existing switch
  statements need updating outside of `toolGetMedia`.
- The `get_media` tool schema (inputs and output) is unchanged. Only the
  prose description changes.

### Resource impact

- Each in-flight `get_media` call now holds its `Confirmation` and
  `MediaDownloadRef` map entries for up to 60 seconds longer than before.
  Both structs are small (< 1 KB each). The number of concurrent downloads is
  bounded by the `Pool` session cap, so memory impact is negligible.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| In-flight entry never cleaned up if the handler panics | `Finalize`/`Delete` are called via `defer`, which runs through panics that are caught by the HTTP framework's recover middleware. |
| Sweep removes an in-flight entry whose TTL expired while download is in progress | Acceptable: the 10-minute TTL is well beyond the 60-second download timeout. If Sweep fires during a download, the download completes or fails before TTL elapses in practice. |
| A misbehaving client deliberately calls `get_media` twice in rapid succession to probe whether a confirmation exists | The second call now receives `ErrConfirmationInFlight` instead of `ErrConfirmationNotFound`. This is slightly more information, but it is not sensitive: the client already holds the `confirmation_id` it issued the first call with. The user/hash binding still prevents cross-user probing. |
