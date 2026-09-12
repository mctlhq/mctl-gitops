# Suppress/route the high-frequency unmatched RecordingRulesNoData alert

## Context
Log sampling on 2026-09-11 (06:37-10:32 UTC, a single 4-hour window) shows the
`RecordingRulesNoData` alert firing on `vmalert-monitoring-victoria-metrics-k8s-stack`
at least 6 times — the highest-frequency alert type observed in the 24h sample and
well above the volume of any other alert type in the same log window. This alert is
not present in the routed-alert list in `context/architecture.md` (neither
PR-capable nor diagnose-only), so every occurrence becomes a generic ticket, no
builtin or YAML skill matches it ("no skills matched ticket"), and per the 3-tier
skill pipeline (`context/decisions/0001-three-tier-skills.md`) it falls through to
the `LLMDiagnosis` builtin skill.

This is a structurally unresolvable, recurring no-op alert (a monitoring-stack
recording-rule gap, not an actionable service incident), yet it is currently paying
the full cost of an LLM diagnosis call on every occurrence. The YAML-skill tier
exists precisely for this kind of fast, team-owned, hot-reload pattern match — a
regex on alertname + instance that lets us either auto-resolve the ticket with a
canned "known recording-rule gap, no action" response, or route it to a
`RecordingRulesNoData` diagnose-only handler, without touching builtin skills, the
circuit breaker, or any Go code.

## User stories
- AS an on-call engineer I WANT the recurring `RecordingRulesNoData` alert on
  `vmalert-monitoring-victoria-metrics-k8s-stack` to stop generating noisy,
  LLM-diagnosed tickets SO THAT I am not distracted by a structurally
  unresolvable, non-actionable alert and Claude API spend is not wasted on it.
- AS the mctl-agent owner I WANT a YAML skill (not a builtin Go skill) to handle
  this pattern SO THAT the fix ships as a config-only, hot-reload change with no
  binary release, no new dependency, and no risk to the circuit breaker or other
  skill tiers.
- AS a platform operator I WANT the ticket still to be recorded (not silently
  dropped) SO THAT there is an audit trail if the underlying recording-rule gap
  ever needs real investigation.

## Acceptance criteria (EARS)
- WHEN an AlertManager alert with `alertname=RecordingRulesNoData` and
  `instance` matching `vmalert-monitoring-victoria-metrics-k8s-stack` arrives,
  THE SYSTEM SHALL match it via a YAML skill in `skills/custom/` before it
  falls through to `LLMDiagnosis`.
- WHEN the YAML skill matches such an alert, THE SYSTEM SHALL create (or
  update, if flap-suppression applies) a ticket annotated with a canned
  "known recording-rule gap, no action required" diagnosis, without invoking
  the Claude API.
- WHILE the YAML skill is active, THE SYSTEM SHALL NOT invoke `LLMDiagnosis`
  for any ticket that the YAML skill matched with sufficient confidence.
- IF the alert's `instance` label does not match the configured pattern (i.e.
  it is a `RecordingRulesNoData` alert on a different target), THEN THE
  SYSTEM SHALL fall through to normal skill ranking (including
  `LLMDiagnosis`) unchanged.
- WHEN the YAML skill is hot-reloaded (added, edited, or removed under
  `skills/custom/`), THE SYSTEM SHALL pick up the change without a service
  restart, consistent with the existing YAML-skill tier behavior.
- IF the YAML skill repeatedly fails to apply its remediation template (skill
  execution errors, not "correctly matched and no-op'd"), THEN THE SYSTEM
  SHALL let the existing circuit breaker govern re-ranking exactly as it does
  for any other skill — this proposal SHALL NOT modify circuit breaker
  thresholds or logic.

## Out of scope
- Any change to circuit breaker thresholds or logic.
- Any change to builtin Go skills or the `LLMDiagnosis` skill itself.
- Fixing the underlying recording-rule gap in the monitoring stack (that is a
  `monitoring` tenant / VictoriaMetrics-stack config concern, not an
  `mctl-agent` concern).
- Adding `RecordingRulesNoData` to the routed-alert list in
  `context/architecture.md` as PR-capable or diagnose-only — it remains
  explicitly a "recognize and no-op" pattern, not a remediation target.
- Handling `RecordingRulesNoData` alerts on any instance other than
  `vmalert-monitoring-victoria-metrics-k8s-stack` (out of scope unless a
  future signal shows the same pattern elsewhere).
- Any change affecting the `labs` tenant or its resource usage.
