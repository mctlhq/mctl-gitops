# Tasks: incident-264ce1c0

1. [ ] In `internal/mcp/confirm.go`, verify the current `ConfirmStore.Finalize`
   implementation (added by PR #284) and add a short-lived (e.g. 30s)
   tombstone — or a retained `ConsumedAt` marker — so an already-consumed id
   can be distinguished from one that was never issued or hard-expired.
2. [ ] Add a `Claim`-path lookup for the tombstoned case and have
   `internal/mcp/media_tools.go` (`toolGetMedia`) return a distinct message,
   e.g. "confirmation_id already used — call prepare_get_media again", and
   log a distinct audit outcome instead of the generic "confirmation not
   found, expired, or already used".
3. [ ] Add/update unit tests in `internal/mcp` covering: never-issued id,
   hard-expired id (TTL/Sweep), and tombstoned/already-consumed id — each
   should produce a distinguishable error and audit log outcome.
4. [ ] Verify no behavior change to `ConfirmStore.Consume` / `MediaStore.Pop`
   (send_message, pin_message flows) — these must remain delete-on-first-touch
   and are out of scope.
5. [ ] Confirm the mctl-telegram version deployed to `labs` (currently image
   tag `0.62.2`) already includes PR #284 (merged 2026-07-15); if not, bump
   the image tag as a prerequisite so this change and the earlier fix ship
   together.
6. [ ] After deploy, watch `labs/mctl-telegram` logs/alerts for `user_id 9980`
   to confirm the new distinct error/outcome appears and the
   MctlTelegramToolAvailabilitySlowBurn alert clears; if the alert persists
   with the new "already used" outcome, escalate to a human — this indicates
   a client-side integration bug outside this fix's scope.
