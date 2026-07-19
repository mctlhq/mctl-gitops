# Design: incident-argo-id-slug-collision

## Confidence: LOW (verify against the actual mctl-agents source before
applying — the root cause is corroborated by a reproduced collision artifact
already sitting in this repo, but the exact function/line to patch was not
directly inspected, since the mctl-agents Python source is not checked out
in this environment; only mctl-gitops is)

## Diagnosis
The incident-responder writes each proposal to
`agents-state/{target_service}/proposals/incident-{incident_id[:8]}/`,
matching the "slug: incident- + first 8 characters of the incident ID" rule
documented in CLAUDE.md and in cronworkflow-mctl-agents-incidents.yaml.

For incidents whose `source` is `argo-workflows` (self-reported CronWorkflow
failures posted by the `notify-telegram` onExit step in
cwft-mctl-agents-run.yaml, see lines 411-446 of that file), the incident `id`
is built as `argo-${WORKFLOW_NAME}-$(date +%s)`, e.g.
`argo-mctl-agents-incidents-1784483100-1784483248` or
`argo-mctl-agents-implement-1784072700-1784073633`. Every such ID starts with
the literal 8-character substring `argo-mct`, because `WORKFLOW_NAME` always
begins with the fixed prefix `mctl-`. So `incident_id[:8]` is not a useful
discriminator for this incident source at all — it collapses every
argo-workflows-sourced incident, regardless of which pipeline, timestamp, or
failure, onto the identical proposal slug `incident-argo-mct`.

This is not hypothetical: `agents-state/mctl-gitops/proposals/incident-argo-mct/`
already exists on disk, created 2026-07-17 for a completely different
incident (an `mctl-agents-implement` failure), and is still
`status: in-progress`. Every subsequent incident-responder tick that
encounters an argo-workflows-typed incident (which is common, since the
pipeline reports its own failures back as incidents) resolves to that same
already-occupied path. Depending on how the orchestrator's write-proposal
step handles an existing, non-matching directory (overwrite / hard-fail /
directory-exists exception), this plausibly explains why the
`incident-responder` CronWorkflow has failed on every single tick since at
least 2026-07-18T13:24 (argo-mctl-agents-run-f868212c-1784381073 through
argo-mctl-agents-incidents-1784484900-1784485053 — 7-8 consecutive failures,
zero successes) while the `implement` pipeline, which does not process
argo-workflows-typed incidents and shares the same mutex / OAuth-fallback
machinery, has continued to succeed on schedule in the same window. That
rules out shared-infrastructure contention (mutex wait, OAuth quota) as the
sole explanation, since it would affect both pipelines equally, and it does
not.

## Proposed Fix
In the mctl-agents Python orchestrator's incident-responder module (look for
the proposal-path / slug construction, likely something like
`slug = f"incident-{incident_id[:8]}"` in `orchestrator/incident_responder.py`
or `orchestrator/run_all.py`), change the slug derivation to be
collision-resistant regardless of incident-ID scheme:

- Current (inferred): `slug = "incident-" + incident_id[:8]`
- New (recommended): `slug = "incident-" + hashlib.sha1(incident_id.encode()).hexdigest()[:8]`
  — a one-line change, no per-source special-casing needed, works for both
  UUID-style and `argo-...-<ts>-<ts>`-style IDs, and preserves the existing
  "8 hex-ish characters" slug convention.
- Alternative: special-case `source == "argo-workflows"` and slug from the
  trailing unique timestamp instead of a prefix slice
  (`incident_id.rsplit("-", 1)[-1]`).

Additionally, treat "proposal directory already exists AND its
requirements.md incident ID differs from the incident being processed" as a
recoverable condition (log a warning and pick a disambiguated slug, e.g.
append `-2`) rather than letting it propagate into whatever failure currently
wedges the CronWorkflow — this makes any future collision, from any cause,
degrade gracefully instead of hard-failing every subsequent tick.

## Scope
Two minimal changes, both in the mctl-agents repo:
1. Fix the slug-derivation function.
2. Add the defensive existing-directory-for-a-different-incident check
   before write.

Do not touch the pre-existing `agents-state/mctl-gitops/proposals/incident-argo-mct/`
proposal as part of this change — it belongs to a separate, still
`in-progress` incident and must not be overwritten or reinterpreted.
