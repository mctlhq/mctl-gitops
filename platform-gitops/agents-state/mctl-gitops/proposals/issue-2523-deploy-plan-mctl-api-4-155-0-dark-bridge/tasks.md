# Tasks: issue-2523-deploy-plan-mctl-api-4-155-0-dark-bridge

- [ ] 1. Write `docs/runbooks/mctl-api-4.155.0-dark-rollout.md`. It contains the decision gate (default
  `BLOCKED_RELEASE_HOLD`), the evidence table E1-E11, the release STOP conditions, the post-deploy checks
  P1-P6, and the E5-dependent rollback branches described in design.md. — DoD: every field links its source
  issue or PR; the gate value is BLOCKED; the doc says explicitly that READY is not approval and that
  `release-deploy.yaml` must not be used for this bump.
- [ ] 2. Add a pointer line in `CLAUDE.md` under "Secrets Management" / runbooks, next to the other runbook
  pointers (depends on 1). — DoD: one line referencing the new runbook.
## Future work — separate implementation approvals, NOT this docs-only slice

- [ ] F1. Prepare a separate, owner-approved DevLoop implementation for fail-closed
  release/deployment enforcement on all write paths, including *direct-main* writes
  through `release-deploy.yaml` / `gitops-bump.yaml`. A PR-only validation
  test is insufficient. Prove negative bypass and missing/unknown-hold denial.
  Nothing in F1 is authorised by this documentation proposal.
- [ ] F2. Only after explicit #934 owner GO, Part M/Part S compatibility,
  B4/drain dispositions, verified 4.155.0 release digest/provenance and F1 enforcement:
  open a separate, independently reviewed one-line tag bump PR, with Helm render
  evidence. Never bypass owner approval via direct-main automation.
- [ ] F3. Only after F2 is independently approved and deployed, run P1–P6 and record
  the actually running digest, healthy pods, negative Bridge smoke and Temporal
  history safety. Provider credentials and Bridge activation remain OFF.

## Future verification (not executed under docs-only scope)

- [ ] T1. An independently approved dark-Bridge guard passes on the unmodified
  GitOps config and is proved effective for *direct-main* release workflow writes,
  not just PR checks.
- [ ] T2. The test fails for each fixture variant: `MCTL_BRIDGE_ENABLED: "true"`, the presence of
  `MCTL_BRIDGE_PROVIDERS`, the presence of `MCTL_BRIDGE_PROVIDER_TOKENS`,
  `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE: "true"`, and an `envFromExtraSecret` naming `bridge`.
- [ ] T3. When it is eventually run: `helm template mctl-api <mctl-api repo>/helm` at E10 with the inline values,
  for both 4.154.0 and 4.155.0. The only image difference should be the container image reference; chart drift at `main` also requires independent verification.
- [ ] T4. Post-deploy (separate GO): P3, the negative Bridge smoke. Bridge routes are not served, and the logs show no
  dispatcher or sweeper start.

## Rollback

- Only tasks 1-2 are authorised here (docs-only); reverting the docs PR changes no running state.
- Future F2 tag bump (separate GO): choose according to E5. If 4.154.0 can replay 4.155.0 Temporal histories, revert the bump PR and
  confirm that Argo `admins-mctl-api` is Synced at the revert and that the running digest equals the E11
  pre-bump digest. If it cannot, do NOT revert the image. Stop, page the release owner, and drain or handle
  the affected workflows per mctl-agents#1007 B4 before any revert. The chart tracks mctl-api `main` and is
  not rolled back by the tag revert.
