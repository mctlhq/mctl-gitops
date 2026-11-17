# Two machine users for the C2 service (epic 11 of the service's repository),
# one per direction of trust, deliberately NOT one shared identity:
#
#   consent reader   the service -> mctl-api. The service's token refresher
#                    signs in with this user's key; mctl-api accepts the
#                    resulting token on its consent read routes only.
#   control caller   mctl-api -> the service. mctl-api's kill switch client
#                    signs in with this user's key and PUTs the switch state;
#                    the service verifies the token itself (issuer, JWKS, an
#                    exact subject allow-list and its own audience).
#
# Why two. The private key of each sits in a different pod. The kill switch
# ships closed and opening it is the sensitive act: if the service's pod held
# a credential that could also call the control route, a compromise of that
# pod could open the switch it is supposed to be held shut by. And the
# audiences differ, so a token minted for one direction is refused by the
# other consumer even if its key leaked (checked in tests/c2_machine_users).
#
# Both are machine users of MCTL, which owns both audiences' projects, so
# has_project_check admits them with no grant. No org membership, no role, no
# secret (with_secret = false): the only credential of each is its key. JWT
# access tokens, because neither verifier can read ZITADEL's opaque ones.
#
# Key method: JWT profile (RFC 7523), as orchestrator-devloop.tf. The
# refresher signs an assertion (iss = sub = the user id, kid = the key id,
# aud = https://auth.mctl.ai, at most one hour) and exchanges it at
# https://auth.mctl.ai/oauth/v2/token (grant_type
# urn:ietf:params:oauth:grant-type:jwt-bearer) for a JWT access token, which
# it writes atomically to the token file the consumer re-reads on each call.
# A personal access token was rejected: it never rotates, so the file would
# hold a long-lived bearer, and creating one puts it in the Terraform state.
# A client secret was rejected for the same state reason. Token lifetime is
# the ZITADEL instance default (access tokens 12 h, expires_in in the token
# response); the refresher must renew at half of expires_in, never on a fixed
# interval.

resource "zitadel_machine_user" "c2_consent_reader" {
  org_id            = local.mctl_org_id
  user_name         = "c2-consent-reader"
  name              = "C2 consent reader"
  description       = "C2 service: reads link consent records from mctl-api (consent routes only)"
  with_secret       = false
  access_token_type = "ACCESS_TOKEN_TYPE_JWT"
}

resource "zitadel_machine_user" "c2_control_caller" {
  org_id            = local.mctl_org_id
  user_name         = "c2-control-caller"
  name              = "C2 control caller"
  description       = "mctl-api: flips the C2 service's kill switch (one PUT route)"
  with_secret       = false
  access_token_type = "ACCESS_TOKEN_TYPE_JWT"
}

# The audience of the control route, a project of its own like
# customer_lifecycle (customers.tf): the reserved
# urn:zitadel:iam:org:project:id:{projectid}:aud scope puts this project's id,
# and nothing else, into the access token's aud. mctl-api does not accept it
# and the consent token does not carry it, so neither token works on the
# other's endpoint. The service pins this id and the exact machine subject.
resource "zitadel_project" "c2_control" {
  org_id            = local.mctl_org_id
  name              = "MCTL C2 control"
  has_project_check = true
}

# The consent reader's audience is the MCTL API project: mctl-api lists that
# id under service_subjects for this one subject only (mctl-api.tf), so the
# project audience is not accepted from any other client.

