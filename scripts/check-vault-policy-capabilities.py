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
  2  something could not be observed (missing/unreadable/non-UTF-8/unparseable
     policy file, malformed config, unsupported syntax). UNKNOWN outranks a finding:
     a file that cannot be read is never an empty policy and never a pass.

Config (scripts/vault-policy-expectations.json):
  note          free text. The expectation rows record the policy state deployed
                today; they describe existing access and neither grant nor
                endorse it, and recording one does not narrow it.
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
# The bracket body must be exactly quoted strings separated by commas, with an
# optional trailing comma. Anything else (bare words, numbers, a missing or
# doubled comma) is not silently skipped: it makes the file Unknown.
_CAP_LIST_RE = re.compile(r'\s*"[^"\\]*"(?:\s*,\s*"[^"\\]*")*\s*,?\s*', re.S)


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
        raw = cm.group(1)
        if not raw.strip():
            raise Unknown(f"{label}: path {pattern!r} has an empty capability list")
        if not _CAP_LIST_RE.fullmatch(raw):
            raise Unknown(f"{label}: path {pattern!r} has a capability list that is not a comma-separated list of quoted strings")
        caps = re.findall(r'"([^"]*)"', raw)
        bad = set(caps) - KNOWN_CAPS
        if bad:
            raise Unknown(f"{label}: unknown capability {sorted(bad)} on {pattern!r}")
        # HCL decodes string escapes and interpolation; this checker compares
        # raw text, so any such spelling is unknown rather than evaluated. Vault
        # treats "*" as a glob only as the last character of a path; elsewhere it
        # is a literal, which this checker does not model, so it is unknown too.
        if ("+" in pattern or "{{" in pattern or "%" in pattern
                or "\\" in pattern or "${" in pattern
                or "*" in pattern[:-1]):
            raise Unknown(f"{label}: wildcard/template/escape syntax in {pattern!r} is not supported")
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


def _nonempty_str(v):
    return isinstance(v, str) and v != ""


def _validate_config(cfg):
    """Every field has an exact type; a malformed config is Unknown, never a traceback."""
    if not isinstance(cfg, dict):
        raise Unknown("config: top level must be an object")
    if not _nonempty_str(cfg.get("base_dir")):
        raise Unknown("config: 'base_dir' must be a non-empty string")
    idents = cfg.get("identities")
    if not isinstance(idents, dict) or not idents:
        raise Unknown("config: 'identities' must be a non-empty object")
    for name, ident in idents.items():
        pol = ident.get("policies") if isinstance(ident, dict) else None
        if not isinstance(pol, list) or not pol or not all(_nonempty_str(p) for p in pol):
            raise Unknown(f"config: identity {name!r} needs a non-empty policies list of non-empty strings")
    exps = cfg.get("expectations")
    if not isinstance(exps, list) or not exps:
        raise Unknown("config: 'expectations' must be a non-empty list")
    for i, e in enumerate(exps):
        if not isinstance(e, dict):
            raise Unknown(f"config: expectation #{i} must be an object")
        ident = e.get("identity")
        if not _nonempty_str(ident) or ident not in idents:
            raise Unknown(f"config: expectation #{i} 'identity' must be a string naming a known identity")
        if not _nonempty_str(e.get("path")):
            raise Unknown(f"config: expectation #{i} 'path' must be a non-empty string")
        eff = e.get("effective")
        if not isinstance(eff, list):
            raise Unknown(f"config: expectation #{i} 'effective' must be a list")
        for c in eff:
            if not isinstance(c, str) or c not in KNOWN_CAPS:
                raise Unknown(f"config: expectation #{i} 'effective' has an element that is not a known capability name")


def load_config(path):
    try:
        cfg = json.loads(pathlib.Path(path).read_text(encoding="utf-8", errors="strict"))
    except (OSError, ValueError, RecursionError) as e:  # ValueError covers bad UTF-8 and bad JSON
        raise Unknown(f"config {path}: {e}")
    _validate_config(cfg)
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
                text = p.read_text(encoding="utf-8", errors="strict")
            except (OSError, ValueError) as e:
                # ValueError includes UnicodeDecodeError: a file that is present
                # but not valid UTF-8 could not be observed, so it is UNKNOWN.
                problems.append(f"{name}: cannot read policy file {p}: {getattr(e, 'strerror', None) or e}")
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
