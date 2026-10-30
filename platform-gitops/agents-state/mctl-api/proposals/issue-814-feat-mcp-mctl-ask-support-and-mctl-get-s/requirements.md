# MCP tools mctl_ask_support and mctl_get_support_task (support S1d)

## Context

Issue mctlhq/mctl-api#814 is phase S1d of the tenant support agent epic
(mctlhq/.github#243). The tenant support agent `mctl-support` is live at
`https://support.mctl.ai` (image 0.2.1). It speaks A2A 1.0 over the HTTP+JSON
binding only: `GET /.well-known/agent-card.json`, `POST /message:send`,
`GET /tasks/{id}`, `POST /tasks/{id}:cancel`. Every request must carry the
header `A2A-Version: 1.0`. mctl-support admits a tenant member's own bearer,
and `metadata.tenant` selects the tenant.

S1d makes that agent reachable from every MCP client (Claude, ChatGPT, Cursor)
through mctl-api's existing MCP server. It does this with two thin tools.
`mctl_ask_support` sends the question on the caller's behalf, with the
caller's own bearer unchanged, and by default waits for the answer.
`mctl_get_support_task` reads a task later. mctl-api adds no authority. It
uses no service credential. Its only check is that the caller is a member of
the named tenant. mctl-support then applies its own check as well.

## User stories

- AS a tenant member using an MCP client I WANT to ask the support agent a question about my tenant in one tool call SO THAT I get the diagnosis without leaving my client.
- AS a tenant member I WANT to fetch a support task by id SO THAT I can collect an answer that took longer than the synchronous wait.
- AS a platform operator I WANT mctl-api to forward only the caller's own bearer, and to refuse a tenant the caller is not a member of SO THAT the MCP adapter cannot widen anyone's access to mctl-support.
- AS a platform operator I WANT every failure from mctl-support reported as a failure SO THAT no client reads an outage as "the agent had nothing to say".

## Acceptance criteria (EARS)

- WHEN `mctl_ask_support` is called with `tenant` and `question` THE SYSTEM SHALL send exactly one `POST {SUPPORT_A2A_URL}/message:send`. The request SHALL carry `A2A-Version: 1.0`, `Content-Type: application/json`, the caller's own bearer as `Authorization: Bearer <token>` (unchanged), a user message whose text part is `question`, request-level `metadata.tenant` set to the normalized tenant, `configuration.returnImmediately: true`, and `contextId` when `context_id` is given.
- THE SYSTEM SHALL apply one wait budget of `SUPPORT_ASK_WAIT` (default 60s, maximum 90s), started immediately before the send, to the send and all polling together. No phase SHALL receive a fresh or extended budget.
- IF the send fails without a task id (transport error, budget expiry, 5xx, or an undecodable 2xx body) THEN THE SYSTEM SHALL return the tool error `support_send_outcome_unknown` naming the sent `messageId`, SHALL NOT poll, and SHALL NOT resend `message:send`.
- IF the caller does not have access to `tenant` (`auth.User.HasTenantAccess` is false, or in stdio mode `/api/v1/whoami` lists neither the tenant nor admin) THEN THE SYSTEM SHALL return a tool error and SHALL NOT send any request to mctl-support.
- IF the caller's tenant membership cannot be determined (no authenticated user and `/api/v1/whoami` fails or cannot be decoded) THEN THE SYSTEM SHALL return a tool error and SHALL NOT contact mctl-support.
- IF there is no caller token THEN THE SYSTEM SHALL return a tool error and SHALL NOT contact mctl-support. No service credential is ever substituted.
- WHEN mctl-support answers `message:send` with a task in a non-terminal state THE SYSTEM SHALL poll `GET {SUPPORT_A2A_URL}/tasks/{id}` with the same bearer and `A2A-Version: 1.0` until the task reaches a terminal or interrupted state, or until the configured wait (`SUPPORT_ASK_WAIT`, default 60s) passes.
- WHEN the task reaches `COMPLETED` THE SYSTEM SHALL return the task id, context id, state and answer, read from `status.message.parts` as the primary source. The answer text SHALL be the non-blank text parts of that source in order, joined with `"\n"`, and the structured result (summary, classification, evidence, recommended_actions, escalation_id, dropped_unsupported_evidence) SHALL be its first object-valued data part, passed through unchanged.
- IF a `COMPLETED` task's `status.message` has no non-blank text part and no object-valued data part THEN THE SYSTEM SHALL read the answer from the task's artifacts instead, by the same rules. The two sources SHALL never be mixed, and `history` SHALL never be read as an answer.
- IF a `COMPLETED` task has no meaningful answer in either `status.message` or artifacts THEN THE SYSTEM SHALL return the tool error `support_empty_answer` naming the task id. It SHALL NOT return an empty success.
- WHEN mctl-support answers `message:send` with a direct message instead of a task THE SYSTEM SHALL return that message's text and data as the answer, with no task id.
- IF the wait passes before a terminal state AND the last read of the task succeeded THEN THE SYSTEM SHALL return a non-error result with the task id, context id and current state, plus a note telling the client to continue with `mctl_get_support_task`.
- IF the wait passes before a terminal state AND the last poll failed (or no poll after the send succeeded and the send reply was not terminal) THEN THE SYSTEM SHALL return a tool error naming the task id and the last failure.
- WHEN the task is in `FAILED`, `REJECTED` or `CANCELED` THE SYSTEM SHALL return a tool error naming that state and the reason from the task status message. It SHALL never return an empty answer in its place.
- WHEN the task is in `INPUT_REQUIRED` or `AUTH_REQUIRED` THE SYSTEM SHALL stop waiting and return the state, the status message and the context id.
- IF mctl-support cannot be reached, answers non-2xx, or returns a body that cannot be decoded as an A2A task or message THEN THE SYSTEM SHALL return a tool error that names the HTTP status or failure class. It SHALL NOT return an empty or partial answer.
- WHEN `mctl_get_support_task` is called with `id` THE SYSTEM SHALL send one `GET {SUPPORT_A2A_URL}/tasks/{id}` with the caller's own bearer and `A2A-Version: 1.0`. It SHALL return the state and, for a terminal task, the answer, using the same rendering and failure rules as `mctl_ask_support`.
- IF `id` is empty or is not one path segment THEN THE SYSTEM SHALL refuse the call without contacting mctl-support.
- IF `SUPPORT_A2A_URL` is not configured THEN both tools SHALL return a tool error saying that the support agent is not configured on this server. The tools stay registered.
- WHILE a tool call runs THE SYSTEM SHALL NOT follow HTTP redirects from mctl-support. A redirect is a non-2xx failure, so the bearer is never sent to another host.
- WHILE `mctl_ask_support` waits THE SYSTEM SHALL keep the `/mcp` response writable for the configured wait plus a margin. The 30s `ServerWriteTimeout` SHALL NOT truncate a wait that is within the configured bound.
- WHILE the caller holds a scoped agent run token (for example mctl-support's own `support` scope) THE SYSTEM SHALL refuse `mctl_ask_support` through the existing agent scope middleware. Neither tool is added to the support scope tool list.
- THE SYSTEM SHALL record `mctl_ask_support` as not read-only and `mctl_get_support_task` as read-only in `internal/mcp/annotations_test.go`. It SHALL list both in `docs/portal-allowlist.json` with a decision and a reason, and enable `mctl_ask_support` on the portal only through a `mutatingOnPortal` entry.
- WHEN a synthetic fixture in the mctl-support 0.2.1 shape is answered through `mctl_ask_support` THE SYSTEM SHALL return an answer equal to the answer decoded from a direct `GET /tasks/{id}` on the same fixture, and equal to the literal expected text and result. An implementation that reads only artifacts SHALL fail this check.

## Out of scope

- Any change to mctl-support itself, including its own tenant admission check, which S1a-S1c delivered. That check is tested in mctlhq/mctl-support.
- JSON-RPC A2A binding, streaming (`message:stream`), push notifications, and an MCP tool for `POST /tasks/{id}:cancel`.
- A REST route in mctl-api for support. The tools call mctl-support directly.
- Persisting support tasks or answers in mctl-api.
- Widening `SUPPORT_ALLOWED_TENANTS` (the pilot allowlist lives in mctl-support's values).
- S1e (mctlhq/mctl-support#5).

## Open questions

- The issue says the `mutatingOnPortal` map is in `internal/mcp/annotations_test.go`. In the clone it is in `internal/mcp/portal_allowlist_test.go`, and `annotations_test.go` holds `recordedHints`. This proposal edits both files, each for its own purpose.
- Admins: `HasTenantAccess` admits platform admins for any tenant. The issue says "member of the tenant". This proposal keeps the platform-wide rule (admins pass), which matches the admin override that the `support` run token mint already has (docs/support-agent-scope.md). mctl-support makes the final decision.
- Resolved 2026-10-27: request-level `metadata.tenant` is correct (mctl-support `admission.requested_tenant_from_body` reads it first). See design.md "Confirmed mctl-support 0.2.1 wire contract".
- Resolved 2026-10-27: fixtures are synthetic and anonymised in the 0.2.1 shape (design.md section 6). No recorded response goes into the public mctl-api repository.
- Resolved 2026-10-27: the non-blocking flag in a2a-sdk 1.2.3 is `configuration.returnImmediately`. A `blocking` field does not exist in A2A 1.0 and is silently ignored by the SDK's REST decoder.
- The wait budget versus intermediaries is unconfirmed. `ServerWriteTimeout` is 30s, and this proposal extends the `/mcp` write deadline per request. The upstream timeouts of the Cloudflare MCP portal and the ingress in front of api.mctl.ai were not observed. If either is shorter than 60s, the default wait must be lowered. The proposal caps `SUPPORT_ASK_WAIT` at 90s.
- Token audience. Forwarding the MCP bearer to a second service is a deliberate passthrough, required by the issue. It works only if mctl-support accepts tokens issued for api.mctl.ai (its `MCTL_AUTH_ISSUER` is https://api.mctl.ai, and the issue says a member's bearer is admitted). This was not verified end to end from the MCP path.
