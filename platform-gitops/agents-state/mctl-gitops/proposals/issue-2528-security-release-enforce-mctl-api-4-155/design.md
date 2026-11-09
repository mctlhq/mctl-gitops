# Design: issue-2528-security-release-enforce-mctl-api-4-155

Decision: `READY_FOR_SEPARATE_IMPLEMENTATION_PROPOSAL`. The design below closes every source-verified write
path. Two items stay BLOCKING-UNKNOWN until the owner disposes of them: chart drift until the pin lands,
and out-of-band cluster-admin actions. While any item is BLOCKING-UNKNOWN the hold stays in force. This
document is not a release approval.

## Current state

### The deployed application

`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` is a template of the bootstrap Helm chart,
synced by `root-app` (`platform-gitops/bootstrap/templates/bootstrap/root-app.yaml`, `automated`,
`selfHeal: true`). It renders the Argo CD Application `admins-mctl-api` (project `platform`,
`syncPolicy.automated` with `prune` and `selfHeal`). The Application has two sources:

1. **The Helm chart.** `repoURL: https://github.com/mctlhq/mctl-api.git`, `targetRevision: main`,
   `path: helm`, with the service values inline as a `helm.values: |` block string. In that block:
   - lines 43-45: `image.repository: ghcr.io/mctlhq/mctl-api`, `tag: "4.154.0"`;
   - lines 54 onward: the `env:` map (`ROLLOUT_MARKER`, `GITOPS_*`, ...);
   - `envFromSecret: mctl-api-secrets` (line 377) and `envFromExtraSecret: mctl-api-events` (line 381);
   - `envFromOptionalSecrets` (line 393): `mctl-api-zitadel-hook`, `mctl-api-orchestrator-devloop`, and,
     conditionally, `mctl-api-security-code-scanning`.

   The block also contains Helm control lines (`{{- if (default dict .Values.securityCodeScanning).receiver
   }}`, lines 402-404, 469-570), and line 646 is `server: {{ .Values.spec.destination.server }}`. The raw
   file is therefore not plain YAML. `yaml.safe_load` of it is not a reliable reader, and
   `release-gate.py`'s `_dig(doc, "image.tag")` cannot reach the tag.
2. **The platform manifests.** `repoURL` mctl-gitops, `targetRevision: main`,
   `path: platform-gitops/infra-components/mctl-platform/mctl-api`.

The `envFrom` Secrets come from ExternalSecrets in the bootstrap chart
(`bootstrap/templates/mctl-platform/mctl-api-secrets.yaml` and `mctl-api-*.yaml`). Each uses an explicit
`data[].secretKey` list, and no `dataFrom` appears in any `mctl-api-*.yaml` (grep). A new environment name
from Vault therefore needs a git change to one of these files. The exceptions are
`mctl-api-zitadel-hook` and `mctl-api-orchestrator-devloop`. Those Secrets are written by the zitadel-iac
Job (`helm-charts/zitadel-iac/iac/*.tf`) and are `ignoreDifferences`-ed on `/data`, so their keys are
decided by Terraform in git and then by a Job at runtime.

### The direct-write workflows

`.github/workflows/release-deploy.yaml` runs these jobs in order:

1. **`validate-inputs`** checks input shape and an `ALLOWED_PREFIXES` list that includes
   `platform-gitops/bootstrap/templates/mctl-platform/`.
2. **`preflight`** runs `scripts/release-preflight.py preflight` from `main`. It checks
   `release-bindings.yaml` (`ghcr.io/mctlhq/mctl-api: mctlhq/mctl-api`), ref/tag fit and the release gate.
3. **`build`** calls `build-image.yaml`, which pushes the image to GHCR.
4. **`bump`** runs in `environment: gitops-bump`, checks out `main` with `ssh-key:
   secrets.GITOPS_BUMP_DEPLOY_KEY`, and does two things:
   - The embedded "Bump image tag(s)" Python calls `scripts/release-gate.py check --files ... --new-tag`
     before writing. It then rewrites the tag with regex Pattern 1
     (`repository: <image>\n\s+tag: <old>`), which is the pattern that matches the bootstrap file.
   - "Commit and push" calls `release_gate()` (`release-gate.py verify`) before each of 5
     `git push` / `git pull --rebase origin main` attempts.

