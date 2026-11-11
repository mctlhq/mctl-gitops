#!/usr/bin/env python3
"""Read-only check of the bypass actors on this repository's rulesets (#2543).

Reads every ruleset that applies to the repository (repository and inherited
organization rulesets, all pages) and the detail of each one, then compares
the bypass actors with scripts/ruleset-bypass-allowlist.json.

A finding is:
- a bypass actor whose actor_id is null or not an integer (for actor_type
  DeployKey GitHub always stores null: the entry admits EVERY write deploy key
  on the repository, so it can never be allowlisted);
- a bypass actor that does not match an allowlist entry of that ruleset, or
  matches one whose `expires` date has passed (a transitional entry that was
  not removed in time);
- more bypass actors on a ruleset than its allowlist has entries;
- a ruleset named in the allowlist that a complete listing does not contain,
  or that is not `active`, or whose include/exclude no longer covers
  refs/heads/main, or that lost a rule type listed in its `required_rules`,
  requires fewer approvals than `min_approving_review_count`, or dropped a
  {context, integration_id} pair listed in `required_status_checks`.

"Could not observe" is never "observed absent". A failed, partial (a later
page failing), malformed or truncated read is UNKNOWN. GitHub omits
`bypass_actors` from the response unless the caller can edit the ruleset, so a
detail without that field is UNKNOWN, never "no bypass actors". UNKNOWN
outranks a finding.

Never writes anything. Needs a token whose holder can administer the
repository (an org owner's `gh auth token`); GITHUB_TOKEN in Actions cannot
see bypass actors, which is why this is an operator check (see
docs/runbooks/main-protection-bypass-actors.md) and CI only runs --selftest
through tests/test_ruleset_bypass_check.py.

Usage:
  python3 -I scripts/check-ruleset-bypass-actors.py --gh      # via the gh CLI login
  GH_TOKEN=... python3 -I scripts/check-ruleset-bypass-actors.py  # direct HTTPS
  python3 -I scripts/check-ruleset-bypass-actors.py --fixture snapshot.json

A fixture is {"<api path>": <json body>} with the same paths the live read
uses; a missing path is a failed read.

Exit codes: 0 clean, 10 findings, 20 unknown (some read failed).
"""
import datetime
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO = "mctlhq/mctl-gitops"
CLEAN, FINDINGS, UNKNOWN = 0, 10, 20
MAIN_REF = "refs/heads/main"
MAX_PAGES = 20


class ReadError(Exception):
    """A read did not return what the provider documents. Never means 'empty'."""


