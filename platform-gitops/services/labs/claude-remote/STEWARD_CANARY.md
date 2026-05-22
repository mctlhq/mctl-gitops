# pr-steward escalation canary

Throwaway artifact to exercise the pr-steward escalation path once.

This file exists only so a `feat/agents-canary` PR is in scope for the
in-cluster pr-steward (branch prefix `feat/agents-`). It carries no
configuration and is not read by Helm or any manifest.

Purpose: drive one full watch -> decision -> ready-to-merge Telegram ping
cycle from the in-cluster steward. `merge_mode` is `never`; this PR is not
to be merged. Close it after the escalation tick is observed.
