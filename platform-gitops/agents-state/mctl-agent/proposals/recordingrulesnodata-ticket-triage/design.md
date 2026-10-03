# Design: recordingrulesnodata-ticket-triage

## Current state
Per `context/architecture.md`, mctl-agent runs a 3-tier skill pipeline: ticket →
evidence → skill match (ranked by confidence + circuit breaker) → diagnose → fix
→ PR → notify. `RecordingRulesNoData` is not in the "Known routed alerts" list
(neither PR-capable nor diagnose-only), so it has no builtin or YAML skill
matching it. As a generic ticket, it ranks no skill above the confidence floor,
so it falls through to the `LLMDiagnosis` builtin skill (`internal/skill/builtin/`,
per architecture.md's 9-skill list), which calls the Anthropic API to produce a
diagnosis.

Log sampling (2026-09-11, 06:37-10:32 UTC, 50-line window) shows this alert
firing at least 6 times in 4 hours on `vmalert-monitoring-victoria-metrics-k8s-stack`,
the highest-frequency alert type in the sample, mostly cooldown/flap-suppressed
at the notification layer but still generating ticket-level "no skills matched"
processing and (per the fallthrough logic) `LLMDiagnosis` invocation on each
non-suppressed occurrence. This is a recording-rule gap in the monitoring stack
itself (a VictoriaMetrics/vmalert config issue outside mctl-agent's remit), not
an actionable service incident — there is nothing for `LLMDiagnosis` to
meaningfully diagnose.

## Proposed solution
Add a single new YAML skill file under `skills/custom/` (tier 2 of the 3-tier
system, per `context/decisions/0001-three-tier-skills.md`). This is a config-only
change:

- **Match pattern:** `alertname == "RecordingRulesNoData"` AND
  `instance == "vmalert-monitoring-victoria-metrics-k8s-stack"` (or the
  team/tenant label equivalent, e.g. `tenant == "monitoring"` +
  `job == "vmalert-monitoring-victoria-metrics-k8s-stack"` — exact label
  selection to be confirmed against the live alert payload during
  implementation).
- **Confidence:** set high enough to outrank the fallthrough-to-`LLMDiagnosis`
  path, but the skill only fires on this specific alertname+instance pair, so
  it cannot shadow any other alert type's routing.
- **Action:** annotate the ticket with a fixed "known recording-rule gap, no
  action" diagnosis and mark it resolved/no-op, without calling the Anthropic
  API. The ticket is still created and recorded (for audit/trend visibility);
  only the expensive diagnosis step is skipped.
- **Hot reload:** relies on the existing YAML-skill hot-reload mechanism
  (tier 2), so shipping or adjusting this pattern is a gitops PR to
  `skills/custom/`, not an mctl-agent binary release.

This uses the tier the platform already designed for exactly this situation
(per ADR 0001: "YAML = fast iteration for teams (PR in gitops, not in
mctl-agent)") and requires no new Go code, no new dependency, and no schema
migration.

## Alternatives
1. **Add `RecordingRulesNoData` to the builtin Go skill set as a 10th builtin
   skill.** Rejected: this is a single-tenant (`monitoring`), single-instance
   pattern, not a universal platform-wide remediation; ADR 0001 and
   architecture.md's "what NOT to do" guidance reserve builtin skills for
   stable, universal patterns reviewed/tested in the mctl-agent release cycle.
   A YAML skill is the intentionally lighter-weight fit and avoids a release
   cycle for what may turn out to be a temporary monitoring-stack gap.
2. **Fix flap-suppression/cooldown tuning at the AlertManager routing layer
   instead of at mctl-agent.** Rejected as the primary fix: cooldown already
   suppresses many *notifications*, but ticket-level processing and the
   fallthrough to `LLMDiagnosis` still occurs on non-suppressed occurrences;
   this does not address the actual LLM-cost/noise root cause, and
   AlertManager routing config is outside mctl-agent's repo scope.
3. **Register a remote skill (tier 3) to handle this via an external HTTP
   service.** Rejected: massive overkill for a static regex + canned-response
   pattern; remote skills are reserved for complex AI/ML or vendor-specific
   diagnosis (per ADR 0001), and introducing a new remote-skill integration
   for a no-op pattern adds operational surface area for no benefit.

## Platform impact
- **Migrations:** none. No schema change, no ticket-DB migration.
- **Backward compatibility:** fully additive. Existing alert routing for all
  other alert types is unaffected; the new pattern only intercepts one
  specific alertname+instance pair that currently has no skill match at all.
- **Resource impact (`labs`):** none. This change is scoped entirely to the
  `admins` tenant's mctl-agent ticket-processing path; it introduces no new
  dependency, no new container, and no change to `labs`-tenant workloads or
  memory footprint.
- **Resource impact (`admins`):** expected net *decrease* in Anthropic API call
  volume (fewer `LLMDiagnosis` invocations) and a small decrease in
  ticket-processing latency for this alert type; no meaningful increase in
  mctl-agent's own CPU/memory (YAML skill matching is a cheap regex check).
- **Risks and mitigations:**
  - *Risk: label selector mismatch (e.g. instance/job label spelled or scoped
    differently than assumed) causes the skill to silently never match.*
    Mitigation: validate the exact label set against a live sampled
    `RecordingRulesNoData` alert payload before merging the YAML skill (task
    1 in tasks.md), and add a test fixture from real payload data.
  - *Risk: pattern is too broad and accidentally suppresses a genuinely
    actionable `RecordingRulesNoData` alert on a different instance.*
    Mitigation: match on the specific `instance`/`job` value observed
    (`vmalert-monitoring-victoria-metrics-k8s-stack`), not a bare
    `alertname` match; any other instance falls through unchanged
    (explicit acceptance criterion in requirements.md).
  - *Risk: this masks a real, worsening monitoring-stack problem instead of
    fixing it.* Mitigation: the ticket is still created and annotated (not
    silently dropped), preserving an audit trail; this proposal explicitly
    does not claim to fix the underlying recording-rule gap (see Out of
    scope in requirements.md), only to stop paying LLM cost on a known,
    unresolvable pattern.
  - *Risk: circuit breaker interaction.* Mitigation: no circuit breaker
    threshold or logic is touched; if the YAML skill itself starts failing
    to apply (distinct from "correctly matched, no-op'd"), the existing
    circuit breaker governs re-ranking unchanged, per the platform guardrail
    against touching breaker thresholds without real prod data.
