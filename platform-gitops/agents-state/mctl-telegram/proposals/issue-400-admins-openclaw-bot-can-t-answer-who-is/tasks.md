# Tasks: issue-400-admins-openclaw-bot-can-t-answer-who-is

- [ ] 1. Add `TG_LOGIN_LOOKUP_ADMINS` config parsing — `internal/config/config.go`:
      add `TGLoginLookupAdmins []int64` field near `TGLoginAdmins`/`TGLoginClients`
      (`:51-52`) and populate it via `parseInt64CSV(os.Getenv("TG_LOGIN_LOOKUP_ADMINS"))`
      next to the existing two calls (`:297-298`). Document the var in
      `.env.example` with a one-line comment matching the neighboring entries'
      style.
      DoD: `go build ./...` passes; `TG_LOGIN_LOOKUP_ADMINS` parses the same
      way `TG_LOGIN_ADMINS` does (comma-separated ids, invalid entries dropped
      with a slog warning, per `parseInt64CSV`).

- [ ] 2. Wire the new allowlist into `oauth.Config` and `ResolveScopes`
      (depends on 1) — `internal/oauth/server.go`:
      - Add `LookupAdminTelegramIDs map[int64]bool` to `Config` next to
        `AdminTelegramIDs`/`ClientTelegramIDs` (`:165-172`), nil-defaulted to
        `{}` in the same block as the other two (`:347-351`).
      - Wherever `cmd/server/main.go` currently builds `AdminTelegramIDs`/
        `ClientTelegramIDs` maps from `cfg.TGLoginAdmins`/`cfg.TGLoginClients`
        to pass into `oauth.Config`, add the equivalent conversion for
        `cfg.TGLoginLookupAdmins` → `LookupAdminTelegramIDs`.
      - In `ResolveScopes` (`:666-689`), insert a branch after the
        `AdminTelegramIDs` check and before `isClientTier`:
        `if s.cfg.LookupAdminTelegramIDs[tgID] { return []string{"admin-lookup"}, []string{"admin:users"}, nil }`.
        Full-admin membership takes precedence (checked first, unchanged).
      - Update the `ResolveScopes` doc comment (`:653-665`) to describe all
        three tiers.
      DoD: a Telegram id present only in `LookupAdminTelegramIDs` resolves to
      scopes `["admin:users"]` exactly (no `telegram:*` scopes); an id in both
      `AdminTelegramIDs` and `LookupAdminTelegramIDs` resolves to the full
      admin bundle unchanged.

- [ ] 3. Skip `enable_access` MTProto provisioning for lookup-admin-only
      identities (depends on 2) — `internal/oauth/server.go`,
      `handleTelegramCallback` (`:1144-1159`): extend the routing condition so
      an identity that is lookup-admin but not full-admin is sent directly to
      `s.issueAuthCode(w, r, oc)` instead of into the `stepPhone`/
      `enableSession` flow. Existing admin/client routing must stay identical.
      DoD: a lookup-admin-only login completes without ever hitting
      `handleEnableStart`/`handleEnableCode`/`handleEnablePassword`; a full
      admin or client login is unaffected (still offered `enable_access`).

- [ ] 4. Tests (depends on 2, 3) — `internal/oauth/enable_access_test.go`:
      - Extend `TestResolveScopes_Tiers` (`:726`) with: (a) an id only in
        `LookupAdminTelegramIDs` → exactly `["admin:users"]`, groups containing
        `"admin-lookup"` (or whatever final name task 2 lands on); (b) an id in
        both `AdminTelegramIDs` and `LookupAdminTelegramIDs` → full admin
        bundle, unchanged from today.
      - Add a callback/`enable_access`-gating test asserting a lookup-admin-only
        identity's `handleTelegramCallback` issues an auth code directly and
        does not create a pending `enableSession`/`stepPhone` state, mirroring
        the existing pattern used for the "no scopes" case in that file.
      DoD: `go test ./internal/oauth/...` passes, including the new cases;
      no existing test in the package changes behavior/expectation.

- [ ] 5. (Follow-up, outside this repo — not implemented as part of this PR,
      tracked here for sequencing) Provision the dedicated Telegram lookup
      account: real phone number, one-time Telegram Login Widget sign-in (no
      MTProto phone/SMS/2FA needed for this tier per task 3). Add its
      Telegram id to `TG_LOGIN_LOOKUP_ADMINS` on the `mctl-telegram`
      deployment and redeploy. Capture its OAuth refresh token as a Vault
      secret. Add `mctl-telegram` as an MCP server in
      `mctl-gitops/platform-gitops/services/admins/openclaw/values.yaml`
      `mcp.servers`, scoped to that token.
      DoD: `list_telegram_identities` and `get_user_audit_log` are callable
      from the `admins/openclaw` agent; a manual "who is telegram id X" test
      in `mctl_admins` returns real data instead of the generic error.

- [ ] 6. (Follow-up, outside this repo, explicitly non-blocking per the
      issue) File/track the `mctl-openclaw` "no matching tool" classifier
      improvement in `agent-runner-execution.ts` (catch near line 1753,
      `GENERIC_EXTERNAL_RUN_FAILURE_TEXT` near lines 362-363) so future
      similar gaps surface a diagnosable message instead of the generic
      error. Not implemented here — different repo, different proposal.
      DoD: a tracking issue/proposal exists in the `mctl-openclaw` (or
      equivalent) proposal queue; no code change expected in this repo.

## Tests

- [ ] T1. `TestResolveScopes_Tiers` lookup-admin-only case: scopes are
      exactly `["admin:users"]`; none of `telegram:dialogs:read`,
      `telegram:messages:read`, `telegram:messages:send`,
      `telegram:messages:pin` are present.
- [ ] T2. `TestResolveScopes_Tiers` both-listed case: id in
      `AdminTelegramIDs` and `LookupAdminTelegramIDs` resolves identically to
      today's full-admin-only case.
- [ ] T3. Regression: existing `TestResolveScopes_DBRevokeOverridesEnv`
      (`:549`) and `TestResolveScopes_AutoApprove` (`:574`) still pass
      unmodified — confirms the new branch does not shadow or reorder the
      client-tier resolution path.
- [ ] T4. `enable_access` gating: lookup-admin-only identity's callback
      issues an auth code without entering `stepPhone`; full-admin and
      client identities still enter `enable_access` as before (regression on
      the existing behavior at `:1144-1159`).
- [ ] T5. Manual/integration (post-follow-up-tasks): from the `admins`
      OpenClaw agent, ask "who is telegram id `<known test id>`" and confirm
      it returns identity data (not the generic error text) using the new
      lookup-admin token end to end.

## Rollback

- Tasks 1-4 (this repo) are additive and gated entirely behind
  `TG_LOGIN_LOOKUP_ADMINS` being non-empty. Rollback is a plain revert of the
  PR (or leaving the env var unset in every deployment) — no migration, no
  data written, no existing tier or token affected either way.
- If task 5 (the dependent `mctl-gitops`/ops wiring) has already landed and
  needs to be undone independently: remove the `mctl-telegram` MCP server
  entry from `admins/openclaw`'s `values.yaml` (stops the agent from calling
  the tools) and/or clear `TG_LOGIN_LOOKUP_ADMINS` on the `mctl-telegram`
  deployment (any outstanding token for that id then resolves to no scopes
  on its next refresh, per `ResolveScopes`'s "anyone else" fallback — no
  token revocation call needed, though the refresh token can also be
  explicitly revoked as defense in depth). Neither action requires touching
  this repo's code.
