# Security Policy

## Supported versions

Security fixes are applied to the latest code on the default branch (`master`). If you are self-hosting from an older commit, please upgrade before reporting unless the issue is still reproducible on `master`.

## Reporting a vulnerability

Please **do not** open a public GitHub Issue for security vulnerabilities.

Prefer one of the following:

1. **GitHub Security Advisories** — on [cnwinds/lore-chat](https://github.com/cnwinds/lore-chat), use **Security → Report a vulnerability** (private disclosure).
2. If Advisories are unavailable, open a private channel with the maintainers via the repository contact / owner profile on GitHub.

Include as much of the following as you can:

- Description of the issue and impact
- Steps to reproduce (PoC if available)
- Affected component (e.g. API route, auth, sandbox, Docker deploy)
- Lore Chat commit SHA or image tag you tested against

You should receive an acknowledgement within **7 days**. We will coordinate a fix and disclosure timeline with you. Please give us a reasonable window to ship a patch before public discussion.

## Scope notes for this project

- API keys and secrets belong in local `.env` files (never commit them). See `.env.docker.example` and `backend/.env.example`.
- Runtime knowledge-base data under `docker/data/` and `backend/knowledge/` is local/private; do not include personal KB contents in bug reports unless redacted.
- Sandbox / command execution (`SANDBOX_ENABLED`) expands the attack surface; report sandbox escape or trust-mode bypasses as high priority.
