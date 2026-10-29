# Security and privacy

Margin is intended for small trusted teams on a maintained private server. It is invitation-only, uses hashed passwords, server-side sessions, CSRF checks, sanitized Markdown, workspace authorization, restricted filesystem paths, and HTTPS in production. These controls are not a guarantee against compromise.

Keep the operating system and dependencies current, restrict SSH, use strong unique passwords, and back up private state. MFA/SSO are not built in; use a trusted access proxy if required. Do not expose the loopback application port or Unix broker socket to the network. The root folder broker is privileged; only administrators can request provisioning and only explicitly allowlisted project parents should be offered.

Do not put secrets in visible project documents. Hidden files, symlinks, generated review files, and excluded development directories are filtered, but this is not a secret scanner. CLI agents are separate processes with their own permissions. An unrestricted root process can access all server data.

Public source does not contain deployment configuration, accounts, databases or invitation links. The localhost example is not a production config. Keep runtime files and backups out of Git. If you discover a vulnerability, use GitHub's private vulnerability reporting if enabled, or contact the repository owner privately. Do not post credentials, exploit data, private documents or user information in a public issue.

See `docs/OPERATIONS.md` for backups and data-handling details and the app's Privacy dialog for user-facing statements.
