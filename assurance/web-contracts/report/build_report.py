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
# non-consumer sites that cases/controls may name: reference targets, never a consumer row
FIXTURE_SITES = ("fixture-reference", "fixture-reference-wide", "fixture-checkbox", "fixture-reset", "fixture-broken")
FIXTURE_HOSTS = ("ui.fixture.test", "site.fixture.test")  # allowlist lives here, not in the checked file
# fullmatch everywhere: "$" would accept a trailing newline, and \d accepts non-ASCII digits
DIGEST_REF = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
SHA384_REF = re.compile(r"sha384-[A-Za-z0-9+/]{64}")
EXACT_SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
# any scheme, or a scheme-relative "//host"; runs to whitespace so no tail can leak
URL_RE = re.compile(r"(?<![A-Za-z0-9_/.:-])(?:[A-Za-z][A-Za-z0-9+.-]*:)?//\S+")
STATUSES = ("PASS", "FAIL", "NOT-RUN", "EXCEPTION-PENDING")


class InputError(Exception):
    """Unreadable or malformed input: a hard error, never an empty result."""


# --------------------------------------------------------------------------- URLs

def sanitize_url(url):
    if "\\" in url:
        return "[unparseable-url]"
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
            if isinstance(k, str):
                yield f"{path}.<key>", k
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
        if not isinstance(value, str) or not DIGEST_REF.fullmatch(value):
            bad.append(f"{label}: image must be pinned by @sha256:<64 hex>, got {value!r}")

    digest_image("playwright_image", pins.get("playwright_image"))
    digest_image("nginx_image", pins.get("nginx_image"))
    ver = pins.get("playwright_test_version")
    if not isinstance(ver, str) or not EXACT_SEMVER.fullmatch(ver):
        bad.append(f"playwright_test_version: must be an exact X.Y.Z, got {ver!r}")

    design = pins.get("mctl_design")
    if not isinstance(design, dict):
        bad.append("mctl_design: missing")
        design = {}
    if not isinstance(design.get("commit"), str) or not HEX40.fullmatch(design["commit"]):
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
            if not isinstance(h, dict) or not HEX64.fullmatch(str(h.get("sha256", ""))) \
                    or not SHA384_REF.fullmatch(str(h.get("sha384", ""))):
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
        if sc is not None and (not isinstance(sc, str) or not HEX40.fullmatch(sc)):
            bad.append(f"sites[{n}].source_commit: must be 40-hex or null, got {sc!r}")
        bp = s.get("breakpoint")
        if bp is not None and (isinstance(bp, bool) or not isinstance(bp, int) or bp <= 0):
            bad.append(f"sites[{n}].breakpoint: must be a positive integer or null, got {bp!r}")
        eb = s.get("expected_blocked", [])
        if not isinstance(eb, list) or not all(isinstance(e, str) and valid_expected_blocked(e) for e in eb):
            bad.append(f"sites[{n}].expected_blocked: must be a list of exact host/path strings (no scheme, query or wildcard)")
        if not valid_env(s.get("env", {})):
            bad.append(f"sites[{n}].env: must map upper-case names (not {ENV_RESERVED}) to short plain values without '@'")
        if not valid_tmpfs(s.get("tmpfs", [])):
            bad.append(f"sites[{n}].tmpfs: must be at most 4 distinct absolute paths without dot segments, not /, /proc, /sys or /dev")
        if mode == "not-run" and not (isinstance(s.get("not_run_reason"), str) and s["not_run_reason"].strip()):
            bad.append(f"sites[{n}]: mode not-run needs a not_run_reason")

    declared = pins.get("fixture_hosts")
    if not isinstance(declared, list) or not all(isinstance(h, str) for h in declared):
        bad.append("fixture_hosts: must be a list of strings")
    elif not set(declared) <= set(FIXTURE_HOSTS):
        bad.append(f"fixture_hosts: {sorted(set(declared) - set(FIXTURE_HOSTS))} not in the script allowlist")
    for where, text in _walk_strings(pins):
        for m in URL_RE.finditer(text):
            url = m.group(0)
            try:
                host = None if "\\" in url else urlsplit(url).hostname
            except ValueError:
                host = None
            if host not in FIXTURE_HOSTS:
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
        if c.get("site") not in SITES + FIXTURE_SITES:
            raise InputError(f"cases: {c['id']} names unknown site {c.get('site')!r}")
        for key in ("contract_id", "gate", "route_class", "viewport", "provenance", "exception"):
            if c.get(key) is not None and not isinstance(c[key], str):
                raise InputError(f"cases: {c['id']}.{key} must be a string")
        if c.get("kind", "case") not in ("case", "negative-control"):
            raise InputError(f"cases: {c['id']} has an unknown kind {c.get('kind')!r}")
    return cases, digest


