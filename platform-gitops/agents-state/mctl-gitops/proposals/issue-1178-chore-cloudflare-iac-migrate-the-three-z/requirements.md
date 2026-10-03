# Migrate the three Cloudflare zone roots onto the shared R2 backend

## Context

`infrastructure/cloudflare/zones/mctl-ru`, `zones/mctl-me` and `zones/mctl-ai`
are the only Cloudflare OpenTofu roots still without a `backend.tf`. They have
no `backend "local"` block either — their `versions.tf` files carry a comment
saying "No backend block yet", which resolves to the implicit local backend, so
on a fresh CI runner each of them plans against empty state. All three are
listed in `infrastructure/cloudflare/.local-state-roots`, which is read by
`cloudflare-drift.yml` (skips them), by `cloudflare-plan.yml` (excuses them from
the backend requirement and from the resolved-backend assertion) and by
`.github/scripts/cloudflare-assert-applyable-root.sh` (makes
`cloudflare-apply.yml` refuse them). The consequence is recorded in
`infrastructure/cloudflare/README.md`: the three zone-setting changes shipped so
far had to be applied through the Cloudflare API by hand and then pinned with
`import` blocks, because a value the configuration cannot reach would leave the
fail-closed drift workflow red every night.

This proposal is the configuration half of the ownership transfer: each zone
root gains the same `backend "s3"` block the account and portal roots already
use (R2 bucket `mctl-cloudflare-state`, `use_lockfile = true`, one state key
derived from the root path), its entry leaves `.local-state-roots`, the guard
self-test that depends on that list is rebuilt against a fixture tree, and the
documentation stops claiming that zone settings must be hand-applied. Per the
DevLoop boundary added to the issue on 2026-09-19 this is **one pull request
covering all three roots**; the environment-approved import-only apply per root,
the post-apply `No changes` evidence, the first green scheduled drift run and
the backup evidence are operator work tracked in `mctlhq/mctl-gitops#1281`.

## User stories

- AS a platform operator I WANT the three zone roots to keep their state in the
  shared R2 bucket SO THAT a plan of those roots is a statement about live
  Cloudflare rather than about empty state.
- AS a platform operator I WANT `cloudflare-drift.yml` to cover the zone roots
  SO THAT an out-of-band change to DNS, rulesets, email routing or zone settings
  is reported instead of being invisible.
- AS a platform operator I WANT `cloudflare-apply.yml` to stop refusing the zone
  roots SO THAT a zone-setting change can be reviewed as a plan and applied from
  CI instead of being applied by hand and import-pinned afterwards.
- AS a reviewer of this repository I WANT the CI guards to keep failing closed
  after `.local-state-roots` empties SO THAT the checks that protect the apply
  path are not silently reduced to accepting everything.
- AS a future maintainer I WANT the READMEs to describe the remote-state
  procedure and drop the "hand-applied zone settings" exception SO THAT the
  documented ritual matches what the roots can actually do.

## Acceptance criteria (EARS)

- WHEN the pull request is opened THE SYSTEM SHALL contain exactly one
  `backend.tf` in each of `infrastructure/cloudflare/zones/mctl-ru`,
  `zones/mctl-me` and `zones/mctl-ai`, each declaring `backend "s3"` with
  `bucket = "mctl-cloudflare-state"`, endpoint
  `https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com`,
  `region = "auto"`, `use_lockfile = true`, the four `skip_*` flags and
  `use_path_style = true`, byte-for-byte consistent with
  `infrastructure/cloudflare/account/backend.tf` except for `key`.
- WHILE each root's `backend.tf` is in the tree THE SYSTEM SHALL use the state
  key `cloudflare/zones/<root>/terraform.tfstate`, which is the value
  `.github/scripts/cloudflare-assert-backend.sh` derives from the root path
  (`cloudflare/${ROOT#infrastructure/cloudflare/}/terraform.tfstate`).
- WHEN the pull request is opened THE SYSTEM SHALL no longer list any of the
  three roots in `infrastructure/cloudflare/.local-state-roots`, while keeping
  that file's header prose explaining the mechanism.
- WHILE the same commit adds a backend and removes the list entry THE SYSTEM
  SHALL keep the two halves together, because `cloudflare-plan.yml`'s
  "Assert remote backend" step fails a root that resolved a non-local backend
  while still being listed, and its "Guard root coverage" step fails a root that
  is unlisted with no `backend.tf`.
- WHEN `cloudflare-plan.yml` runs on the pull request THE SYSTEM SHALL pass the
  `Guard root coverage` step without the `cloudflare-root-removal` label, and
  each migrated root's plan job SHALL print `<root> is on the s3 backend`.
- WHEN each migrated root is planned on the pull request THE SYSTEM SHALL report
  its `import` blocks as the only planned actions — 7 for `mctl-ru`, 14 for
  `mctl-me`, 26 for `mctl-ai` — with `0` in the create, update and destroy
  columns of the `Summarize` step's table.
- IF any migrated root's pull-request plan shows a create, update or destroy
  THEN THE SYSTEM SHALL be treated as out-of-band drift: the pull request is not
  merged and the difference is investigated first.
