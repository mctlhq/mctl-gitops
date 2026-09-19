# Design: issue-1278-chore-agents-let-the-shepherd-cwft-commi

## Current state

Everything relevant lives in one file:
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`
(1496 lines). The `shepherd-proposals` entrypoint runs
`shepherd` → `shepherd-fallback` → `commit` → `verify` → `assert-produced`.
There is no shared PVC (removed in gitops#856): each pod SSH-clones
`mctl-gitops` in its own `clone-gitops` initContainer, and cross-step state
travels as Argo artifacts addressed by literal S3 keys.

State reaches `main` through exactly two filters, and both are
`.status.yaml`-only today.

**Filter 1 — the handoff, inside `run-shepherd`.** After the orchestrator
exits, an inline Python heredoc (`COLLECT`, lines 482-589) copies changed
files out of the pod's worktree into `/tmp/state-out`, which Argo uploads as
the `changes` artifact (`{{workflow.name}}/agents-state.tgz`). It is governed
by two constants:

```python
ALLOWED  = re.compile(r"^platform-gitops/agents-state/.+/\.status\.yaml$")   # L493
PATHSPEC = ":(glob)platform-gitops/agents-state/**/.status.yaml"            # L494
```

`PATHSPEC` is the sole `--` argument to `git status --porcelain=v1 -z -uall`
(L503-505); the result is split into `copies` and `deletions` (a path git
reports that is gone on disk is a deletion, because the receiving side
overlays onto a fresh clone and is purely additive — claude P1 on #1046), and
`ALLOWED` re-checks every path before anything is written (L548-556).
Deletions are written to `deleted.lst`. An adoption record is invisible to
`PATHSPEC`, so **today a `.prref.yaml` never leaves the run-shepherd pod** —
exactly the drop the issue describes.

**Filter 2 — the commit, inside `commit-and-push`.** This step holds the
`mctl-gitops-main-writes` mutex (hoisted from spec-level to template-level so
the 300s `post-deploy-verify` sleep no longer holds the global write lock) and
runs `script.source` as root in `alpine/git:2.43.0` against its **own** fresh
clone that the agent never touched (gitops#983 P1). Under `set -e` it:

1. exits early with `activity=none` if `/artifact` is absent or empty
   (L877-883) — generic, filename-agnostic;
2. refuses any non-regular file anywhere in the handoff (L890-894);
3. refuses tree paths that do not match
   `^platform-gitops/agents-state/.+/\.status\.yaml$` (`BAD`, L895) and the
   same for `deleted.lst` (`BAD_DEL`, L901-908);
4. `cp -a /artifact/tree/platform-gitops/agents-state/.` over its clone
   (L910-913) — also generic;
5. applies `deleted.lst` with `git rm --ignore-unmatch -- ":(literal)$rel"`
   (L917-923) — generic;
6. refuses anything changed outside the allowed subtree:
   `NON_STATUS_CHANGES` via `:(exclude,glob)platform-gitops/agents-state/**/.status.yaml`
   (L927-932);
7. probes `STATUS_CHANGES` with the include pathspec and exits `activity=none`
   if empty (L934-939);
8. `git add -- ':(glob)platform-gitops/agents-state/**/.status.yaml'` (L940),
   `git diff --cached --quiet` guard, commit, then a 5-attempt
   push/rebase loop (L962-981).

Steps 1, 4 and 5 already do the right thing for any path. Steps 2, 3, 6, 7 and
8 are the ones pinned to `.status.yaml`.

Two behaviours of git were **measured** in a scratch repository rather than
assumed, because both decide the shape of the fix:

- `git status --porcelain -- <spec-that-matches-nothing>` exits 0 and prints
  nothing. `git add -- <spec-that-matches-nothing>` exits **128**
  (`fatal: pathspec … did not match any files`) and stages *nothing at all*,
  even when a sibling pathspec in the same invocation did match. Under the
  `set -e` at the top of this script, naively appending the adopted-prs
  pathspec to L940 would fail the commit step on every tick that adopts
  nothing — which is the steady state, and a direct violation of the issue's
  second acceptance box.
- The issue's literal `':(glob)*/adopted-prs/*/**'` matches nothing from the
  repository root. `:(glob)` follows fnmatch-with-`FNM_PATHNAME` semantics, so
  `*` does not cross `/`; the expression asks for
  `<one-component>/adopted-prs/<one-component>/**`. The rooted form
  `:(glob)platform-gitops/agents-state/*/adopted-prs/*/**` does match
  `platform-gitops/agents-state/mctl-web/adopted-prs/pr-42/.prref.yaml`.

The record's shape comes from `mctlhq/mctl-agents#334`, whose approved
proposal is in this repo at
`platform-gitops/agents-state/mctl-agents/proposals/issue-334-feat-lifecycle-adopt-proposal-less-same/design.md`:
`ADOPTED_DIRNAME = "adopted-prs"`, `PRREF_FILENAME = ".prref.yaml"`, one
directory per PR named `pr-<number>`, written through the same
`proposal_state.update_status_file` atomic writer as `.status.yaml`. That
design's "durability caveat" names this issue as the blocker.

Finally, `scripts/validate-agents-state-approval.py` (the CI gate that refuses
an unrunnable `accepted` proposal) globs `*/proposals/*/.status.yaml`
(L116, L348), so it never sees `adopted-prs/` and needs no change.

## Proposed solution

Widen both filters in `cwft-mctl-agents-shepherd.yaml`, from
`.status.yaml`-only to `.status.yaml` **plus** `adopted-prs/pr-<n>/.prref.yaml`,
keeping every other property of the step — mutex, rebase loop, commit message,
symlink refusal, deletion handling, `activity` artifact — byte-for-byte.

**One pair of constants, used everywhere.** Both filters get a
two-element include set, defined once per step and referenced from every site,
so the include expression and the `:(exclude,…)` expression can never drift
apart. Drift matters concretely: if the exclude at step 6 were narrower than
the include at step 8, a legitimate record would trip the "refusing to commit
changes outside" guard; if it were wider, a stray file under `adopted-prs/`
would slip past the guard that is supposed to catch it.

In `run-shepherd`'s `COLLECT`:

```python
ALLOWED = re.compile(
    r"^platform-gitops/agents-state/"
    r"(?:.+/\.status\.yaml"
    r"|[^/]+/adopted-prs/pr-[0-9]+/\.prref\.yaml)$"
)
PATHSPECS = [
    ":(glob)platform-gitops/agents-state/**/.status.yaml",
    ":(glob)platform-gitops/agents-state/*/adopted-prs/*/**",
]
```

and the `git status` call becomes `[..., "--", *PATHSPECS]`. Nothing else in
that script changes: the NUL-walk, the rename/copy handling, the symlink
skip, the `follow_symlinks=False` copy and the `bad` check all read from
`ALLOWED` and are already path-generic.

Note the deliberate asymmetry between pathspec and regex. The pathspec is
broad (`adopted-prs/*/**`, the rooted form of what the issue asked for) and
the regex is narrow (`pr-<n>/.prref.yaml`). That is the fail-closed direction:
a stray file under `adopted-prs/` is *seen* by the pathspec and then
*rejected* by the regex with a named error, instead of being silently outside
the filter's view. Matching the two exactly would turn a refusal into a
silent drop.

In `commit-and-push`, the same two expressions are bound to shell variables at
the top of the script and used at every site:

```sh
SPEC_STATUS=':(glob)platform-gitops/agents-state/**/.status.yaml'
SPEC_ADOPTED=':(glob)platform-gitops/agents-state/*/adopted-prs/*/**'
ALLOWED_RE='^platform-gitops/agents-state/(.+/\.status\.yaml|[^/]+/adopted-prs/pr-[0-9]+/\.prref\.yaml)$'
```

- `BAD` and `BAD_DEL` switch from the inline `grep -vE '…\.status\.yaml$'` to
  `grep -vE "$ALLOWED_RE"`.
- `NON_STATUS_CHANGES` takes both excludes:
  `git status … -- ":(exclude,glob)…/**/.status.yaml" ":(exclude,glob)…/*/adopted-prs/*/**"`.
  Measured: with only the existing exclude, a `.prref.yaml` in the checkout
  trips this guard and the step exits 1 — so this line is not optional
  cosmetics, it is what stops the widened handoff from hard-failing the commit.
- `STATUS_CHANGES` is renamed `AGENT_STATE_CHANGES` and probes both pathspecs.
  The empty case keeps its current behaviour exactly: log, `activity=none`,
  `exit 0`, no commit.
- Staging becomes pathspec-by-pathspec, guarded, because of the `git add`
  exit-128 behaviour above:

  ```sh
  set --
  if [ -n "$(git status --porcelain -z -uall -- "$SPEC_STATUS")" ]; then
    set -- "$@" "$SPEC_STATUS"
  fi
  if [ -n "$(git status --porcelain -z -uall -- "$SPEC_ADOPTED")" ]; then
    set -- "$@" "$SPEC_ADOPTED"
  fi
  git add -- "$@"
  ```

  `if` blocks, **not** `[ … ] && set -- …`: `set -e` is active, and a
  top-level and-or list whose left side fails takes the whole script down.
  This file has been bitten by precisely that class of bug before — see the
  `set +e` note at L462-467 explaining why `RC=$?` after a bare `"$@"` never
  ran. Building argv with `set --` is also the pattern `run-shepherd` already
  uses (L434-443) for the same reason.

  The `git diff --cached --quiet` guard at L942 stays, unchanged, as the last
  defence against an empty commit.

**Comments.** Three prose blocks currently assert the narrower contract and
must be corrected in the same commit, or the file starts lying about itself:
the header annotation's "Same `:(glob)` filter as the implementer template"
(L42-43 — it is no longer the same, and that is intentional), the
"Only `.status.yaml` files should change in agents-state/" banner above
`commit-and-push` (L731-734), and the `outputs.artifacts.changes` description
"The `.status.yaml` flips THIS attempt made" (L285-289). Each should name
`mctl-agents#334` and this issue so the next reader finds the writer.

