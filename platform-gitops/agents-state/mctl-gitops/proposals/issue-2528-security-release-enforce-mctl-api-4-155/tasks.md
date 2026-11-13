# Tasks: issue-2528-security-release-enforce-mctl-api-4-155

## Context note

Revision of 2026-11-13. Every task extends the existing gate (`scripts/release-gate.py`,
`platform-gitops/release-gates.yaml` `version_holds`) and existing workflows; no task creates a second
script, policy file or grant directory. Section references are to design.md. Checkbox state is reset: no
task is done because of earlier text. This document is not implementation, an allow record, a release GO
or a residual-risk acceptance.

Preconditions:

- No task starts before an independent review of this text and a separate digest-bound owner approval.
- No task releases, tags, builds, bumps or syncs mctl-api, adds an allow record, reads Secret data, or
  changes keys or the ruleset. Ruleset, App and environment changes (task 14) are prepared by an agent and
  applied by the owner.
- Every PR below touches `protected_re` paths and is merged by a human. Exit codes everywhere: 0 pass,
  6 refused, 7 could not observe; 7 outranks 6 and is never a pass.

- [ ] 1. Update `docs/runbooks/mctl-api-release-hold.md` and `docs/plans/mctl-api-4-155-release-readiness.md`
  (do not duplicate them): the inventory of design.md (P4b row, ACCEPTED-RISK status for P5b/P6, P9
  BLOCKING-UNKNOWN), the "Reconciliation" section replaced by a pointer to this design, readiness step 6
  corrected (tag-only held PR, `release-hold-merge`, no auto-merge, pin not moved with the tag). — DoD: every
  row cites file:line at the PR's base; `grep -n "release-hold.py\|release-holds.yaml\|release-grants"` in both
  documents returns only historical references marked as such.
- [ ] 2. Extend `release-gates.yaml` hold `mctl-api-bootstrap` with `owners`, `runtime_keys`, `guarded`,
  `chart_pin`, `admission_params` (§1.1) and the new record shape in the comment (`release-gates.yaml:45-49`);
  extend `_holds()` (`release-gate.py:203-230`) to validate them, require `expires_at` (quoted, `Z`) and refuse
  `expires`. `allow: []` stays. (depends on 1) — DoD: `python3 scripts/release-gate.py verify` passes on the
  tree; `tests/test_release_gate_bootstrap_hold.py` gains the T5/T6 shape cases and each fails when its
  validation line is reverted. `owners` is entered by the owner.
- [ ] 3. Extend `scripts/release-gate.py` (depends on 2):
  - `policy-digest --hold NAME [--policy-rev REV]` (§1.2);
  - record-level provenance (§1.3) and external checks (§1.4) behind one injectable `_external()`;
  - `check --route direct|pr`, printing `held=true|false`;
  - `diff --context pr|push|merge --expiry-margin DURATION --since SHA` with the classification of §2,
    replacing the blanket refusal at `:480-483` and keeping `:555-557`;
  - `run()` returns 7 when any problem is UNKNOWN.

  — DoD: new `tests/test_release_gate_allow_record.py` (T5, T6, T35, provenance cases of T22) and extended
  `tests/test_release_gate_diff.py` (T12, T16) pass; `--selftest` still passes; the existing worker-gate tests
  in `tests/test_release_gate.py` pass unchanged.
- [ ] 4. Wire `.github/workflows/release-deploy.yaml` and `.github/workflows/gitops-bump.yaml` (depends on 3):
  `check --route` in the bump script (`:354`, `:239`) and its `held` output; `fetch-depth: 0` where a held
  write needs provenance; `START_SHA`; the pre-push `diff` (§3.2) as the last command before every push
  (`release-deploy.yaml:605,702`, `gitops-bump.yaml:486,565`); `await-bump` (`:773`, `:636`) only when
  `held == 'false'`, otherwise a summary line (§3.3); `packages: read` only if D4 resolves that way. — DoD:
  `tests/test_release_deploy_bump.py`, `tests/test_gitops_bump_inputs.py` and
  `tests/test_release_bump_pr_route.py` pass with T1-T4, T7, T8, T19, T29 and T33 added.
