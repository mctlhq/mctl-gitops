# Design: ovk-empty-logs-pod-health-investigation

## Current state
`ovk` is the production, high-SLA tenant for which ADR-0002 exists precisely
to prevent silent auth/session loss (S3-backed state + s3-sync canary +
restore-state probe). Per `context/architecture.md`, `ovk` changes only
after a run-through in `labs`, and restarts are explicitly called out as
painful. This week's `mctl` metrics show `ovk` at 0 log lines (6h window),
1/5 pods used, ~17% memory utilization — unchanged from the post-drop
snapshot reported last week — with 0 active incidents. A sibling proposal,
`ovk-s3-sync-canary-and-pod-health-investigation`, already exists from an
earlier pass covering a related signal set (1h-window s3-sync silence,
ArgoCD `OutOfSync` drift, a sharper resource drop). See
`context/architecture.md` and `context/decisions/0002-s3-state-with-canary-and-probe.md`
for the guardrails this investigation must respect.

## Proposed solution
A read-only, two-step diagnostic:

1. **Reuse-first check.** Before any new investigation work, check whether
   the sibling proposal already produced a finding. If it did and the
   finding still applies (e.g. "confirmed benign, low traffic period"), this
   proposal simply re-confirms the finding still holds after a second week
   and closes. If the sibling investigation is still open or the finding is
   stale, proceed to step 2.
2. **Direct verification.** Independently confirm (a) actual pod
   running/ready/restart-count state via Kubernetes/ArgoCD (not just mctl
   log/metric proxies), (b) whether the s3-sync CronWorkflow for `ovk` is
   executing and simply producing no fresh-timestamp output vs. not running
   at all, and (c) whether ArgoCD's sync status for `ovk-openclaw` shows any
   live-vs-desired manifest drift. Produce a single written finding covering
   both this week's and the sibling's open questions, and escalate to a
   formal incident only if a real problem is confirmed.

## Alternatives
- **Restart the `ovk` pod to "see if it comes back healthy."** Rejected
  outright — explicitly disallowed per `context/architecture.md` ("do not
  propose restarts of `ovk` without a clear justification") until a
  confirmed root cause exists.
- **Treat this as a brand-new investigation, ignoring the sibling
  proposal.** Rejected — would duplicate diagnostic effort and risk two
  investigations reaching different conclusions about the same tenant in
  the same time window.
- **Wait for a third consecutive week before investigating.** Rejected —
  `ovk`'s high-SLA status and the total absence of a raised incident despite
  two weeks of the same anomaly means the detection gap itself is already
  worth understanding now, independent of whether the underlying pod state
  turns out to be benign.

## Platform impact
- **Migrations:** none — read-only investigation.
- **Backward compatibility:** not applicable.
- **Resource impact (`labs`):** none — this proposal does not touch `labs`
  or add any workload; purely diagnostic against `ovk`.
- **Risks and mitigations:**
  - Risk: investigation activity is mistaken for or drifts into a live
    change against `ovk` → Mitigation: every acceptance criterion above is
    explicitly read-only; any remediation is a separate, follow-up proposal.
  - Risk: duplicated effort/conflicting conclusions vs. the sibling
    proposal → Mitigation: mandatory reuse-first step before new
    investigation work begins.
  - Risk: alerting-gap goes unaddressed if closed as "benign" prematurely →
    Mitigation: the written finding must explicitly state whether alerting
    *should* have fired, feeding a possible follow-up alerting-gap fix
    proposal regardless of root cause.
