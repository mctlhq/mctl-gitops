"""Steps that only read mctl-gitops hold no write credential (mctlhq/mctl-agents#1007).

A ratchet: every template step that mounts the deploy key must push, or be listed
in KNOWN_READ_ONLY as work still to do. A new read-only step with the key fails
here, and so does a listed one that no longer has it, so the list can only shrink.
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TPL = ROOT / "platform-gitops/argo-workflows/cluster-templates"
KEY = "mctl-gitops-deploy-key"
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {str(detail)[:400]}")


# Central mctl-agents templates and platform workflows: init containers that clone
# before the step that pushes. Remaining phases; none runs in a tenant namespace.
KNOWN_READ_ONLY = {
    ("cwft-mctl-agents-approve.yaml", "flip-status", "clone-gitops"),
    ("cwft-mctl-agents-approve.yaml", "commit-and-push", "clone-gitops"),
    ("cwft-mctl-agents-implement.yaml", "run-implementer", "clone-gitops"),
    ("cwft-mctl-agents-implement.yaml", "commit-and-push", "clone-gitops"),
    ("cwft-mctl-agents-investigate.yaml", "run-investigator", "clone-gitops"),
    ("cwft-mctl-agents-investigate.yaml", "commit-and-push", "clone-gitops"),
    ("cwft-mctl-agents-reconcile.yaml", "run-reconcile", "clone-gitops"),
    ("cwft-mctl-agents-reconcile.yaml", "commit-and-push", "clone-gitops"),
    ("wft-delete-tenant-safe.yaml", "retire-tenant-services", "main"),
    ("wft-lifecycle-bootstrap.yaml", "bootstrap", "clone-gitops"),
}


def key_volumes(t):
    return {v["name"] for v in t.get("volumes") or [] if (v.get("secret") or {}).get("secretName") == KEY}


def read_only_holders(docs):
    found = set()
    for fname, doc in docs:
        tops = {v["name"] for v in (doc.get("spec") or {}).get("volumes") or []
                if (v.get("secret") or {}).get("secretName") == KEY}
        for t in (doc.get("spec") or {}).get("templates") or []:
            vols = tops | key_volumes(t)
            c = t.get("script") or t.get("container")
            pairs = [("main", c)] if c else []
            pairs += [(i.get("name", ""), i) for i in t.get("initContainers") or []]
            pairs += [(i.get("name", ""), i) for i in t.get("sidecars") or []]
            for name, cont in pairs:
                mounted = any(m["name"] in vols for m in cont.get("volumeMounts") or [])
                src = cont.get("source") or " ".join(cont.get("args") or []) + " ".join(cont.get("command") or [])
                # A comment naming git push does not make a step a writer.
                code = "\n".join(line for line in src.split("\n") if not line.lstrip().startswith("#"))
                if mounted and "git push" not in code:
                    found.add((fname, t["name"], name))
    return found


DOCS = [(p.name, d) for p in sorted(TPL.glob("*.yaml")) for d in yaml.safe_load_all(p.read_text()) if d]
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

# Run and shepherd templates: every clone-gitops init container clones over
# anonymous https with no key, and the step that pushes points origin at ssh
# itself before its first fetch or push.
def init_clones(doc):
    out = []
    for t in doc["spec"]["templates"]:
        for i in t.get("initContainers") or []:
            if i.get("name") == "clone-gitops":
                out.append((t["name"], i))
    return out


def clone_is_anonymous(i):
    text = "\n".join(i.get("args") or []) + "\n" + " ".join(m["name"] + m["mountPath"] for m in i.get("volumeMounts") or [])
    return (KEY not in text and "deploy-key" not in text and ".ssh" not in text
            and "git@github.com" not in text and "id_ed25519" not in text
            and 'git clone --depth=1 "https://github.com/mctlhq/mctl-gitops.git"' in text)


def push_step_sets_ssh_remote(t):
    src = t["script"]["source"]
    code = "\n".join(line for line in src.split("\n") if not line.lstrip().startswith("#"))
    remote = code.find("git remote set-url origin git@github.com:mctlhq/mctl-gitops.git")
    first_net = min(x for x in (code.find("git push"), code.find("git pull")) if x >= 0)
    return remote >= 0 and remote < first_net


for fname, n_clones, pusher in (("cwft-mctl-agents-run.yaml", 3, "commit-and-push"),
                                ("cwft-mctl-agents-shepherd.yaml", 2, "commit-and-push")):
    doc = dict(DOCS)[fname]
    clones = init_clones(doc)
    check(f"{fname}: {n_clones} clone-gitops init containers found", len(clones) == n_clones, len(clones))
    for tname, i in clones:
        check(f"{fname} {tname}: clone-gitops is anonymous https without any key", clone_is_anonymous(i))
    t = [x for x in doc["spec"]["templates"] if x["name"] == pusher][0]
    check(f"{fname} {pusher}: sets the ssh remote before its first fetch or push",
          push_step_sets_ssh_remote(t))

# Proven both ways on the new check: a clone with the key or ssh url is rejected.
good = {"name": "clone-gitops", "args": ['git clone --depth=1 "https://github.com/mctlhq/mctl-gitops.git" /w']}
bad_ssh = {"name": "clone-gitops", "args": ["git clone --depth=1 git@github.com:mctlhq/mctl-gitops.git /w"]}
bad_key = dict(good, volumeMounts=[{"name": "deploy-key", "mountPath": "/secrets/deploy-key"}])
check("the anonymous-clone check accepts https and rejects ssh or a key mount",
      clone_is_anonymous(good) and not clone_is_anonymous(bad_ssh) and not clone_is_anonymous(bad_key))
check("the remote-order check rejects a push step that sets the remote late or never",
      push_step_sets_ssh_remote({"script": {"source": "git remote set-url origin git@github.com:mctlhq/mctl-gitops.git\ngit push"}})
      and not push_step_sets_ssh_remote({"script": {"source": "git push\ngit remote set-url origin git@github.com:mctlhq/mctl-gitops.git"}})
      and not push_step_sets_ssh_remote({"script": {"source": "git push"}})
      and not push_step_sets_ssh_remote({"script": {"source": "# git remote set-url origin git@github.com:mctlhq/mctl-gitops.git\ngit push"}}))

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

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all checks passed")