# Keys of our own, as orchestrator-devloop.tf: the RSA private keys were
# generated offline by the operator and are delivered to Vault by the
# operator; only the public halves are here, so neither this repository nor
# the Terraform state holds a credential (key_details stays empty when
# public_key is given). Rotation: generate a new key, replace public_key
# (ZITADEL replaces the key, the old one stops working on apply), store the
# new private key and point the consumer at the new kid. Both expire on their
# own a year out.
resource "zitadel_machine_key" "c2_consent_reader" {
  org_id          = local.mctl_org_id
  user_id         = zitadel_machine_user.c2_consent_reader.id
  key_type        = "KEY_TYPE_JSON"
  expiration_date = "2027-11-16T00:00:00Z"
  public_key      = <<-EOT
    -----BEGIN PUBLIC KEY-----
    MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEA3UrgHPHgrhIqPZ8UwfH1
    aCDu8naR2MM/oitl3X/PSH956s5pxrK990Yo6wRGj8JYOK/LHdngTJlWUT97Zlc6
    m/SnosIcyF7MphMZmUCTBfEYMu+k6dJZ/2RtRGw4tmXp4geq6OPk4Vw3p3cUr3Yw
    nDHXxUL2xf1Ljwy2Oyo82CK64iDqv3BWXlQRtUFNGbr7tAqj4k3FvqP4AMQMM4lN
    +9B3CyufgCPUJMPjD/HtAD9MP8g6U277QPUzXa/+UbGhM7go3wcyaFRkrXyOlPkZ
    7ZPsQ2eIjwW9tUHMbDmLeVHsC23+x/Y19np07YNLFm8gFoxoXXaUJbGzW2j0q37t
    sk46+eWOEo/cgTTsNWUroXKY5ScWff4p6MdyVFu7Jsg65E17V/nKyotIPly0ddXR
    MQNAblphxq+dSryqMMvYSTlDRcYzbqTARYRI6TjxCoiaIFWyYyd1L1bWcIbBRnIu
    ODzDztKUvxS1mqcSCVev+wemyHpUqYoyGMYw6+hBtyqdAgMBAAE=
    -----END PUBLIC KEY-----
  EOT
}

resource "zitadel_machine_key" "c2_control_caller" {
  org_id          = local.mctl_org_id
  user_id         = zitadel_machine_user.c2_control_caller.id
  key_type        = "KEY_TYPE_JSON"
  expiration_date = "2027-11-16T00:00:00Z"
  public_key      = <<-EOT
    -----BEGIN PUBLIC KEY-----
    MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEA69H1A0dUEv78ON5Ly9h+
    SyJMUJdvCysYVGzj2nCnq3bYN+2PVyRF6NP2qkVAgu6LE9UdkI162uYc6OcuyNQ6
    WYfFzMjaAvSybz9doiuFcGE6faFmCxgHuLW6VjJ1Dz+A+BDUsrzLcVRdcvSVkCey
    uyAl0ugjEU6PKENzOYdnBSFJhDxrTdS1/Qvc8vS37hQJhLFJZsYrcjayzkYmZ2Px
    /DqDnPNzR2yU0nCnaapt91A2VoZPgQVuPHkt71di36RNGJraQFolbXZZGWtSHqIa
    9VpTg33p53tW7gttNMXHXy4cT8KYY1hFyaHLp5nIf6D0xNk1/L7SpWgljVU8dh06
    O3WKPyh2IYU12CdZNma1QR+tSVoRt5zZf9CTTT5t6ss6c0g3cjl0StpBd5Gcu/jz
    qerlJdl/o2Jn1NL4za1y+SNQnDwhz1p7mBryTgceMSGglTKXFQlu0tTC6bKvLbBi
    3pxCVyLrvSotn+55tCRB2jlInMZC/XT/5mV+KfaC6mS7AgMBAAE=
    -----END PUBLIC KEY-----
  EOT
}

# The ids the consumers and the operator need, for nobody who reads Secret
# data. None is a credential. Created empty by Argo CD
# (infra-components/mctl-platform/mctl-api/c2-machine-users.yaml); the Job
# fills it. The operator copies the consumer's values into Vault by hand.
resource "kubernetes_config_map_v1_data" "c2_machine_ids" {
  metadata {
    name      = "mctl-api-c2-machine-ids"
    namespace = "mctl-api"
  }

  data = {
    issuer         = "https://auth.mctl.ai"
    token_endpoint = "https://auth.mctl.ai/oauth/v2/token"
    jwks_url       = "https://auth.mctl.ai/oauth/v2/keys"

    consent_user_id     = zitadel_machine_user.c2_consent_reader.id
    consent_key_id      = zitadel_machine_key.c2_consent_reader.id
    consent_audience    = zitadel_project.mctl_api.id
    consent_scope       = "openid urn:zitadel:iam:org:project:id:${zitadel_project.mctl_api.id}:aud"
    consent_key_expires = zitadel_machine_key.c2_consent_reader.expiration_date

    control_user_id     = zitadel_machine_user.c2_control_caller.id
    control_key_id      = zitadel_machine_key.c2_control_caller.id
    control_audience    = zitadel_project.c2_control.id
    control_scope       = "openid urn:zitadel:iam:org:project:id:${zitadel_project.c2_control.id}:aud"
    control_key_expires = zitadel_machine_key.c2_control_caller.expiration_date
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data.
  force = true
}
