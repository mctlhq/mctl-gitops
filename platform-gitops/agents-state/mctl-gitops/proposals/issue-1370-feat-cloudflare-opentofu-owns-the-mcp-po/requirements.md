# OpenTofu owns the MCP portal; tool allowlists vendored from the service repos

## Context

Six mechanisms write to one remote object today — the Cloudflare MCP portal
`mcp` at `mcp.mctl.ai`. `scripts/portal-controls-apply.sh` writes the three
account-level switches from `infrastructure/cloudflare/portal/mcp-portal-controls.json`;
`scripts/portal-membership-add.sh` appends a `servers[]` entry with every tool
disabled; four near-copies of `portal-allowlist-apply.sh` in `mctl-telegram`,
`mctl-api`, `projects-mcp` and `mctl-alice` each write one server's
`updated_tools`; `seerrsense` and `mctl-coolify-mcp` have a
`docs/portal-allowlist.json` with no apply path at all and are clicked in by
hand; and the dashboard can write anything. The endpoint is a single `PUT`
with merge semantics, which is why both scripts in this repo go to such
lengths to avoid a read-modify-write over `servers` (see the race described
at length in `infrastructure/cloudflare/portal/README.md` and in the header
comment of `scripts/portal-controls-apply.sh`).

The cost is concrete: allowlist drift is invisible unless every copy of the
script grows its own `--check`; the read-modify-write race exists *because*
there are several writers; and a new upstream added through the dashboard
comes up with **all** tools enabled — `coolify` landed on 2026-09-24 at 45/45
including the destructive ones, and its reviewed 22/45 allowlist
(`mctlhq/mctl-coolify-mcp#5`) then had to be clicked in by hand. This
proposal makes OpenTofu the single writer of the portal object in the
existing `infrastructure/cloudflare/portal` root, while leaving the *decision*
("this tool is safe to expose") in the service repo that ships the tool: each
repo's `docs/portal-allowlist.json` is vendored into mctl-gitops as a pinned
copy, bumped by a PR the same way `platform-gitops/services/**/values.yaml`
image tags are bumped today.

## User stories

- AS a platform operator I WANT the portal's server mapping and switches
  described in `infrastructure/cloudflare/portal` SO THAT `cloudflare-plan.yml`
  shows me exactly which tools a change flips before `cloudflare-apply.yml`
  applies it under environment approval.
- AS a service owner I WANT `docs/portal-allowlist.json` to stay in my repo
  SO THAT the decision to expose a tool lands in the same diff as the tool.
- AS a service owner I WANT my repo's CI to open the mctl-gitops bump PR for
  me SO THAT I never run an apply script against production Cloudflare from a
  laptop checkout.
- AS a reviewer I WANT a vendored allowlist that enables more tools than the
  recorded baseline to fail CI SO THAT widening what the portal exposes is
  always an explicit, reviewed line in the diff.
- AS an on-call operator I WANT a hand-made dashboard toggle to appear in the
  next `cloudflare-drift.yml` run SO THAT out-of-band changes to the portal
  are noticed the same way they are for every other Cloudflare root.
- AS the person doing the migration I WANT the whole change gated on a
  measured, stable zero diff SO THAT a provider that cannot round-trip
  `updated_tools` costs a PR, not a broken nightly job.

## Acceptance criteria (EARS)

### Measurement gate (task 0 of the issue)

- WHEN the import PR for `cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp`
  is opened THE SYSTEM SHALL produce a `cloudflare-plan` job summary for
  `infrastructure/cloudflare/portal` showing `1 to import, 0 to add, 0 to
  change, 0 to destroy`, and that summary SHALL be pasted into the PR body.
- WHEN the import has been applied through `cloudflare-apply.yml` THE SYSTEM
  SHALL report `No changes` on the next plan of that root, and again on the
  following nightly `cloudflare-drift.yml` run for that root.
- WHILE the measurement is being taken THE SYSTEM SHALL record, in the PR
  body, the observed behaviour of each of: ordering of `updated_tools`
  entries; computed per-tool fields returned by GET but absent from config
  (`alias`, `description`); tools present in the synced catalogue but absent
  from `updated_tools`; and the round-trip of `default_disabled` and
  `on_behalf`.
- IF a stable zero diff cannot be reached — a perpetual diff on
  `updated_tools` that no config change removes — THEN THE SYSTEM SHALL NOT
  be applied, the import block and the `servers` declaration SHALL be
  withdrawn, the measured reason SHALL be recorded on issue #1370, and the
  fallback below SHALL be landed instead.

