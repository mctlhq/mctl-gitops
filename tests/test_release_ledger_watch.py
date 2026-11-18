"""Release ledger watch (mctlhq/mctl-api#1022 S4b).

After each push to main, release-gate-watch asks the release ledger whether a
write of a ledger-held image was approved:
`python3 tests/test_release_ledger_watch.py`.

  release-gate.py ledger_changes   which held images the push wrote (git, policy
                                   read from the parent)
  release-ledger-shadow.py         watch_verdict (one write against the ledger)
                                   and watch (exit codes, shadow vs enforce)

No network: the ledger and the registry are injected. Every negative case is
mutation-verified: MUTANTS lists one deliberate break per rule, applied to the
script it names, and each must turn at least one case red.
"""
import atexit
import contextlib
import copy
import datetime
import importlib.util
import io
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import types
import urllib.error

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE_SCRIPT = ROOT / "scripts/release-gate.py"
LEDGER_SCRIPT = ROOT / "scripts/release-ledger-shadow.py"
GATE = "platform-gitops/release-gates.yaml"
API = "platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml"
LIVE_API = (ROOT / API).read_text()
_m = re.search(r"repository: ghcr\.io/mctlhq/mctl-api\n(\s+)(tag: [^\n]+)", LIVE_API)
assert _m, "no mctl-api image tag in the bootstrap file"
IND = _m.group(1)


def api(tag, digest=None):
    line = f'tag: "{tag}"' + (f'\n{IND}digest: "{digest}"' if digest else "")
    return LIVE_API.replace(_m.group(2), line)


IMG, R = "ghcr.io/mctlhq/mctl-api", "mctlhq/mctl-api"
V = "4.200.0"
D1, D2 = "sha256:" + "a" * 64, "sha256:" + "b" * 64
C1, C2 = "c" * 40, "d" * 40
NOW = datetime.datetime(2026, 11, 18, tzinfo=datetime.timezone.utc)
_WORK = pathlib.Path(tempfile.mkdtemp(prefix="ledger-watch-test-"))
atexit.register(shutil.rmtree, _WORK, ignore_errors=True)
_n = [0]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# -- ledger_changes (release-gate.py), against real git repos -----------------

def policy(mode="enforce"):
    pol = copy.deepcopy(yaml.safe_load((ROOT / GATE).read_text()))
    h = [x for x in pol["version_holds"] if x["repository"] == IMG][0]
    if mode is None:
        h.pop("ledger", None)
    else:
        h["ledger"] = {"mode": mode, "wait_minutes": 60, "bump_pr_author": "mctl-gitops-pr[bot]",
                       "bump_pr_branch_prefix": "release-bump/"}
    return pol


def git(d, *args):
    return subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@t",
                               "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}).stdout.strip()


def repo(base_pol, base_api, head_pol, head_api):
    _n[0] += 1
    d = _WORK / f"r{_n[0]}"
    revs = []
    for pol, text in ((base_pol, base_api), (head_pol, head_api)):
        for rel, content in ((GATE, None if pol is None else yaml.safe_dump(pol)), (API, text)):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            if content is None:
                (d / rel).unlink(missing_ok=True)
            else:
                (d / rel).write_text(content)
        if not revs:
            git(d, "init", "-q")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "c", "--allow-empty")
        revs.append(git(d, "rev-parse", "HEAD"))
    return d, revs[0], revs[1]


