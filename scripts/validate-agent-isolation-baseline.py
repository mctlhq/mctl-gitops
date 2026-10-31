#!/usr/bin/env python3
"""Gate the agent-isolation matrix against a committed, versioned baseline.

mctl-gitops#2292. Runs the vendored, pinned mctl-agents auditor
(scripts/agent-isolation/auditor/, pinned by auditor.pin.json) over
platform-gitops/ and compares its rows with scripts/agent-isolation/baseline.json.
Accepted gaps stay visible (job summary) but do not fail for existing; a
regression, a worsened or closed gap, an unknown (`not-observed`) object or an
unbaselined row fails. Rows owned by validate-agent-pod-security.py are
recorded but never compared here.

CI never writes the baseline. Regenerate locally with --regenerate and commit
the result in the same PR as the change that caused it.

Run with --selftest to prove the gate still detects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ISO_DIR = ROOT / "scripts/agent-isolation"
PIN = ISO_DIR / "auditor.pin.json"
BASELINE = ISO_DIR / "baseline.json"
TREE = ROOT / "platform-gitops"
POD_SECURITY_SCRIPT = ROOT / "scripts/validate-agent-pod-security.py"

BASELINE_SCHEMA = 1
STATUSES = ("enforced", "partial", "declared-not-enforced", "absent", "not-observed")
# Higher is stronger. Used only to word a change; any change to a gap fails.
RANK = {"enforced": 4, "partial": 3, "declared-not-enforced": 2, "absent": 1, "not-observed": 0}
ROW_FIELDS = ("primitive", "scope", "status", "severity", "source", "field", "detail", "recommendation")
OWNER_GATE = "agent-isolation-gate"
OWNER_POD = "validate-agent-pod-security"

# Rows scripts/validate-agent-pod-security.py already owns. Fixed here so a
# baseline edit cannot reassign one to dodge a check; selftest pins the table.
POD_SECURITY_OWNED = frozenset({
    ("PodSecurity", "securityContext.runAsNonRoot"),
    ("PodSecurity", "securityContext.seccompProfile.type"),
    ("PodSecurity", "container.securityContext.allowPrivilegeEscalation"),
    ("PodSecurity", "container.securityContext.capabilities.drop"),
})

Key = tuple


def owner_of(primitive: str, field: str) -> str:
    return OWNER_POD if (primitive, field) in POD_SECURITY_OWNED else OWNER_GATE


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_digest(pin: dict) -> str:
    files = pin["files"]
    if len(files) == 1:
        return files[0]["sha256"]
    lines = "\n".join(f"{f['vendored_path']}:{f['sha256']}"
                      for f in sorted(files, key=lambda f: f["vendored_path"]))
    return hashlib.sha256(lines.encode()).hexdigest()


# --- pin ---------------------------------------------------------------

def load_pin(pin_path: Path) -> tuple[dict | None, list[str]]:
    try:
        pin = json.loads(pin_path.read_text())
    except (OSError, ValueError) as exc:
        return None, [f"auditor pin unreadable: {pin_path}: {exc}"]
    errs: list[str] = []
    if not isinstance(pin, dict) or pin.get("schema_version") != 1:
        return None, ["auditor.pin.json: unsupported schema_version (want 1)"]
    if not re.fullmatch(r"[0-9a-f]{40}", str(pin.get("commit", ""))):
        errs.append("auditor.pin.json: commit must be a full 40-hex SHA")
    if not pin.get("repo"):
        errs.append("auditor.pin.json: repo missing")
    files = pin.get("files")
    if not isinstance(files, list) or not files:
        errs.append("auditor.pin.json: files must be a non-empty list")
        return pin, errs
    for f in files:
        if not isinstance(f, dict) or not all(
                isinstance(f.get(k), str) and f.get(k) for k in ("source_path", "vendored_path", "sha256")):
            errs.append(f"auditor.pin.json: malformed file entry {f!r}")
            return pin, errs
    if pin.get("entrypoint") not in [f["vendored_path"] for f in files]:
        errs.append("auditor.pin.json: entrypoint must be one of the vendored files")
    return pin, errs


def check_pin_integrity(pin: dict, base: Path) -> list[str]:
    errs = []
    for f in pin["files"]:
        p = base / f["vendored_path"]
        if not p.is_file():
            errs.append(f"vendored auditor file missing: {f['vendored_path']}")
        elif sha256(p) != f["sha256"]:
            errs.append(f"vendored auditor file {f['vendored_path']} sha256 {sha256(p)} != pin {f['sha256']}")
    return errs


def verify_upstream(pin: dict, base: Path) -> list[str]:
    errs = []
    for f in pin["files"]:
        url = f"https://raw.githubusercontent.com/{pin['repo']}/{pin['commit']}/{f['source_path']}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                upstream = r.read()
        except Exception as exc:  # a fetch failure must fail the step
            errs.append(f"cannot fetch {url}: {exc}")
            continue
        if upstream != (base / f["vendored_path"]).read_bytes():
            errs.append(f"vendored {f['vendored_path']} differs from "
                        f"{pin['repo']}@{pin['commit'][:12]}:{f['source_path']}")
    return errs


# --- auditor -----------------------------------------------------------

def run_auditor(entry: Path, tree: Path) -> tuple[dict | None, list[str]]:
    proc = subprocess.run([sys.executable, "-I", str(entry), "--gitops-root", str(tree), "--format", "json"],
                          capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        return None, [f"auditor exited {proc.returncode}: {proc.stderr.strip()[:300]}"]
    try:
        out = json.loads(proc.stdout)
    except ValueError as exc:
        return None, [f"auditor output is not JSON: {exc}"]
    return out, validate_output(out)


def validate_output(out) -> list[str]:
    if not isinstance(out, dict) or not isinstance(out.get("rows"), list) \
            or not isinstance(out.get("templates"), dict):
        return ["auditor output lacks top-level rows/templates"]
    errs, seen = [], set()
    for r in out["rows"]:
        if not isinstance(r, dict) or any(not isinstance(r.get(k), str) for k in ROW_FIELDS):
            errs.append(f"auditor row does not match schema: {str(r)[:120]}")
            continue
        if r["status"] not in STATUSES:
            errs.append(f"auditor row has unknown status {r['status']!r}: {fmt(row_key(r))}")
        if row_key(r) in seen:
            errs.append(f"auditor emitted duplicate row key {fmt(row_key(r))}")
        seen.add(row_key(r))
    return errs


def row_key(r: dict) -> Key:
    return (r["primitive"], r["scope"], r["field"])


def fmt(k: Key) -> str:
    return " | ".join(k)


def agent_steps(out: dict) -> set[str]:
    return {f"{t['cwft']}/{t['template']}" for tpls in out["templates"].values()
            for t in tpls if t.get("agent")}


# --- baseline ----------------------------------------------------------

def load_baseline(path: Path, pin: dict, out_schema) -> tuple[dict | None, list[str]]:
    if not path.is_file():
        return None, [f"baseline missing: {path} (fail closed; never start from an empty baseline)"]
    try:
        b = json.loads(path.read_text())
    except ValueError as exc:
        return None, [f"baseline is not valid JSON: {exc}"]
    if not isinstance(b, dict) or b.get("schema_version") != BASELINE_SCHEMA:
        return None, [f"baseline schema_version must be {BASELINE_SCHEMA}"]
    errs: list[str] = []
    aud = b.get("auditor") or {}
    if aud.get("commit") != pin["commit"] or aud.get("sha256") != pin_digest(pin):
        errs.append("auditor upgraded without re-baselining: baseline.auditor commit/sha256 "
                    "differs from auditor.pin.json")
    if out_schema is not None and aud.get("output_schema_version") != out_schema:
        errs.append("baseline.auditor.output_schema_version differs from auditor.pin.json")
    rows = b.get("rows")
    if not isinstance(rows, list) or not rows:
        return None, errs + ["baseline rows missing or empty"]
    seen = set()
    for r in rows:
        if not isinstance(r, dict) or any(
                not isinstance(r.get(k), str) for k in ("primitive", "scope", "field", "status")):
            errs.append(f"baseline row malformed: {str(r)[:120]}")
            continue
        k = row_key(r)
        if k in seen:
            errs.append(f"baseline duplicate row key {fmt(k)}")
        seen.add(k)
        if r["status"] not in STATUSES:
            errs.append(f"baseline row {fmt(k)}: unknown status {r['status']!r}")
        want = owner_of(r["primitive"], r["field"])
        if r.get("owner") not in (OWNER_GATE, OWNER_POD):
            errs.append(f"baseline row {fmt(k)}: owner must be {OWNER_GATE} or {OWNER_POD}")
        elif r["owner"] != want:
            errs.append(f"baseline row {fmt(k)}: owner {r['owner']} but POD_SECURITY_OWNED says {want}")
        if r["status"] != "enforced" and not str(r.get("issue") or "").strip():
            errs.append(f"baseline row {fmt(k)}: non-enforced row needs an issue")
    steps = b.get("agent_steps")
    if not isinstance(steps, list) or not steps:
        errs.append("baseline agent_steps missing or empty")
    return b, errs


# --- compare -----------------------------------------------------------

def compare(baseline: dict, out: dict) -> tuple[list[str], list[str]]:
    """Return (errors, open gap lines)."""
    errs, gaps = [], []
    cur = {row_key(r): r for r in out["rows"]}
    base = {row_key(r): r for r in baseline["rows"]}
    for k, b in sorted(base.items()):
        if b["owner"] != OWNER_GATE:
            continue
        c = cur.get(k)
        cs = c["status"] if c else None
        bs = b["status"]
        if bs == "enforced":
            if cs != "enforced":
                errs.append(f"regression: {fmt(k)} enforced -> {cs or 'missing'}")
        elif cs is None:
            errs.append(f"{fmt(k)}: baselined {bs} but row is missing (object became unknown)")
        elif cs == bs:
            gaps.append(f"{fmt(k)}: {bs} ({b['issue']})")
        elif cs == "enforced":
            errs.append(f"gap closed: update the baseline in this PR: {fmt(k)} {bs} -> enforced")
        elif cs == "not-observed":
            errs.append(f"{fmt(k)}: baselined {bs} but now not-observed (never counts as clean)")
        elif RANK[cs] < RANK[bs]:
            errs.append(f"gap worsened: {fmt(k)} {bs} -> {cs}")
        else:
            errs.append(f"gap changed: update the baseline in this PR: {fmt(k)} {bs} -> {cs}")
    base_steps = set(baseline["agent_steps"])
    for k in sorted(set(cur) - set(base)):
        if owner_of(k[0], k[2]) == OWNER_GATE:
            errs.append(f"unbaselined row: {fmt(k)} is {cur[k]['status']}")
    # Peer-required: (primitive, field) enforced for every baselined agent step.
    required = None
    for step in base_steps:
        have = {(k[0], k[2]) for k, b in base.items()
                if k[1] == step and b["owner"] == OWNER_GATE and b["status"] == "enforced"}
        required = have if required is None else required.intersection(have)
    for step in sorted(agent_steps(out) - base_steps):
        lacking = sorted((p, f) for p, f in (required or set())
                         if cur.get((p, step, f), {}).get("status") != "enforced")
        if lacking:
            errs.append(f"new agent step {step} lacks controls of its peers: "
                        + ", ".join(f"{p}/{f}" for p, f in lacking))
    return errs, gaps


def summary(pin: dict, out: dict, gaps: list[str]) -> str:
    counts: dict[str, int] = {}
    for r in out["rows"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines = ["### Agent isolation matrix (mctl-gitops#2292)", "",
             f"Auditor: {pin['repo']}@{pin['commit'][:12]}", "",
             ", ".join(f"{s}: {n}" for s, n in sorted(counts.items())), "",
             f"Open accepted gaps ({len(gaps)}):"]
    return "\n".join(lines + [f"- {g}" for g in gaps]) + "\n"


# --- regenerate --------------------------------------------------------

def regenerate(pin: dict, out: dict, previous: Path) -> dict:
    issues = {}
    try:
        for r in json.loads(previous.read_text()).get("rows", []):
            if r.get("issue"):
                issues[(r["primitive"], r["scope"], r["field"])] = r["issue"]
    except (OSError, ValueError, AttributeError):
        pass
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                         cwd=ROOT).stdout.strip() or None
    rows = []
    for r in sorted(out["rows"], key=row_key):
        row = {"primitive": r["primitive"], "scope": r["scope"], "field": r["field"],
               "status": r["status"], "owner": owner_of(r["primitive"], r["field"])}
        if r["status"] != "enforced":
            row["issue"] = issues.get(row_key(r))  # null until a human fills it in; validation rejects null
        rows.append(row)
    return {"schema_version": BASELINE_SCHEMA,
            "auditor": {"repo": pin["repo"], "commit": pin["commit"], "sha256": pin_digest(pin),
                        "auditor_version": pin.get("auditor_version"),
                        "output_schema_version": out.get("schema_version")},
            "generated_from_gitops": sha, "agent_steps": sorted(agent_steps(out)), "rows": rows}


# --- main check --------------------------------------------------------

def check(tree: Path, baseline_path: Path = BASELINE, pin_path: Path = PIN, upstream: bool = False):
    pin, errs = load_pin(pin_path)
    if pin is None or errs:
        return errs, [], pin, None
    base = pin_path.parent
    errs = check_pin_integrity(pin, base)
    if upstream:
        errs += verify_upstream(pin, base)
    if errs:
        return errs, [], pin, None
    out, errs = run_auditor(base / pin["entrypoint"], tree)
    if errs:
        return errs, [], pin, out
    want = pin.get("output_schema_version")
    if want is not None and out.get("schema_version") != want:
        return [f"auditor schema_version {out.get('schema_version')!r} != pin {want!r}"], [], pin, out
    baseline, errs = load_baseline(baseline_path, pin, want)
    if baseline is None or errs:
        return errs, [], pin, out
    errs, gaps = compare(baseline, out)
    return errs, gaps, pin, out


# --- selftest ----------------------------------------------------------

def _synthetic(rows, steps=("c/a",)):
    return {"schema_version": 2, "rows": rows,
            "templates": {"f.yaml": [{"cwft": s.split("/")[0], "template": s.split("/")[1], "agent": True}
                                     for s in steps]}}


def _row(prim, scope, field, status):
    return {"primitive": prim, "scope": scope, "status": status, "severity": "low", "source": "s",
            "field": field, "detail": "d", "recommendation": "r"}


def _brow(prim, scope, field, status, issue=None, owner=None):
    r = {"primitive": prim, "scope": scope, "field": field, "status": status,
         "owner": owner or owner_of(prim, field)}
    if issue:
        r["issue"] = issue
    return r


def selftest() -> int:
    ok = True

    def expect(label, errs, want_sub):
        nonlocal ok
        if bool(errs) != bool(want_sub) or (want_sub and not any(want_sub in e for e in errs)):
            print(f"selftest FAIL: {label}: got {errs}, wanted {want_sub or 'pass'}")
            ok = False

    if POD_SECURITY_OWNED != {
            ("PodSecurity", "securityContext.runAsNonRoot"),
            ("PodSecurity", "securityContext.seccompProfile.type"),
            ("PodSecurity", "container.securityContext.allowPrivilegeEscalation"),
            ("PodSecurity", "container.securityContext.capabilities.drop")}:
        print("selftest FAIL: POD_SECURITY_OWNED changed")
        ok = False

    E, P, A, N = "enforced", "partial", "absent", "not-observed"
    SA = ("RBAC/ServiceAccount", "c/a", "automountServiceAccountToken")
    RUN = ("PodSecurity", "c/a", "securityContext.runAsNonRoot")

    def case(label, brows, crows, want, steps=("c/a",)):
        errs, _ = compare({"agent_steps": ["c/a"], "rows": brows}, _synthetic(crows, steps))
        expect(label, errs, want)

    case("unchanged enforced", [_brow(*SA, E)], [_row(*SA, E)], None)
    case("regression", [_brow(*SA, E)], [_row(*SA, A)], "regression")
    case("enforced missing", [_brow(*SA, E)], [], "missing")
    case("enforced -> not-observed", [_brow(*SA, E)], [_row(*SA, N)], "regression")
    case("unchanged gap passes", [_brow(*SA, P, "x#1")], [_row(*SA, P)], None)
    case("gap worsened", [_brow(*SA, P, "x#1")], [_row(*SA, A)], "worsened")
    case("gap closed", [_brow(*SA, P, "x#1")], [_row(*SA, E)], "gap closed")
    case("gap -> not-observed", [_brow(*SA, A, "x#1")], [_row(*SA, N)], "not-observed")
    case("gap missing", [_brow(*SA, A, "x#1")], [], "missing")
    case("unbaselined row", [_brow(*SA, E)],
         [_row(*SA, E), _row("Resources", "c/a", "container.resources", E)], "unbaselined")
    case("pod-security row skipped", [_brow(*SA, E), _brow(*RUN, E)], [_row(*SA, E), _row(*RUN, A)], None)
    case("new step lacking peer controls", [_brow(*SA, E)],
         [_row(*SA, E), _row(SA[0], "c/b", SA[2], A)], "lacks controls of its peers", steps=("c/a", "c/b"))

    pin, perrs = load_pin(PIN)
    if pin is None or perrs:
        print(f"selftest FAIL: pin invalid: {perrs}")
        return 1
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)

        def base_with(mut=None, rows=None):
            b = {"schema_version": 1, "agent_steps": ["c/a"],
                 "auditor": {"commit": pin["commit"], "sha256": pin_digest(pin),
                             "output_schema_version": pin.get("output_schema_version")},
                 "rows": rows or [_brow(*SA, E)]}
            if mut:
                mut(b)
            (d / "b.json").write_text(json.dumps(b))
            return load_baseline(d / "b.json", pin, pin.get("output_schema_version"))[1]

        expect("valid baseline", base_with(), None)
        expect("missing baseline", load_baseline(d / "nope.json", pin, None)[1], "missing")
        expect("bad schema", base_with(lambda b: b.update(schema_version=9)), "schema_version")
        expect("duplicate baseline key", base_with(rows=[_brow(*SA, E), _brow(*SA, E)]), "duplicate")
        expect("pin mismatch", base_with(lambda b: b["auditor"].update(sha256="0" * 64)),
               "without re-baselining")
        expect("gap without issue", base_with(rows=[_brow(*SA, P)]), "needs an issue")
        expect("pod row reassigned to gate", base_with(rows=[_brow(*RUN, E, owner=OWNER_GATE)]),
               "POD_SECURITY_OWNED")
        expect("bad owner", base_with(rows=[_brow(*SA, E, owner="nobody")]), "owner must be")

        expect("duplicate output key", validate_output(_synthetic([_row(*SA, E), _row(*SA, E)])), "duplicate")
        expect("bad output status", validate_output(_synthetic([_row(*SA, "green")])), "unknown status")
        expect("bad output schema", validate_output(_synthetic([{"primitive": "x"}])), "schema")
        for label, body, want in (("auditor exit 2", "import sys; sys.exit(2)", "exited 2"),
                                  ("auditor non-JSON", "print('hello')", "not JSON")):
            (d / "stub.py").write_text(body)
            expect(label, run_auditor(d / "stub.py", TREE)[1], want)

        vend = d / "vend"
        shutil.copytree(ISO_DIR / "auditor", vend / "auditor")
        expect("vendored intact", check_pin_integrity(pin, vend), None)
        with (vend / "auditor/agent_isolation_audit.py").open("a") as fh:
            fh.write("\n# tamper\n")
        expect("vendored sha mismatch", check_pin_integrity(pin, vend), "sha256")

        errs, _gaps, _, out = check(TREE)
        expect("current tree passes", errs, None)
        if out is not None:
            ing = [r for r in out["rows"] if r["scope"] == "allow-agent-ingress"]
            if not ing or ing[0]["status"] != E:
                print("selftest FAIL: namespace+pod peer must be enforced (mctl-agents#921)")
                ok = False

        def mutated(label, mutate, want, pod_fails=False):
            nonlocal ok
            root = d / ("tree-" + re.sub(r"\W", "", label))
            shutil.copytree(TREE, root)
            mutate(root)
            expect(label, check(root)[0], want)
            if pod_fails:
                rc = subprocess.run([sys.executable, str(POD_SECURITY_SCRIPT), "--dir",
                                     str(root / "argo-workflows/cluster-templates")],
                                    capture_output=True).returncode
                if rc == 0:
                    print(f"selftest FAIL: {label}: pod-security validator should also fail")
                    ok = False
            shutil.rmtree(root)

        def drop_automount(root):
            p = root / "argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml"
            p.write_text(re.sub(r"^\s*automountServiceAccountToken: false\n", "", p.read_text(),
                                count=1, flags=re.M))

        def widen_ingress(root):
            p = root / "infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml"
            t = p.read_text()
            new = t.replace("          podSelector:\n            matchLabels:\n"
                            "              app.kubernetes.io/name: mctl-agents\n", "", 1)
            if new == t:
                raise SystemExit("selftest: allow-agent-ingress peer not found")
            p.write_text(new)

        def add_step(root):
            p = root / "argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml"
            docs = list(yaml.safe_load_all(p.read_text()))
            docs[0]["spec"]["templates"].append({"name": "rogue", "container": {
                "image": "{{workflow.parameters.agent_image}}", "command": ["true"]}})
            p.write_text(yaml.safe_dump_all(docs))

        mutated("automount removed", drop_automount, "automountServiceAccountToken")
        mutated("ingress widened", widen_ingress, "allow-agent-ingress")
        mutated("new step without controls", add_step, "lacks controls of its peers", pod_fails=True)
        mutated("new step unbaselined", add_step, "unbaselined row")

    print("selftest ok" if ok else "selftest FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--verify-upstream", action="store_true",
                    help="also fetch the pinned files from the pinned commit and compare bytes")
    ap.add_argument("--regenerate", action="store_true",
                    help="local only: print a candidate baseline (stdout or --out); never used in CI")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--tree", type=Path, default=TREE)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.regenerate:
        if os.environ.get("CI"):
            print("ERROR: --regenerate is local only", file=sys.stderr)
            return 1
        pin, errs = load_pin(PIN)
        out = None
        if pin is not None and not errs:
            errs = check_pin_integrity(pin, ISO_DIR)
        if pin is not None and not errs:
            out, errs = run_auditor(ISO_DIR / pin["entrypoint"], args.tree)
        if errs:
            for e in errs:
                print(f"ERROR: {e}", file=sys.stderr)
            return 1
        text = json.dumps(regenerate(pin, out, BASELINE), indent=2) + "\n"
        if args.out:
            args.out.write_text(text)
        else:
            sys.stdout.write(text)
        return 0
    errs, gaps, pin, out = check(args.tree, upstream=args.verify_upstream)
    if pin is not None and out is not None and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(summary(pin, out, gaps))
    for e in errs:
        print(f"ERROR: {e}", file=sys.stderr)
    if errs:
        print("(mctl-gitops#2292; see scripts/agent-isolation/README.md)", file=sys.stderr)
        return 1
    print(f"agent isolation matrix ok ({len(gaps)} open accepted gaps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
