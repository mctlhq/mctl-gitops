# Enforce the mctl-api 4.155.0 owner release hold at the GitOps write and deployment point

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
- **Any write deploy key (amended 2026-11-11).** Ruleset 18465404's only bypass actor is `DeployKey` with
  `actor_id: null` and `bypass_mode: always`, so **both** write keys, `gitops-bump` (165489378) and
  `argo-workflows-bot-2026-10` (166128843), can push any path to `main` with no PR and no required check
  (mctl-gitops#2543, P1). The `gitops-bump` environment also releases its key to any workflow on `main` that
  names it.
- **No hold is machine-readable today.** The only release hold file in the org is mctl-agents
  `.github/release/hold.json`, which governs mctl-agents releases only. The mctl-api hold exists only as
  #934's Draft state and its comments.

The existing release gate (`scripts/release-gate.py` + `platform-gitops/release-gates.yaml`) covers only the
mctl-agents worker group. It cannot parse the bootstrap file, which is a Helm template carrying the service
values inside a `values: |` string. A PR-only check cannot stop direct pushes.

This proposal was amended on 2026-11-11 after an independent review returned AMEND with three P2 findings
(see design.md "Amendment 2026-11-11"). The bootstrap-aware values reader is built in a separate PR, and this
proposal consumes it rather than duplicating it.

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
    the owner's GitHub login and numeric id, `issued_at`, `expires_at` and the allowed channel. It also
    names the source tree and the reviewed release head (amended 2026-11-11).
  - The tag commit's tree equals the grant's `source_tree`, and that equals the tree of
    `reviewed_release_head`. The grant binds the commit the image is built from (the release PR's merge
    commit), never the release PR head.
  - The image config label `org.opencontainers.image.revision` of the digest equals `source_commit`. A
    missing label means unknown (exit 7).
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
- THE SYSTEM SHALL NOT accept a review, approval or CI result on a release PR head as covering a release
  whose tag commit tree differs from that head's tree. Evidence bound to an earlier #934 head (`2fc67f31`,
  `70fcec0b`, `5b76cbc3` or `6241d5c8`, as of 2026-11-11) covers that head only.
- IF a grant was added to `main` by a commit with no associated PR merged by the named owner (for example,
  a direct push through the deploy-key bypass) THEN THE SYSTEM SHALL treat the grant as absent.

Point-of-write enforcement (direct pushes)
- WHEN `release-deploy.yaml` or `gitops-bump.yaml` is asked to write any file in the hold's guarded set
  THE SYSTEM SHALL run `scripts/release-hold.py check` before any file is written. It SHALL also run
  `scripts/release-hold.py verify` on the exact tree before every push attempt, including after each
  rebase. The workflow SHALL push nothing if either check exits non-zero.
- WHEN either direct-write workflow is about to run `git push` THE SYSTEM SHALL make `verify` the last
  command before it. Each attempt SHALL re-read the hold, the grant, the GHCR digest, the tag ref, the
  revision label, the grant's merger and the clock, with nothing cached between attempts. It SHALL treat a
  grant that expires within 15 minutes as expired. A missing or failing script SHALL abort the push.
- THE SYSTEM SHALL allow `environment: gitops-bump` and `GITOPS_BUMP_DEPLOY_KEY` only in
  `release-deploy.yaml` and `gitops-bump.yaml`, enforced by a test.
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
- WHEN a PR is opened or updated THE SYSTEM SHALL evaluate the hold in `release-hold-pr.yml` on
  `pull_request_target`. The workflow definition, `release-hold.py`, the values reader, the policy and the
  grants SHALL come from the base commit. The PR head SHALL be read only as git data, and never checked out
  into the working tree, executed, imported or passed to a shell. (Amended 2026-11-11: the earlier
  `validate-manifests.yml` call ran PR-controlled code and is no longer a gate.)
- THE SYSTEM SHALL treat a change to the guard, the reader, the policy, the grants, the admission allowlist,
  the hold tests or the release, bump, validation or auto-merge workflows as a policy change. Combined with a
  guarded file, it SHALL be refused (`HOLD_POLICY_CHANGED`).
- THE SYSTEM SHALL publish the PR-time result as check `release-hold` from a dedicated checker App. The
  ruleset SHALL require that context bound to the App's integration id, so that no job defined by a PR can
  satisfy it. IF the checker cannot run THEN the PR SHALL stay blocked.
- WHEN a PR changes a guarded file THE SYSTEM SHALL merge it only through `release-hold-merge.yml`. That
  workflow (dispatched on `main`, environment approved by an owner `User`) SHALL re-run `diff` against the
  current `main` tip and the exact head SHA with a 15-minute expiry margin, refuse a PR that is not up to
  date, and merge with `sha=<head>`. The ruleset SHALL have `strict_required_status_checks_policy: true`,
  so a `main` that moved after verification makes the merge fail with no write.
- THE SYSTEM SHALL add the guarded set, `release-holds.yaml`, `release-grants/**`,
  `scripts/release-hold.py`, the admission-policy and allowlist files and `.github/workflows/` to the
  `auto-merge.yml` `protected_re`, so that no bot approval can merge them.

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
  running 4.154.0 pods. The hold SHALL NOT be reported as enforced at the point of effect before Deny.
- THE SYSTEM SHALL take the admission allowlist from a static, guarded file that `release-hold.py`
  validates against grants. It SHALL NOT render the allowlist from grant files at Helm render time, because
  Helm cannot verify merger, tag ref or digest.
- THE SYSTEM SHALL NOT enforce grant expiry at admission. Expiry bounds the start of a rollout (merge or
  push), and pod restarts after expiry remain allowed. A post-sync verifier SHALL compare running image
  digests with the allowlisted digest and alert on a mismatch or an unknown result.

Deploy-key bypass (amended 2026-11-11)
- WHILE ruleset 18465404 lets any deploy key bypass `main` protection THE SYSTEM SHALL rate P5b (the
  `argo-workflows-bot-2026-10` key) and P6 as BLOCKING-UNKNOWN. It SHALL report the hold as enforced
  against them only after mctl-gitops#2543 narrows the bypass, or after the owner accepts the residual in
  writing. Until then, the L5 detector, running with script and policy from the parent commit, is the only
  control on those paths.

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
- THE SYSTEM SHALL include negative bypass tests: a bump with no grant, a bump with a stale grant for a
  different head or tree, a bump from a workflow other than the two allowed ones, a direct push of a tag,
  grant and allowlist, a PR that edits the guard together with a guarded file, a PR-defined spoof of the
  required check, a grant that expires before the merge, a `main` that tightened the hold before the merge,
  and a head that moved after dispatch. Each SHALL prove that no write happened, or, where only detection
  exists (direct push, P5b/P6), that the detector alerts.
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

- (Amended 2026-11-11) The owner decisions D1-D6 in design.md: the ruleset's required context and `strict`,
  the checker App, the P5b/P6 residual versus #2543, the digest-to-source label before #934 merges, Deny
  before reliance, and the chart pin.
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
