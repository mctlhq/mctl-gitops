# Fix mctl-telegram-canary CronJob: adopt into gitops, pin to current image, restore pull credentials

## Context

The `mctl-telegram-canary` CronJob runs every two minutes in the `labs` namespace as a
synthetic end-to-end probe. It was created manually during the issue-89 canary work and was
never committed to either `mctl-telegram` or `mctl-gitops`. As a result it drifted: the
image tag is frozen at `0.23.1` while the service is now at `0.36.0`, and there is no
`imagePullSecret` keeping GHCR credentials current. Every two-minute tick spawns a new pod
that fails with `ImagePullBackOff`, so the `labs` namespace accumulates dead pods with no
automatic cleanup.

The `mctl-telegram` repo already contains `deploy/canary/cronjob.yaml` (namespace
`mctl-telegram`, hardcoded tag `0.23.1`) but that manifest is also stale and is not wired
into the release pipeline. The release-please workflow dispatches `release-deploy.yaml` in
`mctl-gitops` to update the main service deployment, but the canary CronJob is not part of
that dispatch. Fixing this means two concrete deliverables: stop the immediate bleeding (pod
churn) and wire the canary into the gitops release flow so the image tag advances
automatically on every future release.

## User stories

- AS an on-call engineer I WANT the `labs` canary pod churn to stop immediately SO THAT I
  am not paged on dead-pod noise while the structural fix is prepared.
- AS a platform engineer I WANT the canary CronJob manifest committed under gitops version
  control SO THAT its image tag, namespace, and secrets are auditable and do not drift.
- AS a release engineer I WANT the canary CronJob image tag updated automatically on each
  release SO THAT the canary always exercises the same binary version that is deployed to
  production.
- AS an SRE I WANT the canary CronJob to use a gitops-managed GHCR imagePullSecret SO THAT
  image pulls succeed after credential rotation without manual intervention.
- AS a developer I WANT the canary CronJob manifest validated in CI SO THAT a broken
  manifest is caught before it reaches the cluster.

## Acceptance criteria (EARS)

- WHEN the immediate mitigation is applied THE SYSTEM SHALL stop spawning new failing pods
  in the `labs` namespace within one CronJob schedule interval (two minutes).
- WHEN a new release tag is published and `release-deploy.yaml` completes THE SYSTEM SHALL
  update the canary CronJob image tag to the newly released tag without manual intervention.
- WHILE the canary CronJob is deployed THE SYSTEM SHALL reference a named `imagePullSecret`
  that grants pull access to `ghcr.io/mctlhq/mctl-telegram`.
- WHEN the canary CronJob image is successfully pulled and the pod runs to completion THE
  SYSTEM SHALL push `mctl_telegram_canary_success`, `mctl_telegram_canary_duration_seconds`,
  and `mctl_telegram_canary_step_failure_total` metrics to the Pushgateway at
  `http://prometheus-pushgateway.monitoring.svc.cluster.local:9091`.
- WHEN a pull request modifies `deploy/canary/cronjob.yaml` THE SYSTEM SHALL validate the
  manifest in CI (schema lint) before the PR can merge.
- IF the manually-created `labs` namespace CronJob conflicts with the gitops-managed one
  THEN THE SYSTEM SHALL remove the orphan before applying the gitops manifest.
- WHILE the gitops-managed canary is running THE SYSTEM SHALL enforce the same non-root,
  read-only-rootfs, drop-all-capabilities security context that exists in the current
  `deploy/canary/cronjob.yaml`.

## Out of scope

- Changes to the canary probe logic in `cmd/canary/main.go` — this proposal is
  infrastructure-only.
- Changes to `deploy/alerts/canary.rules.yaml` — alert thresholds and PromQL are not
  being revised.
- Canary coverage of additional MCP tools beyond those already probed.
- Rotation or creation of the underlying GHCR personal-access token or robot account —
  that is a secrets-management concern handled in `mctl-gitops`.
- Migration of the canary to the `mctl-telegram` namespace — the live resource lives in
  `labs`; if a namespace migration is desired it is a separate task.

## Open questions

1. **Namespace authority**: `deploy/canary/cronjob.yaml` in this repo declares
   `namespace: mctl-telegram`, but the live cluster resource is in `labs`. The issue does
   not clarify which namespace should be authoritative. This proposal assumes `labs` matches
   the intent (consistent with the `team_name=labs` passed to `release-deploy.yaml`) and
   updates the committed manifest accordingly. If `mctl-telegram` namespace is preferred,
   the implementer must also migrate the live resource and its referenced secret.

2. **imagePullSecret name**: the name of the GHCR pull secret in the `labs` namespace is
   not visible in this repo. This proposal uses the placeholder `ghcr-pull-secret`; the
   implementer should confirm the actual secret name from `mctl-gitops` before applying.

3. **mctl-gitops canary update mechanism**: `release-deploy.yaml` in `mctl-gitops` is not
   visible in this clone. The proposal assumes a `kustomize edit set image` or `sed`-based
   image-tag replacement pattern already exists for the main service and needs to be
   extended for the canary CronJob. If `release-deploy.yaml` uses a different mechanism
   (e.g., Helm values, ArgoCD image-updater) the implementer must adapt accordingly.
