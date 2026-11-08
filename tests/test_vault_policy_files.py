#!/usr/bin/env python3
"""Vault policy files: structure and the writer-prefix rules.

Conservative parser for the small HCL subset these files use (comments, and
`path "<p>" { capabilities = [..] }` blocks). Anything it cannot parse is an
error, never an empty policy.

Checks:
- every vault-policy-*.hcl parses, with known capabilities and balanced braces;
- gitops-writer-read grants only read/list, only under writers/gitops/;
- external-secrets-read and argo-workflow-teams-rw deny secret/{data,metadata}/writers/*;
- no other policy file grants anything on the writers/ prefix.

Run: python3 tests/test_vault_policy_files.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "infrastructure/k3s-preview/cluster-bootstrap/vault-config"
CAPS = {"create", "read", "update", "delete", "list", "sudo", "deny", "patch"}
PREFIX = "writers/"
WRITER_READ = "vault-policy-gitops-writer-read.hcl"
DENY_IN = ["vault-policy-external-secrets-read.hcl", "vault-policy-argo-workflow-teams-rw.hcl"]


def parse(path):
    """Return [(path, [caps])]. Raise ValueError on anything unrecognised."""
    text = re.sub(r"(?m)^\s*(#|//).*$", "", path.read_text())
    if text.count("{") != text.count("}") or text.count("[") != text.count("]"):
        raise ValueError("unbalanced brackets")
    if text.count('"') % 2:
        raise ValueError("unbalanced quotes")
    block = re.compile(r'\s*path\s+"([^"]+)"\s*\{\s*capabilities\s*=\s*\[([^\]]*)\]\s*\}')
    rules, pos = [], 0
    while pos < len(text):
        if not text[pos:].strip():
            break
        m = block.match(text, pos)
        if not m:
            raise ValueError("unrecognised content near: %r" % text[pos:pos + 60].strip())
        caps = [c.strip().strip('"') for c in m.group(2).split(",") if c.strip()]
        bad = [c for c in caps if c not in CAPS]
        if bad or not caps:
            raise ValueError("bad capabilities %r for %s" % (caps, m.group(1)))
        rules.append((m.group(1), caps))
        pos = m.end()
    if not rules:
        raise ValueError("no path rules")
    return rules


def touches_writers(p):
    p = re.sub(r"^secret/(data|metadata)/", "", p)
    return p.startswith(PREFIX) or p == "*" or "/".join(p.split("/")[:1]) == "writers"


def check():
    errs = []
    files = sorted(D.glob("vault-policy-*.hcl"))
    if not files:
        return ["no policy files found (could not observe)"]
    parsed = {}
    for f in files:
        try:
            parsed[f.name] = parse(f)
        except (ValueError, OSError) as e:
            errs.append("%s: %s" % (f.name, e))
    w = parsed.get(WRITER_READ)
    if w is None:
        errs.append("%s missing or unparsable" % WRITER_READ)
    else:
        for p, caps in w:
            if not re.fullmatch(r"secret/(data|metadata)/writers/gitops/\*", p):
                errs.append("%s: path outside writers/gitops: %s" % (WRITER_READ, p))
            if set(caps) - {"read", "list"}:
                errs.append("%s: non-read capability on %s: %s" % (WRITER_READ, p, caps))
        if {p for p, _ in w} != {"secret/data/writers/gitops/*", "secret/metadata/writers/gitops/*"}:
            errs.append("%s: expected exactly the data and metadata paths" % WRITER_READ)
    for name in DENY_IN:
        rules = parsed.get(name)
        if rules is None:
            errs.append("%s missing or unparsable" % name)
            continue
        for want in ("secret/data/writers/*", "secret/metadata/writers/*"):
            if (want, ["deny"]) not in rules:
                errs.append("%s: no deny on %s" % (name, want))
    for name, rules in parsed.items():
        if name == WRITER_READ:
            continue
        for p, caps in rules:
            if touches_writers(p) and caps != ["deny"]:
                errs.append("%s grants %s on %s" % (name, caps, p))
    return errs


if __name__ == "__main__":
    errs = check()
    for e in errs:
        print("FAIL:", e)
    if errs:
        sys.exit(1)
    print("ok")
