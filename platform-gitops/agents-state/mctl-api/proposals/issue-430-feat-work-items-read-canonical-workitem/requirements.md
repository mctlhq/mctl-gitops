# Read canonical WorkItem intents (GET /work-items/{id}/intents)

## Context

mctl-api already stores work-item intents: `work_item_intents` is created in
`internal/workitems/store.go` (schema block, line 59), written by
`Store.AppendIntent` and exposed as `POST /api/v1/work-items/{id}/intents`
(`Handlers.AppendWorkItemIntent`, `internal/api/handlers_work_items.go`). There
is no read path. The lifecycle event `intent_appended` carries only
`{"intent_id": <n>}` (deliberately: the event never copies the text), and an
execution request carries only an optional `intent_id`
(`executionRequestBody.IntentID`, `internal/api/handlers_execution_requests.go`).
The only existing read of an intent is the private helper `getIntent` used by
the idempotency replay path inside `AppendIntent`.

The consequence, recorded in mctl-agents#542 (owner decision 2026-09-30,
option 1): an execution platform that resumes a work item cannot resolve the
intent the resume was requested with, so a resumed execution's ContextSnapshot
C2 cannot be assembled from canonical state. The workaround under
consideration was to duplicate the resume intent into a GitHub comment purely
so context assembly could see it; that would make a surface-local artifact the
source of truth for something mctl-api already holds. This proposal adds the
missing read path — a list and a single-item read — with exactly the visibility
rules every other work-item read already has, and changes nothing else.

## User stories

- AS the execution platform I WANT to read the canonical intents of a work item
  SO THAT a resumed execution's ContextSnapshot is assembled from stored state
  rather than from a GitHub comment written only to be read back.
- AS the execution platform I WANT to resolve one `intent_id` (the one an
  execution request named) SO THAT I can put the requested intent into the
  context of the run I am about to start.
- AS a surface (Telegram, portal) relaying for its linked human I WANT to list
  the intents of a work item that human can see SO THAT I can show what was
  asked for without keeping my own copy.
- AS a platform operator I WANT intent reads to obey the same
  404-never-403 visibility rule as every other work-item read SO THAT the
  existence of another tenant's work is never disclosed.

## Acceptance criteria (EARS)

Availability and authentication

- IF `Options.WorkItems` is nil THEN THE SYSTEM SHALL answer both routes with
  503 and code `work_items_unavailable` (the existing `workItemsUser` path).
- IF the request carries no authenticated user THEN THE SYSTEM SHALL answer 401.

Visibility

- WHILE serving either route THE SYSTEM SHALL resolve `{id}` through the same
  `visibleWorkItem` helper used by `GetWorkItem`, `ListWorkItemExecutions`,
  `ListWorkItemEvents` and the snapshot reads.
- IF the work item does not exist, or exists in a tenant the caller has no
  access to, or is `private` and owned by another principal THEN THE SYSTEM
  SHALL answer 404 with code `work_item_not_found` and SHALL NOT answer 403.
- WHEN the caller is the platform service principal (`auth.NewServiceUser`,
  which is in `admins`) THE SYSTEM SHALL return the intents, as it already
  does for executions and snapshots.
- WHEN a surface principal calls either route with `X-MCTL-Surface-Actor` and a
  valid link THE SYSTEM SHALL run the read as the linked human, with that
  human's visibility and never admin (relay route, `surfacePrincipalGate`).
- IF a surface principal calls either route without a usable link THEN THE
  SYSTEM SHALL answer 403 exactly as it does on the other relay routes
  (`relay_required`, `link_not_found`, `link_revoked`, `link_expired`).

List — `GET /api/v1/work-items/{id}/intents`

- WHEN the route is called THE SYSTEM SHALL return the item's intents in
  ascending `id` order.
- WHEN `after_id` is given THE SYSTEM SHALL return only intents with
  `id > after_id`.
- WHEN `limit` is absent THE SYSTEM SHALL apply a default page size of 50.
- IF `limit` is not an integer in 1..100, or `after_id` is not a non-negative
  integer THEN THE SYSTEM SHALL answer 400 with code `invalid_request`.
