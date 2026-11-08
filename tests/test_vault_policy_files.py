#!/usr/bin/env python3
"""Vault policy files: structure and the writer-prefix rules.

Conservative parser for the small HCL subset these files use (comments, and
`path "<p>" { capabilities = [..] }` blocks). Anything it cannot parse is an
error, never an empty policy.

Checks:
- every vault-policy-*.hcl parses, with known capabilities and balanced braces;
- gitops-writer-read grants only read/list, only under writers/gitops/;
- external-secrets-read and argo-workflow-teams-rw deny secret/{data,metadata}/writers/*;
- no other policy file grants anything on the writers/ subtree, judged by
  evaluating each policy's effective capabilities (see effective_caps) on a
  witness set derived from that policy's own rule patterns (see witnesses),
  not by looking at path prefixes and not on a fixed list of sample paths.

Path matching follows the Vault policy docs (https://developer.hashicorp.com/vault/docs/concepts/policies,
sections "Policy syntax" for globs and "+" segment wildcards, and "Priority
matching"): when several rules in a
policy match a request path, only the highest-priority one applies. Priority:
a later first wildcard beats an earlier one; a path that does not end in "*"
beats one that does; fewer "+" segments beats more; a longer path beats a
shorter one; otherwise the lexicographically larger path wins. Rules with the
identical path are merged, and "deny" in the merged set wins. So a deny is only
protection when its rule is the winning one for the path in question.

Witness construction (pattern-vs-subtree, not sampling): the subtree is
secret/{data,metadata}/writers[/<extra segments>]. Whether a rule can match,
and win, anywhere inside it depends only on how each path segment compares to
the segments the policy's patterns mention. So for every policy the candidate
extra segments are: each literal segment of its patterns, each trailing-glob
partial prefix (as is, and extended), the empty segment, and one fresh segment
no pattern can match by name. Every combination of these up to one segment
deeper than the longest pattern is evaluated; any segment outside the set
behaves like the fresh one. A grant anywhere in that set is a grant on the
subtree.

Fail closed: a pattern shape this evaluator does not model (templated
"{{ }}" paths, "*" anywhere but the end, "+" mixed into a longer segment) or a
witness space too large to enumerate raises ValueError, which the check
reports as an error. It is never read as "no grant".

Self-tests (test_* functions) run before the tree check.

Run: python3 tests/test_vault_policy_files.py
"""
import itertools
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
    return parse_text(path.read_text(encoding="utf-8"))


def parse_text(text):
    text = re.sub(r"(?m)^\s*(#|//).*$", "", text)
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


def validate_pattern(pattern):
    """Raise ValueError for a path shape this evaluator does not model."""
    if "{{" in pattern or "}}" in pattern:
        raise ValueError("templated policy path not evaluable: %s" % pattern)
    if "*" in pattern[:-1]:
        raise ValueError("'*' not at the end of the path not evaluable: %s" % pattern)
    for seg in pattern.rstrip("*").split("/"):
        if "+" in seg and seg != "+":
            raise ValueError("'+' inside a longer segment not evaluable: %s" % pattern)


def rule_matches(pattern, path):
    """Vault path match: exact, "+" for one whole segment, trailing "*" prefix glob."""
    validate_pattern(pattern)
    glob = pattern.endswith("*")
    base = pattern[:-1] if glob else pattern
    psegs = base.split("/")
    segs = path.split("/")
    if glob:
        if len(segs) < len(psegs):
            return False
    elif len(segs) != len(psegs):
        return False
    for i, ps in enumerate(psegs):
        last = i == len(psegs) - 1
        if last and glob:
            return segs[i].startswith(ps)
        if ps == "+":
            if not segs[i]:
                return False
        elif ps != segs[i]:
            return False
    return True


MAX_WITNESSES = 200000


