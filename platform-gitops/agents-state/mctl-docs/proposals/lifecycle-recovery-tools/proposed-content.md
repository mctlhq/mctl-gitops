# Proposed content: lifecycle-recovery-tools

> **Source:** mctl-api@e7ce245, mctl-api@f93d0fd, mctl-api@cacd7e3
> **Depends on:** `proposals/lifecycle-ownership/` landing first (see design.md).
> Diffs below are against that proposal's own `proposed-content.md` output.

---

## Block 1

> **Apply to:** `mctl-docs/docs/platform/lifecycle-ownership.md` (UPDATE, once created)
> **Source:** mctl-api@cacd7e3, mctl-api@f93d0fd, mctl-api@e7ce245

**Before** (the tail of `proposals/lifecycle-ownership/proposed-content.md` Block 1):

```markdown
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

**After:**

```markdown
## Recovery

Reading ownership is not enough to unblock a stuck row — a human operator
needs a way to act, safely, on what the status vocabulary says. Four named
transitions exist for exactly that, each licensed by one specific derived
status:

| Status | Action | What it does |
|---|---|---|
| `dead` | `mctl_fence_lifecycle_claim` | Releases the claim with **no successor** — the row becomes `released` so an ordinary Acquire can take it. The fencing epoch is incremented by the database; the fenced owner stays named on the row for forensics. |
| `stuck` | `mctl_request_lifecycle_handoff` | Starts a handoff off the alive-but-stuck owner toward a named `to_owner`. The outgoing owner is **not removed** — the row stays owned until `to_owner` completes the handoff through its own normal path. The fencing epoch is unchanged. |
| `handoff-stalled` | `mctl_retry_lifecycle_handoff` | Re-arms the handoff's clock for the **same** target. Owner, target, state, and epoch are all unchanged — this does not retarget the handoff. |
| any | `mctl_request_lifecycle_reconcile` | Appends a reconcile-requested event. Mutates **no** ownership column — this is a request for attention, not a claim on the row, so no licensing condition is required. |

Using the wrong action for the current status is refused: fencing a merely
`stuck` (not `dead`) owner returns `409`, and requesting a handoff on an
owner that is `healthy`, already `dead`, or already `handing-off` is
likewise refused with `409` and a hint toward the right action instead
(a dead claim wants `mctl_fence_lifecycle_claim`; an already-handing-off row
wants `mctl_retry_lifecycle_handoff`, not a second handoff layered on top).

### The precondition contract

Every one of the four mutating actions shares the same fail-closed
precondition shape: `expected_owner_type`, `expected_owner_id`,
`expected_epoch`, `expected_version`, and an optional
`expected_last_seen_at` must all match what the store currently holds, or
the call is refused with `412` naming what moved — **and nothing changes**.
There is no override or `force_owner` parameter; the only way in is to
match the current state exactly.

**Always call `mctl_inspect_lifecycle_conflict` first.** It is the
evidence step: the stored row, the derived view (status, `held`,
`dead`/`stuck`/`handoff-stalled` with the bounds the status was measured
against), the legacy DevLoopWorkflow answer, the divergence class between
the two, recent transitions, and the exact precondition values a follow-up
recovery call must send verbatim. If the legacy DevLoopWorkflow answer is
unobtainable, it reports "unavailable" with a reason — **never** "no
DevLoop": an absent answer and a negative one mean different things to a
caller deciding whether a takeover is safe.

**None of these five actions grants GitHub merge or approval authority.**
They change who the lifecycle store says is responsible for an entity
phase — never what that actor may do with a repository.

`mctl_fence_lifecycle_claim` and `mctl_request_lifecycle_handoff` are
**destructive** and require `confirm="yes"` — only send it after showing
the user what will happen and getting explicit agreement.
`mctl_retry_lifecycle_handoff` and `mctl_request_lifecycle_reconcile` are
idempotent, non-destructive mutations: repeating either while the
precondition still matches is safe to retry.

## Where to find it

