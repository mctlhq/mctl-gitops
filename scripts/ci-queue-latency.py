#!/usr/bin/env python3
"""CI queue latency report for mctl-gitops (mctlhq/mctl-gitops#2993, ADR 0004).

Read-only. Needs `gh` authenticated with a token that can read Actions and
pull requests; it never writes. Prints a Markdown table for the ADR.

    scripts/ci-queue-latency.py --since 2026-11-22T00:00:00Z --until 2026-11-24T00:00:00Z
    scripts/ci-queue-latency.py --fixture tests/fixtures/ci_queue_latency/window.json

Metrics:
  a. merge_group run: created_at -> first job started_at
  b. PR merged through the queue: added_to_merge_queue event -> merged_at
  c. release-deploy run: created_at -> merge of its release-bump/<component>-<tag> PR
  d. runs cancelled before any job started (superseded while queued)

"Could not observe" is never "zero": a run whose jobs could not be read is
counted under `unknown`, and any failed API read aborts the report with exit 2.
"""
import argparse
import json
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

REPO = "mctlhq/mctl-gitops"
RELEASE_WORKFLOW = "Release & Deploy"  # workflow name as the runs API reports it


class ReadError(Exception):
    """An API read failed or returned a malformed body (never an empty result)."""


def ts(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def seconds(start, end):
    return (ts(end) - ts(start)).total_seconds()


def first_job_start(jobs):
    """Earliest started_at among jobs, or None when no job ever started."""
    starts = [j["started_at"] for j in jobs if j.get("started_at")]
    return min(starts) if starts else None


def summarize(values):
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"n": len(ordered), "p50": statistics.median(ordered), "p95": p95, "max": ordered[-1]}


def needs_jobs(run):
    """Only these runs enter a metric, so only their jobs are fetched."""
    return (run["event"] == "merge_group" or run.get("name") == RELEASE_WORKFLOW
            or run.get("conclusion") == "cancelled")


def report(data):
    """Pure function: window data (see collect) -> metrics dict."""
    runs, jobs = data["runs"], data["jobs"]
    unknown = []
    merge_group, release_runs, cancelled_unstarted = [], [], []

    for run in runs:
        rid = str(run["id"])
        if not needs_jobs(run):
            continue
        if rid not in jobs:
            unknown.append(run["id"])
            continue
        start = first_job_start(jobs[rid])
        if run["event"] == "merge_group" and start:
            merge_group.append(seconds(run["created_at"], start))
        if run.get("conclusion") == "cancelled" and start is None:
            cancelled_unstarted.append(run["id"])
        if run.get("name") == RELEASE_WORKFLOW:
            release_runs.append(run)

    queue = []
    for pr in data["prs"]:
        events = [e["created_at"] for e in data["timelines"].get(str(pr["number"]), [])
                  if e.get("event") == "added_to_merge_queue"]
        if events and pr.get("merged_at"):
            queue.append(seconds(min(events), pr["merged_at"]))

    # release-deploy names the bump branch release-bump/<basename of the image>-<tag>
    # (release-deploy.yaml), and the runs API does not return the image, so a run
    # is matched on the "-<tag>" suffix. Several components can share one image and
    # one tag; they then share one bump PR, and the earliest merge after dispatch wins.
    bumps = sorted((ts(p["merged_at"]), p["head_ref"]) for p in data["prs"]
                   if p.get("merged_at") and p.get("head_ref", "").startswith("release-bump/"))
    release, release_unmatched = [], 0
    for run in release_runs:
        parts = run["display_title"].split()
        if len(parts) < 3:
            unknown.append(run["id"])
            continue
        tag = parts[2]
        merged = next((m for m, ref in bumps if ref.endswith(f"-{tag}") and m >= ts(run["created_at"])), None)
        if merged is None:
            release_unmatched += 1  # no bump PR merged in the window; not a zero-latency release
            continue
        release.append((merged - ts(run["created_at"])).total_seconds())

    return {
        "merge_group_start": summarize(merge_group),
        "queue_enqueue_to_merge": summarize(queue),
        "release_dispatch_to_bump_merge": summarize(release),
        "release_runs_without_matched_bump": release_unmatched,
        "cancelled_before_start": len(cancelled_unstarted),
        "unknown_runs": len(unknown),
        "runs_total": len(runs),
    }


def fmt(sec):
    sec = int(sec)
    return f"{sec // 3600}h{sec % 3600 // 60:02d}m{sec % 60:02d}s" if sec >= 3600 else f"{sec // 60}m{sec % 60:02d}s"


