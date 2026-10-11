"""Run retire-service's Argo CD Application guard against a stub kubectl.

retire-service removes the Argo CD Application <team>-<component>. That name
alone does not say whose Application it is, so the step must only act on an
Application the `apps` ApplicationSet generated for that team, and must treat
an Application it could not read as an error rather than as absent.

The script is extracted from the template rather than restated here, because a
restated copy would keep passing after the template changed. kubectl is a
stub backed by a state directory, so every call is recorded and no cluster is
needed. The DAG wiring (every destructive step waits for preflight) is checked
structurally, and tpl-git-commit's delete-service is checked for its name
validation.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

TPL_DIR = pathlib.Path("platform-gitops/argo-workflows/cluster-templates")
doc = yaml.safe_load((TPL_DIR / "wft-retire-service.yaml").read_text())
TEMPLATES = {t["name"]: t for t in doc["spec"]["templates"]}
TASKS = {t["name"]: t for t in TEMPLATES["retire-pipeline"]["dag"]["tasks"]}

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


# ── DAG wiring ───────────────────────────────────────────────────────────────


def params(task):
    return {p["name"]: p["value"] for p in task["arguments"]["parameters"]}


def ancestors(name):
    seen = set()
    stack = list(TASKS[name].get("dependencies", []))
    while stack:
        d = stack.pop()
        if d not in seen:
            seen.add(d)
            stack.extend(TASKS[d].get("dependencies", []))
    return seen


check("preflight exists and runs the guard in check mode",
      "preflight" in TASKS and TASKS["preflight"].get("template") == "argocd-app-guard"
      and params(TASKS["preflight"]).get("mode") == "check"
      and not TASKS["preflight"].get("dependencies"),
      str(TASKS.get("preflight")))
check("delete-argocd-app runs the same guard in delete mode",
      TASKS["delete-argocd-app"].get("template") == "argocd-app-guard"
      and params(TASKS["delete-argocd-app"]).get("mode") == "delete",
      str(TASKS["delete-argocd-app"]))
for name in TASKS:
    if name != "preflight":
        check(f"{name} runs only after preflight", "preflight" in ancestors(name),
              str(ancestors(name)))

GUARD = TEMPLATES["argocd-app-guard"]["script"]
env_values = {e["name"]: e["value"] for e in GUARD.get("env", [])}
check("the guard reads its parameters from env, not from the script text",
      "{{" not in GUARD["source"]
      and env_values.get("WORKFLOW_NAMESPACE") == "{{workflow.namespace}}",
      str(env_values))
SOURCE = GUARD["source"]

# ── Stub kubectl ─────────────────────────────────────────────────────────────
#
# State directory: apps/<name>.json is an Application object. Flag files:
#   fail     every read exits 1 (API error / RBAC forbidden)
#   garbage  reads print text that is not JSON
#   empty    reads print nothing and exit 0
#   noitems  reads print a List without an items array
#   stuck    a delete only sets deletionTimestamp (finalizer never clears)
#   swap     a delete replaces the object with a foreign one of the same name
# Every call is appended to `log`.
KUBECTL_STUB = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
S = pathlib.Path(os.environ["KSTATE"])
argv = sys.argv[1:]
with open(S / "log", "a") as f:
    f.write("kubectl " + " ".join(argv) + "\n")
apps = S / "apps"

def flag(n):
    return (S / n).exists()

def load(name):
    p = apps / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None

def store(name, obj):
    (apps / f"{name}.json").write_text(json.dumps(obj))

def gone(name):
    (apps / f"{name}.json").unlink(missing_ok=True)

def opt(flagname):
    return argv[argv.index(flagname) + 1] if flagname in argv else None

def deleted(name, obj):
    if flag("swap"):
        store(name, {"metadata": {"name": name, "uid": "99999999-9999-9999-9999-999999999999",
                                  "labels": {}}, "spec": {"project": "default"}})
    elif flag("stuck"):
        obj["metadata"]["deletionTimestamp"] = "2026-01-01T00:00:00Z"
        store(name, obj)
    else:
        gone(name)

verb = argv[0]
if verb == "get":
    if flag("fail"):
        print("Error from server (Forbidden): forbidden", file=sys.stderr); sys.exit(1)
    if flag("garbage"):
        print("<html>502 Bad Gateway</html>"); sys.exit(0)
    if flag("empty"):
        sys.exit(0)
    if flag("noitems"):
        print(json.dumps({"kind": "List"})); sys.exit(0)
    sel = opt("--field-selector")
    if sel:
        obj = load(sel.split("=", 1)[1])
        print(json.dumps({"kind": "List", "items": [obj] if obj else []})); sys.exit(0)
    name = argv[2]
    obj = load(name)
    if obj is None:
        print(f'Error from server (NotFound): applications.argoproj.io "{name}" not found',
              file=sys.stderr); sys.exit(1)
    print(json.dumps(obj)); sys.exit(0)

if verb == "delete":
    if "--raw" in argv:
        name = opt("--raw").rsplit("/", 1)[1]
        body = json.loads(pathlib.Path(opt("-f")).read_text())
        with open(S / "log", "a") as f:
            f.write("  body " + json.dumps(body, sort_keys=True) + "\n")
        obj = load(name)
        if obj is None:
            print("Error from server (NotFound)", file=sys.stderr); sys.exit(1)
        want = body.get("preconditions", {}).get("uid")
        if want is not None and want != obj["metadata"]["uid"]:
            print("Error from server (Conflict): precondition failed", file=sys.stderr); sys.exit(1)
        deleted(name, obj); sys.exit(0)
    # Plain `kubectl delete application NAME ...` (the unguarded shape).
    name = argv[2]
    obj = load(name)
    if obj is not None:
        deleted(name, obj)
    sys.exit(0)

if verb == "patch":
    name = argv[2]
    obj = load(name)
    if obj is None:
        print("Error from server (NotFound)", file=sys.stderr); sys.exit(1)
    if opt("--type") == "json":
        for op in json.loads(opt("-p")):
            node = obj
            parts = op["path"].strip("/").split("/")
            for p in parts[:-1]:
                node = node.get(p.replace("~1", "/"), {})
            key = parts[-1].replace("~1", "/")
            if op["op"] == "test" and node.get(key) != op["value"]:
                print("Error from server (UnprocessableEntity): test failed", file=sys.stderr)
                sys.exit(1)
            if op["op"] in ("add", "replace"):
                node[key] = op["value"]
    else:
        obj["metadata"]["finalizers"] = None
    if obj["metadata"].get("deletionTimestamp") and not obj["metadata"].get("finalizers"):
        gone(name)
    else:
        store(name, obj)
    sys.exit(0)

print("stub kubectl: unexpected call: " + " ".join(argv), file=sys.stderr)
sys.exit(3)
'''

UID = "11111111-2222-3333-4444-555555555555"


def service_app(team, svc, **over):
    """An Application exactly as the `apps` ApplicationSet renders it."""
    app = {
        "metadata": {
            "name": f"{team}-{svc}",
            "uid": UID,
            "labels": {"team": team, "backstage.io/kubernetes-id": svc, "env": "apps"},
            "finalizers": ["resources-finalizer.argocd.argoproj.io"],
            "ownerReferences": [{"apiVersion": "argoproj.io/v1alpha1",
                                 "kind": "ApplicationSet", "name": "apps",
                                 "controller": True, "blockOwnerDeletion": True}],
        },
        "spec": {"project": "apps", "destination": {"namespace": team}},
    }
    for k, v in over.items():
        if k == "labels":
            app["metadata"]["labels"] = v
        elif k == "project":
            app["spec"]["project"] = v
        elif k == "dest_ns":
            app["spec"]["destination"]["namespace"] = v
        elif k == "owners":
            app["metadata"]["ownerReferences"] = v
        elif k == "name":
            app["metadata"]["name"] = v
    return app


def platform_app(name, project="default", labels=None):
    return {"metadata": {"name": name, "uid": UID, "labels": labels or {},
                         "finalizers": ["resources-finalizer.argocd.argoproj.io"]},
            "spec": {"project": project, "destination": {"namespace": "argocd"}}}


def run(team, svc, apps=(), mode="delete", wf_ns=None, flags=(), source=SOURCE):
    """Run the guard. Returns (result, kubectl log, names left)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        (tmp / "bin").mkdir()
        (tmp / "apps").mkdir()
        (tmp / "log").write_text("")
        for key, app in apps:
            (tmp / "apps" / f"{key}.json").write_text(json.dumps(app))
        for fl in flags:
            (tmp / fl).write_text("")
        for tool, body in (("kubectl", KUBECTL_STUB), ("sleep", "#!/bin/sh\nexit 0\n")):
            (tmp / "bin" / tool).write_text(body)
            (tmp / "bin" / tool).chmod(0o755)
        env = {"PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "KSTATE": str(tmp),
               "PARAM_TEAM_NAME": team, "PARAM_COMPONENT_NAME": svc,
               "PARAM_MODE": mode,
               "WORKFLOW_NAMESPACE": team if wf_ns is None else wf_ns}
        r = subprocess.run(["sh", "-c", source], env=env, capture_output=True,
                           text=True, timeout=60)
        left = sorted(p.stem for p in (tmp / "apps").iterdir())
        return r, (tmp / "log").read_text(), left


