# Tasks: issue-1178-chore-cloudflare-iac-migrate-the-three-z

- [ ] 1. Verify the apply prerequisites before writing any code — that
  `CF_APPLY_TOKEN_MCTL_RU`, `CF_APPLY_TOKEN_MCTL_ME`, `CF_APPLY_TOKEN_MCTL_AI`,
  `R2_APPLY_ACCESS_KEY_ID` and `R2_APPLY_SECRET_ACCESS_KEY` exist as
  **environment** secrets on `cloudflare-apply`, and that the environment's
  deployment-branch policy is exactly `main`
  (`gh api repos/mctlhq/mctl-gitops/environments/cloudflare-apply/secrets`,
  `.../deployment-branch-policies`) — DoD: all five names present as environment
  secrets and one branch policy named `main`; any gap is reported on the issue
  and blocks task 6 only (tasks 2-5 can still land).

- [ ] 2. PR 1 (`zones/mctl-ru`): add
  `infrastructure/cloudflare/zones/mctl-ru/backend.tf`, copied from
  `infrastructure/cloudflare/account/backend.tf` with
  `key = "cloudflare/zones/mctl-ru/terraform.tfstate"`, and replace the "No
  backend block yet" comment in that root's `versions.tf` with a pointer to
  `backend.tf` — DoD: `tofu fmt -check` clean; the key matches what
  `.github/scripts/cloudflare-assert-backend.sh` derives from the root path;
  `bucket`, endpoint and `use_lockfile = true` identical to the account root.

- [ ] 3. PR 1: remove the `infrastructure/cloudflare/zones/mctl-ru` entry and
  its explanatory comment block from `infrastructure/cloudflare/.local-state-roots`
  (depends on 2, same commit) — DoD: the file keeps its header prose, no longer
  names `mctl-ru`, and `.github/scripts/cloudflare-local-state-roots.sh` prints
  only the two remaining roots and exits 0.

- [ ] 4. PR 1: rebuild the two list-dependent cases in
  `.github/scripts/cloudflare-assert-applyable-root.sh`'s self-test — the
  repo-root "root listed in .local-state-roots" case and the `/tmp`
  "listed root, foreign cwd" case — against a fixture tree (temp dir with
  `.github/scripts/`, a stub root carrying `versions.tf`, and a
  `.local-state-roots` naming it), following the "DO NOT DELETE THE `reject`
  CASE" instruction in that file; keep an `accept` control with an empty fixture
  list (depends on 3) — DoD:
  `CLOUDFLARE_GUARD_SELF_TEST=1 .github/scripts/cloudflare-assert-applyable-root.sh`
  prints `self-test OK` with `mctl-ru` off the list, and the reject case still
  fails if the guard is reverted to resolving the list against the caller's cwd.

- [ ] 5. PR 1: update `infrastructure/cloudflare/zones/mctl-ru/README.md` —
  replace the local-state/"Running the pilot" framing with the remote-state
  procedure, and record the measured import count (the root now carries seven
  import blocks, not the two the README still describes) (depends on 2) —
  DoD: the README states the state key, the expected
  `N to import, 0 to add, 0 to change, 0 to destroy`, and the post-apply
  `No changes.`

- [ ] 6. Merge PR 1, then dispatch `cloudflare-apply.yml` with
  `root: infrastructure/cloudflare/zones/mctl-ru` on `main`, review the plan
  table, approve the `cloudflare-apply` environment, and let the import-only
  apply write the state object (depends on 1, 2, 3, 4, 5) — DoD: the `plan` job
  prints `root '…/zones/mctl-ru' accepted` and
  `backend for '…' is s3://mctl-cloudflare-state/cloudflare/zones/mctl-ru/terraform.tfstate with locking`;
  the applied plan shows imports only, `0` in the create, update and destroy
  columns; `cloudflare/zones/mctl-ru/terraform.tfstate` exists in the bucket.

- [ ] 7. Re-dispatch the `cloudflare-apply.yml` `plan` job for `mctl-ru` and
  capture `No changes.` (depends on 6) — DoD: the summary table reads
  `| 0 | 0 | 0 | 0 |` and the plan output is linked from the PR.

- [ ] 8. PR 2 (`zones/mctl-me`): repeat tasks 2, 3 and 5 for `mctl-me`
  (`key = "cloudflare/zones/mctl-me/terraform.tfstate"`), then repeat 6 and 7
  (depends on 7) — DoD: 14 imports, zero add/change/destroy, post-apply
  `No changes.`, entry gone from `.local-state-roots`.

