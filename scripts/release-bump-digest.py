#!/usr/bin/env python3
"""Pin the image digest next to a freshly bumped tag (mctlhq/mctl-gitops#2652).

Runs after the tag-bump step of release-deploy.yaml and gitops-bump.yaml, on
exactly the files that step rewrote (its changed-files handoff). For every
services values block of the form

    repository: <image>
    tag: "<new tag>"

it writes `digest: "<sha256:...>"` on the line directly under `tag:`, at the
same indentation, replacing a digest that is already there. That is the only
shape scripts/release-bump-diff-guard.py accepts for a digest, and the
base-service chart renders `repository:tag@digest` from it.

With no digest given, a block that already pins one is refused: moving the tag
while the old digest stays would keep deploying the old image under the new
tag's name. The guard refuses that diff too; this step says why earlier.

Files outside platform-gitops/services/ (CWFT inline images, bootstrap
templates) are left alone: they carry no digest field yet.

Exit codes: 0 done, 2 bad arguments, 8 a pinned digest with none given,
9 a block this script cannot edit safely.
"""
import argparse
import os
import re
import sys

SERVICES_PREFIX = "platform-gitops/services/"
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
INDENT_RE = re.compile(r"[ \t]*")


def indent(line):
    return INDENT_RE.match(line).group(0)


def fail(code, msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def pin(text, path, image, tag, digest):
    """Return (new text, number of blocks pinned). Exits on a refusal."""
    lines = text.split("\n")
    repo_re = re.compile(r"(^|\s)repository:\s*" + re.escape(image) + r"$")
    out = list(lines)
    inserts = []  # (index to insert at, line)
    pinned = 0
    for i, line in enumerate(lines):
        if not repo_re.search(line) or i + 1 >= len(lines):
            continue
        tag_line = lines[i + 1]
        ind = indent(tag_line)
        m = re.fullmatch(re.escape(ind) + r"tag:\s*([\"']?)(?P<tag>[^\"'\s]*)\1\s*", tag_line)
        if not ind or not m:
            continue
        if m.group("tag") != tag:
            fail(9, f"{path}:{i + 2}: tag of {image} is {m.group('tag')!r}, expected the bumped {tag!r}")
        # Every sibling key of the image block, above and below, so a digest
        # that sits elsewhere in the block is found rather than duplicated.
        siblings = []
        j = i
        while j >= 0 and lines[j].strip() and len(indent(lines[j])) >= len(ind):
            siblings.append(j)
            j -= 1
        j = i + 2
        while j < len(lines) and lines[j].strip() and len(indent(lines[j])) >= len(ind):
            siblings.append(j)
            j += 1
        found = [k for k in siblings if re.match(re.escape(ind) + r"digest:", lines[k])]
        if len(found) > 1:
            fail(9, f"{path}: the {image} block has more than one digest key")
        if found and found[0] != i + 2:
            fail(9, f"{path}:{found[0] + 1}: the {image} digest is not directly under its tag")
        if not digest:
            if found:
                fail(8, f"{path}:{found[0] + 1}: {image} pins a digest and this bump carries none; "
                        "refusing to move the tag under the old digest")
            continue
        new_line = f'{ind}digest: "{digest}"'
        if found:
            out[i + 2] = new_line
        else:
            inserts.append((i + 2, new_line))
        pinned += 1
    for at, new_line in reversed(inserts):
        out.insert(at, new_line)
    return "\n".join(out), pinned


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--image", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--digest", default="")
    ap.add_argument("--changed-files", required=True,
                    help="the bump step's handoff file: one rewritten path per line")
    a = ap.parse_args(argv)

    digest = a.digest.strip()
    if digest and not DIGEST_RE.fullmatch(digest):
        fail(2, f"refusing digest {digest!r}: not sha256:<64 lowercase hex>")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}", a.tag):
        fail(2, f"refusing tag {a.tag!r}: not a valid image tag")
    # release-deploy's image_name shape (gitops-bump narrows it to ghcr.io/mctlhq).
    if not re.fullmatch(r"[a-z0-9.-]+(:[0-9]+)?(/[a-z0-9._-]+)+", a.image):
        fail(2, f"refusing image {a.image!r}: not an image name")

    try:
        with open(a.changed_files) as fp:
            files = [p.strip() for p in fp if p.strip()]
    except OSError as e:
        fail(2, f"cannot read the changed-files handoff {a.changed_files}: {e}")

    total = 0
    for path in files:
        norm = os.path.normpath(path)
        if os.path.isabs(path) or ".." in path.split("/"):
            fail(2, f"refusing path {path!r}: must be relative, without '..'")
        if not norm.startswith(SERVICES_PREFIX):
            continue
        if os.path.realpath(path) != os.path.join(os.path.realpath(os.curdir), norm):
            fail(2, f"refusing path {path!r}: goes through a symlink")
        with open(path) as fp:
            text = fp.read()
        new, n = pin(text, path, a.image, a.tag, digest)
        if new != text:
            with open(path, "w") as fp:
                fp.write(new)
        if n:
            print(f"  {path}: pinned {n} block(s) to {digest}")
        total += n
    if digest and not total:
        print(f"::notice::{a.image}@{digest} built, but no rewritten services values block takes a digest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
