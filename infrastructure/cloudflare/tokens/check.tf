# The live list of account-owned tokens must equal manifest.tf, as a multiset
# of fingerprints. A fingerprint is the name, the status, the expiry, any IP
# condition and the policies (effect, permission group IDs, resources). Token
# IDs, issue dates and last use are left out: rotating a token in place changes
# nothing a reviewer needs to see.
#
# Both directions fail the plan:
#   * undeclared: a live token with no matching entry (created, widened or
#     re-scoped outside Git, or set to expire or restricted by IP);
#   * missing: an entry with no matching live token (revoked, expired,
#     disabled, or changed so it no longer matches).
#
# A failed read is never an empty list. Without `Account API Tokens Read` the
# API answers 9109 and the data source errors, which fails the plan. A listing
# that does come back short shows up as missing entries, not as a pass. The
# data source takes only constants, so it is read during plan and the checks
# below cannot be deferred to an apply that never happens.

locals {
  declared = [
    for t in local.tokens : jsonencode({
      name       = t.name
      status     = "active"
      expires_on = ""
      request_ip = null
      policies = sort([
        for p in t.policies : jsonencode({
          effect            = "allow"
          permission_groups = sort(p.permission_groups)
          resources         = p.resources
        })
      ])
    })
  ]
}

data "cloudflare_account_tokens" "all" {
  account_id = var.account_id

  # Recently expired tokens are listed too, so an expiry is reported as a
  # token whose status changed rather than as one that silently vanished.
  include_expired = true

  lifecycle {
    postcondition {
      condition     = self.result != null && length(self.result) > 0
      error_message = "The account token listing came back empty. That is a failed read, not an account without tokens: the account holds at least the CI tokens declared in manifest.tf."
    }

    # The same fingerprint as local.declared, built from the live listing.
    # Written out again in the error message: a postcondition can only see
    # `self`, so the live side cannot be a local.
    postcondition {
      condition = sort(local.declared) == sort([
        for t in self.result : jsonencode({
          name       = t.name
          status     = t.status
          expires_on = t.expires_on == null ? "" : t.expires_on
          request_ip = try(length(t.condition.request_ip.in), 0) + try(length(t.condition.request_ip.not_in), 0) > 0 ? t.condition.request_ip : null
          policies = sort([
            for p in(t.policies == null ? [] : t.policies) : jsonencode({
              effect            = p.effect
              permission_groups = sort([for g in p.permission_groups : g.id])
              resources         = p.resources
            })
          ])
        })
      ])
      # `for live in [...]` binds the live fingerprints to a name once, so
      # every fingerprint can be counted on both sides: identical tokens exist,
      # and one too many of them is as much a difference as a new name.
      error_message = one([
        for live in [
          [
            for t in self.result : jsonencode({
              name       = t.name
              status     = t.status
              expires_on = t.expires_on == null ? "" : t.expires_on
              request_ip = try(length(t.condition.request_ip.in), 0) + try(length(t.condition.request_ip.not_in), 0) > 0 ? t.condition.request_ip : null
              policies = sort([
                for p in(t.policies == null ? [] : t.policies) : jsonencode({
                  effect            = p.effect
                  permission_groups = sort([for g in p.permission_groups : g.id])
                  resources         = p.resources
                })
              ])
            })
          ]
          ] : format(
          "Account API tokens differ from infrastructure/cloudflare/tokens/manifest.tf (declared count, live count, fingerprint):\n%s\nDeclare the change in manifest.tf, or undo it in the dashboard.",
          join("\n", [
            for f in sort(distinct(concat(local.declared, live))) :
            format("  declared %d, live %d: %s", length([for d in local.declared : d if d == f]), length([for l in live : l if l == f]), f)
            if length([for d in local.declared : d if d == f]) != length([for l in live : l if l == f])
          ])
        )
      ])
    }
  }
}
