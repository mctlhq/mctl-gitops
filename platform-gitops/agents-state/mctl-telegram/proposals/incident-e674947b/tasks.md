# Tasks: incident-e674947b

1. [ ] In mctl-telegram, find the session pool's `Borrow()` implementation
   (the code path that increments `mctl_sessions_borrow_total{result=...}`,
   registered in `internal/metrics/metrics.go` per
   `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
   lines 35-36) and add a `slog`/logger call at WARN level on every
   `result="error"` outcome (i.e. excluding `expired_idle` and
   `expired_absolute`), including the account/`tg_user_id` and the
   underlying error text (so an `AUTH_KEY_DUPLICATED` failure is
   distinguishable from any other borrow error).
2. [ ] Verify the change compiles and existing session-pool tests still pass;
   add/update a unit test asserting the WARN log fires on a simulated
   borrow error and does NOT fire on `expired_idle`/`expired_absolute`.
3. [ ] Bump the mctl-telegram image tag used by
   `platform-gitops/services/labs/mctl-telegram/values.yaml` (`image.tag`,
   currently `0.71.0`) once the fix is released, so the WARN logging reaches
   production. Do this as a follow-up PR after the code change merges and a
   new version is tagged/built — do not bundle an image-tag bump with the
   code PR.
4. [ ] After the new logging is live, re-observe: if a subsequent
   `MctlTelegramSessionBorrowSlowBurn` (or the paging
   `MctlTelegramSessionBorrowFastBurn`) fires, check the new WARN logs for
   `AUTH_KEY_DUPLICATED`. If confirmed, open a follow-up issue to implement
   session exclusivity between the stable (`tg.mctl.ai`) and preview
   (`tg-preview.mctl.ai`) deployments for the operator account (210408407) —
   this is intentionally NOT implemented by this proposal (see design.md
   Scope).
