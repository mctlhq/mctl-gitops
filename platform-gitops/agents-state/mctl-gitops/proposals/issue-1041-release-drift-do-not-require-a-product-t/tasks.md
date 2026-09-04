# Tasks: issue-1041-release-drift-do-not-require-a-product-t

- [ ] 1. Add `is_metadata_path()` to `.github/scripts/release-drift.sh`
      (near `is_release_tag`/`is_releasable_subject`, before
      `unreleased_from_compare`): a `case`-based predicate returning true
      only for `.github/*` (any depth) and the exact literal `CLAUDE.md`. —
      DoD: function exists, matches the allowlist in design.md exactly, no
      other paths (`docs/**`, `README*`, `*.md` generally) match.

- [ ] 2. Add `is_metadata_only_diff()` (depends on 1), placed directly after
      `unreleased_from_compare()`: reads a compare-JSON payload from stdin,
      extracts `.files[]?.filename` via `jq`, returns success iff at least
      one path was seen and every seen path passes `is_metadata_path`; an
      empty/absent `files` list returns failure (fail-safe, not
      metadata-only). — DoD: function exists with the doc-comment style of
      neighboring functions explaining the fail-safe-on-empty behavior.

- [ ] 3. Wire the gate into `check_image()` (depends on 2): reuse the
      already-fetched `$cmp` payload; when `count > 0` and the lag threshold
      is exceeded, call `is_metadata_only_diff <<<"$cmp"` before appending
      `UNRELEASED_*` to `verdict`; on true, set
      `metadata_note="ok: metadata-only changes (${count} commits since ${oldest})"`
      instead, and change the final `printf`'s verdict fallback from
      `"${verdict:-ok}"` to `"${verdict:-${metadata_note:-ok}}"` so
      `RELEASE_PLEASE_FAILED`/`NOT_DEPLOYED_*` still take priority over the
      metadata note when both apply. — DoD: no new `gh api` call added;
      `RELEASE_PLEASE_FAILED` and `NOT_DEPLOYED_*` computation and output
      untouched; `count`/`oldest` still reported in the TSV exactly as
      today regardless of suppression.

- [ ] 4. Update `report()`'s pass/fail matcher (depends on 3): change
      `case "$verdict" in ok|skip:*) ;; *) failed=1; ...; esac` to
      `case "$verdict" in ok|ok:*|skip:*) ;; *) failed=1; ...; esac` so the
      new `ok: metadata-only changes (...)` string does not trip
      `failed=1`/`::error::`. — DoD: grep confirms exactly one `case
      "$verdict"` site in the file and it now includes `ok:*`.

- [ ] 5. Extend `self_test()` (depends on 1, 2) with new assertions
      following the existing inline-fixture style: (a) `is_metadata_path`
      true/false table covering `.github/workflows/x.yml`, `CLAUDE.md`,
      `docs/api/index.md`, `README.md`, `src/app.py`; (b)
      `is_metadata_only_diff` true for a `files` list containing only
      `.github/workflows/claude-review.yml` + `CLAUDE.md`; false for the
      same list plus `src/app.py`; false for `{"files":[]}` and for a
      payload with no `files` key at all. — DoD: `./.github/scripts/release-drift.sh
      --self-test` exits 0 and prints `self-test: ok`; each new assertion
      fails loudly (matching the file's existing `self-test: '...' should
      ...` message style) if run against the pre-change script.

## Tests
- [ ] T1. `./.github/scripts/release-drift.sh --self-test` passes locally
      (`jq`, `awk`, `date` available; no `gh` needed for this step).
- [ ] T2. Regression: temporarily revert step 3's gate (i.e. always append
      `UNRELEASED_*` when `count > 0`, ignoring `is_metadata_only_diff`) and
      confirm the new self-test assertion from step 5(b) — the
      "`.github/**` + `CLAUDE.md` only" fixture — fails. This is the check
      that step 5's tests actually exercise the suppression path and would
      catch its removal, per the issue's mutation-testing acceptance
      criterion. Revert the temporary change afterward; it is a
      verification step, not a permanent change.
- [ ] T3. Manual/CI verification against live data (post-merge, via
      `workflow_dispatch` on `release-drift.yml`, since the four named
      services live in other repos not reachable from this sandboxed
      script run): confirm `mctl-loyalty`, `mctl-pairdesk`, and
      `pfeifenpatenschaft-backend` report `ok: metadata-only changes (...)`
      instead of `UNRELEASED_*`, and that `mctl-docs` still reports its
      `UNRELEASED_*` verdict unchanged.
- [ ] T4. Manual construction of a "one runtime file added" variant of the
      `mctl-loyalty`-style fixture (e.g. append a `src/`-path entry to the
      step-5(b) JSON fixture) and confirm `is_metadata_only_diff` returns
      false for it, matching the issue's "adding one runtime file makes it
      red" acceptance criterion at the unit level.

## Rollback
Single-file change (`.github/scripts/release-drift.sh`) plus its workflow
wrapper is untouched. To roll back: revert the commit. There is no
migration, deployed state, secret, or schema to unwind -- `release-drift.yml`
runs as a stateless daily read-only check with `permissions: contents:
read` and a short-lived App token; a bad revision only affects the report
markdown in `$GITHUB_STEP_SUMMARY` and the workflow's exit code, not any
tenant's live services (this script never writes to `values.yaml` or
triggers deploys). If a rollback is needed mid-day before the next
scheduled run, trigger `workflow_dispatch` manually after reverting to
regenerate a correct report immediately rather than waiting for `17 7 * *
*` UTC.
