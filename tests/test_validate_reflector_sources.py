#!/usr/bin/env python3
"""Proof for scripts/validate-reflector-sources.py (D1, the offline Reflector source guard).

A detector is accepted only when it is shown both ways (AGENTS.md, "Detectors,
Reconcilers and Review Gates"):
  GREEN   on converged input,
  RED     on each deliberate mutation,
  UNKNOWN (exit 2) on unreadable / partial / malformed input, never green,
  and every rule is load-bearing: with that one rule reverted (the module's
  REVERT test seam) its mutation stops being detected.

Every mutated tree is generated into a temporary directory. It is NOT committed
under tests/fixtures: the guard scans the whole tree including tests/fixtures,
so a committed enabler would turn the real repo scan red (the guard is its own
tripwire). This file spells the annotation key in pieces for the same reason.

Run: python3 tests/test_validate_reflector_sources.py   (stdlib only; exit 0 all pass, 1 failure)
"""
import contextlib
import importlib.util
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate-reflector-sources.py"
spec = importlib.util.spec_from_file_location("d1", SCRIPT)
d1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d1)

KEY = "reflector.v1.k8s." + "emberstack.com"
R = "reflection-"
ANCHOR = "platform-gitops/argo-workflows/config/mctl-platform-config.yaml"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="d1-proof-"))
failures, counter = [], [0]


