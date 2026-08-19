# Design: issue-400-admins-openclaw-bot-can-t-answer-who-is

## Current state

- The `admins` tenant's OpenClaw agent (backing `@MCTL_AI_bot` in
  `mctl_admins`) only has the `mctl` and `github` MCP servers wired
  (`mctl-gitops/platform-gitops/services/admins/openclaw/values.yaml`,
  `mcp.servers`, per the issue). It has no Telegram tool at all.
- `mctl-telegram` already ships the exact lookup capability as two admin-only
  MCP tools:
  - `list_telegram_identities` (`internal/mcp/tools.go:871-899`) — lists
    every widget-authenticated user with `{telegram_id, username,
    display_name, access_tier, has_session, connected_via}`, sourced purely
    from `s.Store.ListIdentities(ctx)`.
  - `get_user_audit_log` (`internal/mcp/tools.go:1007-1073`) — resolves a
    Telegram id to a user id via `s.Store.UserIDByTelegramID` and reads
    `s.Store.ListAuditFor`, purely DB-driven.
  Both gate on `requireScope(id, "admin:users")` (`internal/mcp/tools.go:888,
  1037`, helper at `:1196`) and never touch the caller's own MTProto session,
  dialogs, or messages.
- OAuth grants are minted per Telegram identity in
  `Server.ResolveScopes(ctx, tgID)` (`internal/oauth/server.go:666-689`).
  There are exactly two privileged branches today:
  - `s.cfg.AdminTelegramIDs[tgID]` (env `TG_LOGIN_ADMINS`,
    `internal/config/config.go:297`) → groups `["platform-admins",
    "admins"]`, scopes `["telegram:dialogs:read", "telegram:messages:read",
    "telegram:messages:send", "telegram:messages:pin", "admin:users"]` — the
    full bundle, unconditionally.
  - `isClientTier` (DB `users.access_tier` column, falling back to env
    `TG_LOGIN_CLIENTS`) → groups `["clients"]`, the same four `telegram:*`
    scopes, no `admin:users`.
  - Anyone else → no scopes, authenticates but every tool 403s.
  There is no branch that grants `admin:users` alone.
- `handleTelegramCallback` (`internal/oauth/server.go:1144-1159`) decides
  whether to route a freshly-authenticated identity into the `enable_access`
  MTProto provisioning flow (phone → SMS code → 2FA password, the same steps
  `cmd/login/main.go` drives interactively) or straight to
  `issueAuthCode`. The current condition is
  `if !s.cfg.AdminTelegramIDs[identity.TelegramID] && !isClient { issue code
  directly }` — i.e. every admin and every client is walked through session
  provisioning, because their granted scopes assume a working MTProto
  session exists.
- `Server.Config` in `internal/oauth/server.go` holds `AdminTelegramIDs
  map[int64]bool` and `ClientTelegramIDs map[int64]bool`
  (`:165-172`), both nil-defaulted to empty maps at construction
  (`:347-351`).
- `internal/config/config.go:51-52` defines `TGLoginAdmins`/`TGLoginClients`
  `[]int64`, populated from `TG_LOGIN_ADMINS`/`TG_LOGIN_CLIENTS` via
  `parseInt64CSV` (`:297-298`, helper at `:447-462`). `cmd/server/main.go`
  (not modified here, but where these get turned into the `map[int64]bool`
  passed to `oauth.Config`) is the wiring point between config and server.
- Existing scope-tier tests live in `internal/oauth/enable_access_test.go`:
  `TestResolveScopes_Tiers` (`:726`), `TestResolveScopes_AutoApprove`
  (`:574`), `TestResolveScopes_DBRevokeOverridesEnv` (`:549`).

## Proposed solution

Add a third, narrower privileged tier to `ResolveScopes`: a **lookup-admin**
tier that grants `admin:users` alone, with none of the `telegram:*`
messaging scopes and no MTProto session provisioning. This directly answers
the issue's own stated requirement ("выдать ему только нужный tier —
admin:users ... messaging-тулы ему просто нечего читать/отправлять") at the
scope layer instead of relying on the dedicated account happening to stay
empty.

