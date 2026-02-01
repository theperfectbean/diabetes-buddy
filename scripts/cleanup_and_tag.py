#!/usr/bin/env python3
"""Clean up merged feature branch and create release tag."""

import subprocess
import sys


def run_command(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        # Print stderr but don't treat as fatal unless check=True
        if result.returncode != 0:
            print(f"  → {result.stderr.strip()}")
    if check and result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result


def main():
    print("=" * 60)
    print("CLEANUP AND TAG RELEASE")
    print("=" * 60)

    # Track state for summary
    branch_deleted = False
    tag_created = False
    tag_name = "v0.2.0"

    # 1. Delete merged feature branch
    print("\n🗑️  Deleting merged feature branch...")
    print("-" * 40)
    result = run_command(["git", "branch", "-d", "feat/litellm-refactor"])
    if result.returncode == 0:
        branch_deleted = True
        print("✓ Branch deleted")
    elif "not found" in result.stderr.lower():
        print("ℹ️  Branch already deleted")
        branch_deleted = True  # Consider it success
    else:
        print(f"⚠️  Could not delete branch: {result.stderr.strip()}")

    # 2. Create annotated tag
    print(f"\n🏷️  Creating tag {tag_name}...")
    print("-" * 40)
    tag_message = "LiteLLM migration + ChromaDB 768-dim rebuild"
    result = run_command(["git", "tag", "-a", tag_name, "-m", tag_message])
    if result.returncode == 0:
        tag_created = True
        print(f"✓ Tag {tag_name} created")
    elif "already exists" in result.stderr.lower():
        print(f"ℹ️  Tag {tag_name} already exists")
        tag_created = True  # Already exists is fine
    else:
        print(f"⚠️  Could not create tag: {result.stderr.strip()}")

    # 3. Show tag details
    print(f"\n📋 Tag details for {tag_name}:")
    print("-" * 40)
    run_command(["git", "show", tag_name, "--stat"])

    # 4. List all tags
    print("\n🏷️  All tags:")
    print("-" * 40)
    result = run_command(["git", "tag", "-l"])
    if not result.stdout.strip():
        print("(no tags)")

    # 5. Show current branch status
    print("\n🌿 Current branches:")
    print("-" * 40)
    run_command(["git", "branch", "-v"])

    # 6. Final summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Branch deletion:     {'✅ Deleted' if branch_deleted else '❌ Failed'}")
    print(f"Tag created:         {'✅ ' + tag_name if tag_created else '❌ Failed'}")

    # Get commit info for the tag
    result = subprocess.run(
        ["git", "rev-parse", "--short", tag_name],
        capture_output=True, text=True
    )
    tag_commit = result.stdout.strip() if result.returncode == 0 else "unknown"
    print(f"Tagged commit:       {tag_commit}")

    # Count remaining branches
    result = subprocess.run(
        ["git", "branch", "--list"],
        capture_output=True, text=True
    )
    branches = [b.strip().lstrip('* ') for b in result.stdout.strip().split('\n') if b.strip()]
    print(f"Branches remaining:  {len(branches)} ({', '.join(branches)})")

    if branch_deleted and tag_created:
        print("\n" + "=" * 60)
        print("✅ CLEANUP COMPLETE")
        print("=" * 60)
        print(f"\nRelease {tag_name} is ready!")
        print(f"To push: git push origin master --tags")
    else:
        print("\n⚠️  Some operations did not complete successfully")

    return 0


if __name__ == "__main__":
    sys.exit(main())
