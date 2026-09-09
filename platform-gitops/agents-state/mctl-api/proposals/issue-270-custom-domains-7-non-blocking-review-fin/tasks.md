# Tasks: issue-270-custom-domains-7-non-blocking-review-fin

- [ ] 1. (item 1) In `internal/api/handlers_domains.go`,
  `triggerRemoveCustomDomain`: hoist `team := normalizeIdentifier(d.Team)`
  and `service := normalizeIdentifier(d.Service)` into locals, build
  `params` from them, and pass `team` (not `d.Team`) as the fifth argument
  to `h.opts.Executor.Submit`. Extend the existing normalization comment to
  note the `mctl.ai/team` label is the consumer.
  — DoD: no `d.Team` / `d.Service` reference remains between the `params`
  literal and the `Submit` call; `Registry.ValidateInput(op, params)` still
  runs before `Submit`; `go build ./...` clean.

- [ ] 2. (item 2) In `resolveDomainForMutation`, change the no-`?team=`
  fall-through to `if !user.HasTenantAccess(normalizeIdentifier(d.Team))`
  and extend the function doc comment to state that a legacy mixed-case
  `d.Team` is normalized before the access check, matching the `?team=`
  branch's `EqualFold`.
  — DoD: both branches of the function agree on casing for the same legacy
  row; the 404-not-403 non-disclosure behaviour is unchanged.

- [ ] 3. (item 4) In `handlers_domains.go`, introduce
  `type cleanupOutcome string` with constants `cleanupSubmitted`
  ("workflow-submitted"), `cleanupNotRequired` ("not-required"),
  `cleanupUnavailable` ("unavailable"), `cleanupMisconfigured`
  ("misconfigured"), documented with the condition each represents. Change
  `triggerRemoveCustomDomain`'s signature from
  `(string, bool, error)` to `(string, cleanupOutcome, error)` and return
  the matching constant from each of the three former `skipped=true` sites.
  — DoD: the status gate returns `cleanupNotRequired`, the nil
  Executor/Registry gate returns `cleanupUnavailable`, the registry-miss
  gate returns `cleanupMisconfigured`; the submit path returns
  `cleanupSubmitted`.

- [ ] 4. (item 4, depends on 3) Upgrade the registry-miss log in
  `triggerRemoveCustomDomain` from `slog.Warn` to `slog.Error`, with a
  message stating that real ingress/TLS may be left behind, and update
  `DeleteDomain` to write `"ingress_cleanup": string(outcome)` from a single
  response path, including `workflow_name` only when
  `outcome == cleanupSubmitted`.
  — DoD: HTTP 200 + `"status":"deleted"` for every non-error outcome; the
  keep-the-row-on-submit-error contract unchanged; the `DeleteDomain` doc
  comment's "cleanup is skipped" wording updated to the new vocabulary.

- [ ] 5. (item 3) In `internal/domains/store.go`, `NewStore`: after the
  `domainSchema` Exec, add a separate `pool.Exec` for
  `CREATE INDEX IF NOT EXISTS custom_domains_team_lower ON custom_domains
  (lower(team), lower(service))`, logging `slog.Warn` on failure instead of
  failing startup, with a comment citing `ListByTeam`'s `lower()` comparison
  and the `internal/audit/postgres.go` precedent.
  — DoD: an index-creation failure leaves `NewStore` returning a usable
  store; `domainSchema` itself is unchanged; `custom_domains_team` is left
  in place.

- [ ] 6. (item 7) Rewrite the doc comment on
  `TestDeleteDomain_SkipsTeardownForPendingRow`
  (`internal/api/handlers_domains_test.go`) to describe the real gate: only
  a row that is neither active, verified nor failed skips teardown, and
  `StatusFailed` is deliberately excluded from the skip (cross-referencing
  `TestDeleteDomain_FailedRowStillSubmitsTeardown` below it).
  — DoD: no remaining "never reached StatusVerified/StatusActive" wording.

- [ ] 7. (depends on 3) Add a team-argument recorder to
  `fakeDomainExecutor` in `internal/api/handlers_domains_test.go` (e.g.
  `submittedTeams []string`, appended in `Submit` alongside `submitted`).
  — DoD: additive field only; all existing tests in the file still compile
  and pass unchanged.

- [ ] 8. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
  `go test ./...` (per `CLAUDE.md`), plus `go test ./internal/api/...
  ./internal/domains/...` with `TEST_DATABASE_URL` pointed at an ephemeral
  Postgres so the gated tests actually execute.
  — DoD: all clean; the Postgres-gated runs reported in the PR body with the
  command used.

