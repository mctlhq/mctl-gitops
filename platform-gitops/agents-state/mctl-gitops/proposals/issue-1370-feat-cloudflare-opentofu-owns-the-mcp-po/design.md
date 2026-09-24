# Design: issue-1370-feat-cloudflare-opentofu-owns-the-mcp-po

## Current state

### The root that exists

`infrastructure/cloudflare/portal` is already an OpenTofu root. It holds:

- `versions.tf` — `cloudflare/cloudflare ~> 5.0`, `required_version >= 1.9.0`,
  `provider "cloudflare" {}` (token from the environment), and
  `variable "account_id"` defaulting to `6a09f637d20e1f66a8e9d45ebe778058`.
  `.terraform.lock.hcl` pins provider **5.24.0**, which is the version the
  issue's schema description refers to.
- `backend.tf` — R2 bucket `mctl-cloudflare-state`, key
  `cloudflare/portal/terraform.tfstate`, `use_lockfile = true`. Enforced by
  `.github/scripts/cloudflare-assert-backend.sh`, which derives the expected
  key from the root path.
- `mcp-servers.tf` — four `cloudflare_zero_trust_access_ai_controls_mcp_server`
  resources: `tg` (manual OAuth, adopted via an `import` block with
  `id = "${var.account_id}/tg"`), and `projects`, `alice`, `coolify` (DCR).
  **Every one of them carries `lifecycle { ignore_changes = [updated_tools,
  updated_prompts] }`**, with a comment saying those are owned by the service
  repos and applied from there. `api` and `seerrsense` are live on the portal
  but have no resource here at all (`#1363`).
- `mcp-portal-controls.json` — `{portal, hostname, secure_web_gateway,
  code_mode, allow_code_mode}`. Explicitly *not* OpenTofu; the README says
  "When the import lands, this file becomes a resource and the script goes
  away."

### The CI that drives it

- `cloudflare-plan.yml` discovers roots by walking for `versions.tf` under
  `infrastructure/cloudflare` (excluding `modules/`), runs them as a matrix,
  and for `infrastructure/cloudflare/portal` hands the job
  `secrets.CF_PORTAL_READ_TOKEN` via an explicit `&&`/`||` chain (secrets
  cannot be indexed by a variable). It runs `tofu fmt -check -diff`,
  `tofu validate`, asserts the resolved backend type, and writes the plan to
  `$GITHUB_STEP_SUMMARY` — including an `| import | create | update |
  **destroy** |` counts table — never to a PR comment.
- `cloudflare-apply.yml` is `workflow_dispatch` with a `root` input validated
  by `.github/scripts/cloudflare-assert-applyable-root.sh`; its `apply` job
  has `environment: cloudflare-apply`, concurrency group
  `cloudflare-apply-${{ inputs.root }}`, and for the portal uses
  `secrets.CF_APPLY_TOKEN_PORTAL`. The approved plan is re-asserted against a
  digest so the applied plan is the reviewed one.
- `cloudflare-drift.yml` runs nightly (`0 6 * * *`) on the same matrix, with
  concurrency group `cloudflare-tofu-${{ matrix.root }}`. For the portal root
  only, it then runs `scripts/portal-auth-credentials-drift.py` and — after
  minting an `actions/create-github-app-token` with `repositories:
  projects-mcp`, `permission-contents: read`, exported as `ALLOWLIST_TOKEN` —
  `scripts/portal-catalogue-drift.py`. Failures go to Telegram.

### The writers being retired

- `scripts/portal-controls-apply.sh` — vets `mcp-portal-controls.json` against
  `HEAD` (refuses an uncommitted file), checks its shape and that it names
  `mcp`/`mcp.mctl.ai`, then `PUT`s **only** the three switches, precisely so
  the write cannot become a read-modify-write over `servers`. Unit-tested by
  `tests/test_portal_controls_apply.py`, step 27 of `validate-manifests.yml`.
- `scripts/portal-membership-add.sh` — appends one `servers[]` entry shaped
  `{server_id, on_behalf, default_disabled, updated_tools: [{name, enabled:
  false}], updated_prompts: [{name, enabled: false}]}`, copying `on_behalf`
  and `default_disabled` from an existing member after asserting all members
  agree. It gates on the server id already existing as a literal
  `resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "<id>"` in
  `mcp-servers.tf` (a `git show HEAD:` + `grep -qF`). It narrows the
  read-modify-write window with three reads and two post-write diffs, and says
  so: the window is narrowed, not closed. Unit-tested by
  `tests/test_portal_membership_add.py`, step 28.
- Four `scripts/portal-allowlist-apply.sh` copies outside this repo, plus two
  repos with an allowlist and no apply path.

