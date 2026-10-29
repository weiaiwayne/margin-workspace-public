# Operations

## Updates

Keep a private backup first. Review release changes, then in the installed checkout:

```bash
cd /opt/margin-workspace
sudo git pull --ff-only
sudo .venv/bin/pip install -r requirements.txt
sudo systemctl restart margin-broker.service
sudo systemctl kill --kill-whom=main --signal=HUP margin.service
```

Do not rerun the fresh installer for updates. Service-unit changes need review and an explicit copy plus `systemctl daemon-reload`; schema/config migrations, if needed, belong in the release instructions. Keep local configuration under `/etc/margin`, not in the checkout. If your installer copied the code from elsewhere without `.git`, update from a reviewed source checkout while preserving `.venv` and runtime data. Never point updates at a private deployment repository.

## Backups

The database is authoritative for accounts, threads, permissions, document history and Trash metadata. Exported review Markdown is a snapshot, not a complete account/database backup.

Back up the database with SQLite's online backup API (a raw copy of a live WAL file can lose data):

```bash
sudo install -d -m 700 /var/backups/margin
sudo /opt/margin-workspace/.venv/bin/python -c 'import sqlite3; a=sqlite3.connect("file:/var/lib/margin/margin.sqlite?mode=ro",uri=True); b=sqlite3.connect("/var/backups/margin/margin.sqlite"); a.backup(b); b.close(); a.close()'
sudo chmod 600 /var/backups/margin/margin.sqlite
```

Also back up `/etc/margin`, each source project including hidden `.reviews` and `.margin-trash`, `/var/lib/margin/source-history` if present, and service/proxy configuration. Preserve ACLs and ownership, encrypt off-server copies, and test restoration. For a consistent full snapshot, stop the app and broker while backing up all related files; coordinate with external agents editing those files. Do not commit backups to Git.

Restore with both services stopped, restore files/configuration and ownership/ACLs, then start services and check login, workspace boundaries, document edits, comments and export. Never overwrite live data without an explicit recovery decision.

## Accounts and recovery

Administrators create invitations, reset passwords, disable accounts, and grant shared-workspace access through **Manage people**. Invitation links expire after three days and can be used once. If every administrator is locked out, use the CLI to create a *new*, uniquely named recovery administrator, activate it privately, then reset the original administrator. The CLI refuses to overwrite an existing account. Disable the recovery account afterwards.

New private workspaces belong to their administrator owner. The default shared workspace can be assigned to collaborators. Converting a private workspace into a shared workspace is not currently a UI feature; do not manually weaken its owner checks.

## Local coding agents

Browser accounts and Linux accounts are separate. A coding agent must have filesystem access to its assigned workspace, and its own sandbox must include that path. Do not grant it the `margin` group, broker socket, all projects, or the application's database.

For an existing dedicated Linux login account:

```bash
sudo /opt/margin-workspace/.venv/bin/python /opt/margin-workspace/deploy/agent-access.py --project shared --agent YOUR_LINUX_AGENT_ACCOUNT --role write
```

Use the actual project ID from `config.json` or `workspaces.json`. `read` grants review access; `write` additionally allows editing source documents. Review exports remain read-only for non-owner agents. The tool backs up config/database/ACLs and repairs permissions only within the selected workspace. It is a grant/repair tool, not a full revocation workflow. Never invoke it without arguments unless you deliberately want to grant the root operator on current/future workspaces.

A non-root account also needs traversal of the parent path. Use a scoped mount or dedicated project directory instead of opening unrelated home directories. An unrestricted host-root agent is not isolated by ACLs; enforce its workspace scope with the agent's sandbox or a separate container/account.

## Storage and privacy

The default managed quota is 1 GiB per workspace, including Trash. For existing-folder workspaces it covers the writable `workspace/` area, not every existing source file. Raise `storage_limit_bytes` deliberately, while retaining disk headroom for the database, histories, PDF conversion and backups. The app is intended for trusted teams, not anonymous unlimited hosting.

Privacy text is shown in the UI. Documents, comments, names, password hashes, sessions, invitations, and file history live on your server. Your server operator can access them. Sharing/exporting is deliberate; review exports can be read by anyone who already has filesystem access to that project. There is no automatic AI processing or email delivery.
