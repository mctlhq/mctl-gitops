# get_media: defer confirmation/media-ref teardown until download completes

## Context

`get_media` is the second step of a two-step download flow. The first step,
`prepare_get_media`, issues a short-lived `confirmation_id` and caches a
`MediaDownloadRef` (containing the Telegram file location internals) keyed by
that ID. The second step, `get_media`, is expected to consume both in a
single shot, run the actual download, and return base64-encoded bytes.

Currently, both the confirmation row and the media ref are deleted at the very
start of `get_media` — before the 60-second-bounded `telegram.DownloadMedia`
call begins. Large files (5 MB and above) can take longer than the caller's
transport-layer timeout. When the transport gives up and retries the same
`get_media` call with the same `confirmation_id`, the retry's validation step
finds the confirmation row already gone and returns the misleading error
"confirmation_id not found, expired, or already used." The download may still
be running (or may have silently succeeded) on the server side. Reproduced
deterministically against `tg-preview.mctl.ai` for files of 7.5 MB and above
(issue #282).

## User stories

- AS an MCP client I WANT a retry of `get_media` during a slow download to
  receive an unambiguous "download already in progress" response SO THAT I
  can wait and retry later rather than being misled into thinking the
  confirmation was invalid.

- AS an operator I WANT audit logs to clearly distinguish "confirmation
  consumed and download in progress" from "confirmation not found or expired"
  SO THAT I can diagnose client timeout problems without false-positive alerts
  on invalid confirmation IDs.

- AS a developer I WANT the send/pin confirmation flow to be unaffected by
  this change SO THAT existing two-step destructive-action flows keep their
  strict single-shot, delete-on-first-touch semantics.

## Acceptance criteria (EARS)

- WHEN `get_media` is called with a valid `confirmation_id` that has not yet
  been claimed, THE SYSTEM SHALL mark that confirmation as in-flight (without
  deleting it) and proceed with the download.

- WHILE a `get_media` download is in progress under a given `confirmation_id`,
  THE SYSTEM SHALL return an error response with message
  "download already in progress for this confirmation_id — retry shortly" to
  any concurrent or subsequent call presenting the same `confirmation_id`.

- WHEN a `get_media` download completes (successfully or with a terminal
  error), THE SYSTEM SHALL delete both the confirmation row and the
  `MediaDownloadRef` entry, releasing the in-flight lock.

- WHEN `get_media` is called with a `confirmation_id` whose download has
  already completed and the entry is gone, THE SYSTEM SHALL return
  "confirmation_id not found, expired, or already used" (unchanged behaviour,
  same as today for a replayed or truly-expired ID).

- WHEN `get_media` is called with a `confirmation_id` that belongs to a
  different user or was issued for a different (peer, message_id) payload,
  THE SYSTEM SHALL reject the call with the existing mismatch/wrong-user
  errors (unchanged behaviour).

- WHILE a confirmation is marked in-flight, THE SYSTEM SHALL NOT prevent
  `ConfirmStore.Sweep` from removing it once its `ExpiresAt` wall-clock time
  has passed (the 10-minute TTL remains the hard backstop).

- WHEN a `confirm_message` or `pin_message` call invokes `ConfirmStore.Consume`
  (the existing send/pin flow), THE SYSTEM SHALL continue to delete the
  confirmation row immediately (no change to those flows).

- IF the `get_media` handler context is cancelled before or during the
  download, THE SYSTEM SHALL still invoke the Finalize and Delete cleanup
  steps so that the confirmation and media ref are removed and the in-flight
  state does not persist beyond the request lifetime.

## Out of scope

- Result caching: caching the downloaded bytes so that a post-completion retry
  can replay the result without re-downloading. The fix targets the in-flight
  window only; post-completion retries must call `prepare_get_media` again.

- Multi-pod in-flight coordination: `ConfirmStore` and `MediaStore` are
  in-memory per-pod by design. Cross-pod retries are not addressed here.

- Increasing the 60-second `DownloadMedia` context timeout. That is a
  separate performance concern.

- Changes to `prepare_get_media` behaviour, TTL values, or the confirmation
  ID generation scheme.

- Changes to the send/pin confirmation flow (`ConfirmStore.Consume`).

## Open questions

1. Should a retry that arrives after the in-flight download has failed (and
   the entry is therefore gone) receive a distinct "download failed, re-prepare"
   error rather than the generic "not found" error? The issue does not specify;
   this proposal treats post-failure retries the same as truly-expired IDs
   (client must call `prepare_get_media` again).

2. Should the `ConfirmStore.Sweep` goroutine (if one is added in future) skip
   in-flight entries that are not yet expired, or should it use `ExpiresAt`
   as the sole eviction criterion? This proposal uses `ExpiresAt` only (the
   60 s download timeout is well within the 10-minute TTL).

3. Should the new `ErrConfirmationInFlight` error be surfaced in the audit log
   as a warning rather than an error, given it is an expected transient state?
   This proposal logs it at `slog.Warn` level for operator visibility.
