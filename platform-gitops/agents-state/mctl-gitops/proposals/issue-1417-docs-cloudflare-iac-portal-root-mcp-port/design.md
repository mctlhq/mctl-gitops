# Design: issue-1417-docs-cloudflare-iac-portal-root-mcp-port

## Current state

### The two roots and what each owns

`infrastructure/cloudflare/` holds one OpenTofu root per directory containing a
`versions.tf` (`infrastructure/cloudflare/README.md`, "Layout"). Two of them
matter here:

- **`infrastructure/cloudflare/portal/`** — the MCP portal object
  (`mcp-portal.tf`) and its six upstream servers (`mcp-servers.tf`). Applied
  with `CF_APPLY_TOKEN_PORTAL`, scoped to `Account -> MCP Portals` alone
  (`portal/versions.tf`, comment above `provider "cloudflare" {}`). State key
  `cloudflare/portal/terraform.tfstate`.
- **`infrastructure/cloudflare/account/`** — the Access applications, including
  the `mcp_portal` application for `mcp.mctl.ai` (`portal-app.tf`) and the
  three `mcp` member applications (`portal-mcp-apps.tf`). Applied with
  `CF_APPLY_TOKEN_ACCOUNT`.

The split is deliberate and stated in `portal/README.md` lines 42-47: one write
token per root, so folding the MCP resources into `account/` would widen that
root's credential to `MCP Portals`.

Both roots pin `cloudflare/cloudflare` `~> 5` (`portal/versions.tf`,
`account/versions.tf`); `portal/.terraform.lock.hcl` resolves 5.24.0.

### What is already written down, and where

`portal/README.md` is long and prose-heavy. It already carries:

- the portal import record — lines 3-11: imported 2026-09-25 under #1370, plan
  `1 to import, 0 to change`, apply run 36117508212;
- which portal fields are pinned and why — lines 13-33 (`secure_web_gateway`,
  `code_mode`/`allow_code_mode`, `name`/`description`, `servers`);
- `auth_credentials` being write-only, with the measured evidence that it
  produces neither a perpetual diff nor drift detection — lines 78-94, and the
  compensating `scripts/portal-auth-credentials-drift.py`;
- the interactive first-login step Terraform cannot perform — lines 142-162
  ("What Terraform cannot do here") and the `mcp-servers.tf` comments at lines
  78-95 and 169-178;
- the mapping pipeline — lines 243-264: `mcp-portal.tf` builds `updated_tools`
  from `allowlists/<id>.json`, `allowlists/mapping.json` and
  `allowlists/catalogue.json`, and `catalogue.json` exists because provider 5.24
  types the catalogue attribute `tools` as `list(map(string))`, so it is empty
  in state (measured on #1382).

What it does **not** carry: any statement that `mcp_portal` is a supported
provider value, any per-resource table, and any statement about runtime state.
`grep -rn "35798537646\|runtime-user-state"` over the clone returns nothing.

### The facts that are true but scattered

- **All six servers are DCR.** `mcp-servers.tf` declares `tg`, `projects`,
  `alice`, `coolify`, `seerrsense`, `api`, each `auth_type = "oauth"` with no
  `auth_credentials` and no `client_secret` — the file's header comment (lines
  1-20) states that supplying either is what opts a server into manual mode.
  `tg` and `api` moved on 2026-09-26; `seerrsense` on 2026-09-25.
- **Every server carries the same `lifecycle` block**: `ignore_changes =
  [updated_tools, updated_prompts]` (lines 52-56, 108-115, 155-159, 191-195,
  241-245, 283-287), each with the same comment — `mcp-portal.tf` writes the
  mapping, so declaring it on the server too would give this root two writers.
- **The portal mapping inputs are per-server settings that are not the owning
  repo's call**: `allowlists/mapping.json` carries `vendored`,
  `default_disabled`, `on_behalf` and `updated_prompts` for each of the six
  (all six `vendored: true`, `default_disabled: false`, `on_behalf: true`;
  only `coolify` has a non-null `updated_prompts`, three prompts disabled).
