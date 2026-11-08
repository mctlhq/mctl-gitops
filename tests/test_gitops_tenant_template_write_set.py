"""Which workflow templates that run in team namespaces can reach the gitops
write credentials, and who can read those Secrets there
(tracker: mctlhq/mctl-gitops#1033).

Three checks, each with a shrink-only ledger in
tests/fixtures/gitops-tenant-template-write-set.yaml:

a) Template-side reach. Workflow templates are split into platform templates
   (they run in the argo-workflows namespace; mirrored below from
   operations.WorkflowNamespace in mctl-api) and tenant-class templates (every
   other one, so a new template defaults to the stricter class). Following
   templateRef and workflowTemplateRef transitively, the set of write-credential
   Secrets a tenant-class template can reach must equal its ledger entry.
   Sweep covers volumes, projected sources, env secretKeyRef, envFrom, init
   containers and any other mention (see tests/gitops_write_set.py).
b) Closure per tenant. Every credential Secret a tenant-class template reaches
   is produced by an ExternalSecret that the tenant chart renders in each
   tenant namespace; otherwise the pod would wait on a missing Secret.
c) Reader-side reach, by name. For each tenant namespace that holds the Secrets,
   the subjects that can read a Secret (get, list, watch or * with no
   resourceNames or with its name), exec or attach into pods, or start a pod
   some other way (the workload-capable predicate, WORKLOAD_RESOURCES below), or
   obtain another identity or more permissions (escalation, ESCALATION_RESOURCES
   below), through the Roles and ClusterRoles the chart renders. ServiceAccount subjects
   are identified by namespace and name, so the central argo-workflows service
   account is not the tenant's own. The set must equal the ledger (the rows every
   tenant has plus the tenant's extras). The workflow ServiceAccount's own rows
   are the positive control: an empty result would be a detector that cannot see.
   Reads are one row per credential. Resource entries are matched as the
   Kubernetes RBAC authorizer does (see _resource_match). A tenant whose render
   has no non-preview Namespace, and a readers_by_tenant entry for a tenant that
   no longer exists, are failures; the real-chart mutations run on the first
   sorted tenant without extras and the test fails if they did not run.

Unreadable or unparsable input, a failed render, an RBAC rule that cannot be
parsed, or a binding to a ClusterRole this test has not classified is an error,
never an empty set.

Run: python3 tests/test_gitops_tenant_template_write_set.py
"""
import os
import pathlib
import sys
import tempfile

import yaml

import gitops_write_set as W

ROOT = W.ROOT
TPL = ROOT / "platform-gitops/argo-workflows/cluster-templates"
LEDGER = ROOT / "tests/fixtures/gitops-tenant-template-write-set.yaml"
CHART = ROOT / "platform-gitops/helm-charts/tenant"
# Templates submitted into the argo-workflows namespace (mctl-api
# internal/operations/executor.go, WorkflowNamespace) plus lifecycle-bootstrap,
# which is platform-internal. Everything not listed here is tenant-class.
PLATFORM_EXACT = {
    "create-tenant", "delete-tenant", "delete-tenant-safe", "add-custom-domain",
    "remove-custom-domain", "platform-skill-publish", "platform-skill-deprecate",
    "platform-skill-enable", "platform-skill-disable", "lifecycle-bootstrap",
}
PLATFORM_PREFIX = ("mctl-agents-",)
WORKFLOW_KINDS = {"ClusterWorkflowTemplate", "WorkflowTemplate", "CronWorkflow"}
# ClusterRoles a tenant RoleBinding may name that are not defined in this
# repository, with the rules they carry. argo-workflows-view comes from the
# upstream argo-workflows chart (get, list, watch on the Argo CRDs); none of its
# rules touch Secrets, pod exec or workload creation. A ClusterRole defined in
# the rendered output takes precedence over this table; a name in neither place
# is an error.
KNOWN_CLUSTER_ROLES = {"argo-workflows-view": []}
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:600]}")


def is_platform(name):
    return name in PLATFORM_EXACT or name.startswith(PLATFORM_PREFIX)


def refs_of(doc):
    out = set()

    def walk(n):
        if isinstance(n, dict):
            for k, v in n.items():
                if k in ("templateRef", "workflowTemplateRef") and isinstance(v, dict) and v.get("name"):
                    out.add(v["name"])
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(doc)
    return out


def own_secrets(doc):
    """Credential Secret names any container, init container or sidecar of the doc
    can read, plus every other mention (so a mechanism not modelled still counts)."""
    names = {s[3] for s in W.sites_in_doc(doc, W.SECRET_NAMES)}
    for tpls, vols in W.workflow_templates(doc):
        for t in tpls:
            tv = vols + (t.get("volumes") or [])
            conts = [t.get("script") or t.get("container") or {}]
            conts += (t.get("initContainers") or []) + (t.get("sidecars") or [])
            for c in conts:
                names |= W.container_secret_refs(c, tv)
    return names & set(W.SECRET_NAMES)


