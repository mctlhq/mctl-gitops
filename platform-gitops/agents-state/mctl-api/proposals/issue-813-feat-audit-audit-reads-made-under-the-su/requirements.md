# Audit every request made under the support scope (support S0c)

## Context
Issue mctlhq/mctl-api#813 is phase S0c of the tenant support agent epic (mctlhq/.github#243).
A support run holds an agent run token minted with the `support` scope
(`auth.AgentScopeSupport`, `internal/auth/agent_scope.go`). That token is bound to one tenant and
can only read. Today the `audit_events` table (`internal/audit/postgres.go`) records operations,
incident changes and scope refusals at the REST layer (`agent_scope.denied` in
`internal/api/agent_scope_gate.go`). Reads the run is allowed to make leave no audit row. On the
MCP side, a tool call the scope refuses only produces a `slog.Warn` (`internal/mcp/agent_scope.go`).
So from mctl-api alone nobody can answer "what did the support agent read about tenant X, and for
whom?".

The proposal writes exactly one audit row for every request made with a support-scope token,
reads and refusals included. A row records metadata only and never a response body. Admins get a
read of these rows filtered by tenant and by execution id. A failed audit write is counted and
logged, never dropped silently.

## User stories
- AS a platform admin I WANT to list everything support runs read about a tenant SO THAT I can answer a tenant's "who looked at my data" question.
- AS a platform admin I WANT to list every request one support task (execution) made SO THAT I can review a single support conversation end to end.
- AS the tenant member who asked for support I WANT every read made on my behalf to name me in `user_principal_id` SO THAT the agent's access stays attributable to the request I made, and a query by my principal finds it next to my own actions.
- AS an operator I WANT audit write failures to show up as a metric SO THAT a broken audit trail raises an alert instead of passing silently.

## Acceptance criteria (EARS)
- WHEN a request authenticated by a run token whose scope is `support` reaches the REST agent scope gate and is admitted THE SYSTEM SHALL write exactly one `audit_events` row with operation `support.request` after the handler returns. The row SHALL carry the bound tenant, layer `rest`, method and path, the HTTP result status, `user_principal_id` set to the tenant member who minted the token (`AgentRunRequestedBy`), `via_principal_id` set to the support agent's own principal (`user.PrincipalID()` of the agent user), and `via_execution_id` set to the token's execution id.
- WHEN a support-scope token calls an MCP tool and the scope admits the call THE SYSTEM SHALL write exactly one `support.request` row for that tool call, with layer `mcp`, the tool name, the result (`succeeded` or `failed`), the bound tenant and the same principal and execution fields.
- WHILE an MCP tool call made with a support-scope token is in progress THE SYSTEM SHALL fold the loopback REST requests that tool makes with the same token into that tool call's row, as a bounded list of method, path and status. It SHALL NOT write a separate row for each of them, so one support read produces exactly one row.
- IF a support-scope request is refused by the scope, at the REST or the MCP layer, THEN THE SYSTEM SHALL write a row with status `denied` that names the refused route or tool. The refusal SHALL NOT be dropped.
- WHILE writing a support audit row THE SYSTEM SHALL NOT include response bodies, request bodies, tool results or tool argument values other than the tenant.
- IF writing an audit row to PostgreSQL fails THEN THE SYSTEM SHALL increment `mctl_audit_write_failures_total` and log an error that names the operation and the request id.
- IF a support-scope MCP tool call arrives while no support auditor is configured on the MCP server THEN THE SYSTEM SHALL refuse the call rather than serve an unaudited read.
- WHEN an admin calls `GET /api/v1/audit/support` with `tenant` and/or `execution_id` THE SYSTEM SHALL return the matching `support.request` and support-scope `agent_scope.denied` rows, newest first, bounded by `limit` (default 100, max 500). The rows SHALL include the tenant, layer, route or tool, status, `user_principal_id`, `via_principal_id` and `via_execution_id`.
- IF a caller of `GET /api/v1/audit/support` is not a platform admin, or the request names neither `tenant` nor `execution_id`, THEN THE SYSTEM SHALL refuse it (403 or 400 respectively).
- WHILE support rows exist THE SYSTEM SHALL keep them out of `GET /api/v1/audit` (`List`), so high-volume reads do not push operation history out of the 50-row feed or out of `mctl_list_recent_operations`.
- WHEN a request is made by any token other than a support-scope run token THE SYSTEM SHALL write no new audit rows. Existing audit behaviour is unchanged.

## Out of scope
- Auditing reads made by ordinary user, service, surface or other-scope agent tokens.
- Usage or cost records (S1c).
- An MCP tool for the admin read (REST only. Adding a tool changes the tool count in `server_test.go`. It can follow later).
- Retention or archival policy for `audit_events`.
- Failing the request closed when an audit write fails (see Open questions).

## Open questions
- Principal field mapping: **resolved by the owner amendment (2026-10-27), platform convention wins.** Elsewhere in mctl-api `user_principal_id` names the human the request is for and `via_principal_id` names the relaying surface or the acting agent (`User.ViaPrincipalID()` in `internal/auth/principal.go`; delegation in `TestAgentPrincipalGate_SuccessBuildsTheDelegatedSubject`, where `PrincipalID()` is the human subject and the agent is the acting principal). The issue's wording ("`via_principal_id` (the caller the agent acts for)") inverted that and is superseded. A support row therefore carries `user_principal_id = AgentRunRequestedBy()` (the tenant member who minted the token; always set, because the `support` scope is minted only by a tenant member) and `via_principal_id = ` the agent user's own `PrincipalID()` (an agent identity is `KindAgent` and is resolved by `AttachPrincipal`, so it is set whenever the principal store answered). `UserID` stays `agent:<name>`. One query by `user_principal_id` then finds a person's own actions, their delegated actions and the support reads made for them.
- Fail-open vs fail-closed on audit write failure. The issue only requires visibility, so the design serves the response and counts the failure. For REST the row is written after the handler, because the status must be known, so failing closed would need a pre-write and an update.
- When an MCP tool's loopback REST call is refused by the gate, two rows result: the gate's `agent_scope.denied` and the tool-call row with status `denied`. This is kept on purpose, because refusals are security events. The "exactly one row" criterion is read as applying to an admitted read.
- Deployed configuration: **observed by the owner amendment (2026-10-27).** mctl-api is deployed from `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`, not from `services/`, and that manifest sets `AUDIT_DB_URL` to `shared-pg-rw.platform-db.svc:5432/mctl-api?sslmode=require`. Production runs `PostgresLogger`, so support rows are persisted.
