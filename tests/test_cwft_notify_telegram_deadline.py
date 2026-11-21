"""Every agents CWFT notify-telegram template must carry a deadline (#568).

notify-telegram runs as the onExit handler. Without activeDeadlineSeconds a
hung Telegram call (or an egress-proxy wait that never ends) pins the whole
workflow Running. The test walks every cwft-mctl-agents-*.yaml, requires at
least the seven known templates to be found, and fails on any notify-telegram
template with a missing or non-positive deadline above 600s.
"""
import pathlib
import sys

import yaml

DIR = pathlib.Path("platform-gitops/argo-workflows/cluster-templates")
EXPECTED = {"implement", "run", "shepherd", "reconcile", "scout",
            "investigate", "usage-collector"}
MAX_DEADLINE = 600

found, bad = set(), []
for path in sorted(DIR.glob("cwft-mctl-agents-*.yaml")):
    for doc in yaml.safe_load_all(path.read_text()):
        for t in ((doc or {}).get("spec") or {}).get("templates") or []:
            if t.get("name") != "notify-telegram":
                continue
            found.add(path.stem.removeprefix("cwft-mctl-agents-"))
            d = t.get("activeDeadlineSeconds")
            if not isinstance(d, int) or isinstance(d, bool) or not 0 < d <= MAX_DEADLINE:
                bad.append(f"{path.name}: activeDeadlineSeconds={d!r}")

missing = EXPECTED - found
if missing:
    bad.append(f"notify-telegram not found in: {sorted(missing)}")
if bad:
    print("FAIL\n" + "\n".join(bad))
    sys.exit(1)
print(f"ok   {len(found)} notify-telegram templates carry a deadline <= {MAX_DEADLINE}s")
