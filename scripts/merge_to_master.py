#!/usr/bin/env python3
"""Merge feat/litellm-refactor branch into master."""

import subprocess
import sys


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr and result.returncode != 0:
        print(f"stderr: {result.stderr}")
    if check and result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        return result
    return result


def main():
    print("=" * 60)
    print("MERGING feat/litellm-refactor INTO master")
    print("=" * 60)

    # Track state for summary
    commits_to_merge = 0
    merge_hash = None
    conflicts = False

    # 1. Show current branch
    print("\n📍 Current branch:")
    print("-" * 40)
    run_command(["git", "branch", "--show-current"])

    # 2. Show commits that will be merged
    print("\n📋 Commits to be merged:")
    print("-" * 40)
    result = run_command(["git", "log", "--oneline", "master..feat/litellm-refactor"])
    if result.stdout:
        commits_to_merge = len(result.stdout.strip().split('\n'))
    print(f"({commits_to_merge} commits)")

    # 3. Checkout master
    print("\n🔀 Checking out master branch...")
    print("-" * 40)
    result = run_command(["git", "checkout", "master"])
    if result.returncode != 0:
        print("❌ Failed to checkout master")
        sys.exit(1)
    print("✓ On master branch")

    # 4. Perform the merge
    print("\n🔗 Merging feat/litellm-refactor...")
    print("-" * 40)
    merge_message = "Merge feat/litellm-refactor: LiteLLM migration + ChromaDB rebuild"
    result = run_command(
        ["git", "merge", "feat/litellm-refactor", "--no-ff", "-m", merge_message],
        check=False
    )

    if result.returncode != 0:
        if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
            conflicts = True
            print("⚠️  Merge conflicts detected!")
            print("Conflict details:")
            run_command(["git", "status", "--short"], check=False)
        else:
            print(f"❌ Merge failed: {result.stderr}")
            sys.exit(1)
    else:
        print("✓ Merge successful")

    # 5. Get merge commit hash
    result = run_command(["git", "rev-parse", "--short", "HEAD"])
    merge_hash = result.stdout.strip()

    # 6. Show recent commits
    print("\n📜 Recent commits on master:")
    print("-" * 40)
    run_command(["git", "log", "--oneline", "-5"])

    # 7. Show branch status
    print("\n🌿 Branch status:")
    print("-" * 40)
    run_command(["git", "branch", "-v"])

    # 8. Final summary
    print("\n" + "=" * 60)
    print("MERGE SUMMARY")
    print("=" * 60)
    print(f"Merge commit hash:  {merge_hash}")
    print(f"Commits merged:     {commits_to_merge}")
    print(f"Conflicts:          {'Yes ⚠️' if conflicts else 'None ✅'}")
    print(f"Master HEAD:        {merge_hash}")

    if not conflicts:
        print("\n" + "=" * 60)
        print("✅ MERGE COMPLETE - master updated successfully")
        print("=" * 60)
    else:
        print("\n⚠️  Please resolve conflicts before continuing")
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