def witnesses(rules):
    """[(path, extra_segments)] covering every behaviour inside the writers/ subtree."""
    alpha = {""}
    prefixes = set()
    maxlen = 0
    for pat, _ in rules:
        validate_pattern(pat)
        segs = pat.split("/")
        maxlen = max(maxlen, len(segs))
        for i, sg in enumerate(segs):
            if sg == "+":
                continue
            if i == len(segs) - 1 and pat.endswith("*"):
                sg = sg[:-1]
                prefixes.add(sg)
                if sg:
                    alpha.add(sg + "q")
            if sg:
                alpha.add(sg)
    fresh = "f"
    while any(p and (fresh.startswith(p) or p.startswith(fresh)) for p in prefixes) or fresh in alpha:
        fresh += "f"
    alpha.add(fresh)
    alpha = sorted(alpha)
    depth = max(maxlen - 3, 0) + 1
    if sum(len(alpha) ** n for n in range(depth + 1)) * 2 > MAX_WITNESSES:
        raise ValueError("witness space too large to enumerate")
    out = []
    for form in ("data", "metadata"):
        for n in range(depth + 1):
            for combo in itertools.product(alpha, repeat=n):
                out.append(("secret/%s/writers" % form + "".join("/" + c for c in combo), n))
    return out


def priority(pattern):
    """Sort key: the maximum is the rule Vault applies (see module docstring)."""
    wild = [i for i in (pattern.find("+"), pattern.find("*")) if i >= 0]
    first_wild = min(wild) if wild else len(pattern) + 1
    return (first_wild, not pattern.endswith("*"), -pattern.split("/").count("+"), len(pattern), pattern)


def effective_caps(rules, path):
    """Capabilities one policy gives on a concrete path; empty set if none match."""
    hits = [p for p, _ in rules if rule_matches(p, path)]
    if not hits:
        return set()
    win = max(hits, key=priority)
    caps = set()
    for p, c in rules:
        if p == win:
            caps |= set(c)
    return {"deny"} if "deny" in caps else caps


def writers_grants(rules):
    """[(witness, caps)] where the policy grants something other than deny inside writers/."""
    out = []
    for s, _ in witnesses(rules):
        caps = effective_caps(rules, s)
        if caps and caps != {"deny"}:
            out.append((s, sorted(caps)))
    return out


def deny_gaps(rules):
    """Witnesses strictly below writers/ whose effective capabilities are not exactly deny."""
    return [s for s, n in witnesses(rules) if n >= 1 and effective_caps(rules, s) != {"deny"}]


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
    return errs + check_parsed(parsed)


def check_parsed(parsed):
    errs = []
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
        try:
            gaps = deny_gaps(rules)
        except ValueError as e:
            errs.append("%s: cannot evaluate: %s" % (name, e))
            continue
        for gap in gaps[:5]:
            errs.append("%s: deny is not the effective rule on %s" % (name, gap))
    for name, rules in parsed.items():
        if name == WRITER_READ:
            continue
        try:
            grants = writers_grants(rules)
        except ValueError as e:
            errs.append("%s: cannot evaluate: %s" % (name, e))
            continue
        for sample, caps in grants[:5]:
            errs.append("%s grants %s on %s" % (name, caps, sample))
    return errs


_DENY = [("secret/data/writers/*", ["deny"]), ("secret/metadata/writers/*", ["deny"])]


def _good_denying():
    parsed = {WRITER_READ: [("secret/data/writers/gitops/*", ["read"]),
                            ("secret/metadata/writers/gitops/*", ["read", "list"])]}
    parsed.update({n: [("secret/data/platform/*", ["read"])] + _DENY for n in DENY_IN})
    return parsed


def test_real_tree_passes():
    assert check() == []


def test_matcher_basics():
    assert rule_matches("secret/data/writers/*", "secret/data/writers/gitops/x")
    assert not rule_matches("secret/data/writers/*", "secret/data/writers")
    assert rule_matches("secret/+/writers/*", "secret/metadata/writers/a")
    assert not rule_matches("secret/+/writers/*", "secret/data/other/a")
    assert not rule_matches("secret/data/+", "secret/data/")
    assert rule_matches("secret/data/x*", "secret/data/xy/z")
    assert not rule_matches("secret/data/x", "secret/data/xy")


