# Design: issue-268-custom-domains-5-non-blocking-review-fin

## Current state

Read in the clone at `mctlhq/mctl-api` (commit under review: post-`e81215b`).

**Registry and verification.** `internal/domains/store.go` is the Postgres
system of record: table `custom_domains` with `CREATE UNIQUE INDEX
custom_domains_domain ON custom_domains (domain)` (line 51) and statuses
`pending|verified|active|failed` (`types.go:24-30`). `internal/domains/verify.go`
implements `Verifier.Verify`: it checks the TXT challenge
`_mctl-challenge.<domain>` first (line 109-118), then falls back to a CNAME
comparison:

```go
cname, err := v.resolver.LookupCNAME(ctx, d.Domain)
if err == nil && strings.TrimSuffix(cname, ".") == strings.TrimSuffix(cnameTarget, ".") {
```

(`verify.go:122-123`). That comparison is byte-exact on both sides. DNS answers
are case-insensitive and resolvers routinely echo the queried case, and
`cnameTarget` is built by `Handlers.cnameTarget` as
`fmt.Sprintf("%s-%s.%s", team, service, h.platformDomain())`
(`handlers_domains.go:60-62`) from stored `team`/`service` values that `AddDomain`
only `TrimSpace`s (`handlers_domains.go:206-207`) — never lowercases. So a row
stored as `Labs`/`svc` builds `Labs-svc.mctl.ai` and can never equal a lowercase
answer. The failure mode is benign but misleading: TXT is checked first, so the
user is told "create a TXT record" rather than being falsely verified. The same
class of bug was already fixed twice in this file — `platformDomain()`
normalizes via `normalizeHostname` (line 64-73) and `isPlatformDomain`
lowercases the host (line 78-82) — so this is the third instance of a pattern
the PR already established.

**Response shape.** `domainResponse` embeds `*domains.Domain` and adds
`challenge_record` / `challenge_value` / `cname_target`
(`handlers_domains.go:44-49`); `domainResponseFor` (line 51-58) computes all
three unconditionally, including for `active` rows. `ListDomains` maps every row
through it (line 176-179), which is why an `active` domain is listed with a
challenge it no longer needs.

**Verify entry points.** `VerifyDomain` (by id, line 311) resolves through
`resolveDomainForMutation` (line 269) — admin bypass, `?team=` gate, 404-not-403
for cross-team ids. `VerifyDomainByName` (line 330) is the one the
`add-custom-domain` Argo workflow calls; after `GetByDomain` it applies an extra
gate `if d.Team != req.Team || d.Service != req.Service` (line 372). Both funnel
into `verifyAndRespond` (line 384), which calls `MarkVerified` on a positive
verdict.

**Test coverage today** (`internal/api/handlers_domains_test.go`, 704 lines,
Postgres-gated by `TEST_DATABASE_URL`): `negativeResolver` (line 452) is wired
into nearly every verify test; `cnameResolver` (line 622) exists solely for
`TestVerifyDomain_PositiveVerdictMarksVerified` (line 638) — the only positive
verdict test, and it is CNAME-only, by id. `VerifyDomainByName` has only the
negative-verdict test (line 463) and the whitespace-trim test (line 498), so its
`d.Team/d.Service` gate is never exercised on a matching row.
`TestListDomains_FiltersByTeamAndAccess` (line 376) asserts only
`strings.Contains(body, "list.example.com")` — true of the raw `[]domains.Domain`
shape too, so `domainResponseFor` is unpinned at the list level.
`internal/domains/verify_test.go` has five unit tests (TXT match, wrong token,
CNAME fast path, Cloudflare-proxied, neither) and no case-variation test.

**Delete paths.** `DeleteDomain` (`handlers_domains.go:408-430`) resolves the row
and calls `Store.Delete` — nothing else. The MCP tool
`mctl_remove_custom_domain` (`internal/mcp/server.go:1489-1530`) does the
opposite: it POSTs `/api/v1/operations/remove-custom-domain/execute` and never
touches the registry. So today:

- API `DELETE` → row gone, hostname still in `ingress.hosts` /
  `ingress.tls[].hosts`, unique index freed for another team to claim.
