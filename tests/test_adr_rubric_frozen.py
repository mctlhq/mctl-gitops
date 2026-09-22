"""issue-903: the rubric is frozen and the Stage A screen is honest.

T6. `docs/adr/0001-rubric.yaml` weights sum to 100; the weights table in
    `docs/adr/0001-agent-execution-trace-backend.md` matches the YAML
    dimension-for-dimension; every candidate score cell is null and every
    citation empty; top-level `verdict` is null; the ADR status is
    `Proposed`; the `<!-- VERDICT: UNFILLED -->` marker is present; and all
    seven permitted verdicts from issue #903 appear verbatim in both files.

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

for d in dimensions:
    for candidate, cell in d["candidates"].items():
        check(cell["score"] is None, f"{d['key']}/{candidate}: score is not null ({cell['score']!r})")
        check(cell["citation"] == "", f"{d['key']}/{candidate}: citation is not empty ({cell['citation']!r})")

check(rubric["verdict"] is None, f"top-level verdict is not null: {rubric['verdict']!r}")

check("Proposed" in re.search(r"\*\*Status:\*\*\s*(\w+)", adr_text).group(1)
      if re.search(r"\*\*Status:\*\*\s*(\w+)", adr_text) else False,
      "ADR Status line is not exactly Proposed")
check("<!-- VERDICT: UNFILLED -->" in adr_text, "ADR is missing the <!-- VERDICT: UNFILLED --> marker")

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
print("ADR rubric: frozen, weights agree with the Markdown table, Stage A screen is honest")
