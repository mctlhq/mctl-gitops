"""Render the tenant chart and pin down who may read Secrets in a tenant namespace.

A tenant namespace holds the gitops deploy key (mctl-gitops-deploy-key) and
github-actions-pat, because mctl-api submits deploy-service, preview-deploy,
provision-database and retire-service there and those mount both. Until this
test, two subjects that never need them could read them anyway:

- the team's Argo UI SSO account (argo-workflows/sso-team-<tenant>, i.e. every
  tenant member) through the cluster-wide argo-workflows-admin-extra
  ClusterRole, which grants get on every Secret;
- mctl-api, whose submit binding reused the workflow pods' own
  argo-workflow-runner Role (get secrets), although mctl-api only creates the
  handoff Secret and never reads one.

For every tenant values file, in every non-preview namespace the chart
renders:

- every RoleBinding's and ClusterRoleBinding's role is known (a Role rendered here, or a ClusterRole
  classified below), so a new binding cannot escape the check;
- only the workflow ServiceAccounts read Secrets without resourceNames;
  subjects are identified by namespace and name (the shared subject_id helper
  in gitops_write_set.py), so a ServiceAccount of the same name in another
  namespace is a different subject;
- the SSO account reads exactly the artifact-repository credentials Secret
  that the controller config names, and nothing else;
- mctl-api cannot get, list or watch any Secret.

Run: python3 tests/test_tenant_secret_readers.py
"""
import pathlib
import re
import subprocess
import sys

import yaml

import gitops_write_set as W

CHART = pathlib.Path("platform-gitops/helm-charts/tenant")
TENANTS = pathlib.Path("platform-gitops/tenants")
CONTROLLER = pathlib.Path("platform-gitops/bootstrap/templates/core-infra/argo-workflows.yaml")
READ = {"get", "list", "watch", "*"}
# ClusterRoles a tenant RoleBinding may reference, with the Secret rules they
# carry. argo-workflows-view comes from the upstream argo-workflows chart and
# only covers argoproj.io resources.
CLUSTER_ROLES = {"argo-workflows-view": []}
# Subjects that run workflow pods and mount the Secrets themselves, as
# namespace-qualified identities; "{ns}" is the tenant's own namespace. The
# central argo-workflows ServiceAccount is bound in some tenants through the
# smoke-verify Role (tenant.centralWorkflowSA.smokeVerify); which tenants may have
# it is pinned by tests/test_gitops_tenant_template_write_set.py.
WORKFLOW_SAS = {"ServiceAccount/{ns}/argo-workflow-sa", "ServiceAccount/argo-workflows/argo-workflow-sa"}
MCTL_API = "ServiceAccount/mctl-api/mctl-api"

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def render(values_file, tenant):
    proc = subprocess.run(
        ["helm", "template", f"tenant-{tenant}", str(CHART), "-f", str(values_file),
         "--namespace", tenant],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"helm template failed for {tenant}:\n{proc.stderr}")
    return [d for d in yaml.safe_load_all(proc.stdout) if d]


def secret_reads(rules):
    """(unrestricted, names): whether any rule reads all Secrets, and which
    Secrets are readable by name. Rules are parsed by the shared fail-closed
    parser: a rule that cannot be read is a ReadError, never 'no access'."""
    unrestricted, names = False, set()
    for groups, res, verbs, rnames in W.parse_rules(rules):
        if not any(W.group_match(g, "") for g in groups):
            continue
        if not any(W.resource_match(p, "secrets") for p in res):
            continue
        if not (READ & set(verbs)):
            continue
        if rnames:
            names |= set(rnames)
        else:
            unrestricted = True
    return unrestricted, names


m = re.search(r"artifactRepository:.*?accessKeySecret:\s*\n\s*name:\s*(\S+)",
              CONTROLLER.read_text(), re.S)
check(m is not None, f"could not find artifactRepository.s3.accessKeySecret.name in {CONTROLLER}")
ARTIFACT_SECRET = m.group(1) if m else None