- MCP remove → ingress cleaned, orphan registry row still holding the unique
  index and still listed as the team's domain.

Neither path is a complete teardown. `mctl_verify_domain`
(`server.go:1532-1624`) is the counter-example the issue points at: it triggers
`add-custom-domain` server-side of the verification and documents that trigger
explicitly in its tool description.

**Available machinery.** `Options.Executor` (`internal/api/router.go:45`, typed
`WorkflowExecutor` in `interfaces.go`) exposes
`Submit(ctx, op, params, userID, namespace)`; `Options.Registry`
(`router.go:41`) resolves operations by name (`handlers_write.go:40`);
`h.logAudit` (`internal/api/clientmeta.go:171`) records the audit entry.
`internal/operations/executor.go:92-100` already forces `add-custom-domain` and
`remove-custom-domain` into the `argo-workflows` namespace regardless of tenant,
and `registry.go:363-375` declares `remove-custom-domain` with parameters
`team_name`, `service_name`, `domain` (team/service constrained to
`^[a-z0-9][a-z0-9-]{0,30}$` — i.e. the workflow layer already requires the
lowercase form the registry does not enforce).

## Proposed solution

Five focused changes, all inside `internal/domains`, `internal/api`, and
`internal/mcp`. No schema migration.

### 1. Case-insensitive CNAME comparison and lowercase identifiers

In `internal/domains/verify.go`, replace the byte-exact comparison with

```go
if err == nil && strings.EqualFold(strings.TrimSuffix(cname, "."), strings.TrimSuffix(cnameTarget, ".")) {
```

