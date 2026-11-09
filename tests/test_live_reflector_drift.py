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
HEAD = "#CLUSTER context=fixture-ctx server=https://fixture.invalid:6443"
EXP = ["--expect-context", "fixture-ctx"]


def rows_of(path):
    return [l for l in pathlib.Path(path).read_text().splitlines() if l and not l.startswith("#")]


def listing(name, rows, trailer=True, head=True):
    p = TMP / (name + ".txt")
    p.write_text((HEAD + "\n" if head else "") + "\n".join(rows) + "\n" + (f"#END rows={len(rows)}\n" if trailer else ""))
    return p


def row(ns="", name="", allowed="", auto="", reflects="", autoref="", ver="", at=""):
    return "|".join([ns, name, allowed, auto, reflects, autoref, ver, at])


BASE = rows_of(CONVERGED)


def report(label, ok, detail=""):
    counter[0] += 1
    print(("PASS  " if ok else "FAIL  ") + label)
    if not ok:
        failures.append(f"{label}: {detail}")


def run(args, revert=(), exp=True):
    args = list(args)
    if exp and args and not any(str(a).startswith("--expect-") for a in args):
        args += EXP                      # every ordinary case states which cluster it expects; identity cases pass exp=False
    buf = io.StringIO()
    d2.REVERT.clear()
    d2.REVERT.update(revert)
    try:
        with contextlib.redirect_stdout(buf):
            rc = d2.main([str(a) for a in args])
    finally:
        d2.REVERT.clear()
    return rc, buf.getvalue()


def expect(label, args, want, revert=(), exp=True):
    rc, out = run(args, revert, exp)
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
cnt = TMP / "u_count.txt"; cnt.write_text(HEAD + "\n" + "\n".join(BASE[:8]) + "\n#END rows=384\n")
expect("V6 trailer count mismatch (partial)", [cnt] + ANCHOR, 2)
mal = TMP / "u_mal.txt"; mal.write_text(HEAD + "\n" + "\n".join(BASE[:3] + ["a|b|c"]) + "\n#END rows=4\n")
expect("V7 malformed row (3 fields)", [mal] + ANCHOR, 2)
no_anchor = listing("u_anc", [r for r in BASE if not r.startswith("database|postgres-credentials")])
expect("V8 anchor Secret missing from listing", [no_anchor] + ANCHOR, 2)
zero = TMP / "u_zero.txt"; zero.write_text(HEAD + "\n#END rows=0\n")
expect("V9 zero rows with trailer", [zero, "--no-anchor"], 2)
expect("V10 missing file", [TMP / "none.txt"] + ANCHOR, 2)
BOTH = listing("u_both", BASE + [row("zz", "new-secret", allowed="true"), row("zz", "x", reflects="not-a-ref", autoref="True")])
expect("V11 unknown outranks red (red + unreadable mirror => 2)", [BOTH] + ANCHOR, 2)
rc, out = run([BOTH] + ANCHOR)
report("V12 an unreadable mirror source is reported as unreadable only, not ALSO as 'source not allow-listed' (no guess at the source)",
       rc == 2 and "source unreadable" in out and "x <- not-a-ref" not in out and "source not allow-listed" not in out.split("zz/x")[-1], out[-400:])
rc, out = run([listing("n9msg", BASE + [row("admins", "copy-of-x", reflects="database/postgres-credentials", autoref="True")])] + ANCHOR)
report("N9b the mirror finding names the reason: source not allow-listed", rc == 1 and "source not allow-listed" in out, out[-400:])
copy_trunc = TMP / "u_copy_trunc.txt"; copy_trunc.write_text(HEAD + "\n" + "\n".join(BASE + [row("zz", "postgres-credentials")]) + "\n")
expect("V12b copy present but listing truncated => UNKNOWN, not RED/GREEN", [copy_trunc], 2)
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
r = subprocess.run([sys.executable, str(SCRIPT), str(RED["N1"][1][0])] + ANCHOR + EXP, env=env, capture_output=True, text=True)
report("H1 env var cannot weaken the check (CLI still RED on N1)", r.returncode == 1, r.stdout[-300:] + r.stderr[-300:])
r = subprocess.run([sys.executable, str(SCRIPT), str(CONVERGED)] + ANCHOR + EXP, capture_output=True, text=True)
report("H2 CLI on the converged fixture: rc 0, prints GREEN", r.returncode == 0 and "GREEN" in r.stdout, r.stdout + r.stderr)