# surefire-style rerun elements are a failed attempt: never read as a clean pass
JUNIT_CHILDREN = (("failure", "fail"), ("flakyFailure", "fail"), ("rerunFailure", "fail"),
                  ("error", "error"), ("flakyError", "error"), ("rerunError", "error"),
                  ("skipped", "skipped"))


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
        # a status attribute other than run/passed is not a pass (fail closed)
        st = (tc.get("status") or "").lower()
        if st in ("skipped", "disabled", "notrun", "not-run"):
            outcome, message = "skipped", f"status={st}"
        elif st not in ("", "run", "passed", "pass"):
            outcome, message = "error", f"unrecognised status={st}"
        for tag, label in JUNIT_CHILDREN:
            el = tc.find(tag)
            if el is not None:
                outcome = label
                message = el.get("message") or (el.text or "").strip().split("\n")[0]
                if label == "skipped" and not message:
                    # Playwright's JUnit reporter carries a skip reason as <property name="skip">
                    for prop in tc.iterfind("properties/property"):
                        if prop.get("name") == "skip":
                            message = prop.get("value") or ""
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
        if message.startswith("guard-blocked unexpected request(s)"):
            # Raised by the fixture teardown (Playwright reports it as <error message="guard-blocked unexpected ...">,
            # seen in the CI junit of run 45166785569), so the assertions may well have run: not a verdict either way.
            # Wca.get() throws "guard-blocked (reason)" mid-test, before an assertion, and keeps the older wording.
            return "NOT-RUN", "a request no case declared was blocked, so the case outcome is not a verdict: " + message
        return "NOT-RUN", "errored before its assertion" + (f": {message}" if message else "")
    if outcome == "fail":
        return "FAIL", message or "assertion failed"
    # an executed pass
    if case["site"] in SITES and site_mode != "image":
        return "NOT-RUN", f"pins mode is {site_mode!r}, a consumer result needs mode image"
    if case.get("exception") and not control:
        return "EXCEPTION-PENDING", f"{case['exception']} registered, pending owner sign-off"
    return "PASS", ""


FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
# host/path exactly as the guard logs it: lowercase host, then a path; never a scheme, query, port or wildcard
EXPECTED_BLOCKED_RE = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?/[A-Za-z0-9._~/-]*")


# Dummy environment a consumer image may be started with. Names are upper-case identifiers; PORT is forced by the
# harness. Values are a small, shell-inert character set and never carry credentials in a URL ('@' is refused). A real
# secret never belongs here: the file is public and the values are test placeholders. '@' is outside the value
# character set, so credentials in a URL cannot be written.
ENV_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
ENV_VALUE_RE = re.compile(r"[A-Za-z0-9._:/=?&()+,-]{1,200}")
ENV_RESERVED = ("PORT",)
TMPFS_RE = re.compile(r"/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+")


def valid_env(env):
    return (isinstance(env, dict)
            and all(isinstance(k, str) and ENV_NAME_RE.fullmatch(k) and k not in ENV_RESERVED
                    and isinstance(v, str) and ENV_VALUE_RE.fullmatch(v)
                    for k, v in env.items()))


