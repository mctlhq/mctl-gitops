# Design: incident-92739994

## Confidence: LOW

## Diagnosis
The implement workflow failed at run-implementer: the primary attempt failed after about 2 minutes and the fallback could not run because the secret claude-code-oauth-token-2 is not set. assert-attempt then failed the workflow. The log hints the primary failure is most often a Claude five_hour/seven_day usage limit or HTTP 429, but the actual primary failure reason is in a large run-implementer log (about 82 KB) that was not fully readable here, so the primary cause is unconfirmed. The missing second-account token is a Vault/secret provisioning matter that an implementer PR cannot fix.

## Proposed Fix
Code-side only: in the implement workflow wrapper (mctl-agents), when the primary attempt fails and no fallback token is configured, print the primary attempt's failure reason (last error line, HTTP status, usage-limit text) before the "cannot fall back" message, and record it in the durable needs-triage reason in .status.yaml. Do not attempt to create or change any secret. Operator action outside this proposal: provision claude-code-oauth-token-2 and re-queue issue-746 once the usage window resets.

## Scope
Minimal. Only error reporting in the fallback path.
