# Design: issue-2528-security-release-enforce-mctl-api-4-155

## Current state

mctl-api is deployed by the bootstrap Application `admins-mctl-api` in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`:

- First source: `repoURL: https://github.com/mctlhq/mctl-api.git`, `path: helm`,
  `targetRevision: a5b9ef9cf0f880f28b841033a8b2a6d9563ce050`. The comment at
  lines 11-15 cites #2528 hold P7 and says "Move this pin in the same reviewed
  PR that bumps the image tag". Nothing enforces that sentence.
- Inline `helm.values: |` block: `image.repository: ghcr.io/mctlhq/mctl-api`,
  `image.tag: "4.154.0"` (line 50), an `env:` map (from line 59),
  `envFromSecret: mctl-api-secrets`, `envFromExtraSecret: mctl-api-events`,
  `envFromOptionalSecrets: [mctl-api-zitadel-hook, (conditional)
  mctl-api-security-code-scanning]`, plus many `*Secret` refs
  (`oidcProvidersSecret`, `usageWriterTokenSecret`, ...).
- Second source: mctl-gitops `targetRevision: main`,
  `path: platform-gitops/infra-components/mctl-platform/mctl-api`
  (`oidc-zitadel.yaml`, `orchestrator-devloop.yaml`, `zitadel-hook.yaml`).
  These are Secrets/Roles that the zitadel-iac Job fills.
- `syncPolicy.automated` with `prune` and `selfHeal`.