def valid_tmpfs(paths):
    return (isinstance(paths, list) and len(paths) <= 4
            and all(isinstance(p, str) and TMPFS_RE.fullmatch(p)
                    and not any(seg in (".", "..") for seg in p.split("/"))
                    and p.split("/")[1] not in ("proc", "sys", "dev")
                    for p in paths) and len(set(paths)) == len(paths))


def valid_expected_blocked(entry):
    """Exact host/path as the guard logs it. fullmatch (a trailing newline never passes), and no dot segment, empty
    segment or empty host label, none of which can equal a normalised URL: they would be silent dead entries."""
    host, _, path = entry.partition("/")
    return (bool(EXPECTED_BLOCKED_RE.fullmatch(entry)) and ".." not in host and "//" not in "/" + path
            and "/../" not in "/" + path + "/" and not path.endswith("/.."))


def _counts_ok(per_test, totals):
    return (isinstance(per_test, dict) and isinstance(totals, dict)
            and all(isinstance(v, dict) and all(isinstance(n, int) for n in v.values()) for v in per_test.values())
            and all(isinstance(n, int) for n in totals.values()))


def load_substitutions(path):
    """What the guard answered locally (pinned design sheets, empty font sheets) and which declared, expected blocks it
    saw. None = not provided; a file that was given but cannot be read is an input error, never "none"."""
    if not path:
        return None
    try:
        doc = json.loads(Path(path).read_text())
        per_test, totals = doc["per_test"], doc["totals"]
        eb = doc["expected_blocked"]
        eb_per_test, eb_totals = eb["per_test"], eb["totals"]
        ok = _counts_ok(per_test, totals) and _counts_ok(eb_per_test, eb_totals)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InputError(f"substitutions file unreadable ({type(exc).__name__}): cannot say what was answered locally")
    if not ok:
        raise InputError("substitutions file malformed: cannot say what was answered locally")
    return {"per_test": per_test, "totals": totals, "expected_blocked": {"per_test": eb_per_test, "totals": eb_totals}}


def substitution_summary(subst):
    if subst is None:
        return {"status": "not-provided", "totals": {}, "expected_blocked": {}, "statement":
                "not provided: it is unknown whether any request was answered locally or declared-blocked"}
    totals, eb = subst["totals"], subst["expected_blocked"]["totals"]
    parts = []
    if totals:
        parts.append("requests answered locally, none reached their host: design sheets from the pinned mctl-design bytes"
                     + ("; web fonts were NOT loaded (font hosts answered with an empty stylesheet), so a layout result "
                        "that depends on font metrics is not evidence" if any(totals.get(h) for h in FONT_HOSTS) else ""))
    if eb:
        parts.append("requests to declared hosts were aborted, never answered (pins.json expected_blocked): the page ran "
                     "without those scripts and calls, so a result that depends on them is not evidence")
    return {"status": "computed", "totals": totals, "expected_blocked": eb,
            "statement": "; ".join(parts) if parts else "no request was answered locally and no declared block was seen"}


