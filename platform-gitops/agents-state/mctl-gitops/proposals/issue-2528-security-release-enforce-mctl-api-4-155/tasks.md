# Tasks: issue-2528-security-release-enforce-mctl-api-4-155

Preconditions:

- Do not start any implementation task until this proposal has an independent review and a separate
  digest-bound owner approval.
- No task releases, tags, builds, bumps or syncs mctl-api, and none issues a grant.
- Every PR below touches paths in the new `protected_re` and is merged by a human.
- (Amended 2026-11-11) The bootstrap-aware values reader comes from the separate gate PR. Task 3 imports it
  and adds the T-cases it needs; it does not write a second reader.
- (Amended 2026-11-11) Ruleset, App and environment changes (tasks 14-16) are owner actions (D1, D2). An
  agent prepares the exact JSON and evidence, and never applies it.

- [ ] 1. Write the write-path inventory as a versioned document,
  `docs/runbooks/mctl-api-release-hold.md`, using the P1-P10 table in design.md. Each row cites file and
  line, with KNOWN-ENFORCED / KNOWN-NOT-A-PATH / BLOCKING-UNKNOWN and the layer that covers it. Add the
  runbook to CLAUDE.md's secrets/runbooks list. — DoD: every row has a source citation, P7 and P8 are
  marked BLOCKING-UNKNOWN with the disposition the owner must give, and the doc is linked from
  `release-holds.yaml`.
- [ ] 2. Add `platform-gitops/release-holds.yaml` (hold `mctl-api-4.155`, `max_ungranted_tag: "4.154.0"`,
  guarded set, `runtime_keys`, `chart_pin_required: true`, `owners` filled by the owner) and an empty
  `platform-gitops/release-grants/mctl-api/.keep`. (depends on 1) — DoD: the file parses, and the owner
  login and numeric id are entered by the owner, not by an agent.
- [ ] 3. Implement `scripts/release-hold.py` with `check`, `verify [--since SHA]`, `diff`, `--channel`
  and `--selftest`. It includes the inline-values reader, the grant validator (schema, expiry, policy
  digest, owner list, merger identity through the GitHub API, tag ref, GHCR digest) and the monotonic
  hold comparison. Exit 0/6/7. GitHub and registry reads go behind one injectable function so tests can
  feed answers and failures. (depends on 2) — DoD: `--selftest` covers every T-case below that needs no
  git repository, and every unreadable input yields 7.
- [ ] 4. Wire `release-hold.py` into `.github/workflows/release-deploy.yaml` and
  `.github/workflows/gitops-bump.yaml` (depends on 3):
  - call `check --channel direct` in the embedded bump script after `release-gate.py check` and before
    any write;
  - record `START_SHA` before the bump;
  - call `verify --channel direct --since "$START_SHA"` inside `release_gate()` before every push attempt;
  - grant the bump jobs `packages: read` only if the open question on GHCR reads resolves that way.

  — DoD: the existing bump tests still pass, and new tests T1-T12 pass against the real extracted
  scripts.
- [ ] 5. Add an advisory hold notice to `scripts/release-preflight.py preflight` that never changes its
  exit code. (depends on 3) — DoD: `tests/test_release_preflight.py` asserts the notice for a held tag and
  an unchanged exit code.
- [ ] 6. Pin the `admins-mctl-api` chart source `targetRevision` from `main` to the commit SHA of mctl-api
  tag `4.154.0`, resolved with `git ls-remote` and recorded in the PR body. Argo CD then renders the same
  chart that is running, so check the diff with `argocd app diff` (read-only) or `helm template` before
  and after. (depends on 3) — DoD: `release-hold.py verify` passes on the pinned tree and refuses `main`.
  The rendered manifests differ only by what mctl-api `main` has changed since 4.154.0; list any such
  difference in the PR body.
- [ ] 7. Wire the merge path (amended 2026-11-11; depends on 3):
  - `validate-manifests.yml` gets only the `release-hold.py` selftest and unit tests (not a gate);
  - add `.github/workflows/release-hold-pr.yml` (`pull_request_target`, base checkout, head read as data,
    result posted as check `release-hold` by the checker App; design.md §4);
  - add `.github/workflows/release-hold-merge.yml` (`workflow_dispatch` on `main`, environment
    `release-hold-merge`, re-verify, then merge with `sha=<head>`; design.md §4);
  - extend `protected_re` in `.github/workflows/auto-merge.yml` with the paths in design.md section 4;
  - update `tests/test_auto_merge_protected_paths.py`.

  — DoD: a `claude/*` PR fixture touching `mctl-api.yaml` is classified as protected. A static test
  asserts that `release-hold-pr.yml` never checks out, runs or imports head content (no `ref:
  ${{ github.event.pull_request.head.* }}` checkout, head read only via `git show`). T23-T28 pass.
