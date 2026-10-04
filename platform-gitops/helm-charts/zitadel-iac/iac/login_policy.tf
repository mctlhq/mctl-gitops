# The instance default login policy (#1520). S1 imported it unchanged; S2
# makes every sign-in need a WebAuthn authenticator.
#
# Login V2 (v4.19.2) has no switch for "passkeys only": `user_login`
# (allowLocalAuthentication) gates passwords AND passkeys, so `false` would
# leave only external IdPs. Passwords also cannot be removed from existing
# users through any API. So passwords stay allowed, but never suffice:
#   - force_mfa: a password sign-in must add a second factor, and Login V2
#     exempts passkey sign-ins (user-verified WebAuthn) from it;
#   - second_factors = U2F only: that second factor is WebAuthn too, not a
#     phishable TOTP code. With no factor enrolled the user is sent to set one
#     up, with no skip, before any session reaches an application;
#   - allow_register = false: accounts come from this repo (S3), not sign-up;
#   - hide_password_reset: no reset link (there is no SMTP anyway).
# Verified on a local v4.19.2 with Login V2 before rollout (see the PR).
#
# ignore_unknown_usernames: Login V2 answers an unknown login name with the
# password page instead of "User not found", and creates no session for a
# known password user, so the two look the same and the account picker
# learns no name. It does not cover passkey users (every personal account
# here): Login V2 v4.19.2 still sends them to the passkey page, which opens a
# session carrying their display name. That residue is #1612, measured on a
# local v4.19.2. No organization has a login policy of its own in this root,
# so tenant organizations (erpact included) inherit this one.
import {
  to = zitadel_default_login_policy.default
  id = "default"
}

resource "zitadel_default_login_policy" "default" {
  user_login                    = true
  allow_register                = false
  allow_external_idp            = true
  allow_domain_discovery        = true
  force_mfa                     = true
  force_mfa_local_only          = false
  passwordless_type             = "PASSWORDLESS_TYPE_ALLOWED"
  hide_password_reset           = true
  ignore_unknown_usernames      = true
  disable_login_with_email      = false
  disable_login_with_phone      = false
  default_redirect_uri          = ""
  password_check_lifetime       = "240h0m0s"
  external_login_check_lifetime = "240h0m0s"
  mfa_init_skip_lifetime        = "720h0m0s"
  second_factor_check_lifetime  = "18h0m0s"
  multi_factor_check_lifetime   = "12h0m0s"
  second_factors                = ["SECOND_FACTOR_TYPE_U2F"]
  multi_factors                 = ["MULTI_FACTOR_TYPE_U2F_WITH_VERIFICATION"]
  idps                          = []
}