def build(junit_path, cases_path, pins_path, out_dir, artifact, attempt_id, substitutions_path=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("results.json", "matrix.md"):  # a hard error must not leave a prior verdict behind
        (out / stale).unlink(missing_ok=True)

    pins, pins_sha = load_json(pins_path, "pins")
    problems = check_pins(pins)
    if problems:
        raise InputError("pins rejected: " + "; ".join(sanitize_text(p) for p in problems[:5]))
    cases, cases_sha = load_cases(cases_path)
    runs = load_junit(junit_path)
    subst = load_substitutions(substitutions_path)
    junit_sha = sha256_file(junit_path)
    artifact_sha = sha256_file(artifact) if artifact else None
    site_pins = {s["name"]: s for s in pins["sites"]}

    # fail = a harness case FAILed (a fixture, a control, the guard); findings = a consumer case FAILed. Both make
    # "no compliance claim"; only a harness failure is a broken run (exit 1), a finding is evidence about the consumer
    results, control_problem, fail, findings = [], False, False, False
    if not any(c.get("kind", "case") == "negative-control" for c in cases):
        # no controls catalogued = the "every control must FAIL" guarantee is silently off
        control_problem = True
    for c in cases:
        status, reason = derive(c, runs.get(c["id"]), site_pins)
        control = c.get("kind", "case") == "negative-control"
        row = {"id": c["id"], "contract_id": c.get("contract_id"), "gate": c.get("gate"),
               "site": c["site"], "route_class": c.get("route_class"),
               "viewport": c.get("viewport"), "provenance": c.get("provenance", "not-run"),
               "kind": c.get("kind", "case"), "status": status, "reason": reason}
        if subst and subst["per_test"].get(c["id"]):
            row["answered_locally"] = subst["per_test"][c["id"]]
        if subst and subst["expected_blocked"]["per_test"].get(c["id"]):
            row["expected_blocked"] = subst["expected_blocked"]["per_test"][c["id"]]
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
            if c["site"] in SITES:
                findings = True
            else:
                fail = True
        results.append(row)

    per_site = {}
    for name in SITES:
        rows = [r for r in results if r["site"] == name and r["kind"] == "case"]
        counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
        # a PASS that ran while declared requests were aborted ran without scripts or calls the page expects:
        # it stays PASS (the assertion held) but it is never a compliance claim
        blind = sum(1 for r in rows if r["status"] == "PASS" and r.get("expected_blocked"))
        per_site[name] = {"mode": site_pins[name]["mode"], "gitops_tag": site_pins[name]["gitops_tag"],
                          "not_run_reason": site_pins[name].get("not_run_reason"),
                          "counts": counts, "cases": len(rows),
                          "pass_with_declared_blocks": blind,
                          "compliant": bool(rows) and counts["PASS"] == len(rows) and blind == 0}
    gates = {}
    for r in results:
        if r["gate"] and r["kind"] == "case":
            g = gates.setdefault(r["gate"], {s: 0 for s in STATUSES})
            g[r["status"]] += 1
    any_fail = fail or findings or control_problem
    summary_subst = substitution_summary(subst)
    # an entry declared for a site that ran but never seen in the run is stale or mistyped; for a site that did not
    # run, or when no record was given, it is unknown, never "fine"
    never = {}
    if subst is not None:
        seen = set(subst["expected_blocked"]["totals"])
        for name in SITES:
            if site_pins[name]["mode"] == "image":
                gone = sorted(set(site_pins[name].get("expected_blocked", [])) - seen)
                if gone:
                    never[name] = gone
    summary_subst["declared_never_observed"] = never
    if never:
        summary_subst["statement"] += "; declared but never observed (stale or mistyped?): " + ", ".join(
            f"{n}: {', '.join(v)}" for n, v in sorted(never.items()))
    doc = {"attempt_id": attempt_id, "disclaimer": DISCLAIMER, "pins": pins,
           "inputs": {"junit_sha256": junit_sha, "cases_sha256": cases_sha, "pins_sha256": pins_sha},
           "artifact_sha256": artifact_sha,
           "substitutions": summary_subst,
           "artifact_sha256_status": "computed" if artifact else "not-provided",
           "sites": per_site, "gates": gates, "results": results,
           "summary": {"compliance_claim": not any_fail and any(s["compliant"] for s in per_site.values()),
                       "failed_cases": [r["id"] for r in results if r["kind"] == "case" and r["status"] == "FAIL"],
                       "harness_failures": [r["id"] for r in results if r["kind"] == "case" and r["status"] == "FAIL"
                                            and r["site"] not in SITES],
                       "consumer_findings": [r["id"] for r in results if r["kind"] == "case" and r["status"] == "FAIL"
                                             and r["site"] in SITES],
                       "broken_controls": [r["id"] for r in results if r.get("control") == "BROKEN"]
                                       + ([] if any(r["kind"] == "negative-control" for r in results)
                                          else ["<no negative control catalogued>"]),
                       "statement": "no compliance claim" if any_fail else
                                    "per-site compliance only where every catalogued case is PASS"}}
    (out / "results.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    (out / "matrix.md").write_text(render_matrix(doc))
    if control_problem:
        print("negative control did not FAIL: scaffolding cannot detect failure", file=sys.stderr)
        return 2
    if fail:
        print("a catalogued harness case FAILed: no compliance claim", file=sys.stderr)
        return 1
    if findings:
        print("consumer finding(s): a consumer case FAILed, the harness itself is sound; no compliance claim", file=sys.stderr)
    return 0


def _cell(text):
    return sanitize_text(str(text if text is not None else "")).replace("|", "\\|").replace("\n", " ")


def _local(row):
    """A case that ran while the guard answered or aborted declared requests says so on its own row."""
    out = ""
    a = row.get("answered_locally")
    if a:
        out += " [answered locally: " + ", ".join(f"{h} x{n}" for h, n in sorted(a.items())) + "]"
    b = row.get("expected_blocked")
    if b:
        out += " [declared blocked: " + ", ".join(f"{h} x{n}" for h, n in sorted(b.items())) + "]"
    return out


def render_matrix(doc):
    L = [f"# Web contract preview assurance matrix", "",
         f"_{DISCLAIMER}_", "", f"Attempt: `{doc['attempt_id']}`  ",
         f"Artifact sha-256: `{doc['artifact_sha256'] or 'not provided'}`  ",
         f"mctl-design: `{doc['pins']['mctl_design']['commit']}` (css {doc['pins']['mctl_design']['css_version']})  ",
         f"Playwright image: `{doc['pins']['playwright_image']}`  ",
         f"Summary: {doc['summary']['statement']}  ",
         f"Consumer findings (FAIL): {len(doc['summary']['consumer_findings'])}; harness failures: {len(doc['summary']['harness_failures'])}  ",
         f"Substituted requests: {_cell(doc['substitutions']['statement'])}"
         + (f" (answered locally {_cell(json.dumps(doc['substitutions']['totals'], sort_keys=True))})" if doc['substitutions']['totals'] else "")
         + (f" (declared blocked {_cell(json.dumps(doc['substitutions']['expected_blocked'], sort_keys=True))})" if doc['substitutions']['expected_blocked'] else ""), "",
         "## Six-site matrix", "",
         "| Site | Mode | GitOps tag | PASS | FAIL | NOT-RUN | EXCEPTION-PENDING | Compliant | Reason |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, s in doc["sites"].items():
        c = s["counts"]
        L.append(f"| {name} | {s['mode']} | {s['gitops_tag']} | {c['PASS']} | {c['FAIL']} | {c['NOT-RUN']} | "
                 f"{c['EXCEPTION-PENDING']} | {'yes' if s['compliant'] else 'no'} | {_cell(s['not_run_reason'])}"
                 + (f" {s['pass_with_declared_blocks']} PASS ran with declared blocks: never a compliance claim." if s["pass_with_declared_blocks"] else "")
                 + " |")
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
                 f"{status} | {_cell(r['provenance'])} | {_cell(r['reason'])}{_local(r)} |")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- main

class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse exits 2 by default, which here means "control did not FAIL"
        print(f"ERROR: {message}", file=sys.stderr)
        raise SystemExit(3)


def main(argv=None):
    here = Path(__file__).resolve().parent
    ap = _Parser(description=__doc__.split("\n")[0])
    ap.add_argument("--check-pins", action="store_true")
    ap.add_argument("--design-repo")
    ap.add_argument("--pins", default=str(here.parent / "pins.json"))
    ap.add_argument("--junit")
    ap.add_argument("--cases")
    ap.add_argument("--out-dir")
    ap.add_argument("--artifact")
    ap.add_argument("--attempt-id")
    ap.add_argument("--substitutions")
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
        return build(args.junit, args.cases, args.pins, args.out_dir, args.artifact, attempt, args.substitutions)
    except InputError as exc:
        print(f"ERROR: {sanitize_text(str(exc))}", file=sys.stderr)
        return 3
    except Exception as exc:  # an uncaught traceback exits 1, which means "a case FAILed"
        print(f"ERROR: unexpected {type(exc).__name__}: {sanitize_text(str(exc))}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
