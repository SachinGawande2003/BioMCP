# Data Processing

This document summarizes how Heuris-BioMCP handles query data in hosted deployments.

## Processing Model

- Heuris-BioMCP executes scientific lookups and workflow composition on behalf of an MCP client.
- Tool inputs and tool outputs may be transmitted to upstream providers required for the requested workflow.
- The server may keep short-lived in-memory caches to reduce duplicate upstream requests.

## Hosted Deployment Notes

- `session.save` writes to `BIOMCP_SESSION_STORE_DIR`.
- If `BIOMCP_SESSION_STORE_DIR` is unset in HTTP mode, saved sessions default to local disk under `.biomcp_sessions`.
- On ephemeral platforms such as Render free tier, that storage is not durable across restart or redeploy.

## Recommended Controls

- Set `BIOMCP_SESSION_STORE_DIR` to durable storage before relying on saved sessions.
- Configure `BIOMCP_HTTP_RATE_LIMIT_REQUESTS` and `BIOMCP_HTTP_RATE_LIMIT_WINDOW_SECONDS` for abuse control.
- Set `BIOMCP_CORS_ALLOW_ORIGINS` explicitly if browser access is required.
- Review host and reverse-proxy log retention separately from application behavior.
