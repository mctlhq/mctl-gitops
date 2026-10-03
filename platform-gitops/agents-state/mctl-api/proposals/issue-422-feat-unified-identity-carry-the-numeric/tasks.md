# Tasks: issue-422-feat-unified-identity-carry-the-numeric

Scope is slice B of mctl-api#374 only. This issue must not close #374, and
must not touch slice C (refresh regroup), slice D (audience flag day) or
mctl-api#376 (agent actor). Line numbers below are from `main` at `7e5c1c4`
and must be re-read before editing.

- [ ] 1. Add the optional claim: extend `jwtPayload`
      (`internal/auth/oauth_server.go:1453-1459`) with
      `GitHubID int64 \`json:"ghid,omitempty"\`` and a doc comment stating it
      is the numeric GitHub user id of `sub`, optional, and that `sub` stays
      the login. — DoD: `go build ./...` and `go vet ./...` clean; a token
      minted with id 0 serializes to a payload with no `ghid` key
      (asserted in T1).

- [ ] 2. Thread the id through the mint path (depends on 1):
      `IssueCode(login string, githubID int64, clientID, redirectURI, codeChallenge string, groups []string)`
      storing `GitHubID` on `authCodeEntry` (`:1508-1515`);
      `IssueJWT(login string, githubID int64, groups []string)` setting the
      claim; `IssueRefreshToken(login string, githubID int64, groups []string, clientID string)`
      recording it on the in-memory `refreshTokenEntry` (`:1524-1530`);
      `ExchangeCode` (`:1266-1290`) passing `entry.GitHubID` to both.
      `RefreshAccessToken` (`:1339-1401`) passes `entry.GitHubID` on the
      in-memory path and the id returned by `RefreshStore.Rotate` on the
      store path (task 2a). — DoD: package compiles; no change to any
      group-resolution call (`groupsForSession`, `sessionGroups`,
      `ResolveGroups`) beyond the mechanical signature update.

- [ ] 2a. Persist the id in the refresh store (depends on 2; owner decision
      2026-09-30): in `internal/auth/refreshstore/postgres.go` append
      `ALTER TABLE oauth_refresh_tokens ADD COLUMN IF NOT EXISTS github_id BIGINT;`
      to the `schema` constant (nullable, no default, no backfill, no index).
      Change `Store` (`store.go`) to
      `Insert(rawToken, login string, githubID int64, clientID string, groups []string, expiresAt time.Time) error`
      and `Rotate(...) (login string, githubID int64, groups []string, err error)`.
      `Insert` writes `NULL` for `githubID <= 0`. `Rotate` reads `github_id`
      from the presented row, copies it into the successor INSERT, and
      returns it; the lost-response grace path returns the child row's
      value; every error path returns `0`. `IssueRefreshToken` passes the id
      to `Insert`; `RefreshAccessToken` passes the id from `Rotate` to
      `IssueJWT`. Update every in-repo `Store` fake. — DoD: `go test
      ./internal/auth/refreshstore/...` (Postgres-backed) passes with T9;
      the schema constant applied twice is a no-op; no `SELECT *` introduced.

- [ ] 3. Use `ValidateIdentity` at the callback (depends on 2):
      `internal/api/oauth_handlers.go:254` becomes
      `login, ghID, err := o.GitHubValidator.ValidateIdentity(...)`, and
      `ghID` is passed to `IssueCode` at `:265`. Error handling, status codes
      and log messages unchanged. — DoD: the only behavioural difference on
      this handler is the extra claim on the issued token; `GitHubValidator`
      itself is unmodified.

- [ ] 4. Register the metric (depends on 1): unlabelled
      `oauth_jwt_without_github_id_total` counter in `internal/auth`, built
      with `prometheus.NewCounter` and registered in `init()` via
      `MustRegister`, following `internal/auth/federation.go:318-355` and
      `internal/principals/resolver.go:52-57`. — DoD: the counter is visible
      on `/metrics` at zero after boot; `go test ./internal/auth/...` does
      not panic on duplicate registration.

- [ ] 5. Populate the identity at validation (depends on 2, 4): in
      `ValidateJWT` (`:1421-1434`) set `u.githubID = payload.GitHubID` when
      it is `> 0`, otherwise increment
      `oauth_jwt_without_github_id_total`. Keep `sub` as the value passed to
      `NewGitHubUser` and to `groupsForSession`. No new exported setter —
      the field stays unexported (`internal/auth/oidc.go:86`). — DoD:
      `ValidateJWT` on a token with `ghid` yields a `*User` whose
      `Identity()` is `{github, "<id>", <login>, human}`; without `ghid` it
      yields the login-only identity and the counter moves by exactly one.

- [ ] 6. Teach the local-OAuth federation provider to prefer `ghid`
      (depends on 5): `localOAuthProvider.Verify`
      (`internal/auth/provider_localoauth.go:49-58`) derives its `Verified`
      from `u.Identity()` instead of hand-building the login-only shape, and
      refuses defensively if the identity is absent or not
      `ProviderGitHub`. Update the `Name()` doc comment to mention that the
      subject is now the numeric id when the token carries one. — DoD: with
      the registry active, a `ghid` token authenticates to a `*User` with the
      numeric id (via `userFromVerified`, `oidc.go:751-758`) and
      `federation_provider_contract_violations_total` stays zero; without
      `ghid`, behaviour is byte-identical to before.

