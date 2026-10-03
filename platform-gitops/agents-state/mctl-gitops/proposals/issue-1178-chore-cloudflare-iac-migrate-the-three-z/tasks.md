# Tasks: issue-1178-chore-cloudflare-iac-migrate-the-three-z

Scope: one pull request in `mctlhq/mctl-gitops`, covering all three zone roots.
Every task below is completable inside that pull request. The import-only apply
per root, the post-apply `No changes` proof, the scheduled drift evidence and the
backup evidence are `mctlhq/mctl-gitops#1281` and are deliberately not tasks
here.

- [ ] 1. Add `infrastructure/cloudflare/zones/mctl-ru/backend.tf`, copied from
  `infrastructure/cloudflare/account/backend.tf` with
  `key = "cloudflare/zones/mctl-ru/terraform.tfstate"` — DoD: bucket
  `mctl-cloudflare-state`, endpoint
  `https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com`,
  `region = "auto"`, `use_lockfile = true`, the four `skip_*` flags and
  `use_path_style = true` are identical to the account root; the key equals what
  `.github/scripts/cloudflare-assert-backend.sh` derives from the root path;
  `tofu fmt -check -diff` is clean in that directory.

- [ ] 2. Add `infrastructure/cloudflare/zones/mctl-me/backend.tf` with
  `key = "cloudflare/zones/mctl-me/terraform.tfstate"` (same shape as 1) —
  DoD: as task 1, for `mctl-me`.

- [ ] 3. Add `infrastructure/cloudflare/zones/mctl-ai/backend.tf` with
  `key = "cloudflare/zones/mctl-ai/terraform.tfstate"` (same shape as 1) —
  DoD: as task 1, for `mctl-ai`.

- [ ] 4. Delete the "No backend block yet" comment at the end of the `terraform`
  block in `zones/mctl-ru/versions.tf`, `zones/mctl-me/versions.tf` and
  `zones/mctl-ai/versions.tf`, replacing each with a one-line pointer to
  `backend.tf` (depends on 1, 2, 3) — DoD: no file under
  `infrastructure/cloudflare/zones/` still claims the root has no backend or
  keeps local state; `required_providers` and the `provider "cloudflare" {}`
  block are untouched, so each root's committed `.terraform.lock.hcl` stays
  valid under `tofu init -lockfile=readonly`.

- [ ] 5. Remove the three root entries and their per-root prose blocks from
  `infrastructure/cloudflare/.local-state-roots`, keeping the header prose that
  explains the mechanism and which guards read it, and add one line recording
  that the list is empty as of #1178 (depends on 1, 2, 3 — must be the same
  commit, since `cloudflare-plan.yml` fails a root that resolved `s3` while
  still listed and fails a delisted root with no `backend.tf`) — DoD:
  `.github/scripts/cloudflare-local-state-roots.sh` run against the edited file
  prints nothing and exits 0; the file still contains its explanatory header.

- [ ] 6. Rebuild the two list-dependent cases in
  `.github/scripts/cloudflare-assert-applyable-root.sh`'s self-test against a
  fixture tree, as that file's "DO NOT DELETE THE `reject` CASE WHEN
  .local-state-roots EMPTIES" comment instructs: a `mktemp -d` tree holding
  `.github/scripts/` with copies of the guard **and** the real
  `cloudflare-local-state-roots.sh`, a stub root with `versions.tf`, and a
  `.local-state-roots` naming that stub; assert `reject` for the listed stub from
  the fixture tree, `reject` for it from a foreign cwd (`/tmp`), and `accept` for
  it with an empty fixture list as the control (depends on 5) — DoD:
  `CLOUDFLARE_GUARD_SELF_TEST=1 .github/scripts/cloudflare-assert-applyable-root.sh`
  prints `self-test OK` with no root listed in the real tree; the new fixture is
  cleaned by the file's single existing `trap cleanup EXIT` handler (no second
  EXIT trap); the foreign-cwd `reject` case still fails if the guard is reverted
  to resolving the list path against the caller's cwd.