**Ordering.** Filter 1 before filter 2 is not merely tidy — widening only
filter 1 makes every adopting tick *fail* at `NON_STATUS_CHANGES` instead of
silently dropping the record, which is strictly worse than today. Both land in
one commit.

## Alternatives

**Stage the whole `agents-state/` subtree** (`git add -- ':(glob)platform-gitops/agents-state/**'`,
drop the regexes). One line, no `git add` exit-128 problem, no drift risk
between include and exclude. Dropped: those regexes are a security boundary,
not tidiness. This pod runs as root with a write-capable deploy key and pushes
to `main`; the narrow allowlist is what stops an agent-authored path from
reaching it, and the layered checks exist because review found real escapes
twice (`agy` P1 on #1042 — a file smuggled into `.git/hooks/` is invisible to
`git status`; `agy` P1 on #1048 — a symlink dereferenced by `copy2` landing
token contents as an ordinary file). Widening the allowlist from "two known
filenames" to "anything under agents-state" to save four lines trades that
away for nothing.

**Add a third, separate commit step for adoption records.** A dedicated
template staging only `adopted-prs/**`, sequenced after `commit-and-push`.
Dropped: it doubles the number of holders of the `mctl-gitops-main-writes`
mutex per tick and the number of push/rebase races, splits one tick's state
across two commits on `main` (so a crash between them leaves a `.status.yaml`
flip whose adoption record never landed, or the reverse), and needs its own
clone initContainer, its own artifact key and its own retry loop — roughly 120
lines duplicated to avoid widening two regexes.

