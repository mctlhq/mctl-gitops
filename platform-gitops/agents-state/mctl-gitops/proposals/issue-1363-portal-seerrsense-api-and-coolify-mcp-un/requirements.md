# Portal: declare seerrsense, api and coolify in mcp-servers.tf in automatic (DCR) mode

## Context

The MCP portal (`mcp.mctl.ai`) is its own OAuth client against every upstream
and receives only the scopes its registration names. `infrastructure/cloudflare/portal/README.md`
("Why the scope needs describing at all") records the 2026-09-12 failure this
produced for `tg`: a send came back as a dry-run preview because the portal had
been registered by hand with two read scopes. `seerrsense` now shows the same
failure from the other direction — its registration was made through the
dashboard with no `scope` at all, so seerrsense's authorize endpoint grants its
read-only default and `seerrsense_request_media` answers `this token is not
granted the seerr:request scope` (mctlhq/seerrsense#73). A refresh never widens
a live grant.

The declarative cure is not another hand-pinned scope string. The registration
rule in mctlhq/.github#137 puts every upstream in **automatic (DCR)** mode,
where an unnamed scope means the upstream's full `scopes_supported`, and where
Cloudflare can refresh the tool catalogue instead of freezing it at the first
login. Today `infrastructure/cloudflare/portal/mcp-servers.tf` declares only
three of the five live upstreams (`tg` manual, `projects` and `alice` by DCR);
`seerrsense` and `api` are live members with no Terraform resource at all — a
gap the code already acknowledges in `scripts/portal-membership-add.sh` (its
`--check` branch skips the "must be a committed resource" gate precisely for
those two) and in `scripts/portal-auth-credentials-drift.py` (`DCR_SERVERS`).
A sixth server, `coolify` (`https://coolify.mctl.ai/mcp`), is not on the portal
at all.

## User stories

- AS the platform owner I WANT `seerrsense` registered in automatic mode SO
  THAT the portal's token carries `seerr:request` and `request_media` files a
  request instead of refusing.
- AS the platform owner I WANT every live portal upstream declared in
  `mcp-servers.tf` SO THAT no upstream's registration exists only as a
  dashboard click nobody can review or restore.
- AS the platform owner I WANT `coolify` reachable through the portal with its
  destructive tools disabled by default SO THAT I gain Coolify read access
  without gaining a one-click `stop_all_apps`.
- AS an operator I WANT the nightly registration and catalogue detectors to
  keep covering the portal after these servers land SO THAT a green nightly run
  still means something.
- AS a reviewer I WANT the mode switch on a live server to be a deliberate,
  measured step SO THAT no apply silently replaces a working upstream.

## Acceptance criteria (EARS)

- WHEN the portal root is applied THE SYSTEM SHALL declare `seerrsense`, `api`
  and `coolify` as `cloudflare_zero_trust_access_ai_controls_mcp_server`
  resources in `infrastructure/cloudflare/portal/mcp-servers.tf` with
  `auth_type = "oauth"`, no `auth_credentials` and no `client_secret`, which is
  the shape `projects` and `alice` already use for automatic (DCR) mode.
- WHEN a resource is added for a server that is already live (`seerrsense`,
  `api`) THE SYSTEM SHALL adopt it with an `import` block, exactly as the `tg`
  resource does, and SHALL NOT plan a create or a replacement for it.
- IF `tofu plan` for the portal root reports any resource as destroyed or
  replaced THEN THE SYSTEM SHALL fail the change and SHALL NOT be applied
  (`cloudflare-apply.yml` defaults `allow_destroy` to false).
- WHILE mctlhq/seerrsense#74 (portal-restricted DCR granting the full default
  to DCR clients) is unreleased THE SYSTEM SHALL NOT switch the live
  `seerrsense` server out of manual mode.
- IF the fix is needed before mctlhq/seerrsense#74 ships THEN THE SYSTEM SHALL
  import `seerrsense` as manual with
  `scope = "seerr:read seerr:request offline_access"`, modelled on the `tg`
  resource and its `local.tg_scope`.
- WHEN `api` is switched to automatic mode THE SYSTEM SHALL first confirm that
  `https://api.mctl.ai/oauth/register` restricts DCR to
  `https://mcp.mctl.ai/servers-callback`, per mctlhq/.github#137.
- WHEN a live manual server must become automatic THE SYSTEM SHALL first
  measure whether the mode can be changed in place on a throwaway server
  created and destroyed for the purpose, as the README's other measurements
  were made, and SHALL only then touch `seerrsense` or `api`.
