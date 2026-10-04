# MCTL branding on auth.mctl.ai (owner decision 2026-10-04): every sign-in
# should read as an MCTL login, with ZITADEL only underneath. The instance
# default label policy is what Login V2 renders as its BrandingSettings, for
# every organization without a label policy of its own.
#
# Colours are mctl-design's tokens (packages/tokens/src/color.ts): paper and
# ink surfaces, terracotta accent (the deep step on paper, where it is AA),
# the status reds for warnings. The SVGs are copies of mctl-design
# apps/storybook/public/brand/{sidebar-light,sidebar-dark}.svg at 98c8352,
# and the icons are its favicon.svg with each theme's colour baked in; copy
# them again when the brand changes there. The *_hash
# arguments make the provider upload a file again when its content changes.
#
# There is no destroy: the provider's delete is a no-op, and removing this
# resource would leave the last applied branding in place.
resource "zitadel_default_label_policy" "default" {
  primary_color    = "#b83d28" # terracottaDeep
  background_color = "#f1ede4" # paper
  font_color       = "#15181d" # paperInk
  warn_color       = "#c23b3b" # badDeep

  primary_color_dark    = "#e25a3c" # terracotta
  background_color_dark = "#0a0b0d" # ink
  font_color_dark       = "#e6e7e9" # fg
  warn_color_dark       = "#ff6b6b" # bad

  theme_mode             = "THEME_MODE_AUTO"
  hide_login_name_suffix = false
  disable_watermark      = true

  logo_path      = "${path.module}/branding-sidebar-light.svg"
  logo_hash      = filemd5("${path.module}/branding-sidebar-light.svg")
  logo_dark_path = "${path.module}/branding-sidebar-dark.svg"
  logo_dark_hash = filemd5("${path.module}/branding-sidebar-dark.svg")
  icon_path      = "${path.module}/branding-icon-light.svg"
  icon_hash      = filemd5("${path.module}/branding-icon-light.svg")
  icon_dark_path = "${path.module}/branding-icon-dark.svg"
  icon_dark_hash = filemd5("${path.module}/branding-icon-dark.svg")

  # Label policy changes are staged as a preview until activated.
  set_active = true
}