def test_wide_star_grant_fails():
    parsed = _good_denying()
    parsed["vault-policy-other.hcl"] = [("secret/*", ["read"])]
    assert any("vault-policy-other.hcl grants" in e for e in check_parsed(parsed))


def test_plus_segment_grant_fails():
    parsed = _good_denying()
    parsed["vault-policy-other.hcl"] = [("secret/+/writers/*", ["read", "list"])]
    assert any("vault-policy-other.hcl grants" in e for e in check_parsed(parsed))


def test_data_wildcard_forms_fail():
    for pat in ("secret/data/*", "secret/metadata/*", "secret/data/+/gitops/*", "secret/+/+/gitops/x",
                "secret/data/writers", "secret/metadata/writers/*"):
        parsed = _good_denying()
        parsed["vault-policy-other.hcl"] = [(pat, ["update"])]
        assert check_parsed(parsed), pat


def test_unrelated_grants_pass():
    parsed = _good_denying()
    parsed["vault-policy-other.hcl"] = [("secret/data/teams/+/+", ["read"]),
                                       ("secret/data/platform/*", ["read"])]
    assert check_parsed(parsed) == []


def test_deny_only_in_other_policy_is_allowed():
    parsed = _good_denying()
    parsed["vault-policy-other.hcl"] = [("secret/*", ["deny"])]
    assert check_parsed(parsed) == []


def test_shadowed_deny_is_not_protection():
    # The longer read grant outranks the shorter deny glob for writers/gitops/x,
    # so the deny rule exists but is not the effective one there.
    parsed = _good_denying()
    parsed[DENY_IN[0]] = [("secret/data/writers/gitops/*", ["read"]),
                          ("secret/metadata/writers/gitops/*", ["read"])] + _DENY
    errs = check_parsed(parsed)
    assert any(DENY_IN[0] in e and "not the effective rule" in e for e in errs)
    assert any(DENY_IN[0] + " grants" in e for e in errs)


def test_equal_path_deny_wins_over_grant():
    rules = [("secret/data/writers/*", ["read"]), ("secret/data/writers/*", ["deny"])]
    assert effective_caps(rules, "secret/data/writers/a") == {"deny"}


def test_exact_grant_beats_glob_deny():
    rules = [("secret/data/writers/a", ["read"]), ("secret/data/writers/*", ["deny"])]
    assert effective_caps(rules, "secret/data/writers/a") == {"read"}
    assert effective_caps(rules, "secret/data/writers/b") == {"deny"}


def test_plus_rule_outranked_by_later_wildcard():
    # secret/data/+/x has its first wildcard earlier than secret/data/writers/*,
    # so the explicit writers/ rule (the deny) is the one that applies.
    rules = [("secret/data/+/x", ["read"]), ("secret/data/writers/*", ["deny"])]
    assert effective_caps(rules, "secret/data/writers/x") == {"deny"}


def _other_fails(*rules):
    parsed = _good_denying()
    parsed["vault-policy-other.hcl"] = list(rules)
    return any(e.startswith("vault-policy-other.hcl") for e in check_parsed(parsed))


def test_exact_path_in_writers_fails():
    assert _other_fails(("secret/data/writers/foo", ["read"]))
    assert _other_fails(("secret/metadata/writers/foo", ["list"]))


def test_exact_path_under_gitops_fails():
    assert _other_fails(("secret/data/writers/gitops/deploy", ["read"]))


def test_deeper_exact_path_fails():
    assert _other_fails(("secret/data/writers/a/b/c/d", ["read"]))


def test_glob_inside_writers_fails():
    assert _other_fails(("secret/data/writers/z*", ["read"]))
    assert _other_fails(("secret/data/writers/gitops/deep/er*", ["read"]))


def test_plus_segments_fail():
    assert _other_fails(("secret/data/writers/+", ["read"]))
    assert _other_fails(("secret/data/+/foo", ["read"]))
    assert _other_fails(("secret/+/writers/+/x", ["read"]))


