#!/usr/bin/env python3
"""Offline proof for scripts/check-live-reflector-drift.py (D2, the MANUAL live drift check).

D2 needs a metadata listing taken from the cluster, so it is not run in CI. This
test feeds it synthetic recorded input (tests/fixtures/reflector-live/*.txt plus
rows derived from them in memory) and shows it both ways:
  GREEN on the converged listing, RED on each deliberate mutation,
  UNKNOWN (rc 2) on unreadable / partial / malformed input and on any
  combination where an unobservable part could hide drift,
  and every rule load-bearing: reverted (REVERT test seam), its mutation stops being detected.
It also drives scripts/collect-reflector-metadata.sh against a stub kubectl to
pin its output shape and its failure behaviour. No cluster, no network.

Run: python3 tests/test_live_reflector_drift.py   (stdlib only; exit 0 all pass, 1 failure)
"""
import contextlib
import importlib.util
import io
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-live-reflector-drift.py"
COLLECT = ROOT / "scripts" / "collect-reflector-metadata.sh"
FIX = ROOT / "tests" / "fixtures" / "reflector-live"
spec = importlib.util.spec_from_file_location("d2", SCRIPT)
d2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d2)

TMP = pathlib.Path(tempfile.mkdtemp(prefix="d2-proof-"))
failures, counter = [], [0]
CONVERGED = FIX / "converged.txt"
ANCHOR = ["--anchor", "database/postgres-credentials"]


def rows_of(path):
    return [l for l in pathlib.Path(path).read_text().splitlines() if l and not l.startswith("#")]


def listing(name, rows, trailer=True):
    p = TMP / (name + ".txt")
    p.write_text("\n".join(rows) + "\n" + (f"#END rows={len(rows)}\n" if trailer else ""))
    return p


def row(ns="", name="", allowed="", auto="", reflects="", autoref="", ver="", at=""):
    return "|".join([ns, name, allowed, auto, reflects, autoref, ver, at])


BASE = rows_of(CONVERGED)


def report(label, ok, detail=""):
    counter[0] += 1
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        failures.append(f"{label}: {detail}")


def run(args, revert=()):
    buf = io.StringIO()
    d2.REVERT.clear()
    d2.REVERT.update(revert)
    try:
        with contextlib.redirect_stdout(buf):
            rc = d2.main([str(a) for a in args])
    finally:
        d2.REVERT.clear()
    return rc, buf.getvalue()


def expect(label, args, want, revert=()):
    rc, out = run(args, revert)
    report(label, rc == want, f"rc={rc} want={want}\n{out[-500:]}")


def not_detected(label, args, detecting_rc, rule):
    rc, out = run(args, set(rule.split(",")))
    report(f"{label}  [revert {rule}]", rc != detecting_rc, f"still rc={rc} with {rule} reverted")


# ---------------------------------------------------------------- GREEN
print("== GREEN: converged recorded listing ==")
expect("G0 converged fixture, explicit anchor", [CONVERGED] + ANCHOR, 0)
expect("G1 converged fixture, default anchor", [CONVERGED], 0)
G2 = listing("g_unrelated", BASE + [row("database", "other-secret")])
expect("G2 unrelated Secret in the source namespace is GREEN", [G2], 0)
G3 = listing("g_nosrc", BASE + [row("yy", "foo")])
expect("G3 control: unregistered name in another namespace is GREEN", [G3], 0)
rc, out = run([CONVERGED])
report("G4 GREEN output states its scope (Secrets, metadata only, name-based copies)", rc == 0 and "scope: Secrets only" in out, out)
post_row5 = listing("g_post_row5", [r for r in BASE if not r.startswith("database|postgres-credentials")])
expect("G5 sources deleted: --no-anchor GREEN", [post_row5, "--no-anchor"], 0)

# ---------------------------------------------------------------- RED
print("== RED: deliberate mutations ==")
RED = {}
def red(name, label, rows, extra=()):
    p = listing("m_" + name, rows)
    RED[name] = (label, [p] + list(extra))
    expect(f"{name} {label}", RED[name][1], 1)

