"""Run wft-create-tenant's existence checks against a fixture checkout.

create-tenant creates a tenant. Its commit step used to find an existing
tenant directory, skip writing the tenant and carry on provisioning, so a
request for a taken name "succeeded" without creating anything. An existing
tenant is now refused in validate unless reprovision=true asks for a re-run,
and the commit step refuses one that appeared after validate.

Both blocks are extracted from the template rather than restated here, because
a restated copy would keep passing after the template changed. `git clone` is
replaced by a stub on PATH that copies a fixture checkout, or fails.

The second half covers the namespace guard shared by create-tenant,
delete-tenant-safe and delete-tenant (gitops#1768): the static denylist, and
the live "absent / owned / foreign / lookup failed" decision, run against a
stub kubectl. It lives in this file because CI already runs it.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml")
doc = yaml.safe_load(TPL.read_text())
TEMPLATES = {t["name"]: t for t in doc["spec"]["templates"]}
VALIDATE = TEMPLATES["validate-tenant-name"]["script"]["source"]
COMMIT = TEMPLATES["commit-tenant-to-git"]["script"]["source"]

m = re.search(r'^(TENANT_DIR="platform-gitops/tenants/\$\{TENANT\}"\n.*?\nfi)$',
              COMMIT, re.S | re.M)
assert m, "could not extract the commit step's existence check"
COMMIT_CHECK = m.group(1) + '\necho "SKIP_GIT=$SKIP_GIT"\n'

# The workflow must hand reprovision to both steps, or the default applies.
pipeline = [t for t in TEMPLATES["create-tenant-pipeline"]["dag"]["tasks"]]
for task in ("validate", "commit-to-git"):
    params = {p["name"]: p["value"] for t in pipeline if t["name"] == task
              for p in t["arguments"]["parameters"]}
    assert params.get("reprovision") == "{{workflow.parameters.reprovision}}", \
        f"{task} does not receive reprovision"
defaults = {p["name"]: p.get("value") for p in doc["spec"]["arguments"]["parameters"]}
assert defaults.get("reprovision") == "false", "reprovision must default to false"

GIT_STUB = """#!/bin/sh
# git clone <url> <dest>: copy the fixture, or fail like an unreachable remote.
[ "$1" = clone ] || exit 0
for dest; do :; done
[ -n "$FIXTURE" ] || { echo "fatal: unable to access" >&2; exit 128; }
cp -R "$FIXTURE" "$dest"
"""

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def run_validate(tenant, reprovision, fixture):
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        (tmp / "bin").mkdir()
        stub = tmp / "bin" / "git"
        stub.write_text(GIT_STUB)
        stub.chmod(0o755)
        # The step clones to a fixed /tmp path; point it into this temp dir.
        source = VALIDATE.replace("/tmp/mctl-gitops", str(tmp / "clone"))
        env = {
            "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}",
            "PARAM_TENANT_NAME": tenant,
            "PARAM_REPROVISION": reprovision,
            "GITOPS_ORG": "example",
            "GITOPS_REPO": "gitops",
            "FIXTURE": str(fixture) if fixture else "",
        }
        return subprocess.run(["sh", "-c", source], env=env,
                              capture_output=True, text=True)


def run_commit_check(tenant, reprovision, checkout):
    script = f'set -e\nTENANT="$PARAM_TENANT_NAME"\n{COMMIT_CHECK}'
    env = {"PATH": os.environ["PATH"], "PARAM_TENANT_NAME": tenant,
           "PARAM_REPROVISION": reprovision}
    return subprocess.run(["sh", "-c", script], cwd=checkout, env=env,
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as d:
    fixture = pathlib.Path(d) / "checkout"
    (fixture / "platform-gitops" / "tenants" / "taken").mkdir(parents=True)
    (fixture / "platform-gitops" / "tenants" / "taken" / "values.yaml").write_text(
        "tenant:\n  name: taken\n")

    r = run_validate("fresh", "false", fixture)
    check("a new tenant passes validate", r.returncode == 0, r.stdout + r.stderr)

    r = run_validate("taken", "false", fixture)
    check("an existing tenant fails validate", r.returncode != 0, r.stdout)
    check("the failure names the tenant and the way to re-run",
          "already exists" in r.stdout and "reprovision=true" in r.stdout, r.stdout)

    r = run_validate("taken", "true", fixture)
    check("reprovision=true lets an existing tenant through",
          r.returncode == 0, r.stdout + r.stderr)

    r = run_validate("fresh", "true", fixture)
    check("reprovision=true refuses a tenant that does not exist",
          r.returncode != 0, r.stdout)

    r = run_validate("fresh", "yes", fixture)
    check("reprovision other than true/false is refused", r.returncode != 0, r.stdout)

    r = run_validate("fresh", "false", None)
    check("a failed clone fails validate (could not check is not absent)",
          r.returncode != 0, r.stdout)

    r = run_validate("fresh\nkube-system", "false", fixture)
    check("a multi-line name is refused", r.returncode != 0, r.stdout)

    r = run_validate("kube-system", "false", fixture)
    check("a reserved name is still refused", r.returncode != 0, r.stdout)

    r = run_commit_check("fresh", "false", fixture)
    check("commit: a new tenant writes its files",
          r.returncode == 0 and "SKIP_GIT=false" in r.stdout, r.stdout + r.stderr)

    r = run_commit_check("taken", "false", fixture)
    check("commit: a tenant created after validate fails the step",
          r.returncode != 0, r.stdout)

    r = run_commit_check("taken", "true", fixture)
    check("commit: reprovision=true skips the files and carries on",
          r.returncode == 0 and "SKIP_GIT=true" in r.stdout, r.stdout + r.stderr)

# ── Namespace collision / ownership guard (gitops#1768) ──────────────────────
#
# A tenant name that matches a live platform namespace used to pass validate,
# and the tenant ApplicationSet (CreateNamespace=true) then adopted that
# namespace; delete-tenant later deleted it. create-tenant now refuses a name
# whose namespace exists without mctl.me/tenant=<name>, and both delete
# templates refuse to delete such a namespace. The shared `tenant-ns-guard`
# block is extracted from the templates and run against a stub kubectl.

TEMPLATE_DIR = TPL.parent
GUARD_RE = re.compile(r"^# BEGIN tenant-ns-guard\n.*?^# END tenant-ns-guard\n",
                      re.S | re.M)
GUARD_SITES = {
    "wft-create-tenant.yaml": ("validate-tenant-name", "check-namespace-collision"),
    "wft-delete-tenant-safe.yaml": ("validate-tenant-exists", "delete-k8s-resources"),
    "wft-delete-tenant.yaml": ("validate-tenant-exists", "delete-k8s-resources"),
}
ALL_TEMPLATES = {}
for fname in GUARD_SITES:
    d = yaml.safe_load((TEMPLATE_DIR / fname).read_text())
    ALL_TEMPLATES[fname] = {t["name"]: t for t in d["spec"]["templates"]}

guards = {}
for fname, names in GUARD_SITES.items():
    for name in names:
        src = ALL_TEMPLATES[fname][name]["script"]["source"]
        found = GUARD_RE.findall(src)
        check(f"{fname}/{name} carries exactly one tenant-ns-guard block",
              len(found) == 1, f"found {len(found)}")
        if found:
            guards[(fname, name)] = found[0]
GUARD = next(iter(guards.values()), "")
check("every tenant-ns-guard copy is byte-identical",
      len(set(guards.values())) == 1, ", ".join(f"{f}/{n}" for f, n in guards))

TENANTS = sorted(p.name for p in pathlib.Path("platform-gitops/tenants").iterdir()
                 if p.is_dir())


def reserved(names):
    """Return the subset of names tenant_name_reserved refuses."""
    script = GUARD + 'for n in "$@"; do tenant_name_reserved "$n" && echo "$n"; done; exit 0\n'
    r = subprocess.run(["sh", "-c", script, "sh", *names],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return set(r.stdout.split())


# Every live platform namespace named in the issue, plus the patterns' edges.
MUST_REJECT = [
    "argocd", "argo-workflows", "argo-events", "kube-system", "kube-public",
    "kube-node-lease", "default", "cert-manager", "traefik", "vault",
    "external-secrets", "monitoring", "temporal", "backstage", "mctl-api",
    "minio", "database", "platform-db", "platform-events", "forgejo", "zitadel",
    "cnpg-system", "reflector-system", "argo-rollouts", "grafana-iac",
    "vault-human-auth-iac", "local-path-storage", "system-upgrade",
    "observability-eval", "kube-foo", "argonaut", "foo-system", "platform-x",
    "mctl-x", "grafana-x", "vaultx",
    # Platform Argo CD Application names and their hyphen-prefixes (mirrors
    # IsReservedTenantName in mctl-api internal/operations/reserved_tenant.go).
    "tenant", "root", "shared", "cloudnative", "external", "grafana", "loki",
    "otel", "reflector", "valkey", "root-app", "shared-pg", "cloudnative-pg",
    "loki-stack", "temporal-web", "tenant-x", "tenant-admins", "otel-collector",
    "otel-eval-tempo", "argocd-self-managed", "argo-workflows-config",
]
# Existing tenants must stay accepted: the guard also runs when create-tenant
# re-provisions them and when delete-tenant removes them.
LIVE_TENANTS = ["admins", "erpact", "karabu", "labs", "mctl", "ovk"]
MUST_ACCEPT = sorted(set(TENANTS + LIVE_TENANTS)) + [
    "team1", "my-team", "dev-platform", "fresh", "rooted", "sharedx", "lokis",
    "external2", "my-tenant", "otelx", "reflectors"]
# Every platform Application in mctl-api's platformApplicationNames snapshot
# (2026-10-11), and every hyphen-prefix of one, must be refused: a tenant with
# such a name could spell that Application as <tenant>-<service>.
PLATFORM_APPS = [
    "argo-rollouts", "argo-workflows", "argo-workflows-config",
    "argocd-self-managed", "cloudnative-pg", "external-secrets", "forgejo",
    "grafana-iac", "loki-stack", "minio", "monitoring", "otel-collector",
    "otel-eval-tempo", "reflector", "root-app", "shared-pg", "temporal",
    "temporal-web", "valkey", "vault", "vault-human-auth-iac", "zitadel",
]
structural = set()
for app in PLATFORM_APPS:
    parts = app.split("-")
    structural.update("-".join(parts[:i]) for i in range(1, len(parts) + 1))
structural = sorted(n for n in structural if len(n) >= 2)
got = reserved(structural)
check("the denylist refuses every platform Application name and hyphen-prefix",
      got == set(structural), f"not refused: {sorted(set(structural) - got)}")

got = reserved(MUST_REJECT)
check("the denylist refuses every platform namespace name and pattern",
      got == set(MUST_REJECT), f"not refused: {sorted(set(MUST_REJECT) - got)}")
got = reserved(MUST_ACCEPT)
check("the denylist accepts every existing tenant (reprovision keeps working)",
      not got, f"refused: {sorted(got)}")

# Freshness: a platform namespace added to gitops with a literal name must be
# on the denylist too, or the static layer silently goes stale again.
NS_LITERAL = re.compile(r"^\s*namespace:\s*['\"]?([a-z0-9][a-z0-9-]*)['\"]?\s*$", re.M)
platform_ns = set()
for root in ("bootstrap", "infra-components", "argo-workflows", "argocd", "mcp"):
    for f in pathlib.Path("platform-gitops", root).rglob("*.y*ml"):
        platform_ns.update(NS_LITERAL.findall(f.read_text(errors="replace")))
platform_ns -= set(TENANTS)
missing = platform_ns - reserved(sorted(platform_ns))
check("every literal platform namespace in gitops is on the denylist",
      not missing, f"add to tenant_name_reserved: {sorted(missing)}")

# Stub kubectl backed by a state directory: ns/<name> holds the namespace's
# mctl.me/tenant label value (empty file: no label), apps/<name> an Argo CD
# Application. A file `fail` makes every namespace lookup exit 1 (API error or
# RBAC forbidden), `appfail` the Application listing, `rbacfail` the argocd
# Role/RoleBinding deletes. Every call is appended to `log`.
KUBECTL_STUB = r"""#!/bin/sh
S="$KSTATE"
echo "kubectl $*" >> "$S/log"
case "$1 $2" in
  "get namespaces")
    [ -e "$S/fail" ] && { echo "Error from server (Forbidden)" >&2; exit 1; }
    name=${4#metadata.name=}
    [ -e "$S/ns/$name" ] && printf '%s=%s\n' "$name" "$(cat "$S/ns/$name")"
    exit 0 ;;
  "get namespace")
    [ -e "$S/fail" ] && exit 1
    [ -e "$S/ns/$3" ] || { echo "NotFound" >&2; exit 1; }
    exit 0 ;;
  "delete ns")
    rm -f "$S/ns/$3"; exit 0 ;;
  "annotate applicationset")
    exit 0 ;;
  "get app")
    case "$*" in *" -l "*) exit 0 ;; esac
    [ -e "$S/apps/$5" ]; exit $? ;;
  "delete app")
    rm -f "$S/apps/$5"; exit 0 ;;
  "get applications.argoproj.io")
    [ -e "$S/appfail" ] && { echo "Error from server (Forbidden)" >&2; exit 1; }
    ls "$S/apps"; exit 0 ;;
  "delete rolebinding,role")
    [ -e "$S/rbacfail" ] && { echo "Error from server (Forbidden)" >&2; exit 1; }
    exit 0 ;;