- [ ] 9. PR 3 (`zones/mctl-ai`): repeat tasks 2, 3 and 5 for `mctl-ai`
  (`key = "cloudflare/zones/mctl-ai/terraform.tfstate"`), then repeat 6 and 7
  (depends on 8) — DoD: 26 imports, zero add/change/destroy, post-apply
  `No changes.`, `.local-state-roots` now holds header comments and no entries,
  and `cloudflare-local-state-roots.sh` prints nothing and exits 0.

- [ ] 10. PR 3: update `infrastructure/cloudflare/README.md` — delete the
  paragraph stating that all three zone roots keep local state, cannot apply
  from CI and therefore had their zone settings applied by hand; reword the
  `cloudflare-plan.yml` and `cloudflare-drift.yml` rows of the workflow table
  that still name `zones/mctl-ru` as listed and describe roots being skipped;
  leave the separate `dmitriimashkov.com` standing exception intact (depends
  on 9) — DoD: no remaining claim in that file that a zone root is on local
  state or that zone settings must be hand-applied; `dmitriimashkov.com` wording
  unchanged.

- [ ] 11. Post the evidence on issue #1178: per-root plan links (import plan,
  applied plan, post-apply `No changes`), the first green scheduled
  `cloudflare-drift.yml` run, the dispatched `cloudflare-apply.yml` plan
  acceptance, and the `opentofu-state-backup.yml` run showing five state objects
  (depends on 10, T5, T6) — DoD: every acceptance-criteria checkbox in the issue
  has a linked artefact.

## Tests

- [ ] T1. Guard self-tests, run locally on each PR branch before pushing:
  `CLOUDFLARE_GUARD_SELF_TEST=1 .github/scripts/cloudflare-assert-applyable-root.sh`
  and `… cloudflare-assert-backend.sh` both print `self-test OK`. The `guards`
  job in `cloudflare-plan.yml` re-runs them on the PR.
- [ ] T2. `cloudflare-plan.yml` on each migration PR: the "Guard root coverage"
  step passes *without* the `cloudflare-root-removal` label, and the migrated
  root's plan job prints `<root> is on the s3 backend`.
- [ ] T3. The migrated root's PR plan is imports-only: the summary table shows
  `0` in create, update and destroy. Any non-zero value stops the migration and
  is investigated as out-of-band drift.
- [ ] T4. Negative control on the key: temporarily point a scratch branch's
  `backend.tf` at a wrong key and confirm
  `cloudflare-assert-backend.sh` rejects it with "backend key is … expected …"
  rather than planning from empty state. Not merged.
- [ ] T5. The first scheduled `cloudflare-drift.yml` run (06:00 UTC) after each
  migration includes the root in its matrix, reports in sync, and emits no
  "this root's state holds no resources" warning.
- [ ] T6. The first scheduled `opentofu-state-backup.yml` run (03:30 UTC) after
  the third migration logs `state objects in source: 5` for
  `mctl-cloudflare-state` and a non-zero copied count.
- [ ] T7. `tofu fmt -check -diff` and `tofu validate` clean in each migrated
  root (also enforced by the plan job).
- [ ] T8. `cloudflare-apply.yml` acceptance is verified by a dispatched `plan`
  job per root, which is the acceptance criterion the issue names; it is the
  same dispatch used in task 6 before approval.

## Rollback

- **Before any apply (state object does not exist yet):** revert the PR. The
  root goes back on `.local-state-roots`, drift skips it again, apply refuses it
  again, and nothing in Cloudflare or R2 has changed. If the revert lands after
  the entry was removed but the `backend.tf` stays (or vice versa), the plan job
  fails closed on the listed-root/resolved-backend mismatch — fix by reverting
  both halves, since they were one commit.
- **After the import-only apply:** Cloudflare is still untouched, so rollback is
  only about ownership. Reverting the PR restores the exception entry and
  leaves an orphan state object in R2; that object is harmless (nothing reads a
  listed root's state), and may be deleted with the `R2_APPLY_*` credential if
  the orphan is unwanted. Guard self-test fixtures reverted with it.
- **Bad or corrupted state written:** the apply held the lock and R2 writes are
  atomic, so a torn object is not a failure mode. For a wrong one, follow
  `docs/runbooks/opentofu-state-restore.md`; if the failure is the *first*
  import (no prior snapshot of that key exists), delete the object and re-run
  the import apply instead of restoring.
- **Unexpected Cloudflare mutation:** the destroy guard refuses an unrequested
  destroy before approval and again before apply, so this should be unreachable;
  if it happens, `tofu state rm` the affected addresses, re-read the objects
  through the API and compare `modified_on` — the reversibility check already
  documented in `zones/mctl-ru/README.md`.
