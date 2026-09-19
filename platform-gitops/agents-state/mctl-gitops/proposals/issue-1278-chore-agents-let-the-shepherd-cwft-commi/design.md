# Design: issue-1278-chore-agents-let-the-shepherd-cwft-commi

## Current state

Everything relevant lives in one file:
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`
(1496 lines). The `shepherd-proposals` entrypoint runs
`run-shepherd` -> (`shepherd-fallback`) -> `commit` -> `verify` ->
`assert-produced`. There is no shared PVC: each step's `initContainer`
SSH-clones `mctl-gitops` for itself, and cross-step state travels as Argo
artifacts addressed by literal S3 keys (see the "No PVC" note on
`spec.volumes`, and `mctl-gitops#856`).

State produced by a tick therefore crosses **two** boundaries, and each one is
independently scoped to `.status.yaml`:

**1. The collector inside `run-shepherd`.** After the orchestrator exits, an
inline `python - "$RC" <<'COLLECT'` heredoc (lines ~482-589) walks
`git status --porcelain=v1 -z -uall` over a single pathspec and copies the
matches into `/tmp/state-out/tree`, recording removals in
`/tmp/state-out/deleted.lst`:

```python
ALLOWED  = re.compile(r"^platform-gitops/agents-state/.+/\.status\.yaml$")
PATHSPEC = ":(glob)platform-gitops/agents-state/**/.status.yaml"
```

Anything not matching `PATHSPEC` is never seen; anything matching `PATHSPEC`
but failing `ALLOWED` (or containing `..` / control characters) is a hard
`sys.exit(1)`. The result is uploaded as the `changes` artifact at
`{{workflow.name}}/agents-state.tgz`.

**2. `commit-and-push`.** It holds the `mctl-gitops-main-writes` mutex at
template level (hoisted down from spec level so the 5-minute
`post-deploy-verify` sleep no longer holds the global write lock), clones a
pristine checkout in its own `initContainer`, then in its `script.source`
(lines ~831-981):

