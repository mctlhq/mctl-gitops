#!/usr/bin/env python3
"""Vault policy files: structure and the writer-prefix rules.

Conservative parser for the small HCL subset these files use (comments, and
`path "<p>" { capabilities = [..] }` blocks). Anything it cannot parse is an
error, never an empty policy.

Checks:
- every vault-policy-*.hcl parses, with known capabilities and balanced braces;
- gitops-writer-read grants only read/list, only under writers/gitops/;
- external-secrets-read and argo-workflow-teams-rw deny secret/{data,metadata}/writers/*
  (only these two KV v2 forms: those policies deny nothing else);
- no other policy file grants anything on the writers/ subtree, where the subtree
  is the KV v2 API forms secret/{data,metadata,subkeys,delete,undelete,destroy}/writers/...
  (GRANT_FORMS; other mounts and other API paths are not covered), judged by
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

Witness construction (a decision procedure, not sampling). A rule's match on a
path depends on each segment only through: equality with a literal segment of
some pattern, "starts with" a trailing-glob prefix of some pattern, and
non-emptiness (for "+"). Segments that agree on all three are
indistinguishable, so it is enough to evaluate one representative per class
(segment_alphabet, with the argument in its docstring): every literal, the
empty segment, and for every glob prefix m (including the empty one) the class
"starts with m, is no literal, starts with no longer glob prefix". Segments past
a rule's last position are unconstrained, so paths of one segment more than the
longest pattern stand for all deeper ones. Evaluating winner-takes-precedence
on every combination of representatives up to that depth therefore decides, for
the policy, whether any path in the subtree is granted. The brute-force
cross-check test compares this against exhaustive enumeration over a small
alphabet.

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
GRANT_FORMS = ("data", "metadata", "subkeys", "delete", "undelete", "destroy")
DENY_FORMS = ("data", "metadata")
FRESH_CHARS = "zyxwvutsrqponmlkjihgfedcba9876543210"


def segment_alphabet(rules):
    """One representative per segment equivalence class induced by the rules.

    Whether a rule matches a path segment depends only on (a) equality with a
    literal segment of some pattern, (b) "starts with" a trailing-glob prefix of
    some pattern, (c) for "+", non-emptiness. Two segments that agree on all of
    these are indistinguishable to every rule. The classes are:
      - one per literal segment (the literal itself);
      - the empty segment;
      - for each glob prefix m (and the empty prefix): the strings that start
        with m, are not a literal and start with no longer glob prefix. They
        are represented by m + c, where c is a character that occurs in no
        pattern, so m + c is never a literal and starts with no longer prefix
        (a longer prefix would have to contain c). The prefix m itself is in
        the same class unless it is a literal, which has its own class.
    Every string falls in exactly one class (its longest matching glob prefix
    decides the third kind), so the list is complete.
    """
    literals, prefixes, chars = set(), {""}, set()
    for pat, _ in rules:
        validate_pattern(pat)
        chars |= set(pat)
        segs = pat.split("/")
        for i, sg in enumerate(segs):
            if sg == "+":
                continue
            if i == len(segs) - 1 and pat.endswith("*"):
                prefixes.add(sg[:-1])
            elif sg:
                literals.add(sg)
    c = next((x for x in FRESH_CHARS if x not in chars), None)
    if c is None:
        raise ValueError("no unused character for the fresh segment")
    return sorted(literals | {m + c for m in prefixes} | {""})


def max_segments(rules):
    return max(len(pat.split("/")) for pat, _ in rules)


def witness_paths(rules, head, min_extra, max_extra):
    """[(path, extra)]: head segments followed by min_extra..max_extra segments, each
    drawn from segment_alphabet. A path with more segments than the longest
    pattern behaves like one with exactly one more segment than it, because
    segments past a rule's last position are unconstrained, so callers pass
    max_extra = max_segments - len(head) + 1 at most (see witnesses)."""
    alpha = segment_alphabet(rules)
    if sum(len(alpha) ** n for n in range(max_extra + 1)) > MAX_WITNESSES:
        raise ValueError("witness space too large to enumerate")
    out = []
    for n in range(min_extra, max_extra + 1):
        for combo in itertools.product(alpha, repeat=n):
            out.append(("/".join(tuple(head) + combo), n))
    return out


def witnesses(rules, forms=GRANT_FORMS):
    """[(path, extra_segments)] covering every behaviour inside the writers/ subtree
    of the given KV v2 API forms: secret/<form>/writers[/<extra>...]. Extra
    segments run from none to one past the longest pattern (all deeper paths
    behave like the deepest one)."""
    depth = max(max_segments(rules) - 3, 0) + 1
    out = []
    for form in forms:
        out += witness_paths(rules, ("secret", form, "writers"), 0, depth)
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
    return [s for s, n in witnesses(rules, DENY_FORMS) if n >= 1 and effective_caps(rules, s) != {"deny"}]


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
            errs.append("%s grants %s on %s (writers/ subtree, KV v2 forms %s)"
                        % (name, caps, sample, "/".join(GRANT_FORMS)))
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


def test_all_kv2_forms_are_protected():
    for form in GRANT_FORMS:
        assert _other_fails(("secret/%s/writers/x" % form, ["read"])), form
        assert _other_fails(("secret/%s/writers/*" % form, ["update"])), form
        assert _other_fails(("secret/%s/writers/a/b" % form, ["delete"])), form
    assert _other_fails(("secret/+/writers/*", ["read"]))
    # Forms that are not KV v2 API forms of this mount stay out of scope.
    assert not _other_fails(("secret/config/writers/x", ["read"]))
    assert not _other_fails(("other/data/writers/x", ["read"]))


def test_extra_forms_witnessed():
    ws = {p for p, _ in witnesses([("secret/destroy/writers/x", ["update"])])}
    assert "secret/destroy/writers/x" in ws
    for form in GRANT_FORMS:
        assert "secret/%s/writers" % form in ws


def test_writer_read_pattern_check_unchanged_for_extra_forms():
    parsed = _good_denying()
    parsed[WRITER_READ] = parsed[WRITER_READ] + [("secret/subkeys/writers/gitops/*", ["read"])]
    assert any("path outside writers/gitops" in e for e in check_parsed(parsed))


def test_unnamed_segment_class_is_witnessed():
    # Every named or empty segment is denied by an exact rule; only a segment no
    # pattern names is granted by the "+" rule. Without the fresh class this looks clean.
    rules = [("secret/data/writers/+", ["read"]), ("secret/data/writers/", ["deny"]),
             ("secret/data/writers/a", ["deny"])]
    # The pattern's own words are literals too, so deny those as well.
    rules += [("secret/data/writers/" + w, ["deny"]) for w in ("secret", "data", "writers")]
    grants = writers_grants(rules)
    assert grants and all(c == ["read"] for _, c in grants)
    assert _other_fails(*rules)
    # And with the exact denies shadowing nothing wider, it is the unnamed class alone.
    assert {s for s, _ in grants} == {"secret/data/writers/" + segment_alphabet(rules)[-1]}


def test_depth_beyond_longest_pattern_is_witnessed():
    # Every path as long as the longest pattern is denied; the glob only wins one
    # segment deeper.
    rules = [("secret/data/writers/*", ["read"]), ("secret/data/writers/+", ["deny"]),
             ("secret/data/writers/", ["deny"])]
    assert all(s.count("/") >= 4 for s, _ in writers_grants(rules))
    assert writers_grants(rules)
    assert _other_fails(*rules)


def test_glob_prefix_class_between_literals_is_witnessed():
    # "ab..." is granted by the broad glob, while the segment "a" and the longer
    # prefix class "aq..." are denied: a witness set of {a, aq...} misses "ab".
    rules = [("secret/data/writers/a*", ["read"]), ("secret/data/writers/a", ["deny"]),
             ("secret/data/writers/aq*", ["deny"]), ("secret/data/writers/", ["deny"]),
             ("secret/data/writers/a/*", ["deny"])]
    got = {s for s, _ in writers_grants(rules)}
    assert got and all(s.split("/")[3].startswith("a") for s in got), got
    assert _other_fails(*rules)


# -- brute-force cross-check ------------------------------------------------

def _outcomes(rules, paths):
    return {frozenset(effective_caps(rules, "/".join(p))) for p in paths}


_BRUTE = None


def _brute_paths(maxlen):
    global _BRUTE
    if _BRUTE is None:
        segs = [""] + ["".join(t) for n in (1, 2, 3) for t in itertools.product("abz", repeat=n)]
        _BRUTE = [t for n in range(1, maxlen + 1) for t in itertools.product(segs, repeat=n)]
    return _BRUTE


def _procedure_outcomes(rules):
    depth = max_segments(rules) + 1
    return _outcomes(rules, (tuple(p.split("/")) if p else ("",)
                            for p, _ in witness_paths(rules, (), 1, depth)))


def _random_rules(rng):
    lits, prefixes = ["a", "b", "ab", "+"], ["", "a", "b", "ab"]
    caps = [["read"], ["list"], ["update"], ["create"], ["delete"], ["deny"], ["patch"]]
    rules = []
    for _ in range(rng.randint(2, 4)):
        n = rng.randint(1, 2)
        segs = [rng.choice(lits) for _ in range(n - 1)]
        last = rng.choice(lits[:3] + ["+"] + [x + "*" for x in prefixes] * 2)
        rules.append(("/".join(segs + [last]), rng.choice(caps)))
    return rules


def test_procedure_matches_exhaustive_enumeration():
    import random
    rng = random.Random(20261108)
    fixed = [
        [("a*", ["read"]), ("a", ["deny"]), ("ab*", ["deny"]), ("", ["deny"])],
        [("*", ["read"]), ("a", ["deny"]), ("b", ["deny"]), ("", ["deny"])],
        [("a/+", ["read"]), ("a/*", ["deny"]), ("a/b", ["update"])],
        [("a*", ["read"]), ("ab*", ["list"]), ("a", ["update"]), ("ab", ["deny"]), ("", ["create"])],
    ]
    sets = fixed + [_random_rules(rng) for _ in range(40)]
    for rules in sets:
        maxlen = max_segments(rules) + 1
        assert maxlen <= 3, rules
        brute = _outcomes(rules, _brute_paths(3))
        assert _procedure_outcomes(rules) == brute, rules


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
