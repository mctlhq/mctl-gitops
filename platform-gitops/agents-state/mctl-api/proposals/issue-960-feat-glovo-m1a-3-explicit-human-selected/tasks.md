# Tasks: issue-960-feat-glovo-m1a-3-explicit-human-selected

- [ ] 0. Confirm slice 1 (Glovo audience, `GlovoResource`, `IsGlovoAudience`, gate) and slice 2 (`internal/glovo` refusal enum, allowlist DDL) merge status. If either is absent, add the closed interfaces/accessors named in design.md sections 4-5 so this slice compiles alone. — DoD: build passes on main with no slice 1/2 code. A short note in the PR says which symbols are temporary shims.
- [ ] 1. `internal/auth/teamgrant`: `Store` interface, `PostgresStore` (inline DDL for `oauth_team_grants`, partial unique index), `MemoryStore`, and `Create`/`Activate`/`Check`/`Revoke*` with a typed `ErrGrantInvalid` distinct from store errors. — DoD: unit tests for supersede-on-create, expiry, mismatch, and revoke by family/principal; `go vet` and golangci-lint clean.
- [ ] 2. `refreshstore`: add `Session.TeamGrantID`, column `team_grant_id`, and carry it through `RotateIf` and the in-memory store (depends on 1). — DoD: postgres and memory tests show the id survives rotation; old rows read as "".
- [ ] 3. `internal/glovo/allowlist.go`: `glovo_pilot_allowlist` DDL (identical to the #953 design, `IF NOT EXISTS`), `IsAllowlisted`, `Add`, `Remove`. Admin-only `PUT|DELETE /api/v1/glovo/pilot/{tenant}/principals/{prn}` in `router.go`, with an OpenAPI entry. — DoD: no route or method accepts a tenant without a principal; the DB CHECK rejects an empty or non-`prn_` principal; 404/503 tenant lookup semantics are tested.
- [ ] 4. `internal/glovo/scope`: `TeamEligibility` (membership ∩ allowlist minus `GLOVO_NON_SELECTABLE_TENANTS`) and `Resolver.Resolve(ctx, *auth.User)` implementing steps 1-7 of design.md section 4 with the closed refusal enum, plus `RequireScope` middleware (depends on 1, 3). — DoD: the resolver has no parameter other than ctx and user; a failing read returns 503, never a refusal code.
- [ ] 5. Token claims: `jwtPayload.TeamGrant`/`SelectedTenant` (`tgr`/`stn`); `issueJWTFor` sets them only for the Glovo audience; `verifyAccessToken` requires single-entry `aud` for Glovo; `User.TeamGrant()` accessor (depends on 0). — DoD: claims are absent on API and support tokens, and ignored if forged onto them.
- [ ] 6. Consent: in `finishAuthorization`, a Glovo resource always goes to `requestTeamConsent`; the page shows an unselected radio list; `takeConsentDecision` validates exactly one `tenant` against the recomputed eligibility, creates the grant and calls `issueGrant` with `TeamGrantID`; zero eligible -> `access_denied`; `handleOAuthAuthorize` refuses `tenant`/`selected_tenant` params on Glovo flows; the audit entry includes tenant and grant id (depends on 1, 4). — DoD: handler tests for every client kind.
- [ ] 7. Code exchange and refresh: `authCodeEntry` carries the grant; `ExchangeCodeForResource` checks and activates the grant, and refuses a Glovo code without one; the `RefreshAccessTokenForResource` `accept` callback checks the grant and live eligibility; `handleOAuthToken` refuses team parameters on Glovo sessions (depends on 2, 4, 5, 6). — DoD: no refusal path writes a successor token; a lost eligibility revokes grant and family.
- [ ] 8. Revocation coupling: `RevokeRefreshToken`, reuse/downgrade `RevokeFamily`, `RevokePrincipalSessions` revoke the grant first and surface a grant-store failure as 503 (depends on 1, 7). — DoD: tests pin the order and the failure behaviour.
- [ ] 9. Wiring in `cmd/api/main.go`: stores, `GLOVO_NON_SELECTABLE_TENANTS` (default `admins,labs`), startup refusal when `GLOVO_MCP_RESOURCE` is set without principal mode or without a grant store; Helm values default empty; `docs/glovo-team-grant.md` (depends on 1-8). — DoD: with `GLOVO_MCP_RESOURCE` unset, the full existing test suite passes unchanged; the MCP tool count in `server_test.go` is unchanged (no new MCP tools).

## Tests
- [ ] T1. One eligible team, unselected: the consent page has no `checked` option; posting approve without `tenant` -> `access_denied`, no grant row, no code.
- [ ] T2. Multiple eligible teams: only membership ∩ allowlist teams are listed; posting a listed team issues a grant for exactly that team; posting a non-listed, foreign or repeated `tenant` -> refused, no grant.
- [ ] T3. Same team, two users: user A's grant cannot be used by B's token (principal mismatch -> `ambiguous_tenant`); A's allowlist row does not admit B (`not_in_pilot`).
- [ ] T4. Forged inputs: an `X-Mctl-Selected-Tenant` header, `?tenant=` query, `tenant`/`owner`/`namespace`/`task_queue` in the body or MCP args, and `tenant` on `/oauth/authorize` or `/oauth/token` never change the resolved scope and are refused where the contract says so. A hand-crafted JWT with `stn` but an unknown `tgr` -> `ambiguous_tenant`. `tgr`/`stn` on an API-audience token -> ignored.
- [ ] T5. Wrong audience and multi-aud: an API or support token on a Glovo route -> `not_authorized`/401; a Glovo token whose `aud` holds two entries -> rejected at verification.
- [ ] T6. Membership removed mid-session: the next resource request -> `no_tenant`; the next refresh -> `invalid_grant`, with grant and family revoked. Allowlist row removed -> `not_in_pilot` on the next request.
- [ ] T7. Refresh switching team: a team parameter on the token endpoint -> `invalid_request`; a new authorize+consent for team B supersedes team A's grant, and A's still-valid access token then fails `Check` -> `ambiguous_tenant`.
- [ ] T8. Personal scope and no `labs` default: a principal whose only membership is `labs` or `admins` sees zero eligible -> `access_denied`; a grant naming a non-selectable or non-team tenant -> `scope_unsupported`; nothing ever resolves to `labs` by default.
- [ ] T9. Expired, revoked and pending grants -> `ambiguous_tenant`; a grant/membership/allowlist store failure -> 503, and a failure on refresh spends no token.
- [ ] T10. No Telegram/surface fallback: a relayed surface identity, an agent-run token and an admin without an allowlist row all fail `Resolve`.
- [ ] T11. Revocation: RFC 7009 revoke and `RevokePrincipalSessions` revoke the grant before the family; a grant-store failure is 503, not success.
- [ ] T12. Regression: with `GLOVO_MCP_RESOURCE` unset, the existing `oauth_*_test.go` suites pass unchanged, and non-CIMD API-audience flows still skip consent.

## Rollback
Unset `GLOVO_MCP_RESOURCE` (or set `GLOVO_DISABLED`). No Glovo flow is then
possible, no grant is created or checked, and every other flow is
byte-identical to today. If code must be reverted, revert the PR. The
additive DDL (`oauth_team_grants`, `oauth_refresh_tokens.team_grant_id`,
`glovo_pilot_allowlist`) can stay in place because older code ignores it.
To revoke all live pilot sessions immediately, run
`UPDATE oauth_team_grants SET state='revoked', revoked_reason='rollback'`.
