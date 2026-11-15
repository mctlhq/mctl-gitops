# Design: issue-394-usage-deterministic-error-when-both-issu

## Current state
- `internal/usage/types.go`, `(*Record).Validate()` (line ~271), calls `r.validateCorrelation()` after the `calculated_cost`/`pricing_version` check and returns the first error.
- `internal/usage/types.go`, `(*Record).validateCorrelation()` (line ~364), checks `target_repo`, `execution_id` and `temporal_run_id` in a fixed order. It then checks the two numeric correlation fields like this:
  ```go
  for name, v := range map[string]*int64{"issue_number": r.IssueNumber, "pr_number": r.PRNumber} {
      if v == nil { continue }
      if *v <= 0 { return fmt.Errorf("%w: %s must be positive", ErrInvalidRecord, name) }
      if r.TargetRepo == "" { return fmt.Errorf("%w: %s requires target_repo", ErrInvalidRecord, name) }
  }
  ```
  Go map iteration order is unspecified and randomized, so a record such as `{IssueNumber: 0, PRNumber: -1, TargetRepo: "mctlhq/x"}` or `{IssueNumber: 12, PRNumber: 13}` (no repo) yields a message naming either field.
- `internal/api/handlers_usage.go:186` maps `usage.ErrInvalidRecord` to an HTTP 400 that carries the error text, so the nondeterminism reaches producers.
- `internal/usage/usage_test.go`, `TestCorrelationShapesAreValidatedAtIngest` (line ~368), has an `invalid` table. Today it only asserts `err != nil`, and every case has at most one invalid number. No case has both invalid, and no case checks which field is named.
- The same map pattern appears in `Validate()` for the token counters (lines ~291-298). It is not part of this issue.

Deployed state checked:
- `/workdir/mctl-gitops/platform-gitops/services/*/mctl-api`: not present. The checkout's `services/` has only the `admins`, `karabu`, `labs` and `namax66` tenants, and none has an `mctl-api` service directory. I could not observe mctl-api's deployed config there. This change is a pure in-process validation-ordering fix with no configuration dependency, so the gap does not affect the design.
- mctl MCP tools: not called. Nothing in this change depends on tenant, hostname, env or replica state.

## Proposed solution
In `validateCorrelation()`, replace the map literal with an ordered slice of name/value pairs:

```go
for _, f := range []struct {
    name string
    v    *int64
}{
    {"issue_number", r.IssueNumber},
    {"pr_number", r.PRNumber},
} {
    if f.v == nil {
        continue
    }
    if *f.v <= 0 {
        return fmt.Errorf("%w: %s must be positive", ErrInvalidRecord, f.name)
    }
    if r.TargetRepo == "" {
        return fmt.Errorf("%w: %s requires target_repo", ErrInvalidRecord, f.name)
    }
}
```

The order matches the struct field order (`IssueNumber` before `PRNumber` in `Record`, `types.go` lines 140-141) and the order the issue proposes. Error texts and accept/reject results are unchanged. Only the choice of field named when both are invalid becomes fixed (always `issue_number`).

Add a comment noting that the slice is ordered deliberately, so that nobody later "simplifies" it back to a map.

Tests: extend `usage_test.go` with a test (or a second table inside `TestCorrelationShapesAreValidatedAtIngest`) that asserts on the exact message for records where both numbers are invalid. Run each case many times (for example 50 iterations), because a single call to the old map-based code can pass by luck.

## Alternatives
1. **Sort the map keys before iterating.** This is deterministic, but it allocates, needs `sort`/`slices`, and makes alphabetical order the contract by accident. It is no clearer than a literal slice. Dropped.
2. **Two explicit `if` blocks, one per field.** This is deterministic and readable, but it duplicates the two checks and their messages. The slice keeps one copy of the logic, and it is what the issue asks for. Dropped.
3. **Report all invalid fields with `errors.Join`.** This is more informative, but it changes the message text that producers see and goes beyond a P3 determinism fix. Dropped (out of scope).

## Platform impact
- Migrations: none. Storage and schema (`internal/usage/store.go`) are untouched.
- Backward compatibility: the HTTP status and every message string stay the same. For the both-invalid case, the message is now always the `issue_number` variant, which was already one of the two possible outputs, so no producer can see a message it could not see before.
- Resources: negligible. A two-element slice literal replaces a two-element map allocation, which is slightly cheaper.
- Risks: almost none. Risk: a future edit reintroduces a map. Mitigation: the code comment plus the repeated-iteration test.
