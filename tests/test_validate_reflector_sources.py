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
import json
import gzip
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


def not_detected(label, root, detecting_rc, *rules):
    """Revert-the-fix: with the rule(s) removed the mutation must stop being detected. Several rules are given
    when two independent layers (the line scan and the structural pass) both see the mutation."""
    rc, out = run(root, set(rules))
    report(f"{label}  [revert {'+'.join(rules)}]", rc != detecting_rc, f"still rc={rc} with {rules} reverted")


def has(label, root, text, want=True, revert=()):
    rc, out = run(root, revert)
    report(label, (text in out) == want, out[-500:])


def kobj(annos, name="x", extra=""):
    """A synthetic manifest (kind Secret) with the given annotation lines. Holds no data and no credential."""
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
expect("G2 a recognised binary type (PNG magic) holding NUL bytes is skipped, not a false UNKNOWN", mk("nulbin", {"img/logo.dat": b"\x89PNG\r\n\x1a\n\0\0\0"}), 0)

# ---------------------------------------------------------------- RED
print("== RED: deliberate mutations ==")
RED = {}   # name -> (label, tree)
def red(name, label, rel, content):
    RED[name] = (label, mk("m_" + name, {rel: content}))
    expect(f"{name} {label}", RED[name][1], 1)

red("M1", 'Secret allowed: "true"', "platform-gitops/s.yaml", kobj([f'{KEY}/{R}allowed: "true"']))
red("M2", 'auto-enabled "true" without allowed', "platform-gitops/s.yaml", kobj([f'{KEY}/{R}auto-enabled: "true"']))
red("M3", 'value "TRUE"', "platform-gitops/s.yaml", kobj([f'{KEY}/{R}allowed: "TRUE"']))
red("M4", 'value " true" (leading space)', "platform-gitops/s.yaml", kobj([f'{KEY}/{R}allowed: " true"']))
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
red("M10", "same annotation under tests/fixtures/", "tests/fixtures/s.yaml", kobj([f'{KEY}/{R}allowed: "true"']))
red("M11", "match-all namespaces, flags not provably false", "platform-gitops/s.yaml", kobj([f'{KEY}/{R}auto-namespaces: ".*"']))
red("M12", "empty namespaces regex, flags absent", "platform-gitops/s.yaml", kobj([f'{KEY}/{R}allowed-namespaces: ""']))
red("M13", "committed mirror/pull annotation (reflects)", "platform-gitops/s.yaml",
    kobj([f'{KEY}/reflects: "database/postgres-credentials"'], extra="  namespace: tenant\n"))
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
red("M20", "UTF-16 (BOM) Secret with allowed true", "platform-gitops/s16.yaml", kobj([f'{KEY}/{R}allowed: "true"']).encode("utf-16"))
red("M21", "enabler inside node_modules is scanned", "web/node_modules/pkg/s.yaml", kobj([f'{KEY}/{R}allowed: "true"']))

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
NUL = mk("u_nul_yaml", {"platform-gitops/nobom.yaml": kobj([f'{KEY}/{R}allowed: "true"']).encode("utf-16-le")})
expect("U8 NUL byte in .yaml without BOM", NUL, 2)

# ---------------------------------------------------------------- symlinks
print("== symlinks: observable, never followed out of the root ==")
OUT = TMP / "outside"
(OUT / "sub").mkdir(parents=True)
(OUT / "sub" / "s.yaml").write_text(kobj([f'{KEY}/{R}allowed: "true"']))
(OUT / "f.yaml").write_text(kobj([f'{KEY}/{R}allowed: "true"']))
SL_IN = mk("sl_inside", {"real/inner.yaml": "a: b\n"})
os.symlink(SL_IN / "real", SL_IN / "alias")
expect("S1 directory symlink to a directory inside the root is GREEN (target scanned at its real path)", SL_IN, 0)
has("S1b ...and is listed in COVERAGE by name", SL_IN, "real path): alias")
SL_IN_RED = mk("sl_inside_red", {"real/s.yaml": kobj([f'{KEY}/{R}allowed: "true"'])})
os.symlink(SL_IN_RED / "real", SL_IN_RED / "alias")
expect("S1c enabler behind an in-root directory symlink is still RED (found at the real path)", SL_IN_RED, 1)
SL_OUT = mk("sl_escape")
os.symlink(OUT / "sub", SL_OUT / "escape")
expect("S2 directory symlink escaping the root (target holds an enabler) is UNKNOWN, not GREEN", SL_OUT, 2)
SL_LOOP = mk("sl_loop")
os.symlink(".", SL_LOOP / "self")
t0 = __import__("time").time()
expect("S3 directory symlink loop to . terminates and is GREEN (listed, not followed)", SL_LOOP, 0)
report("S3b ...without recursing (finished in <5s)", __import__("time").time() - t0 < 5)
SL_LOOP2 = mk("sl_loop2")
os.symlink("b", SL_LOOP2 / "a"); os.symlink("a", SL_LOOP2 / "b")
expect("S3c mutual symlink loop (a->b->a) is UNKNOWN", SL_LOOP2, 2)
SL_DANG = mk("sl_dangling_dir")
os.symlink("nowhere/dir/", SL_DANG / "dd")
expect("S4 dangling directory symlink is UNKNOWN", SL_DANG, 2)
SL_FILE = mk("sl_file_escape")
os.symlink(OUT / "f.yaml", SL_FILE / "f.yaml")
expect("S5 file symlink pointing outside the root is UNKNOWN", SL_FILE, 2)
SL_FILE_IN = mk("sl_file_in", {"real.yaml": "a: b\n"})
os.symlink(SL_FILE_IN / "real.yaml", SL_FILE_IN / "alias.yaml")
expect("S6 file symlink inside the root is GREEN", SL_FILE_IN, 0)
ARCH_STALE = mk("stale_arch", {"charts/old.tgz": b""})
run(ARCH_STALE)
rc, out = run(TMP / "nonexistent")
report("S7 early return does not print archives left over from a previous scan (no stale function-attribute state)", rc == 2 and "old.tgz" not in out, out)

# ---------------------------------------------------------------- value binding (JSON patch / flow style)
print("== value binding: a value is read from the SAME list item, never a neighbouring one ==")
PATH_KEY = f"{KEY}~1{R}allowed"
def patch(*ops):
    return "patches:\n  - target: {kind: Secret}\n    patch: |-\n" + "".join("      " + l + "\n" for op in ops for l in op.split("\n"))
OP_FALSE = '- op: add\n  path: /spec/foo\n  value: "false"'
red("W1", 'value BEFORE path ("true"), next op has "false"', "k/kustomization.yaml",
    patch(f'- op: add\n  value: "true"\n  path: /metadata/annotations/{PATH_KEY}', OP_FALSE))
red("W2", 'value after path ("true"), next op has "false"', "k/kustomization.yaml",
    patch(f'- op: add\n  path: /metadata/annotations/{PATH_KEY}\n  value: "true"', OP_FALSE))
red("W3", 'value BEFORE path, the op ends the document, a preceding op has "false"', "k/kustomization.yaml",
    patch(OP_FALSE, f'- op: add\n  value: "true"\n  path: /metadata/annotations/{PATH_KEY}'))
expect("W4 value BEFORE path is its own op's \"false\"; the next op's \"true\" is not read", mk("w4", {"k/kustomization.yaml": patch(
    f'- op: add\n  value: "false"\n  path: /metadata/annotations/{PATH_KEY}', '- op: add\n  path: /spec/foo\n  value: "true"')}), 0)
expect("W5 value 6 keys below the path, same op, \"false\": still found (no fixed look-ahead window)", mk("w5", {"k/kustomization.yaml": patch(
    f'- op: add\n  path: /metadata/annotations/{PATH_KEY}\n  k1: a\n  k2: b\n  k3: c\n  k4: d\n  k5: e\n  k6: f\n  value: "false"')}), 0)
expect("W6 two value keys in one op: duplicate key, UNKNOWN (never GREEN, never read as the first one)", mk("w6", {"k/kustomization.yaml":
       patch(f'- op: add\n  path: /metadata/annotations/{PATH_KEY}\n  value: "false"\n  value: "true"')}), 2)
red("W7", "op with no value at all: not found, unreadable", "k/kustomization.yaml",
    patch(f'- op: remove\n  path: /metadata/annotations/{PATH_KEY}', '- op: add\n  path: /spec/foo\n  value: "false"'))
red("W8", "flow style one-liner with value true, next op false", "k/kustomization.yaml",
    patch('- {op: add, path: /metadata/annotations/' + PATH_KEY + ', value: "true"}', '- {op: add, path: /spec/foo, value: "false"}'))
red("W9", "flow style, value BEFORE path", "k/kustomization.yaml",
    patch('- {op: add, value: "true", path: /metadata/annotations/' + PATH_KEY + '}', '- {op: add, path: /spec/foo, value: "false"}'))
expect("W10 flow style one-liner with its own \"false\" is GREEN", mk("w10", {"k/kustomization.yaml": patch(
    '- {op: add, value: "false", path: /metadata/annotations/' + PATH_KEY + '}', '- {op: add, path: /spec/foo, value: "true"}')}), 0)
red("W11", "JSON patch as an escaped-quote string, true", "k/patch.yaml",
    'patch: "[{\\"op\\":\\"add\\",\\"path\\":\\"/metadata/annotations/' + PATH_KEY + '\\",\\"value\\":\\"true\\"}]"\n')

# ---------------------------------------------------------------- document identity
print("== allow-list bound to the parsed document that holds the enabler ==")
CM = lambda extra="", kind="ConfigMap", ns="argo-workflows", name="mctl-platform-config": (
    f'apiVersion: v1\nkind: {kind}\nmetadata:\n  name: {name}\n  namespace: {ns}\n  annotations:\n    {KEY}/{R}allowed: "true"\n    {KEY}/{R}auto-enabled: "true"\n{extra}')
ALLOWED_DOC = base_files()[ANCHOR]
SPOOF = (f'kind: ConfigMap\nmetadata:\n  name: mctl-platform-config\n  namespace: argo-workflows\n  annotations:\n    {KEY}/{R}allowed: "true"\n'
         f'"kind": Secret\n"metadata":\n  "name": postgres-credentials\n  "namespace": database\n  annotations:\n    {KEY}/{R}allowed: "true"\n')
SP = mk("a1", {"platform-gitops/spoof.yaml": SPOOF})
expect("A1 duplicate top-level keys (kind + quoted \"kind\") with an allow-listed name: UNKNOWN, not GREEN", SP, 2)
has("A1b ...and says why", SP, "defined more than once in one mapping")
red("A2", "`--- # comment` separator: the second document (a Secret) is a separate document", "platform-gitops/two.yaml",
    ALLOWED_DOC + "--- # next\n" + kobj([f'{KEY}/{R}allowed: "true"']))
red("A3", "`--- !!map` separator", "platform-gitops/two2.yaml", ALLOWED_DOC + "--- !!map\n" + kobj([f'{KEY}/{R}allowed: "true"']))
red("A4", "separator with trailing spaces", "platform-gitops/two3.yaml", ALLOWED_DOC + "---   \n" + kobj([f'{KEY}/{R}allowed: "true"']))
red("A5", "allow-listed name but kind Secret", "platform-gitops/s.yaml", CM(kind="Secret"))
red("A6", "allow-listed ConfigMap carrying a SECOND enabler outside its own metadata.annotations", "platform-gitops/n.yaml",
    CM() + f'spec:\n  template:\n    metadata:\n      annotations:\n        {KEY}/{R}allowed: "true"\n')
red("A7", "allow-listed doc in a .txt file: the allow-list applies to parsed YAML/JSON only", "platform-gitops/doc.txt", CM())
expect("A8 the legitimate allow-listed source written with quoted keys (JSON-style) is GREEN", mk("a8", {ANCHOR: (
    '{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "mctl-platform-config", "namespace": "argo-workflows", "annotations": {'
    f'"{KEY}/{R}allowed": "true", "{KEY}/{R}auto-enabled": "true", "{KEY}/{R}auto-namespaces": ""}}}}}}\n')}), 0)
UNPARSE = mk("a9", {"platform-gitops/tmpl.yaml": CM() + "data:\n  x: {{ .Values.x }}\n"})
expect("A9 allow-listed name in a .yaml that is not valid YAML: UNKNOWN", UNPARSE, 2)
red("A10", "same name, different namespace, in a parsed doc", "platform-gitops/o.yaml", CM(ns="tenant-x"))

# ---------------------------------------------------------------- escape-encoded keys
print("== escape-encoded keys ==")
red("E1", 'key spelled with \\x65 escapes in a double-quoted YAML key', "platform-gitops/e1.yaml",
    "kind: Secret\nmetadata:\n  name: x\n  annotations:\n    \"r\\x65flector.v1.k8s." + "emberstack.com/r\\x65" + "flection-allowed\": \"true\"\n")
red("E2", "key spelled with \\u0065 escapes (JSON)", "platform-gitops/e2.json",
    '{"kind":"Secret","metadata":{"name":"x","annotations":{"r\\u0065flector.v1.k8s.' + 'emberstack.com/r\\u0065' + 'flection-allowed":"true"}}}\n')
