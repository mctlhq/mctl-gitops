#!/usr/bin/env python3
"""Fail when the rendered bootstrap chart stops enforcing Authenticated Origin Pulls.

Traefik refuses any TLS handshake that does not present this account's
Cloudflare client certificate. That is what closes the gap
`infrastructure/cloudflare/README.md` records under "another Cloudflare
customer": the origin IP allowlist trusts *all* of Cloudflare, so someone could
point their own zone at this origin and arrive from a legitimate Cloudflare
address. An IP allowlist cannot tell one Cloudflare customer from another; a
client certificate can (#1153, #1172, #1173).

The whole enforcement is two objects in one file, and there are more ways to
lose it than to delete it:

  * TLSOption/default in the traefik namespace -- named `default`, so Traefik
    applies it to every router that does not name another one. Remove it and
    Traefik stops asking for a certificate at all; weaken clientAuthType to
    VerifyClientCertIfGiven and a client presenting nothing is let through,
    which is exactly the traffic this refuses.
  * The CA it verifies against, delivered by an ExternalSecret. It must publish
    the key as `tls.ca`; Traefik ignores any other key in clientAuth.secretNames
    SILENTLY, which leaves clientAuth configured and verifying nothing. That was
    measured against a live probe, not read from docs.

Nothing fails loudly in any of those cases. The cluster keeps serving traffic,
every probe stays green, and the only observable difference is that a check
which used to happen no longer does -- the same shape as the VMPodScrape that
sat unnoticed in vm-rules/ for three months (#1159), and the same reason this
exists.

Checks the RENDERED chart rather than the source file, because that is what
reaches the cluster: a values change, a template guard or an accidental
`{{- if }}` could drop the objects while leaving the YAML looking right.

On CodeQL, because this file has tripped it twice and will again. Kubernetes
spells the fields `secretNames` and `secretKey`, so the queries
py/clear-text-logging-sensitive-data and py/clear-text-storage-sensitive-data
treat anything read through them as credentials. Nothing here is: the script
parses `helm template` output and compares object NAMES
(`traefik-origin-pull-ca`) and key NAMES (`tls.ca`). No key material is read,
written or printed anywhere in it.

Two of those alerts were raised and handled differently on purpose. The storage
one was removed at the cause — the self-test no longer writes a fixture chart to
disk, which it never needed. The logging one was dismissed in code scanning as a
false positive (alert #4), because the values it objects to are exactly what an
operator reading a red CI run needs to see: which CA the TLSOption actually
ended up naming. Suppressing that would make the failure message useless.

Earlier revisions also called CA_SECRET_NAME `SECRET` and `ca_sources`
`secrets`, which tripped the same queries on the identifier alone. Do not rename
them back.

Run with --selftest to prove the detector still detects.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops/bootstrap"
VALUES = CHART / "values.yaml"

NAMESPACE = "traefik"
CA_SECRET_NAME = "traefik-origin-pull-ca"
CA_KEY = "tls.ca"
AUTH_TYPE = "RequireAndVerifyClientCert"
VAULT_PATH = "platform/traefik/origin-pull"
VAULT_PROPERTY = "ca.crt"


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
    elif len(options) > 1:
        # Not merely untidy: whichever wins decides whether the origin enforces,
        # and the manifests give no clue which.
        found.append(f"{len(options)} TLSOption/default objects in {NAMESPACE}; expected exactly one")
    else:
        auth = options[0].get("spec", {}).get("clientAuth") or {}
        got_type = auth.get("clientAuthType")
        if got_type != AUTH_TYPE:
            found.append(
                f"TLSOption/default clientAuthType is {got_type!r}, expected {AUTH_TYPE!r} "
                "(VerifyClientCertIfGiven lets a client presenting nothing through, "
                "which is exactly the traffic this refuses)"
            )
        names = auth.get("secretNames") or []
        # Exactly this one, not merely "contains it". Traefik pools every CA
        # named here into one trust store, so an extra entry means an extra CA
        # that can mint client certificates this origin will accept.
        if names != [CA_SECRET_NAME]:
            found.append(
                f"TLSOption/default secretNames is {names!r}, expected exactly [{CA_SECRET_NAME!r}] "
                "(Traefik trusts every CA listed, so an extra entry widens what the "
                "origin accepts)"
            )

    ca_sources = [
        d
        for d in docs
        if d.get("kind") == "ExternalSecret"
        and d.get("metadata", {}).get("name") == CA_SECRET_NAME
        and d.get("metadata", {}).get("namespace") == NAMESPACE
    ]
    if not ca_sources:
        found.append(
            f"no ExternalSecret/{CA_SECRET_NAME} in namespace {NAMESPACE}: the TLSOption "
            "would reference a secret nothing creates"
        )
    elif len(ca_sources) > 1:
        # Duplicates are last-wins at apply time, so checking only the first
        # would let a second one redefine the CA without this noticing.
        found.append(
            f"{len(ca_sources)} ExternalSecret/{CA_SECRET_NAME} objects in {NAMESPACE}; "
            "expected exactly one (a later duplicate silently overrides the first)"
        )
    else:
        spec = ca_sources[0].get("spec") or {}

        # metadata.name is not what Traefik looks up -- target.name is the
        # Secret ESO actually creates. If they diverge, Traefik finds nothing,
        # the TLSOption cannot be built, and the origin quietly stops
        # enforcing. Absent means "same as the ExternalSecret", which is fine.
        target = (spec.get("target") or {}).get("name", CA_SECRET_NAME)
        if target != CA_SECRET_NAME:
            found.append(
                f"ExternalSecret/{CA_SECRET_NAME} creates a Secret named {target!r}; "
                f"the TLSOption looks up {CA_SECRET_NAME!r} and would find nothing"
            )

        entries = spec.get("data") or []
        matching = [e for e in entries if e.get("secretKey") == CA_KEY]
        if not matching:
            published = [e.get("secretKey") for e in entries]
            found.append(
                f"ExternalSecret/{CA_SECRET_NAME} does not produce the {CA_KEY!r} key "
                f"(produces {published!r}); Traefik ignores any other key silently and "
                "would verify nothing"
            )
        elif len(matching) > 1:
            # Same last-wins hazard as duplicate objects, one level down: ESO
            # walks the list in order, so a second entry for the same key
            # decides what the CA actually is.
            found.append(
                f"ExternalSecret/{CA_SECRET_NAME} defines {CA_KEY!r} {len(matching)} times; "
                "expected exactly one (a later entry overrides the earlier)"
            )
        else:
            # Where the CA comes from matters as much as what it is called: the
            # same key name sourced from somewhere else is a different CA.
            ref = matching[0].get("remoteRef") or {}
            if (ref.get("key"), ref.get("property")) != (VAULT_PATH, VAULT_PROPERTY):
                found.append(
                    f"ExternalSecret/{CA_SECRET_NAME} sources {CA_KEY!r} from "
                    f"{ref.get('key')!r}/{ref.get('property')!r}, expected "
                    f"{VAULT_PATH!r}/{VAULT_PROPERTY!r}"
                )

    # A hand-written Secret of the same name in the same chart fights ESO for
    # ownership: whichever wrote last decides which CA Traefik trusts, and it
    # flaps. The CA has exactly one source, and it is Vault.
    literal = [
        d
        for d in docs
        if d.get("kind") == "Secret"
        and d.get("metadata", {}).get("name") == CA_SECRET_NAME
        and d.get("metadata", {}).get("namespace") == NAMESPACE
    ]
    if literal:
        found.append(
            f"the chart also renders a plain Secret/{CA_SECRET_NAME} in {NAMESPACE}; "
            "it would race the ExternalSecret for ownership and could replace the CA"
        )

    return found


GOOD_OPTION = f"""apiVersion: traefik.io/v1alpha1
kind: TLSOption
metadata:
  name: default
  namespace: {NAMESPACE}
