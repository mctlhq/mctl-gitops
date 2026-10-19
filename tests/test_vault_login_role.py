#!/usr/bin/env python3
"""Tenant workflows log in to Vault with their own tenant role only.

deploy-service, provision-database and retire-service run as
{tenant}/argo-workflow-sa. The Vault role argo-workflow carries the platform
policies (every team's secrets, platform secrets, policy management), so a
template reachable from a tenant namespace must not ask for it. Each login
derives the role from the pod's namespace instead: argo-workflows (the
children wft-smoke-test submits) keeps argo-workflow, any other namespace
gets argo-workflow-tenant-<namespace>, which Vault binds to that namespace.

This checks, by running the role choice rather than grepping for it:
- every login in a non-platform template derives the role from the namespace;
- the shell and Python variants agree for argo-workflows, a tenant and an
  empty namespace (which must not fall back to the platform role);
- wft-create-tenant creates the tenant role bound to the tenant namespace
  with the tenant-<t> policy, and both delete-tenant variants delete it.

Run: python3 tests/test_vault_login_role.py
"""
import pathlib
import re
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = ROOT / "platform-gitops/argo-workflows/cluster-templates"
# Templates that only ever run in argo-workflows and need the platform role.
PLATFORM_ONLY = {
    "wft-create-tenant.yaml", "wft-delete-tenant.yaml", "wft-delete-tenant-safe.yaml",
    "cwft-rotate-github-token.yaml", "wft-smoke-test.yaml",
    "cwft-zitadel-login-consolidation.yaml", "wft-bootstrap-platform.yaml",
}
SHELL_CHOICE = re.compile(
    r"^( *)SA_NS=\$\(cat /var/run/secrets/kubernetes\.io/serviceaccount/namespace\)\n"
    r"(\1case \"\$SA_NS\" in\n.*?^\1esac)$", re.S | re.M)
PY_CHOICE = re.compile(r'^ *role = ("argo-workflow" if ns == .*)$', re.M)

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def sources(path):
    for doc in yaml.safe_load_all(path.read_text()):
        for t in ((doc or {}).get("spec") or {}).get("templates") or []:
            src = (t.get("script") or {}).get("source")
            if src:
                yield t["name"], src


def shell_role(block, ns):
    r = subprocess.run(["sh", "-c", block + '\nprintf %s "$VAULT_ROLE"'],
                       env={"PATH": "/usr/bin:/bin", "SA_NS": ns}, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else f"<exit {r.returncode}>"


def py_role(expr, ns):
    return eval(expr, {}, {"ns": ns})


def want(ns):
    return "argo-workflow" if ns == "argo-workflows" else f"argo-workflow-tenant-{ns}"


# 1. Every login outside the platform-only templates chooses by namespace.
logins = 0
for path in sorted(T.glob("*.yaml")):
    if path.name in PLATFORM_ONLY:
        continue
    for name, src in sources(path):
        n = src.count("auth/kubernetes/login")
        if not n:
            continue
        logins += n
        where = f"{path.name}/{name}"
        check(f"{where}: no literal argo-workflow role",
              not re.search(r'role\\?"\s*:\s*\\?"argo-workflow\\?"|role=argo-workflow\b', src))
        shells, pys = SHELL_CHOICE.findall(src), PY_CHOICE.findall(src)
        check(f"{where}: one namespace-derived role per login",
              len(shells) + len(pys) == n, (len(shells), len(pys), n))
        if shells:
            check(f"{where}: the shell login sends $VAULT_ROLE",
                  src.count('\\"role\\":\\"${VAULT_ROLE}\\"') == len(shells))
        if pys:
            check(f"{where}: the Python login sends role", '"role": role' in src)
        for _, block in shells:
            for ns in ("argo-workflows", "labs", "erpact"):
                got = shell_role(block, ns)
                check(f"{where}: shell, namespace {ns} -> {want(ns)}", got == want(ns), got)
            got = shell_role(block, "")
            check(f"{where}: shell, empty namespace is not the platform role",
                  got != "argo-workflow", got)
        for expr in pys:
            for ns in ("argo-workflows", "labs", "erpact"):
                got = py_role(expr, ns)
                check(f"{where}: python, namespace {ns} -> {want(ns)}", got == want(ns), got)
            check(f"{where}: python, empty namespace is not the platform role",
                  py_role(expr, "") != "argo-workflow")
check("found the tenant logins (tpl-vault-write x3, provision-database x1)",
      logins >= 4, logins)

# 2. create-tenant makes the role; delete-tenant removes it.
create = (T / "wft-create-tenant.yaml").read_text()
m = re.search(r'vault write "auth/kubernetes/role/argo-workflow-tenant-\$\{TENANT\}" \\\n'
              r'((?: +.*\\\n)* +.*\n)', create)
check("create-tenant writes argo-workflow-tenant-${TENANT}", bool(m))
if m:
    args = m.group(1)
    for arg in ('bound_service_account_names=argo-workflow-sa',
                'bound_service_account_namespaces="${TENANT}"',
                'token_policies="tenant-${TENANT}"'):
        check(f"create-tenant role: {arg}", arg in args, args)
    check("create-tenant role: no wildcard namespace", "*" not in args, args)
for f in ("wft-delete-tenant.yaml", "wft-delete-tenant-safe.yaml"):
    src = (T / f).read_text()
    # delete-vault-policy deletes and reads back each role; its behaviour is
    # exercised in tests/test_wft_delete_tenant_vault.py.
    check(f"{f} deletes the tenant role",
          'f"argo-workflow-tenant-{tenant}"' in src
          and 'delete(f"auth/kubernetes/role/{role}", "role")' in src)

if failures:
    print("\nFAILURES:\n" + "\n".join(failures), file=sys.stderr)
    sys.exit(1)
print("\nAll checks passed.")
