# Design: incident-88775245

## Diagnosis
The Argo workflow `mctl-agents-investigate-7afd8173` ran the issue
investigator against `https://github.com/mctlhq/seerrsense/issues/6` and
failed on both the primary attempt and the account-2 fallback attempt, each
exiting 1 with the identical, deterministic message:

  "Repo 'seerrsense' is not a known service. Add it to config/settings.py
  SERVICES (NON_ROTATING_SERVICES if it has no agents/<svc>/ scaffold)
  before investigating its issues. Known: mctl-web, mctl-openclaw, mctl-docs,
  mctl-api, mctl-portal, mctl-agent, mctl-gitops, mctl-agents, mctl-telegram,
  mctl-design, mctl-pairdesk, mctl-academy"

This is not a quota/rate-limit problem, even though the downstream
`assert-attempt` step's generic wording ("Most often the Claude five_hour
usage limit / HTTP 429 on both accounts") suggests that. Both attempts fail
identically before any model call completes usefully, on a hardcoded
allowlist check in `orchestrator.run_issue_investigator` /
`config/settings.py` — `seerrsense` is simply not in the `SERVICES` list
mctl-agents recognizes. `commit-and-push` correctly reports "no proposal
files handed off" as a consequence, and `notify-telegram` posted the
resulting incident. The skill gap here is structural: mctl-agents' issue
investigator can only be pointed at repos already registered in its own
settings, and `seerrsense` — a target repo, not one of mctl-agents' own
managed platform services — was never added.

## Proposed Fix
In the mctl-agents repo, `config/settings.py`:
- Add `"seerrsense"` to `SERVICES`.
- Add it to `NON_ROTATING_SERVICES` as well, since seerrsense is an external
  target repo being investigated on behalf of a GitHub issue (via
  mctl_trigger_issue), not one of mctl-agents' own managed services with an
  `agents/<svc>/` scaffold — the same category the error message describes
  for repos with no scaffold.
- Verify (implementer should check `config/settings.py` directly, since this
  responder has no shell/repo access beyond mctl-gitops) that
  `NON_ROTATING_SERVICES` is exactly the list of "known but unscaffolded"
  targets and that adding seerrsense there does not implicitly require other
  wiring (e.g. a dockerfile_repo mapping) elsewhere in `config/settings.py`.

## Scope
Minimal: one entry added to `SERVICES` and one to `NON_ROTATING_SERVICES` in
`config/settings.py`. No orchestrator logic changes needed — the check
already exists and works as designed; it was just missing this repo.

## Confidence: MEDIUM
The failure message names the exact fix required, and both independent
attempts (primary + fallback account) hit the identical deterministic check,
ruling out flakiness or quota exhaustion. Confidence is not HIGH only because
this responder cannot read `config/settings.py` directly to confirm the
current contents of `SERVICES`/`NON_ROTATING_SERVICES` or spot any secondary
wiring seerrsense might also need.
