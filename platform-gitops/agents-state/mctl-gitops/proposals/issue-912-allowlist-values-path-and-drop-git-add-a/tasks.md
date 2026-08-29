# Tasks: issue-912-allowlist-values-path-and-drop-git-add-a

- [ ] 1. Add the `ALLOWED_PREFIXES` tuple and `validate_allowed()` function to
  `gitops-bump.yaml`'s inline Python bump script (`.github/workflows/gitops-bump.yaml`,
  "Bump image tags" step), calling it on `vpath` (when set), on the raw
  `vglob` pattern string (when set), and on every path returned by
  `glob.glob(vglob)` — placed immediately after the existing mutual-exclusivity
  check (`if not vpath and not vglob` / `if vpath and vglob`) and before the
  `os.path.isfile` existence check. — DoD: a dispatch with
  `values_path=.github/workflows/x.yaml` exits non-zero (code 4) with a
  stderr message naming the path and the three allowed prefixes, before any
  `open()` call; a dispatch with a valid `values_path` under
  `platform-gitops/services/` is unaffected.

- [ ] 2. Apply the same change to `release-deploy.yaml`'s inline Python bump
  script (`.github/workflows/release-deploy.yaml`, "Bump image tag(s)" step),
  including validating the constructed default
  `f"platform-gitops/services/{team}/{service}/values.yaml"` when neither
  override is given. (depends on 1, same logic, separate file) — DoD: same
  behavior as task 1, plus a dispatch with no `values_path`/`values_glob`
  override still succeeds for a real `team_name`/`component_name` pair whose
  default values.yaml exists.

- [ ] 3. In both workflows' Python bump script, write the list of files that
  were actually modified (i.e. `out != content` and `n > 0`) to
  `/tmp/gitops-bump-changed-files.txt`, one path per line, at the end of the
  step (after the existing summary prints). (depends on 1, 2) — DoD: the file
  exists after a successful bump run and contains exactly the paths that were
  rewritten, not the full `files` list (files with `WARN — no image pattern
  matched` or `already at <tag>` must not appear).

- [ ] 4. Replace `git add -A` with `git add -- $(cat
  /tmp/gitops-bump-changed-files.txt)` in both workflows' "Commit and push"
  steps, guarding on the file being empty/absent before running `git add` at
  all (treat as "no staged changes" and exit 0, matching current behavior for
  the already-at-target case). (depends on 3) — DoD: `git status` after a
  bump commit shows only the intended file(s) staged even when the runner's
  working tree has unrelated modified/untracked files present; the existing
  "no staged changes" exit-0 short-circuit still works when the bump script
  found nothing to change.

- [ ] 5. Update the inline comments in both workflows that currently say
  "scope is image tag lines only" / describe `git add -A` implicitly, so they
  describe the new allowlist + explicit-add behavior instead of the old
  assumption. (depends on 4) — DoD: no comment in either file references
  `git add -A` or implies unscoped staging.

## Tests

- [ ] T1. Negative: dispatch `gitops-bump.yaml` (or exercise the Python
  script directly with `VALUES_PATH=.github/workflows/x.yaml` set) and
  confirm it fails before modifying any file, with exit code 4 and a message
  naming the allowed prefixes.
- [ ] T2. Negative: same as T1 but with a `..`-embedded path
  (`platform-gitops/services/../../etc/passwd`) and with an absolute path
  (`/etc/passwd`) — both must be rejected by the `..`/absolute-path checks
  before the prefix check runs.
- [ ] T3. Negative: `values_glob` pattern string itself outside the
  allowlist (e.g. `.github/**/*.yaml`) is rejected without ever calling
  `glob.glob()`.
- [ ] T4. Positive: `values_path=platform-gitops/services/labs/claude-remote/values.yaml`
  (a real existing file in this repo) passes validation and the run proceeds
  to the existing tag-bump logic unchanged.
- [ ] T5. Positive: `values_glob=platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`
  passes validation for the pattern string and for every file it expands to.
- [ ] T6. Positive: `values_path=platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`
  passes validation (the platform-bootstrap-service case documented in
  deploy.md and grounded in design.md).
- [ ] T7. Positive, normalization edge case:
  `values_path=platform-gitops/services/./labs/claude-remote/values.yaml`
  (redundant but non-traversal `./` segment) still passes after
  `os.path.normpath`.
- [ ] T8. Commit-scope: after a successful single-file bump, `git show
  --stat HEAD` on the resulting commit lists exactly one changed file, even
  when a scratch file was deliberately left dirty/untracked in the checkout
  before the "Commit and push" step ran (simulating the "unrelated stray
  file" risk `git add -A` had).
- [ ] T9. No-op path: a bump run where the target is already at `new_tag`
  still exits 0 with the "No staged changes" notice and does not call `git
  add` on an empty/missing changed-files list.
- [ ] T10. `release-deploy.yaml` default-path case: dispatch with neither
  `values_path` nor `values_glob` set, for a `team_name`/`component_name`
  whose `platform-gitops/services/<team>/<component>/values.yaml` exists,
  still succeeds (confirms the added validation on the constructed default
  doesn't regress the common case).

## Rollback

Both changes are confined to `.github/workflows/gitops-bump.yaml` and
`.github/workflows/release-deploy.yaml`. If the allowlist proves too narrow
for a real caller after merge (see design.md's "Risk: allowlist too narrow"),
first prefer a fast-follow PR adding the missing prefix to `ALLOWED_PREFIXES`
in both files — this is lower-risk than a full rollback since it only widens
policy, it doesn't touch the `git add -A` removal. If the change needs to be
fully reverted, `git revert` the merge commit for this PR — both workflows
are self-contained (all logic inline, no new files, no gitops-managed state
touched), so a revert cleanly restores the prior `git add -A` + unvalidated
`values_path`/`values_glob` behavior with no follow-up cleanup required. No
data migration, no in-flight state (each dispatch run is independent), so
rollback carries no risk beyond re-exposing the original issue until the fix
is reapplied.

## Operator decisions (approve, 2026-08-29)

- Accepted with three binding adjustments:
  1. Do NOT use `git add -- $(cat <file>)` — unquoted command substitution
     word-splits on spaces/newlines. Use `xargs -r git add --` or a
     `while IFS= read -r` loop over the handoff file.
  2. The /tmp handoff file MUST fail closed: if the bump step reports
     success but the handoff file is missing or empty at `git add` time,
     exit non-zero — a silent no-op commit hides a broken pipeline.
  3. Caller inventory (verified 2026-08-29 across all 23 org repos, record
     as a comment next to the allowlist): the three prefixes
     `bootstrap/templates/mctl-platform/` (mctl-agent/api/portal),
     `argo-workflows/cluster-templates/` (mctl-agents CWFT glob) and
     `services/` (docs/telegram/academy/design and all tenant services)
     cover every real caller of gitops-bump/release-deploy. No fourth
     prefix exists today; adding one requires editing the allowlist
     deliberately.