def changes_cases(gate_mod):
    def lc(base_pol, base_api, head_pol, head_api):
        d, b, h = repo(base_pol, base_api, head_pol, head_api)
        ch, unk = gate_mod.ledger_changes(d, b, h)
        return [(c["mode"], c["version"], c["digest"], c["old_version"]) for c in ch], [m for m, _ in unk]

    out = []
    enf = policy("enforce")
    out.append(("changes: an unchanged tag is the deployed state, not a write",
                lc(enf, api("4.160.0"), enf, api("4.160.0")), ([], [])))
    out.append(("changes: a tag write under an enforced hold is reported, no digest pinned",
                lc(enf, api("4.160.0"), enf, api(V)), ([("enforce", V, None, "4.160.0")], [])))
    out.append(("changes: a pinned digest is handed over",
                lc(enf, api("4.160.0"), enf, api(V, D1)), ([("enforce", V, D1, "4.160.0")], [])))
    out.append(("changes: a digest-only write is a write",
                lc(enf, api(V), enf, api(V, D1)), ([("enforce", V, D1, V)], [])))
    out.append(("changes: a write below held_from is not held",
                lc(enf, api("4.160.0"), enf, api("4.100.0")), ([], [])))
    out.append(("changes: shadow mode is reported as shadow",
                lc(policy("shadow"), api("4.160.0"), policy("shadow"), api(V)), ([("shadow", V, None, "4.160.0")], [])))
    out.append(("changes: a hold without a ledger block is not the watch's",
                lc(policy(None), api("4.160.0"), policy(None), api(V)), ([], [])))
    out.append(("changes: the policy is read from the parent, not the push",
                lc(enf, api("4.160.0"), policy(None), api(V)), ([("enforce", V, None, "4.160.0")], [])))
    out.append(("changes: an unreadable pushed file is unknown, with the hold's mode",
                lc(enf, api("4.160.0"), enf, "not yaml: ["), ([], ["enforce"])))
    out.append(("changes: a removed held file is unknown, not 'no change'",
                lc(enf, api("4.160.0"), enf, None), ([], ["enforce"])))
    out.append(("changes: a pushed tag that is not X.Y.Z is unknown, not skipped",
                lc(enf, api("4.160.0"), enf, api("latest")), ([], ["enforce"])))
    out.append(("changes: a policy absent at the parent is unknown with no mode",
                lc(None, api("4.160.0"), enf, api(V)), ([], [None])))
    d, b, _ = repo(enf, api("4.160.0"), enf, api(V))
    try:
        got = gate_mod.ledger_changes(d, b, "f" * 40)
        got = ([], [m for m, _ in got[1]])
    except Exception as exc:  # noqa: BLE001
        got = type(exc).__name__
    out.append(("changes: an unreadable pushed commit is unknown, never raised or clean", got, ([], ["enforce"])))
    return out


# -- judge_ledger (historical), watch_verdict and watch (release-ledger-shadow.py)

def grant(state="approved", digest=D1, commit=C1, amr=("mfa", "user"), expires="2026-11-20T09:14:30Z",
          consumed=None, decision=True, gid="aar_1"):
    g = {"approval": {"id": gid, "state": state, "expires_at": expires},
         "artifact": {"repository": R, "version": V, "tag_commit": commit, "image_digest": digest}}
    if consumed:
        g["approval"]["consumed_at"] = consumed
    if decision and state in ("approved", "rejected"):
        g["decision"] = {"amr": list(amr)}
    return g


def body(*grants):
    return {"schema_version": "1", "repository": R, "version": V, "grants": list(grants)}


