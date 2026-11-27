#!/usr/bin/env python3
"""Decide whether the check runs of a release-bump PR head allow enqueueing it.

    gh api --paginate .../commits/<sha>/check-runs --jq '.check_runs[]|{id,name,status,conclusion}' \
      | release-bump-checks-ready.py --own-check auto-merge --expect <total_count> \
            --required agy-formal-review,cloudflare-plan,reserved-hosts,validate

When auto-merge.yml did the wait, the job that waited was itself a check run on
the PR head, pending until it exited, so a wait on "every check finished" never
ended (mctlhq/mctl-gitops#2739, #2748). The one check run that may be ignored is
the waiting job's own, matched by its exact name: not a prefix, not a
case-insensitive match, so "auto-merge-lint" still counts. The current caller,
release-bump-enqueue-wait.sh, runs outside the PR head and passes an empty
name, which matches no run.

Reads concatenated JSON objects (one per check run) on stdin. Exit codes:
  0   ready: every other check run completed with success, neutral or skipped,
      and every --required name is present
  10  not yet: something is queued or running, or a required check has not
      reported
  11  a check run failed (failure, cancelled, timed_out, action_required, ...)
  12  unknown: the list could not be read in full or holds an entry the
      script does not understand

Only 0 permits a merge. Unreadable, malformed, truncated (--expect differs from
the number of runs read) and unrecognised states are 12, never "no checks, so
nothing is wrong". Several runs of one name (a re-run) count as the newest one.
"""
import argparse
import json
import sys

READY, WAIT, FAIL, UNKNOWN = 0, 10, 11, 12
PENDING = {"queued", "in_progress", "waiting", "pending", "requested"}
GOOD = {"success", "neutral", "skipped"}


def parse(text):
    dec, i, out = json.JSONDecoder(), 0, []
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return out
        obj, i = dec.raw_decode(text, i)
        out.append(obj)


def evaluate(runs, own, required, expect=None):
    """Return (code, reasons) for a list of check-run dicts."""
    if not isinstance(runs, list):
        return UNKNOWN, ["check runs are not a list"]
    if expect is not None and len(runs) != expect:
        return UNKNOWN, [f"{len(runs)} check runs read, {expect} reported"]
    latest = {}
    for r in runs:
        if not (isinstance(r, dict) and isinstance(r.get("name"), str) and r["name"]
                and isinstance(r.get("id"), int) and isinstance(r.get("status"), str)):
            return UNKNOWN, [f"unreadable check run: {r!r}"]
        if r["name"] == own:
            continue
        if r["name"] not in latest or r["id"] > latest[r["name"]]["id"]:
            latest[r["name"]] = r
    unknown, failed, waiting = [], [], []
    for name, r in sorted(latest.items()):
        st, concl = r["status"], r.get("conclusion")
        if st in PENDING:
            waiting.append(f"{name}: {st}")
        elif st != "completed":
            unknown.append(f"{name}: unknown status {st!r}")
        elif concl in GOOD:
            pass
        elif isinstance(concl, str) and concl:
            failed.append(f"{name}: {concl}")
        else:
            unknown.append(f"{name}: completed without a conclusion")
    for name in required:
        if name not in latest:
            waiting.append(f"{name}: not reported")
    for code, reasons in ((UNKNOWN, unknown), (FAIL, failed), (WAIT, waiting)):
        if reasons:
            return code, reasons
    return READY, []


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--own-check", required=True)
    ap.add_argument("--required", default="")
    ap.add_argument("--expect", type=int)
    a = ap.parse_args(argv)
    try:
        runs = parse(sys.stdin.read())
    except ValueError as e:
        print(f"unknown: check runs are not JSON ({e})")
        return UNKNOWN
    required = [n for n in a.required.split(",") if n]
    code, reasons = evaluate(runs, a.own_check, required, a.expect)
    label = {READY: "ready", WAIT: "wait", FAIL: "fail", UNKNOWN: "unknown"}[code]
    print(label + "".join(f"\n  {r}" for r in reasons))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
