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

There are three **planned** artifacts. Only A, the docs-only runbook, is in scope now.
B (executable enforcement) and C (production tag-bump) require separate proposals and owner approvals.

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

### Release gate not inherited from documentation

Publishing this runbook does not authorise release, CI/workflow changes, tag bump,
deployment or activation. #934's owner hold remains active until Part M/Part S,
B4/drain, actual deploy-path enforcement and an explicit owner GO are evidenced.
The future guard must be independently designed, reviewed, approved and verified;
E1–E11 are necessary evidence but cannot by themselves enforce the release hold.

### B. Future fail-closed release/deployment guard (NOT part of this docs-only slice)

An independently approved implementation can add a PR CI test parsing the
`helm.values` block in `mctl-api.yaml`, asserting that:

- `MCTL_BRIDGE_ENABLED` is absent or `"false"`;
- `MCTL_BRIDGE_PROVIDERS` and `MCTL_BRIDGE_PROVIDER_TOKENS` are absent;
- `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` is absent or `"off"`;
- no `envFromExtraSecret` / ExternalSecret name contains `bridge`.

**PR-only CI does not enforce the hold**: `release-deploy.yaml` and `gitops-bump.yaml`
can push bootstrap tags directly to `main`, bypassing PR checks. A separate, reviewed,
fail-closed point-of-effect guard MUST cover those writes and every other production
deployment path, with negative bypass tests and missing/unknown-hold denial. This docs-only
proposal installs no guard, so the decision gate stays `BLOCKED_RELEASE_HOLD`.

### C. Future tag-bump PR (only after separately enforced guard, READY evidence and owner GO)

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

- No migration or runtime change from A (the only in-scope artifact: docs-only).
  B is not authorised here; it must prove real point-of-effect enforcement.
- The future change C rolls 2 pods (a new image). The sticky-cookie identity link flow restarts its link
  challenges ("start again"), which is acceptable.
- Risks and mitigations:
  - Temporal history incompatibility on rollback: mitigated by E5 being mandatory and by the
    Temporal-aware rollback branch.
  - Chart drift from `targetRevision: main`: mitigated by E10 and by stating that the tag revert does not
    roll back the chart.
  - The bypass path (`release-deploy.yaml` / `gitops-bump.yaml`): **NOT** mitigated by a
    runbook prohibition. A separate enforced gate with denial tests is mandatory before release.
  - A new 4.155.0 default activating something: mitigated by the STOP condition on the release notes, the
    test B env assertions, and the negative smoke P3.

## Dark-release compatibility evidence, 2026-11-09 UTC

**Assessment: `HOLD_CONTINUES`. #2523 gate: `BLOCKED_RELEASE_HOLD`.** This appendix records a read-only assessment and amends the proposed evidence. It leaves the DevLoop parked at `proposed`.

