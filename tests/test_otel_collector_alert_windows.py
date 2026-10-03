"""Every `increase(...[W])` in the otel-collector rules must have W < its `for`.

gitops#1189 shipped `increase(...[15m]) > 0` with `for: 5m`. A single scrape's
worth of increase keeps that expression true for the whole fifteen minutes, so
the five-minute hold is passed on the way through and the alert pages for a
spike that is already over. The hold stops being a hold, which is the one thing
it was there to do.

This is a platform-wide lesson, not a one-off: the same shape has been fixed
before in the mctl-telegram rules. The promtool case "a single refused-spans
spike does not fire" proves the behaviour for the two rules that exist today;
this test states the rule itself, so a third rule added later cannot
reintroduce the shape without anyone noticing.

Scoped to this one file deliberately. The other rule files are not audited here
and some legitimately use a long window with no `for:` at all, which is a
different (and fine) construction -- widening the scope is a separate change
with its own review.

Run: python3 tests/test_otel_collector_alert_windows.py
"""
import pathlib
import re
import sys

import yaml

RULES = pathlib.Path(
    "platform-gitops/infra-components/observability/vm-rules/"
    "otel-collector-alerts.yaml")

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
LOOKBACK = re.compile(r"\bincrease\s*\([^)]*\[(\d+)([smhd])\]")


def seconds(duration):
    m = re.fullmatch(r"(\d+)([smhd])", duration.strip())
    assert m, f"unparsable duration {duration!r}"
    return int(m.group(1)) * UNITS[m.group(2)]


doc = yaml.safe_load(RULES.read_text())
failures = []
checked = 0

for group in doc["spec"]["groups"]:
    for rule in group["rules"]:
        windows = LOOKBACK.findall(rule.get("expr", ""))
        if not windows:
            continue
        hold = rule.get("for")
        if hold is None:
            failures.append(
                f"{rule['alert']}: uses increase() with no `for:` -- a single "
                f"scrape then pages immediately")
            continue
        hold_s = seconds(hold)
        for value, unit in windows:
            checked += 1
            window_s = int(value) * UNITS[unit]
            if window_s >= hold_s:
                failures.append(
                    f"{rule['alert']}: increase() lookback {value}{unit} is not "
                    f"shorter than for: {hold} -- a one-scrape spike survives "
                    f"the hold and pages")

if not checked:
    failures.append(
        "no increase() lookbacks found at all -- the regex no longer matches "
        "the rules it is supposed to police")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print(f"otel-collector alert windows: {checked} lookback(s), all shorter than their hold")
