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
   `main` → commit → push → PR → wait for the auto-triggered review → 0
   unaddressed P1/P2 → merge with a merge commit, never squash). Before branching, check
   whether the working tree is already on a stale leftover branch from a
   prior task (`git status` shows "upstream is gone") — if so, `git fetch`,
   `git checkout main && git pull`, *then* branch, so the new branch is based
   on current `main` and doesn't accidentally resurrect an already-merged
   branch name.
4. Watches the PRs with `review-watch` instead of polling manually. Do NOT
   comment `@claude review`: `claude-review.yml`'s `pull_request` trigger
   already reviews on open and on every push, and a manual comment starts a
   second paid session on the same commit.
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

## Engine first — the Claude Code CLI moves with the model

A new model is gated by a minimum Claude Code CLI version. An older CLI fails
every call with `API Error: 400 Claude Code <ver> does not support this model;
version <min> or newer is required` (the 5.5 models need 2.1.280+). A model
migration is therefore always model ID **plus** engine:

- `mctl-agents`: `claude-agent-sdk==X` in `pyproject.toml` + `uv lock
  --upgrade-package claude-agent-sdk`. The wheel bundles the CLI; check
  `claude_agent_sdk/_cli_version.py` in the installed package. Read the SDK
  CHANGELOG between the two versions for breaking changes.
- `claude-code-action` pins — `mctlhq/.github` `claude-review.yml` (both
  steps) and `mctl-agents` `diagrams-refresh.yml`: `@<sha> # vX (CLI Y)`.
  The action's `action.yml` declares `CLAUDE_CODE_VERSION`; resolve the sha
  with `gh api repos/anthropics/claude-code-action/commits/<tag> --jq .sha`.
- `mctl-coolify-mcp` uses `@v1` (floating) and follows automatically.
- `mctl-agent` calls the API directly (anthropic-sdk-go) — no CLI gate.

Take the latest SDK and action releases. Rollout order: engine live first
(mctl-agents release, then its image-tag bump in mctl-gitops), then any gitops
env pin that selects the new model. The shared reviewer bumps engine and
defaults in the same PR, which is safe because its own run on that PR
exercises both.

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

## Repos and files covered (as of 2026-09-30, Sonnet 5 → Sonnet 5.5)

Sweep the whole org, not just the two agent repos:
`gh search code "<old-model-id>" --owner mctlhq`. As of this migration the
live selections were:

- `mctl-agent`: `internal/skill/builtin/llm_diagnosis.go` (the model),
  `internal/metrics/metrics.go` (pre-populated `LLMRequests` label — must
  match the model), `internal/skill/builtin/llm_diagnosis_telemetry_test.go`.
- `mctl-agents`: `config/model-policy.yaml` (profile `balanced` carries every
  service agent, the implementer and the incident responder),
  `.env.example`, `.github/workflows/diagrams-refresh.yml`, and the tests
  that assert the policy value (`tests/test_resolver.py`).
- `mctlhq/.github`: `.github/workflows/claude-review.yml` — the reusable PR
  reviewer's `model-high` / `model-mid` / `model-low` input defaults. The
  tiering is deliberate there (security-sensitive diffs get the stronger
  model); swap the IDs, keep the tiers. Callers pin the workflow by SHA and
  Dependabot bumps the pins weekly, so callers pick the change up without an
  edit — except a caller that overrides an input (e.g. `projects-mcp`).
- `projects-mcp`: `.github/workflows/claude-review.yml` overrides the reusable
  reviewer's `model-high` (to keep Sonnet on its sensitive paths) — it does
  not inherit the default change, so edit it directly.
- `mctl-coolify-mcp`: `.github/workflows/claude.yml` and
  `.github/workflows/claude-code-review.yml` pin `--model` themselves (no
  reusable reviewer). `evals.yml` defaults to Haiku and is separate.
