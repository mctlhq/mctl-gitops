# Design: issue-2528-security-release-enforce-mctl-api-4-155

## Binding reconciliation amendment (2026-11-11, R0 packet #2602)

This section supersedes conflicting baseline claims, paths and task instructions
below. All existing security requirements, three P2 findings, grant provenance,
trusted-base checking, merge/effect-time revalidation, admission, negative tests
and separate owner/operator approvals remain required. This amendment is not
implementation, grant acceptance, release GO or residual-risk acceptance.

At mctl-gitops `5f10a8c2750408320162d13628e35bdd8ca6bf53`:
- #2590 already provides the bootstrap reader and `version_holds` in
  `scripts/release-gate.py`; the mctl-api hold has `allow: []`.
- #2595/#2596 route mctl-api bumps through PRs; they do not remove the wildcard
  DeployKey bypass or prove the first live routed bump.
- #2597 stamps the resolved source revision in the build image label.
- #2599 pins the chart to `a5b9ef9cf0f880f28b841033a8b2a6d9563ce050`, preserving
  the live `/devloop` path. Do not repin it to the 4.154.0 chart commit.
- #2591 removed the orchestrator identity envFrom entry. Other env injection
  paths still need verification; no Secret payload reads are permitted.

Extend the EXISTING gate and reader; do not create `release-hold.py`, a second
policy file (`release-holds.yaml`), or a second set of release grant records.
Keep `platform-gitops/release-gates.yaml` as policy and its `version_holds[].allow`
as the grant-record location. Leave `allow: []` until separately authorized.
New held-version allow records must additionally bind `digest`, `source_commit`,
`source_tree`, `reviewed_release_head` and `policy_digest`; verify the existing
`grant`, `approved_by` and expiry against actual owner approval and provenance.
The exact timestamp migration must preserve the rule that expiry gates new
writes/merges, not later pod restarts or unrelated releases of deployed state.

All earlier `release-hold.py` command references mean the corresponding existing
`release-gate.py` command extended with the same security semantics. Preserve
`check`, `verify`, `diff`, `--policy-rev` and existing worker gate behavior.
Checker/merger workflows must load the extended gate and policy from the trusted
base; PR-head scripts are data only. Guard the gate, reader, tests, policy,
workflow and allow-record changes as policy changes. Re-read external evidence
at merge and before every publish attempt; an unreadable source refuses effect.
Image tag and chart pin move together in a reviewed, authorized release PR.
The first live App-authored bump and final-head review remain unproven.

Admission parameters use the static, validated allowlist of the amended design,
not unverified Helm rendering from grant strings. No change to #2543 authority:
DeployKey and cluster-admin residuals require separate explicit dispositions.
The canonical coordination packet is
`docs/plans/mctl-api-4-155-release-readiness.md`; this proposal remains the
implementation specification. Any amendment changes the content digest and
requires fresh independent review and a fresh digest-bound human grant.


Decision: `READY_FOR_SEPARATE_IMPLEMENTATION_PROPOSAL`. The design below closes every source-verified write
path. Two items stay BLOCKING-UNKNOWN until the owner disposes of them: chart drift until the pin lands,
and out-of-band cluster-admin actions. The 2026-11-11 amendment adds a third: any holder of a write deploy key
(P5b, P6) can bypass the CI layers until mctl-gitops#2543 narrows the ruleset bypass. While any item is
BLOCKING-UNKNOWN the hold stays in force. This document is not a release approval.

## Amendment 2026-11-11 (independent review AMEND, three P2)