def fetch(path, token):
    """One JSON document and its Link header. Anything but a 200 with a JSON body fails."""
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, body, link = resp.status, resp.read(), resp.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        raise ReadError(f"{path}: HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ReadError(f"{path}: {e}") from e
    if status != 200:
        raise ReadError(f"{path}: HTTP {status}")
    try:
        return json.loads(body), link
    except ValueError as e:
        raise ReadError(f"{path}: malformed body") from e


def gh_fetch(path, token):
    """Same contract as fetch(), through the gh CLI and its own credentials and TLS."""
    path = path.removeprefix(API)
    try:
        proc = subprocess.run(["gh", "api", "--include", path], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ReadError(f"{path}: gh failed: {e}") from e
    if proc.returncode != 0:
        raise ReadError(f"{path}: gh exit {proc.returncode}")
    raw = proc.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
    head, sep, body = raw.partition("\n\n")
    status = head.split("\n", 1)[0].split()
    if not sep or len(status) < 2 or status[1] != "200":
        raise ReadError(f"{path}: unexpected response status {status[1:2]}")
    link = ""
    for ln in head.split("\n")[1:]:
        k, _, v = ln.partition(":")
        if k.strip().lower() == "link":
            link = v.strip()
    try:
        return json.loads(body), link
    except ValueError as e:
        raise ReadError(f"{path}: malformed body") from e


def fixture_fetcher(doc):
    """Serve a recorded snapshot. A path that was not recorded is a failed read."""
    def _fetch(path, token):
        path = path.removeprefix(API)
        if path not in doc:
            raise ReadError(f"{path}: not in fixture")
        entry = doc[path]
        if isinstance(entry, dict) and "__body__" in entry:
            return entry["__body__"], entry.get("__link__", "")
        return entry, ""
    return _fetch


def list_rulesets(repo, token, fetcher):
    """Every ruleset that applies to the repo, all pages. A later page failing fails the read."""
    out, url, pages = [], f"/repos/{repo}/rulesets?includes_parents=true&per_page=100", 0
    while url:
        data, link = fetcher(url, token)
        if not isinstance(data, list):
            raise ReadError(f"{url}: expected a list")
        for r in data:
            if not isinstance(r, dict) or not isinstance(r.get("id"), int) or isinstance(r.get("id"), bool):
                raise ReadError(f"{url}: malformed ruleset entry")
        out.extend(data)
        m = re.search(r'<([^>]+)>;\s*rel="next"', link or "")
        url = m.group(1) if m else None
        pages += 1
        if pages > MAX_PAGES:
            raise ReadError("ruleset listing did not end")
    return out


def _ref_glob(pattern):
    """GitHub ref patterns match like File.fnmatch with FNM_PATHNAME: `*` and
    `?` stop at `/`, only `**` crosses it."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _matches_main(patterns, strict):
    """Does any ref_name pattern select main? `~DEFAULT_BRANCH` is main here.

    strict (include side): GitHub's pathname-aware match, so a pattern such as
    `refs/*` is not taken to cover main. Not strict (exclude side): also the
    permissive fnmatch, which errs toward a finding."""
    for p in patterns:
        if p in ("~ALL", "~DEFAULT_BRANCH") or _ref_glob(p).match(MAIN_REF):
            return True
        if not strict and fnmatch.fnmatchcase(MAIN_REF, p):
            return True
    return False


def _rule_params(rules, rtype, rid):
    for r in rules:
        if r.get("type") == rtype:
            params = r.get("parameters")
            if not isinstance(params, dict):
                raise ReadError(f"ruleset {rid}: {rtype} rule has no parameters")
            return params
    return None


def _actor_key(a):
    return (a.get("actor_type"), a.get("actor_id"), a.get("bypass_mode", "always"))


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def evaluate_ruleset(rid, detail, allowed, today):
    """Findings for one ruleset detail. Raises ReadError when it cannot tell."""
    if not isinstance(detail, dict) or detail.get("id") != rid:
        raise ReadError(f"ruleset {rid}: malformed detail")
    if "bypass_actors" not in detail:
        raise ReadError(f"ruleset {rid}: bypass_actors not returned "
                        "(token cannot edit this ruleset): bypass list unobserved")
    actors = detail["bypass_actors"]
    if not isinstance(actors, list):
        raise ReadError(f"ruleset {rid}: bypass_actors is not a list")
    findings = []
    name = detail.get("name", "?")
    entries = allowed or []
    if len(actors) > len(entries):
        findings.append(f"ruleset {rid} ({name}): {len(actors)} bypass actors, "
                        f"allowlist has {len(entries)}")
    used = set()
    for a in actors:
        if not isinstance(a, dict) or not isinstance(a.get("actor_type"), str):
            raise ReadError(f"ruleset {rid}: malformed bypass actor")
        if not _is_int(a.get("actor_id")):
            findings.append(f"ruleset {rid} ({name}): bypass actor {a.get('actor_type')} "
                            f"has actor_id {a.get('actor_id')!r}: not a single identifiable "
                            "actor (DeployKey admits every write deploy key)")
            continue
        match = None
        for i, e in enumerate(entries):
            if i not in used and _actor_key(e) == _actor_key(a):
                match = i
                break
        if match is None:
            findings.append(f"ruleset {rid} ({name}): bypass actor "
                            f"{a.get('actor_type')}:{a.get('actor_id')} "
                            f"mode {a.get('bypass_mode', 'always')} is not on the allowlist")
            continue
        used.add(match)
        exp = entries[match].get("expires")
        if exp is not None and datetime.date.fromisoformat(exp) < today:
            findings.append(f"ruleset {rid} ({name}): allowlisted bypass actor "
                            f"{entries[match].get('label', a.get('actor_id'))} expired on {exp}")
    return findings


def validate_allowlist(allowlist):
    rulesets = allowlist.get("rulesets") if isinstance(allowlist, dict) else None
    if not isinstance(rulesets, dict):
        raise ValueError("allowlist has no rulesets map")
    for rid, spec in rulesets.items():
        if not rid.isdigit() or not isinstance(spec, dict) or not isinstance(spec.get("bypass_actors"), list):
            raise ValueError(f"allowlist entry {rid!r} is malformed")
        for e in spec["bypass_actors"]:
            if not isinstance(e, dict) or not _is_int(e.get("actor_id")) or not isinstance(e.get("actor_type"), str):
                raise ValueError(f"allowlist entry {rid!r}: every actor needs actor_type and an integer actor_id")
            if e.get("expires") is not None:
                if not isinstance(e["expires"], str):
                    raise ValueError(f"allowlist entry {rid!r}: expires must be a YYYY-MM-DD string")
                datetime.date.fromisoformat(e["expires"])
        if "min_approving_review_count" in spec and not _is_int(spec["min_approving_review_count"]):
            raise ValueError(f"allowlist entry {rid!r}: min_approving_review_count must be an integer")
        ctxs = spec.get("required_status_checks", [])
        if not isinstance(ctxs, list) or not all(
                isinstance(c, dict) and isinstance(c.get("context"), str) and _is_int(c.get("integration_id"))
                for c in ctxs):
            raise ValueError(f"allowlist entry {rid!r}: required_status_checks must be "
                             "{context, integration_id} pairs")
        req = spec.get("required_rules", [])
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            raise ValueError(f"allowlist entry {rid!r}: required_rules must be a list of rule types")
    return rulesets


def scan(token, allowlist, fetcher=fetch, repo=REPO, today=None):
    """(findings, unknown, observed ruleset ids)."""
    today = today or datetime.date.today()
    findings, unknown, observed = [], [], []
    try:
        expected = validate_allowlist(allowlist)
    except ValueError as e:
        return findings, [f"allowlist unusable: {e}"], observed
    try:
        listing = list_rulesets(repo, token, fetcher)
    except ReadError as e:
        return findings, [str(e)], observed
    listed = {r["id"]: r for r in listing}
    # Only a complete listing that lacks it is "absent": the protection is gone.
    for rid in expected:
        if int(rid) not in listed:
            findings.append(f"ruleset {rid} ({expected[rid].get('name', '?')}) is not in the "
                            "complete ruleset listing: main protection removed")
    # Every listed ruleset is read, tag and push ones included, so an
    # unexpected bypass actor anywhere on the repository is visible.
    for rid in sorted(listed):
        try:
            detail, _ = fetcher(f"/repos/{repo}/rulesets/{rid}", token)
            spec = expected.get(str(rid))
            findings.extend(evaluate_ruleset(rid, detail, spec["bypass_actors"] if spec else [], today))
            if spec:
                if detail.get("enforcement") != "active":
                    findings.append(f"ruleset {rid}: enforcement is {detail.get('enforcement')!r}, not active")
                ref = (detail.get("conditions") or {}).get("ref_name") or {}
                inc, exc = ref.get("include"), ref.get("exclude", [])
                if not isinstance(inc, list) or not isinstance(exc, list) \
                        or not all(isinstance(x, str) for x in inc + exc):
                    raise ReadError(f"ruleset {rid}: conditions.ref_name malformed")
                if not _matches_main(inc, strict=True) or _matches_main(exc, strict=False):
                    findings.append(f"ruleset {rid}: does not cover {MAIN_REF} "
                                    f"(include {inc}, exclude {exc})")
                rules = detail.get("rules")
                if not isinstance(rules, list) or not all(isinstance(r, dict) for r in rules):
                    raise ReadError(f"ruleset {rid}: rules malformed")
                present = {r.get("type") for r in rules}
                for want in spec.get("required_rules", []):
                    if want not in present:
                        findings.append(f"ruleset {rid}: required rule {want!r} is missing")
                if "min_approving_review_count" in spec:
                    pr = _rule_params(rules, "pull_request", rid)
                    n = pr.get("required_approving_review_count") if pr is not None else None
                    if pr is not None and not _is_int(n):
                        raise ReadError(f"ruleset {rid}: required_approving_review_count malformed")
                    if pr is not None and n < spec["min_approving_review_count"]:
                        findings.append(f"ruleset {rid}: pull_request requires {n} approvals, "
                                        f"fewer than {spec['min_approving_review_count']}")
                if "required_status_checks" in spec:
                    sc = _rule_params(rules, "required_status_checks", rid)
                    if sc is not None:
                        checks = sc.get("required_status_checks")
                        if not isinstance(checks, list) or not all(
                                isinstance(c, dict) and isinstance(c.get("context"), str) for c in checks):
                            raise ReadError(f"ruleset {rid}: required_status_checks malformed")
                        # The source matters: a context without its integration_id
                        # can be satisfied by anyone who can post a status.
                        have = {(c["context"], c.get("integration_id")) for c in checks}
                        for want in spec["required_status_checks"]:
                            if (want["context"], want["integration_id"]) not in have:
                                findings.append(f"ruleset {rid}: required status check {want['context']!r} "
                                                f"from integration {want['integration_id']} is missing")
            observed.append(rid)
        except ReadError as e:
            unknown.append(str(e))
    return findings, unknown, observed


def verdict(findings, unknown):
    if unknown:
        return UNKNOWN
    return FINDINGS if findings else CLEAN


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    args = argv[1:]
    fetcher, token = fetch, os.environ.get("GH_TOKEN", "")
    if args[:1] == ["--fixture"] and len(args) == 2:
        try:
            with open(args[1]) as fh:
                fetcher = fixture_fetcher(json.load(fh))
        except (OSError, ValueError) as e:
            print(f"fixture unreadable: {e}", file=sys.stderr)
            return UNKNOWN
    elif args == ["--gh"]:
        fetcher, token = gh_fetch, ""
    elif args:
        print(__doc__, file=sys.stderr)
        return UNKNOWN
    elif not token:
        print("GH_TOKEN is not set: nothing was read", file=sys.stderr)
        return UNKNOWN
    try:
        with open(os.path.join(here, "ruleset-bypass-allowlist.json")) as fh:
            allowlist = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"allowlist unreadable: {e}", file=sys.stderr)
        return UNKNOWN
    findings, unknown, observed = scan(token, allowlist, fetcher)
    code = verdict(findings, unknown)
    print(f"observed {len(observed)} rulesets: {observed}")
    for label, items in (("FINDING", findings), ("UNKNOWN", unknown)):
        for i in items:
            print(f"{label}: {i}")
    print({CLEAN: "RESULT: clean", FINDINGS: "RESULT: findings",
           UNKNOWN: "RESULT: unknown (a read failed or was not permitted)"}[code])
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
