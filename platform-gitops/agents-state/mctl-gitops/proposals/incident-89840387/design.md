# Design: incident-89840387

## Diagnosis
The shepherd's `post-deploy-verify` step, defined in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`, lists ALL
ArgoCD Applications in the `argocd` namespace (`kubectl get applications.argoproj.io -n argocd`)
and fails the whole workflow if ANY Application transitioned to `Health=Degraded` after the
workflow started and is still Degraded after a 120s grace period — with no scoping to the
service/repo this particular shepherd tick actually touched. In this run, `run-shepherd` found
"no implemented/review-fixing proposals with a PR found" for mctl-agents (i.e. it changed
nothing), yet the workflow still failed because the unrelated Application
`argocd/labs-agent-worker-preview` (team `labs`, a preview environment) flipped to Degraded during
the 300s+120s verify window and had not recovered. `mctl_get_service_status` for `labs/agent-worker-preview`
still reports `Degraded` an hour later, while its own pod logs show `agent-worker` jobs completing
successfully throughout — evidence this is a flaky/false-positive health signal on an ephemeral
preview app, not an outage this shepherd tick caused or could have caused.

Because the safeguard is unscoped, any Application anywhere in the `argocd` namespace becoming
newly Degraded during any shepherd tick's ~7-minute verify window fails that tick, regardless of
which service/proposal it was advancing. This is why two unrelated mctl-agents proposals
(`issue-305-...` and `issue-364-...`, ticks 23 seconds apart) both failed with the identical
`post-deploy-verify flagged: argocd/labs-agent-worker-preview` reason — neither tick's own work was
at fault.

No skill matched this incident (analysis field empty), which is expected: this is a workflow/gitops
configuration bug, not a service runtime fault a skill would recognize.

## Proposed Fix
In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`, in the
`post-deploy-verify` template's script, exclude preview-environment Applications (name suffix
`-preview`, per the platform's preview-naming convention — see `mctl_create_preview` /
`{app}-{preview_id}` and existing apps like `labs-agent-worker-preview`,
`labs-telegram-preview`) from the newly-Degraded check, since these are ephemeral, TTL'd
environments expected to flap independently of any shepherd merge:

- Current (initial check, ~line 1119-1125):
  ```
  BAD=$(printf '%s' "$RAW" | jq -r --arg ts "$THRESHOLD" '
    ($ts | fromdateiso8601) as $threshold
    | .items[]
    | select(.status.health.status == "Degraded")
    | select(((.status.health.lastTransitionTime // "1970-01-01T00:00:00Z") | fromdateiso8601) > $threshold)
    | "\(.metadata.namespace)/\(.metadata.name)"
  ' | tr '\n' ' ')
  ```
  New: add `| select((.metadata.name | endswith("-preview")) | not)` immediately after the
  `select(.status.health.status == "Degraded")` line.

- Current (post-grace recheck, ~line 1133-1139): same addition to the `BAD2` jq pipeline.

Do NOT change the unfiltered snapshot (`degraded_unfiltered.txt`, ~line 1161-1165) — that list is
used by onExit for a different purpose (deciding whether it's safe to resolve the shepherd
fingerprint) and should keep seeing preview apps.

## Scope
Minimal. Only touch the two jq filter pipelines (`BAD` and `BAD2`) inside the `post-deploy-verify`
template of this one ClusterWorkflowTemplate. Does not change the safeguard's behavior for
non-preview (production) Applications, and does not touch `degraded_unfiltered.txt`.

## Confidence: MEDIUM
Diagnosis is based on the actual step logs and the current file content read at diagnosis time, but
the implementer should confirm line numbers/exact surrounding context still match before editing,
and confirm no other consumer relies on preview apps being included in the filtered `BAD`/`BAD2`
lists.