def render(metrics, window):
    rows = [("merge-group run created -> first job started", "merge_group_start"),
            ("PR enqueue -> merged", "queue_enqueue_to_merge"),
            ("release-deploy dispatch -> bump PR merged", "release_dispatch_to_bump_merge")]
    out = [f"Window: {window}", "", "| Metric | n | p50 | p95 | max |", "|---|---|---|---|---|"]
    for label, key in rows:
        m = metrics[key]
        if m["n"]:
            out.append(f"| {label} | {m['n']} | {fmt(m['p50'])} | {fmt(m['p95'])} | {fmt(m['max'])} |")
        else:
            out.append(f"| {label} | 0 | not measured | not measured | not measured |")
    out += ["", f"Release runs without a matched bump PR in the window (excluded): "
                f"{metrics['release_runs_without_matched_bump']}",
            f"Runs cancelled before any job started: {metrics['cancelled_before_start']}",
            f"Runs with unreadable jobs (excluded, not counted as zero): {metrics['unknown_runs']}",
            f"Runs in window: {metrics['runs_total']}"]
    return "\n".join(out)


def gh_json(path, *params, paginate=True):
    """Returns a list of pages (one page when paginate is False)."""
    # -f/-F make `gh api` default to POST; every read here must be an explicit GET.
    cmd = ["gh", "api", "--method", "GET"] + (["--paginate", "--slurp"] if paginate else []) + [path, *params]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ReadError(f"gh api {path} failed: {r.stderr.strip()}")
    try:
        body = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise ReadError(f"gh api {path}: malformed body: {e}")
    pages = body if paginate else [body]
    if not isinstance(pages, list):
        raise ReadError(f"gh api {path}: unexpected shape")
    return pages


def merged_prs(since, until):
    """Merged PRs in the window. The listing is newest-updated first and merged_at
    <= updated_at, so it stops at the first page whose last PR was updated before
    `since` instead of reading the repository's whole closed-PR history."""
    prs, page = [], 1
    while True:
        (items,) = gh_json(f"repos/{REPO}/pulls", "-f", "state=closed", "-f", "per_page=100",
                           "-f", "sort=updated", "-f", "direction=desc", "-f", f"page={page}", paginate=False)
        if not isinstance(items, list):
            raise ReadError("gh api pulls: unexpected shape")
        for p in items:
            if p.get("merged_at") and since <= p["merged_at"] <= until:
                prs.append({"number": p["number"], "merged_at": p["merged_at"], "head_ref": p["head"]["ref"]})
        if not items or items[-1]["updated_at"] < since:
            return prs
        page += 1


def chunks(since, until, hours=6):
    """Split the window so each runs query stays under the API's 1000-result cap."""
    start, end, step = ts(since), ts(until), timedelta(hours=hours)
    while start < end:
        stop = min(start + step, end)
        yield start.strftime("%Y-%m-%dT%H:%M:%SZ"), stop.strftime("%Y-%m-%dT%H:%M:%SZ")
        start = stop


def collect_runs(since, until):
    pages = gh_json(f"repos/{REPO}/actions/runs", "-f", f"created={since}..{until}", "-f", "per_page=100")
    got = sum(len(pg["workflow_runs"]) for pg in pages)
    # The runs API serves at most 1000 results per query; a larger total_count means
    # the list would be a silently shorter one, so refuse instead.
    if pages and pages[0]["total_count"] > got:
        raise ReadError(f"{since}..{until} holds {pages[0]['total_count']} runs but the API "
                        f"returned {got}; use a narrower window")
    return [{"id": r["id"], "event": r["event"], "name": r["name"], "display_title": r["display_title"],
             "created_at": r["created_at"], "conclusion": r["conclusion"]}
            for pg in pages for r in pg["workflow_runs"]]


def collect(since, until):
    runs = {}
    for lo, hi in chunks(since, until):
        for r in collect_runs(lo, hi):
            runs[r["id"]] = r
    runs = list(runs.values())
    def fetch_jobs(run):
        pages = gh_json(f"repos/{REPO}/actions/runs/{run['id']}/jobs", "-f", "per_page=100")
        return str(run["id"]), [{"started_at": j["started_at"]} for p in pages for j in p["jobs"]]

    # A failed read raises out of map(): the whole report aborts, never a shorter list.
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = dict(pool.map(fetch_jobs, [r for r in runs if needs_jobs(r)]))
    prs = merged_prs(since, until)
    timelines = {}
    for p in prs:
        pages = gh_json(f"repos/{REPO}/issues/{p['number']}/timeline", "-f", "per_page=100")
        timelines[str(p["number"])] = [{"event": e.get("event"), "created_at": e.get("created_at")}
                                       for page in pages for e in page]
    return {"runs": runs, "jobs": jobs, "prs": prs, "timelines": timelines}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--fixture", help="read recorded window data instead of calling gh")
    a = ap.parse_args(argv)
    try:
        if a.fixture:
            with open(a.fixture) as f:
                data = json.load(f)
            window = a.fixture
        else:
            if not (a.since and a.until):
                ap.error("--since and --until are required without --fixture")
            data, window = collect(a.since, a.until), f"{a.since} .. {a.until}"
        print(render(report(data), window))
    except (ReadError, OSError, KeyError, ValueError) as e:
        print(f"ci-queue-latency: cannot observe the window: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
