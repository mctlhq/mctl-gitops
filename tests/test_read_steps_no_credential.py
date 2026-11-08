"""Steps that only read mctl-gitops hold no write credential (mctlhq/mctl-agents#1007).

A ratchet: every template step that mounts the deploy key must push, or be listed
in KNOWN_READ_ONLY as work still to do. A new read-only step with the key fails
here, and so does a listed one that no longer has it, so the list can only shrink.
"""
import pathlib
import re
import sys

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


def pushes(src):
    """Whether the script text runs `git push`. Comment lines do not count and
    backslash-newline continuations are joined first."""
    code = "\n".join(line for line in src.replace("\\\n", " ").split("\n")
                     if not line.lstrip().startswith("#"))
    return bool(GIT_PUSH.search(code))


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
    DOCS = [(p.name, d) for p in sorted(TPL.glob("*.yaml")) for d in W.load_docs(p)]
except W.ReadError as e:
    DOCS = []
    check("the workflow templates could be read", False, e)
check("the workflow templates were found", len(DOCS) > 0)
found = read_only_holders(DOCS)
check("no read-only step holds the key beyond the known list", found <= KNOWN_READ_ONLY, found - KNOWN_READ_ONLY)
check("the known list has no step that lost the key", KNOWN_READ_ONLY <= found, KNOWN_READ_ONLY - found)

for fname, tname in (("tpl-validate-tenant.yaml", "validate"), ("tpl-validate-tenant.yaml", "image-name"),
                     ("wft-preview-deploy.yaml", "deploy")):
    doc = dict(DOCS)[fname]
    t = [x for x in doc["spec"]["templates"] if x["name"] == tname][0]
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

# Blind spots closed (#1033): references other than a volume mount, and pushes
# that are not the literal text "git push". Each case is a step that holds the
# key; the read-only ones must be reported, the writers must not.
KREF = {"valueFrom": {"secretKeyRef": {"name": KEY, "key": "ssh-privatekey"}}}
VOLK = [{"name": "k", "secret": {"secretName": KEY}}]
MNT = [{"name": "k", "mountPath": "/k"}]


def step(name, **c):
    return {"name": name, "volumes": VOLK, "script": dict({"volumeMounts": MNT}, **c)}


blind = {"spec": {"templates": [
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
got = read_only_holders([("b.yaml", blind), ("c.yaml", cron)])
check("blind spots: env, envFrom, projected, init env, echo, cron workflowSpec readers are reported",
      got == {("b.yaml", "env-reader", "main"), ("b.yaml", "envfrom-reader", "main"),
              ("b.yaml", "proj-reader", "main"), ("b.yaml", "init-env-reader", "i"),
              ("b.yaml", "echo-reader", "main"), ("c.yaml", "cron-reader", "main")}, got)
check("blind spots: -C, extra spaces, if !, env prefix, continuation and argv pushes are writers",
      not any(n.endswith("writer") for _, n, _ in got), got)

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
