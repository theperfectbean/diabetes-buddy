#!/usr/bin/env python3
"""Clone OpenAPS documentation repositories to data/sources/"""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

REPOS = [
    ("openaps-docs", "https://github.com/openaps/docs"),
    ("androidaps-docs", "https://github.com/openaps/AndroidAPSdocs"),
    ("loopdocs", "https://github.com/LoopKit/loopdocs"),
]

def get_dir_size_mb(path: Path) -> float:
    """Calculate directory size in MB."""
    total = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    return total / (1024 * 1024)

def main():
    # 1. Create data/sources/ directory
    sources_dir = PROJECT_ROOT / "data" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created directory: {sources_dir}")

    results = []

    # 2. Clone each repository
    for name, url in REPOS:
        dest = sources_dir / name
        print(f"\nCloning {name}...")

        if dest.exists():
            print(f"  Skipping - already exists at {dest}")
            md_files = list(dest.rglob("*.md"))
            size_mb = get_dir_size_mb(dest)
            results.append({
                "repo": name,
                "status": "SKIPPED (exists)",
                "files": len(md_files),
                "size_mb": size_mb
            })
            continue

        # Clone with --depth 1
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            md_files = list(dest.rglob("*.md"))
            size_mb = get_dir_size_mb(dest)
            print(f"  SUCCESS: {len(md_files)} .md files, {size_mb:.2f} MB")
            results.append({
                "repo": name,
                "status": "SUCCESS",
                "files": len(md_files),
                "size_mb": size_mb
            })
        else:
            print(f"  FAILED: {result.stderr}")
            results.append({
                "repo": name,
                "status": "FAILED",
                "error": result.stderr,
                "files": 0,
                "size_mb": 0
            })

    # 3. Print summary report
    print("\n" + "=" * 70)
    print("CLONE REPORT")
    print("=" * 70)
    print(f"{'Repository':<20} {'Status':<20} {'MD Files':<12} {'Size (MB)':<10}")
    print("-" * 70)

    total_files = 0
    total_size = 0.0

    for r in results:
        print(f"{r['repo']:<20} {r['status']:<20} {r['files']:<12} {r['size_mb']:.2f}")
        total_files += r['files']
        total_size += r['size_mb']

    print("-" * 70)
    print(f"{'TOTAL':<20} {'':<20} {total_files:<12} {total_size:.2f}")
    print("=" * 70)

if __name__ == "__main__":
    main()
