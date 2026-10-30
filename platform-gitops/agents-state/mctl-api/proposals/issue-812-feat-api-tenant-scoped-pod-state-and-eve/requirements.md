# Tenant-scoped pod state and Kubernetes events reads, and the empty-tenant workflow leak fix (support S0b)

## Context
Issue mctlhq/mctl-api#812 is phase S0b of the tenant support agent epic (mctlhq/.github#243). During the namax66 onboarding (2026-10-25..26), half of the root causes (OOMKilled containers, ImagePullBackOff, quota-exceeded `FailedCreate`, `FailedScheduling`) were visible only in pod status and Kubernetes events. Today no tenant-scoped mctl-api read exposes either: the closest reads are `GET /api/v1/resources/{tenant}` (ResourceQuota usage), `GET /api/v1/status/{team}/{app}` (ArgoCD health) and `GET /api/v1/logs/{team}/{app}` (Loki). A tenant, or a support agent acting for one, cannot see why a pod is not running.

The same phase also closes a visibility leak in `GET /api/v1/workflows` (`Handlers.ListWorkflows`, internal/api/handlers_read.go). It hides other tenants' rows from non-admins, but any row whose derived tenant is empty (platform workflows such as `mctl-agents-*` and `dev-loop-*`) is returned to every authenticated caller.

## User stories
- AS a tenant member I WANT to see the state of every pod of my service (phase, container states, last termination reason and exit code, restart count, waiting reason, requests and limits) SO THAT I can tell an OOM kill, a crash loop or an image pull failure apart without platform-admin help.
- AS a tenant member I WANT to list the Kubernetes events in my namespace over a time window SO THAT I can see quota-exceeded, scheduling and back-off failures.
- AS a support agent bound to one tenant I WANT these reads exposed as read-only MCP tools SO THAT a read-only scope can call them without approval.
- AS a platform operator I WANT non-admin callers to stop seeing platform (empty-tenant) workflow rows SO THAT platform activity does not leak to tenants.

## Acceptance criteria (EARS)
Pod state read: `GET /api/v1/pods/{team}/{app}` and MCP `mctl_get_service_pods`
- WHEN an authenticated caller with tenant access to `{team}` requests pod state for `{app}`, THE SYSTEM SHALL return one item per pod of that service in namespace `{team}`. Each item carries: pod name, phase, node-independent conditions summary (ready), creation time, and per container (init and app): name, image, ready, restart count, current state (`running` / `waiting` with reason and message / `terminated` with reason, exit code, timestamps), last termination state (reason such as `OOMKilled` or `Error`, exit code, finished time), and resource requests and limits.
- IF the caller has no tenant access to `{team}`, THEN THE SYSTEM SHALL answer 403 and SHALL NOT call the Kubernetes API.
- IF the Kubernetes client is not configured, THEN THE SYSTEM SHALL answer 503. It SHALL NOT return an empty list.
- IF the Kubernetes API call fails, THEN THE SYSTEM SHALL answer 503 with a message naming only the namespace. The raw error SHALL go to the log only.
- WHEN the service has no pods, THE SYSTEM SHALL return an empty `items` array with `count: 0`.
- THE SYSTEM SHALL NOT include container `env`, `envFrom`, volume sources, Secret objects or Secret/ConfigMap values in the response. Where a pod references a Secret (for example `imagePullSecrets`), only its name may appear.

Events read: `GET /api/v1/events/{team}` and MCP `mctl_list_namespace_events`
- WHEN an authenticated caller with tenant access to `{team}` requests events, THE SYSTEM SHALL return the Kubernetes events in namespace `{team}` whose last-observed time falls within the requested window (`since`, default `1h`, maximum `24h`), newest first, capped at 200 items. Each item carries type, reason, message, involved object kind and name, count, first and last timestamps, and the source component.
- WHEN the optional `app` filter is given, THE SYSTEM SHALL return only events whose involved object name is the service's workload name or starts with it (`{team}-{app}`).
- WHEN the optional `type` filter is `Warning` or `Normal`, THE SYSTEM SHALL return only events of that type.
- IF `since` is unparsable or outside 1m..24h, THEN THE SYSTEM SHALL answer 400.
- IF the caller has no tenant access to `{team}`, THEN THE SYSTEM SHALL answer 403 and SHALL NOT call the Kubernetes API.
- IF the item cap truncates the result, THEN THE SYSTEM SHALL set `truncated: true`.
- IF the Kubernetes client is not configured or the API call fails, THEN THE SYSTEM SHALL answer 503. It SHALL NOT return an empty list.
- IF `secretscan.Scan` (internal/secretscan) flags an event message or a container state message, THEN THE SYSTEM SHALL replace that message with `[redacted: <pattern>]` before returning it.

