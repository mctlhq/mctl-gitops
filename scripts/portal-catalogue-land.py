#!/usr/bin/env python3
"""Propose the catalogue.json update for a portal server that re-synced, when
that update cannot widen exposure (mctlhq/mctl-gitops#2416).

scripts/portal-catalogue-drift.py exits 5 when a server's live tool list and
allowlists/catalogue.json disagree. Only the live portal knows that list, and
only after the service has deployed and the server has re-synced, so the bump
PR cannot carry it when it opens. This script runs from cloudflare-drift.yml
after that exit 5 and writes the change to a PR:

  - the open bump PR of that server, when there is exactly one; or
  - a new `portal-catalogue/<server>-<digest>` PR from main.

It only proposes. It never merges, never writes to Cloudflare and never edits
what baseline.json allows: `tools_enabled` and `enabled_tools` are not touched.
Merging stays with the review gate and the portal changes only on an approved
`cloudflare-apply`.

It writes nothing for a server unless every one of these holds:

  - every tool the catalogue gains is decided and disabled in the allowlist;
  - no tool the catalogue loses is enabled there (an enabled tool leaving the
    portal may be an outage, and a person should read it);
  - the allowlist is non-widening against main's baseline.json;
  - a bump PR's own baseline entry still equals main's: a difference is a
    person's decision in progress, and that PR is theirs.

Branch content is data. This script reads it through the API and never runs
anything from it, because it holds a token that can write to the repository.

Could-not-observe is not observed-absent: any failed or malformed read, or a
PR listing that may be cut short, ends that server as `unknown` with nothing
written. Only a 404 on a branch means the branch does not exist.

Exits 0 once the input file is usable. The drift job is already red by now, and
the outcome goes to the alert through the `summary` step output.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime as _dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys

ALLOWLISTS = "infrastructure/cloudflare/portal/allowlists"
BOT_AUTHOR = "app/mctl-agents"
PR_LIMIT = 500
SERVER_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
TOOL_RE = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


class Unknown(Exception):
    """A read failed or returned something this script cannot trust."""


class NotFound(Exception):
    """The provider's documented absence signal: HTTP 404."""


@dataclasses.dataclass
class Refusal:
    reason: str


@dataclasses.dataclass
class Change:
    catalogue: dict
    baseline: dict
    added: list[str]
    gone: list[str]
    baseline_changed: bool


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def check_live(server: str, live) -> None:
    if not isinstance(live, list) or not live:
        raise Unknown(f"{server}: the live tool list is empty or not a list")
    if not all(isinstance(n, str) and TOOL_RE.fullmatch(n) for n in live):
        raise Unknown(f"{server}: the live tool list has an unexpected name")
    if len(set(live)) != len(live):
        raise Unknown(f"{server}: the live tool list repeats a name")


