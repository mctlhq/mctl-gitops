"""Render test for the pre-pull verifier's identity (mctl-agents#1007, F3).

The PreSync Job runs in the service's own Argo CD app; its Role and RoleBinding
come from the tenant app, because the `apps` project does not allow RBAC
objects. Nothing orders two apps, so the order that CAN be fixed is fixed in the
rendered output: the ServiceAccount is a PreSync hook of the same app at an
earlier sync wave than the Job, and the tenant chart no longer creates it. What
cannot be ordered (the Role) is waited for by the script (tests/test_prepull_verify.py).

Green on the real tree, red on each deliberate mutation of a copied chart.
Plain script: `python3 tests/test_prepull_render.py` (needs helm).
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = ROOT / "platform-gitops/helm-charts/base-service"
TENANT = ROOT / "platform-gitops/helm-charts/tenant"
SVC = ROOT / "platform-gitops/services/admins/mctl-agents-worker/values.yaml"
TEN = ROOT / "platform-gitops/tenants/admins/values.yaml"
failures = []


def flag(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures.append(f"{name}: {detail}")


def helm(chart, release, values, *extra):
    r = subprocess.run(["helm", "template", release, str(chart), "-f", str(values), *extra],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def docs(text):
    return [d for d in yaml.safe_load_all(text) if d]


def of_kind(items, kind):
    return [d for d in items if d.get("kind") == kind]


def problems(base_chart, tenant_chart):
    """Every way the SA/Role/Job wiring is wrong; empty means wired."""
    out = []
    rc, text, err = helm(base_chart, "admins-mctl-agents-worker", SVC)
    if rc:
        return [f"base-service render failed: {err[:200]}"]
    base = docs(text)
    rc, text, err = helm(tenant_chart, "tenant-admins", TEN)
    if rc:
        return [f"tenant render failed: {err[:200]}"]
    ten = docs(text)

    jobs = [j for j in of_kind(base, "Job") if j["metadata"]["name"].endswith("-prepull-verify")]
    if len(jobs) != 1:
        return [f"expected one verify Job, found {len(jobs)}"]
    job = jobs[0]
    sa_name = job["spec"]["template"]["spec"].get("serviceAccountName")
    ann = job["metadata"].get("annotations", {})
    if ann.get("argocd.argoproj.io/hook") != "PreSync":
        out.append("the Job is not a PreSync hook")

    sas = [s for s in of_kind(base, "ServiceAccount") if s["metadata"]["name"] == sa_name]
    if len(sas) != 1:
        out.append(f"the Job's ServiceAccount {sa_name!r} is not rendered by the same app ({len(sas)} found)")
    else:
        sa_ann = sas[0]["metadata"].get("annotations", {})
        if sa_ann.get("argocd.argoproj.io/hook") != "PreSync":
            out.append("the ServiceAccount is not a PreSync hook, so it is not ordered before the Job")
        try:
            if int(sa_ann.get("argocd.argoproj.io/sync-wave", "0")) >= int(ann.get("argocd.argoproj.io/sync-wave", "0")):
                out.append("the ServiceAccount's sync wave is not earlier than the Job's")
        except ValueError:
            out.append("a sync wave is not an integer")

    # The tenant app must not also own the ServiceAccount (two owners fight), and must bind it.
    if any(s["metadata"]["name"] == sa_name for s in of_kind(ten, "ServiceAccount")):
        out.append("the tenant chart also creates the ServiceAccount: two apps own one object")
    binds = [b for b in of_kind(ten, "RoleBinding") if b["metadata"]["name"] == "prepull-verifier"]
    roles = [r for r in of_kind(ten, "Role") if r["metadata"]["name"] == "prepull-verifier"]
    if len(binds) != 1 or len(roles) != 1:
        return out + ["tenant chart does not render exactly one prepull-verifier Role and RoleBinding"]
    subj = binds[0]["subjects"]
    if subj != [{"kind": "ServiceAccount", "name": sa_name, "namespace": "admins"}]:
        out.append(f"RoleBinding subject {subj} is not the Job's ServiceAccount {sa_name!r} in admins")
    if binds[0]["roleRef"]["name"] != roles[0]["metadata"]["name"]:
        out.append("RoleBinding does not point at the Role")

    # The Role must cover what the script reads.
    script = (BASE / "files/prepull-verify.sh").read_text()
    need = set()
    for kind, verb, group in (("deployment", "get", "apps"), ("daemonset", "get", "apps"), ("pods", "list", "")):
        if re.search(rf"kubectl get {kind}\b", script):
            need.add((group, {"deployment": "deployments", "daemonset": "daemonsets", "pods": "pods"}[kind], verb))
    have = {(g, res, v) for rule in roles[0]["rules"] for g in rule["apiGroups"] for res in rule["resources"] for v in rule["verbs"]}
    if need - have:
        out.append(f"the Role does not grant what the script reads: {sorted(need - have)}")
    extra = have - need
    if extra:
        out.append(f"the Role grants more than the script reads: {sorted(extra)}")
    if roles[0]["metadata"]["namespace"] != "admins" or binds[0]["metadata"]["namespace"] != "admins":
        out.append("Role or RoleBinding is not in the service's namespace")

    env = {e["name"]: e.get("value") for e in job["spec"]["template"]["spec"]["containers"][0]["env"]}
    if not env.get("RBAC_WAIT_SECONDS", "").isdigit():
        out.append("the Job has no numeric RBAC_WAIT_SECONDS")
    elif int(env["RBAC_WAIT_SECONDS"]) + 30 >= job["spec"]["activeDeadlineSeconds"]:
        out.append("the RBAC wait leaves no time before the Job deadline")
    return out


def copy_charts(tmp):
    b, t = tmp / "base-service", tmp / "tenant"
    shutil.copytree(BASE, b)
    shutil.copytree(TENANT, t)
    return b, t


# 1. Green on the real tree.
found = problems(BASE, TENANT)
flag("real tree: the verifier identity is wired", not found, "; ".join(found))

# 2. Every service that enables pre-pull lives in a tenant that renders the Role.
for v in sorted((ROOT / "platform-gitops/services").glob("*/*/values.yaml")):
    doc = yaml.safe_load(v.read_text()) or {}
    if (doc.get("prepull") or {}).get("enabled"):
        team = v.parts[-3]
        ten = yaml.safe_load((ROOT / f"platform-gitops/tenants/{team}/values.yaml").read_text())
        flag(f"{v.parent.name}: tenant {team} enables prepullVerifier", (ten.get("tenant", {}).get("prepullVerifier") or {}).get("enabled") is True)

# 3. The wait must stay inside the deadline: the chart refuses otherwise.
rc, _, err = helm(BASE, "x", SVC, "--set", "prepull.rbacWaitSeconds=100")
flag("chart refuses a wait that leaves no time before the deadline", rc != 0 and "rbacWaitSeconds" in err, err[:200])

# 4. Red on each mutation of a copied chart.
MUTANTS = [
    ("SA hook annotation removed", "base", "templates/prepull.yaml",
     '    argocd.argoproj.io/hook: PreSync\n    argocd.argoproj.io/sync-wave: "-1"\n', ""),
    ("SA at the same wave as the Job", "base", "templates/prepull.yaml", 'sync-wave: "-1"', 'sync-wave: "0"'),
    ("SA after the Job", "base", "templates/prepull.yaml", 'sync-wave: "-1"', 'sync-wave: "1"'),
    ("Job at an earlier wave than the SA", "base", "templates/prepull.yaml", 'sync-wave: "0"', 'sync-wave: "-5"'),
    ("tenant chart owns the SA again", "tenant", "templates/prepull-verifier.yaml",
     "apiVersion: rbac.authorization.k8s.io/v1\nkind: Role\n",
     "apiVersion: v1\nkind: ServiceAccount\nmetadata:\n  name: prepull-verifier\n  namespace: {{ $ns }}\n---\napiVersion: rbac.authorization.k8s.io/v1\nkind: Role\n"),
    ("RoleBinding names another ServiceAccount", "tenant", "templates/prepull-verifier.yaml", "    name: prepull-verifier\n    namespace", "    name: someone-else\n    namespace"),
    ("Role loses the pods list", "tenant", "templates/prepull-verifier.yaml", 'verbs: ["list"]', 'verbs: ["get"]'),
    ("Role grants more than the script reads", "tenant", "templates/prepull-verifier.yaml", 'verbs: ["get"]\n  - apiGroups: [""]', 'verbs: ["get", "delete"]\n  - apiGroups: [""]'),
    ("RBAC wait env dropped", "base", "templates/prepull.yaml", "            - name: RBAC_WAIT_SECONDS\n              value: {{ .Values.prepull.rbacWaitSeconds | quote }}\n", ""),
]
for name, which, rel, old, new in MUTANTS:
    with tempfile.TemporaryDirectory() as t:
        b, tn = copy_charts(pathlib.Path(t))
        f = (b if which == "base" else tn) / rel
        src = f.read_text()
        n = src.count(old)
        if n < 1:
            flag(f"mutant anchor exists: {name}", False, f"count={n}")
            continue
        # replace only the first occurrence unless the anchor is the shared wave text
        f.write_text(src.replace(old, new, 1) if name not in ("Job at an earlier wave than the SA",) else src.replace(old, new))
        got = problems(b, tn)
        flag(f"mutant killed: {name}", bool(got), "mutant still reports a wired identity")

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f[:300])
    sys.exit(1)
print("all checks passed")
