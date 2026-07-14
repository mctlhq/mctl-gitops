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
     (reverse-import grep; see dead-code carve-out below). Editing an
     unimported file has zero runtime effect and just adds noise to the diff.
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
5. Re-runs the verification grep to confirm no stale model strings remain
   outside documented dead-code carve-outs.

## Known dead-code carve-out

- `mctl-agent/internal/diagnosis/analyzer.go` — unimported, not wired into
  `cmd/agent/main.go` or `internal/skill/builtin/register.go`. Confirm before
  every run with:
  ```
  grep -rln "internal/diagnosis" mctl-agent --include="*.go"
  ```
  If that ever comes back non-empty (someone wires the package in), it must
  be edited too on the next migration — don't blindly skip it forever.

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
Expected sole remaining hits: documented dead-code carve-outs (see above).
Everything else must show the new model ID. Each PR's own `@claude review`
run exercises the newly-edited `claude_args` path live — a successful bot
review is de facto proof the workflow YAML is valid and the model ID is
accepted.