Concretely:

1. **Config**: add `TGLoginLookupAdmins []int64` to `internal/config/config.go`
   (next to `TGLoginAdmins`/`TGLoginClients`), populated from a new env var
   `TG_LOGIN_LOOKUP_ADMINS` via the existing `parseInt64CSV` helper. Document
   it in `.env.example` alongside the (currently undocumented, but
   code-comment-described) admin/client vars.
2. **oauth.Config**: add `LookupAdminTelegramIDs map[int64]bool` to
   `internal/oauth/server.go`'s `Config` struct, nil-defaulted to `{}` in the
   same block as `AdminTelegramIDs`/`ClientTelegramIDs` (`:347-351`).
   `cmd/server/main.go` wires `cfg.TGLoginLookupAdmins` into it the same way
   it wires the other two allowlists.
3. **ResolveScopes**: insert the new branch. Full-admin stays authoritative
   (an id in both allowlists gets the full bundle — this makes double-listing
   safe and avoids an accidental downgrade if an operator temporarily adds an
   existing full admin to the lookup list):
   ```go
   func (s *Server) ResolveScopes(ctx context.Context, tgID int64) (groups, scopes []string, err error) {
       if s.cfg.AdminTelegramIDs[tgID] {
           return []string{"platform-admins", "admins"}, []string{...}, nil // unchanged
       }
       if s.cfg.LookupAdminTelegramIDs[tgID] {
           return []string{"admin-lookup"}, []string{"admin:users"}, nil
       }
       isClient, err := s.isClientTier(ctx, tgID)
       ... // unchanged
   }
   ```
4. **enable_access gating**: update the condition in
   `handleTelegramCallback` (`:1144-1159`) so a lookup-admin-only identity is
   also routed straight to `issueAuthCode`, skipping the phone/SMS/2FA flow —
   it has no `telegram:*` scope, so a session would be provisioned and never
   used:
   ```go
   isClient, err := s.isClientTier(r.Context(), identity.TelegramID)
   ...
   isLookupOnlyAdmin := s.cfg.LookupAdminTelegramIDs[identity.TelegramID] &&
       !s.cfg.AdminTelegramIDs[identity.TelegramID]
   if (!s.cfg.AdminTelegramIDs[identity.TelegramID] && !isClient) || isLookupOnlyAdmin {
       s.issueAuthCode(w, r, oc)
       return
   }
   ```
5. **No change to `internal/mcp/tools.go`**: both target tools already gate
   purely on the `admin:users` scope string via `requireScope`, not on group
   name or tier. They work unmodified once the caller's token carries that
   scope.
6. **Tests**: extend `internal/oauth/enable_access_test.go` —
   `TestResolveScopes_Tiers` gains a lookup-admin-only case (scopes == exactly
   `["admin:users"]`, no `telegram:*`) and a both-listed case (full bundle
   wins). A new or extended `enable_access` handler test asserts a
   lookup-admin-only identity is *not* routed into
   `stepPhone`/`enableSession` and instead gets an immediate auth code.
7. **Docs**: update `internal/oauth/server.go`'s `ResolveScopes` doc comment
   (`:653-665`) to describe the three tiers instead of two, and add
   `TG_LOGIN_LOOKUP_ADMINS` to `.env.example` with a one-line description
   matching the style of neighboring vars.

Outside this repo (tracked as dependent follow-up tasks, not implemented
here): provision the dedicated Telegram account, complete its one-time Login
Widget sign-in (no MTProto phone/SMS/2FA needed for this tier), add its
Telegram id to `TG_LOGIN_LOOKUP_ADMINS` on the `mctl-telegram` deployment,
capture its OAuth refresh token as a Vault secret, and add `mctl-telegram` as
an MCP server in
`mctl-gitops/platform-gitops/services/admins/openclaw/values.yaml`
`mcp.servers`.

## Alternatives