def decide(server: str, live: list[str], catalogue: dict, baseline: dict,
           allowlist: dict, reference: dict, today: str) -> Refusal | Change:
    """Pure decision. `catalogue`, `baseline` and `allowlist` are the target
    branch's documents; `reference` is main's baseline.json.
    """
    check_live(server, live)
    tools = allowlist.get("tools")
    if not isinstance(tools, list) or not tools:
        raise Unknown(f"{server}: the allowlist has no tools")
    try:
        decisions = {t["name"]: t["enabled"] for t in tools}
    except (TypeError, KeyError) as e:
        raise Unknown(f"{server}: malformed allowlist entry: {e!r}") from e
    if not all(isinstance(v, bool) for v in decisions.values()):
        raise Unknown(f"{server}: a non-boolean enabled in the allowlist")
    try:
        current = catalogue["servers"][server]
        entry = baseline["servers"][server]
        ref = reference["servers"][server]
        allowed = set(ref["enabled_tools"])
        allowed_count = ref["tools_enabled"]
    except (TypeError, KeyError) as e:
        raise Unknown(f"{server}: missing catalogue or baseline entry: {e!r}") from e
    if not isinstance(current, list) or not isinstance(allowed_count, int):
        raise Unknown(f"{server}: malformed catalogue or baseline entry")

    if entry != ref:
        return Refusal("its PR already edits baseline.json, so a person is deciding it")

    added = [n for n in live if n not in current]
    gone = [n for n in current if n not in live]
    undecided = [n for n in added if n not in decisions]
    if undecided:
        return Refusal(f"no decision in the allowlist for {names(undecided)}")
    enabled_added = [n for n in added if decisions[n]]
    if enabled_added:
        return Refusal(f"this would turn on {names(enabled_added)}")
    enabled_gone = [n for n in gone if decisions.get(n)]
    if enabled_gone:
        return Refusal(f"enabled tools left the portal: {names(enabled_gone)}")
    enabled = sorted(n for n, on in decisions.items() if on)
    widening = [n for n in enabled if n not in allowed]
    if widening:
        return Refusal(f"the allowlist widens exposure with {names(widening)}")
    if len(enabled) > allowed_count:
        return Refusal(f"the allowlist enables {len(enabled)} tools, baseline.json allows {allowed_count}")

    new_catalogue = json.loads(json.dumps(catalogue))
    new_catalogue["servers"][server] = list(live)
    new_baseline = json.loads(json.dumps(baseline))
    baseline_changed = entry.get("tools_total") != len(decisions)
    if baseline_changed:
        new_baseline["servers"][server]["tools_total"] = len(decisions)
        new_baseline["servers"][server]["recorded"] = today
    return Change(new_catalogue, new_baseline, added, gone, baseline_changed)


def names(items: list[str], limit: int = 5) -> str:
    shown = ", ".join(items[:limit])
    return f"{shown} and {len(items) - limit} more" if len(items) > limit else shown