def reach_by_template(docs):
    """{template name: sorted credential Secrets it can reach} for tenant-class
    workflow templates, following references transitively."""
    wf = {d["metadata"]["name"]: d for d in docs if d.get("kind") in WORKFLOW_KINDS}
    out = {}
    for name, doc in wf.items():
        if is_platform(name):
            continue
        seen, todo, got = set(), [name], set()
        while todo:
            n = todo.pop()
            if n in seen or n not in wf:
                continue
            seen.add(n)
            got |= own_secrets(wf[n])
            todo += sorted(refs_of(wf[n]))
        if got:
            out[name] = sorted(got)
    return out


def load_template_docs():
    docs = []
    for p in W.yaml_files(TPL):
        docs += W.load_docs(p)
    if not docs:
        raise W.ReadError("no workflow templates found")
    return docs


# Workload-capable predicate: the (apiGroup, resource) pairs whose creation or
# modification starts a pod, and the verbs that count. Anything that can start a
# pod in a namespace can give it a volume, env var or envFrom that names a
# Secret there, so these are as good as reading the Secret. "*" in a rule's
# apiGroups, resources or verbs matches everything; a "*/sub"
# entry matches that subresource of any resource (see _resource_match). resourceNames is ignored on purpose: create cannot be
# limited by name, and patch/update of one named object can still change the
# pod template it runs.
_START = frozenset({"create", "patch", "update"})
WORKLOAD_RESOURCES = {
    ("", "pods"): frozenset({"create"}),
    ("", "pods/ephemeralcontainers"): frozenset({"patch", "update"}),
    ("", "replicationcontrollers"): _START,
    ("apps", "deployments"): _START,
    ("apps", "statefulsets"): _START,
    ("apps", "replicasets"): _START,
    ("apps", "daemonsets"): _START,
    ("batch", "jobs"): _START,
    ("batch", "cronjobs"): _START,
    ("argoproj.io", "workflows"): _START,
    ("argoproj.io", "cronworkflows"): _START,
    ("argoproj.io", "workflowtemplates"): _START,
}
EXEC_RESOURCES = ("pods/exec", "pods/attach")
# Privilege-escalation reach: ways to obtain the identity or the permissions of
# another subject, which is as good as having its Secret access. Counted as the
# separate way "escalation". Verbs: serviceaccounts/token create mints a token for
# a ServiceAccount; impersonate acts as a user, group or ServiceAccount; the
# RBAC objects can be written (create, update, patch) or bound/escalated past the
# caller's own permissions (bind, escalate). resourceNames is ignored as above.
# Conservative on purpose: a rule on a cluster-scoped resource (clusterroles,
# clusterrolebindings) inside a namespaced Role grants nothing in the cluster but
# is still counted. Out of scope: impersonating userextras or uids, which adds
# attributes to an identity that must itself be impersonated.
_RBAC = "rbac.authorization.k8s.io"
_RBAC_WRITE = frozenset({"create", "update", "patch", "bind", "escalate"})
ESCALATION_RESOURCES = {
    ("", "serviceaccounts/token"): frozenset({"create"}),
    ("", "users"): frozenset({"impersonate"}),
    ("", "groups"): frozenset({"impersonate"}),
    ("", "serviceaccounts"): frozenset({"impersonate"}),
    (_RBAC, "roles"): _RBAC_WRITE,
    (_RBAC, "rolebindings"): _RBAC_WRITE,
    (_RBAC, "clusterroles"): _RBAC_WRITE,
    (_RBAC, "clusterrolebindings"): _RBAC_WRITE,
}
EXEC_VERBS = frozenset({"create", "get"})
READ_VERBS = frozenset({"get", "list", "watch"})


def _strs(rule, key, required=True):
    v = rule.get(key)
    if v is None and not required:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise W.ReadError(f"unparseable RBAC rule ({key} is not a list of strings): {rule!r}"[:300])
    return v


def _group_match(pat, group):
    return pat == "*" or pat == group


def _resource_match(pat, res):
    """Whether one entry of a rule's `resources` matches the requested resource
    `res` ("pods", or "pods/exec" for a subresource). Exactly the Kubernetes RBAC
    authorizer's ResourceMatches (k8s.io/kubernetes
    plugin/pkg/auth/authorizer/rbac/rbac.go): "*" matches everything, including
    every subresource; an exact "resource" or "resource/subresource" matches
    itself; "*/subresource" matches that subresource of any resource, and only
    when the request has a subresource. "resource/*" is NOT a form the authorizer
    understands (it never matches), and neither is "*/*"; the Kubernetes RBAC
    reference documents only "*", "resource/subresource" and "*/subresource"."""
    if pat == "*" or pat == res:
        return True
    sub = res.partition("/")[2]
    return bool(sub) and pat == "*/" + sub


def _verb_match(verbs, wanted):
    return "*" in verbs or bool(set(verbs) & set(wanted))