1. **Follow the issue literally: reuse the existing full-admin tier with a
   fresh, "empty" dedicated account.** No code change — just add the new
   account's id to `TG_LOGIN_ADMINS` and complete the full phone/SMS/2FA
   `cmd/login` flow. Simpler, zero new code/tests/risk surface. Rejected as
   the primary recommendation because it still hands the bot a live MTProto
   session with real read/send/pin capability that `list_telegram_identities`
   /`get_user_audit_log` never need — the safety property rests entirely on
   the account staying empty forever, which is an operational convention, not
   an enforced guarantee. Kept as a documented fallback (see Open questions
   in requirements.md) if the platform prefers zero code churn.
2. **Make the new tier DB-backed (a third `users.access_tier` value,
   e.g. `"lookup"`), managed at runtime via `set_telegram_access` like the
   `client` tier.** More flexible (grant/revoke without a redeploy), but
   `set_telegram_access` currently only validates `tier == db.TierClient ||
   tier == db.TierNone` (`internal/mcp/tools.go:935-937`) and admin is
   env-only by design — mixing an env-only privileged tier with a DB-managed
   one adds asymmetry the current two-tier model doesn't have. Rejected for
   this proposal to stay consistent with how `admins` already works
   (env-only allowlist, redeploy to change); left as a documented future
   enhancement.
3. **Add a client-credentials / service-account OAuth grant type instead of
   a new identity tier**, letting the bot authenticate as a "service" rather
   than as a Telegram user at all. Closest to how a platform team would
   normally solve "give a bot least-privilege API access," but it is a much
   larger change to `internal/oauth/server.go`'s grant dispatch
   (`handleToken`, `:1359-1366`) and the whole `ResolveScopes` model, which
   is fundamentally keyed on a live Telegram identity end to end
   (`internal/oauth/server.go`'s own architecture comment). Rejected as
   disproportionate to this issue; the narrower-tier approach solves the
   concrete problem with a much smaller, well-isolated diff.

## Platform impact

- **Migrations**: none. No DB schema change — the new tier is env-only,
  mirroring `TG_LOGIN_ADMINS`.
- **Backward compatibility**: fully additive. `TG_LOGIN_LOOKUP_ADMINS` unset
  ⇒ `LookupAdminTelegramIDs` is an empty map ⇒ `ResolveScopes` and the
  `enable_access` gate behave byte-for-byte as today for every existing
  identity. No existing tier, scope string, or tool behavior changes.
- **Resource impact**: negligible — one more small allowlist map held in
  memory, one more branch in a hot-path-adjacent (login-time, not
  per-request) function.
- **Risks + mitigations**:
  - *Risk*: an operator lists an id in `TG_LOGIN_LOOKUP_ADMINS` expecting
    `telegram:*` denial, but the id is also (now or later) added to
    `TG_LOGIN_ADMINS`, silently upgrading it. *Mitigation*: this is
    documented as intentional precedence (full-admin wins) in both the code
    comment and requirements.md, so it reads as "safe superset" rather than
    surprising; if stricter behavior is wanted later, the branch order can be
    swapped to make lookup-admin the terminal case.
  - *Risk*: forgetting the `enable_access` gating change (step 4) would leave
    a lookup-admin-only identity walked through a pointless phone/SMS/2FA
    flow on first login. Low severity (self-correcting — the operator just
    skips or abandons it, and the account still gets a scoped code either
    way once `isClientTier`/admin checks are unaffected) but confusing;
    called out explicitly as a required task, not optional polish.
  - *Risk*: the dependent `mctl-gitops` change (wiring the MCP server) and
    the Vault secret provisioning happen out of band from this repo's CI —
    this proposal's code change is inert (unused) until that follow-up
    lands. Sequenced explicitly in tasks.md so the implementer/reviewer
    knows this PR alone does not close the issue's user-facing symptom.
  - *Risk*: leaked lookup-admin refresh token. Blast radius is now
    genuinely limited to `list_telegram_identities` and `get_user_audit_log`
    (read-only, redacted audit rows per `internal/mcp/tools.go:1025` —
    "message bodies, phone numbers and session bytes are never recorded") —
    materially smaller than a leaked full-admin or personal token today.
