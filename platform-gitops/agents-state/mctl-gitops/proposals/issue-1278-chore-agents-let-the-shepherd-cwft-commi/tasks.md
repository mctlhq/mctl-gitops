# Tasks: issue-1278-chore-agents-let-the-shepherd-cwft-commi

All edits are in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`
unless stated otherwise. Line numbers refer to the file as of the commit this
proposal was written against.

- [ ] 1. Widen the handoff filter in `run-shepherd`'s `COLLECT` heredoc.
  Replace the single `PATHSPEC` (L494) with a `PATHSPECS` list holding
  `":(glob)platform-gitops/agents-state/**/.status.yaml"` and
  `":(glob)platform-gitops/agents-state/*/adopted-prs/*/**"`, splat it into
  the `git status` argv (L503-505), and widen `ALLOWED` (L493) to
  `^platform-gitops/agents-state/(?:.+/\.status\.yaml|[^/]+/adopted-prs/pr-[0-9]+/\.prref\.yaml)$`.
  — DoD: a worktree containing a `.prref.yaml` produces it in `/tmp/state-out/tree`;
  a file at `adopted-prs/junk.txt` still exits 1 with the "refusing to hand
  off paths outside the allowed subtree" message; the NUL-walk, rename/copy
  handling, symlink skip and `follow_symlinks=False` copy are untouched.

- [ ] 2. Bind the filter expressions once in `commit-and-push`'s
  `script.source` (depends on 1). Introduce `SPEC_STATUS`, `SPEC_ADOPTED` and
  `ALLOWED_RE` near the top of the script, using the same two pathspecs and
  the same regex as task 1.
  — DoD: every filter site below references these variables; the two
  expressions appear exactly once each in the file.

- [ ] 3. Widen the handoff validators `BAD` (L895) and `BAD_DEL` (L902) to
  `grep -vE "$ALLOWED_RE"` (depends on 2).
  — DoD: a tree containing only `.status.yaml` and `pr-<n>/.prref.yaml`
  passes; a tree containing `platform-gitops/services/...` or
  `adopted-prs/junk.txt` still exits 1 with the existing message; the
  `! -type f` symlink/special-file refusal at L890-894 is unchanged.

- [ ] 4. Widen the `NON_STATUS_CHANGES` guard (L927) to pass both
  `:(exclude,glob)` pathspecs (depends on 2).
  — DoD: with a `.prref.yaml` present in the checkout the guard is silent;
  with a file outside the allowlist present it still exits 1.

- [ ] 5. Widen the change probe (L934), renaming `STATUS_CHANGES` to
  `AGENT_STATE_CHANGES`, to query both pathspecs (depends on 2).
  — DoD: the empty case is behaviourally identical to today — logs
  "nothing to commit", writes `none` to `/tmp/onexit/activity`, `exit 0`.

- [ ] 6. Replace the unconditional `git add` (L940) with guarded argv
  construction (depends on 5): probe each pathspec with `git status` and
  append it via `set -- "$@" …` only when it matched, using `if` blocks rather
  than `[ … ] && …`.
  — DoD: `git add` is never handed a pathspec that matches nothing; a tick
  with only `.status.yaml` changes passes exactly one pathspec; the
  `git diff --cached --quiet` guard at L942 and everything below it —
  commit-message construction, the 5-attempt push/rebase loop, the `activity`
  writes — are unchanged.

- [ ] 7. Correct the three prose blocks that assert the old contract (depends
  on 1-6): the header annotation "Same `:(glob)` filter as the implementer
  template" (L42-43), the "Only `.status.yaml` files should change" banner
  above `commit-and-push` (L731-734), and the `changes` artifact description
  (L285-289). Each names `mctlhq/mctl-agents#334` and this issue, and the
  header note states that the divergence from the implementer template is
  deliberate.
  — DoD: no comment in the file claims the filter is `.status.yaml`-only.

- [ ] 8. Confirm no other gate needs widening (depends on 1).
  — DoD: written confirmation in the PR body that
  `scripts/validate-agents-state-approval.py` globs `*/proposals/*/.status.yaml`
  and is unaffected; that `cwft-mctl-agents-implement.yaml` and
  `cwft-mctl-agents-reconcile.yaml` are deliberately left alone; and that no
  `.gitignore` entry excludes `adopted-prs/`.