def secrets_rules(rules, secret):
    """The ways the given rules reach one Secret: read, exec (exec or attach into
    a pod), workload-create (start a pod some other way, see WORKLOAD_RESOURCES),
    escalation (see ESCALATION_RESOURCES).
    A rule that cannot be parsed raises ReadError: it is not 'no access'."""
    via = set()
    if rules is not None and not isinstance(rules, list):
        raise W.ReadError(f"unparseable RBAC rules: {rules!r}"[:300])
    for r in rules or []:
        if not isinstance(r, dict):
            raise W.ReadError(f"unparseable RBAC rule: {r!r}"[:300])
        if "resources" not in r and r.get("nonResourceURLs"):
            continue  # URL rule: reaches no namespaced object
        groups, res, verbs = _strs(r, "apiGroups"), _strs(r, "resources"), _strs(r, "verbs")
        names = _strs(r, "resourceNames", required=False)

        def has(group, resource, wanted):
            return (any(_group_match(g, group) for g in groups)
                    and any(_resource_match(p, resource) for p in res)
                    and _verb_match(verbs, wanted))
        if has("", "secrets", READ_VERBS) and (not names or secret in names):
            via.add("read")
        if any(has("", x, EXEC_VERBS) for x in EXEC_RESOURCES):
            via.add("exec")
        if any(has(g, x, v) for (g, x), v in WORKLOAD_RESOURCES.items()):
            via.add("workload-create")
        if any(has(g, x, v) for (g, x), v in ESCALATION_RESOURCES.items()):
            via.add("escalation")
    return via


subject_id = W.subject_id


def reader_rows(docs, ns, secrets):
    """Rows [subject, role, via] for one namespace: RoleBindings in it and
    ClusterRoleBindings, through the Roles and ClusterRoles in `docs`."""
    roles = {d["metadata"]["name"]: d.get("rules") for d in docs
             if d.get("kind") == "Role" and d["metadata"].get("namespace") == ns}
    croles = {}
    for d in docs:
        if d.get("kind") == "ClusterRole":
            if d.get("aggregationRule"):
                raise W.ReadError(f"ClusterRole {d['metadata']['name']} is aggregated: its rules are not in the render")
            croles[d["metadata"]["name"]] = d.get("rules")
    rows = set()
    for b in docs:
        kind = b.get("kind")
        if kind not in ("RoleBinding", "ClusterRoleBinding"):
            continue
        if kind == "RoleBinding" and b["metadata"].get("namespace") != ns:
            continue
        ref = b["roleRef"]
        if ref["kind"] == "Role" and kind == "RoleBinding":
            if ref["name"] not in roles:
                raise W.ReadError(f"RoleBinding {b['metadata']['name']} in {ns} names Role {ref['name']}, not rendered")
            rules = roles[ref["name"]]
        elif ref["kind"] == "ClusterRole" and ref["name"] in croles:
            rules = croles[ref["name"]]
        elif ref["kind"] == "ClusterRole" and ref["name"] in KNOWN_CLUSTER_ROLES:
            rules = KNOWN_CLUSTER_ROLES[ref["name"]]
        else:
            raise W.ReadError(f"{kind} {b['metadata']['name']} in {ns} names unclassified {ref['kind']} {ref['name']}")
        for s in b.get("subjects") or []:
            if kind == "ClusterRoleBinding" and isinstance(s, dict) and s.get("kind") == "ServiceAccount" \
                    and not s.get("namespace"):
                raise W.ReadError(f"ClusterRoleBinding {b['metadata']['name']}: ServiceAccount subject without namespace")
            who = subject_id(s, ns)
            for sec in secrets:
                for v in secrets_rules(rules, sec):
                    # A read depends on the Secret (resourceNames), so it is one row
                    # per credential: moving access from one Secret to the other
                    # changes the rows. The other ways reach every Secret in the
                    # namespace, so they are one row however many credentials.
                    rows.add((who, ref["name"], f"read:{sec}" if v == "read" else v))
    return sorted(rows)


def expected_rows(ledger, tenant, ns):
    """Ledger rows for one tenant: the rows every tenant has plus its own extras.
    `{ns}` stands for the tenant namespace (the tenant-local ServiceAccount)."""
    rows = list(ledger["readers"]) + list((ledger.get("readers_by_tenant") or {}).get(tenant) or [])
    return sorted((r[0].replace("{ns}", ns), r[1], r[2]) for r in rows)


def produced(docs, ns):
    """Secret names the ExternalSecrets in `ns` produce: spec.target.name, which
    defaults to the ExternalSecret's own name. Neither readable is an error."""
    out = set()
    for d in docs:
        if d.get("kind") != "ExternalSecret" or d["metadata"].get("namespace") != ns:
            continue
        target = (d.get("spec") or {}).get("target") or {}
        name = target.get("name") or d["metadata"].get("name")
        if not isinstance(name, str) or not name:
            raise W.ReadError(f"ExternalSecret in {ns} has no readable target name")
        out.add(name)
    return out


def tenant_namespaces(docs):
    return [d["metadata"]["name"] for d in docs if d.get("kind") == "Namespace"
            and (d["metadata"].get("labels") or {}).get("mctl.me/preview") != "true"]


def tenant_ns_or_error(tenant, docs):
    """The non-preview namespaces of a rendered tenant. None is an error: a tenant
    that was not observed must not drop out of the checks."""
    nss = tenant_namespaces(docs)
    if not nss:
        raise W.ReadError(f"tenant {tenant}: the render has no non-preview Namespace")
    return nss


def mutation_tenant(ledger, tenants):
    """The tenant the real-chart mutations run on: the first in sorted order with no
    readers_by_tenant entry, so its rows are the base rows. None when there is none."""
    extras = ledger.get("readers_by_tenant") or {}
    return next((t for t in sorted(tenants) if t not in extras), None)


