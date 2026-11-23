"""Fail-closed mapping of the web contract assurance report (mctlhq/mctl-gitops#2929, task 3).

Runs assurance/web-contracts/report/build_report.py as a subprocess against synthetic
JUnit files generated here. No browser, no network. Every check below was also proven
red by mutating build_report.py (see the PR description), because a detector that can
only pass is not a detector.
"""
import copy
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
from base64 import b64encode

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "assurance/web-contracts/report/build_report.py"
PINS = json.loads((ROOT / "assurance/web-contracts/pins.json").read_text())
SHA = "a" * 64
FIXTURE_SITE = "fixture-reference"

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:600]}")


def run(*args):
    p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def junit(entries):
    """entries: list of (name, outcome, message); outcome pass|fail|error|skipped."""
    out = ['<?xml version="1.0"?>', '<testsuites><testsuite name="s">']
    for name, outcome, msg in entries:
        body = {"pass": "", "fail": f'<failure message="{msg}"/>', "error": f'<error message="{msg}"/>',
                "skipped": f'<skipped message="{msg}"/>'}[outcome]
        out.append(f'<testcase name="{name}">{body}</testcase>')
    out.append("</testsuite></testsuites>")
    return "\n".join(out)


def case(cid, site=FIXTURE_SITE, **kw):
    return dict({"id": cid, "contract_id": "AC-HDR-8", "gate": "G1", "site": site,
                 "route_class": "L", "viewport": "375", "provenance": "[PREVIEW]"}, **kw)


def pins_with(mutate=None):
    p = copy.deepcopy(PINS)
    if mutate:
        mutate(p)
    return p


def report(cases, entries, pins=None, junit_text=None, control=True):
    """Run the report once. Returns (exit, results_dict_or_None, matrix_text_or_None, stderr).
    The catalog must hold a negative control, so one that FAILs is added unless control=False
    or the catalog already has one (an empty catalog stays empty)."""
    if control and cases and not any(c.get("kind") == "negative-control" for c in cases):
        cases = cases + [case("CTL-DEFAULT", kind="negative-control")]
        entries = list(entries) + [("CTL-DEFAULT", "fail", "detected")]
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "junit.xml").write_text(junit_text if junit_text is not None else junit(entries))
        (d / "cases.json").write_text(json.dumps({"cases": cases}))
        (d / "pins.json").write_text(json.dumps(pins if pins is not None else PINS))
        rc, _, err = run("--junit", d / "junit.xml", "--cases", d / "cases.json", "--pins", d / "pins.json",
                         "--out-dir", d / "out", "--attempt-id", "t-1")
        res = d / "out/results.json"
        mx = d / "out/matrix.md"
        return (rc, json.loads(res.read_text()) if res.exists() else None,
                mx.read_text() if mx.exists() else None, err)


def status_of(results, cid):
    return next(r for r in results["results"] if r["id"] == cid)["status"]


# --- fail-closed result mapping -------------------------------------------------
rc, res, mx, err = report([case("T-PASS")], [("T-PASS", "pass", "")])
check("executed pass is PASS and exits 0", rc == 0 and status_of(res, "T-PASS") == "PASS", (rc, err))

rc, res, _, err = report([case("T-FAIL")], [("T-FAIL", "fail", "boom")])
check("failure is FAIL and exits 1", rc == 1 and status_of(res, "T-FAIL") == "FAIL", (rc, err))
check("failure carries the no-compliance statement", res and res["summary"]["statement"] == "no compliance claim")

rc, res, _, _ = report([case("T-SKIP")], [("T-SKIP", "skipped", "no browser")])
check("skipped becomes NOT-RUN, never PASS", rc == 0 and status_of(res, "T-SKIP") == "NOT-RUN"
      and "no browser" in res["results"][0]["reason"], res)

rc, res, _, _ = report([case("T-MISS")], [("OTHER", "pass", "")])
check("missing testcase becomes NOT-RUN", rc == 0 and status_of(res, "T-MISS") == "NOT-RUN", res)

rc, res, _, _ = report([case("T-ERR")], [("T-ERR", "error", "launch failed")])
check("error before the assertion becomes NOT-RUN", rc == 0 and status_of(res, "T-ERR") == "NOT-RUN", res)

