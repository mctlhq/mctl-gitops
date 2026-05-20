# Operator playbook: agents-state proposals

This document is for the **human operator** who reviews proposals in
`platform-gitops/agents-state/<service>/proposals/` and decides when an
implementer run is allowed to start. It is *not* read by any automation —
it is process guidance for the person turning the dial.

## What the implementer actually reads

`cwft-mctl-agents-implement.yaml` runs
`python -m orchestrator.run_implementer` from
`ghcr.io/mctlhq/mctl-agents`. Per inline comments in the workflow
templates (`cwft-mctl-agents-implement.yaml`,
`cwft-mctl-agents-issue-poll.yaml`, `cwft-mctl-agents-investigate.yaml`),
the implementer reads exactly four files from each proposal directory:

- `requirements.md`
- `design.md`
- `tasks.md`
- `.status.yaml`

Anything outside those four files — README.md in the proposals/
directory, GitHub issue body, GitHub comments, prose pasted into a chat
— is **invisible to the implementer**. Scope changes that need to land
must be written into one of those four files.

## Status lifecycle

The values observed in `.status.yaml` across this repo, and which tier
writes each one:

| Status | Written by | Meaning |
| --- | --- | --- |
| `proposed` | investigator | Draft is written. Not yet operator-approved. |
| `accepted` | operator | Tier 2 (implementer) will pick it up on the next run. |
| `in-progress` | implementer | Implementer is running, or crashed mid-run. A PR may or may not exist yet — check the `pr:` field. The shepherd's dead-letter recovery covers this state too. |
| `implemented` | implementer | Implementer pushed a branch and opened a PR. Tier 3 (shepherd) takes over. |
| `error` | implementer | Implementer crashed before opening a PR. Needs operator force-retry. |
| `review-fixing` | shepherd | Shepherd pushed a follow-up commit to address codex/Claude review feedback. Flips back to `implemented` after the followup lands. |
| `review-stuck` | shepherd | Shepherd retried address-review repeatedly and gave up. Needs human intervention on the PR. |
| `merged` | shepherd | PR was merged (either by shepherd's `gh pr merge` or out of band by a human). Terminal. |
| `rejected` | operator or shepherd | Operator declined the proposal, or shepherd observed the PR was closed unmerged. Terminal. |

Source of truth: `cwft-mctl-agents-implement.yaml:82-88` (`proposed →
in-progress → implemented` on success, `→ error` on crash) and
`cwft-mctl-agents-shepherd.yaml:11`, `:39-41`, `:154-155`
(`{implemented, review-fixing}` discovery scope, `→ review-fixing`,
`→ implemented`, `→ merged`, `→ rejected`, `→ review-stuck`).

Trigger for Tier 2 (implementer) is `status: accepted`. Trigger for
Tier 3 (shepherd) is `status` in `{implemented, review-fixing}` *with*
a `pr:` URL. Do not use `approved` — no workflow matches it, and the
proposal will sit idle.

## Definition of Ready before flipping to `accepted`

Run through this list per proposal directory. If any line fails, the
proposal stays at `proposed` and gets edited in place.

- `requirements.md` is in EARS form (`WHEN`/`IF`/`WHILE … THE SYSTEM
  SHALL …`) and references concrete symbols / files / metrics from the
  target repo. No vague "improve X" or "make it production-grade"
  without a measurable criterion.
- `design.md` names the files that will change and the approach. No
  open architectural questions left unanswered.
- `tasks.md` is a checklist a contributor could pick up cold.
- Out-of-scope is explicit. Anything the investigator deferred is
  listed, not assumed.
- Each acceptance criterion is checkable — a command output, a metric
  value, a file existing, a manifest validating.
- Open questions in `requirements.md` are either resolved or
  explicitly marked "implementer picks reasonable default" with the
  default stated.

## Go / No-Go checklist

Use this when batching review of investigator-generated proposals.
Failing any line → leave at `proposed` and edit in place; do not push
through.

- [ ] All four files present: `requirements.md`, `design.md`,
      `tasks.md`, `.status.yaml`.
- [ ] No prose-only language without measurable success criteria.
- [ ] At least one validatable artifact per proposal (a command to
      run, a metric query, a file path that must exist).
- [ ] Scope refinements are inside the four files — not in GitHub
      issue comments or PR descriptions, which the implementer will
      not see.
- [ ] EARS criteria refer to symbols / metrics / paths that actually
      exist in the target repo at HEAD.
- [ ] `.status.yaml` `source.url` points at the right upstream issue,
      and the issue is not already resolved.

## How to hand a task off to another env

When the investigator wrote the proposal in one env but you need
implementer to run against a different env (or you simply need to edit
proposals from a fresh checkout):

1. Clone or refresh `mctl-gitops`.
2. Create a working branch.
3. Edit files inside
   `platform-gitops/agents-state/<service>/proposals/<slug>/`.
4. Push to a branch; open a PR to `main`.
5. The implementer scheduled run reads `main` — proposal edits do not
   take effect until the PR merges.

```bash
git clone git@github.com:mctlhq/mctl-gitops.git
cd mctl-gitops
git checkout -b chore/proposals-tighten-86-94

# edit platform-gitops/agents-state/<svc>/proposals/<slug>/{requirements,design,tasks}.md
# and/or .status.yaml to flip status: proposed -> status: accepted

git add platform-gitops/agents-state
git commit -m "chore(proposals): tighten requirements for <svc> issue-<n>"
git push -u origin chore/proposals-tighten-86-94
```

The proposal does not "move" between environments — the gitops repo is
the single source of truth. "Env handoff" in practice means a fresh
checkout, edits, PR.

## Moderation triage

Upstream issues sometimes attract irrelevant or adversarial comments
(e.g. unrelated tooling chatter, prompt-injection-shaped text).
Investigator output already filters most of this, but flag and route
to repo maintainers for action — do not bake adversarial content into
`requirements.md` "for completeness".

## When a proposal is not good enough

- **Fixable**: edit the four files in place, keep `status: proposed`,
  document the edit in the commit message.
- **Out of scope or duplicate**: set `status: rejected` with a short
  reason in the commit. Do not delete the directory.
- **Wrong target service**: move the directory under the correct
  `agents-state/<service>/proposals/` and re-point `source` in
  `.status.yaml`.

## Recovering stuck or errored proposals

- **`error`**: implementer crashed before opening a PR. Inspect the
  workflow logs, fix whatever caused the crash (env, secrets, code
  bug), then flip back to `accepted` so the next implementer run picks
  it up. If you need to bypass the in-progress guard, the implementer
  template accepts `force=true`.
- **`in-progress` with no `pr:`**: implementer started but never
  reached PR creation. Same recovery as `error` — usually a crashed
  pod. Flip to `accepted` (with `force=true` if needed).
- **`in-progress` *with* a `pr:`**: implementer crashed *after* push
  but before flipping to `implemented`. The shepherd's dead-letter
  recovery (`cwft-mctl-agents-shepherd.yaml:219-223`) will pick it up
  on the next shepherd run — do not manually re-trigger the
  implementer, that opens a duplicate PR.
- **`review-stuck`**: shepherd gave up on address-review. Look at the
  PR comments, push a fix manually (or close the PR and flip to
  `rejected`).
- **`implemented` not progressing**: shepherd CronWorkflow may be
  suspended (it ships suspended by default per the workflow template
  annotation). Un-suspend or trigger a one-shot run.
