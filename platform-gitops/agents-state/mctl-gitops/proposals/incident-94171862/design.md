# Design: incident-94171862

## Confidence: LOW

## Diagnosis
The investigate workflow for mctl-agents issue 1051 failed because the Claude Code OAuth subscription token used by the investigator was rejected with HTTP 403 `oauth_org_not_allowed` ("Your organization has disabled Claude subscription access for Claude Code"). The agent ran 28 turns before the rejection, wrote none of requirements.md/design.md/tasks.md, and the fallback attempt could not run because the secondary token (`claude-code-oauth-token-2`) is not set. The assert-attempt step's generic hint (five_hour usage limit / 429) is not the actual cause here. This is an account/credential policy problem on the Anthropic side, not a defect in the issue or in repo configuration. The skill matcher missed it because the incident is a generic workflow_failed with no matching skill.

## Proposed Fix
Primarily an operator action outside the repository: re-enable Claude subscription access for the organization, or provision an Anthropic API key / a valid `claude-code-oauth-token-2` in Vault so the fallback attempt works. Then re-trigger the investigation of mctl-agents issue 1051.

Repository-side, only if the implementer can confirm it by reading the CWFT / external-secret definitions in mctl-gitops: check that the secret key `claude-code-oauth-token-2` is actually wired into the investigate WorkflowTemplate and its ExternalSecret. If the wiring is missing, add it. If the wiring is already present, make NO change.

## Scope
Minimal. Do not alter any other secret, policy or template. No incident text requested any change; none was acted on.