rc, res, _, _ = report([case("T-DUP")], [("T-DUP", "pass", ""), ("T-DUP", "fail", "flaky")])
check("a duplicate testcase with a failure is FAIL (worst outcome wins)",
      rc == 1 and status_of(res, "T-DUP") == "FAIL", res)

rc, res, _, _ = report([case("T-EX", exception="EX-1")], [("T-EX", "pass", "")])
check("pass on a registered exception is EXCEPTION-PENDING, not PASS",
      rc == 0 and status_of(res, "T-EX") == "EXCEPTION-PENDING", res)

rc, res, _, _ = report([case("T-EXF", exception="EX-1")], [("T-EXF", "fail", "x")])
check("failure on a registered exception is still FAIL", rc == 1 and status_of(res, "T-EXF") == "FAIL", res)

def to_not_run(p):
    # pinned here, not read from the live pins.json: promoting a consumer there must not change this test
    s = next(s for s in p["sites"] if s["name"] == "mctl-web")
    s["mode"], s["image"] = "not-run", None
    s["not_run_reason"] = "test: forced not-run"


rc, res, _, _ = report([case("T-CONS", site="mctl-web")], [("T-CONS", "pass", "")], pins=pins_with(to_not_run))
check("consumer pass while pins mode is not-run is NOT-RUN (contradiction)",
      status_of(res, "T-CONS") == "NOT-RUN", res)


def to_image(p):
    s = next(s for s in p["sites"] if s["name"] == "mctl-web")
    s["mode"], s["image"], s["not_run_reason"] = "image", s["observed_image_digest"], None


rc, res, _, err = report([case("T-CONS2", site="mctl-web")], [("T-CONS2", "pass", "")], pins=pins_with(to_image))
check("consumer pass with mode image is PASS", rc == 0 and status_of(res, "T-CONS2") == "PASS", (rc, err))

rc, res, _, _ = report([case("T-A"), case("T-B")], [("T-A", "pass", "")])
check("only the executed case passes when another is unmapped",
      status_of(res, "T-A") == "PASS" and status_of(res, "T-B") == "NOT-RUN"
      , res)
_, res, _, _ = report([case("W-A", site="mctl-web"), case("W-B", site="mctl-web")],
                      [("W-A", "pass", "")], pins=pins_with(to_image))
check("a site is not compliant while any catalogued case is NOT-RUN",
      res["sites"]["mctl-web"]["compliant"] is False and res["summary"]["compliance_claim"] is False, res)
_, res, _, _ = report([case("W-A", site="mctl-web"), case("W-B", site="mctl-web")],
                      [("W-A", "pass", ""), ("W-B", "pass", "")], pins=pins_with(to_image))
check("a site is compliant when every catalogued case is PASS",
      res["sites"]["mctl-web"]["compliant"] is True, res)

# --- negative controls ------------------------------------------------------------
rc, res, _, err = report([case("C-1", kind="negative-control")], [("C-1", "pass", "")])
check("a negative control that PASSES exits 2", rc == 2 and "cannot detect failure" in err, (rc, err))
check("the broken control is recorded in results", res and res["summary"]["broken_controls"] == ["C-1"], res)

rc, res, _, err = report([case("C-2", kind="negative-control")], [("C-2", "skipped", "x")])
check("a negative control that did not run exits 2 (unknown outranks)", rc == 2, (rc, err))

rc, res, _, err = report([case("C-3", kind="negative-control")], [("C-3", "fail", "detected")])
check("a negative control that FAILs is healthy and exits 0",
      rc == 0 and res["results"][0]["control"] == "DETECTED", (rc, err))
check("a detected control does not mark a failure", res["summary"]["failed_cases"] == [], res)

# --- URL sanitization -------------------------------------------------------------
dirty = "https://user:pw@evil.example/a/b?token=SECRET#frag"
rc, res, mx, _ = report([case("T-URL")], [("T-URL", "fail", f"GET {dirty} blocked")])
blob = json.dumps(res) + (mx or "")
check("URL is reduced to host and path", "evil.example/a/b" in blob, blob[:300])
check("query, fragment and userinfo are stripped everywhere",
      not any(s in blob for s in ("SECRET", "frag", "user:pw", "token=")), blob[:300])

