# MCP Connection & OAuth PKCE Troubleshooting

This skill documents the diagnosis and recovery procedures for Model Context Protocol (MCP) servers, with specific focus on remote OAuth 2.0 PKCE authentication flows, transport selection, and token lifecycle management.

---

## Architecture & Configuration Files

MCP servers can be configured in two main formats depending on the client runtime:

1. **Claude Code / Standalone Schema** (`~/.claude.json` or `mcp.json`):
   ```json
   {
     "mcpServers": {
       "mctl": {
         "type": "http",
         "url": "https://api.mctl.ai/mcp"
       },
       "upwork": {
         "type": "stdio",
         "command": "uv",
         "args": ["run", "upwork-mcp"]
       }
     }
   }
   ```

2. **Antigravity / Gemini CLI Schema** (`~/.gemini/config/mcp_config.json`):
   - **Remote SSE / HTTP**:
     ```json
     {
       "mcpServers": {
         "mctl": {
           "serverUrl": "https://api.mctl.ai/mcp"
         }
       }
     }
     ```
   - **Local Stdio Wrapper**:
     ```json
     {
       "mcpServers": {
         "my-tool": {
           "command": "/path/to/wrapper-script"
         }
       }
     }
     ```

---

## Step-by-Step Diagnostic & Recovery Flow

### 1. Handling `Unauthorized [Auth Needed]` & OAuth 2.0 PKCE Flow

When a remote MCP endpoint requires OAuth 2.0 with strict PKCE (`code_challenge` + `code_challenge_method=S256`), manual URL links missing PKCE params will fail with:
`{"error":"invalid_request","error_description":"PKCE S256 is required"}`.

**Procedure for Automated PKCE Authentication**:

1. **Register OAuth Client Dynamically**:
   ```python
   import requests
   reg = requests.post("https://<server-domain>/oauth/register", json={
       "client_name": "mcp-client",
       "redirect_uris": ["http://localhost:12105/callback"]
   }).json()
   client_id = reg["client_id"]
   ```

2. **Generate PKCE S256 Pair**:
   ```python
   import os, base64, hashlib
   verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').replace('=', '')
   challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('utf-8')).digest()).decode('utf-8').replace('=', '')
   ```

3. **Construct Clean Authorization URL**:
   ```text
   https://<server-domain>/oauth/authorize?response_type=code&client_id=<client_id>&redirect_uri=http%3A%2F%2Flocalhost%3A12105%2Fcallback&scope=<scopes>&code_challenge=<challenge>&code_challenge_method=S256
   ```

4. **Launch One-Shot Callback Listener & Exchange Code**:
   Start a temporary local HTTP server on `http://localhost:12105/callback`. When the browser redirects back with `?code=...`, perform the `POST /oauth/token` exchange with `code_verifier=verifier`.

5. **Store Tokens in Client Token Repositories**:
   Save the resulting tokens into **BOTH** client token locations to support all runtimes and surface `✓ [Authed]` and `[Sign Out]` in the CLI:

   - **Antigravity CLI Token Repository** (`~/.gemini/antigravity-cli/mcp_oauth_tokens.json`) - *Map keyed by serverUrl*:
     ```json
     {
       "https://<server-domain>/mcp": {
         "client_id": "<client_id>",
         "token": {
           "access_token": "<access_token>",
           "token_type": "Bearer",
           "refresh_token": "<refresh_token>",
           "expiry": "2030-01-01T00:00:00Z"
         },
         "token_url": "https://<server-domain>/oauth/token"
       }
     }
     ```

   - **Legacy / Standalone Token Repository** (`~/.gemini/mcp-oauth-tokens.json`) - *Array format*:
     ```json
     [
       {
         "serverName": "<server_name>",
         "token": {
           "accessToken": "<access_token>",
           "tokenType": "Bearer",
           "scope": "<scopes>",
           "expiresAt": 1790000000000
         },
         "clientId": "<client_id>",
         "tokenUrl": "https://<server-domain>/oauth/token",
         "mcpServerUrl": "https://<server-domain>/mcp",
         "updatedAt": 1786051830000
       }
     ]
     ```

> [!IMPORTANT]
> **Native HTTP vs Stdio Command**: Configure remote HTTP servers in `mcp_config.json` with `"serverUrl": "https://<server-domain>/mcp"` (NOT `"command"` wrapper). When paired with an entry in `~/.gemini/antigravity-cli/mcp_oauth_tokens.json`, Antigravity CLI sends the Bearer token natively, recognizes the OAuth session, and displays `✓ [Authed]` and `[Sign Out]`.

---

### 2. Resolving Lingering Process Locks (`context deadline exceeded`)

If a remote proxy process (e.g. `mcp-remote`) crashes or hangs, it holds open local sockets and ports, causing new CLI connection attempts to fail with `context deadline exceeded`.

**Recovery**:
1. Check for stale processes: `ps aux | grep mcp-remote`
2. Kill stale instances: `kill -9 <PID>`
3. Check and free occupied callback ports: `lsof -i :<PORT> | awk 'NR>1 {print $2}' | xargs kill -9`

---

### 3. Transport Selection & Diagnostic Log Redirection

Avoid piping raw unbuffered logs to `stderr` in stdio wrappers, as unhandled log lines interfere with the initial JSON-RPC handshake causing `EOF` or `client is closing`.

**Best Practice Wrapper Pattern**:
```bash
#!/bin/bash
exec /opt/homebrew/bin/mcp-remote "https://<server-domain>/mcp" 2>/tmp/mcp-<server>.log
```

---

### 4. Telegram Preview & `WWW-Authenticate` Header Requirements

When configuring remote MCP endpoints (such as `https://tg-preview.mctl.ai/mcp`), clients rely on standard HTTP 401 response headers to trigger interactive login flows (surfacing **[Sign In]** buttons instead of connection failures):

1. **401 Unauthorized Response**: Unauthenticated requests to `/mcp` must return HTTP `401 Unauthorized` with the header:
   ```http
   WWW-Authenticate: Bearer realm="mctl-telegram", error="invalid_token"
   ```
2. **Dynamic Preview Auth Routing**: In preview environments (`tg-preview.mctl.ai`), ensure JWT issuer validation dynamically respects the preview hostname and scope list.

---

### 5. Context7 MCP & CLI Setup

Context7 provides documentation context via CLI and MCP stdio integration:

1. **CLI Authentication**:
   ```bash
   ctx7 login
   # Stores API key (ctx7sk-*) in macOS Keychain under service 'context7'
   ```

2. **MCP Configuration in `~/.gemini/settings.json`**:
   ```json
   {
     "mcpServers": {
       "context7": {
         "command": "npx",
         "args": ["-y", "@upstash/context7-mcp"]
       }
     }
   }
   ```
