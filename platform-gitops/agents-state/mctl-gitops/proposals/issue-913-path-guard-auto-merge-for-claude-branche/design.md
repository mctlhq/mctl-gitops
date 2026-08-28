# Design: issue-913-path-guard-auto-merge-for-claude-branche

## Current state

`.github/workflows/auto-merge.yml` has two jobs:

- `request-review`: on `pull_request` `opened`/`synchronize` where
  `startsWith(github.head_ref, 'claude/')`, adds `copilot` as a reviewer.
- `auto-merge`: on `pull_request_review` `submitted`, guarded by
  `github.event.review.state == 'approved' &&
  startsWith(github.event.pull_request.head.ref, 'claude/')`. Its single
  step runs `gh pr merge <number> --merge --delete-branch` unconditionally.
  No checkout, no diff inspection, no path logic at all.

Two other repo-owned workflows push straight to `main` without a PR
(`gitops-bump.yaml`, `release-deploy.yaml`'s `bump` job) — CLAUDE.md's
"Branch Protection Exception" section documents that this is safe because
each is mechanically scoped to a single `image.tag` field. `auto-merge.yml`
has no equivalent scoping today: it merges the PR's diff verbatim, whatever
it touches.

`validate-manifests.yml` establishes the repo's convention for CI logic
that is more than a one-liner: put it in a standalone script under
`scripts/` (`scripts/validate-platform-skills.py`,
`scripts/materialize-openclaw-platform-skills.py`,
`scripts/validate-local-workdir.py`) and invoke it with `python3
scripts/<name>.py` from the workflow. `pyyaml` is already a workflow
dependency (`python3 -m pip install --quiet pyyaml`), and these scripts are
plain, dependency-light, and independently runnable.

`claude-review.yml` (reusable workflow from `mctlhq/.github`) is the only
other automation that inspects `claude/*` / bot PRs in this repo; it is a
review gate, not a merge gate, and is unaffected by this change.

Elsewhere on the platform, `platform-gitops/services/labs/mctl-agent`
(`PR_STEWARD_*` env, values.yaml ~line 66-90) runs a *different*
auto-merge system (`pr-steward`) for other repos (`mctl-telegram`,
`mctl-pairdesk`, `mctl-design`, `mctl-docs`), configured per-repo with a
branch-prefix + `merge_mode`. `mctl-gitops` itself is explicitly on
`merge_mode: never` there ("phase A; switch to when-green after the
existing implementer backlog is triaged" — see
`docs/plans/github-first-implementer-pr-lifecycle.md`). So today
`mctl-gitops`'s only live auto-merge path for `claude/*` branches is this
repo's own `auto-merge.yml`. That is the sole target of this proposal.

## Proposed solution

Add a path allowlist gate as a new step in the `auto-merge` job, between
the trigger condition and the existing `gh pr merge` step, following the
repo's `scripts/`-script convention:

1. **New script `scripts/check_pr_path_allowlist.py`** (plain script, no
   third-party deps beyond stdlib — unlike the `validate-*.py` scripts it
   doesn't need `pyyaml`). Reads changed file paths one per line from
   stdin, checks each against a hardcoded allowlist:

   ```python
   ALLOWED_PREFIXES = (
       "platform-gitops/services/",
       "platform-gitops/agents-state/",
   )
   ```

   Prints any non-matching path to stdout (one per line) and exits `1` if
   any exist; exits `0` (silent) if every path matches or the input is
   empty. Matching is a plain `str.startswith()` prefix check against the
   GitHub-API-reported repo-relative path — no filesystem access, no glob
   library, nothing that a crafted filename could trick.

   The script lives outside `platform-gitops/services/**` and
   `platform-gitops/agents-state/**`, so it is itself never on the
   allowlist: a `claude/*` PR cannot widen or disable the gate and then
   have that same PR auto-merge. Widening the allowlist always requires a
   PR that a human approves through the normal path (the script sits under
   `scripts/`, which only `request-review`'s Copilot-reviewer nudge covers
   — same review posture as any other `.github`/`scripts` change today).

2. **Modify the `auto-merge` job** in `.github/workflows/auto-merge.yml`:

   - Add `actions/checkout` (same pinned SHA already used by
     `validate-manifests.yml`), checking out
     `${{ github.event.pull_request.base.ref }}` — the **base** branch,
     not the PR head. This is deliberate: the gate logic must not be
     something the PR under evaluation can influence. Since the job only
     needs `scripts/check_pr_path_allowlist.py` as it exists on `main`,
     checking out base is both safer and correct.
   - Add a step that lists changed files via the paginated REST endpoint
     (not `gh pr view --json files`, which is unpaginated and silently
     truncates around 100 entries):
     ```bash
     gh api "repos/${{ github.repository }}/pulls/${{ github.event.pull_request.number }}/files" \
       --paginate --jq '.[].filename'
     ```
   - Pipe that list into `python3 scripts/check_pr_path_allowlist.py`,
     capture its exit code and stdout (blocked-file list) without letting
     a non-zero exit fail the job (`if ... ; then / else` around the
     python3 call, or `|| true` + explicit `$?` capture), and set a step
     output `allowed=true|false` via `$GITHUB_OUTPUT`.
   - Gate the existing merge step on `steps.path-check.outputs.allowed ==
     'true'`.
   - Add a new step, gated on `steps.path-check.outputs.allowed ==
     'false'`, that:
     - Checks existing PR comments for a marker string
       (`<!-- auto-merge-path-guard -->`) via
       `gh api repos/.../issues/<n>/comments --jq '...'`.
     - If absent, posts one comment (via `gh pr comment`) containing the
       marker, the list of out-of-allowlist files, and a one-line
       explanation ("This PR touches paths outside the auto-merge
       allowlist and requires a manual merge after review.").
   - If the `gh api ... /files` call itself fails (network/API error), let
     the step fail naturally (`set -euo pipefail`) — the job goes red, no
     merge happens, matching the "fail closed" requirement.

   No change to `request-review` — it only requests review, adds no
   privilege.

3. **`skip a claude/* PR touching .github/workflows/**` verification**:
   since `.github/workflows/` does not start with either allowed prefix,
   any changed file there — including edits to `auto-merge.yml` itself —
   is caught by the same generic prefix check. No special-case code needed
   for "workflows" as a category; it falls out of the allowlist being
   *inclusive* rather than the old behavior being *unrestricted*.

## Alternatives

1. **`dorny/paths-filter` (third-party action) instead of a repo script.**
   Rejected: every other workflow in this repo either uses first-party
   `actions/*` actions or a repo-owned `scripts/*.py` script (see
   `validate-manifests.yml`); introducing a new third-party action for a
   ~15-line prefix check adds a supply-chain dependency (and a SHA to pin
   and rotate) for no real gain over stdlib string matching. Also,
   `paths-filter` computes the diff between two refs on disk, which would
   require checking out the PR head — the exact thing alternative 3 (and
   the chosen design) deliberately avoids.

2. **Denylist instead of allowlist** (block `.github/workflows/**`,
   `platform-gitops/bootstrap/**`, secrets paths explicitly; allow
   everything else). Rejected: a denylist only stays safe if every future
   sensitive directory is remembered and added to it. The issue explicitly
   asks for an allowlist ("diff the PR's changed files against an
   allowlist... If any file falls outside, skip"), and an allowlist fails
   closed by construction — a new top-level directory added to the repo
   next month is automatically NOT auto-mergeable until someone
   deliberately opts it in, which is the safer default for a GitOps repo
   that is the ArgoCD source of truth for the whole platform.

3. **Check out the PR head and run the allowlist script from there**
   (simpler mental model: "run the checked-in version of the check
   against the PR's own tree"). Rejected: that lets a `claude/*` PR that
   edits `scripts/check_pr_path_allowlist.py` (e.g. widening the allowlist
   to include `.github/workflows/`) evaluate itself against its own
   loosened rule and auto-merge in one shot with a single approval — the
   exact self-approval hole the "auditor" user story in requirements.md
   calls out. Running the check from the base ref closes this.

4. **Do the allowlist check inline in the workflow YAML (bash/jq only, no
   python script).** Considered and partially rejected: prefix matching is
   simple enough to do in bash, but the repo's established pattern
   (`validate-manifests.yml`) is to push anything beyond a couple of lines
   into a `scripts/*.py` file so it's independently testable and readable
   in a diff. Given this logic is security-relevant, testability wins.

## Platform impact

- **Migrations / backward compatibility**: none. No schema, no data. Purely
  additive workflow logic; a `claude/*` PR that only touches
  `platform-gitops/services/**` or `platform-gitops/agents-state/**`
  behaves identically to today (still merges on one approval).
- **Resource impact**: negligible — one extra `actions/checkout` and one
  extra `gh api --paginate` call per approved `claude/*` PR review event.
- **Risk: false positive blocks a legitimate routine PR.** Mitigation:
  allowlist starts with exactly the two prefixes the issue names, which
  cover the overwhelming majority of `claude/*` traffic (service values
  bumps, agent proposal state); the posted comment tells a human exactly
  which file tripped the gate, so recovery is "merge manually," not "PR is
  stuck forever."
- **Risk: comment spam on repeated review events.** Mitigated by the
  marker-comment de-dup check before posting.
- **Risk: pagination bug re-introduces the >100-files blind spot.**
  Mitigated by explicitly requiring `--paginate` on the `gh api` call
  (acceptance criterion) instead of `gh pr view --json files`, and by a
  task to add a test asserting this.
- **Risk: this very PR (which touches `.github/workflows/auto-merge.yml`
  and adds `scripts/check_pr_path_allowlist.py`) cannot demonstrate its
  own fix by auto-merging** — by design, since neither path is on the
  allowlist, this PR itself will be blocked by the gate it introduces and
  require manual merge. That is the correct, intended outcome, not a bug.