rc, res, mx, _ = report([case("T-BS")], [("T-BS", "fail", "GET http://evil.example\\@h.test/p?token=SECRET x")])
check("a URL with a backslash is not trusted: reduced to a placeholder",
      "[unparseable-url]" in json.dumps(res) and "SECRET" not in json.dumps(res) + (mx or ""), res)
rc, res, mx, _ = report([case("T-PS")], [("T-PS", "fail", "GET ftp://u:pw@h.test/x//y and //h.test/z?q=SECRET")])
check("non-http and scheme-relative URLs are reduced too",
      not any(x in json.dumps(res) for x in ("pw", "SECRET", "u:")), res)

# --- outputs ----------------------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    (d / "junit.xml").write_text(junit([("T-OUT", "pass", ""), ("C-OUT", "fail", "x")]))
    (d / "cases.json").write_text(json.dumps({"cases": [case("T-OUT"), case("C-OUT", kind="negative-control")]}))
    (d / "art.tgz").write_bytes(b"artifact-bytes")
    rc, _, err = run("--junit", d / "junit.xml", "--cases", d / "cases.json", "--out-dir", d / "o",
                     "--artifact", d / "art.tgz", "--attempt-id", "run-7")
    out = json.loads((d / "o/results.json").read_text()) if (d / "o/results.json").exists() else {}
    mx = (d / "o/matrix.md").read_text() if (d / "o/matrix.md").exists() else ""
    check("results.json carries attempt id, pins and artifact sha-256",
          rc == 0 and out.get("attempt_id") == "run-7"
          and out.get("artifact_sha256") == hashlib.sha256(b"artifact-bytes").hexdigest()
          and out.get("pins", {}).get("playwright_image") == PINS["playwright_image"], (rc, err))
    check("matrix.md lists the six sites, the crosswalk and the disclaimer",
          all(s in mx for s in ("mctl-web", "mctl-docs", "mctl-telegram", "mctl-academy", "mctl-alice", "seerrsense"))
          and "Crosswalk" in mx and "preview assurance only; not production conformance" in mx, mx[:200])
    rc, _, err = run("--junit", d / "junit.xml", "--cases", d / "cases.json", "--out-dir", d / "o2",
                     "--artifact", d / "missing.tgz")
    check("an unreadable artifact is a hard error, not a null digest", rc == 3, (rc, err))

# --- review round 2: controls must exist, sites must be known, outcome precedence -----
rc, res, _, err = report([case("T-NC")], [("T-NC", "pass", "")], control=False)
check("a catalog with no negative control exits 2 and makes no compliance claim",
      rc == 2 and res and res["summary"]["compliance_claim"] is False
      and res["summary"]["broken_controls"] == ["<no negative control catalogued>"], (rc, err))

rc, res, _, err = report([case("T-TYPO", site="mctl-wbe")], [("T-TYPO", "pass", "")])
check("a case naming an unknown site exits 3 and writes no result", rc == 3 and res is None, (rc, err))
rc, res, _, err = report([case("T-GATE", gate=["x"])], [("T-GATE", "pass", "")])
check("a non-string case field exits 3 with a validation message", rc == 3 and res is None and "must be a string" in err, (rc, err))

rc, res, _, _ = report([case("T-EF")], [("T-EF", "error", "e"), ("T-EF", "fail", "f")])
check("duplicate error then fail is FAIL (fail outranks error)", rc == 1 and status_of(res, "T-EF") == "FAIL", res)

rc, res, _, _ = report([case("T-NEST")], [], junit_text=(
    '<testsuites><testsuite name="a"><testsuite name="b"><testcase name="T-NEST"><failure message="n"/>'
    '</testcase></testsuite></testsuite></testsuites>'))
check("a testcase in a nested testsuite is found", status_of(res, "T-NEST") == "FAIL", res)

rc, res, _, _ = report([case("T-NN")], [], junit_text='<testsuites><testsuite><testcase><failure/></testcase></testsuite></testsuites>')
check("a testcase without a name exits 3", rc == 3 and res is None)

for label, body, want in (("flakyFailure", "<flakyFailure message='f'/>", "FAIL"),
                          ("rerunError", "<rerunError message='f'/>", "NOT-RUN")):
    rc, res, _, _ = report([case("T-X")], [], junit_text=
        f'<testsuites><testsuite><testcase name="T-X">{body}</testcase></testsuite></testsuites>')
    check(f"a {label} child is never a clean pass", status_of(res, "T-X") == want, res)