- **The `mcp_portal` Access application** (`account/portal-app.tf`) is adopted
  for `session_duration = "8760h"`, with `type = "mcp_portal"` on line 32,
  `oauth_configuration` deliberately unset (lines 21-23), three cookie fields
  pinned to live values so the import does not change the portal's cookie
  (lines 53-58), and `policies` referenced by id (lines 60-69) so the policy
  body stays as it is.
- **The `mcp` member applications** (`account/portal-mcp-apps.tf`) exist for
  `projects`, `alice` and `coolify`; the three pre-existing siblings for `api`,
  `tg` and `seerrsense` are live, unmanaged and deliberately left out (lines
  33-36), because importing them is its own reviewed change.

### The two stale lines the audit found

1. `portal/README.md` lines 104-107: "`updated_tools` / `updated_prompts` are in
   `ignore_changes`. They are the allowlists owned by `mctl-telegram`,
   `mctl-api` and `seerrsense`, **applied from those repositories**. Nothing
   here sets them, so nothing here can revert them." Contradicted by
   `mcp-portal.tf` lines 1-15 and by `portal/README.md`'s own lines 243-264:
   since #1370 this root is the single writer and the allowlists are vendored.
2. `account/README.md` lines 78-80: "The portal object itself is **still
   unimported**; it carries the tool allowlists owned by three other
   repositories, so adopting it is a separate decision." Contradicted by
   `portal/README.md` lines 3-11.

### What CI does with a documentation-only change here

- `.github/workflows/cloudflare-plan.yml` has **no `paths:` filter** by design
  (header comment, lines 10-14); its `changes` job greps the diff for
  `^infrastructure/cloudflare/`, so a README-only change under that prefix sets
  `changed=true` and the workflow runs `fmt`, `validate` and a plan **per root**.
  That is a read-only job and must come back with the same plans as `main`,
  which a documentation-only diff guarantees — but it does mean the PR is not
  "CI does nothing".
- `.github/workflows/yamllint.yml` filters on `platform-gitops/**` only, so it
  does not run for this change.
- There is **no markdown linter** in the repository: no `.markdownlint*` config
  at the root, and no workflow referencing `markdown`, `mdformat`, `lychee` or a
  link checker.

## Proposed solution

Three documentation edits and two line fixes, in two files, plus one
cross-reference line. No `.tf`, `.json` or workflow file is touched.

### 1. `infrastructure/cloudflare/portal/README.md` — a "Provider support" section

Inserted immediately after the opening paragraph (after line 11), before "What
is pinned, and why each field", because it answers the question a reader has
before they read any field list.

Content, all of it citable:

