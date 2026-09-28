# Tasks: issue-463-shepherd-extract-severity-misses-claude

- [ ] 1. Add the module-level compiled pattern `_SEVERITY_RE` to
      `orchestrator/run_shepherd.py`, immediately above `_extract_severity`
      (currently L1656). Use the exact pattern in design.md, which was verified
      against all 20 existing `test_extract_severity_*` assertions plus T1-T7
      below (40/40). Anchored with `re.MULTILINE | re.VERBOSE`; three branches
      (closed bold `**P2**` + delimiter-or-end-of-line, open bold `**P2` +
      required delimiter, bare `P2` + required delimiter); delimiter class `:`,
      `—`, `–`, `-`; intra-marker gap `[ \t]*`, never `\s*`; optional single
      leading list bullet (`-`, `*`, `+`, `1.`, `1)`) and leading whitespace;
      end-of-line reachable only after a closing `**`. Comment the pattern with
      the forms it accepts. — DoD: `re` is imported (it already is, used by
      `_neutralize_prompt_tags`), the pattern compiles at import, `ruff` and
      `mypy` clean.
- [ ] 2. Rewrite the body of `_extract_severity` (depends on 1) to
      `found = {m.group(1) or m.group(2) for m in _SEVERITY_RE.finditer(body)}`
      followed by the existing severity-ordered loop
      `for sev in ("P1", "P2", "P3")` returning `sev` when
      `f"![{sev} Badge]" in body or sev in found`. Delete the three `if`
      branches. — DoD: the badge check is untouched in behaviour, severity
      precedence (P1 over P2 over P3, regardless of position) is preserved, the
      signature and return type `str | None` are unchanged, and no call site in
      `read_codex_review` (L1775, L1804, L1852, L1874) is edited.
- [ ] 3. Rewrite the `_extract_severity` docstring (depends on 2) to state the
      grammar the regex implements and cite the three incidents that produced
      it: mctl-portal#88 (`P1:`), mctl-telegram#674 (`**P2** —`),
      newton-mcp-gateway#21 (`**P2**:`). — DoD: no stale claim survives; in
      particular the current "appears anywhere in the body (bold prefix)" line
      is corrected to "opens a line".
- [ ] 4. Extend the `_extract_severity` test block in
      `tests/test_run_shepherd.py` (L3411-3474) with T1-T6 below (depends on
      2). Keep the existing seven tests unmodified — they are the
      backward-compatibility contract. — DoD: `uv run pytest
      tests/test_run_shepherd.py -k extract_severity` passes with every
      pre-existing assertion intact.
- [ ] 5. Add the decision-level test T7 next to the `read_codex_review` tests
      (depends on 2), using `make_pr()` (L50), `_route_gh` (L2125),
      `run_shepherd.REVIEW_BOT`, `HEAD_SHA` and `HEAD_PUSHED_AT`. — DoD: the
      test exercises `read_codex_review` -> `decide` end to end and asserts
      `address-review`, not just the helper.
- [ ] 6. Run the mutation check (depends on 4, 5): locally revert the
      `_extract_severity` body to the pre-change branches, run the new tests,
      confirm T1, T2, T3, T7 fail and the pre-existing tests still pass, then
      restore. Record the observed failure output in the PR description. — DoD:
      the PR description shows the mutation-check evidence, per the workspace
      rule that a regression test must be proven to catch the regression.
- [ ] 7. Full gate (depends on 1-5): `uv run ruff check .`,
      `uv run mypy orchestrator`, `uv run pytest tests/test_run_shepherd.py`.
      — DoD: all three clean; no test outside the severity block changed.
