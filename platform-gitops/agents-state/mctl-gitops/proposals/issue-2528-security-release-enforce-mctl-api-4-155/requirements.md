# Bind the mctl-api 4.155.0 release hold to artifact, chart and runtime flags at the GitOps point of effect

## Context

Issue mctlhq/mctl-gitops#2528 asks for the mctl-api 4.155.0 owner hold to be
enforced where a GitOps write or deployment takes effect. A check in an earlier
PR is not enough. 4.155.0 bundles the Bridge changes (#970/#971) with the
deferred execution-request queue, and both are under the owner hold of
mctl-api#934. Since the issue was filed, part of the hold has been built.
`platform-gitops/release-gates.yaml` carries a `version_holds` entry
`mctl-api-bootstrap` (`held_from: "4.155.0"`, `allow: []`). `scripts/release-gate.py`
reads the `values: |` block of
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` and refuses
a held tag that has no allow record. It does this before the write, before every
push (`--policy-rev origin/main`) on the direct and PR routes, in `validate`,
and after the fact in `release-gate-watch.yml`. The chart source is now pinned to
`a5b9ef9cf0f880f28b841033a8b2a6d9563ce050`.

This proposal amends the #2528 proposal to cover what is still not enforced
(see `docs/plans/mctl-api-4-155-release-readiness.md`, "Reconcile before
deciding the implementation grant"):

- an allow record is a set of strings (version, grant, approver, expiry). It is
  not bound to an immutable artifact, a source commit, a reviewed release head
  or the chart revision;
- nothing refuses the Bridge and queue runtime keys in the bootstrap values or
  in the Secrets the app loads with `envFrom`;
- the PR-time check runs the PR's own copy of the guard;
- the chart pin is not tied to the tag.

The change extends the existing reader. A second reader is out of scope.

## User stories

- AS the release owner I WANT a held mctl-api version to deploy only when an
  allow record names the exact image digest, source commit, release head and
  chart revision SO THAT a string-only or reused approval cannot release a
  different artifact.
- AS the release owner I WANT the Bridge and queue activation keys refused in
  every GitOps-declared env source of mctl-api SO THAT "dark Bridge" stays true
  regardless of which version runs.
- AS a platform operator I WANT every write path to the bootstrap file to run the
  same, trusted check immediately before the write SO THAT a PR, retry, rebase or
  newer `main` cannot discard the hold.
- AS a reviewer I WANT an explicit inventory of the write paths that remain
  unenforced SO THAT the release decision records them as owner-accepted residual
  risk rather than assuming they are covered.

## Acceptance criteria (EARS)

Allow-record binding

- WHEN `release-gates.yaml` is loaded and a hold has `require_binding: true`
  THE SYSTEM SHALL reject (exit 6) any allow record that lacks one of `digest`
  (`sha256:` plus 64 lowercase hex), `source_commit`, `release_head` or
  `chart_revision` (each 40 lowercase hex), or carries a malformed one.
- WHEN a held version (>= `held_from`) is checked in bump mode (`check`) or tree
  mode (`verify`) THE SYSTEM SHALL require the first source of the held
  Application whose `repoURL` is the hold's `chart_repo` to have a
  `targetRevision` exactly equal to the allow record's `chart_revision`.
- WHILE a hold has `require_pinned_chart: true` THE SYSTEM SHALL refuse the held
  file, at any version, if its `chart_repo` source `targetRevision` is not a
  40-hex commit (for example `main` or a tag name) or if that source appears
  more or less than exactly once.
- WHEN `release-gate.py artifact --hold <name> --version <v>` runs THE SYSTEM
  SHALL resolve `<repository>:<v>` in GHCR to a manifest digest and refuse unless
  it equals the allow record's `digest`, refuse unless the image config label
  `org.opencontainers.image.revision` equals `source_commit`, and refuse unless
  the mctl-api git tag `<v>` resolves to `source_commit`.
- IF any GHCR or GitHub read for the artifact check fails, times out, is
  partial or is malformed THEN THE SYSTEM SHALL exit 7 (UNKNOWN) and the calling
  workflow SHALL treat that as a refusal with no write.
- WHEN `release-deploy.yaml` or `gitops-bump.yaml` writes or pushes a held version
  of the bootstrap file (bump job, every `publish-direct` attempt, every
  `publish-pr` attempt) THE SYSTEM SHALL run the artifact check in the same step
  that already runs `release-gate.py verify --policy-rev origin/main`, after any
  rebase and before the push.

Runtime keys

- WHILE a hold lists `forbidden_env` THE SYSTEM SHALL refuse (exit 6), at any
  version, if any listed name appears as a key of `env` in the held file's
  `values: |` block, as a `secretKey` of an ExternalSecret in the hold's
  `env_sources`, or as a token in any other file matched by `env_sources`.
- THE SYSTEM SHALL ship `forbidden_env` for `mctl-api-bootstrap` as
  `MCTL_BRIDGE_ENABLED`, `MCTL_BRIDGE_PROVIDERS`, `MCTL_BRIDGE_PROVIDER_TOKENS`
  and `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`.
- IF an `env_sources` pattern matches no file, or a matched file cannot be
  read or parsed THEN THE SYSTEM SHALL refuse with an UNKNOWN problem line.

Trust and TOCTOU

- WHEN `validate-manifests.yml` runs on a pull request THE SYSTEM SHALL also run
  the base branch's `scripts/release-gate.py` (read with `git show
  origin/<base>:scripts/release-gate.py`, executed with `python3 -I` from a
  temporary directory) against the PR tree, in addition to the PR's own copy.
- IF a single pull request or pushed commit changes both the hold policy
  (`version_holds` in `release-gates.yaml`, or `scripts/release-gate.py`) and the
  held file's image tag or chart `targetRevision` THEN THE SYSTEM SHALL refuse it
  (`release-gate.py diff` and the PR validator). A grant and the change it
  authorises land in separate reviewed changes.
- WHILE an allow record is consumed by a new write THE SYSTEM SHALL read the
  policy from `origin/main` at push time (existing `--policy-rev origin/main`),
  so a newer `main` that removed or changed the record refuses the push.

Inventory and reporting

- THE SYSTEM SHALL record every write path in
  `docs/runbooks/mctl-api-release-hold.md` as KNOWN-ENFORCED, KNOWN-NOT-A-PATH or
  BLOCKING-UNKNOWN. P7 is updated to reflect the landed pin.
- WHILE P5b, P6, P8, P9 (Job-written Secrets) or P12 are BLOCKING-UNKNOWN THE
  SYSTEM SHALL NOT be described as preventing deployment of a held version. The
  release decision packet SHALL carry the owner's dated residual-risk disposition
  for each of them.
- IF a test of a refusal path is run THEN THE SYSTEM SHALL demonstrate that no
  commit reached the target ref (no new SHA on the disposable remote's `main`,
  no `release-bump/*` branch push).

## Out of scope

- Any change to mctl-api#934 (Draft/hold), any mctl-api tag, build or release.
- Adding an allow record for 4.155.0, or any approval/GO. This proposal grants
  nothing.
- Deploy key, ruleset (18465404), App, environment, or credential changes
  (#2543). These are recorded as residual risk only.
- The ValidatingAdmissionPolicy (P8), the App-bound `release-hold` status context
  (P12), the post-sync digest verifier CronJob, and ruleset `strict` checks:
  separate owner-approved work.
- Scanning Secrets written at runtime by the zitadel-iac Job beyond static text
  in `platform-gitops/helm-charts/zitadel-iac/**`. Reading Secret payloads is
  forbidden.
- Bridge activation, provider credentials, the reviewer aggregate gate (#1040),
  the B4 marker rollback (#1007), the release signal watcher (#1292).
- A separate `release-hold.py`. The existing reader is extended.

## Open questions

- Does the mctl-api chart at `a5b9ef9c` render an `image.digest` value? If yes,
  should the hold also require `image.digest` in the bootstrap values to equal
  the allow record's `digest`, so that Argo pulls by digest rather than by a
  mutable tag? Without it, the artifact check proves tag-to-digest only at write
  time. A tag re-push afterwards is a residual risk (the post-sync verifier is
  out of scope).
- Which credential does the artifact check use for GHCR? The Actions
  `GITHUB_TOKEN` with `packages: read` if the package grants this repo access, or
  anonymous if `ghcr.io/mctlhq/mctl-api` is public. Neither was observed in this
  run.
- What format does `release_head` take: the #934 head SHA at review time, or the
  merge commit on mctl-api `main`? This design binds it as an audit field and
  checks only that it is well-formed. A machine check of it against GitHub
  (PR merged at that head) is a follow-up.
- The issue reports grants `aar_31e2ff84...` (fresh) and `aar_e6e35315...`
  (superseded). Their ledger state was not read: UNKNOWN.
- Decision for the issue: `READY_FOR_SEPARATE_IMPLEMENTATION_PROPOSAL` for the
  gate extension above. Releasing 4.155.0 stays `BLOCKED_UNPROVEN_WRITE_PATH`
  until #2543 closes P5b/P6, or until the owner accepts that residual in
  writing.