def mutated(log):
    return any(line.split()[1] in ("delete", "patch") for line in log.splitlines()
               if line.startswith("kubectl "))


def own(team, svc, **over):
    app = service_app(team, svc, **over)
    return (app["metadata"]["name"], app)


# Own Application: deleted, through the UID precondition.
r, log, left = run("labs", "portfolio", [own("labs", "portfolio")])
check("own service Application is deleted",
      r.returncode == 0 and left == [], r.stdout + r.stderr + log)
check("the delete carries the verified UID as a precondition",
      "delete --raw /apis/argoproj.io/v1alpha1/namespaces/argocd/applications/labs-portfolio"
      in log and f'"preconditions": {{"uid": "{UID}"}}' in log, log)

# Platform Applications whose names are <team>-<component> for some input.
FOREIGN = [
    ("root", "app", platform_app("root-app", labels={"app.kubernetes.io/managed-by": "x"})),
    ("shared", "pg", platform_app("shared-pg")),
    ("tenant", "labs", platform_app("tenant-labs", "platform",
                                    {"env": "x", "mctl.me/tenant": "labs"})),
    ("argocd", "self-managed", platform_app("argocd-self-managed")),
    ("admins", "mctl-api", platform_app("admins-mctl-api", "platform")),
    ("labs", "oidc-zitadel", platform_app("labs-oidc-zitadel")),
]
for team, svc, app in FOREIGN:
    name = f"{team}-{svc}"
    for mode in ("check", "delete"):
        r, log, left = run(team, svc, [(name, app)], mode=mode)
        check(f"{mode}: {name} is refused and left untouched",
              r.returncode != 0 and left == [name] and not mutated(log)
              and "refusing" in r.stdout, r.stdout + r.stderr + log)

