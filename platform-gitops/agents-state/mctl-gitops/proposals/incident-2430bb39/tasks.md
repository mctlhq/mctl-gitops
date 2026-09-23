# Tasks: incident-2430bb39

1. [ ] Edit `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml`:
   in the `mctl-telegram-slo-burn` group, `MctlTelegramSessionBorrowSlowBurn`
   alert, append the "Known contributing risk" sentence (see design.md) to the
   `annotations.description` block scalar. Do not change the `expr`, `for`,
   `labels`, or `summary` fields, and do not touch any other alert in this
   file.
2. [ ] Verify the file still parses as valid YAML and the VMRule's `expr` for
   every alert is byte-identical to before the edit (only the one
   `description` string should differ in the diff).
3. [ ] No dependent changes (no image tag bump, no other file touched). Note
   in the PR description that the actual suspected root cause — the
   out-of-band `mctl-telegram-canary` Secret's identity — is outside gitops
   and requires a human to check/rotate it directly in Vault/Kubernetes; this
   PR only documents the lead on the alert for whoever picks up the
   reliability ticket.