def ledger_cases(m):
    def j(b, commit=None, historical=True):
        return m.judge_ledger(b, R, V, D1, commit, NOW, historical=historical)[0]

    expired, consumed = grant(expires="2026-11-17T00:00:00Z"), grant(consumed="2026-11-17T10:00:00Z")
    out = [
        ("judge: an expired MFA approval still approved the write", j(body(expired)), m.ALLOW),
        ("judge: a consumed MFA approval still approved the write", j(body(consumed)), m.ALLOW),
        ("judge: gate mode still refuses an expired approval", j(body(expired), C1, False), m.REFUSE),
        ("judge: gate mode still refuses a consumed approval", j(body(consumed), C1, False), m.REFUSE),
        ("judge: a rejection outranks an approval", j(body(grant(), grant(state="rejected", gid="aar_2"))), m.REFUSE),
        ("judge: an approval without MFA does not count", j(body(grant(amr=("pwd",)))), m.REFUSE),
        ("judge: an approval of another digest does not count", j(body(grant(digest=D2))), m.REFUSE),
        ("judge: without a commit any tag commit of this digest counts", j(body(grant(commit=C2))), m.ALLOW),
        ("judge: gate mode still binds the commit", j(body(grant(commit=C2)), C1, False), m.REFUSE),
        ("judge: pending decides nothing", j(body(grant(state="pending"))), m.REFUSE),
        ("judge: no decision evidence is unknown", j(body(grant(decision=False))), m.UNKNOWN),
        ("judge: a malformed answer is unknown", j({"repository": R, "version": V}), m.UNKNOWN),
    ]

    resolved = []

    def wv(change, read=lambda r, v: body(grant()), resolve=lambda i, t: resolved.append(t) or D1):
        return m.watch_verdict({"repository": IMG, "version": V, "digest": None, **change}, read, resolve, NOW)[0]

    def boom(*_a):
        raise OSError("down")

    def http(*_a):
        raise urllib.error.HTTPError("u", 403, "x", {}, None)

    out += [
        ("verdict: pinned approved digest allows", wv({"digest": D1}), m.ALLOW),
        ("verdict: a pinned digest is not looked up in the registry", (wv({"digest": D1}), resolved[:]),
         (m.ALLOW, [])),
        ("verdict: no pin, the registry digest is judged", wv({}), m.ALLOW),
        ("verdict: no pin, a registry digest nobody approved refuses", wv({}, resolve=lambda i, t: D2), m.REFUSE),
        ("verdict: pinned digest nobody approved refuses", wv({"digest": D2}), m.REFUSE),
        ("verdict: an unreadable registry is unknown", wv({}, resolve=boom), m.UNKNOWN),
        ("verdict: a malformed registry digest is unknown", wv({}, resolve=lambda i, t: "sha256:x"), m.UNKNOWN),
        ("verdict: an unreadable ledger is unknown", wv({"digest": D1}, read=boom), m.UNKNOWN),
        ("verdict: a refused ledger read is unknown", wv({"digest": D1}, read=http), m.UNKNOWN),
        ("verdict: a malformed pinned digest refuses", wv({"digest": "sha256:x"}), m.REFUSE),
        ("verdict: an image outside ghcr.io cannot be named", wv({"repository": "docker.io/x/y"}), m.UNKNOWN),
    ]

    def route(changes=(), unk=(), read=lambda r, v: body(grant()), base=C1, raises=False):
        saved = {k: getattr(m, k) for k in ("_release_gate", "_read_ledger", "_registry_digest")}
        reads = []

        def lc(_root, _b, _h):
            if raises:
                raise OSError("git down")
            return [dict(c) for c in changes], list(unk)
        m._release_gate = lambda: types.SimpleNamespace(ledger_changes=lc)
        m._read_ledger = lambda r, v: reads.append(v) or read(r, v)
        m._registry_digest = lambda i, t: D1
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = m.watch(types.SimpleNamespace(base=base, head=C2))
            return rc, len(reads)
        finally:
            for k, v in saved.items():
                setattr(m, k, v)

    def ch(mode="enforce", digest=None):
        return {"mode": mode, "hold": "h", "repository": IMG, "version": V, "digest": digest, "old_version": "4.160.0"}

    rej = lambda r, v: body(grant(state="rejected"))  # noqa: E731

    def down(*_a):
        raise OSError("down")
    out += [
        ("watch: no held write, nothing read, pass", route(), (0, 0)),
        ("watch: enforced write with an approval passes", route([ch()]), (0, 1)),
        ("watch: enforced write without an approval is a violation", route([ch()], read=rej), (6, 1)),
        ("watch: enforced write with an unreadable ledger is unknown", route([ch()], read=down), (7, 1)),
        ("watch: shadow write without an approval only reports", route([ch("shadow")], read=rej), (0, 1)),
        ("watch: shadow write with an unreadable ledger only reports", route([ch("shadow")], read=down), (0, 1)),
        ("watch: shadow file unreadable only reports", route(unk=[("shadow", "x")]), (0, 0)),
        ("watch: enforced file unreadable is unknown", route(unk=[("enforce", "x")]), (7, 0)),
        ("watch: an unreadable policy is unknown", route(unk=[(None, "x")]), (7, 0)),
        ("watch: unknown outranks a violation", route([ch(), ch(digest="sha256:x")], read=down), (7, 1)),
        ("watch: a violation is not hidden by an approved write", route([ch(digest=D2), ch()]), (6, 2)),
        ("watch: a failed git read is unknown", route([ch()], raises=True), (7, 0)),
        ("watch: a malformed base is unknown, not clean", route([ch()], base="0"), (7, 0)),
    ]
    return out


GATE_MUTANTS = {
    "policy read from the push": ("        raw = _blob(repo, base, GATE)\n        if raw is None:\n            return [], [(None",
                                  "        raw = _blob(repo, head, GATE)\n        if raw is None:\n            return [], [(None"),
    "unchanged image reported as a write": ("        if new == old:\n            continue", "        if False:\n            continue"),
    "digest-only write ignored": ("        if new == old:\n            continue",
                                  "        if new[0] == old[0]:\n            continue"),
    "held_from ignored": ("        if v >= _semver(h[\"held_from\"]):", "        if True:"),
    "unreadable file is no change": ("            unk.append((led[\"mode\"], f\"{h['name']}: {h['file']} image unreadable",
                                     "            None and unk.append((led[\"mode\"], f\"{h['name']}: {h['file']} image unreadable"),
    "non-semver pushed tag skipped": ("            unk.append((led[\"mode\"], f\"{h['name']}: pushed tag {new[0]!r} is not X.Y.Z\"))",
                                      "            pass"),
    "pinned digest dropped": ("    return tag, digest or None", "    return tag, None"),
}

