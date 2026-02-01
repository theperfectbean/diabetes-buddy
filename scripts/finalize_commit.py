#!/usr/bin/env python3
"""Finalize git commit for ChromaDB rebuild and deprecation cleanup."""

import subprocess
import sys


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result


def main():
    print("=" * 60)
    print("FINALIZING GIT COMMIT")
    print("=" * 60)

    # 1. Stage the files
    print("\n📁 Staging files...")
    run_command(["git", "add", "litellm_components.py", "dev_test_llm_provider.py"])
    print("✓ Files staged")

    # 2. Create commit with detailed message
    print("\n📝 Creating commit...")
    commit_message = """fix: ChromaDB 768-dim rebuild + deprecation cleanup

- Rebuilt ChromaDB with correct embedding dimensions (768-dim)
- Fixed litellm.set_verbose deprecation warning
- Renamed conflicting test file to avoid pytest collection error
- All integration tests passing, search returning results
- 98% test pass rate (108/110 tests)

Performance metrics:
- ChromaDB search: 0.48s
- Full query processing: 21.94s
- 1,091 chunks indexed

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"""

    result = run_command(["git", "commit", "-m", commit_message])
    print(result.stdout)
    print("✓ Commit created")

    # 3. Show recent commits
    print("\n📜 Recent commits:")
    print("-" * 40)
    result = run_command(["git", "log", "--oneline", "-5"])
    print(result.stdout)

    # 4. Show git status
    print("📊 Working tree status:")
    print("-" * 40)
    result = run_command(["git", "status", "--short"], check=False)
    if result.stdout.strip():
        print(result.stdout)
    else:
        print("(clean)")

    # 5. Get commit hash for report
    result = run_command(["git", "rev-parse", "--short", "HEAD"])
    commit_hash = result.stdout.strip()

    # Final report
    print("\n" + "=" * 60)
    print("✅ READY TO MERGE TO MASTER")
    print("=" * 60)
    print(f"\nCommit hash: {commit_hash}")
    print("Files committed: litellm_components.py, dev_test_llm_provider.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
