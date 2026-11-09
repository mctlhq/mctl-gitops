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
expect("G2 a recognised binary type (PNG magic) holding NUL bytes is skipped, not a false UNKNOWN", mk("nulbin", {"img/logo.dat": b"\x89PNG\r\n\x1a\n\0\0\0"}), 0)

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

# ---------------------------------------------------------------- symlinks
print("== symlinks: observable, never followed out of the root ==")
OUT = TMP / "outside"
(OUT / "sub").mkdir(parents=True)
(OUT / "sub" / "s.yaml").write_text(secret([f'{KEY}/{R}allowed: "true"']))
(OUT / "f.yaml").write_text(secret([f'{KEY}/{R}allowed: "true"']))
SL_IN = mk("sl_inside", {"real/inner.yaml": "a: b\n"})
os.symlink(SL_IN / "real", SL_IN / "alias")
expect("S1 directory symlink to a directory inside the root is GREEN (target scanned at its real path)", SL_IN, 0)
has("S1b ...and is listed in COVERAGE", SL_IN, "alias")
SL_IN_RED = mk("sl_inside_red", {"real/s.yaml": secret([f'{KEY}/{R}allowed: "true"'])})
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
red("W6", "two value keys in one op: ambiguous, unreadable", "k/kustomization.yaml",
    patch(f'- op: add\n  path: /metadata/annotations/{PATH_KEY}\n  value: "false"\n  value: "true"'))
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
has("A1b ...and says why", SP, "cannot be read as one YAML document")
red("A2", "`--- # comment` separator: the second document (a Secret) is a separate document", "platform-gitops/two.yaml",
    ALLOWED_DOC + "--- # next\n" + secret([f'{KEY}/{R}allowed: "true"']))
red("A3", "`--- !!map` separator", "platform-gitops/two2.yaml", ALLOWED_DOC + "--- !!map\n" + secret([f'{KEY}/{R}allowed: "true"']))
red("A4", "separator with trailing spaces", "platform-gitops/two3.yaml", ALLOWED_DOC + "---   \n" + secret([f'{KEY}/{R}allowed: "true"']))
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
ENABLER = secret([f'{KEY}/{R}allowed: "true"'])
CLEAN = "a: b\n"
expect("P1 clean .tgz is GREEN", mk("p1", {"charts/c.tgz": tar_bytes({"c/values.yaml": CLEAN})}), 0)
has("P1b ...and COVERAGE says it was opened and scanned", mk("p1"), "charts/c.tgz (1 members)")
red("P2", "enabler inside a .tgz member", "charts/c.tgz", tar_bytes({"c/templates/s.yaml": ENABLER}))
red("P3", "enabler inside a .zip member", "charts/c.zip", zip_bytes({"c/s.yaml": ENABLER}))
red("P4", "enabler inside a plain .tar member", "charts/c.tar", tar_bytes({"c/s.yaml": ENABLER}, mode="w"))
red("P5", "enabler inside a single .gz", "charts/s.yaml.gz", gzip.compress(ENABLER.encode()))
red("P6", "enabler inside a .tgz nested in a .zip", "charts/n.zip", zip_bytes({"inner.tgz": tar_bytes({"s.yaml": ENABLER})}))
red("P7", "enabler inside a .whl (zip)", "dist/x.whl", zip_bytes({"x/s.yaml": ENABLER}))
expect("P8 corrupt archive is UNKNOWN", mk("p8", {"charts/bad.tgz": b"not an archive at all"}), 2)
expect("P9 empty archive file is UNKNOWN", mk("p9", {"charts/empty.zip": b""}), 2)
expect("P10 archive nested deeper than the limit is UNKNOWN", mk("p10", {"a.zip": zip_bytes({"b.zip": zip_bytes({"c.zip": zip_bytes({"d.yaml": CLEAN})})})}), 2)
expect("P11 NUL member of an unknown type inside an archive is UNKNOWN", mk("p11", {"c.zip": zip_bytes({"blob.dat": b"\0\0\0x"})}), 2)
expect("P12 invalid UTF-8 member in an archive is UNKNOWN", mk("p12", {"c.tgz": tar_bytes({"m.yaml": b"a: \xff\xfe\xfa\n"})}), 2)
hostile = "../../x\n::error::pwned.yaml"
HN = mk("p13", {"c.zip": zip_bytes({hostile: ENABLER})})
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
NL = mk("n1", {"platform-gitops/a\n::error::pwned.yaml": secret([f'{KEY}/{R}allowed: "true"'])})
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
(SIB / "rootX" / "s.yaml").write_text(ENABLER)
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
    red("K4-" + key, f"committed mirror marker {key}", "platform-gitops/m.yaml", secret([f'{KEY}/{key}: "database/postgres-credentials"'], extra="  namespace: tenant\n"))
for key in ("allowed-namespaces", "auto-namespaces", "allowed-namespaces-selector", "auto-namespaces-selector"):
    red("K5-" + key, f"namespace key {key} match-all with flags absent", "platform-gitops/n.yaml", secret([f'{KEY}/{R}{key}: ".*"']))