esac
echo "stub kubectl: unexpected call: $*" >&2
exit 3
"""


def run_kube(script, tenant, namespaces, apps=(), fail=False, wf_ns="argo-workflows",
             appfail=False, rbacfail=False, reprovision="false"):
    """Run a template script against the stub. Returns (result, log, ns left)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        (tmp / "bin").mkdir()
        (tmp / "ns").mkdir()
        (tmp / "apps").mkdir()
        (tmp / "log").write_text("")
        for name, label in namespaces.items():
            (tmp / "ns" / name).write_text(label)
        for name in apps:
            (tmp / "apps" / name).write_text("")
        if fail:
            (tmp / "fail").write_text("")
        if appfail:
            (tmp / "appfail").write_text("")
        if rbacfail:
            (tmp / "rbacfail").write_text("")
        for tool, body in (("kubectl", KUBECTL_STUB), ("sleep", "#!/bin/sh\nexit 0\n")):
            (tmp / "bin" / tool).write_text(body)
            (tmp / "bin" / tool).chmod(0o755)
        env = {"PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "KSTATE": str(tmp),
               "PARAM_TENANT_NAME": tenant, "WORKFLOW_NAMESPACE": wf_ns,
               "PARAM_REPROVISION": reprovision}
        r = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
        left = sorted(p.name for p in (tmp / "ns").iterdir())
        return r, (tmp / "log").read_text(), left