red("E3", "key spelled with \\U00000065 escapes in a script", "scripts/e3.sh",
    "kubectl annotate secret x 'r\\U00000065flector.v1.k8s." + "emberstack.com/r\\U00000065" + "flection-allowed=true'\n")
expect("E4 an unrelated \\u escape in a JSON file is not a false RED", mk("e4", {"platform-gitops/e4.json": '{"msg":"caf\\u00e9"}\n'}), 0)

# ---------------------------------------------------------------- archives
print("== archives: opened in memory, scanned, caps enforced ==")
import io, tarfile, zipfile, gzip
def tar_bytes(files, mode="w:gz"):
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode=mode) as tf:
        for n, c in files.items():
            c = c if isinstance(c, bytes) else c.encode()
            ti = tarfile.TarInfo(n); ti.size = len(c)
            tf.addfile(ti, io.BytesIO(c))
    return bio.getvalue()
def zip_bytes(files):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        for n, c in files.items(): zf.writestr(n, c)
    return bio.getvalue()
HIT_DOC = kobj([f'{KEY}/{R}allowed: "true"'])
CLEAN = "a: b\n"
expect("P1 clean .tgz is GREEN", mk("p1", {"charts/c.tgz": tar_bytes({"c/values.yaml": CLEAN})}), 0)
has("P1b ...and COVERAGE says it was opened and scanned", mk("p1"), "charts/c.tgz (1 members)")
red("P2", "enabler inside a .tgz member", "charts/c.tgz", tar_bytes({"c/templates/s.yaml": HIT_DOC}))
red("P3", "enabler inside a .zip member", "charts/c.zip", zip_bytes({"c/s.yaml": HIT_DOC}))
red("P4", "enabler inside a plain .tar member", "charts/c.tar", tar_bytes({"c/s.yaml": HIT_DOC}, mode="w"))
red("P5", "enabler inside a single .gz", "charts/s.yaml.gz", gzip.compress(HIT_DOC.encode()))
red("P6", "enabler inside a .tgz nested in a .zip", "charts/n.zip", zip_bytes({"inner.tgz": tar_bytes({"s.yaml": HIT_DOC})}))
red("P7", "enabler inside a .whl (zip)", "dist/x.whl", zip_bytes({"x/s.yaml": HIT_DOC}))
expect("P8 corrupt archive is UNKNOWN", mk("p8", {"charts/bad.tgz": b"not an archive at all"}), 2)
expect("P9 empty archive file is UNKNOWN", mk("p9", {"charts/empty.zip": b""}), 2)
expect("P10 archive nested deeper than the limit is UNKNOWN", mk("p10", {"a.zip": zip_bytes({"b.zip": zip_bytes({"c.zip": zip_bytes({"d.yaml": CLEAN})})})}), 2)
expect("P11 NUL member of an unknown type inside an archive is UNKNOWN", mk("p11", {"c.zip": zip_bytes({"blob.dat": b"\0\0\0x"})}), 2)
expect("P12 invalid UTF-8 member in an archive is UNKNOWN", mk("p12", {"c.tgz": tar_bytes({"m.yaml": b"a: \xff\xfe\xfa\n"})}), 2)
hostile = "../../x\n::error::pwned.yaml"
HN = mk("p13", {"c.zip": zip_bytes({hostile: HIT_DOC})})
rc, out = run(HN)
report("P13 hostile member name (../, newline, ::error::) is found (RED) and printed escaped, no extraction, no log injection",
       rc == 1 and not any(l.startswith("::") for l in out.splitlines()) and "\\u000a" in out and not (HN / "x").exists(), out[-400:])
def with_caps(label, want, files, **caps):
    old = {k: getattr(d1, k) for k in caps}
    try:
        for k, v in caps.items(): setattr(d1, k, v)
        expect(label, mk(label.split()[0].lower(), files), want)
    finally:
        for k, v in old.items(): setattr(d1, k, v)
with_caps("P14 member over the size cap is UNKNOWN", 2, {"c.tgz": tar_bytes({"a.yaml": "x" * 5000})}, MAX_MEMBER_BYTES=1000)
with_caps("P15 more members than the cap is UNKNOWN", 2, {"c.zip": zip_bytes({f"f{i}.yaml": CLEAN for i in range(5)})}, MAX_MEMBERS=3)
with_caps("P16 total uncompressed size over the cap is UNKNOWN", 2, {"c.zip": zip_bytes({f"f{i}.yaml": "a: " + "b" * 400 + "\n" for i in range(5)})}, MAX_TOTAL_BYTES=1500)
with_caps("P17 within the caps is GREEN (control for P14-P16)", 0, {"c.zip": zip_bytes({f"f{i}.yaml": CLEAN for i in range(3)})}, MAX_MEMBERS=3, MAX_MEMBER_BYTES=1000, MAX_TOTAL_BYTES=1500)
BOMB = mk("p18", {"b.zip": zip_bytes({"big.yaml": "a" * 3000})})
old = d1.MAX_MEMBER_BYTES; d1.MAX_MEMBER_BYTES = 1000
try:
    rc, out = run(BOMB)
finally: d1.MAX_MEMBER_BYTES = old
report("P18 a member that is larger than the cap once decompressed is UNKNOWN (the cap is on real bytes, not on declared sizes)", rc == 2, out[-300:])

# ---------------------------------------------------------------- binary / undecodable files of any extension
print("== NUL / invalid UTF-8 in any extension is UNKNOWN unless a recognised binary type ==")
for ext in (".json", ".sh", ".tf", ".tpl", ".txt", ".py", ".toml", ""):
    expect(f"B1 NUL byte in a file with extension {ext!r} is UNKNOWN", mk("b1" + ext.strip("."), {"x/f" + ext: b"a\0b"}), 2)
for ext in (".yaml", ".md", ".txt", ""):
    expect(f"B2 invalid UTF-8 in a file with extension {ext!r} is UNKNOWN", mk("b2" + ext.strip("."), {"x/f" + ext: b"a: \xff\xfe\n"}), 2)
expect("B3 .pdf with NUL bytes is a recognised binary type: GREEN", mk("b3", {"docs/a.pdf": b"%PDF-1.4\0\0"}), 0)
expect("B4 PNG magic under an unknown extension is a recognised binary type: GREEN", mk("b4", {"docs/a.xyz": b"\x89PNG\r\n\x1a\n\0"}), 0)
expect("B5 .pyc is a recognised binary type: GREEN", mk("b5", {"__pycache__/a.cpython-310.pyc": b"\x00\x01\x02"}), 0)
expect("B6 a text file that merely contains a PNG-like word is not exempt (NUL, .yaml)", mk("b6", {"x/f.yaml": b"PNG\0"}), 2)

# ---------------------------------------------------------------- printed paths
print("== control characters in printed paths ==")
NL = mk("n1", {"platform-gitops/a\n::error::pwned.yaml": kobj([f'{KEY}/{R}allowed: "true"'])})
rc, out = run(NL)
report("N1 RED finding for a file whose NAME has a newline and ::error:: is printed escaped (no line starts with ::)", rc == 1 and not any(l.startswith("::") for l in out.splitlines()) and "\\u000a" in out, out[-300:])
ND = mk("n2", {"x\n::warning::y/f.yaml": CLEAN}); os.symlink(OUT / "sub", ND / "l\n::error::z")
rc, out = run(ND)
report("N2 UNKNOWN reason for a hostile symlink name is escaped too", rc == 2 and not any(l.startswith("::") for l in out.splitlines()), out[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), str(mk("base")), "--bogus\n::error::x"], capture_output=True, text=True)
report("N3 hostile CLI argument is printed escaped", r.returncode == 2 and not any(l.startswith("::") for l in r.stdout.splitlines()), r.stdout)

# ---------------------------------------------------------------- mutation gaps: sibling-prefix symlink, walk errors, value reading, key classes
print("== rule-by-rule coverage ==")
SIB = TMP / "sib"; (SIB / "root").mkdir(parents=True); (SIB / "rootX").mkdir()
for rel, c in base_files().items():
    (SIB / "root" / rel).parent.mkdir(parents=True, exist_ok=True); (SIB / "root" / rel).write_text(c)
(SIB / "rootX" / "s.yaml").write_text(HIT_DOC)
os.symlink(SIB / "rootX", SIB / "root" / "sibling")
expect("K1 directory symlink to a SIBLING directory whose name starts with the root's name is outside the root: UNKNOWN", SIB / "root", 2)
if os.geteuid() == 0:
    print("SKIP  K2 unreadable directory (running as root)")
else:
    UD = mk("k2", {"locked/inner.yaml": CLEAN}); (UD / "locked").chmod(0)
    expect("K2 unreadable directory (walk error) is UNKNOWN", UD, 2)
    (UD / "locked").chmod(0o755)
red("K3", "enabler key with no readable value (kubectl annotate with the key only)", "scripts/k3.sh",
    f"kubectl annotate secret x {KEY}/{R}allowed\n")
for key in ("reflects", "auto-reflects", "reflected-version", "reflected-at"):
    red("K4-" + key, f"committed mirror marker {key}", "platform-gitops/m.yaml", kobj([f'{KEY}/{key}: "database/postgres-credentials"'], extra="  namespace: tenant\n"))
for key in ("allowed-namespaces", "auto-namespaces", "allowed-namespaces-selector", "auto-namespaces-selector"):
    red("K5-" + key, f"namespace key {key} match-all with flags absent", "platform-gitops/n.yaml", kobj([f'{KEY}/{R}{key}: ".*"']))
red("K6", "unknown annotation suffix", "platform-gitops/u.yaml", kobj([f'{KEY}/bogus-setting: "x"']))
red("K7", "removal of an UNKNOWN suffix is not a removal of a known key", "scripts/r.sh", f"kubectl annotate secret x {KEY}/bogus-\n")
expect("K8 removal of a known key (kubectl annotate key-) is GREEN", mk("k8", {"scripts/r.sh": f"kubectl annotate secret x {KEY}/{R}allowed-\n"}), 0)
red("K9", "only ONE flag provably false, namespaces match-all", "platform-gitops/n.yaml", kobj([f'{KEY}/{R}allowed: "false"', f'{KEY}/{R}auto-namespaces: ".*"']))
expect("K10 BOTH flags false with match-all namespaces is GREEN (Row-1 end state)", mk("k10", {"platform-gitops/n.yaml": kobj([f'{KEY}/{R}allowed: "false"', f'{KEY}/{R}auto-enabled: "false"', f'{KEY}/{R}auto-namespaces: ".*"'])}), 0)
expect("K11 reflects pointing at the allow-listed source is GREEN", mk("k11", {"platform-gitops/p.yaml": kobj([f'{KEY}/reflects: "argo-workflows/mctl-platform-config"'], extra="  namespace: tenant\n")}), 0)
red("K12", "auto-reflects pointing at the allow-listed source is NOT allowed", "platform-gitops/p.yaml", kobj([f'{KEY}/auto-reflects: "argo-workflows/mctl-platform-config"']))
red("K13", "reflects pointing anywhere else", "platform-gitops/p.yaml", kobj([f'{KEY}/reflects: "argo-workflows/other"']))
for i, v in enumerate(["", ".*", ".+", ".*?", "[\\s\\S]*", "[^]*", "^.*$", "(.*)", "tenant-a,.*", "^(.*)$"]):
    red(f"K14-{i}", f"match-all namespace regex {v!r}", "platform-gitops/n.yaml", kobj([f'{KEY}/{R}auto-namespaces: "{v}"']))
for v in ("tenant-a", "tenant-.*", "^tenant-[a-z]+$"):
    expect(f"K15 specific namespace regex {v!r} with flags absent is GREEN", mk("k15", {"platform-gitops/n.yaml": kobj([f'{KEY}/{R}auto-namespaces: "{v}"'])}), 0)
for v in ("false", "False", "FALSE", " false ", "'false'"):
    expect(f"K16 flag value {v!r} is provably false: GREEN", mk("k16", {"platform-gitops/n.yaml": kobj([f'{KEY}/{R}allowed: {v}'])}), 0)
expect("K17 .md prose naming the bare domain is GREEN", mk("k17", {"docs/n.md": "Reflector (" + "reflector.v1.k8s." + "emberstack.com) is installed.\n"}), 0)
expect("K18 .md prose naming a bare flag token is GREEN", mk("k18", {"docs/n.md": "set " + R + "allowed to false\n"}), 0)
red("K19", "a key-shaped templated tail in .md is still flagged", "docs/n.md", "see " + KEY + "/{{ .Values.k }}\n")
red("K20", "unqualified token in a .txt file", "docs/n.txt", "set " + R + "allowed to true\n")
has("K21 RED output carries the finding text and the findings count", mk("m_M1"), "not provably")
has("K22 the unrecognised-suffix finding prints the whole tail", RED["M17-helm"][1], "{{ .Values.k }}")
rc, out = run(mk("m_M1"))
report("K23 RED prints 'RED (exit 1)' with the counts", "RED (exit 1)" in out and "findings=" in out, out[-300:])
rc, out = run(TMP / "nonexistent")
report("K24 UNKNOWN prints its reason", rc == 2 and "root not a directory" in out, out[-300:])
buf = io.StringIO()
with contextlib.redirect_stdout(buf): rc = d1.main([str(mk("k26")), "--anchor", "does/not/exist.yaml"])
report("K26 a missing --anchor file is UNKNOWN even when the default allow-listed source parses elsewhere", rc == 2 and "anchor missing" in buf.getvalue(), buf.getvalue()[-300:])
d1.REVERT.add("anchor_file")
try:
    with contextlib.redirect_stdout(io.StringIO()): rc2 = d1.main([str(mk("k26")), "--anchor", "does/not/exist.yaml"])
