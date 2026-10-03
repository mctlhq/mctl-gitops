# Import the tg / seerrsense / api MCP Access applications and the portal policies into the account root

## Context

`infrastructure/cloudflare/account/` manages the Access side of the private MCP
portal: the portal's own application (`portal-app.tf`,
`cloudflare_zero_trust_access_application.mcp_portal`, adopted by an `import`
block) and three `type = "mcp"` member applications created by OpenTofu for
`projects`, `alice` and `coolify` (`portal-mcp-apps.tf`). Three sibling member
applications — for `tg`, `seerrsense` and `api` — were created by hand in the
dashboard on 2026-09-10 and were deliberately left out of state;
`portal-mcp-apps.tf:34-36` records that decision and says importing them is its
own reviewed change. The policies those three applications carry are outside
state for the same reason, and the `mcp_portal` application's policy
`5f0102c7-fd88-499c-9b15-9167633d6c63` is referenced by id only
(`portal-app.tf:64-69`) with no resource behind it.

An object that is not in state is invisible to `cloudflare-drift.yml` —
OpenTofu only compares what it tracks — so today a dashboard edit to any of
those three applications, or to any of their policies, would change who can
reach `tg`, `seerrsense` or `api` through `mcp.mctl.ai` and no scheduled run
would ever go red. Closing that gap is acceptance criterion 1 of
mctlhq/mctl-gitops#1092 ("Portal, three MCP servers, both Access applications
and their policies imported; `tofu plan` prints `No changes`"). This proposal is
the description-only half: add `import` blocks and resource bodies that describe
exactly what is live, so the PR's `cloudflare-plan` check for `account` reads
`N to import, 0 to add, 0 to change, 0 to destroy`. The import apply itself is
an owner-dispatched, environment-approved `cloudflare-apply.yml` run after
merge.

## User stories

- AS the platform owner I WANT the `tg`, `seerrsense` and `api` portal member
  applications in OpenTofu state SO THAT a hand edit to any of them is reported
  by the nightly drift run instead of living unseen.
- AS the platform owner I WANT every policy those applications and the
  `mcp_portal` application reference declared in Git SO THAT who may reach the
  private aggregate is reviewable in a pull request rather than only in the
  dashboard.
- AS a reviewer I WANT the adoption to plan as import-only SO THAT I can see the
  change adopts what exists and alters no grant.
- AS a future maintainer I WANT `portal-mcp-apps.tf`'s header comment to stop
  saying the three siblings stay out of state SO THAT the file does not
  contradict the state it now describes.

## Acceptance criteria (EARS)

- WHEN a pull request implementing this proposal is opened THE SYSTEM SHALL
  produce a `cloudflare-plan` result for `infrastructure/cloudflare/account`
  whose summary table reads `N to import, 0 to add, 0 to change, 0 to destroy`,
  with `N` equal to the three member applications plus every reusable policy
  resource newly declared.
- WHEN the configuration for `tg`, `seerrsense` and `api` is written THE SYSTEM
  SHALL declare one `cloudflare_zero_trust_access_application` resource per
  application, each paired with an `import` block whose id is
  `accounts/${var.account_id}/<live application id>`.
- WHEN a policy those applications reference is a reusable (account-level)
  Access policy THE SYSTEM SHALL declare exactly one
  `cloudflare_zero_trust_access_policy` resource for it, paired with an `import`
  block whose id is `accounts/${var.account_id}/<live policy id>`, and
  reference it from every application that uses it by resource attribute rather
  than by a repeated literal id.
- IF two of the adopted applications reference the same live policy object THEN
  THE SYSTEM SHALL reference the single resource declared for it from both, and
  SHALL NOT declare a second resource for the same object.
- IF a policy an adopted application references is app-scoped rather than
  reusable — not returned by `GET /accounts/{account_id}/access/policies` —
  THEN THE SYSTEM SHALL describe it inline in that application's `policies`
  list at its live values and SHALL NOT declare a standalone policy resource for
  it, and SHALL record in a comment why that policy has no resource of its own.
- WHEN the `mcp_portal` application's policy `5f0102c7-fd88-499c-9b15-9167633d6c63`
  turns out to be a reusable policy THE SYSTEM SHALL replace the literal id in
  `portal-app.tf` with a reference to the imported policy resource, and the plan
  for that application SHALL still read `0 to change`.
