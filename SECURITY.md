# Security Policy

## Supported versions

Security fixes are applied to the latest release on the default branch.

| Version | Supported |
| --- | --- |
| Latest `main` / most recent release | Yes |
| Older tags and forks | No |

## Reporting a vulnerability

Please do not open public GitHub issues for security reports.

Use one of these private channels:

1. Open a GitHub Security Advisory for this repository.
2. If advisories are unavailable, contact the maintainer through the repository owner profile and include "Security report" in the subject or first line.

Include:

- A clear description of the issue and affected component.
- Steps to reproduce.
- Expected impact.
- Any proof-of-concept details needed to verify the report.

## Response targets

- Initial acknowledgment: within 72 hours.
- Triage update: within 7 calendar days.
- Remediation target for confirmed high-severity issues: as quickly as practical, with status updates when timelines change.

## Disclosure expectations

- Please give maintainers a reasonable amount of time to investigate and ship a fix before public disclosure.
- Coordinate disclosure timing for vulnerabilities that could expose API credentials, query payloads, or remote execution surfaces.

## Data handling notes

BioMCP brokers requests to third-party biomedical APIs. Depending on the tool, user prompts and query parameters may be sent to upstream services such as NCBI, UniProt, Reactome, NVIDIA NIM, or other configured providers.

Operational notes:

- Environment variables are read locally by the server process and are not returned in tool output.
- HTTP health endpoints expose server capability status but should not expose secrets.
- Query results may be cached in memory for performance. Cache contents are process-local and are cleared when the process restarts.
- Session intelligence features can retain in-process research context and provenance until the server process exits or the session is reset.

Before deploying a public instance, review logging, reverse-proxy access logs, and host retention settings to ensure they match your privacy requirements.