rc, res, _, _ = report([case("T-ST")], [], junit_text=
    '<testsuites><testsuite><testcase name="T-ST" status="skipped"/></testsuite></testsuites>')
check("a status=skipped attribute is NOT-RUN with its reason", status_of(res, "T-ST") == "NOT-RUN"
      and res["results"][0]["reason"].startswith("skipped"), res)
# Playwright's JUnit reporter carries the skip reason in <properties>, not on <skipped>
rc, res, _, _ = report([case("T-PW")], [], junit_text=
    '<testsuites><testsuite><testcase name="T-PW"><properties><property name="skip" value="breakpoint unknown '
    'see https://mctl.ai/x?q=1"/></properties><skipped></skipped></testcase></testsuite></testsuites>')
check("a Playwright skip reason is kept and sanitized", status_of(res, "T-PW") == "NOT-RUN"
      and "breakpoint unknown" in res["results"][0]["reason"] and "q=1" not in res["results"][0]["reason"], res)
for name in ("fixture-checkbox", "fixture-reference-wide", "fixture-broken"):
    rc, res, _, err = report([case("T-FX", site=name)], [("T-FX", "pass", "")])
    check(f"{name} is an accepted fixture site", rc == 0 and status_of(res, "T-FX") == "PASS", (rc, err))

rc, res, _, _ = report([case("G-A", site="mctl-web"), case("G-B", site="mctl-web")],
                       [("G-A", "pass", ""), ("G-B", "fail", "x")], pins=pins_with(to_image))
check("a failing case on one site cancels the claim of another compliant site",
      rc == 1 and res["summary"]["compliance_claim"] is False, res)
rc, res, _, _ = report([case("G-A", site="mctl-web"), case("G-F", site=FIXTURE_SITE)],
                       [("G-A", "pass", ""), ("G-F", "fail", "x")], pins=pins_with(to_image))
check("the failing case is on another site, so mctl-web is compliant yet no claim is made",
      res["sites"]["mctl-web"]["compliant"] is True and res["summary"]["compliance_claim"] is False, res)
rc, res, _, _ = report([case("G-A", site="mctl-web")], [("G-A", "pass", "")], pins=pins_with(to_image))
check("a clean compliant run does make the claim", rc == 0 and res["summary"]["compliance_claim"] is True, res)
rc, res, _, _ = report([case("G-A")], [("G-A", "pass", "")])
check("per-gate counts are tallied", res["gates"]["G1"]["PASS"] == 1, res)

with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    (d / "out").mkdir()
    (d / "out/results.json").write_text('{"stale": true}')
    (d / "out/matrix.md").write_text("stale")
    (d / "junit.xml").write_text("<html/>")
    (d / "cases.json").write_text(json.dumps({"cases": [case("S")]}))
    rc, _, err = run("--junit", d / "junit.xml", "--cases", d / "cases.json", "--out-dir", d / "out")
    check("a hard error removes stale outputs of an earlier run",
          rc == 3 and not (d / "out/results.json").exists() and not (d / "out/matrix.md").exists(), (rc, err))
with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    (d / "junit.xml").write_text(junit([("S", "pass", "")]))
    (d / "cases.json").write_text(json.dumps({"cases": [case("S")]}))
    (d / "afile").write_text("x")
    rc, _, err = run("--junit", d / "junit.xml", "--cases", d / "cases.json", "--out-dir", d / "afile")
    check("an unexpected exception exits 3, never the traceback exit 1", rc == 3 and "unexpected" in err, (rc, err))
rc, _, err = run("--bogus")
check("an argparse error exits 3, never 2", rc == 3, (rc, err))