finally: d1.REVERT.clear()
report("K26b revert-the-fix: with the anchor-file rule removed the missing --anchor is no longer UNKNOWN [revert anchor_file]", rc2 != 2, f"rc={rc2}")

# ---------------------------------------------------------------- revert-the-fix
print("== revert-the-fix: rule removed => its mutation must stop being detected ==")
def rr(name, *rules, rc=1):
    not_detected(f"{name} {RED[name][0]}", RED[name][1], rc, *rules)
for n in ("M3", "M4", "M5"): rr(n, "flag_not_provable_false")
for n in ("M7", "M9", "M16"): rr(n, "formats")
rr("M15", "formats", "structural")
for n in ("M11", "M12"): rr(n, "ns_matchall")
rr("M13", "reflects_marker")
rr("M14", "unqualified")
for n in ("helm", "shell", "fmt", "plus", "empty", "digit", "tilde"): rr("M17-" + n, "prefix_unrecognised_suffix")
rr("M20", "utf16_bom")
not_detected("S2 escaping directory symlink", SL_OUT, 2, "dir_symlinks")
not_detected("S5 escaping file symlink", SL_FILE, 2, "dir_symlinks")
has("S1b directory symlink listing gone when its rule is reverted", SL_IN, "COVERAGE directory symlinks: 1 with", want=False, revert={"dir_symlinks"})
rr("E1", "escape_decode", "structural"); rr("E2", "escape_decode", "structural"); rr("E3", "escape_decode")
not_detected("P2 enabler in .tgz", RED["P2"][1], 1, "open_archives")
not_detected("P3 enabler in .zip", RED["P3"][1], 1, "open_archives")
not_detected("P6 enabler in nested archive", RED["P6"][1], 1, "open_archives")
if os.geteuid() != 0:
    not_detected("K2 unreadable directory", UD, 2, "walk_errors")
not_detected("U4 blind parser", U_BLIND, 2, "anchor")

# ---------------------------------------------------------------- the seam is not reachable from outside
print("== no outside lever on the guard ==")
env = dict(os.environ, SA_DET_REVERT="flag_not_provable_false,formats,anchor,escape_decode,open_archives", SA_DET_PROOF_NONCE="x")
r = subprocess.run([sys.executable, str(SCRIPT), str(RED["M3"][1])], env=env, capture_output=True, text=True)
report("H1 env var cannot weaken the guard (CLI still RED on M3)", r.returncode == 1, r.stdout[-300:] + r.stderr[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), str(mk("base")), "--bogus"], capture_output=True, text=True)
report("H2 unknown CLI argument is UNKNOWN (rc 2), no traceback", r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), str(mk("base")), "--anchor"], capture_output=True, text=True)
report("H3 --anchor without a value is UNKNOWN (rc 2), no traceback", r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-300:])


# ---------------------------------------------------------------- mutation-matrix closure (PR #2553 round 3)
print("== boundaries, output and CLI paths found uncovered by the full mutation matrix ==")
with_caps("X1 member of exactly the size cap is read and GREEN (cap is >, not >=)", 0, {"c.zip": zip_bytes({"a.yaml": "a: " + "b" * 996 + "\n"})}, MAX_MEMBER_BYTES=1000)
with_caps("X2 member one byte over the cap is UNKNOWN", 2, {"c.zip": zip_bytes({"a.yaml": "a: " + "b" * 997 + "\n"})}, MAX_MEMBER_BYTES=1000)
with_caps("X3 tar member of exactly the cap is GREEN", 0, {"c.tgz": tar_bytes({"a.yaml": "a: " + "b" * 996 + "\n"})}, MAX_MEMBER_BYTES=1000)
with_caps("X4 total of exactly the total cap is GREEN", 0, {"c.zip": zip_bytes({"a.yaml": "a: " + "b" * 496 + "\n", "b.yaml": "a: " + "b" * 496 + "\n"})}, MAX_TOTAL_BYTES=1000)
with_caps("X5 total one byte over the total cap is UNKNOWN", 2, {"c.zip": zip_bytes({"a.yaml": "a: " + "b" * 496 + "\n", "b.yaml": "a: " + "b" * 497 + "\n"})}, MAX_TOTAL_BYTES=1000)
rc, out = run(mk("x6"))
report("X6 GREEN output carries the COVERAGE block and the exact GREEN line", rc == 0 and "COVERAGE" in out and "GREEN (exit 0, repo scope only; NOT 'no S-A')" in out, out[-300:])
EMPTY = TMP / "x7_empty"; EMPTY.mkdir()
rc, out = run(EMPTY, {"anchor_file"})
report("X7 a root with no files is UNKNOWN by the zero-files rule alone (anchor check reverted)", rc == 2 and "no files scanned" in out, out[-300:])
rc, out = run(EMPTY)
report("X7b ...and UNKNOWN (anchor missing) with the anchor check in place", rc == 2 and "anchor missing" in out, out[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), "--anchor"], capture_output=True, text=True)
report("X8 a leading flag is parsed as a flag, not as the root (output says bad arg, no scan of a path called --anchor)", r.returncode == 2 and "bad arg" in r.stdout, r.stdout[-300:])
YSTUB = TMP / "x9_stub"; YSTUB.mkdir(); (YSTUB / "yaml.py").write_text("raise ImportError('blocked for the test')\n")
r = subprocess.run([sys.executable, str(SCRIPT), str(mk("base"))], env=dict(os.environ, PYTHONPATH=str(YSTUB)), capture_output=True, text=True)
report("X9 PyYAML missing: UNKNOWN (rc 2) with the reason, never GREEN", r.returncode == 2 and "PyYAML is not installed" in r.stdout and "GREEN" not in r.stdout, r.stdout[-300:] + r.stderr[-300:])
LIST_DOC = "- mctl-platform-config\n- {annotations: {" + KEY + "/" + R + "allowed: \"true\"}}\n"
rc, out = run(mk("x10", {"platform-gitops/l.yaml": LIST_DOC}))
report("X10 allow-listed name plus an enabler inside a YAML LIST document (not a mapping): not GREEN", rc != 0, out[-300:])
SCALAR_DOC = "mctl-platform-config\n" + KEY + "/" + R + "allowed: \"true\"\n"
rc, out = run(mk("x11", {"platform-gitops/l.yaml": SCALAR_DOC}))
report("X11 allow-listed name plus an enabler in a document that is not a mapping: not GREEN", rc != 0, out[-300:])
red("X12", 'match-all with a space after the comma ("x, .*")', "platform-gitops/s.yaml", kobj([f'{KEY}/{R}allowed-namespaces: "x, .*"']))
red("X13", 'match-all wrapped in parentheses with inner blanks ("( .* )")', "platform-gitops/s.yaml", kobj([f'{KEY}/{R}allowed-namespaces: "( .* )"']))
red("X14", 'match-all anchored and parenthesised ("^(.*)$")', "platform-gitops/s.yaml", kobj([f'{KEY}/{R}allowed-namespaces: "^(.*)$"']))
expect("X15 provably-false values with blanks and case are GREEN (false / ' False ' / \"FALSE\")", mk("x15", {"platform-gitops/s.yaml": kobj([f'{KEY}/{R}allowed: " False "', f"{KEY}/{R}auto-enabled: FALSE"])}), 0)
PATCH_BLANK = ("patches:\n  - target: {kind: Secret}\n    patch: |-\n      - op: add\n        path: /spec/foo\n        value: \"false\"\n\n"
               f"      - op: add\n\n        value: \"true\"\n        path: /metadata/annotations/{PATH_KEY}\n")
red("X16", "blank lines inside a JSON-patch op do not detach the value from its path", "k/kustomization.yaml", PATCH_BLANK)
expect("X17 an uppercase file name is not treated as a binary type by case folding of a NUL-containing .PNG", mk("x17", {"img/LOGO.PNG": b"\0\0\0 not a png"}), 2)

red("X18", "enabler on the FIRST line of a file that starts with a UTF-8 BOM", "platform-gitops/bom.yaml", b"\xef\xbb\xbf" + f'{KEY}/{R}allowed: "true"\n'.encode())
for key_ in ("reflected-version", "reflected-at"):
    rc, out = run(mk("x19" + key_[-2:], {"platform-gitops/m.yaml": kobj([f"{KEY}/{key_}: 1"])}))
    report(f"X19 committed {key_} is named a mirror marker (not just an unknown key)", rc == 1 and "mirror marker" in out, out[-300:])

expect("X20 selector keys with flags provably false are known keys and GREEN", mk("x20", {"platform-gitops/sel.yaml": kobj([f'{KEY}/{R}allowed: "false"', f'{KEY}/{R}auto-enabled: "false"', f'{KEY}/{R}allowed-namespaces-selector: "team=a"', f'{KEY}/{R}auto-namespaces-selector: "team=a"'])}), 0)
red("X21", "empty selector, flags absent: match-all semantics", "platform-gitops/sel2.yaml", kobj([f'{KEY}/{R}auto-namespaces-selector: ""']))

# ---------------------------------------------------------------- round 2 (PR #2553 @ b69a29c81): parse-based reading
print("== round 2: keys and values read from the PARSED document, not only from lines ==")
import time
SPLIT3 = "reflector.v1.k8s.ember\\\n      stack.com/reflec\\\n      tion-allowed"      # one key over three source lines
HEADER = "apiVersion: v1\nkind: Secret\nmetadata:\n  name: x\n  namespace: database\n"
def annos(body): return HEADER + "  annotations:\n" + body
RED_R2 = {}
def red2(name, label, rel, content, rc=1):
    RED_R2[name] = mk("r2_" + name, {rel: content})
    expect(f"{name} {label}", RED_R2[name], rc)

red2("N1a", "explicit `? \"...\\<newline>...\"` key split over three lines, value true", "platform-gitops/n1a.yaml",
     annos(f'    ? "{SPLIT3}"\n    : "true"\n'))
red2("N1b", "same key split over three lines in a flow mapping opened on the `annotations:` line (kubectl rejects it too: UNKNOWN)", "platform-gitops/n1b.yaml",
     HEADER + f'  annotations: {{"{SPLIT3}": "true"}}\n', rc=2)
red2("N1b2", "same, flow mapping on its own line: PyYAML refuses it, so the line-ending backslash alone makes it UNKNOWN", "platform-gitops/n1b2.yaml",
     annos(f'    {{"{SPLIT3}": "true"}}\n'), rc=2)
expect("N1c split key resolved and provably false is GREEN (fully resolved)", mk("n1c", {"platform-gitops/n1c.yaml": annos(f'    ? "{SPLIT3}"\n    : "false"\n')}), 0)
red2("N1d", "single-quoted key folded over two lines: the resolved key is not a known suffix", "platform-gitops/n1d.yaml",
     annos("    ? 'reflector.v1.k8s." + "emberstack.com/reflec\n      tion-allowed'\n    : \"true\"\n"))
red2("N1e", "JSON string key written with a backslash-newline-free \\u escape and an explicit value true", "platform-gitops/n1e.json",
     '{"kind":"Secret","metadata":{"name":"x","annotations":{"reflector.v1.k8s.\\u0065mberstack.com/reflec\\u0074ion-allowed":"true"}}}\n')
for nm, fix in (("N1a", RED_R2["N1a"]),):
    not_detected(f"{nm} explicit multi-line key", fix, 1, "structural")
A_KEY = "reflector.v1.k8s." + "emberstack.com/" + R + "allowed"
red2("N2a", "alias used as a key (anchor on a plain value with a same-line value: false)", "platform-gitops/n2a.yaml",
     f'x: {{a: &k {A_KEY}, value: "false"}}\n' + annos('    *k : "true"\n'))
red2("N2b", "alias used as a key (anchor on a flow-map key)", "platform-gitops/n2b.yaml",
     f'a: {{&k {A_KEY}: "false"}}\n' + annos('    *k : "true"\n'))
expect("N2c alias key that resolves to a provably false value is GREEN", mk("n2c", {"platform-gitops/n2c.yaml": f'a: {{&k {A_KEY}: "false"}}\n' + annos('    *k : "false"\n')}), 0)
red2("N2d", "alias of a whole mapping carrying the enabler, reused under another key", "platform-gitops/n2d.yaml",
     annos(f'    a: &m {{{A_KEY}: "true"}}\n    b: *m\n'))
