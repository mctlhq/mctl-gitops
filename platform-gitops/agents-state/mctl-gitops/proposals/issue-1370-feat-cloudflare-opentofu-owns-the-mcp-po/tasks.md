# Tasks: issue-1370-feat-cloudflare-opentofu-owns-the-mcp-po

> **Slice 1 — the only slice this implementer run does (2026-09-25).** Implement
> **PR A: tasks 1-5, plus T1 and T7**, as one PR, and stop. Do not start PR B
> or anything after it; each later PR is its own run once the previous one has
> merged. The first attempt (2026-09-24) stopped with no commits for two
> reasons, both fixed here: the whole sequence was too large for one run, and
> task 2 needs live values it had no credential to read. Those values are now
> committed next to this file as `live-snapshot-2026-09-25.json`: take
> `default_disabled`, `on_behalf` and `updated_prompts` for `mapping.json`
> (task 2) and the per-server counts for `baseline.json` (task 3) from it, and
> read no other source for them. Record in the PR body that they came from
> that snapshot.

Four PRs in mctl-gitops (A: vendoring, B: import + measurement, C: apply +
record, D: retirements) plus one small PR per owning service repo. Nothing
writes to Cloudflare before task 9, and task 9 is an operator dispatch.

## PR A — vendor the data, validate it, write nothing to Cloudflare

- [ ] 1. Vendor the six allowlists into
      `infrastructure/cloudflare/portal/allowlists/{tg,api,seerrsense,projects,alice,coolify}.json`,
      byte-identical to each owning repo's `docs/portal-allowlist.json` on
      `main` (`OWNERS` in `scripts/portal-catalogue-drift.py` is the
      authoritative repo map) — DoD: six files committed; each is
      the service file unchanged (top-level `{"$comment", "portal", "server",
      "default_disabled", "tools"}`, tools carrying `reason`) with `server`
      equal to the file stem; `mctlhq/mctl-coolify-mcp#5` is merged first, so
      coolify's file exists on `main`; counts match
      the issue's constraint line (alice 12/12, projects 8/8, tg 30/30, api
      75/75, coolify 22/45, seerrsense 5/5); the source commit sha of each is
      in the PR body.

- [ ] 2. Write `allowlists/mapping.json` (depends on 1) — DoD: a
      `{"servers": {"<id>": {"vendored": bool, "default_disabled": bool,
      "on_behalf": bool, "updated_prompts": [...], "updated_tools": [...]}}}`
      object covering all six live members; `default_disabled`/`on_behalf`
      copied from the live portal (the same two fields
      `scripts/portal-membership-add.sh` asserts are uniform across members);
      `updated_prompts` literal per server (api 4/4, coolify 0/3, the rest
      empty); `updated_tools` present only where `vendored` is false.

- [ ] 3. Write `allowlists/sources.json` and `allowlists/baseline.json`
      (depends on 1, 2) — DoD: `sources.json` has `{repo, path, ref, sha,
      vendored_at}` per vendored server; `baseline.json` has
      `{tools_total, tools_enabled, prompts_total, prompts_enabled, recorded}`
      per server, equal to the live mapping at import time.

- [ ] 4. Add `scripts/validate-portal-allowlists.py` (depends on 2, 3) — DoD:
      executable, stdlib-only, `--selftest` first then bare, following the
      `check()`/`FAILURES` style of `scripts/validate-agent-platform.py`;
      enforces shape, file/`mapping.json` coverage, `sources.json` coverage,
      the literal `resource "cloudflare_zero_trust_access_ai_controls_mcp_server"
      "<id>"` grep against `mcp-servers.tf` with a commented
      `UNMANAGED = {"api", "seerrsense"}` exception, and the `baseline.json`
      non-widening comparison; exits non-zero with the offending path and a
      one-line reason for each failure mode.

- [ ] 5. Wire the validator into `.github/workflows/validate-manifests.yml`
      (depends on 4) — DoD: a new step named
      `Validate the vendored MCP portal allowlists`, placed beside the existing
      portal steps (`Unit-test the MCP portal controls apply script` ...
      `Unit-test the portal tool catalogue drift detector`), running
      `--selftest` then the bare invocation; green on this PR.

## PR B — import the portal, and take the measurement

- [ ] 6. Add `infrastructure/cloudflare/portal/mcp-portal.tf` (depends on 2) —
      DoD: an `import` block for
      `cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp` following
      `mcp-servers.tf`'s `id = "${var.account_id}/tg"` form; a resource
      declaring `hostname`, `secure_web_gateway`, `code_mode`,
      `allow_code_mode` with the values in `mcp-portal-controls.json`, and
      `servers` built from `local.portal_mapping` with
      `jsondecode(file("${path.module}/allowlists/<id>.json"))` for vendored
      servers; `depends_on` on the four managed server resources;
      `tofu fmt -check -diff` and `tofu validate` green in `cloudflare-plan`.

