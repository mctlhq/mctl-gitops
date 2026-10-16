# Design: incident-91756910

## Confidence: LOW

## Diagnosis
The implement workflow failed on both the primary and the account-2 fallback attempt. The implementer logs show the Claude SDK returned HTTP 403 with error `oauth_org_not_allowed` ("Your organization has disabled Claude subscription access for Claude Code"). This is not a usage limit or a 429: the OAuth subscription token auth mode itself is rejected at organization level, so the implementer made zero model calls and produced no commits. The final `assert-attempt` step message guesses "usage limit / HTTP 429 or token-2 unset", which is misleading for this failure. The real remedy (supplying an Anthropic API key, or an org admin re-enabling subscription access) is a credential/org-policy action outside the repository and must be done by a human. The same cause appears in incident argo-mctl-agents-implement-af43e7b8-1791747930.

## Proposed Fix
Code-level, minimal: in the mctl-agents implement workflow's assert-attempt step (and the orchestrator code that writes the needs-triage reason), detect `oauth_org_not_allowed` / "disabled Claude subscription access" in the implementer output and report it explicitly as an auth/org-policy failure instead of the generic 429/usage-limit hint. Do not change any credentials, secrets, or auth configuration. The implementer should verify the current location of the assert-attempt message before editing.

## Scope
Minimal. Only the failure-reason message text/classification. Credential or org setting changes are out of scope and need a human.