def ns_state(ns, tenant, namespaces, fail=False):
    script = GUARD + 'tenant_ns_state "$1" "$2"; echo "rc=$?"\n'
    script = script.replace('"$1" "$2"; echo', f'"{ns}" "{tenant}"; echo')
    r, _, _ = run_kube(script, tenant, namespaces, fail=fail)
    return r.stdout.strip()


check("tenant_ns_state: no namespace is absent",
      ns_state("fresh", "fresh", {}) == "absent\nrc=0")
check("tenant_ns_state: mctl.me/tenant=<tenant> is owned",
      ns_state("labs", "labs", {"labs": "labs"}) == "owned\nrc=0")
check("tenant_ns_state: an unlabelled namespace is foreign",
      ns_state("temporal", "temporal", {"temporal": ""}) == "foreign\nrc=0")
check("tenant_ns_state: another tenant's label is foreign",
      ns_state("labs", "labs", {"labs": "ovk"}) == "foreign\nrc=0")
out = ns_state("fresh", "fresh", {}, fail=True)
check("tenant_ns_state: a failed lookup is an error, not absent",
      "absent" not in out and "rc=2" in out, out)

# create-tenant: check-namespace-collision, run as the template would.
CREATE_CHECK = TEMPLATES["check-namespace-collision"]["script"]["source"]
r, _, _ = run_kube(CREATE_CHECK, "fresh", {"temporal": "", "labs": "labs"})
check("create: a fresh name with no namespace passes the live check",
      r.returncode == 0, r.stdout + r.stderr)
