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

Workflow leak
- WHEN a non-admin caller lists workflows, THE SYSTEM SHALL omit every audit row whose parameters are unreadable, and every audit row whose derived tenant is empty unless the caller is an agent scope with `ReadAllTenants` (see Open questions).
- WHEN an admin lists workflows, THE SYSTEM SHALL continue to return empty-tenant rows.
- WHILE a caller carries a tenant-bound support identity (introduced by S0a), THE SYSTEM SHALL return only rows whose team equals the bound tenant.

## Out of scope
- The support scope itself (S0a) and read auditing (S0c).
- Pod logs from previous container instances (Loki logs are already exposed through `mctl_get_service_logs`).
- Preview-namespace (`{team}-preview`) pods and events.
- Any write action on pods (restart, delete).
- Node-level information (node names, node conditions) beyond what an event message itself states.

## Open questions
- Where the mctl-api ServiceAccount's RBAC lives. It is not in this repo's `helm/` chart or in the visible gitops `services/` and `tenants/` paths. The reads need `list` on `pods` and `events` (core and/or `events.k8s.io`) in tenant namespaces. The existing `k8s.AgentRunBinding` already does `get pods`, so some pod read exists. Verify, and grant `list` if missing, in the platform repo that owns it. Until then the reads answer 503, not empty.
- Pod selection label. The design selects by `app.kubernetes.io/instance={team}-{app}`. That follows the ArgoCD app name `{team}-{app}` and Loki's pod regex `{ns}-{app}-.+` in internal/loki. It falls back to the pod-name prefix `{team}-{app}-` when the label matches nothing. Confirm against the base-service chart.
- Agent scopes with `ReadAllTenants` (the issue-investigator scope) are not admins. Read literally, the fix hides platform workflow rows from them too. The proposal keeps those rows visible to admins and to `ReadAllTenants` agent scopes only, because those scopes already read every tenant and use platform rows for diagnosis. The reviewer should confirm or tighten this.
- S0a (support scope with a bound tenant) has not landed: `internal/auth` has no support scope today. The `team == bound tenant` rule is implemented as a hook that S0a fills in, or directly if S0a merges first (see design).
