# Tasks: issue-1363-portal-seerrsense-api-and-coolify-mcp-un

- [ ] 0. Turn DCR on for the portal callback in seerrsense, in its own PR
  ahead of this one. mctlhq/seerrsense#74 shipped in **1.11.0** (live
  2026-09-24) with DCR **off by default**: `SEERRSENSE_DCR_REDIRECT_URIS` has no
  built-in value, and unset means `/register` answers 404 and
  `registration_endpoint` is absent. Add
  `SEERRSENSE_DCR_REDIRECT_URIS: https://mcp.mctl.ai/servers-callback` to the
  env of `platform-gitops/services/labs/seerrsense/values.yaml`, merge it, and
  wait for ArgoCD to sync. — DoD:
  `https://seerrsense.mctl.ai/.well-known/oauth-authorization-server` carries
  `registration_endpoint: https://seerrsense.mctl.ai/register`, and the service
  is Healthy. Task 2's seerrsense probes depend on this: without it they get
  404, and task 5 would fall back to the interim manual path for no reason.

- [ ] 1. Measure whether a live manual-OAuth server can be switched to
  automatic in place, on a throwaway server only. Create one in manual mode
  (a create needs a non-empty `client_secret`), then try (a) a `PUT` with no
  `auth_credentials` and (b) the `auth_type: bearer` -> `auth_type: oauth`
  flip with no `auth_credentials` on the way back; read back
  `auth_config_summary` and `authentication_status` after each; destroy the
  throwaway. — DoD: the result of each lever is written into
  `infrastructure/cloudflare/portal/README.md` as a dated measurement, in the
  style of the existing "What moves the snapshot, measured 2026-09-13" table,
  and the throwaway server no longer exists.