- [ ] 5. Advisory notice in `scripts/release-preflight.py preflight` for a held tag ("build allowed, the bump
  needs an allow record"), exit code unchanged. (depends on 3) — DoD: `tests/test_release_preflight.py`
  asserts the notice and the unchanged exit code.
- [ ] 6. Chart pin rule: `verify` refuses a non-40-hex `targetRevision` for `chart_pin.repo_url`. Keep the pin
  at `a5b9ef9cf0f880f28b841033a8b2a6d9563ce050`; correct the comment at `mctl-api.yaml:14-15` to "a pin move is a
  separate reviewed PR". (depends on 3) — DoD: T9 passes; the diff of `mctl-api.yaml` touches comments only.
- [ ] 7. Merge path (depends on 3): extend `protected_re` (`auto-merge.yml:82`) per §4.1; add
  `.github/workflows/release-hold-pr.yml` (§4.2) and `.github/workflows/release-hold-merge.yml` (§4.3). —
  DoD: `tests/test_auto_merge_protected_paths.py` covers T32 and T34; new `tests/test_release_gate_merge_path.py`
  statically asserts that `release-hold-pr.yml` has no checkout of a head ref, runs only
  `python3 -I "$RUNNER_TEMP/gate/release-gate.py"`, never posts success on a non-zero exit, and that
  `release-hold-merge.yml` passes `sha=` and runs `diff --context merge`; T23, T25-T28 pass.
- [ ] 8. In-repo watcher: `release-gate-watch.yml:60` passes `--context push`; header keeps the line 13
  limitation. (depends on 3) — DoD: `tests/test_release_gate_watch.py` covers an ALLOW_CHANGE push without
  provenance (violated) and a failed API read (unknown).
- [ ] 9. `helm template` cross-check: render `platform-gitops/bootstrap` and assert `block_values()` returns
  the same image, tag, env and chart revision for `admins-mctl-api`. (depends on 3) — DoD: the test fails on a
  fixture where Helm and the reader disagree.
- [ ] 10. ValidatingAdmissionPolicy `mctl-api-release-hold`, binding and the static params file (§5),
  `[Warn, Audit]`, `failurePolicy: Fail`, `paramNotFoundAction: Deny`. (depends on 2) — DoD: rendered by
  `helm template`, validate passes, an envtest/kind fixture proves T13; `verify` proves T30.
- [ ] 11. Separate PR switching the binding to `[Deny]` after one sync with no warnings, with the live digest
  added. (depends on 10) — DoD: PR body carries the audit evidence and the digest.
- [ ] 12. Dependency map in the runbook (#934, #2523, mctl-agents#993, #992, mctl-agents#1007, mctl-api#935,
  #1040, #1292), each with "machine-checked: yes/no". (depends on 1) — DoD: each link present.
- [ ] 13. Verify the existing revision label (`build-image.yaml:488-498,635`) against an actual built digest:
  read the config label of a recent non-mctl-api build. No second label writer. — DoD: T20 passes against the
  recorded config blob fixture; the runbook records the observed digest and label.
- [ ] 14. (Owner action, D1/D2) Prepare the ruleset JSON adding `release-hold` bound to the checker App
  (`strict` already `true`), the two Apps and environments `release-hold-checker` and `release-hold-merge`.
  (depends on 7) — DoD: exact JSON in the runbook; T24 and T31 pass in a disposable repository with synthetic
  identities; applied by the owner, never by an agent.
- [ ] 15. Out-of-repo detector and post-sync verifier (§7) in the repository chosen in D7, with the pinned
  gate SHA. (depends on 3, D7) — DoD: T22c and T29 pass; a run that cannot read mctl-gitops alerts "could not
  observe".
- [ ] 16. #2543 coordination: link the owner's dated, attributed P5b/P6 acceptance (scope 4.155.0, expiry,
  incident and rollback owner) in the runbook; record which #2543 stage turns P5b/P6 into KNOWN-ENFORCED.
  (depends on 1) — DoD: the link resolves to an owner-authored record; until it exists the packet reads
  "accepted per owner direction, record not linked: NO-GO".

## Tests

Negative tests run the real embedded bump script and push loop, extracted from the workflow YAML as
`tests/test_release_deploy_bump.py` and `tests/test_gitops_bump_inputs.py` already do, against a temporary
clone whose `origin` is a local bare repository. **Each asserts that the bare `main` SHA is unchanged, no file
was rewritten and no PR was merged.** External reads are fed through `_external()`.

- [ ] T1. `release-deploy` bump of the bootstrap file to 4.155.0 with no record: 6, no write.
- [ ] T2. The same through `gitops-bump`: 6, no write.
- [ ] T3. 4.156.0 and 5.0.0 with no record: refused (`>= held_from`).
- [ ] T4. A valid record on `--route direct`: refused, no write.
- [ ] T5. Each record defect is 6: expired; `expires_at` more than 7 days after `merged_at`; wrong
  `policy_digest`; `approved_by` not in `owners`; `merged_by` login or id different from `approved_by`/`owners`;
  `merged_by.type == "Bot"`; provenance PR touching another file; wrong digest; wrong `source_commit`; tree
  mismatch; label different; `expires` date field; unquoted `expires_at`; missing field.
- [ ] T6. Each unreadable input is 7: policy missing or unparseable; shallow history; GitHub API error or
  timeout; GHCR error; label missing; values block not found; two image references; PR file list unreadable
  or count different from `changed_files`.
- [ ] T7. `--since`: a concurrent commit changes the hold rules; after the rebase the run refuses; bare `main`
  holds only the concurrent commit.
- [ ] T8. A concurrent commit adds `MCTL_BRIDGE_PROVIDERS`; after the rebase the pre-push `diff` refuses.
- [ ] T9. Chart `targetRevision` `main`, `HEAD` or a branch: `verify` refuses; `a5b9ef9c...` passes.
- [ ] T10. Inline values: each forbidden key, `MCTL_BRIDGE_ENABLED: "true"`, the queue key `"on"`, and
  `valueFrom` on an absent_or_false key are refused; `"false"` and absent pass.
- [ ] T11. A forbidden key in each `guarded` file family is refused by `diff` and `verify`.
- [ ] T12. Classification: ALLOW_CHANGE + HELD_TAG refused; POLICY_CHANGE + HELD_TAG refused
  (`HOLD_POLICY_CHANGED`); a record present only in head does not authorise a tag; editing or removing the
  record of the deployed version is refused; a worker `min_tag` change alone is POLICY_CHANGE, not refused.
- [ ] T13. Admission: 4.155.0 without an allowlist entry denied; forbidden env denied; Secret with
  `MCTL_BRIDGE_PROVIDER_TOKENS` denied; missing params denied; 4.154.0 with current env admitted.
- [ ] T14. Argo templates still build only `platform-gitops/services/` paths (P5a).
- [ ] T15. Positive control: an ordinary bump of `platform-gitops/services/admins/mctl-docs/values.yaml` and of
  `mctl-portal.yaml` lands exactly one commit; worker-gate behaviour unchanged.
- [ ] T16. Positive control: a valid record on base plus a PR that changes only the tag line passes
  `diff --context merge` (HELD_TAG). The same PR also changing the chart pin or `ROLLOUT_MARKER` is refused
  (HELD_TAG + HELD_CONTENT), consistent with `release-gate.py:555-557`. `ROLLOUT_MARKER` alone is HELD_CONTENT:
  `release-hold` success, human merge.
- [ ] T18. Fixture mctl-api repository: release head H merged as M and tagged; with an intervening commit X,
  `tree(M) != tree(H)` and the record is refused; without X it passes; the fixture shows which commit is tagged.
- [ ] T19. A record bound to an earlier head (different tree) or to a non-tag `source_commit` is refused in
  `check`, the pre-push `diff` and `release-hold-merge`.
- [ ] T20. Revision label absent: 7; different from `source_commit`: 6.
- [ ] T21. A fixture workflow naming `environment: gitops-bump` or `GITOPS_BUMP_DEPLOY_KEY` fails
  `tests/test_gitops_write_credential_holders.py`; a simulated push from it is a watcher violation.
- [ ] T22. Deploy-key push simulations on the bare repository (detection, not prevention, until #2543):
  (a) one commit sets 4.155.0, adds a record and a params entry: `diff --context push` exits 6 (no provenance);
  (b) a push that changes `digest` of an owner-merged record: 6 (provenance moves to the push);
  (c) as (a), and the same commit edits `release-gate-watch.yml` and `release-gate.py` to exit 0: the in-repo
  watcher of the pushed commit does not alert (asserted; documented limitation), and the out-of-repo detector
  with the pinned script alerts.
- [ ] T23. A PR editing `release-gate.py` or a hold workflow together with a tag bump: `release-hold-pr`
  reports `HOLD_POLICY_CHANGED`; a canary in the head script proves it never ran.
- [ ] T24. Disposable repository: a PR-defined job named `release-hold` posting as GitHub Actions does not
  satisfy the App-bound context.
- [ ] T25. `release-hold-merge` with a record expired or expiring within 15 minutes: no merge, `release-hold`
  failure re-posted.
- [ ] T26. `main` moved after step 2 (incl. a simulated deploy-key push): merge refused by `strict`; no merge.
- [ ] T27. Head moved after dispatch: refused at step 1 or by `sha=`; no merge.
- [ ] T28. Dispatcher or approver not in `owners`, or a Bot: refused, no merge.
- [ ] T29. GHCR digest differs from the record at push or at merge: refused, no write. A pod `imageID` that
  differs makes the post-sync verifier alert; an unreadable pod list is "unknown", never clean.
- [ ] T30. A params file naming 4.155.0 without a matching record: refused by `verify` and `diff`.
- [ ] T31. Disposable repository: a merger-App merge with `sha=` succeeds only when every ruleset rule holds
  (including `require_extra_approval_for_unattributed_changes`); otherwise the owner-merge fallback is
  recorded. A fork PR: `release-hold-pr` refuses a fetched head that is not `head_sha`.
- [ ] T32. P4b: a `release-bump/mctl-api-4.155.0` PR with a valid record and a bot approval stays open
  (`protected_re`); a `release-bump/*` PR for another image still merges once `CLEAN`.
- [ ] T33. P4b: a held `publish-pr` run skips `await-bump`, writes the summary and ends without waiting; a
  missing `held` output is treated as held.
- [ ] T34. Every `version_holds[].file` matches `protected_re`; removing the mctl-api entry fails the test.
- [ ] T35. `policy_digest` is stable across key order, whitespace and comments; unchanged by a worker
  `min_tag` raise or an added record; changed by an edit of `held_from`, `owners`, `runtime_keys`, `guarded`,
  `chart_pin` or `file`.
- [ ] T17. Mutation matrix (pattern of `tests/test_release_gate_guard.py`): removing each of the following
  makes at least one test above fail: `check` in each bump script; the pre-push `diff` in each publish job;
  `--since`; per-attempt re-read; the expiry margin; record-level provenance; `approved_by`/`owners` match;
  `policy_digest`; tree equality; the classification refusals; `run()` returning 7; the base-only
  `python3 -I` execution in `release-hold-pr`; `sha=` and up-to-date checks in `release-hold-merge`; the
  mctl-api entry in `protected_re` and the `held` gate on `await-bump` (P4b); the out-of-repo detector's pinned
  script (T22c).

## Rollback

Every change is a reviewed PR to mctl-gitops; roll back with `git revert` through another reviewed PR, in
reverse order:

0. **Ruleset and Apps (task 14).** If the checker App fails, every PR is blocked (fail-closed). Break-glass:
   the owner removes the `release-hold` context (recorded as an incident); keep #934 Draft and dispatch no
   mctl-api bump until it is restored. Remove the context before deleting `release-hold-pr.yml`, never after.
1. **Admission.** Revert task 11 to return to Warn/Audit; revert task 10 if pods are blocked. A cluster-admin
   deleting the binding is an incident followed by the revert PR (root-app `selfHeal` would recreate it).
2. **Workflows (tasks 4, 7, 8).** Reverting returns to today's `version_holds` floor with `allow: []`, which
   still refuses every tag `>= 4.155.0`; it only loses digest/provenance binding and the trusted merge.
3. **Gate extension (tasks 2, 3).** Revert only after the workflows no longer pass the new flags; an unknown
   flag is a non-zero exit, so a refusal, not a pass.

No rollback step touches mctl-api releases, images, credentials, deploy keys or Bridge state.
