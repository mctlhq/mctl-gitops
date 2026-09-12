# Tasks: recordingrulesnodata-ticket-triage

- [ ] 1. Capture and validate the exact label set of a live `RecordingRulesNoData`
      alert on `vmalert-monitoring-victoria-metrics-k8s-stack` (alertname,
      instance/job, tenant labels) from recent AlertManager payloads or logs.
      — DoD: a sample payload/fixture is saved (e.g. under a test-fixtures
      location) confirming the exact field names and values to match on.
- [ ] 2. Author the YAML skill file under `skills/custom/` matching on the
      validated alertname + instance/job pattern, with a canned
      "known recording-rule gap, no action" diagnosis template and no
      LLM-invocation step (depends on 1) — DoD: YAML skill file is written,
      lints/validates against the existing YAML-skill schema used by the
      hot-reload loader, and matches only the intended alertname+instance
      pair (not a bare alertname match).
- [ ] 3. Verify hot-reload picks up the new skill without a service restart in
      a non-prod/staging check (depends on 2) — DoD: skill appears in
      `GET /api/v1/skills` (or equivalent) after dropping the file in place,
      with no mctl-agent restart.
- [ ] 4. Confirm ranking/confidence configuration causes this skill to win
      over the fallthrough-to-`LLMDiagnosis` path for matching tickets, while
      leaving all other alert types' ranking unaffected (depends on 2) — DoD:
      a matching ticket is skill-matched by the new YAML skill and does not
      trigger an Anthropic API call; a non-matching `RecordingRulesNoData`
      ticket (different instance) still falls through to `LLMDiagnosis`
      unchanged.
- [ ] 5. Confirm the ticket record is still created/audit-visible (not
      silently dropped) when the new skill matches (depends on 2) — DoD:
      ticket appears in `GET /api/v1/tickets` with the canned diagnosis
      annotation and a resolved/no-op status.
- [ ] 6. Deploy via gitops PR to the environment holding `skills/custom/`
      (depends on 2, 3, 4, 5) — DoD: PR merged, skill live in `admins` tenant,
      no `labs`-tenant change involved.
- [ ] 7. Monitor for one full day-cycle post-deploy to confirm the intended
      drop in `LLMDiagnosis` invocation volume for this alert type (depends
      on 6) — DoD: next day's mctl metrics/log sample shows
      `RecordingRulesNoData` on this instance no longer reaching
      `LLMDiagnosis`, with ticket volume/audit trail intact.

## Tests
- [ ] T1. Unit/fixture test: given the captured sample payload (task 1), the
      YAML skill matcher returns a match with the expected confidence.
- [ ] T2. Negative test: a `RecordingRulesNoData` alert with a different
      `instance`/`job` value does NOT match the new skill and falls through
      to normal ranking (including potential `LLMDiagnosis`).
- [ ] T3. Negative test: alerts of other alertnames (e.g.
      `CPUThrottlingHigh`, `PodCrashLooping`) are unaffected by the new
      skill's presence — no change in their existing routing/skill match.
- [ ] T4. Integration test: end-to-end ticket creation for a matching alert
      confirms no Anthropic API call is made and the ticket is
      created/resolved with the canned diagnosis.
- [ ] T5. Hot-reload test: adding/removing the YAML skill file at runtime
      changes matching behavior without a service restart.
- [ ] T6. Circuit-breaker non-interference test: confirm no change to circuit
      breaker thresholds/state as a result of this skill's normal (matching)
      operation.

## Rollback
Remove (or revert, via gitops) the YAML skill file under `skills/custom/`.
Because this is a hot-reload tier-2 skill with no schema migration, no builtin
Go code change, and no circuit-breaker/config change, rollback is a single
file removal that takes effect without an mctl-agent restart or redeploy of
the binary. Tickets already created/resolved by the skill while it was active
are left as-is (historical record); no data cleanup is required. If rollback
is needed, `RecordingRulesNoData` alerts on this instance simply revert to
falling through to `LLMDiagnosis` as before this change.
