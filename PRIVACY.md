# Privacy Policy

Heuris-BioMCP processes only the inputs required to fulfill tool calls and return structured responses to the connected MCP client.

## What Data Is Processed

- Tool inputs sent by the MCP client, including queries, identifiers, free text, and workflow parameters.
- Tool outputs produced by Heuris-BioMCP and upstream scientific data providers.
- Basic operational telemetry needed to keep the service healthy, such as timestamps, request paths, latency, and error summaries.

## How Data Is Used

- To execute requested BioMCP tools and stream results back to the client.
- To diagnose failures, rate-limit abuse, and improve reliability.
- To maintain short-lived in-memory caches that reduce repeated provider calls.

## What Is Not Sold

- Heuris-BioMCP does not sell user data.
- Heuris-BioMCP does not use tool inputs or outputs for advertising.

## Retention

- In-memory cache entries expire according to source-specific TTLs.
- Saved research sessions persist only if `BIOMCP_SESSION_STORE_DIR` points to durable storage.
- On ephemeral hosts such as Render free-tier instances, saved sessions can disappear after restart or deploy.
- Reverse-proxy, platform, and host logs may retain request metadata outside this repository's control.

## Third-Party Processing

Tool execution can send request data to external providers such as NCBI, Reactome, UniProt, ClinicalTrials.gov, and NVIDIA NIM, depending on the tool being used. Those providers apply their own privacy and retention policies.

## Security

Security disclosures and handling expectations are documented in [SECURITY.md](SECURITY.md).

## Contact

Support and operational questions should go through the channels in [SUPPORT.md](SUPPORT.md).