- [ ] 7. Record the measurement in the PR body (depends on 6) — DoD: the
      `cloudflare-plan` job summary for `infrastructure/cloudflare/portal` is
      pasted verbatim; it reads `1 to import, 0 to add, 0 to change, 0 to
      destroy`; and the four task-0 questions are each answered from it in
      prose: `updated_tools` ordering, computed `alias`/`description`,
      catalogue tools absent from `updated_tools`, and the round-trip of
      `default_disabled`/`on_behalf`.

- [ ] 8. **Gate.** If task 7's plan shows any attribute change that no config
      edit removes (depends on 7) — DoD: PR B is closed unmerged, the measured
      plan and the reason are commented on issue #1370, and work switches to
      tasks 16-19 (fallback). Otherwise PR B merges and work continues at 9.

## PR C — apply, and confirm the second plan

- [ ] 9. Dispatch `cloudflare-apply.yml` with
      `root=infrastructure/cloudflare/portal` (depends on 8) — DoD: the
      `cloudflare-apply` environment approval is granted by a human after
      reading the plan; the apply succeeds; the run's summary is linked on
      #1370. This is the only step in the whole proposal that writes to
      Cloudflare.

- [ ] 10. Confirm the second plan (depends on 9) — DoD: the next nightly
      `cloudflare-drift.yml` run for this root reports `No changes`, and
      `scripts/portal-auth-credentials-drift.py` and
      `scripts/portal-catalogue-drift.py` still exit 0 in the same run; the
      run link is recorded on #1370. A non-zero here means task 8's gate
      failed late: revert task 6 and land the fallback.

## PR D — the bump path and the retirements

- [ ] 11. Add `.github/workflows/portal-allowlist-vendor.yml` (depends on 4) —
      DoD: `workflow_dispatch` with `server`, `allowlist`, `source_repo`,
      `source_sha`; mints the `mctl-agents` App token from
      `secrets.AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` with
      `permission-contents: write` and `permission-pull-requests: write`;
      runs `scripts/validate-portal-allowlists.py` **before** committing;
      writes `allowlists/<server>.json` + the `sources.json` entry and nothing
      else (never `baseline.json`); pushes `portal-allowlist/<server>-<sha7>`
      and opens a PR titled with the enabled-count delta; concurrency group
      `portal-allowlist-vendor-<server>`, `cancel-in-progress: false`; no new
      secret is introduced.

- [ ] 12. Add `--vendor-check` to the validator and a drift step (depends on
      11) — DoD: `--vendor-check` compares each vendored file against its
      `sources.json` sha and against the owning repo's `main`, using
      `ALLOWLIST_TOKEN` for `PRIVATE_OWNERS`; a new
      `cloudflare-drift.yml` step for the portal root only, reusing the
      existing `Generate a read token for the private upstreams` step's
      output, gated the same way (`steps.plan.conclusion == 'success' &&
      !cancelled()`); its finding is reported and alerted distinctly from a
      stale catalogue.

- [ ] 13. Retire the controls script (depends on 9) — DoD:
      `scripts/portal-controls-apply.sh`,
      `tests/test_portal_controls_apply.py`, that test's
      `validate-manifests.yml` step, and
      `infrastructure/cloudflare/portal/mcp-portal-controls.json` are deleted;
      the first section of `infrastructure/cloudflare/portal/README.md` is
      rewritten to describe the resource; the "that is not OpenTofu" bullet in
      `docs/runbooks/cloudflare-operations.md` is corrected; no reference to
      the script survives `grep -rn portal-controls-apply .`.

- [ ] 14. Retire the membership script (depends on 9) — DoD:
      `scripts/portal-membership-add.sh`,
      `tests/test_portal_membership_add.py` and that test's step are deleted;
      the README's membership section is replaced by the "add a seventh
      server" order (create the server resource, apply, admin completes the
      first upstream login, then vendor an allowlist and bump); the
      re-snapshot recipe's step 5 and its `seerrsense` hand-`PUT` block are
      rewritten to point at the vendored file and the bump PR; no reference
      survives `grep -rn portal-membership-add .`.

- [ ] 15. Fix the stale comments (depends on 13, 14) — DoD: the `OWNERS` note
      in `scripts/portal-catalogue-drift.py`, the `DCR_SERVERS` note in
      `scripts/portal-auth-credentials-drift.py`, and
      `infrastructure/cloudflare/account/portal-mcp-apps.tf` lines 11 and 120
      no longer name a retired script; both detectors' `--selftest` still pass.

## Per-service-repo PRs (one each)

- [ ] 16. Add the dispatch workflow to `mctl-telegram`, `mctl-api`,
      `seerrsense`, `projects-mcp`, `mctl-alice`, `mctl-coolify-mcp` (depends
      on 11) — DoD: `on: push: branches: [main], paths:
      ['docs/portal-allowlist.json']`; dispatches
      `portal-allowlist-vendor.yml` in `mctlhq/mctl-gitops` with the file
      content, the repo and `github.sha`, using the existing `GITOPS_TOKEN`;
      no new secret in any repo.

- [ ] 17. Delete `scripts/portal-allowlist-apply.sh` from `mctl-telegram`,
      `mctl-api`, `projects-mcp` and `mctl-alice` (depends on 16) — DoD:
      `grep -rn portal-allowlist-apply` is empty across all mctlhq repos;
      `mctlhq/mctl-telegram#635`, `mctlhq/mctl-api#300` and
      `mctlhq/seerrsense#70` are closed with a link to this change.

