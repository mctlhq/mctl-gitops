# Design: labs-s3-sync-silent-canary

## Current state
Per `context/architecture.md` ("State guards") and ADR-0002, each tenant's openclaw pod
runs an s3-sync sidecar/container that periodically writes auth/session state to a
per-tenant S3 bucket, and a separate Argo CronWorkflow ("s3-sync canary") independently
verifies that fresh writes are landing in that bucket. A restore-state readiness probe
on the pod itself checks the *read* path (state restored from S3 on startup) and gates
ArgoCD rollout success.

In the latest metrics pass, `mctl_get_service_logs` for `admins`/`openclaw` and
`ovk`/`openclaw` returned normal, immediate log output for the s3-sync container
(successful syncs every 1-2 minutes). The identical query against `labs`/`openclaw`
returned 0 lines for both a 1h and a 6h window. All three tenants' ArgoCD apps report
health=Healthy/syncStatus=Synced on the same image tag (`2026.7.11-beta.2`), synced
within the same minute, and `mctl_list_incidents` shows no open incidents for any
tenant — so there is no corroborating signal (yet) that `labs` state persistence has
actually failed. This is exactly the ambiguity ADR-0002 warns about: the canary's job
is to catch this class of problem, and right now we cannot tell if the canary itself
is the thing that's broken.

## Proposed solution
A time-boxed, read-only diagnostic pass, scoped to `labs` only:

1. **Confirm log query correctness.** Re-run `mctl_get_service_logs` against
   `labs`/`openclaw` with explicit container-name enumeration (list all containers in
   the pod spec, not just `s3-sync`) to rule out a container-naming mismatch (recall
   the researcher already found the service is named `openclaw`, not `mctl-openclaw`
   — the same class of naming drift could affect the s3-sync container name in `labs`
   specifically, e.g. a `labs`-only overlay).
2. **Check the s3-sync CronWorkflow directly.** Query Argo Workflows status
   (last-run timestamp, exit code, schedule) for the `labs` s3-sync CronWorkflow
   independent of pod logs — this is the authoritative signal ADR-0002 describes,
   pod logs are secondary.
3. **Cross-check S3 bucket contents for `labs`.** If tooling allows read-only
   listing of the `labs` state bucket, compare the most recent object timestamp
   against the `admins`/`ovk` buckets sampled in the same window.
4. **Sample a longer window and a different time-of-day** in case the zero-line
   result was an artifact of the specific 1h/6h windows sampled (e.g. `labs` syncs
   less frequently because it has fewer active channel sessions — it is the
   experimental tenant per `context/architecture.md`).
5. **Write up findings** as a short report (root cause + recommendation), and if a
   genuine sync gap is confirmed, open it as a tracked incident/action item rather
   than closing this proposal silently.

This stays entirely read-only/diagnostic: no config, alert-threshold, bucket, or
probe changes are made as part of this proposal, consistent with ADR-0002's explicit
"what NOT to propose" list and the effort-2 rating in the analyst's finding.

## Alternatives
- **Immediately "fix" the canary by restarting the `labs` s3-sync CronWorkflow or
  pod.** Dropped: restarting before understanding root cause risks masking a real
  problem (or, per ADR-0002's footguns list, triggering a rollout-style canary gap
  that produces false alerts) without ever explaining the original zero-log signal.
- **Treat the 0-line result as a tooling false positive and close with no action.**
  Dropped: ADR-0002 explicitly frames unexplained canary silence as the exact failure
  mode that causes silent auth loss on restart; closing without verifying the
  CronWorkflow/bucket state directly would not meet the bar the ADR sets.
- **Broaden scope to redesign canary alerting/observability for all three tenants.**
  Dropped as over-scoped for an effort-2 finding; if the root cause turns out to be a
  systemic observability gap, that becomes a follow-up proposal, not this one.

## Platform impact
- **Migrations:** none. This is a read-only investigation.
- **Backward compatibility:** not applicable — no interfaces or schemas change.
- **Resource impact (especially `labs`):** zero. No new process, sidecar, or
  configuration is added to `labs`. All checks are external (log queries, Argo
  Workflows status, S3 listing) and add no footprint to the running pod.
- **Risks and mitigations:**
  - *Risk:* the investigation confirms a real sync gap in `labs` and there is a
    delay before it is triaged, during which a `labs` restart could lose auth.
    *Mitigation:* per the acceptance criteria, any confirmed genuine gap must be
    raised as a tracked incident/action item immediately, not deferred to a future
    inbox cycle.
  - *Risk:* diagnostic queries against Argo Workflows/S3 require elevated
    read permissions not currently exercised by this agent's tooling.
    *Mitigation:* if such access is unavailable, the task falls back to documenting
    the gap and explicitly recommending which team/role should run the remaining
    checks, rather than silently skipping them.
