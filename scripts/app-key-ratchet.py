#!/usr/bin/env python3
"""Ratchet for references to the GitHub App signing keys (#1033).

Walks the git TREE of every non-archived org repository (code search misses
repos: it found 12 of 18), reads each workflow file and reports every
reference to the App key secrets that is not on the allowlist.

"Could not observe" is never "observed absent". Every failed, partial or
malformed read raises ReadError and ends in exit code 20, which outranks a
finding. A repo named in the allowlist that the token cannot see is unknown,
not clean.

Exit codes: 0 clean, 10 findings, 20 unknown (some read failed).
Report-only mode is decided by the caller (the workflow turns 10 into a
warning); this script always tells the truth.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
ORG = "mctlhq"
CLEAN, FINDINGS, UNKNOWN = 0, 10, 20


class ReadError(Exception):
    """A read did not return what the provider documents. Never means 'empty'."""


def _get(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read(), resp.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        raise ReadError(f"{url}: HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ReadError(f"{url}: {e}") from e


def fetch(path, token):
    """One JSON document. Anything but a 200 with a parseable body is a failed read."""
    status, body, link = _get(path if path.startswith("http") else API + path, token)
    if status != 200:
        raise ReadError(f"{path}: HTTP {status}")
    try:
        return json.loads(body), link
    except ValueError as e:
        raise ReadError(f"{path}: malformed body") from e


def fetch_list(path, token, fetcher=fetch):
    """All pages of a list. A later page failing fails the whole read."""
    out, url, seen = [], path, 0
    while url:
        data, link = fetcher(url, token)
        if not isinstance(data, list):
            raise ReadError(f"{url}: expected a list")
        out.extend(data)
        m = re.search(r'<([^>]+)>;\s*rel="next"', link or "")
        url = m.group(1) if m else None
        seen += 1
        if seen > 50:
            raise ReadError(f"{path}: pagination did not end")
    return out


REF = re.compile(
    r"""secrets\s*(?:\.\s*|\[\s*['"])(AGENTS_APP_PRIVATE_KEY|APP_PRIVATE_KEY)\b""")
INHERIT = re.compile(r"^\s*secrets:\s*inherit\s*$", re.M)


def refs_in(text):
    """(key names referenced, uses `secrets: inherit`)."""
    return set(REF.findall(text)), bool(INHERIT.search(text))


def scan(token, allowlist, fetcher=fetch):
    """Returns (findings, unknown, stale, observed_repos)."""
    findings, unknown, stale = [], [], []
    allowed = allowlist["repos"]
    try:
        repos = fetch_list(f"/orgs/{ORG}/repos?per_page=100&type=all", token, fetcher)
    except ReadError as e:
        return [], [f"repo listing: {e}"], [], []
    for r in repos:
        if not isinstance(r, dict) or "name" not in r or "archived" not in r:
            return [], ["repo listing: malformed entry"], [], []
    live = {r["name"]: r for r in repos if not r["archived"]}
    for name in sorted(allowed):
        if name not in live:
            unknown.append(f"{name}: in the allowlist but not visible to this token")
    observed = []
    for name, r in sorted(live.items()):
        branch = r.get("default_branch")
        if not branch:
            unknown.append(f"{name}: no default branch in listing")
            continue
        try:
            tree, _ = fetcher(f"/repos/{ORG}/{name}/git/trees/{branch}?recursive=1", token)
            if not isinstance(tree, dict) or not isinstance(tree.get("tree"), list):
                raise ReadError("malformed tree")
            if tree.get("truncated") is not False:
                raise ReadError("tree truncated or truncation unknown")
            files = [
                t for t in tree["tree"]
                if t.get("type") == "blob"
                and re.match(r"^\.github/.*\.ya?ml$", t.get("path", ""))
            ]
            found = {}
            for t in files:
                blob, _ = fetcher(f"/repos/{ORG}/{name}/git/blobs/{t['sha']}", token)
                if not isinstance(blob, dict) or blob.get("encoding") != "base64":
                    raise ReadError(f"{t['path']}: malformed blob")
                try:
                    text = base64.b64decode(blob["content"], validate=False).decode("utf-8", "replace")
                except (KeyError, ValueError, TypeError) as e:
                    raise ReadError(f"{t['path']}: undecodable blob") from e
                keys, inherit = refs_in(text)
                if keys or inherit:
                    found[t["path"]] = (keys, inherit)
        except ReadError as e:
            unknown.append(f"{name}: {e}")
            continue
        observed.append(name)
        ok = allowed.get(name, {})
        for path, (keys, inherit) in sorted(found.items()):
            for k in sorted(keys):
                if k not in ok.get(path, []):
                    findings.append(f"{name}:{path} references {k}")
            if inherit and "inherit" not in ok.get(path, []):
                findings.append(f"{name}:{path} uses `secrets: inherit`")
        for path, ks in ok.items():
            for k in ks:
                if k == "inherit":
                    continue
                if k not in found.get(path, (set(), False))[0]:
                    stale.append(f"{name}:{path} no longer references {k}")
    return findings, unknown, stale, observed


def verdict(findings, unknown):
    if unknown:
        return UNKNOWN
    return FINDINGS if findings else CLEAN


def main(argv):
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("GH_TOKEN is not set: nothing was read", file=sys.stderr)
        return UNKNOWN
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "app-key-allowlist.json")) as fh:
            allowlist = json.load(fh)
        if not isinstance(allowlist.get("repos"), dict):
            raise ValueError("no repos map")
    except (OSError, ValueError) as e:
        print(f"allowlist unreadable: {e}", file=sys.stderr)
        return UNKNOWN
    findings, unknown, stale, observed = scan(token, allowlist)
    code = verdict(findings, unknown)
    print(f"observed {len(observed)} repositories")
    for label, items in (("FINDING", findings), ("UNKNOWN", unknown), ("stale allowlist entry", stale)):
        for i in items:
            print(f"{label}: {i}")
    print({CLEAN: "RESULT: clean", FINDINGS: "RESULT: findings", UNKNOWN: "RESULT: unknown (a read failed)"}[code])
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