not_detected("N2a alias key", RED_R2["N2a"], 1, "structural")
not_detected("N2b alias key", RED_R2["N2b"], 1, "structural")
PATHK = f"/metadata/annotations/{KEY}~1{R}allowed"
def op_file(body): return "- op: add\n  path: " + PATHK + "\n" + body
for nm, label, body in (
        ("N3a", 'duplicate `value` key, second "true" after "false"', '  value: "false"\n  "value": "true"\n'),
        ("N3b", 'duplicate `value` key spelled with an escape: "v\\x61lue"', '  value: "false"\n  "v\\x61lue": "true"\n'),
        ("N3c", 'duplicate `value` key as an explicit key', '  value: "false"\n  ? value\n  : "true"\n'),
        ("N3d", 'merge key supplying a second `value`', '  value: "false"\n  <<: {value: "true"}\n'),
        ("N3e", 'two merge sources both supplying value', '  <<: [{value: "false"}, {value: "true"}]\n')):
    red2(nm, label, "k/patch.yaml", op_file(body), rc=2)
    inline = "patches:\n  - target: {kind: Secret}\n    patch: |-\n" + "".join("      " + l + "\n" for l in op_file(body).splitlines())
    red2(nm + "k", label + " (inside a kustomization patch string)", "k/kustomization.yaml", inline, rc=2)
red2("N8a", "trailing comment on the path line says `value: false`, the real value is true", "k/patch.yaml",
     "- op: add\n  path: " + PATHK + "   # value: false\n  value: \"true\"\n")
red2("N8b", "same inside a kustomization patch string", "k/kustomization.yaml",
     "patches:\n  - target: {kind: Secret}\n    patch: |-\n      - op: add\n        path: " + PATHK + "   # value: false\n        value: \"true\"\n")
red2("N8c", "comment on the key line of a plain annotation hides a true", "platform-gitops/n8c.yaml",
     annos(f'    {A_KEY}: "true"   # value: false\n'))
expect("N8d a comment saying `value: true` next to a real false is GREEN", mk("n8d", {"k/patch.yaml": "- op: add\n  path: " + PATHK + "   # value: true\n  value: \"false\"\n"}), 0)
expect("N8e a real false with a trailing comment is GREEN", mk("n8e", {"platform-gitops/n8e.yaml": annos(f'    {A_KEY}: "false"   # was true\n')}), 0)
not_detected("N8a trailing comment", RED_R2["N8a"], 1, "structural", "comments")
def unknown_reasons(text, revert=()):
    d1.REVERT.clear(); d1.REVERT.update(revert)
    try: return d1.scan_text("t", text, ".yaml")[2]
    finally: d1.REVERT.clear()
for nm, body in (("N3a", '  value: "false"\n  "value": "true"\n'), ("N3b", '  value: "false"\n  "v\\x61lue": "true"\n'),
                 ("N3c", '  value: "false"\n  ? value\n  : "true"\n'), ("N3d", '  value: "false"\n  <<: {value: "true"}\n'),
                 ("N3e", '  <<: [{value: "false"}, {value: "true"}]\n')):
    # function level: the UNKNOWN reason must come from the structural pass (and, for N3d/N3e, from the syntax tripwire)
    report(f"{nm} duplicate value: UNKNOWN reason present", bool(unknown_reasons(op_file(body))))
    report(f"{nm} duplicate value  [revert structural+tricks]: no UNKNOWN reason any more", not unknown_reasons(op_file(body), {"structural", "tricks"}))

# alias bombs and size caps (availability): bounded, finish quickly, never GREEN by timing out
LOL = "a0: &a0 [" + ",".join(["lol"] * 9) + "]\n" + "".join(f"a{i}: &a{i} [" + ",".join([f"*a{i-1}"] * 9) + "]\n" for i in range(1, 10))
t0 = time.time()
rc, out = run(mk("n4a", {"platform-gitops/bomb.yaml": LOL + annos(f'    {A_KEY}: "false"\n')}))
report("N4a a billion-laughs document that also names a Reflector key finishes in under 10 s and is GREEN (flag false)", rc == 0 and time.time() - t0 < 10, f"rc={rc} {time.time() - t0:.1f}s")
t0 = time.time()
rc, out = run(mk("n4b", {"platform-gitops/bomb2.yaml": LOL + "z: *a9\n" + annos(f'    {A_KEY}: "true"\n')}))
report("N4b ... and RED when the key is enabled (the bomb does not hide it)", rc == 1 and time.time() - t0 < 10, f"rc={rc} {time.time() - t0:.1f}s")
with_caps("N4c document over the byte cap that names a Reflector key is UNKNOWN", 2, {"platform-gitops/big.yaml": "k: " + "x" * 3000 + "\n" + annos(f'    {A_KEY}: "false"\n')}, MAX_DOC_BYTES=1000)
with_caps("N4d more nodes than the cap is UNKNOWN", 2, {"platform-gitops/many.yaml": "l: [" + ",".join("1" * 1 for _ in range(300)) + "]\n" + annos(f'    {A_KEY}: "false"\n')}, MAX_NODES=100)
with_caps("N4e nesting deeper than the cap is UNKNOWN", 2, {"platform-gitops/deep.yaml": "d: " + "[" * 30 + "]" * 30 + "\n" + annos(f'    {A_KEY}: "false"\n')}, MAX_YAML_DEPTH=10)
with_caps("N4f ... and the same document within the caps is GREEN", 0, {"platform-gitops/deep.yaml": "d: " + "[" * 30 + "]" * 30 + "\n" + annos(f'    {A_KEY}: "false"\n')}, MAX_YAML_DEPTH=100)
DEEP = "d: " + "[" * 3000 + "]" * 3000 + "\n" + annos(f'    {A_KEY}: "true"\n')
rc, out = run(mk("n4g", {"platform-gitops/deeper.yaml": DEEP}))
report("N4g 3000-deep nesting plus an enabler does not crash and is not GREEN", rc != 0 and "Traceback" not in out, out[-200:])
WORKFLOW = ROOT / ".github" / "workflows" / "validate-manifests.yml"
if WORKFLOW.exists():
    steps = WORKFLOW.read_text().split("- name: Reflector source guard and detector proofs")[-1].split("\n      - name:")[0]
    report("N4h the workflow step wraps D1 and both proofs in `timeout 120` (a timeout fails the step)",
           steps.count("timeout 120 python3") == 3, steps[:400])
else:
    print("SKIP  N4h workflow file not present in this copy of the tree")

# regexes that match every namespace
for i, v in enumerate((".*|x", "(?s).*", "[a-z0-9-]*", ".{0,}", "database|.*", "(.*)|y", "[a-z0-9]*", "^.{0,63}$")):
    red2(f"N5-{i}", f"match-all namespace regex {v!r}", "platform-gitops/n5.yaml", kobj([f'{KEY}/{R}auto-namespaces: "{v}"']))
for v in ("tenant-a", "tenant-.*", "^tenant-[a-z]+$", "database", "a|b"):
    expect(f"N5g narrow namespace regex {v!r} is GREEN", mk("n5g", {"platform-gitops/n5.yaml": kobj([f'{KEY}/{R}auto-namespaces: "{v}"'])}), 0)
red2("N5h", "unreadable regex is never narrow", "platform-gitops/n5h.yaml", kobj([f'{KEY}/{R}auto-namespaces: "(unclosed"']))

# archive entry caps
def tar_with_links(n):
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as tf:
        for i in range(n):
            ti = tarfile.TarInfo(f"l{i}"); ti.type = tarfile.SYMTYPE; ti.linkname = "x"; tf.addfile(ti)
        c = b"a: b\n"; ti = tarfile.TarInfo("f.yaml"); ti.size = len(c); tf.addfile(ti, io.BytesIO(c))
    return bio.getvalue()
with_caps("N6a more non-regular tar members than the cap is UNKNOWN", 2, {"c.tgz": tar_with_links(8)}, MAX_MEMBERS=5)
with_caps("N6b a few symlink members plus a clean file are skipped and GREEN (non-regular members are not read)", 0, {"c.tgz": tar_with_links(2)}, MAX_MEMBERS=5)
with_caps("N6c exactly MAX_MEMBERS tar entries is GREEN", 0, {"c.tgz": tar_with_links(4)}, MAX_MEMBERS=5)
with_caps("N6d one entry over MAX_MEMBERS in a tar is UNKNOWN", 2, {"c.tgz": tar_with_links(5)}, MAX_MEMBERS=5)
real_zip = d1.zipfile.ZipFile
def boom(*a, **k): raise AssertionError("ZipFile opened a zip whose entry count is over the cap")
SIX = mk("n6f", {"c.zip": zip_bytes({f"f{i}.yaml": CLEAN for i in range(6)})})      # built before ZipFile is replaced
old = d1.MAX_MEMBERS; d1.MAX_MEMBERS = 3
d1.zipfile.ZipFile = boom
try:
    rc, out = run(SIX)
finally:
    d1.zipfile.ZipFile = real_zip; d1.MAX_MEMBERS = old
report("N6e zip entry count over the cap is refused from the end record, before zipfile reads the central directory", rc == 2 and "AssertionError" not in out, out[-300:])
report("N6f ... and the reason names the central directory, not a crash inside zipfile", "central directory announces" in out, out[-300:])
rc, out = run(mk("n6g", {"c.zip": zip_bytes({f"f{i}.yaml": CLEAN for i in range(20000)})}))
report("N6g exactly 20000 zip entries (the real cap) is GREEN", rc == 0, out[-200:])
rc, out = run(mk("n6h", {"c.zip": zip_bytes({f"f{i}.yaml": CLEAN for i in range(20001)})}))
report("N6h 20001 zip entries is UNKNOWN", rc == 2, out[-200:])
report("N6i the cap constants are the documented ones (a +-1 change is a decision, not an accident)",
       (d1.MAX_DEPTH, d1.MAX_MEMBERS, d1.MAX_MEMBER_BYTES, d1.MAX_TOTAL_BYTES, d1.MAX_DOC_BYTES, d1.MAX_NODES, d1.MAX_YAML_DEPTH)
       == (2, 20000, 16 * 1024 * 1024, 64 * 1024 * 1024, 1024 * 1024, 100000, 100))

# BOM + list item (reviewer id 17: not equivalent)
red2("X22", "UTF-8 BOM before `- path:` of a JSON-patch op (the BOM must not hide the op)", "k/patch.yaml",
     b"\xef\xbb\xbf- op: add\n  path: " + PATHK.encode() + b"\n  value: \"true\"\n")
expect("X22b BOM + `- path:` with value false is GREEN", mk("x22b", {"k/patch.yaml": b"\xef\xbb\xbf- op: add\n  path: " + PATHK.encode() + b"\n  value: \"false\"\n"}), 0)
# non-YAML text with tricks: unparseable document mentioning a key plus an alias is UNKNOWN, never GREEN
red2("N9a", "unparseable template with an alias key and a Reflector key: UNKNOWN", "helm/t.yaml",
     "{{- if .Values.x }}\n" + f'a: &k {A_KEY}\n' + "*k : \"true\"\n", rc=2)
expect("N9b unparseable template that merely mentions a Reflector key literally (false) is GREEN", mk("n9b", {"helm/t.yaml": "x: {{ .Values.x }}\n" + f'{A_KEY}: "false"\n'}), 0)
expect("N9c the repo's own `*` and `#` in comments and quoted strings are not tricks", mk("n9c", {"helm/t.yaml": "# */* and &x\nq: \"*\"\nx: {{ .Values.x }}\n" + f'{A_KEY}: "false"\n'}), 0)


# ---------------------------------------------------------------- round 2b: boundaries, line numbers and helpers found by the matrix
print("== round 2b: exact boundaries, reported line numbers, comment stripping, output truncation ==")
def out_of(files, name, revert=()):
    rc, out = run(mk(name, files), revert)
    return rc, out
