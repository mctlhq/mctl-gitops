"""build-image.yaml scans the pushed image with Trivy, warn-only by default (mctlhq/mctl-gitops#332).

Properties: the scan runs after the digest is recorded and targets name@digest; the action is
pinned by commit SHA; one env switch (IMAGE_SCAN_BLOCKING, default "false") drives both
continue-on-error and exit-code; the SARIF goes up as an artifact and the job gains no
security-events permission (release-deploy.yaml calls this workflow); and the report step never
turns "could not scan" or "unreadable report" into a clean result. The report step's real script
runs against fixtures; named mutants of the workflow must turn the suite red.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/build-image.yaml"
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:400]}")


def sarif(n):
    import json
    return json.dumps({"version": "2.1.0", "runs": [{"results": [{"ruleId": f"CVE-{i}"} for i in range(n)]}]})


def run_report(script, outcome, sarif_text):
    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d) / "r.sarif"
        if sarif_text is not None:
            path.write_text(sarif_text)
        summary = pathlib.Path(d) / "summary.md"
        env = {**os.environ, "SCAN_OUTCOME": outcome, "SARIF": str(path), "IMAGE_REF": "ghcr.io/x/y@sha256:" + "a" * 64,
               "BLOCKING": "false", "GITHUB_STEP_SUMMARY": str(summary)}
        r = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
        return r.returncode, r.stdout, summary.read_text() if summary.exists() else ""


def judge(text):
    out = []
    doc = yaml.safe_load(text)
    steps = doc["jobs"]["build"]["steps"]
    names = [s.get("name") for s in steps]

    def step(n):
        return next((s for s in steps if s.get("name") == n), None)

    scan, rep, up, dig = step("Scan image (Trivy)"), step("Report scan outcome"), step("Upload image scan report"), step("Record image digest")
    out.append(("scan, report and upload steps exist", bool(scan and rep and up), names))
    if not (scan and rep and up):
        return out
    out.append(("scan runs after the digest is recorded", names.index("Scan image (Trivy)") > names.index("Record image digest"), names))
    out.append(("scan action pinned by full commit SHA", bool(re.fullmatch(r"aquasecurity/trivy-action@[0-9a-f]{40}", scan["uses"])), scan["uses"]))
    w = scan.get("with", {})
    out.append(("scan targets name@digest", "steps.digest.outputs.digest" in w.get("image-ref", "") and "@" in w.get("image-ref", ""), w.get("image-ref")))
    out.append(("scan output is SARIF", w.get("format") == "sarif" and str(w.get("output", "")).endswith(".sarif"), w))
    out.append(("switch defaults to warn-only", doc["env"].get("IMAGE_SCAN_BLOCKING") == "false", doc.get("env")))
    out.append(("continue-on-error follows the switch", "env.IMAGE_SCAN_BLOCKING" in str(scan.get("continue-on-error")) and "!= 'true'" in str(scan.get("continue-on-error")), scan.get("continue-on-error")))
    out.append(("exit-code follows the switch", "env.IMAGE_SCAN_BLOCKING == 'true'" in str(w.get("exit-code")) and "'1'" in str(w.get("exit-code")) and "'0'" in str(w.get("exit-code")), w.get("exit-code")))
    out.append(("report step runs even when the scan failed", "cancelled" in str(rep.get("if")), rep.get("if")))
    out.append(("report step reads the scan outcome", "steps.scan.outcome" in str(rep["env"].get("SCAN_OUTCOME")), rep["env"]))
    out.append(("SARIF is uploaded as an artifact", up["uses"].startswith("actions/upload-artifact@") and "cancelled" in str(up.get("if")), up))
    perms = doc["jobs"]["build"].get("permissions", {})
    out.append(("no security-events permission (release-deploy caller)", "security-events" not in perms, perms))

    script = rep["run"]
    ref = "sha256:" + "a" * 64
    cases = [
        ("scan failed -> warning, not clean", "failure", None, lambda rc, so, sm: rc == 0 and "did not complete" in so and "NOT known to be clean" in so),
        ("scan skipped -> warning, not clean", "skipped", None, lambda rc, so, sm: "did not complete" in so and "NOT known to be clean" in so),
        ("success but report missing -> warning", "success", None, lambda rc, so, sm: "missing or unreadable" in so and "finding(s)" not in so),
        ("success but report garbage -> warning", "success", "not json", lambda rc, so, sm: "missing or unreadable" in so and "finding(s)" not in so),
        ("success but report has no runs -> warning", "success", "{}", lambda rc, so, sm: "missing or unreadable" in so and "finding(s)" not in so),
        ("success, zero findings -> no warning", "success", sarif(0), lambda rc, so, sm: rc == 0 and "::warning::" not in so and "no fixable" in sm),
        ("success, findings -> warning with count", "success", sarif(3), lambda rc, so, sm: "::warning::Trivy found 3" in so),
    ]
    for name, outcome, body, pred in cases:
        rc, so, sm = run_report(script, outcome, body)
        out.append((name, pred(rc, so, sm), (rc, so, sm)))
    return out


MUTANTS = [
    ("scan made blocking by default", 'IMAGE_SCAN_BLOCKING: "false"', 'IMAGE_SCAN_BLOCKING: "true"'),
    ("continue-on-error dropped", "continue-on-error: ${{ env.IMAGE_SCAN_BLOCKING != 'true' }}", "continue-on-error: false"),
    ("action unpinned", "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25", "aquasecurity/trivy-action@v0.36.0"),
    ("scan by tag, not digest", "image-ref: ${{ inputs.image_name }}@${{ steps.digest.outputs.digest }}", "image-ref: ${{ inputs.image_name }}:${{ inputs.image_tag }}"),
    ("failed scan reported silently", 'if [ "${SCAN_OUTCOME}" != "success" ]; then', 'if false; then'),
    ("unreadable report treated as clean", 'unreadable:*|"")', 'NEVER)'),
    ("security-events permission added", "      id-token: write\n    steps:", "      id-token: write\n      security-events: write\n    steps:"),
]


def main():
    text = WF.read_text()
    for name, ok, detail in judge(text):
        check(name, ok, detail)
    for name, old, new in MUTANTS:
        if text.count(old) != 1:
            check(f"mutant anchor: {name}", False, f"found {text.count(old)}")
            continue
        red = [n for n, ok, _ in judge(text.replace(old, new)) if not ok]
        check(f"mutant turns the suite red: {name}", bool(red), "no case failed")
    if failures:
        print("\nFAILURES:")
        print("\n".join(failures))
        sys.exit(1)
    print("\nall build-image trivy scan checks passed")


main()
