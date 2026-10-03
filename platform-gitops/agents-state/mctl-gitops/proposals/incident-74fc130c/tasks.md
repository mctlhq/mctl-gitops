# Tasks: incident-74fc130c

1. [ ] If `platform-gitops/docs/runbooks/mctl-telegram-session-borrow-alerts.md`
   does not already exist (e.g. incident-4331f490's proposal has not been
   implemented yet), create it documenting: the alert pair
   (MctlTelegramSessionBorrowSlowBurn / MctlTelegramSessionBorrowFastBurn),
   the SLI they watch (mctl_sessions_borrow_total{result="error"} ratio,
   excluding TTL expirations), the candidate root cause (the
   mctl-telegram-canary Secret possibly still sharing operator identity
   210408407 with the preview deployment, causing AUTH_KEY_DUPLICATED), and
   the manual remediation step (verify/remint the Secret to tg_user_id
   924671154 per the decision already recorded in
   services/labs/mctl-telegram/values.yaml). If it already exists, treat
   this task as done — do not duplicate the file.
2. [ ] Verify the file renders as valid Markdown and links back to
   `platform-gitops/services/labs/mctl-telegram/values.yaml` and
   `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`.
3. [ ] No dependent manifest, image-tag, or alert-rule changes — this
   proposal only adds documentation. The out-of-band Secret rotation itself
   is a manual operator step, out of scope for this PR; call it out
   explicitly in the runbook as unresolved.