r, _, _ = run_kube(CREATE_CHECK, "temporal", {"temporal": ""})
check("create: 'temporal' is refused", r.returncode != 0, r.stdout)
r, _, _ = run_kube(CREATE_CHECK, "payments", {"payments": ""})
check("create: an unlabelled live namespace not on the denylist is refused",
      r.returncode != 0 and "mctl.me/tenant=payments" in r.stdout, r.stdout)
r, _, _ = run_kube(CREATE_CHECK, "payments", {"payments-preview": "other"})
check("create: a foreign <name>-preview namespace is refused",
      r.returncode != 0, r.stdout)
r, _, _ = run_kube(CREATE_CHECK, "labs", {"labs": "labs", "labs-preview": "labs"})
check("create: the tenant's own namespaces pass (reprovision)",
      r.returncode == 0, r.stdout + r.stderr)
r, _, _ = run_kube(CREATE_CHECK, "fresh", {}, fail=True)
check("create: could not list namespaces fails the check",
      r.returncode != 0 and "could not list namespaces" in r.stdout, r.stdout)

for task in pipeline:
    if task["name"] == "create-vault-policy":
        deps = set(task.get("dependencies", []))
check("create: nothing is written to Vault before every check passes",
      {"validate", "check-namespace", "check-applications"} <= deps, str(deps))