def stale_tenants(ledger, tenants):
    """readers_by_tenant keys with no tenant directory. Fail closed: an entry that
    outlives its tenant is an unreviewed grant kept on the ledger, so it is a
    failure, and the change that deletes the tenant deletes the entry."""
    return sorted(set(ledger.get("readers_by_tenant") or {}) - set(tenants))


def missing_secrets(reach, have):
    return sorted({s for secs in reach.values() for s in secs} - set(have))


def load_ledger():
    try:
        data = yaml.safe_load(LEDGER.read_text())
        assert isinstance(data["template_reach"], dict) and isinstance(data["readers"], list)
        assert isinstance(data.get("readers_by_tenant") or {}, dict)
        return data
    except (OSError, KeyError, TypeError, AssertionError, yaml.YAMLError) as e:
        raise W.ReadError(f"{LEDGER}: {e}") from e


# ---- converged input --------------------------------------------------------------------
try:
    ledger = load_ledger()
    reach = reach_by_template(load_template_docs())
    want = {k: sorted(v) for k, v in ledger["template_reach"].items()}
    check("tenant-class templates reach no credential beyond the ledger",
          all(set(v) <= set(want.get(k, [])) for k, v in reach.items()),
          {k: v for k, v in reach.items() if not set(v) <= set(want.get(k, []))})
    check("every ledger entry still reaches its credential (ledger can only shrink)",
          all(set(v) <= set(reach.get(k, [])) for k, v in want.items()),
          {k: v for k, v in want.items() if not set(v) <= set(reach.get(k, []))})
    check("the ledger observed something", len(want) > 0)

    POSITIVE = ("ServiceAccount/{ns}/argo-workflow-sa", "argo-workflow-runner", f"read:{W.SECRET_NAMES[0]}")
    check("the reader ledger has the workflow ServiceAccount as positive control",
          any(r[0] == POSITIVE[0] and r[2].startswith("read:") for r in ledger["readers"]))
    n_ns = 0
    tenants_seen = set()
    rendered = {}  # tenant -> (values file, rendered docs, namespaces)
    for vf in W.tenant_values():
        t = vf.parent.name
        docs = W.helm_render(CHART, vf, f"tenant-{t}", t)
        nss = tenant_ns_or_error(t, docs)
        rendered[t] = (vf, docs, nss)
        tenants_seen.add(t)
        for ns in nss:
            n_ns += 1
            have = produced(docs, ns)
            check(f"{ns}: every credential a tenant-class template reaches is rendered here",
                  not missing_secrets(reach, have), missing_secrets(reach, have))
            held = sorted(have & set(W.SECRET_NAMES))
            rows = reader_rows(docs, ns, held)
            want_rows = expected_rows(ledger, t, ns)
            check(f"{ns}: the subjects that reach the credentials equal the ledger",
                  rows == want_rows, (sorted(set(rows) - set(want_rows)), sorted(set(want_rows) - set(rows))))
            pos = (POSITIVE[0].replace("{ns}", ns),) + POSITIVE[1:]
            check(f"{ns}: the positive control is observed", pos in rows, rows)
    check("tenant namespaces were rendered", n_ns > 0)
    stale = stale_tenants(ledger, tenants_seen)
    check("readers_by_tenant names only tenants that exist (delete the entry with the tenant)", not stale, stale)

    # Real-chart mutations. The tenant is the first one, in sorted order, that has no
    # readers_by_tenant entry, so its rows are the base rows and each mutation must
    # add rows to them. No fixed tenant name: renaming or deleting a tenant cannot
    # silently remove the cases, and the counter below fails if none ran.
    mut_tenant = mutation_tenant(ledger, rendered)
    check("a real-chart mutation tenant was found (one without readers_by_tenant extras)", mut_tenant is not None)
    mutations_run = 0
    if mut_tenant is not None:
        vf, _, nss = rendered[mut_tenant]
        for ns in nss:
            have = produced(rendered[mut_tenant][1], ns)
            held = sorted(have & set(W.SECRET_NAMES))
            want_rows = expected_rows(ledger, mut_tenant, ns)
            for label, args in (("the central ServiceAccount binding turned on",
                                 ("--set", "tenant.centralWorkflowSA.smokeVerify=true")),
                                ("a central restart grant added",
                                 ("--set", "tenant.centralWorkflowSA.restartDeployments={x}"))):
                mut = reader_rows(W.helm_render(CHART, vf, f"tenant-{mut_tenant}", mut_tenant, args), ns, held)
                mutations_run += 1
                added = sorted(set(mut) - set(want_rows))
                check(f"{ns}: {label} adds rows that are not in the ledger", bool(added), added)
    check("the real-chart mutation cases ran (two per mutation tenant namespace)",
          mut_tenant is not None and mutations_run >= 2, mutations_run)
except W.ReadError as e:
    check("the repository could be observed", False, e)

# ---- mutations --------------------------------------------------------------------------
K, P = W.SECRET_NAMES
VOL = [{"name": "k", "secret": {"secretName": K}}]


def wft(name, tpl, extra_spec=None):
    return {"kind": "ClusterWorkflowTemplate", "metadata": {"name": name},
            "spec": dict({"templates": [tpl]}, **(extra_spec or {}))}