def secret_check_binding(tenant, ns, b, rules, ref):
    """Check one binding's subjects against the Secret rules of its role."""
    name = b["metadata"]["name"]
    try:
        unrestricted, names = secret_reads(rules)
    except W.ReadError as e:
        check(False, f"{tenant}: {b['kind']} {name} in {ns}: {e}")
        return set()
    sso_names = set()
    for s in b.get("subjects") or []:
        if b["kind"] == "ClusterRoleBinding" and isinstance(s, dict) and s.get("kind") == "ServiceAccount" \
                and not s.get("namespace"):
            check(False, f"{tenant}: ClusterRoleBinding {name}: ServiceAccount subject {s.get('name')} has no namespace")
            continue
        try:
            who = W.subject_id(s, ns)
        except W.ReadError as e:
            check(False, f"{tenant}: {b['kind']} {name} in {ns}: {e}")
            continue
        if who == f"ServiceAccount/argo-workflows/sso-team-{tenant}":
            check(not unrestricted,
                  f"{tenant}: {name} in {ns} lets the SSO account {who} read every "
                  "Secret, including the gitops deploy key")
            sso_names |= names
            continue
        if who == MCTL_API:
            check(not unrestricted and not names,
                  f"{tenant}: {name} in {ns} lets mctl-api read Secrets "
                  f"({'all' if unrestricted else sorted(names)}); it only creates them")
            continue
        if unrestricted:
            # The allowance is for the namespaced shape only: a RoleBinding to a Role in
            # this namespace. A ClusterRoleBinding applies in every namespace.
            allowed = b["kind"] == "RoleBinding" and ref["kind"] == "Role"
            check(allowed and who in {w.replace("{ns}", ns) for w in WORKFLOW_SAS},
                  f"{tenant}: {b['kind']} {name} in {ns} grants get/list on every Secret to {who}")
    return sso_names


def check_tenant(tenant, docs):
    """Check one tenant's rendered documents; returns the namespaces checked."""
    namespaces = [d["metadata"]["name"] for d in docs if d["kind"] == "Namespace"
                  and d["metadata"].get("labels", {}).get("mctl.me/preview") != "true"]
    check(namespaces, f"{tenant}: the chart rendered no tenant namespace")
    try:
        cluster_roles = W.cluster_role_rules(docs)
    except W.ReadError as e:
        check(False, f"{tenant}: {e}")
        cluster_roles = {}
    for ns in namespaces:
        roles = {d["metadata"]["name"]: d.get("rules") for d in docs
                 if d["kind"] == "Role" and d["metadata"].get("namespace") == ns}
        sso_names = set()
        for b in docs:
            # A ClusterRoleBinding applies in every namespace, so it is checked in each.
            if b["kind"] not in ("RoleBinding", "ClusterRoleBinding"):
                continue
            if b["kind"] == "RoleBinding" and b["metadata"].get("namespace") != ns:
                continue
            name, ref = b["metadata"]["name"], b["roleRef"]
            if ref["kind"] == "Role":
                check(b["kind"] == "RoleBinding" and ref["name"] in roles,
                      f"{tenant}: {b['kind']} {name} in {ns} references Role {ref['name']}, "
                      "which the chart does not render in that namespace")
                rules = roles.get(ref["name"])
            else:
                check(ref["name"] in cluster_roles or ref["name"] in CLUSTER_ROLES,
                      f"{tenant}: {b['kind']} {name} in {ns} references ClusterRole "
                      f"{ref['name']}; classify its Secret access in CLUSTER_ROLES")
                rules = cluster_roles[ref["name"]] if ref["name"] in cluster_roles else CLUSTER_ROLES.get(ref["name"])
            sso_names |= secret_check_binding(tenant, ns, b, rules, ref)
        check(sso_names == {ARTIFACT_SECRET},
              f"{tenant}: the SSO account must read exactly {ARTIFACT_SECRET} in {ns} "
              f"(archived logs in the Argo UI), got {sorted(sso_names)}")
    return namespaces


