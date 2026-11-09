# Enforce the mctl-api 4.155.0 owner release hold at the GitOps write and deployment point

## Context

Issue mctlhq/mctl-gitops#2528 asks for an investigation and a design. It does not ask for a release. The
production mctl-api is the Argo CD Application `admins-mctl-api`
(`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`), pinned to `image.tag: "4.154.0"`. The
release candidate 4.155.0 is the Draft release-please PR mctlhq/mctl-api#934. It carries Bridge (#970/#971)
and the unrelated deferred execution-request queue functionality, both under the 2026-11-03 owner release
hold. Several paths can move the bootstrap tag with no human decision bound to it:

- **release-deploy.** Merging #934 makes mctl-api's `release-please.yml` dispatch `release-deploy.yaml`
  automatically with `values_path=platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`. That
  workflow pushes straight to `main` with the `gitops-bump` deploy key.
- **gitops-bump.** `gitops-bump.yaml` does the same for any caller that holds `actions: write` on mctl-gitops.
- **Auto-merge.** A `claude/*` PR that edits the bootstrap file is not on the `auto-merge.yml` protected-path
  list, so it can merge on a bot approval.
- **Chart drift.** The chart source is `targetRevision: main` of the mctl-api repo. Its defaults can change
  production with no GitOps write.

The existing release gate (`scripts/release-gate.py` + `platform-gitops/release-gates.yaml`) covers only the
mctl-agents worker group. It cannot parse the bootstrap file, which is a Helm template carrying the service
values inside a `values: |` string. A PR-only check cannot stop direct pushes.

This proposal designs a fail-closed, TOCTOU-safe release hold for the mctl-api image and its dark-Bridge
invariants. The hold is enforced where the write takes effect (before write, before every push attempt, at
merge) and where the deployment takes effect (Kubernetes admission in the `mctl-api` namespace). A
post-push detector backs this up. A held version moves only with an immutable owner grant that is bound to
the image digest and the source commit. Its outcome is
`READY_FOR_SEPARATE_IMPLEMENTATION_PROPOSAL`. The two paths that are not fully provable from source (chart
drift, out-of-band cluster-admin actions) stay explicit blocking items, and the design closes them. This is
never a release approval.

## User stories

- AS the mctl-api release owner I WANT every path that can change the production mctl-api image or its
  Bridge/queue flags to refuse a held version unless my digest-bound grant is present SO THAT the 4.155.0
  hold cannot be bypassed by an automatic release-please dispatch, a direct bump or an auto-merged PR.
- AS a security reviewer I WANT the grant to name the exact image digest, the source commit, the policy it
  was issued against, my identity and an expiry SO THAT a CI SUCCESS, a string "GO" or a newer tag can never
  stand in for approval.
- AS a platform operator I WANT ordinary releases of every other service, and non-image edits to
  mctl-api.yaml, to keep working unchanged SO THAT the hold costs nothing outside its scope.
- AS an on-call engineer I WANT Argo CD to be unable to roll a held image or a Bridge provider credential into
  the `mctl-api` namespace even if git is wrong SO THAT a mistake in the CI layer is not a production event.
- AS the author of #2523 I WANT the dark-rollout rules (no `MCTL_BRIDGE_PROVIDERS`, no
  `MCTL_BRIDGE_PROVIDER_TOKENS`, Bridge and queue-while-active absent or `"false"`) enforced by machine SO
  THAT "dark" is checked, not promised.

## Acceptance criteria (EARS)

Write-path inventory
- THE SYSTEM SHALL keep a source-verified inventory of every mctl-api production mutation path, as listed
  in design.md "Write-path inventory". Each path SHALL have a status of KNOWN-ENFORCED, KNOWN-NOT-A-PATH or
  BLOCKING-UNKNOWN. WHILE any path is BLOCKING-UNKNOWN THE SYSTEM SHALL keep the hold in force for every
  held version, whatever grants exist.

Hold policy
- THE SYSTEM SHALL read the hold from `platform-gitops/release-holds.yaml`. A hold names the image
  (`ghcr.io/mctlhq/mctl-api`), the highest ungranted tag (`4.154.0`), the guarded file set, the
  forbidden or restricted runtime keys, and the allowed grant owners.
- WHILE a hold is in force THE SYSTEM SHALL treat every SemVer tag above the hold's `max_ungranted_tag` as
  held, not only `4.155.0`, because a later tag contains the held content.