The independent pre-approval review of 2026-11-09 (mctl-gitops#2528 comment 6740255964, read at `8a783fe9`)
returned **AMEND** with three P2 findings and one P3. On 2026-11-11 the owner directed that the three P2 be
fixed in this canonical proposal before any digest-bound approval (mctl-gitops#2523 comment 6783446919,
#2528 comment 6783453619, mctl-api#934 comment 6783454374). Implementation stays blocked until an
independent review of this amended text and a separate owner approval bound to its content digest.

Facts re-read on 2026-11-11 for this amendment (read-only; no value of any credential was read):

- `gh api repos/mctlhq/mctl-gitops/keys` lists two write (non-read-only) deploy keys: `gitops-bump`
  (id 165489378, last used 2026-11-10T00:44Z) and `argo-workflows-bot-2026-10` (id 166128843, last used
  2026-11-09T06:24Z).
- Ruleset 18465404 (`refs/heads/main`, active) has exactly one bypass actor,
  `{"actor_type":"DeployKey","actor_id":null,"bypass_mode":"always"}`. `actor_id: null` matches **every**
  deploy key, so both keys above can push any path to `main` (#2543, P1). No role or admin entry is
  present: the only "always" bypass is this deploy-key class. The ruleset has
  `strict_required_status_checks_policy: false` and the required contexts `validate`, `reserved-hosts` and
  `cloudflare-plan`, all bound to integration 15368 (GitHub Actions). Classic branch protection on `main`
  has `enforce_admins: false` and no review or status rule, so it adds nothing to the ruleset.
- Environment `gitops-bump` has one branch policy (`main`) and `can_admins_bypass: true`. It releases
  `GITOPS_BUMP_DEPLOY_KEY` to **any** job on `main` that names the environment, not only to
  `release-deploy.yaml` and `gitops-bump.yaml`.
- `validate-manifests.yml` runs on `pull_request` and on push to `main`. On `pull_request`, both the workflow
  definition and the checked-out code come from the PR merge ref.
- `platform-gitops/release-gates.yaml` still covers only `mctl-agents-workers`, and `release-gate.py` reads a
  top-level `image.tag`. The mctl-api bootstrap file keeps its values inside a `values: |` block scalar, so
  adding an mctl-api entry to `release-gates.yaml` would not work. A bootstrap-aware reader is being built in a
  separate PR by another agent. This proposal consumes that reader as the `release-hold.py` values reader
  (§2) and does not re-specify it.
- mctl-api#934 is still Draft, head `6241d5c81a4c7ef849c8aae85c7807be3ad4a945`, base
  `081bd6b7dcdb688a329497c02b4323be421a0bac`. The heads recorded earlier (`e818c114` in this design,
  `5b76cbc3` in the 2026-11-09 #2528 note) are stale. mctl-api allows merge commits only
  (`allow_squash_merge: false`, `allow_rebase_merge: false`).
- mctl-api `helm/templates/deployment.yaml` on `main` renders
  `image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"` (line 29) and the label
  `app.kubernetes.io/version: {{ .Values.image.tag | quote }}` (line 7). A value
  `tag: "4.155.0@sha256:..."` would produce an invalid label value (`@` and `:` are not allowed in label
  values). The bootstrap file therefore **cannot** be digest-pinned through `image.tag` with this chart.
- `build-image.yaml` sets no `org.opencontainers.image.revision` label and produces no provenance
  attestation (grep for `attest`, `provenance` and `labels` finds none). Nothing machine-readable links a
  GHCR digest to the source commit it was built from.
- The only machine-readable release hold in the org is mctl-agents `.github/release/hold.json`
  (`"hold": true`, read by mctl-agents `release-please.yml` through `check_hold.py`). It governs
  mctl-agents releases only. Nothing on any mctl-gitops write path reads it. The 2026-11-03 mctl-api hold
  exists only as #934's Draft state and its comments.

| Finding | Fix | Where |
|---|---|---|
| **P2-1** A second bypass-capable write key is missing, and P5 was rated KNOWN-NOT-A-PATH on template code alone | P5 is split into P5a (template code: paths are built under `services/`) and P5b (the `argo-workflows-bot-2026-10` credential, which can push any path). P5b and P6 are BLOCKING-UNKNOWN until #2543 narrows the bypass. The hold counts as enforced against deploy-key holders only after that, or after the owner accepts the residual in writing. New row P11: any workflow on `main` that names the `gitops-bump` environment gets that key. The admission parameter is no longer rendered by Helm from grant files. It is a static allowlist file that `release-hold.py` validates like any guarded file, and a grant or allowlist pushed directly fails the merger check | "Write-path inventory", §1 checks 4 and 7-8, §5, §8 |
| **P2-2** The PR guard runs code the PR controls, and the required context `validate` can come from a workflow the PR edits | The PR-time hold check moves to `release-hold-pr.yml` on `pull_request_target`. Its definition and script come from the base, and the PR head is read only as git data: never executed or imported. The result is posted as check `release-hold` by a dedicated checker App, and the ruleset requires `release-hold` bound to that App's integration id, so no job defined in a PR can satisfy it. Changes to the guard, the policy, the workflows or the tests count as policy changes | §4 |
| **P2-3** No re-verification at merge or effect | Guarded changes merge only through `release-hold-merge.yml`: `workflow_dispatch` on `main`, environment with the owner as required reviewer. It re-runs `diff` against the current `main` tip and the exact head SHA, requires an expiry margin, and merges with `sha=<head>`. The ruleset gains `strict_required_status_checks_policy: true`. Both direct-write workflows re-read the grant, digest, tag ref and clock immediately before **every** `git push` and fail closed. A post-sync verifier compares the running image digests with the grant | §3, §4, §5, §7 |
| **P3** Stale #934 head; admission ignores `expires_at`; inventory rows missing | Head re-read (above). The grant now binds the source commit, its tree and the reviewed release head (§1a). Expiry bounds the merge and push window: it is enforced there, and deliberately not at admission (§5). Rows P13 and P14 are added | §1a, §5, inventory |

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
| P5a | Argo `wft-deploy-service`, `wft-rollback-service`, `tpl-git-commit` **as written** | no: paths built as `platform-gitops/services/${TEAM}/${COMPONENT}/values.yaml` (wft-deploy-service.yaml:399, wft-rollback-service.yaml:131, tpl-git-commit.yaml:342-345) | n/a | KNOWN-NOT-A-PATH for the template code (T14 keeps it honest) |
| P5b | Write deploy key `argo-workflows-bot-2026-10` (id 166128843; Secret `argo-workflows/mctl-gitops-deploy-key`, with copies in tenant namespaces per the #2543 phase-1 inventory) used **outside** the template code: any template step, pod or principal that can use the key | yes: the ruleset bypass (`DeployKey`, `actor_id: null`, `always`) lets it push any path to `main`, including the bootstrap tag, `release-holds.yaml`, a grant and the admission allowlist, with no PR and no required check | none | **BLOCKING-UNKNOWN** until #2543. L1-L4 do not stop this writer, because it can change the guarded file and the allowlist in one commit. L5 detects it (a direct-pushed grant fails check 4). See §8 |
| P6 | mctl-agents CWFT `commit-and-push` steps (deploy-key push to `main`) | the credential can push any path; template code scopes `git add` to `agents-state/**` | template guard only | **BLOCKING-UNKNOWN** with P5b (same credential class); L5 detects |
| P11 | Any workflow file on `main` other than the two bump workflows that names `environment: gitops-bump` and so receives `GITOPS_BUMP_DEPLOY_KEY` (id 165489378) | yes: direct push with no `release-hold.py` call | branch policy `main` only | KNOWN-ENFORCED by a static test (T21) plus `protected_re` on `.github/workflows/`; L5 detects |
| P12 | The required context `validate` (integration 15368), which a PR can satisfy by defining its own job with that name | yes, as a merge gate | none | KNOWN-ENFORCED by the App-bound `release-hold` context (§4); `validate` is no longer relied on for the hold |
| P13 | `portal-allowlist-vendor.yml` (App token, environment `app-gitops-pr`; pushes a `portal-allowlist/*` branch, opens a PR, auto-merge) | no direct `main` write; it stages only `infrastructure/cloudflare/portal/allowlists/*` | auto-merge classification | KNOWN-NOT-A-PATH for direct writes; a PR touching guarded files is held by `protected_re` and by `release-hold` |
| P14 | `cloudflare-drift.yml` (environment `app-gitops-pr`; PR-based) | no direct `main` write | PR flow | KNOWN-NOT-A-PATH for direct writes; same PR controls as P13 |
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
  head `e818c114e59ab67be7729785af51bdf38a1e5259` on 2026-11-09. Re-read on 2026-11-11: head
  `6241d5c81a4c7ef849c8aae85c7807be3ad4a945` (see the amendment; any head is evidence for that head only).
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
  source_commit: "<40 hex>"     # mctl-api commit the tag points at (the merge commit of the release PR), never the PR head
  source_tree: "<40 hex>"       # git tree of source_commit
  reviewed_release_head: "<40 hex>"  # commit whose full content the reviews and compatibility evidence covered
  build_run: "<run id>"         # release-deploy run that built `digest` (audit evidence only; never replaces check 8)
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
7. In a read-only fetch of mctl-api, `source_commit^{tree}` equals `source_tree`, and
   `reviewed_release_head^{tree}` equals `source_tree` (§1a).
8. The image config of `digest` carries the label `org.opencontainers.image.revision` equal to
   `source_commit`. A missing label is exit 7 (task 13 adds the label to `build-image.yaml`).

Any API, registry or git error means exit 7, which refuses. This is the "digest/head-bound, explicit
identity, expiry" grant. Nothing parses PR comments, check runs or CI status.

Check 4 is also what makes a grant **pushed directly** (P5b, P6, P11) invalid: a commit that reached `main`
through the deploy-key bypass has no associated merged PR, so every consumer (L1-L3 and the L5 detector)
treats that grant as absent.

### 1a. Release PR head versus source commit (amended 2026-11-11)

A release-please PR such as #934 changes only `CHANGELOG.md` and the version files. Its head is "mctl-api
`main` at the last release-please refresh, plus one release commit". What is released is everything reachable
from the tag commit: the 2026-11-11 operator audit counts about 557 changed files against 4.154.0. A review of
the release PR's diff is therefore not a review of the release. Three objects are involved:

1. **The reviewed head** (`reviewed_release_head`): the commit that the full-source reviews, the
   compatibility runs and the #2523 evidence were run against. The #934 head moves every time anything merges
   to mctl-api `main` (`2fc67f31`, `70fcec0b`, `5b76cbc3` and `6241d5c8` so far). Evidence for an earlier head
   is void.
2. **The source commit** (`source_commit`): mctl-api merges by merge commit only. Merging #934 therefore
   creates a merge commit M whose parents are the `main` tip at that moment and the #934 head. release-please
   tags M as `4.155.0` and dispatches `release-deploy.yaml` with `git_ref=4.155.0`, and `build-image.yaml`
   builds the image from M's tree. If anything merged to mctl-api `main` after the last refresh and before the
   merge, M contains code that no reviewer saw.
3. **The image digest** (`digest`): what Argo CD would pull.

The grant binds the last two, and ties them to the first by tree equality. A grant is valid only if all of
these hold: tag `4.155.0` dereferences to `source_commit`; `tree(source_commit) == source_tree ==
tree(reviewed_release_head)`; the digest's revision label equals `source_commit`; and the GHCR digest of
`:4.155.0` equals `digest`. A grant never names the PR head as the released object. An approval of the
release PR, or a green CI run on its head, is never accepted as covering M. If the trees differ, there are
only two valid moves: a new review of M itself (then `reviewed_release_head = source_commit`), or a new
release.

The implementation proves the assumption "release-please tags the merge commit" with a fixture (T18). If
that assumption turns out to be wrong, the check still works, because it compares trees, not commit
identities.

### 2. `scripts/release-hold.py` (new; same contract as `release-gate.py`)

It has `check --files F... --new-tag T`, `verify`, `diff --base B --head H` and `--selftest`. Exit 0 means
pass, 6 refused and 7 unknown.

**Reading the inline values.** (Amended 2026-11-11: the bootstrap-aware reader is delivered by the separate
gate PR mentioned in the amendment. `release-hold.py` imports that reader rather than adding a second one,
and the contract below is what it must satisfy.) The reader locates the Application's first `sources[]` item whose
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
- **Re-verification at write time (amended 2026-11-11, P2-3).** In **both** `release-deploy.yaml` and
  `gitops-bump.yaml`, `verify` is the last command before each `git push`, with nothing in between that
  can change the tree. Every attempt re-reads, with no cache across attempts: the hold and the grant from the
  tree being pushed, the GHCR digest, the tag ref, the revision label, the grant PR's merger, and the clock.
  `--expiry-margin 15m` treats a grant that expires within 15 minutes as expired. Any non-zero exit, or a
  missing or unparseable script, aborts the job before `git push`. The policy and the script are those of the
  `main` checkout the job started from (the workflows check out `ref: main`), and `--since START_SHA`
  refuses a rebase onto a weaker hold.
- **Only these two workflows may use the bump key (P11).** A test asserts that `environment: gitops-bump`
  and `GITOPS_BUMP_DEPLOY_KEY` appear in no `.github/workflows/*` file other than `release-deploy.yaml` and
  `gitops-bump.yaml` (T21). `protected_re` covers all of `.github/workflows/`, so adding a third user needs
  a human merge, and the trusted check refuses it together with guarded files.
- **`release-preflight.py preflight`.** For a held image it calls `release-hold.py check` in an advisory
  mode and emits `::notice::held tag: build allowed, bump will refuse without a direct-channel grant`.
  This mode never fails the build, because the grant needs the built digest. `publish` keeps refusing to
  replace an existing tag (exit 10), so a held tag is built exactly once.
- **`release-gate.py`.** Unchanged. The worker gate is out of scope and keeps its own semantics.
- **`release-gate-guard.sh` (Argo).** Unchanged. P5 cannot address the bootstrap file. A regression test
  asserts that the Argo templates still construct only `platform-gitops/services/` paths.

### 4. Merge path (amended 2026-11-11 for P2-2 and P2-3)

**`validate-manifests.yml` is no longer a hold gate.** It keeps `release-hold.py --selftest` and the unit
tests, because they catch bugs early. On `pull_request` they run the PR's own code, so their result is never
treated as a hold decision.

**Trusted PR-time check (P2-2): `.github/workflows/release-hold-pr.yml`.**

- Triggers: `pull_request_target` (`opened, reopened, synchronize, ready_for_review`), plus
  `workflow_dispatch` for re-checks. With `pull_request_target`, GitHub takes the workflow definition from
  the base branch, so a PR cannot change what runs.
- It checks out `github.event.pull_request.base.sha` (not the merge ref), with `persist-credentials: false`
  and `permissions: {contents: read}`, and runs `scripts/release-hold.py` and the bootstrap reader from that
  checkout. It fetches the head with `git fetch origin refs/pull/<n>/head`, which works for fork PRs as well,
  and refuses (exit 7) unless the fetched commit equals `head_sha`. It reads head files only as bytes with
  `git show <head_sha>:<path>`. Head content is never checked out into the working tree, executed, imported,
  installed, sourced, or passed to a shell or a third-party action.
- Policy and grants come from the base tree only. Changes to the guard, the policy or its tests count as
  policy changes: `scripts/release-hold.py`, the bootstrap reader module, `release-holds.yaml`,
  `release-grants/**`, the admission allowlist, `tests/test_release_hold*`, `.github/workflows/release-hold-*.yml`,
  `release-deploy.yaml`, `gitops-bump.yaml`, `validate-manifests.yml` and `auto-merge.yml`. A PR that combines
  any of these with a guarded file is refused as `HOLD_POLICY_CHANGED`. A PR that changes only policy or guard
  code reaches `main` only through a human merge (`protected_re`), and it takes effect for later PRs, never for
  itself.
- The result is posted as check run `release-hold` on `head_sha` by a dedicated **checker App** with `checks:
  write` and `metadata: read` only. Its private key is a secret of two environments, both limited to `main`:
  `release-hold-checker` (PR-time job) and `release-hold-merge` (merge job, below). It is never a secret of
  any other environment, and it is not a repository secret. The ruleset's required checks gain
  `{"context": "release-hold", "integration_id": <checker App id>}`. A job defined in a PR runs on the PR ref,
  so it cannot enter that environment, and it posts as GitHub Actions (15368). It therefore cannot satisfy the
  context. This is why adding a step to `validate` is not enough: `validate` is bound to 15368, and any PR can
  define a job with that name (P12).
- Non-guarded PRs get `release-hold` = success. A PR that changes a guarded file gets `release-hold` =
  failure with the summary "guarded change: merge through release-hold-merge", even when the change is valid.
  Only the trusted merge below turns it green. A grant-only PR (it touches only one new
  `release-grants/mctl-api/<tag>.yaml`) gets success when the file is schema-valid against the base policy.
  The owner merges it personally, because grant check 4 requires `merged_by` to be the owner as a `User`.
- If the checker App or its environment is unavailable, no success is posted and every PR is blocked. That
  is fail-closed. The break-glass is in Rollback.

**Re-verification at merge (P2-3): `.github/workflows/release-hold-merge.yml`.**

- `workflow_dispatch` on `main` only, inputs `pr` and `head_sha` (40 hex). It runs in environment
  `release-hold-merge`, which has the owner as required reviewer and `can_admins_bypass: false`. Both the
  approving reviewer (login and id from the deployment-review API) and `github.actor` must be `User`s in the
  hold's `owners`. They are recorded in the check summary and the merge commit body.
- Steps, all from the `main` checkout:
  1. Read the PR. Refuse unless it is open and non-draft, its head equals `head_sha`, and it is up to date
     (`merge-base(main, head_sha)` is the current `main` tip).
  2. Run `release-hold.py diff --base <main tip> --head <head_sha> --channel pull-request
     --expiry-margin 15m`. This re-reads the grant from `main`, the GHCR digest, the tag ref, the revision
     label and the grant PR's merger.
  3. Post `release-hold` = success on `head_sha` with a checker App token.
  4. Immediately call `PUT /repos/mctlhq/mctl-gitops/pulls/<pr>/merge` with `sha=<head_sha>` and
     `merge_method=merge`, using a **merger App** token.
- The ruleset gains `strict_required_status_checks_policy: true`. If `main` moves after step 2, GitHub then
  refuses the merge as out of date, and `sha` makes it refuse if the head moves. Either refusal writes
  nothing; the run reports, and the owner re-dispatches. The only remaining window is between steps 3 and 4
  (seconds). During that window, the verified state is still what merges.
- **Identities (amended after review round 1).** Two Apps, each with the least it needs:
  - The **checker App** (`checks: write`, `metadata: read`) posts `release-hold`. Its key lives in
    `release-hold-checker` and `release-hold-merge`.
  - The **merger App** (`contents: write`, `pull_requests: write`, `metadata: read`) only calls the merge
    API. Its key lives **only** in `release-hold-merge`, which requires the owner's approval for every run.
    It is **not** a bypass actor on any ruleset, so its merge must satisfy every ruleset rule like any other
    merge: the approving review, all required contexts (including `release-hold` from the checker App),
    `strict`, and `require_extra_approval_for_unattributed_changes`. Whether an App merge satisfies that last
    rule is **not verified**, and it is proven in the disposable repository before task 14 (T31). If it does
    not, the merge fails closed and step 4 falls back to the owner merging personally within the
    expiry margin. The run's re-verification remains the record of what was checked.
  - Neither App is the `mctl-agents` App, and neither key is reachable from a job that a PR defines.

  The merge is made by the merger App, so `merged_by` is a Bot. That is acceptable for bump PRs, because the
  decision identity is the environment approver. It is never acceptable for grant PRs (see above).
- `strict` applies to every PR in the repository: each must be up to date with `main` before merging. That
  is an owner decision (D1).

**`auto-merge.yml` `protected_re`.** It gains `^platform-gitops/release-holds\.yaml$`,
`^platform-gitops/release-grants/`, `^scripts/release-hold[a-z_]*\.py$`, the bootstrap reader module path,
`^platform-gitops/bootstrap/templates/mctl-platform/mctl-api[^/]*\.yaml$`,
`^platform-gitops/infra-components/mctl-platform/mctl-api/`, `^platform-gitops/helm-charts/zitadel-iac/iac/`,
`^platform-gitops/bootstrap/templates/system/(admission-policies|mctl-api-release-hold-params)\.yaml$`,
`^\.github/workflows/` and `^tests/test_release_hold[a-z_]*\.py$`.
`tests/test_auto_merge_protected_paths.py` is updated.

### 5. Point of deployment effect (admission)

A new ValidatingAdmissionPolicy `mctl-api-release-hold` is added to `admission-policies.yaml`, bound with
a `namespaceSelector` on `kubernetes.io/metadata.name: mctl-api`. Its param is a ConfigMap
`mctl-api-release-hold` in `kube-system`.

**How the param is produced (amended 2026-11-11, P2-1).** The ConfigMap is **not** rendered by Helm from
`release-grants/**`. Helm runs at Argo CD render time with no GitHub API or registry access, so it cannot
check merger identity, tag ref or digest. A renderer that trusted grant files would therefore accept a grant
pushed with a deploy key. Instead the ConfigMap is a static file,
`platform-gitops/bootstrap/templates/system/mctl-api-release-hold-params.yaml`, listing the allowed
`{tag, digest}` pairs and the runtime-key rules. It is a guarded file: `release-hold.py` refuses any tree in
which it names a tag above `max_ungranted_tag` without a valid grant (checks 1-8) for that tag and digest. The
bump PR changes the image tag, the chart SHA and the allowlist together, and the trusted merge verifies all
three.

The policy covers:

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

Admission sees what Argo CD actually applies. It therefore also covers P7 (image and env) and P8
(`kubectl`, Argo CD parameter overrides). Its residual is a cluster-admin deleting the binding. root-app
`selfHeal` recreates it, but a cluster-admin can disable that too, which is recorded as BLOCKING-UNKNOWN
for the owner.

**Limits of admission (amended 2026-11-11).**

- **It sees only the image string.** With the current chart the image is `repo:tag` (see the amendment
  facts), so admission enforces the tag and the env/Secret rules, not the digest. The digest is enforced at
  merge and at push, where the GHCR digest is compared with the grant seconds before the write. Between the
  write and the kubelet pull, a GHCR tag overwrite would not be seen by admission. The post-sync verifier
  (§7) detects it. Closing that gap needs an `image.digest` value in the mctl-api chart, which can only come
  in a later mctl-api release. It is a follow-up, not part of 4.155.0.
- **No expiry at admission, by design.** `expires_at` bounds when a rollout may *start* (merge or push). After
  that the merged state is the decision, and later pod restarts must not fail because a grant aged out. VAP
  CEL has no wall-clock function in any case.
- **Deny before reliance.** The hold is reported as enforced at the point of deployment effect only after
  task 11 (Deny) has landed. Until then, L4 is detection (Audit), and the decision packet must say so.
- **Not robust to P5b/P6 on its own.** A deploy-key writer can change the bootstrap tag and the allowlist in
  one direct commit, and admission would then admit the result. See §8.

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
stays a detector. Its script and policy come from the parent commit's tree (`$BEFORE`), not from the pushed
commit, so a direct push cannot also disable its own detection (amended 2026-11-11).

**Post-sync digest verifier (amended 2026-11-11).** A read-only check compares
`status.containerStatuses[].imageID` of `mctl-api` pods with the allowlisted digest and alerts on a mismatch
or an unreadable state. It runs where read-only cluster access already exists: a CronJob in `mctl-api` with a
ServiceAccount allowed only `get`/`list` on pods. It detects; it does not enforce.

### 8. Deploy-key bypass and #2543 (amended 2026-11-11, P2-1)

The ruleset bypass `DeployKey`/`actor_id: null`/`always` lets **both** write keys push any path to `main`:
`gitops-bump` (165489378, environment `gitops-bump`) and `argo-workflows-bot-2026-10` (166128843,
`argo-workflows/mctl-gitops-deploy-key`). The design is made robust to that as follows, and it states
honestly what remains.

- **gitops-bump key, inside the two bump workflows (P1, P2):** enforced. `check` runs before any write, and
  `verify` runs before every push (§3).
- **gitops-bump key, any other workflow (P11):** prevented statically (T21, `protected_re`) and detected (L5).
- **Argo/agents key (P5b, P6):** **not prevented** by L1-L4. One direct commit can set the tag, add a grant and
  extend the allowlist. What limits it today:
  - a grant added by a direct push has no owner-merged PR, so every check treats it as absent (check 4);
  - L5 runs on every push to `main`, with script and policy from the parent, and alerts on a held tag, a grant
    or an allowlist change without a valid grant;
  - the chart pin keeps chart defaults fixed.

  This is detection after the fact, not a release hold.
- **What closes it:** #2543's remediation. Either the bypass is narrowed to named writers whose write path runs
  `release-hold.py verify` server-side (#2543 option B, a write broker), or the guarded paths are excluded
  from every bypass. One candidate for the second is a push ruleset with a `file_path_restriction` on the
  guarded set and no bypass actors. Two things about it are **not verified**: whether that rule is available
  for this public repository, and how it treats PR merges. Proving both is part of #2543's disposable-repo
  test plan, never a production experiment.
- **Decision rule:** while P5b/P6 are open, the 4.155.0 deploy decision may treat the hold as enforced only
  against P1-P4 and P7-P14. Before any DEPLOY GO, the owner either waits for #2543 or accepts the P5b/P6
  residual in writing (D3).

Nothing in this design deletes or rotates a key or changes the ruleset. Ruleset changes (the new required
context and `strict`) are owner actions in the implementation phase.

### Resulting flow for 4.155.0 (described, not executed)

0. Preconditions: tasks 1-13 are merged, L4 is in Deny (task 11), the revision label is live in
   `build-image.yaml` (task 13), and the owner has disposed of P5b/P6 (D3) and P8.
1. The owner un-drafts and merges #934. Merge commit M is tagged 4.155.0, and release-please dispatches
   release-deploy. Preflight issues a notice, the build pushes the image (labelled with M), and the bump
   refuses: there is no grant, the tag is held, and the channel is direct. Nothing is written.
2. The owner compares `tree(M)` with the tree of the head the evidence covered, and reviews the digest, SBOM
   and provenance and the #2523 evidence. The owner then opens and merges (personally, as a `User`) a PR that
   adds only `release-grants/mctl-api/4.155.0.yaml`, with `channel: pull-request`.
3. A bump PR changes three things and nothing else: `tag` to `"4.155.0"`, the chart SHA to `source_commit`,
   and the allowlist file. `release-hold-pr` (base code) posts "merge through release-hold-merge". The owner
   dispatches `release-hold-merge` with the head SHA and approves its environment. It re-verifies against the
   current `main` and merges with `sha=<head>`.
4. Admission allows the granted tag. Any env drift is denied. The post-sync verifier confirms that the
   running digest equals the grant.

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

## Owner decisions required (amended 2026-11-11)

None of these is taken by this proposal or by an agent.

- **D1.** Add the required context `release-hold`, bound to the checker App, to ruleset 18465404, and set
  `strict_required_status_checks_policy: true`. `strict` affects every PR in this repository.
- **D2.** Create two new narrow Apps, or name existing Apps that meet the same constraints (the `mctl-agents`
  App is excluded):
  - the checker App (`checks: write`, `metadata: read`), with its key in `release-hold-checker` and
    `release-hold-merge`;
  - the merger App (`contents: write`, `pull_requests: write`, `metadata: read`), with its key only in
    `release-hold-merge`.

  Neither App is a ruleset bypass actor.
- **D3.** P5b/P6: wait for #2543, or accept in writing, for the 4.155.0 decision only, that deploy-key holders
  can bypass L1-L4 and are only detected (L5).
- **D4.** The digest-to-source link is machine-checked only (check 8). The revision label (task 13) must
  be live before #934 merges. If #934 merges first, the 4.155.0 image has no label, it can never pass check
  8, and a new release (new tag, rebuilt with the label) is needed. There is no owner-attested alternative:
  it was dropped in review round 1, because it would be a non-machine-checked path around check 8. The owner
  decides the order: task 13 first, or accept that merging #934 early forces a re-release.
- **D5.** Reach Deny (task 11) before the hold is relied on at the point of effect.
- **D6.** Keep the chart pinned for the duration of the hold (existing question below).

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