- [ ] 8. Add `diff --channel direct` and `verify` steps for `release-hold.py` to
  `.github/workflows/release-gate-watch.yml`, using the existing violated/unknown Telegram split. (depends
  on 3) — DoD: `tests/test_release_gate_watch.py` covers a hold violation and an unknown result.
- [ ] 9. Add the `helm template` cross-check test. It renders `platform-gitops/bootstrap` and asserts that
  `release-hold.py`'s reader returns the same image, tag, env map and chart `targetRevision` for
  `admins-mctl-api`. (depends on 3) — DoD: the test fails when the reader is fed a fixture that Helm and
  the reader disagree on.
- [ ] 10. Add the ValidatingAdmissionPolicy `mctl-api-release-hold`, its binding (namespace `mctl-api`)
  and the param ConfigMap, rendered from `release-holds.yaml` and grants, to
  `platform-gitops/bootstrap/templates/system/admission-policies.yaml`. Use `validationActions: [Warn,
  Audit]`, `failurePolicy: Fail` and `paramNotFoundAction: Deny`. (depends on 2) — DoD: the policy is
  rendered by `helm template`, `kubeconform`/validate-manifests pass, and a kind or envtest fixture in
  CI proves that both the T13 deny cases and the allow case are evaluated.
- [ ] 11. A separate PR, after one observed sync with no `mctl-api-release-hold` warnings on the 4.154.0
  pods and with the live image digest added to the allowlist, switches the binding to `[Deny]`. (depends on
  10) — DoD: the PR body has the audit-log or warning evidence and the live digest.
- [ ] 12. Record the dependency map in the runbook: #934, #2523, mctl-agents#993 Part M, #992 Part S,
  mctl-agents#1007 B4, mctl-api#935 drain, #1040 and #1292, and how each feeds `grant.prerequisites` or
  coordinates. (depends on 1) — DoD: each link is present, with "machine-checked: no" where the owner
  judges it.

- [ ] 13. (Amended 2026-11-11) In `build-image.yaml`, stamp `org.opencontainers.image.revision` with the
  resolved 40-hex SHA of the source checkout (`git rev-parse HEAD` after checkout, never the input ref).
  Extend `release-hold.py` check 8 to read it from the image config. (Independent of 3) — DoD: a test build
  in a fixture shows the label, and T20 passes. The task must be live before #934 merges, unless the owner
  takes D4 option two.