- [ ] 9. State the rollout ordering (depends on 1-7). Comment on
  `mctlhq/mctl-agents#334` and on this issue that `SHEPHERD_ADOPT_PRS` may be
  enabled only after this PR is merged and ArgoCD has synced the CWFT.
  — DoD: both issues carry the ordering statement, satisfying the issue's
  third acceptance box.

## Tests

New file `tests/test_cwft_shepherd_commit_pathspec.py`, following the
established pattern of `tests/test_tpl_git_commit_yq.py`: `yaml.safe_load` the
CWFT, pull `script.source` out of the `commit-and-push` template by name, and
run it under `sh` against a temporary git repository with a fabricated
`/artifact` tree. Wire it into `.github/workflows/validate-manifests.yml` as a
`python3 tests/test_cwft_shepherd_commit_pathspec.py` step, alongside the
existing unit-test steps.

- [ ] T1. Adoption record travels: a handoff containing
  `platform-gitops/agents-state/mctl-web/adopted-prs/pr-42/.prref.yaml` is
  accepted, staged and committed; the commit contains that path.
- [ ] T2. **No-adoption regression** (the issue's second acceptance box): a
  handoff containing only a `.status.yaml` change exits 0, produces a commit
  identical in content to the pre-change behaviour, and never trips the
  `git add` "pathspec did not match any files" failure.
- [ ] T3. Guard compatibility: a checkout carrying a `.prref.yaml` does not
  trip `NON_STATUS_CHANGES`.
- [ ] T4. Empty handoff: no `/artifact`, or an `/artifact` with an empty tree
  and empty `deleted.lst`, still logs "nothing to commit", writes `none` to
  `/tmp/onexit/activity`, exits 0, and creates no commit.
- [ ] T5. Fail-closed, tree: a handoff containing
  `adopted-prs/junk.txt`, `adopted-prs/pr-42/evil.sh`, or any path under
  `platform-gitops/services/` exits non-zero and creates no commit.
- [ ] T6. Fail-closed, deletions: a `deleted.lst` naming a path outside the
  allowlist exits non-zero; one naming a real `.prref.yaml` stages that
  deletion.
- [ ] T7. Symlink refusal still fires: a symlink anywhere under `/artifact`
  exits 1 before anything touches the checkout.
- [ ] T8. COLLECT unit test (may live in the same file, invoking the extracted
  heredoc with `python3`): a worktree with a `.prref.yaml` hands it off; one
  with an unexpected path under `adopted-prs/` exits 1.
- [ ] T9. Pathspec sanity, guarding the issue's literal spelling: assert that
  `:(glob)*/adopted-prs/*/**` matches nothing from the repository root and
  that the rooted form matches the record. This is the trap that motivated the
  rooted pathspec; pin it so nobody "simplifies" it back.
- [ ] T10. CI gates pass unchanged: `scripts/validate-shell-param-interpolation.py`
  and `scripts/validate-local-workdir.py` still succeed against the edited
  template.

Manual verification after merge, in order:

- [ ] M1. Wait ~3 minutes for ArgoCD to sync the CWFT (Argo snapshots
  templates at submit time — `CLAUDE.md`).
- [ ] M2. Trigger a `dry_run=true` shepherd tick and confirm it is green and
  commits nothing new.
- [ ] M3. Only then, with `SHEPHERD_ADOPT_PRS` enabled in `mctl-agents`, run a
  real tick against one allowlisted repo and confirm an `adopted-prs/` entry
  appears in `main` — the issue's first acceptance box.

## Rollback

The change is confined to one file and is inert while `SHEPHERD_ADOPT_PRS` is
off, so the ordering gives a free rollback window: if anything looks wrong,
turn the flag off in `mctl-agents` first and the CWFT immediately behaves as
it did before, with no gitops change required.

If the template itself misbehaves — a commit step failing on ticks that
previously succeeded — revert the single commit on a branch and merge it
(`git revert <sha>`; per `CLAUDE.md` this repo's branch-protection exception
covers only `gitops-bump.yaml` and `release-deploy.yaml`, so a revert still
goes through a PR). ArgoCD re-syncs the CWFT within ~3 minutes and the next
tick uses the restored template.

Nothing needs undoing on `main`'s content: any `.prref.yaml` already committed
becomes inert data that no code reads once the flag is off, and can be removed
later in an ordinary cleanup commit. There is no state migration and no
resource to reclaim.
