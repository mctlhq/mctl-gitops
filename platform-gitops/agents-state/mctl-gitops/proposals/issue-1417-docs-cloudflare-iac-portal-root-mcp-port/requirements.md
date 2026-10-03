# Write down the `mcp_portal` provider verdict, the per-resource unmanaged/secret field table, and the runtime-state exclusion

## Context

Issue #1417 is a docs-only child of #1092. Three of #1092's acceptance
criteria are about recording decisions that have already been taken and
proven in production, and none of the three is met on `main` today. The
`mcp_portal` provider-support verdict is **supported** — `type = "mcp_portal"`
is on line 32 of `infrastructure/cloudflare/account/portal-app.tf`, imported
in apply run 35798537646 and zero-diff in every nightly `cloudflare-drift.yml`
run since — but neither `infrastructure/cloudflare/portal/README.md` nor
`infrastructure/cloudflare/account/README.md` says so, so the next person to
ask "can OpenTofu express an MCP portal Access application?" has to re-measure
it. The facts about intentionally unmanaged fields and about secrets that are
bootstrapped interactively exist, but scattered across prose paragraphs
(`portal/README.md` "The field OpenTofu cannot see", lines ~78-107) and `.tf`
comments (`mcp-servers.tf`, `portal-app.tf` lines ~21-23), with no per-resource
table anyone can scan. And the deliberate exclusion of runtime OAuth/session
state is nowhere at all.

Two lines are also actively wrong, which is worse than missing. `portal/README.md`
~104-107 still says `updated_tools` / `updated_prompts` "are the allowlists owned
by `mctl-telegram`, `mctl-api` and `seerrsense`, applied from those repositories" —
untrue since #1370, which made `mcp-portal.tf` the single writer of the portal
mapping from vendored `allowlists/*.json`. `account/README.md` ~78-80 still says
"The portal object itself is still unimported" — untrue since the #1370 import
(apply run 36117508212, plan `1 to import, 0 to change`), which the very first
paragraph of `portal/README.md` records. Both are the kind of stale line a reader
acts on before noticing it contradicts another file.

This proposal changes documentation only. No `.tf` file is touched, no apply
is dispatched, and nothing about the live Cloudflare account changes.

## User stories

- AS an operator picking up the portal root, I WANT the `mcp_portal`
  provider-support verdict written down with its provider version and the apply
  run that proved it SO THAT I do not re-measure a question that has a
  production answer.
- AS a reviewer of a Cloudflare pull request, I WANT one per-resource table of
  managed fields, `ignore_changes`, write-only / interactively bootstrapped
  secrets and excluded runtime state SO THAT I can tell in one read whether a
  proposed change touches something OpenTofu deliberately does not own.
- AS an auditor of #1092, I WANT the runtime OAuth/session state exclusion
  stated with its reason SO THAT "Git is the desired state" is not read as a
  claim that per-user grants and sessions are in Git.
- AS anyone reading `portal/README.md` or `account/README.md`, I WANT the two
  stale lines corrected SO THAT the READMEs of two roots do not contradict each
  other about who writes the allowlists and whether the portal is imported.

## Acceptance criteria (EARS)

- WHEN a reader opens `infrastructure/cloudflare/portal/README.md` THE SYSTEM
  SHALL present a "Provider support" section stating that
  `cloudflare_zero_trust_access_ai_controls_mcp_portal`,
  `cloudflare_zero_trust_access_ai_controls_mcp_server` and
  `cloudflare_zero_trust_access_application` with `type = "mcp_portal"` are
  supported by `cloudflare/cloudflare` 5.x (measured 2026-09-12, lock file
  5.24.0), citing `account/portal-app.tf:32`, apply run 35798537646 and the
  zero-diff nightly drift record.
