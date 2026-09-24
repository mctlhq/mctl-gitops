# Design: issue-1363-portal-seerrsense-api-and-coolify-mcp-un

## Current state

**The root.** `infrastructure/cloudflare/portal/` is an OpenTofu root of its
own (`versions.tf`, `backend.tf` with state key
`cloudflare/portal/terraform.tfstate` in the `mctl-cloudflare-state` R2
bucket, `mcp-servers.tf`, plus `mcp-portal-controls.json` for the separate
controls write). `versions.tf` pins `cloudflare/cloudflare ~> 5.0` (lock file:
5.24.0) and carries `variable "account_id"` with the account default. It is
deliberately not folded into `infrastructure/cloudflare/account/`, because
`cloudflare-apply.yml` enforces one write token per root: this root gets
`CF_APPLY_TOKEN_PORTAL` (Account -> MCP Portals) and nothing wider.

**What `mcp-servers.tf` declares today** — three resources:

- `tg` (lines 42-96): adopted with an `import` block
  (`id = "${var.account_id}/tg"`), `auth_type = "oauth"`, and an
  `auth_credentials` blob with `auth_mode = "manual"` whose
  `registration_info.scope` is `local.tg_scope`, the five telegram/account
  scopes. `client_secret` is deliberately absent — the file records the
  measured asymmetry that *creating* a manual server needs a non-empty
  `client_secret` (`7001`) while *updating* one does not.
- `projects` (lines 134-152): DCR. No `auth_credentials`, no `client_secret` —
  "supplying either is what opts a server INTO manual mode".
- `alice` (lines 181-199): DCR, same shape, for an upstream that is its own
  authorization server.

All three carry `lifecycle { ignore_changes = [updated_tools, updated_prompts] }`,
because those allowlists are owned by the upstream repositories' own
`docs/portal-allowlist.json` and applied from there.

`seerrsense` and `api` are live portal members with **no resource here at
all**. Two places in the repo already encode that fact:
`scripts/portal-membership-add.sh` skips its "must be a committed Terraform
resource" gate in `--check` mode specifically because "`api` and `seerrsense`
are both members of portal `mcp` today with no Terraform resource at all", and
`scripts/portal-auth-credentials-drift.py` names `DCR_SERVERS = {"projects"}`.
`coolify` is neither a resource nor a member.

**The stale comment.** Lines 98-107, introducing `projects`, say "The three
above are `auth_mode: manual`". With `tg` the only manual resource in the file,
that is now false — issue item 6.

**Why mode matters, measured and written down.** `README.md` records that
manual mode freezes the capability catalogue at the first user authorization
("Manual OAuth capabilities are captured during the first user authorization")
because sync runs with an admin credential only DCR registration holds; the
re-snapshot table (line 280) measured that `PUT auth_credentials` with a new
scope leaves `last_synced` unchanged, and that only an `auth_type: bearer` flip
puts the server back through `waiting` and clears `auth_config_summary`, with
the flip *back to manual* requiring a `client_secret`.

**What the detectors assume.**

- `scripts/portal-auth-credentials-drift.py` compares the `auth_credentials`
  blob recorded in state against the live `auth_config_summary` projection (the
  attribute is write-only, so state is the only desired value). In
  `desired_from_state`, a server id in `DCR_SERVERS` with no blob is skipped, a
  server in `DCR_SERVERS` that *grew* a blob raises `Undetermined`, and any
  other server with no blob raises `Undetermined` too — from inside the
  resource loop, so it aborts the whole scan (exit 2). `DCR_SERVERS` is
  `{"projects"}` and does not list `alice`.
- `scripts/portal-catalogue-drift.py` maps `OWNERS = {tg, api, seerrsense,
  projects}` to owning repositories, fetches each `docs/portal-allowlist.json`
  from `raw.githubusercontent.com` unless the server is in
  `PRIVATE_OWNERS = {"projects"}` (contents API + `ALLOWLIST_TOKEN`), and
  intersects `OWNERS` with the server ids found in OpenTofu state so that a
  merged-but-unapplied entry is a plan, not an outage. A portal member absent
  from `OWNERS` is reported undetermined. `KNOWN_STALE` holds one waiver:
  `("seerrsense", "closed-output-schemas")`, `until` 2026-10-15, naming
  `get_media`, `request_media`, `resolve_media`, `search_media`, `whoami`.
- Both `--selftest`s run on every pull request from `validate-manifests.yml`
  (steps at lines 354 and 363), and both run nightly from `cloudflare-drift.yml`
  for this root only, after a clean plan.
- `.github/workflows/cloudflare-portal-health.yml` reads **every** server
  hourly with `CF_PORTAL_READ_TOKEN` and fails when any is not `ready` or
  carries an `error`, notifying Telegram once per distinct problem per UTC day.

**How a change reaches Cloudflare.** A merge changes nothing. `cloudflare-plan.yml`
publishes the plan on the PR; `cloudflare-apply.yml` is dispatched by hand for
one root, plans unprivileged, then waits on the `cloudflare-apply` environment
reviewer before writing, with `allow_destroy` defaulting to false. The MCP tool
`mctl_trigger_portal_server_auth_apply` dispatches exactly that workflow for
this root.

