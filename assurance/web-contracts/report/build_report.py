#!/usr/bin/env python3
"""Fail-closed report builder for the web contract preview assurance harness.

Preview assurance only; not production conformance (mctlhq/mctl-gitops#2929).

  build_report.py --check-pins [--pins PATH] [--design-repo PATH]
  build_report.py --junit junit.xml --cases cases.json --pins pins.json
                  --out-dir DIR [--artifact FILE] [--attempt-id ID]

Rules ("could not observe" is never "observed absent"):
  * The report iterates over cases.json, never over the JUnit file. A catalogued
    case without an executed testcase is NOT-RUN, never PASS.
  * skipped, or an error raised before the assertion  -> NOT-RUN (with a reason)
  * failure                                           -> FAIL
  * pass on a registered exception (EX-n)             -> EXCEPTION-PENDING
  * pass on a site whose pins mode is not "image"     -> NOT-RUN (contradiction)
  * a negative control must FAIL; PASS or NOT-RUN there exits 2
  * unreadable or malformed junit/cases/pins is a hard error (exit 3), never an
    empty result
  * every URL in any emitted text is reduced to host + path

Exit codes: 0 ok, 1 a non-control case FAILed (no compliance claim),
2 a negative control did not FAIL, 3 unreadable/malformed input or pin check failed.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from base64 import b64encode
from pathlib import Path
from urllib.parse import urlsplit

DISCLAIMER = "preview assurance only; not production conformance"
SITES = ("mctl-web", "mctl-docs", "mctl-telegram", "mctl-academy", "mctl-alice", "seerrsense")
MODES = ("image", "fixture-only", "not-run")
SHEETS = ("mctl.css", "global.css", "prose.css", "site.css")
DIGEST_REF = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
EXACT_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
URL_RE = re.compile(r"https?://[^\s'\"<>)\]]+", re.IGNORECASE)
STATUSES = ("PASS", "FAIL", "NOT-RUN", "EXCEPTION-PENDING")


class InputError(Exception):
    """Unreadable or malformed input: a hard error, never an empty result."""


# --------------------------------------------------------------------------- URLs

def sanitize_url(url):
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return "[unparseable-url]"
    if not host:
        return "[unparseable-url]"
    return host + parts.path


def sanitize_text(text):
    return URL_RE.sub(lambda m: sanitize_url(m.group(0)), text or "")


# --------------------------------------------------------------------------- IO

def load_json(path, what):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError) as exc:
        raise InputError(f"{what} unreadable or malformed: {path}: {type(exc).__name__}")


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        raise InputError(f"artifact unreadable: {path}: {type(exc).__name__}")


# --------------------------------------------------------------------------- pins

def _walk_strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def check_pins(pins):
    """Return a list of problems; empty means the pins are acceptable."""
    bad = []
    if not isinstance(pins, dict):
        return ["pins: top level is not an object"]

    def digest_image(label, value, nullable=False):
        if value is None and nullable:
            return
        if not isinstance(value, str) or not DIGEST_REF.match(value):
            bad.append(f"{label}: image must be pinned by @sha256:<64 hex>, got {value!r}")

    digest_image("playwright_image", pins.get("playwright_image"))
    digest_image("nginx_image", pins.get("nginx_image"))
    ver = pins.get("playwright_test_version")
    if not isinstance(ver, str) or not EXACT_SEMVER.match(ver):
        bad.append(f"playwright_test_version: must be an exact X.Y.Z, got {ver!r}")

    design = pins.get("mctl_design")
    if not isinstance(design, dict):
        bad.append("mctl_design: missing")
        design = {}
    if not isinstance(design.get("commit"), str) or not HEX40.match(design["commit"]):
        bad.append(f"mctl_design.commit: must be 40 lowercase hex, got {design.get('commit')!r}")
    contracts = design.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        bad.append("mctl_design.contracts: missing or empty")
    else:
        for c in contracts:
            if not isinstance(c, dict) or not c.get("id"):
                bad.append(f"mctl_design.contracts: entry without id: {c!r}")
    sheets = design.get("sheets")
    versions = [design.get("css_version")] + list(design.get("also_verified_versions") or [])
    if not isinstance(sheets, dict):
        bad.append("mctl_design.sheets: missing")
        sheets = {}
    for v in versions:
        entry = sheets.get(v) if isinstance(v, str) else None
        if not isinstance(entry, dict):
            bad.append(f"mctl_design.sheets[{v}]: missing")
            continue
        for f in SHEETS:
            h = entry.get(f)
            if not isinstance(h, dict) or not re.match(r"^[0-9a-f]{64}$", str(h.get("sha256", ""))) \
                    or not re.match(r"^sha384-[A-Za-z0-9+/]{64}$", str(h.get("sha384", ""))):
                bad.append(f"mctl_design.sheets[{v}][{f}]: needs a 64-hex sha256 and a sha384-<base64> value")

    sites = pins.get("sites")
    if not isinstance(sites, list):
        bad.append("sites: missing")
        sites = []
    names = [s.get("name") if isinstance(s, dict) else None for s in sites]
    if sorted(n for n in names if n) != sorted(SITES) or len(names) != len(SITES):
        bad.append(f"sites: must list exactly {sorted(SITES)} once each, got {names}")
    for s in sites:
        if not isinstance(s, dict):
            bad.append(f"sites: entry is not an object: {s!r}")
            continue
        n = s.get("name")
        mode = s.get("mode")
        if mode not in MODES:
            bad.append(f"sites[{n}].mode: must be one of {MODES}, got {mode!r}")
        if not isinstance(s.get("gitops_tag"), str) or not s["gitops_tag"]:
            bad.append(f"sites[{n}].gitops_tag: missing")
        digest_image(f"sites[{n}].image", s.get("image"), nullable=True)
        if mode == "image" and s.get("image") is None:
            bad.append(f"sites[{n}]: mode image requires a digest-pinned image, got null")
        if s.get("observed_image_digest") is not None:
            digest_image(f"sites[{n}].observed_image_digest", s["observed_image_digest"])
        sc = s.get("source_commit")
        if sc is not None and (not isinstance(sc, str) or not HEX40.match(sc)):
            bad.append(f"sites[{n}].source_commit: must be 40-hex or null, got {sc!r}")
        bp = s.get("breakpoint")
        if bp is not None and (isinstance(bp, bool) or not isinstance(bp, int) or bp <= 0):
            bad.append(f"sites[{n}].breakpoint: must be a positive integer or null, got {bp!r}")
        if mode == "not-run" and not (isinstance(s.get("not_run_reason"), str) and s["not_run_reason"].strip()):
            bad.append(f"sites[{n}]: mode not-run needs a not_run_reason")

    fixture_hosts = pins.get("fixture_hosts")
    if not isinstance(fixture_hosts, list) or not all(isinstance(h, str) for h in fixture_hosts):
        bad.append("fixture_hosts: must be a list of strings")
        fixture_hosts = []
    for where, text in _walk_strings(pins):
        for m in URL_RE.finditer(text):
            try:
                host = urlsplit(m.group(0)).hostname
            except ValueError:
                host = None
            if host not in fixture_hosts:
                bad.append(f"{where}: URL to a non-fixture host: {sanitize_url(m.group(0))}")
    return bad


def _git_bytes(repo, *args):
    try:
        return subprocess.check_output(["git", "-C", repo, *args], stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"") or b""
        raise InputError(f"git {' '.join(args[:2])} failed in design repo: "
                         f"{type(exc).__name__} {detail.decode('utf-8', 'replace').strip()[:200]}")


def check_design_repo(pins, repo):
    """Verify the pinned commit, the sheet directory and both hashes. Raises InputError
    when the repo cannot be read; returns a list of mismatches otherwise."""
    design = pins["mctl_design"]
    commit = design["commit"]
    _git_bytes(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    bad = []
    versions = [design["css_version"]] + list(design.get("also_verified_versions") or [])
    for v in versions:
        base = f"apps/storybook/public/{v}"
        listed = _git_bytes(repo, "ls-tree", "--name-only", commit, base + "/").decode().split("\n")
        have = {os.path.basename(p) for p in listed if p}
        if not have:
            bad.append(f"{base}/ is absent at {commit}")
            continue
        for f in SHEETS:
            if f not in have:
                bad.append(f"{base}/{f} is absent at {commit}")
                continue
            blob = _git_bytes(repo, "show", f"{commit}:{base}/{f}")
            want = design["sheets"][v][f]
            got256 = hashlib.sha256(blob).hexdigest()
            got384 = "sha384-" + b64encode(hashlib.sha384(blob).digest()).decode()
            if got256 != want["sha256"]:
                bad.append(f"{base}/{f}: sha256 {got256} != pinned {want['sha256']}")
            if got384 != want["sha384"]:
                bad.append(f"{base}/{f}: sha384 {got384} != pinned {want['sha384']}")
    return bad


def run_check_pins(args):
    pins, _ = load_json(args.pins, "pins")
    problems = check_pins(pins)
    if problems:
        for p in problems:
            print(f"PIN-FAIL: {sanitize_text(p)}", file=sys.stderr)
        return 3
    print("pins: OK (digest pins, 40-hex commits, exact versions, no non-fixture URLs)")
    if not args.design_repo:
        print("design-sheets: NOT-RUN (no --design-repo given; the commit, the sheet directory "
              "and the sha256/sha384 values were NOT verified)")
        return 0
    mism = check_design_repo(pins, args.design_repo)
    if mism:
        for m in mism:
            print(f"PIN-FAIL: {m}", file=sys.stderr)
        return 3
    print("design-sheets: OK (pinned commit present, sheet directories present, "
          "sha256 and sha384 agree with pins.json)")
    return 0


# --------------------------------------------------------------------------- report

def load_cases(path):
    data, digest = load_json(path, "cases")
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        raise InputError("cases: needs a non-empty 'cases' list")
    seen = set()
    for c in cases:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"]:
            raise InputError(f"cases: entry without id: {c!r}")
        if c["id"] in seen:
            raise InputError(f"cases: duplicate id {c['id']}")
        seen.add(c["id"])
        if not isinstance(c.get("site"), str):
            raise InputError(f"cases: {c['id']} has no site")
        if c.get("kind", "case") not in ("case", "negative-control"):
            raise InputError(f"cases: {c['id']} has an unknown kind {c.get('kind')!r}")
    return cases, digest


def load_junit(path):
    """Map testcase name -> list of (outcome, message). A malformed file is an error."""
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        raise InputError(f"junit unreadable or malformed: {path}: {type(exc).__name__}")
    root = tree.getroot()
    if root.tag not in ("testsuites", "testsuite"):
        raise InputError(f"junit: unexpected root element <{root.tag}>")
    out = {}
    for tc in root.iter("testcase"):
        name = tc.get("name")
        if not name:
            raise InputError("junit: testcase without a name")
        outcome, message = "pass", ""
        for tag, label in (("failure", "fail"), ("error", "error"), ("skipped", "skipped")):
            el = tc.find(tag)
            if el is not None:
                outcome = label
                message = el.get("message") or (el.text or "").strip().split("\n")[0]
                break
        out.setdefault(name, []).append((outcome, message))
    return out


def classify(runs):
    """Collapse the executions of one testcase, worst outcome first (fail-closed)."""
    if runs is None:
        return "missing", "no executed testcase for this catalogued case"
    for want in ("fail", "error", "skipped"):
        for outcome, message in runs:
            if outcome == want:
                return outcome, message
    return "pass", ""


def derive(case, runs, site_pins):
    """Return (status, reason) for one catalogued case. Never PASS without an executed pass."""
    outcome, message = classify(runs)
    message = sanitize_text(message)
    control = case.get("kind", "case") == "negative-control"
    site_mode = site_pins.get(case["site"], {}).get("mode") if case["site"] in SITES else None
    if outcome == "missing":
        return "NOT-RUN", message
    if outcome == "skipped":
        return "NOT-RUN", "skipped" + (f": {message}" if message else "")
    if outcome == "error":
        return "NOT-RUN", "errored before its assertion" + (f": {message}" if message else "")
    if outcome == "fail":
        return "FAIL", message or "assertion failed"
    # an executed pass
    if case["site"] in SITES and site_mode != "image":
        return "NOT-RUN", f"pins mode is {site_mode!r}, a consumer result needs mode image"
    if case.get("exception") and not control:
        return "EXCEPTION-PENDING", f"{case['exception']} registered, pending owner sign-off"
    return "PASS", ""


def build(junit_path, cases_path, pins_path, out_dir, artifact, attempt_id):
    pins, pins_sha = load_json(pins_path, "pins")
    problems = check_pins(pins)
    if problems:
        raise InputError("pins rejected: " + "; ".join(sanitize_text(p) for p in problems[:5]))
    cases, cases_sha = load_cases(cases_path)
    runs = load_junit(junit_path)
    junit_sha = sha256_file(junit_path)
    artifact_sha = sha256_file(artifact) if artifact else None
    site_pins = {s["name"]: s for s in pins["sites"]}

    results, control_problem, fail = [], False, False
    for c in cases:
        status, reason = derive(c, runs.get(c["id"]), site_pins)
        control = c.get("kind", "case") == "negative-control"
        row = {"id": c["id"], "contract_id": c.get("contract_id"), "gate": c.get("gate"),
               "site": c["site"], "route_class": c.get("route_class"),
               "viewport": c.get("viewport"), "provenance": c.get("provenance", "not-run"),
               "kind": c.get("kind", "case"), "status": status, "reason": reason}
        if control:
            # The inversion: a control is healthy only when the detector saw it FAIL.
            if status == "FAIL":
                row["control"] = "DETECTED"
            else:
                row["control"] = "BROKEN"
                row["reason"] = ("scaffolding cannot detect failure: control " +
                                 ("passed" if status in ("PASS", "EXCEPTION-PENDING") else "did not run"))
                control_problem = True
        elif status == "FAIL":
            fail = True
        results.append(row)

    per_site = {}
    for name in SITES:
        rows = [r for r in results if r["site"] == name and r["kind"] == "case"]
        counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
        per_site[name] = {"mode": site_pins[name]["mode"], "gitops_tag": site_pins[name]["gitops_tag"],
                          "not_run_reason": site_pins[name].get("not_run_reason"),
                          "counts": counts, "cases": len(rows),
                          "compliant": bool(rows) and counts["PASS"] == len(rows)}
    gates = {}
    for r in results:
        if r["gate"] and r["kind"] == "case":
            g = gates.setdefault(r["gate"], {s: 0 for s in STATUSES})
            g[r["status"]] += 1
    any_fail = fail or control_problem
    doc = {"attempt_id": attempt_id, "disclaimer": DISCLAIMER, "pins": pins,
           "inputs": {"junit_sha256": junit_sha, "cases_sha256": cases_sha, "pins_sha256": pins_sha},
           "artifact_sha256": artifact_sha,
           "artifact_sha256_status": "computed" if artifact else "not-provided",
           "sites": per_site, "gates": gates, "results": results,
           "summary": {"compliance_claim": not any_fail and any(s["compliant"] for s in per_site.values()),
                       "failed_cases": [r["id"] for r in results if r["kind"] == "case" and r["status"] == "FAIL"],
                       "broken_controls": [r["id"] for r in results if r.get("control") == "BROKEN"],
                       "statement": "no compliance claim" if any_fail else
                                    "per-site compliance only where every catalogued case is PASS"}}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    (out / "matrix.md").write_text(render_matrix(doc))
    if control_problem:
        print("negative control did not FAIL: scaffolding cannot detect failure", file=sys.stderr)
        return 2
    if fail:
        print("a catalogued case FAILed: no compliance claim", file=sys.stderr)
        return 1
    return 0


def _cell(text):
    return sanitize_text(str(text if text is not None else "")).replace("|", "\\|").replace("\n", " ")


def render_matrix(doc):
    L = [f"# Web contract preview assurance matrix", "",
         f"_{DISCLAIMER}_", "", f"Attempt: `{doc['attempt_id']}`  ",
         f"Artifact sha-256: `{doc['artifact_sha256'] or 'not provided'}`  ",
         f"mctl-design: `{doc['pins']['mctl_design']['commit']}` (css {doc['pins']['mctl_design']['css_version']})  ",
         f"Playwright image: `{doc['pins']['playwright_image']}`  ",
         f"Summary: {doc['summary']['statement']}", "",
         "## Six-site matrix", "",
         "| Site | Mode | GitOps tag | PASS | FAIL | NOT-RUN | EXCEPTION-PENDING | Compliant | Reason |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, s in doc["sites"].items():
        c = s["counts"]
        L.append(f"| {name} | {s['mode']} | {s['gitops_tag']} | {c['PASS']} | {c['FAIL']} | {c['NOT-RUN']} | "
                 f"{c['EXCEPTION-PENDING']} | {'yes' if s['compliant'] else 'no'} | {_cell(s['not_run_reason'])} |")
    L += ["", "## Gates", "", "| Gate | PASS | FAIL | NOT-RUN | EXCEPTION-PENDING |", "| --- | --- | --- | --- | --- |"]
    for g in sorted(doc["gates"]):
        c = doc["gates"][g]
        L.append(f"| {g} | {c['PASS']} | {c['FAIL']} | {c['NOT-RUN']} | {c['EXCEPTION-PENDING']} |")
    L += ["", "## Crosswalk (AC / G1-G4 to executed test)", "",
          "| Test ID | Contract ID | Gate | Site | Status | Provenance | Reason |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in doc["results"]:
        status = r["status"] + (f" (control {r['control']})" if "control" in r else "")
        L.append(f"| {_cell(r['id'])} | {_cell(r['contract_id'])} | {_cell(r['gate'])} | {_cell(r['site'])} | "
                 f"{status} | {_cell(r['provenance'])} | {_cell(r['reason'])} |")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- main

def main(argv=None):
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check-pins", action="store_true")
    ap.add_argument("--design-repo")
    ap.add_argument("--pins", default=str(here.parent / "pins.json"))
    ap.add_argument("--junit")
    ap.add_argument("--cases")
    ap.add_argument("--out-dir")
    ap.add_argument("--artifact")
    ap.add_argument("--attempt-id")
    args = ap.parse_args(argv)
    try:
        if args.check_pins:
            return run_check_pins(args)
        if not (args.junit and args.cases and args.out_dir):
            raise InputError("report mode needs --junit, --cases and --out-dir")
        attempt = args.attempt_id
        if not attempt:
            run, att = os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT")
            attempt = f"{run}-{att}" if run and att else str(uuid.uuid4())
        return build(args.junit, args.cases, args.pins, args.out_dir, args.artifact, attempt)
    except InputError as exc:
        print(f"ERROR: {sanitize_text(str(exc))}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