| Evidence | Observation | Disposition |
| --- | --- | --- |
| E1, release candidate | [API #934](https://github.com/mctlhq/mctl-api/pull/934) is Draft with auto-merge absent at `e818c114e59ab67be7729785af51bdf38a1e5259`, based on `77b9d063a2b7b4a495767e9a1d64061f3404eee1`. The PR diff is release metadata. The effective diff from 4.154.0 (`a11b54d7dcb653586763802ec58256ac7110bdb0`) spans 215 files. [Owner hold](https://github.com/mctlhq/mctl-api/pull/934#issuecomment-6613386625) is active. | STOP |
| E2–E3, worker integration | [Part M #993](https://github.com/mctlhq/mctl-agents/issues/993) splits implementation into sequential child DevLoops with their own digest-bound approvals. The contract requires meaningful feedback, typed refusals, proof-gated recovery and orphan handling. [Part S #992](https://github.com/mctlhq/mctl-agents/pull/992) is Draft at `6b60a7fadecf5897ba2cfdf369b26086cca5da73`, with cancelled tests and skipped Claude/Agy checks. Its `IMPLEMENT_EXECUTION_PATCH` is the Temporal `implement-execution-id` marker, with no environment toggle. | Integration unproven |
| E4, baseline dispatcher | All three production workers run 1.117.0, imageID digest `sha256:6162d8635374efd4d903c5f5b38cb317d05075041d44a0ea6fdf7dbf818ed09a`, and are Ready. The control deployment sets the existing `EXECUTION_REQUEST_DISPATCHER=true` although its code default is OFF. Keep this baseline when rehearsing API-only compatibility. Queue OFF preserves active-execution create refusal (`409 execution_active`), leaves the new claim filter off and suppresses the new orphan reconciler. | Static compatibility only. Require frozen API and actual worker builds against isolated Postgres and representative Temporal histories. Prove legacy create/claim/fulfil/reject, legacy resume, no deferred row on 409, no false success, and mixed API replica/rollback behavior. |
| E5, rollback | [B4 #1007](https://github.com/mctlhq/mctl-agents/issues/1007#issuecomment-6729850086) remains FAIL. The previous production scan was a point-in-time pre-M1 baseline (0 present, 25 absent, 0 unknown). Worker rollback depends on actual history and continue-as-new chains. The API is a Temporal client. API image rollback separately needs API intake, DB and worker compatibility evidence. | Require explicit disposition for the API-only path and forward-only fallback. No blind revert, no new production history scan in this assessment. |
| E6, drain | [API #935](https://github.com/mctlhq/mctl-api/issues/935#issuecomment-6641695239) remains a proposed single-row, lease-aware CAS and approval-grant design. Existing reject requires the live claim, matching claimant and claim token. Queue OFF prevents new active-execution queue admissions. Existing outstanding requests and the ordinary dispatcher still require a documented disposition. | No pause/list/reject-by-ID procedure. Require owner-reviewed evidence for whether #935 can be deferred for the dark path. |
| E7–E9, release and reviews | GitHub tag ref and Release lookup for 4.155.0 were absent. No matching immutable candidate artifact, SBOM or provenance was established. The old Claude approval on #934 is for `254a119` and covers release metadata. | Open. Review this evidence on its own docs PR and bind the future release evidence separately to the reviewed source and artifact. |
| E10, desired configuration | [Bootstrap app](https://github.com/mctlhq/mctl-gitops/blob/c7737eb3b1e0f7d8976a2a6e648b7720e7e6a7bf/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml) pins API 4.154.0 and tracks chart main. Offline Helm render with Argo's live inline values and candidate chart differs only in image and its derived `app.kubernetes.io/version` label. Chart changed since 4.154.0, including ingress and optional decide-client refs. | Re-render at the actual proposed chart revision. Tag revert leaves the chart revision independent. |
| E11, live API | `admins-mctl-api` Healthy/Synced, chart revision `77b9d063a2b7b4a495767e9a1d64061f3404eee1`, GitOps revision `c7737eb3b1e0f7d8976a2a6e648b7720e7e6a7bf`. Two Ready 4.154.0 pods, zero restarts, imageID digest `sha256:42d5a572156f179f0f697bd3279fe7817831294d9ccb4a55a91d28b02f9d4488`. | Read-only baseline. P1–P6 for 4.155.0 remain pending. |
| F1, deploy effect | [#2528](https://github.com/mctlhq/mctl-gitops/issues/2528) is open. Both direct-main workflows allow the bootstrap path and invoke `scripts/release-gate.py`; policy currently lists only the worker group. The API bootstrap app uses automated sync. | Mandatory STOP until separately approved enforcement and negative bypass tests cover each authorized write/deploy path. |

### Candidate controls and production input paths

| Control | Code behavior and observed configuration |
| --- | --- |
| `MCTL_BRIDGE_ENABLED` | Literal `true` enables Bridge. Absent in production. Off skips Bridge store init and its DDL, Bridge dispatch/expiry startup and route registration. |
| `MCTL_BRIDGE_PROVIDERS`, `MCTL_BRIDGE_PROVIDER_TOKENS` | Keep both absent. Provider config is loaded independently of the Bridge startup gate, so check credential paths separately. No matching keys in the current env sources. |
| `MCTL_BRIDGE_EXPIRY_SWEEP_INTERVAL`, `MCTL_BRIDGE_SCRUB_DATABASE_URL` | Expiry setting applies only when Bridge starts, default 30s. Scrub is a separate CLI, requires explicit confirmation and its own scoped DB URL. Both keys absent in API env sources. |
| `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` | Empty/unset or normalized `off` disables. Normalized `on` enables. Other values, including `false`, fail startup validation. Absent from current env sources. [Parser](https://github.com/mctlhq/mctl-api/blob/e818c114e59ab67be7729785af51bdf38a1e5259/internal/workitems/queue_switch.go) |
| `MCTL_ORCHESTRATOR_DEVLOOP_PROVIDER`, `MCTL_ORCHESTRATOR_DEVLOOP_SUBJECT`, `MCTL_ORCHESTRATOR_DEVLOOP_REPOS` | Mapping is inactive without a valid pair. The production optional Secret `mctl-api-orchestrator-devloop` already contains both keys and the Deployment sets the repo allowlist. A matching verified identity can acquire the new scoped start/read principal at 4.155.0 without a manifest change. Key presence is established. Effective behavior and any owner exception to the all-new-controls-dark scenario remain open. |
| `DEVLOOP_DECIDE_CLIENT_ID`, `DEVLOOP_DECIDE_CLIENT_SECRET` | Both absent. The optional Helm `devLoopDecideSecret` defaults empty and is not set. The chart publishes the path, while the handler fails closed when the client pair or authz prerequisites are unavailable. |

The API Deployment's inline env and five envFrom Secrets were checked by key name only: `mctl-api-secrets` and `mctl-api-events` from ExternalSecrets/Vault, and optional `mctl-api-zitadel-hook`, `mctl-api-orchestrator-devloop` and `mctl-api-security-code-scanning`. The chart also has targeted OIDC and OAuth references, plus file-backed credentials, which feed their named consumers and are distinct from envFrom. No Secret values are included here. The inspection is a configuration snapshot and must be repeated against the actual rollout inputs.

Other changes in the release diff remain in the test scope, including work-item storage/index startup, OIDC subject-audience validation, scoped run tokens, review assertions and DevLoop intake. A green package test or a negative Bridge smoke alone cannot settle the paired rollout.

**Next owner decision:** review the proposed #2523 documentation amendment and keep #934 on hold. Once this amendment has independent Claude and Agy evidence on the same docs HEAD, the owner can decide the corresponding current digest-bound **docs-only** proposal grant through the authenticated DevLoop path. Separately decide whether to commission #2528 enforcement and an isolated compatibility rehearsal. Any future exception for the already provisioned orchestrator identity, alternative to the Part M/S gate, or disposition for B4/#935 needs an explicit recorded owner decision. A release GO can be reconsidered only after the applicable evidence and point-of-effect guard are verified.
