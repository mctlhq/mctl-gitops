#!/usr/bin/env python3
"""Move a service's image back to an earlier tag AND its digest, together.

    rollback-image-ref.py --values platform-gitops/services/<team>/<svc>/values.yaml \
        --tag <earlier tag> [--digest sha256:<64 hex>]

Run from the root of a git clone with enough history (see wft-rollback-service).

Why: since mctl-gitops#2652 a services values file can pin `digest:` directly
under `tag:`, and the base-service chart then renders `repository:tag@digest`,
so the digest wins and the tag is only a label. A rollback that rewrites the
tag alone leaves the NEW image running under the OLD tag's name, and the
workflow still reports success.

What it does, for the one `repository:` / `tag:` block of the file:
  * --digest given: that digest is used, unless the file's own history shows
    the tag bound to other digests only (a mismatch is refused). With no
    history for the tag it is taken on trust, and the output says so.
  * no --digest: the digest the tag had in the file's history (same
    repository only) is restored with it. A tag bound to two different digests
    is refused unless --digest names one of them.
  * any history that cannot be fully observed (log, tree, blob fetch, a log
    as long as the limit) is a refusal, never a shorter history.
  * the file pins a digest now and none can be found for the target: refused.
    Moving the tag under the old digest would be a silent no-op.
  * the file pins no digest now and none is known: the tag alone moves, as it
    always did.
Tag and digest are written in one edit, and the result is re-read before it
replaces the file.

Exit codes: 0 done (or already there), 2 bad arguments or path, 8 a digest
cannot be established for the target tag, 9 the file or its history cannot be
edited or read safely. None of them leaves a half-written file.
"""
import argparse
import os
import re
import subprocess
import sys

SERVICES_PREFIX = "platform-gitops/services/"
TAG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
INDENT_RE = re.compile(r"[ \t]*")


