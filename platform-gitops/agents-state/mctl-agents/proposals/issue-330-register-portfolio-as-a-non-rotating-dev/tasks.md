# Tasks: issue-330-register-portfolio-as-a-non-rotating-dev

- [ ] 1. Add `"portfolio"` to `SERVICES` in `config/settings.py` — append it
      after `"seerrsense"` (line 57) and before the commented-out
      `# "upwork-mcp"` entry. DoD: `python -c "from config.settings import
      SERVICES; assert 'portfolio' in SERVICES"` succeeds; no other line in the
      list is reordered or reformatted.
- [ ] 2. Add `"portfolio"` to `NON_ROTATING_SERVICES` in `config/settings.py`
      (depends on 1) — append it to the set alongside `"seerrsense"` (line 69).
      DoD: `ROTATING_SERVICES` is unchanged from `main` (same names, same
      order); `python -c "from config.settings import ROTATING_SERVICES; assert
      'portfolio' not in ROTATING_SERVICES"` succeeds.
- [ ] 3. Extend the `config/settings.py` header comment with a `portfolio`
      paragraph (depends on 1, 2), matching the existing per-service blocks for
      `mctl-telegram` (lines 22-24), `mctl-design` (26-31) and `mctl-academy`
      (33-43). DoD: the comment states that `portfolio` is a static Astro site
      in tenant `labs` developed exclusively through the DevLoop, that it has no
      `agents/portfolio/` scaffold and therefore must not enter
      `ROTATING_SERVICES`, and that registration is what lets
      `run_issue_poller.py` dispatch its `agents:intake` issues at all. Line
      length stays within ruff's `line-length = 120`.
- [ ] 4. Add `tests/test_settings.py` with the membership and invariant
      assertions (depends on 1, 2) — see the Tests section below. DoD: the file
      exists, imports only from `config.settings`, opens with
      `from __future__ import annotations`, and every test has a docstring
      naming the drift it catches (house style, cf.
      `tests/test_agent_inventory.py`).
- [ ] 5. Confirm `docs/agent-inventory.yaml` needs no change (depends on 1) —
      re-read the file and `orchestrator/validate_manifest.py:392+`
      (`check_manifests_match_inventory`) to verify the inventory is keyed by
      agent, not by service, and that no `seerrsense` / `mctl-pairdesk` /
      `mctl-academy` entry exists to mirror. DoD: the file is untouched in the
      diff, and the PR description records this explicitly (the issue made the
      inventory edit conditional).
- [ ] 6. Verify the two runtime guards accept the new name (depends on 1) —
      confirm by reading that `orchestrator/run_issue_investigator.py:1373` and
      `orchestrator/run_issue_poller.py:160-161,201` both test membership
      against the single imported `SERVICES` list and hold no private copy. DoD:
      `grep -rn "not a known service" orchestrator/` shows only those two sites,
      both reached via `config.settings.SERVICES`.
- [ ] 7. Run the full local gate (depends on 1-4): `uv run --locked pytest -q`,
      `uv run --locked ruff check orchestrator config tests tools`, and
      `uv run --locked mypy` — the exact commands from
      `.github/workflows/pr-validation.yml:230,257,264`. DoD: all three exit 0.
- [ ] 8. Open the PR with a Conventional Commit title in the style of the
      precedent commit (depends on 7): `fix(config): register portfolio as a
      non-rotating service`, body linking `mctlhq/mctl-agents#330` and noting
      that the matching `mctl-api` enum change is tracked separately as
      `mctlhq/mctl-api#274`. DoD: PR green on `pr-validation.yml`.

## Tests

- [ ] T1. `tests/test_settings.py::test_portfolio_is_a_registered_service` —
      asserts `"portfolio" in SERVICES`. Catches the case where the entry is
      dropped or misspelled, which is what makes the investigator exit with
      "Repo 'portfolio' is not a known service".
- [ ] T2. `tests/test_settings.py::test_portfolio_is_non_rotating` — asserts
      `"portfolio" in NON_ROTATING_SERVICES` and `"portfolio" not in
      ROTATING_SERVICES`. Catches a future edit that promotes it into the
      proactive rotation, which has no `agents/portfolio/` scaffold to run.
- [ ] T3. `tests/test_settings.py::test_non_rotating_services_are_all_registered`
      — asserts `set(NON_ROTATING_SERVICES) <= set(SERVICES)`. Generalises the
      typo class: a name present only in `NON_ROTATING_SERVICES` is inert and
      would otherwise fail silently.
- [ ] T4. `tests/test_settings.py::test_services_has_no_duplicates` — asserts
      `len(SERVICES) == len(set(SERVICES))`. Cheap guard against a
      copy-paste re-registration during a future append.
- [ ] T5. Pre-existing, must stay green:
      `tests/test_agent_inventory.py::test_service_agent_scope_matches_rotating_services`
      (`matched == set(ROTATING_SERVICES)`). This is the tripwire that fails if
      task 2 is forgotten — verify it passes rather than assuming it.
- [ ] T6. Full suite regression: `uv run --locked pytest -q` over `tests/`
      (`testpaths = ["tests"]`), with particular attention to
      `tests/test_run_issue_poller.py` and
      `tests/test_run_issue_investigator.py`, which exercise the two guards.
- [ ] T7. Manual post-rollout smoke (after the release pipeline ships the new
      CWFT image, outside this PR): label one `mctlhq/portfolio` issue
      `agents:intake` and confirm the poller logs a started DevLoopWorkflow
      rather than `WARN: portfolio is not a known service`. Alternatively run
      `python -m orchestrator.run_issue_poller --dry-run`, which prints
      `[dry-run] would start/attach ...` for known services.

## Rollback

The change is two list entries, one comment block and one new test file — no
state, no migration, no gitops manifest. To roll back: `git revert` the merge
commit on `mctlhq/mctl-agents` and let the release pipeline ship the reverted
image. Reverting restores the previous behaviour exactly — `portfolio` issues
go back to being skipped with the label kept, and the investigator exits with
"not a known service".

Nothing downstream is orphaned by a revert, with two things to be aware of:

- Any `agents-state/portfolio/proposals/<slug>/` directories the investigator
  already wrote in `mctl-gitops` remain on disk. They become unreachable by the
  implementer (its `--service` filter rejects unknown names again) but are inert
  — delete them in a separate gitops commit only if the registration is being
  abandoned permanently, not as part of an emergency revert.
- Any `portfolio` PR the implementer already opened is a normal GitHub PR and is
  unaffected; close it manually if the registration is being withdrawn.

Partial rollback, if the only problem is that the shepherd should not touch
`portfolio` PRs: no code revert is needed — add `portfolio` to the
`SHEPHERD_SKIP_SERVICES` env var in the gitops CronWorkflow
(`run_shepherd.py:317-330` reads it at import time), which is a
`mctl-gitops`-only change.
