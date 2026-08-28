# Set explicit AUTO_MERGE_ENABLED=false for mctl-agent deployment

## Context
The `admins-mctl-agent` ArgoCD Application (rendered from
`platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`) sets
`DRY_RUN: "false"` in its `env` block but does not set `AUTO_MERGE_ENABLED`.
Per the issue, the mctl-agent code default for `AUTO_MERGE_ENABLED` is
`true`, so with `DRY_RUN` off the agent's generated PRs against this repo
(`mctlhq/mctl-gitops`) can auto-merge without a human or Claude review
gate. This is a fail-open configuration gap: the deployment is silently
relying on an upstream code default rather than stating its own intent.
The fix is deployment-only — pin the env var explicitly so the running
pod's behavior is visible in git and does not depend on whatever the
mctl-agent code default happens to be on any given image tag.

This complements the existing OPTIMIZER note already in the same file
("Optimizer PRs use agent/optimize/* branches, which stay review-gated —
claude/* would auto-merge"), which shows the operator is already relying
on branch-prefix behavior for one PR class; this issue asks that the
top-level flag itself be explicit and fail-closed for the general case.

## User stories
- AS the platform operator I WANT the mctl-agent deployment to explicitly
  declare `AUTO_MERGE_ENABLED=false` SO THAT agent-authored PRs to
  mctl-gitops always land as review-gated, regardless of what the
  mctl-agent binary's compiled-in default is on any given image tag.
- AS a reviewer of `bootstrap/templates/mctl-platform/mctl-agent.yaml` I
  WANT the auto-merge posture to be readable directly from the env block
  SO THAT I don't have to cross-reference the mctl-agent source to know
  whether generated PRs merge unattended.

## Acceptance criteria (EARS)
- WHEN `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`
  is edited THE SYSTEM SHALL declare `AUTO_MERGE_ENABLED: "false"` as a
  string-quoted entry in the Application's `spec.source.helm.values.env`
  map, alongside the existing `DRY_RUN: "false"`.
- WHEN the base-service Helm chart renders this Application's values THE
  SYSTEM SHALL produce a Deployment env entry `- name: AUTO_MERGE_ENABLED`
  `value: "false"` (per the `{{ $key }}` / `{{ $value | quote }}` loop in
  `platform-gitops/helm-charts/base-service/templates/deployment.yaml`).
- WHEN ArgoCD syncs the change to the `admins` namespace THE SYSTEM SHALL
  result in the live `admins-mctl-agent` pod exposing
  `AUTO_MERGE_ENABLED=false` in its container env (verified by pod env
  inspection, not merely `Synced`/`Healthy` status — per the issue's
  fail-closed config rule).
- IF the mctl-agent image tag in this same file (`1.16.2`) is older than
  whatever version first reads `AUTO_MERGE_ENABLED` THEN THE SYSTEM SHALL
  still carry the explicit env entry (it is inert on old tags, matching
  the precedent already documented in this file for `GITHUB_TOKEN_FILE`:
  "Unset (mctl-agent <= 1.15.3) it falls back to the frozen env value, so
  this key ... is inert on older tags").
- WHILE this change is deployment-config-only THE SYSTEM SHALL NOT modify
  `image.tag`, RBAC, secrets wiring, or any other env key in this file.

## Out of scope
- Flipping the mctl-agent code-side default for `AUTO_MERGE_ENABLED` from
  `true` to `false` — tracked in the companion mctl-agent issue referenced
  by this issue's cross-link comment, and already called out as
  out-of-scope in the related proposal
  `platform-gitops/agents-state/mctl-agent/proposals/issue-98-fail-closed-when-inbound-auth-tokens-are/requirements.md`.
- Any change to the `agent/optimize/*` vs `claude/*` branch-prefix
  auto-merge distinction mentioned in the `OPTIMIZER_ENABLED` comment in
  the same file — that mechanism is unaffected by this flag and is left
  as-is.
- Adding CI/manifest-render assertions beyond a manual `helm template`
  check (see tasks.md) — no test harness for bootstrap-chart env values
  currently exists in this repo (`platform-gitops/bootstrap` has no Helm
  chart of its own to lint against; it is raw ArgoCD Application specs
  consumed by root-app).

## Open questions
- None. The issue is fully specified: one file, one new explicit env key,
  verified by rendered manifest and live pod env after sync.
