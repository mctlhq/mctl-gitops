# Design: issue-575-docs-runbook-document-the-tg-login-looku

## Current state

### The tier in code

`ResolveScopes` (`internal/oauth/server.go:983`) checks four tiers in order.
The lookup branch is second, at `:1049`:

```go
if s.cfg.LookupAdminTelegramIDs[tgID] {
    return []string{"admin-lookup"}, []string{"admin:users:read"}, nil
}
```

It sits after the `AdminTelegramIDs` branch (`:984`) and before
`isClientTier` (`:1052`), which is the whole precedence rule: full admin wins
over lookup, lookup wins over client. The comment block at `:1019-1046`
states that a dual listing is a configuration mistake and that the ordering is
pinned by `TestResolveScopes_Tiers`
(`internal/oauth/enable_access_test.go:835`).

`admin:users:read` is consumed in exactly two places, both via
`requireAnyScope(id, "admin:users", "admin:users:read")`:
`list_telegram_identities` (`internal/mcp/tools.go:1070`, tool declared at
`:1053`) and `get_user_audit_log` (`:1526`, declared at `:1499`). The helper's
doc comment (`:1852-1864`) enumerates the seven admin write tools that keep a
plain `requireScope(id, "admin:users")` gate — `set_telegram_access` (`:1108`),
`set_account_send` (`:1157`), `set_account_mode` (`:1377`),
`provision_local_account` (`:1462`), `revoke_telegram_session` (`:1587`),
`revoke_worker_token` (`:1672`), `mint_worker_token` (`:2104`) — plus the admin
mint routes in `internal/agentapi` and `internal/workertoken`. A denied call
returns `identity missing scope admin:users` from `requireScope`
(`internal/mcp/tools.go:1841`).

### Onboarding path

`handleTelegramCallback` binds `isLookupOnly` once
(`internal/oauth/server.go:1558`) as "in `LookupAdminTelegramIDs` and not in
`AdminTelegramIDs`", and reuses it at two sites. The routing site (`:1631`)
sends a lookup-only identity straight to `s.issueAuthCode`, skipping
`enable_access` entirely — the comment at `:1623-1630` gives the reason: the
tier gets no `telegram:*` scope, so an MTProto session would be unusable.
`internal/oauth/enable_access.go:998` and
`TestEnableAccess_LookupAdminOnlySkipsFlow`
(`internal/oauth/enable_access_test.go:545`) cover the same boundary. Practical
consequence: onboarding is one Login Widget sign-in — no phone, SMS or 2FA.

### The removal exemption

The other `isLookupOnly` site is the open-registration materialization block
(`internal/oauth/server.go:1559`): when `AutoApproveClients` is on, first
sign-in persists `access_tier='client'` for an un-tiered user, and a
lookup-only identity is excluded. The rationale comment (`:1537-1546`) is
explicit: without the exemption, taking the bot out of the allowlist would
*promote* it to the full client tier off the persisted row, and operators
reasonably read allowlist removal as de-provisioning. It also keeps the bot out
of `list_telegram_identities` as a client and out of the new-client digest.

### Refresh monotonicity after #572

`handleTokenRefresh` re-resolves scopes for the identity and then bounds them:

```go
resolvedScopes := scopes
groups, scopes = boundRefreshGrant(groups, resolvedScopes, rt.Scope)
if len(scopes) < len(resolvedScopes) {
    writeTokenError(w, "invalid_grant", "refresh authorization no longer available", ...)
```

(`internal/oauth/server.go:2136-2145`; `boundRefreshGrant` at `:2231`
intersects current scopes with the predecessor's grant and returns `nil, nil`
when the intersection is empty). A refresh can therefore preserve or shrink a
grant, never widen it. There are two distinct wire outcomes after an allowlist
removal, and which one occurs depends on `AUTO_APPROVE_CLIENTS`:

1. **Open registration ON** (labs: `AUTO_APPROVE_CLIENTS: "true"` in
   `mctl-gitops/platform-gitops/services/labs/mctl-telegram/values.yaml:109`).
   The exemption means the identity has no persisted tier, so `isClientTier`
   (`internal/oauth/server.go:1073`) hits its `default:` branch and returns
   true for open registration. `ResolveScopes` therefore returns the five-scope
   client bundle. The intersection with the original `admin:users:read` grant
   is empty, `0 < 5` holds, and the refresh fails **HTTP 400 `invalid_grant`,
   "refresh authorization no longer available"**. This is pinned by
   `TestToken_RefreshCannotExpandLookupGrantAfterAllowlistRemoval`
   (`internal/oauth/refresh_test.go:554`), which sets
   `AutoApproveClients = true` and asserts `http.StatusBadRequest`; the grace
   replay path is pinned by `TestToken_RefreshGraceRecoveryCannotExpandGrant`
   (`:595`).
