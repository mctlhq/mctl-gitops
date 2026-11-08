#!/usr/bin/env python3
"""Offline check of committed Vault policy HCL against an expected-capability table.

Reads the policy files named in a small JSON config, evaluates the effective
capabilities each identity gets on each listed request path (Vault ACL rules:
an exact path beats a glob, otherwise the longest trailing-`*` prefix wins,
capabilities of the same pattern merge across the identity's policies, and a
`deny` in the winning set is final), and compares them with the table. It never
talks to Vault: it proves what the repository text says, not what is applied.

Exit codes:
  0  every expectation holds
  1  at least one expectation differs (a finding)
  2  something could not be observed (missing/unreadable/unparseable policy
     file, malformed config, unsupported syntax). UNKNOWN outranks a finding:
     a file that cannot be read is never an empty policy and never a pass.

Config (scripts/vault-policy-expectations.json):
  base_dir      directory holding the policy files, relative to --root
  identities    {name: {"policies": [file, ...]}}
  expectations  [{"identity", "path", "effective": [caps]}]
                `effective` is the exact capability set; [] means no rule
                matches, ["deny"] means an explicit deny wins.

Usage:
  scripts/check-vault-policy-capabilities.py [--root DIR] [--config FILE]
"""
import argparse
import json
import pathlib
import re
import sys

KNOWN_CAPS = {"create", "read", "update", "delete", "list", "sudo", "deny", "patch", "subscribe", "recover"}
OK, FINDING, UNKNOWN = 0, 1, 2


class Unknown(Exception):
    """A read that could not be completed; never treated as an empty result."""


def strip_comments(text):
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "#" or text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise Unknown("unterminated block comment")
            i = j + 2
            continue
        else:
            out.append(c)
        i += 1
    if in_str:
        raise Unknown("unterminated string")
    return "".join(out)


_PATH_RE = re.compile(r'\s*path\s+"((?:[^"\\]|\\.)*)"\s*\{', re.S)
_CAPS_RE = re.compile(r'\s*capabilities\s*=\s*\[([^\]]*)\]\s*', re.S)


def parse_policy(text, label):
    """Return a list of (pattern, set(caps)). Anything else is Unknown."""
    src = strip_comments(text)
    rules, pos = [], 0
    while True:
        if not src[pos:].strip():
            break
        m = _PATH_RE.match(src, pos)
        if not m:
            raise Unknown(f"{label}: unsupported or malformed HCL near: {src[pos:pos+40].strip()!r}")
        pattern = m.group(1)
        end = src.find("}", m.end())
        if end < 0:
            raise Unknown(f"{label}: unterminated block for path {pattern!r}")
        body = src[m.end():end]
        if "{" in body:
            raise Unknown(f"{label}: nested block in path {pattern!r} is not supported")
        cm = _CAPS_RE.fullmatch(body)
        if not cm:
            # Any attribute besides capabilities (e.g. allowed_parameters)
            # changes the effective result in ways this check cannot model.
            raise Unknown(f"{label}: path {pattern!r} has attributes other than capabilities")
        caps = re.findall(r'"([^"]*)"', cm.group(1))
        if not caps:
            raise Unknown(f"{label}: path {pattern!r} has an empty capability list")
        bad = set(caps) - KNOWN_CAPS
        if bad:
            raise Unknown(f"{label}: unknown capability {sorted(bad)} on {pattern!r}")
        if "+" in pattern or "{{" in pattern or "%" in pattern:
            raise Unknown(f"{label}: wildcard/template syntax in {pattern!r} is not supported")
        rules.append((pattern, set(caps)))
        pos = end + 1
    if not rules:
        raise Unknown(f"{label}: no path rules found")
    return rules


def effective(rule_sets, request_path):
    exact, globs = {}, {}
    for pattern, caps in rule_sets:
        if pattern.endswith("*"):
            if request_path.startswith(pattern[:-1]):
                globs.setdefault(pattern, set()).update(caps)
        elif pattern == request_path:
            exact.setdefault(pattern, set()).update(caps)
    if exact:
        winner = next(iter(exact.values()))
    elif globs:
        winner = globs[max(globs, key=len)]
    else:
        return []
    return ["deny"] if "deny" in winner else sorted(winner)


def load_config(path):
    try:
        cfg = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as e:
        raise Unknown(f"config {path}: {e}")
    if not isinstance(cfg, dict):
        raise Unknown("config: top level must be an object")
    for key, typ in (("base_dir", str), ("identities", dict), ("expectations", list)):
        if not isinstance(cfg.get(key), typ) or not cfg[key]:
            raise Unknown(f"config: missing or empty {key!r}")
    for name, ident in cfg["identities"].items():
        pol = ident.get("policies") if isinstance(ident, dict) else None
        if not isinstance(pol, list) or not pol or not all(isinstance(p, str) for p in pol):
            raise Unknown(f"config: identity {name!r} needs a non-empty policies list")
    for i, e in enumerate(cfg["expectations"]):
        ok = (isinstance(e, dict) and e.get("identity") in cfg["identities"]
              and isinstance(e.get("path"), str) and isinstance(e.get("effective"), list)
              and all(c in KNOWN_CAPS for c in e["effective"]))
        if not ok:
            raise Unknown(f"config: expectation #{i} is malformed or names an unknown identity")
    return cfg


def run(root, config):
    cfg = load_config(config)
    base = pathlib.Path(root) / cfg["base_dir"]
    parsed, problems = {}, []
    for name, ident in cfg["identities"].items():
        rules = []
        for fname in ident["policies"]:
            p = base / fname
            try:
                text = p.read_text()
            except OSError as e:
                problems.append(f"{name}: cannot read policy file {p}: {e.strerror or e}")
                continue
            try:
                rules.extend(parse_policy(text, str(p)))
            except Unknown as e:
                problems.append(f"{name}: {e}")
        parsed[name] = rules
    if problems:
        return UNKNOWN, problems
    findings = []
    for e in cfg["expectations"]:
        got = effective(parsed[e["identity"]], e["path"])
        want = sorted(e["effective"])
        if got != want:
            findings.append(f"{e['identity']} on {e['path']}: expected {want}, got {got}")
    return (FINDING, findings) if findings else (OK, [])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    here = pathlib.Path(__file__).resolve().parent
    ap.add_argument("--root", default=str(here.parent))
    ap.add_argument("--config", default=str(here / "vault-policy-expectations.json"))
    a = ap.parse_args(argv)
    try:
        code, lines = run(a.root, a.config)
    except Unknown as e:
        code, lines = UNKNOWN, [str(e)]
    label = {OK: "OK", FINDING: "MISMATCH", UNKNOWN: "UNKNOWN (could not observe)"}[code]
    for ln in lines:
        print(f"{label}: {ln}")
    if code == OK:
        print("Vault policy capability table holds for the committed policy files.")
    return code


if __name__ == "__main__":
    sys.exit(main())
