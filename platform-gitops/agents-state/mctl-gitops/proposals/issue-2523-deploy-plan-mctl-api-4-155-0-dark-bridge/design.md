# Design: issue-2523-deploy-plan-mctl-api-4-155-0-dark-bridge

## Current state

- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` defines the Argo CD Application
  `admins-mctl-api` (project `platform`, destination namespace `mctl-api`). It is a multi-source app:
  - Source 1 is the Helm chart at `https://github.com/mctlhq/mctl-api.git`, `path: helm`,
    `targetRevision: main`, with inline `helm.values`. Line 45 holds `image.repository: ghcr.io/mctlhq/mctl-api`
    and `tag: "4.154.0"`, and `replicaCount: 2` is set with a sticky-cookie Service and topology spread.
  - Source 2 is `platform-gitops/infra-components/mctl-platform/mctl-api` (OIDC/Zitadel secrets and roles).
  - `syncPolicy.automated` sets `prune: true, selfHeal: true`, with ServerSideApply, ApplyOutOfSyncOnly and
    RespectIgnoreDifferences.
- The env block has no `MCTL_BRIDGE_*` and no `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`; I checked with grep
  across the env keys at lines 55-368. Temporal is wired through `TEMPORAL_ADDRESS` and
  `TEMPORAL_NAMESPACE: mctl-agents` (lines 360-361). `ROLLOUT_MARKER: "2026-10-26-jwt-signing-keys"` (line 69)
  is how gitops forces a pod restart. It is not needed for an image bump, because a tag change already rolls
  the pods.
- Per the mctl-api#970/#971 proposals under `platform-gitops/agents-state/mctl-api/proposals/`, mctl-api wires
  the bridge only when `MCTL_BRIDGE_ENABLED == "true"` (`cmd/api/main.go`). An unset value therefore means
  dark: no routes, no `bridge.Dispatcher`, no expiry sweeper.
- `.github/workflows/release-deploy.yaml` and `gitops-bump.yaml` may push an `image.tag` directly to `main` for
  paths under `platform-gitops/bootstrap/templates/mctl-platform/` (the `ALLOWED_PREFIXES` allowlist), with no PR
  (see CLAUDE.md, "Branch Protection Exception").
- `platform-gitops/release-gates.yaml` (read by `scripts/release-gate.py`) gates only `mctl-agents-workers`
  today, with `min_tag "1.117.0"` for mctl-agents#1007. It has no gate for mctl-api.
  `.github/workflows/release-gate-watch.yml` and `release-drift.yml` are detectors, not enforcement.
- Tests are standalone Python files under `tests/` invoked from `.github/workflows/validate-manifests.yml`, for
  example `python3 tests/test_agent_credential_delivery.py`.

Deployed state checked:
- `mctl_get_service_status(admins, mctl-api)`: Argo app `admins-mctl-api` was Healthy / Synced, updatedAt
  2026-11-09T00:33:08Z, project `platform`. The `revision` field came back empty, so the synced revision is not
  observed.
- `mctl_get_service_config(admins, mctl-api)`: error "service not found". The app is not a catalogue service,
  so neither the config nor the live image tag was observed through this tool.
- `mctl_get_service_pods(admins, mctl-api)`: error "service not found". Pod readiness and the running digest
  were not observed.
- `mctl_list_services(admins)`: complete=true. mctl-api is not listed (it is a platform bootstrap app). The
  mctl-agents workers all run `ghcr.io/mctlhq/mctl-agents:1.117.0`, which equals the `release-gates.yaml`
  floor.
- `$MCTL_GITOPS_ROOT/services/admins/`: no mctl-api directory. Its source of truth is the bootstrap template
  above.
- The status of mctl-api#934, mctl-agents#993/#992/#1007 and mctl-api#935 is not observable from this run (no
  GitHub reads). It is taken from the issue body as open or incomplete and must be re-read when the checklist
  is filled in.

## Proposed solution

There are three artifacts. Only the first two are implemented now. The third is a gated future PR.

### A. Release-readiness runbook: `docs/runbooks/mctl-api-4.155.0-dark-rollout.md` (doc-only PR)

The runbook contains:

1. A decision gate whose value is exactly `BLOCKED_RELEASE_HOLD` or `READY_FOR_SEPARATE_DARK_DEPLOY_APPROVAL`.
   The default is BLOCKED. It flips only when every evidence field below is filled in, and the flip itself is
   not approval.