def test_bare_mount_glob_fails():
    assert _other_fails(("secret/*", ["read"]))
    assert _other_fails(("*", ["read"]))
    assert _other_fails(("sec*", ["read"]))


def test_wider_glob_in_another_policy_fails():
    assert _other_fails(("secret/data/*", ["read"]), ("secret/data/platform/*", ["read"]))
    assert _other_fails(("secret/metadata/*", ["list"]))


def test_unrelated_exact_and_glob_pass():
    assert not _other_fails(("secret/data/writer", ["read"]), ("secret/data/writersx/*", ["read"]),
                            ("secret/data/platform/writers/*", ["read"]))
    assert not _other_fails(("secret/data/writers-old/x", ["read"]))


def test_unevaluable_patterns_fail_closed():
    for pat in ("secret/data/{{identity.entity.name}}/*", "secret/*/writers", "secret/data/wri+ters/x"):
        assert _other_fails((pat, ["read"])), pat
        try:
            writers_grants([(pat, ["read"])])
        except ValueError:
            continue
        raise AssertionError("evaluated %r" % pat)


def test_unevaluable_in_deny_policy_fails_closed():
    parsed = _good_denying()
    parsed[DENY_IN[0]] = parsed[DENY_IN[0]] + [("secret/data/{{x}}/y", ["read"])]
    assert any(DENY_IN[0] in e and "cannot evaluate" in e for e in check_parsed(parsed))


def test_partial_segment_globs_do_not_overmatch():
    assert not rule_matches("secret/data/ab*", "secret/data/a")
    assert not rule_matches("secret/data/ab*", "secret/data/ba")
    assert not rule_matches("secret/data/writers/gitops*", "secret/data/writers/gitop")
    assert not rule_matches("secret/data/x*", "secret/data/yx")
    assert not rule_matches("secret/da*", "secret/metadata/x")
    assert rule_matches("secret/da*", "secret/data/x")
    assert rule_matches("secret/data/ab*", "secret/data/abc/d")


def test_partial_glob_outside_writers_passes():
    assert not _other_fails(("secret/data/wx*", ["read"]))
    assert not _other_fails(("secret/data/writers-*", ["read"]))


def test_glob_grant_next_to_exact_deny_fails():
    # The exact deny only covers the path "z"; the glob grant still wins on "zq...".
    assert _other_fails(("secret/data/writers/z*", ["read"]), ("secret/data/writers/z", ["deny"]))
    # Same, with the deeper "z/..." paths denied too: only the extended segment "zq" is granted.
    assert _other_fails(("secret/data/writers/z*", ["read"]), ("secret/data/writers/z", ["deny"]),
                        ("secret/data/writers/z/*", ["deny"]))


def test_trailing_slash_exact_grant_beats_deny_glob():
    parsed = _good_denying()
    parsed[DENY_IN[0]] = parsed[DENY_IN[0]] + [("secret/data/writers/", ["list"])]
    assert any(DENY_IN[0] in e and "not the effective rule" in e for e in check_parsed(parsed))


def test_missing_deny_fails():
    parsed = _good_denying()
    parsed[DENY_IN[1]] = [("secret/data/platform/*", ["read"])]
    assert any(DENY_IN[1] in e for e in check_parsed(parsed))


def test_parse_text_rejects_garbage():
    for bad in ('path "a" { capabilities = ["read" list] }', 'path "a" { capabilities = ["nope"] }', ""):
        try:
            parse_text(bad)
        except ValueError:
            continue
        raise AssertionError("accepted %r" % bad)


def run_selftests():
    names = sorted(n for n in globals() if n.startswith("test_"))
    for n in names:
        globals()[n]()
    return len(names)


if __name__ == "__main__":
    print("selftests: %d passed" % run_selftests())
    errs = check()
    for e in errs:
        print("FAIL:", e)
    if errs:
        sys.exit(1)
    print("ok")
