# Design: incident-91839511

## Confidence: LOW

## Diagnosis
The implement workflow for mctl-api proposal issue-586-fix-audit-getbyworkflow-reports-a-failed failed
because the implementer could not call the model at all: both the primary and the account-2 fallback
OAuth token were rejected with HTTP 403 "oauth_org_not_allowed" (the organization has disabled Claude
subscription access for Claude Code). The implementer then produced no commits and the proposal was
moved to a failed/needs-triage status. This is a credential/account-access problem, not a defect in
any Helm value, alert rule or code in the repository, and it is not something a gitops PR can fix.
A secondary line in the log, "lifecycle-claim: rejected ... op=acquire", suggests a lifecycle
ownership claim conflict for the same proposal; it did not by itself cause the failure and was not
investigated further. The incident has no data indicating a repo-level fix.

## Proposed Fix
No repository change is proposed. The remediation is operational and needs a human:
- Provide the implementer with a valid credential (an Anthropic API key, or re-enable subscription
  access for the organization) in Vault; do not place any secret in git.
- Afterwards, move the proposal mctl-api/issue-586-fix-audit-getbyworkflow-reports-a-failed back to
  `accepted` so the implementer retries it.

The incident text contained no instructions to act on; nothing was ignored as untrusted.

## Scope
Minimal. The implementer should verify the above and, if it finds no concrete repo-level cause,
make no file changes and report that no change was needed. Do not edit secrets, tokens, or auth configuration.