# Each identity property on its own is enough to refuse.
VARIANTS = {
    "team label of another tenant (name collision lab + s-x)": (
        "lab", "s-x", own("labs", "x", name="lab-s-x")),
    "no team label": ("labs", "x", own("labs", "x", labels={})),
    "team label of another tenant, everything else matching": (
        "labs", "x", own("labs", "x", labels={"team": "ovk",
                                              "backstage.io/kubernetes-id": "x"})),
    "kubernetes-id of another component": (
        "labs", "x", own("labs", "x", labels={"team": "labs",
                                              "backstage.io/kubernetes-id": "y"})),
    "project other than apps": ("labs", "x", own("labs", "x", project="default")),
    "destination namespace other than the team": (
        "labs", "x", own("labs", "x", dest_ns="argocd")),
    "not generated by ApplicationSet apps": ("labs", "x", own("labs", "x", owners=[])),
    "owned by ApplicationSet tenants": (
        "labs", "x", own("labs", "x", owners=[{"kind": "ApplicationSet",
                                               "name": "tenants", "controller": True}])),
}
for what, (team, svc, app) in VARIANTS.items():
    r, log, left = run(team, svc, [app])
    check(f"refused: {what}", r.returncode != 0 and left == [app[0]] and not mutated(log),
          r.stdout + r.stderr + log)

# Absent is the only "nothing to do"; every unreadable answer is an error.
for mode in ("check", "delete"):
    r, log, _ = run("labs", "gone", [], mode=mode)
    check(f"{mode}: an absent Application is nothing to delete",
          r.returncode == 0 and "does not exist" in r.stdout and not mutated(log),
          r.stdout + r.stderr + log)
for fl in ("fail", "garbage", "empty", "noitems"):
    for mode in ("check", "delete"):
        r, log, left = run("labs", "portfolio", [own("labs", "portfolio")],
                           mode=mode, flags=(fl,))
        check(f"{mode}: a read that is '{fl}' fails instead of passing as absent",
              r.returncode != 0 and left == ["labs-portfolio"] and not mutated(log),
              r.stdout + r.stderr + log)