## Proposed solution

Five changes, in a deliberate order, with the riskiest question answered on a
throwaway server before any live upstream is touched.

### 1. Measure the mode switch first (no live server involved)

The issue asks "check whether the provider can switch mode in place". The
README already established that omitting `auth_credentials` is what *creates* a
DCR server, but never measured *clearing* an existing manual registration. The
answer cannot be obtained from the plan, because `auth_credentials` is
write-only: state keeps the last applied value and the API cannot contradict
it, so dropping the attribute from a config whose state already holds one is
not guaranteed to produce any write at all.

So: create a throwaway manual-OAuth server (a create needs a non-empty
`client_secret`; any value works with `token_endpoint_auth_method: none`), then
try, in order, (a) a `PUT` that sends the server with no `auth_credentials`,
and (b) the measured `auth_type: bearer` -> `auth_type: oauth` flip with **no**
`auth_credentials` on the way back. Read back `auth_config_summary` and
`authentication_status` after each, then destroy the throwaway. Whichever works
becomes the documented procedure; if neither does, the fallback is a deliberate
recreate with the re-add steps below. This mirrors how every other claim in
this README was established ("measured on 2026-09-12 against a throwaway server
created and destroyed for the purpose").

### 2. `seerrsense` and `api`: adopt, never create

Both get an `import` block plus a resource, exactly like `tg`:

```hcl
import {
  to = cloudflare_zero_trust_access_ai_controls_mcp_server.seerrsense
  id = "${var.account_id}/seerrsense"
}
```

The resources are written in the **automatic** shape — `auth_type = "oauth"`,
no `auth_credentials`, no `client_secret`, plus the same
`ignore_changes = [updated_tools, updated_prompts]` — so the committed file
states the target mode declaratively, matching `projects` and `alice`. The
out-of-band mode clearing from step 1 is what actually moves the live server
into that mode; the import then adopts it and the plan must come back
**no-op** (or a rename/description-only update). An import that plans a
*replace* is the stop condition: `allow_destroy` stays false and the change is
re-examined, satisfying the issue's rule 5.

Ordering gates, taken from the issue and from mctlhq/.github#137:

- `seerrsense` waits for mctlhq/seerrsense#74 (portal-restricted DCR, full
  default for DCR clients). The gate is verified live, not assumed: a probe DCR
  registration with `redirect_uris = ["https://mcp.mctl.ai/servers-callback"]`
  must succeed, and the same probe from any other callback must be refused.
  Interim, only if the fix is needed sooner: import `seerrsense` as **manual**
  with `scope = "seerr:read seerr:request offline_access"` in a `local`
  alongside `local.tg_scope`. That path is an update, not a create, so it needs
  no `client_secret` in state — the same asymmetry `tg` relies on.
- `api` needs the same portal-callback restriction confirmed on
  `https://api.mctl.ai/oauth/register` (it advertises DCR, scope `mctl`, auth
  `none`) before the switch.

### 3. `coolify`: a new DCR resource, created from scratch

`coolify.mctl.ai` offers CIMD with a DCR fallback and grants `coolify` when no
scope is named, so it is created in the automatic shape with no
`auth_credentials` and no `client_secret` — which also sidesteps the
`client_secret` requirement, since that applies only to manual-mode creates.
The apply leaves it in `waiting`; an admin then completes the upstream login
once from the dashboard, and that account becomes the admin credential for
every later sync (and decides what the snapshot contains). Only then does
`scripts/portal-membership-add.sh coolify` succeed — it refuses an empty
catalogue by design — writing every advertised tool `enabled: false`. Enabling
anything is a separate decision, recorded in a new
`docs/portal-allowlist.json` in `mctlhq/mctl-coolify-mcp` and applied from
there; that split is exactly why coolify's destructive tools (`stop_all_apps`,
deletes, bulk env updates) are safe to register before they are reviewed.

### 4. Teach the two detectors about the new shape

Both changes are load-bearing, not cosmetic — the same lesson the README
records from when `projects` landed:

- `scripts/portal-auth-credentials-drift.py`: `DCR_SERVERS` becomes
  `{"projects", "alice", "seerrsense", "api", "coolify"}` (minus `seerrsense`
  if the interim manual path is taken — in that case its pinned blob is what
  the detector compares, like `tg`'s). Without this, each new blob-less
  resource raises `Undetermined` from inside the loop and the nightly check
  reports "could not run" for `tg` as well. `alice` is included because it is
  already in the file and already in that failure mode.
- `scripts/portal-catalogue-drift.py`: `OWNERS` gains
  `"coolify": "mctlhq/mctl-coolify-mcp"` and `"alice": "mctlhq/mctl-alice"`;
  `PRIVATE_OWNERS` gains `coolify` if that repository is private. `OWNERS` is
  intersected with state ids by `expected_missing`, so an entry added in the
  same PR as the resource is correctly treated as a plan until the apply
  happens. An `OWNERS` entry with no committed allowlist yet reports
  undetermined, which is why the allowlist file in `mctl-coolify-mcp` is part
  of this work rather than a follow-up.

Both scripts' `--selftest` must stay green; `validate-manifests.yml` runs them
on the pull request.

### 5. Documentation

Fix the stale "The three above are `auth_mode: manual`" comment above
`projects` (now: `tg` is the only manual one, and why). Add to `README.md`: the
measured answer from step 1, the sequencing gates for `seerrsense`/`api`, the
coolify onboarding steps, and a note that a server sitting in `waiting` makes
`cloudflare-portal-health.yml` red hourly until the admin login is done.

## Alternatives

**A. Fix it server-side in seerrsense** (make the no-scope default grant
`seerr:request`). Proposed as seerrsense#72 and dropped: it widens every
no-scope client's grant, not just the portal's, which loses least privilege by
default, and it does nothing about `api`, `coolify`, or the two undeclared
resources. The portal-side fix is also how `tg` was fixed, so it keeps one
story.

**B. Import `seerrsense` and `api` as manual with pinned scope strings** (the
`tg` model, for both). Lowest risk: an update, no `client_secret`, no
recreate, and it fixes `request_media` immediately. Dropped as the default
because it contradicts mctlhq/.github#137, freezes both catalogues at their
first login forever (the README's whole re-snapshot recipe exists to work
around exactly that), and re-creates the hand-pinned-scope class of bug this
issue is closing. Kept as the explicitly-labelled interim path for
`seerrsense` only, if the fix is needed before #74 ships.

**C. Destroy and recreate the live servers in Terraform.** Guarantees the
target mode and needs no measurement. Dropped as the default: it loses the
portal membership entry and the tool allowlist decisions behind it, forces a
fresh login and a fresh snapshot, and `cloudflare-apply.yml` refuses a
destructive plan unless `allow_destroy` is set — a gate worth keeping armed.
It remains the documented fallback if step 1 shows no in-place switch exists,
and then it is done deliberately, with `portal-membership-add.sh` and the
owning repository's `portal-allowlist-apply.sh` re-run afterwards.

**D. Keep doing it from the dashboard.** This is the status quo that produced
the bug: `seerrsense`'s scope "had been set by hand when the server was created
on 2026-09-10, and was recorded nowhere", and `projects`'s membership was "a
dashboard click with nothing committed at all". Dropped by the existence of
this root.

## Platform impact

**Migrations / backward compatibility.** No Kubernetes, ArgoCD, Helm or
tenant-facing change; nothing under `platform-gitops/` moves. The blast radius
is the Cloudflare account's MCP Portals surface plus two Python detectors. No
state migration: `seerrsense` and `api` are adopted by `import`, which the `tg`
precedent measured as "one update and nothing else, `client_secret` does not
appear in the diff, and there is no replacement".

**Resource impact.** None in-cluster. One extra upstream on the portal and one
extra server in the hourly health sweep and the nightly detectors.

**Risks and mitigations.**

- *A live upstream is replaced instead of adopted.* Mitigation: `import` blocks
  for both live servers; the PR plan from `cloudflare-plan.yml` is read before
  apply; `allow_destroy` stays false, so a destructive plan cannot be applied
  by accident.
- *The mode switch is not possible in place and `seerrsense`/`api` end up
  half-migrated.* Mitigation: step 1 answers this on a throwaway server first;
  the recreate fallback has explicit re-add steps; the interim manual import
  restores `request_media` without any mode change at all.
- *The registration loses tool allowlist decisions.* Mitigation:
  `ignore_changes = [updated_tools, updated_prompts]` on every resource, and
  `portal-membership-add.sh` diffs every other member's mapping
  decision-for-decision against what it sent before declaring success.
- *A server in `waiting` makes `cloudflare-portal-health.yml` red hourly and
  notifies Telegram daily.* Mitigation: schedule the admin login in the same
  session as the apply; the health job's Telegram cache key already collapses
  repeats to one per UTC day.
- *The nightly registration check aborts for every server.* Mitigation: the
  `DCR_SERVERS` update ships in the same PR as the resources, and its
  `--selftest` runs on the PR.
- *A wider grant does not reach an existing session.* Mitigation: the documented
  sign-out/sign-in after apply, and an acceptance test that actually files
  *Ratatouille* (TMDB 2062).
- *Coolify's destructive tools become reachable.* Mitigation:
  `portal-membership-add.sh` writes every tool `enabled: false`, and only
  `mctl-coolify-mcp`'s own committed `docs/portal-allowlist.json` can enable
  one.
- *The seerrsense closed-output-schema waiver goes stale.* `KNOWN_STALE`
  expires 2026-10-15 and names five tools; a post-switch re-snapshot that
  changes the tool set can make it wider than what fires (exit 3, "delete or
  narrow it in the script"). Watch the first nightly run after the switch.
