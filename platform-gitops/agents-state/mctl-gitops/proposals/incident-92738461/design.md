# Design: incident-92738461

## Confidence: LOW

## Diagnosis
The investigate workflow for mctl-agents issue 746 failed in run-investigator at run token setup: the exchange with mctl-api was refused with HTTP 403 agent_run_exchange_refused. The fallback account-2 token is also not set, so there was no fallback. The exact reason for the refusal (agent release binding, profile, or run policy) is not visible in the available logs. The related implement workflow for the same issue (mctl-agents-implement-70aeec81) also failed and is likely the same cause, but was not examined.

## Proposed Fix
No definitive file change is identified. The implementer must first verify, via the agent release binding and execution profile for the investigator agent in the gitops agent-platform manifests, whether the binding or profile is valid and allowed to exchange run tokens (shadow_scope "investigate"). Change a value only if a concrete misconfiguration is found. Also check whether claude-code-oauth-token-2 is expected to be provisioned in Vault for the fallback path; do not invent secret values.

## Scope
Minimal. Only touch the single field or rule that causes this specific failure. If nothing in gitops is misconfigured, make no change and record that human follow-up is needed.
