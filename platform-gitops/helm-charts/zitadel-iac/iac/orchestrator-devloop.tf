# The orchestrator DevLoop principal (mctlhq/mctl-api#963, docs/
# orchestrator-devloop.md in that repository): the Codex orchestrator on the
# Mac mini starts DevLoop for issues it has triaged, and reads those loops
# back, without a human relaying each start. mctl-api maps exactly this
# machine user (MCTL_ORCHESTRATOR_DEVLOOP_PROVIDER/_SUBJECT) to
# service:mctl-orchestrator-devloop, confined by a route gate to POST
# /api/v1/agents/dev-loop/start, GET /api/v1/agents/dev-loop/{id} and GET
# /api/v1/whoami, for the repositories in MCTL_ORCHESTRATOR_DEVLOOP_REPOS
# (bootstrap/templates/mctl-platform/mctl-api.yaml). It can never approve a
# proposal: that stays a human admin's decision.
#
# A machine user of MCTL, which owns the MCTL API project, so has_project_check
# admits it with no grant. No org membership, no project role, no secret
# (with_secret = false): its only credential is the key below. JWT access
# tokens, because mctl-api cannot verify ZITADEL's opaque ones. mctl-api reads
# no ZITADEL role or group, and drops the groups of this identity anyway.
resource "zitadel_machine_user" "orchestrator_devloop" {
  org_id            = local.mctl_org_id
  user_name         = "orchestrator-devloop"
  name              = "Orchestrator DevLoop"
  description       = "Codex orchestrator on the Mac mini: starts and reads DevLoop only (mctl-api#963)"
  with_secret       = false
  access_token_type = "ACCESS_TOKEN_TYPE_JWT"
}

# A key of our own: the RSA private key was generated on the Mac mini and
# never left it (~/etc/mctl-devloop-zitadel.pem, mode 0600). Only its public
# half is here, so neither this repository nor the Terraform state holds a
# credential (key_details stays empty when public_key is given). The mini
# signs a JWT-profile assertion (RFC 7523) with kid = this key's id and
# iss = sub = the machine user's id, both published in the ConfigMap below.
#
# Rotation: generate a new key on the mini, replace public_key (ZITADEL
# replaces the key, so the old one stops working on apply), and point the
# mini at the new kid. It expires on its own a year out, so a lost or
# forgotten key does not stay valid indefinitely.
resource "zitadel_machine_key" "orchestrator_devloop" {
  org_id          = local.mctl_org_id
  user_id         = zitadel_machine_user.orchestrator_devloop.id
  key_type        = "KEY_TYPE_JSON"
  expiration_date = "2027-11-08T00:00:00Z"
  public_key      = <<-EOT
    -----BEGIN PUBLIC KEY-----
    MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAqHLc6kA0f08lsT7VBTUP
    6zXchcOeIDvUz5ubV71OmYfudzskO5N2W/9rny6wwpuiNxpQ9KHigSmgPMTrxQtd
    LuUnhH4dli+JiE80CZ72nm2uQOAY5tp9XB0wMrxgZ+SOoQCOUidOS463SgeXkH7Q
    KFdy/wtwIkdW1Zphfkw2j9N084kecPE9YItUuwChcSmuwsUpZnBI8TQ+UdeW5/fQ
    UsgSlKrEGg4CJGfB3f++rZTQVdBg7ZXHqtN7M4i3DKylqG83KQGz0aSYArvPlzsZ
    DDfIztTcv/8Kr2QF291iYNdxs/LlwUWcRUsBpeEWqFEvKJEw0IlJXN5epQeic49a
    lYlqBW/aYf+p3rJK9aDfjLvUQEc6eltSwDhnhE5tTXdm25Q6xRfPHmT3dZMsaeQ5
    LoS3INGSiU3w+CEoprULXhoJsG/PBWWaVxG9ccxdGmZfgAn5HlhLB5wf0Al16cqe
    Aao//FiMQyVE6Mvj6p/mY+LDCddRwNflrtUQQZZb8bbTAgMBAAE=
    -----END PUBLIC KEY-----
  EOT
}

# The identity mctl-api maps, read through the chart's envFromOptionalSecrets
# (mctl-api/mctl-api-orchestrator-devloop). Nothing in it is secret, but the
# chart passes env from Secrets only. `zitadel` is the name of the provider
# entry in MCTL_OIDC_PROVIDERS (mctl-api.tf). mctl-api reads it at container
# start: bump ROLLOUT_MARKER after the Job first writes it.
resource "kubernetes_secret_v1_data" "orchestrator_devloop_env" {
  metadata {
    name      = "mctl-api-orchestrator-devloop"
    namespace = "mctl-api"
  }

  data = {
    MCTL_ORCHESTRATOR_DEVLOOP_PROVIDER = "zitadel"
    MCTL_ORCHESTRATOR_DEVLOOP_SUBJECT  = zitadel_machine_user.orchestrator_devloop.id
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data; see forgejo.tf.
  force = true
}

# The same ids for the operator who configures the mini, who never reads
# Secret data: the user id (iss/sub of the assertion) and the key id (kid).
# Neither is a credential.
resource "kubernetes_config_map_v1_data" "orchestrator_devloop_ids" {
  metadata {
    name      = "mctl-api-orchestrator-devloop-ids"
    namespace = "mctl-api"
  }

  data = {
    user_id     = zitadel_machine_user.orchestrator_devloop.id
    key_id      = zitadel_machine_key.orchestrator_devloop.id
    project_id  = zitadel_project.mctl_api.id
    issuer      = "https://auth.mctl.ai"
    key_expires = zitadel_machine_key.orchestrator_devloop.expiration_date
  }

  field_manager = "zitadel-iac"
  # Created by Argo CD with no data.
  force = true
}
