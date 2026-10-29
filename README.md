# Margin Workspace

**Read, edit, and discuss your Markdown files on your own VPS.** Margin gives project folders a familiar document workspace: formatted editing, highlighted comments, shared reviews, uploads, folders, and PDF previews. Your documents remain ordinary files that your coding agents can read.

By **LampBotics AI Lab**. Self-hosted, invitation-only, with no external AI service, analytics, or document-storage account required. MIT licensed; bundled third-party components retain their own licenses.

## Easiest setup: give this prompt to your coding agent

Open your CLI coding agent on the VPS, paste this prompt, and replace the three bracketed values. Your agent needs SSH/sudo access. A domain is required for the standard HTTPS setup; create its DNS A record pointing to your VPS first. If you have an AAAA record, it must also point to this server.

```text
Install Margin Workspace on this VPS from:
https://github.com/weiaiwayne/margin-workspace-public

My hostname: [margin.example.com]
Certificate contact email: [you@example.com]
Administrator username: [admin]

Read README.md, docs/AGENT_SETUP.md, and docs/VPS.md from the repository first.
Inspect the OS, available ports, DNS, and existing web services. Preserve every
existing application, project, account, and document. Never overwrite an existing
Margin installation or open project folders to all users.

On a supported Ubuntu/Debian VPS, clone to /opt/margin-workspace, preview
`python3 deploy/install.py --plan` with my domain/email/username, then run the
installer with sudo. If this server already has a reverse proxy or the hostname
is in use, integrate safely using the documented configuration instead of replacing it.

Use HTTPS, keep the app on loopback, and leave public registration disabled.
Give me the private one-time setup link so I choose my password; do not invent,
commit, or log a password. Explain any DNS action I must perform.

Start with the shared workspace at /srv/margin-projects/shared. Ask which
additional project-parent directories I want available before adding them to
the broker allowlist. Keep other workspaces private unless I explicitly share them.

Verify HTTPS, the service, login/setup, creating a disposable Markdown file,
comment export, folder navigation, and PDF export. Remove test fixtures.
Show me the URL, how to invite collaborators, how to connect an existing folder,
and how to back up and update the installation. Do not commit any runtime data,
configuration, invitation links, or secrets to GitHub.
```

The complete [agent setup guide](docs/AGENT_SETUP.md) includes verification and recovery steps. The agent installs the application; Margin does not require an agent or API subscription to run.

## Manual quick start

The installer targets **Ubuntu 24.04 / Debian 12 or newer**, Python 3.11+, systemd, and nginx. Use a VPS with at least **2 GB RAM and adequate disk space** as a starting point for a small team; PDF exports and larger workloads need more resources. Existing Caddy/Apache or non-systemd hosts need an adapted deployment; see [VPS setup](docs/VPS.md).

```bash
sudo apt-get update
sudo apt-get install -y git python3
sudo git clone https://github.com/weiaiwayne/margin-workspace-public.git /opt/margin-workspace
cd /opt/margin-workspace
python3 deploy/install.py --domain margin.example.com --email you@example.com --username admin --plan
sudo python3 deploy/install.py --domain margin.example.com --email you@example.com --username admin
```

Allow inbound **80 and 443** in the VPS/provider firewall while retaining SSH access. The installer installs dependencies, creates system services, obtains a Let's Encrypt certificate, and prints a **private, single-use setup link** valid for three days. Open it and choose your password. There is no default password. Do not paste the setup link into public issues or logs.

The installer is for **fresh installations** and refuses to overwrite an existing Margin configuration. It never changes your firewall automatically. Review the preview and [installation details](docs/VPS.md) before running it on a shared server.

## Your first workspace

1. Open your HTTPS URL and activate your administrator account.
2. The **Shared workspace** starts at `/srv/margin-projects/shared`.
3. Use **Manage people** to create invitations and grant access to that shared workspace. Send the invitation links yourself; Margin does not send email.
4. Use **Manage workspaces** to create a private workspace or connect an existing folder under an allowed project parent. New private workspaces are visible only to their administrator owner.
5. Create a Markdown/text document, or upload files. Select text to comment, click a comment to revisit its passage, and right-click files/folders for actions. Mobile users can use the **···** menus.
6. Click **Save comments to project**, then copy the **Prompt to send to your building agent** shown below the document.

Existing-folder workspaces let you edit existing Markdown/text documents; new uploads and folders go into that folder's `workspace/` subfolder. Newly created workspaces are editable throughout. Browser collaborators are not automatically granted Linux/SSH accounts. See [agent filesystem access](docs/OPERATIONS.md#local-coding-agents).

## Features

- Markdown and plain-text editing, formatting controls, source mode, and revision-conflict checks.
- Passage comments, replies, resolved history, and agent-readable `.reviews/*.review.md` exports.
- Upload/download, folder creation, file/folder rename, recoverable Trash, and storage display.
- Local PDF preview and Markdown-to-PDF download from a file's context menu.
- Automatic file refresh and connection recovery when adding a workspace.
- Invitation-only accounts, per-workspace authorization, HTTPS cookies, CSRF protection, and login throttling.
- Mobile layouts, touch menus, and accessible connection/status messages.

Editing is **not simultaneous Google Docs co-editing**: saves check revisions to prevent overwriting someone else's edits. The default managed-storage quota is **1 GiB per workspace**, including Trash. Uploads use available quota; Markdown/text editing and Markdown-to-PDF conversion have a **2 MiB source limit**. The file index is capped at 10,000 files. No SSO, MFA, automatic email, Git synchronization, or automatic agent execution is included.

## How comments reach an agent

For `plans/example.md`, Margin exports comments to `.reviews/plans/example.md.review.md`. The export includes quoted passages, source hashes, reviewer names, replies, and resolved history. Posting a comment saves it in the database immediately; **Save comments to project** writes the agent-readable snapshot.

An example prompt:

> Read `plans/example.md` and `.reviews/plans/example.md.review.md`. Preserve human edits and resolved history. Check quoted passages against the current file, address open comments, and report what changed. If a file is unreadable, report its path rather than assuming it has no comments.

## Improve Margin with your coding agent

Found a bug or want a new feature? Ask your CLI coding agent to update Margin. Agent-assisted contributions are welcome: review and test the changes, push them to your fork, and open a pull request to this public repository. See [Contributing](CONTRIBUTING.md) for a ready-to-copy prompt. Direct pushes require maintainer access.

## Administration and development

- [VPS deployment and troubleshooting](docs/VPS.md)
- [Updates, backups, recovery, and local-agent access](docs/OPERATIONS.md)
- [Security and privacy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

The application uses Flask, SQLite, Gunicorn, vanilla JavaScript, Tiptap, PDF.js, and WeasyPrint. Browser assets are included, so Node.js is unnecessary for normal installation. Rebuilding the rich-text editor requires `npm ci && npm run build`.

For development, copy `config.example.json` to `config.json`, create its local `workspace` directory, install `requirements.txt` in a virtualenv, and run:

```bash
python app.py --config config.json --username admin --name Administrator
MARGIN_CONFIG=config.json python -m gunicorn --bind 127.0.0.1:8765 wsgi:app
```

The example config deliberately uses HTTP cookies only for **localhost development**. The VPS installer generates a separate HTTPS-only production config. Keep runtime files out of Git.