**Have `mctl-agents` write adoption state into the existing
`proposals/<slug>/.status.yaml` shape** so no gitops change is needed at all.
Dropped: it is not this repository's call, #334 has already shipped the
`adopted-prs/` shape and its rationale (a `PRRef` is deliberately not a
proposal — there is no `requirements.md`/`design.md`/`tasks.md` behind it, and
`_discover_refs`' proposal glob is explicitly left untouched), and synthesising
a fake proposal directory for every adopted PR would pollute the tree that
`validate-agents-state-approval.py` and the mentor digest both walk.

## Platform impact

**Migrations.** None. `adopted-prs/` is a new sibling directory that does not
exist in `main` yet; nothing in this repo reads it.

**Backward compatibility.** Full, in both directions. With
`SHEPHERD_ADOPT_PRS` off — its state on the day this merges — no `.prref.yaml`
is ever written, both new pathspecs match nothing, the guarded `git add` falls
back to exactly the single pathspec it passes today, and the tick produces a
byte-identical commit or no commit at all. A shepherd image *older* than
`#334` is equally unaffected. This change is inert until the flag flips, which
is the whole point of merging it first.

**Resource impact.** Two extra `git status` invocations per commit step
against a `--depth=1` clone: microseconds, and none of it inside the mutex
window in any meaningful sense. Commit size grows by one small YAML file per
adopted PR per tick, bounded by `SHEPHERD_ADOPT_MAX_PRS_PER_TICK` (default 1).

**Risks and mitigations.**

- *A no-adoption tick fails at `git add`.* The measured exit-128 behaviour;
  the single most likely way to get this wrong. Mitigated by the guarded argv
  construction and by test T2, which exercises precisely that path.
- *A widened handoff hard-fails at `NON_STATUS_CHANGES`.* Happens if the
  exclude pathspec is not widened in lockstep with the include. Mitigated by
  binding both expressions to one variable pair, and by T3.
- *The allowlist is widened further than intended.* `adopted-prs/*/**` in the
  pathspec is intentionally broader than the regex so that stray content is
  refused loudly; a reviewer should check the regex is the narrow one and the
  pathspec the broad one, not the reverse.
- *Argo template snapshotting.* Per `CLAUDE.md`, Argo snapshots
  ClusterWorkflowTemplates at submit time — wait ~3 minutes after merge for
  ArgoCD to sync before triggering a verification tick, or the run will use
  the old template and the change will look like it did nothing.
- *Cross-repo ordering.* If `SHEPHERD_ADOPT_PRS` is enabled in `mctl-agents`
  before this merges, records are written and dropped every tick and the
  `MAX_REVIEW_ATTEMPTS` bound does not hold across ticks. #334 already ships
  default-off, caps adoption at one PR per tick, and prints a startup warning
  naming this issue; the mitigation here is to state the ordering in both
  issues, as the acceptance list requires.
