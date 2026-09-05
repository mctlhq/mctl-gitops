#!/usr/bin/env python3
"""Aggregate Claude and Agy's PR review verdicts into one commit status.

`mctl-gitops#1038` merged on Claude's single approving review while Agy — the
second, async reviewer wired via `.github/workflows/agy-review.yml` — did not
finish until four minutes later and found a real P2 (`#1039`). Branch
protection had no concept of "did every configured reviewer finish for this
exact head" or "did any of them find a blocker", so an async reviewer
answering after merge was invisible to it.

`.github/workflows/review-gate.yml` calls this script to decide the
`review-gate` commit status: `pending` while a required reviewer's run for
the PR's *current* head SHA has not completed, `failure` if a completed run
did not conclude success or found a P1/P2, `success` only once every
required reviewer is terminal and clean for that exact head.

Confirmed against real payloads pulled from this repo's own PR history
(proposal task 1 — supersedes the recorded assumption in `requirements.md`'s
Open questions, which could not see the reusable workflows' output from a
clone alone):

- Claude posts a `pulls/{n}/reviews` entry whose `commit_id` is the exact
  head SHA it reviewed (`claude[bot]`, state `APPROVED` or
  `CHANGES_REQUESTED`) — verified on `#1038`, `#1048`, `#1042`, `#1046`.
  `CHANGES_REQUESTED` already means "has a P1/P2 finding" per that reusable
  workflow's own convention (its review body literally reads "Has P1/P2
  findings, changes requested: ..."); an `APPROVED` review's body reads "No
  P1/P2 findings...". This makes the review `state` itself the P1/P2 signal
  — no need to parse inline-comment severity badges. Those badges do not
  exist: inline review comments are plain `P1:` / `**P2**` / `P3:` text
  (verified on `#1042`/`#1048`), but the review-level state already
  aggregates them, which is a more robust signal than re-parsing free text.
- Agy posts as `github-actions[bot]` with the `<!-- agy-review -->` marker
  (confirmed) plus a machine-readable verdict marker as the last line of the
  comment: `<!-- VERDICT: PASS -->`, `<!-- VERDICT: FAIL:P1 -->`,
  `<!-- VERDICT: FAIL:P2 -->`, or `<!-- VERDICT: FAIL:P1,P2 -->` (confirmed
  both from real comments on `#1038`, `#1043`, `#1045`, `#1046`, `#1054` and
  from the reusable workflow's own source at
  `mctlhq/.github/.github/workflows/agy-review.yml`, which defines all four
  forms and treats a missing/malformed tag as fail-closed itself). This is
  used directly instead of parsing the free-text `**Severity:** P1` lines
  `design.md` anticipated, since it is the exact signal being decided on
  and it is more precise than either bot's own job conclusion: with this
  proposal's paired `blocking: true` flip (task 4), Agy's own job now also
  fails its Actions run on a FAIL verdict, so a failed run and a FAIL
  comment usually coincide — but the comment, when present, still gives a
  specific reason (which severities) instead of a bare "run failed". A
  reviewer run that completes without ever posting a comment at all, or
  whose last line does not match one of the four exact forms above (e.g.
  "agy run failed on this PR; see the workflow log." — observed on `#1042`
  — carries no verdict marker), is treated as reviewer failure, not
  success — fail closed, not silent pass.
- Agy's comment carries no head SHA of its own, so it is bound to the
  current head via the matching `actions/runs?head_sha=` entry's
  `created_at` as a window start (the time-window heuristic `design.md`
  describes), rather than via `commit_id` as for Claude's reviews.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"

CLAUDE_LOGIN = "claude[bot]"
CLAUDE_WORKFLOW_PATH = ".github/workflows/claude-review.yml"
AGY_LOGIN = "github-actions[bot]"
AGY_WORKFLOW_PATH = ".github/workflows/agy-review.yml"
AGY_MARKER = "<!-- agy-review -->"

VERDICT_RE = re.compile(r"<!--\s*VERDICT:\s*(PASS|FAIL:P[12](?:,P[12])*)\s*-->")
DEADLINE_RE = re.compile(r"deadline ([0-9T:+\-Z]+)")
DEADLINE_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Mirrors deploy-signal.py's DEFAULT_GRACE_MINUTES precedent for "how long is
# a legitimate delay vs. a stall worth failing closed on" in this same repo
# (requirements.md's recorded assumption for "reviewer never responded").
DEFAULT_GRACE_MINUTES = 45

CONTEXT = "review-gate"

REQUIRED_REVIEWERS = ("claude-review", "agy-review")


def _next_link(link_header):
    """Parse the RFC 5988 Link header GitHub uses for pagination."""
    if not link_header:
        return None
    for part in link_header.split(","):
        section = part.split(";")
        if len(section) < 2:
            continue
        url = section[0].strip()
        if url.startswith("<") and url.endswith(">"):
            url = url[1:-1]
        rel = section[1].strip()
        if rel == 'rel="next"':
            return url
    return None


def _request(method, path, token, data=None):
    url = path if path.startswith("http") else f"{API}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "review-gate",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        link = resp.headers.get("Link")
    parsed = json.loads(raw) if raw else None
    return parsed, link


def gh_get_all(path, token):
    """GET with Link-header pagination, returning the concatenated list.

    `actions/runs` responses wrap the list in a `workflow_runs` key; every
    other list endpoint used here (reviews, issue comments, pulls) returns a
    bare JSON array. Both shapes are handled so callers never see the
    difference.
    """
    out = []
    next_path = path
    while next_path:
        parsed, link = _request("GET", next_path, token)
        if isinstance(parsed, dict) and "workflow_runs" in parsed:
            out.extend(parsed["workflow_runs"])
        elif isinstance(parsed, list):
            out.extend(parsed)
        else:
            return parsed
        next_path = _next_link(link)
    return out


def get_pr(repo, pr, token):
    parsed, _ = _request("GET", f"/repos/{repo}/pulls/{pr}", token)
    return parsed


def get_reviews(repo, pr, token):
    return gh_get_all(f"/repos/{repo}/pulls/{pr}/reviews?per_page=100", token)


def get_issue_comments(repo, pr, token):
    return gh_get_all(f"/repos/{repo}/issues/{pr}/comments?per_page=100", token)


def list_open_prs(repo, token):
    return gh_get_all(f"/repos/{repo}/pulls?state=open&per_page=100", token)


def latest_run_for_workflow(repo, head_sha, workflow_path, token):
    """The newest Actions run of `workflow_path` for `head_sha`, or None.

    Queried from Actions run metadata rather than parsed out of comment
    text — this is what gives exact-head binding "for free" (design.md,
    Alternative 2) without needing either reviewer's comment to embed its
    own head SHA or run ID.
    """
    runs = gh_get_all(f"/repos/{repo}/actions/runs?head_sha={head_sha}&per_page=100", token)
    matching = [r for r in runs if r.get("path") == workflow_path]
    if not matching:
        return None
    return max(matching, key=lambda r: r["created_at"])


def latest_status(repo, sha, token, context=CONTEXT):
    statuses = gh_get_all(f"/repos/{repo}/commits/{sha}/statuses?per_page=100", token)
    matching = [s for s in statuses if s.get("context") == context]
    if not matching:
        return None
    return max(matching, key=lambda s: s["created_at"])


def post_status(repo, sha, state, description, token, context=CONTEXT, target_url=None):
    data = {"state": state, "description": description[:140], "context": context}
    if target_url:
        data["target_url"] = target_url
    _request("POST", f"/repos/{repo}/statuses/{sha}", token, data=data)


def claude_verdict(repo, pr, head_sha, token):
    """Returns (state, reason) where state is pending/success/failure."""
    run = latest_run_for_workflow(repo, head_sha, CLAUDE_WORKFLOW_PATH, token)
    if run is None:
        return "pending", "Claude PR review has not started for this head yet"
    if run.get("status") != "completed":
        return "pending", "Claude PR review is still running for this head"
    if run.get("conclusion") != "success":
        return "failure", (
            f"Claude PR review run concluded {run.get('conclusion')} "
            "(tooling failure, not a clean review)"
        )
    reviews = [
        r
        for r in get_reviews(repo, pr, token)
        if r.get("user", {}).get("login") == CLAUDE_LOGIN
        and r.get("commit_id") == head_sha
        and r.get("state") in ("APPROVED", "CHANGES_REQUESTED")
    ]
    if not reviews:
        return "failure", (
            "Claude PR review job completed but posted no APPROVED/CHANGES_REQUESTED "
            "review for this exact head (fail closed)"
        )
    latest = max(reviews, key=lambda r: r["submitted_at"])
    if latest["state"] == "CHANGES_REQUESTED":
        return "failure", "Claude PR review requested changes (P1/P2 finding)"
    return "success", "Claude PR review approved with no P1/P2 findings"


def agy_verdict(repo, pr, head_sha, token):
    """Returns (state, reason).

    Reads the posted comment even when the Actions run itself did not
    conclude `success`: since the paired `blocking: true` flip (task 4)
    makes Agy's own job fail its run on a FAIL verdict, a failed run and a
    FAIL comment usually coincide, and the comment (when present) gives a
    specific, more useful reason than a bare "run failed". Either way the
    overall state is `failure` unless the run succeeded AND the comment says
    PASS -- a clean verdict cannot rescue a run that failed for some other,
    unexplained reason.
    """
    run = latest_run_for_workflow(repo, head_sha, AGY_WORKFLOW_PATH, token)
    if run is None:
        return "pending", "Agy PR review has not started for this head yet"
    if run.get("status") != "completed":
        return "pending", "Agy PR review is still running for this head"

    comments = [
        c
        for c in get_issue_comments(repo, pr, token)
        if c.get("user", {}).get("login") == AGY_LOGIN
        and AGY_MARKER in (c.get("body") or "")
        and c.get("created_at", "") >= run["created_at"]
    ]
    if not comments:
        return "failure", (
            f"Agy PR review run concluded {run.get('conclusion')} and posted no "
            "marked review comment for this exact head (fail closed)"
        )
    latest = max(comments, key=lambda c: c["created_at"])
    match = VERDICT_RE.search(latest.get("body") or "")
    if not match:
        return "failure", (
            f"Agy PR review run concluded {run.get('conclusion')} with no parseable "
            "<!-- VERDICT --> marker in its comment (fail closed)"
        )
    verdict = match.group(1)
    if verdict == "PASS":
        if run.get("conclusion") != "success":
            return "failure", (
                f"Agy PR review run concluded {run.get('conclusion')} despite a clean "
                "verdict comment (tooling failure, not a clean review)"
            )
        return "success", "Agy PR review found no P1/P2"
    return "failure", f"Agy PR review found P1/P2 findings ({verdict.split(':', 1)[1]})"


def evaluate(repo, pr, token, override_head_sha=None):
    """Combine both reviewers' verdicts for the PR's live head.

    `override_head_sha` is the head SHA the caller's triggering event was
    for (a `workflow_run.head_sha`). If it no longer matches the PR's live
    head, a later push has already superseded it — this run has nothing
    left to say and must not post a verdict for a head that is no longer
    current (the new-push invalidation acceptance criterion).
    """
    pr_obj = get_pr(repo, pr, token)
    head_sha = pr_obj["head"]["sha"]
    if override_head_sha and override_head_sha != head_sha:
        return {
            "state": "stale",
            "head_sha": head_sha,
            "message": (
                f"event head {override_head_sha} no longer matches PR's live head "
                f"{head_sha}; superseded, posting nothing"
            ),
        }
    results = {
        "claude-review": claude_verdict(repo, pr, head_sha, token),
        "agy-review": agy_verdict(repo, pr, head_sha, token),
    }
    failing = [f"{name}: {reason}" for name, (state, reason) in results.items() if state == "failure"]
    if failing:
        return {"state": "failure", "head_sha": head_sha, "message": "; ".join(failing)}
    pending = [name for name, (state, _reason) in results.items() if state == "pending"]
    if pending:
        return {"state": "pending", "head_sha": head_sha, "message": f"waiting on: {', '.join(pending)}"}
    clean = "; ".join(reason for _state, reason in results.values())
    return {"state": "success", "head_sha": head_sha, "message": clean}


def cmd_pending(repo, pr, token, grace_minutes):
    pr_obj = get_pr(repo, pr, token)
    head_sha = pr_obj["head"]["sha"]
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=grace_minutes)).strftime(DEADLINE_FMT)
    description = f"waiting on {', '.join(REQUIRED_REVIEWERS)} (deadline {deadline})"
    post_status(repo, head_sha, "pending", description, token)
    print(f"posted pending for {head_sha}: {description}")
    return 0


def cmd_evaluate(repo, pr, token, event_head_sha):
    result = evaluate(repo, pr, token, override_head_sha=event_head_sha)
    if result["state"] == "stale":
        print(result["message"])
        return 0
    if result["state"] == "pending":
        # Leave the existing pending status (with its deadline) alone; the
        # other trigger fires the evaluator again once the missing run
        # completes. Nothing to post here.
        print(f"still pending for {result['head_sha']}: {result['message']}")
        return 0
    post_status(repo, result["head_sha"], result["state"], result["message"], token)
    print(f"posted {result['state']} for {result['head_sha']}: {result['message']}")
    return 0


def cmd_sweep(repo, token, grace_minutes):
    prs = list_open_prs(repo, token)
    flipped = 0
    for pr_obj in prs:
        pr = pr_obj["number"]
        head_sha = pr_obj["head"]["sha"]
        status = latest_status(repo, head_sha, token)
        if status is None or status.get("state") != "pending":
            continue
        match = DEADLINE_RE.search(status.get("description") or "")
        if not match:
            continue
        deadline = datetime.strptime(match.group(1), DEADLINE_FMT).replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < deadline:
            continue
        results = {
            "claude-review": claude_verdict(repo, pr, head_sha, token),
            "agy-review": agy_verdict(repo, pr, head_sha, token),
        }
        missing = [name for name, (state, _reason) in results.items() if state == "pending"]
        if not missing:
            # Both reviewers actually reached a terminal state since the
            # pending status was posted; let the evaluate path (which will
            # still fire, or already has) report the real verdict rather
            # than guessing one here.
            continue
        description = f"timed out waiting on: {', '.join(missing)} (past deadline {match.group(1)})"
        post_status(repo, head_sha, "failure", description, token)
        flipped += 1
        print(f"PR #{pr}: flipped {head_sha} to failure ({description})")
    print(f"swept {len(prs)} open PR(s), flipped {flipped}")
    return 0


def self_test():
    """A checker that has never been seen to fail is not known to work.

    Exercises every verdict branch against fixture data, with every network
    call monkeypatched out — no live `gh`/HTTP calls, per task 2's DoD.
    """
    g = globals()
    patched = (
        "get_pr",
        "latest_run_for_workflow",
        "get_reviews",
        "get_issue_comments",
        "post_status",
        "latest_status",
        "list_open_prs",
    )
    real = {name: g[name] for name in patched}
    posted = []

    def fake_post_status(repo, sha, state, description, token, context=CONTEXT, target_url=None):
        posted.append({"repo": repo, "sha": sha, "state": state, "description": description})

    def run(status="completed", conclusion="success", created_at="2026-09-04T13:16:22Z"):
        return {"status": status, "conclusion": conclusion, "created_at": created_at}

    def review(state, commit_id="HEAD", submitted_at="2026-09-04T13:17:38Z"):
        return {"user": {"login": CLAUDE_LOGIN}, "state": state, "commit_id": commit_id, "submitted_at": submitted_at}

    def agy_comment(verdict, created_at="2026-09-04T13:22:06Z"):
        marker = "" if verdict is None else f"\n<!-- VERDICT: {verdict} -->\n"
        body = f"{AGY_MARKER}\n## Antigravity (agy) review — informational\n{marker}"
        return {"user": {"login": AGY_LOGIN}, "created_at": created_at, "body": body}

    def check(name, condition):
        if not condition:
            print(f"SELF-TEST FAILED: {name}")
            return False
        print(f"  {name}")
        return True

    ok = True
    try:
        g["post_status"] = fake_post_status
        g["get_pr"] = lambda repo, pr, token: {"head": {"sha": "HEAD"}}

        # 1. Neither reviewer has a run yet for this head.
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: None
        g["get_reviews"] = lambda repo, pr, token: []
        g["get_issue_comments"] = lambda repo, pr, token: []
        result = evaluate("o/r", 1, None)
        ok &= check("pending while neither reviewer has started", result["state"] == "pending")

        # 2. Both reviewers terminal and clean.
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: run()
        g["get_reviews"] = lambda repo, pr, token: [review("APPROVED")]
        g["get_issue_comments"] = lambda repo, pr, token: [agy_comment("PASS")]
        result = evaluate("o/r", 1, None)
        ok &= check("success once both reviewers are terminal and clean", result["state"] == "success")

        # 3. Claude alone finds a P1/P2 -> failure, even with Agy clean.
        g["get_reviews"] = lambda repo, pr, token: [review("CHANGES_REQUESTED")]
        result = evaluate("o/r", 1, None)
        ok &= check(
            "failure when Claude requests changes",
            result["state"] == "failure" and "claude-review" in result["message"],
        )
        g["get_reviews"] = lambda repo, pr, token: [review("APPROVED")]

        # 4. Agy alone finds a P2 -> failure, even with Claude clean.
        g["get_issue_comments"] = lambda repo, pr, token: [agy_comment("FAIL:P2")]
        result = evaluate("o/r", 1, None)
        ok &= check(
            "failure when Agy finds a P2",
            result["state"] == "failure" and "P2" in result["message"],
        )

        # 5. A reviewer's own run not concluding success is fail-closed, not
        #    silently treated as "no findings".
        g["get_issue_comments"] = lambda repo, pr, token: [agy_comment("PASS")]
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: (
            run(conclusion="failure") if path == AGY_WORKFLOW_PATH else run()
        )
        result = evaluate("o/r", 1, None)
        ok &= check(
            "fails closed when a reviewer's own run does not conclude success",
            result["state"] == "failure" and "tooling failure" in result["message"],
        )

        # 6. #1038 reproduction: Claude clean first, Agy still outstanding
        #    must stay non-success; Agy's later P2 must then fail, even
        #    though Claude was already clean.
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: (
            None if path == AGY_WORKFLOW_PATH else run()
        )
        g["get_reviews"] = lambda repo, pr, token: [review("APPROVED")]
        g["get_issue_comments"] = lambda repo, pr, token: []
        result = evaluate("o/r", 1, None)
        ok &= check(
            "#1038 regression: not success while Agy is still outstanding",
            result["state"] == "pending",
        )
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: run()
        g["get_issue_comments"] = lambda repo, pr, token: [agy_comment("FAIL:P2")]
        result = evaluate("o/r", 1, None)
        ok &= check(
            "#1038 regression: Agy's later P2 fails even though Claude was already clean",
            result["state"] == "failure",
        )

        # 7. Stale head: an evaluator run for a superseded head_sha posts
        #    nothing rather than reusing an old verdict.
        g["get_pr"] = lambda repo, pr, token: {"head": {"sha": "NEWHEAD"}}
        posted.clear()
        rc = cmd_evaluate("o/r", 1, None, "HEAD")
        ok &= check("a superseded head posts nothing", rc == 0 and not posted)
        g["get_pr"] = lambda repo, pr, token: {"head": {"sha": "HEAD"}}

        # 8. Timeout sweep: a pending status past its deadline with one
        #    reviewer never terminal flips to failure naming that reviewer.
        g["list_open_prs"] = lambda repo, token: [{"number": 1, "head": {"sha": "HEAD"}}]
        g["latest_status"] = lambda repo, sha, token, context=CONTEXT: {
            "state": "pending",
            "description": "waiting on claude-review, agy-review (deadline 2020-01-01T00:00:00Z)",
        }
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: (
            None if path == AGY_WORKFLOW_PATH else run()
        )
        g["get_reviews"] = lambda repo, pr, token: [review("APPROVED")]
        g["get_issue_comments"] = lambda repo, pr, token: []
        posted.clear()
        cmd_sweep("o/r", None, DEFAULT_GRACE_MINUTES)
        ok &= check(
            "timeout sweep flips a stale pending to failure naming the missing reviewer",
            bool(posted) and posted[0]["state"] == "failure" and "agy-review" in posted[0]["description"],
        )

        # 9. A completed, successful run with no parseable verdict at all
        #    (comment missing, or marker missing) is fail-closed too.
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: run()
        g["get_reviews"] = lambda repo, pr, token: []
        result = evaluate("o/r", 1, None)
        ok &= check(
            "fails closed when Claude's run completed but posted no terminal review",
            result["state"] == "failure" and "claude-review" in result["message"],
        )

        # 10. Agy's comma-list verdict form (both P1 and P2 in one run) is
        #     parsed as a failure, per the reusable workflow's own four
        #     exact forms (mctlhq/.github/.github/workflows/agy-review.yml).
        g["get_reviews"] = lambda repo, pr, token: [review("APPROVED")]
        g["get_issue_comments"] = lambda repo, pr, token: [agy_comment("FAIL:P1,P2")]
        result = evaluate("o/r", 1, None)
        ok &= check(
            "parses Agy's comma-list FAIL:P1,P2 verdict as a failure",
            result["state"] == "failure" and "P1,P2" in result["message"],
        )

        # 11. blocking:true means Agy's own job now fails its Actions run on
        #     a FAIL verdict -- the failure reason should still name the
        #     specific severity from the comment, not a bare "run failed".
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: (
            run(conclusion="failure") if path == AGY_WORKFLOW_PATH else run()
        )
        g["get_issue_comments"] = lambda repo, pr, token: [agy_comment("FAIL:P2")]
        result = evaluate("o/r", 1, None)
        ok &= check(
            "a failed blocking-mode Agy run still reports the specific P2 finding",
            result["state"] == "failure" and "P2" in result["message"],
        )
        g["latest_run_for_workflow"] = lambda repo, sha, path, token: run()
    finally:
        for name, value in real.items():
            g[name] = value

    if not ok:
        return 1
    print("self-test passed")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true", help="run the self-test suite and exit; no network calls")
    ap.add_argument("--action", choices=["pending", "evaluate", "sweep"])
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    ap.add_argument("--pr", type=int)
    ap.add_argument(
        "--event-head-sha",
        help="head_sha from the triggering workflow_run event, used to detect a superseded head",
    )
    ap.add_argument("--grace-minutes", type=int, default=DEFAULT_GRACE_MINUTES)
    args = ap.parse_args()

    if args.selftest:
        return self_test()

    if not args.action:
        ap.error("--action is required unless --selftest is given")
    if args.action in ("pending", "evaluate") and not args.pr:
        ap.error(f"--pr is required for --action {args.action}")
    if not args.repo:
        ap.error("--repo is required (or set GITHUB_REPOSITORY)")

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        if args.action == "pending":
            return cmd_pending(args.repo, args.pr, token, args.grace_minutes)
        if args.action == "evaluate":
            return cmd_evaluate(args.repo, args.pr, token, args.event_head_sha)
        return cmd_sweep(args.repo, token, args.grace_minutes)
    except urllib.error.HTTPError as exc:
        print(f"::error::GitHub API returned {exc.code} for {exc.url}")
        return 1
    except urllib.error.URLError as exc:
        print(f"::error::could not reach the GitHub API ({exc.reason})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
