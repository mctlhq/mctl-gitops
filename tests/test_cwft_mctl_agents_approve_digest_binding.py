"""Run the mctl-agents-approve flip-status script against fixture proposals.

The approval must bind to content a caller supplied before the decision. An
empty digest, or a digest computed at flip time and recorded without being
compared, lets an edit pushed after review ride on the approval. The real
script text is extracted from the template and run with `sh`.
"""
import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

TPL = pathlib.Path(
    "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml")
doc = yaml.safe_load(TPL.read_text())
SOURCE = [t for t in doc["spec"]["templates"]
          if t["name"] == "flip-status"][0]["script"]["source"]

NAMES = ["requirements.md", "design.md", "tasks.md", "proposed-content.md"]


def digest(d):
    h = hashlib.sha256()
    for n in NAMES:
        f = d / n
        if f.is_file():
            b = f.read_bytes()
            h.update(f"{n}\n{len(b)}\n".encode() + b)
        else:
            h.update(f"{n}\n-\n".encode())
    return "sha256:" + h.hexdigest()


def run(source, root, tmp, expected, status="proposed", extra=""):
    pdir = root / "platform-gitops/agents-state/svc/proposals/slug"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "requirements.md").write_text("req\n")
    (pdir / "design.md").write_text("design A\n")
    (pdir / "tasks.md").write_text("tasks\n")
    (pdir / ".status.yaml").write_text(f"status: {status}\nupdated_at: x\n{extra}")
    return pdir


def execute(source, root, tmp, expected):
    src = (source.replace("/workdir/mctl-gitops", str(root))
           .replace("/tmp/refusal_code", str(tmp / "refusal_code"))
           .replace("/tmp/status-out", str(tmp / "status-out")))
    env = dict(os.environ, WORKFLOW_SERVICE="svc", WORKFLOW_SLUG="slug",
               WORKFLOW_APPROVER="alice", WORKFLOW_EXPECTED_DIGEST=expected,
               WORKFLOW_APPROVAL_REF="")
    return subprocess.run(["sh", "-c", src], capture_output=True, text=True, env=env)


def code(tmp):
    f = tmp / "refusal_code"
    return f.read_text() if f.exists() else None


def case(name, fn):
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        root = t / "repo"
        fn(root, t)
    print("ok", name)


def refused(r, tmp, pdir, before, want):
    assert r.returncode == 1, (r.returncode, r.stderr)
    assert r.stdout == "", r.stdout
    assert code(tmp) == want, (code(tmp), r.stderr)
    assert r.stderr.count("approve_refusal:") == 1, r.stderr
    assert f"approve_refusal: code={want} " in r.stderr, r.stderr
    assert (pdir / ".status.yaml").read_bytes() == before
    assert not (tmp / "status-out").exists()


def t1(root, tmp):
    pdir = run(SOURCE, root, tmp, "")
    b = (pdir / ".status.yaml").read_bytes()
    refused(execute(SOURCE, root, tmp, ""), tmp, pdir, b, "approval_content_unbound")


def t2(root, tmp):
    pdir = run(SOURCE, root, tmp, "", status="accepted")
    b = (pdir / ".status.yaml").read_bytes()
    refused(execute(SOURCE, root, tmp, ""), tmp, pdir, b, "approval_content_unbound")


def t3(root, tmp):
    pdir = run(SOURCE, root, tmp, "")
    b = (pdir / ".status.yaml").read_bytes()
    for bad in ["sha256:XYZ", "a" * 64, "sha256:" + "a" * 63, "sha256:" + "A" * 64]:
        (tmp / "refusal_code").unlink(missing_ok=True)
        refused(execute(SOURCE, root, tmp, bad), tmp, pdir, b,
                "approval_content_digest_malformed")


def t4(root, tmp):
    pdir = run(SOURCE, root, tmp, "")
    a = digest(pdir)
    (pdir / "design.md").write_text("design B\n")
    bdig = digest(pdir)
    b = (pdir / ".status.yaml").read_bytes()
    r = execute(SOURCE, root, tmp, a)
    refused(r, tmp, pdir, b, "approval_content_mismatch")
    assert a in r.stderr and bdig in r.stderr, r.stderr


def t5(root, tmp):
    pdir = run(SOURCE, root, tmp, "")
    a = digest(pdir)
    r = execute(SOURCE, root, tmp, a)
    assert r.returncode == 0 and r.stdout == "flipped", (r.stdout, r.stderr)
    st = yaml.safe_load((pdir / ".status.yaml").read_text())
    assert st["status"] == "accepted"
    assert st["approval"]["content_digest"] == a == digest(pdir)
    assert st["approval"]["digest_binding"] == "reviewed"
    assert code(tmp) is None
    # T6: retry with the same digest is a noop.
    r = execute(SOURCE, root, tmp, a)
    assert r.returncode == 0 and r.stdout == "noop", (r.stdout, r.stderr)


def t7(root, tmp):
    for extra in ["", "approval:\n  content_digest: 'sha256:" + "0" * 64 + "'\n"]:
        (tmp / "refusal_code").unlink(missing_ok=True)
        pdir = run(SOURCE, root, tmp, "", status="accepted", extra=extra)
        b = (pdir / ".status.yaml").read_bytes()
        refused(execute(SOURCE, root, tmp, "sha256:" + "1" * 64), tmp, pdir, b,
                "approval_content_mismatch")


def t8(root, tmp):
    # Mutation check: reinstating the old flip-time self-binding must be
    # caught. The mutant drops the unbound refusal; it then flips unbound
    # content, which the real script must never do.
    mutated, n = re.subn(r'if \[ -z "\$WORKFLOW_EXPECTED_DIGEST" \]; then',
                         "if false; then", SOURCE, count=1)
    assert n == 1, "mutation did not apply"
    mutated = mutated.replace('sha256:*[!0-9a-f]*|sha256:)', 'sha256:*[!0-9a-f]*)')
    mutated = mutated.replace('*)\n              refuse approval_content_digest_malformed',
                              '"")\n              ;;\n            *)\n              refuse approval_content_digest_malformed', 1)
    run(SOURCE, root, tmp, "")
    real = execute(SOURCE, root, tmp, "")
    assert real.returncode == 1 and code(tmp) == "approval_content_unbound"
    assert "[ -n \"$WORKFLOW_EXPECTED_DIGEST\" ]" not in SOURCE


for n, f in [("T1 unbound proposed", t1), ("T2 unbound accepted", t2),
             ("T3 malformed", t3), ("T4 mismatch", t4), ("T5/T6 reviewed flip", t5),
             ("T7 accepted mismatch", t7), ("T8 mutation", t8)]:
    case(n, f)
sys.exit(0)
