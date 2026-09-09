# Tasks: issue-268-custom-domains-5-non-blocking-review-fin

- [ ] 1. Make the CNAME comparison case-insensitive in
      `internal/domains/verify.go:123` — replace the `==` on the two
      `strings.TrimSuffix(..., ".")` values with `strings.EqualFold(...)`, and
      extend the doc comment on the fast-path block to say why (DNS names are
      case-insensitive; resolvers echo the queried case). — DoD: `go test
      ./internal/domains/...` passes and the comparison no longer depends on
      case on either side.
- [ ] 2. Add `normalizeIdentifier(s string) string` to
      `internal/api/handlers_domains.go` (trim + lowercase, documented next to
      `normalizeHostname`) and use it for `req.Team`/`req.Service` in
      `AddDomain` (lines 206-207) and `VerifyDomainByName` (lines 351-352).
      (depends on 1) — DoD: a registration posted with `"team":"Labs"` stores
      `labs`, and `TestVerifyDomainByName_TrimsTeamAndServiceWhitespace` still
      passes.
- [ ] 3. Make `VerifyDomainByName`'s ownership gate
      (`handlers_domains.go:372`) case-insensitive with `strings.EqualFold` on
      both `Team` and `Service`, so rows written before task 2 stay reachable.
      Keep the 404 (never 403) response. (depends on 2) — DoD: a row stored as
      `Labs`/`SVC` is found by a request for `labs`/`svc`; a genuine
      team/service mismatch still 404s.
- [ ] 4. Gate the challenge fields in `domainResponseFor`
      (`handlers_domains.go:51-58`) on `d.Status == domains.StatusPending ||
      d.Status == domains.StatusFailed`; always keep `cname_target`. Document
      the reasoning in the function comment. — DoD: `GET /api/v1/domains`
      returns `challenge_record`/`challenge_value` for a pending row and omits
      them for an active one.
- [ ] 5. Extract `triggerRemoveCustomDomain(ctx, r, d) (workflowName string,
      skipped bool, err error)` in `handlers_domains.go`: no-op with
      `skipped=true` when `h.opts.Executor == nil || h.opts.Registry == nil`
      (plus a `slog.Warn`); otherwise `h.opts.Registry.Get("remove-custom-domain")`
      + `h.opts.Executor.Submit(ctx, op, {"team_name","service_name","domain"},
      user.ID, d.Team)`, followed by an `h.logAudit` entry mirroring
      `handlers_write.go:230-238`. — DoD: unit-testable with a fake
      `WorkflowExecutor`; no behavior change when the executor is nil.
- [ ] 6. Wire task 5 into `DeleteDomain` (`handlers_domains.go:408-430`):
      submit the workflow BEFORE `Store.Delete`, return 500 without deleting if
      the submission fails, and respond
      `{"status":"deleted","ingress_cleanup":"workflow-submitted"|"skipped",
      "workflow_name":...}`. Update the handler's doc comment to state the
      teardown contract. (depends on 5) — DoD: a successful delete submits
      exactly one `remove-custom-domain`; a failing submit leaves the row in the
      store.
- [ ] 7. Repoint `toolRemoveCustomDomain` (`internal/mcp/server.go:1511-1527`)
      at the API: list `?team=&service=`, match the hostname case-insensitively
      (trailing dot stripped), `DELETE /api/v1/domains/{id}?team=...`; fall back
      to the existing `POST /api/v1/operations/remove-custom-domain/execute`
      when no registry row matches. Keep `requireConfirm` and the destructive
      hint. (depends on 6) — DoD: one MCP call removes both the row and the
      ingress entry; a hostname with no registry row still triggers the
      workflow.
- [ ] 8. Update the `mctl_remove_custom_domain` tool description
      (`server.go:1493`) to state the trigger contract explicitly, in the style
      of `mctl_verify_domain`'s description (`server.go:1539`). (depends on 7) —
      DoD: the description names both effects (registry row + ingress/TLS
      cleanup) and the legacy fallback.
