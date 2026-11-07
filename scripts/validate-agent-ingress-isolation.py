#!/usr/bin/env python3
"""Evaluate the union of repository NetworkPolicies for agent pods (mctl-gitops#2289).

Agent step pods share the `argo-workflows` namespace with platform workflow
pods (#807 HARDEN_IN_PLACE), so isolation is carried by pod selectors. This
check loads every NetworkPolicy (raw manifests under platform-gitops/ plus any
rendered chart files given as arguments), and for each synthetic source pod
and destination pod evaluates the UNION of all policies selecting the
destination, the way a CNI does: allowed if no policy selects the destination,
else if any rule of any selecting policy matches source and port.

The result is compared with an expected allow/deny matrix. Two matrices exist:

  TODAY   what the repository admits now. This is what CI enforces
          (step A of #2289; no NetworkPolicy is changed by it).
  TARGET  what #2301 (step B) must reach. Each #2301 policy PR moves cells
          from TODAY to TARGET and switches the default here.

A second lint rejects any peer whose namespaceSelector matches
`argo-workflows` without a podSelector. The peers that still do are listed in
NAMESPACE_ONLY_BASELINE; #2301 empties that list.

Selector semantics (matchLabels, In, NotIn, Exists, DoesNotExist) follow the
Kubernetes API. Whether the CNI (kube-router) enforces NotIn that way is NOT
proven here; that is the live probe's job (scripts/probe-agent-ingress.sh).

Run with --selftest to prove the detector still detects.
Usage: validate-agent-ingress-isolation.py [--matrix today|target] [rendered.yaml ...]
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GITOPS = ROOT / "platform-gitops"
AGENT_LABEL = ("app.kubernetes.io/name", "mctl-agents")
WF = "argo-workflows"

# --- synthetic pods -------------------------------------------------------
# (namespace, pod labels). Controller/server labels are the upstream chart's
# expected ones and still need live confirmation (#2289 task 2).
_WFLBL = {"workflows.argoproj.io/workflow": "wf"}
SOURCES = {
    "agent": (WF, {**_WFLBL, AGENT_LABEL[0]: AGENT_LABEL[1], "mctl.ai/team": "admins"}),
    "agent-hook": (WF, {**_WFLBL, AGENT_LABEL[0]: AGENT_LABEL[1], "mctl.ai/team": "admins"}),
    "platform": (WF, dict(_WFLBL)),
    "controller": (WF, {"app.kubernetes.io/name": "argo-workflows-workflow-controller",
                        "app.kubernetes.io/component": "workflow-controller"}),
    "server": (WF, {"app.kubernetes.io/name": "argo-workflows-server",
                    "app.kubernetes.io/component": "server"}),
}
# name -> (namespace, pod labels, port)
DESTS = {
    "vault": ("vault", {"app.kubernetes.io/name": "vault"}, 8200),
    "backstage": ("backstage", {"app.kubernetes.io/name": "backstage"}, 7007),
    "mctl-api": ("mctl-api", {"app.kubernetes.io/name": "mctl-api"}, 8080),
    "platform-db": ("platform-db", {"cnpg.io/cluster": "shared-pg"}, 5432),
    "otel": ("monitoring", {"app.kubernetes.io/name": "opentelemetry-collector",
                            "app.kubernetes.io/instance": "otel-collector"}, 4318),
    "proxy": ("mctl-agents-egress", {"app.kubernetes.io/name": "agent-egress-proxy"}, 3128),
    "argo-server": (WF, {"app.kubernetes.io/name": "argo-workflows-server",
                         "app.kubernetes.io/component": "server"}, 2746),
    "platform-pod": (WF, dict(_WFLBL), 80),
}

# Allowed destinations per source; every other cell must be denied.
_ALL_NS_REACH = {"controller": {"mctl-api", "platform-db", "otel", "argo-server", "platform-pod"},
                 "server": {"mctl-api", "platform-db", "otel", "argo-server", "platform-pod"}}
MATRICES = {
    # Repository state as of this proposal. Agent pods still reach everything
    # the namespace-wide / workflow-label peers admit.
    "today": {
        "agent": {"mctl-api", "otel", "proxy", "vault", "backstage", "platform-db",
                  "argo-server", "platform-pod"},
        "agent-hook": {"mctl-api", "otel", "proxy", "vault", "backstage", "platform-db",
                       "argo-server", "platform-pod"},
        "platform": {"vault", "backstage", "mctl-api", "platform-db", "otel", "argo-server", "platform-pod"},
        **_ALL_NS_REACH,
    },
    # Goal of #2301.
    "target": {
        "agent": {"mctl-api", "otel", "proxy"},
        "agent-hook": {"mctl-api", "otel", "proxy"},
        "platform": {"vault", "backstage", "mctl-api", "platform-db", "otel", "argo-server", "platform-pod"},
        "controller": {"platform-db", "argo-server", "platform-pod"},
        "server": {"platform-db", "argo-server", "platform-pod"},
    },
}

# Policies still admitting argo-workflows by namespace alone (policy ns, name).
# #2301 removes these one by one; the list must end empty.
NAMESPACE_ONLY_BASELINE = {
    ("mctl-api", "allow-mctl-api-ingress"),
    ("platform-db", "allow-shared-pg-ingress"),
    ("monitoring", "allow-otel-collector-ingress"),
}


# --- selector evaluation --------------------------------------------------
def sel_matches(sel: dict | None, labels: dict) -> bool:
    if not sel:
        return True
    for k, v in (sel.get("matchLabels") or {}).items():
        if labels.get(k) != v:
            return False
    for e in sel.get("matchExpressions") or []:
        key, op, vals = e["key"], e["operator"], e.get("values") or []
        if op == "In" and labels.get(key) not in vals:
            return False
        if op == "NotIn" and key in labels and labels[key] in vals:
            return False
        if op == "Exists" and key not in labels:
            return False
        if op == "DoesNotExist" and key in labels:
            return False
    return True


def ns_labels(ns: str) -> dict:
    return {"kubernetes.io/metadata.name": ns}


def peer_matches(peer: dict, policy_ns: str, src_ns: str, src_labels: dict) -> bool:
    if "ipBlock" in peer:
        return False
    if "namespaceSelector" in peer:
        if not sel_matches(peer["namespaceSelector"], ns_labels(src_ns)):
            return False
    elif src_ns != policy_ns:
        return False
    return sel_matches(peer.get("podSelector"), src_labels)


def port_matches(ports: list | None, port: int) -> bool:
    if not ports:
        return True
    return any(p.get("port") == port and p.get("protocol", "TCP") == "TCP" for p in ports)


def allowed(policies: list[dict], src: tuple, dst: tuple) -> bool:
    src_ns, src_labels = src
    dst_ns, dst_labels, port = dst
    selecting = []
    for p in policies:
        if (p["metadata"].get("namespace") or "") != dst_ns:
            continue
        spec = p.get("spec") or {}
        types = spec.get("policyTypes") or ["Ingress"]
        if "Ingress" in types and sel_matches(spec.get("podSelector"), dst_labels):
            selecting.append(p)
    if not selecting:
        return True
    for p in selecting:
        for rule in (p["spec"].get("ingress") or []):
            frm = rule.get("from")
            if not port_matches(rule.get("ports"), port):
                continue
            if frm is None or any(peer_matches(peer, dst_ns, src_ns, src_labels) for peer in frm):
                return True
    return False


def evaluate(policies: list[dict], matrix: dict) -> list[str]:
    found = []
    for sname, src in SOURCES.items():
        for dname, dst in DESTS.items():
            want = dname in matrix.get(sname, set())
            got = allowed(policies, src, dst)
            if want != got:
                found.append(f"{sname} -> {dname}:{dst[2]}: policies {'allow' if got else 'deny'}, "
                             f"expected {'allow' if want else 'deny'}")
    return found


def lint_namespace_only(policies: list[dict], baseline: set) -> list[str]:
    found = []
    seen = set()
    for p in policies:
        ns, name = p["metadata"].get("namespace", ""), p["metadata"].get("name", "")
        for rule in (p.get("spec") or {}).get("ingress") or []:
            for peer in rule.get("from") or []:
                if "namespaceSelector" in peer and not peer.get("podSelector") \
                        and sel_matches(peer["namespaceSelector"], ns_labels(WF)):
                    if (ns, name) in baseline:
                        seen.add((ns, name))
                    else:
                        found.append(f"{ns}/{name}: peer admits namespace {WF} without a podSelector")
    return found


# --- loading ----------------------------------------------------------------
def load_policies(paths: list[Path]) -> list[dict]:
    out: dict[tuple, dict] = {}
    for path in paths:
        try:
            docs = list(yaml.safe_load_all(path.read_text()))
        except yaml.YAMLError:
            continue  # Helm template syntax; its rendered form arrives via argv.
        for doc in docs:
            if isinstance(doc, dict) and doc.get("kind") == "NetworkPolicy":
                m = doc.get("metadata") or {}
                out[(m.get("namespace", ""), m.get("name", ""))] = doc
            elif isinstance(doc, dict) and doc.get("kind") == "List":
                for item in doc.get("items") or []:
                    if isinstance(item, dict) and item.get("kind") == "NetworkPolicy":
                        m = item.get("metadata") or {}
                        out[(m.get("namespace", ""), m.get("name", ""))] = item
    return list(out.values())


# --- selftest ---------------------------------------------------------------
def _np(ns, name, pod_sel, rules):
    return {"kind": "NetworkPolicy", "metadata": {"namespace": ns, "name": name},
            "spec": {"podSelector": pod_sel, "policyTypes": ["Ingress"], "ingress": rules}}


def _ns(name):
    return {"matchLabels": {"kubernetes.io/metadata.name": name}}


_NOT_AGENT = {"matchExpressions": [{"key": "workflows.argoproj.io/workflow", "operator": "Exists"},
                                   {"key": AGENT_LABEL[0], "operator": "NotIn", "values": [AGENT_LABEL[1]]}]}
_WF_EXISTS = {"matchExpressions": [{"key": "workflows.argoproj.io/workflow", "operator": "Exists"}]}


def _hardened() -> list[dict]:
    """Synthetic policies in the shape #2301 must produce."""
    def p(port): return [{"protocol": "TCP", "port": port}]
    return [
        _np("vault", "v", {}, [{"from": [{"namespaceSelector": _ns(WF), "podSelector": _NOT_AGENT}],
                                "ports": p(8200)}]),
        _np("backstage", "b", {}, [{"from": [{"namespaceSelector": _ns(WF), "podSelector": _NOT_AGENT}],
                                    "ports": p(7007)}]),
        _np("platform-db", "d", {}, [
            {"from": [{"namespaceSelector": _ns(WF), "podSelector": _NOT_AGENT},
                      {"namespaceSelector": _ns(WF), "podSelector": {"matchExpressions": [
                          {"key": "app.kubernetes.io/component", "operator": "In",
                           "values": ["workflow-controller", "server"]}]}}],
             "ports": p(5432)}]),
        _np("mctl-api", "a", {}, [{"from": [{"namespaceSelector": _ns(WF), "podSelector": _WF_EXISTS}],
                                   "ports": p(8080)}]),
        _np("monitoring", "o", {"matchLabels": {"app.kubernetes.io/name": "opentelemetry-collector"}},
            [{"from": [{"namespaceSelector": _ns(WF), "podSelector": _WF_EXISTS}],
              "ports": p(4317) + p(4318)}]),
        _np(WF, "w", {}, [{"from": [{"podSelector": {"matchExpressions": [
            {"key": AGENT_LABEL[0], "operator": "NotIn", "values": [AGENT_LABEL[1]]}]}}]}]),
        _np("mctl-agents-egress", "e", {}, [{"from": [{"namespaceSelector": _ns(WF), "podSelector": {
            "matchLabels": {AGENT_LABEL[0]: AGENT_LABEL[1]}}}], "ports": p(3128)}]),
    ]