class Gh:
    """The GitHub reads and writes this script needs, through `gh`."""

    def __init__(self, repo: str):
        self.repo = repo

    def _run(self, *args: str, stdin: str | None = None) -> str:
        p = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            if "HTTP 404" in p.stderr:
                raise NotFound(" ".join(args[:2]))
            raise Unknown(f"gh {args[0]} {args[1] if len(args) > 1 else ''} failed: {p.stderr.strip()[:200]}")
        return p.stdout

    def _json(self, *args: str, stdin: str | None = None):
        out = self._run(*args, stdin=stdin)
        try:
            return json.loads(out)
        except ValueError as e:
            raise Unknown(f"gh {args[0]} returned a malformed body") from e

    def main_sha(self) -> str:
        sha = self._json("api", f"repos/{self.repo}/git/ref/heads/main")["object"]["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
            raise Unknown("could not resolve main")
        return sha

    def read(self, path: str, ref: str, rewrite: bool = False) -> tuple[dict, str]:
        """A JSON file and its blob sha. With `rewrite`, refuses a file that
        writing it back would reformat: that diff would hide the real change.
        """
        doc = self._json("api", f"repos/{self.repo}/contents/{path}?ref={ref}")
        if not isinstance(doc, dict) or doc.get("encoding") != "base64" or not doc.get("sha"):
            raise Unknown(f"{path}: unexpected contents response")
        try:
            text = base64.b64decode(doc["content"]).decode("utf-8")
            parsed = json.loads(text)
        except ValueError as e:
            raise Unknown(f"{path}: malformed") from e
        if rewrite and dumps(parsed) != text:
            raise Unknown(f"{path}: not in the canonical format")
        return parsed, doc["sha"]

    def open_prs(self) -> list[dict]:
        prs = self._json("pr", "list", "--repo", self.repo, "--state", "open", "--limit", str(PR_LIMIT),
                         "--json", "number,url,headRefName,headRefOid,isCrossRepository,author")
        if not isinstance(prs, list):
            raise Unknown("the PR listing is not a list")
        if len(prs) >= PR_LIMIT:
            raise Unknown(f"the PR listing reached its limit of {PR_LIMIT} and may be cut short")
        return prs

    def prs_for(self, branch: str) -> list[dict]:
        prs = self._json("pr", "list", "--repo", self.repo, "--state", "all", "--head", branch,
                         "--json", "number,url,state")
        if not isinstance(prs, list):
            raise Unknown("the PR listing is not a list")
        return prs

    def branch_exists(self, branch: str) -> bool:
        try:
            self._json("api", f"repos/{self.repo}/git/ref/heads/{branch}")
        except NotFound:
            return False
        return True

    def create_branch(self, branch: str, sha: str) -> None:
        self._json("api", "--method", "POST", f"repos/{self.repo}/git/refs",
                   "-f", f"ref=refs/heads/{branch}", "-f", f"sha={sha}")

    def put(self, path: str, text: str, blob: str, branch: str, message: str) -> None:
        # `sha` makes this a compare-and-swap: a concurrent change answers 409
        # and ends as unknown rather than being overwritten.
        body = json.dumps({"message": message, "branch": branch, "sha": blob,
                           "content": base64.b64encode(text.encode("utf-8")).decode("ascii")})
        self._json("api", "--method", "PUT", f"repos/{self.repo}/contents/{path}", "--input", "-", stdin=body)

    def create_pr(self, branch: str, title: str, body: str) -> dict:
        payload = json.dumps({"title": title, "head": branch, "base": "main", "body": body})
        return self._json("api", "--method", "POST", f"repos/{self.repo}/pulls", "--input", "-", stdin=payload)


def pr_link(pr: dict) -> str:
    url = pr.get("url") or pr.get("html_url") or ""
    return f'<a href="{html.escape(url, quote=True)}">#{int(pr["number"])}</a>'


def write_change(gh, change: Change, server: str, branch: str, blobs: tuple[str, str], current: dict) -> bool:
    cat_path = f"{ALLOWLISTS}/catalogue.json"
    base_path = f"{ALLOWLISTS}/baseline.json"
    wrote = False
    if dumps(change.catalogue) != dumps(current["catalogue"]):
        gh.put(cat_path, dumps(change.catalogue), blobs[0], branch,
               f"portal({server}): sync catalogue.json with the live portal\n\n"
               f"Adds: {', '.join(change.added) or 'none'}. Removes: {', '.join(change.gone) or 'none'}.\n"
               "Written by scripts/portal-catalogue-land.py: every added tool is disabled.")
        wrote = True
    if change.baseline_changed:
        gh.put(base_path, dumps(change.baseline), blobs[1], branch,
               f"portal({server}): record tools_total in baseline.json\n\n"
               "Only the recorded total moves. What is allowed to be enabled does not.")
        wrote = True
    return wrote


def land(gh, server: str, live: list[str], today: str) -> str:
    """One server's outcome, as a safe HTML sentence for the alert."""
    if not SERVER_RE.fullmatch(server):
        raise Unknown("unexpected server id")
    check_live(server, live)
    sha = gh.main_sha()
    mapping, _ = gh.read(f"{ALLOWLISTS}/mapping.json", sha)
    if not (mapping.get("servers", {}).get(server) or {}).get("vendored"):
        return f"{server}: not a vendored server, so update it by hand."
    reference, _ = gh.read(f"{ALLOWLISTS}/baseline.json", sha)

    pattern = re.compile(rf"portal-allowlist/{re.escape(server)}-[0-9a-f]{{7}}")
    matching = [p for p in gh.open_prs() if pattern.fullmatch(p.get("headRefName") or "")]
    trusted = [p for p in matching
               if not p.get("isCrossRepository") and (p.get("author") or {}).get("login") == BOT_AUTHOR]
    if len(matching) != len(trusted) or len(trusted) > 1:
        return f"{server}: more than one candidate bump PR, or one the bot did not open, so nothing was written."

    if trusted:
        pr = trusted[0]
        ref, branch = pr["headRefOid"], pr["headRefName"]
    else:
        pr = None
        ref = sha
        digest = hashlib.sha256("\n".join(live).encode("utf-8")).hexdigest()[:7]
        branch = f"portal-catalogue/{server}-{digest}"
        existing = gh.prs_for(branch)
        open_pr = [p for p in existing if p.get("state") == "OPEN"]
        if open_pr:
            return (f"{server}: already proposed in {pr_link(open_pr[0])}. "
                    "Merge it after review, then approve cloudflare-apply.")
        if existing:
            return f"{server}: {pr_link(existing[0])} proposed this and was closed, so it was not reopened."

    catalogue, cat_blob = gh.read(f"{ALLOWLISTS}/catalogue.json", ref, rewrite=True)
    baseline, base_blob = gh.read(f"{ALLOWLISTS}/baseline.json", ref, rewrite=True)
    allowlist, _ = gh.read(f"{ALLOWLISTS}/{server}.json", ref)
    outcome = decide(server, live, catalogue, baseline, allowlist, reference, today)
    if isinstance(outcome, Refusal):
        where = f" in {pr_link(pr)}" if pr else ""
        return f"{server}: <b>needs your decision</b>{where}: {html.escape(outcome.reason)}. Nothing was written."

    current = {"catalogue": catalogue}
    if pr is None and not gh.branch_exists(branch):
        gh.create_branch(branch, sha)
    wrote = write_change(gh, outcome, server, branch, (cat_blob, base_blob), current)
    if pr is None:
        pr = gh.create_pr(
            branch, f"portal({server}): sync catalogue.json with the live portal",
            f"`{server}` re-synced and `catalogue.json` lags it (drift exit 5).\n\n"
            f"- Adds: {', '.join(outcome.added) or 'none'}\n"
            f"- Removes: {', '.join(outcome.gone) or 'none'}\n\n"
            "Every added tool is disabled in the allowlist and nothing here widens exposure. "
            "Merging writes nothing; the portal changes on the next approved `cloudflare-apply`.\n\n"
            "Opened by `scripts/portal-catalogue-land.py` (mctlhq/mctl-gitops#2416).")
    if not wrote:
        return (f"{server}: {pr_link(pr)} already carries the catalogue change. "
                "Merge it after review, then approve cloudflare-apply.")
    added = html.escape(names(outcome.added)) if outcome.added else "no new tools"
    return (f"{server}: updated {pr_link(pr)}, disabled tools only ({added}). "
            "Merge it after review, then approve cloudflare-apply.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lag", required=True, help="JSON {server: [live tool names]} from portal-catalogue-drift.py --lag-out")
    args = ap.parse_args()
    try:
        with open(args.lag, encoding="utf-8") as f:
            lag = json.load(f)
        if not isinstance(lag, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as e:
        print(f"::error::could not read {args.lag}: {e!r}")
        lines = ["could not read which servers lag, so nothing was written."]
        lag = {}
    else:
        lines = []
    gh = Gh(os.environ["GITHUB_REPOSITORY"])
    today = _dt.date.today().isoformat()
    for server, live in sorted(lag.items()):
        safe = server if SERVER_RE.fullmatch(server) else "a server"
        try:
            lines.append(land(gh, server, live, today))
        except (Unknown, NotFound, KeyError, TypeError, AttributeError, ValueError,
                subprocess.TimeoutExpired) as e:
            # The detail goes to the log. The alert gets a fixed sentence, so
            # nothing from an API error can reach a parse_mode=HTML message.
            print(f"::warning::{safe}: {e!r}")
            lines.append(f"{safe}: <b>state unknown</b>, nothing further was written. See the run log.")
    summary = " ".join(lines)
    print(summary)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"summary={summary}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
