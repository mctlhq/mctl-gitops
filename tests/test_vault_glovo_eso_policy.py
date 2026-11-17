#!/usr/bin/env python3
"""Glovo C2 ESO split (mctlhq/mctl-gitops#2759): repo-text checks, no Vault contact.

- vault-policy-eso-mctl-glovo.hcl grants only read on secret/data/platform/mctl-glovo/*
  and read,list on secret/metadata/platform/mctl-glovo/*: no other path, no
  other capability;
- vault-policy-external-secrets-read.hcl denies the same prefix (data and
  metadata forms), next to the github-app-agents deny, and still grants
  platform/* (the deny is what narrows it);
- vault-policy-argo-workflow-teams-rw.hcl (live role argo-workflow, SA
  argo-workflow-sa, which tenant-writable WorkflowTemplates can run as) carries
  the same deny, so its platform/* grant cannot read, overwrite or delete the prefix;
- vault-policy-glovo-db-creds-read.hcl (platform-db store glovo-db-creds) grants
  only read on the database-* keys and read,list on their metadata.

Self-tests run first and prove each check red on a deliberate mutation.
Run: python3 tests/test_vault_glovo_eso_policy.py
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "infrastructure/k3s-preview/cluster-bootstrap/vault-config"
spec = importlib.util.spec_from_file_location("vpf", ROOT / "tests/test_vault_policy_files.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)

PREFIX = "secret/data/platform/mctl-glovo/"
META = "secret/metadata/platform/mctl-glovo/"
ESO_FILE = "vault-policy-eso-mctl-glovo.hcl"
CLUSTER_FILE = "vault-policy-external-secrets-read.hcl"
ARGO_FILE = "vault-policy-argo-workflow-teams-rw.hcl"
DB_FILE = "vault-policy-glovo-db-creds-read.hcl"
DB_PREFIX = "secret/data/platform/mctl-glovo/database-"
DB_META = "secret/metadata/platform/mctl-glovo/database-"


def eso_problems(rules):
    out = []
    want = {PREFIX + "*": ["read"], META + "*": ["list", "read"]}
    got = {}
    for pat, caps in rules:
        got.setdefault(pat, []).extend(caps)
    for pat, caps in got.items():
        if pat not in want:
            out.append(f"path {pat!r} is outside platform/mctl-glovo/")
        elif sorted(set(caps)) != want[pat]:
            out.append(f"path {pat!r} has capabilities {sorted(set(caps))}, want {want[pat]}")
    for pat in want:
        if pat not in got:
            out.append(f"missing rule for {pat!r}")
    return out


def cluster_problems(rules):
    out = []
    got = {}
    for pat, caps in rules:
        got.setdefault(pat, []).extend(caps)
    for pat in ("secret/data/platform/mctl-glovo*", "secret/metadata/platform/mctl-glovo*"):
        if got.get(pat) != ["deny"]:
            out.append(f"missing explicit deny on {pat}")
    if "secret/data/platform/*" not in got:
        out.append("platform/* grant vanished: the deny test would pass vacuously")
    # the deny must win for every path under the prefix, by the real priority rules
    for form in ("data", "metadata"):
        caps = V.effective_caps(rules, f"secret/{form}/platform/mctl-glovo/control-caller")
        if caps != {"deny"}:
            out.append(f"secret/{form}/platform/mctl-glovo/x resolves to {sorted(caps)}, want deny")
    return out


def db_problems(rules):
    out = []
    want = {DB_PREFIX + "*": ["read"], DB_META + "*": ["list", "read"]}
    got = {}
    for pat, caps in rules:
        got.setdefault(pat, []).extend(caps)
    for pat, caps in got.items():
        if pat not in want:
            out.append(f"path {pat!r} is outside the database-* keys")
        elif sorted(set(caps)) != want[pat]:
            out.append(f"path {pat!r} has capabilities {sorted(set(caps))}, want {want[pat]}")
    for pat in want:
        if pat not in got:
            out.append(f"missing rule for {pat!r}")
    return out


def selftest():
    good_eso = [(PREFIX + "*", ["read"]), (META + "*", ["read", "list"])]
    assert not eso_problems(good_eso)
    assert eso_problems(good_eso + [("secret/data/platform/*", ["read"])])
    assert eso_problems(good_eso + [("secret/data/teams/x/*", ["read"])])
    assert eso_problems([(PREFIX + "*", ["read", "update"]), (META + "*", ["read", "list"])])
    assert eso_problems(good_eso[:1])
    base = [("secret/data/platform/*", ["read"]), ("secret/metadata/platform/*", ["read", "list"])]
    good_cluster = base + [("secret/data/platform/mctl-glovo*", ["deny"]),
                           ("secret/metadata/platform/mctl-glovo*", ["deny"])]
    assert not cluster_problems(good_cluster)
    assert cluster_problems(base)
    assert cluster_problems(good_cluster[:3])
    assert cluster_problems(good_cluster[2:])
    # a deny narrowed to a different prefix does not count
    assert cluster_problems(base + [("secret/data/platform/mctl-glovo-x*", ["deny"]),
                                    ("secret/metadata/platform/mctl-glovo-x*", ["deny"])])
    # argo-workflow-teams-rw has the same shape as the cluster store: a broad
    # platform/* grant that only the deny narrows. cluster_problems checks both.
    assert cluster_problems(base + [("secret/data/platform/mctl-glovo*", ["deny"])])
    good_db = [(DB_PREFIX + "*", ["read"]), (DB_META + "*", ["read", "list"])]
    assert not db_problems(good_db)
    assert db_problems(good_db + [("secret/data/platform/mctl-glovo/*", ["read"])])
    assert db_problems([(DB_PREFIX + "*", ["read", "update"]), (DB_META + "*", ["read", "list"])])
    assert db_problems(good_db[:1])
    print("selftests: ok")


def main():
    selftest()
    eso = V.canonical_rules(V.parse(D / ESO_FILE))
    cluster = V.canonical_rules(V.parse(D / CLUSTER_FILE))
    problems = [f"{ESO_FILE}: {p}" for p in eso_problems(eso)]
    problems += [f"{CLUSTER_FILE}: {p}" for p in cluster_problems(cluster)]
    argo = V.canonical_rules(V.parse(D / ARGO_FILE))
    problems += [f"{ARGO_FILE}: {p}" for p in cluster_problems(argo)]
    db = V.canonical_rules(V.parse(D / DB_FILE))
    problems += [f"{DB_FILE}: {p}" for p in db_problems(db)]
    if problems:
        print("\n".join("FAIL " + p for p in problems), file=sys.stderr)
        return 1
    print("ok: glovo ESO policy, db-creds policy, cluster-store and argo-workflow deny")
    return 0


if __name__ == "__main__":
    sys.exit(main())
