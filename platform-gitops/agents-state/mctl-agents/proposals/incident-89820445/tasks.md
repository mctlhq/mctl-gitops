# Tasks: incident-89820445

1. [ ] Confirm this is the same assert-attempt classification gap as incident-89820765
   (proposal mctl-telegram/issue-510) — same failure signature, same time window.
2. [ ] Apply the classification fix described in incident-89820765's design.md to the
   shared mctl-agents implementer/assert-attempt path (do not duplicate the fix
   per-service).
3. [ ] Verify no .github-specific code change is needed — `roadmap/scripts/reconcile.py`
   already satisfies the issue-67 requirements.
4. [ ] Re-run or dry-run the assert-attempt step against both incident-89820765 and
   incident-89820445 to confirm both now resolve without a workflow_failed incident.
