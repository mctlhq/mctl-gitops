# Tasks: issue-1327-feat-pa-enforce-per-client-read-only-oau

- [ ] 1. Add the `pa-readonly` profile to `internal/toolprofile/toolprofile.go`.
  - Add the constant `PersonalAssistantReadonly = "pa-readonly"`.
  - Tools: `list_dialogs`, `list_folders`, `list_topics`, `get_messages` (with
    `noMedia`), `search_messages` and `get_my_identity`.
  - Register it in `profiles`.

  DoD: `toolprofile.Lookup("pa-readonly")` returns exactly those six tools, and the
  existing profile and binding tests pass.

- [ ] 2. Add the ceiling primitives to `internal/oauth/scopes.go`.
  - Add `PersonalAssistantScopeCeiling` (`telegram:dialogs:read`,
    `telegram:messages:read`).
  - Add `capToCeiling(groups, scopes, ceiling)`, which returns the intersection and
    `nil` groups.
  - Write doc comments that contrast it with `narrowGrant`.

  DoD: unit tests cover an admin set with broadcast, a lookup-tier set, an empty set
  and an unknown future scope.

- [ ] 3. Add `PersonalAssistantClientID` to `oauth.Config` and fail-closed validation
  in `oauth.New`. Depends on 1 and 2.
  - The value must be one of:
    - a preregistered `client_id`, or
    - a CIMD URL with `cfg.CIMD != nil`.
  - The value must not be:
    - `ConnectClientID`;
    - an id with the `tgdcr_` or `tgmcp_` prefix;
    - an id with surrounding whitespace.
  - A conflicting `ClientProfiles.ByClientID` binding is refused.
  - On success, inject `ByClientID[pa] = pa-readonly` into the server's copy of the
    bindings.
  - Build `s.scopeCeilings` and add `s.ceilingFor`.

  DoD: `New` returns an error for every invalid case. With an empty value it builds a
  server identical to today's.

- [ ] 4. Apply the ceiling at every grant path in `internal/oauth/server.go`. Depends on 3.
  - Grant paths: `handleTokenAuthCode` (after `narrowGrant`), `handleTokenRefresh` and
    `attemptGraceRecovery` (after `boundRefreshGrant`, before `refreshGrantStillValid`),
    and `ExchangeConnect`.
  - Make sure the stored refresh-token scope is the ceilinged set.
  - Add `ceiling_applied` and the stripped scope names to the existing grant log line.

  DoD: every `mintAccessToken` caller receives ceilinged scopes for the PA client.

- [ ] 5. Add the `mintAccessToken` invariant. Depends on 3.
  - For a ceiling client, refuse with `errCeilingViolation` if any scope is outside
    the ceiling or groups are non-empty.
  - Callers map this to `server_error` and log at ERROR.

  DoD: a direct call with admin scopes for the PA client mints nothing.

- [ ] 6. Add the requested-scope contract to `handleAuthorize`. Depends on 3.
  - For a ceiling client, a `scope` field outside the ceiling causes a redirect with
    `error=invalid_scope` (after the redirect_uri is validated). No pending entry or
    code is created.
  - An empty scope is accepted.

  DoD: tests cover asking for `admin:users`, `telegram:messages:send` and the exact
  two reads.

- [ ] 7. Add `OAUTH_PA_CLIENT_ID` in `internal/config/config.go` and wire it in
  `cmd/server/main.go`. Depends on 3.
  - Config validation: the value must be one of:
    - a preregistered id, or
    - a CIMD URL with `OAUTH_CIMD_ACCEPT` on and its host in
      `OAUTH_CIMD_ALLOWED_HOSTS`.
  - Pass the value in the `oauth.Config` literal and add it to the startup log.

  DoD: `config.Load` errors on an invalid value. Unset yields an empty value.

- [ ] 8. Documentation. Depends on 7.
  - Document `OAUTH_PA_CLIENT_ID`, the ceiling semantics and the `pa-readonly` profile
    next to the existing `OAUTH_PREREGISTERED_CLIENTS` and `MCP_CLIENT_PROFILES` docs
    (SECURITY.md, the runbook "Client tool profiles", the env tables).
  - Note in `docs/agent-runtime/personal-assistant-threat-model.md` T8 that the `tg`
    ceiling is implemented and how it is configured.
  - Update any doc or compatibility tests that enumerate env vars or profiles
    (`docs/compatibility_test.go`).

  DoD: docs CI passes. CHANGELOG is left to release-please.

