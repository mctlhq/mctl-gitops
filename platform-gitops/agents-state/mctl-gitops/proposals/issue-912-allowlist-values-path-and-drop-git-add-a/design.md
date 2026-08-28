# Design: issue-912-allowlist-values-path-and-drop-git-add-a

## Current state

Two reusable `workflow_dispatch` workflows push tag-bump commits straight to
`main`, both minting an `mctl-agents` GitHub App token that is on the
`main-protection` ruleset's bypass list (`.github/workflows/gitops-bump.yaml`
lines 64-76, `.github/workflows/release-deploy.yaml` lines 81-93; the
rationale is documented inline in both files and in this repo's `CLAUDE.md`
under "Branch Protection Exception — Automated Bot Commits").

`gitops-bump.yaml`:
- Inputs: `image_name`, `image_tag`, and exactly one of `values_path` /
  `values_glob` (mutual exclusivity checked inline in the Python bump script,
  lines 95-100).
- The "Bump image tags" step (lines 78-179) resolves `files` from either the
  literal `vpath` or `sorted(glob.glob(vglob))`, checks `os.path.isfile` on
  each, then rewrites image-tag patterns in place with regex substitution.
  Nothing constrains `vpath`/`vglob` to any directory — a value of
  `.github/workflows/ci.yml` or `../../etc/passwd`-style traversal is only
  ever checked for "does this file exist", not "is this file supposed to be
  touched by this workflow".
- The "Commit and push to main" step (lines 181-197) runs `git add -A`,
  meaning the commit's contents are whatever the working tree happens to
  contain at that point — not scoped to the file(s) the previous step
  actually edited.

`release-deploy.yaml`:
- Same shape, plus a `build` job that builds the image first. The `bump` job
  (lines 59-235) has an identical Python bump script (lines 105-189, with the
  same `files` resolution logic and the same absence of path validation),
  and the same `git add -A` in "Commit and push" (line 200).
- Default when neither override is given: computed server-side as
  `f"platform-gitops/services/{team}/{service}/values.yaml"` (line 131) —
  this one is already constrained by construction since `team`/`service` are
  plain `workflow_dispatch` string inputs interpolated into a fixed prefix,
  not attacker-controlled path segments in the traversal sense, but it is
  still worth validating for defense in depth per the requirements.

Real callers of the override inputs, confirmed by reading this clone:
- `platform-gitops/argo-workflows/cluster-templates/` holds
  `cwft-mctl-agents-*.yaml` files whose `agent_image` parameter carries an
  inline `value: <image>:<tag>` (see the "Pattern 4" comment duplicated in
  both bump scripts, e.g. `gitops-bump.yaml` lines 145-152). These are bumped
  via `values_glob`, e.g.
  `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`.