- [ ] 9. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run`, and
      `go test ./...` per `CLAUDE.md`; confirm the MCP tool count expectation in
      `internal/mcp/server_test.go` is unchanged (no tool added or removed) and
      that `TestMCPToolsCoverEveryNonHandlerOnlyOperation` still passes.
      (depends on 1-8) — DoD: all clean.

## Tests

- [ ] T1. `internal/domains/verify_test.go`:
      `TestVerify_CNAMEFastPath_CaseInsensitive` — resolver answers
      `LABS-SVC.MCTL.AI.` for target `labs-svc.mctl.ai`; expect
      `Verified: true, Method: MethodCNAME`. Always runs (no Postgres). Pins
      task 1.
- [ ] T2. `internal/api/handlers_domains_test.go`: `txtResolver` stub +
      `TestVerifyDomain_TXTPathMarksVerified` — decode `challenge_value` from
      the `AddDomain` response, feed it back from `LookupTXT`, assert
      `method: "txt"`, `verified: true`, and a persisted `status=verified` with
      non-nil `verified_at`. Closes finding 2.
- [ ] T3. `TestVerifyDomainByName_HappyPathMarksVerified` — same TXT stub via
      `POST /api/v1/domains/verify`; asserts the endpoint the `add-custom-domain`
      workflow calls (`mctl-gitops#1085`) persists verification. Closes
      finding 3.
- [ ] T4. `TestVerifyDomainByName_ServiceMismatchNotFound` — registered under
      `labs`/`svc`, verified with `service:"other"`, expect 404. Pins the gate at
      `handlers_domains.go:372`.
- [ ] T5. `TestVerifyDomainByName_MixedCaseTeamServiceStillMatches` — register
      with `"team":"Labs","service":"SVC"`, verify with lowercase, expect 200.
      Pins tasks 2 and 3.
- [ ] T6. `TestListDomains_IncludesChallengeForPending` — decode the list body
      into `map[string][]map[string]any` and assert the `challenge_record`,
      `challenge_value` and `cname_target` keys exist. Closes finding 4's first
      half (replaces the `strings.Contains` assertion's weak guarantee).
- [ ] T7. `TestListDomains_OmitsChallengeForActive` — flip the row to `active`
      via `UpdateDomainStatus` with `auth.NewServiceUser()`, then assert the two
      challenge keys are absent and `cname_target` is still present. Pins
      task 4.
- [ ] T8. `TestDeleteDomain_TriggersRemoveCustomDomain` — fake
      `WorkflowExecutor` recording `Submit` calls; assert exactly one submission
      with `team_name`/`service_name`/`domain` matching the row, that it happens
      before the row disappears, and that `workflow_name` is in the response.
      Pins task 6.
- [ ] T9. `TestDeleteDomain_SubmitFailureKeepsRow` — fake executor returning an
      error; assert 500 and that `store.Get(id)` still succeeds. Pins the
      ordering guarantee.
- [ ] T10. `TestDeleteDomain_NilExecutorSkipsCleanup` — existing
      `TestDeleteDomain_OwnTeamSucceeds` shape with no executor; assert 200 and
      `ingress_cleanup: "skipped"`. Pins the no-regression path.
- [ ] T11. `internal/mcp/server_test.go`:
      `TestRemoveCustomDomain_DeletesRegistryRow` — httptest server asserting the
      tool issues `DELETE /api/v1/domains/{id}` (not the operations path) when
      the list returns a matching row, and
      `TestRemoveCustomDomain_FallsBackForUnregisteredHostname` — asserting the
      operations POST when the list is empty. Pins task 7.

Note: T2-T10 are Postgres-gated by `TEST_DATABASE_URL`
(`handlers_domains_test.go:45-50`) and skip in CI, matching every existing
handler test in that file. T1 and T11 always run.

## Rollback

Each change is independent and revertable on its own:

- Findings 1-4 are pure code/test edits with no persisted state: `git revert`
  the commit. The only externally visible change is the two omitted JSON fields
  from `domainResponseFor`; reverting restores them immediately (the values are
  recomputed from `domain` + `verification_token`, both still in the row).
- Finding 5's blast radius is one extra Argo workflow per deletion. If
  `remove-custom-domain` submissions start failing and blocking deletions,
  the immediate mitigation without a redeploy is to revert task 6's ordering
  (delete first, submit best-effort) or, operationally, to fall back to the
  pre-change behavior by reverting the commit — `DeleteDomain` then returns to
  registry-only deletion and `mctl_remove_custom_domain` to workflow-only
  removal, exactly today's state.
- No schema change, so there is nothing to migrate back. Rows written after the
  change hold lowercase `team`/`service`; a reverted build still reads them,
  because lowercase values match the old byte-exact comparisons.
