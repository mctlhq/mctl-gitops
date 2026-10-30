"""ADR 0002 rubric is frozen until a verdict is recorded.

Fails if: weights do not sum to 100 or disagree with the ADR table; any score
or citation is set while the ADR verdict record is empty; or, once a verdict
is recorded, any cell lacks a citation.

Run: python3 tests/test_adr0002_rubric_frozen.py
"""
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUBRIC = ROOT / "docs" / "adr" / "0002-rubric.yaml"
ADR = ROOT / "docs" / "adr" / "0002-log-backend.md"

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


rubric = yaml.safe_load(RUBRIC.read_text())
adr = ADR.read_text()
dims = rubric["dimensions"]

check(sum(d["weight"] for d in dims) == 100, "weights do not sum to 100")

rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|$", adr, re.MULTILINE)
adr_weights = {n: int(w) for n, w in rows if n not in ("Dimension",)}
yaml_weights = {d["name"]: d["weight"] for d in dims}
check(adr_weights == yaml_weights, f"ADR table {adr_weights} != rubric {yaml_weights}")

check(set(rubric["candidates"]) == {"loki-current", "victorialogs"}, "unexpected candidates")
for d in dims:
    check(set(d["candidates"]) == set(rubric["candidates"]), f"{d['key']}: candidate set mismatch")

unfilled = "<!-- VERDICT: UNFILLED -->" in adr
if rubric["verdict"] is None:
    check(unfilled, "no verdict recorded but ADR lacks the UNFILLED marker")
    check("**Status:** Proposed" in adr, "ADR status must be Proposed while unscored")
    for d in dims:
        for c, cell in d["candidates"].items():
            check(cell["score"] is None, f"{d['key']}/{c}: score set while verdict is empty")
            check(cell["citation"] == "", f"{d['key']}/{c}: citation set while verdict is empty")
else:
    check(not unfilled, "verdict recorded but ADR still has the UNFILLED marker")
    for d in dims:
        for c, cell in d["candidates"].items():
            check(str(cell["citation"]).strip() != "", f"{d['key']}/{c}: no citation")
            s = cell["score"]
            check(s is None or (isinstance(s, int) and 1 <= s <= 5), f"{d['key']}/{c}: bad score {s!r}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("ADR 0002 rubric: frozen, weights agree with the ADR table")
