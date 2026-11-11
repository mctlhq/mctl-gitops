#!/usr/bin/env python3
"""Prove the staged mctl-api egress policy allows what the inventory requires
and denies what it must not (owner decision #7, Glovo M1).

Evaluates the NetworkPolicy semantics we use (ipBlock+except, namespaceSelector
with optional podSelector, bare podSelector = same namespace, ports) against a
list of required and forbidden destinations. --selftest mutates the policy and
requires the test to go RED: removing any required allow, widening a forbidden
one. Exit 0 ok, 1 refused (a check failed), 2 unknown (unreadable input).
Network-level facts a parser cannot prove are covered by the gate procedure in
deploy/staged/glovo-m1/mctl-api-egress.md.
"""
from __future__ import annotations

import copy
import ipaddress
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "deploy/staged/glovo-m1/netpol/mctl-api-egress.yaml"
POLICY_NS = "mctl-api"
CANARY = {"app.kubernetes.io/name": "mctl-api", "mctl.ai/egress-policy": "enforced"}


def ns(name, port, proto="TCP", pod=None):
    return {"ns": name, "pod": pod or {}, "port": port, "proto": proto}


def ip(addr, port, proto="TCP"):
    return {"ip": addr, "port": port, "proto": proto}


# Required: from the inventory (see mctl-api-egress.md). name -> destination.
REQUIRED = {
    "dns-udp": ns("kube-system", 53, "UDP", {"k8s-app": "kube-dns"}),
    "dns-tcp": ns("kube-system", 53, "TCP", {"k8s-app": "kube-dns"}),
    "kube-apiserver": ip("10.255.0.101", 6443),
    "sibling-replica": ns(POLICY_NS, 8080, pod={"app.kubernetes.io/name": "mctl-api"}),
    "postgres": ns("platform-db", 5432),
    "valkey": ns("platform-events", 6379),
    "temporal": ns("temporal", 7233),
    "vault": ns("vault", 8200),
    "loki": ns("monitoring", 3100),
    "argo-workflows": ns("argo-workflows", 2746),
    "backstage": ns("backstage", 7007),
    "erpact": ns("erpact", 8000),
    "zitadel-api": ns("zitadel", 8080),
    "zitadel-login": ns("zitadel", 3000),
    "public-https-auth": ip("104.16.1.1", 443),
    "public-https-github": ip("140.82.112.3", 443),
}

# Forbidden: must NOT be reachable.
FORBIDDEN = {
    "public-ssh": ip("140.82.112.3", 22),
    "public-smtp": ip("203.0.113.9", 25),
    "public-postgres": ip("203.0.113.9", 5432),
    "public-http-plain": ip("203.0.113.9", 80),
    "public-https-udp-quic": ip("203.0.113.9", 443, "UDP"),
    "cloud-metadata": ip("169.254.169.254", 80),
    "cloud-metadata-443": ip("169.254.169.254", 443),
    "private-10-https": ip("10.0.0.5", 443),
    "private-172-https": ip("172.20.1.1", 443),
    "private-192-https": ip("192.168.1.1", 443),
    "cgnat-https": ip("100.64.0.1", 443),
    "kubelet-on-apiserver-node": ip("10.255.0.101", 10250),
    "external-dns": ip("8.8.8.8", 53, "UDP"),
    "other-ns-service": ns("kube-system", 10250),
    "tenant-ns-service": ns("admins", 8080),
    "postgres-wrong-ns": ns("admins", 5432),
    "wrong-port-vault": ns("vault", 8201),
    "wrong-pod-dns": ns("kube-system", 53, "UDP", {"k8s-app": "other"}),
}


class Unknown(Exception):
    pass


def _in(cidr_s, addr):
    return ipaddress.ip_address(addr) in ipaddress.ip_network(cidr_s)


def _labels_match(sel, labels):
    return all(labels.get(k) == v for k, v in (sel or {}).get("matchLabels", {}).items())