mount = {"name": "t", "volumes": VOL, "script": {"source": "x", "volumeMounts": [{"name": "k", "mountPath": "/k"}]}}
check("a tenant-class template mounting the key is reached", reach_by_template([wft("a", mount)]) == {"a": [K]})
check("a platform template mounting the key is not tenant-class",
      reach_by_template([wft("mctl-agents-run", mount), wft("create-tenant", mount)]) == {})
check("a reference to a template that mounts the key is followed",
      reach_by_template([wft("a", {"name": "t", "steps": [[{"name": "s", "templateRef": {"name": "b", "template": "t"}}]]}),
                         wft("b", mount)]) == {"a": [K], "b": [K]})
check("env secretKeyRef is reached", reach_by_template([wft("a", {"name": "t", "script": {"source": "x", "env": [
    {"name": "A", "valueFrom": {"secretKeyRef": {"name": P, "key": "token"}}}]}})]) == {"a": [P]})
check("envFrom is reached", reach_by_template([wft("a", {"name": "t", "container": {
    "envFrom": [{"secretRef": {"name": K}}]}})]) == {"a": [K]})
check("an init container mount is reached", reach_by_template([wft("a", {"name": "t", "volumes": VOL, "script": {"source": "x"},
    "initContainers": [{"name": "i", "volumeMounts": [{"name": "k", "mountPath": "/k"}]}]})]) == {"a": [K]})
check("a CronWorkflow's inline workflowSpec is reached", reach_by_template([{
    "kind": "CronWorkflow", "metadata": {"name": "c"},
    "spec": {"workflowSpec": {"volumes": VOL, "templates": [{"name": "t", "script": {
        "source": "x", "volumeMounts": [{"name": "k", "mountPath": "/k"}]}}]}}}]) == {"c": [K]})
check("a commented-out mount is not reached", reach_by_template([wft("a", {"name": "t", "script": {"source": f"# {K}\nx"}})]) == {})
check("a missing ExternalSecret is reported", missing_secrets({"a": [K, P]}, {K}) == [P])
check("nothing missing when the tenant renders both", missing_secrets({"a": [K, P]}, {K, P}) == [])

def role(rules, subjects=None, binding_ns="n", role_ns="n"):
    return [{"kind": "Role", "metadata": {"name": "r", "namespace": role_ns}, "rules": rules},
            {"kind": "RoleBinding", "metadata": {"name": "b", "namespace": binding_ns},
             "roleRef": {"kind": "Role", "name": "r"},
             "subjects": subjects or [{"kind": "ServiceAccount", "name": "s"}]}]


def rows_of(rules, secrets=(K,), **kw):
    return reader_rows(role(rules, **kw), "n", list(secrets))


def raises(fn):
    try:
        fn()
    except W.ReadError:
        return True
    return False


def rule(groups, res, verbs, names=None):
    return {"apiGroups": groups, "resources": res, "verbs": verbs, **({"resourceNames": names} if names else {})}


core = lambda res, verbs, names=None: rule([""], res, verbs, names)
SA = "ServiceAccount/n/s"
RK = f"read:{K}"
check("get on every Secret is a read", rows_of([core(["secrets"], ["get"])]) == [(SA, "r", RK)])
check("get limited to another name is not a read", rows_of([core(["secrets"], ["get"], ["other"])]) == [])
check("get limited to the name is a read", rows_of([core(["secrets"], ["get"], [K])]) == [(SA, "r", RK)])
# one row per credential: a resourceNames edit that moves access from one Secret to the other
# must change the rows, and a rule that names both gives one row each
check("get limited to the other credential is a read of that one only",
      rows_of([core(["secrets"], ["get"], [P])], secrets=(K, P)) == [(SA, "r", f"read:{P}")])
check("moving resourceNames from one credential to the other changes the rows",
      rows_of([core(["secrets"], ["get"], [K])], secrets=(K, P)) != rows_of([core(["secrets"], ["get"], [P])], secrets=(K, P)))
check("get on both credentials is one row each",
      rows_of([core(["secrets"], ["get"], [K, P])], secrets=(K, P)) == [(SA, "r", f"read:{P}"), (SA, "r", RK)])
check("exec and workload-create stay one row however many credentials are held",
      rows_of([core(["pods/exec"], ["create"]), core(["pods"], ["create"])], secrets=(K, P)) ==
      [(SA, "r", "exec"), (SA, "r", "workload-create")])
check("wildcard group, resources and verbs reach by every way",
      [r[2] for r in rows_of([rule(["*"], ["*"], ["*"])])] == ["escalation", "exec", RK, "workload-create"])
check("pods/exec create is exec", rows_of([core(["pods/exec"], ["create"])]) == [(SA, "r", "exec")])
check("pods/exec get (legacy websocket exec) is exec", rows_of([core(["pods/exec"], ["get"])]) == [(SA, "r", "exec")])
check("pods/attach create is exec", rows_of([core(["pods/attach"], ["create"])]) == [(SA, "r", "exec")])
check("pods/* is not a form the authorizer matches: it reaches nothing",
      rows_of([core(["pods/*"], ["create"])]) == [])
check("creating Secrets only is not a read", rows_of([core(["secrets"], ["create"])]) == [])
check("an empty Role reaches nothing", rows_of(None) == [] and rows_of([]) == [])
check("a nonResourceURLs rule reaches nothing", rows_of([{"nonResourceURLs": ["/healthz"], "verbs": ["get"]}]) == [])

