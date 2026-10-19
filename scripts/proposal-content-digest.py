#!/usr/bin/env python3
"""Print the content digest of a proposal directory, for mctl-agents-approve.

Usage:
  proposal-content-digest.py <proposal-dir>
  proposal-content-digest.py --rev <commit> <proposal-dir>
  proposal-content-digest.py --selftest

Pass the output as `expected_content_digest` so the approval binds to the
bytes you reviewed. Framing matches the mctl-agents-approve CWFT and mctl-agents
`proposal_state.proposal_content_digest`: per file, in order,
"<name>\\n<len>\\n<bytes>" for a present file and "<name>\\n-\\n" for an absent
one; then SHA-256.
"""
import hashlib
import pathlib
import re
import subprocess
import sys
import tempfile

NAMES = ["requirements.md", "design.md", "tasks.md", "proposed-content.md"]
CWFT = pathlib.Path(__file__).resolve().parent.parent / (
    "platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml")


def digest(read):
    """read(name) -> bytes or None."""
    h = hashlib.sha256()
    for name in NAMES:
        data = read(name)
        if data is None:
            h.update(f"{name}\n-\n".encode())
        else:
            h.update(f"{name}\n{len(data)}\n".encode())
            h.update(data)
    return "sha256:" + h.hexdigest()


def from_dir(d):
    d = pathlib.Path(d)
    if not d.is_dir():
        sys.exit(f"error: not a directory: {d}")
    return digest(lambda n: (d / n).read_bytes() if (d / n).is_file() else None)


def from_rev(rev, d):
    d = d.rstrip("/")
    for args in (["rev-parse", "--verify", f"{rev}^{{commit}}"],
                 ["cat-file", "-e", f"{rev}:{d}"]):
        r = subprocess.run(["git", *args], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"error: git {' '.join(args)} failed: {r.stderr.strip()}")

    def read(n):
        r = subprocess.run(["git", "show", f"{rev}:{d}/{n}"], capture_output=True)
        return r.stdout if r.returncode == 0 else None
    return digest(read)


def selftest():
    import yaml
    doc = yaml.safe_load(CWFT.read_text())
    src = [t for t in doc["spec"]["templates"]
           if t["name"] == "flip-status"][0]["script"]["source"]
    m = re.search(r"^ *PROPOSAL_DIR=.*?^ *CONTENT_DIGEST=[^\n]*$", src, re.S | re.M)
    assert m, "could not extract the digest loop from the CWFT"
    with tempfile.TemporaryDirectory() as t:
        p = pathlib.Path(t)
        (p / "requirements.md").write_bytes(b"req\n")
        (p / "design.md").write_bytes(b"")
        (p / "tasks.md").write_bytes("täsk\n".encode())  # proposed-content.md absent
        script = (f'set -e\nSTATUS_FILE="{t}/.status.yaml"\n{m.group(0)}\n'
                  'printf "%s" "$CONTENT_DIGEST"\n')
        out = subprocess.run(["sh", "-c", script], capture_output=True,
                             text=True, check=True).stdout
        got = from_dir(p)
        assert out == got, f"CWFT {out} != helper {got}"
    print("ok")


def main(argv):
    if argv == ["--selftest"]:
        return selftest()
    if len(argv) == 1 and not argv[0].startswith("-"):
        print(from_dir(argv[0]))
    elif len(argv) == 3 and argv[0] == "--rev":
        print(from_rev(argv[1], argv[2]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
