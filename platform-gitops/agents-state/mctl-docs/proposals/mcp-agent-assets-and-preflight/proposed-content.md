<!-- Target: docs/mcp/tools-reference.md, new subsection under agent platform tools -->

### `mctl_list_agent_assets` (admin)

Read-only merged index of agent assets: the registry catalog, gitops execution profiles, release intents, agent-platform policy catalogs and platform skills. It also includes reverse references: which profiles use a given skill, tool, policyRef or model-policy task.

Takes no parameters. Each source reports `status` `ok` or `unavailable`. **An unavailable source is `null`, never an empty list**, so a missing source is not mistaken for "nothing there". The index carries no eligibility or grant semantics.

### `mctl_get_agent_preflight` (admin)

Read-only report on whether an agent and execution profile would pass the platform's CI-equivalent rules: budget and timeout ceilings, sandbox, known references, approval gates, capability discovery and binding lifecycle.

| Parameter | Required | Description |
|---|---|---|
| `agent_name` | yes | For example `issue-investigator`. |
| `environment` | one form | `production` or `shadow`. |
| `definition_version` + `profile` | other form | An explicit pin; `profile_version` is optional. |

Use either `environment`, or `definition_version` with `profile`, not both. The tool resolves through the registry and falls back to the gitops profile, reporting which it used. Every check is `pass`, `fail` or `unknown` and names the CI rule it mirrors. **`unknown` is never `pass`.** This report has no eligibility semantics; `validate-agent-platform.py` in CI stays authoritative.
