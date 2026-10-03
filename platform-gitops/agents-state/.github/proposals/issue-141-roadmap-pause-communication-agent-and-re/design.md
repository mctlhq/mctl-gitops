# Design: issue-141-roadmap-pause-communication-agent-and-re

## Current state

### The control plane

`roadmap/` in `mctlhq/.github` is the Git source of truth for roadmap desired state
(`roadmap/README.md`). One `EpicDefinition` per file under `roadmap/epics/`, validated
offline in three layers by `roadmap/scripts/validate.py` (JSON Schema, per-manifest
semantics, corpus invariants) and enforced by `.github/workflows/roadmap-validate.yml`.

Derivation is strictly layered and each layer is pure:

- `reconcile.py` — desired manifest vs a GET-only `GitHubGraphSnapshot`, emits `RoadmapDiff`.
- `completion.py` — per work item, is the bound issue delivered; `allRequired` roll-up.
- `health.py` — diff plus completion into `RoadmapHealth`.
- `ready.py` — joins authored `dependsOn`/`externalDependsOn` with
  `completion.item_status` into a `RoadmapReadySet`.
- `plan.py` — pure diff-to-operations; `apply.py` — the only writer, through
  `github_apply.py`'s four-endpoint allow-list.
- `publish.py` — one commit to the orphan `roadmap-state` branch holding
  `snapshot.json`, `ready-set.json`, `health.json`, `publication.json`.

mctl-api consumes only the published files; it never runs the evaluator
(`roadmap/README.md`, "Publication").

### `spec.lifecycle` already exists

`roadmap/schemas/epic-definition.schema.json` line 33 makes `lifecycle` **required**,
and line 37 declares the enum:

```json
"lifecycle": {"enum": ["proposed", "active", "paused", "completed", "archived"]}
```

`roadmap/epics/edge-ai-android.yaml:14` already carries `lifecycle: paused`. Across the
corpus: 11 `active`, 5 `completed`, 1 `paused`.

The issue's premise — "the current v1alpha1 EpicDefinition deliberately has no authored
`status` field" — is correct and must be respected: `status` is rejected by
`additionalProperties: false`, and `roadmap/README.md` names authored `status` as
precisely the kind of field the schema exists to reject. But `lifecycle` is the
authored field that does carry this meaning, and it is already enumerated for `paused`.
**No schema extension is needed to represent an epic-level pause.**

### Where `lifecycle` is honoured, and where it is not

Honoured: `publish.py::_epic_identity` (lines 263-279) copies `spec.lifecycle` verbatim
into `publication.json` `epics[].lifecycle`, with a docstring that says exactly why —
so a consumer asked for "every active epic" does not have to re-read the manifests.
`roadmap/tests/test_publish.py:171-215` pins this by flipping one manifest to `paused`
and asserting the copied value.

Confirmed empirically against the live publication (state revision
`39ce89a83101eca332dcd385689b064f5c3fa861`, observation `capturedAt`
2026-09-26T22:57:44Z): `mctl_get_ready_work_items` with no epic returned twelve epics,
every one `lifecycle: active`. `edge-ai-android` (paused) and all five `completed`
epics were absent. `mctl_plan_epic_wave` documents a hard `epic_paused` refusal with
no override.

**Not honoured:** `ready.py`, `health.py` and `completion.py` never read
`spec.lifecycle` — a grep over `roadmap/scripts/` finds it only in `publish.py`.
`roadmap/schemas/roadmap-ready-set.schema.json` `$defs.epic` is
`additionalProperties: false`, `required: ["name", "manifest"]`, with only `name`,
`issue` and `manifest` — no lifecycle. So the published `ready-set.json` lists `ready`
items for a paused epic, and a consumer reading that file alone, without joining
`publication.json`, would pick them up. This was verified by computation, not assumed
(see "Platform impact").

### The two epics today