- Verdict: **supported**. `cloudflare_zero_trust_access_application.type`
  accepts `mcp_portal` in `cloudflare/cloudflare` 5.x (measured 2026-09-12,
  recorded on #1092); the lock file in both roots resolves 5.24.0.
- The proof is a round trip, not a documentation claim:
  `infrastructure/cloudflare/account/portal-app.tf:32` declares
  `type = "mcp_portal"`, it was imported in apply run 35798537646, and every
  nightly `cloudflare-drift.yml` run since has been zero-diff for that root.
- The two portal resource types themselves —
  `cloudflare_zero_trust_access_ai_controls_mcp_portal` and
  `..._mcp_server` — are likewise supported and in state (the portal import,
  #1370, apply run 36117508212).
- And the boundary, so "supported" is not over-read: `auth_credentials` is
  write-only (the provider cannot read it back, so it detects no drift on it —
  `portal/README.md` "The field OpenTofu cannot see"), and the catalogue
  attribute `tools` is typed `list(map(string))` in 5.24 while the API's tool
  objects are nested, so it is empty in state and `allowlists/catalogue.json`
  exists to stand in for it (#1382).

A one-line pointer is added beside
`infrastructure/cloudflare/README.md:6` ("Inventory and the zero-diff proof:
`mctl-gitops#1083`") naming where the `mcp_portal` verdict lives, so the
"root README" reading of criterion 2 that means the directory README is also
satisfied without duplicating the text.

### 2. `infrastructure/cloudflare/portal/README.md` — the per-resource table

A new section, "What each resource manages, and what it deliberately does not",
placed after the "Provider support" section. One row per resource, four content
columns exactly as the issue specifies:

| Resource | Managed fields | `ignore_changes` | Write-only / `interactive-secret-bootstrap` | Runtime state excluded |

Rows:

1. `cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp` (`mcp-portal.tf`) —
   managed: `hostname`, `name`, `description`, `secure_web_gateway`,
   `code_mode`, `allow_code_mode`, `servers[]` (`server_id`,
   `default_disabled`, `on_behalf`, `updated_prompts`, `updated_tools` built
   from the three `allowlists/` files); none ignored; no secret; excluded: the
   synced catalogue `tools`, unreadable in 5.24.
2-7. One row per server, `tg`, `api`, `seerrsense`, `projects`, `alice`,
   `coolify` (`mcp-servers.tf`) — managed: `account_id`, `id`, `name`,
   `hostname`, `auth_type = "oauth"`, `description`, `secure_web_gateway`,
   `is_shared_oauth_callback_enabled`; ignored: `updated_tools`,
   `updated_prompts` (single-writer rule); secret-bootstrap: the first upstream
   OAuth login completed once from the dashboard ("Authenticate server"), which
   mints the admin credential used for every later sync and is never committed —
   `interactive-secret-bootstrap`; excluded: `status`, `last_synced`,
   `last_successful_sync`, `authentication_status`, `tools`. The historical
   manual-mode fields `auth_credentials` and `client_secret` get a footnote:
   write-only, no server carries them today, and `client_secret_version` is what
   `scripts/portal-auth-credentials-drift.py` compares.
8. `cloudflare_zero_trust_access_application.mcp_portal` (`account/portal-app.tf`)
   — managed: `name`, `type = "mcp_portal"`, `domain`, `destinations`,
   `allowed_idps`, `auto_redirect_to_identity`, `cors_headers`,
   `session_duration = "8760h"`, the three cookie fields; unmanaged by
   intention: `oauth_configuration` (enabling Access managed OAuth would replace
   the portal's own authorization server under every connected client) and the
   policy body, referenced by id `5f0102c7-…`; excluded: Access user sessions.
9. `cloudflare_zero_trust_access_application.portal_member_{projects,alice,coolify}`
   (`account/portal-mcp-apps.tf`) — managed: `name`, `type = "mcp"`,
   `destinations` (`via_mcp_server_portal` + `mcp_server_id`),
   `session_duration`, inline `policies`; excluded: Access user sessions.
10. The three pre-existing `mcp` applications for `api`, `tg` and `seerrsense` —
   **unmanaged in full**, deliberately, pending the separate import child of
   #1092.

The table lives in the portal README even though rows 8-10 are resources of the
`account/` root, because a reader asking "what does Git own about the portal"
should not have to know the root split first. Each of those rows names its file
path, and `account/README.md` gets a pointer to the table.

### 3. `infrastructure/cloudflare/portal/README.md` — "Deliberately not in Git"

A short section after the table, stating the exclusion positively:

- per-user upstream OAuth grants (the grant a person's dashboard login creates
  against an upstream);
- Access user sessions;
- server runtime sync status: `status`, `last_synced`, `authentication_status`.

With the reason: this is `runtime-user-state` under `mctlhq/.github#47` — it is
per-person, time-varying and not a desired state anything could reconcile
towards; declaring it would make every plan red on a normal login. And with the
pointer to what does watch it instead:
`.github/workflows/cloudflare-portal-health.yml` (hourly per-server health),
`scripts/portal-auth-credentials-drift.py` and
`scripts/portal-catalogue-drift.py` (nightly from `cloudflare-drift.yml`).

`account/README.md` gets a one-sentence version for Access user sessions, its
own surface, pointing at the portal README for the full list.

### 4. The two stale line fixes

- `portal/README.md` ~104-107: rewrite the bullet. `updated_tools` /
  `updated_prompts` are in `ignore_changes` on each **server** resource because
  `mcp-portal.tf` is the single writer of the portal mapping (#1370) — not
  because the allowlists are applied from the service repositories. The decision
  about a tool still belongs to the owning repository's
  `docs/portal-allowlist.json`, vendored byte-identical into
  `allowlists/<id>.json` by `.github/workflows/portal-allowlist-vendor.yml`; the
  write is here.
- `account/README.md` ~78-80: rewrite the struck-through `#1092` bullet's tail.
  The portal object was imported into `../portal/` in #1370 (plan
  `1 to import, 0 to change`, apply run 36117508212), and its tool allowlists
  are vendored into that root rather than applied from three other
  repositories. What remains unimported here is the three sibling `mcp`
  applications, which is the separate child of #1092.

## Alternatives

**A new `docs/` page instead of editing the two READMEs.** Rejected. Every
comparable decision in this area is recorded next to the configuration it
governs — `portal/README.md`, `account/README.md`,
`zones/mctl-ai/README.md` — and `infrastructure/cloudflare/README.md`'s
break-glass section is the only thing that delegates to `docs/runbooks/`, for a
procedure rather than a fact. A third location would make four places to check
and would not remove either stale line, which is half the issue.

**Generating the table from the `.tf` files with a script (a `terraform-docs`-style
step, or a new `scripts/validate-portal-*.py` that asserts the table matches
`ignore_changes`).** Attractive because the table can go stale exactly the way
the two lines being fixed did. Rejected for this proposal: the issue is
explicitly docs-only, a generator would need a HCL parser that this repository
deliberately avoids (`mcp-portal.tf` lines 8-12 note that `mapping.json` exists
so "neither side needs an HCL parser"), and the most valuable columns —
`interactive-secret-bootstrap` and "runtime state excluded" — are judgements
that exist in no `.tf` attribute and could not be generated. Worth a follow-up
issue for the `ignore_changes` column alone.

**Putting the provider verdict in `account/README.md` instead**, since
`portal-app.tf` lives in that root. Rejected as the primary location: scope
item 1 of the issue names `portal/README.md`, and a reader asking the
`mcp_portal` question is reading about the portal, not about R2 buckets and
organization settings. `account/README.md` gets a pointer instead, which costs
one line and keeps a single source.

**Fixing only the two stale lines and deferring items 1-3.** Rejected: the stale
lines are the cheapest quarter of the work and the three missing records are the
ones #1092 is actually blocked on.

## Platform impact

- **Migrations:** none. No state, no schema, no resource.
- **Backward compatibility:** total. Every `.tf`, `.json` and workflow file is
  byte-identical after the change, so `tofu plan` output for both roots is
  unchanged and the nightly `cloudflare-drift.yml` behaviour is unchanged.
- **Resource impact:** none in Cloudflare. In CI, the pull request does run the
  full `cloudflare-plan` matrix (its `changes` job matches
  `^infrastructure/cloudflare/`), which is a handful of read-only plan jobs —
  the same cost as any other pull request in this directory.
- **Risk: the table goes stale.** It is a snapshot of six servers and four
  applications, and the last two months of this directory show exactly how that
  ends (two stale lines, this issue). Mitigations: every row cites its file and
  resource address so a reader can check it in one `grep`; the table is placed
  in the same file as the "To add a seventh server" checklist
  (`portal/README.md`), and that checklist gains a step telling the author to
  add the server's row. A generated table is recorded above as the follow-up.
- **Risk: the verdict is recorded for a provider version that moves.** The note
  pins the measurement to `cloudflare/cloudflare` 5.x with the lock file's
  5.24.0 and the date, so a future 6.x reader knows what was measured rather
  than inheriting an undated claim.
- **Risk: a reader treats "supported" as "everything is in Git".** Mitigated by
  design: the provider-support section ends with the two known limits, and the
  "Deliberately not in Git" section follows immediately after the table.
- **Risk: an implementer edits a `.tf` file to make a table row true.** The
  requirements state the invariant (`.tf` untouched); the reviewer should check
  `git diff --stat` shows only `.md` files.
- **Security:** nothing secret is written. The `interactive-secret-bootstrap`
  column records that a credential exists and how it is minted, never its value;
  the policy id and account id already appear in these files and this repository
  is public, which is consistent with the existing `portal-app.tf` comments.
