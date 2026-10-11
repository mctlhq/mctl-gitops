# The invitation mails must tell the user their login name (messages.tf,
# mctlhq/mctl-api#462): Login V2 v4.19.x cannot sign a passkey user in by
# e-mail while ignore_unknown_usernames is on, and nothing else names the
# login name. Run in CI (`tofu test`) against mocked providers; plans target
# the message texts only, as in admins.tftest.hcl.

mock_provider "zitadel" {
  mock_data "zitadel_orgs" {
    defaults = { ids = ["100000000000000001"] }
  }
  mock_data "zitadel_human_users" {
    defaults = { user_ids = ["100000000000000002"] }
  }
}

mock_provider "kubernetes" {}

variables {
  tenant_users    = "{\"erpact\": \"{\\\"tuser\\\": \\\"{\\\\\\\"email\\\\\\\": \\\\\\\"t@example.com\\\\\\\", \\\\\\\"first_name\\\\\\\": \\\\\\\"T\\\\\\\", \\\\\\\"last_name\\\\\\\": \\\\\\\"U\\\\\\\"}\\\"}\"}"
  smtp_password   = "test"
  platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\"}\"}"
}

run "invitation_mails_name_the_login_name" {
  command = plan
  plan_options {
    target = [
      zitadel_default_verify_email_message_text.en,
      zitadel_default_verify_email_message_text.ru,
      zitadel_default_invite_user_message_text.en,
      zitadel_default_invite_user_message_text.ru,
    ]
  }
  assert {
    condition = alltrue([
      for t in [
        zitadel_default_verify_email_message_text.en.text,
        zitadel_default_verify_email_message_text.ru.text,
        zitadel_default_invite_user_message_text.en.text,
        zitadel_default_invite_user_message_text.ru.text,
      ] : strcontains(t, "{{.PreferredLoginName}}")
    ])
    error_message = "Every invitation mail (verify e-mail and invite user, en and ru) must carry {{.PreferredLoginName}}."
  }
}
