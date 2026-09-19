# Design: issue-1178-chore-cloudflare-iac-migrate-the-three-z

## Current state

**The roots.** `infrastructure/cloudflare/` holds five OpenTofu roots, each
identified by a `versions.tf`: `account/`, `portal/`, `zones/mctl-ru/`,
`zones/mctl-me/`, `zones/mctl-ai/`, plus the shared `modules/zone-baseline/`
which is explicitly not a root. `account/backend.tf` and `portal/backend.tf`
both declare the same `backend "s3"` block — R2 endpoint
`https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com`, bucket
`mctl-cloudflare-state`, `region = "auto"`, `use_lockfile = true`, plus
`skip_credentials_validation`, `skip_requesting_account_id`,
`skip_metadata_api_check`, `skip_region_validation` and `use_path_style` —
differing only in `key` (`cloudflare/account/terraform.tfstate`,
`cloudflare/portal/terraform.tfstate`).

The three zone roots have no `backend.tf` at all. Each `versions.tf` ends with a
comment instead: `zones/mctl-ru/versions.tf` says "No backend block yet. The
zero-diff pilot (#1087) runs against a local state file ... the R2 backend and
its state key arrive with the control-plane bootstrap (#1093)";
`zones/mctl-me/versions.tf` repeats it verbatim; `zones/mctl-ai/versions.tf`
says the same and points at `../../.local-state-roots`. So the effective backend
is the implicit local one, and on a fresh runner that means empty state.

**What the roots describe.** Counting `import` blocks: `zones/mctl-ru/import.tf`
has 7 (apex and wildcard records, the dynamic-redirect and firewall rulesets
through `module.baseline`, and `min_tls_version` / `always_use_https` / `ssl`),
`zones/mctl-me/import.tf` has 14 (the same baseline four plus seven zone-local
records plus the three settings), `zones/mctl-ai/import.tf` has 26 (thirteen DNS
records, the custom firewall ruleset, seven email-routing rules, the catch-all,
the MCP-portal CNAME, and three zone settings declared in `zones/mctl-ai/tls.tf`
rather than in the module, because that root does not use `zone-baseline`).

**The exception list.** `infrastructure/cloudflare/.local-state-roots` names all
three roots, with per-root prose explaining the deferral ("belongs to #1103",
"the migration is that issue's follow-on"). It is parsed by
`.github/scripts/cloudflare-local-state-roots.sh`, which strips CR and inline
comments, normalises to the `infrastructure/cloudflare/...` prefix, and uses
`awk 'NF'` rather than `grep -v` specifically so that an empty list exits 0 —
its comment calls an empty list "the normal end state of this list". Four
consumers read it:

1. `cloudflare-drift.yml` (`discover` job, lines ~43-85) subtracts the listed
   roots from the discovered set, so the three zones are never planned on the
   06:00 UTC schedule, and fails the run if a listed entry names no real root.
2. `cloudflare-plan.yml` "Guard root coverage" (check 2, lines ~222-227) excuses
   a listed root from the `backend.tf`-must-exist requirement, and separately
   (lines ~256-262) fails if a listed entry is not a discovered root.
3. `cloudflare-plan.yml` "Assert remote backend" (lines ~460-500) reads
   `backend.type` out of `$TF_DATA_DIR/terraform.tfstate` after `tofu init`. For
   a listed root it requires the resolved backend to be `local` (or absent) and
   emits a warning; for an unlisted root it requires `s3`. So a root that gains
   an `s3` backend while staying on the list **fails**: "resolved the 's3'
   backend but is still listed in .local-state-roots".
4. `.github/scripts/cloudflare-assert-applyable-root.sh`, called by both jobs of
   `cloudflare-apply.yml`, refuses a listed root outright: "it has no remote
   state to apply against".

**The guard self-tests.** `cloudflare-plan.yml`'s `assert-scripts` job runs both
guards with `CLOUDFLARE_GUARD_SELF_TEST=1` unconditionally on every pull
request, because these scripts fail by *accepting*. The applyable-root
self-test hard-codes `zones/mctl-ru` in list-dependent cases —
`expect reject "infrastructure/cloudflare/zones/mctl-ru" "root listed in
.local-state-roots"` and `expect_from /tmp reject ... "listed root, foreign
cwd"` — and carries an explicit instruction: "DO NOT DELETE THE `reject` CASE
WHEN .local-state-roots EMPTIES ... replace this case against whatever root is
listed then — or, if none is, with a fixture tree like the failing-helper case
above." The non-canonical spellings (`.../mctl-ru/`, `/.`, `//zones/`) are
rejected by the canonical-form arm before the list is consulted, so they survive
the list emptying; the two cases named above do not. The backend self-test
already contains `expect accept ... "cloudflare/zones/mctl-me/terraform.tfstate"
... "a nested zone root"`, so the key shape this change introduces is already
asserted.

**Credentials.** The pull-request plan job uses the read-only
`CLOUDFLARE_API_TOKEN` (zone-scoped) and `R2_PLAN_ACCESS_KEY_ID`, which is
Object Read on `mctl-cloudflare-state` only — hence `-lock=false` on every plan,
since taking the lock is a write. `cloudflare-apply.yml` maps one write token
per root and already includes `CF_APPLY_TOKEN_MCTL_RU`,
`CF_APPLY_TOKEN_MCTL_ME` and `CF_APPLY_TOKEN_MCTL_AI`; the only thing making it
refuse the zone roots today is the `.local-state-roots` entry.
`opentofu-state-backup.yml` snapshots each bucket recursively with
`--include '*.tfstate'`, so it needs no per-key list.

**The documented consequence.** `infrastructure/cloudflare/README.md` "Zone
settings" (lines ~180-187) states that the values were applied through the API
first because "All three zone roots keep local state and cannot apply from CI
while they are listed in `.local-state-roots` (#1111)". The `cloudflare-plan.yml`
row of the workflow table (line ~392) still says the list holds only
`zones/mctl-ru` and that its migration "belongs to #1103" — stale on both
counts. Each zone README repeats the local-state reasoning, and
`zones/mctl-ru/README.md` documents a `tofu state rm` reversibility step that was
safe only because the state was throwaway. A separate paragraph (lines ~205-208)
describes `dmitriimashkov.com` as a "standing exception" — that one is about a
zone with no root at all and must survive.

## Proposed solution

One pull request, five kinds of change, no behavioural change to what the roots
manage.

**1. Add `backend.tf` to each zone root.** Copy `account/backend.tf` verbatim,
changing only `key`:

| root | key |
| --- | --- |
| `infrastructure/cloudflare/zones/mctl-ru` | `cloudflare/zones/mctl-ru/terraform.tfstate` |
| `infrastructure/cloudflare/zones/mctl-me` | `cloudflare/zones/mctl-me/terraform.tfstate` |
| `infrastructure/cloudflare/zones/mctl-ai` | `cloudflare/zones/mctl-ai/terraform.tfstate` |

The keys are not free choices: `cloudflare-assert-backend.sh` derives
`EXPECTED_KEY="cloudflare/${ROOT#infrastructure/cloudflare/}/terraform.tfstate"`
from the root path and refuses anything else, precisely so a typo becomes a
failure instead of a plan computed from empty state. `use_lockfile = true` is
likewise asserted (`// empty` is deliberately avoided there so an explicit
`false` is distinguishable from absence), and the endpoint is matched exactly,
not as a substring.

A separate `backend.tf` file rather than a block inside `versions.tf` is
required, not stylistic: `cloudflare-plan.yml`'s coverage guard tests
`grep -qxF -- "$r/backend.tf" <<< "$head_paths"` against the git tree.

**2. Delete the stale backend comments** at the end of each root's
`versions.tf`, replacing them with a one-line pointer to `backend.tf`. Leaving
them is worse than cosmetic: they assert the root is on local state, which
after this change is false, and the repository's convention is that comments
explain non-obvious configuration rather than narrate history that has moved on.
The provider block and `required_providers` are untouched, so
`.terraform.lock.hcl` stays valid under `tofu init -lockfile=readonly`.

**3. Empty `.local-state-roots` of entries.** Remove all three path lines and
the per-root prose blocks, keep the header prose that explains what the file
means and which three guards read it, and add a short line recording that the
list is empty as of this change. The helper already handles an empty list, drift
falls back to "all discovered roots" when the file produces no output
(`if [ -s "$RUNNER_TEMP/local-state-roots" ]`), and the plan guard's reverse
check iterates nothing.

This has to be the same commit as (1). The two orderings both fail closed on
purpose: backend without delisting trips "resolved the 's3' backend but is still
listed", delisting without a backend trips "root declares no backend". That is
the invariant this design leans on rather than works around.

**4. Rebuild the list-dependent guard self-test cases.** In
`cloudflare-assert-applyable-root.sh`, replace the two cases that depend on a
real listed root with a fixture tree, following the pattern the failing-helper
case already establishes in that file: `mktemp -d`, create
`.github/scripts/`, copy both the guard **and** the real
`cloudflare-local-state-roots.sh` into it, create
`infrastructure/cloudflare/zones/<stub>/versions.tf`, write a
`.local-state-roots` naming that stub root, and assert

- `reject` for the stub root while it is listed, run from the fixture tree;
- `reject` for the same root from a foreign cwd (`/tmp`) — the case that pins
  the "list path resolved against the caller's cwd" defect, which is why the
  file's comment forbids deleting it;
- `accept` for the same root with an empty fixture list, as the control that
  stops the two rejects passing for the wrong reason.

The single `trap cleanup EXIT` discipline the file insists on is preserved: the
new fixture is cleaned by the existing `cleanup` function (extend it; do not add
a second EXIT trap — the file records that mistake being made once already).
Labels of the three non-canonical `mctl-ru` cases are reworded to say the
rejection comes from the canonical-form arm, since the list no longer
contributes; the cases themselves stay, and may keep using `account` as the
subject root.

**5. Documentation.**

- `infrastructure/cloudflare/README.md`, "Zone settings": rewrite the paragraph
  so the API-first ordering is recorded as history ("applied through the API
  before the configuration landed, while the zone roots could not apply —
  #1178 removed that constraint"), and state plainly that a zone-setting change
  is now a plan reviewed in `cloudflare-apply.yml`. Remove the claim that the
  roots keep local state and cannot apply from CI. The `dmitriimashkov.com`
  "standing exception" paragraph is left exactly as it is.
- The same file's workflow table: the `cloudflare-plan.yml` row stops naming
  `zones/mctl-ru` as the listed root and describes the list as empty; the
  `cloudflare-drift.yml` row keeps the explanation of *why* listed roots are
  skipped (the mechanism is still live) but states that no root is skipped
  today; the `cloudflare-apply.yml` row needs no change, since it describes the
  mechanism generically.
- `zones/mctl-ru/README.md`, `zones/mctl-me/README.md`,
  `zones/mctl-ai/README.md`: replace each "state is local / listed in
  `.local-state-roots`" section with the state key, the imports-only expectation
  (7 / 14 / 26 imports, `0 to add, 0 to change, 0 to destroy`), the fact that
  the import is executed by dispatching `cloudflare-apply.yml` on `main` and
  approving the `cloudflare-apply` environment rather than from a laptop, and
  the post-import `No changes.` verification. Note the intended apply order
  `mctl-ru` -> `mctl-me` -> `mctl-ai` and the window in which drift reports
  pending imports. Re-frame the `tofu state rm` reversibility note in
  `zones/mctl-ru/README.md` as an operation on shared remote state, and drop the
  "Running the pilot" framing, which describes a throwaway state file that no
  longer exists.

**What the pull request can prove by itself.** `cloudflare-plan.yml` will, for
each migrated root: `tofu fmt -check`, `tofu init -lockfile=readonly` against
R2, assert the resolved backend is `s3` (now via the unlisted branch), validate,
plan with the read-only credentials, and publish an
`| import | create | update | destroy |` table. Against an empty-but-real remote
state key that table reads `| 7 | 0 | 0 | 0 |`, `| 14 | 0 | 0 | 0 |` and
`| 26 | 0 | 0 | 0 |`. Those three plans are the pull-request evidence; anything
non-zero outside the import column means out-of-band drift and stops the merge.
`No changes` is only reachable after the state objects exist, which is `#1281`.

## Alternatives

**Three pull requests, one per root, each merged and applied before the next.**
This is what the issue's scope item 1 and the superseded proposal describe, and
it is what the DevLoop boundary of 2026-09-19 explicitly rules out ("one pull
request covering all three zone roots ... Not a sequence of per-root PRs"). It
also buys less than it looks: the risky step is the apply, which happens
post-merge in either shape, and the ordering can be preserved as apply order.
Its one real advantage — the guard self-test keeps a genuinely listed root for
two of the three pull requests — is worth less than the fixture tree the file
itself asks for, which is robust to the list being empty forever.

**Keep the roots on `.local-state-roots` until the applies have run, then delist
in a follow-up.** This would avoid the drift-reports-imports window. It cannot
work: `cloudflare-plan.yml`'s "Assert remote backend" step fails a listed root
whose init resolved a non-local backend, by design and with a message naming
exactly this migration. The gate was built to refuse the half-migrated state.

**Migrate the existing local state with `tofu init -migrate-state` instead of
re-importing.** Rejected because there is no authoritative local state to
migrate: every root's README describes its state file as throwaway, produced on
whoever's laptop ran the import last, and `-migrate-state` would promote an
unreviewed lineage into the shared bucket. Re-importing into an empty key
reproduces state from Cloudflare itself, which is the only source worth
trusting, and it is the path both the plan job and the apply job already
support.

**Delete `.local-state-roots` now that it is empty.** Rejected: four consumers
read it, the helper treats an empty list as the normal end state, and the header
prose is the only place the "a listed root is a visible gap, not a style" rule is
written down. An absent file also silently turns the plan guard's
excuses-nothing check into a no-op. Keeping an entry-free file with its comments
costs nothing and keeps the next exception cheap to declare.

## Platform impact

**Migrations.** No Kubernetes, Helm or ArgoCD surface is touched; nothing in
`platform-gitops/` changes. The state migration is a new R2 object per root,
created by the post-merge import-only apply, not by this pull request.

**Backward compatibility.** Cloudflare configuration is unchanged — no resource
or `import` block is edited, so no DNS record, ruleset, email-routing rule or
zone setting can move as a result of merging. A local operator with a leftover
`terraform.tfstate` in one of the zone roots will be prompted by `tofu init` to
migrate it; the READMEs will say to work from a clean checkout and let the
import rebuild state from Cloudflare instead.

**Resource impact.** Three additional state objects in `mctl-cloudflare-state`
(five total), each a few tens of kilobytes, automatically picked up by the
recursive `opentofu-state-backup.yml` snapshot. Three additional plan jobs per
scheduled drift run, which already exist in the pull-request matrix.

**Risk: the window between merge and the applies.** Until each state object is
written, a `cloudflare-drift.yml` run plans the root against empty remote state,
sees its `import` blocks as changes, exits 2 and reports `DRIFT` with a Telegram
notification. Mitigation: the pull-request body and the root READMEs name the
window and the 06:00 UTC schedule, so `#1281` dispatches the three applies
promptly; the failure is loud, benign and self-clearing, and the alternative
(delisting later) is refused by the plan gate. Nothing in the window can mutate
Cloudflare: drift never applies, and it runs with the read-only credential.

**Risk: a wrong state key silently plans from empty state.** This is the failure
mode `cloudflare-assert-backend.sh` exists for; it derives the expected key from
the root path and also pins bucket, exact endpoint and `use_lockfile`. Deriving
the keys from the root paths as specified above is what keeps that guard quiet
for the right reason.

**Risk: weakening the apply guards while emptying their fixture.** The
`assert-scripts` job runs unconditionally on every pull request, so a broken
self-test blocks the merge rather than sliding through; the risk is a self-test
rewritten to pass vacuously. Mitigation: the fixture tree keeps a paired
`accept` control, and the foreign-cwd `reject` case — the only one that can fail
on the cwd defect — is preserved rather than deleted, as the file demands.

**Risk: the read-only plan credential cannot init the new keys.** Low:
`R2_PLAN_ACCESS_KEY_ID` is Object Read on the whole `mctl-cloudflare-state`
bucket, not a prefix, and the account and portal roots already init against it
on every pull request. A missing object is an empty state, not an error, and
plan never takes the lock (`-lock=false`).

**Security.** No new secret, no new credential scope, no change to the
read/write split. The endpoint and bucket names are already public in this
repository. `use_lockfile = true` brings the zone roots under the same
conditional-write locking guarantee `cloudflare-apply.yml` relies on by never
passing `-lock=false`.