- WHEN the store holds at least one intent of this item with `id` greater than
  the last id on the returned page THE SYSTEM SHALL report `truncated: true`;
  otherwise it SHALL report `truncated: false`.
- WHILE reporting `truncated: true` THE SYSTEM SHALL return exactly `limit`
  intents, so the caller can continue with `after_id` = the last returned `id`.
- WHEN the item has no intents (or none after `after_id`) THE SYSTEM SHALL
  return `intents: []` with `truncated: false`, never `null`.
- WHILE answering THE SYSTEM SHALL include `schema_version: "workitem/v1"` and
  the effective `limit`.

Get one — `GET /api/v1/work-items/{id}/intents/{intent_id}`

- WHEN `{intent_id}` names an intent of `{id}` THE SYSTEM SHALL return that
  intent.
- IF `{intent_id}` names an intent of a different work item, names no intent at
  all, or is not a number THEN THE SYSTEM SHALL answer 404 with code
  `intent_not_found` (the code `POST .../execution-requests` already returns
  for a cross-item `intent_id`), and SHALL NOT answer 400 or
  `work_item_not_found`.

Response content

- WHILE returning an intent THE SYSTEM SHALL return exactly the stored
  `workitems.Intent` fields — `id`, `work_item_id`, `actor_principal`,
  `surface`, `text`, `params`, `created_at` — and no derived content: no
  transcript, no authorization or approval state, no event history.
- IF the retention sweeper has nulled an intent's `text` (the column is
  nullable for exactly that reason) THEN THE SYSTEM SHALL return the row with
  `text` as the empty string rather than failing the read.

Read-only

- WHILE serving either route THE SYSTEM SHALL perform no write: no work-item
  event, no idempotency record, no state or `state_version` change.
- WHILE serving either route THE SYSTEM SHALL stay outside the 20/min write
  rate-limit group, in the same read block as the other work-item reads.
- WHILE auditing THE SYSTEM SHALL keep the existing behaviour of work-item
  reads (no audit entry), and SHALL under no circumstance log intent text.

Contract

- WHEN this ships THE SYSTEM SHALL document both routes in
  `internal/openapi/openapi.yaml` and in `docs/work-context-contract.md`
  (REST surface table, and the relay-route list if the routes are relay-eligible).

## Out of scope

- Any write path, schema change or migration. `work_item_intents` and
  `Store.AppendIntent` are untouched.
- Making intents authorization or approval state. They stay provenance and
  input; approvals remain `action_approval_requests` and the approval
  projection.
- Assembling ContextSnapshot C2 itself. That is mctl-agents#542's work; this
  issue only supplies the read it needs.
- A new MCP tool. The MCP tool count in `internal/mcp/server_test.go` must not
  change.
- Cursor/opaque pagination tokens, descending order, filtering by actor or
  surface, and full-text search over intent text.
- Redacting or purging intent text (the retention sweeper, #353).
- Changing the `intent_appended` event to carry text.

## Open questions

- "The route is relay-eligible like the other work-item reads": the current
  `surfaceRoutes` allowlist in `internal/api/handlers_surface_identity.go`
  admits `GET /work-items/{id}` and the two execution-request reads, but NOT
  `GET /work-items/{id}/executions`, `/events` or `/snapshots`. So "the other
  work-item reads" is not a single existing rule. Taken as written in the
  issue: both new routes are added to `surfaceRoutes` with `relay: true`.
  A reviewer who wants surfaces kept off intent text should say so and the two
  allowlist entries are dropped — nothing else in the design changes.
- Page-size wording: the issue says "default 50, maximum 100" but not whether
  an over-maximum `limit` is clamped or refused. `ListWorkItems` refuses
  (400 `invalid_request`, "limit must be an integer from 1 to 500") while
  `workitems.Store.List` clamps. Taken as: the handler refuses (explicit to the
  caller) and the store clamps as defence in depth.
- Whether `limit` should also appear in the response. The issue names only
  `truncated`; `internal/evidence/read.go`'s `ListResult` carries both. Taken
  as: include `limit`, since a caller that omitted it cannot otherwise know the
  page size it got.