checked = 0
for values_file in sorted(TENANTS.glob("*/values.yaml")):
    tenant = values_file.parent.name
    checked += len(check_tenant(tenant, render(values_file, tenant)))

check(checked > 0, "no tenant namespace rendered; the test checked nothing")

# Self-test, run on synthetic documents: the check must be green on a converged input and
# red on each deliberate mutation. The recorded failures are swapped out for the case.
def failures_of(docs):
    global failures
    saved, failures = failures, []
    try:
        check_tenant("t", docs)
        return list(failures)
    finally:
        failures = saved


def tenant_docs(rules, subject, kind="RoleBinding", ref_kind="Role"):
    sso = {"kind": "ServiceAccount", "name": "sso-team-t", "namespace": "argo-workflows"}
    meta = {"name": "x", "namespace": "t"} if kind == "RoleBinding" else {"name": "x"}
    return [
        {"kind": "Namespace", "metadata": {"name": "t"}},
        {"kind": "Role", "metadata": {"name": "all", "namespace": "t"}, "rules": rules},
        {"kind": "ClusterRole", "metadata": {"name": "all"}, "rules": rules},
        {"kind": "Role", "metadata": {"name": "art", "namespace": "t"}, "rules": [
            {"apiGroups": [""], "resources": ["secrets"], "verbs": ["get"], "resourceNames": [ARTIFACT_SECRET]}]},
        {"kind": "RoleBinding", "metadata": {"name": "sso", "namespace": "t"},
         "roleRef": {"kind": "Role", "name": "art"}, "subjects": [sso]},
        {"kind": kind, "metadata": meta, "roleRef": {"kind": ref_kind, "name": "all"}, "subjects": [subject]}]