- [ ] 14. (Owner action, D1/D2) Prepare the ruleset 18465404 change: add the required context
  `release-hold` bound to the checker App's integration id, and set `strict_required_status_checks_policy:
  true`. Prepare the checker App and environment `release-hold-checker` (branch policy `main`). Prepare
  environment `release-hold-merge` (required reviewer = owner, `can_admins_bypass: false`). (depends on 7)
  — DoD: exact JSON in the runbook, and a dry run in a disposable repository (T24, T26). Applied by the
  owner, never by an agent.
- [ ] 15. Add the post-sync digest verifier (read-only CronJob in `mctl-api`, ServiceAccount allowed only
  `get`/`list` on pods; alert on mismatch or unknown). Make `release-gate-watch.yml` run `release-hold.py`
  from the parent commit's tree. (depends on 3, 8) — DoD: T29 and T22 pass.
- [ ] 16. Coordinate with mctl-gitops#2543. Record in the runbook which #2543 remediation turns P5b/P6 from
  BLOCKING-UNKNOWN into enforced: a broker running `release-hold.py verify`, or a no-bypass path
  restriction proven in a disposable repository. Until then, the decision packet carries D3. (depends on 1)
  — DoD: the runbook rows for P5b/P6 link the #2543 evidence, or the owner's written acceptance.

## Tests

All negative tests run the real embedded bump script and the real "Commit and push" loop. These are
extracted from the workflow YAML, as `tests/test_release_deploy_bump.py` and `tests/test_gitops_bump_inputs.py`
already do. They run against a temporary clone whose `origin` is a local bare repository. **Each negative
test asserts that the bare repository's `main` SHA is unchanged and that no file on disk was rewritten.**
"Refused" alone is not enough.

- [ ] T1. `release-deploy` bump of the bootstrap file to `4.155.0` with no grant refuses with exit 6 and
  no write.
- [ ] T2. The same through the `gitops-bump` script refuses with exit 6 and no write.
- [ ] T3. `4.156.0` and `5.0.0` with no grant are refused (ceiling semantics, not an exact match on 4.155.0).
- [ ] T4. A valid grant with `channel: pull-request`, used through either direct workflow, is refused with
  no write.
- [ ] T5. Each grant defect is refused with no write: expired, `expires_at` more than 7 days after issue,
  wrong `policy_sha256`, owner not in `owners`, merger different from owner, merger `type: Bot`, wrong
  digest, digest absent, wrong `source_commit`, tag ref absent, malformed YAML, missing field.
- [ ] T6. Each unreadable input gives exit 7 with no write: hold file missing, hold file unparseable,
  grant directory unreadable, GitHub API error or timeout, registry error, `values: |` block not found,
  two mctl-api sources, two image matches.
- [ ] T7. The concurrent `main` update case: during the push loop, the bare repository receives a commit
  that removes the hold, the push is rejected, and the script rebases. The `--since START_SHA` monotonic
  check refuses, and the bare `main` holds only the concurrent commit.
- [ ] T8. The rebase/retry case: a concurrent commit adds `MCTL_BRIDGE_PROVIDERS` to `mctl-api.yaml` on
  the bare `main`. After the rebase `verify` refuses, and nothing from this run is pushed.
- [ ] T9. Chart drift: a tree with chart `targetRevision: main` (or `HEAD`, or a branch name) fails
  `verify`, and any bump of the file is refused.
- [ ] T10. Runtime keys in the inline values: `MCTL_BRIDGE_PROVIDERS`, `MCTL_BRIDGE_PROVIDER_TOKENS`,
  `MCTL_BRIDGE_ENABLED: "true"`, `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE: "on"`, and a `valueFrom` on
  either absent_or_false key are each refused. `MCTL_BRIDGE_ENABLED: "false"` and an absent key pass.
- [ ] T11. Secondary injection: a forbidden key added as `secretKey` in `mctl-api-secrets.yaml`, in a
  file under `infra-components/mctl-platform/mctl-api/`, or in `helm-charts/zitadel-iac/iac/*.tf` is refused
  by `diff` and `verify`.
- [ ] T12. `diff` (PR path):
  - a PR that adds a grant and bumps the tag together is refused;
  - a PR that edits an existing grant is refused;
  - a PR that relaxes `release-holds.yaml` is reported `HOLD_POLICY_CHANGED`;
  - a grant present only in head, not in base, does not authorise a bump.
- [ ] T13. Admission (envtest or kind):
  - a Deployment, ReplicaSet or Pod with `ghcr.io/mctlhq/mctl-api:4.155.0` is denied with no grant;
  - one with `MCTL_BRIDGE_PROVIDERS` in env is denied;
  - a Secret in `mctl-api` with key `MCTL_BRIDGE_PROVIDER_TOKENS` is denied;
  - a missing param ConfigMap means deny;
  - `4.154.0` with the current env is admitted.
- [ ] T14. Argo templates: assert that `wft-deploy-service.yaml`, `wft-rollback-service.yaml` and
  `tpl-git-commit.yaml` still build only `platform-gitops/services/` paths (P5 stays KNOWN-NOT-A-PATH).
- [ ] T15. Positive control: an ordinary `release-deploy` bump of `platform-gitops/services/admins/mctl-docs/values.yaml`
  and of `bootstrap/templates/mctl-platform/mctl-portal.yaml` lands exactly one commit on the bare `main`,
  and the mctl-agents worker gate behaviour is unchanged.
- [ ] T16. Positive control: a grant in base (with all checks fed valid answers) plus a PR that changes
  only `tag: "4.155.0"` and the chart SHA to `source_commit` passes `diff --channel pull-request`. The same
  tree with `ROLLOUT_MARKER` also changed still passes (env change allowed), and with
  `MCTL_BRIDGE_ENABLED: "true"` it is refused.
- [ ] T18. Release PR head versus source commit: in a fixture mctl-api repository, release head H is merged
  with a merge commit M and tagged. If `main` gained commit X between H and the merge, `tree(M) != tree(H)`
  and the bump is refused with no write. Without X, the trees are equal and the check passes. The fixture
  also proves which commit release-please tags.
- [ ] T19. Stale grant: a grant whose `reviewed_release_head` is an earlier #934-style head (different tree),
  or whose `source_commit` is not the tag commit, is refused through both direct workflows and through
  `release-hold-merge`, with no write.
- [ ] T20. Revision label absent gives exit 7; a label different from `source_commit` gives exit 6; no write
  in either case.
- [ ] T21. Bump from a different workflow: a fixture workflow file other than the two allowed ones that names
  `environment: gitops-bump` or `GITOPS_BUMP_DEPLOY_KEY` fails the static test. A simulated push from such a
  workflow (no `release-hold.py` call) to the bare repository is reported by the L5 `diff` as a violation.
- [ ] T22. Direct push through the deploy-key bypass (P5b/P6, simulated on the bare repository): one commit
  sets the tag to 4.155.0, adds a grant and extends the allowlist, with no PR. `release-hold.py diff --base
  <parent>` exits 6, because the grant has no owner-merged PR. The detector, run from the parent's script,
  alerts. A variant where the same commit also edits `scripts/release-hold.py` to `exit 0` still alerts. The
  test is named as detection, not prevention, until #2543 lands.
- [ ] T23. PR-controlled guard: a fixture PR edits `scripts/release-hold.py` (or the reader, or a hold
  workflow, or a hold test) together with a tag bump. `release-hold-pr` refuses (`HOLD_POLICY_CHANGED`). A
  canary in the head's script (it writes a file when run) proves that the head script was never executed.
- [ ] T24. Spoofed check (disposable repository with synthetic identities, no production credentials): a
  PR-defined job named `release-hold` posts a success check as GitHub Actions. The ruleset that requires
  `release-hold` from the checker App still blocks the merge.
- [ ] T25. Expiry at merge: a grant that expires between the PR-time check and `release-hold-merge`, or that
  expires within the 15-minute margin, is refused. The PR stays open and `main` is unchanged.
- [ ] T26. `main` moved: a commit tightening the hold (or adding a forbidden key) lands after the PR check.
  `release-hold-merge` refuses. In the disposable repository, `strict` makes a manual merge of the now
  out-of-date PR fail.
- [ ] T27. Head moved: a push to the PR after dispatch makes `release-hold-merge` refuse (`head_sha`
  mismatch), and the merge API with `sha=` refuses. No merge.
- [ ] T28. Identity: the dispatcher or the environment approver is not in `owners`, or is a Bot. Refused,
  no merge.
- [ ] T29. Digest drift: the GHCR digest of the tag differs from the grant at push or at merge time. Refused,
  no write. A fixture pod `imageID` that differs from the allowlist makes the post-sync verifier alert, and
  an unreadable pod list is reported as unknown, never as clean.
- [ ] T30. An allowlist file naming 4.155.0 without a valid grant in the same tree is refused by `verify`
  and by `diff`.
- [ ] T17. Mutation check: removing each layer's call makes at least one of T1-T8 or T18-T30 fail. The
  calls are: check in the bump script, verify in the push loop, `--since`, the per-attempt re-read, the
  expiry margin, the base-only checkout in `release-hold-pr`, the `sha=` and up-to-date checks in
  `release-hold-merge`, the tree equality, and check 4 for direct-pushed grants. The guard_test pattern from `tests/test_release_gate_guard.py`
  is reused.

## Rollback

Every change is a reviewed PR to mctl-gitops, so rollback is `git revert` of that PR through another
reviewed PR, in reverse order:

0. **Ruleset and Apps (task 14; amended 2026-11-11).** If the checker App or its environment fails, every PR
   is blocked (fail-closed). Break-glass: the owner removes the `release-hold` required context from ruleset
   18465404, which is recorded as an incident. While the context is removed, keep #934 Draft and dispatch no
   mctl-api bump. Restore the context before the next guarded merge. `strict` can be turned off
   independently. Remove the required context **before** deleting `release-hold-pr.yml`, never after.
   Reverting `release-hold-merge.yml` returns guarded PRs to a plain human merge, without merge-time
   re-verification.
1. **Admission.** Revert the Deny switch (task 11) to return to Warn/Audit. If mctl-api pods are blocked,
   revert task 10, and root-app prunes the policy and binding. The emergency path is a cluster-admin
   deleting the `mctl-api-release-hold` binding, recorded as an incident, and is followed by the revert PR
   because root-app `selfHeal` would recreate it.
2. **Workflow wiring (tasks 4, 7, 8).** Revert to restore the previous `release-gate.py`-only behaviour.
   This is safe for every service, but it reopens P1-P4 for mctl-api. While reverted, keep the release-please
   PR #934 Draft, and do not dispatch either bump workflow for `ghcr.io/mctlhq/mctl-api`.
3. **Chart pin (task 6).** Revert to restore `targetRevision: main`. Only do this after confirming no held
   content is on mctl-api `main`'s `helm/`.
4. **Policy files (tasks 2, 3).** Remove only after the workflows no longer call `release-hold.py`; a
   missing script is exit non-zero, so a refusal, not a silent pass.

No rollback step touches mctl-api releases, images, credentials or Bridge state. No step deletes or
rotates a deploy key; that belongs to #2543.