Defense in depth on the other side: add a small helper in
`handlers_domains.go` — `normalizeIdentifier(s string) string { return
strings.ToLower(strings.TrimSpace(s)) }` — and use it for `req.Team` /
`req.Service` in both `AddDomain` (replacing the bare `TrimSpace` at lines
206-207) and `VerifyDomainByName` (lines 351-352). Lowercasing before
`user.HasTenantAccess(req.Team)` is intentional: tenant/group names are lowercase
DNS-safe strings platform-wide (`create-tenant`'s own parameter pattern), so this
only makes previously-failing spellings work.

Because rows written before this change may hold mixed-case values, the
`VerifyDomainByName` ownership gate becomes case-insensitive too:

```go
if !strings.EqualFold(d.Team, req.Team) || !strings.EqualFold(d.Service, req.Service) {
```

This keeps legacy rows reachable without a data migration. The gate stays a 404
(never a 403) so it still cannot disclose which team owns a hostname.

### 2-4. Handler tests and honest challenge fields

Add to `internal/api/handlers_domains_test.go`:

- `txtResolver` stub (mirroring the existing `cnameResolver`) whose `LookupTXT`
  returns a value captured from the `AddDomain` response. `AddDomain` already
  returns `challenge_value` (`handlers_domains.go:46-47`), so the test decodes it
  from the recorder body — no reaching into the store for the random token.
  Test `TestVerifyDomain_TXTPathMarksVerified` asserts `verified: true`,
  `method: "txt"`, and a persisted `status=verified` + non-nil `verified_at`.
- `TestVerifyDomainByName_HappyPathMarksVerified` — same TXT stub, driven
  through `POST /api/v1/domains/verify`, pinning the endpoint the Argo workflow
  calls.
- `TestVerifyDomainByName_ServiceMismatchNotFound` — registers under
  `labs`/`svc`, verifies with `service: "other"`, asserts 404. This is the gate
  at line 372, currently unpinned in the matching direction.
- `TestListDomains_IncludesChallengeForPending` — asserts `challenge_record`,
  `challenge_value` and `cname_target` appear in the list body (decode into
  `map[string][]map[string]any` and check keys, not `strings.Contains`, so the
  assertion cannot pass accidentally).
- `TestListDomains_OmitsChallengeForActive` — flips a row to `active` via
  `UpdateDomainStatus` with `auth.NewServiceUser()` (the pattern at line 539)
  and asserts the two challenge keys are absent while `cname_target` remains.

The gating itself is one branch in `domainResponseFor`:

```go
func (h *Handlers) domainResponseFor(d *domains.Domain) domainResponse {
    resp := domainResponse{Domain: d, CNAMETarget: h.cnameTarget(d.Team, d.Service)}
    // Challenge fields describe outstanding work. A verified/active row has
    // already proven ownership, so echoing its challenge back invites the
    // reader to think something is still pending.
    if d.Status == domains.StatusPending || d.Status == domains.StatusFailed {
        resp.ChallengeRecord = domains.ChallengeRecord(d.Domain)
        resp.ChallengeValue = domains.ChallengeValue(d.VerificationToken)
    }
    return resp
}
```

`failed` is included because a failed row still needs the tenant to fix DNS and
retry. The struct fields already carry `omitempty`, so the wire shape simply
loses two keys — additive-compatible for any consumer that treats them as
optional. In `internal/domains/verify.go` nothing changes: `Result` always
returns `expected_record` / `expected_value`, so a caller that wants the
challenge for any row can still get it from a verify call.

Also add `TestVerify_CNAMEFastPath_CaseInsensitive` to
`internal/domains/verify_test.go` (uppercase answer, uppercase target, trailing
dot) — the unit-level pin for change 1.

### 5. One complete teardown path

Make `DeleteDomain` the single place that tears a domain down, and point the MCP
tool at it.

`DeleteDomain` gains a pre-delete step, extracted as
`triggerRemoveCustomDomain(ctx, r, d) (workflowName string, skipped bool, err error)`:

1. If `h.opts.Executor == nil || h.opts.Registry == nil`, return
   `skipped = true` (unit tests and any deployment without an executor keep
   today's behavior; `TestDeleteDomain_OwnTeamSucceeds` continues to pass
   unchanged).
2. Otherwise look up the `remove-custom-domain` operation via
   `h.opts.Registry.Get("remove-custom-domain")` and
   `h.opts.Executor.Submit(ctx, op, map[string]string{"team_name": d.Team,
   "service_name": d.Service, "domain": d.Domain}, user.ID, d.Team)`.
3. Record an audit entry through `h.logAudit` with
   `Operation: "remove-custom-domain"` and the returned workflow name, matching
   how `ExecuteOperation` audits submissions (`handlers_write.go:230-238`).

**Ordering is workflow-first, delete-second.** If `Submit` fails, the handler
returns 500 and leaves the row intact: the registry then still claims the
hostname that ingress still declares, which is the consistent state. The
opposite order would reproduce exactly the orphan the issue describes. The
residual window — workflow submitted, `Store.Delete` then fails — leaves a row
whose ingress entry is being removed; the response says so, and a retried DELETE
is safe because the `remove-custom-domain` workflow is a no-op on a hostname it
no longer finds.

Response body becomes:

```json
{"status": "deleted", "ingress_cleanup": "workflow-submitted", "workflow_name": "remove-custom-domain-abc123"}
```

or `{"status": "deleted", "ingress_cleanup": "skipped"}` when no executor is
configured. `status: "deleted"` is preserved so existing callers do not break.

On the MCP side, `toolRemoveCustomDomain` (`server.go:1511`) changes its handler
to: `GET /api/v1/domains?team=&service=`, find the entry whose `domain` matches
(case-insensitively, after trimming a trailing dot — reusing the same
normalization rule), then `DELETE /api/v1/domains/{id}?team={team}`. If no
matching row exists (a legacy hostname registered through the old Backstage
proxy), fall back to the current
`POST /api/v1/operations/remove-custom-domain/execute` so nothing that works
today stops working. The `requireConfirm` guard and the destructive-hint
annotation stay. The tool description gains the trigger contract sentence, in
the style `mctl_verify_domain` already uses: "Removes the registry row AND
triggers the remove-custom-domain workflow (ingress hosts + TLS entries) in one
call." The Go doc comment on `DeleteDomain` states the same contract.

`internal/mcp/server_test.go`'s `operationToTool` parity fixture
(line 843-861) still holds: `remove-custom-domain` remains mapped to
`mctl_remove_custom_domain`; the operation is now submitted server-side by the
handler the tool calls. No MCP tool is added or removed, so the tool-count
expectation in `server_test.go` is unaffected.

## Alternatives

1. **Document-only for finding 5** (the issue's second option): leave
   `DeleteDomain` as-is and just say teardown is the caller's responsibility.
   Cheapest and zero-risk, but it leaves the unique-index hazard — team A
   deletes, team B registers and verifies the same hostname while team A's
   ingress still declares it — as a documented footgun rather than a fixed one.
   Since the machinery (`Executor` + `Registry`) is already in `Options` and
   already used by `handlers_write.go`, the fix is small enough not to trade
   away.
2. **Lowercase `team`/`service` in the store plus a backfill migration**
   (`UPDATE custom_domains SET team = lower(team), service = lower(service)`)
   instead of `EqualFold` comparisons. Cleaner long-term data, but it needs a
   migration step in a repo whose `domains` schema is auto-created idempotently
   at startup (`store.go:66`) with no migration framework, and it would still
   need the `EqualFold` compare for the rollout window. Dropped in favour of
   normalize-on-write plus tolerant compare; a backfill can follow later
   without touching this design.
3. **Trigger `remove-custom-domain` from the MCP tool only, keeping the API
   handler registry-only.** Preserves the API's narrow contract, but every other
   caller of `DELETE /api/v1/domains/{id}` (portal, curl, future automation)
   would still leave ingress behind — the same class of gap that made the
   Backstage proxy unusable. Putting the trigger behind the API keeps the
   guarantee at the system-of-record layer where it belongs.
4. **Delete the row first, then fire the workflow asynchronously.** Faster
   response, but it makes the failure mode the exact orphan the issue is about.
   Rejected.

## Platform impact

- **Migrations:** none. `custom_domains` is unchanged; the auto-created schema in
  `store.go:37-53` is untouched.
- **Backward compatibility (API):** `DELETE /api/v1/domains/{id}` keeps
  `{"status":"deleted"}` and adds two fields — additive.
  `GET /api/v1/domains` and `POST /api/v1/domains` stop emitting
  `challenge_record`/`challenge_value` for `verified`/`active` rows; both fields
  are already `omitempty`, so the change is "an optional field is now absent
  when meaningless". `internal/mcp/server.go:1561-1567` decodes only
  `id`/`domain`/`status` from the list, so `mctl_verify_domain` is unaffected.
- **Backward compatibility (behavior):** verification becomes *more* permissive
  (a case-varying CNAME that previously fell through to TXT now verifies) — it
  never accepts a target it should not, because `EqualFold` on a full hostname is
  the DNS-correct comparison.
- **Resource impact:** one extra Argo workflow submission per domain deletion
  (`remove-custom-domain` is `RiskLow`, and it already ran on every MCP-driven
  removal today). No new dependency, no new env var.
- **Risks + mitigations:**
  - *A consumer relies on challenge fields for non-pending rows.* Mitigation:
    the gate is a single `if` in `domainResponseFor`, trivially revertable; the
    verify endpoints still return `expected_record`/`expected_value`
    unconditionally.
  - *A deployment without `Options.Executor` silently skips ingress cleanup.*
    Mitigation: explicit `ingress_cleanup: "skipped"` in the response plus a
    `slog.Warn`, so it is visible rather than assumed.
  - *Lowercasing `team` breaks a tenant whose group name is mixed-case.*
    Mitigation: no such tenant can exist — `create-tenant`'s registry pattern is
    `^[a-z0-9][a-z0-9-]{0,30}$` and namespaces are `team-{name}`; existing rows
    stay reachable via the `EqualFold` gate.
  - *Postgres-gated tests do not run in CI* (`TEST_DATABASE_URL` unset, see
    `handlers_domains_test.go:45-50`), so the new handler tests only guard
    locally/on-demand. Mitigation: the case-insensitivity pin also lands as a
    pure unit test in `internal/domains/verify_test.go`, which always runs, and
    the `DeleteDomain` nil-executor path is asserted in the always-running
    `TestDomainRoutes_NilStore503` style with a fake executor.
