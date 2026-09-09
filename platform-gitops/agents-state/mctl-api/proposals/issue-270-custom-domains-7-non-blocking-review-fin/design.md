# Design: issue-270-custom-domains-7-non-blocking-review-fin

## Current state

Everything below was read in the clone at `eca288e` (the merge of #269).

### `internal/api/handlers_domains.go` (661 lines)

- `normalizeIdentifier(s)` lowercases + trims a team/service name;
  `normalizeHostname(d)` additionally strips a trailing dot. Both are used
  on every caller-supplied value in `ListDomains`, `AddDomain` and
  `VerifyDomainByName`.
- `resolveDomainForMutation(w, r, id)` (around line 300-360) is the shared
  authorization path for `VerifyDomain` and `DeleteDomain`. Order: nil user
  -> 401; `Store.Get(id)` -> 404/500; `user.IsAdmin()` -> allow; then either
  the `?team=` branch (normalizes the param, `HasTenantAccess` -> 403,
  `strings.EqualFold(d.Team, team)` -> 404) or the fall-through
  `if !user.HasTenantAccess(d.Team)` -> 404. **The fall-through compares
  `d.Team` raw** — item 2. A legacy row stored as `Labs` is therefore
  reachable through the `?team=Labs` branch (EqualFold) but 404s for the
  same caller when `?team=` is omitted.
- `DeleteDomain` calls `triggerRemoveCustomDomain`, then `Store.Delete`, then
  writes one of two bodies:
  `{"status":"deleted","ingress_cleanup":"skipped"}` or
  `{"status":"deleted","ingress_cleanup":"workflow-submitted","workflow_name":...}`.
- `triggerRemoveCustomDomain(ctx, r, d) (workflowName string, skipped bool, err error)`
  returns `skipped=true` from three unrelated places:
  1. the status gate (`d.Status` is not active/verified/failed) — a genuine
     no-op, no ingress ever existed;
  2. `h.opts.Executor == nil || h.opts.Registry == nil` — `slog.Warn`, the
     expected local/test state;
  3. `h.opts.Registry.Get("remove-custom-domain")` miss — `slog.Warn`, a
     production misconfiguration that silently leaves ingress behind.
  All three collapse into the single string `"skipped"` — item 4.
- It builds `params` with `normalizeIdentifier(d.Team)` /
  `normalizeIdentifier(d.Service)`, runs `Registry.ValidateInput(op, params)`,
  then calls `h.opts.Executor.Submit(ctx, op, params, userID, d.Team)` —
  **the fifth argument is raw `d.Team`** — item 1.

### `internal/operations/executor.go`

`Submit(ctx, op, params, userID, team)` uses `team` for exactly two things:
`WorkflowNamespace(op.WorkflowTemplate, team)` and the `mctl.ai/team` label
(line ~166). Per `WorkflowNamespace` (line 76-120), `add-custom-domain` and
`remove-custom-domain` are explicitly pinned to the `argo-workflows`
namespace regardless of team, so item 1 really is label-only: a mixed-case
row produces a `mctl.ai/team=Labs` label while its own workflow parameters
say `team_name=labs`.

### `internal/domains/store.go`

- `domainSchema` (one multi-statement const, executed once in `NewStore`)
  declares `custom_domains`, `custom_domains_domain` (unique on `domain`)
  and `custom_domains_team ON custom_domains (team, service)`.
- `ListByTeam` filters with `lower(team)=lower($1)` (and `lower(service)=lower($2)`),
  which cannot use `custom_domains_team` — item 3.
- `Create` already compares with `strings.EqualFold` for the legacy-row
  idempotency path, and `internal/domains/store_test.go`'s
  `TestCreate_LegacyMixedCaseRowIsIdempotentNotConflict` inserts a genuine
  mixed-case row by calling `s.Create(ctx, newDomain("Labs","Svc",...))`
  directly. That is the exact technique the missing `ListByTeam` test needs.
- Precedent for adding an index to an already-deployed table lives in
  `internal/audit/postgres.go` lines 69-84: a separate loop of
  `CREATE INDEX CONCURRENTLY IF NOT EXISTS` `Exec`s whose failure is a
  `slog.Warn`, not a startup error, with a comment explaining that
  CONCURRENTLY cannot run inside the implicit transaction pgx wraps a
  multi-statement `Exec` in.

### `internal/mcp/server.go`, `toolRemoveCustomDomain` (line 1489+)

Lists `/api/v1/domains?team=..&service=..`, and sets
`listWarn := listErr`; if `listErr == nil` it unmarshals and, on a parse
failure, sets `listWarn = fmt.Errorf("parse domains list: %w", err)`. On a
match it issues `DELETE /api/v1/domains/{id}?team=..` and returns the body
verbatim (it never parses `ingress_cleanup`). Otherwise it POSTs to
`/api/v1/operations/remove-custom-domain/execute` and, when `listWarn != nil`,
appends the "could not consult the domains registry" note.
`doRequest` (line ~2350) converts both a transport failure and any
`StatusCode >= 400` into a non-nil error, so `listErr != nil` is reachable
from a test with a backend that returns 500 — but no test does that today
(item 5). `TestRemoveCustomDomain_NotesUnparseableList`
(`internal/mcp/server_test.go:1288`) only covers the 200-with-bad-body half.

### `internal/api/handlers_domains_test.go`

Postgres-gated on `TEST_DATABASE_URL` via `newTestDomainStore` (skips
otherwise). `fakeDomainExecutor` (line ~940) records `submitted []map[string]string`
and supports an `onSubmit` hook, but **discards the `namespace`/`team`
argument** — it is only echoed into `SubmitResult.Namespace`. Item 1 has no
observable assertion point until that fake records the team argument.
`TestDeleteDomain_FailedRowStillSubmitsTeardown` (line 1272) asserts only
`len(exec.submitted) != 1` — item 6 — while its siblings
(`TestDeleteDomain_TriggersRemoveCustomDomain`,
`TestDeleteDomain_SkipsTeardownForPendingRow`,
`TestDeleteDomain_NilExecutorSkipsCleanup`) all assert params and/or the
response field. `TestDeleteDomain_SkipsTeardownForPendingRow`'s doc comment
(line 1218-1221) says "a row that never reached StatusVerified/StatusActive",
which no longer matches the gate now that `StatusFailed` is excluded from
the skip — item 7.

## Proposed solution

One PR, seven mechanical changes, no new packages and no new dependencies.
Grouped by file:

### 1. `internal/api/handlers_domains.go`

**(a) Normalize the `Submit` team argument (item 1).** Hoist the normalized
values into locals so params and the `Submit` call provably share them:

```go
team := normalizeIdentifier(d.Team)
service := normalizeIdentifier(d.Service)
params := map[string]string{"team_name": team, "service_name": service, "domain": d.Domain}
...
result, submitErr := h.opts.Executor.Submit(ctx, op, params, userID, team)
```

Sharing one local is deliberately better than adding a second
`normalizeIdentifier(d.Team)` at the call site: it makes drift impossible
rather than merely fixed today. `ValidateInput` still runs on `params`
before `Submit`, so the security property (`^[a-z0-9][a-z0-9-]{0,30}$`
rejects `/` and `..` after lowercasing) is untouched.

**(b) Normalize the fall-through access check (item 2).** In
`resolveDomainForMutation`, change
`if !user.HasTenantAccess(d.Team)` to
`if !user.HasTenantAccess(normalizeIdentifier(d.Team))`, and extend the
existing doc comment to say why (group names are canonical lowercase;
`d.Team` may predate `AddDomain`'s normalization — the same reason the
`?team=` branch above uses `EqualFold`).

**(c) Disambiguate `ingress_cleanup` (item 4).** Replace the
`skipped bool` return with a typed outcome, declared next to the handler:

```go
// cleanupOutcome is the value reported as ingress_cleanup in DeleteDomain's
// response. It distinguishes "nothing needed cleaning" from the two ways
// cleanup could not run — only one of which is benign.
type cleanupOutcome string

const (
    cleanupSubmitted    cleanupOutcome = "workflow-submitted"
    cleanupNotRequired  cleanupOutcome = "not-required"  // status gate: no ingress ever existed
    cleanupUnavailable  cleanupOutcome = "unavailable"   // no Executor/Registry (local/test)
    cleanupMisconfigured cleanupOutcome = "misconfigured" // op absent from the registry: real ingress may be orphaned
)
```

`triggerRemoveCustomDomain` becomes
`(workflowName string, outcome cleanupOutcome, err error)`; the three
former `skipped=true` sites return `cleanupNotRequired`,
`cleanupUnavailable` and `cleanupMisconfigured` respectively. The registry
miss is upgraded from `slog.Warn` to `slog.Error` — it is the one case where
a real ingress host and TLS entry survive a successful-looking delete.
`DeleteDomain` writes `"ingress_cleanup": string(outcome)` in a single
response path, adding `workflow_name` only for `cleanupSubmitted`. HTTP
status, the row-deletion contract and the keep-the-row-on-submit-error
contract are all unchanged.

### 2. `internal/domains/store.go` (item 3)

Add a functional index. Following `internal/audit/postgres.go`'s precedent
rather than appending to `domainSchema`, so a failure to build the index on
an existing deployment cannot take mctl-api's startup down:

```go
// Separate Exec, not part of domainSchema: ListByTeam compares
// lower(team)/lower(service), which cannot use custom_domains_team
// (team, service). A failure here costs an index, not a startup — the
// query still returns correct rows, just via a sequential scan.
if _, err := pool.Exec(ctx,
    `CREATE INDEX IF NOT EXISTS custom_domains_team_lower
     ON custom_domains (lower(team), lower(service))`); err != nil {
    slog.Warn("domains store: could not create custom_domains_team_lower index", "error", err)
}
```

Non-CONCURRENTLY is fine here and simpler than audit's variant: the table is
tiny (tens of rows) and the index is built once at startup, so the brief
write lock is not observable. The existing `custom_domains_team` index is
left in place (see Open questions in requirements.md).

### 3. `internal/mcp/server.go`

No production change. The `listErr != nil` branch already behaves
correctly; item 5 is purely a missing test (see tasks T5).

### 4. Tests

- `fakeDomainExecutor` gains a `submittedTeams []string` (or a
  `submittedTeam string`) field recording `Submit`'s `namespace`/team
  argument, so item 1 becomes assertable. Existing tests are unaffected
  because the field is additive.
- New `TestDeleteDomain_NormalizesSubmitTeamArgument`: a legacy row created
  via `store.Create` with `Team: "Labs"`, promoted to `StatusActive`, then
  deleted; asserts the recorded team argument is `labs`.
- New `TestResolveDomainForMutation_MixedCaseRowWithoutTeamParam` (exercised
  through `DeleteDomain` with no `?team=`): legacy `Labs` row, caller in
  group `labs`, expects 200 rather than today's 404.
- New `TestListByTeam_MixedCaseStoredRow` in `internal/domains/store_test.go`:
  `s.Create(ctx, newDomain("Labs","Svc", ...))` then
  `ListByTeam(ctx, "labs", "svc")` returns it — the `lower()` comparison
  against a genuinely mixed-case stored row that
  `TestDomainLifecycle_MixedCaseTeamRoundTrips` never reaches (that test goes
  through `AddDomain`, which lowercases on write).
- New `TestRemoveCustomDomain_NotesFailedList` in `internal/mcp/server_test.go`:
  backend returns 500 for `GET /api/v1/domains`, 200 for the execute path;
  asserts the fallback fires and the result text contains "could not consult
  the domains registry".
- `TestDeleteDomain_FailedRowStillSubmitsTeardown` gains the params and
  `ingress_cleanup == "workflow-submitted"` assertions (item 6).
- Doc comment on `TestDeleteDomain_SkipsTeardownForPendingRow` rewritten to
  describe the real gate (item 7).
- The three existing tests asserting `ingress_cleanup == "skipped"`
  (`TestDeleteDomain_SkipsTeardownForPendingRow` -> `not-required`,
  `TestDeleteDomain_NilExecutorSkipsCleanup` -> `unavailable`) are updated,
  and a new `TestDeleteDomain_MissingOperationIsMisconfigured` covers the
  third value with a `Registry` that has no `remove-custom-domain` entry.

Nothing here adds or removes an MCP tool, so `server_test.go`'s tool-count
expectation (per `CLAUDE.md`) is unchanged.

## Alternatives

1. **Normalize `d.Team`/`d.Service` once, at the top of
   `resolveDomainForMutation`, and mutate the loaded `*domains.Domain`.**
   Would fix items 1 and 2 in one line and prevent any future call site from
   getting it wrong. Dropped: the struct is also serialized straight back to
   callers (`domainResponseFor`, `UpdateDomainStatus`), so silently
   rewriting it would change what a caller sees for a legacy row — a
   behaviour change disguised as a normalization fix, and one that reads as
   though the stored row was migrated when it was not.

2. **Actually migrate the data: `UPDATE custom_domains SET team=lower(team),
   service=lower(service)`, then revert `ListByTeam`/`Create`/
   `VerifyDomainByName` to exact comparison and keep the plain
   `(team, service)` index.** This is the cleanest end state and would make
   items 1, 2 and 3 disappear rather than be patched. Dropped: #269
   deliberately chose comparison over migration, the repo has no migration
   framework (every store auto-creates its schema in its constructor), and a
   one-shot `UPDATE` in a constructor that runs on every pod start is a worse
   artifact than a functional index. Worth revisiting as its own proposal.

3. **Add a boolean `cleanup_required`/`cleanup_ran` pair instead of a
   four-valued `ingress_cleanup` string.** More machine-friendly. Dropped:
   it changes the response shape (`map[string]string` becomes mixed-type),
   whereas widening the existing string's vocabulary keeps the shape and the
   `"workflow-submitted"` value byte-identical, and the MCP tool relays the
   body verbatim without parsing.

4. **Put the new index in `domainSchema` alongside the existing two.**
   Simplest diff. Dropped in favour of the separate warn-on-failure `Exec`
   because `domainSchema` failure is fatal to `NewStore` (`pool.Close()` +
   error return), which would turn a botched index build on a live database
   into an mctl-api startup failure. `internal/audit/postgres.go` already
   solved this exact problem the other way.

## Platform impact

- **Migrations.** One additive index, created idempotently at store
  construction (`CREATE INDEX IF NOT EXISTS`). No column, constraint or data
  change. Rollout is the normal mctl-api image bump; the index appears the
  first time a new pod constructs the store.
- **Backward compatibility.** The `ingress_cleanup` value `"skipped"`
  disappears from responses, replaced by `not-required` / `unavailable` /
  `misconfigured`. A repo-wide grep finds `"skipped"` only in
  `internal/api/handlers_domains.go` and its own tests; the MCP tool passes
  the delete body through untouched, and `internal/openapi/openapi.yaml`
  does not describe the domains routes at all. Risk is therefore limited to
  an out-of-repo consumer string-matching `"skipped"` — mitigated by calling
  the change out explicitly in the PR body and CHANGELOG.
  `"workflow-submitted"`, `status`, `workflow_name` and every HTTP status
  code are unchanged.
- **Behaviour change (item 2).** A legacy mixed-case row that previously
  404'd on `DELETE`/`verify` without `?team=` now resolves. This widens
  reachability, so it deserves a careful read: it only ever grants access
  when `normalizeIdentifier(d.Team)` matches a group the caller already has,
  and group membership is canonical lowercase in practice, so it cannot
  grant a caller access to a team they are not in. The 404-not-403
  non-disclosure property is preserved.
- **Resource impact.** One extra index on a table with tens of rows:
  negligible storage, negligible write amplification, and it removes a
  sequential scan from every `GET /api/v1/domains` call.
- **Risks + mitigations.**
  - *Risk:* the `misconfigured` path is upgraded to `slog.Error` and could
    become noisy if some environment legitimately lacks the operation.
    *Mitigation:* it is emitted only on an actual delete of an
    active/verified/failed row with an `Executor` configured — a rare
    combination, and one an operator genuinely wants to see.
  - *Risk:* the new Postgres-backed tests are `TEST_DATABASE_URL`-gated and
    skip in CI (the whole domains suite already does).
    *Mitigation:* run them locally against an ephemeral Postgres before
    merge and say so in the PR; the MCP test (item 5) needs no database and
    does run in CI.
  - *Risk:* changing `triggerRemoveCustomDomain`'s signature touches the one
    caller and every test that constructs it. *Mitigation:* it is an
    unexported method with exactly one caller (`DeleteDomain`); `go vet` and
    the compiler catch any miss.