- WHEN that section is read THE SYSTEM SHALL also name the two things provider
  5.24 cannot express — `auth_credentials` being write-only, and the catalogue
  attribute `tools` typed `list(map(string))` so it is empty in state
  (measured on #1382) — so that "supported" is not read as "complete".
- WHEN a reader reaches the per-resource table in
  `infrastructure/cloudflare/portal/README.md` THE SYSTEM SHALL list one row
  each for: the portal object
  (`cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp`), the six servers
  (`tg`, `api`, `seerrsense`, `projects`, `alice`, `coolify`), the `mcp_portal`
  Access application, and the `mcp` Access applications (the three managed in
  `account/portal-mcp-apps.tf` and the three deliberately unmanaged siblings).
- WHILE that table exists THE SYSTEM SHALL give it exactly four content
  columns: managed fields, `ignore_changes`, write-only or secret-bootstrap
  (labelled `interactive-secret-bootstrap`, never committed), and runtime state
  excluded.
- WHEN a row describes a server THE SYSTEM SHALL record that every server is
  registered by DCR with no `auth_credentials` and no `client_secret`, that
  `updated_tools` and `updated_prompts` are in `lifecycle.ignore_changes`
  because `mcp-portal.tf` is their single writer, and that the first upstream
  OAuth login from the dashboard is an `interactive-secret-bootstrap` step
  Terraform cannot perform.
- WHEN a row describes the `mcp_portal` Access application THE SYSTEM SHALL
  record that `oauth_configuration` is deliberately unset (turning on Access
  managed OAuth would replace the portal's own authorization server under every
  connected client) and that its policy is referenced by id, so the policy body
  is not managed here.
- WHEN a reader reaches the "Deliberately not in Git" paragraph THE SYSTEM
  SHALL name per-user upstream OAuth grants, Access user sessions, and the
  server runtime fields `status`, `last_synced` and `authentication_status`, and
  SHALL give the reason as `runtime-user-state` under `mctlhq/.github#47`.
- IF a reader looks for where runtime state is watched instead THEN THE SYSTEM
  SHALL point at the things that do watch it —
  `.github/workflows/cloudflare-portal-health.yml`,
  `scripts/portal-auth-credentials-drift.py` and
  `scripts/portal-catalogue-drift.py` — rather than leaving the exclusion
  looking like an oversight.
- WHEN the stale bullet at `portal/README.md` ~104-107 is read after this change
  THE SYSTEM SHALL state that since #1370 OpenTofu is the only writer of the
  portal mapping, from allowlists vendored into `allowlists/<id>.json`, and that
  `ignore_changes` on the server resources exists to keep this root from having
  two writers of one mapping.
- WHEN the import list at `account/README.md` ~72-80 is read after this change
  THE SYSTEM SHALL state that the portal object was imported in #1370 (apply run
  36117508212) into `../portal/`, and SHALL NOT claim it is unimported.
- WHILE this proposal is implemented THE SYSTEM SHALL leave every `.tf`, `.json`
  and workflow file in `infrastructure/cloudflare/` byte-identical.
- WHEN the pull request runs CI THE SYSTEM SHALL keep every required check
  green, including `cloudflare-plan`, which runs per-root plans for any pull
  request touching `infrastructure/cloudflare/` — a documentation-only diff must
  therefore still produce the same plans as `main`.

## Out of scope

- Any change to a `.tf` file, any `allowlists/*.json` edit, and any dispatch of
  `cloudflare-apply.yml`. This proposal writes no configuration and applies
  nothing.
- The Access-application import for the three unmanaged `mcp` siblings (`api`,
  `tg`, `seerrsense`), which is a separate child of #1092. This proposal only
  records that they are unmanaged today.
- Correcting the portal object's stale `description` ("Phase 0: tg only"). It is
  a live-value change to `mcp-portal.tf` and therefore an apply, which
  `portal/README.md` already calls out as a separate, visible change.
- Editing the body of issue #1083 or #1092 on GitHub. A pull request cannot do
  it; see Open questions.
- Adding a markdown linter to CI. The repository has none today, and introducing
  one would reformat far more than these two files.

## Open questions

- **"The root README" in criterion 2 is ambiguous.** It can mean the OpenTofu
  *root* module's README (`infrastructure/cloudflare/portal/README.md`) or the
  directory root README (`infrastructure/cloudflare/README.md`). Scope item 1 of
  the issue names `portal/README.md` explicitly, so the authoritative text goes
  there; a one-line cross-reference is added next to the existing
  "Inventory and the zero-diff proof: `mctl-gitops#1083`" line
  (`infrastructure/cloudflare/README.md:6`) so the other reading is satisfied
  too. Proceeding on that interpretation.
- **"and in the #1083 matrix" is not a repository artifact.** No file in this
  clone contains that matrix — `1083` appears exactly once, in
  `infrastructure/cloudflare/README.md:6`, as a reference to the GitHub issue.
  A pull request cannot update an issue body. Interpretation: this proposal
  satisfies the in-repo half, and the implementer records in the PR description
  that the #1083 issue-body matrix needs the same one-line verdict added by
  hand. Flagged rather than blocked.
- **Whether the "Deliberately not in Git" paragraph belongs in both READMEs.**
  The issue says it is stated in neither. Interpretation: the full paragraph
  goes in `portal/README.md` (which owns the portal and the servers, hence
  `status` / `last_synced` / `authentication_status`), and a short pointer goes
  in `account/README.md` next to the Access applications, because Access user
  sessions are that root's surface.
- **Whether `client_secret_version` counts as runtime state.** It is a live
  field `scripts/portal-auth-credentials-drift.py` compares against state, and
  no server is manual today. It is recorded in the table as historical
  write-only context rather than in the runtime-exclusion paragraph.
- `infrastructure/cloudflare/README.md`'s Layout block (lines 24-28) lists only
  `account/` and `zones/<zone>/`, not `portal/`. That is a fourth stale line the
  audit did not list. Not fixed here — it is outside items 1-4 — and worth its
  own issue.
