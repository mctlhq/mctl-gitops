"""The two inline tag writers keep the same protections (mctlhq/mctl-gitops#2652).

release-deploy.yaml and gitops-bump.yaml each carry their own copy of the bump
script, and the copies drifted: release-deploy went without the symlink check,
the "only tags changed" edit check and the quoting of the split-registry tag
that gitops-bump had. Their inputs differ on purpose (path lists, default path,
image shape), so the scripts are not required to be identical; the pieces that
guard what reaches main are, and are compared here as Python ASTs, so comments
and spacing may differ but behaviour may not. Each named mutation must turn the
comparison red. Plain script: `python3 tests/test_bump_writers_parity.py`.
"""
import ast
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WRITERS = {
    "release-deploy": (".github/workflows/release-deploy.yaml", "Bump image tag(s)"),
    "gitops-bump": (".github/workflows/gitops-bump.yaml", "Bump image tags"),
}
SHARED_FUNCTIONS = ("validate_allowed", "same_but_tags", "only_tags_changed")


def script(path, step_name):
    doc = yaml.safe_load((ROOT / path).read_text())
    steps = [s for job in doc["jobs"].values() for s in job.get("steps", []) if s.get("name") == step_name]
    assert len(steps) == 1, f"{path}: {len(steps)} steps named {step_name!r}"
    run = steps[0]["run"]
    start = run.index("<<'PYEOF'\n") + len("<<'PYEOF'\n")
    return run[start:run.index("\nPYEOF", start)]


def pieces(source):
    """Shared functions, the replacement callables and the edit-check call, as AST dumps."""
    tree = ast.parse(source)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in SHARED_FUNCTIONS:
            out[node.name] = ast.dump(node, annotate_fields=False)
    # Every .subn(lambda ...) replacement, by the literal text it writes.
    out["replacements"] = sorted(
        ast.dump(n.args[0].body, annotate_fields=False) for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "subn"
        and n.args and isinstance(n.args[0], ast.Lambda))
    out["edit check before write"] = any(
        isinstance(n, ast.Call) and getattr(n.func, "id", None) == "only_tags_changed" for n in ast.walk(tree))
    return out


def compare(sources):
    a, b = (pieces(s) for s in sources.values())
    bad = []
    for name in SHARED_FUNCTIONS:
        if name not in a or name not in b:
            bad.append(f"{name} missing from one writer")
        elif a[name] != b[name]:
            bad.append(f"{name} differs")
    if a["replacements"] != b["replacements"]:
        bad.append("tag replacements differ")
    if not (a["edit check before write"] and b["edit check before write"]):
        bad.append("a writer does not call only_tags_changed")
    return bad


MUTANTS = [
    ("release-deploy", "symlink check dropped",
     "if os.path.realpath(path) != os.path.join(os.path.realpath(os.curdir), normalized):", "if False:"),
    ("release-deploy", "split tag unquoted",
     """p3.subn(lambda m: m.group(1) + ' "' + new_tag + '"', out)""", "p3.subn(lambda m: m.group(1) + ' ' + new_tag, out)"),
    ("release-deploy", "edit check not called",
     "if not only_tags_changed(content, out):", "if False:"),
    ("gitops-bump", "edit check loosened",
     'o.split(":", 1)[0] != n.split(":", 1)[0] or new_tag not in n', 'new_tag not in n'),
    ("gitops-bump", "parsed comparison loosened",
     'b.endswith(":" + new_tag)', 'b.endswith(new_tag)'),
]


def main():
    sources = {k: script(*v) for k, v in WRITERS.items()}
    failures = compare(sources)
    for f in failures:
        print("FAIL", f)
    if not failures:
        print("PASS the writers share their protections")
    survivors = []
    for which, name, old, new in MUTANTS:
        if sources[which].count(old) != 1:
            survivors.append(f"{name}: anchor not found once")
        elif not compare({**sources, which: sources[which].replace(old, new)}):
            survivors.append(name)
    for s in survivors:
        print("MUTANT SURVIVED", s)
    print(f"{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} mutants killed")
    sys.exit(1 if failures or survivors else 0)


if __name__ == "__main__":
    main()
