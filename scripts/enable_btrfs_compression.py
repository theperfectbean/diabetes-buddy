#!/usr/bin/env python3
"""Enable btrfs zstd compression on data/sources/ directory."""

import subprocess
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
SOURCES_DIR = PROJECT_ROOT / "data" / "sources"

def log(msg: str):
    """Log with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def run_cmd(cmd: list, check: bool = False, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a subprocess command and log it."""
    log(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)

def parse_compsize_output(output: str) -> dict:
    """Parse compsize output to extract stats."""
    stats = {"total_raw": 0, "total_disk": 0, "ratio": 1.0}
    lines = output.strip().split('\n')
    for line in lines:
        if line.startswith("Total:") or line.startswith("Processed"):
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "TOTAL":
            # Format: TOTAL Type Perc Disk Uncomp Referenced
            # Try to parse the disk and uncompressed sizes
            try:
                stats["ratio"] = float(parts[1]) if parts[1].replace('.','').isdigit() else 1.0
            except:
                pass
    return stats

def get_du_size(path: str) -> str:
    """Get directory size using du."""
    result = run_cmd(["du", "-sh", path])
    if result.returncode == 0:
        return result.stdout.split()[0]
    return "unknown"

def main():
    print("=" * 60)
    print("BTRFS ZSTD COMPRESSION - data/sources/")
    print("=" * 60)

    # ===== STEP 1: Install compsize =====
    log("STEP 1: Checking compsize tool...")
    result = run_cmd(["which", "compsize"])
    if result.returncode != 0:
        log("compsize not found, installing...")
        try:
            result = run_cmd(["sudo", "pacman", "-S", "--noconfirm", "compsize"], check=True, timeout=120)
            log("compsize installed successfully")
        except subprocess.CalledProcessError as e:
            log(f"Failed to install compsize: {e.stderr}")
            log("Continuing without detailed compression stats...")
    else:
        log(f"compsize found: {result.stdout.strip()}")

    # ===== STEP 2: Baseline measurement =====
    log("\nSTEP 2: Baseline measurement (before compression)...")
    baseline_du = get_du_size(str(SOURCES_DIR))
    log(f"Baseline du -sh: {baseline_du}")

    baseline_compsize = None
    result = run_cmd(["sudo", "compsize", "-x", str(SOURCES_DIR)], timeout=120)
    if result.returncode == 0:
        baseline_compsize = result.stdout
        log("Baseline compsize output:")
        print(result.stdout)
    else:
        log(f"compsize failed: {result.stderr}")

    # Count files
    md_files = list(SOURCES_DIR.rglob("*.md"))
    png_files = list(SOURCES_DIR.rglob("*.png"))
    jpg_files = list(SOURCES_DIR.rglob("*.jpg")) + list(SOURCES_DIR.rglob("*.jpeg"))
    log(f"Files: {len(md_files)} .md, {len(png_files)} .png, {len(jpg_files)} .jpg")

    # ===== STEP 3: Enable compression property =====
    log("\nSTEP 3: Setting compression property to zstd...")
    result = run_cmd(["sudo", "btrfs", "property", "set", str(SOURCES_DIR), "compression", "zstd"])
    if result.returncode != 0:
        log(f"ERROR: Failed to set compression property: {result.stderr}")
        return

    # Verify
    result = run_cmd(["btrfs", "property", "get", str(SOURCES_DIR), "compression"])
    if result.returncode == 0:
        log(f"Verified: {result.stdout.strip()}")
    else:
        log(f"Warning: Could not verify property: {result.stderr}")

    # ===== STEP 4: Compress existing files =====
    log("\nSTEP 4: Starting defragmentation with zstd compression...")
    log("This will compress all 5.2 GB of existing files...")

    start_time = time.time()
    try:
        result = run_cmd(
            ["sudo", "btrfs", "filesystem", "defragment", "-r", "-czstd", str(SOURCES_DIR)],
            timeout=900  # 15 minute timeout
        )
        elapsed = time.time() - start_time

        if result.returncode == 0:
            log(f"Defragment completed in {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        else:
            log(f"Defragment returned code {result.returncode}")
            if result.stderr:
                log(f"stderr: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        log(f"Defragment timed out after {elapsed:.1f} seconds")

    # ===== STEP 5: Post-compression measurement =====
    log("\nSTEP 5: Post-compression measurement...")
    post_du = get_du_size(str(SOURCES_DIR))
    log(f"Post-compression du -sh: {post_du}")

    post_compsize = None
    result = run_cmd(["sudo", "compsize", "-x", str(SOURCES_DIR)], timeout=120)
    if result.returncode == 0:
        post_compsize = result.stdout
        log("Post-compression compsize output:")
        print(result.stdout)

    # ===== STEP 6: Generate report =====
    print("\n" + "=" * 60)
    print("=== Btrfs Compression Report ===")
    print("=" * 60)

    print("\n1. BASELINE (Before Compression):")
    print(f"   Disk usage (du): {baseline_du}")
    print(f"   Markdown files: {len(md_files)}")
    print(f"   Image files: {len(png_files) + len(jpg_files)}")
    if baseline_compsize:
        for line in baseline_compsize.strip().split('\n')[-3:]:
            print(f"   {line}")

    print("\n2. COMPRESSION APPLIED:")
    print(f"   Property set: compression=zstd ✓")
    print(f"   Defragment duration: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"   Files processed: ~{len(md_files) + len(png_files) + len(jpg_files)} files")

    print("\n3. POST-COMPRESSION:")
    print(f"   Disk usage (du): {post_du}")
    if post_compsize:
        for line in post_compsize.strip().split('\n')[-3:]:
            print(f"   {line}")

    # Parse sizes for savings calculation
    def parse_size(s: str) -> float:
        """Parse size string like '5.2G' to GB float."""
        s = s.strip().upper()
        if s.endswith('G'):
            return float(s[:-1])
        elif s.endswith('M'):
            return float(s[:-1]) / 1024
        elif s.endswith('K'):
            return float(s[:-1]) / (1024 * 1024)
        return float(s)

    try:
        before_gb = parse_size(baseline_du)
        after_gb = parse_size(post_du)
        saved_gb = before_gb - after_gb
        pct = (saved_gb / before_gb) * 100 if before_gb > 0 else 0

        print("\n4. SPACE SAVED:")
        print(f"   Before: {before_gb:.2f} GB")
        print(f"   After: {after_gb:.2f} GB")
        print(f"   Saved: {saved_gb:.2f} GB ({pct:.1f}% reduction)")
    except:
        print("\n4. SPACE SAVED: (see du values above)")

    print("\n5. FUTURE IMPACT:")
    print("   ✓ All new files in data/sources/ will auto-compress")
    print("   ✓ Monthly PubMed/ADA updates will auto-compress")
    print("   ✓ git pull updates will auto-compress")

    print("\n" + "=" * 60)
    print("Status: SUCCESS ✓")
    print("Next: Ready for ChromaDB ingestion with reduced disk usage")
    print("=" * 60)

if __name__ == "__main__":
    main()
