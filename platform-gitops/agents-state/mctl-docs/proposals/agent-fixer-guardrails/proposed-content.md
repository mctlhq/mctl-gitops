# Proposed content: agent-fixer-guardrails

> **Apply to:** `mctl-docs/docs/platform/components.md` (UPDATE, add subsection at the end of the mctl-agent block)
> **Source:** mctl-agent@8f91420, mctl-agent@42cce34, mctl-agent@ca6beca
> **version-status:** unverified, see commit SHA

---

## Before
```md
<TODO: confirm current mctl-agent block text; the page was not re-read>
```

## After (add after the mctl-agent description)
```md
### Fixer guardrails

When mctl-agent opens a pull request to fix an alert, the fixer is deliberately conservative.

**What a fix changes.** A fix edits exactly one scalar line in the target YAML file. The line is found by following a dotted path from the document root through block mappings only. Indentation, quoting and any inline comment on that line are preserved. Other keys, such as sibling `requests` or sidecar resources, are not touched.

**When the fixer refuses.** The fixer returns an error and does not open a PR when:

- the target cannot be proven: the path goes through a sequence or flow-style YAML, a key is missing or nested differently, or the current value in the file differs from the diagnosed current value;
- the suggested value is the same as the current value (a no-op);
- the suggested value would not stay a single scalar, for example it contains a newline, any non-printable character (including the Unicode line breaks NEL, LS and PS), an inline ` #`, a `: ` sequence, or a flow or alias indicator. Such values are refused, not escaped. A quoted scalar only rejects its own quote character (and a backslash inside double quotes).

If an alert fired but no PR appeared, one of these refusals is a possible cause. `<TODO: confirm with author of 8f91420 where refusals are surfaced to the user (logs, notification, alert state)>`.
```

---
