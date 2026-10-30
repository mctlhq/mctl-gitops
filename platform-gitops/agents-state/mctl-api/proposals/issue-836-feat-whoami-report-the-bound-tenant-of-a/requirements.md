# whoami: report the bound tenant of a tenant-bound agent token

## Context
A tenant-bound agent run token (today: scope `support`, agent `mctl-support`) can act only
on one tenant. `auth.User.BoundTenant()` (`internal/auth/agent.go`) returns that tenant, and
the REST gate (`internal/api/agent_scope_gate.go`), the MCP gate
(`internal/mcp/agent_scope.go`) and `workflowRowVisible` (`internal/api/handlers_read.go`)
all enforce it. But `GET /api/v1/whoami` and `mctl_whoami` report only `id`, `groups`,
`isAdmin` and `namespaces`, which for such a token are `agent:mctl-support`, `[]`, `false`,
`[]`. An agent asking "who am I and what can I see" learns nothing usable. In the
mctl-support 0.2.0 smoke (mctlhq/.github#243) the model asked the user for a team name
instead of reading its tenant's services.

The issue asks whoami to expose the bound tenant as an informational field, and
`mctl_whoami` to print it. Separately, `toolWhoami` (`internal/mcp/server.go`) discards the
`json.Unmarshal` error. A malformed upstream body then renders an empty identity that looks
like "no access" when the read actually failed. It should return a tool error instead.

## User stories
- AS a tenant-bound agent (e.g. mctl-support) I WANT whoami to tell me my bound tenant SO THAT I can pass it as `team`/`tenant` to read tools without asking the user.
- AS a human or admin caller I WANT the whoami response to stay unchanged SO THAT existing clients and scripts keep working.
- AS an operator I WANT a failed whoami read to show up as an error SO THAT it is never mistaken for "this identity has no access".

## Acceptance criteria (EARS)
- WHEN an authenticated principal for which `user.BoundTenant()` returns `(t, true)` calls `GET /api/v1/whoami` THE SYSTEM SHALL include `"boundTenant": t` in the JSON response.
- IF `user.BoundTenant()` returns `ok == false` (human bearer, admin, service user, unscoped agent, unbound-scope agent such as `investigate`, or a bound scope with an empty tenant) THEN THE SYSTEM SHALL omit the `boundTenant` key from the response entirely.
- WHILE serving whoami THE SYSTEM SHALL keep `id`, `groups`, `isAdmin` and `namespaces` computed exactly as today (the bound tenant is not added to `namespaces` or `groups`).
- WHEN the upstream whoami body contains a non-empty `boundTenant` THE SYSTEM SHALL have `mctl_whoami` print a line `Bound tenant: <tenant>` in its text result.
- IF the upstream whoami body has no `boundTenant` (or it is empty) THEN `mctl_whoami` SHALL print no `Bound tenant` line, and the rest of its output SHALL be byte-identical to today.
- THE SYSTEM SHALL describe, in the `mctl_whoami` tool description, that a tenant-bound token reports its bound tenant and can act only on that tenant.
- IF `json.Unmarshal` of the upstream whoami body fails THEN `mctl_whoami` SHALL return a tool error (`IsError: true`) whose message says the identity could not be read, and SHALL NOT render an identity.
- WHILE whoami is served THE SYSTEM SHALL NOT authorize any request against `boundTenant`; enforcement stays in `BoundTenant()` and the existing scope gates.

## Out of scope
- Whether `namespaces` (or `groups`) should also list the bound tenant. The issue leaves this explicitly undecided.
- Any change to agent scope routes or tools, `BoundTenant()` semantics, or the gates that enforce it.
- Exposing other run-token fields (work item, execution id, scope name, run id) in whoami.
- Changes in mctl-support (its prompt workaround from mctlhq/mctl-support#12 can be removed later, separately).
- Changes to `docs/portal-allowlist.json` beyond what tests require. The tool name and annotations are unchanged.

## Open questions
- Should the field also be exposed as a typed struct, or stay a key in the existing `map[string]interface{}` response? This proposal keeps the map and adds the key conditionally, which needs no further decision.
- Should `mctl_whoami` also show the agent scope name (e.g. `support`)? Not requested. Left out.
- Does a malformed body with a 2xx status reach `toolWhoami` in practice? `apiGet` already errors on transport and non-2xx failures. The new error path covers only the decode failure the issue names.
