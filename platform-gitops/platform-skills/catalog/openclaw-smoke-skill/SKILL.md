---
name: openclaw-smoke-skill
description: Throwaway E2E smoke-test skill for the OpenClaw platform-skill materialization adapter. Safe to deprecate.
---

# OpenClaw Smoke Skill

This is a temporary smoke-test skill used to verify the platform-skill
materialization pipeline (catalog → tenant binding → generated Helm values →
skills-fanout → agent workspace).

When asked to confirm this skill is loaded, respond with the single word:

MATERIALIZED