- IF an in-place mode switch is not possible THEN THE SYSTEM SHALL recreate the
  server deliberately and SHALL re-run `scripts/portal-membership-add.sh <id>`
  and the owning repository's `scripts/portal-allowlist-apply.sh` afterwards, so
  that no tool decision is lost.
- WHEN `coolify` is created THE SYSTEM SHALL leave it in `waiting` until an
  admin completes the upstream login once, and SHALL then add it with
  `scripts/portal-membership-add.sh coolify`, which writes every advertised tool
  with `enabled: false`.
- WHILE `coolify` has no `docs/portal-allowlist.json` in `mctlhq/mctl-coolify-mcp`
  THE SYSTEM SHALL keep every coolify tool disabled on the portal.
- WHEN a DCR-registered server is added to the portal root THE SYSTEM SHALL
  name it in `DCR_SERVERS` in `scripts/portal-auth-credentials-drift.py`,
  because that script raises `Undetermined` (exit 2, aborting the whole scan)
  for any non-DCR server in state that holds no `auth_credentials`.
- WHEN a server becomes a portal member THE SYSTEM SHALL name its owning
  repository in `OWNERS` in `scripts/portal-catalogue-drift.py`, because a
  mapped server absent from `OWNERS` is reported undetermined rather than
  skipped.
- WHEN the change is merged THE SYSTEM SHALL leave both detectors' `--selftest`
  green, since `validate-manifests.yml` runs them on every pull request.
- WHEN the comment block above the `projects` resource is updated THE SYSTEM
  SHALL no longer claim "The three above are `auth_mode: manual`", which is
  false once only `tg` is manual.
- WHEN the apply is done THE SYSTEM SHALL require `seerrsense` and `api` to be
  signed out and back in from the portal dashboard, because a new registration
  is a new grant and a refresh is bound to the original one.
- WHEN acceptance is checked THE SYSTEM SHALL file *Ratatouille* (2007, TMDB
  2062) through `seerrsense_request_media` via the portal instead of answering
  `this token is not granted the seerr:request scope`.
- WHEN acceptance for `coolify` is checked THE SYSTEM SHALL show the server out
  of `waiting` with a populated catalogue, and a read-only tool (for example
  `get_version`) answering through the portal once enabled.

## Out of scope

- `tg`: stays manual with its pinned `local.tg_scope` until mctl-telegram
  conforms to mctlhq/.github#137. Only the stale comment near it is corrected.
- Changing any upstream's server-side scope defaults. The server-side
  alternative for seerrsense (seerrsense#72) was proposed and dropped.
- Deciding which coolify tools are enabled. That decision belongs in a new
  `docs/portal-allowlist.json` in `mctlhq/mctl-coolify-mcp`, applied from that
  repository; this proposal only adds the member with everything disabled.
- Ending the unapproved DevLoop execution for seerrsense#73 — tracked in
  mctlhq/mctl-api#392.
- `mctl-mcp`, a public directory entry rather than a server.
- Any Kubernetes, ArgoCD or Helm change; this touches only the Cloudflare
  portal OpenTofu root, two Python detectors and their documentation.

## Open questions

- Can the Cloudflare provider/API clear a stored manual registration in place,
  leaving the server in automatic mode? The README measured that only the
  `auth_type: bearer` flip clears `auth_config_summary`, and that a switch back
  *to* manual requires a `client_secret`; a flip back to `oauth` with **no**
  `auth_credentials` has not been measured. Task 1 measures it on a throwaway
  server before anything live is touched. Assumption used meanwhile: it works,
  with deliberate recreate as the documented fallback.
- Is `mctlhq/mctl-coolify-mcp` private? If so, `coolify` must also join
  `PRIVATE_OWNERS` in `scripts/portal-catalogue-drift.py` so its allowlist is
  fetched through the contents API with `ALLOWLIST_TOKEN`, the way `projects`
  is. Assumed private until checked, since that is the safe direction (a public
  repo fetched with a token still works).
- `alice` is declared in `mcp-servers.tf` as a DCR server but appears in
  neither `DCR_SERVERS` nor `OWNERS`. If it has already been applied, the
  nightly registration check is aborting today. This proposal fixes it in
  passing; a reviewer should confirm whether `alice` is applied and whether a
  separate issue already covers it.
- `KNOWN_STALE[("seerrsense", "closed-output-schemas")]` expires 2026-10-15 and
  names five tools. If the #74 release changes seerrsense's tool set, the
  post-switch re-snapshot may make that waiver wider than what fires (exit 3).
  Whether to narrow or delete it is left to the run that observes it.
- Does an admin login for `coolify` snapshot a different tool set than a
  non-admin one, as `projects` does? Unknown; the login should be done by the
  owner address to match the `projects`/`alice` precedent.
