# Tasks: incident-d7920bbc

1. [ ] Find the MctlTelegramSessionBorrowSlowBurn rule in mctl-gitops and read its expression.
2. [ ] Verify whether client-caused errors (USERNAME_NOT_OCCUPIED / HTTP 400) are counted as borrow failures; if yes, exclude them from the error numerator.
3. [ ] If the rule already counts only genuine failures, make no change and note it in the PR/report.
