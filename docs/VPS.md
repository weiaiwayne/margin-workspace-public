# VPS installation

The fresh-install script targets Ubuntu 24.04 and Debian 12 or newer with Python 3.11+, apt, systemd, nginx, and a domain pointing to the server. The core app can run elsewhere; the privileged folder broker and supplied service isolation are Linux/systemd-specific. The release's backend tests and disposable browser flows have been exercised; a clean install on every provider/OS image is not claimed.

## Before you install

- Point the hostname's A record to the VPS. Remove a stale AAAA record or configure IPv6 and nginx listeners correctly before certificate issuance. The supplied nginx template listens on IPv4; add IPv6 listeners if you publish an AAAA record.
- Allow inbound 80/443 at both provider and host firewall. Retain SSH. The app itself stays on `127.0.0.1:8766`.
- Use a hostname not already served by another application. The installer writes only its own `margin-<hostname>` nginx site and refuses obvious hostname collisions. Have your agent inspect other proxy configurations, including `conf.d`, before installation.
- Review existing local users and services named `margin` or `margin-broker`; do not reuse an unrelated service identity.
- Run `python3 deploy/install.py --domain margin.example.com --email you@example.com --plan` without sudo to preview.

The installer uses apt for Python, nginx, certbot, ACL tools, fonts and Pango libraries; it installs pinned Python packages in `/opt/margin-workspace/.venv`. It creates an unprivileged `margin` account and a local root broker reachable only over a restricted Unix socket. HTTPS login is not exposed until certificate issuance succeeds.

The script accepts `--username`, `--name`, and repeatable `--allow-root /srv/projects`. An allowed root must already exist, except the built-in `/srv/margin-projects`. Connect its child project folders from the UI. Do not expose `/`, credential directories, or broad system trees.

## Paths and services

| Item | Default |
|---|---|
| Source/venv | `/opt/margin-workspace` |
| App config | `/etc/margin/config.json` |
| Folder broker config | `/etc/margin/broker.json` |
| Private workspace registry | `/etc/margin/workspaces.json` |
| Database | `/var/lib/margin/margin.sqlite` |
| Initial shared documents | `/srv/margin-projects/shared` |
| Web service | `margin.service`, loopback port 8766 |
| Folder broker | `margin-broker.service`, `/run/margin-broker/control.sock` |
| HTTPS proxy | `/etc/nginx/sites-available/margin-<hostname>` |

The web service has a read-only filesystem with explicit writable data and workspace mounts. The broker provisions project ACLs and systemd mounts and restarts the web service when a folder is connected; the browser retries this connection automatically. Keep its socket restricted to the service, and do not assign other users to the `margin` group.

## Existing reverse proxy / manual installation

Do not run the fresh installer over an existing Margin configuration. For Caddy, Apache, or an existing nginx site, your coding agent should:

1. Install the dependencies listed in `deploy/install.py`, create the service identity, and place the code in `/opt/margin-workspace` with a dedicated venv.
2. Generate configurations using `configuration(domain, allowed_roots)` in the installer, adapting only reviewed paths. Keep the JSON files root-owned (`config.json`/registry group-readable by `margin`, broker config root-only).
3. Create the shared source folder and state directory, owned by `margin`; install both supplied units and create the systemd drop-in directory. Ensure all application/venv parent directories are traversable by the service user. Avoid recursive permission changes to existing projects.
4. Proxy the HTTPS host root to `127.0.0.1:8766`, preserve Host and set trusted forwarding headers. Keep `secure_cookie=true`, `proxy=true`, a narrow `hosts` list, and a matching HTTPS `public_url`. Never trust a publicly reachable direct app port.
5. Create the admin with `runuser -u margin -- /opt/margin-workspace/.venv/bin/python /opt/margin-workspace/app.py --config /etc/margin/config.json --username admin --name Administrator`. Return the resulting setup link privately.
6. Start services, validate HTTPS and permissions, and configure certificate renewal using the selected proxy's normal mechanism.

For nginx, `nginx(domain, tls=True)` in the installer renders the root-location configuration. Retain streaming uploads, generous proxy timeouts, and workspace storage quotas. Do not expose login over plain HTTP.

## Troubleshooting and interrupted installation

- **DNS/certificate failure:** fix DNS/firewall first. The installer leaves its own HTTP challenge site returning 503 for the app. Before configuration/shared-folder creation, rerunning the same command can resume certificate setup. Do not delete existing user data to bypass a preflight check.
- **An installation already exists:** use the update guide. If a first install stopped after writing configuration, inspect `journalctl -u margin -u margin-broker`, complete the remaining service/TLS steps manually, and preserve the database. If an admin already exists, do not rerun account creation or reset them silently.
- **502:** check `systemctl status margin margin-broker` and the journal. Inspect configuration errors, directory traversal permissions, port conflicts, and dependency installation.
- **Cannot connect folder:** confirm its parent is allowlisted; symlinks, hidden folders, protected service paths, and overlapping workspaces are intentionally refused.
- **Cannot read comments from a CLI agent:** follow the per-workspace ACL instructions in `OPERATIONS.md`; never use `chmod -R 777`.
- **PDF export:** check native Pango/Harfbuzz/fonts and the 2 MiB Markdown limit. Conversion has time/memory limits and may reject very complex documents.

Native-library guidance: [WeasyPrint installation](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html). Certificate challenge/renewal guidance: [Certbot user guide](https://eff-certbot.readthedocs.io/en/stable/using.html).
