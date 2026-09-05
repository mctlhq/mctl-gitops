# Document the DevLoop workflow-liveness `describe` endpoint

## Context

On 2026-08-29, `mctl-api` shipped a new REST endpoint (commit `d6aca27`) that reports
whether a DevLoop workflow execution is still alive. This is a minor, admin-facing
addition to the existing DevLoop surface — but `docs/api/index.md`, the platform's REST
API reference, does not mention any DevLoop endpoints at all today. Because item #1 in
this batch (`platform-operations-approval-flow`) already touches the DevLoop area to
document the durable `mctl_approve_dev_loop` signal path and references "checking
whether a workflow is still live" as part of the approval decision guide, this is a
natural, low-effort addition to close the same gap while the dev-loop area is already
being documented.

## User stories

- AS a **platform admin** I WANT to check via REST whether a DevLoop workflow execution
  is still alive SO THAT I can decide whether to use the durable Temporal-signal
  approve path or the direct GitOps-file approval operation.
- AS a **developer** integrating with the platform API I WANT `docs/api/index.md` to
  list DevLoop endpoints SO THAT I don't have to read `mctl-api` source to discover
  them.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/api/index.md` THE SYSTEM SHALL show an entry for the new
  DevLoop `describe` endpoint, including its HTTP method, path, and response shape.
- IF a reader wants to call the `describe` endpoint THEN THE SYSTEM SHALL provide a
  runnable `curl` example.
- WHILE the exact REST path, HTTP method, and response field names are not
  independently confirmed from source in this pass THE SYSTEM SHALL mark those with
  `<TODO: confirm with author of d6aca27>` rather than inventing them.
- WHEN the entry is added THE SYSTEM SHALL note that it is admin-only / diagnostics-
  oriented, consistent with the rest of the DevLoop admin surface.

## Out of scope

- Documenting the full DevLoop REST surface beyond the `describe` endpoint (no other
  DevLoop endpoints were identified as undocumented in this scan).
- Any UI/dashboard visualization of workflow liveness (not part of this commit).
- Localisation / i18n.