### What the allowlists look like

`scripts/portal-catalogue-drift.py` is the existing consumer and fixes the
shape: `{"server": "<portal server id>", "tools": [{"name": ..., "enabled":
...}]}`. Its `OWNERS` maps `tg → mctlhq/mctl-telegram`, `api →
mctlhq/mctl-api`, `seerrsense → mctlhq/seerrsense`, `projects →
mctlhq/projects-mcp`, `alice → mctlhq/mctl-alice`, `coolify →
mctlhq/mctl-coolify-mcp`, always at `docs/portal-allowlist.json` on `main`;
`PRIVATE_OWNERS = {"projects"}` routes that one through the contents API with
`ALLOWLIST_TOKEN`. The script reads only `name` — it compares the portal's
stored tool names against the upstream's — and deliberately ignores `enabled`.
`scripts/portal-auth-credentials-drift.py` holds `DCR_SERVERS = {"projects",
"alice", "coolify"}` and reads `tofu show -json` from stdin.

### The bump pattern to copy

`.github/workflows/gitops-bump.yaml` is `workflow_dispatch`-only, called by app
repos with a `GITOPS_TOKEN` that needs nothing more than `actions: write` on
mctl-gitops. All gitops knowledge stays here; the caller passes data. The
commit is made with a token minted in-workflow from `secrets.AGENTS_APP_ID` /
`secrets.AGENTS_APP_PRIVATE_KEY` (`actions/create-github-app-token`,
`permission-contents: write`), because the `mctl-agents` App is on the
`main-protection` ruleset's bypass list. `CLAUDE.md` scopes that bypass
narrowly: it covers `image.tag` bumps only.

## Proposed solution

### Shape of the change

```
infrastructure/cloudflare/portal/
  mcp-portal.tf              NEW  import + the portal resource
  mcp-servers.tf             comments updated; ignore_changes kept
  mcp-portal-controls.json   DELETED (its fields become resource attributes)
  allowlists/
    tg.json api.json seerrsense.json projects.json alice.json coolify.json
    mapping.json             per-server attributes that are NOT the repo's call
    sources.json             provenance: repo, path, ref, sha, vendored_at
    baseline.json            live enabled/total at import time
scripts/validate-portal-allowlists.py   NEW  (--selftest, --vendor-check)
.github/workflows/portal-allowlist-vendor.yml   NEW  dispatch -> bump PR
```

### `mcp-portal.tf`

An `import` block adopting the live object — the same adoption pattern
`mcp-servers.tf` already uses for `tg` — plus one resource:

```hcl
locals {
  # Everything about a mapping that is NOT the service repo's decision:
  # default_disabled, on_behalf, and the prompt allowlist. Kept in JSON, not
  # HCL, so scripts/validate-portal-allowlists.py needs no HCL parser.
  portal_mapping = jsondecode(file("${path.module}/allowlists/mapping.json"))
}

import {
  to = cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp
  id = "${var.account_id}/mcp"
}

resource "cloudflare_zero_trust_access_ai_controls_mcp_portal" "mcp" {
  account_id         = var.account_id
  id                 = "mcp"
  hostname           = "mcp.mctl.ai"
  secure_web_gateway = false
  code_mode          = "off"
  allow_code_mode    = false

  servers = [
    for id, s in local.portal_mapping.servers : {
      server_id        = id
      default_disabled = s.default_disabled
      on_behalf        = s.on_behalf
      updated_prompts  = s.updated_prompts
      updated_tools = s.vendored ? [
        for t in jsondecode(file("${path.module}/allowlists/${id}.json")).tools :
        { name = t.name, enabled = t.enabled }
      ] : s.updated_tools
    }
  ]

  depends_on = [
    cloudflare_zero_trust_access_ai_controls_mcp_server.tg,
    cloudflare_zero_trust_access_ai_controls_mcp_server.projects,
    cloudflare_zero_trust_access_ai_controls_mcp_server.alice,
    cloudflare_zero_trust_access_ai_controls_mcp_server.coolify,
  ]
}
```

Three things this shape buys. First, `mapping.json` is read by both OpenTofu
and the Python validator, so the validator never parses HCL — the one fragile
coupling the alternative designs all had. Second, `vendored: false` is the
issue's "servers with no file keep their live mapping, declared literally"
escape hatch, and it is per-server rather than per-file. Third, `depends_on`
makes the ordering explicit for the four servers this root creates; `api` and
`seerrsense` are mapped without being managed, which is the `#1363` split and
must not be closed here.