MCP tools
- THE SYSTEM SHALL register both tools with names that `auth.IsReadTool` admits (`mctl_get_...` / `mctl_list_...`), `ReadOnlyHint=true` and `DestructiveHint=false`, and SHALL record them in `recordedHints` and `TestReadOnlyToolsAreTheRecordedSet`.
- WHILE an `AgentScopeInvestigate` run token is used, THE SYSTEM SHALL admit the two new GET routes through that scope's route list.
- WHILE a `support` run token (S0a) is used, THE SYSTEM SHALL admit both routes through the `support` route list with the `{team}` segment bound to the token's tenant (`BindTenant`), and SHALL admit both MCP tools through `supportTools` with their `team` argument required and equal to the bound tenant. A `support` token reading another tenant's pods or events SHALL get 403 `agent_scope_denied`.

Kubernetes RBAC
- THE PLATFORM SHALL grant the mctl-api ServiceAccount `list` on `pods` and `list` on `events` (core API group) in every tenant namespace, through the tenant chart's `mctl-api-workflows` Role, before the mctl-api release that serves these routes is deployed. No `get`/`list` on Secrets, ConfigMaps or `pods/log`, and no write verb, is added.

Workflow leak
- WHEN a non-admin caller lists workflows, THE SYSTEM SHALL omit every audit row whose parameters are unreadable, and every audit row whose derived tenant is empty unless the caller is an agent scope with `ReadAllTenants` (see Open questions).
- WHEN an admin lists workflows, THE SYSTEM SHALL continue to return empty-tenant rows.
- WHILE a caller carries a tenant-bound support identity, THE SYSTEM SHALL keep returning only rows whose team equals the bound tenant. That rule and `User.BoundTenant()` are owned by S0a (mctlhq/mctl-api#811, task 7); S0b SHALL NOT redefine or stub them, and its change SHALL keep S0a's bound-tenant tests green.

## Out of scope
- The support scope itself (S0a) and read auditing (S0c).
- Pod logs from previous container instances (Loki logs are already exposed through `mctl_get_service_logs`).
- Preview-namespace (`{team}-preview`) pods and events.
- Any write action on pods (restart, delete).
- Node-level information (node names, node conditions) beyond what an event message itself states.

## Decisions (owner amendment, 2026-10-26)

- Ordering: S0b is implemented after S0a's PR (mctlhq/mctl-api#811) has merged. S0b builds on S0a's `support` scope, `User.BoundTenant()` and bound-tenant `ListWorkflows` rule instead of stubbing them, so the two PRs do not both edit the same lines.
- Split on `ListWorkflows`: S0a owns the bound-tenant branch (a support token sees only its own tenant's rows, never empty-tenant rows). S0b owns the non-admin leak fix (empty-tenant and unreadable rows hidden from non-admins, except `ReadAllTenants` agent scopes for empty-tenant rows).
- Support scope: S0b adds its two routes to the `support` route list and its two tools to `supportTools`, as S0a's requirements already state ("The S0b diagnostics routes are added when S0b defines them").
- RBAC: granted in mctl-gitops, in the tenant chart's `mctl-api-workflows` Role (task 0), as its own gitops PR merged and synced before the mctl-api release. Today that Role grants only `workflows` and `resourcequotas`; the existing `get pods` is in `argo-workflows` (Role `mctl-api-workflow-submitter`), not in tenant namespaces. See design.md, Current state.

## Open questions
- Pod selection label. The design selects by `app.kubernetes.io/instance={team}-{app}`. That follows the ArgoCD app name `{team}-{app}` and Loki's pod regex `{ns}-{app}-.+` in internal/loki. It falls back to the pod-name prefix `{team}-{app}-` when the label matches nothing. Confirm against the base-service chart.
- Agent scopes with `ReadAllTenants` (the issue-investigator scope) are not admins. Read literally, the fix hides platform workflow rows from them too. The proposal keeps those rows visible to admins and to `ReadAllTenants` agent scopes only, because those scopes already read every tenant and use platform rows for diagnosis. The reviewer should confirm or tighten this.
