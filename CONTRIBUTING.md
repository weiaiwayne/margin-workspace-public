# Contributing

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