- [ ] 2. Verify the DCR preconditions on the two upstreams that are switching
  (depends on 0 for seerrsense; independent of 1 in practice). For `api.mctl.ai`: a probe
  registration at `/oauth/register` with
  `redirect_uris = ["https://mcp.mctl.ai/servers-callback"]` succeeds, and the
  same probe from a foreign callback is refused (mctlhq/.github#137). For
  `seerrsense`: the same two probes, plus confirmation that a DCR client naming
  no scope is granted exactly `seerr:read seerr:request`. That is
  seerrsense's `DCR_DEFAULT_SCOPE`. `offline_access` is not in it, and a
  refresh token is issued regardless, so its absence is expected, not a
  failure. #74 is already released (1.11.0). — DoD: both probe results
  recorded in the PR description. If the seerrsense probe fails, task 5 takes
  the interim manual path instead of the automatic
  one, and this is stated in the PR.

- [ ] 3. Check whether `mctlhq/mctl-coolify-mcp` is private
  (`gh repo view --json isPrivate`). — DoD: the answer decides whether
  `coolify` joins `PRIVATE_OWNERS` in `scripts/portal-catalogue-drift.py` in
  task 7; recorded in the PR.

- [ ] 4. Add the `coolify` resource to
  `infrastructure/cloudflare/portal/mcp-servers.tf`: automatic (DCR) shape —
  `auth_type = "oauth"`, `hostname = "https://coolify.mctl.ai/mcp"`, no
  `auth_credentials`, no `client_secret`, a description naming the issue, and
  `lifecycle { ignore_changes = [updated_tools, updated_prompts] }`, modelled
  on the `alice` resource. — DoD: `tofu validate` passes and
  `cloudflare-plan.yml` on the PR plans exactly one create and no
  replacements.

- [ ] 5. Add `seerrsense` to `mcp-servers.tf` with an `import` block
  (`id = "${var.account_id}/seerrsense"`) plus a resource (depends on 1, 2).
  Default path: the automatic shape (no `auth_credentials`, no
  `client_secret`). Interim path, taken only if task 2 says #74 is not
  released: manual, with a `local.seerrsense_scope` of
  `"seerr:read seerr:request offline_access"` in the same `locals` block as
  `local.tg_scope`, modelled field-for-field on the `tg` resource. — DoD: the
  PR plan shows an import and **no** replace for `seerrsense`; which path was
  taken is stated in a comment above the resource, with the reason.

- [ ] 6. Add `api` to `mcp-servers.tf` the same way — `import` block for
  `${var.account_id}/api` plus an automatic-shape resource (depends on 1, 2).
  — DoD: the PR plan shows an import and no replace for `api`.
  If task 2 finds that `api.mctl.ai`'s DCR is **not** restricted to the portal
  callback (a foreign-callback probe succeeds), do not switch `api`. Import it
  in its current live mode with no mode change, so it is at least recorded,
  and open an issue in mctlhq/mctl-api for the restriction (mctlhq/.github#137).
  Do not block the rest of this PR on it. Note: such a probe leaves one
  registration row on `api`, which is acceptable.

- [ ] 7. Update the two nightly detectors in the same PR (depends on 4, 5, 6).
  `scripts/portal-auth-credentials-drift.py`: extend `DCR_SERVERS` to
  `{"projects", "alice", "coolify", "api"}` plus `"seerrsense"` unless task 5
  took the interim manual path, and update the comment above it to say why each
  is there. `scripts/portal-catalogue-drift.py`: add
  `"coolify": "mctlhq/mctl-coolify-mcp"` and `"alice": "mctlhq/mctl-alice"` to
  `OWNERS`, and add `coolify` to `PRIVATE_OWNERS` if task 3 says private. —
  DoD: both `--selftest`s exit 0 locally and in `validate-manifests.yml` on the
  PR.

- [ ] 8. Fix the stale comment above the `projects` resource in
  `mcp-servers.tf` ("The three above are `auth_mode: manual`") so it names `tg`
  as the only manual server and states why it stays manual (mctl-telegram does
  not yet conform to mctlhq/.github#137, and its DCR default drops unnamed
  scopes). — DoD: no comment in the file contradicts the resources below it.

- [ ] 9. Update `infrastructure/cloudflare/portal/README.md` (depends on 1-8):
  the measured mode-switch answer, the registration rule from
  mctlhq/.github#137 and which servers are on which side of it today, the
  coolify onboarding sequence, and the note that a server left in `waiting`
  makes `cloudflare-portal-health.yml` red hourly until the admin login. — DoD:
  a reader who has never seen this issue can repeat every step from the README
  alone.

- [ ] 10. Merge, then dispatch `cloudflare-apply.yml` for
  `infrastructure/cloudflare/portal` (or the `mctl_trigger_portal_server_auth_apply`
  MCP tool), read the published plan, and approve on the `cloudflare-apply`
  environment (depends on 9). `allow_destroy` stays false. — DoD: apply
  succeeds; `tofu plan` afterwards is `no-op`; no resource was replaced.

- [ ] 11. Perform the live mode switch for `seerrsense` and `api` using the
  procedure measured in task 1 (skip for `seerrsense` if the interim manual
  path was taken) (depends on 10). If no in-place switch exists, recreate each
  server deliberately, one at a time. — DoD: each server's
  `auth_config_summary` reports automatic/DCR and `authentication_status` is
  `waiting` or `ready`.

- [ ] 12. Complete the upstream OAuth login once per server from the dashboard,
  from the owner address, for `coolify` and for any server recreated in task 11
  (depends on 11). For `seerrsense` and `api`, sign out first — a new
  registration is a new grant and a refresh is bound to the original one. —
  DoD: every server reports `ready` with a populated `tools` catalogue and
  `last_synced` set.

- [ ] 13. Add `coolify` to the portal's membership:
  `CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... scripts/portal-membership-add.sh coolify --dry-run`
  then without the flag (depends on 12). Re-run
  `scripts/portal-membership-add.sh <id>` for any server recreated in task 11,
  and re-apply that server's own `docs/portal-allowlist.json` with its
  repository's `scripts/portal-allowlist-apply.sh`. — DoD:
  `portal-membership-add.sh coolify --check` exits 0; every coolify tool is
  present with `enabled: false`; the script's own post-write diff of the other
  members' mappings reported no change.

- [ ] 14. Commit `docs/portal-allowlist.json` in `mctlhq/mctl-coolify-mcp` with
  a decision per tool — read-only tools (for example `get_version`) enabled,
  destructive ones (`stop_all_apps`, deletes, bulk env updates) disabled — and
  apply it from a checkout of that repository (depends on 13). — DoD: the
  allowlist is merged on that repo's `main` and the portal reflects it; nothing
  destructive is enabled.

- [ ] 15. Record the outcome on this issue and on mctlhq/seerrsense#73 (already
  closed as not planned when the approach moved here; record there, do not
  reopen),
  including the measured answer from task 1 and the acceptance results
  (depends on T1-T5). — DoD: both issues carry the result; seerrsense#73 is
  closed if the acceptance test passed.

## Tests

- [ ] T1. `scripts/portal-auth-credentials-drift.py --selftest` and
  `scripts/portal-catalogue-drift.py --selftest` both exit 0 on the PR
  (enforced by `validate-manifests.yml`), and `tofu validate` /
  `cloudflare-plan.yml` pass for the portal root.
- [ ] T2. The PR plan for the portal root contains no `destroy` and no
  `replace` action for `tg`, `projects`, `alice`, `seerrsense` or `api` — the
  hard stop condition of this change.
- [ ] T3. Acceptance, seerrsense: request *Ratatouille* (2007, TMDB 2062)
  through the portal. `seerrsense_request_media` files it instead of answering
  `this token is not granted the seerr:request scope`.
- [ ] T4. Acceptance, coolify: the server has left `waiting`, its catalogue is
  populated, and `get_version` answers through the portal once enabled.
- [ ] T5. Acceptance, api: a tool that needs the `mctl` scope answers through
  the portal after the sign-out/sign-in.
- [ ] T6. The first nightly `cloudflare-drift.yml` run after the apply reports
  the registration check in sync (exit 0) and the catalogue check at exit 0 or
  3 — a 3 means only that the `seerrsense` `KNOWN_STALE` waiver
  (`until` 2026-10-15, five named tools) is now wider than what fires, and is
  narrowed in the script rather than by re-snapshotting.
- [ ] T7. The next hourly `cloudflare-portal-health.yml` run after task 12 is
  green: every server `ready`, none in `waiting` or `error`.

## Rollback

Nothing here touches the cluster, so rollback is entirely on the Cloudflare
portal surface and in this repository.

1. *Before the apply* (tasks 4-9 only): revert the PR. The merge changed
   nothing live — `cloudflare-apply.yml` is dispatched by hand — so a revert is
   the whole rollback.
2. *After the apply, before the mode switch* (task 10): `seerrsense` and `api`
   are adopted but unchanged in mode; `coolify` exists in `waiting`. Revert the
   PR, re-dispatch `cloudflare-apply.yml` and approve a plan that destroys only
   `coolify` (`allow_destroy: true`, and read the plan: nothing else may be in
   it). The two imports leave state, the live servers stay as they were.
3. *After the mode switch* (task 11): restore the previous manual registration
   with the README's four-block re-snapshot recipe — `auth_type: bearer`, then
   back to `oauth`/`manual` resending the full `auth_credentials` blob and a
   non-empty `client_secret`. For `seerrsense` the blob to restore is the
   interim manual one (`scope = "seerr:read seerr:request offline_access"`);
   for `api`, the registration backed up in step 0 of that recipe, which is why
   that backup is taken before any flip. Note that the flip bumps
   `client_secret_version`, so `portal-auth-credentials-drift.py` reports drift
   until one no-change `cloudflare-apply.yml` run refreshes state.
4. *If membership or a tool allowlist was lost* (task 13): re-run
   `scripts/portal-membership-add.sh <id>` and then the owning repository's
   `scripts/portal-allowlist-apply.sh` from a checkout of that repository. The
   membership script refuses an empty catalogue and diffs every other member's
   mapping against what it sent, so a partial write fails loud rather than
   silently reverting another repository's decisions.
5. *If coolify must simply go away*: remove its resource and its `OWNERS` /
   `DCR_SERVERS` entries, apply with `allow_destroy: true`, and drop its
   `server_id` from the portal's `servers[]`.