params = {p["name"]: p["value"] for t in pipeline if t["name"] == "check-applications"
          for p in t["arguments"]["parameters"]}
check("create: the Application check receives tenant_name and reprovision",
      params == {"tenant_name": "{{workflow.parameters.tenant_name}}",
                 "reprovision": "{{workflow.parameters.reprovision}}"}, str(params))

# create-tenant: check-application-collision, against the live Application
# names (as on the cluster on 2026-10-11, trimmed).
APP_CHECK = TEMPLATES["check-application-collision"]["script"]["source"]
LIVE_APPS = ("root-app", "shared-pg", "temporal-web", "admins-mctl-api",
             "admins-mctl-web", "labs-mctl-telegram", "erpact-infra",
             "tenant-labs", "tenant-admins", "my-team-web")
for name, reprov, want, why in [
        ("fresh", "false", True, "a name no Application uses passes"),
        ("lab", "false", True, "a name that is only a string prefix (lab/labs-x) passes"),
        ("my", "false", False, "a hyphen-prefix of another tenant's apps is refused"),
        ("my-team-web", "false", False, "an exact Application name is refused"),
        ("temporal", "false", False, "a hyphen-prefix of a platform Application is refused"),
        ("labs", "true", True, "reprovision: the tenant's own <T>-<svc> apps pass"),
        ("admins", "true", True, "reprovision: platform apps under the tenant prefix pass"),
        ("shared-pg", "true", False, "reprovision: an exact Application name is still refused"),
        ("labs", "false", False, "without reprovision an existing tenant's prefix is refused")]:
    r, _, _ = run_kube(APP_CHECK, name, {}, apps=LIVE_APPS, reprovision=reprov)
    check(f"create: {why}", (r.returncode == 0) == want, r.stdout + r.stderr)
r, _, _ = run_kube(APP_CHECK, "fresh", {}, apps=LIVE_APPS, appfail=True)
check("create: a failed Application listing refuses (could not list is not absent)",
      r.returncode != 0 and "could not list" in r.stdout, r.stdout + r.stderr)
r, _, _ = run_kube(APP_CHECK, "fresh", {}, apps=())
check("create: a listing without root-app refuses (incomplete read)",
      r.returncode != 0 and "root-app" in r.stdout, r.stdout + r.stderr)
r, _, _ = run_kube(APP_CHECK, "fresh", {}, apps=LIVE_APPS, reprovision="yes")
check("create: the Application check refuses a malformed reprovision",
      r.returncode != 0, r.stdout)

with tempfile.TemporaryDirectory() as d:
    empty = pathlib.Path(d) / "checkout"
    (empty / "platform-gitops" / "tenants").mkdir(parents=True)
    r = run_validate("cnpg-system", "false", empty)
    check("create: validate refuses a denylist pattern (*-system)",
          r.returncode != 0 and "reserved" in r.stdout, r.stdout)

RBAC_RE = re.compile(r"^# BEGIN tenant-argocd-rbac-cleanup\n.*?^# END tenant-argocd-rbac-cleanup\n",
                     re.S | re.M)
rbac_blocks = {}
for fname in ("wft-delete-tenant-safe.yaml", "wft-delete-tenant.yaml"):
    src = ALL_TEMPLATES[fname]["delete-k8s-resources"]["script"]["source"]
    found = RBAC_RE.findall(src)
    check(f"{fname} carries exactly one tenant-argocd-rbac-cleanup block",
          len(found) == 1, f"found {len(found)}")
    rbac_blocks[fname] = found[0] if found else None
check("every tenant-argocd-rbac-cleanup copy is byte-identical",
      len(set(rbac_blocks.values())) == 1 and None not in rbac_blocks.values())

