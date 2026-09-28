# Shepherd: parse closed-bold severity markers (`**P2** —`, `**P2**:`) so CHANGES_REQUESTED PRs enter the fix loop

## Context

`orchestrator/run_shepherd.py::_extract_severity` turns a review comment body
into a severity string (`P1` / `P2` / `P3` / `None`). Everything downstream
depends on it: `read_codex_review` (run_shepherd.py L1704-1910) only builds a
`CodexFinding` when `_extract_severity(body) in ("P1", "P2")`, and `decide()`
(L1954+) only routes a PR to `address-review` when there is at least one fresh
finding to hand the implementer. When the parser returns `None` for a real
finding, the shepherd logs `codex_findings=0 ... -> wait` and a
`CHANGES_REQUESTED` PR waits forever, because a `CHANGES_REQUESTED` verdict with
an empty finding set is an explicit `wait` (see
`test_changes_requested_with_nothing_fresh_left_is_a_wait` in
`tests/test_run_shepherd.py`).

Today's parser (L1656-1679) accepts the badge form `![P2 Badge]`, the
*open*-bold forms `**P2 —` / `**P2 -` / `**P2:` (delimiter inside the bold span)
and the bare forms `P2 —` / `P2 -` / `P2:` at the start of the body or of a
line. claude[bot] now also writes the *closed*-bold form, where the bold span
closes before the delimiter: `**P2** — finding` (mctlhq/mctl-telegram#674, 7
findings dropped) and `**P2**: finding` (mctlhq/newton-mcp-gateway#21, 3
findings dropped, over two hours of `-> wait` ticks). Neither matches: the
bold branch wants the delimiter inside the `**`, and the bare branch fails
because the line starts with `**`. This is the same failure class as
mctl-portal#88 (the `P1:` variant), in a new spelling — and each new spelling
has cost a human a hand-driven fix round. The fix is to replace the chain of
`if` branches with one anchored, `re.MULTILINE` regex that accepts the whole
observed family, while keeping the badge check and the existing
"no severity marker in prose" behaviour.

## User stories

- AS the PR shepherd I WANT to recognise every severity marker claude[bot]
  actually writes SO THAT a `CHANGES_REQUESTED` PR reaches `address-review`
  instead of spinning on `wait`.
- AS a platform operator I WANT the marker grammar expressed as one anchored
  pattern SO THAT the next spelling variant is a one-line change plus a
  fixture, not another `if` branch and another incident.
- AS a reviewer of agent PRs I WANT ordinary prose mentioning `P2` to stay
  unparsed SO THAT the shepherd does not invent findings and loop on
  `address-review` until the attempt cap trips.

## Acceptance criteria (EARS)

- WHEN `_extract_severity` is called with a body whose line begins with
  `**P1**`, `**P2**` or `**P3**` followed by `:`, ` —`, ` -`, or end of line,
  THE SYSTEM SHALL return that severity.
- WHEN `_extract_severity` is called with the verbatim
  mctlhq/newton-mcp-gateway#21 P2 body — a leading `(Correction: ...)`
  paragraph, then a line starting `**P2**: \`base64.b64decode(...)\`` — THE
  SYSTEM SHALL return `"P2"`.
- WHEN `_extract_severity` is called with the verbatim mctlhq/mctl-telegram#674
  prefix `**P2** — a revoked session with no \`connect:*\` audit row renders ...`
  THE SYSTEM SHALL return `"P2"`.
- WHEN a body uses any format accepted before this change — `![P2 Badge]`
  anywhere in the body, and `**P2 —` / `**P2 -` / `**P2:` / `P2 —` / `P2 -` /
  `P2:` opening a line (including the first line) — THE SYSTEM SHALL return the
  same severity it returns today.
- WHEN a severity token appears mid-line in prose, e.g. `there are P2: issues
  here`, `see **P2** above`, `No P1/P2 findings (2 P3). Good to merge.`, or
  `There are P3 nits to consider`, THE SYSTEM SHALL return `None`.
- WHILE a body contains markers of more than one severity THE SYSTEM SHALL
  return the most severe one (`P1` over `P2` over `P3`), which is the
  precedence the current severity-ordered `for` loop produces, regardless of
  the order the markers appear in the body.
- WHEN the marker is preceded on its line only by whitespace and at most one
  Markdown list bullet (`-`, `*`, `+`, or `1.` / `1)`), THE SYSTEM SHALL still
  return that severity, since claude[bot] review bodies list findings as
  bullets.
- IF the delimiter is separated from the marker by a line break rather than
  spaces or tabs THEN THE SYSTEM SHALL return `None` for that occurrence — the
  intra-marker gap must not be `\s*`, which would span newlines.
- WHEN `read_codex_review` parses a `CHANGES_REQUESTED` review at the head SHA
  together with one inline claude[bot] comment whose body is `**P2**: ...`
  anchored at the head SHA and newer than `head_pushed_at`, THE SYSTEM SHALL
  produce a `CodexReview` with exactly one `P2` finding, and `decide()` SHALL
  return `address-review` rather than `wait`.
- WHEN the parser change is reverted and the new tests are re-run, THE SYSTEM
  SHALL fail those tests (mutation check), proving they pin the new behaviour
  and not an incidental one.

## Out of scope

- Any change to `decide()`, `read_codex_review`, `process_one`, the freshness
  filter `_is_fresh_finding`, the `MAX_REVIEW_ATTEMPTS` cap, or the
  `GATING_BOTS` set. This proposal only changes marker parsing.
- Changing which severities gate a merge: `P3` keeps being parsed and keeps
  being ignored by callers (`sev in ("P1", "P2")`).
- Retro-fixing the already-stuck PRs mctl-telegram#674 and
  newton-mcp-gateway#21; #674 was driven by hand and the parser fix makes the
  next tick self-sufficient.
- A general Markdown parser, or asking claude[bot] to emit a machine-readable
  finding format. Both are larger changes tracked elsewhere if wanted.

## Open questions

- Mid-line open-bold markers (`Summary: **P2 — foo**`) are accepted today and
  will stop being accepted once the pattern is anchored to line starts. The
  issue's own criterion (`see **P2** above` must return `None`) requires that
  narrowing, and no test, fixture, or observed body in this repo depends on a
  mid-line marker — the one "mid-body" test case
  (`tests/test_run_shepherd.py` L3429) has the marker after `\n\n`, i.e. at a
  line start. Proceeding with anchoring; a reviewer who disagrees can widen
  the bold branch to unanchored at the cost of the prose criterion.
- The list-bullet tolerance and the en-dash (`–`) delimiter are deliberate
  supersets of the issue's literal criteria, added because both are cheap and
  the recurring cost here is the *next* variant. Either can be dropped without
  touching the rest of the design.
- Whether a Markdown heading prefix (`#### **P2**: ...`) should also be
  accepted. Not observed in any cited PR; left out to keep the pattern small.