ALL = [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get"]}]
sa = lambda ns, name="argo-workflow-sa": {"kind": "ServiceAccount", "name": name, "namespace": ns}
if ARTIFACT_SECRET:
    check(not failures_of(tenant_docs(ALL, sa("t"))), "self-test: the tenant's own workflow ServiceAccount may read every Secret")
    check(not failures_of(tenant_docs(ALL, {"kind": "ServiceAccount", "name": "argo-workflow-sa"})),
          "self-test: a ServiceAccount subject without namespace is in the binding's namespace")
    check(failures_of(tenant_docs(ALL, sa("other"))),
          "self-test: a ServiceAccount named like the workflow one in another namespace is not allowed")
    check(failures_of(tenant_docs(ALL, sa("t", "someone-else"))), "self-test: another ServiceAccount reading every Secret is flagged")
    check(failures_of(tenant_docs(ALL, sa("other", "mctl-api"))), "self-test: mctl-api named ServiceAccount elsewhere with every Secret is flagged")
    check(failures_of(tenant_docs(ALL, sa("mctl-api", "mctl-api"))), "self-test: mctl-api reading every Secret is flagged")
    NAMED = [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get"], "resourceNames": ["other"]}]
    check(failures_of(tenant_docs(NAMED, sa("mctl-api", "mctl-api"))), "self-test: mctl-api reading a named Secret is flagged")
    check(not failures_of(tenant_docs(NAMED, sa("t", "mctl-api"))),
          "self-test: a ServiceAccount named mctl-api in the tenant namespace is not the platform mctl-api")
    check(failures_of(tenant_docs(ALL, {"kind": "User", "name": "u"}, "ClusterRoleBinding", "ClusterRole")),
          "self-test: a ClusterRoleBinding granting every Secret to a user is flagged")
    check(failures_of(tenant_docs(ALL, sa("argo-workflows"), "ClusterRoleBinding", "ClusterRole")),
          "self-test: a ClusterRoleBinding to the central workflow ServiceAccount is flagged (cluster-wide read)")
    check(failures_of(tenant_docs(ALL, sa("t"), "ClusterRoleBinding", "ClusterRole")),
          "self-test: a ClusterRoleBinding to the tenant's own workflow ServiceAccount is flagged")
    check(not failures_of(tenant_docs(ALL, sa("argo-workflows"))),
          "self-test: the namespaced Role binding of the central workflow ServiceAccount is accepted")
    check(failures_of(tenant_docs(ALL, sa("argo-workflows"), "RoleBinding", "ClusterRole")),
          "self-test: a RoleBinding of the central workflow ServiceAccount through a ClusterRole is flagged")
    # fail closed: RBAC that cannot be read is an error, never "no Secret access"
    def swap(docs, rules, *, aggregated=False):
        out = []
        for d in docs:
            if d["kind"] in ("Role", "ClusterRole") and d["metadata"]["name"] == "all":
                d = dict(d, rules=rules)
                if aggregated and d["kind"] == "ClusterRole":
                    d["aggregationRule"] = {"clusterRoleSelectors": [{"matchLabels": {"x": "y"}}]}
            out.append(d)
        return out
    wf = sa("t")
    for label, bad in (("rules that are not a list", "get"),
                       ("rules as an empty mapping", {}),
                       ("a rule that is not a mapping", ["get"]),
                       ("verbs as a string", [{"apiGroups": [""], "resources": ["secrets"], "verbs": "get"}]),
                       ("resources as a string", [{"apiGroups": [""], "resources": "secrets", "verbs": ["get"]}]),
                       ("apiGroups as a string", [{"apiGroups": "", "resources": ["secrets"], "verbs": ["get"]}]),
                       ("resourceNames as a string", [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get"], "resourceNames": "x"}]),
                       ("a rule without verbs", [{"apiGroups": [""], "resources": ["secrets"]}])):
        for kind, ref_kind in (("RoleBinding", "Role"), ("ClusterRoleBinding", "ClusterRole")):
            check(failures_of(swap(tenant_docs(ALL, wf, kind, ref_kind), bad)),
                  f"self-test: {label} in a {ref_kind} is an error, not 'no access'")
    check(failures_of(swap(tenant_docs(ALL, wf, "ClusterRoleBinding", "ClusterRole"), [], aggregated=True)),
          "self-test: an aggregated ClusterRole with empty rules is an error")
    check(failures_of(swap(tenant_docs(ALL, wf, "ClusterRoleBinding", "ClusterRole"), None, aggregated=True)),
          "self-test: an aggregated ClusterRole with no rules is an error")
    check(failures_of(swap(tenant_docs(ALL, wf, "RoleBinding", "Role"), [], aggregated=True)),
          "self-test: an aggregated ClusterRole is an error even when only a Role is bound")
    check(not failures_of(swap(tenant_docs(ALL, wf), [{"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get"]}])),
          "self-test: readable rules without Secret access are no access")
    check(secret_reads([{"nonResourceURLs": ["/healthz"], "verbs": ["get"]}]) == (False, set()),
          "self-test: a pure URL rule reaches no Secret")
    check(failures_of(tenant_docs(ALL, {"kind": "ServiceAccount", "name": "argo-workflow-sa"}, "ClusterRoleBinding", "ClusterRole")),
          "self-test: a ClusterRoleBinding ServiceAccount subject without namespace is flagged")
    check(failures_of(tenant_docs(ALL, sa("argo-workflows", "sso-team-t"), "ClusterRoleBinding", "ClusterRole")),
          "self-test: a ClusterRoleBinding giving the SSO account every Secret is flagged")
    check(failures_of(tenant_docs(ALL, "x")), "self-test: a subject that is not a mapping is flagged")

if failures:
    print("\n".join(f"FAIL: {f}" for f in failures))
    sys.exit(1)
print(f"tenant Secret readers: {checked} namespaces, only workflow SAs read all Secrets")