# --- malformed input is a hard error, never an empty pass ---------------------------
rc, res, mx, err = report([case("T-M")], [], junit_text="<testsuites><testsuite><testcase name='x'>")
check("malformed junit exits 3 and writes no result", rc == 3 and res is None, (rc, err))
rc, res, _, _ = report([case("T-M")], [], junit_text="<html/>")
check("junit with a foreign root exits 3", rc == 3 and res is None)
rc, res, _, _ = report([case("T-M")], [], junit_text="")
check("empty junit file exits 3", rc == 3 and res is None)
rc, res, _, _ = report([], [("x", "pass", "")])
check("an empty case catalog exits 3 (not a vacuous pass)", rc == 3 and res is None)
rc, res, _, _ = report([case("D"), case("D")], [("D", "pass", "")])
check("duplicate case ids exit 3", rc == 3 and res is None)
rc, res, _, err = report([case("T-P")], [("T-P", "pass", "")], pins=pins_with(lambda p: p.pop("playwright_image")))
check("report refuses to run on rejected pins", rc == 3 and res is None, (rc, err))

# --- pin rejection (--check-pins) ---------------------------------------------------
def pin_rc(mutate):
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "pins.json"
        f.write_text(json.dumps(pins_with(mutate)))
        rc, out, err = run("--check-pins", "--pins", f)
        return rc, out + err


def site(p, name="mctl-web"):
    return next(s for s in p["sites"] if s["name"] == name)


