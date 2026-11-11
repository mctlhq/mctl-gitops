"""Proof both ways for scripts/check-ruleset-bypass-actors.py (#2543).

Green on a converged input AND red on each deliberate mutation: a bypass actor
with a null or non-integer actor_id, an extra actor, an actor in the wrong
mode, an expired transitional entry, the main-protection ruleset gone or
disabled. A failed, partial, malformed or permission-trimmed read must end in
UNKNOWN (20), never in clean, and UNKNOWN outranks a finding.

The recorded live snapshot (scripts/tests/fixtures/ruleset-bypass/) must stay
red against the committed allowlist until the DeployKey entry is removed.

Run: python3 -I tests/test_ruleset_bypass_check.py (from the repository root)
"""
import copy
import datetime
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/check-ruleset-bypass-actors.py"
spec = importlib.util.spec_from_file_location("bypass_check", SCRIPT)
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)

failures = []
TODAY = datetime.date(2026, 11, 11)
REPO = "mctlhq/mctl-gitops"
LIST = f"/repos/{REPO}/rulesets?includes_parents=true&per_page=100"
LIVE = ROOT / "scripts/tests/fixtures/ruleset-bypass/live-2026-11-11.json"
BUMP_APP = 1000001   # synthetic App ids: the real ones do not exist yet
ARGO_APP = 1000002


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:600]}")


def ruleset(rid, name, actors, enforcement="active", include=("refs/heads/main",)):
    return {"id": rid, "name": name, "target": "branch", "enforcement": enforcement,
            "bypass_actors": actors,
            "conditions": {"ref_name": {"include": list(include), "exclude": []}},
            "rules": [{"type": r, **({"parameters": copy.deepcopy(PARAMS[r])} if r in PARAMS else {})} for r in RULES]}


def integ(app_id, mode="always"):
    return {"actor_id": app_id, "actor_type": "Integration", "bypass_mode": mode}


RULES = ["deletion", "non_fast_forward", "pull_request", "required_status_checks"]
PARAMS = {"pull_request": {"required_approving_review_count": 1},
          "required_status_checks": {"required_status_checks": [
              {"context": c, "integration_id": 15368} for c in ("cloudflare-plan", "reserved-hosts", "validate")]}}
DEPLOY_KEY = {"actor_id": None, "actor_type": "DeployKey", "bypass_mode": "always"}


def world(protection_actors, extra=None):
    """A converged repository: main-protection plus the disabled legacy `main` ruleset."""
    doc = {
        LIST: [{"id": 14564982, "name": "main", "target": "branch", "enforcement": "disabled"},
               {"id": 18465404, "name": "main-protection", "target": "branch", "enforcement": "active"}],
        f"/repos/{REPO}/rulesets/14564982": ruleset(14564982, "main", [], "disabled", ("~DEFAULT_BRANCH",)),
        f"/repos/{REPO}/rulesets/18465404": ruleset(18465404, "main-protection", protection_actors),
    }
    if extra:
        doc.update(extra)
    return doc


def allow(*entries, rules=RULES):
    return {"rulesets": {"18465404": {"name": "main-protection", "required_rules": list(rules),
                                      "min_approving_review_count": 1,
                                      "required_status_checks": [
                                          {"context": c, "integration_id": 15368}
                                          for c in ("validate", "reserved-hosts", "cloudflare-plan")],
                                      "bypass_actors": list(entries)}}}


ALLOW_TARGET = allow({"actor_type": "Integration", "actor_id": BUMP_APP, "bypass_mode": "always",
                      "label": "gitops-bump-writer"})


def run(doc, allowlist=ALLOW_TARGET, fetcher=None):
    f, u, o = C.scan("t", allowlist, fetcher or C.fixture_fetcher(doc), REPO, TODAY)
    return C.verdict(f, u), f, u, o


# 1. Converged target state is clean.
code, f, u, o = run(world([integ(BUMP_APP)]))
check("converged: one allowlisted App bypass actor -> clean", code == 0 and not f and not u, f"{code} {f} {u}")
check("converged: every listed ruleset was read", o == [14564982, 18465404], o)