`mcp-portal-controls.json`'s five fields land as: `portal`/`hostname` become
the resource's identity and `hostname` attribute; the three switches become
attributes. The file's job — recording the baseline so "untouched" is
checkable — is done better by state plus the nightly plan.

`ignore_changes = [updated_tools, updated_prompts]` **stays** on every server
resource. Without it the root would contain two writers of the same mapping,
and the comment above each block is rewritten from "owned by the service
repos, applied from there" to "owned by the portal resource in this root,
built from the vendored copy in `allowlists/`".

### The measurement gate, and how it is actually taken

The issue is right that everything hangs on whether this round-trips. The
useful observation is that **the measurement is a CI artifact, not a laptop
exercise**: `cloudflare-plan.yml` already runs `tofu plan` for this root on
every PR with `CF_PORTAL_READ_TOKEN` and publishes the counts table and the
full plan to the job summary. So the import PR *is* the measurement:

1. PR opens. `cloudflare-plan` summary must read `1 to import, 0 to add, 0 to
   change, 0 to destroy`. Any `update` line names the attribute that does not
   round-trip, and the four specific questions in the issue's task 0 —
   `updated_tools` ordering, computed `alias`/`description`, catalogue tools
   absent from `updated_tools`, `default_disabled`/`on_behalf` — are each
   answered by reading it. The summary is pasted into the PR body.
2. Merge, then dispatch `cloudflare-apply.yml` with
   `root=infrastructure/cloudflare/portal`. The `cloudflare-apply` environment
   approval is the human gate, and the digest assert guarantees the applied
   plan is the reviewed one.
3. The **second** plan is the post-apply one: the next nightly
   `cloudflare-drift.yml` run for this root must be `No changes`. That is the
   acceptance criterion "twice in a row", and it is recorded on the issue.

Between step 1 and step 2 the declaration is merged but not applied, which is
safe: an unapplied `import` block changes nothing in Cloudflare, and the only
path that writes is a dispatched, approved apply.

If step 1 or step 3 shows an unremovable diff, nothing has been applied yet at
step 1 and the withdrawal is a revert; at step 3 the fallback is landed and the
portal resource keeps `servers` undeclared, exactly as `#1092` decided.

### The validator

`scripts/validate-portal-allowlists.py`, following the repo's established
convention exactly (executable `scripts/validate-*.py`, `--selftest` run first
then the bare invocation, added to `validate-manifests.yml` beside steps 27-30,
stdlib only, hand-rolled `check()`/`FAILURES` reporting). It enforces:

- shape: each `allowlists/<id>.json` is the service repo's file byte-identical,
  so its top-level keys are exactly the allowed set `{"$comment", "portal",
  "server", "default_disabled", "tools"}` (any other key fails);
  `portal == "mcp"`; `server == <id>`; `default_disabled == true`; `tools` a
  non-empty list; each entry's keys drawn from `{"name", "enabled",
  "reason", "upstream_gates", "override"}` with `name` a non-empty string,
  `enabled` a boolean, `reason` a non-empty string, and `override`, when
  present, equal to `"sensitive-read"` on an entry with `enabled: false`; no duplicate names. OpenTofu reads
  only `name` and `enabled`; the other keys are audit trail, carried so the
  vendored copy stays byte-identical and the bump diff is the service diff.
- coverage: `{files} == {mapping.json servers where vendored}` and every
  vendored file has a `sources.json` entry; `mapping.json` non-vendored entries
  carry a literal `updated_tools`.
- existence: every server id in `mapping.json` appears as
  `resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "<id>"` in
  `mcp-servers.tf`, or is on a short, commented `UNMANAGED = {"api",
  "seerrsense"}` list mirroring `#1363` — reusing the literal-grep technique
  from `portal-membership-add.sh`'s `tf_declared()` rather than inventing a
  parser.
- non-widening: per server, `enabled` count and total must equal
  `baseline.json`, or the failure names the delta. A legitimate widening bump
  fails until a human edits `baseline.json` in the same PR. The workflow below
  deliberately does **not** update `baseline.json` for you.
- `--vendor-check` (network, drift only): compares each vendored file against
  the `sha` recorded in `sources.json` and against that repo's `main`, using
  `ALLOWLIST_TOKEN` for private owners, and reports lag as its own finding.

`--selftest` replays fixtures under `scripts/tests/fixtures/portal-allowlists/{valid,invalid}`,
the layout `scripts/validate-agent-platform.py` already uses.

### The bump path

Two halves, mirroring `gitops-bump.yaml`'s division of knowledge.