### The vendored allowlists

- WHEN the portal root is planned THE SYSTEM SHALL build each
  `servers[].updated_tools` from `jsondecode(file(...))` of
  `infrastructure/cloudflare/portal/allowlists/<server>.json`, a byte-identical
  pinned copy of that service repo's `docs/portal-allowlist.json` on `main`.
- WHILE a server has no vendored allowlist file THE SYSTEM SHALL declare that
  server's `updated_tools` literally, matching its live mapping at import time.
- WHEN `validate-manifests.yml` runs THE SYSTEM SHALL fail if any vendored
  file has a top-level key outside `{"$comment", "portal", "server",
  "default_disabled", "tools"}`, if `portal` is not `"mcp"`, if `server` does
  not equal the file's stem, if `default_disabled` is not `true`, if `tools` is
  empty or not a list, if any tool entry has a key outside `{"name", "enabled",
  "reason", "upstream_gates", "override"}`, if an `override` is present on an
  enabled entry or is not `"sensitive-read"`, or if any tool entry lacks a non-empty string `name`, a boolean
  `enabled` or a non-empty string `reason`, or if a tool name is duplicated.
  These are the keys all six service files carry today (measured 2026-09-25);
  a byte-identical copy must pass its own validator.
- WHEN `validate-manifests.yml` runs THE SYSTEM SHALL fail if a vendored file
  or a `mapping.json` entry names a server with no
  `resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "<id>"` in
  `infrastructure/cloudflare/portal/mcp-servers.tf`.
- WHEN `validate-manifests.yml` runs THE SYSTEM SHALL fail if the set of
  `allowlists/*.json` files and the key set of `allowlists/mapping.json`
  `servers` differ, or if `allowlists/sources.json` lacks a provenance entry
  for any vendored file.
- IF a vendored file enables more tools for a server than
  `allowlists/baseline.json` records for that server THEN THE SYSTEM SHALL
  fail the validator unless the same diff updates that server's
  `baseline.json` entry.
- WHEN a vendored allowlist file changes by one tool THE SYSTEM SHALL show
  exactly that one `enabled` flip in the PR's `cloudflare-plan` summary and
  nothing else.

### The bump path

- WHEN `docs/portal-allowlist.json` changes on `main` in an owning service
  repo THE SYSTEM SHALL dispatch the mctl-gitops vendoring workflow, using the
  same `GITOPS_TOKEN` credential the image-tag bumps already use, with no new
  secret introduced anywhere.
- WHEN the vendoring workflow runs THE SYSTEM SHALL open a pull request
  against `main` of mctl-gitops that updates exactly
  `allowlists/<server>.json` and that server's `allowlists/sources.json`
  entry, and SHALL NOT commit directly to `main`.
- WHILE the vendoring workflow is building a commit THE SYSTEM SHALL run the
  allowlist validator against the dispatched content and fail the dispatch
  rather than open a PR whose CI is known to be red.
- IF the dispatched bump would enable more tools than `baseline.json` records
  THEN THE SYSTEM SHALL still open the PR, and that PR SHALL fail CI until a
  human updates `baseline.json` in it.
- WHEN the nightly portal drift job runs THE SYSTEM SHALL compare each
  vendored file against its recorded source commit and against that repo's
  `main`, and report a lag as a distinct finding from a stale catalogue.

### Single writer, and the retirement

- WHILE the portal resource is in state THE SYSTEM SHALL keep
  `ignore_changes = [updated_tools, updated_prompts]` on every
  `cloudflare_zero_trust_access_ai_controls_mcp_server` resource in
  `mcp-servers.tf`, so that the portal resource is the only writer of the
  mapping inside the root as well as outside it.
- WHEN the portal resource owns `secure_web_gateway`, `code_mode` and
  `allow_code_mode` THE SYSTEM SHALL delete
  `infrastructure/cloudflare/portal/mcp-portal-controls.json`,
  `scripts/portal-controls-apply.sh`, `tests/test_portal_controls_apply.py`
  and that test's step in `validate-manifests.yml`, in the same PR.
- WHEN the portal resource declares the full `servers` set THE SYSTEM SHALL
  delete `scripts/portal-membership-add.sh`,
  `tests/test_portal_membership_add.py` and that test's step in
  `validate-manifests.yml`, in the same PR.
- WHEN the vendoring path is live for a service THE SYSTEM SHALL delete that
  repo's `scripts/portal-allowlist-apply.sh`, and no
  `portal-allowlist-apply.sh` SHALL remain in any mctlhq repository.
