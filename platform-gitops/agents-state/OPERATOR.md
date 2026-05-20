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

The values observed in `.status.yaml` across this repo:

| Status | Meaning |
| --- | --- |
| `proposed` | Investigator wrote the draft. Not yet operator-approved. |
| `accepted` | Operator-approved. Implementer will pick it up on the next run. |
| `in-progress` | Implementer started; PR not yet opened. |
| `merged` | PR landed. |
| `rejected` | Operator decided not to implement. |

Trigger for the implementer is `status: accepted`. Do not use
`approved` — the workflow does not match it and the proposal will sit
idle.

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

## Go / No-Go checklist (issues #86–#94 reference set)

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
