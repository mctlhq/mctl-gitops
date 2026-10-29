# One WAF expression, shared by every zone root: block requests whose
# User-Agent claims to be a well-known crawler while Cloudflare's verified-bot
# check says otherwise. Real Googlebot, bingbot, ClaudeBot and the rest are in
# Cloudflare's verified-bot list, matched by source network, which a header
# cannot fake; a request with the name but without the verification is a
# scanner in disguise.
#
# Observed 2026-10-22 on *.mctl.me (mctl-landing-form Workers Logs): one
# scanner on Google Cloud (AS396982, 35.231.0.0/16) sent 189k requests in a
# day, rotating evenly through ~30 crawler User-Agents (Googlebot, bingbot,
# Applebot, Claude-User, ChatGPT-User, PerplexityBot, KimiBot, GrokBot, ...)
# while requesting /.env, /.git/config, /.terraform/terraform.tfstate and the
# like on a wordlist of subdomains. `verifiedBotCategory` was empty on every
# one of them. The same traffic then follows the worker's 301 to *.mctl.ai, so
# mctl.ai carries the rule too.
#
# A module with no resources and no provider: it exists so the three zone
# rulesets cannot drift apart on the list. Regex (`matches`) is not available
# on these plans, hence one `contains` clause per fragment. The verified-bot
# field is `cf.client.bot`: it carries the same information as
# `cf.bot_management.verified_bot`, which the field reference marks as
# requiring an Enterprise plan with Bot Management, while `cf.client.bot` is
# the form Cloudflare's own "stop malicious bots" guide uses on every plan.
#
# User-initiated agents (Claude-User, ChatGPT-User, Perplexity-User) are left
# out on purpose. They are not crawlers: they are the requests an assistant
# makes for one user, including every MCP connector call from claude.ai and
# ChatGPT, and they are not in Cloudflare's verified-bot list, so this rule
# blocked them all. On 2026-10-29 it returned 403 `mcp_request_blocked` to
# every claude.ai connector on mcp.mctl.ai within minutes of the apply. The
# scanner also rotated through ~25 other names that stay listed, and its
# /.env and /.git probes do not depend on the User-Agent at all.
# Spoofing these three names is therefore allowed again on purpose; the
# damage that scanner did came through the *.mctl.me wildcard, which
# block_unknown_subdomains still closes. Do not re-add them here.

locals {
  fragments = [
    "googlebot", "bingbot", "applebot", "yandexbot", "duckduckbot", "duckassistbot",
    "claudebot", "claude-searchbot", "anthropic-ai",
    "gptbot", "oai-searchbot",
    "perplexitybot", "kimibot", "kimi-searchbot", "grokbot",
    "bravebot", "meta-webindexer", "meta-externalagent", "facebookexternalhit",
    "qwenbot", "hunyuan", "chatglm-spider", "bytespider", "amazonbot", "petalbot",
  ]
}

output "expression" {
  description = "Rules-language expression matching a spoofed crawler: a listed User-Agent fragment on a request that is not a verified bot."
  value = format(
    "(not cf.client.bot and (%s))",
    join(" or ", [for f in local.fragments : format("lower(http.user_agent) contains \"%s\"", f)]),
  )
}

output "description" {
  description = "Rule description to use with the expression, so the three zones read the same in the dashboard."
  value       = "block crawler User-Agents that are not verified bots (spoofed-crawlers module)"
}