def selftest() -> int:
    ok = True

    def check(label, cond):
        nonlocal ok
        if not cond:
            print(f"selftest FAIL: {label}")
            ok = False

    base = _hardened()
    check("hardened set passes the target matrix", not evaluate(base, MATRICES["target"]))
    check("hardened set has no namespace-only peer", not lint_namespace_only(base, set()))

    def mut(fn):
        pols = copy.deepcopy(base)
        fn(pols)
        return pols

    def drop_notin(pols):  # removal of the NotIn mctl-agents exclusion at vault
        pols[0]["spec"]["ingress"][0]["from"][0]["podSelector"] = _WF_EXISTS

    def restore_podselector_all(pols):  # podSelector {} as the intra-namespace source
        pols[5]["spec"]["ingress"][0]["from"] = [{"podSelector": {}}]

    def ns_only(pols):  # namespace-only peer
        del pols[3]["spec"]["ingress"][0]["from"][0]["podSelector"]

    def extra_policy(pols):  # a second policy: only the union catches it
        pols.append(_np("vault", "extra", {}, [{"from": [{"namespaceSelector": _ns(WF)}]}]))

    def ns_empty_podsel(pols):  # cross-namespace peer with podSelector {}
        pols[3]["spec"]["ingress"][0]["from"][0]["podSelector"] = {}

    for label, fn in [("namespace peer with podSelector {}", ns_empty_podsel),
                      ("removed NotIn exclusion", drop_notin),
                      ("podSelector {} restored intra-namespace", restore_podselector_all),
                      ("namespace-only peer", ns_only),
                      ("second policy re-admits the namespace", extra_policy)]:
        pols = mut(fn)
        detected = bool(evaluate(pols, MATRICES["target"])) or bool(lint_namespace_only(pols, set()))
        check(f"detects: {label}", detected)
    # The lint alone must catch a namespace-only peer even if the matrix is satisfied.
    check("lint detects namespace-only peer", bool(lint_namespace_only(mut(ns_only), set())))
    check("lint detects podSelector {} peer", bool(lint_namespace_only(mut(ns_empty_podsel), set())))
    # Missing agent label on the source flips the NotIn side: platform-side reach for an agent.
    agent_unlabelled = {"agent": (WF, dict(_WFLBL))}
    check("unlabelled agent pod reaches vault in hardened set (fail-open shape is real)",
          allowed(base, agent_unlabelled["agent"], DESTS["vault"]))
    check("matrices differ", MATRICES["today"] != MATRICES["target"])
    if ok:
        print("selftest ok")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--matrix", choices=sorted(MATRICES), default="today")
    ap.add_argument("rendered", nargs="*", type=Path, help="rendered chart output files")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    paths = sorted(GITOPS.rglob("*.yaml")) + list(args.rendered)
    policies = load_policies(paths)
    baseline = NAMESPACE_ONLY_BASELINE if args.matrix == "today" else set()
    found = evaluate(policies, MATRICES[args.matrix]) + lint_namespace_only(policies, baseline)
    for v in found:
        print(f"ERROR: {v}", file=sys.stderr)
    if found:
        print("(mctl-gitops#2289, docs/runbooks/agent-pod-isolation.md)", file=sys.stderr)
        return 1
    print(f"agent ingress isolation ok ({len(policies)} policies, matrix={args.matrix})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
