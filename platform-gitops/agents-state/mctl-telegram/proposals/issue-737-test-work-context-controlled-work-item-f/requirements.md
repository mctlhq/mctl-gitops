# Controlled work item for the #443 live session (no code change)

## Context
Issue #737 is a controlled test fixture rather than a feature request or a bug. Its only purpose is to be the target of the owner's live session that closes #443 (work-context surface adapter) and supplies REST evidence for mctlhq/mctl-api#341. The owner runs `/mctl link`, then `/mctl work https://github.com/mctlhq/mctl-telegram/issues/737` from Telegram Saved Messages, then `/mctl work status` until the `start` execution request is `fulfilled`. The owner then opens the same WorkItem in the portal at `/work-items/<id>` (mctlhq/mctl-portal#126).

The issue says this investigation is the expected side effect of `/mctl work`, which submits a `start` execution request. It also says the resulting proposal must **not** be approved and that nothing should be implemented. So this proposal intentionally specifies no change to `mctl-telegram`. It records what the session observes, using the existing manual procedure in `docs/work-context.md` ("Manual cross-surface verification"). It also records the guardrails that keep the fixture from turning into real work.

## User stories
- AS the platform owner I WANT a disposable, well-defined issue to bind a Telegram thread to SO THAT I can exercise `/mctl work` end to end without the run producing a real code change.
- AS a reviewer of #443 / mctl-api#341 I WANT the session evidence (work item id, request id, request state transitions, execution id) recorded on #443 SO THAT the acceptance of the work-context adapter is backed by a real run.
- AS a DevLoop operator I WANT this proposal to be clearly marked as do-not-approve SO THAT the Tier 2 implementer never opens a PR for it.

## Acceptance criteria (EARS)
- WHEN the owner sends `/mctl work https://github.com/mctlhq/mctl-telegram/issues/737` from a linked account THE SYSTEM SHALL canonicalise the URL via `workctx.CanonicalIssueURL`, create or reuse the WorkItem, and submit exactly one `start` execution request (existing behaviour in `WorkHandler.handleOpen`).
- WHEN the owner sends `/mctl work status` THE SYSTEM SHALL report the work item id, state, latest execution and the request state as rendered by `formatRequestState` (existing behaviour in `WorkHandler.handleWorkStatus`).
- WHEN the start request reaches `fulfilled` THE SYSTEM SHALL show the execution id that the portal's `/work-items/<id>` view also shows for the same WorkItem.
- WHILE this proposal exists THE SYSTEM SHALL remain unchanged: no source, schema, migration, config or doc file in `mctl-telegram` is modified on behalf of issue #737.
- IF this proposal is ever presented for approval THEN the approver SHALL decline it, and the DevLoop SHALL NOT reach the implementer.
- WHEN the session evidence has been recorded on #443 THE owner SHALL close issue #737.

## Out of scope
- Any code, test, migration or documentation change to `mctl-telegram`.
- Approving this proposal, running `mctl_trigger_implementer` for it, or opening a PR.
- Changes to mctl-api (#341) or mctl-portal (#126). Those repos only supply the other surfaces that are observed.
- Fixing any defect the live session might uncover. Such a defect gets its own issue.

## Open questions
- Whether the DevLoop for this issue should be explicitly cancelled after the evidence is captured, or left parked at the approval signal. Proposed answer: cancel or let it time out, but never approve. The owner decides.
- Whether the evidence posted on #443 should include the raw REST responses from mctl-api#341 or only ids and states. Proposed answer: ids and states only, with no Telegram identifiers beyond what is already public.
