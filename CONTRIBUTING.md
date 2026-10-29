# Contributing

Contributions made with CLI coding agents are welcome. Ask your agent to fix a bug, improve the interface, or add a feature. You remain responsible for reviewing the change and verifying that it works.

Fork this public repository, work on a branch, and ask your agent to push to your fork and open a pull request here. Direct pushes to this repository require maintainer access; contributions are reviewed before merging. Never publish your deployment configuration or users’ documents and comments.

## Prompt for your coding agent

```text
Help me improve Margin Workspace:
https://github.com/weiaiwayne/margin-workspace-public

Requested change: [describe the bug or feature]

Read CONTRIBUTING.md and the relevant code. Work in a development checkout
on a feature branch, preserving my live installation and all user data.
Implement the change, run relevant tests with disposable fixtures, and explain
what changed and how you verified it. Review the diff for secrets and private data.
Push the branch to my fork and open a pull request against the public repository
with a clear description and test results. Do not deploy to my live instance
unless I explicitly ask.
```

## Validation

Run backend tests against disposable directories, never a production database:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
node --check static/app.js
```

Some ACL tests need Linux ACL tools and suitable privileges. Browser workflow tests need Playwright and Chromium; install them into the development environment and use scripts that create temporary fixtures. `browser_smoke.py` expects a separately prepared local preview and must never target live user data.

Keep sample projects and accounts generic. Do not include private deployments, project names, domains, absolute personal paths, credentials, screenshots of user data, database dumps, or invitation links. Keep generated vendor-license notices when rebuilding assets. This repository has its own public history; do not merge a private deployment repository into it.

Maintainers publish common application changes to both their development repository and this public distribution. Public-specific installation and documentation live here. A release must retain neutral examples, pass a private-reference/credential check, and pass relevant tests before pushing. Document any migrations and do not silently reset accounts or permissions.
