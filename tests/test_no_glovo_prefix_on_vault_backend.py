#!/usr/bin/env python3
"""No ExternalSecret may read secret/platform/mctl-glovo/* through a ClusterSecretStore.

mctlhq/mctl-gitops#2759: the cluster-wide `vault-backend` store denies the
prefix (vault-policy-external-secrets-read.hcl, and the same deny on
argo-workflow-teams-rw). Any ExternalSecret that still reads a key under it
through that store, or through any ClusterSecretStore, loses access the moment
the deny is applied, and CNPG managed-role passwords (cnpg.io/reload) go stale
with it. This test makes that a CI failure instead of a production one.

Scope: every ExternalSecret and ClusterExternalSecret document in plain YAML
and in Helm templates under platform-gitops/, deploy/ and infrastructure/
(agents-state/ is notes, not manifests). Documents are split on `---` lines
and read as text, so templated manifests are covered without rendering.

A document counts as reading the prefix when it contains `platform/mctl-glovo`,
or a templated key `platform/{{ ... }}` in a file that mentions mctl-glovo (the
service template builds its keys from `$app`). For such a document:
- secretStoreRef.kind must be literally `SecretStore` (or absent: ESO's default
  is SecretStore). A ClusterSecretStore, in any name, is a failure.
- a secretStoreRef that cannot be read is a failure, never a pass: not being
  able to see the store is not the same as the store being fine.

Self-tests run first and prove each rule red on a deliberate mutation and green
on the converged shape. Run: python3 tests/test_no_glovo_prefix_on_vault_backend.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN = ("platform-gitops", "deploy", "infrastructure")
SKIP_PARTS = {"agents-state", ".git", "node_modules"}
EXTS = {".yaml", ".yml", ".tpl"}

KIND_RE = re.compile(r"^kind:\s*[\"']?(ExternalSecret|ClusterExternalSecret)[\"']?\s*$", re.M)
LITERAL_RE = re.compile(r"platform/mctl-glovo")
TEMPLATED_RE = re.compile(r"platform/\{\{")
FILE_RE = re.compile(r"mctl-glovo")
REF_RE = re.compile(r"^(?P<ind>[ ]*)secretStoreRef:\s*$", re.M)


def docs(text):
    return [d for d in re.split(r"^---\s*$", text, flags=re.M) if d.strip()]


def store_refs(doc):
    """Every secretStoreRef block as a dict of its direct scalar children."""
    out = []
    lines = doc.splitlines()
    for i, line in enumerate(lines):
        m = REF_RE.match(line)
        if not m:
            continue
        base = len(m.group("ind"))
        ref = {}
        for nxt in lines[i + 1:]:
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            ind = len(nxt) - len(nxt.lstrip())
            if ind <= base:
                break
            k, _, v = nxt.strip().partition(":")
            ref[k.strip()] = v.strip().strip("\"'")
        out.append(ref)
    return out


def problems(text, label):
    out = []
    file_mentions = bool(FILE_RE.search(text))
    for doc in docs(text):
        if not KIND_RE.search(doc):
            continue
        reads = bool(LITERAL_RE.search(doc)) or (file_mentions and bool(TEMPLATED_RE.search(doc)))
        if not reads:
            continue
        name = re.search(r"^\s{2}name:\s*(\S+)", doc, re.M)
        who = name.group(1) if name else "?"
        refs = store_refs(doc)
        if not refs:
            out.append(f"{label}: ExternalSecret {who} reads the Glovo prefix but has no readable secretStoreRef")
            continue
        for ref in refs:
            kind = ref.get("kind", "SecretStore")
            if kind != "SecretStore":
                out.append(f"{label}: ExternalSecret {who} reads the Glovo prefix through "
                           f"{kind} {ref.get('name', '?')!r}; use a namespaced SecretStore")
    return out


def tree_problems(root):
    out, seen = [], 0
    for top in SCAN:
        base = root / top
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix not in EXTS or not p.is_file() or SKIP_PARTS & set(p.parts):
                continue
            try:
                text = p.read_text()
            except (OSError, UnicodeDecodeError) as e:
                out.append(f"{p.relative_to(root)}: cannot read ({e}); an unread file is not a clean one")
                continue
            seen += 1
            out += problems(text, str(p.relative_to(root)))
    return out, seen


ES = """apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: x
spec:
  secretStoreRef:
    kind: {kind}
    name: {name}
  data:
    - secretKey: a
      remoteRef:
        key: {key}
"""


def selftest():
    def es(kind, name, key):
        return ES.format(kind=kind, name=name, key=key)

    g = "platform/mctl-glovo/database-runtime"
    assert not problems(es("SecretStore", "glovo-db-creds", g), "t")
    assert problems(es("ClusterSecretStore", "vault-backend", g), "t")
    assert problems(es("ClusterSecretStore", "some-other-cluster-store", g), "t")
    # other prefixes on vault-backend are out of scope here
    assert not problems(es("ClusterSecretStore", "vault-backend", "platform/mctl-api/x"), "t")
    # kind omitted means SecretStore in ESO
    assert not problems(es("SecretStore", "s", g).replace("    kind: SecretStore\n", ""), "t")
    # a second document in the same file is judged on its own
    two = es("SecretStore", "s", g) + "---\n" + es("ClusterSecretStore", "vault-backend", g)
    assert len(problems(two, "t")) == 1
    # no secretStoreRef at all: unreadable, not clean
    assert problems(es("SecretStore", "s", g).replace("  secretStoreRef:\n    kind: SecretStore\n    name: s\n", ""), "t")
    # templated key in a file that mentions mctl-glovo
    tpl = '{{- $app := "mctl-glovo" }}\n' + es("ClusterSecretStore", "vault-backend", "platform/{{ $app }}/x")
    assert problems(tpl, "t")
    assert not problems('{{- $app := "mctl-glovo" }}\n' + es("SecretStore", "{{ $app }}-vault", "platform/{{ $app }}/x"), "t")
    # a templated platform key in a file with no mention of the service is not judged
    assert not problems(es("ClusterSecretStore", "vault-backend", "platform/{{ $app }}/x"), "t")
    # ClusterExternalSecret nests the store ref deeper
    ces = es("ClusterSecretStore", "vault-backend", g).replace("kind: ExternalSecret", "kind: ClusterExternalSecret")
    assert problems(ces, "t")
    print("selftests: ok")


def main():
    selftest()
    out, seen = tree_problems(ROOT)
    if seen == 0:
        print("FAIL scanned no files: an unobserved tree is not a clean one", file=sys.stderr)
        return 1
    if out:
        print("\n".join("FAIL " + p for p in out), file=sys.stderr)
        return 1
    print(f"ok: no Glovo-prefix ExternalSecret uses a ClusterSecretStore ({seen} files scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