`.github/workflows/gitops-bump.yaml` is bump-only. It has the same `gitops-bump` environment and deploy
key, global `concurrency: gitops-bump`, the same `release-gate.py check` (line 234) and a `verify` + `git
push` loop (lines 398-399). It has no preflight: the release bindings are not checked, the image is not
checked to exist, and no digest is read.

### The existing release gate

`scripts/release-gate.py` has `check`, `verify`, `diff` and `--selftest`. Exit 6 means refused and 7 means
unknown. It reads `platform-gitops/release-gates.yaml`, which has one gate, `mctl-agents-workers` (three
`services/admins/mctl-agents-worker*/values.yaml`, `min_tag: "1.117.0"`). Its model is "a group of flat
values files whose top-level `image.tag` moves together". `diff` reads policy from the parent commit and
compares parsed content minus `image.tag`. Its call sites are:

- the bump step and push loop of both workflows;
- `release-preflight.py`;
- `validate-manifests.yml` (lines 580-592: selftest, verify, `tests/test_release_gate*.py`);
- `release-gate-watch.yml` (on push, `diff --base $BEFORE --head $SHA` and `verify`, with Telegram on
  violation or unknown; the file says it is "a detector, not enforcement").

`platform-gitops/argo-workflows/scripts/release-gate-guard.sh` is the yq/sh twin used by the shared Argo
templates. Its `valid_gated_path` accepts only `platform-gitops/services/*/*/values.yaml`.

### Merge path

`.github/workflows/auto-merge.yml` merges `claude/*` and `portal-allowlist/*` PRs on any approved review.
Its `protected_re` (line 71) holds `release-gate.py`, `release-gates.yaml`, the bump workflows and others
back for a human merge. It does **not** include `bootstrap/templates/mctl-platform/mctl-api.yaml`.
`.github/CODEOWNERS` routes review but does not enforce it (`require_code_owner_review: false`; one account
has write access).

### Admission

`platform-gitops/bootstrap/templates/system/admission-policies.yaml` already ships
ValidatingAdmissionPolicies (`mctl-deny-forged-workflow-labels`, `mctl-tenant-networkpolicy-allowlist`,
`mctl-deny-sa-token-externalsecrets`, `mctl-reserved-platform-hosts-ingress`). A namespace-bound policy for
`mctl-api` is therefore an established pattern.

### Release source

mctl-api's `.github/workflows/release-please.yml` (read through the GitHub API) has a `dispatch` job in
environment `app-dispatch` that runs `gh workflow run release-deploy.yaml --repo mctlhq/mctl-gitops ... -f
values_path=platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` whenever release-please
creates a release. **Merging #934 therefore triggers a direct push of 4.155.0 to production with no further
human step today.** The current `release-gate.py` would pass it, because the bootstrap file is not in any
gate.

### Write-path inventory

