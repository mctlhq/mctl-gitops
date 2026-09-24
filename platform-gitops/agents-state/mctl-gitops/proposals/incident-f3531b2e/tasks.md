# Tasks: incident-f3531b2e

1. [ ] In `services/labs/mctl-telegram/values.yaml`, immediately above the
       "# Synthetic end-to-end canary." comment block (around line 437), add a
       comment noting incident 5a1534d8-b8e8-4985-885d-a969f3531b2e
       (MctlTelegramSessionBorrowSlowBurn, 2026-09-24), instructing an operator
       to verify the `mctl-telegram-canary` Secret's `tg_user_id` is 924671154
       (not 210408407, which preview holds open concurrently for the
       communication-agent soak), and to remint it via the self-renewal path
       (mctl-telegram#421) if it is not.
2. [ ] Verify the file still parses as valid YAML after the edit (comment-only
       change; no keys added or removed).
3. [ ] No image tag bump or other dependent change is needed — this is a
       documentation/checklist-only change with LOW confidence in resolving
       the alert directly. Do not mark the underlying incident as fixed by
       this change alone.