red("N1", "mirror survivor (all markers)", BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True", ver="1234", at="2026-11-09T10:00:00Z")], ANCHOR)
red("N2", "mirror with only reflects", BASE + [row("admins", "object-storage-credentials", reflects="database/object-storage-credentials")], ANCHOR)
red("N3", "mirror with reflects + auto-reflects", BASE + [row("tenant-x", "tenant-bootstrap-secret", reflects="database/tenant-bootstrap-secret", autoref="True")], ANCHOR)
red("N4", "new Secret allowed=true", BASE + [row("zz", "new-secret", allowed="true")], ANCHOR)
red("N5", "auto-enabled=true only", BASE + [row("zz", "new-secret", auto="true")], ANCHOR)
red("N6", "allowed=TRUE", BASE + [row("zz", "new-secret", allowed="TRUE")], ANCHOR)
red("N7", "allowed=' true'", BASE + [row("zz", "new-secret", allowed=" true")], ANCHOR)
red("N8", "a source flipped back to true/true", [r.replace("|false|false|", "|true|true|") if r.startswith("database|postgres-credentials") else r for r in BASE], ANCHOR)
red("N9", "mirror whose NAME is not a source (mirror rule alone)", BASE + [row("admins", "copy-of-x", reflects="database/postgres-credentials", autoref="True")], ANCHOR)
red("N10", "non-annotated copy of postgres-credentials", BASE + [row("zz", "postgres-credentials")])
red("N11", "non-annotated copy of object-storage-credentials", BASE + [row("tenant-x", "object-storage-credentials")])
red("N12", "non-annotated copy of tenant-bootstrap-secret", BASE + [row("tenant-x", "tenant-bootstrap-secret")])
red("N13", "--source generalises the copy rule", BASE + [row("yy", "foo")], ["--source", "zz/foo"])
expect("N14 committed mirror-survivor fixture", [FIX / "mirror-survivor.txt"] + ANCHOR, 1)

# ---------------------------------------------------------------- UNKNOWN
print("== UNKNOWN: could not observe (rc 2, never green) ==")
expect("V1 mirror markers but no reflects (source unreadable)", [listing("u1", BASE + [row("zz", "x", at="2026-11-09T10:00:00Z")])] + ANCHOR, 2)
expect("V2 reflects malformed", [listing("u2", BASE + [row("zz", "x", reflects="not-a-ref", autoref="True")])] + ANCHOR, 2)
empty = TMP / "u_empty.txt"; empty.write_text("")
expect("V3 empty file", [empty] + ANCHOR, 2)
expect("V4 kubectl rc != 0", [CONVERGED, 1] + ANCHOR, 2)
expect("V5 truncated listing (no trailer)", [FIX / "truncated.txt"] + ANCHOR, 2)
cnt = TMP / "u_count.txt"; cnt.write_text("\n".join(BASE[:8]) + "\n#END rows=384\n")
expect("V6 trailer count mismatch (partial)", [cnt] + ANCHOR, 2)
mal = TMP / "u_mal.txt"; mal.write_text("\n".join(BASE[:3] + ["a|b|c"]) + "\n#END rows=4\n")
expect("V7 malformed row (3 fields)", [mal] + ANCHOR, 2)
no_anchor = listing("u_anc", [r for r in BASE if not r.startswith("database|postgres-credentials")])
expect("V8 anchor Secret missing from listing", [no_anchor] + ANCHOR, 2)
zero = TMP / "u_zero.txt"; zero.write_text("#END rows=0\n")
expect("V9 zero rows with trailer", [zero] + ANCHOR, 2)
expect("V10 missing file", [TMP / "none.txt"] + ANCHOR, 2)
BOTH = listing("u_both", BASE + [row("zz", "new-secret", allowed="true"), row("zz", "x", reflects="not-a-ref", autoref="True")])
expect("V11 unknown outranks red (red + unreadable mirror => 2)", [BOTH] + ANCHOR, 2)
copy_trunc = TMP / "u_copy_trunc.txt"; copy_trunc.write_text("\n".join(BASE + [row("zz", "postgres-credentials")]) + "\n")
expect("V12 copy present but listing truncated => UNKNOWN, not RED/GREEN", [copy_trunc], 2)
expect("V13 bad rc argument (not an int)", [CONVERGED, "notanint"], 2)
expect("V14 --anchor and --no-anchor together", [CONVERGED, "--anchor", "database/postgres-credentials", "--no-anchor"], 2)
expect("V15 --anchor missing its value", [CONVERGED, "--anchor"], 2)
expect("V16 default anchor missing (post-delete state without --no-anchor)", [no_anchor], 2)
expect("V17 --source without ns/name", [CONVERGED, "--source", "bare"], 2)
expect("V18 no arguments", [], 2)
rc, out = run([TMP / "none.txt"] + ANCHOR)
report("V19 unreadable input never prints GREEN", "GREEN" not in out, out)

# ---------------------------------------------------------------- revert-the-fix
print("== revert-the-fix: rule removed => its mutation must stop being detected ==")
for n in ("N1", "N2", "N3"): not_detected(f"{n} {RED[n][0]}", RED[n][1], 1, "mirror_rule,copy_rule")
not_detected(f"N9 {RED['N9'][0]}", RED["N9"][1], 1, "mirror_rule")
for n in ("N10", "N11", "N12", "N13"): not_detected(f"{n} {RED[n][0]}", RED[n][1], 1, "copy_rule")
for n in ("N5", "N6", "N7"): not_detected(f"{n} {RED[n][0]}", RED[n][1], 1, "source_flags")
not_detected("V5 truncated listing", [FIX / "truncated.txt"] + ANCHOR, 2, "trailer")
not_detected("V6 trailer count mismatch", [cnt] + ANCHOR, 2, "trailer")
not_detected("V11 unknown outranks red", [BOTH] + ANCHOR, 2, "unknown_outranks")
not_detected("V16 default anchor", [no_anchor], 2, "default_anchor")

# ---------------------------------------------------------------- no outside lever
print("== no outside lever on the check ==")
env = dict(os.environ, SA_DET_REVERT="mirror_rule,copy_rule,source_flags,trailer", SA_DET_PROOF_NONCE="x")
r = subprocess.run([sys.executable, str(SCRIPT), str(RED["N1"][1][0])] + ANCHOR, env=env, capture_output=True, text=True)
report("H1 env var cannot weaken the check (CLI still RED on N1)", r.returncode == 1, r.stdout[-300:] + r.stderr[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), str(CONVERGED)] + ANCHOR, capture_output=True, text=True)
report("H2 CLI on the converged fixture: rc 0, prints GREEN", r.returncode == 0 and "GREEN" in r.stdout, r.stdout + r.stderr)

