# First-class WorkItem view across surfaces and executions

## Context
Issue mctlhq/mctl-portal#126 (parent roadmap mctlhq/.github#21) asks the portal to show a canonical
WorkItem as a durable object of its own, not as one chat or one execution. A single WorkItem can span
several executions (E1, E2, E3) started from different surfaces (Telegram, MCP/API, Portal). Each
execution has its own ContextSnapshot and, once mctlhq/mctl-portal#111 ships, its own Execution Canvas.
The page must answer: what the work is, what state it is in, which surfaces touched it, which executions
and ContextSnapshots belong to it, what is blocking it, which human input or approval is pending, what
evidence exists, and what the next governed action is.

The portal currently has no WorkItem concept. The closest analogues are the proposals UI
(`packages/app/src/components/proposals/*` with `plugins/proposals-backend`) and the
`custom-domains-backend` gateway to mctl-api. The issue sets a hard backend boundary: the portal reads a
normalized WorkItem read model from mctl-api (contract mctlhq/mctl-api#227). It does not join GitHub,
Temporal, Argo, proposal files and context storage itself, and it never mutates Temporal or Argo directly.

## User stories
- AS a tenant developer I WANT to open a deep link to one WorkItem SO THAT I can see its current state
  and history in one place, whichever surface started it.
- AS a tenant developer I WANT to see which surfaces (Telegram, MCP/API, Portal) have interacted with
  the WorkItem as metadata only SO THAT I understand where it came from without exposing private
  conversation content.
- AS an operator I WANT to see every correlated execution with its ContextSnapshot ID, version and
  provenance, with the active or pending execution set apart from historical ones, SO THAT I can
  understand what changed between E1 and E2.
- AS an approver I WANT the current blocker, pending human input, pending approvals and the next
  governed action shown clearly SO THAT I can unblock the work.
- AS an approver I WANT any action I start from the page to be re-authorized by mctl SO THAT the
  portal never grants me more than my own policy allows.
- AS any user I WANT stale, missing or unobservable data shown as unknown SO THAT I never mistake a
  gap for success or for "nothing there".

## Acceptance criteria (EARS)
- WHEN a user opens `/work-items/:workItemId` THE SYSTEM SHALL fetch that WorkItem through the
  `work-items` backend plugin, which reads it from the mctl-api WorkItem read model. THE SYSTEM SHALL
  render the WorkItem's canonical identity, title, lifecycle status (WAITING, RUNNING, BLOCKED,
  COMPLETED, or the upstream value as-is), owner team and policy summary.
- WHEN the WorkItem has surface references THE SYSTEM SHALL list each one with its surface kind,
  reference ID, transition type, actor and timestamp. THE SYSTEM SHALL NOT render message or
  transcript bodies.
- IF the upstream payload contains transcript or message content fields THEN THE SYSTEM SHALL drop
  them in the backend mapper before the response reaches the browser.
- WHEN the WorkItem has correlated executions THE SYSTEM SHALL list every execution with its ID,
  surface of origin, status, start and end times, ContextSnapshot ID, version, provenance and status,
  and its result or blocker summary.
- WHILE an execution is marked current (active or pending) by the read model THE SYSTEM SHALL show it
  apart from historical executions, above them.
- WHEN an execution has a canvas reference and Execution Canvas is available (config
  `workItems.executionCanvasUrlTemplate` is set) THE SYSTEM SHALL render a deep link to that
  execution's canvas. IF it is not available THEN THE SYSTEM SHALL show "canvas unavailable" and no
  broken link.
- WHEN the WorkItem has pending human input, pending approvals, blockers or next governed actions THE
  SYSTEM SHALL show them in a "Pending" section at the top of the page, visible without scrolling on
  desktop.
- WHEN the WorkItem has evidence (issue, PR, deployment, trace) THE SYSTEM SHALL render each item as
  an external link with its kind and label. THE SYSTEM SHALL only render `http(s)` URLs as links.
- IF a field or section is reported by the read model as `unknown`, `stale` or `unobservable`, or is
  absent from the payload, THEN THE SYSTEM SHALL render an explicit "Unknown" or "Stale since <time>"
  indicator. THE SYSTEM SHALL NOT render it as success, as an empty list, or as "none".
- IF mctl-api is unreachable, times out or returns 5xx THEN THE SYSTEM SHALL return 502 from the
  backend plugin, and the page SHALL show an error panel, not an empty WorkItem.
- WHEN a user who is neither a member of the WorkItem's owner team nor a platform admin requests a
  WorkItem THE SYSTEM SHALL respond 403. A WorkItem ID that does not exist SHALL respond 404.
- WHEN a user triggers a governed action (resume, approve, provide input) from the page THE SYSTEM
  SHALL re-authorize the caller in the backend on that request (team membership plus the action's
  required role). Only then SHALL it forward the action to the mctl-api action endpoint, which applies
  its own policy.
- THE SYSTEM SHALL NOT treat the fact that another surface previously performed an action as a reason
  to allow it.
- IF mctl-api rejects an action (4xx) THEN THE SYSTEM SHALL show the rejection reason and re-fetch the
  WorkItem. THE SYSTEM SHALL NOT update its local view optimistically.
- WHILE the `workItems.actionsEnabled` config flag is false (the default) THE SYSTEM SHALL render
  pending actions as read-only, with a note to complete them on an authorized surface, and the action
  routes SHALL return 403.
- THE SYSTEM SHALL NOT call Temporal, Argo, GitHub or context storage directly from the browser or
  from the work-items backend plugin.
- WHILE the viewport is mobile-width THE SYSTEM SHALL fall back to a single-column timeline/list
  layout with the same information.

## Out of scope
- A generic chat or transcript history viewer.
- Rebuilding Execution Canvas internals (#111). This proposal only deep-links to it.
- Browser-side orchestration or reconciliation across GitHub, Temporal, Argo, proposal files and
  context storage.
- Mutating Temporal or Argo directly, or by any path that bypasses mctl-api.
- Building the mctl-api WorkItem read model itself (mctlhq/mctl-api#227). Gaps in it become focused
  backend follow-up issues.
- A WorkItem list or search page beyond a minimal "open by ID" entry (possible follow-up).

## Open questions
- The exact wire shape of the canonical WorkItem contract (mctlhq/mctl-api#227) was not available in
  this clone. The design defines a portal-side type and a defensive mapper. Field names must be checked
  against mctl-api before implementation, as was done for `toPortalDomain` in custom-domains-backend.
- Authority for actions. custom-domains-backend calls mctl-api with a shared platform service token
  that passes mctl-api's admin bypass. Using that for WorkItem actions would let mctl-api's policy see
  the portal, not the user. Assumption: actions stay behind `workItems.actionsEnabled=false` until
  mctl-api accepts an on-behalf-of actor (or the user's own credential) and evaluates policy for that
  actor. Until then the page is read-only for actions.
- The ID format of a WorkItem, which decides the shape of the deep-link URL, is not specified. This
  proposal treats it as an opaque URL-encoded string checked against a conservative regex.
- Whether the read model returns an owner team for authorization, or whether mctl-api's own `?team=`
  scoping is the source of truth. The design assumes an `owner.team` field.
- Execution Canvas #111 is not in this repo yet. Its route shape is unknown, so the link comes from a
  config template.
- The "depends on" items (second-surface resume pilot, working-memory continuity) are not present.
  Acceptance items 1 to 4 can only be shown end-to-end once they and mctl-api#227 have landed. Until
  then the UI is verified against fixtures.
