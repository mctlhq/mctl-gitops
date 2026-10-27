# mctl-support S1a: A2A server, admission and task store

## Context
Issue mctlhq/mctl-support#2 is phase S1a of the tenant support agent epic
(mctlhq/.github#243). It asks for the first vertical slice of `mctl-support`:
an A2A 1.0 server (HTTP+JSON/REST binding, official `a2a-sdk==1.2.3`) at
`support.mctl.ai` that admits a tenant member's question and tracks it as a
task. The work covers admission, idempotency, a Postgres task store with
retention, and a deterministic fake executor. The model-driven agent loop
arrives in S1b. In this phase a scripted executor stands in for it, so the
protocol, admission and storage can be tested without a model or mctl-api.

The phase also registers the `mctl-support` agent definition in the mctl-api
agent registry. It opens one WorkItemExecution (`we_...`) per support task,
so each task's `support` run token is bound to an execution and is revoked
when that execution ends. It deploys two hardened replicas through gitops.
This matters because the pilot tenant (`namax66`) asked for the product. It
is also the first service that mints a tenant-bound token from a caller's
bearer, so admission and tenant isolation must be right from the first
deployed version.

## User stories
- AS a member of an allowlisted tenant I WANT to send a support question over A2A and get a task back SO THAT I can follow its progress and read the answer.
- AS a tenant member I WANT a retried `message:send` with the same message identity to return the original task SO THAT a network retry never starts a second investigation.
- AS a tenant member I WANT to cancel a running task through any replica SO THAT a stuck or unwanted investigation stops and its run token stops working.
- AS a platform admin I WANT unauthenticated callers, non-members and non-allowlisted tenants refused SO THAT the agent only serves the pilot and admins.
- AS a tenant member I WANT my tasks and contexts invisible to other principals SO THAT nobody can read or probe my support conversations.
- AS the platform operator I WANT transcripts and inactive contexts deleted after 7 days and task metadata after 30 days SO THAT retention follows decision D10.
- AS a developer I WANT a deterministic fake executor SO THAT contract tests run without a model or mctl-api.

## Acceptance criteria (EARS)

Protocol
- WHEN a client requests `GET /.well-known/agent-card.json` THE SYSTEM SHALL return an A2A 1.0 agent card that declares the HTTP+JSON binding, exactly one skill with id `diagnose`, and a `securitySchemes` entry of type OAuth 2 pointing at mctl-api's authorization server metadata.
- THE SYSTEM SHALL serve `POST /message:send`, `GET /tasks/{id}` and `POST /tasks/{id}:cancel` through the routes of the pinned `a2a-sdk` (`a2a.server.routes`), with no hand-maintained second transport.
- THE SYSTEM SHALL report only the A2A task states `submitted`, `working`, `completed`, `input-required`, `failed`, `canceled` and `rejected`.
- IF a client calls `message:stream` or a push-notification endpoint THEN THE SYSTEM SHALL answer with the A2A "unsupported operation" error. The agent card SHALL declare `streaming: false` and `pushNotifications: false`.

Admission
- IF a request carries no bearer, or a bearer that mctl-api does not accept, THEN THE SYSTEM SHALL refuse it with HTTP 401 before any task, context or reservation is written.
- WHEN a bearer is accepted THE SYSTEM SHALL resolve the caller's principal id, admin flag and tenant memberships from mctl-api using that bearer.
- IF the request does not resolve to exactly one tenant the caller is a member of THEN THE SYSTEM SHALL refuse it with HTTP 403 and write nothing. "Exactly one" means: the single membership, or the one tenant named in the request metadata (`metadata.tenant`) when the caller is a member of several.
- IF the resolved tenant is not in the configured allowlist and the caller is not a platform admin THEN THE SYSTEM SHALL refuse the request with HTTP 403 and write nothing.
- IF mctl-api cannot be reached or returns an error while admission is resolved THEN THE SYSTEM SHALL fail closed (HTTP 503) and never treat the failure as "no memberships" or "allowed".

Ownership and isolation
- IF `GET /tasks/{id}` or `POST /tasks/{id}:cancel` names a task owned by another principal THEN THE SYSTEM SHALL return the same `TaskNotFound` error, with the same status and body shape, that it returns for an id that does not exist.
- IF `message:send` names a `contextId` that the caller does not own THEN THE SYSTEM SHALL return the same error whether that context exists for someone else or does not exist at all.
- WHILE a context exists THE SYSTEM SHALL bind it to exactly one (principal, tenant) pair, and SHALL refuse a continuation that resolves to a different tenant.

Idempotency
- WHEN `message:send` arrives with a `messageId` that the same principal has already sent THE SYSTEM SHALL return the existing task and SHALL NOT start a second execution, a second WorkItemExecution or a second run token.
- THE SYSTEM SHALL reserve the (principal, messageId) pair in Postgres in the same transaction that creates the task, before the executor is started, so that two concurrent duplicates on two replicas yield one task.
- IF a duplicate `messageId` arrives with different message content THEN THE SYSTEM SHALL refuse it with an A2A invalid-params error and leave the existing task unchanged.

Replicas and cancel
- WHILE two replicas share one Postgres database THE SYSTEM SHALL let a task created through one replica be read, continued (`input-required`, then a follow-up message) and cancelled through the other.
- WHEN a cancel is accepted for a task running on another replica THE SYSTEM SHALL stop that replica's in-flight executor. The task SHALL reach `canceled`, and the WorkItemExecution SHALL be moved to a terminal phase so that its run token is revoked.
- WHEN a task reaches `completed`, `failed`, `canceled` or `rejected` THE SYSTEM SHALL move its WorkItemExecution to the matching terminal phase.

WorkItemExecution and token
- WHEN a new task is admitted THE SYSTEM SHALL create exactly one WorkItemExecution (`we_...`) for it in mctl-api under the `mctl-support` agent, record the id on the task, and mint the task's `support` run token from the caller's bearer, bound to that execution.
- IF the execution cannot be created or the token cannot be minted THEN THE SYSTEM SHALL move the task to `failed` with an explicit reason and SHALL NOT run the executor.
- THE SYSTEM SHALL never persist the caller's bearer or the run token in Postgres or in logs.

Retention
- WHEN the retention job runs THE SYSTEM SHALL delete transcripts older than 7 days, contexts with no activity for 7 days, and task metadata older than 30 days, measured against an injectable clock.
- WHILE several replicas run THE SYSTEM SHALL let only one replica execute a given retention pass, using a Postgres advisory lock.
- IF a retention pass fails THEN THE SYSTEM SHALL log the error and retry on the next schedule, never silently reporting success.

Fake executor
- WHERE `SUPPORT_EXECUTOR=fake` is configured THE SYSTEM SHALL answer with a scripted answer selected by the message text. One script is an immediate `completed` answer, one is a slow multi-second `working` turn that honours cancel, one asks for `input-required` and one ends in `failed`. No model or mctl-api read is used.
- IF `SUPPORT_EXECUTOR=fake` is set while `SUPPORT_ENV=production` THEN THE SYSTEM SHALL refuse to start. The exception is when the explicit `SUPPORT_ALLOW_FAKE_IN_PRODUCTION=true` flag is set for the S1a pilot.

Deployment
- THE SYSTEM SHALL run as 2 replicas in tenant `admins` under restricted PSS, with `runAsNonRoot`, all capabilities dropped, seccomp `RuntimeDefault`, a read-only root filesystem, `automountServiceAccountToken: false` and no projected service-account token volume.
- THE SYSTEM SHALL be reachable at `https://support.mctl.ai` with TLS.

Live probe
- WHEN the S1a deployment is live THE SYSTEM's operator SHALL record, for a token minted as a `namax66` member: HTTP 200 from `GET /api/v1/status/namax66/news-factory`, and 403 `agent_scope_denied` for another tenant's service, over REST and through MCP `mctl_get_service_status`. The output SHALL be attached to issue #2.

## Out of scope
- The model-driven agent loop, the Anthropic tool runner and the support read tools (S1b).
- `message:stream`, push notifications and any external OAuth/A2A exposure (S2). This includes the hard audience-enforcement check on `api.mctl.ai` that must precede S2.
- JSON-RPC, unless the pinned SDK serves it without extra code. If it does, it is not tested as a second contract.
- Changes to mctl-api itself (the `support` scope, minting and WorkItemExecution endpoints are S0a / mctl-api#811). This phase only consumes them.
- A platform-wide FQDN egress mechanism (none exists in mctl-gitops today).

## Reviewer decisions (amendment 2026-10-27)
- Namespace: deploy into the existing `admins` namespace for S1a. A dedicated
  namespace with internet egress off is a later gitops change.
- Egress: the namespace-wide `allow-internet-egress` limitation is accepted
  for S1a and written down in values.yaml, as the issue allows.
- mctl-api endpoints: fixed in design.md "mctl-api contract", including the
  new `a2a` execution engine (mctl-api#824, a prerequisite for deployment).
- AgentDefinition: canonical file `agent/agent.yaml` in this repo,
  registered in the mctl-api registry by the operator after merge.
- A duplicate `messageId` with different content is refused (invalid params).
- Tenant selection for multi-tenant callers is `metadata.tenant`.
- The task owner key is whoami's `id`; whoami has no principal id field.

## Open questions (as investigated; resolved above)
- Namespace. The issue asks for "tenant `admins`, namespace `support`". The tenant chart (`platform-gitops/helm-charts/tenant`) creates either the namespace `admins` or one namespace per `teams[]` entry named `admins-<team>`, and setting `teams` would replace the existing `admins` namespace. Proposed: deploy into the existing `admins` namespace for S1a, and track a dedicated namespace as a gitops chart change. Needs reviewer confirmation.
- Egress. The `admins` namespace has `allowInternetEgress: true` (tenant values and the live `mctl_get_tenant`). Kubernetes NetworkPolicies are additive, so a pod-level policy cannot narrow it. The limitation is written down in design.md; a real restriction needs the dedicated namespace above.
- The exact mctl-api endpoints for principal resolution, WorkItemExecution creation, terminal-phase transition and `support` token minting come from the mctl-api#811 contract. That contract is not readable from this clone and must be confirmed during implementation.
- Where the canonical `mctl-support` AgentDefinition lives: in this repo (`agent/agent.yaml`, proposed) or in mctl-agents `agents/_manifests/`. ADR 007 puts definitions in mctl-agents.
- Whether a duplicate `messageId` with different content should be refused (proposed) or answered with the original task.
- The tenant-selection rule for callers in several tenants (`metadata.tenant`, proposed) is not specified by the issue.
