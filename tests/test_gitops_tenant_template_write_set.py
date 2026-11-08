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
   resourceNames or with its name), exec into pods, or create pods, through the
   Roles the chart renders. The set must equal the ledger. The workflow
   ServiceAccount's own rows are the positive control: an empty result would be
   a detector that cannot see.

Unreadable or unparsable input, a failed render, or a binding to a ClusterRole
this test has not classified is an error, never an empty set.

Run: python3 tests/test_gitops_tenant_template_write_set.py
"""
import pathlib
import sys

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
# ClusterRoles a tenant RoleBinding may name, with their rules (none of these
# touch Secrets, pods/exec or pod creation).
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


def secrets_rules(rules, secret):
    """The ways the given rules reach one Secret: read, exec, pod-create."""
    via = set()
    for r in rules or []:
        groups = set(r.get("apiGroups") or [])
        if not ({"", "*"} & groups):
            continue
        res, verbs = set(r.get("resources") or []), set(r.get("verbs") or [])
        names = r.get("resourceNames")
        if {"secrets", "*"} & res and {"get", "list", "watch", "*"} & verbs and (not names or secret in names):
            via.add("read")
        if {"pods/exec", "*"} & res and {"create", "*"} & verbs:
            via.add("exec")
        if {"pods", "*"} & res and {"create", "*"} & verbs:
            via.add("pod-create")
    return via


def reader_rows(docs, ns, secrets):
    """Rows [subject, role, via] for one namespace."""
    roles = {d["metadata"]["name"]: d.get("rules") for d in docs
             if d.get("kind") == "Role" and d["metadata"].get("namespace") == ns}
    rows = set()
    for b in docs:
        if b.get("kind") != "RoleBinding" or b["metadata"].get("namespace") != ns:
            continue
        ref = b["roleRef"]
        if ref["kind"] == "Role":
            if ref["name"] not in roles:
                raise W.ReadError(f"RoleBinding {b['metadata']['name']} in {ns} names Role {ref['name']}, not rendered")
            rules = roles[ref["name"]]
        elif ref["name"] in KNOWN_CLUSTER_ROLES:
            rules = KNOWN_CLUSTER_ROLES[ref["name"]]
        else:
            raise W.ReadError(f"RoleBinding {b['metadata']['name']} in {ns} names unclassified ClusterRole {ref['name']}")
        for s in b.get("subjects") or []:
            who = f"{s['kind']}/{s['name']}"
            for sec in secrets:
                for v in secrets_rules(rules, sec):
                    rows.add((who, ref["name"], v))
    return sorted(rows)


def produced(docs, ns):
    return {d["spec"]["target"]["name"] for d in docs
            if d.get("kind") == "ExternalSecret" and d["metadata"].get("namespace") == ns}


def tenant_namespaces(docs):
    return [d["metadata"]["name"] for d in docs if d.get("kind") == "Namespace"
            and (d["metadata"].get("labels") or {}).get("mctl.me/preview") != "true"]


def missing_secrets(reach, have):
    return sorted({s for secs in reach.values() for s in secs} - set(have))


def load_ledger():
    try:
        data = yaml.safe_load(LEDGER.read_text())
        assert isinstance(data["template_reach"], dict) and isinstance(data["readers"], list)
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

    want_rows = sorted(map(tuple, ledger["readers"]))
    check("the reader ledger has the workflow ServiceAccount as positive control",
          any(r[0] == "ServiceAccount/argo-workflow-sa" and r[2] == "read" for r in want_rows))
    n_ns = 0
    for vf in W.tenant_values():
        t = vf.parent.name
        docs = W.helm_render(CHART, vf, f"tenant-{t}", t)
        for ns in tenant_namespaces(docs):
            n_ns += 1
            have = produced(docs, ns)
            check(f"{ns}: every credential a tenant-class template reaches is rendered here",
                  not missing_secrets(reach, have), missing_secrets(reach, have))
            held = sorted(have & set(W.SECRET_NAMES))
            rows = reader_rows(docs, ns, held)
            check(f"{ns}: the subjects that reach the credentials equal the ledger",
                  rows == want_rows, (sorted(set(rows) - set(want_rows)), sorted(set(want_rows) - set(rows))))
            check(f"{ns}: the positive control is observed", ("ServiceAccount/argo-workflow-sa",
                  "argo-workflow-runner", "read") in rows, rows)
    check("tenant namespaces were rendered", n_ns > 0)
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

role = lambda rules: [{"kind": "Role", "metadata": {"name": "r", "namespace": "n"}, "rules": rules},
                      {"kind": "RoleBinding", "metadata": {"name": "b", "namespace": "n"},
                       "roleRef": {"kind": "Role", "name": "r"}, "subjects": [{"kind": "ServiceAccount", "name": "s"}]}]
core = lambda res, verbs, names=None: {"apiGroups": [""], "resources": res, "verbs": verbs, **({"resourceNames": names} if names else {})}
check("get on every Secret is a read", reader_rows(role([core(["secrets"], ["get"])]), "n", [K]) == [("ServiceAccount/s", "r", "read")])
check("get limited to another name is not a read", reader_rows(role([core(["secrets"], ["get"], ["other"])]), "n", [K]) == [])
check("get limited to the name is a read", reader_rows(role([core(["secrets"], ["get"], [K])]), "n", [K]) == [("ServiceAccount/s", "r", "read")])
check("wildcard resources reach by read, exec and pod creation",
      [r[2] for r in reader_rows(role([{"apiGroups": ["*"], "resources": ["*"], "verbs": ["*"]}]), "n", [K])] == ["exec", "pod-create", "read"])
check("pods/exec create is exec", reader_rows(role([core(["pods/exec"], ["create"])]), "n", [K]) == [("ServiceAccount/s", "r", "exec")])
check("creating Secrets only is not a read", reader_rows(role([core(["secrets"], ["create"])]), "n", [K]) == [])
try:
    reader_rows([{"kind": "RoleBinding", "metadata": {"name": "b", "namespace": "n"},
                  "roleRef": {"kind": "ClusterRole", "name": "new-role"}, "subjects": []}], "n", [K])
    check("an unclassified ClusterRole binding is an error", False)
except W.ReadError:
    check("an unclassified ClusterRole binding is an error", True)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