# The resources and verbs that must count, written out independently of the table so
# that dropping one from WORKLOAD_RESOURCES goes red.
MUST_START = [("", "pods", "create"), ("", "pods/ephemeralcontainers", "patch"),
              ("", "pods/ephemeralcontainers", "update"), ("", "replicationcontrollers", "create")]
MUST_START += [(g, r, v) for g, rs in (("apps", ("deployments", "statefulsets", "replicasets", "daemonsets")),
                                       ("batch", ("jobs", "cronjobs")),
                                       ("argoproj.io", ("workflows", "cronworkflows", "workflowtemplates")))
               for r in rs for v in ("create", "patch", "update")]
for group, res, v in MUST_START:
    check(f"{res} ({group or 'core'}) {v} must be workload-create",
          rows_of([rule([group], [res], [v])]) == [(SA, "r", "workload-create")])

# workload-capable: every resource in WORKLOAD_RESOURCES, with each verb that counts
# and one that does not, so removing a resource or a verb from the table goes red.
for (group, res), verbs in sorted(WORKLOAD_RESOURCES.items()):
    for v in sorted(verbs):
        check(f"{res} ({group or 'core'}) {v} is workload-create",
              rows_of([rule([group], [res], [v])]) == [(SA, "r", "workload-create")])
    check(f"{res} ({group or 'core'}) get/list/watch/delete is not workload-create",
          rows_of([rule([group], [res], ["get", "list", "watch", "delete"])]) == [])
    check(f"{res} ({group or 'core'}) in another API group is not workload-create",
          rows_of([rule(["other.example"], [res], ["*"])]) == [])
    check(f"{res} ({group or 'core'}) with the wildcard verb and limited by name is workload-create",
          rows_of([rule([group], [res], ["*"], ["one"])]) == [(SA, "r", "workload-create")])
check("a wildcard resource in the apps group is workload-create",
      rows_of([rule(["apps"], ["*"], ["create"])]) == [(SA, "r", "workload-create")])
check("a wildcard API group on workflows is workload-create",
      rows_of([rule(["*"], ["workflows"], ["patch"])]) == [(SA, "r", "workload-create")])
check("a wildcard verb on workflows is workload-create",
      rows_of([rule(["argoproj.io"], ["workflows"], ["*"])]) == [(SA, "r", "workload-create")])
check("a rule that lists several resources reports the workload one",
      rows_of([rule(["apps"], ["services", "deployments"], ["update"])]) == [(SA, "r", "workload-create")])
check("read-only access to workflows and deployments is not workload-create",
      rows_of([rule(["argoproj.io", "apps"], ["workflows", "deployments"], ["get", "list", "watch"])]) == [])

# Resource spellings, as the Kubernetes RBAC authorizer reads them (ResourceMatches):
# "*", exact "resource" or "resource/subresource", and "*/subresource". Written out
# independently of the tables: (group, resource as requested, verbs that count, way).
MUST_WAYS = [("", "pods/exec", ("create", "get"), "exec"), ("", "pods/attach", ("create", "get"), "exec"),
             ("", "pods/ephemeralcontainers", ("patch", "update"), "workload-create"),
             ("", "serviceaccounts/token", ("create",), "escalation"),
             ("", "users", ("impersonate",), "escalation"), ("", "groups", ("impersonate",), "escalation"),
             ("", "serviceaccounts", ("impersonate",), "escalation")]
MUST_WAYS += [("rbac.authorization.k8s.io", r, ("create", "update", "patch", "bind", "escalate"), "escalation")
              for r in ("roles", "rolebindings", "clusterroles", "clusterrolebindings")]
MUST_WAYS += [(g, r, ("create", "patch", "update"), "workload-create") for g, r in (
    ("", "replicationcontrollers"), ("apps", "deployments"), ("apps", "statefulsets"), ("apps", "replicasets"),
    ("apps", "daemonsets"), ("batch", "jobs"), ("batch", "cronjobs"), ("argoproj.io", "workflows"),
    ("argoproj.io", "cronworkflows"), ("argoproj.io", "workflowtemplates"))]
MUST_WAYS += [("", "pods", ("create",), "workload-create")]
for group, res, verbs, way in MUST_WAYS:
    parent, _, sub = res.partition("/")
    spellings = [res] + (["*/" + sub] if sub else [])
    for pat in spellings:
        for v in verbs:
            check(f"{way}: {group or 'core'} resources [{pat}] verb {v} is counted",
                  rows_of([rule([group], [pat], [v])]) == [(SA, "r", way)])
        check(f"{way}: {group or 'core'} resources [{pat}] with the wildcard verb and a resourceName is counted",
              rows_of([rule([group], [pat], ["*"], ["one"])]) == [(SA, "r", way)])
        check(f"{way}: {group or 'core'} resources [{pat}] in another API group is not counted",
              rows_of([rule(["other.example"], [pat], list(verbs))]) == [])
    check(f"{way}: {group or 'core'} resources [{res}] with only get/list/watch/delete or no matching verb is not counted",
          rows_of([rule([group], [res], [v for v in ("list", "watch", "delete") if v not in verbs])]) == [])
    # Spellings the authorizer does not match: "resource/*", "*/*", "*/<another subresource>",
    # and the parent alone for a subresource.
    for bad in (res + "/*", parent + "/*", "*/*", "*/zzz"):
        check(f"{way}: {group or 'core'} resources [{bad}] is not matched (not an authorizer form)",
              rows_of([rule([group], [bad], list(verbs))]) == [])
    if sub:
        check(f"{way}: {group or 'core'} resources [{parent}] alone does not match the subresource {sub}",
              rows_of([rule([group], [parent], [v for v in verbs if v != "create" or parent != "pods"])]) == [])
