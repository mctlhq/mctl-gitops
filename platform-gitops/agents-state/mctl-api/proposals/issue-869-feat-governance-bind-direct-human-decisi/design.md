# Design: Slice 1 of issue-869

## Where the change lives

`internal/api` only, plus the OpenAPI file, one doc and the MCP tool schemas.

- `handlers_approval_governance.go`: `guardDecision(w, r, user, a, decision, sentDigest)` becomes `guardDecision(..., bind *decisionBinding)`. The old `sentDigest != ""` test stays for the legacy alias; the binding comparison is added next to it.
- `handlers_action_approvals.go`: `actionDecisionBody` gains `Binding *decisionBinding`. The path id must equal `binding.approval_ref`, else 409 `approval_context_changed`.
- `handlers_dev_loop.go`: `approveDevLoopRequest` gains `Binding`. `decideDevLoopApproval` receives it and, when set, resolves the grant by `approval_ref` against the execution's grants instead of taking the newest. The newest grant is still read, only to report `current_approval_ref`.

```go
type decisionBinding struct {
    ApprovalRef   string `json:"approval_ref"`
    ContextDigest string `json:"context_digest"`
    ContentDigest string `json:"content_digest"`
}
```

## Order of checks (first failure wins)

1. `isHumanAdmin` (403 `approval_decider_forbidden`), unchanged and first.
2. Identity-field refusal, body decode (400).
3. Mode: `enforce` and no binding -> 422 `approval_binding_missing`. `observe` and no binding -> audit + counter, continue legacy.
4. Binding shape: all three fields present and well formed (422 `approval_binding_missing`).
5. Grant lookup. Store unreadable -> 503, never "no grant" (could not observe is not observed absent).
6. `approval_ref` is not the grant being decided (DevLoop: not in this execution) -> 409 `approval_context_changed`.
7. Terminal-state refusals keep precedence, as today.
8. `guardDecision`: policy admission, context completeness, then context digest and content digest equality -> 409 `approval_context_changed`.
9. `DecideActionApproval` compare-and-set. An already approved grant with the same binding returns the existing decision (idempotent).

Terminal-state refusals (7) precede governance refusals (8), matching the existing precedence section of `decision-context-contract.md`.

## Why a server mode and not "binding present means strict" alone

A caller that omits `binding` would bypass any rule keyed on its presence. So presence is strict (no partial bindings), and absence is controlled by the server mode, measured in `observe`, and refused in `enforce`. This is the same observe-then-enforce pattern the receipt gate used (`MCTL_AGENT_RECEIPT_GATE`).

## What this slice does not do

It does not read the live proposal digest from gitops. The binding compares what the person saw (`content_digest`) with what the grant holds (`artifact_hash`). A grant that is itself stale against the proposal is handled by the mctl-agents supersede path and mctl-agents#773; this slice does not claim to cover it.

## New codes

Only `approval_binding_missing` (422) is new. Everything else reuses `approval_context_changed` (409) and the existing state codes. `approval_binding_missing` is not an `aar_` decision outcome.

## Risks

- A card that renders `content_digest` from a different source than the grant's `artifact_hash` would always mismatch. The OpenAPI text states the source field.
- `observe` leaves the hole open until the flip. The counter and the audit entry are how the flip is justified.
