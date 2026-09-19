# Proposed content: lifecycle-ownership

> **Source:** mctl-api@5a1da2d, mctl-api@e7aee63, mctl-api@1064b2c, mctl-api@783a238

This proposal touches five locations. Each block below states its own
**Apply to** target and mode.

---

## Block 1

> **Apply to:** `mctl-docs/docs/platform/lifecycle-ownership.md` (CREATE)
> **Source:** mctl-api@5a1da2d, mctl-api@e7aee63, mctl-api@1064b2c

```markdown
# Lifecycle Ownership

The lifecycle ownership store answers one question: **who is currently
responsible for advancing a given entity through a given phase of its
lifecycle** — a pull request through review remediation, or an
accepted proposal through implementation.

It is a small, deliberately narrow subsystem. It does not track *what* an
entity is (GitHub and `mctl-gitops` remain authoritative for that); it
tracks only *who may act on it right now*, and whether that actor is still
alive.

## Why it exists

Before this store, "who owns this PR/proposal right now" was assembled from
several different signals with no single source of truth, and the one
load-bearing check failed open on error — meaning "nobody owns this" and "I
couldn't find out" produced the same, unsafe answer. The ownership store
replaces that with one durable record per `(entity, phase)`, backed by
Postgres, with exclusivity enforced by the database itself rather than by an
in-process lock.

## Entities and phases

Ownership is scoped to a `(kind, phase)` pair. As of this writing, two pairs
are legal:

| Kind | Phase | Held by |
|---|---|---|
| `pull-request` | `review-remediation` | The actor driving a pull request from blocking review findings to a terminal state |
| `devloop-proposal` | `implement` | The actor turning an accepted proposal into a pull request |

An unknown `(kind, phase)` pair is rejected at the API boundary (`400`)
rather than silently stored.

## Owners

An owner is identified by a `type` and an `id` — for example
`devloop-workflow` / `dev-loop-<workflow-id>`, or `shepherd` / `cron`. Owner
**types** you may see: `devloop-workflow`, `shepherd`, `pr-steward`,
`reconciler`, `human-codeowner`.

Ownership says who is responsible. It does **not** grant GitHub merge or
approval authority — those remain governed by normal GitHub permissions and
branch protection.

## Reading the state

Every ownership record stores one of four states:

- `active` — a live owner is driving this phase
- `handing-off` — ownership is mid-transfer to a named incoming owner; the
  row stays owned throughout (a handoff is never "unowned")
- `released` — the previous owner stepped back; the work is not finished
- `terminal` — the phase is finished; nothing should pick it up

Staleness is **not** stored — it's derived on every read by comparing
`last_progress_at` against a per-`(kind, phase)` bound:

| Kind / phase | Staleness bound | Why |
|---|---|---|
| `pull-request` / `review-remediation` | 6 hours | 4x the ~4h in-loop shepherd sweep cadence, so one missed tick doesn't make a healthy owner look stale |
| `devloop-proposal` / `implement` | 130 minutes | Matches the lease the implementer already writes |

"Progress" means an *effected change*, not a heartbeat — a tick that polled
and found nothing must not record progress, or an owner could prove
liveness forever while achieving nothing.

## The status vocabulary

Callers of the MCP tool or the REST read endpoints get a **derived** status
on top of the stored state. It is a closed vocabulary — read it before
acting on it:

| Status | Meaning | Safe to take over? |
|---|---|---|
| `healthy` | Active, within its staleness bound | No |
| `stuck` | Active, alive, but making no progress | No — this needs a human, not a second automated actor that will be equally stuck |
| `dead` | Active or handing-off, past its staleness/liveness bound | **Yes** — this is the only status that licenses another actor to take over (ADR-010 §4) |
| `handing-off` | Mid-transfer, within bound | No |
| `handoff-stalled` | Mid-transfer, past bound | The row is dead *and* recoverable — read `held` (below), not the status string, to decide "does this record currently withhold the entity" |
| `released` | Owner stepped back voluntarily | Work remains, no active owner |
| `terminal` | Phase finished | Nothing should pick this up |
| `unknown` | The store could not answer | **Never** treat this as "unowned" |

`held` is carried separately from `status` for exactly the `handoff-stalled`
case above: a handing-off row past its liveness bound is simultaneously
"dead" and "not held" — reading takeover permission off the status string
alone gets that backwards.

## A `503` is not a `404`

Every read path in this subsystem distinguishes "the store is unreachable"
(`503`) from "there is no record for this entity/phase" (`404`, or absence
from a list). A caller that cannot tell these apart will eventually treat an
outage as permission to act — which is exactly the failure mode this store
exists to close off. **A `503` here always means "unknown," never
"unowned."**

## Where to find it

- REST API — see [Lifecycle Ownership endpoints](/api/#lifecycle-ownership)
  on the REST API reference.
- MCP tool — see [`mctl_get_lifecycle_ownership`](/mcp/tools-reference#lifecycle-ownership)
  on the Tools Reference.

Both surfaces are **admin-only**. The write endpoints
(`acquire`/`progress`/`handoff`/`release`/`terminal`) are intended for
internal platform actors — the DevLoop workflow engine, the shepherd, and
the reconciler — not for manual, human-driven calls.
```

