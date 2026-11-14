# Security Policy

This repository is a research showcase: it contains the implementation, tests, documentation and
evaluation artifacts of MFG-AgentGraph. Nothing here is intended to hold production credentials or
personal data, and it is not deployed as a service.

## Reporting

Please report a security issue privately rather than opening a public issue — use GitHub's
"Report a vulnerability" advisory flow on this repository, or contact the owner directly.

Include the affected file or workflow, what is exposed, and a suggested remediation if you have one.
Please do not include working credential values in a report.

## Rules for contributors

- Never commit real secrets, tokens, passwords, API keys, SSH keys or credential-store contents.
  Keep them in local `.env` files or CI secrets, never in tracked files.
- Do not paste credential values into issues, pull requests, commit messages, screenshots or logs.
  Redact them in status updates.
- Local service endpoints in this repository are loopback-only (`127.0.0.1`/`::1`). The pinned
  development stack is unauthenticated for data-plane access and is meant for a single operator on
  one workstation, never for a shared or public host.

## If a secret is committed

1. Revoke and rotate it immediately — assume it is compromised.
2. Remove it from the working tree.
3. Treat the exposed value as unusable, then clean history if the repository will be shared further.
4. Document the incident without preserving the secret value.
