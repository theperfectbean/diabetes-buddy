LLM Provider Migration — Bundle README
===================================

This repository contains a git bundle of the current feature branch implementing an LLM provider
abstraction and test-hygiene fixes. The bundle file is named `llm_provider_migration.bundle` and
is located at the repository root.

Quick notes
- The bundle contains the branch: `feature/llm-provider-migration-$(date +%Y%m%d%H%M)` as created locally.
- Bundle filename: `llm_provider_migration.bundle` (approx 40MB in this run).

Importing the bundle into a new repo

Method A — create a new clone directly from the bundle:
```bash
git clone llm_provider_migration.bundle my-repo
cd my-repo
git log --oneline --decorate --graph -n 10
```

Method B — initialize an empty repo and pull the branch from the bundle:
```bash
mkdir my-repo && cd my-repo
git init
git remote add origin <REMOTE-URL>  # optional: set if you plan to push later
git pull ../llm_provider_migration.bundle $(git bundle list-heads ../llm_provider_migration.bundle | awk '{print $2}')
```

After importing
- Verify the active branch with `git branch --show-current`.
- Run tests locally (recommended inside the virtualenv):
```bash
source .venv/bin/activate
pip install -r requirements-core.txt
pytest -q
```

Pushing to a remote (if you have hosting)
```bash
git remote add origin git@github.com:<OWNER>/<REPO>.git
git push -u origin $(git rev-parse --abbrev-ref HEAD)
```

If you want, I can also add a small note to `docs/LLM_PROVIDER_MIGRATION.md` linking to this bundle. 

Contact / provenance
- Created locally on: Jan 30, 2026
- Creator: repository maintainer (local machine)
