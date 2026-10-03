# Tasks: proposal-backlog-consolidation

- [ ] 1. Audit all 29 candidate slugs (10 go-upgrade, 8 pgx, 8 mcp-go, 3 unmerged chi + 1
      already-merged chi) and record, per slug: existing `.status.yaml` state (if any) and
      targeted fix version/CVE list. — DoD: a table (in the PR description or an internal
      note) listing all 29+1 slugs with status and target version, matching the counts and
      corrections documented in `requirements.md`'s Context section.
- [ ] 2. Confirm the two already-merged slugs (`chi-security-patch`,
      `pgx-sqli-cve-2025-54236`) require no further action beyond excluding them from the
      duplicate count (depends on 1) — DoD: both confirmed `status: merged` in the audit
      table, explicitly marked "no action."
- [ ] 3. Confirm canonical selection for the pgx family
      (`pgx-critical-memory-safety-cve-v2`, targets v5.11.0) and the mcp-go family
      (`mcp-go-upgrade-v3`, targets v1.1.0) per this cycle's inbox designation (depends on 1)
      — DoD: both canonicals re-verified as targeting the current latest upstream release as
      of 2026-09-26.
- [ ] 4. Confirm canonical selection for the go-upgrade family
      (`go-1.24-eol-unpatched-cve`, targets Go >=1.26.4, prefers 1.27.x) (depends on 1) — DoD:
      re-verified as the highest-target, most-recent, self-declared-superseding proposal among
      the 10 go-upgrade slugs.
- [ ] 5. Recommend canonical selection for the chi family (`chi-upgrade-v525`) and flag it
      explicitly as needing human/analyst confirmation, since all 3 unmerged chi candidates
      target an identical version (depends on 1) — DoD: recommendation and flag recorded in
      the PR description, not silently treated as final.
- [ ] 6. Write a `.status.yaml` with `status: superseded` and a `superseded_by: <canonical
      slug>` field for each non-canonical, unmerged slug in the four families (9 go-upgrade +
      6 pgx + 7 mcp-go + 2 chi = 24 files) (depends on 2, 3, 4, 5) — DoD: every non-canonical
      slug's directory contains a `.status.yaml` with this shape, and its existing
      `requirements.md`/`design.md`/`tasks.md` files are left byte-for-byte unchanged.
- [ ] 7. Post a summary comment/report listing the final state: 1 open canonical proposal per
      family (4 total), 24 newly-marked-superseded, 2 already-merged (unchanged), for a human
      reviewer to action (depends on 6) — DoD: summary produced and available to the next
      orchestrator/analyst cycle so it isn't re-derived from scratch.

## Tests
- [ ] T1. Spot-check: for each of the 4 canonical slugs, confirm its `requirements.md` target
      version matches or exceeds every non-canonical sibling's target version in the same
      family (except chi, which is flagged as a tie).
- [ ] T2. Verify no `.status.yaml` was added to any of the 4 canonical slugs themselves (they
      remain open/unmarked, ready for `status: accepted`).
- [ ] T3. Verify no existing `requirements.md`, `design.md`, or `tasks.md` file content was
      modified for any of the 24 superseded slugs — only new `.status.yaml` files were added.
- [ ] T4. Confirm the two already-merged slugs' existing `.status.yaml` files were read but
      not overwritten.

## Rollback
If a `superseded` marking turns out to be wrong (e.g. a "superseded" proposal actually had
unique scope the canonical one lacks), the rollback is to delete that slug's `.status.yaml`
file, restoring it to its original open/unmarked state — no other file was touched, so this is
a single-file revert per affected slug. Because no `mctl-api` code or deployment is touched by
this proposal, there is no service-level rollback path needed; the only "system" being changed
is proposal metadata in the gitops-backed `proposals/` directory, which is itself
version-controlled and revertible via a normal git revert of the consolidation commit.