spec:
  clientAuth:
    secretNames:
      - {CA_SECRET_NAME}
    clientAuthType: {AUTH_TYPE}
"""

GOOD_CA_SOURCE = f"""apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {CA_SECRET_NAME}
  namespace: {NAMESPACE}
spec:
  data:
    - secretKey: {CA_KEY}
      remoteRef:
        key: {VAULT_PATH}
        property: {VAULT_PROPERTY}
"""


DUPLICATE_CA_ENTRY = f"""    - secretKey: {CA_KEY}
      remoteRef:
        key: platform/somewhere-else
        property: {VAULT_PROPERTY}
"""

LITERAL_SECRET = f"""---
apiVersion: v1
kind: Secret
metadata:
  name: {CA_SECRET_NAME}
  namespace: {NAMESPACE}
"""


def selftest() -> int:
    """Prove the detector fires on each way the enforcement can be lost.

    Feeds parsed documents straight to problems() rather than rendering a
    fixture chart through helm. What is under test is the predicate, not helm;
    the render path is exercised by the real run, which follows this one in CI.
    It is also what keeps this file free of a temp-file write whose contents
    CodeQL reads as sensitive because Kubernetes spells its fields secretKey
    and secretNames.
    """
    cases = [
        ("intact", GOOD_OPTION, GOOD_CA_SOURCE, 0),
        ("TLSOption deleted", "", GOOD_CA_SOURCE, 1),
        ("CA ExternalSecret deleted", GOOD_OPTION, "", 1),
        (
            "clientAuthType weakened to VerifyClientCertIfGiven",
            GOOD_OPTION.replace(AUTH_TYPE, "VerifyClientCertIfGiven"),
            GOOD_CA_SOURCE,
            1,
        ),
        (
            "TLSOption points at another CA instead",
            GOOD_OPTION.replace(f"- {CA_SECRET_NAME}", "- some-other-ca"),
            GOOD_CA_SOURCE,
            1,
        ),
        (
            "a second CA appended to secretNames",
            GOOD_OPTION.replace(f"- {CA_SECRET_NAME}", f"- {CA_SECRET_NAME}\n      - some-other-ca"),
            GOOD_CA_SOURCE,
            1,
        ),
        (
            "CA published under ca.crt instead of tls.ca",
            GOOD_OPTION,
            GOOD_CA_SOURCE.replace(f"secretKey: {CA_KEY}", "secretKey: ca.crt"),
            1,
        ),
        (
            "CA sourced from a different Vault path",
            GOOD_OPTION,
            GOOD_CA_SOURCE.replace(VAULT_PATH, "platform/somewhere-else"),
            1,
        ),
        (
            "duplicate TLSOption/default",
            GOOD_OPTION + "---\n" + GOOD_OPTION,
            GOOD_CA_SOURCE,
            1,
        ),
        (
            "duplicate CA ExternalSecret, the second one wrong",
            GOOD_OPTION,
            GOOD_CA_SOURCE + "---\n" + GOOD_CA_SOURCE.replace(f"secretKey: {CA_KEY}", "secretKey: ca.crt"),
            1,
        ),
        (
            "TLSOption moved out of the traefik namespace",
            GOOD_OPTION.replace(f"namespace: {NAMESPACE}", "namespace: default"),
            GOOD_CA_SOURCE,
            1,
        ),
        (
            "ExternalSecret creates a Secret under a different name",
            GOOD_OPTION,
            GOOD_CA_SOURCE.replace("  data:", "  target:\n    name: something-else\n  data:"),
            1,
        ),
        (
            "tls.ca defined twice, the second sourced from elsewhere",
            GOOD_OPTION,
            GOOD_CA_SOURCE + DUPLICATE_CA_ENTRY,
            1,
        ),
        (
            "a plain Secret claims the same name",
            GOOD_OPTION,
            GOOD_CA_SOURCE + LITERAL_SECRET,
            1,
        ),
    ]

    failures = 0
    for name, option, ca_source, expected in cases:
        docs = [d for d in yaml.safe_load_all(f"{ca_source}---\n{option}") if d]
        got = 1 if problems(docs) else 0
        if got != expected:
            verb = "missed" if expected else "false-positived on"
            print(f"self-test FAILED: {verb} {name!r}", file=sys.stderr)
            failures += 1

    if failures:
        return 1
    print(
        f"validate-origin-mtls.py self-test: {len(cases)} cases, "
        "detector fires on each way enforcement is lost"
    )
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
