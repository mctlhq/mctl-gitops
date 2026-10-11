# Requirements: Services listing: managed rows and incomplete results

version-status: unverified, see commit SHA

## Acceptance criteria (EARS)
- THE tools reference SHALL describe the `managed` field values `catalogue`, `external`, `platform`.
- THE page SHALL state that only `catalogue` services support deploy, rollback and scale.
- WHEN `complete` is false, THE page SHALL explain the result is incomplete (ArgoCD unreadable), not empty.
- THE page SHALL state that manifest source of platform-managed rows is withheld from non-admins.