- WHEN a script is retired THE SYSTEM SHALL update, in the same PR, every
  reference to it in `infrastructure/cloudflare/portal/README.md`,
  `docs/runbooks/cloudflare-operations.md`,
  `infrastructure/cloudflare/account/portal-mcp-apps.tf`, and the `OWNERS` /
  `DCR_SERVERS` notes in `scripts/portal-catalogue-drift.py` and
  `scripts/portal-auth-credentials-drift.py`.
- WHILE this change is in flight THE SYSTEM SHALL NOT widen what the portal
  exposes: the live mapping at import time is the baseline — alice 12/12,
  projects 8/8, tg 30/30, api 75/75 with prompts 4/4, coolify 22/45 with
  prompts 0/3, seerrsense 5/5.
- WHEN the portal root is applied THE SYSTEM SHALL go through
  `cloudflare-apply.yml` with the `cloudflare-apply` environment approval and
  the `CF_APPLY_TOKEN_PORTAL` write token, exactly as today.

### Fallback (only if the measurement gate fails)

- IF the measurement gate fails THEN THE SYSTEM SHALL leave `servers`
  undeclared on the portal resource, per `#1092`, and SHALL replace the four
  `portal-allowlist-apply.sh` copies with one server-agnostic
  `scripts/portal-allowlist-apply.sh` in mctl-gitops that takes the server id
  from the file's own `server` field.
- IF the fallback is landed THEN THE SYSTEM SHALL add a
  `.github/workflows/portal-allowlist-apply.yml` that plans, then waits for
  approval in the `cloudflare-apply` environment, then applies, sharing a
  concurrency group with every other portal writer, and SHALL add a nightly
  `--check` over all six servers to `cloudflare-drift.yml`.

## Out of scope

- Moving `seerrsense` and `api` from manual OAuth registration to DCR, and
  adopting them as `cloudflare_zero_trust_access_ai_controls_mcp_server`
  resources. That is `#1363` and needs live measurements and credentials this
  change does not have; this proposal declares their *portal mapping* without
  touching their *server registration*.
- The re-snapshot recipe itself (`infrastructure/cloudflare/portal/README.md`).
  Its step 5 is rewritten to point at the new path, but the bearer-flip
  procedure is unchanged.
- Committing each upstream's tool schemas so that a schema change under an
  unchanged name is detectable. Still the known gap noted in
  `scripts/portal-catalogue-drift.py`'s "Read its green carefully" section.
- Moving the portal root into `infrastructure/cloudflare/account`. The
  one-write-token-per-root rule in `cloudflare-apply.yml` keeps them separate.
- Changing which tools are enabled for any server. Every vendored file is a
  byte-for-byte copy of what the owning repo already committed.

## Open questions

- The exact provider v5.24 attribute names on
  `cloudflare_zero_trust_access_ai_controls_mcp_portal` for the three switches
  (`secure_web_gateway`, `code_mode`, `allow_code_mode`), for the hostname,
  and the accepted import id form (`<account_id>/mcp` by analogy with
  `mcp-servers.tf`'s `import { id = "${var.account_id}/tg" }`). Resolved by
  `tofu plan` on the import PR; the API field names in
  `mcp-portal-controls.json` are the starting assumption.
- Whether `updated_tools` is a List or a Set in the provider schema, and
  whether `alias` and `description` are Optional+Computed. This is the whole
  content of the measurement gate; assume the worst (perpetual diff) until the
  plan says otherwise.
- Whether the API materialises catalogue tools that are absent from
  `updated_tools` as implicit disabled entries on read. If it does, every
  vendored file must enumerate all of a server's tools. All six do
  (measured 2026-09-25): coolify's file lists all 45 tools, 22 enabled and 23
  disabled, gated in its own CI by `npm run check:portal-allowlist`.
- Whether each of the six owning repos already holds the `GITOPS_TOKEN`
  secret used by the image bumps, or whether some only have it in the repos
  that deploy. Assumed present where a release workflow exists; the dispatch
  workflow is added per repo as that is confirmed.
- Whether the `mctl-agents` App installation may open pull requests in
  mctl-gitops (it currently mints `permission-contents: write` for direct
  pushes in `gitops-bump.yaml`); `permission-pull-requests: write` is assumed
  grantable on the same installation.
- Whether `mctl-alice` and `mctl-coolify-mcp` are public. `PRIVATE_OWNERS` in
  `scripts/portal-catalogue-drift.py` names only `projects`, so the nightly
  vendor-lag check needs the App token's `repositories:` list widened only for
  `projects-mcp`; assumed unchanged for the rest.
