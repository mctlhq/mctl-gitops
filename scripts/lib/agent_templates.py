"""Shared agent-template detection for the agent validators (mctl-gitops#2289).

Used by validate-agent-pod-security.py and validate-agent-pod-labels.py so the
two cannot disagree about what an agent template is.
"""

from __future__ import annotations

MARKER = "workflow.parameters.agent_image"
AGENT_IMAGE_PREFIX = "ghcr.io/mctlhq/mctl-agents"
AGENT_LABEL_KEY = "app.kubernetes.io/name"
AGENT_LABEL_VALUE = "mctl-agents"

# Templates that run the mctl-agents image only as a Python runtime for a
# platform job. They need Vault, which agent pods must not have, so they must
# NOT carry the agent label.
PLATFORM_IMAGE_USERS = frozenset({"zitadel-login-consolidation"})

# Agent templates that do not follow the mctl-agents-* name.
EXTRA_AGENT_NAMES = frozenset({"lifecycle-bootstrap"})


def image_of(tpl: dict) -> str:
    for key in ("container", "script"):
        body = tpl.get(key)
        if isinstance(body, dict):
            return str(body.get("image", ""))
    return ""


def runs_agent_image(spec: dict) -> bool:
    for tpl in spec.get("templates") or []:
        image = image_of(tpl)
        if MARKER in image or image.startswith(AGENT_IMAGE_PREFIX):
            return True
    return False


def is_agent_cwft(name: str, spec: dict) -> bool:
    """True when a (Cluster)WorkflowTemplate is an agent template."""
    if name in PLATFORM_IMAGE_USERS:
        return False
    return name.startswith("mctl-agents-") or name in EXTRA_AGENT_NAMES or runs_agent_image(spec)
