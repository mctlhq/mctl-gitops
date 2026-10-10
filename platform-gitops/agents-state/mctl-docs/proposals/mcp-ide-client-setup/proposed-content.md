## VS Code, Cursor and Windsurf

These editors connect with the same MCP server URL as other clients and sign in through OAuth in your browser.

1. Add `https://api.mctl.ai/mcp` as a remote MCP server in the editor's MCP settings (see the editor's own MCP documentation for the file or UI).
2. Start the server. The editor registers itself and opens a browser window.
3. Sign in and approve access. The editor receives the code through its own callback.

| Editor | Callback used |
|---|---|
| VS Code | `vscode.dev/redirect` (or Insiders) |
| Cursor | `cursor://` deep link |
| Windsurf | local loopback |

::: info
Only clients whose callback is allow-listed can register. If registration is refused, contact the platform team.
:::
