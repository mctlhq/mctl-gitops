# Document the TG_LOGIN_LOOKUP_ADMINS lookup-admin tier in the runbook

## Context

`TG_LOGIN_LOOKUP_ADMINS` gates the `admin-lookup` tier: an identity listed
there resolves to the single scope `admin:users:read`
(`internal/oauth/server.go:1049`), which opens exactly the two read-only admin
lookups `list_telegram_identities` and `get_user_audit_log` through
`requireAnyScope` (`internal/mcp/tools.go:1070`, `:1526`, helper at `:1865`).
The name appears nowhere in operator-facing documentation: the only hit under
`docs/` is `docs/plans/local-bridge-review.md`, a review-findings plan whose F3
entry describes pre-`0.62.3` behaviour and is stale as an operator reference.
Everything an operator needs — what the tier grants, that onboarding needs no
MTProto session, how tiers take precedence, and what removal does — lives only
in Go source comments today.

The tier is a prerequisite for #400 (wiring the `admins/openclaw` bot to a
scoped identity-lookup account), so an operator will shortly be asked to add
an id to this allowlist and, later, to remove one. Removal is where the trap
is: the observable result of removing an id differs depending on
`AUTO_APPROVE_CLIENTS`, and in the labs deployment (`AUTO_APPROVE_CLIENTS:
"true"` in `mctl-gitops/platform-gitops/services/labs/mctl-telegram/values.yaml`)
a refresh after removal returns `invalid_grant`, not the scopeless HTTP 200 the
issue text predicts. This proposal is documentation only: one new section in
`docs/runbook.md` plus its table-of-contents entry. No `.go` file changes.

## User stories

- AS a platform operator I WANT `docs/runbook.md` to state exactly what
  `TG_LOGIN_LOOKUP_ADMINS` grants SO THAT I can add an identity to it without
  reading `internal/oauth/server.go`.
- AS a platform operator I WANT to know that a lookup-only identity never
  enters the `enable_access` flow SO THAT I do not schedule a human with a
  phone, an SMS code and a 2FA password for an onboarding that needs none.
- AS a platform operator I WANT the removal semantics documented, including
  both wire-level outcomes and which one applies to this deployment, SO THAT
  I can verify de-provisioning instead of trusting an HTTP status code.
- AS a platform operator I WANT the tier-precedence rule written down SO THAT
  I recognise an id listed in two allowlists as a configuration mistake.
- AS the engineer implementing #400 I WANT the "allowlist before first
  sign-in" ordering documented SO THAT I do not create a token family that can
  never acquire `admin:users:read`.

## Acceptance criteria (EARS)

- WHEN the change is complete THE SYSTEM SHALL contain, in `docs/runbook.md`,
  one new top-level `##` section covering the lookup-admin tier.
- WHEN a reader opens that section THE SYSTEM SHALL state that the tier
  resolves to `admin:users:read` and nothing else, that this opens exactly
  `list_telegram_identities` and `get_user_audit_log`, and that no `telegram:*`
  scope and no admin write tool is granted.
- WHEN a reader opens that section THE SYSTEM SHALL state that a lookup-only
  identity is routed straight to the authorization code and skips
  `enable_access`, so onboarding is a single Telegram sign-in with no phone
  number, SMS code or 2FA prompt.
- WHEN a reader opens that section THE SYSTEM SHALL state the tier precedence
  (full admin beats lookup, lookup beats client) and that a dual listing is a
  configuration mistake rather than a way to combine bundles.
- WHEN a reader opens that section THE SYSTEM SHALL state that a lookup-only
  identity is exempt from the `AUTO_APPROVE_CLIENTS` first-sign-in write of
  `access_tier='client'`, and SHALL give the reason: without the exemption,
  allowlist removal would promote the identity to the full client tier off the
  persisted row instead of dropping it.
- WHEN a reader opens that section THE SYSTEM SHALL describe both refresh
  outcomes after allowlist removal, and SHALL say which one applies when
  `AUTO_APPROVE_CLIENTS` is on:
  - IF open registration is on (or the identity otherwise still resolves to
    scopes outside its original grant) THEN THE SYSTEM SHALL document that the
    refresh fails with `invalid_grant "refresh authorization no longer
    available"`.
  - IF the identity resolves to no scopes at all (open registration off, or DB
    tier explicitly `none`) THEN THE SYSTEM SHALL document that the refresh
    returns HTTP 200 with a scopeless access token and that the failure
    surfaces only at the next tool call.
- WHILE the section describes verification THE SYSTEM SHALL instruct the
  operator to confirm de-provisioning by calling a tool, not by reading the
  refresh response code.
