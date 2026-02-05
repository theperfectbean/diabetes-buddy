#!/usr/bin/env python3
"""
Installation verification script for Diabetes Buddy.

Checks dependencies, API keys, and runs a simple test query.
"""

import sys
from pathlib import Path

print("=" * 60)
print("Diabetes Buddy - Installation Verification")
print("=" * 60)

# Check Python version
print(f"\n✓ Python {sys.version.split()[0]}")
if sys.version_info < (3, 8):
    print("❌ ERROR: Python 3.8+ required")
    sys.exit(1)

# Check dependencies
print("\nChecking dependencies...")
missing = []

try:
    import google.genai
    print("  ✓ google-genai")
except ImportError:
    print("  ❌ google-genai")
    missing.append("google-genai")

try:
    import chromadb
    print("  ✓ chromadb")
except ImportError:
    print("  ❌ chromadb")
    missing.append("chromadb")

try:
    import PyPDF2
    print("  ✓ PyPDF2")
except ImportError:
    print("  ❌ PyPDF2")
    missing.append("PyPDF2")

try:
    import dotenv
    print("  ✓ python-dotenv")
except ImportError:
    print("  ❌ python-dotenv")
    missing.append("python-dotenv")

try:
    import mcp
    print("  ✓ mcp")
except ImportError:
    print("  ❌ mcp")
    missing.append("mcp")

if missing:
    print(f"\n❌ Missing dependencies: {', '.join(missing)}")
    print("\nInstall with:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

# Check API key
print("\nChecking configuration...")
from dotenv import load_dotenv
import os

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    print(f"  ✓ .env file found")
    load_dotenv(env_path)
else:
    print(f"  ⚠️  No .env file found")

api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    print(f"  ✓ GEMINI_API_KEY set ({api_key[:10]}...)")
else:
    print("  ❌ GEMINI_API_KEY not set")
    print("\nCreate .env file with:")
    print('  echo "GEMINI_API_KEY=your-key-here" > .env')
    sys.exit(1)

# Check knowledge base
print("\nChecking knowledge base...")
project_root = Path(__file__).parent

pdf_paths = {
    "Theory": "docs/theory/Think-Like-a-Pancreas-A-Practical-Guide-to-Managing-Gary-Scheiner-MS-Cdces-Revised-2025-Hachette-Go-9780306837159-ce3facbbce8e750f2d5875907dcab753-Annas-Archive.pdf",
    "CamAPS": "docs/manuals/algorithm/user_manual_fx_mmoll_commercial_ca.pdf",
    "Ypsomed": "docs/manuals/hardware/YPU_eIFU_REF_700009424_UK-en_V01.pdf",
    "Libre": "docs/manuals/hardware/ART41641-001_rev-A-web.pdf",
}

missing_pdfs = []
for name, path in pdf_paths.items():
    full_path = project_root / path
    if full_path.exists():
        size_mb = full_path.stat().st_size / (1024 * 1024)
        print(f"  ✓ {name} ({size_mb:.1f} MB)")
    else:
        print(f"  ❌ {name} - Not found")
        missing_pdfs.append(name)

if missing_pdfs:
    print(f"\n⚠️  Missing PDFs: {', '.join(missing_pdfs)}")
    print("Some features may not work.")

# Test import
print("\nTesting imports...")
try:
    sys.path.insert(0, str(project_root))
    from agents import TriageAgent, SafetyAuditor
    print("  ✓ Agents imported successfully")
except Exception as e:
    print(f"  ❌ Import error: {e}")
    sys.exit(1)

# Run simple test (skip if no PDFs)
if not missing_pdfs:
    print("\nRunning test query...")
    print("  (This may take a moment on first run)")
    
    try:
        triage = TriageAgent()
        response = triage.classify("What is basal insulin?")
        print(f"  ✓ Classification: {response.category.value} ({response.confidence:.0%})")
        print(f"  ✓ System functional!")
    except Exception as e:
        print(f"  ⚠️  Test query failed: {e}")
        print("  System may still work, but check configuration.")

print("\n" + "=" * 60)
print("✅ Installation verification complete!")
print("=" * 60)
print("\nNext steps:")
print("  1. Run: python -m diabuddy")
print("  2. Or: python mcp_server.py (for MCP integration)")
print("  3. Read: README.md for full documentation")
print("\n")