# delete-tenant-safe and legacy delete-tenant.
for fname in ("wft-delete-tenant-safe.yaml", "wft-delete-tenant.yaml"):
    tpls = ALL_TEMPLATES[fname]
    validate = tpls["validate-tenant-exists"]["script"]["source"]
    delete = tpls["delete-k8s-resources"]["script"]["source"]
    short = fname.removeprefix("wft-").removesuffix(".yaml")

    r, _, _ = run_kube(validate, "gone", {"labs": "labs"}, apps=())
    check(f"{short}: validate passes when the namespace is absent",
          r.returncode == 0, r.stdout + r.stderr)
    r, _, _ = run_kube(validate, "acme", {"acme": "acme", "acme-preview": "acme"})
    check(f"{short}: validate passes for the tenant's own namespaces",
          r.returncode == 0, r.stdout + r.stderr)
    r, _, _ = run_kube(validate, "payments", {"payments": ""})
    check(f"{short}: validate refuses an unlabelled namespace",
          r.returncode != 0, r.stdout)
    r, _, _ = run_kube(validate, "temporal", {"temporal": "temporal"})
    check(f"{short}: validate refuses a reserved name even if labelled",
          r.returncode != 0, r.stdout)
    r, _, _ = run_kube(validate, "acme", {}, fail=True)
    check(f"{short}: validate fails when namespaces cannot be listed",
          r.returncode != 0, r.stdout)
    r, log, _ = run_kube(validate, "acme", {"acme": "acme"}, wf_ns="labs")
    check(f"{short}: validate refuses to run outside argo-workflows",
          r.returncode != 0 and "must run in namespace argo-workflows" in r.stdout
          and log == "", r.stdout + log)

    r, log, left = run_kube(delete, "acme", {"acme": "acme", "acme-preview": "acme"},
                            apps=("tenant-acme",))
    check(f"{short}: delete removes the tenant's own namespace",
          r.returncode == 0 and "acme" not in left, r.stdout + r.stderr + log)
    lines = log.splitlines()
    want = "kubectl delete rolebinding,role -n argocd -l mctl.me/tenant=acme"
    app_del = next((i for i, l in enumerate(lines) if l.startswith("kubectl delete app")), None)
    ns_del = [i for i, l in enumerate(lines) if l.startswith("kubectl delete ns")]
    rbac_del = [i for i, l in enumerate(lines) if l == want]
    check(f"{short}: delete removes the tenant's argocd Roles/RoleBindings by label",
          len(rbac_del) == 1, log)
    check(f"{short}: ...after tenant-<T> and the namespaces are deleted",
          app_del is not None and ns_del and rbac_del
          and rbac_del[0] > app_del and rbac_del[0] > max(ns_del), log)

    r, log, _ = run_kube(delete, "acme", {}, apps=())
    check(f"{short}: delete removes the argocd RBAC even when tenant-<T> is already gone",
          r.returncode == 0 and want in log, r.stdout + r.stderr + log)

    r, log, left = run_kube(delete, "acme", {"acme": "acme", "acme-preview": "acme"},
                            apps=("tenant-acme",), rbacfail=True)
    # (legacy delete-tenant never deleted <T>-preview; that is unchanged)
    check(f"{short}: a failed argocd RBAC cleanup still deletes the namespaces",
          "acme" not in left and (short == "delete-tenant" or "acme-preview" not in left),
          r.stdout + log)
    check(f"{short}: ...and fails the step",
          r.returncode != 0 and "could not delete" in r.stdout, r.stdout + r.stderr + log)

    r, log, left = run_kube(delete, "payments", {"payments": ""},
                            apps=("tenant-payments",))
    check(f"{short}: delete refuses an unlabelled namespace and touches nothing",
          r.returncode != 0 and "payments" in left and "delete" not in log,
          r.stdout + log)

    r, log, left = run_kube(delete, "acme", {"acme": "ovk"}, apps=("tenant-acme",))
    check(f"{short}: delete refuses another tenant's namespace",
          r.returncode != 0 and "acme" in left and "delete" not in log, r.stdout + log)

    r, log, _ = run_kube(delete, "acme", {"acme": "acme"}, apps=("tenant-acme",),
                         fail=True)
    check(f"{short}: delete fails (not 'not found, skipping') on a lookup error",
          r.returncode != 0 and "delete" not in log, r.stdout + log)

    r, log, _ = run_kube(delete, "acme", {}, apps=())
    check(f"{short}: delete skips an absent namespace",
          r.returncode == 0 and "delete ns" not in log, r.stdout + r.stderr + log)

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