- WHEN a reader opens that section THE SYSTEM SHALL state that an account must
  be listed in `TG_LOGIN_LOOKUP_ADMINS` before its first sign-in, because a
  refresh can never widen a grant and a later-allowlisted family needs a fresh
  authorization-code flow.
- WHEN a reader opens that section THE SYSTEM SHALL state where the value
  lives: parsed from `TG_LOGIN_LOOKUP_ADMINS` in `internal/config/config.go`
  into `TGLoginLookupAdmins`, set per deployment in
  `mctl-gitops/platform-gitops/services/labs/mctl-telegram/values.yaml`
  alongside `TG_LOGIN_ADMINS`, so a change is a mctl-gitops PR plus a redeploy.
- WHEN a reader opens that section THE SYSTEM SHALL give a positive
  verification step (`list_telegram_identities` returns data for the lookup
  identity) and a negative one (a write tool such as `set_telegram_access` or
  `mint_worker_token` is refused with a missing-scope error).
- WHEN the change is complete THE SYSTEM SHALL list the new section in the
  `## Table of contents` block of `docs/runbook.md`, in the same bullet style
  as its neighbours, changing nothing else in that block.
- WHILE the change is under review THE SYSTEM SHALL leave every file other
  than `docs/runbook.md` unmodified.
- WHEN `go test ./docs/... ./deploy/...` runs THE SYSTEM SHALL pass, including
  `TestRunbookAnchorsPresent` and `TestRunbookMetricNamesRegistered`
  (`docs/runbook_test.go`) and `deploy/alerts/runbook_links_test.go`.
- IF the new prose would name a metric THEN THE SYSTEM SHALL omit it: no
  `mctl_*` token may appear in the new section, since the section cites no
  metrics and any unregistered name fails
  `TestRunbookMetricNamesRegistered`.
- IF the new section would carry an `<a id="...">` anchor THEN THE SYSTEM
  SHALL omit it, because no alert rule points at this section; the
  table-of-contents entry links to the heading's generated slug instead.

## Out of scope

- Changing the scopeless-token-on-removal behaviour, the exemption, or any
  other `.go` file. This is current behaviour and is documented, not fixed.
- Documenting the full-admin (`admin:users`) or client tiers beyond the one
  precedence sentence and the removal comparison that the section requires.
- Adding or changing `TG_LOGIN_LOOKUP_ADMINS` values in mctl-gitops. That
  belongs to #400. The key is not present in the labs `values.yaml` today.
- Updating `docs/plans/local-bridge-review.md`, whose F3 finding predates
  `0.62.3`. It is a point-in-time review artifact, not operator guidance.
- Adding `TG_LOGIN_LOOKUP_ADMINS` to `.env.example`, `README.md` or any other
  file: the issue restricts the diff to `docs/runbook.md`.

## Open questions

- The issue states that removal makes `ResolveScopes` return an empty set and
  therefore yields HTTP 200 with a scopeless token. On `main` that holds only
  when open registration is off: `isClientTier`
  (`internal/oauth/server.go:1073`) returns true for an un-tiered user when
  `AutoApproveClients` is set, so a removed lookup identity resolves to the
  full client bundle, `boundRefreshGrant` intersects it down to nothing, and
  the guard at `internal/oauth/server.go:2142` fires with `invalid_grant`.
  `TestToken_RefreshCannotExpandLookupGrantAfterAllowlistRemoval`
  (`internal/oauth/refresh_test.go:554`) pins exactly that, with
  `AutoApproveClients = true`, and labs runs `AUTO_APPROVE_CLIENTS: "true"`.
  Interpretation taken: document both branches and name the condition that
  selects between them, since a runbook that describes only the scopeless-200
  case would mis-describe the live deployment. A reviewer who prefers the
  issue's literal wording should say so on the PR.
- Every other section of `docs/runbook.md` carries an explicit
  `<a id="...">` anchor, including the non-alert
  `oauth-refresh-reauthorization`, `deployment-compatibility` and
  `communication-agent-operations` sections. The issue forbids adding one
  here. Interpretation taken: follow the issue, and link the
  table-of-contents entry at the heading's generated slug. Adding the anchor
  would not break `TestRunbookAnchorsPresent`, which only asserts presence of
  the seven alert anchors, so this is reversible on reviewer preference.
- The issue asks the section to say the variable is "set per-deployment in
  `values.yaml` alongside `TG_LOGIN_ADMINS`". It is not set there yet.
  Interpretation taken: describe the file as the place the value belongs and
  where a change is made, without claiming a value is currently configured.
