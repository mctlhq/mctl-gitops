# Tasks: issue-1417-docs-cloudflare-iac-portal-root-mcp-port

- [ ] 1. Re-read the ground truth before writing a word: `infrastructure/cloudflare/portal/README.md`,
  `infrastructure/cloudflare/account/README.md`, `portal/mcp-portal.tf`,
  `portal/mcp-servers.tf`, `account/portal-app.tf`, `account/portal-mcp-apps.tf`,
  `portal/allowlists/mapping.json`, `portal/versions.tf` and
  `portal/.terraform.lock.hcl` — DoD: a scratch list of the six server resource
  addresses, every `lifecycle.ignore_changes` block, the resolved provider
  version (5.24.0) and the exact line numbers of the two stale passages
  (`portal/README.md` ~104-107, `account/README.md` ~78-80).

- [ ] 2. Add the "Provider support" section to `infrastructure/cloudflare/portal/README.md`,
  inserted after the opening paragraph (after the line ending "Both have been
  retired.") and before "## What is pinned, and why each field" (depends on 1) —
  DoD: the section states the verdict **supported** for
  `cloudflare_zero_trust_access_application.type = "mcp_portal"` in
  `cloudflare/cloudflare` 5.x (measured 2026-09-12, lock 5.24.0), cites
  `../account/portal-app.tf:32`, apply run **35798537646** and the zero-diff
  nightly drift record since; it also names the two portal resource types in
  state (portal import #1370, apply run 36117508212) and closes with the two
  provider limits — `auth_credentials` write-only, catalogue `tools` typed
  `list(map(string))` and therefore empty in state (#1382).

- [ ] 3. Add the per-resource table to `infrastructure/cloudflare/portal/README.md`
  under a new heading ("What each resource manages, and what it deliberately does
  not"), immediately after the section from task 2 (depends on 2) — DoD: a
  markdown table with exactly the four content columns *managed fields* /
  *`ignore_changes`* / *write-only or secret-bootstrap
  (`interactive-secret-bootstrap`, never committed)* / *runtime state excluded*,
  and rows for: the portal object, each of `tg`, `api`, `seerrsense`,
  `projects`, `alice`, `coolify`, the `mcp_portal` Access application, the three
  managed `mcp` member applications, and the three deliberately unmanaged `mcp`
  siblings (`api`, `tg`, `seerrsense`). Every row names its file path. No claim
  in the table is absent from a `.tf` file or from an existing README paragraph.

- [ ] 4. Add the "Deliberately not in Git" section to
  `infrastructure/cloudflare/portal/README.md`, directly after the table
  (depends on 3) — DoD: it names per-user upstream OAuth grants, Access user
  sessions, and the server runtime fields `status`, `last_synced`,
  `authentication_status`; gives the reason as `runtime-user-state` under
  `mctlhq/.github#47`; and points at
  `.github/workflows/cloudflare-portal-health.yml`,
  `scripts/portal-auth-credentials-drift.py` and
  `scripts/portal-catalogue-drift.py` as what watches that state instead.

- [ ] 5. Fix the stale allowlist bullet at `infrastructure/cloudflare/portal/README.md`
  ~104-107 (depends on 1) — DoD: the bullet no longer says the allowlists are
  "applied from those repositories"; it says `ignore_changes` on each server
  resource exists because `mcp-portal.tf` is the single writer of the portal
  mapping since #1370, with the decision still owned by each repo's
  `docs/portal-allowlist.json`, vendored byte-identical into
  `allowlists/<id>.json` by `.github/workflows/portal-allowlist-vendor.yml`.
  `grep -n "applied from those repositories" infrastructure/cloudflare/portal/README.md`
  returns nothing.

- [ ] 6. Fix the stale import line at `infrastructure/cloudflare/account/README.md`
  ~78-80 (depends on 1) — DoD: the `#1092` bullet states the portal object was
  imported into `../portal/` in #1370 (plan `1 to import, 0 to change`, apply run
  36117508212) and that its allowlists are vendored into that root; it records
  that what remains unimported here is the three sibling `mcp` applications
  (`api`, `tg`, `seerrsense`), a separate child of #1092.
  `grep -n "still unimported" infrastructure/cloudflare/account/README.md`
  returns nothing.

- [ ] 7. Add the two cross-references (depends on 2, 3, 4) — DoD:
  (a) one line beside `infrastructure/cloudflare/README.md:6` pointing at the
  `mcp_portal` provider verdict in `portal/README.md`; (b) one sentence in
  `infrastructure/cloudflare/account/README.md` near the Access applications
  noting that Access user sessions are deliberately not in Git and pointing at
  the portal README's "Deliberately not in Git" section and the per-resource
  table.

- [ ] 8. Extend the existing "To add a seventh server" checklist in
  `infrastructure/cloudflare/portal/README.md` with a step: add the new server's
  row to the per-resource table (depends on 3) — DoD: the checklist step exists,
  so the table has a named upkeep owner rather than becoming the next stale
  passage.

- [ ] 9. Open the pull request from a feature branch (depends on 2-8) — DoD:
  `git diff --stat origin/main` lists only `infrastructure/cloudflare/portal/README.md`,
  `infrastructure/cloudflare/account/README.md` and
  `infrastructure/cloudflare/README.md`; the PR body records that the #1083
  issue-body matrix still needs the same one-line verdict added by hand, since a
  pull request cannot edit an issue; the PR references `Refs mctlhq/mctl-gitops#1092`
  and closes #1417.

## Tests

- [ ] T1. No configuration moved: `git diff --name-only origin/main` contains no
  path ending in `.tf`, `.json`, `.yml`, `.yaml`, `.py` or `.sh`. This is the
  proposal's central invariant — docs only, no apply.
- [ ] T2. Plans are unchanged: `cloudflare-plan` is green on the pull request.
  It runs the full per-root matrix (its `changes` job matches
  `^infrastructure/cloudflare/`), and a documentation-only diff must produce the
  same plans as `main` — any diff there means task 1's read turned into an edit.
- [ ] T3. `yamllint` and `validate-manifests` are green. `yamllint.yml` filters
  on `platform-gitops/**` and should not run at all; if it does, something
  outside this directory was touched.
- [ ] T4. Stale lines are gone: `grep -rn "applied from those repositories\|still unimported" infrastructure/cloudflare/`
  returns nothing.
- [ ] T5. New facts are present and citable:
  `grep -rn "35798537646" infrastructure/cloudflare/portal/README.md` and
  `grep -rn "runtime-user-state" infrastructure/cloudflare/portal/README.md`
  each return at least one line.
- [ ] T6. Table completeness, by eye against `mcp-servers.tf`: the six server
  resource ids in the table are exactly `tg`, `api`, `seerrsense`, `projects`,
  `alice`, `coolify` — the same set as
  `grep -c 'resource "cloudflare_zero_trust_access_ai_controls_mcp_server"' infrastructure/cloudflare/portal/mcp-servers.tf`
  (6) and as the keys of `portal/allowlists/mapping.json`.
- [ ] T7. Table accuracy, by eye: every row whose `ignore_changes` cell names
  `updated_tools` / `updated_prompts` corresponds to a real `lifecycle` block in
  `mcp-servers.tf`, and no row claims a field the resource does not declare —
  in particular the `mcp_portal` row must show `oauth_configuration` as
  deliberately unset, matching `account/portal-app.tf` lines 21-23.
- [ ] T8. Markdown renders: the new table has a header row, a separator row and
  the same column count on every line; the README opens cleanly in a markdown
  viewer. There is no markdown linter in this repository, so this check is
  manual and the reviewer owns it.

## Rollback

Documentation-only, so rollback is a revert and nothing else: `git revert` the
merge commit on `main`, or open a follow-up pull request restoring the two
README files. Nothing needs to be applied, un-applied or re-imported —
`cloudflare-apply.yml` is never dispatched for this change, the OpenTofu state
of both roots is untouched, and the nightly `cloudflare-drift.yml` result is
identical before and after.

Partial rollback is also safe and may be the better answer if one row of the
table turns out to be wrong: delete or correct that row in a follow-up pull
request rather than reverting the whole change, since the provider verdict, the
runtime-state paragraph and the two stale-line fixes are independent of each
other and of any individual row.