- `platform-gitops/services/<team>/<component>/values.yaml` is the default
  target for ordinary per-tenant services (confirmed directory listing:
  `platform-gitops/services/{admins,labs,ovk}/<service>/`).
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`,
  `mctl-api.yaml`, and `mctl-portal.yaml` each contain an `image:`/`tag:`
  block (confirmed by reading each file: `mctl-agent.yaml` line 18
  `tag: "1.16.2"`, `mctl-api.yaml` line 18 `tag: "4.32.7"`,
  `mctl-portal.yaml` line 258 `tag: 4.13.0`). These three are exactly the
  platform-bootstrap services named in
  `platform-gitops/platform-skills/catalog/mctl-platform/references/deploy.md`
  ("Pattern A" repos: mctl-agent, mctl-api, mctl-agents, mctl-docs,
  mctl-portal, mctl-telegram) whose doc text explicitly says to add
  `values_path`/`values_glob` "only if that repo's gitops values file isn't
  at the default `platform-gitops/services/<team>/<component>/values.yaml`"
  — i.e. these are the documented real-world case that needs an override
  pointed outside `platform-gitops/services/`.

No shared script directory is used by either workflow today — both inline
the entire bump script as a Python heredoc, and the two scripts are already
near-duplicates of each other (same regex patterns, same structure, same
inline comments copy-pasted verbatim). There is a `scripts/` directory at
repo root, but nothing in `.github/workflows/` currently invokes a script
from it for this logic (`scripts/materialize-openclaw-platform-skills.py`
and friends are invoked by `validate-manifests.yml` for a different purpose).

## Proposed solution

Add an allowlist-validation function to the top of each workflow's existing
inline Python bump script (duplicated in both files, matching the existing
duplication convention — see Alternatives for why this beats extracting a
shared script), and replace `git add -A` with an explicit file list in the
"Commit and push" step of both workflows.

1. **Allowlist constant**, defined identically in both scripts:
   ```python
   ALLOWED_PREFIXES = (
       "platform-gitops/services/",
       "platform-gitops/argo-workflows/cluster-templates/",
       "platform-gitops/bootstrap/templates/mctl-platform/",
   )
   ```

2. **Validation function**, run on every candidate path (the raw
   `values_path`, the raw `values_glob` pattern string itself, and every file
   the glob expands to) before any `open()`/`os.path.isfile()` call:
   ```python
   def validate_allowed(path):
       if os.path.isabs(path):
           print(f"ERROR: path must be relative, got absolute path: {path}", file=sys.stderr)
           sys.exit(4)
       # normpath collapses "a/../b" segments; comparing before/after catches
       # any ".." traversal attempt without relying on normpath alone (a
       # symlink-free repo checkout means normpath is sufficient here, but
       # the explicit ".." substring check documents intent and fails closed
       # even if a future path shape confuses normpath).
       if ".." in path.split("/"):
           print(f"ERROR: path must not contain '..' segments: {path}", file=sys.stderr)
           sys.exit(4)
       normalized = os.path.normpath(path)
       if not normalized.startswith(ALLOWED_PREFIXES):
           print(
               f"ERROR: path '{path}' is not under an allowed prefix. "
               f"Allowed: {', '.join(ALLOWED_PREFIXES)}",
               file=sys.stderr,
           )
           sys.exit(4)
   ```
   Call `validate_allowed(vpath)` right after the existing mutual-exclusivity
   check (both scripts already have `if not vpath and not vglob: ...` /
   `if vpath and vglob: ...` blocks at this exact point — the new call slots
   in immediately after). For `values_glob`, validate the raw glob pattern
   string first (so a glob pattern that starts outside the allowlist fails
   before `glob.glob()` even runs), then validate every path returned by
   `glob.glob(vglob)` individually (so a glob pattern that is itself
   allowlisted but expands somewhere unexpected — not achievable with
   Python's `glob` today, since it never crosses `..` unless the pattern
   contains it, but validating expanded paths too costs nothing and matches
   the "WHEN a values_glob expands ... validate every expanded file"
   acceptance criterion literally).

   `release-deploy.yaml`'s default-path branch
   (`files = [vpath or f"platform-gitops/services/{team}/{service}/values.yaml"]`)
   gets the same `validate_allowed()` call applied to whichever value ends up
   in `files[0]`, so the constructed default is checked too (defense in
   depth; `team`/`service` are free-form strings and nothing today stops a
   `team_name` containing `../` from escaping `platform-gitops/services/`
   before this change).

3. **`git add -A` replacement.** Both scripts already build (and print) the
   `files` list and already know, per file, whether it changed
   (`out == content` branch). Change the Python step to additionally write
   the set of files that were actually modified (i.e. `total_replaced > 0`
   for that path) to a step output or a temp file, e.g. append each changed
   path to `$GITHUB_OUTPUT` as a newline-joined `changed_files` value (GitHub
   Actions multiline output syntax) or write them to
   `/tmp/gitops-bump-changed-files.txt`, one path per line — the temp-file
   approach is simpler to shell-quote correctly than multiline
   `GITHUB_OUTPUT` and avoids depending on the output being well-formed
   across job boundaries within the same job. Then in "Commit and push":
   ```bash
   set -euo pipefail
   git config user.email "ci@mctl.ai"
   git config user.name  "mctl-ci"
   if [[ ! -s /tmp/gitops-bump-changed-files.txt ]]; then
     echo "::notice::No staged changes (already at ${NEW_TAG})"
     exit 0
   fi
   git add -- $(cat /tmp/gitops-bump-changed-files.txt)
   if git diff --staged --quiet; then
     echo "::notice::No staged changes (already at ${NEW_TAG})"
     exit 0
   fi
   ...
   ```
   Using `git add -- <files>` (double-dash) rather than bare `git add
   <files>` so a resolved path that happens to start with `-` can never be
   misparsed as a flag — the allowlist already forbids this in practice
   since all allowed prefixes start with `platform-gitops/`, but the
   double-dash costs nothing and is the correct defensive default for any
   `git add` fed a variable file list.

   The two-stage "changed files" hand-off (write in the Python step, read in
   the bash step) keeps the existing step boundary and existing division of
   responsibility (Python computes/edits, bash commits/pushes) rather than
   merging the steps, which would be a larger diff for no behavioral gain.

4. **Error exit codes.** Both scripts already use a small convention of
   distinct exit codes per failure class (1 = missing/conflicting inputs, 2 =
   file-not-found/empty-glob, 3 = no pattern matched). Allowlist violations
   use a new `sys.exit(4)`, consistent with that convention, so CI logs and
   any future automation parsing exit codes can distinguish "policy
   violation" from "just a typo'd path".

## Alternatives

1. **Extract a shared `scripts/validate-values-path.py` invoked by both
   workflows.** Rejected for this change: the two workflows already
   duplicate their entire ~85-line bump script verbatim rather than sharing
   it (confirmed by diffing `gitops-bump.yaml` lines 86-179 against
   `release-deploy.yaml` lines 115-189 — they are near-identical). Adding a
   shared file for only the new validation logic, while leaving the larger
   pre-existing duplication in place, would split one script's logic across
   two locations without fixing the actual duplication problem, and would
   require a `checkout` + `PYTHONPATH`/invocation wiring change that neither
   workflow currently has. If the existing duplication is worth fixing,
   that is a separate, larger refactor outside this issue's scope (touches
   trigger/permission surface neither workflow's issue asked to change).

2. **Enforce the allowlist as a CODEOWNERS-style path restriction on the App
   token / branch ruleset instead of in-workflow validation.** Rejected:
   GitHub's ruleset bypass mechanism (used here) does not support per-path
   scoping of a bypass — the bypass is granted to the App identity for the
   whole ruleset, not narrowed to specific file globs. Enforcing the scope
   has to happen in the workflow that decides what to commit, which is what
   this design does.

3. **Reject on first violation for the whole run vs. best-effort skip-and-
   continue for out-of-allowlist files in a glob.** Rejected the
   skip-and-continue variant: the issue's acceptance criteria say "fails the
   run", and silently dropping a file from a glob because it happened to
   fall outside the allowlist would be a surprising, hard-to-notice partial
   success — worse than a loud failure that tells the caller exactly which
   path violated policy and which prefixes are allowed.

## Platform impact

- **Backward compatibility.** All three real call shapes identified above
  (`platform-gitops/services/...`, glob under
  `platform-gitops/argo-workflows/cluster-templates/...`, and
  `platform-gitops/bootstrap/templates/mctl-platform/...`) remain allowed
  unchanged — no existing caller's `values_path`/`values_glob` value needs
  to change. This is the acceptance criterion "Normal image-bump dispatches
  still commit only the intended file."
- **New failure mode, intentional.** A dispatch with
  `values_path=.github/workflows/x.yaml` now fails fast with a clear
  stderr message and exit code 4, before any file is opened — this is the
  issue's other acceptance criterion, verified by a new negative test (see
  tasks.md).
- **No migration needed.** This only touches two `.github/workflows/*.yaml`
  files; no gitops-managed Kubernetes/Helm state changes, no ArgoCD
  Application changes, no Vault/ExternalSecret changes.
- **Risk: allowlist too narrow, breaking a caller not visible in this
  read-only clone.** Mitigated by grounding the three prefixes in files that
  actually exist and carry `image:`/`tag:` data (not guessed), and by
  recording the gap explicitly in Open questions so a human reviewer can
  cross-check against any caller inventory they have that this clone
  doesn't expose (e.g. other repos' `release-please.yml` dispatch steps).
  If a real caller breaks post-merge, the fix is a one-line allowlist
  addition, not a redesign.
- **Risk: `..`/absolute-path check has a gap.** `os.path.normpath` on a
  path that is already relative and allowlist-prefixed cannot escape the
  prefix without a `..` segment, and the explicit `".." in path.split("/")`
  check runs before the prefix check, so a path like
  `platform-gitops/services/../../etc/passwd` is caught by the `..` check
  before it ever reaches the prefix `startswith` test. Mitigation: the task
  list includes explicit tests for both `..`-embedded and absolute-path
  inputs, and for a path that only becomes allowlisted after normalization
  (e.g. `platform-gitops/services/./labs/foo/values.yaml`, which must still
  pass).
- **No resource/runtime impact.** Validation is a handful of string
  operations against a 3-4 file list; no measurable change to job duration.
