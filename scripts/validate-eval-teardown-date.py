#!/usr/bin/env python3
"""Fail when the observability-eval sandbox (issue #903 / #1280) is open
past its declared teardown date, or opened without one.

`platform-gitops/bootstrap/values.yaml`'s `otelCollector.eval.teardownAfter`
is a greppable annotation (`eval-namespace.yaml`'s
`mctl.ai/teardown-after`), not something anything enforced until now: a
two-week spike namespace with no active enforcement is exactly the kind of
thing that becomes silently permanent.

Rule, only while `otelCollector.eval.enabled` is `true`:
  - `teardownAfter` must parse as `YYYY-MM-DD` (datetime.date.fromisoformat);
  - it must be `>= today`;
  - it must be `<= today + 14 days`.

While `eval.enabled` is not `true`, this passes regardless of
`teardownAfter` -- the sandbox is closed, so the value is free to be `""`.

`--today YYYY-MM-DD` injects the reference date (used by --selftest, so the
selftest fixtures are deterministic and do not go stale as real time moves
on). Because `.github/workflows/validate-manifests.yml` also triggers on
`push: [main]`, an expired sandbox turns main red even with no open PR --
the same reasoning the workflow's header comment gives for the openclaw
version-pin check.

Run with --selftest to prove the detector still detects (all five T3
branches from the proposal's tasks.md).
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALUES_FILE = ROOT / "platform-gitops/bootstrap/values.yaml"

MAX_WINDOW_DAYS = 14


def _today(today_override: str | None) -> datetime.date:
    if today_override:
        return datetime.date.fromisoformat(today_override)
    return datetime.date.today()


def check_values(doc: dict, today: datetime.date) -> str | None:
    """Return an error message, or None if the sandbox's teardown state is OK."""
    otel = doc.get("otelCollector") if isinstance(doc, dict) else None
    eval_block = otel.get("eval") if isinstance(otel, dict) else None
    if not isinstance(eval_block, dict):
        # No eval block at all -- nothing to enforce.
        return None

    if eval_block.get("enabled") is not True:
        # Sandbox closed: teardownAfter is free to be anything, including "".
        return None

    teardown_after = eval_block.get("teardownAfter")
    if not teardown_after:
        return (
            "otelCollector.eval.enabled is true but teardownAfter is empty -- "
            "set it to a YYYY-MM-DD date at most 14 days out in the same commit "
            "that opens the sandbox"
        )

    try:
        teardown_date = datetime.date.fromisoformat(str(teardown_after))
    except ValueError:
        return (
            f"otelCollector.eval.teardownAfter={teardown_after!r} is not a "
            "YYYY-MM-DD date"
        )

    if teardown_date < today:
        return (
            f"otelCollector.eval.teardownAfter={teardown_after} has passed "
            f"(today is {today.isoformat()}) while otelCollector.eval.enabled "
            "is still true -- run the one-commit teardown documented in "
            "docs/runbooks/tracing-bake-off.md"
        )

    max_date = today + datetime.timedelta(days=MAX_WINDOW_DAYS)
    if teardown_date > max_date:
        return (
            f"otelCollector.eval.teardownAfter={teardown_after} is more than "
            f"{MAX_WINDOW_DAYS} days out from today ({today.isoformat()}) -- "
            "the sandbox window is capped at 14 days"
        )

    return None


def _values(enabled: bool, teardown_after: str) -> dict:
    return {"otelCollector": {"eval": {"enabled": enabled, "teardownAfter": teardown_after}}}


def selftest() -> int:
    """Prove all five T3 branches from tasks.md."""
    today = datetime.date(2026, 9, 24)

    cases = [
        ("disabled + empty teardownAfter passes", _values(False, ""), True),
        ("enabled + 7 days out passes", _values(True, (today + datetime.timedelta(days=7)).isoformat()), True),
        ("enabled + empty teardownAfter fails", _values(True, ""), False),
        ("enabled + yesterday fails", _values(True, (today - datetime.timedelta(days=1)).isoformat()), False),
        ("enabled + 30 days out fails (>14d bound)", _values(True, (today + datetime.timedelta(days=30)).isoformat()), False),
    ]

    ok = True
    for label, doc, should_pass in cases:
        err = check_values(doc, today)
        passed = err is None
        if passed != should_pass:
            ok = False
            print(f"selftest FAIL: {label}: expected pass={should_pass}, got pass={passed} (err={err!r})", file=sys.stderr)

    # Also prove a malformed date string is refused, not silently accepted.
    err = check_values(_values(True, "not-a-date"), today)
    if err is None:
        ok = False
        print("selftest FAIL: a malformed teardownAfter date must fail, not pass", file=sys.stderr)

    if not ok:
        return 1

    print(
        "selftest OK: detector fires on missing/expired/out-of-window "
        "teardownAfter, stays quiet while eval.enabled is false, and passes "
        "a valid within-14-day date"
    )
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()

    today_override = None
    if "--today" in argv:
        idx = argv.index("--today")
        if idx + 1 >= len(argv):
            print("--today requires a YYYY-MM-DD argument", file=sys.stderr)
            return 2
        today_override = argv[idx + 1]

    if not VALUES_FILE.is_file():
        print(f"{VALUES_FILE} not found -- refusing to pass vacuously", file=sys.stderr)
        return 2

    doc = yaml.safe_load(VALUES_FILE.read_text())
    today = _today(today_override)
    err = check_values(doc, today)
    if err:
        print(f"::error::{err}", file=sys.stderr)
        return 1

    print("OK: observability-eval sandbox teardown date is within policy (or the sandbox is closed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
