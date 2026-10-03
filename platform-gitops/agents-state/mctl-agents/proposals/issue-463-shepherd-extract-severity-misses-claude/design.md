# Design: issue-463-shepherd-extract-severity-misses-claude

## Current state

`orchestrator/run_shepherd.py` is a single ~4070-line module. The relevant
chain is:

1. `_extract_severity(body: str) -> str | None` (L1656-1679). Today it loops
   `for sev in ("P1", "P2", "P3")` and, per severity, tries three checks in
   order:
   - badge: `f"![{sev} Badge]" in body` — anywhere in the body (legacy Codex);
   - open bold: `f"**{sev} —" in body or f"**{sev} -" in body or f"**{sev}:" in body`
     — anywhere in the body, delimiter *inside* the bold span;
   - bare: for `mark` in `f"{sev} —"`, `f"{sev} -"`, `f"{sev}:"` —
     `body.startswith(mark) or f"\n{mark}" in body`, i.e. anchored to the start
     of the body or of a line.
   Because the outer loop is severity-ordered, a `P1` marker anywhere in the
   body wins over a `P2` marker that appears earlier — the function has
   *severity* precedence, not positional precedence. That is load-bearing and
   easy to lose in a rewrite.

2. `read_codex_review(pr)` (L1704-1910) calls `_extract_severity` at four
   sites: the top-level review body (L1775), line-anchored review comments
   (L1804), claude[bot] issue comments (L1852) and connector issue comments
   (L1874). Each site builds a `CodexFinding` only when
   `sev in ("P1", "P2")`. `P3` is parsed and then discarded by every caller.

3. `decide(pr, codex_review, ...)` (L1954+) checks findings *first*: anything
   raised against the current head blocks, whoever raised it. With
   `has_responded=True`, `head_verdict == "CHANGES_REQUESTED"` and an empty
   finding list, it returns `("wait", None)` — pinned by
   `test_changes_requested_with_nothing_fresh_left_is_a_wait`
   (`tests/test_run_shepherd.py` ~L5360). That is exactly the observed dead
   end: `codex_findings=0 ... -> wait` on every tick
   (`mctl-agents-shepherd-fdc64f36` for mctl-telegram#674,
   `mctl-agents-shepherd-17ce3e70` for newton-mcp-gateway#21). The tick log
   line is emitted at `process_one` L2815.

4. Tests. `tests/test_run_shepherd.py` L3411-3474 is the
   `_extract_severity` format-compatibility block (badge, open bold, hyphen,
   bare at body start, bare mid-body, colon variant from mctl-portal#88, and
   the no-match cases). Decision-level tests build a `PRSnapshot` with
   `make_pr()` (L50), fake the GitHub reads by patching
   `run_shepherd._gh_api_json` with the `_route_gh(pr, reviews=...,
   review_comments=..., issue_comments=...)` helper (L2125), call
   `run_shepherd.read_codex_review(pr)` and assert on `decide(pr, review)` —
   `test_connector_inline_finding_gates_merge` (L2139+) is the closest
   template for what this proposal needs.

No prose documentation describes the marker grammar: the `_extract_severity`
docstring is the documentation, and it is currently wrong about which forms
are accepted. `docs/` has no shepherd review-format page (`docs/` holds adr,
benchmarks, observability, operations, diagrams).

The repo has no `CLAUDE.md`. Tooling: Python 3.12, `uv`, `pytest~=9.0`,
`ruff~=0.16`, `mypy~=2.3` (`pyproject.toml`), release-please with conventional
commits (`release-please-config.json`).

## Proposed solution

Replace the three `if` branches inside the severity loop with **one anchored,
module-level compiled regex**, keeping the badge substring check exactly as it
is and keeping severity precedence.

```python
# Severity marker grammar, anchored to the start of a line (re.MULTILINE).
# Two alternatives, matching what claude[bot] and the Codex connector have
# actually written:
#   bold:  **P2 —   **P2 -   **P2:   **P2** —   **P2** -   **P2**:   **P2**
#   bare:  P2 —     P2 -     P2:
# The bold span may close before OR after the delimiter, and a closed bold
# span may end the line with no delimiter at all.
_SEVERITY_RE = re.compile(
    r"""
    ^[ \t]*(?:[-*+][ \t]+|\d+[.)][ \t]+)?       # optional list bullet
    (?:
        \*\*(P[123])(?:
              \*\*[ \t]*(?::|—|–|-|$)                             # **P2** — / **P2**: / **P2**
            | \*\*[ \t]*\([^)\n]*\)[ \t]*(?::|—|–|-)             # **P2** (security): / **P2** (x) —
            | (?:[ \t]*\([^)\n]*\))?[ \t]*(?::|—|–|-)            # **P2 — / **P2: / **P2 (security):
          )
      | (P[123])(?:[ \t]*\([^)\n]*\))?[ \t]*(?::|—|–|-)          # P2 — / P2: / P2 (carried over …):
    )
    """,
    re.MULTILINE | re.VERBOSE,
)


def _extract_severity(body: str) -> str | None:
    found = {m.group(1) or m.group(2) for m in _SEVERITY_RE.finditer(body)}
    for sev in ("P1", "P2", "P3"):
        if f"![{sev} Badge]" in body or sev in found:
            return sev
    return None
```

Why this shape:

- **`^` with `re.MULTILINE`** is what makes prose safe. `there are P2: issues
  here` and `see **P2** above` never start a line with the marker, so they do
  not match, which is the issue's explicit no-false-positive criterion. It also
  reproduces today's bare-branch semantics (`body.startswith(mark)` or
  `"\n" + mark`) without the two-case split.
