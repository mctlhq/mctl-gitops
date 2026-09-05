---
name: switch-agent-model
description: Migrate the Claude model ID used by all mctl-agent/mctl-agents runtime agents and their CI PR-review bots to a new model, in one coordinated pass across both repos.
user-invocable: true
---

# switch-agent-model — migrate all mctl-agent/mctl-agents model references

Triggered by: `/switch-agent-model <new-model-id>`
Example: `/switch-agent-model claude-sonnet-6`

## What this skill does

1. Greps both repos for current model-ID literals:
   ```
   grep -rn "claude-[a-z]*-[0-9.-]*" mctl-agent mctl-agents \
     --include="*.go" --include="*.py" --include="*.yml" --include="*.yaml" --include="*.example"
   ```
2. Classifies each hit:
   - **Live runtime code** — verify it's actually wired in before editing
     (reverse-import grep). Editing an unimported file has zero runtime
     effect and just adds noise to the diff.

     **The reverse-import grep does not judge two kinds of file**, because
     nothing imports them by design: **entrypoints** (Go `main` packages,
     executable `run_*.py`, anything a CWFT or Dockerfile invokes directly)
     and **tests** (`*_test.go`, `tests/test_*.py`). A zero-importer result
     there means nothing — always update them. Reach for the heuristic only
     for a library-shaped file that claims to be imported and isn't.

     A file you do skip on dead-code grounds must be appended to the
     carve-out list below in the same PR (see step 5), not skipped silently.
   - **CI review-bot tiering** (`claude-review.yml`'s "Classify PR
     complexity and pick model" step) — collapse to the new model and delete
     the classify step, unless told to preserve tiering.
   - **`.env.example` defaults** — update to match the code defaults, and
     fix any drift you notice between the example file and the actual
     source default (they drift silently over time).
   - **Local `.env`** — never edit; report stale lines to the user instead,
     since it's gitignored and not part of the reviewable change.
3. One branch/PR per repo, following the `git-flow` skill (fresh branch off
   `main` → commit → push → PR → `@claude review` → wait for 0 unaddressed
   P1/P2 → merge with a merge commit, never squash). Before branching, check
   whether the working tree is already on a stale leftover branch from a
   prior task (`git status` shows "upstream is gone") — if so, `git fetch`,
   `git checkout main && git pull`, *then* branch, so the new branch is based
   on current `main` and doesn't accidentally resurrect an already-merged
   branch name.
4. Posts `@claude review` and watches both PRs with `review-watch` instead
   of polling manually.
5. Re-runs the verification grep. Every remaining hit must be justified,
   and the only admissible justification is the step-2 one: the file is
   unimported dead code, and it is neither an entrypoint nor a test. Record
   such a file in the **carve-out list in this document** — a note in the PR
   body does not carry: a future run reads `SKILL.md` and the codebase, it
   does not dig through closed PRs. If the list is empty, no hit may
   survive.

## Dead-code carve-out list

Files that carry a model ID, are genuinely unimported, and are neither an
entrypoint nor a test. A migration may leave these on the old model; anything
not listed here must be updated.

**The list is currently empty.** `mctl-agent/internal/diagnosis/analyzer.go`
used to be its sole entry and was deleted outright in mctl-agent#123, so today
every model-ID hit in either repo is live and must change.

When you add an entry, record the reverse-import grep that proved it dead, so
the next run can re-verify the claim instead of trusting it:

```
grep -rln "<import path>" <repo> --include="*.go"
```

If that ever comes back non-empty, the file is no longer dead — drop it from
this list and edit it like any other live file.

## Tiering removal — CI review bot

Both repos' `.github/workflows/claude-review.yml` had a "Classify PR
complexity and pick model" step selecting opus/sonnet/haiku by a diff-size /
touched-path score. Default behavior: delete that step entirely and hardcode
the new model directly in both `claude_args: '--model <new-model-id> ...'`
occurrences (primary review + fallback-token review). Only keep the classify
step if a future migration explicitly wants per-PR tiering again — in that
case just swap the model IDs inside the `case` statement instead of deleting
it.

## Tiering removal — runtime agent (mentor / fast-path)

Some agents intentionally pin a stronger or cheaper model for a subset of
work (e.g. `mctl-agents`' mentor deliberately ran on Opus for its
low-frequency weekly digest; `mctl-agent`'s LLM-diagnosis skill routed
crashloop/resource-limit tickets to Haiku for speed/cost). Default: migrate
everything to the single new model uniformly, deleting the routing logic and
its explanatory comments (they go stale once the tiering they describe is
gone). Only preserve a carve-out if explicitly asked to keep a cheaper/
stronger tier for a specific agent or ticket type.

## Repos and files covered (as of 2026-07-15, Sonnet 5 migration)

- `mctl-agent`: `internal/skill/builtin/llm_diagnosis.go`,
  `.github/workflows/claude-review.yml`
  (worked example: https://github.com/mctlhq/mctl-agent/pull/36)
- `mctl-agents`: `config/settings.py`, `.env.example`,
  `.github/workflows/claude-review.yml`
  (worked example: https://github.com/mctlhq/mctl-agents/pull/54)

`orchestrator/run_issue_investigator.py`, `orchestrator/run_incident_responder.py`,
and `orchestrator/run_implementer.py` in `mctl-agents` never need direct
edits — they resolve their model via `os.getenv("<X>_MODEL",
SERVICE_AGENT_MODEL)` fallback chains and inherit automatically once
`SERVICE_AGENT_MODEL` changes.

Add new files/repos here as the mctl-agent/mctl-agents family grows.

## Local .env caveat

Never edit a user's local, gitignored `.env`. Just report the stale lines
found (`grep -n "_MODEL=" .env`) and tell them what to change by hand.

## Verification

```bash
grep -rn "<old-model-id-patterns>" mctl-agent mctl-agents \
  --include="*.go" --include="*.py" --include="*.yml" --include="*.yaml" --include="*.example"
```
Every match must show the new model ID, with one admissible exception: a file
listed in the carve-out section above. A hit that is dead code but *not* yet
listed is not a pass — add it to the list in this same PR, with the
reverse-import grep that proves it dead. An unexplained remaining hit fails. Each PR's own `@claude review`
run exercises the newly-edited `claude_args` path live — a successful bot
review is de facto proof the workflow YAML is valid and the model ID is
accepted.