2. **Open registration OFF, or DB tier explicitly `none`.** `ResolveScopes`
   returns no scopes; `resolvedScopes` and the bounded set are both empty, the
   `len(scopes) < len(resolvedScopes)` guard does not fire, and the refresh
   returns **HTTP 200 with a scopeless access token**. The identity's next
   `list_telegram_identities` call is what fails, at `requireAnyScope`. An
   operator verifying de-provisioning must call a tool, not read the refresh
   status.

The issue text asserts only outcome 2. Outcome 1 is what the merged code does
under the labs configuration, so the section documents both and names the
condition. A *promotion* — an identity now resolving to scopes outside the
original grant — is outcome 1's general form: widening requires a fresh
authorization-code flow. That is also why an account must be allowlisted
*before* its first sign-in; a family issued earlier can never acquire
`admin:users:read`.

### Where the value lives

`internal/config/config.go:337` parses `TG_LOGIN_LOOKUP_ADMINS` with
`parseInt64CSV` into `TGLoginLookupAdmins` (declared `:70`, next to
`TGLoginAdmins` and `TGLoginClients`). `cmd/server/main.go:792-794` converts
the slice into the `map[int64]bool` passed as
`oauth.Config.LookupAdminTelegramIDs` (`:812`). `cmd/server/agentsendgate.go:27`
mirrors the same precedence for the background executor. The labs deployment
sets `TG_LOGIN_ADMINS` at `values.yaml:92`; `TG_LOGIN_LOOKUP_ADMINS` is not
set there yet, so adding an id is a mctl-gitops PR plus a redeploy.

### The document being edited

`docs/runbook.md` (1452 lines) opens with a `## Table of contents` bullet list
(`:15-31`), then sixteen `##` sections. Every section carries an explicit
`<a id="...">` anchor immediately above its heading, and every TOC bullet links
to one. Seven of those anchors are asserted by `TestRunbookAnchorsPresent`
(`docs/runbook_test.go:10`) because alert rules deep-link them;
`deploy/alerts/runbook_links_test.go` checks the alert side.
`TestRunbookMetricNamesRegistered` (`:35`) extracts every `mctl_[a-z_]+` token
from the runbook and fails unless the base series name appears in
`internal/metrics/metrics.go`. The nearest neighbour to the new material is
`## OAuth refresh re-authorization after scope changes` (`:36`, anchor
`oauth-refresh-reauthorization`), which already tells operators that a
coordinated wave of `invalid_grant` after a scope-bundle change is an expected
re-authorization migration rather than an outage.