## Fallback (only if task 8 or task 10 fails)

- [ ] 18. Leave `servers` undeclared per `#1092` — DoD: task 6's resource keeps
      only the switches and `hostname`; `servers` is either absent or in
      `ignore_changes`, with the measured plan quoted in the comment
      explaining why.
- [ ] 19. Add one server-agnostic `scripts/portal-allowlist-apply.sh` to
      mctl-gitops (depends on 18) — DoD: the server id comes from the file's
      own `server` field, never an argument; `--check` and `--dry-run` modes;
      it vets the file against `HEAD` the way
      `scripts/portal-controls-apply.sh` does; a `tests/test_portal_allowlist_apply.py`
      in the repo's stdlib style, wired into `validate-manifests.yml`.
- [ ] 20. Add `.github/workflows/portal-allowlist-apply.yml` (depends on 19) —
      DoD: plan, then `environment: cloudflare-apply`, then apply; it shares
      one concurrency group with every other portal writer; a nightly
      `--check` over all six servers is added to the portal branch of
      `cloudflare-drift.yml`.

## Tests

- [ ] T1. `scripts/validate-portal-allowlists.py --selftest` covers, from
      fixtures under `scripts/tests/fixtures/portal-allowlists/{valid,invalid}`:
      each of the six live files as-is (must pass: byte-identical copies are
      valid); a top-level key outside the allowed set; `portal` not `"mcp"`;
      `default_disabled` not `true`; a `tools` map instead of a list; empty
      `tools`; a tool with a key outside the allowed set; a tool with no
      `reason`; a non-boolean `enabled`; an empty `name`; a
      duplicate name; a `server` field disagreeing with the filename; a file
      with no `mapping.json` entry and a `mapping.json` entry with no file; a
      missing `sources.json` entry; a server id absent from `mcp-servers.tf`
      and not on `UNMANAGED`; one more tool enabled than `baseline.json`
      records; and the same with `baseline.json` updated to match (must pass).
- [ ] T2. `--vendor-check` selftest cases with the network stubbed: vendored
      equals the recorded sha and equals `main` (quiet); equals the sha but
      differs from `main` (lag, reported); differs from the recorded sha
      (tampered, reported distinctly); the upstream unreadable (undetermined,
      not a failure), mirroring `portal-catalogue-drift.py`'s handling.
- [ ] T3. `scripts/portal-auth-credentials-drift.py --selftest` and
      `scripts/portal-catalogue-drift.py --selftest` still pass after task 15's
      comment edits and after `mcp-portal.tf` exists in the root (the latter
      walks `tofu show -json` state and must not trip over a new resource
      type).
- [ ] T4. `tofu fmt -check -diff` and `tofu validate` green for the portal root
      in the `cloudflare-plan` job of PR B.
- [ ] T5. The one-flip test: on a scratch branch, flip exactly one `enabled` in
      `allowlists/coolify.json` and confirm `cloudflare-plan`'s summary shows
      exactly one change and no other attribute moves. Discard the branch.
- [ ] T6. Task 11's workflow is exercised once end-to-end with a no-op bump
      (dispatch the current content of one allowlist) and must open a PR whose
      diff is empty or whose only change is the `vendored_at` timestamp, and
      whose CI is green.
- [ ] T7. `.github/workflows/validate-manifests.yml` is green on every PR in
      the sequence; `cloudflare-plan`'s `assert-scripts` job and root-coverage
      guard stay green (the new `allowlists/` directory contains no `.tf` and
      must not be discovered as a root).

## Rollback

- **Before task 9** nothing has been written to Cloudflare. Reverting PR A and
  PR B is a pure git revert; the six writers keep working unchanged.
- **After task 9, if the portal is wrong.** The fastest correction is another
  approved apply: fix `mapping.json` or the vendored file, merge, dispatch
  `cloudflare-apply.yml` for the root. The reviewed-plan digest assert makes
  this the same gated path as the original apply.
- **After task 9, if the resource itself is the problem** (a perpetual diff
  found only post-apply, or an apply that dropped a mapping): restore the live
  mapping from `baseline.json` plus the vendored files by hand through the API
  — the `seerrsense` read-modify-write recipe in
  `infrastructure/cloudflare/portal/README.md` is the procedure, and it must be
  run with no apply of this root in flight — then `tofu state rm
  cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp` and revert PR B.
  State is versioned in R2 and `opentofu-state-backup.yml` covers this root, so
  a bad state can also be restored per section 4 of
  `docs/runbooks/cloudflare-operations.md`.
- **After task 13/14**, rolling back the retirements is a git revert: the
  scripts are self-contained and read only committed files plus the API. If
  they are restored while the portal resource is still in state, run
  `--check` only — an apply from a script would now fight the nightly plan.
- **The break-glass rule still applies.** Any hand mutation made during a
  rollback is recorded per section 1 of
  `docs/runbooks/cloudflare-operations.md`, and the next drift run is the
  check that it was recorded correctly.