- WHEN `.local-state-roots` no longer names a real root THE SYSTEM SHALL still
  pass `CLOUDFLARE_GUARD_SELF_TEST=1
  .github/scripts/cloudflare-assert-applyable-root.sh`, with the list-dependent
  `reject` cases rebuilt against a fixture tree as that file's own
  "DO NOT DELETE THE `reject` CASE WHEN .local-state-roots EMPTIES" comment
  instructs, and with a paired `accept` control so the case cannot pass for the
  wrong reason.
- WHEN `.github/scripts/cloudflare-local-state-roots.sh` is run against the
  edited file THE SYSTEM SHALL print nothing and exit 0.
- WHEN `tofu fmt -check -diff` and `tofu validate` run in each migrated root
  THE SYSTEM SHALL report no diff and no error.
- WHEN the documentation is read after the change THE SYSTEM SHALL no longer
  state that a zone root keeps local state, that a zone root cannot apply from
  CI, or that zone settings must be applied by hand and import-pinned; this
  covers the "Zone settings" paragraph and the `cloudflare-plan.yml` /
  `cloudflare-drift.yml` rows of the workflow table in
  `infrastructure/cloudflare/README.md`, plus the corresponding sections of
  `zones/mctl-ru/README.md`, `zones/mctl-me/README.md` and
  `zones/mctl-ai/README.md`.
- WHILE the documentation is updated THE SYSTEM SHALL leave the unrelated
  `dmitriimashkov.com` "standing exception" paragraph
  (`infrastructure/cloudflare/README.md`, the zone with no root, decision 10)
  intact, since that exception is about an intentionally unmanaged zone and not
  about hand-applied zone settings.
- WHEN each root's README is read after the change THE SYSTEM SHALL record the
  root's state key, the expected imports-only plan, that the import is executed
  by dispatching `cloudflare-apply.yml` on `main` rather than from a laptop, and
  that the post-import verification plan prints `No changes.`
- IF the READMEs still describe a local `tofu state rm` reversibility ritual
  THEN THE SYSTEM SHALL mark it as an operation on shared remote state, because
  the state it edits is no longer throwaway.

## Out of scope

- The import-only apply itself. Writing each state object needs the
  `cloudflare-apply` environment's required reviewer and the per-root
  `CF_APPLY_TOKEN_MCTL_*` write credential; it is dispatched on `main` after
  this pull request merges and is tracked in `mctlhq/mctl-gitops#1281`.
- Proving `No changes` against remote state, the first green scheduled
  `cloudflare-drift.yml` run, the dispatched `cloudflare-apply.yml` `plan`
  acceptance and the scheduled state-backup evidence. All four require a merged
  main, live credentials or a scheduled run, so none can be produced inside the
  pull request; they are `#1281`'s acceptance evidence.
- Any change to what the three roots manage. No resource, `import` block, zone
  setting, DNS record, ruleset or email-routing rule is added, removed or
  altered; the only `.tf` files touched are the new `backend.tf` files and the
  stale backend comments in each `versions.tf`.
- `opentofu-state-backup.yml`. It snapshots `s3://mctl-cloudflare-state`
  recursively with `--include '*.tfstate'`, so the three new keys are picked up
  with no code change once they exist.
- The per-root write-token chain in `cloudflare-apply.yml`. It already maps
  `CF_APPLY_TOKEN_MCTL_RU`, `CF_APPLY_TOKEN_MCTL_ME` and
  `CF_APPLY_TOKEN_MCTL_AI`; verifying those secrets exist is operator work.
- Worker routes for `mctl.me` / `mctl.ru`, `dmitriimashkov.com`, and the
  `security_level` setting — all deliberately unmanaged today and unaffected.
- Any change to `infrastructure/k3s-preview` or to the `mctl-terraform-state`
  bucket.

## Open questions

- The issue says "replace `backend "local"` with the shared `backend "s3"`".
  No zone root contains a `backend "local"` block; they contain a comment saying
  no backend block exists yet, which resolves to the implicit local backend.
  Interpretation taken: add `backend.tf` and delete the stale comment.
- The issue's scope item 2 ("re-run the imports against the remote state and
  prove `No changes`") cannot happen inside the pull request, because the first
  write to a state key is an apply. Interpretation taken: the pull request ships
  the configuration and shows each root's imports-only plan from
  `cloudflare-plan.yml`; the `No changes` proof is `#1281`.
- Between merge and the three import-only applies, each migrated root plans its
  imports against an empty remote state, so a scheduled `cloudflare-drift.yml`
  run (06:00 UTC) in that window exits 2 and reports `DRIFT` with pending
  imports. Interpretation taken: the window is named in the READMEs and in the
  pull-request body so the operator dispatches the applies before the next
  scheduled run; nothing in the pull request can shorten it, and keeping the
  roots listed to suppress it is rejected by the plan job's listed-root /
  resolved-backend mismatch check.
- The ordering `mctl-ru` -> `mctl-me` -> `mctl-ai` is a property of the applies,
  not of a single pull request. Interpretation taken: record the order as the
  documented apply order rather than splitting the pull request.
- `.local-state-roots` becomes entry-free. Interpretation taken: keep the file
  with its header prose (the helper's own comment calls an empty list "the
  normal end state", and three workflow steps plus two guards read it) rather
  than deleting it.