- short-circuits to `activity=none` if `/artifact` is absent or empty;
- refuses any non-regular file in the handoff (`find /artifact -mindepth 1
  ! -type d ! -type f`) — the guard that matters, because `git status` cannot
  see into `.git/` (agy P1 on gitops#1042);
- refuses handoff paths failing
  `grep -vE '^platform-gitops/agents-state/.+/\.status\.yaml$'` (`BAD`), and
  the same regex over `deleted.lst` (`BAD_DEL`);
- `cp -a /artifact/tree/platform-gitops/agents-state/. ...` onto the fresh
  clone, then applies `deleted.lst` with `git rm -- ':(literal)$rel'`;
- refuses out-of-scope changes:
  `NON_STATUS_CHANGES="$(git status ... -- ':(exclude,glob)platform-gitops/agents-state/**/.status.yaml' ...)"`;
- short-circuits to `activity=none` if
  `STATUS_CHANGES="$(git status ... -- ':(glob)platform-gitops/agents-state/**/.status.yaml' ...)"` is empty;
- `git add -- ':(glob)platform-gitops/agents-state/**/.status.yaml'`, then
  `git diff --cached --quiet` as a defensive second empty check;
- commits `chore(agents): shepherd [<slug>|<service>|run] <DATE>` and pushes
  with a 5x retry / `git pull --rebase` loop;
- writes `yes` / `none` to `/tmp/onexit/activity`, collected as the
  `onexit-activity.tgz` artifact (this file deliberately has **no**
  `outputs.parameters` — see the long note above `templates:`, #530/#531 and
  gitops#1186).

So there are **six** places, not one, that name the allow-listed shape. The
issue's scope ("extend the commit step to stage the glob") is necessary but not
sufficient: a `git add` widened alone would stage a file that never arrived,
because the collector filtered it out one pod earlier.

Sibling precedent for the wider shape already exists:
`cwft-mctl-agents-investigate.yaml` uses
`ALLOWED = ^platform-gitops/agents-state/[^/]+/proposals/[^/]+/[^/]+` with
`PATHSPEC = ":(glob)platform-gitops/agents-state/*/proposals/*/**"` and the
matching `:(exclude,glob)` guard (lines 392, 830, 840, 845).
`cwft-mctl-agents-run.yaml` is the loose end of the family — it stages all of
`platform-gitops/agents-state/` (lines 303-304, 696, 702) and would already
commit an adoption record. `cwft-mctl-agents-implement.yaml` (895-908) and
`cwft-mctl-agents-reconcile.yaml` (293, 476-491) carry the same
`.status.yaml`-only allow-list as the shepherd.

The record shape comes from `#334`
(`platform-gitops/agents-state/mctl-agents/proposals/issue-334-feat-lifecycle-adopt-proposal-less-same/design.md`):
`ADOPTED_DIRNAME = "adopted-prs"`, `PRREF_FILENAME = ".prref.yaml"`, slug
`pr-<number>`, so the repo-relative path is
`platform-gitops/agents-state/<service>/adopted-prs/pr-<number>/.prref.yaml`.
Nothing in `.gitignore` matches it, and no CI gate would trip on it:
`scripts/validate-agents-state-approval.py` globs
`*/proposals/*/.status.yaml` only, and `scripts/validate-local-workdir.py`
asserts workdir/storage invariants over the five agent templates, not their
pathspecs.

**Measured, not assumed.** In a throwaway repository containing
`platform-gitops/agents-state/mctl-web/adopted-prs/pr-42/.prref.yaml`:

| pathspec | result |
| --- | --- |
| `:(glob)*/adopted-prs/*/**` (the issue's literal text) | matches nothing |
| `:(glob)platform-gitops/agents-state/*/adopted-prs/*/**` | matches the `.prref.yaml` |
| `:(exclude,glob)platform-gitops/agents-state/**/.status.yaml` | reports the `.prref.yaml` as out of scope |
| both excludes together | reports nothing |

Two consequences. First, the pathspec must be spelled from the repository root
(both scripts run with cwd = repo root), because git pathspecs are
cwd-relative and `*` does not cross `/`. Second, the out-of-scope guard **must**
be widened in the same commit as the collector: widen the collector alone and
`NON_STATUS_CHANGES` turns every adopting tick into a hard `exit 1` that also
drops the `.status.yaml` flips the tick had earned. Today no such failure is
possible only because the record never reaches that pod.

## Proposed solution

One commit against `cwft-mctl-agents-shepherd.yaml`, adding a second
allow-listed shape at each of the six gates and nowhere else. Define the shape
once in prose at the top of each script block and use it verbatim:

- pathspec: `:(glob)platform-gitops/agents-state/*/adopted-prs/*/**`
- regex: `^platform-gitops/agents-state/[^/]+/adopted-prs/[^/]+/[^/]+`

The regex and the pathspec describe the same set by construction — that
equality is the invariant a reviewer should check, and it is why the regex
admits any file inside a record directory rather than `.prref.yaml` alone (the
investigate template makes the same choice for `proposals/<slug>/`).

**1. `run-shepherd` collector.** `PATHSPEC` becomes a list and is splatted
into the `git status` argv; `ALLOWED` becomes an alternation:

```python
ALLOWED = re.compile(
    r"^platform-gitops/agents-state/(?:"
    r".+/\.status\.yaml"
    r"|[^/]+/adopted-prs/[^/]+/[^/]+"
    r")$"
)
PATHSPECS = [
    ":(glob)platform-gitops/agents-state/**/.status.yaml",
    ":(glob)platform-gitops/agents-state/*/adopted-prs/*/**",
]
```

`git status --porcelain=v1 -z -uall -- <p1> <p2>` takes the union, so a tick
that writes only one kind is unaffected. The rename/copy NUL-walk, the
`islink` skips, the `copy2(..., follow_symlinks=False)` secret-leak guard, the
deletions channel and the `sys.exit(rc)` passthrough are all untouched — the
change is two constants.

**2. `commit-and-push`.** Introduce one shell variable for the ERE and use it
in both handoff checks, so the two regexes cannot drift:

```sh
ALLOWED_RE='^platform-gitops/agents-state/(.+/\.status\.yaml|[^/]+/adopted-prs/[^/]+/[^/]+)$'
```

then `grep -vE "$ALLOWED_RE"` for `BAD` and `BAD_DEL` (double quotes, and the
value contains no shell metacharacters; `grep -E` is what alpine's busybox
provides and it handles the alternation — asserted by the unit test in Tasks).
The `cp -a` already copies the whole `agents-state/` subtree, so it needs no
change. Then:

- out-of-scope guard gains a second exclude term and is renamed `OUT_OF_SCOPE`
  (matching the investigate template's name, since "NON_STATUS" no longer
  describes what it means):
  `git status --porcelain -z -uall -- ':(exclude,glob)platform-gitops/agents-state/**/.status.yaml' ':(exclude,glob)platform-gitops/agents-state/*/adopted-prs/*/**'`
- the change detector gains the second glob and is renamed `IN_SCOPE_CHANGES`.
  This is the edit that satisfies "an adoption-only tick still commits": today
  a tick that wrote only a `.prref.yaml` would hit the
  "No `.status.yaml` updates" short-circuit and report `activity=none`.
- `git add -- '<p1>' '<p2>'`.

The `git diff --cached --quiet` defensive check, the commit message, the mutex,
the 5x push/rebase loop, `activity` semantics, artifact keys and resources stay
byte-identical. Because both new expressions match nothing when no record was
written, a non-adopting tick takes exactly the same code path as today — which
is the "no empty commit" acceptance criterion, and is asserted directly rather
than argued.

**3. Documentation in the file.** The `workflows.argoproj.io/description`
block's step-3 text ("Same `:(glob)` filter as the implementer template") is
now false and becomes a two-shape statement naming
`mctlhq/mctl-agents#334`, the ordering (this template first, `SHEPHERD_ADOPT_PRS`
second), and the reason the two shapes exist. The `# Only .status.yaml files
should change in agents-state/` comment above `- name: commit-and-push` gets
the same correction.

**4. A regression test in CI.** `tests/test_shepherd_commit_scope.py`, in the
style of `tests/test_tpl_git_commit_yq.py` and
`tests/test_release_deploy_bump.py`: parse the CWFT with `pyyaml`, extract the
`commit-and-push` `script.source`, run it against a throwaway git repo with a
stub remote and a stub `/artifact`, and assert the matrix in Tasks/Tests —
including a pin that the issue's naive `*/adopted-prs/*/**` matches nothing, so
nobody "simplifies" it back. Wired into `.github/workflows/validate-manifests.yml`
beside the other extracted-script tests. This repository's CI convention is
that a guard never seen to fire is not known to work; the same logic applies to
an allow-list never seen to admit.

No change to `cronworkflow-mctl-agents-shepherd.yaml`: enabling adoption is
`#334`'s rollout step and deliberately a separate commit.

## Alternatives

**A. Widen to the whole `agents-state/` subtree, as `cwft-mctl-agents-run.yaml`
already does.** One-line change at every gate, and immune to future record
shapes. Dropped: the collector runs in the pod where the Claude SDK agent had
Bash, and `commit-and-push` runs as root with a write-capable deploy key on
`main`. The narrow allow-list is the boundary three separate review findings
built (agy P1 on gitops#1042, claude P1/P2 on gitops#1046, agy P1 on
gitops#1048); trading it for brevity spends security to save four lines. That
`run` is looser is an argument for tightening `run`, not for loosening the
shepherd.

**B. A second, separate commit step for adoption state.** Keeps the existing
step literally untouched and satisfies "keep the existing paths unchanged" in
the most literal way. Dropped: it doubles the clone, the mutex acquisition and
the push/rebase loop for state that belongs in the same commit as the
`.status.yaml` flip it accompanies; two commits per tick on `main` where one
suffices; and two independently-drifting copies of the SSH/known-hosts preamble
and the retry loop — the exact duplication this file's own comments argue
against.

**C. Stage `.prref.yaml` only, with regex
`^platform-gitops/agents-state/[^/]+/adopted-prs/pr-[0-9]+/\.prref\.yaml$`.**
Tightest possible, and it does match `#334`'s current writer exactly. Dropped
as the default: the pathspec and the regex would then describe different sets
unless the pathspec were equally tight, and a later `#334` revision writing a
sibling file inside the record (evidence overflow, a lock file) would land as a
`exit 1` in *this* repository with a confusing message. Recorded as an open
question; switching is a one-line change if the record shape is frozen.

**D. Store adoption state outside git (a PVC, S3, a table in `mctl-api`).**
Dropped: it is a much larger change in the wrong repository, it loses the
review/audit/`git rm` properties that make agents-state legible, and the
shepherd pods deliberately have no shared volume since `mctl-gitops#856`.

## Platform impact

**Migrations.** None. `adopted-prs/` is a new sibling directory that does not
exist yet in `main`; nothing reads it but `run_shepherd`.

**Backward compatibility.** Additive at every gate. With `SHEPHERD_ADOPT_PRS`
unset — the state on merge — no `.prref.yaml` is ever written, both new
expressions match nothing, and the tick's observable behaviour (commit content,
commit message, `activity`, exit code, artifact keys) is identical. ArgoCD
syncs the CWFT; per `CLAUDE.md`, allow ~3 minutes before the next tick picks up
the new template, since Argo snapshots templates at submit time.

**Resource impact.** Negligible: a handful of small YAML files per adopting
tick. `emptyDir` sizing (8Gi), the `ephemeral-storage` requests/limits and the
3-day `ttlStrategy` are untouched. Commit volume on `main` rises only when
adoption is enabled, and `SHEPHERD_ADOPT_MAX_PRS_PER_TICK` defaults to 1.

**Risks and mitigations.**

- *Widened write surface into `main`.* The new shape is bounded to
  `agents-state/<service>/adopted-prs/<record>/`, still cannot reach `.git/`
  (the non-regular-file guard runs first, before anything touches the
  checkout), still cannot contain `..` or control characters, and still copies
  symlinks as symlinks. Mitigation: keep the regex and pathspec equal, and pin
  the refusal cases in the new unit test.
- *Partial edit.* Widening the collector without the `OUT_OF_SCOPE` guard turns
  every adopting tick into `exit 1` and loses that tick's `.status.yaml` flips
  too. Mitigation: the six edits are enumerated as ordered tasks with a single
  DoD, and the unit test covers the mixed case, which fails if either half is
  missing.
- *ERE portability.* The guards run in `alpine/git:2.43.0` (busybox `grep`).
  Mitigation: the alternation is plain POSIX ERE, and the unit test runs the
  extracted script rather than a paraphrase of it.
- *Ordering.* Merging this before `#334` is safe and inert; merging `#334`'s
  enablement before this reintroduces the unbounded loop. Mitigation: the
  ordering is stated in the CWFT description, on both issues, and `#334` ships
  default-off with a startup warning naming this issue.
- *Rebase contention.* Unchanged: template-level mutex plus the 5x
  `git pull --rebase` loop. A larger commit does not change the contention
  window materially.