red("K6", "unknown annotation suffix", "platform-gitops/u.yaml", secret([f'{KEY}/bogus-setting: "x"']))
red("K7", "removal of an UNKNOWN suffix is not a removal of a known key", "scripts/r.sh", f"kubectl annotate secret x {KEY}/bogus-\n")
expect("K8 removal of a known key (kubectl annotate key-) is GREEN", mk("k8", {"scripts/r.sh": f"kubectl annotate secret x {KEY}/{R}allowed-\n"}), 0)
red("K9", "only ONE flag provably false, namespaces match-all", "platform-gitops/n.yaml", secret([f'{KEY}/{R}allowed: "false"', f'{KEY}/{R}auto-namespaces: ".*"']))
expect("K10 BOTH flags false with match-all namespaces is GREEN (Row-1 end state)", mk("k10", {"platform-gitops/n.yaml": secret([f'{KEY}/{R}allowed: "false"', f'{KEY}/{R}auto-enabled: "false"', f'{KEY}/{R}auto-namespaces: ".*"'])}), 0)
expect("K11 reflects pointing at the allow-listed source is GREEN", mk("k11", {"platform-gitops/p.yaml": secret([f'{KEY}/reflects: "argo-workflows/mctl-platform-config"'], extra="  namespace: tenant\n")}), 0)
red("K12", "auto-reflects pointing at the allow-listed source is NOT allowed", "platform-gitops/p.yaml", secret([f'{KEY}/auto-reflects: "argo-workflows/mctl-platform-config"']))
red("K13", "reflects pointing anywhere else", "platform-gitops/p.yaml", secret([f'{KEY}/reflects: "argo-workflows/other"']))
for i, v in enumerate(["", ".*", ".+", ".*?", "[\\s\\S]*", "[^]*", "^.*$", "(.*)", "tenant-a,.*", "^(.*)$"]):
    red(f"K14-{i}", f"match-all namespace regex {v!r}", "platform-gitops/n.yaml", secret([f'{KEY}/{R}auto-namespaces: "{v}"']))
for v in ("tenant-a", "tenant-.*", "^tenant-[a-z]+$"):
    expect(f"K15 specific namespace regex {v!r} with flags absent is GREEN", mk("k15", {"platform-gitops/n.yaml": secret([f'{KEY}/{R}auto-namespaces: "{v}"'])}), 0)
for v in ("false", "False", "FALSE", " false ", "'false'"):
    expect(f"K16 flag value {v!r} is provably false: GREEN", mk("k16", {"platform-gitops/n.yaml": secret([f'{KEY}/{R}allowed: {v}'])}), 0)
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
def rr(name, rule, rc=1):
    not_detected(f"{name} {RED[name][0]}", RED[name][1], rc, rule)
for n in ("M3", "M4", "M5"): rr(n, "flag_not_provable_false")
for n in ("M7", "M9", "M15", "M16"): rr(n, "formats")
for n in ("M11", "M12"): rr(n, "ns_matchall")
rr("M13", "reflects_marker")
rr("M14", "unqualified")
for n in ("helm", "shell", "fmt", "plus", "empty", "digit", "tilde"): rr("M17-" + n, "prefix_unrecognised_suffix")
rr("M20", "utf16_bom")
not_detected("S2 escaping directory symlink", SL_OUT, 2, "dir_symlinks")
not_detected("S5 escaping file symlink", SL_FILE, 2, "dir_symlinks")
has("S1b directory symlink listing gone when its rule is reverted", SL_IN, "alias", want=False, revert={"dir_symlinks"})
rr("E1", "escape_decode"); rr("E2", "escape_decode"); rr("E3", "escape_decode")
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
red("X12", 'match-all with a space after the comma ("x, .*")', "platform-gitops/s.yaml", secret([f'{KEY}/{R}allowed-namespaces: "x, .*"']))
red("X13", 'match-all wrapped in parentheses with inner blanks ("( .* )")', "platform-gitops/s.yaml", secret([f'{KEY}/{R}allowed-namespaces: "( .* )"']))
red("X14", 'match-all anchored and parenthesised ("^(.*)$")', "platform-gitops/s.yaml", secret([f'{KEY}/{R}allowed-namespaces: "^(.*)$"']))
expect("X15 provably-false values with blanks and case are GREEN (false / ' False ' / \"FALSE\")", mk("x15", {"platform-gitops/s.yaml": secret([f'{KEY}/{R}allowed: " False "', f"{KEY}/{R}auto-enabled: FALSE"])}), 0)
PATCH_BLANK = ("patches:\n  - target: {kind: Secret}\n    patch: |-\n      - op: add\n        path: /spec/foo\n        value: \"false\"\n\n"
               f"      - op: add\n\n        value: \"true\"\n        path: /metadata/annotations/{PATH_KEY}\n")
red("X16", "blank lines inside a JSON-patch op do not detach the value from its path", "k/kustomization.yaml", PATCH_BLANK)
expect("X17 an uppercase file name is not treated as a binary type by case folding of a NUL-containing .PNG", mk("x17", {"img/LOGO.PNG": b"\0\0\0 not a png"}), 2)

red("X18", "enabler on the FIRST line of a file that starts with a UTF-8 BOM", "platform-gitops/bom.yaml", b"\xef\xbb\xbf" + f'{KEY}/{R}allowed: "true"\n'.encode())
for key_ in ("reflected-version", "reflected-at"):
    rc, out = run(mk("x19" + key_[-2:], {"platform-gitops/m.yaml": secret([f"{KEY}/{key_}: 1"])}))
    report(f"X19 committed {key_} is named a mirror marker (not just an unknown key)", rc == 1 and "mirror marker" in out, out[-300:])

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nchecks={counter[0]} failures={len(failures)}")
for f in failures:
    print("FAILED:", f)
sys.exit(1 if failures else 0)