rc, out = pin_rc(None)
check("the committed pins.json is accepted", rc == 0, out)
rc, out = pin_rc(lambda p: p.update(playwright_image="mcr.microsoft.com/playwright:v1.64.1-noble"))
check("tag-only playwright image is rejected", rc == 3 and "playwright_image" in out, out)
rc, out = pin_rc(lambda p: p.update(nginx_image=p["nginx_image"].split("@")[0]))
check("tag-only nginx image is rejected", rc == 3 and "nginx_image" in out, out)
rc, out = pin_rc(lambda p: p.update(playwright_image="mcr.microsoft.com/playwright:v1.64.1-noble@sha256:abc123"))
check("short digest is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p["mctl_design"].update(commit="6d82a6b23936"))
check("short commit sha is rejected", rc == 3 and "commit" in out, out)
rc, out = pin_rc(lambda p: p["mctl_design"].update(commit="main"))
check("branch name as commit is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p["mctl_design"].update(commit="6D82A6B239365213D6859F2794C2449AF7DD4E1F"))
check("uppercase 40-hex commit is rejected (canonical form only)", rc == 3, out)
rc, out = pin_rc(lambda p: site(p).update(source_commit="abc1234"))
check("short site source_commit is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: site(p).update(image="ghcr.io/mctlhq/mctl-web:7.24.0"))
check("tag-only site image is rejected", rc == 3 and "mctl-web" in out, out)
rc, out = pin_rc(lambda p: site(p).update(mode="image", image=None))
check("mode image with a null image is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: site(p).update(observed_image_digest="ghcr.io/mctlhq/mctl-web:latest"))
check("tag-only observed digest note is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: site(p).update(not_run_reason="see https://mctl.ai/status?x=1"))
check("http(s) URL to a non-fixture host is rejected", rc == 3 and "non-fixture" in out, out)
check("the rejected URL is sanitized in the message", "x=1" not in out, out)
rc, out = pin_rc(lambda p: site(p).update(not_run_reason="see https://ui.fixture.test/x"))
check("http(s) URL to a fixture host is allowed", rc == 0, out)
rc, out = pin_rc(lambda p: site(p).update(mode="not-run", not_run_reason=""))
check("mode not-run without a reason is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p["sites"].pop())
check("a missing site is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p.update(playwright_test_version="^1.64.1"))
check("a range for @playwright/test is rejected", rc == 3, out)
# --- review round 2: pin regex edges ---------------------------------------------------
GOOD40 = "6d82a6b239365213d6859f2794c2449af7dd4e1f"
rc, out = pin_rc(lambda p: p["mctl_design"].update(commit=GOOD40[:39]))
check("a 39-hex commit is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p["mctl_design"].update(commit=GOOD40 + "a"))
check("a 41-hex commit is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p["mctl_design"].update(commit=GOOD40 + "\n"))
check("a commit with a trailing newline is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p.update(playwright_image=p["playwright_image"].split("@")[0] + "@sha256:" + "z" * 64))
check("a 64-char non-hex digest is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p.update(playwright_image=p["playwright_image"] + "\n"))
check("an image digest with a trailing newline is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p.update(playwright_test_version="1.2.3\n"))
check("a version with a trailing newline is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p.update(playwright_test_version="\uff11.\uff12.\uff13"))
check("a non-ASCII digit version is rejected", rc == 3, out)
for bp in (0, True, -1, "981"):
    rc, out = pin_rc(lambda p: site(p, "mctl-academy").update(breakpoint=bp))
    check(f"breakpoint {bp!r} is rejected", rc == 3 and "breakpoint" in out, out)
for url in ("ftp://u:pw@evil.example/x", "postgres://u:pw@evil.example/db", "//evil.example/x?t=SECRET",
            "http://evil.example\\@ui.fixture.test/", "https://evil.example/p?a=b]c=SECRET"):
    rc, out = pin_rc(lambda p: site(p).update(not_run_reason="see " + url))
    check(f"non-http or tricky URL {url[:24]!r} is rejected and not echoed",
          rc == 3 and "SECRET" not in out and "pw@" not in out, out)
rc, out = pin_rc(lambda p: p.update({"https://evil.example/k": "v"}))
check("a URL used as a dict key is rejected", rc == 3, out)
rc, out = pin_rc(lambda p: p.update(fixture_hosts=p["fixture_hosts"] + ["evil.example"]))
check("fixture_hosts cannot widen the script allowlist", rc == 3, out)
rc, out = pin_rc(lambda p: p["mctl_design"].update(also_verified_versions=["9.9.9"]))
check("an also_verified version without a sheet entry is rejected", rc == 3 and "9.9.9" in out, out)

with tempfile.TemporaryDirectory() as d:
    f = pathlib.Path(d) / "pins.json"
    f.write_text("{not json")
    rc, _, err = run("--check-pins", "--pins", f)
    check("malformed pins.json is a hard error", rc == 3, err)
    rc, _, err = run("--check-pins", "--pins", pathlib.Path(d) / "absent.json")
    check("absent pins.json is a hard error", rc == 3, err)

# --- design repo verification (self-contained synthetic git repo) ---------------------
def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false", *a], capture_output=True, text=True, check=True).stdout.strip()


def sheet_bytes(v, f):
    return f"/* {v} {f} */\nbody{{color:#{abs(hash((v, f))) % 0xFFFFFF:06x}}}\n".encode()


def make_repo(d, skip_dir=None, tamper=None):
    repo = pathlib.Path(d) / "design"
    repo.mkdir()
    git(repo, "init", "-q")
    sheets = {}
    for v in ("0.21.0", "0.20.2"):
        sheets[v] = {}
        for f in ("mctl.css", "global.css", "prose.css", "site.css"):
            b = sheet_bytes(v, f)
            sheets[v][f] = {"sha256": hashlib.sha256(b).hexdigest(),
                            "sha384": "sha384-" + b64encode(hashlib.sha384(b).digest()).decode()}
            if v != skip_dir:
                p = repo / "apps/storybook/public" / v / f
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b + (b"x" if tamper == (v, f) else b""))
    if skip_dir:
        (repo / "README").write_text("x")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "t")
    return repo, git(repo, "rev-parse", "HEAD"), sheets


def design_rc(repo, commit, sheets, pins_mutate=None):
    p = pins_with()
    p["mctl_design"]["commit"], p["mctl_design"]["sheets"] = commit, sheets
    if pins_mutate:
        pins_mutate(p)
    f = pathlib.Path(repo).parent / "pins.json"
    f.write_text(json.dumps(p))
    rc, out, err = run("--check-pins", "--pins", f, "--design-repo", repo)
    return rc, out + err


with tempfile.TemporaryDirectory() as d:
    repo, commit, sheets = make_repo(d)
    rc, out = design_rc(repo, commit, sheets)
    check("design repo with agreeing sha256 and sha384 passes", rc == 0 and "design-sheets: OK" in out, out)

    bad = copy.deepcopy(sheets)
    bad["0.21.0"]["site.css"]["sha256"] = "0" * 64
    rc, out = design_rc(repo, commit, bad)
    check("a sha256 that disagrees with the pinned commit fails", rc == 3 and "sha256" in out, out)

    bad = copy.deepcopy(sheets)
    bad["0.21.0"]["site.css"]["sha384"] = "sha384-" + "A" * 64
    rc, out = design_rc(repo, commit, bad)
    check("a sha384 that disagrees with the pinned commit fails", rc == 3 and "sha384" in out, out)

    rc, out = design_rc(repo, "1" * 40, sheets)
    check("a pinned commit absent from the design repo is a hard error", rc == 3, out)

    f = pathlib.Path(d) / "pins2.json"
    f.write_text(json.dumps(PINS))
    rc, out, err = run("--check-pins", "--pins", f, "--design-repo", pathlib.Path(d) / "no-such-repo")
    check("an unreadable --design-repo is a hard error, not a skip", rc == 3, (out, err))

with tempfile.TemporaryDirectory() as d:
    repo, commit, sheets = make_repo(d, skip_dir="0.21.0")
    rc, out = design_rc(repo, commit, sheets)
    check("a missing apps/storybook/public/0.21.0/ directory fails", rc == 3 and "0.21.0/ is absent" in out, out)

with tempfile.TemporaryDirectory() as d:
    f = pathlib.Path(d) / "pins.json"
    f.write_text(json.dumps(PINS))
    rc, out, _ = run("--check-pins", "--pins", f)
    check("without --design-repo the sheet check is reported NOT-RUN, never a silent pass",
          rc == 0 and "design-sheets: NOT-RUN" in out, out)

# ---- guard substitutions: what the harness answered locally must be visible, and unreadable is an error
def report_with_subst(subst_text):
    """Like report(), with a --substitutions file (None = flag not given). Returns (exit, results, matrix, stderr)."""
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        cases = [case("S-A"), case("S-CTL", kind="negative-control")]
        (d / "junit.xml").write_text(junit([("S-A", "pass", ""), ("S-CTL", "fail", "detected")]))
        (d / "cases.json").write_text(json.dumps({"cases": cases}))
        (d / "pins.json").write_text(json.dumps(PINS))
        extra = []
        if subst_text is not None:
            (d / "subst.json").write_text(subst_text)
            extra = ["--substitutions", d / "subst.json"]
        rc, _, err = run("--junit", d / "junit.xml", "--cases", d / "cases.json", "--pins", d / "pins.json",
                         "--out-dir", d / "out", "--attempt-id", "t-1", *extra)
        res = d / "out/results.json"
        mx = d / "out/matrix.md"
        return rc, (json.loads(res.read_text()) if res.exists() else None), (mx.read_text() if mx.exists() else None), err


rc, res, mx, _ = report_with_subst(None)
check("without a substitutions file the report says it is unknown, not none",
      rc == 0 and res["substitutions"]["status"] == "not-provided" and "unknown" in res["substitutions"]["statement"]
      and "not provided" in mx, res and res["substitutions"])
rc, res, mx, _ = report_with_subst(json.dumps({"per_test": {}, "totals": {}}))
check("an empty record says nothing was answered locally",
      rc == 0 and res["substitutions"]["statement"] == "no request was answered locally", res and res["substitutions"])
good = {"per_test": {"S-A": {"ui.mctl.ai": 3, "fonts.googleapis.com": 1}},
        "totals": {"ui.mctl.ai": 3, "fonts.googleapis.com": 1}}
rc, res, mx, _ = report_with_subst(json.dumps(good))
row = next(r for r in res["results"] if r["id"] == "S-A")
check("a case that ran with answered requests carries them on its row and in the matrix",
      rc == 0 and row["status"] == "PASS" and row.get("answered_locally") == good["per_test"]["S-A"]
      and "[answered locally: fonts.googleapis.com x1, ui.mctl.ai x3]" in mx, row)
check("font substitution is called out as not evidence for font-metric results",
      "NOT loaded" in res["substitutions"]["statement"] and "not evidence" in mx, res["substitutions"])
for label, text in (("not json", "{"), ("missing keys", "{}"), ("wrong types", json.dumps({"per_test": [], "totals": {}})),
                    ("negative-or-text count", json.dumps({"per_test": {"S-A": {"h": "x"}}, "totals": {}}))):
    rc, res, mx, err = report_with_subst(text)
    check(f"an unreadable or malformed substitutions file ({label}) is an input error, never 'none'",
          rc == 3 and res is None and "cannot say what was answered locally" in err, (rc, err))

if failures:
    print("\n".join(failures))
    sys.exit(1)