In **mctl-gitops**, `.github/workflows/portal-allowlist-vendor.yml`:
`workflow_dispatch` with inputs `server`, `allowlist` (the file content),
`source_repo`, `source_sha`. It mints the `mctl-agents` App token from
`secrets.AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` with
`permission-contents: write` **and** `permission-pull-requests: write`, writes
`allowlists/<server>.json` and the `sources.json` entry, runs
`scripts/validate-portal-allowlists.py` before committing so a malformed
dispatch fails here rather than as a red PR, pushes branch
`portal-allowlist/<server>-<sha7>` and opens a PR whose title states the
delta (`portal(<server>): 22/45 -> 23/45 tools`). Concurrency group
`portal-allowlist-vendor-<server>`, `cancel-in-progress: false`.

It opens a PR rather than pushing to `main`. `CLAUDE.md`'s branch-protection
exception is written for `image.tag` and argued from "trivial changes"; a
change to what the portal exposes is the opposite of trivial, and the PR is
where `cloudflare-plan` shows the flip — which is the point of the whole
design.

In **each service repo**, a ~25-line workflow on
`push: branches: [main], paths: ['docs/portal-allowlist.json']` that dispatches
the above with `GITOPS_TOKEN`. No new secret: that token already needs only
`actions: write` on mctl-gitops, which is what the image bumps use.

Passing the content through the dispatch, rather than having gitops CI fetch
it, is what keeps mctl-gitops CI from ever needing to read the private
`projects-mcp` — the issue's stated reason. Provenance is not lost: the
`source_sha` lands in `sources.json`, and `--vendor-check` closes the loop
nightly from the one job that *does* already hold a token for `projects-mcp`.

### Retirement

Each script dies in the PR that makes it obsolete:

- controls: delete `scripts/portal-controls-apply.sh`,
  `tests/test_portal_controls_apply.py`, its `validate-manifests.yml` step, and
  `mcp-portal-controls.json`; rewrite the first section of
  `infrastructure/cloudflare/portal/README.md`; fix
  `docs/runbooks/cloudflare-operations.md` (its "that is not OpenTofu" bullet).
- membership: delete `scripts/portal-membership-add.sh`,
  `tests/test_portal_membership_add.py`, its step, and rewrite the README's
  membership section and the re-snapshot recipe's step 5 (which today tells the
  operator to run `portal-allowlist-apply.sh`, or to hand-`PUT` for
  `seerrsense`) to "edit the vendored file, let the bump PR plan, apply".
- allowlists: delete `scripts/portal-allowlist-apply.sh` from `mctl-telegram`,
  `mctl-api`, `projects-mcp`, `mctl-alice`; add the dispatch workflow to all
  six owning repos. Closes `mctlhq/mctl-telegram#635`, `mctlhq/mctl-api#300`,
  `mctlhq/seerrsense#70`.
- comment fixes: the `OWNERS` block in `scripts/portal-catalogue-drift.py`, the
  `DCR_SERVERS` note in `scripts/portal-auth-credentials-drift.py`, and
  `infrastructure/cloudflare/account/portal-mcp-apps.tf` lines 11 and 120,
  all of which name the retired scripts.

## Alternatives

**Keep the scripts, add `--check` to each.** The `#1092` position, and the
cheapest change: four repos grow a check mode and the nightly job calls them.
Dropped because it leaves six writers on one merge-semantics `PUT` — the
race documented in the portal README is a property of that fact, not of any
one script — and because a dashboard click still goes unnoticed for the
fields no script watches. It survives only as the fallback, where it is at
least reduced to *one* server-agnostic script in one repo with one approval
gate.

**Have mctl-gitops CI fetch each allowlist from `main` at plan time.** Removes
the vendoring and the bump PRs entirely. Dropped for three reasons: `plan`
would then depend on six external repos' `main` at the moment it runs, so the
plan is not reproducible and the apply may not be what was reviewed; it needs
a token for the private `projects-mcp` in the plan job, widening a credential
that today is `Account -> MCP Portals` and nothing else; and `fileset`/`file`
are the only ways a root reads data without a provider, so this would mean a
`http` data source or a CI pre-step writing the files anyway — which is
vendoring, just without review.

**Move the decision into mctl-gitops entirely.** One allowlist file per server
in this repo, no service-repo copy, no bump PRs. Simplest possible data flow.
Dropped because it reverses the one thing `#1092` got right and the portal
README states twice: "the decision *this tool is safe to expose* belongs in
the same diff as the tool". A tool added in `mctl-telegram` would be reviewed
in one repo and exposed by a PR in another, days apart.