- [ ] 7. Reword the three non-canonical `mctl-ru` self-test case labels in the
  same file so they attribute the rejection to the canonical-form arm rather
  than to the list (depends on 6) — DoD: the cases still run and still reject;
  no label claims a rejection comes from `.local-state-roots` when the list is
  empty.

- [ ] 8. Update `infrastructure/cloudflare/zones/mctl-ru/README.md`: replace the
  local-state / "Running the pilot" framing with the remote-state procedure —
  state key `cloudflare/zones/mctl-ru/terraform.tfstate`, the expected
  `7 to import, 0 to add, 0 to change, 0 to destroy`, that the import is executed
  by dispatching `cloudflare-apply.yml` on `main` and approving the
  `cloudflare-apply` environment, and the post-import `No changes.` verification;
  re-frame the `tofu state rm` reversibility note as an operation on shared
  remote state (depends on 1, 4) — DoD: the README no longer says the root keeps
  local state, is listed in `.local-state-roots`, or cannot apply from CI, and
  the import count matches `grep -c '^import {' import.tf`.

- [ ] 9. Update `infrastructure/cloudflare/zones/mctl-me/README.md` the same way,
  with `cloudflare/zones/mctl-me/terraform.tfstate` and
  `14 to import, 0 to add, 0 to change, 0 to destroy` (depends on 2, 4) — DoD:
  as task 8, for `mctl-me`.

- [ ] 10. Update `infrastructure/cloudflare/zones/mctl-ai/README.md` the same
  way, with `cloudflare/zones/mctl-ai/terraform.tfstate` and
  `26 to import, 0 to add, 0 to change, 0 to destroy` (depends on 3, 4) — DoD:
  as task 8, for `mctl-ai`.

- [ ] 11. In each of the three root READMEs, record the intended apply order
  (`mctl-ru` -> `mctl-me` -> `mctl-ai`) and the window between merge and the
  applies, in which a 06:00 UTC `cloudflare-drift.yml` run plans the root's
  pending imports and therefore reports `DRIFT` (depends on 8, 9, 10) — DoD:
  each README names the window, says it clears as soon as that root's import
  apply has run, and states that drift never writes to Cloudflare.

- [ ] 12. Update the "Zone settings" section of
  `infrastructure/cloudflare/README.md`: rewrite the API-first paragraph as
  history and remove the claim that all three zone roots keep local state and
  cannot apply from CI; state that a zone-setting change is now a plan reviewed
  through `cloudflare-apply.yml`. Leave the separate `dmitriimashkov.com`
  "standing exception" paragraph (the zone with no root, decision 10) exactly as
  it is (depends on 5) — DoD: no remaining claim in that file that a zone root is
  on local state or that zone settings must be hand-applied and import-pinned;
  the `dmitriimashkov.com` wording is byte-identical to before.

- [ ] 13. Update the workflow table in `infrastructure/cloudflare/README.md`: the
  `cloudflare-plan.yml` row stops naming `zones/mctl-ru` as the listed root and
  stops citing #1103 as the owner of its migration, and the
  `cloudflare-drift.yml` row keeps the explanation of why a listed root is
  skipped while stating that no root is skipped today (depends on 5) — DoD:
  `grep -rn 'mctl-ru' infrastructure/cloudflare/README.md` shows no claim that
  the root is on local state or awaiting migration; the mechanism description
  survives.

- [ ] 14. Write the pull-request body: link the three `cloudflare-plan.yml`
  per-root plan summaries (each showing its imports-only table), state that
  `No changes` is only reachable after the import-only applies and point at
  `mctlhq/mctl-gitops#1281` for those, for the scheduled drift evidence, for the
  dispatched `cloudflare-apply.yml` `plan` acceptance and for the backup
  evidence, and note that `opentofu-state-backup.yml` needs no change because it
  snapshots the bucket recursively with `--include '*.tfstate'` (depends on all
  above) — DoD: every acceptance criterion in issue #1178 is either evidenced in
  the body or explicitly attributed to #1281.

