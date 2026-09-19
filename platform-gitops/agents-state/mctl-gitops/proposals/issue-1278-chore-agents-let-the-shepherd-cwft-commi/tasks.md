# Tasks: issue-1278-chore-agents-let-the-shepherd-cwft-commi

All file edits are in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`
unless stated otherwise. Tasks 1-6 are one logical change and must land in a
single commit: any subset leaves the pipeline worse than before (see design,
"Partial edit").

The two shapes, used verbatim everywhere:

- pathspec `:(glob)platform-gitops/agents-state/*/adopted-prs/*/**`
- ERE `^platform-gitops/agents-state/[^/]+/adopted-prs/[^/]+/[^/]+`

- [ ] 1. In the `run-shepherd` `COLLECT` heredoc (~line 493), replace the
  single `PATHSPEC` string with a `PATHSPECS` list holding the existing
  `:(glob)platform-gitops/agents-state/**/.status.yaml` plus the adopted-prs
  pathspec, and splat it into the `git status --porcelain=v1 -z -uall --`
  argv. — DoD: the `git status` call passes both pathspecs; no other line of
  the collector changes; a run that writes only `.status.yaml` produces a
  byte-identical handoff tree to today's.
- [ ] 2. In the same heredoc, widen `ALLOWED` to the alternation of the
  existing `.+/\.status\.yaml` and the adopted-prs ERE, anchored `^...$`, with
  a comment stating that `ALLOWED` and `PATHSPECS` must describe the same set.
  (depends on 1) — DoD: a `.prref.yaml` under a record directory passes; a file
  directly under `agents-state/<svc>/adopted-prs/` (no record dir) and anything
  under `agents-state/<svc>/` that is neither shape still hits the
  "refusing to hand off paths outside the allowed subtree" `sys.exit(1)`.
- [ ] 3. In `commit-and-push`'s `script.source`, define `ALLOWED_RE` once
  (single-quoted assignment, the ERE above alternated with the `.status.yaml`
  shape) and use `grep -vE "$ALLOWED_RE"` for both the `BAD` check over
  `/artifact/tree` (~line 895) and the `BAD_DEL` check over
  `/artifact/deleted.lst` (~line 902). Keep both error messages, updating their
  text to name both allowed shapes. (depends on 2) — DoD: one regex literal in
  the step; both checks still exit 1 on a disallowed path; the symlink /
  special-file `find` guard above them is unchanged and still runs first.
- [ ] 4. Add the adopted-prs pathspec as a second `:(exclude,glob)` term to the
  out-of-scope guard (~line 927) and rename the variable
  `NON_STATUS_CHANGES` -> `OUT_OF_SCOPE`, matching
  `cwft-mctl-agents-investigate.yaml`. Update the refusal message to
  "outside .status.yaml or an adopted-prs record under
  platform-gitops/agents-state/". (depends on 3) — DoD: a checkout holding only
  an adoption record reports nothing out of scope; a checkout holding a change
  anywhere else still exits 1.
- [ ] 5. Add the adopted-prs pathspec to the change detector (~line 934) and
  rename `STATUS_CHANGES` -> `IN_SCOPE_CHANGES`; update its
  "No .status.yaml updates — nothing to commit" message to cover both shapes.
  (depends on 4) — DoD: a tick whose only change is a `.prref.yaml` does NOT
  short-circuit to `activity=none`; a tick with no change in either shape still
  writes `none` and exits 0 before `git add`.
- [ ] 6. Add the adopted-prs pathspec to the `git add --` invocation
  (~line 940), keeping the existing `.status.yaml` pathspec first.
  (depends on 5) — DoD: `git diff --cached` after staging contains both shapes;
  the following `git diff --cached --quiet` defensive branch, the commit
  message construction, the mutex block, and the 5x push/rebase loop are
  untouched.
- [ ] 7. Correct the in-file documentation: step 3 of the
  `workflows.argoproj.io/description` annotation (the "Same `:(glob)` filter as
  the implementer template" sentence, ~line 42) and the
  `# Only .status.yaml files should change in agents-state/` comment above
  `- name: commit-and-push` (~line 732). State both shapes, name
  `mctlhq/mctl-agents#334` as the writer, and state the ordering: this template
  merges first, `SHEPHERD_ADOPT_PRS` is enabled only afterwards.
  (depends on 6) — DoD: no sentence in the file still claims the commit is
  `.status.yaml`-only; `grep -n 'implementer template' ` returns no stale
  claim.
- [ ] 8. Add `tests/test_shepherd_commit_scope.py` implementing T1-T7 below:
  load the CWFT with `pyyaml`, locate the `commit-and-push` template, extract
  `script.source`, and drive it with `sh` against a throwaway git repo (bare
  remote via `file://`, stub `~/.ssh` steps skipped by pre-seeding the config
  or by trimming the ssh preamble in the harness — document whichever the
  implementation uses and assert the trim is anchored so it cannot silently
  drop a guard). (depends on 6) — DoD: the test fails if any one of tasks 1-6
  is reverted, and passes on the merged tree.