- [ ] 9. Add a CHANGELOG entry and note in the PR body that
  `ingress_cleanup: "skipped"` is replaced by `not-required` /
  `unavailable` / `misconfigured`, and that no in-repo consumer parses it
  (grep evidence: only `handlers_domains.go` and its tests).
  — DoD: the response-vocabulary change is discoverable without reading the
  diff.

## Tests

- [ ] T1. (item 1) `TestDeleteDomain_NormalizesSubmitTeamArgument`
  (`internal/api/handlers_domains_test.go`): create a legacy row via
  `store.Create` with `Team: "Labs"`, `Service: "svc"`, promote it with
  `store.SetStatus(..., domains.StatusActive, "")`, DELETE it as a caller in
  group `labs`; assert the recorded team argument from task 7 is `"labs"`,
  and that `submitted[0]["team_name"] == "labs"`.

- [ ] T2. (item 2) `TestDeleteDomain_MixedCaseRowWithoutTeamParamResolves`:
  same legacy `Labs` row, DELETE with **no** `?team=` query param as a
  caller in group `labs`; expect 200 (today: 404). Add the negative twin —
  a caller in group `other` gets 404, proving normalization did not widen
  access beyond the caller's own groups.

- [ ] T3. (item 4) `TestDeleteDomain_SkipsTeardownForPendingRow` now asserts
  `ingress_cleanup == "not-required"`; `TestDeleteDomain_NilExecutorSkipsCleanup`
  now asserts `"unavailable"`; new
  `TestDeleteDomain_MissingOperationIsMisconfigured` configures an
  `operations.Registry` without `remove-custom-domain`, deletes an active
  row and asserts 200, zero submissions, and
  `ingress_cleanup == "misconfigured"`.

- [ ] T4. (item 3) `TestListByTeam_MixedCaseStoredRow`
  (`internal/domains/store_test.go`): insert via
  `s.Create(ctx, newDomain("Labs", "Svc", "mixed-list.example.com"))` —
  bypassing `AddDomain`'s normalization the way
  `TestCreate_LegacyMixedCaseRowIsIdempotentNotConflict` already does — then
  assert `ListByTeam(ctx, "labs", "svc")` returns exactly that row, and that
  `ListByTeam(ctx, "labs", "")` does too.

- [ ] T5. (item 5) `TestRemoveCustomDomain_NotesFailedList`
  (`internal/mcp/server_test.go`, next to
  `TestRemoveCustomDomain_NotesUnparseableList`): `httptest` backend returns
  500 with `{"error":"boom"}` for `GET /api/v1/domains` and a normal body
  for `/operations/remove-custom-domain/execute`; assert the tool result is
  not an error, the execute path was hit, and the text contains "could not
  consult the domains registry". Assert the DELETE path is never called.

- [ ] T6. (item 6) Extend `TestDeleteDomain_FailedRowStillSubmitsTeardown`
  to assert `submitted[0]` has `team_name=labs`, `service_name=svc`,
  `domain=delete-failed.example.com` and that the response body carries
  `ingress_cleanup == "workflow-submitted"` plus a non-empty
  `workflow_name`, matching its three sibling tests.

- [ ] T7. Confirm the MCP tool count expectation in
  `internal/mcp/server_test.go` is untouched (no tool added or removed by
  this change), per `CLAUDE.md`.

## Rollback

Every change is contained in three files
(`internal/api/handlers_domains.go`, `internal/domains/store.go`,
`internal/mcp/server_test.go`) plus two test files, with no schema or data
mutation, so rollback is a plain image revert:

1. `mctl_rollback_service` (or a GitOps `image.tag` revert) to the previous
   mctl-api tag. The API is stateless with respect to this change; the old
   binary keeps returning `ingress_cleanup: "skipped"` immediately.
2. The `custom_domains_team_lower` index survives the revert and is inert —
   the old binary's `ListByTeam` issues the identical `lower()` query and
   simply benefits from it. No action needed. If it must go for some
   unrelated reason: `DROP INDEX IF EXISTS custom_domains_team_lower;`
   (safe, non-blocking on a table this size).
3. If only the `ingress_cleanup` vocabulary turns out to break an unknown
   consumer, the narrow fix is to set all three non-submitted constants back
   to the literal `"skipped"` — a four-line change that keeps items 1, 2, 3,
   5, 6 and 7 in place.