- THE SYSTEM SHALL lift or relax a hold only by a human-merged PR to `release-holds.yaml`. A hold SHALL NOT
  expire with time.

Owner grant
- THE SYSTEM SHALL accept a held tag only WHEN a grant file
  `platform-gitops/release-grants/mctl-api/<tag>.yaml` exists in the policy tree and passes every check
  below. Each check is fail-closed:
  - It names the hold, the image, the tag, the immutable GHCR manifest digest (`sha256:` 64 hex), the
    40-hex mctl-api source commit of the tag, the sha256 of `release-holds.yaml` it was issued against,
    the owner's GitHub login and numeric id, `issued_at`, `expires_at` and the allowed channel.
  - The owner is in the hold's `owners` list.
  - The commit that introduced the grant came from a PR merged by that same owner (a `User`, not a
    `Bot`).
  - It has not expired.
  - The live GHCR digest of `<image>:<tag>` equals the grant digest.
  - The mctl-api tag ref resolves to the grant's source commit.
- IF the grant is missing, malformed, expired, issued against a different policy digest, issued by an
  identity not in `owners`, merged by anyone other than the named owner, or bound to a digest or commit that
  does not match THEN THE SYSTEM SHALL refuse the change and write nothing.
- THE SYSTEM SHALL NOT treat a CI result, a check-run conclusion, a PR approval by itself, or a free-text
  "GO" comment as a grant.

Point-of-write enforcement (direct pushes)
- WHEN `release-deploy.yaml` or `gitops-bump.yaml` is asked to write any file in the hold's guarded set
  THE SYSTEM SHALL run `scripts/release-hold.py check` before any file is written. It SHALL also run
  `scripts/release-hold.py verify` on the exact tree before every push attempt, including after each
  rebase. The workflow SHALL push nothing if either check exits non-zero.
- WHILE the grant's `channel` is `pull-request` (the default, as #2523 requires) THE SYSTEM SHALL refuse a
  held tag in both direct-write workflows even when a valid grant exists.
- WHEN a push attempt follows a rebase THE SYSTEM SHALL compare the hold policy of the rebased tree with the
  policy at the job's starting commit. IF the target's hold was weakened or removed in between THEN THE
  SYSTEM SHALL refuse the run, so that a newer `main` can never silently discard the hold the run started
  under.
- WHEN `release-deploy.yaml` preflight runs for a held tag without a valid grant THE SYSTEM SHALL let the
  image build proceed (an image in GHCR is not a deployment, and the grant needs its digest). It SHALL
  record a notice, and the bump job SHALL refuse.

Merge-path enforcement (PRs)
- WHEN a PR changes any file in the guarded set, `release-holds.yaml` or `release-grants/**`
  THE SYSTEM SHALL run `release-hold.py diff --base <merge-base> --head <head>` in `validate-manifests.yml`.
  The policy and grant are read from the base side only.
- THE SYSTEM SHALL add the guarded set, `release-holds.yaml`, `release-grants/**`,
  `scripts/release-hold.py` and the admission-policy file to the `auto-merge.yml` `protected_re`, so that no
  bot approval can merge them.

Deployment-effect enforcement (Kubernetes admission)
- THE SYSTEM SHALL deploy a ValidatingAdmissionPolicy, bound to the `mctl-api` namespace, for Deployments,
  ReplicaSets and Pods. It SHALL deny a container image of `ghcr.io/mctlhq/mctl-api` whose tag and digest
  are not in the policy's allowlist parameter. It SHALL deny `MCTL_BRIDGE_PROVIDERS` and
  `MCTL_BRIDGE_PROVIDER_TOKENS` in container `env`. It SHALL deny any value other than absent or `"false"`
  for `MCTL_BRIDGE_ENABLED` and `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`.
- THE SYSTEM SHALL deny Secrets in the `mctl-api` namespace whose `data` or `stringData` keys include
  `MCTL_BRIDGE_PROVIDERS`, `MCTL_BRIDGE_PROVIDER_TOKENS` or `MCTL_BRIDGE_ENABLED`, because `envFrom` can
  inject them without any container `env` entry.
- THE SYSTEM SHALL roll out the admission policy with `validationActions: [Warn, Audit]` first, and
  switch to `[Deny]` only in a separate reviewed PR after one observed sync shows no warning for the
  running 4.154.0 pods.

