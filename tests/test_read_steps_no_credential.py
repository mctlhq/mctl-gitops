"""Steps that only read mctl-gitops hold no write credential (mctlhq/mctl-agents#1007).

A ratchet: every template step that mounts the deploy key must push, or be listed
in KNOWN_READ_ONLY as work still to do. A new read-only step with the key fails
here, and so does a listed one that no longer has it, so the list can only shrink.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

import gitops_write_set as W

ROOT = pathlib.Path(__file__).resolve().parent.parent
TPL = ROOT / "platform-gitops/argo-workflows/cluster-templates"
KEY = "mctl-gitops-deploy-key"
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:400]}")


# Central mctl-agents templates and platform workflows: init containers that clone
# before the step that pushes. Next phase; none runs in a tenant namespace.
KNOWN_READ_ONLY = {
    ("cwft-mctl-agents-approve.yaml", "flip-status", "clone-gitops"),
    ("cwft-mctl-agents-approve.yaml", "commit-and-push", "clone-gitops"),
    ("cwft-mctl-agents-implement.yaml", "run-implementer", "clone-gitops"),
    ("cwft-mctl-agents-implement.yaml", "commit-and-push", "clone-gitops"),
    ("cwft-mctl-agents-investigate.yaml", "run-investigator", "clone-gitops"),
    ("cwft-mctl-agents-investigate.yaml", "commit-and-push", "clone-gitops"),
    ("cwft-mctl-agents-reconcile.yaml", "run-reconcile", "clone-gitops"),
    ("cwft-mctl-agents-reconcile.yaml", "commit-and-push", "clone-gitops"),
    ("cwft-mctl-agents-run.yaml", "run-orchestrator", "clone-gitops"),
    ("cwft-mctl-agents-run.yaml", "commit-and-push", "clone-gitops"),
    ("cwft-mctl-agents-run.yaml", "run-incident-responder", "clone-gitops"),
    ("cwft-mctl-agents-shepherd.yaml", "run-shepherd", "clone-gitops"),
    ("cwft-mctl-agents-shepherd.yaml", "commit-and-push", "clone-gitops"),
    ("wft-delete-tenant-safe.yaml", "retire-tenant-services", "main"),
    ("wft-lifecycle-bootstrap.yaml", "bootstrap", "clone-gitops"),
}


# A push is `git` at command position followed, through any options and their
# values, by `push`: `git push`, `git  push`, `git -C dir push`, `git -c k=v push`,
# `GIT_SSH_COMMAND=... git push`, `if ! git push`, `timeout 60 git push`. A word
# inside an echo or a quoted message is not at command position.
GIT_PUSH = re.compile(
    r"(?:^|[;&|(`{]|\b(?:then|do|else|if|elif|while|until)\b)\s*!?\s*"
    r"(?:\w+=\S*\s+)*(?:(?:exec|command|sudo|env|timeout\s+\S+|retry)\s+)*"
    r"git(?:\s+-\S+(?:\s+[^\s-]\S*)?)*\s+push\b", re.M)


# `sh -c "..."`, `bash -lc '...'` and `eval "..."` run their quoted argument as code.
RUNS_ARG = re.compile(r"(?:\beval|\b(?:ba|z|da|k)?sh(?:\s+-\w+)*\s+-\w*c)\s*$")


def _skip_dq(code, i):
    """Index just past the double quote that closes a double-quoted string whose
    body starts at `i`; a `$(...)` inside it is skipped as a whole, quotes and all."""
    n = len(code)
    while i < n:
        if code[i] == "\\":
            i += 2
        elif code[i] == '"':
            return i + 1
        elif code.startswith("$(", i):
            i = _subst_end(code, i + 2) + 1
        else:
            i += 1
    return n


def _subst_end(code, i):
    """Index of the `)` that closes a `$(` whose body starts at `i` (len(code) when
    there is none). Parentheses nest, and a quoted string inside may hold a `)`."""
    n, depth = len(code), 1
    while i < n:
        c = code[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            k = code.find("'", i + 1)
            i = n if k < 0 else k + 1
            continue
        if c == '"':
            i = _skip_dq(code, i + 1)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _mask(code):
    """(code with quoted spans emptied, code carried inside quotes). A quoted
    span is data, so a separator or `git push` inside it is not a command; what
    does run is `$(...)` or a backtick body inside double quotes, and the argument
    of sh -c / bash -c / eval. Those bodies are returned for a second pass, which
    reads them as code in their own right (so a quote inside `$(...)` inside
    double quotes is matched by its own partner, not by the outer one).
    An unterminated quote is treated as quoted to the end: that errs towards
    reporting a step as read-only, which a reviewer sees, rather than hiding it."""
    out, nested, i, n = [], [], 0, len(code)
    while i < n:
        ch = code[i]
        if ch == "\\" and i + 1 < n:
            out.append(code[i:i + 2])
            i += 2
            continue
        if ch not in "'\"":
            out.append(ch)
            i += 1
            continue
        j, body = i + 1, []
        while j < n and code[j] != ch:
            c = code[j]
            if c == "\\" and ch == '"' and j + 1 < n:
                body.append(code[j:j + 2])
                j += 2
            elif ch == '"' and code.startswith("$(", j):
                k = _subst_end(code, j + 2)
                nested.append(code[j + 2:k])
                j = k + 1
            elif ch == '"' and c == "`":
                k = j + 1
                while k < n and code[k] != "`":
                    k += 2 if code[k] == "\\" else 1
                nested.append(code[j + 1:k])
                j = k + 1
            else:
                body.append(c)
                j += 1
        if RUNS_ARG.search("".join(out)):
            nested.append("".join(body))
        out.append(ch + ch)
        i = j + 1
    return "".join(out), nested


def pushes(src):
    """Whether the script text runs `git push`. Comment lines do not count,
    backslash-newline continuations are joined first, and quoted text is data
    (see _mask). Known limits: a heredoc body is read as code, so a push written
    inside one counts as a push; shell variables and functions are not expanded."""
    code = "\n".join(line for line in src.replace("\\\n", " ").split("\n")
                     if not line.lstrip().startswith("#"))
    masked, nested = _mask(code)
    return bool(GIT_PUSH.search(masked)) or any(pushes(x) for x in nested)


def read_only_holders(docs):
    """(file, template, container) of every step that can read the key (volume,
    projected source, env secretKeyRef or envFrom) and never runs git push.
    Workflow-family documents only: templates and CronWorkflow workflowSpec."""
    found = set()
    for fname, doc in docs:
        for tpls, spec_vols in W.workflow_templates(doc):
            for t in tpls:
                vols = spec_vols + (t.get("volumes") or [])
                c = t.get("script") or t.get("container")
                pairs = [("main", c)] if c else []
                pairs += [(i.get("name", ""), i) for i in t.get("initContainers") or []]
                pairs += [(i.get("name", ""), i) for i in t.get("sidecars") or []]
                for name, cont in pairs:
                    holds = KEY in W.container_secret_refs(cont, vols, (KEY,))
                    src = cont.get("source") or " ".join(
                        [str(x) for x in (cont.get("command") or []) + (cont.get("args") or [])])
                    if holds and not pushes(src):
                        found.add((fname, t["name"], name))
    return found


try:
    DOCS = [(p.name, d) for p in W.yaml_files(TPL) for d in W.load_docs(p)]
except W.ReadError as e:
    DOCS = []
    check("the workflow templates could be read", False, e)
check("the workflow templates were found", len(DOCS) > 0)
if DOCS:
    found = read_only_holders(DOCS)
    check("no read-only step holds the key beyond the known list", found <= KNOWN_READ_ONLY, found - KNOWN_READ_ONLY)
    check("the known list has no step that lost the key", KNOWN_READ_ONLY <= found, KNOWN_READ_ONLY - found)

    docs_by_file = dict(DOCS)
    for fname, tname in (("tpl-validate-tenant.yaml", "validate"), ("tpl-validate-tenant.yaml", "image-name"),
                         ("wft-preview-deploy.yaml", "deploy")):
        doc = docs_by_file.get(fname)
        tpls = [x for x in (doc or {}).get("spec", {}).get("templates", []) if x.get("name") == tname]
        check(f"{fname} {tname}: the template was found", len(tpls) == 1, fname)
        if len(tpls) != 1:
            continue
        t = tpls[0]
        text = yaml.safe_dump(t)
        check(f"{fname} {tname}: no key anywhere in the step", KEY not in text and "deploy-key" not in text)
        check(f"{fname} {tname}: no ssh setup", ".ssh" not in text and "git@github.com" not in text)
        check(f"{fname} {tname}: clones over anonymous https",
              'git clone --depth=1 "https://github.com/${GITOPS_ORG}/${GITOPS_REPO}.git"' in t["script"]["source"])

# Proven both ways: the sweep flags a read-only step with the key, and not a writer.
sample = {"spec": {"templates": [
    {"name": "reader", "volumes": [{"name": "k", "secret": {"secretName": KEY}}],
     "script": {"source": "git clone x", "volumeMounts": [{"name": "k", "mountPath": "/k"}]}},
    {"name": "writer", "volumes": [{"name": "k", "secret": {"secretName": KEY}}],
     "script": {"source": "git push", "volumeMounts": [{"name": "k", "mountPath": "/k"}]}},
    {"name": "plain", "script": {"source": "git clone x"}},
    {"name": "commented", "volumes": [{"name": "k", "secret": {"secretName": KEY}}],
     "script": {"source": "# git push\ngit clone x", "volumeMounts": [{"name": "k", "mountPath": "/k"}]}},
    {"name": "side", "volumes": [{"name": "k", "secret": {"secretName": KEY}}],
     "sidecars": [{"name": "s", "args": ["sleep"], "volumeMounts": [{"name": "k", "mountPath": "/k"}]}]},
]}}
check("the sweep flags the read-only holders and not the writer", read_only_holders([("x.yaml", sample)]) == {
    ("x.yaml", "reader", "main"), ("x.yaml", "commented", "main"), ("x.yaml", "side", "s")})

# Other reference forms (#1033): references other than a volume mount, and pushes
# that are not the literal text "git push". Each case is a step that holds the
# key; the read-only ones must be reported, the writers must not.
KREF = {"valueFrom": {"secretKeyRef": {"name": KEY, "key": "ssh-privatekey"}}}
VOLK = [{"name": "k", "secret": {"secretName": KEY}}]
MNT = [{"name": "k", "mountPath": "/k"}]


def step(name, **c):
    return {"name": name, "volumes": VOLK, "script": dict({"volumeMounts": MNT}, **c)}


other_forms = {"spec": {"templates": [
    {"name": "env-reader", "script": {"source": "git clone x", "env": [dict({"name": "K"}, **KREF)]}},
    {"name": "envfrom-reader", "container": {"args": ["sleep"], "envFrom": [{"secretRef": {"name": KEY}}]}},
    {"name": "proj-reader", "volumes": [{"name": "p", "projected": {"sources": [{"secret": {"name": KEY}}]}}],
     "script": {"source": "git clone x", "volumeMounts": [{"name": "p", "mountPath": "/p"}]}},
    {"name": "init-env-reader", "script": {"source": "git push"}, "initContainers": [
        {"name": "i", "args": ["git", "clone"], "env": [dict({"name": "K"}, **KREF)]}]},
    step("echo-reader", source='echo "git push later"\ngit clone x'),
    {"name": "env-writer", "script": {"source": "git push", "env": [dict({"name": "K"}, **KREF)]}},
    step("c-writer", source="git -C /work push origin HEAD:main"),
    step("spaced-writer", source="git   push"),
    step("if-writer", source="if ! git push origin HEAD:main; then exit 1; fi"),
    step("env-prefix-writer", source="GIT_SSH_COMMAND=ssh git push"),
    step("continued-writer", source="git \\\n  push origin x"),
    {"name": "argv-writer", "volumes": VOLK, "container": {"command": ["git", "-C", "/w", "push"], "volumeMounts": MNT}},
]}}
cron = {"spec": {"workflowSpec": {"volumes": VOLK, "templates": [
    {"name": "cron-reader", "script": {"source": "git clone x", "volumeMounts": MNT}}]}}}
got = read_only_holders([("b.yaml", other_forms), ("c.yaml", cron)])
check("read-only steps: env, envFrom, projected, init env, echo, cron workflowSpec readers are reported",
      got == {("b.yaml", "env-reader", "main"), ("b.yaml", "envfrom-reader", "main"),
              ("b.yaml", "proj-reader", "main"), ("b.yaml", "init-env-reader", "i"),
              ("b.yaml", "echo-reader", "main"), ("c.yaml", "cron-reader", "main")}, got)
check("writer steps: -C, extra spaces, if !, env prefix, continuation and argv pushes are writers",
      not any(n.endswith("writer") for _, n, _ in got), got)

# Quoted text is data (#1033 review): a separator or keyword inside quotes is not a
# command boundary, while code that really runs from inside quotes still counts.
for src, want in (
        ('echo "done; git push next"', False),
        ('echo "then git push"', False),
        ("echo 'a; git push'", False),
        ('echo "a | git push"', False),
        ('echo "a && git push"', False),
        ("echo 'it'\"'\"'s; git push'", False),
        ('git commit -m "msg" && git push', True),
        ('git -C "my dir" push', True),
        ("git -c 'k=v w' push", True),
        ('echo "x"; git push', True),
        ('echo "$(git push)"', True),
        ('echo "`git push`"', True),
        ('echo "$(echo \\"a\\"; git push)"', True),
        ('bash -c "git push"', True),
        ("sh -c 'git push origin HEAD'", True),
        ('bash -lc "git push"', True),
        ('eval "git push"', True),
        ('echo "unterminated; git push', False),
        ('echo \\"; git push', True),
        ('echo "a" "b"; git push', True),
        ('echo "$(echo hi)"', False),
        ("git clone 'x;git push'", False),
        # quotes nested inside $(...) or backticks inside double quotes pair with each other
        ('echo "$(echo "a; git push")"', False),
        ('echo "$(echo "then git push")"', False),
        ('echo "$(echo "x"; git push)"', True),
        ('echo "$(echo "$(echo "a; git push")")"', False),
        ('echo "$(echo "$(git push)")"', True),
        ('echo "$(echo "a)"; git push)"', True),
        ('echo "$(echo "a)")"; git push', True),
        ('echo "$(echo "a)")" "b; git push"', False),
        ('echo "$(echo "x $(echo ")") y")"; git push', True),
        ('echo "$(echo "x $(echo ")") y; git push")"', False),
        ('echo "`echo "a; git push"`"', False),
        ('echo "`echo a; git push`"', True),
        ('x="$(git log --format="%s; git push")"', False),
        ('x="$(git log --format="%s")" && git push', True),
        ("echo \"$(echo 'a; git push')\"", False),
        ("echo \"$(echo 'a)'; git push)\"", True),
        ('echo "$(echo "unterminated; git push', False)):
    check(f"pushes({src!r}) is {want}", pushes(src) is want, pushes(src))
# Where the quote scanner errs: a quote it cannot pair (an unterminated one) is read as quoted
# to the end of the script, so a `git push` after it is NOT seen and the step is reported
# as read-only. That direction is deliberate (a reviewer looks at a step listed as read-only,
# whereas a step wrongly taken for a writer would leave the ratchet silently); a heredoc body
# is the opposite case and is read as code, so a push written inside one counts as a push.
check("an unpaired quote hides what follows it, so the step is reported as read-only (documented direction)",
      pushes('echo "oops\ngit push') is False)
check("a heredoc body is read as code (documented direction)", pushes("cat <<EOF\ngit push\nEOF") is True)
qs = {"spec": {"templates": [
    step("quoted-sep-reader", source='echo "a; git push"'),
    step("quoted-keyword-reader", source='echo "then git push"'),
    step("subst-writer", source='echo "$(git push)"'),
    step("sh-c-writer", source="bash -c 'git push'"),
    step("nested-quote-reader", source='echo "$(echo "a; git push")"'),
    step("nested-quote-writer", source='echo "$(echo "a"; git push)"')]}}
got = read_only_holders([("q.yaml", qs)])
check("steps that only quote a push are read-only holders, steps that run one are writers",
      got == {("q.yaml", "quoted-sep-reader", "main"), ("q.yaml", "quoted-keyword-reader", "main"),
              ("q.yaml", "nested-quote-reader", "main")}, got)

# A template directory that cannot be loaded is one recorded failure, not a crash in the
# lookups that follow. The case runs this file against a copy of the tests with an
# unparsable template; the child skips this case (RR_CHILD) to avoid recursing.
if not os.environ.get("RR_CHILD"):
    with tempfile.TemporaryDirectory() as td:
        tree = pathlib.Path(td)
        shutil.copytree(ROOT / "tests", tree / "tests", ignore=shutil.ignore_patterns("__pycache__", "fixtures"))
        tpl = tree / "platform-gitops/argo-workflows/cluster-templates"
        tpl.mkdir(parents=True)
        (tpl / "bad.yaml").write_text("kind: [unclosed\n")
        proc = subprocess.run([sys.executable, str(tree / "tests" / pathlib.Path(__file__).name)],
                              capture_output=True, text=True, env=dict(os.environ, RR_CHILD="1"))
        check("unloadable templates fail the run with one recorded failure and no traceback",
              proc.returncode == 1 and "Traceback" not in proc.stderr
              and "FAIL  the workflow templates could be read" in proc.stdout, (proc.returncode, proc.stderr[-300:]))

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
