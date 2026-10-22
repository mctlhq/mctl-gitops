"""issue-903: the rubric is frozen and the Stage A screen is honest.

T6. `docs/adr/0001-rubric.yaml` weights sum to 100; the weights table in
    `docs/adr/0001-agent-execution-trace-backend.md` matches the YAML
    dimension-for-dimension; every candidate score cell is null and every
    citation empty; top-level `verdict` is null; the ADR status is
    `Proposed`; the `<!-- VERDICT: UNFILLED -->` marker is present; and all
    seven permitted verdicts from issue #903 appear verbatim in both files.

    Once #1280 has recorded a verdict (top-level `verdict` non-null), the
    freeze is replaced by the scored-state contract T6b instead of being
    dropped: the verdict is one of the seven, the ADR is `Accepted` and its
    Decision section names that verdict, every score is an integer 0-5 with
    a citation, and every cell left null carries a citation saying why it
    was not measured (#1280 acceptance: "any cell that could not be
    measured says so instead of being scored"). Weights stay as frozen.

T7. Stage A honesty check. All five candidates have a `stage_a` row; every
    row's verdict is one of SURVIVES/SCREENED-OUT/UNVERIFIED; no row whose
    `evidence` is `issue-903-body` is marked SURVIVES; every SCREENED-OUT
    row carries a non-empty `reason`; and traceway specifically is
    UNVERIFIED, because this repository contains no evidence about it.

Run: python3 tests/test_adr_rubric_frozen.py
"""
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUBRIC = ROOT / "docs" / "adr" / "0001-rubric.yaml"
ADR = ROOT / "docs" / "adr" / "0001-agent-execution-trace-backend.md"

ALLOWED_VERDICTS = {"SURVIVES", "SCREENED-OUT", "UNVERIFIED"}
EXPECTED_CANDIDATES = {"traceway", "tempo", "langfuse", "phoenix", "signoz"}

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


rubric = yaml.safe_load(RUBRIC.read_text())
adr_text = ADR.read_text()

# --- T6: rubric freeze -------------------------------------------------

dimensions = rubric["dimensions"]
total_weight = sum(d["weight"] for d in dimensions)
check(total_weight == 100, f"dimension weights sum to {total_weight}, not 100")

# Extract the ADR's Markdown weights table (rows of `| Name | Weight |`).
table_rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|$", adr_text, re.MULTILINE)
adr_weights = {name.strip(): int(weight) for name, weight in table_rows
               if name.strip() not in ("Dimension", "Candidate")}
rubric_weights = {d["name"]: d["weight"] for d in dimensions}
check(
    adr_weights == rubric_weights,
    f"ADR weights table {adr_weights} does not match rubric YAML {rubric_weights}",
)

status_match = re.search(r"\*\*Status:\*\*\s*(\w+)", adr_text)
adr_status = status_match.group(1) if status_match else None
verdict = rubric["verdict"]

if verdict is None:
    # T6, frozen: nothing scored before the soak decides.
    for d in dimensions:
        for candidate, cell in d["candidates"].items():
            check(cell["score"] is None, f"{d['key']}/{candidate}: score is not null ({cell['score']!r})")
            check(cell["citation"] == "", f"{d['key']}/{candidate}: citation is not empty ({cell['citation']!r})")
    check(adr_status == "Proposed", f"ADR Status is {adr_status!r}, not Proposed")
    check("<!-- VERDICT: UNFILLED -->" in adr_text, "ADR is missing the <!-- VERDICT: UNFILLED --> marker")
else:
    # T6b, scored: every cell is either a cited measurement or a cited
    # "not measured"; a bare null or an uncited score is a failure.
    scored = 0
    for d in dimensions:
        for candidate, cell in d["candidates"].items():
            score, citation = cell["score"], cell["citation"]
            check(isinstance(citation, str) and citation.strip() != "",
                  f"{d['key']}/{candidate}: no citation (a score needs its evidence, a null needs its reason)")
            if score is not None:
                scored += 1
                check(isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 5,
                      f"{d['key']}/{candidate}: score {score!r} is not an integer 0-5")
    check(scored > 0, "a verdict is recorded but no cell is scored")
    check(adr_status == "Accepted", f"verdict recorded but ADR Status is {adr_status!r}, not Accepted")
    check("<!-- VERDICT: UNFILLED -->" not in adr_text,
          "verdict recorded but the ADR still carries <!-- VERDICT: UNFILLED -->")
    decision = adr_text.split("\n## Decision\n", 1)
    check(len(decision) == 2 and verdict in decision[1].split("\n## ", 1)[0],
          f"ADR Decision section does not name the recorded verdict {verdict!r}")

expected_verdicts = [
    "ADOPT TRACEWAY",
    "ADOPT TEMPO + AI SPECIALIST",
    "ADOPT LANGFUSE",
    "ADOPT PHOENIX for eval specialization",
    "ADOPT SIGNOZ",
    "ADOPT TEMPO / mctl-native only",
    "CONTINUE COMPARISON with an explicit unresolved blocker",
]
check(
    len(expected_verdicts) == 7,
    "this test's own expected_verdicts list is not seven entries -- fix the test",
)
rubric_verdicts = rubric.get("permitted_verdicts", [])
check(
    rubric_verdicts == expected_verdicts,
    f"rubric permitted_verdicts {rubric_verdicts} does not match issue #903 verbatim",
)
check(verdict is None or verdict in expected_verdicts,
      f"recorded verdict {verdict!r} is not one of the seven permitted verdicts")
for v in expected_verdicts:
    check(v in adr_text, f"ADR is missing permitted verdict verbatim: {v!r}")

# --- T7: Stage A honesty -------------------------------------------------

stage_a = rubric.get("stage_a", [])
seen_candidates = {row["candidate"] for row in stage_a}
check(seen_candidates == EXPECTED_CANDIDATES,
      f"stage_a candidates {seen_candidates} != expected {EXPECTED_CANDIDATES}")

for row in stage_a:
    check(row["verdict"] in ALLOWED_VERDICTS,
          f"{row['candidate']}: verdict {row['verdict']!r} not in {ALLOWED_VERDICTS}")
    if row.get("evidence") == "issue-903-body":
        check(row["verdict"] != "SURVIVES",
              f"{row['candidate']}: evidence is issue-903-body but verdict is SURVIVES "
              f"-- a claim resting only on the issue text may not be promoted to SURVIVES")
    if row["verdict"] == "SCREENED-OUT":
        check(bool(row.get("reason", "").strip()),
              f"{row['candidate']}: SCREENED-OUT row has no reason")

traceway = next((row for row in stage_a if row["candidate"] == "traceway"), None)
check(traceway is not None, "no stage_a row for traceway")
if traceway is not None:
    check(traceway["verdict"] == "UNVERIFIED",
          f"traceway verdict must be UNVERIFIED (no evidence in this repository), got {traceway['verdict']!r}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(f"ADR rubric: {'frozen' if verdict is None else 'scored, verdict ' + repr(verdict)}, "
      "weights agree with the Markdown table, Stage A screen is honest")