- **`[ \t]*`, never `\s*`.** `\s` matches `\n`, so the sketch in the issue
  (`^\*\*P[123](?:\*\*)?\s*(?::|—|-)`) would let a line containing only `**P2**`
  bind to a `-` opening the *next* line — a bullet list under a heading would
  parse as a finding. Restricting the intra-marker gap to spaces and tabs
  removes that whole class.
- **The bold alternative splits into closed-bold and open-bold**, which covers
  all four bold spellings while keeping `$` narrow: delimiter inside the bold
  (`**P2 —`, `**P2:`, today's form) requires a delimiter; delimiter after a
  closed bold (`**P2** —`, `**P2**:`, the #674 and #21 forms) and a closed bold
  that ends the line (`**P2**` alone, the form the issue also asks for) are the
  other branch. `$` is reachable only *after a closing* `**`, so neither a bare
  line reading `P2` nor an unclosed `**P2` at end of line parses — both match
  today's behaviour. Collapsing this into the issue's single
  `(?:\*\*)?[ \t]*(?::|—|-|$)` would make `**P2\n— text` parse as `P2`, which
  is why it is two sub-branches.
- **Verified against every existing assertion.** The pattern above was run
  against the full current `tests/test_run_shepherd.py` (288 passed) plus the
  T1-T9 cases in tasks.md, including the amended parenthetical-qualifier
  cases: no regression in the accepted set.
- **`finditer` + severity-ordered lookup, not `search`.** A plain `search`
  would return the *first* marker positionally and silently downgrade a body
  whose `P2` precedes its `P1`. Collecting all matches into a set and then
  scanning `("P1", "P2", "P3")` keeps the existing severity precedence
  byte-for-byte, and keeps the badge check in the same ordered scan so
  `![P1 Badge]` still outranks a `P2` line.
- **Optional parenthetical qualifier (owner amendment).** claude[bot]'s round-2 review on
  mctlhq/newton-mcp-gateway#21 wrote `P3 (carried over from prior review, still unaddressed —
  non-blocking): ...`; the same spelling with `P2` would reproduce the #21 stall. One
  same-line group `\([^)\n]*\)` is allowed between the marker and the delimiter in all three
  branches. After a closed bold it *requires* a delimiter (`**P2** (x)` alone does not parse),
  so the end-of-line rule stays reachable only directly after `**`. The qualifier excludes `)`
  and `\n`, so it cannot swallow text across lines, and line anchoring still rejects
  `there are P2 (maybe): x`. Checked against the full existing `tests/test_run_shepherd.py`
  (288 passed) plus 22 cases including every T1-T9 example.
- **Optional list bullet.** claude[bot] review bodies commonly list findings as
  `- **P2**: ...`. Allowing at most one bullet (or `1.` / `1)`) plus leading
  whitespace costs one token group and does not weaken the prose criteria:
  `- see **P2** above` still fails because the marker does not follow the
  bullet. Flagged in requirements as a deliberate superset the reviewer may cut.
- **En dash `–`** joins `—` and `-` in the delimiter alternation for the same
  "stop paying for the next variant" reason. Also cuttable.

The `_extract_severity` docstring is rewritten to state the grammar the regex
implements and to cite the three incidents (mctl-portal#88 `P1:`,
mctl-telegram#674 `**P2** —`, newton-mcp-gateway#21 `**P2**:`), so the next
reader sees the history that produced each branch. No other function, type or
call site changes; `CodexFinding.severity` still carries `"P1"` or `"P2"`.

Tests are added in the existing `_extract_severity` block
(`tests/test_run_shepherd.py` L3411-3474): the two verbatim incident bodies as
regression fixtures, the closed-bold matrix, the multi-severity precedence
case, the newline-gap case, and the prose non-matches. One new
**decision-level** test sits with the `read_codex_review` tests: `make_pr()`,
a `CHANGES_REQUESTED` review at `HEAD_SHA`, one claude[bot] inline comment
`**P2**: ...` at `HEAD_SHA` created after `HEAD_PUSHED_AT`, routed through
`_route_gh`, asserting one finding and `decide(pr, review)[0] ==
"address-review"`. That test is the one that would have caught the incident:
the helper-level tests alone do not prove the fix reaches the decision.

## Alternatives

1. **Add two more `if` branches** (`f"**{sev}** —"`, `f"**{sev}**:"`).
   Smallest possible diff and zero risk to existing formats, but it is the
   third time this function grows a branch for a spelling, the branches are
   unanchored substring checks that keep accepting mid-line prose, and the
   issue explicitly asks for a regex instead. Dropped.

2. **Strip Markdown emphasis before matching** (delete `**` from the body, then
   run the bare-prefix check). One rule instead of a grammar, and it makes
   `**P2** —` and `P2 —` literally the same input. Dropped because it mutates
   offsets and content used nowhere else, silently makes `a**P2**:b` parse, and
   would need its own inverse-mapping story if the parser ever has to report
   *where* the marker was.

3. **Ask for a structured signal instead of parsing prose** — e.g. require
   claude[bot] to emit a `<findings>` block or a checkbox table, and key the
   shepherd off that. Strictly better long-term and would end this bug class,
   but it is a cross-repo change to the review prompt plus a compatibility
   window for in-flight PRs, while the PRs stuck today need a parser that
   handles the text the bot already writes. Dropped as out of scope; worth a
   separate issue.

4. **Positional first-match regex (`search`)**, the simplest reading of the
   issue's sketch. Dropped: it changes severity precedence for mixed bodies,
   an unrelated behaviour regression with no test pinning it today.

## Platform impact

- **Migrations / state:** none. No schema, no `.status.yaml` field, no GitOps
  file changes. Pure in-process parsing.
- **Backward compatibility:** every format accepted today keeps parsing, with
  one deliberate narrowing: an open-bold marker *mid-line*
  (`Summary: **P2 — foo**`) stops matching. That narrowing is required by the
  issue's no-false-positive criterion, and no test, fixture, or cited body
  depends on it — the "mid-body" test at L3429 has its marker after `\n\n`.
- **Blast radius:** `_extract_severity` feeds only `read_codex_review`, so the
  worst failure modes are (a) under-matching — the status quo, PRs wait and a
  human intervenes, and (b) over-matching — the shepherd calls
  `address-review` on prose, burns implementer attempts, and hits
  `MAX_REVIEW_ATTEMPTS` which flips the proposal to `review-stuck` rather than
  merging anything. Neither can merge code that a reviewer blocked: findings
  only ever *add* a gate in `decide()`.
- **Resource impact:** one compiled module-level regex over comment bodies
  already in memory; negligible. Compiling at import (not per call) avoids
  re-compilation across the four call sites and the per-PR loop.
- **Risks + mitigations:**
  - *Regex accepts something prose-like* -> the prose non-match tests and the
    anchoring; `[ \t]*` instead of `\s*` closes the cross-line variant.
  - *Severity precedence silently changes* -> explicit mixed-severity test.
  - *Fix does not actually reach the decision* -> the decision-level test, plus
    the mutation check (revert the parser body, confirm the new tests fail)
    required by the workspace rule for regression tests.
  - *Yet another spelling appears later* -> the grammar now lives in one
    documented pattern; adding a delimiter is a one-token change plus a
    fixture. The docstring names each incident so the reason for each branch
    survives.
- **Operational follow-up:** after merge, the next shepherd tick on a PR in
  this state should log `codex_findings>0 ... -> address-review`. Worth
  spot-checking one live tick (`mctl_get_workflow_logs` on the next
  `mctl-agents-shepherd-*` run) rather than assuming.