ExternalSecrets that feed `envFrom` live in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-secrets.yaml`,
`mctl-api-usage-writer.yaml` and `mctl-api-security-code-scanning.yaml`. They
list explicit `secretKey:` entries; there is no `dataFrom`, so every env name
they can inject is visible in git. The zitadel-iac Job writes Secrets from
Terraform in `platform-gitops/helm-charts/zitadel-iac/`, so those keys are only
statically visible as text.

Hold enforcement already on `main`:

- `platform-gitops/release-gates.yaml` declares `version_holds` with
  `mctl-api-bootstrap` (`file`, `repository: ghcr.io/mctlhq/mctl-api`,
  `held_from: "4.155.0"`, `allow: []`). The documented allow record shape is
  `{version, grant, approved_by, expires}`.
- `scripts/release-gate.py`:
  - `block_values()` parses the single `values: |` block with a duplicate-key
    loader.
  - `_holds()` validates the section; a missing section is an error.
  - `_bootstrap_tag()` requires exactly one `repository:`/`tag:` pair.
  - `hold_problems()` refuses a held version with no record. Expiry gates new
    writes only.
  - The subcommands are `check` (bump), `verify` (tree), both with
    `--policy-rev`, and `diff` (policy from the parent).
  - Unreadable input is a refusal.
- Callers (per `docs/runbooks/mctl-api-release-hold.md`):
  - `release-deploy.yaml`: bump `:354`, `publish-direct` `:598` (before every
    attempt), `publish-pr` `:701`.
  - `gitops-bump.yaml`: `:239`, `:485`, `:564`.
  - `validate-manifests.yml:597-598`: `--selftest` and `verify`, run from the
    PR's own tree with the PR's own policy.
  - `release-gate-watch.yml:60,82`: `diff` and `verify` on push to `main` and
    daily.
- `platform-gitops/release-bump-routes.yaml` sends `ghcr.io/mctlhq/mctl-api`
  bumps through the `release-bump/*` PR route. The first live use has not been
  observed.
- `build-image.yaml:484-498` stamps `org.opencontainers.image.revision` with a
  resolved 40-hex source revision.
- Tests: `tests/test_release_gate_bootstrap_hold.py` (real script, copies of the
  real bootstrap file, a MUTANTS list) and `tests/test_release_deploy_bump.py`,
  `test_release_bump_pr_route.py`, `test_release_gate_diff.py`,
  `test_release_gate_watch.py`.
- `.github/CODEOWNERS` has `* @MashkovD` only. Whether the ruleset requires
  code-owner review was not observed.

Write-path inventory (from `docs/runbooks/mctl-api-release-hold.md`):

- KNOWN-ENFORCED: P1, P2, P3, P4, P4b and P11.
- KNOWN-NOT-A-PATH: P5a, P10 and P13.
- BLOCKING-UNKNOWN:
  - P5b/P6: the write deploy keys are a ruleset bypass actor.
  - P8: Argo CD and kubectl overrides.
  - P9: other optional Secrets.
  - P12: `validate` can be spoofed by a PR-defined job.
  - P7: still listed as `targetRevision: main`, but the pin to `a5b9ef9c` has
    since landed, so the runbook is stale on this row.

`docs/plans/mctl-api-4-155-release-readiness.md` asks that this proposal be
amended. It should extend `allow` with `digest` and `source_commit` plus
release-head/tree bindings, use injectable GitHub/GHCR reads, and not add a
second reader.

Deployed state checked:

- `mctl_get_service_status(admins, mctl-api)`: Argo app `admins-mctl-api`
  Healthy / Synced, project `platform`, updatedAt 2026-11-11T22:23:22Z. The
  revision field was empty, so the synced chart/gitops revision was not observed.
- `mctl_get_service_pods(admins, mctl-api)`: error "service not found: mctl-api
  (workspace admins)". The bootstrap app is not a catalogue service, so live pod
  image IDs and the digest were NOT observed (recorded under Open questions; not
  treated as absent).
- Git: `mctl-api.yaml` shows tag `4.154.0` and chart pin `a5b9ef9c`.
  `release-gates.yaml` shows `allow: []`.

## Proposed solution

Extend `release-gate.py` and the `mctl-api-bootstrap` hold. No new tool, no new
reader of the values block.

### 1. Policy schema (`platform-gitops/release-gates.yaml`)

```yaml
version_holds:
  - name: mctl-api-bootstrap
    issue: mctlhq/mctl-gitops#2528
    file: platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml
    repository: ghcr.io/mctlhq/mctl-api
    held_from: "4.155.0"
    chart_repo: https://github.com/mctlhq/mctl-api.git
    require_pinned_chart: true
    require_binding: true
    source_repo: mctlhq/mctl-api          # where tag -> commit is resolved
    forbidden_env:
      - MCTL_BRIDGE_ENABLED
      - MCTL_BRIDGE_PROVIDERS
      - MCTL_BRIDGE_PROVIDER_TOKENS
      - MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE
    env_sources:
      - platform-gitops/bootstrap/templates/mctl-platform/mctl-api*.yaml
      - platform-gitops/infra-components/mctl-platform/mctl-api/*.yaml
      - platform-gitops/helm-charts/zitadel-iac/**
    allow: []
    # record shape with require_binding:
    #   - version: "4.155.0"
    #     grant: mctlhq/mctl-gitops#NNNN
    #     approved_by: mashkovd
    #     expires: 2026-12-31
    #     digest: sha256:<64 hex>
    #     source_commit: <40 hex>
    #     release_head: <40 hex>
    #     chart_revision: <40 hex>
```

`_holds()` validates the new fields. Unknown keys in a hold or a record are
errors, so a typo cannot silently drop a check. `forbidden_env` entries must
match `^[A-Z_][A-Z0-9_]*$`, and each `env_sources` glob must match at least one
file.

### 2. Offline checks (run by `check`, `verify`, and therefore by every existing caller)

- `chart_problems(root, hold, allow_rec)`: in the held file, find the
  `repoURL: <chart_repo>` line and its sibling `targetRevision:`. The
  relationship is textual because the file is a Helm template, so the
  `_bootstrap_tag` style is used: there must be exactly one occurrence.
  - With `require_pinned_chart`, the revision must be 40 hex.
  - If the version under judgement is held, it must equal
    `allow_rec.chart_revision`.

  This ties the chart pin to the tag. It also refuses chart `main` drift
  (reverting to `targetRevision: main`) at any version.
- `env_problems(root, hold)`:
  - Collect the keys of `block_values(text)["env"]` from the held file.
  - For `env_sources`: in YAML files, collect every `secretKey` and every `env`
    or `stringData`/`data` key in each parsed document. Helm-template files are
    read with the same `_HELM_LINE` stripping, and a file that will not parse is
    read as text. Non-YAML files (`*.tf`) are read as text, matching
    `\b<NAME>\b`.
  - Any hit refuses. Any read or parse failure refuses as UNKNOWN.

  This check is version-independent: the flags are refused for 4.154.0 as well,
  so the activation hold is separate from the release hold, as the issue asks.

`hold_problems()` calls both. In verify mode, an already-deployed allowed
version stays verifiable after `expires`, which is the existing semantics. The
chart binding is still checked, because a chart move is a new effect.

### 3. Online artifact check (new subcommand `artifact`)

```
release-gate.py artifact --hold mctl-api-bootstrap --version 4.155.0 [--policy-rev origin/main]
```

It reads through one injectable module-level function, `_fetch(kind, ref)`,
replaced in tests:

1. GHCR: `GET /v2/mctlhq/mctl-api/manifests/<version>` with an OCI index/manifest
   `Accept`. The `Docker-Content-Digest` must equal `digest`. For an index, the
   index digest is what is bound.
2. GHCR config blob: `org.opencontainers.image.revision` must equal
   `source_commit`. For an index, every platform manifest's config must carry
   the same label.
3. GitHub: `GET /repos/<source_repo>/git/ref/tags/<version>`, with annotated tags
   peeled. The commit must equal `source_commit`.

The exits mirror the existing ones:

- 0: pass.
- 6: mismatch.
- 7: UNKNOWN, meaning any HTTP error, timeout (fixed 20 s), missing header, JSON
  error, or no record for the version. The workflows treat it as a refusal.

For a version below `held_from`, `artifact` exits 0 without network access, so
ordinary releases are unchanged.

### 4. Wiring (point of effect)

In `release-deploy.yaml` and `gitops-bump.yaml`, add `release-gate.py artifact
--policy-rev origin/main` beside each existing `verify --policy-rev origin/main`.
That covers the bump job and every `publish-direct` and `publish-pr` attempt.
It runs only when the bumped image is the hold's repository and the new tag is
>= `held_from`, which `check` already computes. Like `release_gate()` in
`publish-direct`, it is called after each rebase and immediately before the
push, so a retry re-reads `origin/main`. A record removed or changed on a
newer `main` therefore refuses the push.

In `validate-manifests.yml`:

- Keep the current steps.
- Add a "trusted gate" step. It writes `git show origin/${{ github.base_ref
  }}:scripts/release-gate.py` to `$RUNNER_TEMP/trusted/` and runs it with
  `python3 -I ... --root "$GITHUB_WORKSPACE" verify`, so the PR cannot weaken
  the code that judges it (P2-2, partial).
- Run `artifact` when the PR tree's held tag is >= `held_from`.
- On `push` events, use `github.event.before`.

`release-gate-watch.yml` adds `artifact` to its daily `verify`, as a detector.

### 5. Separation of grant and effect

`diff_problems()` and a new PR-side call (`release-gate.py diff --base
<merge-base> --head HEAD`, from the trusted copy) refuse a change set that
modifies `version_holds`/`scripts/release-gate.py` **and** the held file's tag
or chart `targetRevision`. The owner's allow record therefore merges first
(reviewed, code-owned), and the bump is a separate change judged by the policy
already on `main`.

### 6. Documentation

- `docs/runbooks/mctl-api-release-hold.md`:
  - Update P7 to KNOWN-ENFORCED (pin plus `require_pinned_chart`).
  - Add the new checks to "What is enforced today".
  - Mark P9 as partially enforced (git-visible keys only).
  - Leave P5b, P6, P8, P12 and Job-written Secret values BLOCKING-UNKNOWN.
- The comment block at the top of `release-gates.yaml` documents the new fields
  and exit codes.

### Release flow after this change (informational, grants nothing)

1. BUILD GO, then the mctl-api tag and image.
2. The owner reads the digest, source commit and chart commit.
3. A reviewed PR adds the bound allow record.
4. A separate routed bump PR moves the tag and `targetRevision` together. The
   gate checks all bindings at write and push time.
5. Post-sync: observe the imageIDs (out of scope).

## Alternatives

- **(B) An independent `release-hold.py` with shared policy data.** This was
  the earlier #2589 design. It was dropped because it gives two readers of one
  values block, and the readiness plan and the runbook reject that.
- **(C) A gate only in the release workflows (no `verify`/`validate`
  coverage).** Dropped because it leaves P3/P4 (human and bot PRs) and the
  post-push detector without the bindings. It also cannot refuse a chart revert
  or a flag added by a PR.
- **Require Argo to pull by digest (`image.digest` in values) instead of an
  online artifact check.** This is stronger at the point of effect, but whether
  the chart at `a5b9ef9c` supports it was not verified. It is recorded as an
  open question and can be added as an offline check later
  (`values.image.digest == allow.digest`). The online check is still needed to
  bind digest to source commit.
- **An admission policy (VAP) as the only enforcement.** It covers P8, but it
  needs a cluster change and an observed sync. It is kept as separate work.

## Platform impact

- Migration: `release-gates.yaml` gains fields. With `allow: []` today no record
  needs migrating. `require_binding` makes the four new record fields mandatory
  for this hold only, and the `mctl-agents-workers` gate is untouched.
- Backward compatibility: tags below 4.155.0 behave exactly as today. The new
  failure modes for ordinary releases are: chart `targetRevision` not 40 hex (it
  is already pinned), and a forbidden key appearing (none appears today; this
  must be confirmed in task 1). A false positive from a comment that names a
  flag in `env_sources` blocks releases. Mitigations: comments in YAML files are
  excluded by parsing, so only `.tf` text matching can hit a comment, and the
  error names file and line.
- Network dependency: the `artifact` check only runs for held versions. A GHCR
  or GitHub outage blocks a held release, which is fail-closed by design, and
  never blocks ordinary releases.
- Resources: a few HTTP calls per publish attempt; no cluster resources.
- Risks:
  - The deploy-key bypass (P5b/P6) can still change the policy and the tag
    together. The separation check runs post-push only in that case
    (detector). Mitigation: the owner's written residual acceptance, and #2543.
  - Tag re-push after the check: residual unless digest pinning lands.
  - The trusted-copy step depends on `origin/<base>` being fetched; a fetch
    failure fails the step.
- This design, once merged, grants nothing. 4.155.0 stays refused because
  `allow` is empty.
