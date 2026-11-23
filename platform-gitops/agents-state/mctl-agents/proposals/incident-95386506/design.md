# Design: incident-95386506

## Diagnosis
The investigator was started for issue mctlhq/mctl-glovo#42. The orchestrator
(`python -m orchestrator.run_issue_investigator`) rejected it because `mctl-glovo`
is not in the `SERVICES` list in `config/settings.py`, and exited 1. The fallback
attempt failed too (no second OAuth token set), so the workflow reported Failed.
The primary cause is the unregistered repo, not quota. This is observed directly
in the workflow logs, not taken from incident text.

## Proposed Fix
In mctl-agents `config/settings.py`, add `mctl-glovo` to `NON_ROTATING_SERVICES`
(and thereby `SERVICES`), since no `agents/mctl-glovo/` scaffold exists. Also add
it to any enum lists that mirror SERVICES if the repo keeps them in sync
(for example the service enums in operation schemas), following how a recent
non-rotating service was added.

## Alternative
If mctl-glovo is not meant to be handled by the platform, close the fix as
not needed and have the issue removed from the poller instead. Verify the repo
is an intended platform service before applying.

## Confidence: LOW
The error message names the fix, but whether the platform should onboard
mctl-glovo is a product decision the logs cannot confirm.

## Scope
Minimal. Only the service registration for mctl-glovo.