check("*/exec in a rule that lists several resources reports the exec way",
      rows_of([core(["configmaps", "*/exec"], ["create"])]) == [(SA, "r", "exec")])
check("*/subresource does not match a resource that has no subresource",
      rows_of([core(["*/exec"], ["get"])]) == [(SA, "r", "exec")] and rows_of([core(["*/exec"], ["list"])]) == [])
check("the bare resource wildcard matches subresources too",
      [r[2] for r in rows_of([core(["*"], ["create"])])] == ["escalation", "exec", "workload-create"])
check("a read of Secrets through resources */secrets does not count (no such subresource)",
      rows_of([core(["*/secrets"], ["get"])]) == [])
# _resource_match itself, against the authorizer's table
for pat, res, want in (("*", "pods", True), ("*", "pods/exec", True), ("pods", "pods", True), ("pods", "pods/exec", False),
                       ("pods/exec", "pods/exec", True), ("pods/exec", "pods", False), ("*/exec", "pods/exec", True),
                       ("*/exec", "pods", False), ("*/exec", "pods/attach", False), ("pods/*", "pods/exec", False),
                       ("pods/*", "pods", False), ("*/*", "pods/exec", False), ("*/*", "pods", False),
                       ("*/exe", "pods/exec", False), ("*/xec", "pods/exec", False), ("", "pods", False)):
    check(f"_resource_match({pat!r}, {res!r}) is {want}", _resource_match(pat, res) is want)

# the tenant chosen for the real-chart mutations, and what a render without a namespace is
check("the mutation tenant is the first sorted one without extras",
      mutation_tenant({"readers_by_tenant": {"a": []}}, ["c", "b", "a"]) == "b")
check("the mutation tenant is chosen when readers_by_tenant is missing", mutation_tenant({}, ["b", "a"]) == "a")
check("no mutation tenant when every tenant has extras", mutation_tenant({"readers_by_tenant": {"a": []}}, ["a"]) is None)
check("a render with only a preview namespace is an error", raises(lambda: tenant_ns_or_error(
    "t", [{"kind": "Namespace", "metadata": {"name": "p", "labels": {"mctl.me/preview": "true"}}}])))
check("a render with no Namespace is an error", raises(lambda: tenant_ns_or_error("t", [])))
check("a render with a namespace returns it", tenant_ns_or_error(
    "t", [{"kind": "Namespace", "metadata": {"name": "t"}}]) == ["t"])
check("a readers_by_tenant entry for a deleted tenant is reported",
      stale_tenants({"readers_by_tenant": {"gone": [], "here": []}}, {"here"}) == ["gone"])
check("no stale tenants when every entry has its tenant", stale_tenants({"readers_by_tenant": {"here": []}}, {"here"}) == [])
check("no stale tenants when the ledger has no readers_by_tenant", stale_tenants({}, {"here"}) == [])

# fail closed: a rule that cannot be understood is an error, never 'no access'
for label, bad in (("a rule that is not a mapping", ["create"]),
                   ("verbs that are not a list", [{"apiGroups": [""], "resources": ["pods"], "verbs": "create"}]),
                   ("resources missing", [{"apiGroups": [""], "verbs": ["create"]}]),
                   ("apiGroups missing", [{"resources": ["pods"], "verbs": ["create"]}]),
                   ("a non-string verb", [{"apiGroups": [""], "resources": ["pods"], "verbs": [1]}]),
                   ("resourceNames that are not a list", [{"apiGroups": [""], "resources": ["pods"], "verbs": ["get"],
                                                            "resourceNames": "x"}])):
    check(f"an unparseable rule is an error: {label}", raises(lambda bad=bad: rows_of(bad)))
check("rules that are not a list is an error", raises(lambda: rows_of({"verbs": ["get"]})))
check("an unclassified ClusterRole binding is an error", raises(lambda: reader_rows(
    [{"kind": "RoleBinding", "metadata": {"name": "b", "namespace": "n"},
      "roleRef": {"kind": "ClusterRole", "name": "new-role"}, "subjects": []}], "n", [K])))
check("a binding to a Role that is not rendered is an error", raises(lambda: reader_rows(
    [{"kind": "RoleBinding", "metadata": {"name": "b", "namespace": "n"},
      "roleRef": {"kind": "Role", "name": "gone"}, "subjects": []}], "n", [K])))
check("a subject that is not a mapping is an error", raises(lambda: rows_of([core(["pods"], ["create"])], subjects=["x"])))

# subjects carry their namespace
LOCAL = {"kind": "ServiceAccount", "name": "s"}
check("a ServiceAccount subject without a namespace is in the binding's namespace",
      rows_of([core(["secrets"], ["get"])], subjects=[LOCAL]) == [("ServiceAccount/n/s", "r", RK)])
