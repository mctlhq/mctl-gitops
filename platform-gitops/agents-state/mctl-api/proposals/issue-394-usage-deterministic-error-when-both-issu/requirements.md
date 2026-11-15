# Deterministic usage-record error when both issue_number and pr_number are invalid

## Context
`(*Record).validateCorrelation()` in `internal/usage/types.go` checks `issue_number` and `pr_number` by ranging over a map literal, `map[string]*int64{"issue_number": r.IssueNumber, "pr_number": r.PRNumber}`. Go randomizes map iteration order. So when both fields are invalid in one record, the `ErrInvalidRecord` message (returned as a 400 by `internal/api/handlers_usage.go`) can name either field, and the choice can change from one call to the next. The record is rejected either way, so correctness holds. But the message changes between retries of the same payload, which makes errors hard to compare and hard to assert on in tests.

The issue (a residual P3 from the review of mctl-api#391 / mctlhq/mctl-agents#499) asks for the check to iterate a fixed, ordered slice instead, plus a test that covers both fields being invalid.

## User stories
- AS a usage-record producer (for example mctl-agents) I WANT the same invalid payload to always produce the same 400 message SO THAT I can compare and deduplicate errors across retries.
- AS a mctl-api developer I WANT validation errors to be deterministic SO THAT tests can assert on the exact field named.

## Acceptance criteria (EARS)
- WHEN a record has both `issue_number` and `pr_number` set and both are invalid THE SYSTEM SHALL return an `ErrInvalidRecord` error that names `issue_number`, on every call.
- WHEN a record has `issue_number` valid and `pr_number` invalid THE SYSTEM SHALL return an error naming `pr_number` (behaviour unchanged).
- WHEN a record has `pr_number` valid and `issue_number` invalid THE SYSTEM SHALL return an error naming `issue_number` (behaviour unchanged).
- IF either number is present and not positive THEN THE SYSTEM SHALL return "`<field>` must be positive" (message text unchanged).
- IF either number is present without `target_repo` THEN THE SYSTEM SHALL return "`<field>` requires target_repo" (message text unchanged).
- WHILE validating correlation fields THE SYSTEM SHALL check them in the fixed order `issue_number`, then `pr_number`, regardless of runtime map ordering.
- WHEN a record has no invalid correlation fields THE SYSTEM SHALL accept it exactly as today.

## Out of scope
- Changing which records are accepted or rejected, or changing any error message text.
- The same map-iteration pattern over token counters in `(*Record).Validate()` (`input_tokens` ... `web_search_requests`, `types.go` lines 291-298). It has the same nondeterminism but was not raised in the issue (see Open questions).
- Collecting all validation errors at once instead of returning the first.
- Any database, API schema or handler change.

## Open questions
- `Validate()` has the same nondeterministic pattern for its negative-token check (a map over six counters). Should it get the same fix in this change? This proposal leaves it out to stay within the issue's scope. A reviewer may choose to include it, since the fix is the same mechanical one.
