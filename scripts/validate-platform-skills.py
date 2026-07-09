#!/usr/bin/env python3
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = ROOT / "platform-gitops" / "platform-skills"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")
SECRET_RE = re.compile(
    r"(ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,})"
)


def fail(errors, message):
    errors.append(message)


def load_yaml(path, errors):
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        fail(errors, f"{path}: {exc}")
        return {}


def main():
    errors = []
    catalog = BASE / "catalog"
    skills = {}

    for skill_dir in sorted(catalog.glob("*")) if catalog.exists() else []:
        if not skill_dir.is_dir():
            continue
        meta_path = skill_dir / "metadata.yaml"
        content_path = skill_dir / "SKILL.md"
        meta = load_yaml(meta_path, errors)
        name = meta.get("name")
        if not name or not NAME_RE.match(name):
            fail(errors, f"{meta_path}: invalid or missing name")
            continue
        if name != skill_dir.name:
            fail(errors, f"{meta_path}: name must match directory")
        if name in skills:
            fail(errors, f"{meta_path}: duplicate skill name {name}")
        skills[name] = meta
        for field in ("title", "description", "owner"):
            if not meta.get(field):
                fail(errors, f"{meta_path}: missing {field}")
        if meta.get("visibility") not in {"public", "tenant", "admin", "platform-internal"}:
            fail(errors, f"{meta_path}: invalid visibility")
        if meta.get("status") not in {"draft", "active", "deprecated"}:
            fail(errors, f"{meta_path}: invalid status")
        if not isinstance(meta.get("runtimes"), list):
            fail(errors, f"{meta_path}: runtimes must be a list")
        if not content_path.exists():
            fail(errors, f"{content_path}: missing SKILL.md")
        elif SECRET_RE.search(content_path.read_text(encoding="utf-8")):
            fail(errors, f"{content_path}: possible secret detected")

    tenant_bindings = BASE / "bindings" / "tenants"
    for path in sorted(tenant_bindings.glob("*.yaml")) if tenant_bindings.exists() else []:
        binding = load_yaml(path, errors)
        tenant = binding.get("tenant")
        if not tenant or not NAME_RE.match(tenant):
            fail(errors, f"{path}: invalid tenant")
        for skill_name in binding.get("enabledSkills") or []:
            meta = skills.get(skill_name)
            if not meta:
                fail(errors, f"{path}: unknown skill {skill_name}")
                continue
            if meta.get("visibility") != "tenant":
                fail(errors, f"{path}: {skill_name} has {meta.get('visibility')} visibility and cannot be tenant-bound")
            elif meta.get("status") not in {"active", "deprecated"}:
                # draft can never be bound; deprecated stays valid so a skill
                # already enabled for a tenant doesn't start failing CI the
                # moment it's deprecated (platform-skill-enable already
                # blocks *new* bindings to non-active skills).
                fail(errors, f"{path}: {skill_name} has status {meta.get('status')} and cannot be tenant-bound")

    role_bindings = BASE / "bindings" / "roles"
    for path in sorted(role_bindings.glob("*.yaml")) if role_bindings.exists() else []:
        binding = load_yaml(path, errors)
        role = binding.get("role")
        if not role or not NAME_RE.match(role):
            fail(errors, f"{path}: invalid role")
        for skill_name in binding.get("enabledSkills") or []:
            meta = skills.get(skill_name)
            if not meta:
                fail(errors, f"{path}: unknown skill {skill_name}")
                continue
            if meta.get("visibility") == "platform-internal":
                fail(errors, f"{path}: {skill_name} has platform-internal visibility and cannot be bound to a role")
            elif meta.get("status") not in {"active", "deprecated"}:
                fail(errors, f"{path}: {skill_name} has status {meta.get('status')} and cannot be bound to a role")

    policy_path = BASE / "policy.yaml"
    if policy_path.exists():
        policy = load_yaml(policy_path, errors)
        for field in ("tenantAllowlist", "tenantDenylist"):
            entries = policy.get(field) or {}
            if not isinstance(entries, dict):
                fail(errors, f"{policy_path}: {field} must be a mapping of tenant to skill list")
                continue
            for tenant, skill_names in entries.items():
                if not isinstance(skill_names, list):
                    fail(errors, f"{policy_path}: {field}.{tenant} must be a list")
                    continue
                for skill_name in skill_names:
                    if skill_name not in skills:
                        fail(errors, f"{policy_path}: {field}.{tenant} references unknown skill {skill_name}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"validated {len(skills)} platform skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