## Tests

All fixtures use synthetic ids and existing personas (Alice, Bob, Carol, Dana). Run
`git grep <id>` before picking a numeric id. Tests use `newTestServer` and the real
`ResolveScopes`, `narrowGrant` and `boundRefreshGrant`.

- [ ] T1 (S1-T8, `internal/oauth`): an admin who is also a broadcast operator
  (`AdminTelegramIDs` plus `BroadcastOperatorTelegramIDs`) completes the PA
  authorization-code flow, once with an empty scope and once with the two reads.
  - The response `scope` is exactly `telegram:dialogs:read telegram:messages:read`.
  - The access-token claims carry the same two scopes, no groups, and
    `prf=pa-readonly`.
- [ ] T2 (S1-T8, refresh): run T1, then refresh, then trigger a grace-window replay.
  Every response and every rotated row stays exactly the two reads. A row seeded with
  wider stored scopes (a pre-change family) is narrowed on refresh.
- [ ] T3 (S1-T8, end to end, `internal/mcp`, following the
  `zero_admin_e2e_test.go` pattern): verify the T1 token through the real local-jwt
  provider and run it through `scopeToolFilter` and `toolAllowed`.
  - Refused: `list_telegram_identities`, `set_telegram_access`, `mint_worker_token`,
    `prepare_broadcast`, `list_broadcasts`, `get_broadcast`, `cancel_broadcast`,
    `send_message`, and every `account:manage` tool. Both `tools/list` and `tools/call`
    refuse them.
  - Allowed: the six pinned reads.
- [ ] T4 (confinement): the T1 token is refused with 403 at `/api/bridge/token` and
  `/api/mcp/worker-token`, and at one `/api/account` route, through `auth.Middleware`.
- [ ] T5 (S1-T11): the same admin principal, using a non-PA client (an implicit or DCR
  client and a different preregistered client), gets exactly today's grant on both
  exchange and refresh: the `admin:users`, `admin:broadcast` and `account:manage`
  scopes, groups present and no profile.
  - Also run the existing `scope_narrowing_test.go`, `refresh_test.go` and
    `client_profile_test.go` unchanged.
- [ ] T6 (spoofing):
  - A DCR registration whose `client_name` mimics the PA receives a generated
    client_id and no ceiling.
  - `/oauth/authorize` with the PA client_id and an unregistered redirect_uri on an
    implicit-allowlisted host is refused (`invalid_client`).
  - A code issued to a non-PA client redeemed with the PA client_id fails with
    `client_id mismatch`, and the reverse fails too.
  - A PA refresh token presented with another client_id fails, and the reverse fails
    too.
  - Requesting `admin:users` as the PA client yields `invalid_scope`.
- [ ] T7 (fail-closed config, `oauth.New` and `config.Load`). Each of these fails startup:
  - a PA id that is not preregistered;
  - the id `mctl_self_connect`;
  - an id with a `tgdcr_` or `tgmcp_` prefix;
  - an id with whitespace;
  - a CIMD URL while CIMD is off;
  - a CIMD URL whose host is not allowlisted;
  - `MCP_CLIENT_PROFILES` binding the PA client to `core-reply`.

  An unset value starts with no ceiling.
- [ ] T8 (invariant): calling `mintAccessToken` for the PA origin with admin scopes or
  with non-empty groups returns `errCeilingViolation`.
- [ ] T9 (degenerate identity): a PA grant for an identity entitled to only one read,
  or to none, reports that truthful narrower set (or no scope), never more. This is
  the server half of S1-T9 and S1-T10. The executor checks are owned by #1314.
- [ ] T10: `go vet`, `golangci-lint` and `go test ./...` are green. The tool surface
  snapshot (ADR 0007) is unchanged, since no tool is added.

## Rollback

- The change is inert until `OAUTH_PA_CLIENT_ID` is set, and no deployment sets it in
  this change. Rolling back means reverting the merge commit and releasing. No data
  migration is involved.
- If it is configured later and misbehaves, unset `OAUTH_PA_CLIENT_ID` in the
  `mctl-telegram` values. Ordinary clients are unaffected either way. PA linking (#1314)
  must stay disabled while the variable is unset, because without the ceiling the
  executor's exact-scope check fails for admin principals by design.
