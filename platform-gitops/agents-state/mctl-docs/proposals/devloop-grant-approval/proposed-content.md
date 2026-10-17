# Proposed content: devloop-grant-approval

> **Apply to:** `mctl-docs/docs/guides/gitops-workflows.md` (UPDATE: append section; move if `platform-operations-approval-flow` lands elsewhere)
> **Source:** mctl-api@55f168c, d2f2c71, 6311b05, dab23f3, 4df8488; mctl-gitops@653572f

---

```md
## Approving a DevLoop run

A DevLoop run pauses after the investigator proposes a change and waits for human
approval. Approval never happens automatically. Three mechanisms exist:

| Path | Use |
|---|---|
| Approval grant (`aar_…`) bound to the run's execution (`we_…`) | Preferred. Approval is tied to a human principal and recorded. |
| `mctl_approve_dev_loop` (Temporal signal) | Admin approves a live run directly. |
| `mctl-agents-approve` operation | Flips the proposal's `.status.yaml` for runs without a live workflow. |

### Grant-based approval

An approval grant names the run it applies to. The run accepts it only if:

- the grant is for that execution (a grant bound to another target is refused);
- the grant is not denied, already spent or expired;
- it is an approval grant (another kind is refused).

If several grants exist, the **newest** one decides. A fresh approval is needed
after a re-run or resume. <TODO: confirm with author of d2f2c71 how a grant is issued>

### Legacy approver relay

The earlier relay, in which an agent relayed an approval on behalf of an admin, is
audited and counted, and is **disabled in production**. Use one of the paths above.
```

---