`roadmap/epics/communication-agent.yaml` (root `mctl-telegram#518`, `lifecycle: active`):
six work items, two required (`quota-domain` #334, `c2-safety-gate` #347 which depends
on it), four optional (`temporal-approvals` #339 with children #340/#341, and
`channels-preview` #350). Live: health `healthy`, completion `incomplete`,
`blocking: [c2-safety-gate, quota-domain]`, ready set `[approval-workflow,
channels-preview, quota-domain, temporal-approvals]`, one informational
`HierarchyUnexpectedChild` for #305 under #518.

`roadmap/epics/client-lifecycle.yaml` (root `mctlhq/.github#22`, `lifecycle: active`):
seven work items, all required. Live: health `healthy`, zero drift, completion
`incomplete` (4 of 7 complete), ready set `[lookup-deployment]`, three informational
`HierarchyUnexpectedChild` entries (#620/#621/#622 under #438).

The manifest's own comment on `lookup-deployment` already records the split: "The
mctl-telegram half of #400 is delivered (#511 added the admin:users lookup tier, #575
documented it). What remains is the deployment half in mctl-gitops#1182."

`mctl-gitops#1182` (OPEN) is titled "chore(admins/openclaw): connect the mctl-telegram
lookup MCP server (TG_LOGIN_LOOKUP_ADMINS, Vault refresh token, token-refresh
sidecar)". Its five ordered scope steps are: set `TG_LOGIN_LOOKUP_ADMINS` in
`platform-gitops/services/labs/mctl-telegram/values.yaml`; sign a dedicated lookup
account in once via the Login Widget; store that account's OAuth refresh token in Vault
beside the `admins/openclaw` secrets; add a third `mcp.servers` entry plus a
token-refresh sidecar in `platform-gitops/services/admins/openclaw/values.yaml`; verify
live from `mctl_admins`.

`mctl-telegram#400` (OPEN, `stateReason: REOPENED`) is the originating bug — the
`admins/openclaw` agent could not answer "who is this client?". Its "Status 2026-09-11"
section states: "The half inside this repository is delivered: #511 ... and #575
(runbook). Only the deployment half remains; it is tracked in mctlhq/mctl-gitops#1182
and is blocked on the dedicated lookup Telegram account (operator)."

`mctl-telegram#679` (OPEN) binds `onboarding-integration` and currently depends on
`operator-identity-lookup` (#400), `safe-broadcast` (#439) and `product-update-feed`
(#440).

### `mctl-telegram#440` is not trustworthy evidence

`#440` is CLOSED with `stateReason: COMPLETED`, `closedAt` 2026-09-26T06:52:09Z, so
`completion.py` records it `complete` / `closed`. The closing reference is
`mctl-telegram#682` — "chore(main): release 0.69.0", author `app/mctl-agents`, head
branch `release-please--branches--main--components--mctl-telegram`, merged
2026-09-26T06:52:08Z. It is a release-please release pull request, not an
implementation pull request.

The owner's own last comment on #440, at 2026-09-26T01:56:17Z — under five hours
earlier — is a nine-row acceptance matrix that concludes:

> **Not closing #440:** 7 is missing, 6 and 9 lack end-to-end evidence, and 1 needs its
> deviation confirmed.

Criterion 7 ("the approved update can be passed unchanged/versioned to the safe
broadcast prepare step") is marked `❌ ↪ #683`; `mctl-telegram#683` is OPEN. Criteria 6
and 9 are `🟡 implemented, lacking evidence`; criterion 1 is `🟡` with an unconfirmed
deviation. The earlier comment on the same issue ends "Leaving #440 open."

So the epic's observed `complete` for `product-update-feed` is a release-automation
artifact that contradicts the only recorded human acceptance decision.

## Proposed solution

Two independent manifest changes, each the smallest representation the control plane
already supports, plus one optional, additive schema hardening. Nothing is implemented
until a human approves.

### 1. Communication Agent — one line

`roadmap/epics/communication-agent.yaml:18`:

```diff
-  lifecycle: active
+  lifecycle: paused
```

Nothing else changes. No `required` flag is flipped, no `dependsOn` edge moved, no
issue closed or relabelled, no `status` field invented.

Why this cannot fake completion: `completion.py` reads only the observed GitHub state
carried by the snapshot. `lifecycle` is not one of its inputs. Verified by running
`health.py` against the edited manifest — exit 0, `healthy`, completion unchanged at
`incomplete` with `blocking: [c2-safety-gate, quota-domain]`. Delivered C1 evidence and
existing code are untouched because the pause touches no issue and no repository.

Why this is the smallest canonical representation: the value is already in the schema
enum, already in use by `edge-ai-android`, already copied into the publication by
`publish._epic_identity`, and already the field the wave-selection consumer filters on.

Where the pause bites, and where it does not:

| layer | behaviour after `lifecycle: paused` |
|---|---|
| `validate.py` | PASS (whole corpus, verified 17/17) |
| `reconcile.py` / `plan.py` | zero operations, zero notes, zero refusals, exit 0 |
| `completion.py` | unchanged — `incomplete`, same `blocking` list |
| `health.py` | unchanged — `healthy`, exit 0 |
| `ready.py` | **unchanged** — still `ready: [approval-workflow, channels-preview, quota-domain, temporal-approvals]` |
| `publish.py` | `publication.json` `epics[].lifecycle` becomes `paused` |
| mctl-api ready-work / wave planner | epic excluded; `mctl_plan_epic_wave` refuses `epic_paused` |

The `ready.py` row is the honest gap the issue asked to be surfaced rather than
glossed. The governed wave path is gated, so the manifest change alone satisfies the
owner requirement; but a consumer reading `ready-set.json` in isolation is not gated.

### 1b. Smallest explicit control-plane extension (optional, additive)

Add an optional `lifecycle` property to `$defs.epic` in
`roadmap/schemas/roadmap-ready-set.schema.json`, and for symmetry in
`roadmap-health.schema.json`, populated by `ready.render` / `health.render` from the
same validated manifest bytes, exactly as `publish._epic_identity` already does:

```json
"lifecycle": {"enum": ["proposed", "active", "paused", "completed", "archived"]}
```

Both `$defs.epic` blocks are `additionalProperties: false` with
`required: ["name", "manifest"]`, so an optional addition is backward compatible:
existing documents keep validating and no consumer breaks. This is deliberately
*not* a prerequisite — it is a hardening so that "is this epic paused" is answerable
from the file that answers "what is ready", without a join. Proposed as its own slice
so that approving the pause does not require approving a schema change.

Explicitly rejected: making `ready.py` emit zero ready items for a paused epic. That
would conflate two axes the control plane keeps separate — readiness is a property of
the dependency graph, selectability is a policy decision — and would make the ready set
lie about a graph that has not changed. Carry the fact; let the consumer decide.

### 2. Client Lifecycle — retire the branch, keep the epic

**`lookup-deployment` / `mctl-gitops#1182` → retire as not planned.** All five scope
steps are `admins/openclaw` deployment. Step 1 rolls out `TG_LOGIN_LOOKUP_ADMINS` for a
dedicated lookup account the owner has prohibited; step 2 signs that account in; step 3
is the Vault refresh token the owner has prohibited; step 4 is the third MCP server
entry the owner has prohibited; step 5 verifies through the bot being decommissioned.
No generic platform capability survives extraction: the reusable half —
the `admin:users`-only lookup tier, `TG_LOGIN_LOOKUP_ADMINS` support,
`list_telegram_identities` and `get_user_audit_log` — already shipped in
mctl-telegram#511 and #575 and is not tracked by this work item at all.

**`operator-identity-lookup` / `mctl-telegram#400` → retire as not planned.** #400's own
status section states the in-repository half is delivered and only the #1182 deployment
half remains. Retiring #1182 leaves #400 with zero remaining scope. Retaining it
re-scoped as a generic capability would mean authoring a consumer surface that does not
exist once `admins/openclaw` is decommissioned — a required item that can never become
ready, which is exactly the falsely-blocked state this proposal is meant to remove.
The already-shipped capability is preserved by doing nothing to it: no code is touched
and #511/#575 stay closed-as-completed.

**Retire means remove from the manifest *and* close the issue as not planned.** This is
a control-plane mechanic, not bookkeeping: `completion.py` maps `closed_not_planned` to
`incomplete`, and `ready.py` maps an item whose *own* issue is `closed_not_planned` to
`blocked` (`roadmap/README.md`, "Readiness" — the one place an item names itself as its
own blocker). A required item closed not-planned but left in the manifest would make
`client-lifecycle` permanently blocked and permanently incomplete. Closure alone is
insufficient; manifest removal is the operative change.

Resulting manifest edits to `roadmap/epics/client-lifecycle.yaml`:

- delete work item `lookup-deployment` (#1182) and its leading comment block;
- delete work item `operator-identity-lookup` (#400);
- delete phase `identity` ("Operator identity lookup"), now empty. `validate.py` has no
  rule requiring a phase to hold work items — it checks only duplicate phase ids
  (line 214) and unknown phase references (line 246) — so keeping it would also
  validate. Removal is tidiness.
- `onboarding-integration.dependsOn` becomes `[safe-broadcast, product-update-feed]`.

Preserved unchanged: `client-reachability-preferences` (#438),
`login-bot-update-receiver` (#619), `safe-broadcast` (#439), `product-update-feed`
(#440), `onboarding-integration` (#679), all `successCriteria`, and every other epic in
the corpus.

### 3. New `dependsOn` for `mctl-telegram#679`

```yaml
    - id: onboarding-integration
      dependsOn:
        - safe-broadcast
        - product-update-feed
```

`operator-identity-lookup` is removed, so #679 retains no OpenClaw-only dependency. The
first `successCriteria` entry ("Operator-facing identity lookup is scoped, auditable and
privacy-safe") is left in place: it is already satisfied by the shipped #511/#575
capability and describes the epic's standard, not an open work item.

### 4. `#440` / `product-update-feed` is **not** safe to rely on

Recommendation: **reopen `mctl-telegram#440`** (owner action, after approval). The
manifest needs no edit for this item; reopening restores `completion.reason: open` and
the honest graph. Rationale: it is the smallest possible correction, and it enacts the
owner's own written decision ("Not closing #440") which a release-please merge
overrode.

Why this is urgent rather than academic: retiring `operator-identity-lookup` removes
#679's last incomplete predecessor, so `onboarding-integration` turns **ready** on the
strength of #440's false `complete`. Computed after-state with #440 left closed:
`ready: [onboarding-integration]`, blocked 0. A wave planner would be handed #679 as
startable work whose stated precondition — a versioned handoff to broadcast `Prepare` —
is openly tracked as missing in #683.

Alternative, if the owner ratifies the partial delivery: keep #440 closed and add a
required work item bound to #683:

```yaml
    - id: product-update-delivery
      title: Persist frozen digests and hand them to broadcast Prepare by source_ref
      owner: mctl-telegram
      phase: updates
      required: true
      issue:
        repository: mctlhq/mctl-telegram
        number: 683
      dependsOn:
        - product-update-feed
```

with `product-update-delivery` added to `onboarding-integration.dependsOn`. This is a
larger manifest change and adds two governed operations (an `AddSubIssue` for #683
under #22 and an `AddDependency` #679 ← #683), so it is offered as the fallback.

### 5. Before / after counts

Before = the live publication, state revision `39ce89a…`, observation `capturedAt`
2026-09-26T22:57:44Z. After = computed by running `ready.py` and `health.py` over the
edited manifests against a snapshot reproducing the same observed issue states; the
before column of that computation reproduces the live ready set exactly, which is what
licenses the after column.

**`communication-agent`** (2 required, 4 optional):

| measure | before | after (`lifecycle: paused`) |
|---|---|---|
| required total | 2 | 2 |
| required complete | 0 | 0 |
| required ready (evaluator) | 1 — `quota-domain` | 1 — unchanged |
| required blocked (evaluator) | 1 — `c2-safety-gate` | 1 — unchanged |
| all items ready (evaluator) | 4 | 4 — unchanged |
| all items blocked (evaluator) | 2 | 2 — unchanged |
| `completion.status` | `incomplete` | `incomplete` |
| `health.state` | `healthy` | `healthy` |
| **wave-selectable required-ready (mctl-api)** | **1** | **0 — epic excluded, `epic_paused`** |

The point of the table is the last row versus the rest: the pause changes selectability
and nothing else. That is what "paused, not completed" looks like in this control plane.

**`client-lifecycle`** (all items required):

| measure | before | after: #1182/#400 retired | after: retired **and** #440 reopened |
|---|---|---|---|
| required total | 7 | 5 | 5 |
| complete | 4 | 4 | 3 |
| ready | 1 — `lookup-deployment` | 1 — `onboarding-integration` | 1 — `product-update-feed` |
| blocked | 2 — `operator-identity-lookup`, `onboarding-integration` | 0 | 1 — `onboarding-integration` |
| unknown | 0 | 0 | 0 |
| `completion.status` | `incomplete` | `incomplete` | `incomplete` |
| `health.state` | `healthy` (0 drift) | `healthy` after the two-step sequence | `healthy` |

The middle column is the one to read carefully: retiring the OpenClaw branch on its own
leaves the epic with zero blocked items and #679 ready, resting on #440's unverified
completion. The right-hand column is the recommended end state.

### 6. Exact GitHub mutations the reconciler / apply would need

**Communication Agent: none.** `plan.py` against the paused manifest returns
`operations: 0, notes: 0, refusals: 0`, exit 0. The pause authors no relation, so the
desired graph is relation-identical. The pre-existing informational
`HierarchyUnexpectedChild` for `mctl-telegram#305` under `#518` is unchanged and is
never actioned (`roadmap/README.md`, "Diff entry to operation": a note, no GitHub call).

**Client Lifecycle, done as one pull request: the governed plan is REFUSED.**

```
REFUSED: RemoveDependency targets an identity this manifest does not author: mctlhq/mctl-telegram#400
```
`plan.py` exits 3, zero operations for the whole manifest. The observed `blocked_by`
edge #679 ← #400 becomes `DependencyUnexpected` (severity `drift`) while #400 has left
`DesiredGraph.authored_keys()`, and `roadmap/README.md`'s "Refusal rules" require every
operation endpoint to be an authored identity. This is fail-closed — nothing is
written — but the epic then cannot be reconciled by `apply.py` at all until the edge is
removed out of band. Sequencing is therefore part of the design, not an afterthought.

**Pull request 1 — dependency edge only.** Edit only
`onboarding-integration.dependsOn` (drop `operator-identity-lookup`); leave both work
items in place so both endpoints stay authored. Computed plan: exit 1, exactly one
operation, zero notes, zero refusals:

| field | value |
|---|---|
| type | `RemoveDependency` |
| opId | `f955af581e0687da` |
| owner | `onboarding-integration` |
| blocked | `mctlhq/mctl-telegram#679` |
| blocker | `mctlhq/mctl-telegram#400` |
| precondition | `DependencyPresent` |
| GitHub call | `DELETE /repos/mctlhq/mctl-telegram/issues/679/dependencies/blocked_by/{id of #400}` |

Run `apply.py --live --execute --approved-sha256 <sha of the merged bytes>
--issue-ids <map containing #400's numeric id>`, per `roadmap/README.md`'s guard list.

**Pull request 2 — remove the work items and the phase.** Only after pull request 1's
apply has landed and `reconcile.py` shows zero drift. Computed plan: exit 0,
`operations: 0`, `refusals: 0`, `notes: 2`:

- `HierarchyUnexpectedChild` — child `mctlhq/mctl-gitops#1182`, observedParent `mctlhq/.github#22`
- `HierarchyUnexpectedChild` — child `mctlhq/mctl-telegram#400`, observedParent `mctlhq/.github#22`

`health.py` on the same inputs exits 0 (`healthy`), because informational entries are
not drift.

**Manual operator actions, outside the governed apply path.** `plan.py` deliberately
never removes a child the manifest does not own (`roadmap/README.md`: "removing children
this manifest does not own [is] deliberately absent ... [it] would delete state the
manifest never described"). So these are GitHub-UI or `gh` operations:

1. `DELETE /repos/mctlhq/.github/issues/22/sub_issue` for `mctl-gitops#1182`
2. `DELETE /repos/mctlhq/.github/issues/22/sub_issue` for `mctl-telegram#400`
3. close `mctl-gitops#1182` with state reason **`not_planned`** (never `completed`)
4. close `mctl-telegram#400` with state reason **`not_planned`**
5. reopen `mctl-telegram#440` (recommended remedy for deliverable 5)

Steps 1 and 2 are optional in the strict sense — the residue is informational only —
but leaving them makes the GitHub tree disagree with the manifest for readers who use
GitHub as the planning UI.

**Publication freshness.** Merging either manifest triggers `roadmap-publish.yml` on
the `roadmap/**` push. A governed apply that lands a write also requests a publication
via `publication_request.py`. Before planning any wave afterwards, request one
explicitly: `ROADMAP_WAVE_MAX_AGE` defaults to 30 minutes and no cron can promise that.

### 7. Rollback and unpause semantics

Unpausing the Communication Agent is one line in the reverse direction:

```diff
-  lifecycle: paused
+  lifecycle: active
```

No compensating change exists to forget, because the pause made none: no item became
optional, no issue was closed, no dependency moved, and the evaluator's ready set never
changed. On merge, `roadmap-publish.yml` republishes, `epics[].lifecycle` returns to
`active`, and the epic reappears in `mctl_get_ready_work_items` with exactly the ready
set it has today. `plan.py` before and after is empty in both directions, so no
governed apply is needed to unpause and none can be forgotten.

Rollback of the Client Lifecycle retirement is materially heavier and asymmetric, which
is the honest reason to treat the two decisions as separate approvals: reverting pull
request 2 restores the work items, reverting pull request 1 restores the `dependsOn`
edge and makes the governed apply re-create the `blocked_by` relation
(`DependencyMissing` → `AddDependency`), and the two issue closures must be reopened by
hand. Revert in the reverse order: reopen #1182 and #400, then revert pull request 2,
then revert pull request 1, then apply.

## Alternatives

**A. Encode the pause by flipping `quota-domain` and `c2-safety-gate` to
`required: false`.** Dropped, and explicitly warned against by the issue. It would make
`allRequired` vacuously satisfiable, turning `completion.status` from `incomplete` to
`complete` the moment nothing required remains — the exact false completion this
proposal must avoid — and it destroys the information needed to unpause, since nothing
records which items were required before. It also would not stop intake: optional items
still get a readiness state and still appear as `ready`.

**B. Encode the pause by closing #518 and its children as `not_planned`.** Dropped.
`closed_not_planned` is `incomplete` in `completion.py` and `blocked` in `ready.py`, so
it would suppress selection — but it says "we decided not to do this", not "we stopped
for now". Unpausing would require reopening six issues and would lose the
`stateReason` history. It also fails the "preserve already-delivered C1 evidence"
requirement in spirit, since the issues are where that evidence lives.

**C. Add a new `spec.status` (or `spec.paused`, `pausedAt`, `pausedBy`) field.**
Dropped as unnecessary. `spec.lifecycle` already enumerates `paused`, is already
required, is already copied into the publication, and is already the field the wave
planner filters on. Adding a second overlapping field would create two authored
answers to one question — precisely the multi-representation drift
`roadmap/README.md` exists to eliminate.

**D. Make `ready.py` return zero `ready` items for a paused epic.** Dropped. It
conflates readiness (a property of the dependency graph and observed completion) with
selectability (a policy decision), and would make `ready-set.json` describe a graph
that did not change. The chosen 1b alternative — carry `lifecycle` in the ready set and
let the consumer filter — preserves the layering and is strictly additive.

**E. Retain `mctl-telegram#400` re-scoped as a generic "operator identity lookup"
capability.** Dropped. The generic capability already shipped (#511, #575); what
remains in #400 is exclusively the `admins/openclaw` deployment. Keeping it as a
required item would leave `client-lifecycle` with an item that can never become ready
now that the only consumer surface is being decommissioned. Keeping it as
`required: false` would be tidier for reconciliation (it stays authored, so the
`RemoveDependency` never refuses) but it contradicts the owner's "retire" intent and
leaves a permanently `ready` optional item advertising decommissioned work.

**F. Retire both Client Lifecycle items in one pull request and delete the #679 ← #400
edge manually first.** A real option, and one pull request instead of two. Dropped as
the recommendation because the manual deletion happens while #400 is still authored, so
any governed apply run in the window between the deletion and the merge would see
`DependencyMissing` and helpfully re-create the edge. The two-pull-request sequence
keeps every write inside the governed path and has no such window.

**G. Accept `mctl-telegram#440`'s closed state and change nothing.** Dropped. The
closing actor is a release-please bot pull request; the last human decision on the
issue is an explicit refusal to close, with criterion 7 openly moved to #683. Accepting
it would let a required item read `complete` on evidence its own owner rejected, and —
because retiring #400 makes #679 ready — would feed that false completion straight into
wave selection.

## Platform impact

**Migrations.** None. Both changes are YAML edits to existing manifests. The optional
1b schema addition is an optional property on an `additionalProperties: false` object,
so every already-published `ready-set.json` and `health.json` stays valid and no
consumer needs to change in lockstep.

**Backward compatibility.** `spec.lifecycle: paused` is already an enumerated value in
production use (`edge-ai-android`), already handled by `publish._epic_identity`, and
already pinned by `roadmap/tests/test_publish.py`. No consumer sees a new shape.

**Verification already performed** (offline, against the cloned corpus; no writes, no
live mutation):

- `python3 roadmap/scripts/validate.py roadmap/epics` on the edited corpus — 17/17 PASS,
  exit 0, including both edited manifests.
- `ready.py` on the unedited manifests with a snapshot reproducing the observed issue
  states reproduces the live ready sets exactly for both epics, which validates the
  method before it is used for the after-state.
- `ready.py` on the paused Communication Agent manifest — byte-identical ready set.
- `ready.py` on the edited Client Lifecycle manifest — the three-column table above.
- `plan.py` on the paused manifest — 0 operations / 0 notes / 0 refusals, exit 0.
- `plan.py` on a one-shot Client Lifecycle removal — `REFUSED`, exit 3.
- `plan.py` on the pull-request-1 manifest — one `RemoveDependency`, `opId f955af581e0687da`, exit 1.
- `plan.py` on the pull-request-2 manifest with the edge already removed — 0 operations,
  2 notes, exit 0; `health.py` exit 0.

**Resource impact.** One extra publication run per merged pull request
(`publish.py cost` reported 545 GETs per capture on 2026-09-23, against a documented
1000/hour budget). Two manifest pull requests plus one governed apply's publication
request is at most three captures, and `publication_order.py decide` collapses
same-hour duplicates. Well inside budget.

**Risks and mitigations.**

| risk | mitigation |
|---|---|
| A one-shot Client Lifecycle change refuses the governed plan and leaves the epic unreconcilable | Two-pull-request sequence; pull request 2 gated on pull request 1's apply reporting zero drift (task 7, test T5) |
| `ready-set.json` still lists four `ready` items for the paused epic | The governed wave path filters on `publication.json`; empirically confirmed. Optional 1b hardening closes the direct-read gap |
| The DevLoop `issue-poll` schedule (`*/15 * * * *`) starts #334/#347/#350 regardless of roadmap lifecycle | Verify its selection criteria (task 9); if it is label- or state-driven, back the pause with a GitHub-side hold on the six issues. A search of `mctlhq/mctl-agents` found no roadmap-lifecycle awareness |
| Retiring #400 silently unblocks #679 on #440's false `complete` | Reopen #440 in the same approved change set (task 10); the after-state table makes the exposure explicit |
| A future release-please pull request closes another roadmap-required issue the same way | Flagged as an open question with a bounded scope; deliberately not actioned here |
| Closing #1182/#400 without removing them from the manifest would permanently block the epic | Stated as an acceptance criterion; the manifest removal, not the closure, is the operative change, and task order enforces it |
| An approval is invalidated by a force-push after review | Already handled: `apply.py --approved-sha256` binds approval to the exact manifest bytes |

**Security and authority.** Nothing in this proposal grants new authority. No model
writes to the GitHub graph: manifest text goes through human review and merge, and
`apply.py` re-reads each endpoint before at most one allow-listed write. No credential,
Vault entry or Telegram account is created; retiring #1182 in fact removes the only
roadmap item that would have required one.