def fail(code, msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def indent(line):
    return INDENT_RE.match(line).group(0)


class Unreadable(Exception):
    pass


def read_block(text, label):
    """Return the one image block of a values file as a dict, or raise Unreadable."""
    lines = text.split("\n")
    found = []
    for i, line in enumerate(lines):
        if not re.search(r"(^|\s)repository:\s*\S+\s*$", line) or i + 1 >= len(lines):
            continue
        ind = indent(lines[i + 1])
        m = re.fullmatch(re.escape(ind) + r"tag:\s*(?P<q>[\"']?)(?P<tag>[^\"'\s]*)(?P=q)\s*", lines[i + 1])
        if not ind or not m:
            continue
        found.append((i, ind, m))
    if len(found) != 1:
        raise Unreadable(f"{label}: expected exactly one repository/tag block, found {len(found)}")
    i, ind, m = found[0]
    # Every sibling key of the block, above and below, so a digest that sits
    # anywhere in it is found rather than duplicated.
    siblings = []
    j = i
    while j >= 0 and lines[j].strip() and len(indent(lines[j])) >= len(ind):
        siblings.append(j)
        j -= 1
    j = i + 2
    while j < len(lines) and lines[j].strip() and len(indent(lines[j])) >= len(ind):
        siblings.append(j)
        j += 1
    digests = [k for k in siblings if re.match(re.escape(ind) + r"digest:", lines[k])]
    if len(digests) > 1:
        raise Unreadable(f"{label}: the block has more than one digest key")
    digest = None
    if digests:
        if digests[0] != i + 2:
            raise Unreadable(f"{label}: the digest is not directly under tag")
        dm = re.fullmatch(re.escape(ind) + r"digest:\s*([\"']?)(?P<d>sha256:[0-9a-f]{64})\1\s*", lines[i + 2])
        if not dm:
            raise Unreadable(f"{label}: the digest line is not a sha256:<64 hex> value")
        digest = dm.group("d")
    rm = re.search(r"repository:\s*(\S+)\s*$", lines[i])
    return {"repository": rm.group(1).strip("\"'"), "lines": lines, "tag_at": i + 1, "indent": ind, "quote": m.group("q"),
            "tag": m.group("tag"), "digest": digest, "digest_at": (i + 2) if digests else None}


def rewrite(block, tag, digest):
    """Return the new text with tag and digest set; digest None keeps no digest line."""
    lines = list(block["lines"])
    ind, q = block["indent"], block["quote"]
    lines[block["tag_at"]] = f"{ind}tag: {q}{tag}{q}"
    if digest:
        line = f'{ind}digest: "{digest}"'
        if block["digest_at"] is not None:
            lines[block["digest_at"]] = line
        else:
            lines.insert(block["tag_at"] + 1, line)
    elif block["digest_at"] is not None:
        del lines[block["digest_at"]]
    return "\n".join(lines)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


HISTORY_LIMIT = 2000
FETCH_CHUNK = 100


def history(path, tag, repository, limit):
    """Digests the tag was bound to, for this repository, in the file's history.

    Returns a set (None member = a tag-only entry). Raises Unreadable on ANY
    failure to observe: an unreadable log, a tree or blob that cannot be read
    or fetched, a log as long as the limit (the tail would be unseen). A
    commit where the file is absent is told apart from a failed read by
    `git ls-tree`: rc 0 and empty output is absence, anything else is an error.
    """
    r = git("log", "-n", str(limit), "--format=%H", "--", path)
    if r.returncode != 0:
        raise Unreadable(f"cannot read the history of {path}: {r.stderr.strip()[:200]}")
    shas = r.stdout.split()
    if not shas:
        raise Unreadable(f"no history for {path}: a shallow clone cannot answer which digest a tag had")
    if len(shas) >= limit:
        raise Unreadable(f"history of {path} is {len(shas)} commits, the limit: the older part is unseen")
    oids = {}
    for sha in shas:
        t = git("ls-tree", sha, "--", path)
        if t.returncode != 0:
            raise Unreadable(f"cannot read {path} at {sha[:10]}: {t.stderr.strip()[:200]}")
        if not t.stdout.strip():
            continue  # the file is absent at this commit
        meta, _, _name = t.stdout.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or parts[1] != "blob":
            raise Unreadable(f"{path} at {sha[:10]} is not a regular file")
        oids[sha] = parts[2]
    # A blobless clone holds trees only: fetch the blobs explicitly, in batches,
    # and treat any failure as unreadable rather than as a missing commit.
    need = sorted(set(oids.values()))
    for k in range(0, len(need), FETCH_CHUNK):
        chunk = need[k:k + FETCH_CHUNK]
        have = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
                              input="\n".join(chunk) + "\n", capture_output=True, text=True)
        missing = [c for c in chunk if f"{c} blob" not in have.stdout.split("\n")]
        if missing:
            f = git("fetch", "--quiet", "--no-tags", "--filter=blob:none", "origin", *missing)
            if f.returncode != 0:
                raise Unreadable(f"cannot fetch {len(missing)} historical blobs of {path}: {f.stderr.strip()[:200]}")
    seen = set()
    for sha, oid in oids.items():
        show = git("cat-file", "blob", oid)
        if show.returncode != 0:
            raise Unreadable(f"cannot read blob {oid[:10]} of {path} at {sha[:10]}: {show.stderr.strip()[:200]}")
        try:
            b = read_block(show.stdout, f"{path}@{sha[:10]}")
        except Unreadable:
            continue  # an older shape of the file; it cannot tell us anything
        if b["repository"] == repository and b["tag"] == tag:
            seen.add(b["digest"])
    return seen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--values", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--digest", default="")
    ap.add_argument("--history-limit", type=int, default=HISTORY_LIMIT)
    a = ap.parse_args(argv)

    digest = a.digest.strip()
    if not TAG_RE.fullmatch(a.tag):
        fail(2, f"refusing tag {a.tag!r}: not a valid image tag")
    if digest and not DIGEST_RE.fullmatch(digest):
        fail(2, f"refusing digest {digest!r}: not sha256:<64 lowercase hex>")
    path = a.values
    norm = os.path.normpath(path)
    if os.path.isabs(path) or ".." in path.split("/") or not norm.startswith(SERVICES_PREFIX):
        fail(2, f"refusing path {path!r}: must be a relative path under {SERVICES_PREFIX}")
    if os.path.realpath(path) != os.path.join(os.path.realpath(os.curdir), norm):
        fail(2, f"refusing path {path!r}: goes through a symlink")

    try:
        with open(path) as fp:
            text = fp.read()
        cur = read_block(text, path)
    except (OSError, Unreadable) as e:
        fail(9, str(e))

    # Which digest does the target tag carry?
    source = "none"
    target = None
    try:
        known = history(path, a.tag, cur["repository"], a.history_limit)
    except Unreadable as e:
        known = None
        hist_err = str(e)
    pinned_known = sorted(d for d in (known or set()) if d)
    if len(pinned_known) > 1 and digest not in pinned_known:
        fail(8, f"{path}: tag {a.tag} was bound to more than one digest in history "
                f"({', '.join(pinned_known)}); pass target_digest equal to the one that is right")
    if digest and known is None:
        fail(8, f"{path}: --digest {digest} cannot be checked against history ({hist_err}); "
                "refusing to write a digest that was not verified")
    if digest:
        if pinned_known and digest not in pinned_known:
            fail(8, f"{path}: --digest {digest} does not match {pinned_known[0]}, the digest tag {a.tag} "
                    "had in history; refusing a tag and digest that disagree")
        target, source = digest, "argument"
    elif pinned_known:
        target, source = pinned_known[0], "history"
    elif cur["digest"]:
        why = ("its history shows the tag without a digest" if known else
               "the tag does not appear in its history" if known is not None else hist_err)
        fail(8, f"{path}: pins digest {cur['digest']} and no digest is known for tag {a.tag} ({why}); "
                "rolling the tag back alone would keep running the current image. "
                "Pass the target digest explicitly (target_digest).")
    elif known is None:
        # Nothing is pinned now, so a tag-only edit is still exact; history was
        # only needed to find a digest that does not exist to restore.
        source = "none"

    new = rewrite(cur, a.tag, target)
    try:
        chk = read_block(new, path)
    except Unreadable as e:
        fail(9, f"the edit would leave an unreadable file: {e}")
    if chk["tag"] != a.tag or chk["digest"] != target:
        fail(9, f"{path}: the edit did not produce tag {a.tag} and digest {target}")
    if new == text:
        print(f"{path}: already at {a.tag}" + (f"@{target}" if target else ""))
        return 0
    tmp = path + ".rollback.tmp"
    with open(tmp, "w") as fp:
        fp.write(new)
    os.replace(tmp, path)
    note = " NOT checked against history or registry" if source == "argument" and not pinned_known else ""
    print(f"{path}: tag {cur['tag']} -> {a.tag}; digest "
          f"{cur['digest'] or 'none'} -> {target or 'none'} (source: {source}{note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