| # | Path | Can change prod mctl-api image/flags? | Today | Status after this design |
|---|------|---------------------------------------|-------|--------------------------|
| P1 | `release-deploy.yaml` bump job (auto-dispatched by mctl-api release-please, or manual dispatch) | yes, direct push to `main` | only `release-gate.py` (not covering this file) | KNOWN-ENFORCED (L1, L2) |
| P2 | `gitops-bump.yaml` (any holder of `actions: write` on mctl-gitops, e.g. the `mctl-gitops-dispatch` App and mctl-api's `GITOPS_ACTIONS_TOKEN`) | yes, direct push | same | KNOWN-ENFORCED (L1, L2) |
| P3 | Human PR to `main` | yes | review only | KNOWN-ENFORCED (L3) |
| P4 | `claude/*` PR auto-merged on bot approval | yes | not protected | KNOWN-ENFORCED (L3 + `protected_re`) |
| P5 | Argo `wft-deploy-service`, `wft-rollback-service`, `tpl-git-commit` | no: paths built as `platform-gitops/services/${TEAM}/${COMPONENT}/values.yaml` (wft-deploy-service.yaml:399, wft-rollback-service.yaml:131, tpl-git-commit.yaml:342-345) | n/a | KNOWN-NOT-A-PATH (kept honest by L4, L5) |
| P6 | mctl-agents CWFT `commit-and-push` steps (deploy-key push to `main`) | the credential can push any path; template code scopes `git add` to `agents-state/**` | template guard only | KNOWN, residual: L4 enforces, L5 detects |
| P7 | Chart `targetRevision: main` of mctl-api `helm/` | yes, with no GitOps write (defaults, new templates) | none | BLOCKING-UNKNOWN until pinned (task 6); L4 covers image/env |
| P8 | Argo CD UI/CLI sync with parameter override, `kubectl set image/env`, by cluster admins | yes | `selfHeal` reverts drift but not a disabled auto-sync | BLOCKING-UNKNOWN; L4 denies image/env; deleting the admission policy itself needs cluster-admin |
| P9 | Runtime Secret keys from zitadel-iac Job (`envFromOptionalSecrets`) | yes, via `envFrom` | none | KNOWN-ENFORCED in git (L1-L3 scan `helm-charts/zitadel-iac/iac/`), L4 Secret rule |
| P10 | Vault value change on an existing `secretKey` | changes values only, not env names | n/a | KNOWN-NOT-A-PATH for new flag names; values of the four keys are covered by L4 |

### Deployed state checked

- **`mctl_get_service_status(admins, mctl-api)`** returned `argocd.name=admins-mctl-api`, `health=Healthy`,
  `syncStatus=Synced`, `project=platform`, `updatedAt=2026-11-09T01:14:09Z`, `revision=""` (empty: the synced
  revision was not reported), and `service=null`. The service is not in the tenant catalogue.
- **`mctl_get_service_pods(admins, mctl-api)`** returned the error "service not found: mctl-api (workspace
  admins)". The running image digest, pod env and replica count were **not observed**.
- **`$MCTL_GITOPS_ROOT/services/admins/`** has no `mctl-api` directory, as expected for a bootstrap
  Application. The deployed config is the bootstrap file in the clone (tag `4.154.0`, no `MCTL_BRIDGE_*`, no
  `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`; grep of the whole repo outside `agents-state/` found none).
- **`gh pr view 934 -R mctlhq/mctl-api`** returned `chore(main): release 4.155.0`, OPEN, `isDraft: true`,
  head `e818c114e59ab67be7729785af51bdf38a1e5259`.
- **`gh api repos/mctlhq/mctl-api/git/refs/tags/4.155.0`** returned 404: the tag does not exist. The latest
  releases are 4.154.0, 4.153.0 and 4.152.0 (2026-11-03).
- **`gh api .../contents/helm/values.yaml`** on mctl-api `main` has no Bridge or queue key today. The
  templates are `deployment.yaml`, `ingress.yaml`, `service.yaml` and `serviceaccount.yaml`. This is
  point-in-time only, because the source tracks `main` (P7).

## Proposed solution

Option B: a narrow, dedicated hold guard. It shares policy data, reuses the existing release-gate call
sites, and adds an admission layer at the point of deployment effect. It has five layers, and no single
layer is trusted alone.

### 1. Policy and grant data (new, reviewed-only files)

`platform-gitops/release-holds.yaml`:

```yaml
holds:
  - name: mctl-api-4.155
    issue: mctlhq/mctl-gitops#2528
    release: mctlhq/mctl-api#934
    image: ghcr.io/mctlhq/mctl-api
    target: platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
    max_ungranted_tag: "4.154.0"        # every SemVer tag above this is held
    owners:                              # who may issue a grant (login + numeric id)
      - {login: <owner-login>, id: <numeric-id>}   # filled by the owner in the implementation PR
    guarded:                             # files that can change image, env or envFrom keys
      - platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
      - platform-gitops/bootstrap/templates/mctl-platform/mctl-api-*.yaml
      - platform-gitops/infra-components/mctl-platform/mctl-api/**
      - platform-gitops/helm-charts/zitadel-iac/iac/**
      - platform-gitops/bootstrap/templates/system/admission-policies.yaml
    runtime_keys:
      forbidden: [MCTL_BRIDGE_PROVIDERS, MCTL_BRIDGE_PROVIDER_TOKENS]
      absent_or_false: [MCTL_BRIDGE_ENABLED, MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE]
    chart_pin_required: true
```