def base_files():
    return {
        ANCHOR: f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: mctl-platform-config
  namespace: argo-workflows
  annotations:
    {KEY}/{R}allowed: "true"
    {KEY}/{R}auto-enabled: "true"
    {KEY}/{R}auto-namespaces: ""
data:
  A: b
""",
        "platform-gitops/argo-workflows/secrets/workflow-credentials.yaml": f"""apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: mctl-gitops-deploy-key
spec:
  target:
    name: mctl-gitops-deploy-key
    template:
      metadata:
        annotations:
          {KEY}/{R}allowed: "false"
          {KEY}/{R}auto-enabled: "false"
""",
        "README.md": "notes\n",
    }


def mk(name, extra=None, drop=()):
    d = TMP / name
    files = base_files()
    for k in drop:
        files.pop(k)
    files.update(extra or {})
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
    return d


def run(root, revert=()):
    """Runs the guard in-process; returns (rc, output)."""
    buf = io.StringIO()
    d1.REVERT.clear()
    d1.REVERT.update(revert)
    try:
        with contextlib.redirect_stdout(buf):
            rc = d1.main([str(root)])
    finally:
        d1.REVERT.clear()
    return rc, buf.getvalue()


def report(label, ok, detail=""):
    counter[0] += 1
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        failures.append(f"{label}: {detail}")


def expect(label, root, want, revert=()):
    rc, out = run(root, revert)
    report(label, rc == want, f"rc={rc} want={want}\n{out[-600:]}")


def not_detected(label, root, detecting_rc, rule):
    """Revert-the-fix: with `rule` removed the mutation must stop being detected."""
    rc, out = run(root, {rule})
    report(f"{label}  [revert {rule}]", rc != detecting_rc, f"still rc={rc} with {rule} reverted")


def has(label, root, text, want=True, revert=()):
    rc, out = run(root, revert)
    report(label, (text in out) == want, out[-500:])


def secret(annos, name="x", extra=""):
    body = "\n".join(f"    {a}" for a in annos)
    return f"kind: Secret\nmetadata:\n  name: {name}\n{extra}  annotations:\n{body}\n"


# ---------------------------------------------------------------- GREEN
print("== GREEN: converged input ==")
expect("G0 converged fixture", mk("base"), 0)
expect("G1 Row-1 end state: Secret sources false/false, regexes kept", mk("endstate", {"platform-gitops/endstate.yaml":
       f"""kind: Secret
metadata:
  name: postgres-credentials
  namespace: database
  annotations:
    {KEY}/{R}allowed: "false"
    {KEY}/{R}auto-enabled: "false"
    {KEY}/{R}allowed-namespaces: ".*"
    {KEY}/{R}auto-namespaces: ".*"
"""}), 0)
expect("G2 NUL byte in a non-text extension is skipped, not a false UNKNOWN", mk("nulbin", {"blob.bin": b"PK\0\0binary"}), 0)

# ---------------------------------------------------------------- RED
print("== RED: deliberate mutations ==")
RED = {}   # name -> (label, tree)
def red(name, label, rel, content):
    RED[name] = (label, mk("m_" + name, {rel: content}))
    expect(f"{name} {label}", RED[name][1], 1)

red("M1", 'Secret allowed: "true"', "platform-gitops/s.yaml", secret([f'{KEY}/{R}allowed: "true"']))
red("M2", 'auto-enabled "true" without allowed', "platform-gitops/s.yaml", secret([f'{KEY}/{R}auto-enabled: "true"']))
red("M3", 'value "TRUE"', "platform-gitops/s.yaml", secret([f'{KEY}/{R}allowed: "TRUE"']))
red("M4", 'value " true" (leading space)', "platform-gitops/s.yaml", secret([f'{KEY}/{R}allowed: " true"']))
red("M5", "templated ExternalSecret annotation (Helm value)", "helm/es.yaml",
    f"""kind: ExternalSecret
metadata:
  name: x
spec:
  target:
    template:
      metadata:
        annotations:
          {KEY}/{R}allowed: "{{{{ .Values.reflect }}}}"
""")
red("M6", "ExternalSecret spec.target.template.metadata.annotations true", "platform-gitops/es.yaml",
    f"""apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: pg
spec:
  target:
    name: pg
    template:
      metadata:
        annotations:
          {KEY}/{R}allowed: "true"
          {KEY}/{R}auto-enabled: "true"
""")
red("M7", "kubernetes_secret in .tf", "infra/db.tf",
    f"""resource "kubernetes_secret" "db" {{
  metadata {{
    name = "db"
    annotations = {{
      "{KEY}/{R}allowed" = "true"
      "{KEY}/{R}auto-enabled" = "true"
    }}
  }}
}}
""")
red("M8", "ConfigMap channel that is not allow-listed", "platform-gitops/cm.yaml",
    f'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: other-config\n  annotations:\n    {KEY}/{R}allowed: "true"\n    {KEY}/{R}auto-enabled: "true"\n')
red("M9", "kubectl annotate ...=true in a script", "scripts/fix.sh",
    f"#!/bin/sh\nkubectl annotate secret postgres-credentials -n database {KEY}/{R}allowed=true --overwrite\n")
red("M10", "same annotation under tests/fixtures/", "tests/fixtures/s.yaml", secret([f'{KEY}/{R}allowed: "true"']))
red("M11", "match-all namespaces, flags not provably false", "platform-gitops/s.yaml", secret([f'{KEY}/{R}auto-namespaces: ".*"']))
red("M12", "empty namespaces regex, flags absent", "platform-gitops/s.yaml", secret([f'{KEY}/{R}allowed-namespaces: ""']))
red("M13", "committed mirror/pull annotation (reflects)", "platform-gitops/s.yaml",
    secret([f'{KEY}/reflects: "database/postgres-credentials"'], extra="  namespace: tenant\n"))
red("M14", "key built indirectly (unqualified token)", "helm/t.tpl",
    'metadata:\n  annotations:\n    {{ printf "%s/' + R + 'allowed" $prefix }}: "true"\n')
red("M15", "kustomize JSON-patch ~1 form", "k/kustomization.yaml",
    f"""patches:
  - target: {{kind: Secret}}
    patch: |-
      - op: add
        path: /metadata/annotations/{KEY}~1{R}allowed
        value: "true"
""")
red("M16", "helm --set with escaped dots", "scripts/h.sh",
    "helm upgrade x y --set 'secret.annotations.reflector\\.v1\\.k8s\\." + "emberstack\\.com/" + R + "allowed=true'\n")
for n, suffix in [("helm", "/{{ .Values.k }}"), ("shell", "/$K"), ("fmt", "/%s"), ("plus", "+x"),
                  ("empty", "/"), ("digit", "/1abc"), ("tilde", "~1{{ .Values.k }}")]:
    red("M17-" + n, f"prefix spelled out, suffix not a known token ({suffix})", "helm/es.yaml",
        f"kind: ExternalSecret\nmetadata:\n  name: x\nspec:\n  target:\n    template:\n      metadata:\n        annotations:\n          {KEY}{suffix}: \"true\"\n")
red("M18", "allow-listed name in a DIFFERENT namespace", "platform-gitops/other-ns.yaml",
    f'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: mctl-platform-config\n  namespace: tenant-x\n  annotations:\n    {KEY}/{R}allowed: "true"\n    {KEY}/{R}auto-enabled: "true"\n')
red("M19", "allow-listed name with NO namespace", "platform-gitops/nons.yaml",
    f'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: mctl-platform-config\n  annotations:\n    {KEY}/{R}allowed: "true"\n')
red("M20", "UTF-16 (BOM) Secret with allowed true", "platform-gitops/s16.yaml", secret([f'{KEY}/{R}allowed: "true"']).encode("utf-16"))
red("M21", "enabler inside node_modules is scanned", "web/node_modules/pkg/s.yaml", secret([f'{KEY}/{R}allowed: "true"']))

# ---------------------------------------------------------------- UNKNOWN
print("== UNKNOWN: could not observe (exit 2, never green) ==")
expect("U1 missing root", TMP / "nonexistent", 2)
(TMP / "empty").mkdir()
expect("U2 empty directory", TMP / "empty", 2)
expect("U3 partial tree (anchor file missing)", mk("u_partial", drop=(ANCHOR,)), 2)
U_BLIND = mk("u_blind", {ANCHOR: "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: mctl-platform-config\n"})
expect("U4 anchor present but parser sees no enabler (blind parser)", U_BLIND, 2)
if os.geteuid() == 0:
    print("SKIP  U5 unreadable file (running as root, chmod 000 is readable)")
else:
    d = mk("u_unreadable", {"locked.yaml": "x\n"})
    (d / "locked.yaml").chmod(0)
    expect("U5 unreadable file", d, 2)
    (d / "locked.yaml").chmod(0o644)
expect("U6 root is a file", mk("u_file") / "README.md", 2)
d = mk("u_dangling")
os.symlink("/nonexistent/zzz", d / "dangling.yaml")
expect("U7 dangling symlink", d, 2)
NUL = mk("u_nul_yaml", {"platform-gitops/nobom.yaml": secret([f'{KEY}/{R}allowed: "true"']).encode("utf-16-le")})
expect("U8 NUL byte in .yaml without BOM", NUL, 2)

# ---------------------------------------------------------------- revert-the-fix
print("== revert-the-fix: rule removed => its mutation must stop being detected ==")
def rr(name, rule, rc=1):
    not_detected(f"{name} {RED[name][0]}", RED[name][1], rc, rule)
for n in ("M3", "M4", "M5"): rr(n, "flag_not_provable_false")
for n in ("M7", "M9", "M15", "M16"): rr(n, "formats")
for n in ("M7", "M9", "M10"): rr(n, "file_types")
for n in ("M11", "M12"): rr(n, "ns_matchall")
rr("M13", "reflects_marker")
rr("M14", "unqualified")
for n in ("helm", "shell", "fmt", "plus", "empty", "digit", "tilde"): rr("M17-" + n, "prefix_unrecognised_suffix")
rr("M18", "allow_ns")
rr("M20", "utf16_bom")
not_detected("U4 blind parser", U_BLIND, 2, "anchor")
not_detected("U8 NUL in text extension", NUL, 2, "nul_text_unknown")
ARCH = mk("g_archive", {"charts/argo-cd-1.2.3.tgz": b"", "charts/other.zip": b""})
has("C1 COVERAGE lists the packaged .tgz (not opened)", ARCH, "charts/argo-cd-1.2.3.tgz")
has("C2 COVERAGE lists the packaged .zip", ARCH, "charts/other.zip")
has("C3 COVERAGE says none when none", mk("base"), "0 packaged archive(s)")
has("R13 archive coverage line gone when its rule is reverted", ARCH, "charts/argo-cd-1.2.3.tgz", want=False, revert={"archive_coverage"})

# ---------------------------------------------------------------- the seam is not reachable from outside
print("== no outside lever on the guard ==")
env = dict(os.environ, SA_DET_REVERT="flag_not_provable_false,formats,file_types,anchor", SA_DET_PROOF_NONCE="x")
r = subprocess.run([sys.executable, str(SCRIPT), str(RED["M3"][1])], env=env, capture_output=True, text=True)
report("H1 env var cannot weaken the guard (CLI still RED on M3)", r.returncode == 1, r.stdout[-300:] + r.stderr[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), str(mk("base")), "--bogus"], capture_output=True, text=True)
report("H2 unknown CLI argument is UNKNOWN (rc 2), no traceback", r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), str(mk("base")), "--anchor"], capture_output=True, text=True)
report("H3 --anchor without a value is UNKNOWN (rc 2), no traceback", r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-300:])

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nchecks={counter[0]} failures={len(failures)}")
for f in failures:
    print("FAILED:", f)
sys.exit(1 if failures else 0)