Runtime-flag guard in git
- WHILE no activation grant exists THE SYSTEM SHALL refuse any guarded file that sets
  `MCTL_BRIDGE_PROVIDERS` or `MCTL_BRIDGE_PROVIDER_TOKENS`, or sets `MCTL_BRIDGE_ENABLED` or
  `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` to anything other than absent or `"false"`. The check covers
  the bootstrap inline values, the mctl-api ExternalSecrets, and the infra-components and zitadel-iac
  sources of the `envFrom` Secrets.
- THE SYSTEM SHALL keep an activation grant separate from a release grant. A release grant SHALL never allow
  any of these keys.

Chart drift
- WHILE a hold is in force THE SYSTEM SHALL pin the `admins-mctl-api` chart source (`repoURL`
  `https://github.com/mctlhq/mctl-api.git`, `path: helm`) to an immutable revision instead of `main`. It
  SHALL refuse (`verify`) a guarded tree whose chart `targetRevision` is `main`, `HEAD` or any branch name.

Fail-closed
- IF any input cannot be read or decided THEN THE SYSTEM SHALL refuse. Exit 7 means unknown, and SHALL never
  be treated as a pass. Such inputs include `release-holds.yaml`, a grant, the bootstrap file, the extracted
  inline values, the GitHub API (merger identity, tag ref) and the GHCR registry (digest).

Detection
- WHEN any push lands on `main` THE SYSTEM SHALL run `release-hold.py diff` (policy from the parent) and
  `verify` in `release-gate-watch.yml`. On a violation or an unknown result it SHALL alert Telegram. This
  detects; it does not enforce.

Tests
- THE SYSTEM SHALL include synthetic negative tests that run the real embedded bump scripts and push loops
  against a local bare repository. Each test SHALL prove that no commit reached the bare `main` for every
  refusal case in tasks.md. A normal authorised release of another service, and a granted bump through a PR,
  SHALL serve as positive controls.

## Out of scope

- Any change to mctl-api#934 (Draft/hold), any mctl-api release, tag or image build, or any tag bump.
- Mutating running pipelines, deploy keys, Vault values or credentials; Argo apply, sync or rollback.
- Bridge activation or issuing provider credentials. The activation grant format is defined but never issued
  here.
- Rewriting tenant services, the mctl-agents worker gate (`release-gates.yaml` group) or worker versioning.
- Any new automatic GO. Nothing in this design can issue a grant.
- The reviewer aggregate gate (#1040), the mctl-agents B4 marker rollback (#1007) and the release signal
  watcher (#1292). They are referenced as inputs or coordination points, not re-implemented.

## Open questions

- Out-of-band cluster-admin paths (Argo CD UI/CLI sync with parameter overrides, `kubectl` with the
  `KUBECONFIG`/`ARGOCD_TOKEN` repository secrets, deleting or unbinding the ValidatingAdmissionPolicy) could
  not be observed from source. Admission covers the first two, and root-app `selfHeal` reverts the policy
  removal, but a cluster-admin can still disable both. This is recorded as BLOCKING-UNKNOWN until the owner
  accepts it as residual risk, or Argo CD RBAC evidence shows it is closed.
- Can the `gitops-bump` and `release-deploy` bump jobs read the GHCR manifest digest of the private(?)
  `ghcr.io/mctlhq/mctl-api` package (visibility not observed) with `packages: read` on `GITHUB_TOKEN`? Not
  observed. If not, the digest
  check fails closed and every held bump refuses. That is safe, but it needs a read credential decision.
- Should the bootstrap value become digest-pinned (`tag: "4.155.0@sha256:..."`) so that Argo pulls the exact
  granted manifest? This needs confirmation that the mctl-api chart's image template accepts it. It would also
  need `release-gate.py`/`release-preflight.py` SemVer handling for this file. Proposed as a follow-up.
- The issue calls the hold "a 2026-11-03 owner hold". This design treats the date as when the hold was set,
  not as an expiry: holds never lapse with time. If the owner meant an expiry, `release-holds.yaml` gains a
  field, but expiry would still only relax via a reviewed PR.
- The inline values are checked structurally, so a comment there is ignored. Every other guarded file is
  scanned as raw text, so a comment that merely names a forbidden key there (for example, one explaining the
  dark rollout) refuses. Is that conservative behaviour acceptable, or should those files strip YAML/HCL
  comments before scanning?
- Pinning the chart to an immutable revision changes how mctl-api chart changes reach production: they then
  need an explicit `targetRevision` bump. Does the owner accept this for the duration of the hold?
