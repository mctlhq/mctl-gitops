# Tasks: issue-2-mctl-support-s1a-a2a-server-admission-an

- [ ] 1. Add `src/mctl_support/config.py`. Settings come from env: `DATABASE_URL`, `MCTL_API_URL`, `MCTL_AUTH_ISSUER`, `SUPPORT_PUBLIC_URL`, `SUPPORT_ALLOWED_TENANTS`, `SUPPORT_EXECUTOR`, `SUPPORT_ENV`, `SUPPORT_ALLOW_FAKE_IN_PRODUCTION`, retention windows (7d / 7d / 30d) and the `server_thread` provider capability. — DoD: an unknown executor fails at startup. Production with `fake` and without the explicit flag fails at startup. Unit-tested.
- [ ] 2. Add `mctl_api.py` (depends on 1). It holds the `MctlApi` protocol, `HttpMctlApi` and `FakeMctlApi`, with `whoami`, `create_execution`, `mint_support_token` and `finish_execution`. Endpoint paths and bodies are the ones in design.md "mctl-api contract" (whoami, work item, execution with engine `a2a`, mint, finish, self-revoke). — DoD: every non-2xx or transport error raises `MctlApiDenied` or `MctlApiUnavailable`, never an empty result. The bearer is never logged.
- [ ] 3. Add `agent_card.py`. It builds the A2A 1.0 card with the `diagnose` skill, the HTTP+JSON interface, `streaming=false`, `pushNotifications=false` and an OAuth 2 `securitySchemes` entry from `MCTL_AUTH_ISSUER`. — DoD: the card validates against the SDK's `AgentCard` model and is served unauthenticated at `/.well-known/agent-card.json`.
- [ ] 4. Add the store schema and migrations (`store/schema.py`, `migrations/`, `python -m mctl_support.migrate`). Tables: `contexts`, `message_reservations`, `task_owners` and `transcripts`, plus the SDK SQL task table. — DoD: migrations are idempotent, so running twice is a no-op, and they are covered by a Postgres test.
- [ ] 5. Add `admission.py` (depends on 2). The middleware does bearer check, principal resolution, exactly-one-tenant selection (single membership or `metadata.tenant`) and the allowlist (tenant in the allowlist, or admin). The result is a `Caller` in the call context. — DoD: the responses are 401 for missing or rejected, 403 for non-member, ambiguous or non-allowlisted, and 503 for mctl-api errors. Nothing is written before admission passes.
- [ ] 6. Add `ownership.py` and `idempotency.py` (depends on 4, 5). `OwnedTaskStore` filters by owner. The context-ownership check returns an identical error for missing and foreign contexts. The `(principal, messageId)` reservation uses a uuid5 task id and a content digest. — DoD: foreign and missing tasks or contexts give identical responses. A duplicate send returns the existing task. A mismatched digest gives invalid params.
- [ ] 7. Add `executors/fake.py` and `executors/lifecycle.py` (depends on 2, 6). The fake scripts are `answer`, `slow`, `ask` and `fail`. The lifecycle wrapper creates the work item and the `a2a` WorkItemExecution, mints the token, and in a `finally` finishes the execution with the mapped terminal phase and self-revokes the token. — DoD: no model or mctl-api read in the fake. Execution or mint failure gives task `failed` with a reason. The token is in memory only.
- [ ] 8. Add `app.py` and `__main__.py` (depends on 3-7). They wire the SDK REST routes, the request handler, the SQL task store and `a2a.server.cluster` cancel. They also add `/healthz` and `/readyz` (readyz checks the DB) and start uvicorn. Add the LISTEN/NOTIFY cancel fallback only if the SDK cluster module does not deliver cancel to the owning replica. — DoD: `POST /message:send`, `GET /tasks/{id}` and `POST /tasks/{id}:cancel` work end-to-end against Postgres. `message:stream` and push endpoints return the unsupported-operation error.
- [ ] 9. Add `retention.py` (depends on 4). `run_retention(session, now)` plus a `RetentionLoop` with `pg_try_advisory_lock`, hourly. — DoD: with an injected clock it deletes exactly the expired rows, and only one replica runs a pass.
- [ ] 10. Add the `Dockerfile` (`python:3.12-slim`, `uv sync --locked --no-dev`, `USER 10001`, read-only-root friendly). Extend `.github/workflows/ci.yml` with a `postgres` service, and fail instead of skipping DB tests when `CI=true`. Update `README.md` with run and config documentation, and the S1a limitations (developer role required, namespace-wide egress). No GHCR push and no tag-triggered build in this repo: images are built by mctl-gitops `release-deploy.yaml`. — DoD: CI is green with the DB tests running, and the image runs as non-root with a read-only root FS.
- [ ] 11. Add the agent definition `agent/agent.yaml` for `mctl-support`. The implementer PR stops at the file and the written steps; the registration itself is an operator step after merge. Record the operator registration steps in the PR: `mctl_create_agent`, a published definition version, and a profile in mctl-gitops `agent-platform/execution-profiles/` if the binding requires one. — DoD: `mctl_get_agent mctl-support` returns the definition, and a WorkItemExecution can be created under it.
- [ ] 12. (Operator, after the implementer PR merges and mctl-api#824 is released; not part of the implementer PR.) Open an mctl-gitops PR for `platform-gitops/services/admins/mctl-support/values.yaml` (base-service), plus `catalog-info.yaml`, the Vault DB credentials (`teams/admins/mctl-support/database`) and the DNS for `support.mctl.ai` (depends on 10). The values set:
  - 2 replicas, with a RollingUpdate of maxSurge 1 and maxUnavailable 0;
  - `automountServiceAccountToken: false` and no ServiceAccount;
  - restricted security context with uid 10001;
  - `job-db-init` running migrations;
  - ingress on `support.mctl.ai` with TLS;
  - env `SUPPORT_EXECUTOR=fake`, `SUPPORT_ALLOW_FAKE_IN_PRODUCTION=true` and `SUPPORT_ALLOWED_TENANTS=namax66`.

  A comment in the values documents the egress limitation: the namespace-wide `allow-internet-egress` cannot be narrowed per pod. — DoD: the Argo app is Synced and Healthy with 2 ready pods, and `curl https://support.mctl.ai/.well-known/agent-card.json` returns the card.
- [ ] 13. (Operator, after 12.) Run the live probe (depends on 11, 12). Mint a `support` token as a `namax66` member through an S1a task and record the following. Attach the raw output to issue #2. — DoD: the output is attached and shows:
  - `GET /api/v1/status/namax66/news-factory` gives 200;
  - another tenant's service gives 403 `agent_scope_denied`;
  - the same two checks through MCP `mctl_get_service_status`.

## Tests
- [ ] T1. Admission, unauthenticated: no bearer and a rejected bearer each give 401. The test fails if the middleware is removed from the app factory, because an assertion checks that the protected route is not reachable without it.
- [ ] T2. Admission, non-member: a caller resolving to zero memberships, or naming a tenant they are not a member of, gets 403. With several memberships and no `metadata.tenant`, the caller gets 403.
- [ ] T3. Admission, allowlist: a member of a non-allowlisted tenant gets 403. An admin gets through. A member of `namax66` gets through. Each test fails when its check is deleted.
- [ ] T4. Admission fail-closed: when `FakeMctlApi.whoami` raises unavailable, the response is 503 and no rows are written.
- [ ] T5. Cross-principal: `GET /tasks/{id}` and `:cancel` for another principal's task return a response byte-identical (status and body) to the one for a random non-existent id.
- [ ] T6. Foreign `contextId`: `message:send` with another principal's context and with a random context gives identical errors.
- [ ] T7. Idempotency: the same `messageId` sent twice returns the same task id. `FakeMctlApi.create_execution` and `mint_support_token` are called once. Two concurrent sends on two app instances sharing one DB give one task. A different-content duplicate gives invalid params.
- [ ] T8. Fake executor: `answer` reaches `completed`; `ask` reaches `input-required`, and a follow-up reaches `completed`; `fail` reaches `failed`. The WorkItemExecution is finished with the matching terminal phase.
- [ ] T9. Cancel: a `slow` task cancelled mid-turn reaches `canceled`, its executor coroutine stops, and `finish_execution(..., canceled)` is called.
- [ ] T10. Retention with a frozen clock:
  - a transcript older than 7d is deleted and one younger is kept;
  - a context inactive for over 7d is deleted and an active one is kept;
  - task metadata older than 30d is deleted and younger metadata is kept;
  - two concurrent passes do not both run (advisory lock).
- [ ] T11. Two replicas: the S-1 gate re-run on the real code. Two uvicorn processes share one Postgres. A task is sent to replica A, then read, continued and cancelled through replica B.
- [ ] T12. Agent card: there is one skill `diagnose`, an OAuth 2 security scheme, and streaming and push are false.
- [ ] T13. Secrets hygiene: captured logs and every DB row contain neither the bearer nor the run token.
- [ ] T14. The existing `tests/test_stack.py` stays green; the pins are unchanged.

## Rollback
- Service: revert the mctl-gitops PR, or set `replicaCount: 0` in `services/admins/mctl-support/values.yaml`. Nothing else depends on mctl-support yet, so removal has no knock-on effects. The Argo app can be deleted to free the pod and Service quota.
- Data: the `admins-mctl-support` database holds only S1a pilot tasks. It can be dropped, or left for retention to empty.
- Tokens: the in-flight run tokens are bound to WorkItemExecutions. Finishing (or letting expire) the open `we_...` executions revokes them. To stop all minting, disable the `mctl-support` agent definition version in the registry (`mctl_set_agent_version_lifecycle`, disabled).
- Code: revert the merge commit in mctl-support. The bootstrap state (`tests/test_stack.py` only) is the known-good baseline.
