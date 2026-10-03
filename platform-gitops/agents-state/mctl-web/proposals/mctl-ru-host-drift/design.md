# Design: mctl-ru-host-drift

## Current state
Per `context/architecture.md`, the Cloudflare Worker routes `mctl.ai/api/*` for the
application's own API endpoints, and separately redirects `mctl.me/*`, `*.mctl.me/*`,
`mctl.ru/*`, and `*.mctl.ru/*` to `mctl.ai`. `mctl.ai` is documented as the sole primary
host for OAuth callbacks (`GITHUB_CLIENT_ID`/`SECRET`/`OAUTH_HMAC_KEY`), the
Backstage-integrated tenant-creation forms, and the served Nuxt static site.

Separately, `mctl_get_service_config` (mctl MCP tool, `admins` tenant, `mctl-web`
service) currently reports the live host field as `mctl.ru`, contradicting the
documented architecture. No independent verification (DNS lookup, direct Worker route
inspection, or live HTTP request to `mctl.ru` checking for a redirect vs. a direct
200 response) has been performed yet — the discrepancy is raw output from one tool,
cross-checked only against documentation, not against the actual live routing
configuration.

## Proposed solution
This is an investigation-first proposal; the "solution" phase is split into two stages:

**Stage 1 — Investigation (always executed):**
1. Inspect the Worker's deployed route configuration directly (e.g. `wrangler.toml` /
   deployed route bindings via `wrangler deployments` or the Cloudflare dashboard) to
   see the actual, current route-to-host bindings, independent of `mctl_get_service_config`.
2. Perform a live HTTP check against `mctl.ru` (e.g. `curl -I https://mctl.ru/`) to
   observe whether it returns a redirect (3xx to `mctl.ai`) as documented, or serves
   content directly (2xx) — the latter would indicate a genuine divergence.
3. Trace `mctl_get_service_config`'s data source: identify which underlying field/label
   populates its "host" value, and whether that field is derived from live routing data
   or from a static/config-time label that could be stale.
4. Cross-reference DNS records for `mctl.ru` and `mctl.ai` to confirm which one
   currently resolves to the Cloudflare Worker/Pages target.

**Stage 2 — Conditional fix (only if Stage 1 confirms a genuine divergence):**
- If `mctl.ru` is found to be serving non-redirect application traffic: update Worker
  route bindings so `mctl.ru/*` only performs the documented redirect to `mctl.ai`;
  audit and correct the GitHub OAuth callback allow-list and CORS policy to ensure they
  are scoped to `mctl.ai` only (or intentionally extended, with justification, if a
  legitimate reason for direct `mctl.ru` serving is found); update
  `context/architecture.md` to reflect the corrected, verified state.
- If `mctl.ru` is found to be a stale/mislabeled config-tool value only: no application
  or infrastructure change is made; instead, file/track a correction against the
  config-tool's data source (outside this repo's control, if the tool itself is owned
  elsewhere) and note the resolution in this proposal.

This staged approach directly matches the acceptance criteria in `requirements.md`,
which forbid any routing/OAuth/CORS change while the root cause is unconfirmed.

## Alternatives
- **Immediately "fix" the Worker routing / OAuth allow-list to assume `mctl.ru` is
  wrong.** Rejected: this assumes the worst-case interpretation without verification;
  if the config-tool label is simply stale, this would be a wasted (and potentially
  disruptive) change to working production routing.
- **Ignore the discrepancy as tooling noise.** Rejected: the analyst rated this Impact 4
  precisely because a genuine OAuth/CORS host mismatch has real security implications
  (silent auth failures or unintended cross-origin acceptance); dismissing it without
  verification is not acceptable given the stakes.
- **Fold this into `reconcile-current-version-doc`.** Rejected: that proposal's scope
  is explicitly limited to the version-number field and states application/
  infrastructure changes are out of scope; the host/domain question requires
  infrastructure-level investigation (Worker routes, DNS, OAuth config) that doesn't
  fit that proposal's documentation-only remit. Keeping them separate avoids scope
  creep in either proposal.

## Platform impact
- **Migrations:** none in Stage 1 (investigation only). Stage 2, if triggered, would
  involve Worker route configuration changes and possibly OAuth allow-list/CORS config
  updates — no data migrations.
- **Backward compatibility:** Stage 1 has zero user-facing impact. Stage 2, if
  triggered, must preserve the documented redirect behavior (`mctl.ru/*` → `mctl.ai`)
  so that any existing links/bookmarks pointing at `mctl.ru` continue to resolve
  correctly via redirect rather than breaking.
- **Resource impact:** mctl-web runs in the `admins` tenant, not `labs` — there is no
  `labs` memory impact from this investigation or any conditional fix. Investigation
  work is read-only inspection (DNS lookup, HTTP check, config inspection); no new
  compute resources are consumed.
- **Risks and mitigations:**
  - Risk: acting on the config-tool label without verification could disrupt working
    production OAuth flows. Mitigation: acceptance criteria explicitly forbid any
    change while the root cause is unconfirmed (see `requirements.md`).
  - Risk: if a genuine divergence is confirmed, a rushed OAuth allow-list change could
    lock out legitimate users during the transition. Mitigation: Stage 2's fix plan
    must be reviewed and staged (e.g. allow-list both hosts temporarily during cutover)
    before any allow-list entry is removed.
  - Risk: investigation stalls without a clear owner for the config-tool's data source
    if that tool is external to this repo. Mitigation: task list includes an explicit
    "report/ticket" step so the investigation still produces a documented outcome even
    if the tool itself can't be directly edited by this repo.