central = {"kind": "ServiceAccount", "name": "s", "namespace": "argo-workflows"}
check("the same ServiceAccount name in another namespace is a different subject",
      rows_of([core(["secrets"], ["get"])], subjects=[LOCAL, central]) ==
      [("ServiceAccount/argo-workflows/s", "r", RK), ("ServiceAccount/n/s", "r", RK)])
check("Users and Groups are kind/name",
      [r[0] for r in rows_of([core(["secrets"], ["get"])], subjects=[
          {"kind": "User", "name": "u"}, {"kind": "Group", "name": "g"}])] == ["Group/g", "User/u"])

# ClusterRoles: rendered ones are read, aggregated ones and bindings to unknown ones are errors,
# a ClusterRoleBinding applies in every namespace
crole = lambda rules, **extra: {"kind": "ClusterRole", "metadata": {"name": "cr"}, "rules": rules, **extra}
rb = {"kind": "RoleBinding", "metadata": {"name": "b", "namespace": "n"},
      "roleRef": {"kind": "ClusterRole", "name": "cr"}, "subjects": [LOCAL]}
crb = {"kind": "ClusterRoleBinding", "metadata": {"name": "b"},
       "roleRef": {"kind": "ClusterRole", "name": "cr"}, "subjects": [central]}
check("a RoleBinding to a rendered ClusterRole grants its rules in the namespace",
      reader_rows([crole([rule(["apps"], ["deployments"], ["create"])]), rb], "n", [K]) ==
      [("ServiceAccount/n/s", "cr", "workload-create")])
check("a ClusterRoleBinding grants its rules in the namespace",
      reader_rows([crole([rule(["apps"], ["deployments"], ["create"])]), crb], "n", [K]) ==
      [("ServiceAccount/argo-workflows/s", "cr", "workload-create")])
check("an aggregated ClusterRole is an error", raises(lambda: reader_rows(
    [crole(None, aggregationRule={"clusterRoleSelectors": []}), rb], "n", [K])))
check("a ClusterRoleBinding with a ServiceAccount subject without namespace is an error", raises(lambda: reader_rows(
    [crole([]), dict(crb, subjects=[LOCAL])], "n", [K])))
check("a RoleBinding in another namespace is not counted", reader_rows(
    [crole([rule(["apps"], ["deployments"], ["create"])]), dict(rb, metadata={"name": "b", "namespace": "other"})], "n", [K]) == [])

# the ledger: per-tenant extras, and the namespace placeholder
LED = {"readers": [["ServiceAccount/{ns}/a", "r", "read"]],
       "readers_by_tenant": {"t1": [["ServiceAccount/argo-workflows/a", "r", "exec"]]}}
check("expected rows: the base rows with the tenant namespace", expected_rows(LED, "t2", "t2") == [("ServiceAccount/t2/a", "r", "read")])
check("expected rows: a tenant's extras are added",
      expected_rows(LED, "t1", "t1") == [("ServiceAccount/argo-workflows/a", "r", "exec"), ("ServiceAccount/t1/a", "r", "read")])
check("a tenant that is not in readers_by_tenant gets no extras: turning a central grant on for it is a difference",
      expected_rows(LED, "t3", "t3") != sorted(expected_rows(LED, "t1", "t1")))

# ExternalSecret target names
es = lambda name, spec: {"kind": "ExternalSecret", "metadata": {"name": name, "namespace": "n"}, "spec": spec}
check("an ExternalSecret's Secret name is spec.target.name", produced([es("x", {"target": {"name": K}})], "n") == {K})
check("an ExternalSecret without target.name produces a Secret named after itself", produced([es(P, {})], "n") == {P})
check("an ExternalSecret with a null target produces a Secret named after itself", produced([es(P, {"target": None})], "n") == {P})
check("an ExternalSecret with no readable name is an error", raises(lambda: produced([es("", {})], "n")))
check("an ExternalSecret in another namespace is not counted", produced([dict(es(K, {}), metadata={"name": K, "namespace": "z"})], "n") == set())

# tenant_values skips what is not a tenant directory, and fails on what cannot be read
with tempfile.TemporaryDirectory() as td:
    base = pathlib.Path(td)
    (base / "a").mkdir()
    (base / "a/values.yaml").write_text("x: 1\n")
    (base / "b").mkdir()
    (base / "README.md").write_text("x\n")
    (base / ".DS_Store").write_bytes(b"\x00")
    check("tenant_values skips files in the tenants directory and directories without values.yaml",
          [p.parent.name for p in W.tenant_values(base)] == ["a"])
    (base / "a/values.yaml").unlink()
    check("tenant_values with no tenant at all is an error", raises(lambda: W.tenant_values(base)))
    (base / "c").mkdir()
    (base / "c/values.yaml").write_text("x: 1\n")
    (base / "c").chmod(0)
    try:
        if os.access(base / "c", os.R_OK):
            print("SKIP  unreadable tenant directory case: permissions not enforced "
                  f"(euid={os.geteuid()})")
        else:
            check("tenant_values on a directory that cannot be entered is a ReadError",
                  raises(lambda: W.tenant_values(base)))
    finally:
        (base / "c").chmod(0o755)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
