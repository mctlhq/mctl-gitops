# Tasks: nodejs-runtime-upgrade

- [ ] 1. Determine the current Node.js version in the base image — inspect Dockerfile(s) in
  mctl-gitops (and any upstream fork) — DoD: the exact `node:XX.YY.Z` version used in the
  current production image is captured; if < v22.22.0 — the active CVEs are confirmed

- [ ] 2. Bump the base image to Node.js v22.22.0 (depends on 1) — change `FROM node:XX`
  to `FROM node:22.22.0-alpine` (or `-slim` if the current image is slim-based) in the
  Dockerfile — DoD: Dockerfile contains `FROM node:22.22.0-*`; the image builds locally
  (`docker build` succeeds); openclaw starts in a container (`node --version` returns
  v22.22.0)

- [ ] 3. Add a CI step: npm audit (depends on 2) — add `npm audit --audit-level=high
  --production` after `npm ci` and before `docker build` in the CI pipeline — DoD: the
  step is added to the pipeline configuration; with no High/Critical vulnerabilities the
  pipeline passes; with a deliberately introduced vulnerability (npm install of a known-CVE
  package) the pipeline fails with a non-zero exit code

- [ ] 4. Add a CI step: malicious package grep (depends on 2) — add a script that checks
  the lockfile for `lotusbail` and `discord.js-user` (and any other packages from
  `.malicious-packages` if the file exists); the step runs before `npm ci` — DoD: the
  script is added to the pipeline; with a clean lockfile it passes; when adding
  `"lotusbail": "1.0.0"` to the lockfile — it fails with a clear error message

- [ ] 5. Create the file `.malicious-packages` (depends on 4) — one package per line, initial
  list: `lotusbail`, `discord.js-user` — DoD: the file is committed to the repo; the CI
  step reads the list from the file rather than from a hardcoded value in the script;
  adding a new package to the file is picked up by CI without script changes

- [ ] 6. Deploy the new image to `labs` (depends on 3, 4, 5) — build the image with the new
  Node.js, update the tag in the labs gitops overlay, run an ArgoCD sync — DoD: ArgoCD
  shows Synced+Healthy for labs; `kubectl exec` into the pod reports `node --version`
  v22.22.0; the restore-state probe passes (ADR 0002); the RAM delta vs baseline <= 20MB

- [ ] 7. Deploy to `admins` (depends on 6) — observe for 24 hours after labs, then perform
  the same rollout — DoD: ArgoCD Synced+Healthy; admins functional channels work;
  s3-sync canary green

- [ ] 8. Deploy to `ovk` (depends on 7) — rollout to the production tenant — DoD: ArgoCD
  Synced+Healthy; the restore-state probe passes; the s3-sync canary is active; no
  production ovk channel has lost connectivity 24 hours after the deploy

## Tests

- [ ] T1. Node.js version in the image — `docker run --rm <image> node --version` returns
  `v22.22.x`; expected: version >= 22.22.0

- [ ] T2. npm audit on a clean lockfile — run `npm audit --audit-level=high --production`
  in the current code base after the lockfile update; expected: exit code 0,
  no high/critical vulnerabilities found

- [ ] T3. npm audit trigger — temporarily add a known-vulnerable package to devDependencies
  and run audit; expected: exit code != 0, output contains the CVE name

- [ ] T4. Malicious package grep: clean — run the script against the production lockfile;
  expected: "Malicious package check passed.", exit code 0

- [ ] T5. Malicious package grep: detect — manually add the line `"lotusbail": "1.0.0"`
  to package-lock.json (do not commit), run the script; expected: the message
  "SECURITY: malicious package 'lotusbail' found in lockfile", exit code 1

- [ ] T6. Labs RAM baseline — before and after deploying the new image, compare `kubectl top pod`
  for the openclaw pod in labs; expected: delta <= 20MB

- [ ] T7. Restore-state probe after deploy — manually restart the labs pod after deploying
  the new image; expected: the pod transitions to Ready without exceeding the probe timeout

- [ ] T8. S3-sync canary after the labs deploy — wait for the next canary workflow cycle
  after the labs rollout finishes; expected: canary green, fresh S3 timestamp

## Rollback

Rollback runs through gitops without code changes:

1. In the tenant overlay revert to the previous Docker image tag (with the previous Node.js version).
2. Run an ArgoCD sync — ArgoCD deploys the previous image.
3. The restore-state probe guarantees (ADR 0002) that the pod does not become Ready until
   S3 state is restored — even on rollback.

Rollback order during an incident: ovk → admins → labs (reverse of ADR 0001).

The CI steps (`npm audit`, malicious package grep) can be temporarily switched to warn-only
mode (drop the `-e` flag or append `|| true`) if they produce false positives blocking a
hotfix — but this requires an explicit decision and an issue tracker entry.