LEDGER_MUTANTS = {
    "historical mode ignored": ("            if historical:\n                approved.append",
                                "            if False:\n                approved.append"),
    "gate mode weakened to historical": ("            if historical:\n                approved.append",
                                         "            if True:\n                approved.append"),
    "commit never bound": ("(commit is not None and art.get(\"tag_commit\") != commit)", "False"),
    "rejection does not outrank approval": ("    if refused:\n        # A rejection", "    if False:\n        # A rejection"),
    "registry read error is a refusal": ("            return UNKNOWN, f\"registry digest of {image}:{version} unreadable",
                                         "            return REFUSE, f\"registry digest of {image}:{version} unreadable"),
    "registry digest not checked": ("        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):\n            return UNKNOWN",
                                    "        if False:\n            return UNKNOWN"),
    "ledger read error is a refusal": ("        return UNKNOWN, f\"ledger read failed: {type(exc).__name__}: {exc}\"\n    verdict",
                                       "        return REFUSE, f\"ledger read failed: {type(exc).__name__}: {exc}\"\n    verdict"),
    "pinned digest ignored": ("    digest = change.get(\"digest\")\n    if digest is None:",
                              "    digest = None\n    if digest is None:"),
    "shadow fails the watch": ("    enforced = [v for m, _, v, _ in rows if m == \"enforce\"]",
                               "    enforced = [v for m, _, v, _ in rows]"),
    "unreadable policy treated as shadow": ("rows.append((mode or \"enforce\",", "rows.append((mode or \"shadow\","),
    "unknown does not fail": ("    if UNKNOWN in enforced:\n        return 7", "    if False:\n        return 7"),
    "refusal does not fail": ("    if REFUSE in enforced:\n        return 6", "    if False:\n        return 6"),
    "failed git read is clean": ("UNKNOWN: {type(exc).__name__}: {exc}\", file=sys.stderr)\n        return 7",
                                 "UNKNOWN: {type(exc).__name__}: {exc}\", file=sys.stderr)\n        return 0"),
    "malformed base accepted": ("            print(f\"::error::bad --{name} {getattr(args, name)!r}\", file=sys.stderr)\n            return 7",
                                "            print(f\"::error::bad --{name} {getattr(args, name)!r}\", file=sys.stderr)\n            continue"),
}


def wiring():
    wf = yaml.safe_load((ROOT / ".github/workflows/release-gate-watch.yml").read_text())
    job = wf["jobs"]["ledger"]
    steps = {s.get("id"): s for s in job["steps"] if s.get("id")}
    led = steps.get("ledger", {})
    am = (ROOT / ".github/workflows/auto-merge.yml").read_text()
    vm = (ROOT / ".github/workflows/validate-manifests.yml").read_text()
    on = wf.get(True) or wf.get("on")
    return [
        ("wiring: the job may request an OIDC token", job.get("permissions", {}).get("id-token"), "write"),
        ("wiring: the ledger job runs only on a push (mctl-api refuses other events' tokens)",
         job.get("if", "").strip() == "github.event_name == 'push'", True),
        ("wiring: the ledger step runs watch on the pushed range",
         'release-ledger-shadow.py watch --base "$BEFORE" --head "$SHA"' in led.get("run", ""), True),
        ("wiring: a change to the ledger script runs the watch on its PR",
         "scripts/release-ledger-shadow.py" in on["pull_request"]["paths"], True),
        ("wiring: the ledger script is an auto-merge protected path",
         "^scripts/release-ledger-shadow\\.py$" in am, True),
        ("wiring: validate runs this test", "python3 tests/test_release_ledger_watch.py" in vm, True),
    ]


def run_cases(gate_path, ledger_path):
    gate_mod = load(gate_path, f"rg{abs(hash(str(gate_path)))}")
    led_mod = load(ledger_path, f"rl{abs(hash(str(ledger_path)))}")
    return changes_cases(gate_mod) + ledger_cases(led_mod)


def main() -> int:
    cases = run_cases(GATE_SCRIPT, LEDGER_SCRIPT) + wiring()
    bad = [(n, a, e) for n, a, e in cases if a != e]
    for n, a, e in bad:
        print(f"FAIL {n}: got {a}, want {e}")
    missed = []
    # Each mutant runs the cases of the script it breaks (the other script's
    # cases cannot see it). No except: a mutant must be caught by a case going
    # red, not by crashing the harness, which would hide one that applies wrongly.
    for script, muts, suite in ((GATE_SCRIPT, GATE_MUTANTS, changes_cases),
                                (LEDGER_SCRIPT, LEDGER_MUTANTS, ledger_cases)):
        src = script.read_text()
        for name, (old, new) in muts.items():
            assert src.count(old) == 1, f"mutant {name!r} does not apply ({src.count(old)} matches)"
            mpath = _WORK / f"m{abs(hash(name))}.py"
            mpath.write_text(src.replace(old, new))
            if all(a == e for _, a, e in suite(load(mpath, f"m{abs(hash(name))}"))):
                missed.append(name)
    for name in missed:
        print(f"FAIL mutant survived: {name}")
    n_mut = len(GATE_MUTANTS) + len(LEDGER_MUTANTS)
    print(f"ledger watch: {len(cases) - len(bad)}/{len(cases)} cases, {n_mut - len(missed)}/{n_mut} mutants caught")
    return 1 if bad or missed else 0


if __name__ == "__main__":
    sys.exit(main())
