#!/usr/bin/env python3
"""Prove the tenant-ns-guard shell block (SEC-N101) in the tenant workflows.

The block between '# BEGIN tenant-ns-guard' and '# END tenant-ns-guard' must be
identical in create-tenant, delete-tenant-safe and delete-tenant, reject
platform namespace names, accept every existing tenant, and fail closed when
the namespace lookup errors. --selftest also proves a weakened block is caught.
"""
import os
import re
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CT = os.path.join(ROOT, "platform-gitops/argo-workflows/cluster-templates")
FILES = ["wft-create-tenant.yaml", "wft-delete-tenant-safe.yaml", "wft-delete-tenant.yaml"]
BLOCK_RE = re.compile(r"^([ \t]*)# BEGIN tenant-ns-guard\n(.*?)^[ \t]*# END tenant-ns-guard$", re.M | re.S)

REJECT = ("temporal backstage minio database forgejo zitadel kube-foo argo-rollouts "
          "cnpg-system reflector-system system-upgrade local-path-storage platform-db "
          "platform-events mctl-api grafana-iac vault-human-auth-iac argocd default").split()
ACCEPT_EXTRA = ["team1", "dev-platform"]


def dedent(indent, body):
    return "\n".join(l[len(indent):] if l.startswith(indent) else l for l in body.split("\n"))


def extract(path):
    """All guard blocks in a file, dedented."""
    text = open(path).read()
    return [dedent(m.group(1), m.group(2)) for m in BLOCK_RE.finditer(text)]


def run_sh(block, script, kubectl_body=None):
    with tempfile.TemporaryDirectory() as d:
        if kubectl_body is not None:
            k = os.path.join(d, "kubectl")
            with open(k, "w") as f:
                f.write("#!/bin/sh\n" + kubectl_body + "\n")
            os.chmod(k, os.stat(k).st_mode | stat.S_IXUSR)
        env = dict(os.environ, PATH=d + os.pathsep + os.environ["PATH"])
        r = subprocess.run(["sh", "-c", block + "\n" + script], capture_output=True, text=True, env=env)
        return r.returncode, r.stdout.strip()


def check_block(block):
    errs = []
    tenants = sorted(os.listdir(os.path.join(ROOT, "platform-gitops/tenants")))
    for n in REJECT:
        rc, _ = run_sh(block, f'tenant_name_reserved "{n}"')
        if rc != 0:
            errs.append(f"name '{n}' must be rejected")
    for n in tenants + ACCEPT_EXTRA:
        rc, _ = run_sh(block, f'tenant_name_reserved "{n}"')
        if rc == 0:
            errs.append(f"name '{n}' must be accepted")
    cases = [
        ("absent", "exit 0", 0, "absent"),
        ("owned", "printf 'acme\\tacme\\n'", 0, "owned"),
        ("unlabelled", "printf 'acme\\t\\n'", 0, "foreign"),
        ("other tenant", "printf 'acme\\tother\\n'", 0, "foreign"),
        ("lookup error", "echo forbidden >&2; exit 1", None, ""),
    ]
    for label, kbody, want_rc, want_out in cases:
        rc, out = run_sh(block, 'tenant_ns_owner_state acme acme', kbody)
        if want_rc is None:
            if rc == 0 or out:
                errs.append(f"{label}: lookup error must be non-zero with no state, got rc={rc} out={out!r}")
        elif rc != want_rc or out != want_out:
            errs.append(f"{label}: want {want_out!r}, got rc={rc} out={out!r}")
    return errs


def check_called(path, name):
    """The guard must be invoked outside its own definition in every template."""
    text = BLOCK_RE.sub("", open(path).read())
    errs = []
    if not re.search(r"\btenant_name_reserved\s+\"", text):
        errs.append(f"{name}: tenant_name_reserved is defined but never called")
    if name != "wft-delete-tenant.yaml" and not re.search(r"\$\(\s*tenant_ns_owner_state\s", text):
        errs.append(f"{name}: tenant_ns_owner_state is defined but never called")
    return errs


def check_repo():
    errs, blocks = [], {}
    for f in FILES:
        found = extract(os.path.join(CT, f))
        if not found:
            errs.append(f"{f}: no tenant-ns-guard block")
            continue
        if len(set(found)) != 1:
            errs.append(f"{f}: guard blocks differ within the file")
        blocks[f] = found[0]
        errs += check_called(os.path.join(CT, f), f)
    if len(set(blocks.values())) > 1:
        errs.append("tenant-ns-guard block differs between templates: " + ", ".join(blocks))
    if blocks:
        errs += check_block(next(iter(blocks.values())))
    return errs


def selftest():
    good = extract(os.path.join(CT, FILES[0]))[0]
    if check_block(good):
        return ["selftest: pristine block unexpectedly fails: %s" % check_block(good)]
    mutants = {
        "dropped *-system pattern": good.replace("*-system|", ""),
        "dropped temporal": good.replace("temporal|", ""),
        "ignored kubectl exit code": good.replace("|| return 2", ""),
    }
    errs = []
    for name, m in mutants.items():
        if m == good or not check_block(m):
            errs.append(f"selftest: checker did not catch mutant '{name}'")
    return errs


def main():
    errs = selftest() if "--selftest" in sys.argv else check_repo()
    for e in errs:
        print("ERROR:", e)
    if errs:
        return 1
    print("tenant-ns-guard: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
