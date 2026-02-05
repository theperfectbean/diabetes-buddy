LLM provider abstraction: migration & test-hygiene fixes
=====================================================

Summary
-------
This branch implements a provider-agnostic LLM abstraction and supporting changes:

- Adds `agents/llm_provider.py` providing `LLMProvider`, concrete providers (`GeminiProvider`, `OpenAIProvider`, etc.), and `LLMFactory`.
- Implements local embedding fallback (sentence-transformers) for environments without remote embeddings.
- Migrates agents to use the provider API (`generate_text`, `embed_text`, `upload_file`, `get_file`).
- Adds test-hygiene fixes: guarded script-like tests, `tests/conftest.py`, and `pytest.ini` registration for `integration` marker.
- Adds documentation: `docs/LLM_PROVIDER_MIGRATION.md` and `README_BUNDLE.md` for an offline git bundle.
- Prepared offline transfer artifacts: `llm_provider_migration.bundle`, `patches/`, and `llm_provider_migration_package.tar.gz`.

Local test results
------------------
- Ran full test suite locally: `pytest -q` — all tests passed in the developer environment.
- Note: Some environments may need `requirements-extras.txt` for optional deps (sentence-transformers). See docs.

Files of interest
-----------------
- `agents/llm_provider.py` — core abstraction and providers
- `tests/test_llm_provider_switching.py` — provider switching tests
- `docs/LLM_PROVIDER_MIGRATION.md` — migration guide and testing notes
- `README_BUNDLE.md` & `llm_provider_migration.bundle` — offline transport
- `pytest.ini` — registers `integration` marker for heavy tests

How to publish (local steps)
---------------------------
1. Add a remote (if not already configured):

```bash
git remote add origin git@github.com:<OWNER>/<REPO>.git
```

2. Push the branch and set upstream:

```bash
git push -u origin feature/llm-provider-migration-202601301401
```

3. Create a PR (using `gh`):

```bash
gh pr create --title "LLM provider abstraction: migration & test-hygiene fixes" \
  --body "See PR_DESCRIPTION.md for details. Local tests passed: pytest -q." \
  --base master --head feature/llm-provider-migration-202601301401 --fill
```

Offline import (if using the bundle)
-----------------------------------
1. Transfer `llm_provider_migration_package.tar.gz` to the target host.
2. Extract and restore the bundle:

```bash
tar -xzf llm_provider_migration_package.tar.gz
gzip -d llm_provider_migration.bundle.gz
git clone llm_provider_migration.bundle my-repo
cd my-repo
```

Notes
-----
- This environment does not have remote git push access configured; pushing to a remote must be done locally where credentials exist.
- If you want, run the push/PR commands above locally or provide remote credentials and I can push from here.