# reported line numbers (a RED finding must point at the line that spells the key)
LN_DOC = "# c1\nx: y\n---\n" + HEADER + "  annotations:\n" + f'    {A_KEY}: "true"\n'
rc, out = out_of({"platform-gitops/ln1.yaml": LN_DOC}, "ln1")
report("LN1 line scan: RED finding in the second document cites the exact file line (10)", rc == 1 and "ln1.yaml:10:" in out, out[-300:])
LN_HID = "# c1\nx: y\n---\n" + HEADER + "  annotations:\n" + f'    ? "{SPLIT3}"\n    : "true"\n'
rc, out = out_of({"platform-gitops/ln2.yaml": LN_HID}, "ln2")
report("LN2 structural: a multi-line explicit key is cited at the line where it starts (10)", rc == 1 and "ln2.yaml:10:" in out, out[-300:])
LN_OP = "# c1\n" + "- op: add\n  path: " + PATHK + "   # value: false\n  value: \"true\"\n"
rc, out = out_of({"k/ln3.yaml": LN_OP}, "ln3")
report("LN3 JSON-patch op: both layers cite the path line (3)", rc == 1 and out.count("ln3.yaml:3:") >= 2, out[-300:])
LN_PATCH = "patches:\n  - target: {kind: Secret}\n    patch: |-\n      - op: add\n        path: " + PATHK + "\n        value: \"false\"\n        value: \"true\"\n"
rc, out = out_of({"k/kustomization.yaml": LN_PATCH}, "ln4")
report("LN4 a duplicate `value` inside a block-scalar patch is cited at its own file line (7)", rc == 2 and "kustomization.yaml: line 7:" in out, out[-300:])
LN_FLOWPATCH = "patches:\n  - target: {kind: Secret}\n    patch: '[{\"op\":\"add\",\"path\":\"" + PATHK + "\",\"value\":\"false\",\"value\":\"true\"}]'\n"
rc, out = out_of({"k/kustomization.yaml": LN_FLOWPATCH}, "ln5")
report("LN5 a duplicate `value` inside a single-line JSON patch string is cited at its own line (3) and is UNKNOWN", rc == 2 and "kustomization.yaml: line 3:" in out, out[-300:])
rc, out = out_of({"k/kustomization.yaml": LN_FLOWPATCH.replace("patch: '[", "patch: '   [")}, "ln6")
report("LN6 leading blanks before the JSON in a patch string do not hide it", rc == 2, out[-300:])
rc, out = out_of({"k/kustomization.yaml": "patches:\n  - target: {kind: Secret}\n    patch: '{\"op\":\"add\",\"path\":\"" + PATHK + "\",\"value\":\"false\",\"value\":\"true\"}'\n"}, "ln7")
report("LN7 a single JSON object (not a list) in a patch string is read too", rc == 2, out[-300:])
rc, out = out_of({"k/kustomization.yaml": "patches:\n  - target: {kind: Secret}\n    patch: |\n      op: add\n      path: " + PATHK + "\n      value: \"false\"\n      value: \"true\"\n"}, "ln8")
report("LN8 a multi-line mapping string (no leading dash or bracket) is read too", rc == 2, out[-300:])
expect("LN9 a plain string that merely mentions a key and `false` is not re-parsed as a mapping (GREEN)", mk("ln9", {"platform-gitops/ln9.yaml":
       "args:\n  - echo " + A_KEY + ": false\n"}), 0)

# two keys on one line: each value is read from its own span
TWO = lambda a, b: "[{op: add, path: /m/a/" + KEY + "~1" + R + "allowed, value: " + a + "}, {op: add, path: /m/a/" + KEY + "~1" + R + "auto-enabled, value: " + b + "}]\n"
rc, out = out_of({"k/p.yaml": TWO('"false"', '"false"')}, "ln10")
report("LN10 two ops on one flow line, both false: the line scan cannot bind the values and stays RED (fail-closed), one finding per op", rc == 1 and "findings=2" in out, out[-300:])
expect("LN11 two ops on one line, second true: RED", mk("ln11", {"k/p.yaml": TWO('"false"', '"true"')}), 1)
expect("LN12 two ops on one line, first true: RED", mk("ln12", {"k/p.yaml": TWO('"true"', '"false"')}), 1)

# strip_comment, directly
for i, (src, want) in enumerate([('a: "x # y" # z', 'a: "x # y" '), ("a: 'it''s' #c", "a: 'it''s' "), ('a: "q\\" # not"  # c', 'a: "q\\" # not"  '),
                                 ("x#y", "x#y"), ("# whole", ""), ("a:\t# tab", "a:\t"), ("k: it's # c", "k: it's "), ("a: [b, #c", "a: [b, "),
                                 ("a: 'x # y'", "a: 'x # y'"), ('a: "x\\\\" # c', 'a: "x\\\\" '), ("a: 'x' # y 'z' # w", "a: 'x' "), ('- "a#b" #c', '- "a#b" '),
                                 ("a: b#c", "a: b#c"), ("{a: 'x', #c", "{a: 'x', "), ('k: "a" "b" # c', 'k: "a" "b" ')]):
    got = d1.strip_comment(src)
    report(f"SC{i} strip_comment({src!r})", got == want, repr(got))

# exact structural caps (pinned: a change of the comparison or of the counting is a decision, not an accident)
CAPDOC = annos(f'    {A_KEY}: "false"\n')
def caps_rc(name, doc, **caps):
    old = {k: getattr(d1, k) for k in caps}
    try:
        for k, v in caps.items(): setattr(d1, k, v)
        return run(mk(name, {"platform-gitops/c.yaml": doc}))[0]
    finally:
        for k, v in old.items(): setattr(d1, k, v)
n_doc = len(CAPDOC)
def cap_unreadable(cap):
    old = d1.MAX_DOC_BYTES
    try:
        d1.MAX_DOC_BYTES = cap
        return d1.scan_text("x.yaml", CAPDOC, ".yaml")[2]
    finally:
        d1.MAX_DOC_BYTES = old
report("CAP1 a document of exactly MAX_DOC_BYTES is parsed", cap_unreadable(len(CAPDOC)) == [])
report("CAP2 a document one byte over MAX_DOC_BYTES is UNKNOWN (not parsed)", len(cap_unreadable(len(CAPDOC) - 1)) == 1)
# the walk visits root, `metadata`, `annotations`, and the scalar values: pinned by probing the unmutated count once, then asserting both sides
nodes_needed = next(n for n in range(1, 50) if caps_rc("capn%d" % n, CAPDOC, MAX_NODES=n) == 0)
report(f"CAP3 MAX_NODES: the smallest cap that lets this document through is {nodes_needed} (pinned to 25)", nodes_needed == 25, str(nodes_needed))
depth_needed = next(n for n in range(0, 20) if caps_rc("capd%d" % n, CAPDOC, MAX_YAML_DEPTH=n) == 0)
report(f"CAP4 MAX_YAML_DEPTH: the smallest cap that lets this document through is {depth_needed} (pinned to 6)", depth_needed == 6, str(depth_needed))
def nest(levels):
    """A kustomization whose patch string holds a JSON string that holds ... a duplicate-value op."""
    import json
    inner = json.dumps([{"op": "add", "path": PATHK, "value": "false", "value ": "x"}])
    inner = inner.replace('"value "', '"value"')
    for _ in range(levels):
        inner = json.dumps({"patch": inner})
    return "patch: " + json.dumps(inner) + "\n"
res = {n: run(mk("nest%d" % n, {"k/n.yaml": nest(n)}))[0] for n in range(0, 6)}
report("CAP5 nested JSON strings are read down to level 3 and deeper ones are UNKNOWN (never GREEN)", all(v != 0 for v in res.values()) and res[5] == 2, str(res))
rc, out = run(mk("nest_msg", {"k/n.yaml": nest(5)}))
report("CAP6 the too-deep reason says so", "nested more than 3 levels" in out, out[-300:])
# regex length and probe boundaries
rc200 = run(mk("rx200", {"platform-gitops/n.yaml": kobj([f'{KEY}/{R}auto-namespaces: "' + "a" * 200 + '"'])}))[0]
rc201 = run(mk("rx201", {"platform-gitops/n.yaml": kobj([f'{KEY}/{R}auto-namespaces: "' + "a" * 201 + '"'])}))[0]
report("RX1 a 200-character narrow regex is GREEN, a 201-character one is refused (RED)", rc200 == 0 and rc201 == 1, f"{rc200} {rc201}")
for v, want in (("[a-d].*", 0), ("[a-z]*", 0), ("[a-z0-9]*", 1), ("k.*|a.*|d.*", 0)):
    rc = run(mk("rxb", {"platform-gitops/n.yaml": kobj([f'{KEY}/{R}auto-namespaces: "{v}"'])}))[0]
    report(f"RX2 probe boundary: {v!r} matches {sum(1 for p in d1.PROBES if __import__('re').fullmatch(v, p))} of 7 probes -> rc {want}", rc == want, str(rc))
# output truncation
many = {f"platform-gitops/r{i:02d}.yaml": kobj([f'{KEY}/{R}allowed: "true"']) for i in range(30)}
rc, out = out_of(many, "tr_red")
report("TR1 RED lists at most 25 findings and counts all", rc == 1 and sum(1 for l in out.splitlines() if l.strip().startswith("platform-gitops/r")) == 25 and "findings=30" in out, out[-200:])
bad_many = {f"x/u{i:02d}.dat": b"\0" for i in range(12)}
rc, out = out_of(bad_many, "tr_unk")
report("TR2 UNKNOWN lists at most 10 reasons", rc == 2 and sum(1 for l in out.splitlines() if l.strip().startswith("NUL byte")) == 10, out[-200:])
arch = {f"a/c{i:02d}.tgz": tar_bytes({"x.yaml": CLEAN}) for i in range(22)}
rc, out = out_of(arch, "tr_arch")
report("TR3 COVERAGE lists at most 20 archives and counts all", rc == 0 and "scanned: 22" in out and out.count(".tgz (1 members)") == 20, out[-300:])
dl = mk("tr_links"); (dl / "real").mkdir()
for i in range(22): os.symlink(dl / "real", dl / f"ln{i:02d}")
rc, out = run(dl)
report("TR4 COVERAGE lists at most 20 directory symlinks and counts all", rc == 0 and "symlinks: 22 with" in out and sum(1 for i in range(22) if f"ln{i:02d}" in out) == 20, out[-300:])
notes = {f"helm/t{i:02d}.yaml": "{{- if .Values.x }}\n" + f'{A_KEY}: "false"\n' for i in range(12)}
rc, out = out_of(notes, "tr_notes")
report("TR5 COVERAGE counts unparsed documents and lists at most 10", rc == 0 and "not parse as YAML (line scan + syntax tripwire only): 12" in out and out.count("helm/t") == 10, out[-300:])
SECRET_ENABLER = lambda kind, ns: f"kind: {kind}\nmetadata:\n  name: mctl-platform-config\n  namespace: {ns}\n  annotations:\n    {KEY}/{R}allowed: \"true\"\n"
rc, out = out_of({"x/s.yaml": SECRET_ENABLER("Secret", "argo-workflows")}, "tr_msg")
report("TR6 a RED finding on a Secret that is named like the allow-listed source says a Secret must never be one", rc == 1 and "Secret must never be a reflector source" in out, out[-300:])
rc, out = out_of({"x/s.yaml": SECRET_ENABLER("ConfigMap", "other")}, "tr_msg2")
report("TR7 ...and a RED finding on another kind does not claim it", rc == 1 and "Secret must never" not in out, out[-300:])
# the BOM is stripped exactly (3 bytes) before decoding
rc, out = out_of({"x/bom.yaml": b"\xef\xbb\xbf" + b"a: b\n"}, "bom3")
report("BOM1 a UTF-8 BOM before ordinary text decodes cleanly (GREEN; the BOM is exactly 3 bytes)", rc == 0, out[-200:])
# archives
class FakeMember: pass
rc, out = out_of({"c/z.tgz": tar_bytes({"a.yaml": CLEAN, "dir/b.yaml": CLEAN})}, "tgz2")
report("ARC1 tar members counted in COVERAGE", "(2 members)" in out, out[-300:])
zdir = io.BytesIO()
with zipfile.ZipFile(zdir, "w") as zf:
    zf.writestr("d/", ""); zf.writestr("d/a.yaml", CLEAN)
rc, out = out_of({"c/d.zip": zdir.getvalue()}, "zipdir")
report("ARC2 zip directory entries are skipped, files counted (1 member)", rc == 0 and "(1 members)" in out, out[-300:])
rc, out = out_of({"c/g.gz": gzip.compress(b"a: b\n")}, "gz1")
report("ARC3 a bare .gz is read under the name without its suffix", rc == 0 and "(1 members)" in out, out[-300:])
rc, out = out_of({"c/.gz": gzip.compress(b"a: b\n")}, "gz2")
report("ARC4 a .gz whose name is only the suffix still opens", rc == 0, out[-300:])
rc, out = out_of({"c/u.yaml": b"\xff\xfe" + "a: b\n".encode("utf-16-le")}, "u16")
report("ARC5 UTF-16 with BOM decodes and is GREEN", rc == 0, out[-200:])
rc, out = out_of({"c/u32.yaml": b"\xff\xfe\x00\x00" + "a: b\n".encode("utf-32-le")}, "u32")
report("ARC6 UTF-32 with BOM decodes and is GREEN", rc == 0, out[-200:])

# ---------------------------------------------------------------- round 3: N9 (reviewer) per-line and per-file work caps
print("== round 3 N9: a hostile single line or a flood of findings is bounded and UNKNOWN, never a hang or GREEN ==")
import time as _t
FULLKEY = KEY + "/"
def timed(name, files, revert=()):
    t0 = _t.time(); rc, out = run(mk(name, files), revert); return rc, out, _t.time() - t0