2. An evidence table with columns field / source / value / verified-by / date:
   - E1: owner GO lifting the 2026-11-03 hold on mctl-api#934 (comment link).
   - E2: mctl-agents#993 Part M integrated (PR + merge SHA + deployed worker tag).
   - E3: mctl-agents#992 Part S integrated (same fields).
   - E4: compatibility evidence: mctl-api 4.155.0 against the deployed mctl-agents worker tag and Temporal
     history.
   - E5: mctl-agents#1007 B4 marker rollback safety. State whether 4.154.0 can replay histories written by
     4.155.0.
   - E6: mctl-api#935 lease-aware drain disposition (in 4.155.0, or accepted as not blocking, with the reason).
   - E7: tag `4.155.0` verified/signed on the reviewed #934 merge commit, plus the GitHub Release URL.
   - E8: GHCR `ghcr.io/mctlhq/mctl-api:4.155.0` digest. Its build provenance subject must equal E7's commit,
     and it must have an SBOM attestation.
   - E9: all CI and reviewer gates on the E7 commit are completed and green. Automated reviewer verdicts are
     re-checked semantically on that SHA (mctl-agents#240 / mctl-gitops#1040).
   - E10: mctl-api `helm/` chart revision on main at bump time, and the diff of `helm/` since the 4.154.0
     tag. This is needed because the chart tracks `main`.
   - E11: pre-bump live state: the running 4.154.0 digest (the rollback target), the pods, and the Argo
     revision.
3. STOP conditions before release: any E1-E9 field is empty or unknown; an M1 merge is presented as whole
   readiness; a tag other than the reviewed `4.155.0` is proposed; or the release includes a default change
   that turns on Bridge or `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`.
4. Post-deploy checks (P1-P6):
   - P1: Argo `admins-mctl-api` Synced/Healthy at the PR merge revision.
   - P2: 2/2 pods Ready, rollout complete, running digest equals E8, restarts 0.
   - P3: negative Bridge smoke. Bridge routes answer 404 / not registered, and the logs contain no
     dispatcher or expiry-sweeper start lines.
   - P4: existing canaries pass: `/healthz`, `/readyz`, an OAuth sign-in, `GET /api/v1/agents/dev-loop/<known
     id>`, a lifecycle list read with count 0 (per the `LIFECYCLE_DB_URL` comment), and the Temporal client
     connected.
   - P5: error rate and p95 latency in Loki/metrics stay within the 4.154.0 baseline for 30 min.
   - P6: no new Temporal non-determinism or replay errors in mctl-agents workers.
5. Rollback options, chosen according to E5:
   - If E5 says 4.154.0 replays 4.155.0 histories: revert the bump PR, wait for Argo to sync, then verify
     the E11 digest is running.
   - If it does not, an image revert is unsafe. Hold forward, drain or terminate the affected workflows per
     #1007 guidance, and only then revert. This is a STOP-and-page condition, not an operator judgment call.
   - The chart cannot be rolled back by the tag revert, because it tracks main. Note this explicitly.

### B. CI guard: `tests/test_mctl_api_bridge_dark.py`, wired into `validate-manifests.yml`

The test parses the `helm.values` block of `mctl-api.yaml`. It strips the `{{ }}` templating first, the same
way other tests in `tests/` handle bootstrap templates. It asserts that:

- `MCTL_BRIDGE_ENABLED` is absent or `"false"`;
- `MCTL_BRIDGE_PROVIDERS` and `MCTL_BRIDGE_PROVIDER_TOKENS` are absent;
- `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` is absent or `"false"`;
- no `envFromExtraSecret` / ExternalSecret name contains `bridge`.

The assertions are written as the hold, with a pointer to the security-owner GO. Lifting the hold later
means a reviewed PR that edits this test. That makes activation a visible, deliberate act.

### C. Future tag-bump PR (only after the gate reads READY and the owner approves)

The diff is one line, `tag: "4.154.0"` to `tag: "4.155.0"`, in `mctl-api.yaml`, opened from a feature branch.
The PR body links the filled runbook. CI runs `validate-manifests.yml` (including test B) and a
`helm template` render of the mctl-api chart at E10 with the inline values, and attaches the rendered diff
(expected: the image reference only). `release-deploy.yaml` is not used, because its direct push to main
would skip the separate owner approval.

## Alternatives

- **Use `release-deploy.yaml` for the bump.** This is the normal path, but it pushes straight to `main` with
  no PR, so a separate owner approval and Argo review are impossible. Rejected for this release.
- **Pin the image by digest (`tag: "4.155.0@sha256:..."`, as `umami` does).** This is stronger immutability,
  but it changes the established mctl-api pin format and is not what the issue asked for. Recorded as an
  option for the owner. E8 gives the same assurance through verification.
- **Add an mctl-api entry to `release-gates.yaml` with `requires: MCTL_BRIDGE_ENABLED absent`.** That file's
  `requires` and `paths` handling is built for service `values.yaml` groups, and
  `argo-workflows/scripts/release-gate-guard.sh` refuses unknown path shapes. Extending it for a bootstrap
  template is a larger change. A standalone test (B) is narrower.

## Platform impact

- No migration and no runtime change from A or B. B is a CI-only check, and it passes on the current file.
- The future change C rolls 2 pods (a new image). The sticky-cookie identity link flow restarts its link
  challenges ("start again"), which is acceptable.
- Risks and mitigations:
  - Temporal history incompatibility on rollback: mitigated by E5 being mandatory and by the
    Temporal-aware rollback branch.
  - Chart drift from `targetRevision: main`: mitigated by E10 and by stating that the tag revert does not
    roll back the chart.
  - The bypass path (`release-deploy.yaml`): mitigated by the runbook forbidding it. The release owner
    should also not dispatch it.
  - A new 4.155.0 default activating something: mitigated by the STOP condition on the release notes, the
    test B env assertions, and the negative smoke P3.
