# Tasks: incident-4331f490

1. [ ] Create `platform-gitops/docs/runbooks/mctl-telegram-session-borrow-alerts.md`
   documenting: the alert pair (MctlTelegramSessionBorrowSlowBurn /
   MctlTelegramSessionBorrowFastBurn), the SLI they watch
   (mctl_sessions_borrow_total{result="error"} ratio, excluding TTL
   expirations), the candidate root cause (the mctl-telegram-canary Secret
   possibly still sharing operator identity 210408407 with the preview
   deployment, causing AUTH_KEY_DUPLICATED), and the manual remediation step
   (verify/remint the Secret to tg_user_id 924671154 per the decision already
   recorded in services/labs/mctl-telegram/values.yaml).
2. [ ] Verify the new file renders as valid Markdown and links back to
   `platform-gitops/services/labs/mctl-telegram/values.yaml` and
   `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`
   so a future on-call can find the source comments this diagnosis is based
   on.
3. [ ] No dependent manifest, image-tag, or alert-rule changes — this
   proposal only adds documentation. The out-of-band Secret rotation itself
   is a manual operator step, out of scope for this PR; call it out
   explicitly in the runbook as unresolved.