- WHILE the three applications are being described THE SYSTEM SHALL record their
  live attribute values — `session_duration`, `allowed_idps`,
  `auto_redirect_to_identity`, cookie flags, `destinations` — rather than the
  values the already-managed siblings use, so that nothing but state changes.
- WHILE the proposal is in effect THE SYSTEM SHALL leave every policy's
  `decision`, `include`, `exclude` and `require` exactly as Cloudflare returns
  them, so no identity gains or loses access.
- WHEN the resource bodies are produced THE SYSTEM SHALL derive them with
  `tofu plan -generate-config-out` and reduce the generated output, per
  `docs/runbooks/cloudflare-operations.md` step 2 and
  `infrastructure/cloudflare/zones/mctl-me/README.md` ("How the configuration
  got here"), rather than hand-writing bodies and applying to make them fit.
- WHEN the change lands THE SYSTEM SHALL update the header comment of
  `infrastructure/cloudflare/account/portal-mcp-apps.tf` (currently lines 34-36)
  so it no longer states that the three pre-existing sibling applications stay
  out of state, and SHALL point at where they are now declared.
- IF the plan for `account` shows any `add`, `change` or `destroy` THEN THE
  SYSTEM SHALL have its configuration corrected and re-planned, and SHALL NOT be
  merged on the argument that an apply would reconcile it.
- WHILE the merge commit is on `main` and the import apply has not yet run THE
  SYSTEM SHALL be expected to report `DRIFT` for `account` on the scheduled
  `cloudflare-drift.yml` run, which clears once the owner-approved import apply
  completes.

## Out of scope

- Any change to what the applications or policies allow: no address added or
  removed, no `decision`, `include`, `require` or `exclude` edited, no
  identity provider added.
- Harmonizing the three adopted applications' `session_duration` with the
  `8760h` the managed siblings use. If the live value differs (the dashboard
  default is 24h), this proposal records the live value; changing it is a
  separate reviewed change with its own plan line.
- The import apply itself — an environment-approved `cloudflare-apply.yml`
  dispatch on `infrastructure/cloudflare/account`, an owner action after merge.
- The MCP portal object and its tool allowlists (`infrastructure/cloudflare/portal/`),
  which are a different root with a different write token and are already
  zero-diff.
- Any change to `cloudflare-plan.yml`, `cloudflare-apply.yml` or
  `cloudflare-drift.yml`: root discovery is automatic and this proposal adds no
  root.
- Importing anything named in the ownership boundary table of
  `infrastructure/cloudflare/README.md` (the `mac-mini-infra` tunnel, DNS
  records and cache ruleset).

## Open questions

- **The live object ids are not in this repository and are the one blocking
  input.** Nothing under `infrastructure/cloudflare/` records the application
  ids for `tg`, `seerrsense` and `api`, nor their policy ids; the only id
  present is the portal's own app `fd76d449-…` and its policy `5f0102c7-…`.
  They must be read from the account with an `Access: Apps and Policies -> Read`
  token — `GET /accounts/{account_id}/access/apps?type=mcp` and
  `GET /accounts/{account_id}/access/policies` — or produced by the
  `-generate-config-out` procedure run against that token. Proceed by writing
  every id in one clearly-marked `locals` block so the values are a single
  reviewed edit, and state in the PR body that the plan cannot be green until
  the owner supplies them.
- Whether the three applications' policies are reusable account-level policies
  or app-scoped policies decides whether `N` is 3 or larger and whether any
  `cloudflare_zero_trust_access_policy` resource exists at all. Assume reusable
  where `GET /access/policies` returns the id, app-scoped otherwise; the two
  branches are specified above and in `design.md`.
- Whether `5f0102c7-…` is the same object the three hand-made applications use.
  If so, one imported policy resource serves all four applications; if not, each
  gets its own and none is duplicated.
- Whether any of the three carries a `domain`, `oauth_configuration` or
  `cors_headers` the managed siblings do not. Resolved by the generated
  configuration, not by assumption — `portal-app.tf:53-58` is the precedent for
  pinning fields the provider would otherwise default and silently change.
- Whether the adopted applications should live in `portal-mcp-apps.tf` beside
  the created ones or in their own file. This proposal chooses a new file and
  a cross-reference, matching how `portal-app.tf` keeps its one adopted
  application separate; a reviewer may prefer them appended instead.
