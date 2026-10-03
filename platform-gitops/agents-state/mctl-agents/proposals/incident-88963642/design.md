# Design: incident-88963642

## Diagnosis
The investigate workflow for https://github.com/mctlhq/seerrsense/issues/39 failed on both
the primary attempt and the account-2 fallback. The `assert-attempt` step's message blames
the generic "Claude five_hour usage limit / HTTP 429" pattern, but that is only its default
hypothesis when both attempts fail — it did not have the underlying investigator logs. Both
`run-investigator` step logs show the real, deterministic cause: `orchestrator.run_issue_investigator`
rejects the target repo before doing any Claude work, printing:

"Repo 'seerrsense' is not a known service. Add it to config/settings.py SERVICES
(NON_ROTATING_SERVICES if it has no agents/<svc>/ scaffold) before investigating its issues.
Known: mctl-web, mctl-openclaw, mctl-docs, mctl-api, mctl-portal, mctl-agent, mctl-gitops,
mctl-agents, mctl-telegram, mctl-design, mctl-pairdesk, mctl-academy"

`seerrsense` is absent from both the `SERVICES` and `NON_ROTATING_SERVICES` lists in
mctl-agents' `config/settings.py`, so every attempt to investigate an issue in that repo
fails identically and immediately (exit 1) — this is a config gap, not a transient quota
problem, which is why the primary attempt and the fallback account both failed the same way
and why blind retries will not help. Because the investigator step never runs, no proposal
files are produced and `commit-and-push` has nothing to hand off.

## Proposed Fix
In mctl-agents `config/settings.py`, add `"seerrsense"` to the known-services configuration
so `python -m orchestrator.run_issue_investigator --issue-url <seerrsense issue url>` no
longer rejects the repo up front:
- If the mctl-agents repo has no `agents/seerrsense/` scaffold directory, add `"seerrsense"`
  to `NON_ROTATING_SERVICES`.
- If an `agents/seerrsense/` scaffold directory already exists, add `"seerrsense"` to
  `SERVICES` instead.

This responder has no shell access to the mctl-agents repo tree and could not check which
of the two is true — the implementer should check for `agents/seerrsense/` before choosing
the list.

## Scope
Minimal. Add exactly one entry (`"seerrsense"`) to the correct list in
`config/settings.py`. No other files should change.

## Confidence: LOW
Root cause (missing service-registry entry) is confirmed directly from two independent
run-investigator failures with identical error text. Confidence is LOW only on which of
SERVICES vs NON_ROTATING_SERVICES is the correct destination list — verify by checking for
an existing `agents/seerrsense/` scaffold before applying.
