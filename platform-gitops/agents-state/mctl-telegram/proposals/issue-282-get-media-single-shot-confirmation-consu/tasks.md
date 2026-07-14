# Tasks: issue-282-get-media-single-shot-confirmation-consu

- [ ] 1. Add `ErrConfirmationInFlight` sentinel and `Claim`/`Finalize` methods
  to `ConfirmStore` in `internal/mcp/confirm.go` — DoD: `Claim` marks an
  entry as in-flight without deleting it and returns `ErrConfirmationInFlight`
  when already marked; `Finalize` deletes the entry unconditionally; all
  existing `Consume`/`Sweep` behaviour is unchanged; `go vet` and
  `golangci-lint` pass.

- [ ] 2. Add `Get` and `Delete` methods to `MediaStore` in
  `internal/mcp/mediastore.go` (depends on nothing, can be done in parallel
  with 1) — DoD: `Get` returns the ref without deleting and returns nil when
  absent or expired; `Delete` removes the entry unconditionally; existing
  `Pop`/`Sweep` behaviour is unchanged; `go vet` passes.

- [ ] 3. Update `toolGetMedia` in `internal/mcp/media_tools.go` to replace
  `Confirms.Consume`/`MediaStore.Pop` with `Confirms.Claim`/`MediaStore.Get`
  and add `defer` cleanup calling `Confirms.Finalize`/`MediaStore.Delete`
  (depends on 1 and 2) — DoD: handler returns "download already in progress"
  on a concurrent retry with the same `confirmation_id`; all three existing
  error branches (NotFound, Mismatch, WrongUser) still produce the same client
  messages; the size-cap, download, and base64-encoding paths are unchanged;
  `go build ./...` succeeds.

- [ ] 4. Update the `mcplib.WithDescription` string for `get_media` in
  `internal/mcp/media_tools.go` (depends on 3) — DoD: the description no
  longer states "single-shot" for the confirmation lifecycle; wording reflects
  that the confirmation is held in-flight until the download completes.

## Tests

- [ ] T1. `TestConfirmStore_Claim_HappyPath` in `internal/mcp/confirm_test.go`:
  `Issue` then `Claim` succeeds; entry is still present in the map (not
  deleted); `InFlight` is true on the returned confirmation.

- [ ] T2. `TestConfirmStore_Claim_InFlight` in `internal/mcp/confirm_test.go`:
  `Issue`, `Claim` (succeeds), `Claim` again — second call returns
  `ErrConfirmationInFlight`.

- [ ] T3. `TestConfirmStore_Claim_ThenFinalize` in `internal/mcp/confirm_test.go`:
  `Issue`, `Claim`, `Finalize` — subsequent `Claim` returns
  `ErrConfirmationNotFound` (entry gone).

- [ ] T4. `TestConfirmStore_Claim_Expired` in `internal/mcp/confirm_test.go`:
  Pin clock past `ConfirmationTTL`; `Claim` returns `ErrConfirmationNotFound`
  and does NOT delete the entry (leaving it for `Sweep`).

- [ ] T5. `TestConfirmStore_Claim_WrongUser` and
  `TestConfirmStore_Claim_MismatchedPayload` in `internal/mcp/confirm_test.go`:
  verify that the existing user and hash checks work the same way as in
  `Consume`.

- [ ] T6. `TestConfirmStore_Consume_Unchanged` in `internal/mcp/confirm_test.go`:
  existing `TestConfirmStore_SingleShot` and related tests remain green with
  no modification — assert that `Consume` still deletes on first call and that
  `InFlight` is not set by `Consume` (field is zero-value).

- [ ] T7. `TestMediaStore_Get_NonDestructive` in `internal/mcp/mediastore_test.go`:
  `Set`, `Get`, `Get` again — both calls return the ref; map entry is not
  deleted between calls.

- [ ] T8. `TestMediaStore_Get_Expired` in `internal/mcp/mediastore_test.go`:
  pin clock past TTL; `Get` returns nil.

- [ ] T9. `TestMediaStore_Delete` in `internal/mcp/mediastore_test.go`:
  `Set`, `Delete`, `Get` returns nil.

- [ ] T10. `TestGetMedia_ConcurrentRetryGetsInFlight` in
  `internal/mcp/tools_test.go` (or a new `media_tools_test.go`): construct a
  `Server` with a fake `ConfirmStore` and `MediaStore`; simulate two
  concurrent `toolGetMedia` calls with the same `confirmation_id` where the
  first call blocks in the download; assert the second call returns an error
  containing "download already in progress"; assert the first call eventually
  returns the download result and the confirmation entry is gone afterwards.

## Rollback

1. The change is confined to three files in `internal/mcp/` with no schema or
   API surface changes. Rolling back is a straight revert of the PR commit on
   `main`.

2. If the PR has been squash-merged, revert with:
   `git revert <merge-sha>` and open a new PR targeting `main`.

3. Since `ConfirmStore` and `MediaStore` are in-memory, a pod restart after
   rollback resets all state cleanly. No data migration is required.

4. The observable behaviour after rollback is identical to the current
   behaviour: clients retrying a slow download will again receive
   `"confirmation_id not found, expired, or already used"` on the retry.
   This is the pre-fix regression, not data loss.