---

## Block 2

> **Apply to:** `mctl-docs/docs/api/index.md` (UPDATE)
> **Source:** mctl-api@e7aee63, mctl-api@783a238

Insert the following new section between the existing `## Operations`
section and the existing `## MCP Endpoint` section (i.e. right before the
`---` / `## MCP Endpoint` heading at the end of the file).

**Before** (excerpt, end of file):

```markdown
| Status | Description |
|--------|-------------|
| `200` | Workflow submitted |
| `400` | Invalid parameters |
| `403` | Access denied to this tenant |
| `404` | Operation not found |

---

## MCP Endpoint
```

**After:**

```markdown
| Status | Description |
|--------|-------------|
| `200` | Workflow submitted |
| `400` | Invalid parameters |
| `403` | Access denied to this tenant |
| `404` | Operation not found |

---

## Lifecycle Ownership

Read-only reference for the lifecycle ownership store. See
[Lifecycle Ownership](/platform/lifecycle-ownership) for what an entity,
phase, owner, and status mean before using these endpoints.

**Admin access required for every endpoint below.** A caller that is
authenticated but not an admin gets `403`. If the store itself is not
configured (no `LIFECYCLE_DB_URL` / `AUDIT_DB_URL`), every endpoint returns
`503` — never `404` and never an empty result, because "the store didn't
answer" and "nothing owns this" must not be indistinguishable to a caller
deciding whether it may act.

### `GET /api/v1/lifecycle/ownership`

List ownership records, optionally filtered.

**Parameters**

| Name | In | Required | Description |
|------|----|----------|-------------|
| `kind` | query | no | Filter by entity kind (e.g. `pull-request`) |
| `phase` | query | no | Filter by phase (e.g. `review-remediation`) |
| `state` | query | no | Filter by stored state (`active`, `handing-off`, `released`, `terminal`) |
| `owner` | query | no | Filter by owner id |
| `limit` | query | no | Maximum records to return |

> `id` is **not** accepted here. Passing `?id=` on this endpoint returns
> `400` (removed in mctl-api, deprecation window closed 2026-09-14) — use
> `GET /api/v1/lifecycle/ownership/record` to read a single entity.

**Response** `200`
```json
{
  "ownership": [
    {
      "entity": { "kind": "pull-request", "id": "mctlhq/mctl-web#42" },
      "phase": "review-remediation",
      "owner": { "type": "devloop-workflow", "id": "dev-loop-abc12" },
      "epoch": 1,
      "state": "active",
      "acquired_at": "2026-09-14T10:00:00Z",
      "last_progress_at": "2026-09-14T11:30:00Z",
      "stale": false,
      "healthy": true,
      "derived": { "status": "healthy", "held": true, "dead": false, "bounds_known": true }
    }
  ],
  "count": 1
}
```

| Status | Description |
|--------|-------------|
| `200` | List of ownership records |
| `400` | `?id` was passed on this endpoint — use `/record` instead |
| `503` | Lifecycle store not configured / unreachable |

### `GET /api/v1/lifecycle/ownership/record`

Read one ownership record.

**Parameters**

| Name | In | Required | Description |
|------|----|----------|-------------|
| `kind` | query | yes | Entity kind |
| `id` | query | yes | Entity id (e.g. `mctlhq/mctl-web#42`) |
| `phase` | query | yes | Lifecycle phase |