# check mode never mutates.
r, log, left = run("labs", "portfolio", [own("labs", "portfolio")], mode="check")
check("check mode passes an own Application and changes nothing",
      r.returncode == 0 and left == ["labs-portfolio"] and not mutated(log),
      r.stdout + r.stderr + log)

# Inputs.
r, log, _ = run("labs", "portfolio", [own("labs", "portfolio")], wf_ns="ovk")
check("a workflow in another team's namespace is refused before any API call",
      r.returncode != 0 and log == "", r.stdout + log)
r, log, left = run("labs", "portfolio", [own("labs", "portfolio")], wf_ns="argo-workflows")
check("argo-workflows (delete-tenant-safe fallback) may retire a team's service",
      r.returncode == 0 and left == [], r.stdout + r.stderr + log)
for bad in ("", "../x", "a/b", "Labs", "-x", "labs\nroot", "x" * 32, "a b"):
    r, log, _ = run(bad, "svc", [], wf_ns=bad)
    check(f"team name {bad!r} is refused", r.returncode != 0 and log == "", r.stdout + log)
    r, log, _ = run("labs", bad, [])
    check(f"component name {bad!r} is refused", r.returncode != 0 and log == "",
          r.stdout + log)
r, log, _ = run("labs", "portfolio", [own("labs", "portfolio")], mode="purge")
check("an unknown mode is refused", r.returncode != 0 and not mutated(log), r.stdout + log)

# Stuck finalizer: cleared only through a patch pinned to the verified object.
r, log, left = run("labs", "portfolio", [own("labs", "portfolio")], flags=("stuck",))
patches = [l for l in log.splitlines() if l.startswith("kubectl patch")]
check("a stuck finalizer is cleared and the Application removed",
      r.returncode == 0 and left == [], r.stdout + r.stderr + log)
check("the finalizer patch tests uid, team label and project before applying",
      len(patches) == 1 and "--type=json" in patches[0]
      and f'"path":"/metadata/uid","value":"{UID}"' in patches[0]
      and '"path":"/metadata/labels/team","value":"labs"' in patches[0]
      and '"path":"/spec/project","value":"apps"' in patches[0], "\n".join(patches))

# The name is taken over by another object after the delete: no finalizer patch.
r, log, left = run("labs", "portfolio", [own("labs", "portfolio")], flags=("swap",))
check("an object that replaced the Application is not patched",
      r.returncode != 0 and left == ["labs-portfolio"]
      and "kubectl patch" not in log,
      r.stdout + r.stderr + log)

# ── tpl-git-commit delete-service: names become a `git rm -rf` path ──────────
gdoc = yaml.safe_load((TPL_DIR / "tpl-git-commit.yaml").read_text())
DELETE_SERVICE = {t["name"]: t for t in gdoc["spec"]["templates"]}["delete-service"]["script"]
check("delete-service reads its parameters from env",
      "{{" not in DELETE_SERVICE["source"], "")


def run_delete_service(team, svc):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        (tmp / "bin").mkdir()
        (tmp / "log").write_text("")
        for tool in ("apk", "git", "cp", "mkdir", "chmod"):
            (tmp / "bin" / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> "{tmp}/log"\nexit 1\n')
            (tmp / "bin" / tool).chmod(0o755)
        env = {"PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "PARAM_TEAM_NAME": team,
               "PARAM_COMPONENT_NAME": svc, "PARAM_COMPONENT_TYPE": "base-service"}
        r = subprocess.run(["sh", "-c", DELETE_SERVICE["source"]], env=env,
                           capture_output=True, text=True, timeout=60)
        return r, (tmp / "log").read_text()


for team, svc in (("labs", "../../infra-components"), ("..", "x"), ("labs\nx", "y"),
                  ("labs", "")):
    r, log = run_delete_service(team, svc)
    check(f"delete-service refuses {team!r}/{svc!r} before doing anything",
          r.returncode != 0 and "Invalid team or service name" in r.stdout and log == "",
          r.stdout + log)
r, log = run_delete_service("labs", "portfolio")
check("delete-service lets a valid name through to the clone",
      "Invalid" not in r.stdout and log.startswith("apk "), r.stdout + log)

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