- REST API — see [Lifecycle Ownership endpoints](/api/#lifecycle-ownership)
  on the REST API reference.
- MCP tools — see [Lifecycle Ownership](/mcp/tools-reference#lifecycle-ownership)
  on the Tools Reference.

Both surfaces are **admin-only**. The write endpoints
(`acquire`/`progress`/`handoff`/`release`/`terminal`) are intended for
internal platform actors — the DevLoop workflow engine, the shepherd, and
the reconciler — not for manual, human-driven calls. The recovery actions
above are the exception: they exist specifically for a human operator.
```

---

## Block 2

> **Apply to:** `mctl-docs/docs/api/index.md` (UPDATE, once the base `## Lifecycle Ownership` section exists)
> **Source:** mctl-api@f93d0fd

**Before** (the tail of the base proposal's `## Lifecycle Ownership` section, i.e. right before its `### Write endpoints` sub-heading):

```markdown
### `GET /api/v1/lifecycle/events`

Read the transition history for one entity/phase (acquire, progress,
handoff, release, terminal events).
```

**After** (insert a new subsection right after `GET /api/v1/lifecycle/events` and before `### Write endpoints`):

```markdown
### `GET /api/v1/lifecycle/events`

Read the transition history for one entity/phase (acquire, progress,
handoff, release, terminal events).

### Recovery endpoints

Human-operator recovery actions. See
[Recovery](/platform/lifecycle-ownership#recovery) for which action applies
to which derived status. **Admin access required for all five.**

### `GET /api/v1/lifecycle/ownership/conflict`

Read the conflict evidence needed before calling any recovery mutation
below: the stored row, the derived view, the legacy DevLoopWorkflow answer,
divergence, recent events, and the exact precondition values to send.

**Parameters**

| Name | In | Required | Description |
|------|----|----------|-------------|
| `kind` | query | yes | Entity kind |
| `id` | query | yes | Entity id |
| `phase` | query | yes | Lifecycle phase |

The four mutating endpoints below (`recovery/reconcile`, `recovery/fence`,
`recovery/handoff/request`, `recovery/handoff/retry`) share one request
body shape:

```json
{
  "kind": "pull-request",
  "id": "mctlhq/mctl-web#42",
  "phase": "review-remediation",
  "expected_owner_type": "devloop-workflow",
  "expected_owner_id": "dev-loop-abc12",
  "expected_epoch": 1,
  "expected_version": "",
  "expected_last_seen_at": "2026-09-19T10:00:00Z",
  "reason": "owner has not progressed in 8 hours"
}
```

`expected_epoch` is a JSON number, not a string. `expected_version: ""`
means "match an unset version," not "no opinion." `expected_last_seen_at`
is optional. `POST .../recovery/handoff/request` additionally requires
`to_owner_type` and `to_owner_id`.

| Status | Description |
|--------|-------------|
| `200` | Evidence read |
| `400` | Missing `kind`, `id`, or `phase` |
| `404` | No ownership record for this entity/phase |
| `503` | Lifecycle store not configured / unreachable |

### `POST /api/v1/lifecycle/ownership/recovery/reconcile`

Append a reconcile-requested event. Mutates no ownership column — no
licensing condition required, but the shared precondition still fails
closed.

### `POST /api/v1/lifecycle/ownership/recovery/fence`

Release a claim the server re-derives as `dead`, installing no successor.

### `POST /api/v1/lifecycle/ownership/recovery/handoff/request`

Start a handoff off a claim the server re-derives as `stuck`, toward
`to_owner_type`/`to_owner_id`. Requires those two additional fields.

### `POST /api/v1/lifecycle/ownership/recovery/handoff/retry`

Re-arm the clock of a handoff the server re-derives as `handoff-stalled`,
for the same target.

**Status codes shared by all four mutations**

| Status | Description |
|--------|-------------|
| `200` | Transition applied |
| `400` | Missing a required precondition field (named in the error) |
| `403` | Caller is not an admin, or no audit log is configured (a recovery mutation must not proceed unaudited) |
| `409` | The owner does not currently have the status this action requires (e.g. fencing a `stuck`, not `dead`, owner) — the error names the right action instead |
| `412` | A precondition value did not match what the store currently holds — nothing changed; call `.../conflict` again for current values |
| `503` | Lifecycle store not configured / unreachable |

### Write endpoints
```

---

## Block 3

> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE, once the base `## Lifecycle Ownership` section exists)
> **Source:** mctl-api@e7ce245

**Before** (the tail of the base proposal's `## Lifecycle Ownership` section, i.e. its `mctl_get_lifecycle_ownership` description ending in):

```markdown
**A `503` from this tool means the store didn't answer — it means
`unknown`, never `unowned`.** Only a `dead` status licenses another actor to
take over; `stuck` means alive but making no progress, which calls for a
human, not a second automated actor that would be equally stuck.
```

**After** (append five new tool rows to the section's table, plus per-tool subsections):

```markdown
**A `503` from this tool means the store didn't answer — it means
`unknown`, never `unowned`.** Only a `dead` status licenses another actor to
take over; `stuck` means alive but making no progress, which calls for a
human, not a second automated actor that would be equally stuck.

### Recovery tools

> See [Recovery](/platform/lifecycle-ownership#recovery) for which action
> applies to which derived status. **Always call
> `mctl_inspect_lifecycle_conflict` first** for the exact precondition
> values a mutating call needs.

| Tool | Description | Type |
|------|-------------|------|
| `mctl_inspect_lifecycle_conflict` | Read evidence for a recovery decision: stored row, derived status, legacy DevLoopWorkflow answer, divergence, recent events, exact precondition values | Read |
| `mctl_request_lifecycle_reconcile` | Append a reconcile-requested event. Mutates no ownership column | Write (idempotent) |
| `mctl_fence_lifecycle_claim` | Release a `dead` claim with no successor | **Destructive** — requires `confirm="yes"` |
| `mctl_request_lifecycle_handoff` | Start a handoff off a `stuck` owner toward a named target | **Destructive** — requires `confirm="yes"` |
| `mctl_retry_lifecycle_handoff` | Re-arm a `handoff-stalled` handoff's clock for the same target | Write (idempotent) |

All five share `kind`, `id`, `phase` (all required), and — except the
read tool — the precondition set `expected_owner_type`, `expected_owner_id`,
`expected_epoch`, `expected_version` (all required; send `""` for an unset
version), optional `expected_last_seen_at`, and a required `reason` string
recorded on the audit entry. `mctl_request_lifecycle_handoff` additionally
requires `to_owner_type` and `to_owner_id`. None takes an `operation` or
`mode` argument that could pick a different transition — the transition
performed is always the tool name.

**None of the five confers GitHub merge or approval authority.** All are
admin-only.
```

---

## Block 4

> **Apply to:** `mctl-docs/docs/mcp/examples.md` (UPDATE, once the base example exists)
> **Source:** mctl-api@e7ce245

**Before** (the tail of the base proposal's `## Lifecycle Ownership` example):

```markdown
The first two questions call `mctl_get_lifecycle_ownership` with
`pr_url="https://github.com/mctlhq/mctl-web/pull/42"` and
`phase="review-remediation"`; the third calls it with no `id`/`pr_url` and
`state="active"` to list. A `dead` status in the response is the only one
that means it's safe for another actor to take the phase over — `stuck`
means it needs a human, not automation, to unstick it. See
[Lifecycle Ownership](/platform/lifecycle-ownership) for the full status
vocabulary.
```

**After:**

```markdown
The first two questions call `mctl_get_lifecycle_ownership` with
`pr_url="https://github.com/mctlhq/mctl-web/pull/42"` and
`phase="review-remediation"`; the third calls it with no `id`/`pr_url` and
`state="active"` to list. A `dead` status in the response is the only one
that means it's safe for another actor to take the phase over — `stuck`
means it needs a human, not automation, to unstick it. See
[Lifecycle Ownership](/platform/lifecycle-ownership) for the full status
vocabulary.

```
"Why is mctlhq/mctl-web#42 stuck in review-remediation? Show me the conflict evidence"
"That owner is dead — fence the claim"
"This owner is alive but stuck — hand it off to pr-steward/on-call-1"
```

The first question calls `mctl_inspect_lifecycle_conflict`, which returns
the derived status plus the exact `expected_owner_type`/`expected_owner_id`/
`expected_epoch`/`expected_version` to use next. The second calls
`mctl_fence_lifecycle_claim` with those values and `confirm="yes"` — only
after confirming with the user what will happen. The third calls
`mctl_request_lifecycle_handoff` with `to_owner_type="pr-steward"`,
`to_owner_id="on-call-1"`, and `confirm="yes"`; the outgoing owner stays on
the row until `pr-steward/on-call-1` completes the handoff. See
[Recovery](/platform/lifecycle-ownership#recovery) for the full action-to-status mapping.
```

---