`platform-gitops/release-grants/mctl-api/<tag>.yaml`. One file per tag, immutable once merged; `diff`
refuses any modification of an existing grant:

```yaml
grant:
  kind: release                 # `activation` is a separate kind, never issued by this work
  hold: mctl-api-4.155
  image: ghcr.io/mctlhq/mctl-api
  tag: "4.155.0"
  digest: "sha256:<64 hex>"     # GHCR manifest digest the owner reviewed (SBOM/provenance attached to it)
  source_commit: "<40 hex>"     # mctl-api commit the tag points at
  policy_sha256: "<64 hex>"     # sha256 of release-holds.yaml bytes the grant was issued against
  owner: {login: <login>, id: <numeric-id>}
  issued_at: "2026-..Z"
  expires_at: "2026-..Z"        # at most 7 days after issued_at
  channel: pull-request         # or `direct`; #2523 requires pull-request
  prerequisites:                # evidence links; presence checked, content judged by the owner
    part_m: mctlhq/mctl-agents#993 <link>
    part_s: "#992 <link>"
    b4: mctlhq/mctl-agents#1007 <link>
    drain: mctlhq/mctl-api#935 <link>
    reviewer_gate: mctlhq/mctl-gitops#1040 <link>
```

A grant is valid only if **all** of these hold:

1. The schema is valid and every field has the exact shape. `expires_at` is in the future and at most 7
   days after `issued_at`.
2. `policy_sha256` equals the sha256 of `release-holds.yaml` in the **policy tree** (defined below).
3. `owner` is in `holds[].owners`.
4. The commit that added the grant (`git log --diff-filter=A -- <grant>` on the policy tree) is associated
   with a merged PR. `GET /repos/mctlhq/mctl-gitops/commits/<sha>/pulls` must show `merged_by.login ==
   owner.login`, `merged_by.id == owner.id` and `merged_by.type == "User"`. The grant PR touches only
   `release-grants/**`.
5. `GET /repos/mctlhq/mctl-api/git/ref/tags/<tag>`, dereferenced to the commit, equals `source_commit`.
6. The GHCR manifest digest of `<image>:<tag>` (`docker buildx imagetools inspect --format
   '{{json .Manifest}}'` or the registry API) equals `digest`.

Any API, registry or git error means exit 7, which refuses. This is the "digest/head-bound, explicit
identity, expiry" grant. Nothing parses PR comments, check runs or CI status.

### 2. `scripts/release-hold.py` (new; same contract as `release-gate.py`)

It has `check --files F... --new-tag T`, `verify`, `diff --base B --head H` and `--selftest`. Exit 0 means
pass, 6 refused and 7 unknown.

**Reading the inline values.** The reader locates the Application's first `sources[]` item whose
`repoURL` is `https://github.com/mctlhq/mctl-api.git` by line scanning. It takes the `values: |` block
scalar by indentation, drops lines that are only a Helm action (`^\s*\{\{-?.*-?\}\}\s*$`), and
`yaml.safe_load`s the remainder. It also extracts that source's `targetRevision`. Any ambiguity is exit 7:
zero or more than one such source, zero or more than one `image.repository: ghcr.io/mctlhq/mctl-api`
match, or a parse failure. A tests-only cross-check renders the file with `helm template` on the bootstrap
chart and asserts the reader returns the same image, tag and env (task 9), so the line reader cannot
silently drift from Helm.

**Rules** (all evaluated; every problem is reported):

- **Tag.** `image.tag` is SemVer (reusing `_semver` semantics: ASCII, no leading zeros). If it is above
  `max_ungranted_tag`, a valid grant for exactly that tag is required. In `check` and `verify` (the
  direct-write workflows) a held tag additionally requires `grant.channel == direct`. The workflows pass
  `--channel direct`, and `diff` in a PR uses `--channel pull-request`.