rc, out, dt = timed("n9a", {"platform-gitops/n9a.yaml": "a: " + KEY * 20000 + "\n"})
report("N9a one line repeating the key 20000 times, no separator: UNKNOWN (rc 2), not GREEN, in under 5 s", rc == 2 and dt < 5, f"rc={rc} {dt:.1f}s")
rc, out, dt = timed("n9b", {"platform-gitops/n9b.yaml": "a: " + KEY * 200000 + "\n"})
report("N9b the same at 200000 repeats (6 MB line): UNKNOWN in under 10 s", rc == 2 and dt < 10, f"rc={rc} {dt:.1f}s")
rc, out, dt = timed("n9c", {"platform-gitops/n9c.yaml": "a: " + KEY * 200 + "\n"})
report("N9c exactly MAX_LINE_KEYS (200) repeats are still read (RED findings, not the cap)", rc == 1 and "not read" not in out, out[-200:])
rc, out, dt = timed("n9d", {"platform-gitops/n9d.yaml": "a: " + KEY * 201 + "\n"})
report("N9d 201 repeats hit the cap: UNKNOWN", rc == 2 and "not read" in out, out[-200:])
rc, out, dt = timed("n9e", {"platform-gitops/n9e.yaml": "a: " + "x" * 70000 + KEY + "/x\n"})
report("N9e a line over MAX_LINE_BYTES that mentions a key: UNKNOWN", rc == 2, out[-200:])
rc, out, dt = timed("n9f", {"platform-gitops/n9f.yaml": "\n".join(f"a{i}: {KEY}/x" for i in range(200000)) + "\n"})
report("N9f 200000 key lines in one document: UNKNOWN in under 10 s (per-document line cap)", rc == 2 and dt < 10, f"rc={rc} {dt:.1f}s")
rc, out, dt = timed("n9g", {"platform-gitops/n9g.yaml": "x: y\n" * 30000 + KEY + "/x: 1\n"})
report("N9g a document over MAX_DOC_LINES that mentions a key: UNKNOWN", rc == 2 and dt < 10, f"rc={rc} {dt:.1f}s")
rc, out, dt = timed("n9h", {"platform-gitops/n9h.yaml": "\n---\n".join(f"a: {KEY}/{R}allowed: true" for i in range(1200))})
report("N9h more than MAX_FINDINGS_PER_FILE findings in one file: UNKNOWN reason present, list truncated", rc == 2 and "findings in one file" in out, out[-300:])
for rule, f in (("line_cap", "n9a"),):
    rc, out = run(mk("n9r", {"platform-gitops/n9r.yaml": "a: " + KEY * 300 + "\n"}), {rule})
    report("N9i reverting the line cap changes the verdict (RED findings instead of UNKNOWN)", rc == 1, f"rc={rc}")
rc, out = run(mk("n9s", {"platform-gitops/n9s.yaml": "\n---\n".join(f"a: {KEY}/{R}allowed: true" for i in range(1200))}), {"finding_cap"})
report("N9j reverting the finding cap removes the truncation reason", "findings in one file" not in out, out[-200:])
# the workflow wrapper: a timeout must FAIL the step (timeout exits 124, non-zero)
wf = (ROOT / ".github" / "workflows" / "validate-manifests.yml")
if wf.exists():
    txt = wf.read_text()
    report("N9k every detector command in the workflow runs under `timeout 120` (exit 124 fails the step)", txt.count("timeout 120 python3") >= 3, "")
    report("N9l the step is not continue-on-error", "continue-on-error" not in txt.split("Reflector source guard")[1].split("\n  - name:")[0] if "Reflector source guard" in txt else False, "")
    # Behavioural proof, not a grep: the step's own shell options + a real slow command. `timeout` must exit 124 and `set -e` must stop the step.
    import shutil as _sh
    if _sh.which("timeout"):
        t0 = time.time()
        r = subprocess.run(["bash", "-c", "set -euo pipefail; timeout 1 python3 -c 'import time; time.sleep(30)'; echo REACHED"],
                           capture_output=True, text=True, timeout=20)
        report("N9m a command that outlives `timeout` exits 124 and the step (set -euo pipefail) stops before the next line",
               r.returncode == 124 and "REACHED" not in r.stdout and time.time() - t0 < 10, f"rc={r.returncode} out={r.stdout!r}")
    else:
        report("N9m a command that outlives `timeout` exits 124 and the step stops (needs a `timeout` binary: absent = cannot prove)", False, "no `timeout` on PATH")

# ---------------------------------------------------------------- round 4: N10 tagged scalars (!!binary and other tags)
print("== round 4 N10: tags that change the resolved scalar ==")
import base64 as _b64
B64 = lambda text: _b64.b64encode(text.encode()).decode()
AK = KEY + "/" + R + "allowed"
red2("N10a", "explicit key written as !!binary base64, value true", "platform-gitops/n10a.yaml",
     annos(f'    ? !!binary {B64(AK)}\n    : "true"\n'))
red2("N10b", "same with the full tag URI", "platform-gitops/n10b.yaml",
     annos(f'    ? !<tag:yaml.org,2002:binary> {B64(AK)}\n    : "true"\n'))
red2("N10c", "base64 split over lines in a block scalar", "platform-gitops/n10c.yaml",
     annos(f'    ? !!binary |\n      {B64(AK)[:20]}\n      {B64(AK)[20:]}\n    : "true"\n'))
expect("N10d the same !!binary key with a provably false value resolves to GREEN", mk("n10d", {"platform-gitops/n10d.yaml":
       annos(f'    ? !!binary {B64(AK)}\n    : "false"\n')}), 0)
red2("N10e", "!!binary key that is not valid base64 in a document that mentions the family: UNKNOWN", "platform-gitops/n10e.yaml",
     annos('    ? !!binary "@@@"\n    : "true"\n') + f"x: {KEY}\n", rc=2)
red2("N10f", "!!binary VALUE (the bytes are not a boolean): never provably false", "platform-gitops/n10f.yaml",
     annos(f'    {AK}: !!binary {B64("false")}\n'))
red2("N10g", "!!binary as a JSON-patch path", "k/n10g.yaml",
     "- op: add\n  path: !!binary " + B64(PATHK) + "\n  value: \"true\"\n")
red2("N10h", "!!binary key in an unparseable (templated) document: tripwire UNKNOWN", "helm/n10h.yaml",
     "{{- if .Values.x }}\nmetadata:\n  annotations:\n    ? !!binary " + B64(AK) + "\n    : \"true\"\n" + f"# {KEY}\n", rc=2)
red2("N10i", "custom tag on a value: the constructor may rewrite it, so UNKNOWN", "platform-gitops/n10i.yaml",
     annos(f'    {AK}: !custom "false"\n'), rc=2)
red2("N10j", "custom tag on a mapping holding the key: UNKNOWN", "platform-gitops/n10j.yaml",
     annos(f'    ? {AK}\n    : !local\n        a: b\n'), rc=2)
red2("N10k", "!!str on a value that is not provably false stays RED (text judged as written)", "platform-gitops/n10k.yaml",
     annos(f'    {AK}: !!str "true"\n'))
red2("N10l", "a standard tag on a false value is not trusted: the line scan cannot read it, so RED (conservative)", "platform-gitops/n10l.yaml",
     annos(f'    {AK}: !!str "false"\n'))
not_detected("N10a !!binary key", RED_R2["N10a"], 1, "structural")
rc, out = run(RED_R2["N10a"])
report("N10n the finding names the decoded key", rc == 1 and (R + "allowed") in out, out[-300:])
def func_unknown(text): return d1.scan_text("x.yaml", text, ".yaml")[2]
CUSTOM_TAG_DOC = annos(f'    {AK}: !custom "false"\n')
d1.REVERT.add("tags")
try: no_tag_reason = func_unknown(CUSTOM_TAG_DOC)
finally: d1.REVERT.discard("tags")
report("N10o a custom tag is UNKNOWN, and reverting the `tags` rule removes that reason", func_unknown(CUSTOM_TAG_DOC) != [] and no_tag_reason == [], "")

# ---------------------------------------------------------------- round 4: tests for the survivors of the full mutation matrix
print("== round 4: survivors of the full mutation matrix (boundaries, parsing paths, CLI) ==")
def one_doc(text, ext=".yaml"): return d1.scan_text("x" + ext, text, ext)
def capped(name, **kw):
    old = {k: getattr(d1, k) for k in kw}
    try:
        for k, v in kw.items(): setattr(d1, k, v)
        return one_doc(name)
    finally:
        for k, v in old.items(): setattr(d1, k, v)
# ---- exact cap boundaries (the constants themselves are part of the contract)
line_ok = "a: " + KEY + "/" + R + "allowed" + " " * 0
def pad_line(total):
    base = "a: \"" + KEY + "/" + R + "allowed\" # "
    return base + "x" * (total - len(base))
res = one_doc(pad_line(d1.MAX_LINE_BYTES) + "\n")
report("B1 a key-mentioning line of exactly MAX_LINE_BYTES is read (a finding, no 'not read')", len(res[0]) == 1 and res[2] == [], str(res)[:200])
res = one_doc(pad_line(d1.MAX_LINE_BYTES + 1) + "\n")
report("B2 one byte longer is UNKNOWN", len(res[2]) == 1 and "not read" in res[2][0], str(res)[:200])
report("B2b MAX_LINE_BYTES is 65536 (pinned)", d1.MAX_LINE_BYTES == 65536)
rows = lambda n: "".join(f"k{i}: {KEY}/{R}allowed\n" for i in range(n))
res = one_doc(rows(d1.MAX_KEY_LINES))
report("B3 exactly MAX_KEY_LINES key lines are read", res[2] == [] and len(res[0]) == d1.MAX_KEY_LINES, str(res[2])[:200])
res = one_doc(rows(d1.MAX_KEY_LINES + 1))
report("B4 one more key line is UNKNOWN", len(res[2]) == 1 and "not read" in res[2][0], str(res[2])[:200])
report("B4b MAX_KEY_LINES is 200 (pinned)", d1.MAX_KEY_LINES == 200)
plain = lambda n: "x: y\n" * 0 + "".join(f"p{i}: v\n" for i in range(n))
res = one_doc("a: " + KEY + "/" + R + "allowed\n" + plain(d1.MAX_DOC_LINES - 2))
report("B5 a document of exactly MAX_DOC_LINES lines that mentions a key is read", res[2] == [] and len(res[0]) == 1, str(res[2])[:200])
res = one_doc("a: " + KEY + "/" + R + "allowed\n" + plain(d1.MAX_DOC_LINES - 1))
report("B6 one more line is UNKNOWN", len(res[2]) == 1 and "not read" in res[2][0], str(res[2])[:200])
report("B6b MAX_DOC_LINES is 20000 (pinned)", d1.MAX_DOC_LINES == 20000)
res = one_doc(plain(5000) + "a: " + KEY + "/" + R + "allowed\n")
report("B7 many plain lines and one key line: read (the line count is of MENTIONING lines)", res[2] == [] and len(res[0]) == 1, str(res[2])[:200])
res = one_doc("".join(f"k{i}: {KEY.upper()}\n" for i in range(d1.MAX_KEY_LINES + 1)))
report("B8 upper-case spellings count as mentions", len(res[2]) == 1, str(res[2])[:200])
res = one_doc("".join(f"k{i}: reflection-x\n" for i in range(d1.MAX_KEY_LINES + 1)))
report("B9 lines that only say `reflect` count as mentions", len(res[2]) == 1, str(res[2])[:200])
def n_reasons(n): return one_doc(f"# {KEY}\n" + "x: y\n" * (n + 1))[2]
report("B10 exactly 100 UNKNOWN reasons are all kept", len(n_reasons(100)) == 100 and "further" not in "".join(n_reasons(100)), str(len(n_reasons(100))))
r101 = n_reasons(101)
report("B11 101 reasons: truncated to 100 plus one 'further' entry", len(r101) == 101 and "1 further reasons not listed" in r101[-1], str(r101[-1:]))
r150 = n_reasons(150)
report("B12 150 reasons: 100 kept and '50 further' reported", len(r150) == 101 and "50 further reasons not listed" in r150[-1], str(r150[-1:]))
def n_findings(n): return one_doc("\n---\n".join(f"a: {KEY}/{R}allowed" for _ in range(n)))
f1000, f1001 = n_findings(1000), n_findings(1001)
report("B13 exactly MAX_FINDINGS_PER_FILE findings are all kept, no cap reason", len(f1000[0]) == 1000 and not any("findings in one file" in r for r in f1000[2]), str(f1000[2])[:200])
report("B14 one more finding: truncated to 1000 with the cap reason", len(f1001[0]) == 1000 and any("findings in one file" in r for r in f1001[2]), str(f1001[2])[:200])
# nodes: the walk counts every visit of an aliased scalar, the prepass counts unique nodes
ALIASY = f"a: &x v\\nk: {KEY}/{R}allowed\\nl: [" .replace("\\n", "\n") + ", ".join(["*x"] * 20) + "]\n"
need = next(n for n in range(1, 200) if (lambda o: (setattr(d1, "MAX_NODES", n), one_doc(ALIASY)[2] == [] )[1])(None))
d1.MAX_NODES = 100000
report(f"B15 MAX_NODES counts every walked visit: smallest passing cap for an alias fan-out is {need} (pinned to 24)", need == 24, str(need))
d1.MAX_NODES = 100000
SEQ = "a: " + "[" * 5 + "1" + "]" * 5 + f"\nk: {KEY}/{R}allowed\n"
dn = next(n for n in range(0, 30) if (lambda o: (setattr(d1, "MAX_YAML_DEPTH", n), one_doc(SEQ)[2] == [])[1])(None))
d1.MAX_YAML_DEPTH = 100
report(f"B16 YAML depth through nested sequences: smallest passing cap {dn} (pinned to 6)", dn == 6, str(dn))
CK = "? " + "[" * 4 + "a" + "]" * 4 + f"\n: v\nk: {KEY}/{R}allowed\n"
dc = next(n for n in range(0, 30) if (lambda o: (setattr(d1, "MAX_YAML_DEPTH", n), one_doc(CK)[2] == [])[1])(None))
d1.MAX_YAML_DEPTH = 100
report(f"B17 YAML depth through a complex key: smallest passing cap {dc} (pinned to 5)", dc == 5, str(dc))
# nested strings: exact level and exact size
def nested_levels(n):
    s = f"{KEY}/{R}allowed: false"
    for _ in range(n): s = "k: |\n" + "".join("  " + l + "\n" for l in s.splitlines())
    return "v: |\n" + "".join("  " + l + "\n" for l in s.splitlines())