- [ ] 7. Update `docs/federation.md` (depends on 3, 5, 6): describe the
      `ghid` claim under the local-OAuth provider (optional, `omitempty`,
      `sub` still the login, login-only fallback for older tokens); add the
      `oauth_jwt_without_github_id_total` row to the metrics table
      (`:246-258`) with the "counted per validation, not per token" caveat
      and the note that it decays to zero as pre-change refresh families
      (`github_id` `NULL`) expire; describe the new
      `oauth_refresh_tokens.github_id` column;
      remove slice B from the not-covered list (`:280`), leaving slices C
      and D. — DoD: no statement in the document contradicts the code;
      slice C and D wording untouched.

- [ ] 8. Update all in-repo call sites and run the gates (depends on
      2, 2a, 3, 5, 6): `internal/auth/oauth_server_test.go`,
      `internal/auth/refreshstore/postgres_test.go`,
      `oauth_server_groups_test.go`, `oauth_clientstore_test.go`,
      `oauth_registry_expiry_test.go`, `federation_test.go:721`. — DoD:
      `go build ./...`, `go vet ./...`, `golangci-lint run` and
      `go test ./...` all pass; `internal/mcp/server_test.go`'s tool-count
      expectation is unchanged.

## Tests

- [ ] T1. `ghid` round-trip and omission (`internal/auth`): `IssueJWT` with
      id `4242` produces a payload whose decoded `ghid` is `4242` and whose
      `sub` is the login; `IssueJWT` with `0` produces a payload whose raw
      JSON contains no `ghid` substring. This is the mutation-verified
      regression pin required by the issue: dropping `GitHubID` from
      `IssueJWT`'s payload must fail it. Verify the mutation manually by
      temporarily removing the field assignment and confirming a red test.

- [ ] T2. T7 from the parent design record, part 1 — no lookup: a JWT with
      `ghid` validated through the federation registry yields
      `(github, "<id>", display=login)`, and a `principals.Resolver` built
      with a counting `GitHubIDLookup` records zero calls and one
      `Provision` for subject `"<id>"` (mirror
      `internal/principals/resolver_test.go:176-193`).

- [ ] T3. T7 part 2 — legacy token: a JWT minted without `ghid` (construct it
      by minting with id `0`, i.e. the pre-change shape) yields the
      login-only identity, resolves through `ResolveGitHubLogin`, and
      increments `oauth_jwt_without_github_id_total` by exactly one
      (read via `testutil.ToFloat64`).

- [ ] T4. Both middleware chains agree: the same `ghid` token authenticated
      with the registry active and with `MCTL_FEDERATION_DISABLED=true`
      produces equal `*User` values and equal `Identity()` results —
      extend the existing `TestCharacterization_LocalOAuthJWT`
      (`internal/auth/federation_test.go:718-732`) rather than adding a
      parallel harness.

- [ ] T5. Callback wiring: `handleOAuthGitHubCallback` against a stub GitHub
      `/user` endpoint returning `{"login":"alice","id":4242}` issues a code
      whose exchanged access token carries `ghid=4242`; a GitHub validation
      failure still produces the same 502 and no code.

- [ ] T6. Resolution parity for the two store edge cases: a revoked
      `external_identities` row refuses the request the same way with and
      without `ghid`, and a login whose `(github, <id>)` row already exists
      resolves to the same principal id on both paths (extend
      `internal/principals/store_test.go` / `resolver_test.go` fixtures).

- [ ] T7. Refresh keeps `ghid` on both paths: an in-memory refresh exchange
      and a `RefreshStore` refresh each mint a new access token carrying the
      same `ghid` as the first token; a `RefreshStore` family whose row has
      `github_id` `NULL` mints without `ghid` and increments the counter on
      the next validation; every existing test in
      `oauth_server_groups_test.go` (degraded grace, fail-closed, snapshot
      non-overwrite) still passes.

- [ ] T9. Postgres refresh store (`internal/auth/refreshstore/postgres_test.go`):
      (a) `Insert` with id `4242` then `Rotate` returns `4242`, and a second
      `Rotate` of the successor returns `4242` again (the id is copied, not
      only read — mutation pin: dropping `github_id` from the successor
      INSERT must fail this); (b) the lost-response grace path returns the
      child's `4242`; (c) `Insert` with `0` stores `NULL` and `Rotate`
      returns `0`; (d) a row inserted by raw SQL without the column (a
      pre-change row) rotates successfully and returns `0`; (e) applying the
      schema constant twice succeeds.

- [ ] T8. Full gates: `go test ./...` and `cd e2e && go test -v` (e2e only if
      the environment for it is available; it is not expected to be affected).

## Rollback

- Code: `git revert` the single PR. After a revert every token in flight is
  handled by the pre-existing login-only path again. The nullable
  `oauth_refresh_tokens.github_id` column stays: the reverted code names its
  columns explicitly in every `INSERT`/`SELECT`, so it ignores the column and
  its inserts leave it `NULL`. Do not drop it as part of a rollback. No Helm
  value, no configuration flag to flip.
- Partial rollback without a revert: none is needed and none is added
  deliberately. A feature flag for one optional claim would have to be read
  at both mint and validate time and would create a fourth token shape to
  reason about; the login-only path is itself the always-available fallback.
- Operational check after deploy: `oauth_jwt_without_github_id_total` should
  stop growing for freshly logged-in clients and decay towards zero as
  pre-change refresh families expire (≤ 30 days),
  `federation_provider_contract_violations_total{provider="github"}` must
  stay at zero, and `principal_resolution_failed_total` must not rise. A rise
  in the last one is the signal to revert.
