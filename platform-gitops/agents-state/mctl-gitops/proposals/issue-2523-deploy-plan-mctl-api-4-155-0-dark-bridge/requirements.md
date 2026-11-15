# mctl-api 4.155.0 dark Bridge rollout plan, gated on the #934 release hold

## Context

Issue mctlhq/mctl-gitops#2523 asks for a plan only: a narrow, auditable dark rollout of the mctl-api
`4.155.0` release candidate (mctlhq/mctl-api#934). That candidate contains the completed Bridge work
from mctl-api#970/#971 (PRs #972 `53973f3d`, #974 `8c3d564c`). Bridge is not activated and no provider
credentials are issued. The release candidate is a Draft under an explicit owner release hold
(2026-11-03). The hold lifts only after mctl-agents#993 Part M and #992 Part S are integrated, compatibility
evidence exists, and the owner gives a separate GO. mctl-agents#1007 (B4 Temporal marker rollback safety) and
mctl-api#935 (lease-aware drain) also have to be accounted for.

The deployed mctl-api is the Argo CD Application `admins-mctl-api`, declared in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`. It is pinned to `image.tag: "4.154.0"`
and has no `MCTL_BRIDGE_*` variables. This **docs-only** proposal delivers a gated release-readiness checklist and a plan
for a future one-line tag bump. An executable repository/release guard is a **separate mandatory
implementation dependency**, not authorised by this proposal. No merge, tag, build, push,
deployed GitOps mutation or activation is authorised.

## User stories

- AS the mctl-api release owner I WANT a checklist with evidence fields and STOP conditions SO THAT the
  #934 hold cannot be bypassed by a partial readiness signal (e.g. a successful M1 merge alone).
- AS a platform operator I WANT the future GitOps change limited to one `image.tag` line SO THAT the dark
  rollout cannot carry Bridge enablement or unrelated toggles.
- AS the security owner I WANT a fail-closed guard at the point of release/deployment effect
  (including direct-main workflow writes), not merely PR-only CI, SO THAT automatic bumpers
  cannot silently activate Bridge. This slice documents the dependency only.
- AS an on-call engineer I WANT post-deploy smoke checks, stop criteria and a Temporal-aware rollback path
  SO THAT I can decide in minutes whether to halt or revert.

## Acceptance criteria (EARS)

- WHILE the #934 owner release hold is in force THE SYSTEM SHALL report the decision gate as
  `BLOCKED_RELEASE_HOLD`, and the image tag in `mctl-api.yaml` SHALL stay at `4.154.0`.
- THE SYSTEM SHALL report `READY_FOR_SEPARATE_DARK_DEPLOY_APPROVAL` only WHEN every checklist evidence field
  is filled with a link or value. The required evidence is: the explicit owner GO lifting the hold;
  mctl-agents#993 Part M and #992 Part S integration evidence; compatibility evidence; the mctl-agents#1007 B4
  rollback-safety and mctl-api#935 drain dispositions; the verified tag `4.155.0`; the GitHub Release; the
  GHCR digest matching the reviewed source commit; provenance/SBOM; and no failed or unfinished CI or
  reviewer gates on the release commit.
- IF any evidence field is empty, unreadable or "unknown" THEN THE SYSTEM SHALL treat the gate as
  `BLOCKED_RELEASE_HOLD`. An unreadable source is never a pass.
- WHEN the tag-bump PR is opened THE SYSTEM SHALL change exactly one line in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`: `tag: "4.154.0"` to `tag: "4.155.0"`.
  Nothing else changes: no env change, no `ROLLOUT_MARKER` change, no other file.
- THE SYSTEM SHALL deliver the tag bump through a reviewed feature-branch PR, never through
  `release-deploy.yaml` / `gitops-bump.yaml`. Those workflows push directly to `main` and would skip the
  separate owner approval this issue requires.
- BEFORE lifting the hold, a **separately reviewed and approved** fail-closed gate SHALL be
  proven effective on every permitted production deploy path, including direct pushes by
  `release-deploy.yaml` / `gitops-bump.yaml`. It SHALL reject unauthorised
  `MCTL_BRIDGE_ENABLED`, `MCTL_BRIDGE_PROVIDERS`, `MCTL_BRIDGE_PROVIDER_TOKENS` and
  `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`. PR-only CI is insufficient; this docs-only
  scope does not implement the gate and cannot satisfy the release GO.
- WHEN 4.155.0 is deployed, the operator SHALL record post-deploy evidence: the GitOps revision, the tag, the
  running image digest equal to the release digest, `admins-mctl-api` Healthy/Synced, 2/2 ready pods with the
  rollout complete, a negative Bridge HTTP smoke (Bridge routes unavailable, no dispatcher or expiry sweeper
  started in logs), and the existing API/DevLoop canary invariants passing.
- IF a stop condition fires (see design.md) THEN the operator SHALL halt and follow the rollback path for the
  Temporal history/marker state actually deployed. A blind image revert is not the rollback path.

## Unresolved automation bypass (release STOP)

The current `release-deploy.yaml` and `gitops-bump.yaml` can push bootstrap image tags
**directly to `main`**. PR-only CI and a runbook prohibition do not protect these paths.
Until separately authorised, fail-closed, point-of-effect enforcement and negative bypass
tests are verified, `BLOCKED_RELEASE_HOLD` is mandatory, even with green release CI.
The Helm chart follows `main`; reverting the image tag does not revert independently
synced chart changes.

## Out of scope

- Merging, tagging, releasing, building or pushing mctl-api 4.155.0, or creating any alternate tag.
- Applying the tag bump. That is a later PR that needs separate owner approval.
- Bridge activation of any kind: enabling the flag, providers, provider tokens, issuer/identity cutover,
  command ingestion, or endpoint exposure. Also excluded: the decisions in #2469, #2506 and #2457, canonical
  provider OIDC, mctl-api#954, `lease_token` retention, and expiry metrics/alerts.
- Running `go run ./cmd/bridge-scrub` in production.
- Changes to the mctl-api Helm chart or source.
- CI tests, workflow edits, executable release/deploy enforcement and image tag changes
  under this **docs-only** proposal. Each executable guard needs its own owner approval.

## Open questions

- The `admins-mctl-api` Application renders the Helm chart from mctl-api `main` (`targetRevision: main`), not
  from the release tag. Chart changes that landed on main between 4.154.0 and 4.155.0 are therefore already
  live, or will go live independently of the tag bump. The proposal assumes the reviewer accepts this
  existing pattern and records the chart revision as evidence. Pinning the chart to the tag is a separate,
  unrequested change.
- I could not read the running image digest or pod state: `mctl_get_service_pods` and
  `mctl_get_service_config` answered "service not found" because the app is not a catalogue service. The
  live digest of 4.154.0 is unobserved, so it has to be captured before the bump to serve as the rollback
  target.
- Whether 4.155.0 writes new Temporal markers or history events that a 4.154.0 build cannot replay is
  unknown. mctl-agents#1007 B4 has to answer it before rollback-by-revert is declared safe.
- `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`: I assumed default-off in 4.155.0 when unset. The release notes
  must confirm this.
