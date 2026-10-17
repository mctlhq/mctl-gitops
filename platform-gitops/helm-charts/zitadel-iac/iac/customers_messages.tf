# Product copy is English in every supported login locale. Explicit fallback
# prevents a non-English browser from inheriting staff password/passkey help.
# Keep the existing English resource address: translations cannot be deleted.
locals {
  customer_copy_languages = toset(keys(jsondecode(file("${path.module}/login_texts.json"))))
  customer_login_copy_en = {
    common = { title = "Sign in to MCTL" }
    loginname = {
      title       = "Welcome to MCTL"
      description = "Continue with GitHub to access your workspace. Your GitHub account manages sign-in and recovery."
      errors = {
        localAuthenticationNotAllowed = "Use Continue with GitHub. MCTL customer accounts do not use a local password or passkey."
      }
    }
    idp = {
      title            = "Continue to MCTL"
      description      = "Use your GitHub account. MCTL requests your profile and verified email, with no access to your repositories."
      signInWithGithub = "Continue with GitHub"
      # Login v2 shows this one static page for every failed IdP intent,
      # including the identity hook's refusal to create a customer account
      # (mctl-api#653), so it must be right for both without saying which.
      loginError = {
        title       = "We could not sign you in with GitHub"
        description = "If you have an MCTL staff or partner account, go back and choose Sign in with MCTL account. Otherwise, check that your GitHub account has a verified email address and try again. If the problem continues, contact MCTL at https://mctl.ai/#contact."
      }
      accountNotFound = {
        title       = "Your MCTL account is not available"
        description = "Try signing in again with GitHub."
        info        = "If the problem continues, contact MCTL at https://mctl.ai/#contact. Do not create a separate password account."
      }
      completeRegister = {
        title       = "Finish your GitHub profile"
        description = "Add a verified email address in GitHub settings, then return to MCTL and sign in again."
      }
    }
    register = {
      disabled = {
        title       = "Continue with GitHub"
        description = "MCTL creates your customer account when you sign in with GitHub. A separate password or passkey is not needed."
      }
    }
  }
}

# Customers use GitHub for sign-in and recovery. Instance defaults invite
# staff to set up passkeys; never show those instructions to customers.
# ZITADEL cannot delete hosted-login translations: removing this resource
# leaves its last applied copy live. Revert by applying replacement texts.
resource "zitadel_hosted_login_translation" "customers_en" {
  org_id       = zitadel_org.customers.id
  language     = "en"
  translations = jsonencode(local.customer_login_copy_en)
}

# GitHub auto-creation supplies a verified address and should send no
# verification email. If a later verification is required, the org-scoped
# message still gives correct GitHub-only sign-in instructions.
resource "zitadel_verify_email_message_text" "customers_en" {
  org_id      = zitadel_org.customers.id
  language    = "en"
  title       = "Your MCTL account"
  pre_header  = "Confirm your email address"
  subject     = "MCTL: confirm your email address"
  greeting    = "Hello {{.DisplayName}},"
  text        = "Confirm the email address on your MCTL account with the button below, or enter {{.Code}}. Continue with GitHub to sign in at https://mctl.ai. Your MCTL login name {{.PreferredLoginName}} is an account identifier, not a mailbox. Sign-in and account recovery are managed by GitHub. If you did not request this email, ignore it."
  button_text = "Confirm email address"
  footer_text = "MCTL, https://mctl.ai/#contact"
}

resource "zitadel_hosted_login_translation" "customers_fallback" {
  for_each     = setsubtract(local.customer_copy_languages, toset(["en"]))
  org_id       = zitadel_org.customers.id
  language     = each.key
  translations = jsonencode(local.customer_login_copy_en)
}

resource "zitadel_verify_email_message_text" "customers_fallback" {
  for_each    = setsubtract(local.customer_copy_languages, toset(["en"]))
  org_id      = zitadel_org.customers.id
  language    = each.key
  title       = zitadel_verify_email_message_text.customers_en.title
  pre_header  = zitadel_verify_email_message_text.customers_en.pre_header
  subject     = zitadel_verify_email_message_text.customers_en.subject
  greeting    = zitadel_verify_email_message_text.customers_en.greeting
  text        = zitadel_verify_email_message_text.customers_en.text
  button_text = zitadel_verify_email_message_text.customers_en.button_text
  footer_text = zitadel_verify_email_message_text.customers_en.footer_text
}
