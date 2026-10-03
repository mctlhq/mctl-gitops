# The instance default login policy, imported with the values it has today
# (slice S1: zero behaviour change). Changing it to passkey-only is slice S2,
# after the semantics are verified on a local ZITADEL.
import {
  to = zitadel_default_login_policy.default
  id = "default"
}

resource "zitadel_default_login_policy" "default" {
  user_login                    = true
  allow_register                = true
  allow_external_idp            = true
  allow_domain_discovery        = true
  force_mfa                     = false
  force_mfa_local_only          = false
  passwordless_type             = "PASSWORDLESS_TYPE_ALLOWED"
  hide_password_reset           = false
  ignore_unknown_usernames      = false
  disable_login_with_email      = false
  disable_login_with_phone      = false
  default_redirect_uri          = ""
  password_check_lifetime       = "240h0m0s"
  external_login_check_lifetime = "240h0m0s"
  mfa_init_skip_lifetime        = "720h0m0s"
  second_factor_check_lifetime  = "18h0m0s"
  multi_factor_check_lifetime   = "12h0m0s"
  second_factors                = ["SECOND_FACTOR_TYPE_OTP", "SECOND_FACTOR_TYPE_U2F"]
  multi_factors                 = ["MULTI_FACTOR_TYPE_U2F_WITH_VERIFICATION"]
  idps                          = []
}
