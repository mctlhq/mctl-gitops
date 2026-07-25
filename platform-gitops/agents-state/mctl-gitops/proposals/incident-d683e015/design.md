# Design: incident-d683e015

## Confidence: LOW

No Loki logs and no Argo workflow audit record exist for this specific run
(see Evidence in requirements.md), so the exact exception/exit code that
killed this run cannot be observed directly. This design is built from
direct inspection of the current `mctl-agents` orchestrator source and the
current `cwft-mctl-agents-run.yaml` / `cwft-mctl-agents-implement.yaml`
manifests in this checkout (not from stale duration-signature matching
against older incidents), but it remains a plausible-cause proposal, not a
confirmed root cause. The implementer should treat this as one safe,
additive mitigation, not the final word.

## Diagnosis

This is the 6th consecutive failure of the `mctl-agents-incidents` CronWorkflow
tick (`15,45 * * * *`) since the cron was un-suspended today
(2026-07-25T03:00:00Z spend-cap reset, per the CronWorkflow's own
`suspend: false` annotation). Every tick since reactivation has failed
(04:51, ~05:21, ~05:51, ~06:21, ~06:51, 07:17 — matching the fingerprint's
occurrence_count: 6), each around the same ~5-6 minute mark (this one:
327.7s).

This same recurring incident class (source=argo-workflows,
type=workflow_failed, service=mctl-agents) already has an extensive paper
trail in this proposals directory —
`incident-mctl-agents-oauth-quota-exhaustion` (implemented, PR #595),
`incident-argo-mct` (in-progress), and several
`incident-agents-incidents-<epoch>` duplicates from 2026-07-19/20 — all
converging on Claude OAuth token exhaustion (`claude-code-oauth-token` /
`claude-code-oauth-token-2` in Vault at `secret/platform/mctl-agents`) as
the most likely root cause of this whole failure class. That credential
problem is NOT fixable via a GitOps PR (it needs an out-of-band Vault
reseed) and is out of scope here — do not re-attempt that fix in this
proposal.

What none of those prior duplicate analyses inspected is the orchestrator's
own budget configuration, which is directly readable from this checkout's
sibling `mctl-agents` source (`/app/orchestrator/options.py`,
`/app/orchestrator/run_incident_responder.py`):

- `orchestrator/options.py:66` — `INCIDENT_RESPONDER_BUDGET_USD = float(os.getenv("INCIDENT_RESPONDER_BUDGET_USD", "5.00"))`
- `orchestrator/options.py:188` — `build_incident_responder_options(...)` passes this as `max_budget_usd` to the SDK, so the run raises `error_max_budget_usd` and aborts once $5.00 of API spend is reached.
- `cwft-mctl-agents-run.yaml`'s `run-orchestrator` template env block (lines
  194-246) sets `SERVICE_AGENT_BUDGET_USD` and `MENTOR_BUDGET_USD` as
  explicit overrides, but never sets `INCIDENT_RESPONDER_BUDGET_USD` — so
  every incident-responder run is capped at the $5.00 code default with no
  way to raise it short of editing this file.

$5.00 is a plausible cap to blow through in ~5 minutes specifically for
*this* incident class, because incidents about `mctl-agents` itself have no
Loki logs to ground a diagnosis in (confirmed empty again for this run —
see Evidence). That forces the sub-agent into wider exploration (reading
workflow YAML, orchestrator source, prior duplicate proposals — exactly the
work this triage session had to do) instead of the cheap
get_incident -> get_service_logs -> write path a normal tenant-service
incident takes. This mirrors a problem this same file already hit and fixed
once before for the sibling implementer pipeline: `IMPLEMENTER_BUDGET_USD`
in `cwft-mctl-agents-implement.yaml` was raised 3.00 -> 10.00 -> 20.00 after
real runs kept hitting `error_max_budget_usd` on harder-than-average
targets (see that file's inline history comments). The incident-responder
budget was never given the same treatment.

This is offered as an additive, low-risk mitigation alongside the
already-tracked credential-exhaustion theory, not a replacement for it — if
the true cause is token exhaustion, this change is harmless (a higher cap
on a run that fails at SDK auth before spending anything is a no-op); if
the true cause is budget exhaustion during self-diagnosis of an
unusually-hard incident, this directly fixes it.

## Proposed Fix

File: `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-run.yaml`

In the `run-orchestrator` template's `env:` list, immediately after the
existing `MENTOR_BUDGET_USD` entry (current line 245-246):

Current:
```yaml
          - name: MENTOR_BUDGET_USD
            value: "10.00"
```

New (add a new entry directly after it):
```yaml
          - name: MENTOR_BUDGET_USD
            value: "10.00"
          # Raised from the orchestrator's $5.00 code default
          # (orchestrator/options.py INCIDENT_RESPONDER_BUDGET_USD) to match
          # IMPLEMENTER_BUDGET_USD's precedent (cwft-mctl-agents-implement.yaml).
          # Incidents about mctl-agents itself have no Loki logs (service runs
          # as ephemeral Argo pods, not a persistent Deployment), forcing the
          # responder into wider exploration than a normal tenant-service
          # incident and making the $5 default easy to exhaust mid-diagnosis.
          # See mctl-gitops/proposals/incident-d683e015 (Confidence: LOW —
          # OAuth token exhaustion, tracked separately in
          # incident-mctl-agents-oauth-quota-exhaustion, remains the more
          # likely root cause for this failure class as a whole).
          - name: INCIDENT_RESPONDER_BUDGET_USD
            value: "20.00"
```

## Scope

Minimal. One new env var on one container template, mirroring the exact
pattern already used for `SERVICE_AGENT_BUDGET_USD` / `MENTOR_BUDGET_USD` in
the same file and `IMPLEMENTER_BUDGET_USD` in the sibling implement
template. Does not touch the shared `mctl-gitops-main-writes` mutex, the
CronWorkflow schedule, `activeDeadlineSeconds`, or any OAuth/credential
logic — those are out of scope and, per
`incident-mctl-agents-oauth-quota-exhaustion`, the credential problem
specifically requires an out-of-band Vault reseed, not a gitops change.
