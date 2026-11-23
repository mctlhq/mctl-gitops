#!/usr/bin/env python3
"""Count R2 Class A operations in the current billing cycle and push the figure.

Why this exists: R2 bills Class A operations in whole blocks of one million
above a free million per cycle. The 2026-10-22..11-21 cycle used 1.08M and
was charged $4.50 for the 79,622 operations over the line (invoice
IN-90323939), while the cycle before cost $0.52. The dashboard's default
budget alert is a dollar threshold that only fires after the block is billed,
so nothing warned in time. This reports the count, and
infra-components/observability/vm-rules/r2-ops-budget.yaml alerts on the count
and on where it is heading.

The count comes from the Cloudflare GraphQL Analytics API
(r2OperationsAdaptiveGroups, Account Analytics -> Read, nothing more), summed
over the action types R2 bills as Class A. That reproduced the invoice: 1.08M
counted, 1.08M billed. Deletes are free and Class B is far from its limit, so
neither is pushed.

An action type not in the tables below is counted as Class A and reported in
r2_ops_budget_unclassified_actions: an unknown type must never make the figure
smaller, only possibly larger.

Reading is all or nothing. A failed request, a GraphQL error, a body that is
not the expected shape, or a result that fills the query's row limit all mean
the count could not be observed -- never that it is zero or low. An empty
result is accepted as zero only in the first day of a cycle, when it is
plausible; later it is as suspicious as a failed read, because this account
makes R2 requests every minute.

With --pushgateway the outcome is pushed as job r2_ops_budget and the exit
status says only whether the push got through. A successful read replaces the
whole group (PUT), so a figure that no longer applies, such as the projection
in the first two days of a cycle, cannot outlive its cycle. A failed read
names only read_ok and the run time (POST) and leaves the last good figures
alone: an unknown run must neither lower the count nor erase a high one. That
includes cycle_end, which is what lets the alerts tell, after the cycle has
rolled over, that the count they still hold belongs to the cycle before.
Without --pushgateway: 0 read, 2 could not be determined.

The token comes from CLOUDFLARE_API_TOKEN and is sent only in the
Authorization header.

Usage:
    r2-ops-budget.py --account ID [--cycle-day 22] [--pushgateway URL [--push-job NAME]]
    r2-ops-budget.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
ROW_LIMIT = 1000
FREE_TIER_CLASS_A = 1_000_000
# The cycle starts on the 22nd 00:00 UTC (invoices are dated the 22nd and
# cover "Oct 22-Nov 21").
DEFAULT_CYCLE_DAY = 22
# A projection from a few hours of a 31-day cycle says nothing.
MIN_PROJECTION_SECONDS = 2 * 86400
# Accepting an empty result as zero is only plausible this soon after the
# cycle starts.
EMPTY_OK_SECONDS = 86400

# Billed as Class A (https://developers.cloudflare.com/r2/pricing/).
CLASS_A = {
    "ListBuckets", "PutBucket", "ListObjects", "PutObject", "CopyObject",
    "CompleteMultipartUpload", "CreateMultipartUpload", "ListMultipartUploads",
    "UploadPart", "UploadPartCopy", "ListParts", "PutBucketEncryption",
    "PutBucketCors", "PutBucketLifecycleConfiguration",
}
# Billed as Class B, or free. Anything in neither table counts as Class A.
NOT_CLASS_A = {
    "HeadBucket", "HeadObject", "GetObject", "UsageSummary",
    "GetBucketEncryption", "GetBucketLocation", "GetBucketCors",
    "GetBucketLifecycleConfiguration", "GetObjectLockConfiguration",
    "DeleteObject", "DeleteObjects", "DeleteBucket", "DeleteMultipartUpload",
    "AbortMultipartUpload",
}

QUERY = (
    "query($acct: String!, $start: Time!, $end: Time!) {"
    " viewer { accounts(filter: {accountTag: $acct}) {"
    f" r2OperationsAdaptiveGroups(limit: {ROW_LIMIT},"
    " filter: {datetime_geq: $start, datetime_lt: $end}) {"
    " sum { requests } dimensions { actionType } } } } }"
)


class Unknown(Exception):
    """The count could not be observed; nothing is known about it."""


def cycle_bounds(now: dt.datetime, day: int) -> tuple[dt.datetime, dt.datetime]:
    """[start, end) of the billing cycle containing `now` (UTC)."""
    now = now.astimezone(dt.timezone.utc)
    year, month = now.year, now.month
    if now.day < day:
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    start = dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    return start, dt.datetime(ny, nm, day, tzinfo=dt.timezone.utc)


def http_post(url: str, token: str, payload: dict) -> bytes:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "mctl-r2-ops-budget",
        })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise Unknown(f"the API answered HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Unknown(f"the API could not be reached: {e}") from e


def is_count(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def read_ops(account: str, token: str, start: dt.datetime, end: dt.datetime,
             elapsed: float, post=http_post) -> dict[str, int]:
    """Requests per action type in [start, end)."""
    if not token:
        raise Unknown("CLOUDFLARE_API_TOKEN is not set")
    payload = {"query": QUERY, "variables": {
        "acct": account,
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }}
    try:
        body = json.loads(post(GRAPHQL, token, payload))
    except ValueError as e:
        raise Unknown("the answer is not JSON") from e
    if not isinstance(body, dict):
        raise Unknown("the answer is not an object")
    if body.get("errors"):
        raise Unknown(f"GraphQL errors: {body['errors']!r}"[:300])
    try:
        accounts = body["data"]["viewer"]["accounts"]
        if not isinstance(accounts, list) or len(accounts) != 1:
            raise ValueError
        groups = accounts[0]["r2OperationsAdaptiveGroups"]
        if not isinstance(groups, list):
            raise ValueError
        ops: dict[str, int] = {}
        for g in groups:
            action = g["dimensions"]["actionType"]
            n = g["sum"]["requests"]
            if not isinstance(action, str) or not is_count(n):
                raise ValueError
            ops[action] = ops.get(action, 0) + n
    except (KeyError, TypeError, ValueError) as e:
        raise Unknown("the answer is not the expected shape") from e
    if len(groups) >= ROW_LIMIT:
        # The answer may be cut short: a lower count is not an answer.
        raise Unknown(f"the answer fills the {ROW_LIMIT}-row limit")
    if not ops and elapsed > EMPTY_OK_SECONDS:
        raise Unknown("no R2 operations at all this far into the cycle")
    return ops


def class_a(ops: dict[str, int]) -> tuple[int, int]:
    """(Class A total, number of action types in neither table)."""
    total = unclassified = 0
    for action, n in ops.items():
        if action in NOT_CLASS_A:
            continue
        total += n
        if action not in CLASS_A:
            unclassified += 1
    return total, unclassified


def render_metrics(result: tuple[int, int] | None, start: dt.datetime, end: dt.datetime,
                   now: float) -> str:
    """The Pushgateway body for one run. `result` is None when the read failed."""
    lines = [
        "# HELP r2_ops_budget_read_ok 1 when the cycle's R2 operations could be read, 0 when not.",
        "# TYPE r2_ops_budget_read_ok gauge",
        f"r2_ops_budget_read_ok {0 if result is None else 1}",
        "# TYPE r2_ops_budget_last_run_timestamp_seconds gauge",
        f"r2_ops_budget_last_run_timestamp_seconds {now:.0f}",
    ]
    if result is not None:
        used, unclassified = result
        cycle_len = (end - start).total_seconds()
        elapsed = now - start.timestamp()
        lines += [
            "# TYPE r2_ops_budget_last_read_success_timestamp_seconds gauge",
            f"r2_ops_budget_last_read_success_timestamp_seconds {now:.0f}",
            "# HELP r2_ops_budget_class_a_used R2 Class A operations so far in the billing cycle.",
            "# TYPE r2_ops_budget_class_a_used gauge",
            f"r2_ops_budget_class_a_used {used}",
            "# HELP r2_ops_budget_class_a_free_tier Class A operations included free per cycle.",
            "# TYPE r2_ops_budget_class_a_free_tier gauge",
            f"r2_ops_budget_class_a_free_tier {FREE_TIER_CLASS_A}",
            "# TYPE r2_ops_budget_cycle_start_timestamp_seconds gauge",
            f"r2_ops_budget_cycle_start_timestamp_seconds {start.timestamp():.0f}",
            "# HELP r2_ops_budget_cycle_end_timestamp_seconds When the cycle the figures belong to ends.",
            "# TYPE r2_ops_budget_cycle_end_timestamp_seconds gauge",
            f"r2_ops_budget_cycle_end_timestamp_seconds {end.timestamp():.0f}",
            "# TYPE r2_ops_budget_unclassified_actions gauge",
            f"r2_ops_budget_unclassified_actions {unclassified}",
        ]
        if elapsed >= MIN_PROJECTION_SECONDS:
            lines += [
                "# HELP r2_ops_budget_class_a_projected Class A at the end of the cycle if the pace so far holds.",
                "# TYPE r2_ops_budget_class_a_projected gauge",
                f"r2_ops_budget_class_a_projected {used * cycle_len / elapsed:.0f}",
            ]
    return "\n".join(lines) + "\n"


def push(url: str, job: str, body: str, method: str) -> None:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/metrics/job/{urllib.parse.quote(job, safe='')}",
        data=body.encode(), method=method,
        headers={"Content-Type": "text/plain; version=0.0.4"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status // 100 != 2:
            raise OSError(f"Pushgateway answered HTTP {resp.status}")


def selftest() -> int:
    cases: list[bool] = []

    def check(name: str, ok: bool) -> None:
        cases.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {name}")

    utc = dt.timezone.utc
    d = lambda *a: dt.datetime(*a, tzinfo=utc)  # noqa: E731

    s, e = cycle_bounds(d(2026, 11, 22, 0, 0, 0), 22)
    check("the cycle starts on the day itself", (s, e) == (d(2026, 11, 22), d(2026, 12, 22)))
    s, e = cycle_bounds(d(2026, 12, 3, 12), 22)
    check("a day before the cycle day belongs to the cycle before", (s, e) == (d(2026, 11, 22), d(2026, 12, 22)))
    s, e = cycle_bounds(d(2027, 1, 5), 22)
    check("a cycle runs across the year end", (s, e) == (d(2026, 12, 22), d(2027, 1, 22)))
    s, e = cycle_bounds(d(2026, 12, 25), 22)
    check("a December start ends in January", (s, e) == (d(2026, 12, 22), d(2027, 1, 22)))
    s, e = cycle_bounds(d(2026, 11, 21, 23, 59, 59), 22)
    check("the last second of a cycle is still in it", (s, e) == (d(2026, 10, 22), d(2026, 11, 22)))

    start, end = d(2026, 10, 22), d(2026, 11, 22)
    day10 = 10 * 86400.0

    def rows(**kw):
        return {"data": {"viewer": {"accounts": [{"r2OperationsAdaptiveGroups": [
            {"sum": {"requests": n}, "dimensions": {"actionType": a}} for a, n in kw.items()]}]}}}

    def answer(body, elapsed=day10, token="t"):
        def post(url, tok, payload):
            if isinstance(body, Exception):
                raise body
            return body if isinstance(body, bytes) else json.dumps(body).encode()
        try:
            return read_ops("acct", token, start, end, elapsed, post)
        except Unknown:
            return Unknown

    ok = rows(PutObject=100, ListObjects=50, GetObject=9000, DeleteObject=700, HeadBucket=5)
    check("operations are read per action type",
          answer(ok) == {"PutObject": 100, "ListObjects": 50, "GetObject": 9000, "DeleteObject": 700, "HeadBucket": 5})
    check("a missing token is unknown", answer(ok, token="") is Unknown)
    check("an HTTP failure is unknown", answer(Unknown("HTTP 500")) is Unknown)
    check("a body that is not JSON is unknown", answer(b"<html>") is Unknown)
    check("a GraphQL error is unknown",
          answer({"errors": [{"message": "not authorized"}], "data": None}) is Unknown)
    partial = rows(PutObject=100)
    partial["errors"] = [{"message": "partial failure"}]
    check("errors next to otherwise valid data are unknown, not a lower count", answer(partial) is Unknown)
    check("an answer with data null is unknown", answer({"data": None}) is Unknown)
    check("no accounts is unknown", answer({"data": {"viewer": {"accounts": []}}}) is Unknown)
    check("a row without an action type is unknown",
          answer({"data": {"viewer": {"accounts": [{"r2OperationsAdaptiveGroups": [
              {"sum": {"requests": 5}, "dimensions": {}}]}]}}}) is Unknown)
    check("a negative count is unknown", answer(rows(PutObject=-1)) is Unknown)
    check("a boolean count is unknown", answer(rows(PutObject=True)) is Unknown)
    full = {"data": {"viewer": {"accounts": [{"r2OperationsAdaptiveGroups": [
        {"sum": {"requests": 1}, "dimensions": {"actionType": f"A{i}"}} for i in range(ROW_LIMIT)]}]}}}
    check("an answer that fills the row limit is unknown", answer(full) is Unknown)
    check("an empty answer far into the cycle is unknown, not zero", answer(rows()) is Unknown)
    check("an empty answer in the first hours of a cycle is zero", answer(rows(), elapsed=3600.0) == {})

    total, unclassified = class_a({"PutObject": 100, "ListObjects": 50, "GetObject": 9000,
                                   "DeleteObject": 700, "HeadBucket": 5})
    check("only Class A is summed", (total, unclassified) == (150, 0))
    total, unclassified = class_a({"PutObject": 100, "BrandNewAction": 7, "DeleteObject": 1})
    check("an unknown action type counts as Class A and is reported", (total, unclassified) == (107, 1))
    total, _ = class_a({"CompleteMultipartUpload": 1, "CreateMultipartUpload": 2, "UploadPart": 4, "CopyObject": 8})
    check("multipart and copy operations are Class A", total == 15)
    check("the tables do not overlap", not (CLASS_A & NOT_CLASS_A))

    now = start.timestamp() + day10
    body = render_metrics((850_000, 0), start, end, now)
    check("a read pushes read_ok 1, the count, the free tier and a success time",
          "r2_ops_budget_read_ok 1\n" in body and "r2_ops_budget_class_a_used 850000\n" in body
          and "r2_ops_budget_class_a_free_tier 1000000\n" in body
          and f"r2_ops_budget_last_read_success_timestamp_seconds {now:.0f}\n" in body)
    check("a read pushes the end of the cycle its figures belong to",
          f"r2_ops_budget_cycle_end_timestamp_seconds {end.timestamp():.0f}\n" in body)
    cycle_len = (end - start).total_seconds()
    check("the projection scales the pace so far to the whole cycle",
          f"r2_ops_budget_class_a_projected {850_000 * cycle_len / day10:.0f}\n" in body)
    early = render_metrics((1000, 0), start, end, start.timestamp() + 3600)
    check("no projection in the first two days", "projected" not in early)
    bad = render_metrics(None, start, end, now)
    check("a failed read pushes read_ok 0 and nothing about the count or success",
          "r2_ops_budget_read_ok 0\n" in bad and "class_a_used" not in bad
          and "last_read_success" not in bad and "projected" not in bad
          and "cycle_end" not in bad)
    return 0 if all(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--account")
    ap.add_argument("--cycle-day", type=int, default=DEFAULT_CYCLE_DAY)
    ap.add_argument("--pushgateway", help="push the outcome to this Pushgateway base URL")
    ap.add_argument("--push-job", default="r2_ops_budget")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.account:
        ap.error("--account is required")
    if not 1 <= a.cycle_day <= 28:
        ap.error("--cycle-day must be 1..28 so every month has it")
    now_dt = dt.datetime.now(dt.timezone.utc)
    start, end = cycle_bounds(now_dt, a.cycle_day)
    now = now_dt.timestamp()
    result: tuple[int, int] | None
    code = 0
    try:
        ops = read_ops(a.account, os.environ.get("CLOUDFLARE_API_TOKEN", ""), start,
                       min(end, now_dt + dt.timedelta(minutes=1)), now - start.timestamp())
        result = class_a(ops)
        print(f"cycle {start:%Y-%m-%d}..{end:%Y-%m-%d}: {result[0]} Class A of {FREE_TIER_CLASS_A} free"
              f" ({result[1]} unclassified action types)")
    except Unknown as e:
        print(f"UNKNOWN the cycle's operations could not be read: {e}")
        result, code = None, 2
    except Exception as e:  # a crash here proves nothing about the count
        print(f"UNKNOWN the check failed: {type(e).__name__}: {e}")
        result, code = None, 2
    if a.pushgateway:
        # Once pushed, the metric reports the outcome, and a failed Job means
        # only that it never got out. See cloudflare-portal-health.py.
        try:
            push(a.pushgateway, a.push_job, render_metrics(result, start, end, now),
                 "POST" if result is None else "PUT")
        except Exception as e:  # noqa: BLE001
            print(f"UNKNOWN could not push to {a.pushgateway}: {type(e).__name__}: {e}")
            return 2 if code == 0 else code
        print(f"pushed to job {a.push_job}")
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
