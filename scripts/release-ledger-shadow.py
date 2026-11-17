#!/usr/bin/env python3
"""Release ledger, shadow mode (mctlhq/mctl-api#1022 S3, mctlhq/mctl-gitops#2528).

  release-ledger-shadow.py check --repository R --version V --digest D --commit C --image I
  release-ledger-shadow.py --selftest

Reads the release decisions mctl-api keeps for one release
(GET /api/v1/release/grants) and says what a ledger-based gate WOULD decide
for exactly the image this run built, next to what the YAML allow records in
platform-gitops/release-gates.yaml decide today. It enforces nothing: the
release-deploy job that runs it is continue-on-error and nothing needs it.
The point is to collect evidence that the two agree before the ledger
replaces the YAML (S4).

Three ledger verdicts, kept apart end to end:
  allow    an approved, unexpired, unconsumed decision with MFA evidence names
           this repository, version, tag commit AND image digest
  refuse   the ledger was read and holds no such decision (none, rejected,
           expired, consumed, or bound to another digest/commit)
  unknown  the ledger could not be read or its answer is malformed.
           Could not observe is never "no decision" and never "allowed".

The ID token is requested from GitHub with audience https://api.mctl.ai and
is never printed. mctl-api accepts it as the release gate reader only from a
workflow of mctlhq/mctl-gitops on refs/heads/main.

Exit 0 always for `check` (shadow), except on bad arguments; the verdict is
on stdout and in $GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GATE = "platform-gitops/release-gates.yaml"
API = "https://api.mctl.ai"
AUDIENCE = "https://api.mctl.ai"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
COMMIT = re.compile(r"[0-9a-f]{40}", re.ASCII)
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", re.ASCII)
REPO = re.compile(r"[a-z0-9][a-z0-9-]*/[a-z0-9._-]+", re.ASCII)

ALLOW, REFUSE, UNKNOWN = "allow", "refuse", "unknown"
# Cloudflare in front of api.mctl.ai refuses urllib's default User-Agent
# ("Python-urllib/3.x") with 403 "error code: 1010" before the request
# reaches mctl-api; the first live run (4.166.0) read nothing because of it.
USER_AGENT = "mctl-gitops-release-ledger-shadow/1"


def _request(url: str, headers: dict[str, str]) -> urllib.request.Request:
    return urllib.request.Request(url, headers={**headers, "User-Agent": USER_AGENT})


def _ts(raw: Any) -> datetime.datetime:
    """RFC 3339 from Go (Z suffix, 0-9 fraction digits) -> aware datetime."""
    if not isinstance(raw, str):
        raise ValueError(f"timestamp {raw!r} is not a string")
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})", raw, re.ASCII)
    if not m:
        raise ValueError(f"timestamp {raw!r} is not RFC 3339")
    frac = (m.group(2) or ".0")[1:7].ljust(6, "0")
    tz = "+00:00" if m.group(3) == "Z" else m.group(3)
    return datetime.datetime.fromisoformat(f"{m.group(1)}.{frac}{tz}")


def judge_ledger(body: Any, repository: str, version: str, digest: str, commit: str,
                 now: datetime.datetime) -> tuple[str, str]:
    """What a ledger gate would decide for this exact artifact. Pure."""
    if not isinstance(body, dict) or not isinstance(body.get("grants"), list):
        return UNKNOWN, "response is not an object with a grants list"
    if body.get("repository") != repository or body.get("version") != version:
        return UNKNOWN, f"response is for {body.get('repository')!r} {body.get('version')!r}, not this release"
    approved: list[str] = []
    refused: list[str] = []
    others = 0
    for i, g in enumerate(body["grants"]):
        a = g.get("approval") if isinstance(g, dict) else None
        art = g.get("artifact") if isinstance(g, dict) else None
        if not isinstance(a, dict) or not isinstance(art, dict) or not isinstance(a.get("id"), str) \
                or not isinstance(a.get("state"), str):
            # A row we cannot read is a failed read, not a row to skip.
            return UNKNOWN, f"grant {i} is malformed"
        if (art.get("repository"), art.get("version")) != (repository, version):
            return UNKNOWN, f"grant {a['id']} is for another release"
        if art.get("image_digest") != digest or art.get("tag_commit") != commit:
            others += 1
            continue
        state = a["state"]
        if state == "rejected":
            refused.append(f"{a['id']} rejected")
        elif state == "approved":
            dec = g.get("decision")
            if not isinstance(dec, dict) or not isinstance(dec.get("amr"), list):
                return UNKNOWN, f"grant {a['id']} is approved but carries no decision evidence"
            if "mfa" not in dec["amr"]:
                refused.append(f"{a['id']} approved without mfa")
                continue
            try:
                expires = _ts(a.get("expires_at"))
            except ValueError as exc:
                return UNKNOWN, f"grant {a['id']}: {exc}"
            if a.get("consumed_at"):
                refused.append(f"{a['id']} already consumed")
            elif expires <= now:
                refused.append(f"{a['id']} expired at {a['expires_at']}")
            else:
                approved.append(a["id"])
        # pending/expired/other states decide nothing.
    if refused:
        # A rejection of this exact image outranks any approval of it.
        return REFUSE, "; ".join(refused)
    if approved:
        return ALLOW, f"approved by {', '.join(approved)}"
    if others:
        return REFUSE, f"no decision for this digest and commit ({others} grant(s) bind another artifact)"
    return REFUSE, "no approved decision for this release"


def judge_yaml(doc: Any, image: str, version: str, today: datetime.date) -> tuple[str, str]:
    """What the YAML allow records decide for a new write of `version`."""
    holds = doc.get("version_holds") if isinstance(doc, dict) else None
    if not isinstance(holds, list):
        return UNKNOWN, "version_holds missing"
    mine = [h for h in holds if isinstance(h, dict) and h.get("repository") == image]
    if not mine:
        return ALLOW, "no version hold for this image"
    v = SEMVER.fullmatch(version)
    for h in mine:
        floor = SEMVER.fullmatch(str(h.get("held_from")))
        if v is None or floor is None:
            return UNKNOWN, f"hold {h.get('name')}: unreadable versions"
        if tuple(map(int, v.groups())) < tuple(map(int, floor.groups())):
            continue
        rec = [a for a in h.get("allow") or [] if isinstance(a, dict) and a.get("version") == version]
        if not rec:
            return REFUSE, f"{version} has no allow record"
        exp = rec[0].get("expires")
        if not isinstance(exp, datetime.date):
            return UNKNOWN, f"allow record for {version}: expires is not a date"
        if exp < today:
            return REFUSE, f"allow record for {version} expired on {exp}"
        return ALLOW, f"allow record {rec[0].get('grant')}"
    return ALLOW, "below held_from"


def _id_token() -> str:
    url, bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not bearer:
        raise RuntimeError("no GitHub OIDC request environment (job lacks id-token: write?)")
    sep = "&" if "?" in url else "?"
    req = _request(f"{url}{sep}audience={urllib.parse.quote(AUDIENCE, safe='')}",
                   {"Authorization": f"bearer {bearer}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        val = json.load(resp).get("value")
    if not isinstance(val, str) or not val:
        raise RuntimeError("GitHub returned no ID token")
    return val


def _read_ledger(repository: str, version: str) -> Any:
    q = urllib.parse.urlencode({"repository": repository, "version": version})
    req = _request(f"{API}/api/v1/release/grants?{q}",
                   {"Authorization": f"Bearer {_id_token()}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return json.load(resp)


def check(args: argparse.Namespace) -> int:
    for name, rx in (("repository", REPO), ("version", SEMVER), ("digest", DIGEST), ("commit", COMMIT)):
        if not rx.fullmatch(getattr(args, name) or ""):
            print(f"::error::bad --{name} {getattr(args, name)!r}", file=sys.stderr)
            return 2
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        body = _read_ledger(args.repository, args.version)
        ledger = judge_ledger(body, args.repository, args.version, args.digest, args.commit, now)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(200).decode("utf-8", "replace").strip().replace("\n", " ")
        except Exception:  # noqa: BLE001
            detail = ""
        ledger = (UNKNOWN, f"ledger read failed: HTTP {exc.code} {detail}".rstrip())
    except Exception as exc:  # noqa: BLE001 - could not observe is unknown, never refuse/allow
        ledger = (UNKNOWN, f"ledger read failed: {type(exc).__name__}: {exc}")
    try:
        import yaml  # noqa: PLC0415 - only `check` needs it
        yml = judge_yaml(yaml.safe_load((ROOT / GATE).read_text()), args.image, args.version, now.date())
    except Exception as exc:  # noqa: BLE001
        yml = (UNKNOWN, f"{GATE} unreadable: {type(exc).__name__}: {exc}")
    agree = "unknown" if UNKNOWN in (ledger[0], yml[0]) else str(ledger[0] == yml[0]).lower()
    line = (f"ledger-shadow repository={args.repository} version={args.version} digest={args.digest} "
            f"ledger={ledger[0]} yaml={yml[0]} agree={agree}")
    print(line)
    print(f"  ledger: {ledger[1]}")
    print(f"  yaml:   {yml[1]}")
    level = "notice" if agree == "true" else "warning"
    print(f"::{level} title=release ledger (shadow)::ledger={ledger[0]} yaml={yml[0]} agree={agree}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Release ledger (shadow, enforces nothing)\n\n"
                    f"`{args.repository}` `{args.version}` `{args.digest}`\n\n"
                    "| source | verdict | why |\n|---|---|---|\n"
                    f"| ledger | {ledger[0]} | {ledger[1]} |\n| YAML allow | {yml[0]} | {yml[1]} |\n\n"
                    f"agree: **{agree}**\n")
    return 0


def _selftest() -> int:
    R, V = "mctlhq/mctl-api", "4.164.0"
    D, C = "sha256:" + "d" * 64, "c" * 40
    now = datetime.datetime(2026, 11, 18, tzinfo=datetime.timezone.utc)

    def grant(state="approved", digest=D, commit=C, amr=("mfa", "user"), expires="2026-11-20T09:14:30.720789Z",
              consumed=None, decision=True, gid="aar_1"):
        g: dict = {"approval": {"id": gid, "state": state, "expires_at": expires},
                   "artifact": {"repository": R, "version": V, "tag_commit": commit, "image_digest": digest}}
        if consumed:
            g["approval"]["consumed_at"] = consumed
        if decision and state in ("approved", "rejected"):
            g["decision"] = {"amr": list(amr)}
        return g

    def body(*grants):
        return {"schema_version": "1", "repository": R, "version": V, "grants": list(grants)}

    cases = [
        ("approved, mfa, unexpired", body(grant()), ALLOW),
        ("Go timestamp with nanoseconds", body(grant(expires="2026-11-20T09:14:30.123456789Z")), ALLOW),
        ("no grants", body(), REFUSE),
        ("only pending", body(grant(state="pending")), REFUSE),
        ("rejected", body(grant(state="rejected")), REFUSE),
        ("rejection outranks approval", body(grant(), grant(state="rejected", gid="aar_2")), REFUSE),
        ("approved another digest", body(grant(digest="sha256:" + "e" * 64)), REFUSE),
        ("approved another commit", body(grant(commit="f" * 40)), REFUSE),
        ("approved without mfa", body(grant(amr=("pwd",))), REFUSE),
        ("approved but expired", body(grant(expires="2026-11-17T00:00:00Z")), REFUSE),
        ("approved but consumed", body(grant(consumed="2026-11-17T10:00:00Z")), REFUSE),
        ("approved, no evidence", body(grant(decision=False)), UNKNOWN),
        ("approved, bad expiry", body(grant(expires="soon")), UNKNOWN),
        ("not an object", [], UNKNOWN),
        ("no grants list", {"repository": R, "version": V}, UNKNOWN),
        ("answer for another version", {**body(grant()), "version": "4.165.0"}, UNKNOWN),
        ("malformed row", body({"approval": None}), UNKNOWN),
        ("row for another release", body({**grant(), "artifact": {**grant()["artifact"], "version": "1.0.0"}}), UNKNOWN),
    ]
    bad = 0
    for name, b, want in cases:
        got = judge_ledger(b, R, V, D, C, now)[0]
        if got != want:
            bad += 1
            print(f"FAIL ledger {name}: got {got}, want {want}")
    I, today = "ghcr.io/mctlhq/mctl-api", now.date()

    def hold(*allow, held_from="4.155.0"):
        return {"version_holds": [{"name": "h", "repository": I, "held_from": held_from, "allow": list(allow)}]}

    rec = {"version": V, "grant": "x#1", "expires": datetime.date(2026, 12, 1)}
    ycases = [
        ("allow record", hold(rec), ALLOW),
        ("no allow record", hold(), REFUSE),
        ("expired record", hold({**rec, "expires": datetime.date(2026, 11, 1)}), REFUSE),
        ("below held_from", hold(held_from="5.0.0"), ALLOW),
        ("no hold for image", {"version_holds": []}, ALLOW),
        ("no version_holds", {}, UNKNOWN),
        ("expires not a date", hold({**rec, "expires": "2026-12-01"}), UNKNOWN),
    ]
    for name, d, want in ycases:
        got = judge_yaml(d, I, V, today)[0]
        if got != want:
            bad += 1
            print(f"FAIL yaml {name}: got {got}, want {want}")
    ua = _request("https://example.invalid/", {}).get_header("User-agent", "")
    if not ua or ua.lower().startswith("python-urllib"):
        bad += 1
        print(f"FAIL requests carry urllib's default User-Agent ({ua!r}), which Cloudflare refuses")
    total = len(cases) + len(ycases) + 1
    print(f"selftest: {total - bad}/{total} passed")
    return 1 if bad else 0


def main() -> int:
    if sys.argv[1:] == ["--selftest"]:
        return _selftest()
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    for name in ("repository", "version", "digest", "commit", "image"):
        c.add_argument(f"--{name}", required=True)
    return check(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
