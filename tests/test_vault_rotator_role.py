#!/usr/bin/env python3
"""The argo-workflow-rotator Vault role grants exactly what the rotation needs.

Vault role argo-workflow carries the platform policies (every team's secrets,
platform secrets, policy management) and the rotation runs under it. The
dedicated role argo-workflow-rotator replaces that for the one job that needs
only a few KV paths. This test pins the role's reach, positively and negatively,
without a Vault server:

- the path set is DERIVED from the rotate-github-app-tokens template
  (creds_path / dest_path), not restated, so the policy cannot drift from the job;
- a small evaluator of Vault ACL semantics (exact path beats glob, longest glob
  prefix wins, deny wins) answers "may this role do X on path P";
- positive: read on the credential source, read+update on each destination;
- negative: no write on the source, no delete/create/list, nothing on other
  platform or team paths, writers/, sys/, auth/, or KV metadata;
- binding: one service account in one namespace, no wildcard, one policy;
- the policy text has no glob at all, so a broadened path is a failure, not a
  silent grant.

Exit 0 GREEN, 1 RED (a check failed), 2 UNKNOWN (an input could not be read or
parsed: never treated as pass).

Run: python3 tests/test_vault_rotator_role.py
"""
import ast
import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
VC = ROOT / "infrastructure/k3s-preview/cluster-bootstrap/vault-config"
POLICY = VC / "vault-policy-argo-workflow-rotator.hcl"
ROLE = VC / "vault-role-argo-workflow-rotator.json"
CWFT = ROOT / "platform-gitops/argo-workflows/cluster-templates/cwft-rotate-github-token.yaml"
SA_FILE = ROOT / "platform-gitops/argo-workflows/config/sa-and-rbac.yaml"
KV_PREFIX = "secret/data/"

failures = []


class Unknown(Exception):
    pass


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def parse_hcl(text):
    """Return [(path, [capabilities])]. Comments stripped; anything unparsable raises."""
    text = re.sub(r"#[^\n]*", "", text)
    rules = []
    pos = 0
    pat = re.compile(r'\s*path\s+"([^"]+)"\s*\{\s*capabilities\s*=\s*\[([^\]]*)\]\s*\}', re.S)
    while pos < len(text) and text[pos:].strip():
        m = pat.match(text, pos)
        if not m:
            raise Unknown(f"unparsable policy text near: {text[pos:pos + 60]!r}")
        caps = [c.strip().strip('"') for c in m.group(2).split(",") if c.strip()]
        rules.append((m.group(1), caps))
        pos = m.end()
    if not rules:
        raise Unknown("policy has no rules")
    return rules


def allowed(rules, path, cap):
    """Vault ACL: the most specific matching rule decides; deny wins on ties."""
    best, best_key = None, None
    for rp, caps in rules:
        if rp.endswith("*"):
            if not path.startswith(rp[:-1]):
                continue
            key = (0, len(rp))
        elif rp == path:
            key = (1, len(rp))
        else:
            continue
        if best_key is None or key > best_key:
            best, best_key = list(caps), key
        elif key == best_key:
            best += caps
    if best is None or "deny" in best:
        return False
    return cap in best


def template_code():
    doc = next(d for d in yaml.safe_load_all(CWFT.read_text()) if d["kind"] == "ClusterWorkflowTemplate")
    src = doc["spec"]["templates"][0]["script"]["source"]
    start = src.index("<< 'PYEOF'")
    return src[src.index("\n", start) + 1:src.rindex("PYEOF")]


def vault_call_args(code):
    """Argument source of every vault_get/vault_write call, plus any /v1/ URL literal."""
    calls, urls = [], []
    tree = ast.parse(code)
    inner = {id(c) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for c in n.values}
    for node in ast.walk(tree):
        if id(node) in inner:
            continue
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("vault_get", "vault_write") and node.args):
            calls.append((node.func.id, ast.unparse(node.args[0])))
        if isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            text = ast.unparse(node)
            if "/v1/" in text:
                urls.append(text)
    return calls, urls


