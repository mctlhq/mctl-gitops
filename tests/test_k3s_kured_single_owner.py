"""k3s-preview kured: the user manifest must win and follow kube.tf (#2036).

kube-hetzner bundles its own kured DaemonSet without resources and re-applies
it whenever terraform_data.kustomization is replaced. The real DaemonSet lives
in infrastructure/k3s-preview/extra-manifests/kured.yaml.tpl, and the module
re-applies a user manifest only when its rendered content changes. The #2035
apply replaced the base layer and kured silently lost its requests and limits.

K1. The module arguments that feed the base kustomization triggers read from
    `local.<same name>`, so a bump has exactly one place to go.
K2. base_kustomization_inputs hashes every one of those locals, so a change
    to any of them changes the rendered kured manifest.
K3. extra_kustomize_parameters passes base_kustomization_inputs and
    kured_version into the user templates.
K4. kured.yaml.tpl renders the hash as an annotation and the image tag from
    kured_version, with no other placeholder. Rendering with a different
    value for either changes the output, and the rendered DaemonSet keeps
    its resources.

No pytest, matching the plain `python3 tests/<file>.py` convention.

Run: python3 tests/test_k3s_kured_single_owner.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
K3S = ROOT / "infrastructure/k3s-preview"
KUBE_TF = K3S / "kube.tf"
KURED_TPL = K3S / "extra-manifests/kured.yaml.tpl"

TRACKED = [
    "install_k3s_version",
    "hetzner_ccm_version",
    "hetzner_csi_version",
    "kured_version",
    "hetzner_ccm_merge_values",
]

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def block(src: str, header_re: str) -> str:
    """Return the brace-balanced body that follows a header like `locals {`."""
    m = re.search(header_re, src, re.M)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1 : j]
    return ""


def render(tpl: str, params: dict[str, str]) -> str:
    """templatefile() for the subset kured.yaml.tpl uses: ${name} only."""
    names = set(re.findall(r"\$\{([^}]*)\}", tpl))
    missing = names - params.keys()
    if missing:
        raise KeyError(f"template uses parameters nobody passes: {sorted(missing)}")
    return re.sub(r"\$\{([^}]*)\}", lambda m: params[m.group(1)], tpl)


def main() -> int:
    tf = KUBE_TF.read_text()
    module = block(tf, r'^module "kube-hetzner" \{')
    check(bool(module), "kube.tf: module \"kube-hetzner\" block not found")
    locals_bodies = [block(tf[m.start():], r"^locals \{") for m in re.finditer(r"^locals \{", tf, re.M)]
    locals_src = "\n".join(locals_bodies)

    # K1 (top-level module arguments only, not keys inside nested maps)
    params_body = block(module, r"^\s*extra_kustomize_parameters\s*=\s*\{")
    top_level = module.replace(params_body, "") if params_body else module
    for name in TRACKED:
        args = re.findall(rf"^\s*{name}\s*=\s*(.+)$", top_level, re.M)
        check(args == [f"local.{name}"], f"K1: module argument {name} must be exactly `local.{name}`, got {args}")
        check(re.search(rf"^\s*{name}\s*=", locals_src, re.M) is not None, f"K1: local.{name} is not defined")

    # K2
    hash_body = re.search(r"base_kustomization_inputs\s*=\s*sha1\(jsonencode\(\[(.*?)\]\)\)", locals_src, re.S)
    check(hash_body is not None, "K2: base_kustomization_inputs = sha1(jsonencode([...])) not found")
    if hash_body:
        hashed = set(re.findall(r"local\.(\w+)", hash_body.group(1)))
        for name in TRACKED:
            check(name in hashed, f"K2: base_kustomization_inputs does not hash local.{name}")

    # K3
    for name in ("base_kustomization_inputs", "kured_version"):
        check(
            re.search(rf"^\s*{name}\s*=\s*local\.{name}\s*$", params_body, re.M) is not None,
            f"K3: extra_kustomize_parameters must pass {name} = local.{name}",
        )

    # K4
    tpl = KURED_TPL.read_text()
    params = {"base_kustomization_inputs": "a" * 40, "kured_version": "1.21.0"}
    try:
        out = render(tpl, params)
    except KeyError as e:
        failures.append(f"K4: {e}")
        out = ""
    if out:
        ds = [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "DaemonSet"]
        check(len(ds) == 1, f"K4: expected one DaemonSet, found {len(ds)}")
        if ds:
            d = ds[0]
            ann = (d["metadata"].get("annotations") or {}).get("mctl.ai/base-kustomization-inputs")
            check(ann == params["base_kustomization_inputs"], f"K4: hash annotation renders as {ann!r}")
            c = d["spec"]["template"]["spec"]["containers"][0]
            check(c["image"] == "ghcr.io/kubereboot/kured:1.21.0", f"K4: image renders as {c['image']!r}")
            res = c.get("resources") or {}
            check(bool(res.get("requests")) and bool(res.get("limits")), "K4: rendered kured lost its resources")
        for key, other in (("base_kustomization_inputs", "b" * 40), ("kured_version", "9.9.9")):
            check(render(tpl, {**params, key: other}) != out, f"K4: changing {key} does not change the rendered manifest")

    if failures:
        for f in failures:
            print("FAIL", f)
        return 1
    print("ok: K1-K4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