lv = {n: one_doc(nested_levels(n)) for n in range(0, 7)}
first_cap = min((n for n, r in lv.items() if any("nested more than 3 levels" in x for x in r[2])), default=None)
report(f"B18 nested strings: the depth reason first appears at nesting {first_cap} (pinned to 4)", first_cap == 4, str({n: len(r[2]) for n, r in lv.items()}))
# (109: `len(n.value) <= MAX_DOC_BYTES` cannot be tested at its boundary: a nested string is always strictly shorter than the
# outer document that already passed the same cap)
# ---- BOM and encodings
rc, out = run(mk("bomkey", {"platform-gitops/bomkey.yaml": b"\xef\xbb\xbf" + (KEY + "/" + R + "allowed: \"true\"\n").encode()}))
report("B21 a key at the very start of a BOM file is read (the BOM is exactly 3 bytes)", rc == 1, out[-200:])
rc, out = run(mk("u32be", {"c/u32be.yaml": b"\x00\x00\xfe\xff" + "a: b\n".encode("utf-32-be")}))
report("B22 UTF-32 big-endian BOM decodes (GREEN), it is not mistaken for a NUL file", rc == 0, out[-300:])
# ---- archive naming
rc, out = run(mk("upper_tgz", {"c/A.TGZ": tar_bytes({"p.yaml": kobj([f'{KEY}/{R}allowed: "true"'])})}))
report("B23 an upper-case archive name is still opened (RED on its member)", rc == 1, out[-300:])
rc, out = run(mk("yaml_gz", {"c/hid.yaml.gz": gzip.compress(annos(f'    ? "{SPLIT3}"\n    : "true"\n').encode())}))
report("B24 a .yaml.gz member keeps its .yaml extension, so the structural pass reads it (RED)", rc == 1 and "hid.yaml" in out, out[-300:])
# ---- unq, enabling and regex details
report("B25 unq strips outer blanks then quotes then blanks", d1.unq('  "false" ') == "false" and d1.unq("'x'") == "x" and d1.unq("false") == "false")
report("B26 unq leaves a single quote character alone", d1.unq('"') == '"')
report("B27 broad_regex: a blank after a comma is trimmed (`database, .*` is match-all)", d1.broad_regex("database, .*") is True)
report("B28 broad_regex: parentheses are peeled one character at a time (`(.*x)` is narrow)", d1.broad_regex("(.*x)") is False)
rc, out = run(mk("rxcomma", {"platform-gitops/rxc.yaml": kobj([f'{KEY}/{R}auto-namespaces: "database, .*"'])}))
report("B29 `database, .*` in a manifest is RED", rc == 1, out[-200:])
# ---- strip_comment: a quote that opens at column 0
report("B30 strip_comment: a quote at column 0 opens a string", d1.strip_comment('"a # b" # c') == '"a # b" ', d1.strip_comment('"a # b" # c'))
# ---- mentions(): case-insensitive on purpose
rc, out = run(mk("upmention", {"platform-gitops/up.yaml": "# EMBERSTACK\nx: 1\nx: 2\n"}))
report("B31 an upper-case mention still sends the document through the structural pass (duplicate key: UNKNOWN)", rc == 2, out[-200:])
# ---- JSON-patch block scoping
OPS = lambda body: "- op: add\n  path: /spec/x\n  value: \"true\"\n" + body
rc, out = run(mk("bs1", {"k/bs1.yaml": OPS(f"- op: add\n  path: {PATHK}\n  value: \"false\"\n")}))
report("B32 the line before the path line is the previous item's dash: the block starts there, not one line earlier", rc == 0, out[-300:])
rc, out = run(mk("bs2", {"k/bs2.yaml": f"- op: add\n  value: \"false\"\n\n  path: {PATHK}\n"}))
report("B33 a blank line between value and path does not end the block", rc == 0, out[-300:])
rc, out = run(mk("bs3", {"k/bs3.yaml": f"- op: add\n  value: \"false\"\n \n  path: {PATHK}\n"}))
report("B34 a one-space blank line is skipped too", rc == 0, out[-300:])
rc, out = run(mk("bs4", {"k/bs4.yaml": f"other:\n  value: \"true\"\npatch:\n  path: {PATHK}\n  value: \"false\"\n"}))
report("B35 a mapping parent starts the block on the line AFTER it", rc == 0, out[-300:])
rc, out = run(mk("bs5", {"k/bs5.yaml": f"patch:\n  value: \"false\"\n  path: {PATHK}\n"}))
report("B36 the first line after the parent is inside the block", rc == 0, out[-300:])
rc, out = run(mk("bs6", {"k/bs6.yaml": f"patches:\n  - value: \"false\"\n    path: {PATHK}\n"}))
report("B37 an indented list-item parent that carries `value` belongs to the block", rc == 0, out[-300:])
rc, out = run(mk("bs7", {"k/bs7.yaml": f"- op: add\n  path: {PATHK}\n \n  value: \"false\"\n"}))
report("B38 a one-space blank line after the path line does not end the block", rc == 0, out[-300:])
# ---- two keys on one line
rc, out = run(mk("two1", {"x/two.sh": f"kubectl annotate secret s {KEY}/{R}allowed=false {KEY}/{R}auto-enabled=false\n"}))
report("B39 two annotate keys on one line, both false: GREEN (each value is read from its own span)", rc == 0, out[-300:])
rc, out = run(mk("two2", {"x/two.sh": f"kubectl annotate secret s {KEY}/{R}allowed=false {KEY}/{R}auto-enabled=true\n"}))
report("B40 ...second true: RED", rc == 1, out[-300:])
# ---- structural paths
rc, out = run(mk("mk1", {"platform-gitops/mk1.yaml": annos(f'    <<: 5\n    {KEY}/{R}allowed: "false"\n')}))
report("B41 a merge key whose value is not a mapping is UNKNOWN (not a crash)", rc == 2 and "not a mapping" in out, out[-300:])
rc, out = run(mk("ck1", {"platform-gitops/ck1.yaml": annos(f'    ? [a, b]\n    : c\n    {KEY}/{R}allowed: "false"\n')}))
report("B42 a complex (sequence) key beside a key is walked, no crash", rc in (0, 2), out[-200:])
rc, out = run(mk("hid_bin_val", {"platform-gitops/hbv.yaml": annos(f'    ? "{SPLIT3}"\\n    : !!binary {B64("false")}\\n'.replace("\\n", "\n"))}))
report("B43 a hidden key with a !!binary value is never provably false (not GREEN)", rc != 0, out[-300:])
rc, out = run(mk("unp_key", {"platform-gitops/uk1.yaml": annos(f'    ? "x{SPLIT3}"\n    : "false"\n')}))
report("B44 a hidden key with a leading character is an unparsed-key finding", rc == 1 and "unparsed key" in out, out[-300:])
rc, out = run(mk("unp_key2", {"platform-gitops/uk2.yaml": annos(f'    ? "{SPLIT3}/x"\n    : "false"\n')}))
report("B45 a hidden key with trailing text is an unparsed-key finding", rc == 1 and "unparsed key" in out, out[-300:])
rc, out = run(mk("unp_key3", {"platform-gitops/uk3.yaml": annos(f'    ? "{SPLIT3}{SPLIT3}"\n    : "false"\n')}))
report("B46 a hidden key holding the prefix twice is an unparsed-key finding", rc == 1 and "unparsed key" in out, out[-300:])
rc, out = run(mk("unp_path", {"k/up.yaml": f"- op: add\n  path: /metadata/annotations/{KEY}/-x\n  value: \"false\"\n"}))
report("B47 an op path whose prefix has no readable suffix is an unparsed-path finding", rc == 1 and "unparsed path" in out, out[-300:])
# the allow-listed document: any re-spelling or reuse of its keys makes it non-own
ANCH = base_files()[ANCHOR]
rc, out = run(mk("anch_hidden", {ANCHOR: ANCH.replace(f"{KEY}/{R}allowed: ", '? "' + SPLIT3.replace("\\\n      ", "\\\n  ") + '"\n    : ', 1)}))
report("B48 the allow-listed document with one key re-spelled over several lines is no longer allow-listed (RED)", rc != 0, out[-300:])
rc, out = run(mk("anch_alias_path", {ANCHOR: ANCH + f"  q: &p /metadata/annotations/{KEY}~1{R}allowed\n  patch:\n    - op: add\n      path: *p\n      value: \"true\"\n"}))
report("B49 an aliased op path inside the allow-listed document makes it non-own (RED)", rc != 0, out[-300:])
rc, out = run(mk("anch_reuse", {ANCHOR: ANCH.replace("  annotations:\n", "  annotations: &an\n").replace("data:\n  A: b\n", "data:\n  A: b\n  copy: *an\n")}))
report("B50 an alias to the annotations mapping inside the allow-listed document makes it non-own (RED)", rc != 0, out[-300:])
# ---- prose block scalar naming the key is not a hidden value
rc, out = run(mk("prose_block", {"platform-gitops/prose.yaml": f"kind: ConfigMap\nmetadata:\n  name: z\ndata:\n  note: |\n    see {KEY}/{R}allowed: false in the docs\n    and more text\n"}))
report("B51 a literal block of prose that names a key with false is GREEN", rc == 0, out[-300:])
rc, out = run(mk("badnest", {"platform-gitops/badnest.yaml": f"kind: ConfigMap\nmetadata:\n  name: z\ndata:\n  note: |\n    {KEY}/{R}allowed: [unclosed\n    more\n"}))
report("B52 a nested string that does not parse is not a crash", rc in (0, 1, 2), out[-200:])
rc, out = run(mk("badnest2", {"platform-gitops/badnest2.yaml": f"kind: ConfigMap\nmetadata:\n  name: z\ndata:\n  a: &s \"{KEY}/{R}allowed: [unclosed\\nmore\"\n  b: *s\n".replace("\\n", "\\n")}))
report("B53 an aliased string that does not parse is UNKNOWN (reaches a value by alias)", rc in (1, 2), out[-200:])
# ---- non-nested plain text at the nesting limit stays GREEN
inner = f"see {KEY}/{R}allowed docs"
lvl = json.dumps({"p": json.dumps({"p": json.dumps({"p": inner})})}) if False else None
# ---- the kustomize string with a complex key is not made UNKNOWN by the nested parse
rc, out = run(mk("nest_ck", {"k/kustomization.yaml": "patches:\n  - patch: |-\n      op: add\n      path: " + PATHK + "\n      value: \"false\"\n      ? [x, y]\n      : z\n"}))
report("B54 a complex key inside a nested patch string does not make the nested parse strict", rc == 0, out[-300:])
# ---- CLI
rc_a = d1.main([str(mk("cli1")), "--anchor", ANCHOR]) if False else None
buf = io.StringIO()
with contextlib.redirect_stdout(buf): rc = d1.main([str(mk("cli1")), "--anchor", ANCHOR])
report("B55 --anchor with the real anchor file is GREEN", rc == 0, buf.getvalue()[-200:])
buf = io.StringIO()
with contextlib.redirect_stdout(buf): rc = d1.main([str(mk("cli1")), "--anchor", ANCHOR, "--anchor", ANCHOR])
report("B56 two --anchor options are both consumed", rc == 0, buf.getvalue()[-200:])
buf = io.StringIO()
with contextlib.redirect_stdout(buf): rc = d1.main([str(mk("cli1")), "--anchor", ANCHOR, "--anchor", "no/such.yaml"])
report("B57 the second --anchor is read and reported missing", rc == 2 and "anchor missing" in buf.getvalue() and "no/such.yaml" in buf.getvalue(), buf.getvalue()[-200:])