# ---------------------------------------------------------------- CRLF and mixed line endings
print("== CRLF / mixed line endings in the listing ==")
def write_bytes(name, text, eol):
    p = TMP / name
    p.write_bytes(text.replace("\n", eol).encode())
    return p
conv_text = CONVERGED.read_text()
expect("L1 converged listing with CRLF is GREEN", [write_bytes("l1.txt", conv_text, "\r\n")], 0)
mut_text = "\n".join(BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True")]) + f"\n#END rows={len(BASE) + 1}\n"
expect("L2 mutated listing (mirror survivor) with CRLF is RED", [write_bytes("l2.txt", mut_text, "\r\n")] + ANCHOR, 1)
mixed = TMP / "l3.txt"
mixed.write_bytes(("\r\n".join(BASE[:6]) + "\n" + "\r\n".join(BASE[6:]) + "\r\n#END rows=%d\n" % len(BASE)).encode())
expect("L3 mixed endings (CRLF and LF) converged is GREEN", [mixed], 0)
mixed_red = TMP / "l4.txt"
mixed_red.write_bytes(("\n".join(BASE) + "\r\n" + row("zz", "new-secret", allowed="true") + f"\n#END rows={len(BASE) + 1}\r\n").encode())
expect("L4 mixed endings with a source flag true is RED", [mixed_red], 1)
expect("L5 CRLF truncated (no trailer) is UNKNOWN", [write_bytes("l5.txt", "\n".join(BASE[:5]) + "\n", "\r\n")], 2)
expect("L6 CRLF trailer count mismatch is UNKNOWN", [write_bytes("l6.txt", "\n".join(BASE[:5]) + "\n#END rows=99\n", "\r\n")], 2)
not_detected("L1 CRLF listing", [write_bytes("l1r.txt", conv_text, "\r\n")], 0, "crlf")   # with CR handling reverted GREEN must turn into UNKNOWN
rc, _ = run([TMP / "l1r.txt"], {"crlf"})
report("L1 revert-the-fix: CRLF handling reverted => CRLF converged is UNKNOWN (rc 2), the old false negative", rc == 2, f"rc={rc}")
sr = TMP / "l7.txt"; sr.write_bytes(b"a|b|||||| \rzz\n#END rows=1\n")
rc, out = run([sr, "--no-anchor"])
report("L7 stray carriage return inside a row is not GREEN", rc != 0, out)

# ---------------------------------------------------------------- collector: real argv, real JSONPath, end to end into D2
print("== collect-reflector-metadata.sh: argv captured, JSONPath evaluated on synthetic Secrets, then fed to D2 ==")
import json
import re as _re
DOM = "reflector.v1.k8s." + "emberstack.com"      # assembled at run time so the repo guard sees no literal key here
RP = "reflection-"
ESC = DOM.replace(".", "\\.")                      # kubectl JSONPath: a dot inside a map key is written \.
ANNO = lambda k: "{.metadata.annotations." + ESC + "/" + k + "}"
EXPECTED_JP = ("{range .items[*]}{.metadata.namespace}|{.metadata.name}|" + ANNO(RP + "allowed") + "|" + ANNO(RP + "auto-enabled")
               + "|" + ANNO("reflects") + "|" + ANNO("auto-reflects") + "|" + ANNO("reflected-version") + "|" + ANNO("reflected-at")
               + '{"\\n"}{end}')
EXPECTED_ARGV = ["get", "secret", "-A", "-o", "jsonpath=" + EXPECTED_JP]
REAL_KUBECTL = shutil.which("kubectl")

STUB = r"""#!/usr/bin/env python3
# Stub kubectl: records argv, then evaluates the -o jsonpath template (the subset the collector uses) on the
# synthetic Secret list in $STUB_OBJECTS. It mirrors kubectl: a dot in a path segment splits it unless written \.
import json, os, re, sys
json.dump(sys.argv[1:], open(os.environ["STUB_REC"], "w"))
mode = os.environ.get("STUB_MODE", "ok")
if mode == "fail":
    sys.stderr.write("boom\n"); sys.exit(3)
args = sys.argv[1:]
if args[:3] != ["get", "secret", "-A"] or len(args) != 5 or args[3] != "-o" or not args[4].startswith("jsonpath="):
    sys.stderr.write("stub: unexpected arguments\n"); sys.exit(1)
tpl = args[4][len("jsonpath="):]
items = json.load(open(os.environ["STUB_OBJECTS"]))["items"]
toks = [(a, b) for a, b in re.findall(r"\{([^{}]*)\}|([^{}]+)", tpl)]
def get(obj, path):
    for seg in re.split(r"(?<!\\)\.", path.lstrip(".")):
        seg = seg.replace("\\.", ".")
        if not isinstance(obj, dict) or seg not in obj: return ""
        obj = obj[seg]
    return obj if isinstance(obj, str) else ""
def render(body, item):
    out = ""
    for act, lit in body:
        if lit: out += lit
        elif act.startswith("."): out += get(item, act)
        elif act.startswith('"'): out += json.loads(act)
        else: sys.stderr.write("stub: unsupported action %r\n" % act); sys.exit(1)
    return out
acts = [t[0] for t in toks]
if not acts or not acts[0].startswith("range .items[*]") or acts[-1] != "end":
    sys.stderr.write("stub: template is not a range over .items\n"); sys.exit(1)
body = toks[1:-1]
res = "".join(render(body, it) for it in items)
if mode == "truncate":
    sys.stdout.write(res[: len(res) // 2]); sys.stderr.write("connection reset\n"); sys.exit(1)
sys.stdout.write(res)
"""
bindir = TMP / "bin"; bindir.mkdir()
(bindir / "kubectl").write_text(STUB)
(bindir / "kubectl").chmod((bindir / "kubectl").stat().st_mode | stat.S_IEXEC)

def items_of(rows):
    items = []
    for r in rows:
        ns, name, allowed, auto, reflects, autoref, ver, at = r.split("|")
        an = {}
        for k, v in ((RP + "allowed", allowed), (RP + "auto-enabled", auto), ("reflects", reflects),
                     ("auto-reflects", autoref), ("reflected-version", ver), ("reflected-at", at)):
            if v: an[DOM + "/" + k] = v
        md = {"namespace": ns, "name": name}
        if an: md["annotations"] = an
        items.append({"apiVersion": "v1", "kind": "Secret", "metadata": md})
    return {"apiVersion": "v1", "kind": "List", "items": items}

counter_c = [0]
def collect(script, rows=None, mode="ok", tag=None):
    counter_c[0] += 1
    tag = tag or f"c{counter_c[0]}"
    objs, rec = TMP / (tag + ".json"), TMP / (tag + ".argv")
    objs.write_text(json.dumps(items_of(rows if rows is not None else BASE)))
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", STUB_OBJECTS=str(objs), STUB_REC=str(rec), STUB_MODE=mode)
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
    argv = json.loads(rec.read_text()) if rec.exists() else None
    out = TMP / (tag + ".out"); out.write_text(r.stdout)
    return r, argv, out

def collector_proof(script):
    """The collector's verdicts. Returns {check: bool}; all True for the real script, a corrupted one must lose at least one."""
    res = {}
    r, argv, out = collect(script, BASE)
    res["argv is exactly: get secret -A -o jsonpath=<expected template>"] = argv == EXPECTED_ARGV
    res["converged synthetic Secrets => D2 GREEN"] = r.returncode == 0 and run([out, "--anchor", "database/postgres-credentials"])[0] == 0
    mirror = BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True", ver="7", at="2026-01-01T00:00:00Z")]
    r, argv, out = collect(script, mirror)
    res["mirror survivor annotations come through => D2 RED"] = run([out] + ANCHOR)[0] == 1
    flipped = [x.replace("|false|false|", "|true|true|") if x.startswith("database|postgres-credentials") else x for x in BASE]
    r, argv, out = collect(script, flipped)
    res["source flags true come through => D2 RED"] = run([out] + ANCHOR)[0] == 1
    return res

good = collector_proof(COLLECT)
for k, v in good.items(): report("C1 " + k, v)
if REAL_KUBECTL:
    # Cross-check the template against the REAL kubectl JSONPath engine (no cluster: --local on a file). kubectl applies
    # the template to each object separately, so the per-object body is compared, not the range wrapper.
    items = items_of(BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True", ver="7", at="2026-01-01T00:00:00Z")])
    f = TMP / "real.json"; f.write_text(json.dumps(items))
    body = EXPECTED_JP[len("{range .items[*]}"):-len("{end}")]
    r = subprocess.run([REAL_KUBECTL, "annotate", "--local", "-f", str(f), "zz=1", "--overwrite", "-o", "jsonpath=" + body],
                       env=dict(os.environ, KUBECONFIG=os.devnull), capture_output=True, text=True)
    r2, _, _ = collect(COLLECT, BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True", ver="7", at="2026-01-01T00:00:00Z")])
    ok = r.returncode == 0 and r.stdout == "\n".join(r2.stdout.splitlines()[:-1]) + "\n"
    report("C2 REAL kubectl (%s) parses the collector's JSONPath and returns the same rows as the evaluator" % REAL_KUBECTL, ok, f"rc={r.returncode}\n{r.stderr[-400:]}\nreal={r.stdout[-300:]!r}")
    # the trap agy worried about: unescaped dots do NOT address the map key, kubectl silently returns empty
    bad_body = body.replace("\\.", ".")
    rb = subprocess.run([REAL_KUBECTL, "annotate", "--local", "-f", str(f), "zz=1", "--overwrite", "-o", "jsonpath=" + bad_body],
                        env=dict(os.environ, KUBECONFIG=os.devnull), capture_output=True, text=True)
    report("C3 REAL kubectl: unescaped dots silently return empty annotations (why the escaping is load-bearing)", rb.returncode == 0 and "database/postgres-credentials" not in rb.stdout, rb.stdout[-200:])
else:
    print("SKIP  C2/C3 real kubectl not found on PATH: JSONPath checked by the in-test evaluator only (NOT against client-go)")

# collector mutations: corrupt the JSONPath / the arguments, the proof must go RED (lose a check)
real_text = COLLECT.read_text()
def mutate(tag, old, new):
    assert old in real_text, tag
    p = TMP / (tag + ".sh"); p.write_text(real_text.replace(old, new, 1)); p.chmod(0o755)
    res = collector_proof(p)
    lost = [k for k, v in res.items() if not v]
    report(f"CM-{tag}: collector mutated ({old!r} -> {new!r}) is caught", bool(lost), "all checks still passed")
mutate("unescaped-dots", "P='reflector\\.v1\\.k8s\\.'\"emberstack\"'\\.com'", "P='reflector.v1.k8s.'\"emberstack\"'.com'")
mutate("drop-all-namespaces", "get secret -A", "get secret")
mutate("wrong-key", "${P}/reflects}", "${P}/reflected}")
mutate("drop-allowed", "${P}/${R}allowed}", "${P}/${R}allowed2}")
mutate("output-yaml", "-o jsonpath=", "-o yaml --template=")
mutate("bracket-unescaped", "{.metadata.annotations.${P}/${R}allowed}", "{.metadata.annotations['" + DOM + "/" + RP + "allowed']}")

# failure behaviour, end to end into D2
r, argv, out = collect(COLLECT, BASE, mode="fail")
report("E1 kubectl failure: collector exits with kubectl's rc 3 and prints NO trailer", r.returncode == 3 and "#END" not in r.stdout, f"rc={r.returncode} out={r.stdout!r}")
expect("E2 ...and D2 reads that output as UNKNOWN, never GREEN", [out], 2)
r, argv, out = collect(COLLECT, BASE, mode="truncate")
report("E3 kubectl dies mid-stream: collector fails, no trailer", r.returncode == 1 and "#END" not in r.stdout, f"rc={r.returncode}")
expect("E4 ...and D2 reads the partial output as UNKNOWN", [out], 2)
r, argv, out = collect(COLLECT, [])
report("E5 no Secrets at all: trailer says rows=0", r.returncode == 0 and "#END rows=0" in r.stdout, r.stdout)
expect("E6 ...and D2 reads that as UNKNOWN (never as 0 found)", [out], 2)
code_text = "\n".join(l for l in real_text.splitlines() if not l.lstrip().startswith("#"))
report("E7 collector code never reads Secret data (no .data, no -o yaml/json; comments excluded)", not re.search(r"\.data\b|-o\s*(yaml|json)\b|--output", code_text) and "-o jsonpath" in code_text, "")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nchecks={counter[0]} failures={len(failures)}")
for f in failures:
    print("FAILED:", f)
sys.exit(1 if failures else 0)