`docs/plans/local-bridge-review.md:178-207` (finding F3) is the only other
mention of `TG_LOGIN_LOOKUP_ADMINS` under `docs/`. It documents the
pre-`0.62.3` defect — refresh re-resolved scopes *without* bounding them, so
removal broadened the grant — and its advice ("removal alone must not be
described as revocation") is superseded by #572. It is a dated review artifact
and is deliberately left untouched.

## Proposed solution

Add one top-level section to `docs/runbook.md` and one TOC bullet. Nothing
else changes, in this file or any other.

**Placement.** Insert the new section immediately after the
`## OAuth refresh re-authorization after scope changes` section (after
`docs/runbook.md:46`, before the `<a id="deployment-compatibility"></a>` line
at `:48`), separated by the same `---` rule the neighbouring sections use. The
new section is the concrete instance of the general rule stated just above it,
so adjacency lets the tier section reference "the refresh re-authorization
section above" instead of restating monotonicity.

**Heading.** `## Lookup-admin tier and TG_LOGIN_LOOKUP_ADMINS`. Plain ASCII,
no em dash and no parentheses, so the generated slug is predictable:
`#lookup-admin-tier-and-tg_login_lookup_admins`. No `<a id="...">` anchor, per
the issue's scope limit — no alert rule points here.

**TOC bullet.** Insert
`- [Lookup-admin tier and TG_LOGIN_LOOKUP_ADMINS](#lookup-admin-tier-and-tg_login_lookup_admins)`
directly after the existing `OAuth refresh re-authorization` bullet
(`docs/runbook.md:23`), matching document order. No other line in the TOC
block changes.

**Section shape.** Short prose paragraphs plus two compact lists, in the
register of the neighbouring `oauth-refresh-reauthorization` and
`deployment-compatibility` sections — mechanism and reason, not a tutorial.
Sub-headings are avoided; the alert sections' `### Symptom / ### Likely causes`
skeleton is for alert response and does not fit a configuration reference. The
content, in order:

1. **What the tier grants.** `admin:users:read` and nothing else; exactly
   `list_telegram_identities` and `get_user_audit_log`; every admin write tool
   and every `telegram:*` scope stays closed.
2. **Onboarding.** Lookup-only identities skip `enable_access` and go straight
   to the authorization code: one Login Widget sign-in, no phone number, no
   SMS, no 2FA.
3. **Precedence.** Full admin beats lookup beats client; a dual listing is a
   configuration mistake, resolved quietly rather than rejected.
4. **Ordering requirement.** Allowlist the account *before* its first sign-in;
   a refresh can never widen a grant, so a family issued earlier needs a fresh
   authorization-code flow.
5. **Removal.** The `AUTO_APPROVE_CLIENTS` materialization exemption and why
   it exists (removal must mean removal, not promotion to client), then the two
   refresh outcomes with the condition that selects them, and the instruction
   to verify with a tool call rather than a refresh status code.
6. **Where the value lives.** `TG_LOGIN_LOOKUP_ADMINS` →
   `internal/config/config.go` → `oauth.Config.LookupAdminTelegramIDs`; set
   per-deployment in the labs `values.yaml` beside `TG_LOGIN_ADMINS`; changing
   it is a mctl-gitops PR plus a redeploy.
7. **Verification.** Positive: `list_telegram_identities` returns rows for the
   lookup identity. Negative: `set_telegram_access` or `mint_worker_token` is
   refused with `identity missing scope admin:users`.

**Constraints honoured by construction.** No `mctl_` token appears anywhere in
the new text (the section cites no metrics), so
`TestRunbookMetricNamesRegistered` cannot regress. No anchor is added and none
is removed, so `TestRunbookAnchorsPresent` and
`deploy/alerts/runbook_links_test.go` are untouched.

## Alternatives

- **A new file, `docs/lookup-admin-tier.md`.** Rejected: the issue scopes the
  change to `docs/runbook.md`, `docs/runbook_test.go` only guards that file,
  and a separate page would sit outside the TOC an on-call operator actually
  reads. The material is also short enough to be one section.
- **Extend the existing `## OAuth refresh re-authorization after scope
  changes` section instead of adding a new one.** Rejected: that section is a
  general statement about refresh families across all tiers, and folding a
  tier reference into it would bury the scope/onboarding/precedence content
  that has nothing to do with refresh, and would give the TOC no entry for the
  tier. Adjacent placement plus a cross-reference gets the same cohesion
  without the dilution.
- **Document only the scopeless-HTTP-200 removal case, as the issue text
  words it.** Rejected: it is wrong for this deployment. With
  `AUTO_APPROVE_CLIENTS: "true"` the removed identity re-resolves to the client
  bundle and the refresh returns `invalid_grant`, as
  `TestToken_RefreshCannotExpandLookupGrantAfterAllowlistRemoval` asserts. An
  operator following a runbook that promised HTTP 200 would read the 400 as an
  incident. Both cases are documented, with the selecting condition named.
- **Add an `<a id="lookup-admin-tier"></a>` anchor for house-style
  consistency.** Rejected as the default because the issue forbids it; noted in
  `requirements.md` as reversible on reviewer preference, since adding an
  anchor breaks no test.

## Platform impact

- **Migrations:** none. No schema, no config, no code.
- **Backward compatibility:** total. A Markdown-only change to `docs/`; the
  image build and the deployed binary are unaffected. Nothing in `deploy/`
  references the new heading.
- **Resource impact:** none.
- **Risks and mitigations:**
  - *Risk:* the documented removal behaviour drifts if
    `AUTO_APPROVE_CLIENTS` changes for a deployment, or if the open-registration
    fallback in `isClientTier` is later removed. *Mitigation:* the section
    names the condition explicitly rather than asserting one outcome, and
    points at `internal/oauth/server.go` `handleTokenRefresh` /
    `boundRefreshGrant` so a reader can re-derive it.
  - *Risk:* the TOC link breaks if the heading is later reworded, since it
    relies on a generated slug rather than an explicit anchor. *Mitigation:*
    the heading is plain ASCII with no punctuation that the slugger rewrites;
    reviewers check the rendered link on the PR.
  - *Risk:* a future edit introduces a metric name into the section and fails
    `TestRunbookMetricNamesRegistered`. *Mitigation:* CI runs
    `go test ./docs/...`; the constraint is restated in `tasks.md`.
  - *Risk:* readers find `docs/plans/local-bridge-review.md` F3 first and act
    on its superseded advice. *Mitigation:* out of scope here, but flagged for
    a follow-up issue; the new runbook section is the authoritative statement
    and is reachable from the TOC, which the plan document is not.
