"""Exercise rotate-github-app-tokens' scope validation, taken from the template.

The mctl-api target mints an installation token narrowed to one repository and
two permissions. Narrowing is only worth anything if a narrowing that did NOT
apply is noticed: an empty Content-Type, an API change, a typo in the scope
dict all fail the same quiet way, handing out a token with the installation's
full grant that works and logs identically.

So the mint checks GitHub's response against what it asked for. That check is
the thing under test here, and it is EXTRACTED from the CronWorkflow rather
than restated — a copy would keep passing after the template changed, which is
the failure mode this file exists to avoid (same reasoning as
test_tpl_git_commit_yq.py).

Run: python3 tests/test_rotate_github_token_scope.py
"""
import ast
import pathlib
import sys

import yaml

CWFT = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/cwft-rotate-github-token.yaml")


def embedded_python() -> str:
    doc = yaml.safe_load(CWFT.read_text())
    source = doc["spec"]["workflowSpec"]["templates"][0]["script"]["source"]
    start = source.index("<< 'PYEOF'")
    return source[source.index("\n", start) + 1:source.rindex("PYEOF")]


def scope_check_source() -> str:
    """The `if scope:` block out of mint_installation_token, verbatim."""
    tree = ast.parse(embedded_python())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "mint_installation_token":
            for stmt in node.body:
                if isinstance(stmt, ast.If) and getattr(stmt.test, "id", None) == "scope":
                    return ast.unparse(stmt)
    raise AssertionError(
        "could not find the `if scope:` validation in mint_installation_token — "
        "the template changed shape and this test is now checking nothing")


CHECK = scope_check_source()


def empty_scope_guard_source() -> str:
    """The `if scope is not None and not scope:` refusal, verbatim."""
    tree = ast.parse(embedded_python())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "mint_installation_token":
            for stmt in node.body:
                if (isinstance(stmt, ast.If)
                        and isinstance(stmt.test, ast.BoolOp)
                        and "not scope" in ast.unparse(stmt.test)):
                    return ast.unparse(stmt)
    raise AssertionError(
        "could not find the empty-scope refusal in mint_installation_token — "
        "the template changed shape and this test is now checking nothing")


EMPTY_GUARD = empty_scope_guard_source()


def run(scope, result):
    """Execute the extracted check; return None on pass, the message on raise.

    One namespace for globals and locals, deliberately. With two, a
    comprehension or generator expression inside the extracted block cannot see
    names bound in the enclosing exec frame and dies with NameError — so the
    test would report a failure the code does not have, and could mask a real
    pass. Found by mutating the template to use a genexpr and watching this
    blow up instead of judging.
    """
    ns = {"scope": scope, "result": result}
    try:
        exec(compile(CHECK, "<scope-check>", "exec"), ns, ns)
        return None
    except RuntimeError as exc:
        return str(exc)


def main() -> int:
    want = {"repositories": ["mctl-gitops"],
            "permissions": {"contents": "read", "actions": "write"}}
    failures = []

    def case(label, scope, result, should_raise):
        msg = run(scope, result)
        ok = (msg is not None) == should_raise
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(label)

    # What GitHub actually returns for the mctl-api target.
    case("real response (metadata:read added by GitHub) passes",
         want,
         {"permissions": {"contents": "read", "actions": "write", "metadata": "read"},
          "repositories": [{"name": "mctl-gitops"}]},
         should_raise=False)

    # The two ways narrowing is lost, both silent in every other signal.
    case("an extra permission raises",
         want,
         {"permissions": {"contents": "read", "actions": "write", "issues": "write",
                          "metadata": "read"},
          "repositories": [{"name": "mctl-gitops"}]},
         should_raise=True)
    case("the installation's full grant raises",
         want,
         {"permissions": {"contents": "write", "actions": "write", "metadata": "read"},
          "repositories": [{"name": "mctl-gitops"}]},
         should_raise=True)
    case("an extra repository raises",
         want,
         {"permissions": {"contents": "read", "actions": "write", "metadata": "read"},
          "repositories": [{"name": "mctl-gitops"}, {"name": "mctl-api"}]},
         should_raise=True)
    case("a missing requested permission raises",
         want,
         {"permissions": {"contents": "read", "metadata": "read"},
          "repositories": [{"name": "mctl-gitops"}]},
         should_raise=True)

    # A target naming metadata explicitly must not fail for asking for what it
    # is given anyway — the comparison drops it from both sides.
    case("metadata requested explicitly passes",
         {"permissions": {"contents": "read", "metadata": "read"}},
         {"permissions": {"contents": "read", "metadata": "read"}},
         should_raise=False)

    # The strictest scope is the one where an ignored limit matters most, so an
    # explicitly empty request must still be verified rather than skipped.
    case("empty permissions request still verified",
         {"permissions": {}},
         {"permissions": {"contents": "write", "metadata": "read"}},
         should_raise=True)
    case("empty repositories request still verified",
         {"repositories": []},
         {"permissions": {}, "repositories": [{"name": "mctl-gitops"}]},
         should_raise=True)

    # The shape a token that was NOT narrowed actually has: GitHub omits the
    # repositories key entirely on a full grant. Reading that as [] would make
    # a full-access token indistinguishable from a successful narrowing to
    # none — the single most expensive confusion available here, and the one
    # the fixture above could not catch because it supplies the key.
    case("full grant (repositories key absent) raises against []",
         {"repositories": []},
         {"permissions": {}},
         should_raise=True)
    case("full grant (repositories key absent) raises against a named repo",
         {"repositories": ["mctl-gitops"]},
         {"permissions": {"contents": "read", "actions": "write", "metadata": "read"}},
         should_raise=True)

    # `scope: {}` serialises to the body {} — byte-identical to no scope — so
    # it requests NO narrowing while reading like the strictest possible ask.
    # Refused rather than honoured, so nobody writes it expecting the opposite.
    def guard(scope):
        ns = {"scope": scope}
        try:
            exec(compile(EMPTY_GUARD, "<empty-guard>", "exec"), ns, ns)
            return None
        except RuntimeError as exc:
            return str(exc)

    for label, scope, should_raise in [
        ("scope {} is refused outright", {}, True),
        ("no scope is allowed", None, False),
        ("a real narrowing is allowed", {"repositories": []}, False),
    ]:
        msg = guard(scope)
        ok = (msg is not None) == should_raise
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(label)

    # Targets that pass no scope keep the previous behaviour: nothing checked,
    # because nothing was promised.
    case("no scope checks nothing",
         None,
         {"permissions": {"contents": "write", "issues": "write"}},
         should_raise=False)

    if failures:
        print(f"\n{len(failures)} case(s) failed: {', '.join(failures)}")
        return 1
    print("\nscope validation behaves as documented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
