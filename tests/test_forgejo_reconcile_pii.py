"""The Forgejo reconciler must not print users' personal data.

platform-gitops/infra-components/data/forgejo/reconcile.yaml carries main.tf
in a ConfigMap. svalabs/forgejo marks only `password` sensitive on
forgejo_user, so `email` and `full_name` appear in clear in every plan that
creates or changes a user: in the Job log, and from there in Loki. They must
be wrapped in sensitive() in main.tf itself.

T1. The forgejo_user "this" block exists in main.tf (the read is not vacuous).
T2. Its `email` and `full_name` arguments are sensitive(...) expressions.

No pytest, matching the plain `python3 tests/<file>.py` convention.

Run: python3 tests/test_forgejo_reconcile_pii.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RECONCILE = ROOT / "platform-gitops" / "infra-components" / "data" / "forgejo" / "reconcile.yaml"

failures: list[str] = []

docs = [d for d in yaml.safe_load_all(RECONCILE.read_text()) if d]
main_tf = next((d["data"]["main.tf"] for d in docs
                if d.get("kind") == "ConfigMap" and "main.tf" in d.get("data", {})), None)
if main_tf is None:
    print(f"FAIL: no ConfigMap with main.tf in {RECONCILE}", file=sys.stderr)
    sys.exit(1)

m = re.search(r'^resource "forgejo_user" "this" \{\n(.*?)^\}', main_tf, re.S | re.M)
if not m:
    print('FAIL: resource "forgejo_user" "this" not found in main.tf', file=sys.stderr)
    sys.exit(1)
block = m.group(1)

for attr in ("email", "full_name"):
    a = re.search(rf"^  {attr}\s*=\s*(.+)$", block, re.M)
    if not a:
        failures.append(f"forgejo_user.this has no {attr} argument")
    elif not a.group(1).strip().startswith("sensitive("):
        failures.append(f"forgejo_user.this {attr} is not wrapped in sensitive(): {a.group(1).strip()}")

if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("forgejo reconcile: user e-mail and full name are sensitive in the plan")