code, f, u, o = run(world([]), allow())
check("converged: empty bypass list, empty allowlist -> clean", code == 0, f"{code} {f} {u}")

# 2. Mutations: each must be red (10).
code, f, u, _ = run(world([DEPLOY_KEY]))
check("MUTATION DeployKey with actor_id null -> findings",
      code == 10 and any("actor_id None" in x for x in f), f"{code} {f}")

code, f, u, _ = run(world([integ(BUMP_APP), DEPLOY_KEY]),
                    allow({"actor_type": "Integration", "actor_id": BUMP_APP, "bypass_mode": "always"},
                          {"actor_type": "Integration", "actor_id": ARGO_APP, "bypass_mode": "always"}))
check("MUTATION null actor next to an allowlisted one, count within allowlist -> findings",
      code == 10 and any("actor_id None" in x for x in f), f"{code} {f}")

code, f, u, _ = run(world([integ(BUMP_APP), {"actor_id": "1000001", "actor_type": "Integration",
                                             "bypass_mode": "always"}]),
                    allow({"actor_type": "Integration", "actor_id": BUMP_APP, "bypass_mode": "always"},
                          {"actor_type": "Integration", "actor_id": ARGO_APP, "bypass_mode": "always"}))
check("MUTATION string actor_id -> findings", code == 10 and any("'1000001'" in x for x in f), f"{code} {f}")

code, f, u, _ = run(world([integ(BUMP_APP), {"actor_id": True, "actor_type": "Integration",
                                             "bypass_mode": "always"}]))
check("MUTATION boolean actor_id -> findings", code == 10, f"{code} {f}")

code, f, u, _ = run(world([integ(BUMP_APP), integ(ARGO_APP)]))
check("MUTATION extra actor beyond the allowlist -> findings",
      code == 10 and any("2 bypass actors, allowlist has 1" in x for x in f)
      and any(str(ARGO_APP) in x for x in f), f"{code} {f}")

code, f, u, _ = run(world([integ(BUMP_APP), integ(BUMP_APP)]))
check("MUTATION same allowlisted actor listed twice -> findings", code == 10, f"{code} {f}")

code, f, u, _ = run(world([integ(BUMP_APP), integ(BUMP_APP)]),
                    allow({"actor_type": "Integration", "actor_id": BUMP_APP, "bypass_mode": "always"},
                          {"actor_type": "Integration", "actor_id": ARGO_APP, "bypass_mode": "always"}))
check("MUTATION duplicate actor within the allowlist count cannot reuse one entry -> findings",
      code == 10 and any("not on the allowlist" in x for x in f), f"{code} {f}")

code, f, u, _ = run(world([integ(ARGO_APP)]))
check("MUTATION swapped actor, same count -> findings", code == 10 and any("not on the allowlist" in x for x in f),
      f"{code} {f}")

code, f, u, _ = run(world([integ(BUMP_APP, "exempt")]))
check("MUTATION allowlisted actor in another bypass_mode -> findings", code == 10, f"{code} {f}")