- [ ] 8. Open the PR with a conventional-commit title
      (`fix(shepherd): parse closed-bold severity markers`), linking issue #463
      and naming both stuck PRs (mctlhq/mctl-telegram#674,
      mctlhq/newton-mcp-gateway#21). Call out the one deliberate narrowing
      (mid-line open-bold markers no longer parse) and the two deliberate
      supersets (list-bullet prefix, en dash) so a reviewer can cut either. —
      DoD: PR open, description contains the mutation-check evidence from 6.

## Tests

- [ ] T1. Regression fixture, verbatim newton-mcp-gateway#21 P2 body: the
      leading `(Correction: the earlier comment on this line saying "test" was
      an accidental artifact ... Real finding below.)` paragraph, a blank line,
      then ``**P2**: `base64.b64decode(payload, validate=True)` (line 159) runs
      before the `max_image_bytes` size check (line 162).`` ->
      `_extract_severity(...) == "P2"`. Same file, its two siblings
      `**P3**: ...` -> `"P3"`.
- [ ] T2. Regression fixture, verbatim mctl-telegram#674 prefix:
      ``**P2** — a revoked session with no `connect:*` audit row renders ...``
      -> `"P2"`.
- [ ] T3. Closed-bold matrix: `**P1**: finding` -> `"P1"`, `**P2**: finding` ->
      `"P2"`, `**P3**: finding` -> `"P3"`, `**P2** - finding` -> `"P2"`,
      `**P2**` alone on its own line -> `"P2"`.
- [ ] T4. No false positives: `there are P2: issues here` -> `None`,
      `see **P2** above` -> `None`, `Fixed the **P1** from round 2` -> `None`,
      `No P1/P2 findings (2 P3). Good to merge.` -> `None`, `""` -> `None`.
- [ ] T5. Severity precedence: a body whose first line is `P2 — lower` and
      whose later line is `P1 — higher` -> `"P1"` (positional first-match would
      return `"P2"`); and `"![P1 Badge] x\n\n**P2**: y"` -> `"P1"`.
- [ ] T6. Newline gap does not bind: `"**P2**\n- some bullet"` must not treat
      the next line's `-` as the delimiter — assert the result is `"P2"` only
      because of the end-of-line rule, and that `"**P2\n— text"` (marker and
      delimiter split across lines, bold unclosed) -> `None`.
- [ ] T7. Decision level: `pr = make_pr(checks_green=True)`; `reviews` = one
      `{"user": {"login": run_shepherd.REVIEW_BOT}, "commit_id": HEAD_SHA,
      "state": "CHANGES_REQUESTED", "submitted_at": "2026-04-29T11:00:00Z"}`;
      `review_comments` = one claude[bot] comment with `commit_id=HEAD_SHA`,
      `created_at` after `HEAD_PUSHED_AT` and body `**P2**: size check runs
      after the decode`; patch `run_shepherd._gh_api_json` with
      `_route_gh(pr, reviews=..., review_comments=...)`; assert
      `len(review.findings) == 1`, `review.findings[0].severity == "P2"`, and
      `decide(pr, review)[0] == "address-review"` (today: `"wait"`).
- [ ] T8. Regression guard for the existing block: re-run the seven
      pre-existing `test_extract_severity_*` tests unchanged, including the
      mid-body case at L3429 (`"Has P1/P2 findings, ...\n\n**P2 — Title
      (file:74)**\ndesc"` -> `"P2"`) and `"talking about P2: mid-line"` ->
      `None`.

## Rollback

Single-file, single-function change with no persisted state, so rollback is a
plain revert of the PR (`git revert <merge-sha>` on `mctl-agents` main, or
`mctl_rollback_service` to the previous `mctl-agents` image tag if the change
is already deployed). Reverting restores the pre-change parser exactly: the
only effect is that closed-bold findings go back to being dropped and affected
PRs go back to `wait`, which is the current production behaviour — nothing
written by the new code needs undoing, no `.status.yaml` is rewritten, and no
merge decision becomes unsafe (findings only ever add a gate in `decide()`).
If instead the fix over-matches and a PR loops on `address-review`, the
`MAX_REVIEW_ATTEMPTS` cap in `process_one` already terminates the loop at
`review-stuck`; the narrow rollback is to drop the two flagged supersets (the
list-bullet prefix group and the en dash) rather than the whole change.
