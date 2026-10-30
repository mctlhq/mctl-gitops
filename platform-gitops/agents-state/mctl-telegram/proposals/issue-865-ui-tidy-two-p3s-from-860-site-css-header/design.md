# Design: issue-865-ui-tidy-two-p3s-from-860-site-css-header

## Current state
- `internal/ui/chrome.go` embeds `assets/site.css` into `siteCSS` (line 50)
  and appends it to `ComponentsCSS` (line 211). Its package doc comment
  (lines 1-30) wraps at about 80 columns, except line 29:
  `//     site.css mirror (dark, since there is no script to read a stored choice). The tab icon is the only CDN fetch`
  That line is about 115 columns wide and belongs to the `"lite"` tier bullet.
- `internal/ui/chrome_test.go`, `TestSiteCSSMirrorMatchesPinnedVersion`
  (lines 229-237), contains:
  `first := siteCSS[:strings.Index(siteCSS, "\n")]`
  With no newline, the index is -1 and the slice panics. The asset's first line
  is currently `/* @mctlhq/css 0.15.0 — site.css. */` followed by a newline, so
  the test passes today.
- `TestCtrlListColumnCanShrink` (line 207) has a similar unguarded second
  `strings.Index`. The issue does not mention it.

Deployed state checked:
- `/workdir/mctl-gitops/platform-gitops/services/labs/mctl-telegram` exists:
  the service is deployed under tenant `labs`. Its values were not read
  further, because this change touches only a test and a comment and has no
  deployed-config dependency.
- No mctl MCP tools were called. They are not needed for a change that has no
  runtime effect.

## Proposed solution
1. In `TestSiteCSSMirrorMatchesPinnedVersion`, split the slice into an index
   check:
   ```go
   nl := strings.Index(siteCSS, "\n")
   if nl < 0 {
       t.Fatalf("assets/site.css header line has no trailing newline; want first line %q",
           "/* @mctlhq/css "+DesignVersion+" — site.css. */")
   }
   first := siteCSS[:nl]
   ```
   The existing comparison and the `ComponentsCSS` containment check stay as
   they are. A simpler message such as "assets/site.css has no newline after
   its header line" is also acceptable.
2. Re-wrap the `"lite"` bullet in the package doc comment so that every line
   is at most 80 columns. Keep the 4-space continuation indent and the exact
   wording. For example:
   ```
   //     No external CSS/JS: same palette and layout via inlined tokens and the
   //     site.css mirror (dark, since there is no script to read a stored
   //     choice). The tab icon is the only CDN fetch (favicon-telegram.svg).
   ```
   Line 27, which holds the CSP string, is about 84 columns and is a literal
   that should not be broken. Leave it unchanged.

## Alternatives
- `strings.Cut(siteCSS, "\n")` with a `found` check. This is equally correct
  and idiomatic, and the implementer may use it. Either form satisfies the
  acceptance criteria.
- `strings.SplitN(siteCSS, "\n", 2)[0]`. This never panics, but with no
  newline it silently compares the whole file. The failure message would then
  be a large dump rather than a precise one, so it was rejected.
- Re-wrapping the whole file to 80 columns. This is out of scope and creates
  noisy diffs in template and code lines, so it was rejected.

## Platform impact
- No migrations, no runtime change, and no change to resources or backward
  compatibility.
- Risk: almost none. `go test ./internal/ui/...` and `gofmt` confirm the
  change.