- [ ] 9. Add a "Unit-test the shepherd commit scope" step to
  `.github/workflows/validate-manifests.yml`, beside
  `tests/test_tpl_git_commit_yq.py`, with a comment explaining why the scope of
  an agent-driven commit to `main` is tested rather than reviewed.
  (depends on 8) — DoD: the step runs `python3 tests/test_shepherd_commit_scope.py`
  and the job is green on the PR.
- [ ] 10. Record the ordering on both issues: comment on
  `mctlhq/mctl-gitops#1278` and `mctlhq/mctl-agents#334` that this template
  change merges first and `SHEPHERD_ADOPT_PRS` is enabled only after, linking
  each to the other. (depends on 7) — DoD: both issues carry the statement;
  acceptance bullet 3 of the issue is satisfiable by inspection.
- [ ] 11. Post-merge verification note for the operator (in the PR body, not a
  file): wait ~3 minutes for ArgoCD to sync the CWFT before the next tick, per
  `CLAUDE.md` ("Argo snapshots templates at submit time"). — DoD: the PR body
  states the wait and names the first tick to inspect.

## Tests

- [ ] T1. Adoption-only handoff: `/artifact/tree` contains just
  `platform-gitops/agents-state/mctl-web/adopted-prs/pr-42/.prref.yaml`. The
  extracted script commits it, pushes, and writes `yes` to
  `/tmp/onexit/activity`. (Fails today: `STATUS_CHANGES` is empty and the
  script exits 0 with `none`.)
- [ ] T2. Mixed handoff: one `.status.yaml` and one `.prref.yaml`. Exactly one
  commit contains both paths, with the existing
  `chore(agents): shepherd run <DATE>` message shape.
- [ ] T3. Empty handoff: `/artifact` absent, and separately present-but-empty.
  No commit is created, exit code 0, `activity=none` — byte-identical to the
  pre-change behaviour (assert against the commit count on the remote).
- [ ] T4. `.status.yaml`-only handoff: unchanged from today — one commit
  containing exactly that path, `activity=yes`.
- [ ] T5. Refusals: a handoff path outside both shapes
  (`platform-gitops/services/labs/x/values.yaml`); a path inside
  `agents-state/` but in neither shape
  (`agents-state/mctl-web/notes.md`); a `deleted.lst` line outside both
  shapes; and a symlink in the handoff. Each exits non-zero with its own
  message and creates no commit.
- [ ] T6. Deletion of an adoption record listed in `deleted.lst` is applied
  with `git rm -- ':(literal)...'` and reaches the remote; a record whose name
  contains `*` removes only itself (the `:(literal)` regression from
  gitops#1046 must stay fixed for the new shape too).
- [ ] T7. Pathspec pin: assert in a throwaway repo that
  `:(glob)*/adopted-prs/*/**` matches nothing while
  `:(glob)platform-gitops/agents-state/*/adopted-prs/*/**` matches the record,
  so the issue's literal wording is never restored. Assert the collector's
  `ALLOWED` and the step's `ALLOWED_RE` accept and reject the same sample set
  (the "same set" invariant from task 2).
- [ ] T8. `scripts/validate-local-workdir.py`,
  `scripts/validate-agents-state-approval.py --selftest` and
  `kubeconform` (the shepherd file is on the `-ignore-filename-pattern` list,
  so it must stay excluded) all still pass: run the relevant
  `validate-manifests.yml` steps locally before opening the PR.
- [ ] T9. Live smoke, after merge and ~3 minutes of ArgoCD sync: submit a
  one-shot Workflow referencing the CWFT with `dry_run=true` and no adoption
  enabled. Expect `activity=none` or an ordinary `.status.yaml` commit and a
  Succeeded run — proving the widened allow-list did not change the
  no-adoption path.

## Rollback

1. **Immediate, no deploy needed on the `mctl-agents` side.** Leave
   `SHEPHERD_ADOPT_PRS` unset in `cronworkflow-mctl-agents-shepherd.yaml`.
   With no writer, both new expressions match nothing and the template behaves
   exactly as it did before this change — so "rollback" and "merged but not
   enabled" are the same state.
2. **Revert the commit.** `git revert <sha>` on `main`; ArgoCD re-syncs the
   previous CWFT within ~3 minutes and the next tick uses it (templates are
   snapshotted at submit time, so an in-flight tick finishes on whichever
   version it started with). The six gates return to `.status.yaml`-only.
3. **If adoption was already enabled when the revert happens.** Unset
   `SHEPHERD_ADOPT_PRS` in the same change, otherwise the shepherd resumes
   writing records that are silently dropped and the attempt counters stop
   being durable — the exact state `#334` warns about. Already-committed
   records are harmless: nothing but `run_shepherd` reads them, and
   `git rm -r platform-gitops/agents-state/*/adopted-prs/` removes them
   cleanly (`#334` rollback step 3).
4. **If a widened commit lands something unwanted on `main`.** It is an
   ordinary commit under `agents-state/`: `git revert` or `git rm` it. No
   ArgoCD Application watches `agents-state/`, so a bad file there cannot
   degrade a workload; `post-deploy-verify` remains in place for the merge side
   of the shepherd's behaviour, which this change does not touch.