code, f, u, _ = run(world([{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"},
                           integ(BUMP_APP)]))
check("MUTATION admin role re-added -> findings", code == 10, f"{code} {f}")

expired = allow({"actor_type": "Integration", "actor_id": ARGO_APP, "bypass_mode": "always",
                 "label": "argo-writer (transitional)", "expires": "2026-11-10"})
code, f, u, _ = run(world([integ(ARGO_APP)]), expired)
check("MUTATION transitional entry past its expiry -> findings", code == 10 and any("expired" in x for x in f),
      f"{code} {f}")
code, f, u, _ = run(world([integ(ARGO_APP)]), allow(dict(expired["rulesets"]["18465404"]["bypass_actors"][0],
                                                       expires="2026-11-11")))
check("transitional entry on its expiry day -> clean", code == 0, f"{code} {f}")

doc = world([integ(BUMP_APP)])
doc[f"/repos/{REPO}/rulesets/14564982"]["bypass_actors"] = [DEPLOY_KEY]
code, f, u, _ = run(doc)
check("MUTATION bypass actor on another (non-allowlisted) ruleset -> findings",
      code == 10 and any("14564982" in x for x in f), f"{code} {f}")

doc = world([integ(BUMP_APP)])
doc[LIST] = doc[LIST] + [{"id": 99, "name": "org-wide", "target": "branch", "enforcement": "active"}]
doc[f"/repos/{REPO}/rulesets/99"] = ruleset(99, "org-wide", [integ(ARGO_APP)])
code, f, u, _ = run(doc)
check("MUTATION new ruleset carrying a bypass actor -> findings", code == 10 and any("ruleset 99" in x for x in f),
      f"{code} {f}")

doc = world([integ(BUMP_APP)])
doc[LIST] = [r for r in doc[LIST] if r["id"] != 18465404]
code, f, u, _ = run(doc)
check("MUTATION main-protection missing from a complete listing -> findings",
      code == 10 and any("not in the complete ruleset listing" in x for x in f), f"{code} {f}")

doc = world([integ(BUMP_APP)])
doc[f"/repos/{REPO}/rulesets/18465404"]["enforcement"] = "evaluate"
code, f, u, _ = run(doc)
check("MUTATION main-protection set to evaluate -> findings", code == 10, f"{code} {f}")

doc = world([integ(BUMP_APP)])
doc[f"/repos/{REPO}/rulesets/18465404"]["conditions"]["ref_name"]["include"] = ["refs/heads/other"]
code, f, u, _ = run(doc)
check("MUTATION main-protection no longer targets main -> findings", code == 10, f"{code} {f}")

for label, inc, exc in (("exclude refs/heads/main", ["refs/heads/main"], ["refs/heads/main"]),
                        ("exclude ~DEFAULT_BRANCH", ["~DEFAULT_BRANCH"], ["~DEFAULT_BRANCH"]),
                        ("exclude ~ALL", ["refs/heads/main"], ["~ALL"]),
                        ("exclude glob", ["~ALL"], ["refs/heads/ma*"])):
    doc = world([integ(BUMP_APP)])
    doc[f"/repos/{REPO}/rulesets/18465404"]["conditions"]["ref_name"] = {"include": inc, "exclude": exc}
    code, f, u, _ = run(doc)
    check(f"MUTATION main excluded ({label}) -> findings",
          code == 10 and any("does not cover" in x for x in f), f"{code} {f}")

for label, inc in (("refs/*", ["refs/*"]), ("refs/heads/*/x", ["refs/heads/*/x"]),
                   ("refs?heads/main", ["refs?heads/main"])):
    doc = world([integ(BUMP_APP)])
    doc[f"/repos/{REPO}/rulesets/18465404"]["conditions"]["ref_name"] = {"include": inc, "exclude": []}
    code, f, u, _ = run(doc)
    check(f"MUTATION include {label} (single * or ? does not cross /) -> findings",
          code == 10 and any("does not cover" in x for x in f), f"{code} {f}")

for label, inc in (("~ALL", ["~ALL"]), ("glob refs/heads/*", ["refs/heads/*"]), ("refs/**", ["refs/**"]),
                   ("~DEFAULT_BRANCH", ["~DEFAULT_BRANCH"])):
    doc = world([integ(BUMP_APP)])
    doc[f"/repos/{REPO}/rulesets/18465404"]["conditions"]["ref_name"] = {"include": inc, "exclude": []}
    code, f, u, _ = run(doc)
    check(f"include {label} still covers main -> clean", code == 0, f"{code} {f} {u}")

for gone in RULES:
    doc = world([integ(BUMP_APP)])
    d = doc[f"/repos/{REPO}/rulesets/18465404"]
    d["rules"] = [r for r in d["rules"] if r["type"] != gone]
    code, f, u, _ = run(doc)
    check(f"MUTATION rule {gone} removed -> findings", code == 10 and any(gone in x for x in f), f"{code} {f}")

doc = world([integ(BUMP_APP)])
doc[f"/repos/{REPO}/rulesets/18465404"]["rules"] = []
code, f, u, _ = run(doc)
check("MUTATION every rule removed -> findings", code == 10, f"{code} {f}")

doc = world([integ(BUMP_APP)])
for r in doc[f"/repos/{REPO}/rulesets/18465404"]["rules"]:
    if r["type"] == "pull_request":
        r["parameters"]["required_approving_review_count"] = 0
code, f, u, _ = run(doc)
check("MUTATION approvals lowered to 0 -> findings", code == 10 and any("approvals" in x for x in f), f"{code} {f}")

for ctx in ("validate", "reserved-hosts", "cloudflare-plan"):
    doc = world([integ(BUMP_APP)])
    for r in doc[f"/repos/{REPO}/rulesets/18465404"]["rules"]:
        if r["type"] == "required_status_checks":
            r["parameters"]["required_status_checks"] = [
                c for c in r["parameters"]["required_status_checks"] if c["context"] != ctx]
    code, f, u, _ = run(doc)
    check(f"MUTATION status check {ctx} dropped -> findings", code == 10 and any(ctx in x for x in f), f"{code} {f}")

for label, change in (("integration_id dropped", lambda c: c.pop("integration_id")),
                      ("integration_id changed", lambda c: c.update(integration_id=1))):
    doc = world([integ(BUMP_APP)])
    for r in doc[f"/repos/{REPO}/rulesets/18465404"]["rules"]:
        if r["type"] == "required_status_checks":
            for c in r["parameters"]["required_status_checks"]:
                if c["context"] == "validate":
                    change(c)
    code, f, u, _ = run(doc)
    check(f"MUTATION validate check {label} -> findings",
          code == 10 and any("'validate' from integration 15368" in x for x in f), f"{code} {f}")

code, f, u, _ = run(world([DEPLOY_KEY]), {"rulesets": {"18465404": {
    "bypass_actors": [], "required_status_checks": ["validate"]}}})
check("allowlist status check without integration_id -> unknown", code == 20, f"{code} {u}")

for label, mut in (("pull_request without parameters", lambda r: r.pop("parameters") if r["type"] == "pull_request" else None),
                   ("approval count not an int", lambda r: r["parameters"].update(required_approving_review_count="1")
                    if r["type"] == "pull_request" else None),
                   ("status checks not a list", lambda r: r["parameters"].update(required_status_checks="validate")
                    if r["type"] == "required_status_checks" else None)):
    doc = world([integ(BUMP_APP)])
    for r in doc[f"/repos/{REPO}/rulesets/18465404"]["rules"]:
        mut(r)
    code, f, u, _ = run(doc)
    check(f"malformed rule parameters ({label}) -> unknown", code == 20, f"{code} {u}")

# 3. Could not observe is UNKNOWN (20), never clean, and outranks findings.
doc = world([integ(BUMP_APP)])
del doc[f"/repos/{REPO}/rulesets/18465404"]["bypass_actors"]
code, f, u, _ = run(doc)
check("bypass_actors omitted (token cannot edit the ruleset) -> unknown, not 'none'",
      code == 20 and any("unobserved" in x for x in u), f"{code} {u}")

doc = world([DEPLOY_KEY])
del doc[f"/repos/{REPO}/rulesets/14564982"]["bypass_actors"]
code, f, u, _ = run(doc)
check("unknown outranks a finding", code == 20 and f and u, f"{code} {f} {u}")

doc = world([integ(BUMP_APP)])
del doc[f"/repos/{REPO}/rulesets/18465404"]
code, f, u, _ = run(doc)
check("detail read fails -> unknown", code == 20, f"{code} {u}")

doc = world([integ(BUMP_APP)])
del doc[LIST]
code, f, u, _ = run(doc)
check("listing read fails -> unknown, not 'no rulesets'", code == 20 and not f, f"{code} {f} {u}")

for label, body in (("not a list", {"message": "Not Found"}), ("entry without id", [{"name": "x"}]),
                    ("string id", [{"id": "18465404"}])):
    doc = world([integ(BUMP_APP)])
    doc[LIST] = body
    code, f, u, _ = run(doc)
    check(f"malformed listing ({label}) -> unknown", code == 20, f"{code} {u}")

for label, mut in (("bypass_actors not a list", lambda d: d.update(bypass_actors="DeployKey")),
                   ("actor without actor_type", lambda d: d.update(bypass_actors=[{"actor_id": 1}])),
                   ("detail for another id", lambda d: d.update(id=1)),
                   ("conditions missing", lambda d: d.pop("conditions")),
                   ("exclude not a list", lambda d: d["conditions"]["ref_name"].update(exclude="refs/heads/main")),
                   ("rules not a list", lambda d: d.update(rules="pull_request"))):
    doc = world([integ(BUMP_APP)])
    mut(doc[f"/repos/{REPO}/rulesets/18465404"])
    code, f, u, _ = run(doc)
    check(f"malformed detail ({label}) -> unknown", code == 20, f"{code} {u}")

for label, bad in (("no rulesets map", {}), ("DeployKey entry (null id)",
                   allow({"actor_type": "DeployKey", "actor_id": None, "bypass_mode": "always"})),
                   ("bad expiry", allow({"actor_type": "Integration", "actor_id": 1, "expires": "soon"})),
                   ("non-string expiry", allow({"actor_type": "Integration", "actor_id": 1, "expires": 20261201})),
                   ("required_rules not a list", {"rulesets": {"18465404": {"required_rules": "pull_request",
                                                                           "bypass_actors": []}}})):
    code, f, u, _ = run(world([DEPLOY_KEY]), bad)
    check(f"unusable allowlist ({label}) -> unknown, cannot be used to bless a wildcard", code == 20, f"{code} {u}")


# 4. Pagination: a later page failing is a failed read; a healthy second page is joined.
def paged(fail_second):
    doc = world([integ(BUMP_APP)])
    first, second = doc[LIST][:1], doc[LIST][1:]
    base = C.fixture_fetcher(doc)

    def fetch(path, token):
        if path == LIST:
            return first, f'<{C.API}/repos/{REPO}/rulesets?page=2>; rel="next"'
        if "page=2" in path:
            if fail_second:
                raise C.ReadError("page 2: HTTP 502")
            return second, ""
        return base(path, token)
    return fetch


code, f, u, o = run(None, fetcher=paged(True))
check("second listing page failing -> unknown, not a shorter list", code == 20 and not o, f"{code} {u} {o}")
code, f, u, o = run(None, fetcher=paged(False))
check("healthy two-page listing is joined -> clean", code == 0 and o == [14564982, 18465404], f"{code} {f} {u} {o}")


calls = []


class Runaway(Exception):
    pass


def endless(path, token):
    calls.append(path)
    if len(calls) > 200:
        raise Runaway("the client kept following `next` links")
    return [], f'<{C.API}/repos/{REPO}/rulesets?page=n>; rel="next"'


try:
    code, f, u, o = run(None, fetcher=endless)
    check("pagination that never ends -> unknown", code == 20, f"{code} {u}")
except Runaway as e:
    check("pagination that never ends -> unknown", False, e)

# 5. The recorded live snapshot is red against the committed allowlist.
committed = json.loads((ROOT / "scripts/ruleset-bypass-allowlist.json").read_text())
code, f, u, o = run(json.loads(LIVE.read_text()), committed)
check("live snapshot 2026-11-11 (DeployKey, actor_id null) -> findings", code == 10
      and any("DeployKey" in x for x in f), f"{code} {f} {u}")
check("committed allowlist lists no DeployKey wildcard",
      all(e.get("actor_type") != "DeployKey" for r in committed["rulesets"].values() for e in r["bypass_actors"]))

# 6. The CLI: --fixture works end to end, an unreadable fixture is unknown.
p = subprocess.run([sys.executable, "-I", str(SCRIPT), "--fixture", str(LIVE)], capture_output=True, text=True)
check("CLI --fixture on the live snapshot exits 10", p.returncode == 10, p.stdout + p.stderr)
p = subprocess.run([sys.executable, "-I", str(SCRIPT), "--fixture", str(LIVE) + ".missing"],
                   capture_output=True, text=True)
check("CLI unreadable fixture exits 20", p.returncode == 20, p.stdout + p.stderr)

if failures:
    print(f"\n{len(failures)} FAILED")
    for x in failures:
        print(" -", x)
    sys.exit(1)
print("\nall checks passed")