# ---------------------------------------------------------------- CRLF and mixed line endings
print("== CRLF / mixed line endings in the listing ==")
def write_bytes(name, text, eol):
    p = TMP / name
    p.write_bytes(text.replace("\n", eol).encode())
    return p
conv_text = CONVERGED.read_text()
expect("L1 converged listing with CRLF is GREEN", [write_bytes("l1.txt", conv_text, "\r\n")], 0)
mut_text = HEAD + "\n" + "\n".join(BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True")]) + f"\n#END rows={len(BASE) + 1}\n"
expect("L2 mutated listing (mirror survivor) with CRLF is RED", [write_bytes("l2.txt", mut_text, "\r\n")] + ANCHOR, 1)
mixed = TMP / "l3.txt"
mixed.write_bytes((HEAD + "\r\n" + "\r\n".join(BASE[:6]) + "\n" + "\r\n".join(BASE[6:]) + "\r\n#END rows=%d\n" % len(BASE)).encode())
expect("L3 mixed endings (CRLF and LF) converged is GREEN", [mixed], 0)
mixed_red = TMP / "l4.txt"
mixed_red.write_bytes((HEAD + "\n" + "\n".join(BASE) + "\r\n" + row("zz", "new-secret", allowed="true") + f"\n#END rows={len(BASE) + 1}\r\n").encode())
expect("L4 mixed endings with a source flag true is RED", [mixed_red], 1)
expect("L5 CRLF truncated (no trailer) is UNKNOWN", [write_bytes("l5.txt", HEAD + "\n" + "\n".join(BASE[:5]) + "\n", "\r\n")], 2)
expect("L6 CRLF trailer count mismatch is UNKNOWN", [write_bytes("l6.txt", HEAD + "\n" + "\n".join(BASE[:5]) + "\n#END rows=99\n", "\r\n")], 2)
not_detected("L1 CRLF listing", [write_bytes("l1r.txt", conv_text, "\r\n")], 0, "crlf")   # with CR handling reverted GREEN must turn into UNKNOWN
rc, _ = run([TMP / "l1r.txt"], {"crlf"})
report("L1 revert-the-fix: CRLF handling reverted => CRLF converged is UNKNOWN (rc 2), the old false negative", rc == 2, f"rc={rc}")
sr = TMP / "l7.txt"; sr.write_bytes((HEAD + "\n").encode() + b"a|b|||||| \rzz\n#END rows=1\n")
rc, out = run([sr, "--no-anchor"])
report("L7a CLI: a lone carriage return inside a row is split into two lines by readlines and is not GREEN (malformed row)", rc != 0, out)
rc7, why7 = d2.evaluate([HEAD + "\n", "a|b|||||| \rzz\n", "#END rows=1\n"], 0, (), sources=d2.SOURCES)
report("L7b function level (the only way to reach the in-line CR branch): evaluate() answers UNKNOWN", rc7 == 2 and "carriage return" in why7[0], str(why7))

# ---------------------------------------------------------------- cluster identity header (D2 refuses a listing of an unknown or unexpected cluster)
print("== cluster identity: header present, unique, first, and equal to what the operator expects ==")
rows_ok = BASE
def raw(name, text):
    p = TMP / (name + ".txt"); p.write_text(text); return p
body = "\n".join(rows_ok) + f"\n#END rows={len(rows_ok)}\n"
expect("I1 header matches --expect-context: GREEN", [raw("i1", HEAD + "\n" + body), "--expect-context", "fixture-ctx"], 0, exp=False)
expect("I2 header matches --expect-server only: GREEN", [raw("i2", HEAD + "\n" + body), "--expect-server", "https://fixture.invalid:6443"], 0, exp=False)
expect("I3 both expectations match: GREEN", [raw("i3", HEAD + "\n" + body), "--expect-context", "fixture-ctx", "--expect-server", "https://fixture.invalid:6443"], 0, exp=False)
I_WRONG_CTX = [raw("i4", HEAD + "\n" + body), "--expect-context", "other-ctx"]
expect("I4 wrong context: UNKNOWN (a listing of another cluster is not this one)", I_WRONG_CTX, 2, exp=False)
I_WRONG_SRV = [raw("i5", HEAD + "\n" + body), "--expect-server", "https://other.invalid:6443"]
expect("I5 wrong server: UNKNOWN", I_WRONG_SRV, 2, exp=False)
I_BOTH_HALF = [raw("i5b", HEAD + "\n" + body), "--expect-context", "fixture-ctx", "--expect-server", "https://other.invalid:6443"]
expect("I5b context matches but server does not: UNKNOWN (both given must both match)", I_BOTH_HALF, 2, exp=False)
I_NOEXP = [raw("i6", HEAD + "\n" + body)]
expect("I6 no expectation given: UNKNOWN (an unchecked identity proves nothing)", I_NOEXP, 2, exp=False)
I_NOHEAD = [raw("i7", body), "--expect-context", "fixture-ctx"]
expect("I7 no header: UNKNOWN", I_NOHEAD, 2, exp=False)
I_TWO = [raw("i8", HEAD + "\n" + HEAD.replace("fixture-ctx", "other-ctx") + "\n" + body), "--expect-context", "fixture-ctx"]
expect("I8 two headers: UNKNOWN (not first-wins)", I_TWO, 2, exp=False)
I_LATE = [raw("i9", rows_ok[0] + "\n" + HEAD + "\n" + "\n".join(rows_ok[1:]) + f"\n#END rows={len(rows_ok)}\n"), "--expect-context", "fixture-ctx"]
expect("I9 header not on the first line: UNKNOWN", I_LATE, 2, exp=False)
expect("I10 malformed header (no server): UNKNOWN", [raw("i10", "#CLUSTER context=fixture-ctx\n" + body), "--expect-context", "fixture-ctx"], 2, exp=False)
expect("I11 --expect-context with no value: UNKNOWN", [CONVERGED, "--expect-context"], 2, exp=False)
expect("I12 --expect-context followed by another flag: UNKNOWN", [CONVERGED, "--expect-context", "--no-anchor"], 2, exp=False)
expect("I13 unrecognised comment line: UNKNOWN", [raw("i13", HEAD + "\n#NOTE hi\n" + body)], 2)
INJ = [raw("i14", "#CLUSTER context=fixture-ctx server=https://fixture.invalid:6443\n" + body), "--expect-context", "x\n::error::forged"]
rc, out = run(INJ, exp=False)
report("I14 a hostile expectation cannot forge a log line (control characters escaped in the output)", rc == 2 and "\n::error::" not in out and "\\u000a" in out, out)
for lab, a in (("I4", I_WRONG_CTX), ("I5", I_WRONG_SRV), ("I5b", I_BOTH_HALF), ("I6", I_NOEXP), ("I7", I_NOHEAD), ("I8", I_TWO), ("I9", I_LATE)):
    rc, out = run(a, {"cluster_identity"}, exp=False)
    report(f"{lab} revert-the-fix: cluster_identity reverted => no longer UNKNOWN (rc {rc})", rc != 2, out)

# ---------------------------------------------------------------- shadowing: each guard proven alone
print("== each guard proven on its own (the others disabled) ==")
E0 = TMP / "z_empty.txt"; E0.write_text("")
expect("S1 empty file with identity+trailer checks reverted still UNKNOWN (zero rows)", [E0, "--no-anchor"], 2, {"cluster_identity", "trailer"})
expect("S2 empty file with only the trailer check reverted still UNKNOWN (header)", [E0, "--no-anchor"], 2, {"trailer"})
Z = raw("z_zero", HEAD + "\n#END rows=0\n")
expect("S3 header + trailer rows=0: UNKNOWN by the zero-rows rule alone", [Z, "--no-anchor"], 2)
rc, out = run([Z, "--no-anchor"])
report("S3b ...and the reason named is zero rows", "zero rows" in out, out)
expect("S4 zero-rows check is the only thing between header+trailer(0) and GREEN: kept", [Z, "--no-anchor"], 2, {"default_anchor"})
TMID = raw("z_mid", HEAD + "\n" + "\n".join(BASE[:4]) + "\n#END rows=%d\n" % len(BASE) + "\n".join(BASE[4:]) + "\n")
expect("S5 trailer in the middle (rows after it): UNKNOWN", [TMID], 2)
TTWO = raw("z_two", HEAD + "\n" + body + f"#END rows={len(BASE)}\n")
expect("S6 two trailers: UNKNOWN", [TTWO], 2)
TTWOX = raw("z_twox", HEAD + "\n" + "\n".join(BASE) + "\n#END rows=%d\n#END rows=%d\n" % (len(BASE), len(BASE)))
expect("S6b two trailers, both counts right: UNKNOWN (unique, not last-wins)", [TTWOX], 2)
R9 = raw("z_r9", HEAD + "\n" + "\n".join(BASE[:3] + [row("zz", "x") + "|extra"]) + "\n#END rows=4\n")
expect("S7 nine-field row: UNKNOWN (exactly 8 fields, not at least 8)", [R9, "--no-anchor"], 2)
RN = raw("z_rn", HEAD + "\n" + "\n".join(BASE[:3] + [row("", "x")]) + "\n#END rows=4\n")
expect("S8 row without a namespace: UNKNOWN", [RN, "--no-anchor"], 2)
RM = raw("z_rm", HEAD + "\n" + "\n".join(BASE[:3] + [row("zz", "")]) + "\n#END rows=4\n")
expect("S8b row without a name: UNKNOWN", [RM, "--no-anchor"], 2)
GF = listing("z_gf", BASE + [row("zz", "other-secret", allowed="False", auto="FALSE")])
expect("S9 allowed=False / auto=FALSE are provably false: GREEN (case-insensitive)", [GF], 0)
GS = listing("z_gs", BASE + [row("zz", "other-secret", allowed=" false", auto="false ")])
expect("S10 surrounding blanks around false: GREEN", [GS], 0)
# ALLOW_SOURCES is empty in the shipped tool, so the allow-listed-source branch is exercised through evaluate() directly.
ALLOWED = {("database", "postgres-credentials")}
MS_LINES = [HEAD] + [r for r in BASE if not r.startswith("database|postgres-credentials")] + [row("admins", "x", reflects="database/postgres-credentials", autoref="True")]
MS_LINES.append(f"#END rows={len(MS_LINES) - 1}")
rc, out = d2.evaluate(MS_LINES, 0, (), allow=ALLOWED, expect={"context": "fixture-ctx"})
report("S11 mirror of an allow-listed source that is absent from the listing: UNKNOWN (cannot read the source)", rc == 2 and "allow-listed source not in listing" in out[0], f"{rc} {out}")
OK_LINES = [HEAD] + BASE + [row("admins", "x", reflects="database/postgres-credentials", autoref="True")]
OK_LINES.append(f"#END rows={len(OK_LINES) - 1}")
rc, out = d2.evaluate(OK_LINES, 0, (), allow=ALLOWED, expect={"context": "fixture-ctx"})
report("S11c control: the same mirror with its allow-listed source present is GREEN", rc == 0, f"{rc} {out}")
BOTH_OUT = run([BOTH] + ANCHOR)[1]
report("S12 unknown outranks red: the unknown reason is the one printed", "UNKNOWN (exit 2)" in BOTH_OUT and "source unreadable" in BOTH_OUT, BOTH_OUT)
for lab, a, w in (("GREEN", [CONVERGED], "GREEN (exit 0)"), ("RED", RED["N1"][1], "RED (exit 1)"), ("UNKNOWN", [FIX / "truncated.txt"], "UNKNOWN (exit 2)")):
    rc, out = run(a)
    report(f"S13 verdict line for {lab} is exact", out.startswith(w), out[:80])

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
SRV_JP = "jsonpath={.clusters[0].cluster.server}"
CTX, SRV = "fixture-ctx", "https://fixture.invalid:6443"
EXPECTED_CALLS = [["config", "current-context"],
                  ["--context", CTX, "config", "view", "--minify", "-o", SRV_JP],
                  ["--context", CTX, "get", "secret", "-A", "-o", "jsonpath=" + EXPECTED_JP]]
REAL_KUBECTL = shutil.which("kubectl")

STUB = r"""#!/usr/bin/env python3
# Stub kubectl: appends argv to $STUB_REC, answers the three calls the collector makes, and for `get secret` evaluates
# the -o jsonpath template (the subset the collector uses) on the synthetic Secret list in $STUB_OBJECTS. It mirrors
# kubectl: a dot in a path segment splits it unless written \. ; and it only answers calls pinned to --context $STUB_CTX.
import json, os, re, sys
args = sys.argv[1:]
with open(os.environ["STUB_REC"], "a") as f: f.write(json.dumps(args) + "\n")
mode = os.environ.get("STUB_MODE", "ok")
ctx, srv = os.environ["STUB_CTX"], os.environ["STUB_SERVER"]
if args == ["config", "current-context"]:
    if mode == "ctxfail": sys.stderr.write("no current context\n"); sys.exit(5)
    print(ctx); sys.exit(0)
if args[:1] != ["--context"] or len(args) < 3 or args[1] != ctx:
    sys.stderr.write("stub: call not pinned to the current context\n"); sys.exit(1)
args = args[2:]
if args == ["config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}"]:
    if mode == "srvfail": sys.stderr.write("no cluster\n"); sys.exit(6)
    sys.stdout.write(srv); sys.exit(0)
if mode == "fail":
    sys.stderr.write("boom\n"); sys.exit(3)
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
def collect(script, rows=None, mode="ok", tag=None, ctx=CTX, srv=SRV):
    counter_c[0] += 1
    tag = tag or f"c{counter_c[0]}"
    objs, rec = TMP / (tag + ".json"), TMP / (tag + ".argv")
    objs.write_text(json.dumps(items_of(rows if rows is not None else BASE)))
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", STUB_OBJECTS=str(objs), STUB_REC=str(rec), STUB_MODE=mode,
               STUB_CTX=ctx, STUB_SERVER=srv)
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
    calls = [json.loads(l) for l in rec.read_text().splitlines()] if rec.exists() else []
    out = TMP / (tag + ".out"); out.write_text(r.stdout)
    return r, calls, out

def collector_proof(script):
    """The collector's verdicts. Returns {check: bool}; all True for the real script, a corrupted one must lose at least one."""
    res = {}
    r, calls, out = collect(script, BASE)
    res["the three kubectl calls are exactly: current-context; --context C config view --minify server; --context C get secret -A -o jsonpath=<template>"] = calls == EXPECTED_CALLS
    res["output starts with the #CLUSTER identity header and ends with the #END trailer"] = r.stdout.splitlines()[:1] == [HEAD] and r.stdout.splitlines()[-1:] == [f"#END rows={len(BASE)}"]
    res["converged synthetic Secrets => D2 GREEN"] = r.returncode == 0 and run([out, "--anchor", "database/postgres-credentials"])[0] == 0
    mirror = BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True", ver="7", at="2026-01-01T00:00:00Z")]
    r, calls, out = collect(script, mirror)
    res["mirror survivor annotations come through => D2 RED"] = run([out] + ANCHOR)[0] == 1
    flipped = [x.replace("|false|false|", "|true|true|") if x.startswith("database|postgres-credentials") else x for x in BASE]
    r, calls, out = collect(script, flipped)
    res["source flags true come through => D2 RED"] = run([out] + ANCHOR)[0] == 1
    r, calls, out = collect(script, BASE, ctx="other-ctx", srv="https://other.invalid:6443")
    res["the identity written is the one kubectl reported (a different cluster => D2 UNKNOWN against fixture-ctx)"] = r.returncode == 0 and run([out] + ANCHOR)[0] == 2
    return res

good = collector_proof(COLLECT)
for k, v in good.items(): report("C1 " + k, v)
if REAL_KUBECTL:
    # Cross-check the template against the REAL kubectl JSONPath engine (no cluster: --local on a file). kubectl applies
    # the template to each object separately, so the per-object body is compared, not the range wrapper.
    items = items_of(BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True", ver="7", at="2026-01-01T00:00:00Z")])
    f = TMP / "real.json"; f.write_text(json.dumps(items))
    body_jp = EXPECTED_JP[len("{range .items[*]}"):-len("{end}")]
    r = subprocess.run([REAL_KUBECTL, "annotate", "--local", "-f", str(f), "zz=1", "--overwrite", "-o", "jsonpath=" + body_jp],
                       env=dict(os.environ, KUBECONFIG=os.devnull), capture_output=True, text=True)
    r2, _, _ = collect(COLLECT, BASE + [row("admins", "postgres-credentials", reflects="database/postgres-credentials", autoref="True", ver="7", at="2026-01-01T00:00:00Z")])
    ok = r.returncode == 0 and r.stdout == "\n".join(r2.stdout.splitlines()[1:-1]) + "\n"
    report("C2 REAL kubectl (%s) parses the collector's JSONPath and returns the same rows as the evaluator" % REAL_KUBECTL, ok, f"rc={r.returncode}\n{r.stderr[-400:]}\nreal={r.stdout[-300:]!r}")
    # the trap agy worried about: unescaped dots do NOT address the map key, kubectl silently returns empty
    bad_body = body_jp.replace("\\.", ".")
    rb = subprocess.run([REAL_KUBECTL, "annotate", "--local", "-f", str(f), "zz=1", "--overwrite", "-o", "jsonpath=" + bad_body],
                        env=dict(os.environ, KUBECONFIG=os.devnull), capture_output=True, text=True)
    report("C3 REAL kubectl: unescaped dots silently return empty annotations (why the escaping is load-bearing)", rb.returncode == 0 and "database/postgres-credentials" not in rb.stdout, rb.stdout[-200:])
    # identity commands against the REAL kubectl and a synthetic two-context kubeconfig (no cluster is contacted)
    kc = TMP / "kc.yaml"
    kc.write_text("apiVersion: v1\nkind: Config\ncurrent-context: ctx-a\n"
                  "clusters:\n- name: cl-a\n  cluster: {server: 'https://127.0.0.1:1'}\n- name: cl-b\n  cluster: {server: 'https://b.invalid:6443'}\n"
                  "users:\n- name: u\n  user: {}\n"
                  "contexts:\n- name: ctx-a\n  context: {cluster: cl-a, user: u}\n- name: ctx-b\n  context: {cluster: cl-b, user: u}\n")
    kenv = dict(os.environ, KUBECONFIG=str(kc))
    rc1 = subprocess.run([REAL_KUBECTL, "config", "current-context"], env=kenv, capture_output=True, text=True)
    rs = subprocess.run([REAL_KUBECTL, "--context", "ctx-b", "config", "view", "--minify", "-o", SRV_JP], env=kenv, capture_output=True, text=True)
    report("C4 REAL kubectl: `config current-context` and the pinned `--context ctx-b config view --minify` return the context and ITS server",
           rc1.stdout.strip() == "ctx-a" and rs.stdout == "https://b.invalid:6443", f"{rc1.stdout!r} {rs.stdout!r} {rs.stderr[-200:]}")
    # C5 is opt-in: kubectl's behaviour against a dead endpoint (127.0.0.1:1) varies between instant failure and a ~90 s
    # retry loop on this machine, which must never stall CI or a parallel mutation run.
    if os.environ.get("D2_TEST_REAL_E2E"):
        try: rcol = subprocess.run(["bash", str(COLLECT)], env=kenv, capture_output=True, text=True, timeout=150)
        except subprocess.TimeoutExpired: rcol = subprocess.CompletedProcess([], 124, "", "timeout")
        report("C5 REAL kubectl, unreachable server (127.0.0.1:1): collector fails and writes neither header nor trailer (D2 would read UNKNOWN)",
               rcol.returncode != 0 and "#END" not in rcol.stdout and "#CLUSTER" not in rcol.stdout, f"rc={rcol.returncode} out={rcol.stdout!r}")
    else:
        print("SKIP  C5 real-kubectl unreachable-server run (opt-in: D2_TEST_REAL_E2E=1)")
else:
    print("SKIP  C2-C5 real kubectl not found on PATH: JSONPath and identity commands checked by the in-test stub only (NOT against client-go)")

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
mutate("drop-context-pin-get", '--context "$ctx" get secret', "get secret")
mutate("drop-context-pin-view", '--context "$ctx" config view', "config view")
mutate("header-wrong-field", "'#CLUSTER context=%s server=%s\\n' \"$ctx\" \"$srv\"", "'#CLUSTER context=%s server=%s\\n' \"$srv\" \"$ctx\"")
mutate("drop-header", "printf '#CLUSTER context=%s server=%s\\n' \"$ctx\" \"$srv\"\n", "")
mutate("header-before-get", "out=$(kubectl", "printf '#CLUSTER context=%s server=%s\\n' \"$ctx\" \"$srv\"; out=$(kubectl")

# failure behaviour, end to end into D2
r, calls, out = collect(COLLECT, BASE, mode="fail")
report("E1 kubectl failure: collector exits with kubectl's rc 3 and prints NO trailer and NO header", r.returncode == 3 and "#END" not in r.stdout and "#CLUSTER" not in r.stdout, f"rc={r.returncode} out={r.stdout!r}")
expect("E2 ...and D2 reads that output as UNKNOWN, never GREEN", [out], 2)
r, calls, out = collect(COLLECT, BASE, mode="truncate")
report("E3 kubectl dies mid-stream: collector fails, no trailer, no header", r.returncode == 1 and "#END" not in r.stdout and "#CLUSTER" not in r.stdout, f"rc={r.returncode}")
expect("E4 ...and D2 reads the partial output as UNKNOWN", [out], 2)
r, calls, out = collect(COLLECT, [])
report("E5 no Secrets at all: trailer says rows=0", r.returncode == 0 and "#END rows=0" in r.stdout, r.stdout)
expect("E6 ...and D2 reads that as UNKNOWN (never as 0 found)", [out], 2)
r, calls, out = collect(COLLECT, BASE, mode="ctxfail")
report("E8 `current-context` fails: collector exits with its rc 5, no output, no further kubectl call", r.returncode == 5 and r.stdout == "" and len(calls) == 1, f"rc={r.returncode} calls={calls}")
r, calls, out = collect(COLLECT, BASE, mode="srvfail")
report("E9 server lookup fails: collector exits with its rc 6, no output, Secrets never fetched", r.returncode == 6 and r.stdout == "" and all("get" not in c for c in calls), f"rc={r.returncode} calls={calls}")
r, calls, out = collect(COLLECT, BASE, srv="https://bad server:6443")
report("E10 whitespace in the server name: collector refuses (rc 1, no output)", r.returncode == 1 and r.stdout == "", f"rc={r.returncode} out={r.stdout!r}")
code_text = "\n".join(l for l in real_text.splitlines() if not l.lstrip().startswith("#"))
report("E7 collector code never writes Secret data (no .data, no -o yaml/json; comments excluded)", not re.search(r"\.data\b|-o\s*(yaml|json)\b|--output", code_text) and "-o jsonpath" in code_text, "")
report("E11 collector comments do not claim the Secret data is never read", "never reads" not in real_text.lower() and "kubectl itself still fetches" in real_text, "")


# ---------------------------------------------------------------- mutation-matrix closure (PR #2553 round 3)
print("== D2 gaps found by the full mutation matrix ==")
rc, out = d2.evaluate([HEAD + "\n", "a|b||||||\r\n", "x|y|||||| \rz\n", "#END rows=2\n"], 0, (), expect={"context": "fixture-ctx"})
report("Y1 a carriage return INSIDE a row (reachable through evaluate(), not through readlines) is UNKNOWN with its reason", rc == 2 and "carriage return" in out[0], f"{rc} {out}")
expect("Y2 whitespace-only reflects value is a marker with an unreadable source: UNKNOWN (not absent)", [listing("y2", BASE + [row("zz", "x", reflects=" ")]), "--no-anchor"], 2)
expect("Y3 reflects with surrounding blanks is not a readable source: UNKNOWN", [listing("y3", BASE + [row("zz", "x", reflects=" database/postgres-credentials ")]), "--no-anchor"], 2)
rc, out = run([CONVERGED, "--expect-context", "", "--expect-server", "https://fixture.invalid:6443"], exp=False)
report("Y4 --expect-context with an empty value is a bad argument even when --expect-server is given", rc == 2 and "bad argument" in out, out)
rc, out = run([CONVERGED, "--source", "bare"])
report("Y5 bad argument prints its reason", rc == 2 and "bad argument" in out, out)

ROWS_AL = [HEAD, "argo|x||||||", "other|x||||||"]
ROWS_AL.append(f"#END rows={len(ROWS_AL) - 1}")
rc, out = d2.evaluate(ROWS_AL, 0, (), allow={("argo", "x")}, expect={"context": "fixture-ctx"})
report("Y6 a non-annotated copy of an allow-listed name in another namespace is RED (allow-listed names are copy-checked too)", rc == 1 and "copy" in out[0], f"{rc} {out}")

print("== D2 round 2b: argv edges and output truncation ==")
expect("A1 --expect-context as the last argument has no value: UNKNOWN", [CONVERGED] + ANCHOR + ["--expect-context"], 2, exp=False)
expect("A2 --expect-server followed by an option instead of a value: UNKNOWN", [CONVERGED] + ANCHOR + ["--expect-server", "--no-anchor"], 2, exp=False)
expect("A3 a positional rc followed by another option is parsed and the option still applies (rc 1 -> UNKNOWN)", [CONVERGED, 1, "--anchor", "database/postgres-credentials"], 2)
expect("A4 --source without a slash: UNKNOWN", [CONVERGED] + ANCHOR + ["--source", "noslash"], 2)
expect("A5 --anchor and --no-anchor together: UNKNOWN", [CONVERGED] + ANCHOR + ["--no-anchor"], 2)
expect("A6 non-numeric positional rc: UNKNOWN", [CONVERGED, "zz"] + ANCHOR, 2)
many_red = listing("t_red", BASE + [row("zz%d" % i, "n%d" % i, allowed="true") for i in range(14)])
rc, out = run([many_red] + ANCHOR)
report("T1 RED prints at most 10 findings and counts all", rc == 1 and out.count("not provably") + out.count("allowed") >= 1 and "findings=14" in out
       and sum(1 for l in out.splitlines() if l.startswith("   ")) == 10, out[-400:])
mixed = listing("t_mix", BASE + [row("zz%d" % i, "n%d" % i, allowed="true") for i in range(6)] + [row("zq", "x", at="2026-11-09T10:00:00Z")])
rc, out = run([mixed] + ANCHOR)
report("T2 UNKNOWN outranks RED and shows the unknown reason plus at most 3 reds", rc == 2 and "findings=4" in out, out[-400:])

rc, out = run([CONVERGED] + ANCHOR + ["--expect-context"], exp=False)
report("A7 --expect-context as the last argument is reported as a bad argument", rc == 2 and "bad argument" in out, out[-300:])
rc, out = run([post_row5, 0, "--no-anchor"])
report("A8 a positional rc followed by --no-anchor: both are consumed (GREEN without the default anchor)", rc == 0, out[-300:])

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nchecks={counter[0]} failures={len(failures)}")
for f in failures:
    print("FAILED:", f)
sys.exit(1 if failures else 0)