**Declare `servers` but keep `updated_tools` in `ignore_changes` on the portal
resource.** Would give single ownership of membership and switches while
sidestepping the round-trip risk entirely. Dropped because it does not solve
the problem the issue is actually about — the allowlists — and it would leave
the four apply scripts alive with no path to retirement. It is, however, the
natural shape of the fallback if only `updated_tools` refuses to round-trip
while membership does.

## Platform impact

**Migration.** Three merged PRs and one operator-dispatched apply, in order:
vendoring + validator (inert, no tf change) → import + portal resource
(measurement) → apply → retirements. The apply is the only step that writes to
Cloudflare, and it is the existing approved path.

**Backward compatibility.** Between the import merging and the apply, the live
portal is unchanged and every existing script still works. After the apply the
scripts still work but are redundant and dangerous — an operator running
`portal-controls-apply.sh` would write a value tofu now owns, and the next
nightly plan would report it as drift. That is why the retirement PRs follow
immediately rather than being deferred, and why they delete rather than
deprecate.

**Resource impact.** None in-cluster. CI: one more `validate-manifests.yml`
step (stdlib Python, milliseconds), one more nightly network check on the
portal drift job, and one short workflow run per allowlist change.

**Risks and mitigations.**

- *Perpetual diff on `updated_tools`* — the reason the issue gates everything
  on task 0. Mitigated by taking the measurement before any apply, in CI, with
  a written fallback that is a smaller change than this one.
- *A first apply that rewrites `servers` wholesale.* The portal `PUT` is a
  merge, but the provider sends the whole `servers` set, so a server mapped
  live and absent from `mapping.json` would be dropped. Mitigated by
  `baseline.json` enumerating all six with their counts, by the validator
  asserting the declaration matches it, and by reading the import plan's
  attribute diff before approving the apply.
- *Two writers inside one root.* Mitigated by keeping `ignore_changes` on all
  four server resources and saying why in the comment.
- *A vendored copy silently lagging its source.* Inherent to pinning, and
  intended. Mitigated by `sources.json` + `--vendor-check` nightly, reported as
  a finding distinct from a stale catalogue so the two remedies stay separable.
  Note that `portal-catalogue-drift.py` itself is unaffected: it compares tool
  *names* against upstream `main` and ignores `enabled`, so a pending bump PR
  that only flips flags does not redden it.
- *The `mctl-agents` App's bypass being read as broader than it is.* Mitigated
  by opening a PR rather than pushing to `main`, and by not touching
  `CLAUDE.md`'s exception list.
- *A dispatched bump that widens exposure.* Mitigated by the `baseline.json`
  gate failing the PR until a human writes the new counts, and by the delta
  being in the PR title.
- *Loss of `portal-membership-add.sh`'s "empty catalogue" refusal.* Adding a
  seventh server now means writing a `mapping.json` entry by hand, which can
  name a tool the portal has never seen — the API answers `7001`. Mitigated by
  documenting the order in the README (create the server resource, apply, have
  an admin complete the first upstream login, *then* vendor an allowlist), and
  by the apply failing loudly rather than silently.
- *`api` and `seerrsense` mapped but unmanaged.* Their `servers[]` entries are
  declared here while their server registrations remain outside OpenTofu.
  Recorded as the `#1363` seam in both the code comment and the validator's
  `UNMANAGED` list, so closing `#1363` is a deletion from one list rather than
  a rediscovery.


## Amendment (owner, 2026-09-25)

1. **Vendored-file shape.** The proposal first specified vendored files as
   exactly `{"server", "tools"}` with tools exactly `{name, enabled}`, while
   also requiring them byte-identical to the service files. The two cannot
   both hold: every service file carries `$comment`, `portal`,
   `default_disabled` and a per-tool `reason` (tg also `upstream_gates`), so
   PR A would have failed its own validator on its own data. Byte-identical
   wins; the validator checks against an allowed key set instead. OpenTofu
   still reads only `name` and `enabled`.
2. **Two different `default_disabled`s.** The service file's
   `default_disabled: true` means *a tool absent from this file is
   disabled*. The portal's `servers[].default_disabled` means *this server is
   off by default for connecting clients*. They share a name only.
   `mapping.json` takes the portal attribute from the live portal, never from
   the service file; the validator only asserts the file's value is `true`.
3. **Coolify's file enumerates its whole catalogue** (45 entries, 22
   enabled), and PR A waits for `mctlhq/mctl-coolify-mcp#5` to merge.
4. **`override` (added 2026-09-25, mctlhq/mctl-coolify-mcp#5).** A service
   file may disable a read-only tool for a non-write reason with
   `"override": "sensitive-read"`. It only ever narrows exposure, so the
   gitops validator accepts it only with `enabled: false`; OpenTofu ignores it
   and applies `enabled` as usual.
