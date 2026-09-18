# Design: issue-1178-chore-cloudflare-iac-migrate-the-three-z

## Current state

**Roots and how they are found.** Both `cloudflare-plan.yml` and
`cloudflare-drift.yml` discover roots by walking `infrastructure/cloudflare`
for `versions.tf` / `versions.tf.json`, pruning `modules/`. That yields five
roots today: `account`, `portal`, `zones/mctl-ru`, `zones/mctl-me`,
`zones/mctl-ai`.

**Backends.** `infrastructure/cloudflare/account/backend.tf` and
`infrastructure/cloudflare/portal/backend.tf` are byte-identical apart from
`key`: `backend "s3"` against
`https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com`, bucket
`mctl-cloudflare-state`, `key = "cloudflare/<root-relative-path>/terraform.tfstate"`,
`use_lockfile = true`, plus the five `skip_*`/`use_path_style` flags R2 needs.
The three zone roots have **no `backend.tf`**; each `versions.tf` carries a
comment ("No backend block yet…"), and all three are listed in
`infrastructure/cloudflare/.local-state-roots`.

**The exception list.** `.github/scripts/cloudflare-local-state-roots.sh`
normalises that file (strips CR and comments, prefixes `infrastructure/cloudflare/`)
and is read by three places:

- `cloudflare-drift.yml` → discovery excludes listed roots, and *errors* if a
  listed entry names no discovered root;
