# Variable validation of platform_admins and the key/username split in
# admins.tf, run in CI (`tofu test`) against mocked providers: nothing here
# talks to ZITADEL or Kubernetes. Each rejected case is a run that must fail
# on var.platform_admins, so loosening the validation fails this file.
# Plans target the admin users only: the root's import blocks crash
# OpenTofu's mock providers, and nothing else is under test here.

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
  tenant_users  = "{\"erpact\": \"{\\\"tuser\\\": \\\"{\\\\\\\"email\\\\\\\": \\\\\\\"t@example.com\\\\\\\", \\\\\\\"first_name\\\\\\\": \\\\\\\"T\\\\\\\", \\\\\\\"last_name\\\\\\\": \\\\\\\"U\\\\\\\"}\\\"}\"}"
  smtp_password = "test"
}

run "login_name_defaults_to_the_key" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\"}\"}"
  }
  assert {
    condition     = zitadel_human_user.platform_admin["dmitrii"].user_name == "dmitrii"
    error_message = "Without username the login name must be the key."
  }
}

run "username_sets_the_login_name_under_the_same_key" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": \\\"dmitrii.mashkov\\\"}\"}"
  }
  assert {
    condition     = zitadel_human_user.platform_admin["dmitrii"].user_name == "dmitrii.mashkov"
    error_message = "username must become user_name of the user addressed by the unchanged key."
  }
  assert {
    condition     = keys(zitadel_human_user.platform_admin) == ["dmitrii"]
    error_message = "The resource key must stay the Vault field name."
  }
}

run "username_equal_to_its_own_key_is_accepted" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": \\\"dmitrii\\\"}\"}"
  }
}

run "rejects_username_uppercase" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": \\\"Dmitrii.Mashkov\\\"}\"}"
  }
  expect_failures = [var.platform_admins]
}

run "rejects_username_empty" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": \\\"\\\"}\"}"
  }
  expect_failures = [var.platform_admins]
}

run "rejects_username_null" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": null}\"}"
  }
  expect_failures = [var.platform_admins]
}

run "rejects_username_number" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": 42}\"}"
  }
  expect_failures = [var.platform_admins]
}

run "rejects_username_boolean" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": true}\"}"
  }
  expect_failures = [var.platform_admins]
}

run "rejects_username_list" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": [\\\"x\\\"]}\"}"
  }
  expect_failures = [var.platform_admins]
}

run "rejects_username_at_sign" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": \\\"a@b\\\"}\"}"
  }
  expect_failures = [var.platform_admins]
}

run "rejects_username_break_glass_name" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": \\\"mctl-admin\\\"}\"}"
  }
  expect_failures = [var.platform_admins]
}

run "rejects_a_login_name_that_another_key_already_has" {
  command = plan
  plan_options {
    target = [zitadel_human_user.platform_admin]
  }
  variables {
    platform_admins = "{\"dmitrii\": \"{\\\"email\\\": \\\"a@example.com\\\", \\\"first_name\\\": \\\"A\\\", \\\"last_name\\\": \\\"B\\\", \\\"username\\\": \\\"other\\\"}\", \"other\": \"{\\\"email\\\": \\\"o@example.com\\\", \\\"first_name\\\": \\\"O\\\", \\\"last_name\\\": \\\"T\\\"}\"}"
  }
  expect_failures = [var.platform_admins]
}