| Status | Description |
|--------|-------------|
| `200` | Ownership record (same shape as above, single object) |
| `400` | Missing `kind`, `id`, or `phase` |
| `404` | No ownership record for this entity/phase |
| `503` | Lifecycle store not configured / unreachable |

### `GET /api/v1/lifecycle/ownership/batch`

Read many entity ids of one `(kind, phase)` in a single round trip
(used by the shepherd's sweep).

**Parameters**

| Name | In | Required | Description |
|------|----|----------|-------------|
| `kind` | query | yes | Entity kind |
| `phase` | query | yes | Lifecycle phase |
| `id` | query (repeatable) | yes | One or more entity ids; at most 500 per call |

**Response** `200` — a map keyed by entity id; entities with no record are
**absent** from the map rather than present with a `null` value.

### `GET /api/v1/lifecycle/events`

Read the transition history for one entity/phase (acquire, progress,
handoff, release, terminal events).

**Parameters**

| Name | In | Required | Description |
|------|----|----------|-------------|
| `kind` | query | yes | Entity kind |
| `id` | query | yes | Entity id |
| `phase` | query | yes | Lifecycle phase |
| `limit` | query | no | Maximum events to return |

### Write endpoints

The following endpoints exist but are intended for internal platform
actors (the DevLoop workflow engine, the shepherd, the reconciler) rather
than manual calls. They share a `120 requests/minute` rate-limit group,
separate from the `20/min` group used by `/operations/{name}/execute`.

| Method & path | Purpose |
|---|---|
| `POST /api/v1/lifecycle/ownership/acquire` | Acquire ownership of an entity/phase |
| `POST /api/v1/lifecycle/ownership/progress` | Record that the current owner effected a change (requires `evidence`) |
| `POST /api/v1/lifecycle/ownership/handoff/start` | Start a handoff to a named incoming owner |
| `POST /api/v1/lifecycle/ownership/handoff/complete` | Called by the incoming owner to complete a handoff |
| `POST /api/v1/lifecycle/ownership/release` | Release ownership; the work is not finished |
| `POST /api/v1/lifecycle/ownership/terminal` | Mark the phase finished; nothing should pick it up |

Status codes on the write endpoints carry specific meaning: `409` means the
entity/phase is owned by another actor (the current owner is in the
response body); `412` means the caller's epoch precondition failed —
ownership moved since the caller last read it, so it should re-read rather
than retry; `400` means an unknown `(kind, phase)` pair.

<!-- <TODO: confirm exact JSON request body shape for each write endpoint
     (field names beyond kind/id/phase/owner_type/owner_id/epoch) with the
     author of e7aee63 before publishing, since these are internal-actor-only
     and the request/response examples above focus on the read endpoints
     human/API readers actually call.> -->

---
```

---

## Block 3

> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE)
> **Source:** mctl-api@1064b2c

Insert a new `## Lifecycle Ownership` section. A natural placement is
directly after the existing `## Agent Registry` section and before
`## Platform Skills` (both are admin-only, narrow-audience sections, so
grouping them together matches the page's existing organization).

**Before** (excerpt):

```markdown
`mctl_list_agent_executions` and `mctl_list_recent_agent_runs` answer different
questions. The former reads persisted records that outlive the Argo workflow
object; the latter reflects live and recently-completed Argo state and expires
with that object's TTL.

## Platform Skills
```

**After:**

```markdown
`mctl_list_agent_executions` and `mctl_list_recent_agent_runs` answer different
questions. The former reads persisted records that outlive the Argo workflow
object; the latter reflects live and recently-completed Argo state and expires
with that object's TTL.

## Lifecycle Ownership

> **Admin-only.** See [Lifecycle Ownership](/platform/lifecycle-ownership)
> for the concepts (entity, phase, owner, status vocabulary) before using
> this tool.

| Tool | Description | Type |
|------|-------------|------|
| `mctl_get_lifecycle_ownership` | Read who owns advancing an entity (pull request / proposal) through a lifecycle phase (`implement`, `review-remediation`), whether that owner is alive, and how that compares to the legacy DevLoopWorkflow check | Read |

### `mctl_get_lifecycle_ownership`

Two modes, one response shape. Give `id` (or `pr_url`) together with `kind`
and `phase` to read **one** entity; give none of those to **list** what the
store holds, optionally filtered by `state` and `owner_type`. The response's
`records` array is always present — length 0 or 1 in single-entity mode.

**Parameters**

| Name | Required | Description |
|---|---|---|
| `kind` | with `id`/`pr_url` | Entity kind, e.g. `pull-request` or `devloop-proposal` |
| `phase` | with `id`/`pr_url` | Lifecycle phase, e.g. `review-remediation` |
| `id` | no | Entity id, e.g. `mctlhq/mctl-web#42`. Provide this or `pr_url`, not both. Omit both to list |
| `pr_url` | no | Full pull request URL — the entity id is derived from it. Provide this or `id`, not both |
| `state` | no | List filter: stored state (`active`, `handing-off`, `released`, `terminal`). Ignored in single-entity mode |
| `owner_type` | no | List filter: owner type (`shepherd`, `pr-steward`, `devloop-workflow`, etc). Ignored in single-entity mode |
| `limit` | no | List mode: maximum records to return |
| `include_events` | no | `"true"` to attach the transition history to each record. Defaults to off (one extra read per record) |
| `include_legacy` | no | `"false"` to skip the legacy DevLoopWorkflow liveness cross-check. Defaults to `"true"` |

**Response shape** — for each record: `ownership` (the stored row),
`derived` (status, `held`, `dead`, and the bounds the status was measured
against), `legacy` (whether a live DevLoopWorkflow is driving the same
entity — always present, `available: false` with a reason if the probe
couldn't run rather than being absent), `divergence` (how the two compare),
and `events` when `include_events=true`.

**A `503` from this tool means the store didn't answer — it means
`unknown`, never `unowned`.** Only a `dead` status licenses another actor to
take over; `stuck` means alive but making no progress, which calls for a
human, not a second automated actor that would be equally stuck.
```

---

## Block 4

> **Apply to:** `mctl-docs/docs/mcp/examples.md` (UPDATE)
> **Source:** mctl-api@1064b2c

**Before** (excerpt, end of file):

```markdown
```
"Scale my-api to 3 replicas in staging and add the domain
api-staging.example.com to it"
```
```

**After:**

```markdown
```
"Scale my-api to 3 replicas in staging and add the domain
api-staging.example.com to it"
```

## Lifecycle Ownership

```
"Who owns the review-remediation phase for mctlhq/mctl-web#42?"
"Is that owner still alive, or is this PR stuck?"
"List every active review-remediation owner that looks stale"
```

The first two questions call `mctl_get_lifecycle_ownership` with
`pr_url="https://github.com/mctlhq/mctl-web/pull/42"` and
`phase="review-remediation"`; the third calls it with no `id`/`pr_url` and
`state="active"` to list. A `dead` status in the response is the only one
that means it's safe for another actor to take the phase over — `stuck`
means it needs a human, not automation, to unstick it. See
[Lifecycle Ownership](/platform/lifecycle-ownership) for the full status
vocabulary.
```

---

## Block 5

> **Apply to:** `mctl-docs/docs/platform/architecture.md` (UPDATE)
> **Source:** mctl-api@5a1da2d

**Before** (excerpt, `## Request Flow` → `### MCP Request` section header):

```markdown
## Request Flow

### MCP Request
```

**After:**

```markdown
## Request Flow

> `mctl-api` also holds the [lifecycle ownership](/platform/lifecycle-ownership)
> store — a durable record of which actor (a DevLoop workflow, the shepherd,
> or a human codeowner) is currently responsible for advancing a pull
> request or proposal through its next phase. It sits inside the control
> plane shown above but is omitted from the diagram for now, since the
> diagram is component-level rather than subsystem-level.

### MCP Request
```

---