def template_targets():
    code = template_code()
    creds, dests = set(), set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Dict):
            keys = {k.value: v for k, v in zip(node.keys, node.values)
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "creds_path" in keys and "dest_path" in keys:
                creds.add(ast.literal_eval(keys["creds_path"]))
                dests.add(ast.literal_eval(keys["dest_path"]))
    if not creds or not dests:
        raise Unknown("no creds_path/dest_path targets found in the template (it changed shape)")
    return creds, dests


def run():
    rules = parse_hcl(POLICY.read_text())
    role = json.loads(ROLE.read_text())
    creds, dests = template_targets()
    sa_docs = list(yaml.safe_load_all(SA_FILE.read_text()))

    can = lambda cap, p: allowed(rules, p, cap)  # noqa: E731

    # positive, derived from the job
    for c in sorted(creds):
        check(f"read source {c}", can("read", KV_PREFIX + c))
    for d in sorted(dests):
        check(f"read destination {d}", can("read", KV_PREFIX + d))
        check(f"update destination {d}", can("update", KV_PREFIX + d))

    # every Vault call the template makes uses only the derived targets, and the only
    # /v1/ URLs are the definitions of the two helpers plus the login
    calls, urls = vault_call_args(template_code())
    stray = [(f, a) for f, a in calls if a.replace("'", '"') not in ('t["creds_path"]', 't["dest_path"]')]
    check("vault_get/vault_write use only creds_path/dest_path", not stray and bool(calls), str(stray))
    odd = [u for u in urls if "/v1/secret/data/{path}" not in u and "auth/kubernetes/login" not in u]
    check("no other Vault URL in the template", not odd, str(odd))

    # exact reach: the policy grants nothing the job does not name
    want = {KV_PREFIX + p for p in creds | dests}
    have = {p for p, _ in rules}
    check("policy paths == template paths", have == want, f"extra={sorted(have - want)} missing={sorted(want - have)}")
    check("no glob in any policy path", not any("*" in p or "+" in p for p in have))
    check("capabilities are only read/update",
          all(set(c) <= {"read", "update"} for _, c in rules), str(rules))

    # negative
    src = KV_PREFIX + sorted(creds)[0]
    dst = KV_PREFIX + sorted(dests)[0]
    for cap in ("create", "update", "delete", "list", "patch"):
        check(f"source not {cap}-able", not can(cap, src))
    for cap in ("create", "delete", "list", "patch"):
        check(f"destination not {cap}-able", not can(cap, dst))
    foreign = [
        "secret/data/platform/github-app", "secret/data/platform/mctl-agents-other",
        "secret/data/platform/mctl-agents/extra", "secret/data/platform/vault-backup",
        "secret/data/teams/admins/mctl-support/database", "secret/data/teams/anything",
        "secret/data/writers/gitops", "secret/metadata/platform/mctl-agents",
        "secret/metadata/teams/x", "secret/delete/platform/mctl-agents",
        "secret/destroy/platform/mctl-agents", "secret/undelete/platform/mctl-agents",
        "sys/policies/acl/tenant-x", "sys/policies/acl/argo-workflow-rotator",
        "sys/auth", "sys/mounts", "auth/kubernetes/role/argo-workflow",
        "auth/kubernetes/role/argo-workflow-rotator", "database/creds/x", "identity/entity",
    ]
    for p in foreign:
        for cap in ("read", "create", "update", "delete", "list"):
            if can(cap, p):
                check(f"{cap} on {p} denied", False)
                break
        else:
            check(f"all capabilities on {p} denied", True)

    # binding
    check("one bound SA", role.get("bound_service_account_names") == ["argo-workflow-rotator-sa"])
    check("one bound namespace", role.get("bound_service_account_namespaces") == ["argo-workflows"])
    check("no wildcard binding", not any("*" in x for k in ("bound_service_account_names", "bound_service_account_namespaces")
                                         for x in role.get(k, ["*"])))
    check("exactly one policy, the rotator", role.get("token_policies") == ["argo-workflow-rotator"])
    check("not the platform role's policies", not (set(role.get("token_policies", []))
          & {"argo-workflow", "argo-workflow-platform-rotator", "argo-workflow-provisioner", "argo-workflow-teams-rw"}))
    check("alias by SA uid", role.get("alias_name_source") == "serviceaccount_uid")
    check("short token ttl", role.get("token_ttl") == "30m" and role.get("token_max_ttl") == "30m")
    check("no wider token settings", set(role) <= {
        "bound_service_account_names", "bound_service_account_namespaces", "alias_name_source",
        "token_policies", "token_ttl", "token_max_ttl"}, str(sorted(role)))
    sas = [d for d in sa_docs if d and d.get("kind") == "ServiceAccount"
           and d["metadata"]["name"] == "argo-workflow-rotator-sa"
           and d["metadata"]["namespace"] == "argo-workflows"]
    check("the bound ServiceAccount is declared", len(sas) == 1)


if __name__ == "__main__":
    try:
        run()
    except (Unknown, OSError, ValueError, KeyError, StopIteration, SyntaxError, yaml.YAMLError) as e:
        print(f"UNKNOWN  {type(e).__name__}: {e}")
        sys.exit(2)
    if failures:
        print("\nRED")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("\nGREEN")
