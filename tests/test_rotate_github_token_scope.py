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
import json
import pathlib
import sys
import urllib.error
import urllib.request

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


def verify_token_source() -> str:
    """The verify_token function, taken from the template."""
    tree = ast.parse(embedded_python())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "verify_token":
            return ast.unparse(node)
    raise AssertionError(
        "could not find verify_token in the template — it changed shape and "
        "this test is now checking nothing")


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
    case("real response passes",
         want,
         {"permissions": {"contents": "read", "actions": "write", "metadata": "read"},
          "repositories": [{"name": "mctl-gitops"}]},
         should_raise=False)

    # Permissions are NOT asserted from the response any more — GitHub echoes
    # a narrowing it does not fully apply, so the echo proves nothing. These
    # must therefore pass: the repositories half is all this block checks.
    case("extra permissions in the response are ignored here",
         want,
         {"permissions": {"contents": "write", "actions": "write", "issues": "write",
                          "metadata": "read"},
          "repositories": [{"name": "mctl-gitops"}]},
         should_raise=False)
    case("an extra repository raises",
         want,
         {"permissions": {"contents": "read", "actions": "write", "metadata": "read"},
          "repositories": [{"name": "mctl-gitops"}, {"name": "mctl-api"}]},
         should_raise=True)
    # The strictest scope is the one where an ignored limit matters most, so an
    # explicitly empty request must still be verified rather than skipped.
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

    # --- verify_token: the check that replaced the response-based one -------
    #
    # Its logic is "the status code must be one this check accepts". The point
    # worth pinning is that the accepted set is per-probe: a repository outside
    # the token's scope answers 404, not 403, so a rule like "403 means
    # refused" would read a correctly invisible repository as reachable. That
    # mistake was made and caught by running it against the live tokens.
    fn_src = verify_token_source()

    def run_verify(codes, checks):
        """Drive verify_token with a stubbed API returning `codes` in order."""
        seq = list(codes)

        class Resp:
            def __init__(self, status):
                self.status = status

        def fake_urlopen(req):
            code = seq.pop(0)
            if code >= 400:
                raise urllib.error.HTTPError(req.full_url, code, "", None, None)
            return Resp(code)

        ns = {"json": json, "urllib": urllib, "print": lambda *a, **k: None}
        exec(compile(fn_src, "<verify_token>", "exec"), ns, ns)
        real = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            ns["verify_token"]("t0ken", checks, "test")
            return None
        except RuntimeError as exc:
            return str(exc)
        finally:
            urllib.request.urlopen = real

    probes = [({200}, "GET", "/a", None), ({404}, "POST", "/b", {}),
              ({403}, "POST", "/c", {}), ({404}, "GET", "/d", None)]

    for label, codes, should_raise in [
        ("verify: the scoped token's real codes pass", [200, 404, 403, 404], False),
        ("verify: an unscoped token (422 where 403 required) raises", [200, 404, 422, 404], True),
        ("verify: an out-of-scope repo that answers 200 raises", [200, 404, 403, 200], True),
        ("verify: a clone that lost access (403) raises", [403, 404, 403, 404], True),
        ("verify: a dispatch refused (403 where 404 required) raises", [200, 403, 403, 404], True),
    ]:
        msg = run_verify(codes, probes)
        ok = (msg is not None) == should_raise
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(label)

    if failures:
        print(f"\n{len(failures)} case(s) failed: {', '.join(failures)}")
        return 1
    print("\nscope validation behaves as documented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