- `cloudflare-plan.yml` → the "Guard root coverage" step exempts listed roots
  from the `backend.tf`-must-exist rule and errors on a stale entry; the plan
  job's "Assert remote backend" step **fails a listed root whose `tofu init`
  resolved anything other than `local`** ("remove the entry so drift watches it
  again");
- `.github/scripts/cloudflare-assert-applyable-root.sh` → refuses a listed root
  outright, which is what `cloudflare-apply.yml` calls in both its `plan` and
  `apply` jobs.

**Credentials.** Plan and drift run with `R2_PLAN_*` (Object Read only on
`mctl-cloudflare-state`) and therefore pass `-lock=false`; they cannot write a
state object or even a lock. `cloudflare-apply.yml`'s `apply` job runs on the
`cloudflare-apply` environment with `R2_APPLY_*` (read & write) and a per-root
Cloudflare write token — the chain already maps
`CF_APPLY_TOKEN_MCTL_RU` / `_ME` / `_AI`, and a root with no mapping is refused
("the mapping is the allowlist"). It never passes `-lock=false`.

**Imports.** Each zone root has an `import.tf` of declarative `import` blocks:
7 for `mctl-ru`, 14 for `mctl-me`, 26 for `mctl-ai` (matching the figures the
`mctl-me` and `mctl-ai` READMEs record; `mctl-ru`'s README still describes the
original 2-record pilot). Import blocks are previewed by a plan and executed by
an apply, as `zones/mctl-ru/README.md` spells out. Zone settings
(`min_tls_version`, `always_use_https`, `ssl`) were applied through the API by
hand first and then import-pinned, precisely because these roots cannot apply.

**Backup.** `opentofu-state-backup.yml` syncs `s3://mctl-cloudflare-state/`
with `--include '*.tfstate' --include '*.tfstate.backup'`, excluding
`_backups/`. It is key-agnostic: new state objects are picked up with no
workflow change, and the job's source/copied counts are the observable.

**The chicken and egg.** A zone root's remote state object can only be created
by a job holding `R2_APPLY_*` — i.e. `cloudflare-apply.yml`'s `apply` job — and
that job refuses the root while it is on `.local-state-roots`. Meanwhile the
plan job refuses a *listed* root that resolved `s3`. So the only legal ordering
is: backend declared **and** entry removed in one commit, then dispatch apply on
`main`.

## Proposed solution

Three sequential pull requests, one per root, in the issue's order
(`mctl-ru` → `mctl-me` → `mctl-ai`). Each PR is the same shape.

**1. Add `infrastructure/cloudflare/zones/<zone>/backend.tf`.** Copied from
`account/backend.tf`, comments included, with
`key = "cloudflare/zones/<zone>/terraform.tfstate"`. It must be a file literally
named `backend.tf`: the coverage guard tests `grep -qxF -- "$r/backend.tf"`
against the committed tree, so a backend block inside `versions.tf` would fail
the check even though OpenTofu would accept it. The key must match exactly what
`cloudflare-assert-backend.sh` derives from the root path — the script builds
`cloudflare/${ROOT#infrastructure/cloudflare/}/terraform.tfstate` itself, so a
typo is a failure rather than an empty state.

**2. Replace the "No backend block yet" comment in `versions.tf`** with a
one-line pointer to `backend.tf`. The comment is currently the only in-repo
statement of why the root is on local state, and leaving it would be the exact
"comment that contradicts the live configuration" the guards are written
against.

**3. Remove the root's entry (and its explanatory comment block) from
`.local-state-roots`** in the *same* commit. Splitting this out is not possible:
a listed root resolving `s3` fails the plan job by design. After the third PR
the file keeps its header comments and holds no entries —
`cloudflare-local-state-roots.sh` was written for exactly this end state (`awk
'NF'` rather than `grep -v`, so an empty list still exits 0), and drift/plan
tolerate an empty or absent list.

**4. Repair the applyable-root self-test, in the first PR.**
`cloudflare-assert-applyable-root.sh`'s `CLOUDFLARE_GUARD_SELF_TEST` suite
asserts `reject` for `infrastructure/cloudflare/zones/mctl-ru` twice — once from
the repo root ("root listed in .local-state-roots") and once from `/tmp`
("listed root, foreign cwd"), the latter carrying a "DO NOT DELETE THE `reject`
CASE" note explaining it is the only case that can fail on the cwd defect.
Removing `mctl-ru` from the list makes both cases fail, and with them the
`guards` self-test job in `cloudflare-plan.yml`. Fix as that comment
prescribes: build a fixture tree (same pattern as the existing failing-helper
fixture — a temp dir with `.github/scripts/`, a stub root carrying
`versions.tf`, and a `.local-state-roots` naming that root), run the guard copy
from `/tmp`, and assert `reject`; keep a paired `accept` control with an empty
fixture list. The non-canonical-spelling cases (`…/mctl-ru/`, `/.`, `//`) reject
on the canonical-form arm regardless of the list and can stay as they are.
`cloudflare-assert-backend.sh`'s suite needs no change — its `mctl-me` fixture
already asserts that a nested zone key is accepted.

**5. Update the root README** with the measured plan: the import count, the
post-apply `No changes`, and the removal of the "keeps local state / verified
with the read-only plan identity" framing.

**6. After merge, dispatch `cloudflare-apply.yml` for the root.** Its `plan` job
(read-only credentials, `-lock=false`) publishes `| N | 0 | 0 | 0 |` — imports
only — plus the plan digest; a reviewer approves on the `cloudflare-apply`
environment; the `apply` job re-plans with the write identity, refuses if the
digest moved, takes the state lock and applies. The applied plan performs
imports only, so no Cloudflare API write happens; what it produces is the state
object at `cloudflare/zones/<zone>/terraform.tfstate`. Then re-dispatch the plan
(or let drift run) to prove `No changes`.

**7. Final PR also updates `infrastructure/cloudflare/README.md`:** the zone-settings
paragraph that says all three roots keep local state, cannot apply from CI, and
so had their settings applied by hand; the `cloudflare-plan.yml` row in the
workflow table that still names `zones/mctl-ru` as the listed root "whose
migration belongs to #1103"; and the `cloudflare-drift.yml` row's implication
that roots are being skipped. The separate `dmitriimashkov.com` standing
exception stays — that zone has no root and is unaffected.

**Local execution note.** Anyone reproducing this on a workstation must not let
`tofu init` migrate the throwaway local state into R2. Delete
`terraform.tfstate*` and `.terraform/` in the root first and init clean (or
`-reconfigure`), never `-migrate-state`: the local state is a discardable
artefact of the zero-diff proof, its provenance was never reviewed, and pushing
it would make the R2 object unauditable. CI is unaffected — it checks out fresh
and points `TF_DATA_DIR` at `RUNNER_TEMP`.

**Ordering against the drift schedule.** Between merge and the import apply, the
root is discovered by drift with an empty remote state, so the 06:00 UTC run
would plan "N to import", exit 2, go red and notify. Land each PR and run its
apply in the same working window; if the window is missed, the red run is
expected and self-clearing, and it should be annotated rather than silenced.

## Alternatives

- **Two PRs per root — declare the backend first, remove the list entry
  later.** Rejected because it is impossible by construction: the plan job's
  "Assert remote backend" step fails a root that is listed *and* resolved a
  non-local backend, with the message "remove the entry so drift watches it
  again". The guard was written to force exactly the single-commit shape.
- **Seed the R2 objects from a workstation using the apply credential
  (`tofu init` + `tofu apply` locally, or `tofu state push` of the existing
  throwaway state).** Rejected: it moves a read-write state credential onto a
  laptop, produces a state object with no reviewed plan and no digest behind it,
  and `state push` would enshrine state whose provenance nobody reviewed. The
  approval gate in `cloudflare-apply.yml` exists for this exact write.
- **One PR for all three roots.** Acceptable per the issue and cheaper in
  review, but it couples three separate state seedings to one merge: any root
  whose plan is not clean blocks the other two, and the window between merge and
  three separate apply dispatches is when drift is red for everything. Kept as a
  fallback, not the default.
- **Leave the roots on local state and only widen drift to plan them
  read-only.** Rejected: with no state object a plan proposes importing
  everything, which is the nightly false alarm `.local-state-roots` was created
  to stop. It is the status quo with extra noise.
- **Delete `.local-state-roots` once empty.** Rejected: the file's header
  documents the mechanism, all three consumers treat an empty list as normal,
  and the next root imported before its backend exists will need the list again.

## Platform impact

- **Cloudflare objects: unchanged.** Every applied plan is imports-only. Any
  add/change/destroy line means live configuration has moved since the
  import-pinning of #1142 / #1154 / #1168 and is a stop-and-investigate signal,
  not something to apply through.
- **State:** three new objects under `mctl-cloudflare-state`
  (`cloudflare/zones/mctl-{ru,me,ai}/terraform.tfstate`), each with its own
  `use_lockfile` lock. No key collides with `account` or `portal`.
- **Backup:** `opentofu-state-backup.yml` needs no edit — it syncs the whole
  bucket by glob. Its logged "state objects in source" rises from 2 to 5, which
  is the verification for that acceptance criterion.
- **Drift:** the matrix grows from 2 to 5 Cloudflare roots (plus per-root
  concurrency groups). Runtime cost is three more short plans a night; the
  Telegram notifier now covers the zones that carry live traffic.
- **Credentials:** no new secrets. The apply-token chain already names the three
  zone tokens; if any is absent as a `cloudflare-apply` **environment** secret
  the dispatch fails with "no write token is mapped", which is a blocked task,
  not a silent skip. Verify with
  `gh api repos/mctlhq/mctl-gitops/environments/cloudflare-apply/secrets` first.
- **Risk — drift red between merge and apply.** Mitigation: merge and apply in
  one window; the failure is loud, closed and self-clearing.
- **Risk — a bad or partial state write.** Mitigation: the lock is held by the
  apply, R2 object writes are atomic, and the nightly `_backups/` snapshot plus
  `docs/runbooks/opentofu-state-restore.md` cover recovery. Note the snapshot
  taken *before* the first successful apply contains no object for these keys,
  so the true recovery path for a botched first import is to remove the key and
  re-import, not to restore.
- **Risk — the guard self-test breaking on the first PR.** Mitigation: the
  fixture rewrite ships in that same PR and is verified locally with
  `CLOUDFLARE_GUARD_SELF_TEST=1` before pushing; the `guards` job in
  `cloudflare-plan.yml` re-runs it on every pull request.
- **Backward compatibility:** the exception mechanism, the guards and both
  workflows keep working with an empty list; no consumer of
  `.local-state-roots` is removed, so a future root can be excepted again.
