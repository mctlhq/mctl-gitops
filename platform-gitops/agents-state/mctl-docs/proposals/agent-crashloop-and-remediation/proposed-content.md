# Proposed content: agent-crashloop-and-remediation

> **Apply to:** UPDATE `docs/platform/components.md`, `docs/reference/troubleshooting.md`, `docs/guides/rollbacks.md`, `docs/guides/scaling.md`
> **Source:** mctl-agent@36ffb0d, 2223296, b24f23a, 5880140, 610ba08
> **version-status:** unverified, see commit SHA

Existing page contents were not available to this run, so each patch gives the "after" section to add; place it per the TODO anchor.

---

## 1. `docs/platform/components.md` (UPDATE, mctl-agent block)

Before: `<TODO: quote current mctl-agent block>`

After (add):
```md
**Builtin skills.** Includes crash-loop diagnosis, rollback, scale-up and fixer skills. <TODO: confirm full list with author of 610ba08>

**Escalation.** If fix generation fails, or a proposal produces no PR, the agent escalates. Tickets opened by the poller close once the application is healthy, and resolved tickets stay closed.
```

## 2. `docs/reference/troubleshooting.md` (UPDATE)

After (add section):
```md
## Crash-looping pods

The agent diagnoses crash loops from pod state. Credentials in collected logs are redacted. Containers that exit cleanly are not treated as crash-looping.
```

## 3. `docs/guides/rollbacks.md` (UPDATE)

Before: `<TODO: quote current rollback description>`

After (add):
```md
## Automated rollback rules

- A gitops image bump counts as a deploy.
- Rollback restores the pinned image digest.
- Rollback goes back past every bump within the window.
- If the image history is not recognised, rollback fails closed (no change is made).
```

## 4. `docs/guides/scaling.md` (UPDATE)

After (add):
```md
## Automatic scale-up

The agent's scale-up action triggers only on an HPA signal (HPA alerts). Other alerts do not cause automatic scale-up.
```
