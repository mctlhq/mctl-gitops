# Migrate the three Cloudflare zone roots from local state to R2 and put them under drift

## Context

`infrastructure/cloudflare/` holds five OpenTofu roots. Two of them — `account/`
and `portal/` — carry a `backend.tf` with the shared R2 (`s3`) backend, so their
state lives in the `mctl-cloudflare-state` bucket, `cloudflare-drift.yml` plans
them nightly and `cloudflare-apply.yml` will act on them. The three zone roots
(`zones/mctl-ru`, `zones/mctl-me`, `zones/mctl-ai`) have no `backend.tf` at all:
each `versions.tf` still carries the "No backend block yet" comment, and all
three are listed in `infrastructure/cloudflare/.local-state-roots`. Every import
proven so far (#1096, #1103, #1115) ran against throwaway local state, so the
zero-diff proofs recorded in the root READMEs are real but nothing owns the
result. Drift skips these roots by design and apply refuses them
(`.github/scripts/cloudflare-assert-applyable-root.sh`), which is why the three
zone-setting changes (#1142, #1154, #1168) had to be applied by hand through the
API and then import-pinned so the configuration stayed reachable.

The apply identities those roots need now exist: `cloudflare-apply.yml` already
maps `CF_APPLY_TOKEN_MCTL_RU`, `CF_APPLY_TOKEN_MCTL_ME` and
`CF_APPLY_TOKEN_MCTL_AI` per root, and `R2_APPLY_*` is Object Read & Write on the
state bucket. What is missing is the ownership transfer itself: declare the
shared backend on each zone root, re-run the imports against remote state so an
R2 state object exists, take the root off `.local-state-roots`, and let drift
watch it. Until that happens the three zones that actually serve traffic are the
only part of the Cloudflare control plane with no detector behind it.

## User stories

- AS a platform operator I WANT the three zone roots to keep their state in
  `mctl-cloudflare-state` SO THAT a plan of a zone reflects what is live in
  Cloudflare rather than an empty local file.
- AS a platform operator I WANT `cloudflare-drift.yml` to plan the three zone
  roots nightly SO THAT an out-of-band DNS, ruleset or zone-setting change on
  `mctl.ai`, `mctl.me` or `mctl.ru` is reported instead of going unnoticed.
- AS a reviewer I WANT zone changes to be applied by `cloudflare-apply.yml`
  under the existing approval and plan-digest gate SO THAT "applied by hand and
  then import-pinned" stops being the way zone settings change.
- AS the person restoring state after an incident I WANT the three new state
  objects to appear in the nightly `opentofu-state-backup.yml` snapshot SO THAT
  the zone roots have the same recoverability as the account root.

## Acceptance criteria (EARS)

- WHEN a zone root is migrated THE SYSTEM SHALL declare the shared backend in
  its own `backend.tf` file (not in `versions.tf`), with
  `bucket = "mctl-cloudflare-state"`, `key = "cloudflare/zones/<root>/terraform.tfstate"`,
  the R2 endpoint `https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com`
  and `use_lockfile = true`, so that `.github/scripts/cloudflare-assert-backend.sh`
  accepts it.
- WHEN a zone root gains its `backend.tf` THE SYSTEM SHALL remove that root's
  entry from `infrastructure/cloudflare/.local-state-roots` in the same pull
  request.
- IF a root is listed in `.local-state-roots` and `tofu init` resolved a
  non-local backend for it THEN THE SYSTEM SHALL fail the `cloudflare-plan`
  check (the existing "Assert remote backend" branch), which is why the two
  changes cannot be split across pull requests.
- WHEN `cloudflare-plan.yml` runs on the migration pull request THE SYSTEM SHALL
  report "`<root>` is on the s3 backend", pass the root-coverage guard without
  the `cloudflare-root-removal` label, and publish a plan whose create, update
  and destroy columns are all zero.
- WHEN the migration lands on `main` THE SYSTEM SHALL allow
  `cloudflare-apply.yml` to be dispatched for that root: the "Validate the root"
  step prints `root '<root>' accepted` and the mapped write token resolves.
- WHEN the import-only apply completes for a root THE SYSTEM SHALL leave
  Cloudflare unmutated — the applied plan shall show only imports, with zero
  add, change and destroy — and shall write that root's state object to
  `mctl-cloudflare-state`.
- WHEN the root is planned again after that apply THE SYSTEM SHALL print
  `No changes.`
- WHILE all three roots are migrated THE SYSTEM SHALL leave
  `.local-state-roots` with no root entries, and
  `.github/scripts/cloudflare-local-state-roots.sh` shall still exit 0 printing
  nothing.
- WHEN `.local-state-roots` no longer lists `zones/mctl-ru` THE SYSTEM SHALL
  still pass `CLOUDFLARE_GUARD_SELF_TEST=1 .github/scripts/cloudflare-assert-applyable-root.sh`
  — the suite's two list-dependent cases must be rebuilt against a fixture tree,
  as the "DO NOT DELETE THE `reject` CASE" comment in that file instructs.
- WHEN the next scheduled `cloudflare-drift.yml` run fires after a migration
  THE SYSTEM SHALL include the migrated root in its matrix and report it in
  sync, with no "this root's state holds no resources" warning.
- WHEN the next scheduled `opentofu-state-backup.yml` run fires after all three
  migrations THE SYSTEM SHALL count five state objects in
  `mctl-cloudflare-state` and copy all five into the dated `_backups/` prefix.
- WHEN all three roots can apply from CI THE SYSTEM SHALL no longer claim in
  `infrastructure/cloudflare/README.md` that the zone roots keep local state,
  cannot apply from CI, and therefore need their zone settings applied by hand.
- IF any migration plan shows an add, change or destroy action THEN THE SYSTEM
  SHALL stop and the change shall be investigated as out-of-band drift rather
  than applied.

## Out of scope

- Any mutating apply against Cloudflare. The only apply this proposal asks for
  is import-only: it writes state, not Cloudflare objects.
- Importing objects that are deliberately unmanaged: worker routes for
  `mctl.ru` / `mctl.me`, `TXT _acme-challenge.*`, page rules (deleted in #1089),
  `security_level`, and everything owned by `mashkovd/mac-mini-infra` (#1090).
- `dmitriimashkov.com`, which has no root at all (decision 10) and keeps its own
  separate standing exception.
- Changing the `.local-state-roots` mechanism, the guard scripts' logic, or the
  coverage guard. Only the self-test fixtures that depend on the list's current
  contents change.
- Off-bucket state backup (still blocked by R2 bucket-scoped tokens) and R2
  object versioning (does not exist).
- `infrastructure/k3s-preview`, which runs on HashiCorp Terraform and a
  different bucket.

## Open questions

- The issue says "no apply is required to close this issue", but an empty R2
  object means the root's plan is "N to import", which is drift's failure
  signal, and means the backup has nothing to copy. Two acceptance criteria in
  the same issue (green drift, state objects in the backup) therefore require an
  import-only apply. Interpretation taken: what is not required is a *mutating*
  apply; the import-only apply through `cloudflare-apply.yml` is in scope.
- Which "standing exception" wording the issue means. There are two in
  `infrastructure/cloudflare/README.md`: the paragraph saying the zone roots
  keep local state and so zone settings are applied by hand, and a separate one
  about `dmitriimashkov.com` being intentionally unmanaged. Interpretation:
  remove the first, keep the second — the second is about a zone with no root
  and is unaffected by this migration.
- One PR or three. Interpretation: three sequential pull requests in the issue's
  order (`mctl-ru` → `mctl-me` → `mctl-ai`), with the guard self-test fixture
  work done in the first; a single PR showing three separate zero-diff plans
  remains acceptable if the reviewer prefers it.
- Whether `CF_APPLY_TOKEN_MCTL_RU` / `_ME` / `_AI` and `R2_APPLY_*` actually
  exist as **environment** secrets on `cloudflare-apply` (#1111 was a checklist;
  the workflow only fails at dispatch time if they do not). Verified before the
  first dispatch, not assumed.
- `zones/mctl-ru/README.md` still documents the two-record pilot plan ("2 to
  import") while `import.tf` now carries seven import blocks. The migration
  re-measures and records the real figure.