- **Runtime keys.** Across the parsed values (recursive: `env`, `extraEnv`, any list or map), a
  `forbidden` key name anywhere is refused. An `absent_or_false` key may only appear as `env.<KEY>: "false"`.
  In every other guarded file, which is raw text (ExternalSecret `secretKey`, Terraform, manifests), any
  occurrence of a forbidden or absent_or_false key name is refused. The activation grant kind is
  recognised only so that it is refused with "activation grants are not accepted by release-hold".
- **Chart pin.** The chart `targetRevision` must be a 40-hex SHA or a SemVer tag, never `main`, `HEAD` or
  a branch.
- **Unreadable inputs.** A hold file, grant directory or target that is absent or unreadable is exit 7.

**`diff` (merge path and watch).** The **policy tree** is `base`. The script reads `release-holds.yaml`
and `release-grants/**` from `base` only, and evaluates `head`'s guarded files against them. It also
refuses:

- a `head` that edits or removes an existing grant or the hold;
- a PR that changes `release-holds.yaml` or adds a grant together with any guarded file. The grant merges
  first, and the bump is a separate PR that sees it in `base`.

The script reports such changes as `HOLD_POLICY_CHANGED`. That is a refusal for automation, so a human
admin-merge is the only way to change the hold.

**Monotonic check (TOCTOU).** `verify --since <start-sha>` also loads the hold policy at `<start-sha>`.
It refuses when, for the target, the hold at `<start-sha>` is stricter than the hold in the tree being
pushed (removed, higher `max_ungranted_tag`, fewer keys, `chart_pin_required` dropped). A rebase onto a
newer `main` that relaxed the hold therefore aborts the run; it never pushes under the weaker policy. A
fresh dispatch then starts under the new reviewed policy, which is the intended way to pick it up.

### 3. Call sites (point of write)

- **`release-deploy.yaml` `bump` and `gitops-bump.yaml` `bump`.** The embedded script runs
  `scripts/release-hold.py check --channel direct --files ... --new-tag "$NEW_TAG"` right after the
  existing `release-gate.py check` and before any `open(path, 'w')`. A non-zero exit means `sys.exit(6)`.
  "Commit and push" records `START_SHA=$(git rev-parse HEAD)` before the bump, and `release_gate()` gains
  `python3 scripts/release-hold.py verify --channel direct --since "$START_SHA"`. That runs before
  **every** `git push` attempt, including after each `git pull --rebase`. A push is a fast-forward or it
  is rejected, so the tree pushed is always the tree verified (the property the existing comment already
  relies on).
- **`release-preflight.py preflight`.** For a held image it calls `release-hold.py check` in an advisory
  mode and emits `::notice::held tag: build allowed, bump will refuse without a direct-channel grant`.
  This mode never fails the build, because the grant needs the built digest. `publish` keeps refusing to
  replace an existing tag (exit 10), so a held tag is built exactly once.
- **`release-gate.py`.** Unchanged. The worker gate is out of scope and keeps its own semantics.
- **`release-gate-guard.sh` (Argo).** Unchanged. P5 cannot address the bootstrap file. A regression test
  asserts that the Argo templates still construct only `platform-gitops/services/` paths.

### 4. Merge path

- **`validate-manifests.yml`.** It runs `release-hold.py --selftest`, `verify` on the PR head (policy
  from the head is fine for verify), and `diff --base "$(git merge-base origin/main HEAD)" --head HEAD
  --channel pull-request`. The job is part of the required checks.
- **`auto-merge.yml` `protected_re`.** It gains `^platform-gitops/release-holds\.yaml$`,
  `^platform-gitops/release-grants/`, `^scripts/release-hold\.py$`,
  `^platform-gitops/bootstrap/templates/mctl-platform/mctl-api[^/]*\.yaml$`,
  `^platform-gitops/infra-components/mctl-platform/mctl-api/`, `^platform-gitops/helm-charts/zitadel-iac/iac/`,
  `^platform-gitops/bootstrap/templates/system/admission-policies\.yaml$` and
  `^tests/test_release_hold[a-z_]*\.py$`. `tests/test_auto_merge_protected_paths.py` is updated.

