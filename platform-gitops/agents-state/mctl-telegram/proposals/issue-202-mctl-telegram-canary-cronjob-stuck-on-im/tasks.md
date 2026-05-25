# Tasks: issue-202-mctl-telegram-canary-cronjob-stuck-on-im

- [ ] 1. Suspend the live `labs` CronJob immediately (ops, no PR required) — DoD: `kubectl -n labs get cronjob mctl-telegram-canary -o jsonpath='{.spec.suspend}'` returns `true`; no new canary pods appear in `labs` for at least five minutes (2.5 schedule intervals).

- [ ] 2. Delete accumulated dead canary pods in `labs` (ops, no PR required) — DoD: `kubectl -n labs get pods -l job-name` returns no `ImagePullBackOff` or `Error` pods related to `mctl-telegram-canary`.

- [ ] 3. Update `deploy/canary/cronjob.yaml` in `mctl-telegram`: fix namespace, image tag, and add imagePullSecrets — DoD: `deploy/canary/cronjob.yaml` has `namespace: labs`, image tag set to the value of `image.tag` currently in `platform-gitops/services/labs/mctl-telegram/values.yaml` in mctl-gitops (read that file to get the live tag; do not hardcode a version here), and an `imagePullSecrets` stanza referencing `ghcr-credentials` (the confirmed pull-secret name in the `labs` namespace); `go vet ./...` and `go test ./...` still pass (no Go changes needed, but CI must be green).

- [ ] 4. Add `deploy/canary/cronjob.yaml` validation to `build.yml` CI (depends on 3) — DoD: the `build.yml` workflow contains a step that runs `kubectl --dry-run=client -f deploy/canary/cronjob.yaml` (or equivalent `kubeconform` invocation) and the step passes in CI on the PR that makes change 3; a subsequent PR that introduces a malformed field in `cronjob.yaml` causes CI to fail before merge.

- [ ] 5. In `mctl-gitops`: ensure the GHCR pull secret `ghcr-credentials` exists in the `labs` namespace — DoD: `kubectl -n labs get secret ghcr-credentials` succeeds; the secret contains a valid `.dockerconfigjson` with pull credentials for `ghcr.io/mctlhq`.

- [ ] 6. In `mctl-gitops`: extend `release-deploy.yaml` to update the canary CronJob image tag alongside the main service Deployment (depends on 3 and 5) — DoD: triggering a test dispatch of `release-deploy.yaml` with a dummy tag results in the canary CronJob manifest in the gitops repo having the updated image tag committed; the ArgoCD/Flux reconciliation (or equivalent) applies the change to the `labs` cluster without error.

- [ ] 7. Un-suspend (or replace) the `labs` CronJob by applying the gitops-managed manifest (depends on 5 and 6) — DoD: `kubectl -n labs get cronjob mctl-telegram-canary -o jsonpath='{.spec.suspend}'` returns `false` (or the field is absent); within the next two-minute tick a canary pod runs to completion and metrics appear in Pushgateway (`mctl_telegram_canary_success` is present); `MctlTelegramCanaryStale` and `MctlTelegramCanaryAbsent` alerts resolve.

## Tests

- [ ] T1. After task 7, verify `mctl_telegram_canary_success` is present in Pushgateway: `curl -s http://prometheus-pushgateway.monitoring.svc.cluster.local:9091/metrics | grep mctl_telegram_canary_success` returns a line with value `1` within 4 minutes of the CronJob being un-suspended.

- [ ] T2. After task 6, simulate a release dispatch with a new test tag and confirm the canary CronJob image tag in the gitops repo changes to the test tag without touching the main Deployment tag (isolation test for the pipeline change).

- [ ] T3. After task 4, open a draft PR that deliberately sets an invalid field in `deploy/canary/cronjob.yaml` (e.g., `apiVersion: batch/v99`) and confirm the new CI step fails, preventing merge.

- [ ] T4. Confirm that `MctlTelegramCanaryFailing`, `MctlTelegramCanaryStale`, and `MctlTelegramCanaryAbsent` alerts (defined in `deploy/alerts/canary.rules.yaml`) all resolve in the Alertmanager UI after 15 minutes of successful canary runs following task 7.

## Rollback

**If task 7 introduces new failures** (e.g., the un-suspended CronJob still fails to pull):

1. Re-suspend: `kubectl -n labs patch cronjob mctl-telegram-canary -p '{"spec":{"suspend":true}}'`
2. Diagnose: `kubectl -n labs describe pod <latest-canary-pod>` — check `imagePullSecrets` are mounted and the pull-secret contains valid credentials.
3. If the pull secret is the issue, rotate the GHCR token in `mctl-gitops` and update the secret in `labs` before re-attempting task 7.

**If task 6 corrupts the mctl-gitops manifest**:

1. Revert the mctl-gitops PR that introduced the canary tag-update step.
2. The main service Deployment is unaffected because the change is additive (new patch target, not a modification of the existing update path).
3. Re-apply the canary CronJob manifest from the last known-good state: `kubectl -n labs apply -f deploy/canary/cronjob.yaml` using the tag confirmed in task 3.

**At no point** does rolling back affect the main `mctl-telegram` service Deployment — the canary CronJob is an independent resource with no traffic path to production.
