# The mail a new tenant user receives (#1520 S3). ZITADEL sends its
# "verify email" message when a user is created with an unverified address;
# its stock text speaks of "a new email has been added", which reads as a
# mistake to someone who never had an account. These texts say what it is:
# an invitation to set up a passkey. Placeholders are ZITADEL's own
# ({{.DisplayName}}, {{.Code}}); the button carries the link.
#
# The same message also goes out when an existing user changes their e-mail,
# so the wording covers both.
#
# Login V2 sends the "invite user" message instead when someone with no
# sign-in method yet enters their name and asks for a new code ("Resend
# code" on /verify?invite=true). Its stock text is "Invitation to Zitadel
# Login", so it is declared too, with the same wording. Placeholders:
# {{.DisplayName}}, {{.ApplicationName}}; the button carries the link.
#
# Both messages name the login name ({{.PreferredLoginName}}) and say to
# sign in with it rather than the e-mail address (mctlhq/mctl-api#462).
# Login V2 v4.19.x cannot sign a passkey user in by e-mail while
# ignore_unknown_usernames is on (login_policy.tf): it hands the typed
# e-mail to the passkey page, which creates the session with it as a
# login name, and the API's login-name lookup does not match e-mail
# addresses ("Could not request passkey challenge"). Upstream fix:
# zitadel/zitadel#12852 (open). Nothing else tells a user their login name,
# and it is not guessable: no org-domain suffix (must_be_domain is off).

resource "zitadel_default_verify_email_message_text" "en" {
  language    = "en"
  title       = "Your MCTL account"
  pre_header  = "Confirm your e-mail and set up a passkey"
  subject     = "MCTL: confirm your e-mail and set up sign-in"
  greeting    = "Hello {{.DisplayName}},"
  text        = "An MCTL account (auth.mctl.ai) has this e-mail address. Confirm it with the button below, or enter the code {{.Code}}. Then choose Passkeys: you sign in with your device's fingerprint, face or PIN, without a password. To sign in later, enter your login name {{.PreferredLoginName}}, not this e-mail address. If you did not expect this e-mail, ignore it."
  button_text = "Confirm and set up sign-in"
  footer_text = "MCTL, auth.mctl.ai"
}

resource "zitadel_default_verify_email_message_text" "ru" {
  language    = "ru"
  title       = "Ваш аккаунт MCTL"
  pre_header  = "Подтвердите почту и настройте passkey"
  subject     = "MCTL: подтвердите почту и настройте вход"
  greeting    = "Здравствуйте, {{.DisplayName}}!"
  text        = "Этот адрес указан в аккаунте MCTL (auth.mctl.ai). Подтвердите его кнопкой ниже или введите код {{.Code}}. Затем выберите Passkeys: вход будет по отпечатку пальца, лицу или PIN-коду устройства, без пароля. Для входа вводите логин {{.PreferredLoginName}}, а не этот адрес почты. Если вы не ждали этого письма, просто проигнорируйте его."
  button_text = "Подтвердить и настроить вход"
  footer_text = "MCTL, auth.mctl.ai"
}

resource "zitadel_default_invite_user_message_text" "en" {
  language    = "en"
  title       = "Your MCTL account"
  pre_header  = "Set up a passkey for MCTL"
  subject     = "MCTL: set up sign-in to your account"
  greeting    = "Hello {{.DisplayName}},"
  text        = "You have an MCTL account (auth.mctl.ai). Use the button below to confirm your e-mail and set up sign-in, then choose Passkeys: you sign in with your device's fingerprint, face or PIN, without a password. To sign in later, enter your login name {{.PreferredLoginName}}, not this e-mail address. If you did not expect this e-mail, ignore it."
  button_text = "Set up sign-in"
  footer_text = "MCTL, auth.mctl.ai"
}

resource "zitadel_default_invite_user_message_text" "ru" {
  language    = "ru"
  title       = "Ваш аккаунт MCTL"
  pre_header  = "Настройте passkey для MCTL"
  subject     = "MCTL: настройте вход в аккаунт"
  greeting    = "Здравствуйте, {{.DisplayName}}!"
  text        = "Для вас создан аккаунт MCTL (auth.mctl.ai). Нажмите кнопку ниже, чтобы подтвердить почту и настроить вход, и выберите Passkeys: вход будет по отпечатку пальца, лицу или PIN-коду устройства, без пароля. Для входа вводите логин {{.PreferredLoginName}}, а не этот адрес почты. Если вы не ждали этого письма, просто проигнорируйте его."
  button_text = "Настроить вход"
  footer_text = "MCTL, auth.mctl.ai"
}