### 5. Point of deployment effect (admission)

A new ValidatingAdmissionPolicy `mctl-api-release-hold` is added to `admission-policies.yaml`, bound with
a `namespaceSelector` on `kubernetes.io/metadata.name: mctl-api`. Its param is a ConfigMap
`mctl-api-release-hold` in `kube-system`, rendered in the bootstrap chart from `release-holds.yaml` plus
valid grants. The ConfigMap is itself a guarded file. The policy covers:

- **`apps/v1 Deployment`, `ReplicaSet` and `v1 Pod` (CREATE, UPDATE).** For every container and
  initContainer whose image starts with `ghcr.io/mctlhq/mctl-api`, the tag (or `@digest`) must be in
  `params.data.allowed` (`4.154.0`, plus granted `tag` and `digest`). `env[].name` must not be in
  `forbidden`. For `absent_or_false`, `env[].value` must be `"false"` when present, and `valueFrom` is
  refused.
- **`v1 Secret` (CREATE, UPDATE).** `data` and `stringData` keys must not include `forbidden`, or
  `MCTL_BRIDGE_ENABLED` with a value other than `"false"`. This covers `envFrom` from Job-written Secrets
  (P9) and ExternalSecret outputs.
- **Rollout.** The policy starts with `validationActions: [Warn, Audit]`. A separate PR switches it to
  `[Deny]` after one sync with no warnings. `failurePolicy: Fail`, and a param that is not found means
  deny (`paramNotFoundAction: Deny`), so an unreadable policy is a refusal.

Admission sees what Argo CD actually applies. It therefore also covers P6, P7 (image and env) and P8
(`kubectl`, Argo CD parameter overrides). Its residual is a cluster-admin deleting the binding. root-app
`selfHeal` recreates it, but a cluster-admin can disable that too, which is recorded as BLOCKING-UNKNOWN
for the owner.

### 6. Chart pin

`targetRevision: main` on the chart source becomes the commit SHA of mctl-api `4.154.0`. It is resolved
in the implementation PR from `git ls-remote https://github.com/mctlhq/mctl-api refs/tags/4.154.0^{}`,
and the result goes in the PR body. The bump scripts are **not** taught to move it: a granted bump PR moves
image tag and chart SHA together (`verify` asserts the chart SHA equals the grant's `source_commit` for a
held tag). This removes P7's silent path. Leaving the chart on `main` during the hold is refused by
`chart_pin_required`.

### 7. Detection

`release-gate-watch.yml` adds a `release-hold.py diff --base $BEFORE --head $SHA --channel direct` step
and a `verify` step, both feeding the existing Telegram notifications (violation versus could-not-run). It
stays a detector.

### Resulting flow for 4.155.0 (described, not executed)

1. The owner un-drafts and merges #934. Tag 4.155.0 is created, and release-please dispatches
   release-deploy. Preflight issues a notice, the build pushes the image, and the bump refuses: there is no
   grant, the tag is held, and the channel is direct. Nothing is written.
2. The owner reviews the digest, SBOM, provenance and the #2523 evidence. The owner opens and merges
   (personally, as `User`) a PR that adds only `release-grants/mctl-api/4.155.0.yaml`, with
   `channel: pull-request`.
3. A bump PR changes `tag` to `"4.155.0"` and the chart SHA to `source_commit`, nothing else. `diff` reads
   the grant from `base`, checks the GHCR digest, tag ref and merger, and passes. A human merges it.
4. Admission allows the granted digest. Any env drift is denied.

### Dependencies

- **mctl-api#934:** the held release. Not touched.
- **mctl-gitops#2523:** consumes this design. This design is what makes its rules "PR-only bump" and
  "Bridge dark" machine-enforced, and its evidence checklist populates `grant.prerequisites`.
- **mctl-agents#993 (Part M), #992 (Part S), mctl-agents#1007 (B4), mctl-api#935 (drain):** prerequisites
  of the owner GO, recorded in the grant. They are not evaluated by machine; the owner's identity-bound
  merge is the decision.
- **#1040 reviewer aggregate gate:** linked in `prerequisites.reviewer_gate`. Its required status is not
  treated as a GO.
