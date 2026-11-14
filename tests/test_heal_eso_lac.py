#!/usr/bin/env python3
"""scripts/heal-eso-lac.sh must not report a scan it could not run as clean.

gitops bug report ch. 2: the scan read its rows from a process substitution
`< <(kubectl ... | jq ...)`, whose exit status set -e and pipefail never see.
A kubectl that could not reach the cluster produced no rows, and the script
printed "scanned: 0 ... already-clean: 0" and exited 0. A jq that could not
parse kubectl's answer did the same, and an annotation that was not JSON was
counted as already-clean through `fromjson? // {}`.

Each case runs the real script and the real jq against a fake kubectl on
PATH. Nothing here touches a cluster: the fake answers from a fixture and
records every call, and the cases check it was never asked to annotate
anything they did not expect.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "heal-eso-lac.sh"
LAC = "kubectl.kubernetes.io/last-applied-configuration"

FAKE_KUBECTL = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_DIR/calls"
if [[ "$1" == "get" ]]; then
  if [[ -f "$FAKE_DIR/get.rc" ]]; then
    echo "The connection to the server was refused" >&2
    exit "$(cat "$FAKE_DIR/get.rc")"
  fi
  cat "$FAKE_DIR/get.out"
  exit 0
fi
exit 0
"""


def es(ns: str, name: str, lac: str | None) -> dict:
    meta: dict = {"namespace": ns, "name": name}
    if lac is not None:
        meta["annotations"] = {LAC: lac}
    return {"metadata": meta}


STALE = json.dumps({"apiVersion": "external-secrets.io/v1",
                    "metadata": {"resourceVersion": "42"}})
FRESH = json.dumps({"apiVersion": "external-secrets.io/v1beta1", "metadata": {}})


def run(get_out: str | None, get_rc: int | None = None, *args: str):
    d = Path(tempfile.mkdtemp())
    try:
        (d / "kubectl").write_text(FAKE_KUBECTL)
        (d / "kubectl").chmod((d / "kubectl").stat().st_mode | stat.S_IXUSR)
        if get_out is not None:
            (d / "get.out").write_text(get_out)
        if get_rc is not None:
            (d / "get.rc").write_text(str(get_rc))
        env = dict(os.environ, FAKE_DIR=str(d), KUBECONFIG="/nonexistent",
                   PATH=f"{d}:{os.environ['PATH']}")
        p = subprocess.run(["bash", str(SCRIPT), *args], env=env,
                           capture_output=True, text=True)
        calls = (d / "calls").read_text().splitlines() if (d / "calls").exists() else []
        return p.returncode, p.stdout, p.stderr, calls
    finally:
        shutil.rmtree(d)


def items(*objs: dict) -> str:
    return json.dumps({"items": list(objs)})


def main() -> int:
    if shutil.which("jq") is None:
        print("FAIL jq is not installed; this test needs the real jq")
        return 1
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"\n     {detail}"))
        if not ok:
            failures.append(name)

    # Could-not-observe: no summary, exit 2.
    for name, out, rc in [
        ("kubectl cannot reach the cluster", None, 1),
        ("kubectl answers with something that is not JSON", "<html>502</html>", None),
        ("kubectl answers with an object without .items", "{}", None),
        ("kubectl answers with an empty body", "", None),
    ]:
        code, stdout, stderr, calls = run(out, rc)
        check(f"{name}: exit 2", code == 2, f"exit {code}")
        check(f"{name}: no clean summary", "already-clean" not in stdout, stdout)
        check(f"{name}: nothing annotated",
              not any(c.startswith("-n ") for c in calls), str(calls))

    # An annotation that is not JSON is unread, not clean.
    code, stdout, _, _ = run(items(es("a", "broken", "{not json"), es("a", "ok", FRESH)))
    check("an unparseable annotation: exit 2", code == 2, f"exit {code}")
    check("an unparseable annotation: counted as unreadable",
          "unreadable:    1" in stdout and "already-clean: 1" in stdout, stdout)

    # Observed: the real answers still work.
    code, stdout, _, _ = run(items())
    check("an empty cluster: exit 0", code == 0, f"exit {code}")
    check("an empty cluster: scanned 0", "scanned:       0" in stdout, stdout)

    fixture = items(es("a", "stale", STALE), es("b", "fresh", FRESH), es("c", "none", None))
    code, stdout, _, calls = run(fixture)
    check("dry-run: exit 0", code == 0, f"exit {code}")
    check("dry-run: one candidate of three",
          "scanned:       3" in stdout and "candidates:    1" in stdout
          and "already-clean: 2" in stdout, stdout)
    check("dry-run: nothing annotated",
          not any(c.startswith("-n ") for c in calls), str(calls))

    code, stdout, _, calls = run(fixture, None, "--apply")
    annotated = [c for c in calls if c.startswith("-n ")]
    check("apply: exit 0", code == 0, f"exit {code}")
    check("apply: only the stale object is annotated",
          len(annotated) == 1 and annotated[0].startswith("-n a annotate externalsecret stale "),
          str(annotated))

    if failures:
        print(f"\n{len(failures)} failing")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