# ---------------------------------------------------------------- round 5: tag spellings, tagged strings, other extensions
print("== round 5 N11: every spelling of a tag that resolves to !!binary ==")
AKB = B64(AK)
SECRET_HEAD = "kind: Secret\nmetadata:\n  name: x\n  annotations:\n"
SPELL = {
    "N11a %TAG handle plus split tag name": "%TAG !e! tag:yaml.org,2002:b\n---\n" + SECRET_HEAD + f'    !e!inary {AKB}: "true"\n',
    "N11b %TAG handle for the whole prefix": "%TAG !e! tag:yaml.org,2002:\n---\n" + SECRET_HEAD + f'    !e!binary {AKB}: "true"\n',
    "N11c percent-escaped !!bin%61ry": SECRET_HEAD + f'    !!bin%61ry {AKB}: "true"\n',
    "N11d verbatim tag with an escaped letter": SECRET_HEAD + f'    !<tag:yaml.org,2002:b%69nary> {AKB}: "true"\n',
    "N11e primary handle redefined": "%TAG ! tag:yaml.org,2002:\n---\n" + SECRET_HEAD + f'    !binary {AKB}: "true"\n',
}
for i, (nm, doc) in enumerate(SPELL.items()):
    r_ = mk(f"n11_{i}", {"platform-gitops/n11.yaml": doc})
    rc, out = run(r_)
    report(nm + ": not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
    rc2, out2 = run(r_, {"tag_gate"})
    report(nm + ": reverting the `tag_gate` rule makes it GREEN again (load-bearing)", rc2 == 0, f"rc={rc2}")
print("== round 5 N12: the tag sits in a patch string and the outer string never says emberstack ==")
KZ = "patches:\n  - target:\n      kind: Secret\n    patch: |\n      - op: add\n        path: !!binary " + B64(PATHK) + "\n        value: \"true\"\n"
r_ = mk("n12a", {"platform-gitops/kustomization.yaml": KZ})
rc, out = run(r_); report("N12a kustomize patch string with a !!binary path is not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
rc, out = run(r_, {"tag_gate"}); report("N12b ... and reverting `tag_gate` makes it GREEN", rc == 0, f"rc={rc}")
KZ2 = KZ.replace("!!binary " + B64(PATHK), "!!binary " + B64("/metadata/annotations/other"))
expect("N12c the same patch with an unrelated !!binary path is GREEN", mk("n12c", {"platform-gitops/kustomization.yaml": KZ2}), 0)
print("== round 5 N13: files without a yaml extension that parse as YAML ==")
SEC_BIN = SECRET_HEAD + f'    !!binary {AKB}: "true"\n'
for nm, rel in (("N13a .txt", "k/secret.txt"), ("N13b no extension", "k/secret"), ("N13c .tpl", "k/secret.yaml.tpl"), ("N13d .j2", "k/s.yaml.j2")):
    rc, out = run(mk("n13" + nm[3], {rel: SEC_BIN}))
    report(f"{nm} Secret with a !!binary key is RED", rc == 1, f"rc={rc}\n{out[-300:]}")
print("== round 5 N14: no new false positives ==")
expect("N14a unrelated !!int / !!str tags are GREEN", mk("n14a", {"k/a.yaml": "a: !!int '3'\nb: !!str x\n"}), 0)
expect("N14b a shell script string that contains `tag = \"!!int\"` is GREEN",
       mk("n14b", {"k/b.yaml": "script: |\n  yq '. tag = \"!!int\"'\n  if [ -f x ]; then echo !!; fi\n"}), 0)
expect("N14c a !!binary value that decodes to something unrelated is GREEN", mk("n14c", {"k/c.yaml": "data:\n  blob: !!binary " + B64("hello world") + "\n"}), 0)
expect("N14d a custom tag in a document that never spells the key is GREEN (it cannot hide one)", mk("n14d", {"k/d.yaml": "a: !Ref Foo\nb: !Sub x\n"}), 0)
rc, out = run(mk("n14e", {"k/e.yaml": "%TAG !e! tag:yaml.org,2002:\n---\nblob: !e!binary " + B64("hello") + "\n"}))
report("N14e %TAG with an unrelated binary scalar is GREEN", rc == 0, f"rc={rc}\n{out[-200:]}")
rc, out = run(mk("n14f", {"k/f.yaml": "{{- if .Values.x }}\n!!binary " + B64(AK) + ": true\n{{- end }}\n"}))
report("N14f an unparseable template whose text carries base64 of the key is UNKNOWN", rc == 2, f"rc={rc}\n{out[-300:]}")
rc, out = run(mk("n14g", {"k/g.yaml": "{{- if .Values.x }}\nplain: text !!int\n{{- end }}\n"}))
report("N14g an unparseable template with a tag and no key material is GREEN", rc == 0, f"rc={rc}\n{out[-300:]}")

print("== round 5 N15: a .yaml file is never skipped as a binary because of its first bytes ==")
MZ = b"MZ: 1\n# \xff\nkind: Secret\nmetadata:\n  annotations:\n    " + AK.encode() + b": 'true'\n"
r_ = mk("n15", {"k/mz.yaml": MZ})
rc, out = run(r_); report("N15a an MZ-prefixed, undecodable .yaml is UNKNOWN, not skipped", rc == 2, f"rc={rc}\n{out[-300:]}")
rc, out = run(r_, {"yaml_never_binary", "binary_scan"}); report("N15b reverting both rules skips it (GREEN): load-bearing", rc == 0, f"rc={rc}")
rc, out = run(r_, {"yaml_never_binary"}); report("N15c the raw-byte scan alone still makes it UNKNOWN", rc == 2, f"rc={rc}")
print("== round 6 N17: review-4 findings ==")
HELM = "{{- if .Values.x }}\nkind: Secret\nmetadata:\n  annotations:\n    !!bin%61ry " + B64(AK) + ": 'true'\n{{- end }}\n# emberstack\n"
r_ = mk("n17a", {"k/h.yaml": HELM})
rc, out = run(r_); report("N17a textual unparseable Helm .yaml with percent-escaped tag + base64 key is UNKNOWN", rc == 2, f"rc={rc}\n{out[-300:]}")
rc, out = run(r_, {"b64_unparseable"}); report("N17a' reverting the rule: GREEN (load-bearing)", rc == 0, f"rc={rc}\n{out[-300:]}")
r_ = mk("n17b", {"templates/secret": b"\x00{{ if .x }}\n!!bin%61ry " + B64(AK).encode() + b": 'true'\n{{ end }}\n"})
rc, out = run(r_); report("N17b NUL-bearing extensionless template with base64 key is UNKNOWN", rc == 2, f"rc={rc}\n{out[-300:]}")
rc, out = run(r_, {"binary_scan", "b64_unparseable"}); report("N17b' a NUL-bearing non-binary name stays UNKNOWN on its own (NUL rule, not skipped)", rc == 2 and "NUL byte" in out, f"rc={rc}\n{out[-300:]}")
r_ = mk("n17c", {"k/a.png": b"\x89PNG\r\n\x1a\n\x00" + AK.encode()})
rc, out = run(r_); report("N17c a .png that spells the key literally is UNKNOWN", rc == 2, f"rc={rc}\n{out[-300:]}")
rc, out = run(r_, {"binary_scan"}); report("N17c' reverting binary_scan: GREEN (load-bearing)", rc == 0, f"rc={rc}")
r_ = mk("n17d", {"k/a.png": b"\x89PNG\r\n\x1a\n\x00\x01\x02 plain image bytes"})
rc, out = run(r_); report("N17d a binary with no key material is GREEN (control)", rc == 0, f"rc={rc}\n{out[-300:]}")
r_ = mk("n17e", {"k/u.yaml": "kind: Secret\nmetadata:\n  annotations:\n    !!binary " + B64(AK).rstrip("=") + ": 'true'\n"})
rc, out = run(r_); report("N17e unpadded !!binary key is UNKNOWN or RED, never GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
print("== round 5 N16: closing the survivors of the final matrix (new code paths) ==")
TPL = lambda body: "{{- if .Values.x }}\n" + body + "\n{{- end }}\n"
rc, out = run(mk("n16a", {"k/a.yaml": TPL("!!binary " + B64(AK.upper()) + ": true")}))
report("N16a base64 of the key in UPPER case in an unparseable template is UNKNOWN (the match is case-insensitive)", rc == 2, f"rc={rc}\n{out[-200:]}")
rc, out = run(mk("n16b", {"k/b.yaml": TPL("!!int x\nnote: " + B64("a perfectly ordinary sentence that holds no key at all, just text") )}))
report("N16b a long base64 run that does not decode to the key does not make a template UNKNOWN", rc == 0, f"rc={rc}\n{out[-200:]}")
for off in range(4):
    rc, out = run(mk(f"n16c{off}", {"k/c.yaml": TPL("!!x " + "A" * off + B64("x" * off + AK)[0:0] + B64(("x" * off) + AK))}))
    report(f"N16c{off} base64 of the key at alignment {off} in an unparseable template is UNKNOWN", rc == 2, f"rc={rc}\n{out[-200:]}")
# a strategic-merge patch string (mapping text, starts with a letter, has newlines) with a !!binary annotation key
SM = "patch: |\n  apiVersion: v1\n  kind: Secret\n  metadata:\n    name: x\n    annotations:\n      !!binary " + AKB + ": \"true\"\n"
rc, out = run(mk("n16d", {"k/kustomization.yaml": SM}))
report("N16d a multi-line mapping patch string with a !!binary annotation key is not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
FLOWP = "patch: ' [{op: add, path: !!binary " + B64(PATHK) + ", value: \"true\"}]'\n"
rc, out = run(mk("n16e", {"k/kustomization.yaml": FLOWP}))
report("N16e a single-line flow patch string with leading space and a !!binary path is not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
FLOWQ = "patch: '[{op: add, path: !!binary " + B64(PATHK) + ", value: \"true\"}]'\n"
rc, out = run(mk("n16f", {"k/kustomization.yaml": FLOWQ}))
report("N16f the same without the leading space is not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
def nest_tag(body, n):
    for _ in range(n): body = "x: |\n" + "".join("  " + l + "\n" for l in body.split("\n"))
    return body
OPD = "- op: add\n  path: !!binary " + B64(PATHK) + "\n  value: \"true\"\n"
for n in range(1, 6):
    rc, out = run(mk(f"n16g{n}", {"k/n.yaml": nest_tag(OPD, n)}))
    report(f"N16g{n} a !!binary path nested {n} string level(s) deep is not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
# an allow-listed ConfigMap that holds the hidden enabler in a string must not be waved through as 'its own annotation'
CM = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: mctl-platform-config\n  namespace: argo-workflows\ndata:\n  patch: |\n    - op: add\n      path: !!binary " + B64(PATHK) + "\n      value: \"true\"\n"
rc, out = run(mk("n16h", {"k/cm.yaml": CM}))
report("N16h the allow-listed ConfigMap with a tag-hidden enabler inside a data string is not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
CM2 = CM.replace("data:\n", "  annotations:\n    " + KEY + "/" + R + "allowed: \"true\"\ndata:\n", 1)
rc, out = run(mk("n16i", {"k/cm2.yaml": CM2}))
report("N16i the same ConfigMap that also spells the key in its annotations is not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
for nm, pre in (("blank line", "\n"), ("comment", "# a comment\n"), ("whitespace-only line", "   \n")):
    doc = "%TAG !e! tag:yaml.org,2002:b\n" + pre + "---\n" + SECRET_HEAD + f'    !e!inary {AKB}: "true"\n'
    rc, out = run(mk("n16j" + nm[0], {"k/d.yaml": doc}))
    report(f"N16j a {nm} between the %TAG directive and the --- keeps the directive: not GREEN", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
rc, out = run(mk("n16k", {"k/MZ.YAML": MZ}))
report("N16k the binary-magic rule is case-insensitive on the extension (.YAML is text too)", rc == 2, f"rc={rc}\n{out[-300:]}")
rc, out = run(mk("n16l", {"k/ok.yaml": "a: 1\n"}))
report("N16l the run prints the COVERAGE text", d1.COVERAGE.splitlines()[0] in out, out[-300:])
# the anchor document itself (the one allow-listed enabler) must not be waved through when ANOTHER enabler hides in a data string
ANCH = base_files()[ANCHOR]
HID_OP = "  patch: |\n    - op: add\n      path: !!binary " + B64(PATHK) + "\n      value: \"true\"\n"
rc, out = run(mk("n16m", {ANCHOR: ANCH.replace("data:\n  A: b\n", "data:\n  A: b\n" + HID_OP)}))
report("N16m the allow-listed anchor with a tag-hidden enabler in a data string is not GREEN (not 'its own annotation')", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
rc, out = run(mk("n16n", {ANCHOR: ANCH.replace("data:\n  A: b\n", "data:\n  A: b\n" + HID_OP.replace("!!binary " + B64(PATHK), PATHK))}))
report("N16n control: the same hidden op spelled in plain text is not GREEN either", rc in (1, 2), f"rc={rc}\n{out[-300:]}")
rc, out = run(mk("n16o", {ANCHOR: ANCH}))
report("N16o control: the anchor alone is GREEN", rc == 0, f"rc={rc}\n{out[-300:]}")
shutil.rmtree(TMP, ignore_errors=True)
print(f"\nchecks={counter[0]} failures={len(failures)}")
for f in failures:
    print("FAILED:", f)
sys.exit(1 if failures else 0)