- **#1292 release signal watcher:** may consume the hold-violation alert. No duplicate watcher is built.

## Alternatives

- **(A) Extend `release-gate.py` and `release-gates.yaml`.** This reuses every call site, but its data
  model is "flat values files, top-level `image.tag`, a group of equal tags, `min_tag` floor". The
  bootstrap file needs a Helm-template-aware reader, a ceiling plus grant instead of a floor, runtime-key
  rules across several file types, and GitHub/GHCR reads. Folding that into the worker gate raises the
  risk to the mctl-agents rollout (#1007), and its `diff` compares content minus `image.tag`, which is
  wrong for files where env changes are legal. Rejected; the call sites are reused instead.
- **(C) A gate only in `release-deploy.yaml`.** This misses P2 (gitops-bump), P3, P4 (auto-merge), P6, P7
  and P8. It is the coverage gap the issue warns about. Rejected.
- **(D) Admission only.** This is strong at the point of effect, but a refused Deployment update leaves
  `main` claiming 4.155.0 while production runs 4.154.0. Argo then retries the sync forever, and git stops
  being the truth. It also cannot see chart-default drift in non-env templates (for example, a new
  dispatcher Deployment with a different image). Kept as layer L4, not as the only layer.
- **Making `gitops-bump`/`release-deploy` refuse the bootstrap path entirely.** This is simple, but it
  also blocks ordinary non-held operations on mctl-portal and mctl-agent in the same directory, and gives
  no granted path. Rejected in favour of scoping by image plus hold.

## Platform impact

- **Migrations.** These are new files: `release-holds.yaml`, `release-grants/`, `scripts/release-hold.py`,
  tests, and the admission policy plus ConfigMap. Existing workflows gain a step each. No data migration.
- **Backward compatibility.** Services other than mctl-api are unaffected. The hold matches by image, and
  a test proves an ordinary bump still lands. Non-image edits to `mctl-api.yaml` (for example
  `ROLLOUT_MARKER`, resources) still pass, but now need a human merge (`protected_re`). mctl-api releases
  of 4.155.0 and **every later tag** are blocked until granted. That is intended: later tags contain the
  held code.
- **Resource impact.** There are a few GitHub API and registry reads per bump, and admission CEL cost is
  negligible.
- **Risks and mitigations.**
  - **An admission policy bug blocks mctl-api pod restarts (outage).** Mitigations: Warn/Audit first,
    allowlist seeded with the running `4.154.0`, the Deny switch as a separate PR, and rollback by deleting
    the binding through a reviewed PR (root-app syncs it).
  - **An unreadable GHCR digest blocks all held bumps.** This is fail-closed by design. It is recorded as
    an open question so that the read credential is decided before a grant is needed.
  - **The line-based values reader drifts from Helm.** Mitigations: exit 7 on any ambiguity, and the
    `helm template` cross-check test.
  - **The chart pin delays mctl-api chart fixes.** Chart changes need an explicit SHA bump PR during the
    hold. This is accepted as the cost of closing P7.
  - **A single write-access account means the owner both merges and is checked as merger.** The grant
    binds that identity explicitly. Independent review stays a human process, per the issue's gate, and is
    not claimed as machine-enforced.

## Open questions

- **P8 (out-of-band cluster-admin).** This is BLOCKING-UNKNOWN. The owner either accepts it as residual,
  with the admission policy plus `selfHeal`, or supplies Argo CD RBAC and cluster-admin membership evidence.
- **GHCR digest readability** from the bump jobs and from `validate-manifests.yml`: not observed.
- **Running image digest and pod env** were not observed (`mctl_get_service_pods` failed), so the
  admission allowlist is seeded from git (`4.154.0`), not from a live digest. The implementation PR must
  read the live digest before the Deny switch.
- Whether to digest-pin the bootstrap tag (`tag: "<v>@sha256:..."`) depends on the mctl-api chart's image
  template.
- Whether the "2026-11-03" in the issue is a hold date or an intended expiry. This design treats it as
  never-expiring.
- Whether the raw-text key scan of non-values guarded files should strip comments.
