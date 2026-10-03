---
name: devloop-ownership-roles
description: 'Four-role ownership model for the MCTL DevLoop reliability closure loop (and similar multi-agent governance work): who owns product decisions, who owns implementation, who owns lifecycle governance, who owns automated execution, and where reviewers fit. Load this whenever two or more agents (Claude Code, ChatGPT/Codex, or another assistant) are working the same DevLoop scope concurrently, before merging, releasing, deploying, closing/reopening an issue, or deciding who acts next — so no two agents both consider themselves the owner of the same phase.'
---

# DevLoop ownership roles

Codified 2026-09-20 after a concrete incident (mctl-agents#423 / PR #425):
Claude's implementation reached Claude-review APPROVE and the governed
shepherd merged it, but nobody outside that loop independently checked
whether every designated review signal (Agy) actually agreed before the
release PR started to ship it. The fix is not "try harder" — it's a role
split so no single agent both makes and certifies the same lifecycle
decision.

## The four roles

| Role | Owns | Does not do |
|---|---|---|
| **Human (product/authority owner)** | Scope, human approvals, disputed product/architecture calls, authorizing new scope | Does not need to manually approve every clean merge/reconcile/tick once criteria are agreed |
| **Claude Code (implementation & acceptance operator)** | Code, tests, mutation-discriminating tests, fix rounds, local verification (pytest/ruff/mypy), reading pod logs, producing live-acceptance evidence | Does not grant human approvals, does not self-declare "release-ready" as a lifecycle decision, does not bypass shepherd/governed merge |
| **ChatGPT / independent lifecycle verifier & operator** | Live-state verification (current SHA, review status, CI), ownership/gate checks, reconcile/shepherd/merge/release/deploy decisions once criteria are met, reopen/close/comment, choosing the next lifecycle item | Does not parallel-fix code while Claude is already working it |
| **MCTL automation (execution machinery)** | DevLoop, reconciler, implementer, shepherd, release/deploy pipelines | Does not make human product/approval decisions |

**Reviewers (Claude review bot, Agy) are not lifecycle owners.** They are
independent quality signals only:

```
Claude/Agy review → findings/verdict → governance decision → shepherd / merge / fix
```

## The question each role answers

- **Claude Code**: *"Is the technical problem actually fixed, and is there
  proof?"* — change the code, write a test that fails on the old behavior
  and passes on the new one, run the real suite/linters, read the actual
  pod/log evidence, show a bounded refusal is bounded and not an orphaned
  timeout.
- **ChatGPT (or whichever agent holds the verifier role)**: *"Is this
  change allowed to move further through the lifecycle right now?"* — does
  the verdict actually match the current SHA, is there still a blocking
  P1/P2 from any reviewer that ran, can it merge, did the fix make it into
  the release PR, is the release actually deployed (not just merged — a
  merge to `main` is not a deploy), can the issue close, who is the current
  owner (shepherd / reconcile / a human / an agent), does an issue need to
  reopen (as happened on #423 when a post-merge finding surfaced).
- **Human**: approve a proposal, change acceptance criteria, resolve a
  disputed architectural reading, authorize new scope, decide whether
  something is a separate product requirement. Once the human has said
  "do the governance work," routine lifecycle actions that already meet
  agreed criteria (e.g. merging a clean fix-forward PR) are the verifier
  role's delegated operational authority — no need to re-ask each time.

## Automation outranks both agents

If the shepherd correctly owns a PR, neither Claude nor the verifier agent
manually substitutes for it. Intervene only on a proven lifecycle defect:
review-stuck, a dead/missing owner, an explicit human gate, or a state the
automation cannot reach on its own (e.g. `SHEPHERD_INPUT_STATUSES` not
including `review-stuck`, so a stuck proposal needs a targeted `reconcile`
before `shepherd` will ever pick it up again).

## Pipeline shape

```
Human: scope / approval / product decision
  │
  ▼
MCTL: investigation → proposal → implementer
  │
  ▼
Claude Code: implementation/fix work, tests, technical verification
  │
  ▼
Claude review + Agy: independent findings
  │
  ▼
Verifier agent: current-SHA check, ownership/gate check, reconcile/shepherd/merge/release decision
  │
  ▼
MCTL / GitHub / GitOps: merge, release, deploy
  │
  ▼
Claude Code: live acceptance evidence
  │
  ▼
Verifier agent: validate evidence, close/reopen, pick the next lifecycle item
```

## One-line summary

Claude owns changing the system. The verifier agent owns moving the change
through the lifecycle. The human owns human decisions. MCTL owns automated
execution. Reviewers only give independent signals — never a lifecycle
verdict on their own.