## Tests

- [ ] T1. `CLOUDFLARE_GUARD_SELF_TEST=1
  .github/scripts/cloudflare-assert-applyable-root.sh` and
  `CLOUDFLARE_GUARD_SELF_TEST=1 .github/scripts/cloudflare-assert-backend.sh`
  both print `self-test OK` on the branch. `cloudflare-plan.yml`'s
  `assert-scripts` job re-runs both unconditionally on the pull request.
- [ ] T2. `.github/scripts/cloudflare-local-state-roots.sh
  infrastructure/cloudflare/.local-state-roots` prints nothing and exits 0
  (checked with `echo $?`, since the empty-list-exits-0 property is the one the
  helper's `awk 'NF'` exists to guarantee).
- [ ] T3. `tofu fmt -check -diff` and `tofu validate` are clean in all three
  migrated roots; also enforced by the plan job.
- [ ] T4. `cloudflare-plan.yml` on the pull request: the `Guard root coverage`
  step passes **without** the `cloudflare-root-removal` label, and each migrated
  root's plan job prints `<root> is on the s3 backend` rather than the
  "on local state by exception" warning.
- [ ] T5. Each migrated root's plan summary table is imports-only:
  `| 7 | 0 | 0 | 0 |`, `| 14 | 0 | 0 | 0 |`, `| 26 | 0 | 0 | 0 |`. Any non-zero
  create, update or destroy stops the merge and is investigated as out-of-band
  drift before anything else happens.
- [ ] T6. Negative control, on a scratch branch that is never merged: point one
  `backend.tf` at a wrong key and confirm the plan job fails with
  `backend key is ... expected ...` instead of planning from empty state; then
  restore the entry in `.local-state-roots` while keeping `backend.tf` and
  confirm the plan job fails with `resolved the 's3' backend but is still listed
  in .local-state-roots`. Both are the gates this change relies on.
- [ ] T7. Grep assertion over the tree: no file under `infrastructure/cloudflare`
  still asserts that a zone root keeps local state, is listed in
  `.local-state-roots`, or cannot apply from CI, and the
  `dmitriimashkov.com` standing-exception paragraph is unchanged
  (`git diff` on that hunk is empty).

## Rollback

- **Before the merge.** Nothing outside the branch has changed; close the pull
  request. Cloudflare and R2 are untouched at every point in this task list, and
  no task writes state.
- **After the merge, before any import-only apply.** `git revert` the merge
  commit. The three roots go back on `.local-state-roots`, drift skips them
  again, `cloudflare-apply.yml` refuses them again, and no state object was ever
  created. Revert the whole commit, not a half of it: a tree with `backend.tf`
  but no list entry — or the reverse — fails the plan gate by design.
- **If a drift run goes red in the window before the applies.** Expected, not a
  regression: the run reports pending imports for the migrated roots and never
  writes. Either let `#1281` dispatch the import-only applies, which clears it,
  or revert as above.
- **After an import-only apply has written a state object (already `#1281`
  territory).** Cloudflare is still unmutated — an import writes state only — so
  rollback is about ownership. Reverting this pull request leaves an orphan state
  key that nothing reads; it can be deleted with the writable R2 credential if
  unwanted. For a bad or corrupted state object follow
  `docs/runbooks/opentofu-state-restore.md`; if no snapshot of that key exists
  yet (its first write), delete the object and re-run the import apply rather
  than restoring.
- **Guard regressions.** If the rebuilt self-test turns out to pass vacuously,
  revert task 6's hunk and reinstate the list-based cases together with one
  entry in `.local-state-roots`; that pair is self-consistent and fails closed,
  at the price of one root staying unwatched.