def _peer_ok(peer, d):
    if "ipBlock" in peer:
        if "ip" not in d:
            return False
        b = peer["ipBlock"]
        return _in(b["cidr"], d["ip"]) and not any(_in(e, d["ip"]) for e in b.get("except", []))
    if "ns" not in d:
        return False
    nsel, psel = peer.get("namespaceSelector"), peer.get("podSelector")
    if nsel is None and psel is None:
        raise Unknown("empty peer")
    if nsel is not None and not _labels_match(nsel, {"kubernetes.io/metadata.name": d["ns"]}):
        return False
    if nsel is None and d["ns"] != POLICY_NS:
        return False
    if psel is not None:
        if not psel.get("matchLabels"):
            return True  # {} selects every pod
        # Destination pod labels are only known when the entry supplies them.
        return all(d["pod"].get(k) == v for k, v in psel["matchLabels"].items())
    return True


def allowed(doc, d):
    for rule in doc["spec"].get("egress", []):
        ports = rule.get("ports")
        if ports is not None and not any(
            p.get("protocol", "TCP") == d["proto"] and p.get("port") == d["port"] for p in ports
        ):
            continue
        if any(_peer_ok(p, d) for p in rule.get("to", [])):
            return True
    return False


def evaluate(doc) -> list[str]:
    fails = []
    spec = doc.get("spec", {})
    if spec.get("policyTypes") != ["Egress"]:
        fails.append("policyTypes must be exactly [Egress]")
    if "ingress" in spec:
        fails.append("policy must not carry ingress rules")
    if (spec.get("podSelector") or {}).get("matchLabels") != CANARY:
        fails.append("podSelector must be exactly the canary labels")
    if doc.get("metadata", {}).get("namespace") != POLICY_NS:
        fails.append("namespace must be mctl-api")
    for name, d in REQUIRED.items():
        if not allowed(doc, d):
            fails.append(f"required destination denied: {name}")
    for name, d in FORBIDDEN.items():
        if allowed(doc, d):
            fails.append(f"forbidden destination allowed: {name}")
    return fails


def load():
    try:
        doc = yaml.safe_load(POLICY.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise Unknown(f"cannot read {POLICY}: {e}") from e
    if not isinstance(doc, dict) or doc.get("kind") != "NetworkPolicy":
        raise Unknown("not a NetworkPolicy")
    return doc


def selftest(base) -> int:
    bad = 0

    def expect_red(name, mutate):
        nonlocal bad
        d = copy.deepcopy(base)
        mutate(d)
        red = bool(evaluate(d))
        print(f"{'ok  ' if red else 'FAIL'} mutation goes RED: {name}", file=sys.stderr)
        bad += not red

    if evaluate(base):
        print("FAIL baseline is not green", file=sys.stderr)
        return 1
    print("ok   baseline green", file=sys.stderr)
    egress = base["spec"]["egress"]
    for i, rule in enumerate(egress):
        expect_red(f"drop egress rule {i}", lambda d, i=i: d["spec"]["egress"].pop(i))
    expect_red("open all egress", lambda d: d["spec"].__setitem__("egress", [{}]))
    expect_red("public except removed (metadata reachable)",
               lambda d: d["spec"]["egress"][-1]["to"][0]["ipBlock"].pop("except"))
    expect_red("public ports widened to all",
               lambda d: d["spec"]["egress"][-1].pop("ports"))
    expect_red("selector widened to all pods", lambda d: d["spec"].__setitem__("podSelector", {}))
    expect_red("ingress added", lambda d: d["spec"].__setitem__("ingress", [{}]))
    return 1 if bad else 0


def main(argv) -> int:
    try:
        doc = load()
        if argv == ["--selftest"]:
            return selftest(doc)
        fails = evaluate(doc)
    except Unknown as e:
        print(f"UNKNOWN: {e}", file=sys.stderr)
        return 2
    for f in fails:
        print(f"REFUSED: {f}", file=sys.stderr)
    if not fails:
        print(f"mctl-api egress policy: ok ({len(REQUIRED)} required allowed, {len(FORBIDDEN)} forbidden denied)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
