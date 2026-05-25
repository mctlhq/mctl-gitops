# Design: issue-202-mctl-telegram-canary-cronjob-stuck-on-im

## Current state

### Canary binary and image

The `mctl-telegram-canary` binary is built inside the same multi-stage Docker image as the
main service. `Dockerfile` (lines 17, 27) shows:

```
go build ... -o /mctl-telegram-canary ./cmd/canary
COPY --from=builder /mctl-telegram-canary /usr/local/bin/mctl-telegram-canary
```

There is no separate canary image; the CronJob runs
`/usr/local/bin/mctl-telegram-canary` from `ghcr.io/mctlhq/mctl-telegram:<tag>`. The
canary is a black-box HTTP client (`cmd/canary/main.go`, package doc: "no imports from
internal/") that exercises the public OAuth metadata endpoint and MCP tool surface, then
pushes three Prometheus metric families to a Pushgateway.

### Gitops manifest in this repo

`deploy/canary/cronjob.yaml` exists but has two problems:

- Image is hardcoded to `ghcr.io/mctlhq/mctl-telegram:0.23.1` (line 22). Current release
  is `0.36.0`. No automation updates this value on release.
- `namespace: mctl-telegram` (line 5), but the live cluster resource is in `labs`.
- No `imagePullSecrets` field. The manifest relies on ambient node-level credentials or a
  cluster-wide pull secret that may have expired.

### Release pipeline

`.github/workflows/release-please.yml` dispatches `mctl-gitops/.github/workflows/release-deploy.yaml`
on each release with:

```
-f repo=mctlhq/mctl-telegram
-f image_tag="$TAG"
-f team_name=labs
-f component_name=mctl-telegram
```

The dispatch updates the main service Deployment image tag in `mctl-gitops` but the canary
CronJob is not part of that dispatch. As a result the canary image tag never advances.

### Live cluster state

The live CronJob in the `labs` namespace was created manually during issue-89 work and is
not reconciled from any gitops source. It is functionally orphaned: its tag (`0.23.1`) is
far behind, and every two-minute tick spawns a pod that fails with `ImagePullBackOff`
because GHCR either no longer hosts that tag or the pull credentials have expired.

The Prometheus alert `MctlTelegramCanaryStale` in `deploy/alerts/canary.rules.yaml`
(line 31) fires when the canary has not pushed metrics in 10 minutes. It has been firing
continuously since the CronJob broke.

### CI coverage

`build.yml` validates `deploy/alerts/mctl-telegram.rules.yaml` with `promtool` and lints
Grafana JSON, but does not validate `deploy/canary/cronjob.yaml`. A broken manifest in
that file would not be caught before merge.

---

## Proposed solution

The fix has three sequential parts: immediate mitigation, manifest correction, and pipeline
wiring.

### Part 1 — Immediate mitigation (ops, no code change)

Suspend the live `labs` CronJob to stop pod churn immediately:

```
kubectl -n labs patch cronjob mctl-telegram-canary \
  -p '{"spec":{"suspend":true}}'
```

This is a one-time manual step. The gitops-managed replacement (Part 3) will un-suspend
(or supersede) the resource.

### Part 2 — Fix `deploy/canary/cronjob.yaml` in this repo

Update the committed manifest:

1. **Namespace**: change `namespace: mctl-telegram` to `namespace: labs` to match the
   live-cluster target and the `team_name=labs` used by the release pipeline.

2. **Image tag**: update the hardcoded `0.23.1` to `0.36.0` as the new baseline. The tag
   will subsequently be managed by the pipeline (Part 3); this commit sets the correct
   starting point.

3. **imagePullSecrets**: add an `imagePullSecrets` stanza referencing a secret that holds
   GHCR pull credentials (name to be confirmed from `mctl-gitops`, placeholder:
   `ghcr-pull-secret`):

   ```yaml
   spec:
     ...
     jobTemplate:
       spec:
         template:
           spec:
             imagePullSecrets:
               - name: ghcr-pull-secret
   ```

   The secret itself is not created by this repo; it must already exist in the `labs`
   namespace (managed in `mctl-gitops`). If it does not exist the implementer must create
   it as part of the mctl-gitops change.

4. **CI validation**: add a step to `build.yml` that runs `kubectl --dry-run=client -f`
   (or `kubeconform`) against `deploy/canary/cronjob.yaml` so future manifest changes are
   caught in CI before merge.

The manifest security context (non-root UID 1000, `readOnlyRootFilesystem: true`,
`allowPrivilegeEscalation: false`, `drop: ["ALL"]`) is already correct and must not change.

### Part 3 — Wire canary CronJob into `mctl-gitops` release-deploy pipeline

In `mctl-gitops`, extend `release-deploy.yaml` (or the Kustomize overlay it drives) so
that when a new `mctl-telegram` release is dispatched the canary CronJob image tag is also
updated:

```
# Pseudocode — exact mechanism depends on mctl-gitops layout
kustomize edit set image \
  ghcr.io/mctlhq/mctl-telegram=$IMAGE_TAG \
  -- in labs/mctl-telegram-canary/kustomization.yaml
```

If `mctl-gitops` uses raw manifest patching (e.g., `sed -i`) rather than Kustomize, the
equivalent sed expression targets the same image field in the canary CronJob overlay.

After this wiring, each release dispatch automatically updates both the main Deployment and
the canary CronJob to the same tag, eliminating drift.

---

## Alternatives

### A. Suspend only, no gitops adoption

Patch `spec.suspend: true` on the live CronJob and close the issue. This stops the pod
churn immediately and requires zero code changes. It was rejected because it leaves the
canary permanently dark: `MctlTelegramCanaryAbsent` and `MctlTelegramCanaryStale` alerts
continue to fire, and the synthetic end-to-end health signal is lost. The canary was built
specifically for the beta operational posture defined in issue-88 SLOs; silencing it
degrades observability.

### B. Separate canary image built and pushed independently

Build `cmd/canary` into its own Docker image (`ghcr.io/mctlhq/mctl-telegram-canary`) with
its own release tag so it can be versioned independently of the main service. This was
rejected because it adds a second image build pipeline, a second GHCR repository, and a
second set of pull credentials for a binary that is already part of the main image. The
Dockerfile already copies `mctl-telegram-canary` into the runtime layer; sharing the image
is architecturally simpler and avoids drift between the canary and the service it probes.

### C. Replace CronJob with a Prometheus Blackbox Exporter probe

Remove the custom canary binary and replace it with a `blackbox_exporter` HTTP module that
polls the OAuth metadata endpoint on a scrape schedule. This was rejected because the
canary exercises the full MCP Streamable HTTP session handshake (initialize + tools/call),
FLOOD_WAIT detection, and Pushgateway push semantics that a generic blackbox exporter
cannot replicate without significant custom configuration. The existing `cmd/canary/main.go`
provides semantically richer coverage that is worth preserving.

---

## Platform impact

### Migrations

- The live `labs` CronJob must be removed or replaced by the gitops-managed one. If the
  gitops tooling applies the manifest with `kubectl apply`, the resource is updated
  in-place (same name, same namespace). If it deletes-and-recreates, a brief gap in canary
  coverage occurs; the `MctlTelegramCanaryStale` alert suppresses for 10 minutes before
  firing, so a gap shorter than that is invisible to alerting.

### Backward compatibility

- No API changes. The canary binary interface (environment variables, Prometheus metrics)
  is unchanged. The `deploy/alerts/canary.rules.yaml` Prometheus rules remain valid.

### Resource impact

- No change to the CronJob schedule (`*/2 * * * *`) or resource requests/limits. The fix
  restores steady-state resource consumption; it does not increase it.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| `ghcr-pull-secret` name is wrong in `labs` | Confirm secret name from mctl-gitops before applying; add secret existence check to deployment runbook |
| `release-deploy.yaml` uses a mechanism incompatible with the canary patch approach | Read mctl-gitops before implementing Part 3; adapt to actual pattern in use |
| Namespace mismatch causes gitops to create a second resource in `mctl-telegram` namespace | Ensure the orphan in `labs` is the target; do not apply the old `namespace: mctl-telegram` manifest without first deleting it |
| Dead pods in `labs` accumulate until garbage-collected | After suspension, manually delete the failed pods; `failedJobsHistoryLimit: 5` limits future accumulation |
