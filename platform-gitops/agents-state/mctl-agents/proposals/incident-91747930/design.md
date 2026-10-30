# Design: incident-91747930

## Confidence: LOW

## Diagnosis
The implement workflow failed on both the primary and the account-2 fallback attempt. The implementer logs show the Claude SDK returned HTTP 403 with error `oauth_org_not_allowed` ("Your organization has disabled Claude subscription access for Claude Code"). This is not a usage limit or a 429: the OAuth subscription auth mode is rejected at organization level, so no model call was made and no commits were produced. The `assert-attempt` step message suggests 429/usage limit or unset token-2, which misdirects triage. The real remedy (an Anthropic API key, or an org admin re-enabling subscription access) is a human credential/org-policy action. Same root cause as incident argo-mctl-agents-implement-dae24112-1791756910; see proposal incident-91756910.

## Proposed Fix
Overlaps with proposal incident-91756910: classify `oauth_org_not_allowed` failures explicitly in the assert-attempt step / needs-triage reason. If that change has already been made by the other proposal, make no further change and mark tasks complete. Do not modify credentials, secrets, or auth configuration.

## Scope
Minimal. Only the failure-reason message text/classification.