- `mctl-gitops` `execution-profiles/*/profile.yaml`: a profile whose comments
  name the migrated model must follow, and any content change — comments
  included — needs a patch `spec.version` bump plus a re-pinned binding in
  `agent-platform/releases/shadow/<agent>.yaml` (new `bindingRevision`, the
  old one pushed onto `history`), or `validate-profile-version-bumps.py`
  fails. Worked example: issue-investigator-default 1.4.0 -> 1.5.0 with
  binding revision 11 -> 12 (mctl-gitops 14d4bd59).
- **Not in scope: `mctl-academy`.** Its content pipeline
  (`content-replenish.yml`, `AUTHOR_MODEL` / `REVIEWER_MODEL`) chooses its own
  models per provider (Anthropic or Nebius) and is not a platform agent; leave
  it alone unless its owner asks.
- `mctl-gitops`: `platform-gitops/bootstrap/files/usage-pricing/claude-firstparty.json`
  — **add** a price entry for the new model (append-only, never edit the old
  one) and bump `ROLLOUT_MARKER` in
  `bootstrap/templates/mctl-platform/mctl-api.yaml`, or every usage record on
  the new model is stored unpriced. Merge this one before the agents move.
  `ISSUE_INVESTIGATOR_MODEL` in `cwft-mctl-agents-investigate.yaml` is NOT
  part of that PR: it takes effect on the next workflow run, with whatever
  mctl-agents image is deployed, so it moves only after the engine bump below
  is live (see "Engine first").
  CWFT comments that name the resolved model
  (`cwft-mctl-agents-investigate.yaml`, `cwft-mctl-agents-run.yaml`,
  `execution-profiles/issue-investigator-default/profile.yaml`) follow — the profile only with the version bump described above.

`orchestrator/run_issue_investigator.py`, `orchestrator/run_incident_responder.py`,
and `orchestrator/run_implementer.py` in `mctl-agents` never need direct
edits — they resolve their model via `os.getenv("<X>_MODEL",
SERVICE_AGENT_MODEL)` fallback chains and inherit automatically once the
`balanced` profile changes. The investigator is pinned separately by
`ISSUE_INVESTIGATOR_MODEL` in `cwft-mctl-agents-investigate.yaml` (Opus);
migrate it together with the other Opus selections — the reusable reviewer's
`model-high` and `mctl-coolify-mcp`'s own
`claude.yml` / `claude-code-review.yml`, which do not use the reusable
reviewer.

**Recorded data is not a model selection** and keeps the old ID: the old
model's price-catalog entry (rows priced before the move resolve to it),
recorded execution-evidence fixtures pinned by `content_hash`
(`mctl-agents/tests/fixtures/evidence/*`, `mctl-api/internal/evidence/testdata/*`,
ADR-018), OTel trace fixtures, `agents-state` proposals and product-update
`assisted_by` lines. This is the only other admissible remaining hit besides
the dead-code carve-out list.

Add new files/repos here as the mctl-agent/mctl-agents family grows.

## Local .env caveat

Never edit a user's local, gitignored `.env`. Just report the stale lines
found (`grep -n "_MODEL=" .env`) and tell them what to change by hand.

## Verification

Re-run the org-wide sweep on each repo's default branch after the PRs merge —
not only the two agent repos, since live selections also sit in
`mctlhq/.github`, `mctl-coolify-mcp`, `projects-mcp` and `mctl-gitops`
(`mctl-academy` hits are expected and out of scope, see above):

```bash
gh search code "<old-model-id>" --owner mctlhq --json repository,path \
  --jq '.[] | "\(.repository.name) \(.path)"' | sort -u
```
`gh search code` matches tokens, so `claude-sonnet-5` also hits files that
only contain `claude-sonnet-5-5`; confirm each hit with a local
`git grep -nE "<old-id>([^-.0-9]|$)" origin/main` in that repo.
Every match must show the new model ID, with two admissible exceptions: a file
listed in the carve-out section above, and recorded data as defined under
"Repos and files covered". A hit that is dead code but *not* yet
listed is not a pass — add it to the list in this same PR, with the
reverse-import grep that proves it dead. An unexplained remaining hit fails. Each PR's own auto-triggered review
run exercises the newly-edited `claude_args` path live — a successful bot
review is de facto proof the workflow YAML is valid and the model ID is
accepted.
