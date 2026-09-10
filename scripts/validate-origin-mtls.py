#!/usr/bin/env python3
"""Fail when the rendered bootstrap chart stops enforcing Authenticated Origin Pulls.

Traefik refuses any TLS handshake that does not present this account's
Cloudflare client certificate. That is what closes the gap
`infrastructure/cloudflare/README.md` records under "another Cloudflare
customer": the origin IP allowlist trusts *all* of Cloudflare, so someone could
point their own zone at this origin and arrive from a legitimate Cloudflare
address. An IP allowlist cannot tell one Cloudflare customer from another; a
client certificate can (#1153, #1172, #1173).

The whole enforcement is two objects in one file. Delete either and the origin
silently goes back to accepting any Cloudflare address:

  * TLSOption/default in the traefik namespace -- named `default`, so Traefik
    applies it to every router that does not name another one. Remove it and
    Traefik stops asking for a certificate at all.
  * ExternalSecret traefik-origin-pull-ca -- the CA the option verifies
    against. Its key must be `tls.ca`; Traefik ignores any other key in
    clientAuth.secretNames SILENTLY, which leaves clientAuth configured and
    verifying nothing. That was measured against a live probe, not read from
    docs.

Nothing fails loudly in either case. The cluster keeps serving traffic, every
probe stays green, and the only observable difference is that a check which
used to happen no longer does -- the same shape as the VMPodScrape that sat
unnoticed in vm-rules/ for three months (#1159), and the same reason this
exists.

Checks the RENDERED chart rather than the source file, because that is what
reaches the cluster: a values change, a template guard or an accidental
`{{- if }}` could drop the objects while leaving the YAML looking right.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops/bootstrap"
VALUES = CHART / "values.yaml"

NAMESPACE = "traefik"
SECRET = "traefik-origin-pull-ca"
CA_KEY = "tls.ca"
AUTH_TYPE = "RequireAndVerifyClientCert"


def render(chart: Path, values: Path) -> list[dict]:
    """helm template the chart, returning every non-empty document."""
    out = subprocess.run(
        ["helm", "template", "guard", str(chart), "-f", str(values)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"helm template failed:\n{out.stderr.strip()}")
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def problems(docs: list[dict]) -> list[str]:
    """Everything wrong with the origin-mTLS objects in a rendered chart."""
    found = []

    options = [
        d
        for d in docs
        if d.get("kind") == "TLSOption"
        and d.get("metadata", {}).get("name") == "default"
        and d.get("metadata", {}).get("namespace") == NAMESPACE
    ]
    if not options:
        found.append(
            f"no TLSOption/default in namespace {NAMESPACE}: Traefik would not ask "
            "for a client certificate at all, and the origin would accept any "
            "Cloudflare address"
        )
    else:
        # A second one is not merely untidy: whichever loses the race decides
        # whether the origin is enforcing, and the file gives no clue which.
        if len(options) > 1:
            found.append(f"{len(options)} TLSOption/default objects in {NAMESPACE}; expected exactly one")
        auth = options[0].get("spec", {}).get("clientAuth") or {}
        got_type = auth.get("clientAuthType")
        if got_type != AUTH_TYPE:
            found.append(
                f"TLSOption/default clientAuthType is {got_type!r}, expected {AUTH_TYPE!r} "
                "(VerifyClientCertIfGiven lets a client presenting nothing through, "
                "which is exactly the traffic this refuses)"
            )
        names = auth.get("secretNames") or []
        if SECRET not in names:
            found.append(
                f"TLSOption/default does not reference the {SECRET} secret (secretNames={names!r})"
            )

    secrets = [
        d
        for d in docs
        if d.get("kind") == "ExternalSecret"
        and d.get("metadata", {}).get("name") == SECRET
        and d.get("metadata", {}).get("namespace") == NAMESPACE
    ]
    if not secrets:
        found.append(
            f"no ExternalSecret/{SECRET} in namespace {NAMESPACE}: the TLSOption would "
            "reference a secret nothing creates"
        )
    else:
        keys = [e.get("secretKey") for e in (secrets[0].get("spec", {}).get("data") or [])]
        if CA_KEY not in keys:
            found.append(
                f"ExternalSecret/{SECRET} does not produce the {CA_KEY!r} key (keys={keys!r}); "
                "Traefik ignores any other key silently and would verify nothing"
            )

    return found


def _fixture(root: Path, tls_option: str, external_secret: str) -> tuple[Path, Path]:
    """A one-template chart standing in for bootstrap, for the self-test."""
    chart = root / "chart"
    (chart / "templates").mkdir(parents=True)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: guard-fixture\nversion: 0.0.0\n")
    (chart / "values.yaml").write_text("{}\n")
    (chart / "templates" / "objects.yaml").write_text(f"{external_secret}---\n{tls_option}")
    return chart, chart / "values.yaml"


GOOD_OPTION = f"""apiVersion: traefik.io/v1alpha1
kind: TLSOption
metadata:
  name: default
  namespace: {NAMESPACE}
spec:
  clientAuth:
    secretNames:
      - {SECRET}
    clientAuthType: {AUTH_TYPE}
"""

GOOD_SECRET = f"""apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {SECRET}
  namespace: {NAMESPACE}
spec:
  data:
    - secretKey: {CA_KEY}
      remoteRef:
        key: platform/traefik/origin-pull
        property: ca.crt
"""


def selftest() -> int:
    """Prove the detector fires on each way the enforcement can be lost."""
    cases = [
        ("intact", GOOD_OPTION, GOOD_SECRET, 0),
        ("TLSOption deleted", "", GOOD_SECRET, 1),
        ("ExternalSecret deleted", GOOD_OPTION, "", 1),
        (
            "clientAuthType weakened to VerifyClientCertIfGiven",
            GOOD_OPTION.replace(AUTH_TYPE, "VerifyClientCertIfGiven"),
            GOOD_SECRET,
            1,
        ),
        (
            "TLSOption points at another secret",
            GOOD_OPTION.replace(f"- {SECRET}", "- some-other-ca"),
            GOOD_SECRET,
            1,
        ),
        (
            "CA published under ca.crt instead of tls.ca",
            GOOD_OPTION,
            GOOD_SECRET.replace(f"secretKey: {CA_KEY}", "secretKey: ca.crt"),
            1,
        ),
        (
            "TLSOption moved out of the traefik namespace",
            GOOD_OPTION.replace(f"namespace: {NAMESPACE}", "namespace: default"),
            GOOD_SECRET,
            1,
        ),
    ]

    failures = 0
    for name, option, secret, expected in cases:
        with tempfile.TemporaryDirectory() as d:
            chart, values = _fixture(Path(d), option, secret)
            got = 1 if problems(render(chart, values)) else 0
        if got != expected:
            verb = "missed" if expected else "false-positived on"
            print(f"self-test FAILED: {verb} {name!r}", file=sys.stderr)
            failures += 1

    if failures:
        return 1
    print(f"validate-origin-mtls.py self-test: {len(cases)} cases, detector fires on each way enforcement is lost")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()

    if not CHART.is_dir():
        print(f"::error::{CHART} not found -- refusing to pass vacuously", file=sys.stderr)
        return 2

    found = problems(render(CHART, VALUES))
    if found:
        print(
            "::error::the rendered chart no longer enforces Authenticated Origin Pulls; "
            "the origin would accept any Cloudflare address (see #1153 and the "
            '"another Cloudflare customer" section of infrastructure/cloudflare/README.md)',
            file=sys.stderr,
        )
        for problem in found:
            print(f"::error::{problem}", file=sys.stderr)
        return 1

    print("OK: rendered chart enforces client certificates at the origin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
