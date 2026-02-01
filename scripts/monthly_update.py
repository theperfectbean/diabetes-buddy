#!/usr/bin/env python3
"""
Monthly Knowledge Base Update Orchestrator for Diabetes Buddy

Comprehensive script that:
1. Git pulls all OpenAPS repos (only changed files)
2. Re-parses only modified .md/.rst files
3. Runs PubMed search for new articles since last run
4. Updates ChromaDB with new/changed content only (incremental)
5. Generates changelog: data/update_logs/YYYY-MM-DD_changelog.md
6. Estimates storage used (git repo sizes + ChromaDB size)

Usage:
    python scripts/monthly_update.py                 # Full monthly update
    python scripts/monthly_update.py --dry-run       # Show what would change
    python scripts/monthly_update.py --openaps-only  # Only update OpenAPS docs
    python scripts/monthly_update.py --pubmed-only   # Only update PubMed articles
    python scripts/monthly_update.py --estimate      # Show storage estimate
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set up logging
_logs_dir = PROJECT_ROOT / "logs"
_logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_logs_dir / 'monthly_update.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Directories
DATA_DIR = PROJECT_ROOT / "data"
SOURCES_DIR = DATA_DIR / "sources"
CACHE_DIR = DATA_DIR / "cache"
UPDATE_LOGS_DIR = DATA_DIR / "update_logs"
CHROMADB_PATH = PROJECT_ROOT / ".cache" / "chromadb"
LAST_RUN_FILE = CACHE_DIR / "monthly_update_last_run.json"


@dataclass
class UpdatePhaseResult:
    """Result from a single update phase."""
    phase_name: str
    success: bool
    files_processed: int = 0
    files_updated: int = 0
    files_new: int = 0
    embeddings_created: int = 0
    errors: list = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    details: dict = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    def to_dict(self) -> dict:
        return {
            'phase_name': self.phase_name,
            'success': self.success,
            'files_processed': self.files_processed,
            'files_updated': self.files_updated,
            'files_new': self.files_new,
            'embeddings_created': self.embeddings_created,
            'errors': self.errors,
            'elapsed_seconds': self.elapsed_seconds,
            'details': self.details
        }


@dataclass
class MonthlyUpdateReport:
    """Complete report for a monthly update run."""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    phases: list = field(default_factory=list)
    storage_estimate_mb: float = 0
    total_chromadb_chunks: int = 0
    success: bool = True

    def add_phase(self, result: UpdatePhaseResult):
        self.phases.append(result)
        if not result.success:
            self.success = False

    def to_dict(self) -> dict:
        return {
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_elapsed_seconds': (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
            'phases': [p.to_dict() for p in self.phases],
            'storage_estimate_mb': self.storage_estimate_mb,
            'total_chromadb_chunks': self.total_chromadb_chunks,
            'success': self.success
        }


class LastRunTracker:
    """Tracks when the last update was run for incremental updates."""

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if LAST_RUN_FILE.exists():
            try:
                with open(LAST_RUN_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def save(self):
        with open(LAST_RUN_FILE, 'w') as f:
            json.dump(self._data, f, indent=2)

    def get_last_run(self, phase: str) -> Optional[datetime]:
        """Get the last run time for a phase."""
        timestamp = self._data.get(phase, {}).get('last_run')
        if timestamp:
            return datetime.fromisoformat(timestamp)
        return None

    def set_last_run(self, phase: str, timestamp: Optional[datetime] = None):
        """Set the last run time for a phase."""
        if phase not in self._data:
            self._data[phase] = {}
        self._data[phase]['last_run'] = (timestamp or datetime.now()).isoformat()

    def get_days_since_last_run(self, phase: str) -> Optional[int]:
        """Get days since last run."""
        last_run = self.get_last_run(phase)
        if last_run:
            return (datetime.now() - last_run).days
        return None


class MonthlyUpdateOrchestrator:
    """Main orchestrator for monthly knowledge base updates."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.tracker = LastRunTracker()
        self.report = MonthlyUpdateReport()

    def run_full_update(self) -> MonthlyUpdateReport:
        """Run complete monthly update of all knowledge sources."""
        logger.info("=" * 70)
        logger.info("MONTHLY KNOWLEDGE BASE UPDATE")
        logger.info(f"Started: {self.report.start_time.isoformat()}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info("=" * 70)

        # Phase 1: Update OpenAPS documentation
        openaps_result = self._update_openaps_docs()
        self.report.add_phase(openaps_result)

        # Phase 2: Update PubMed articles
        pubmed_result = asyncio.run(self._update_pubmed_articles())
        self.report.add_phase(pubmed_result)

        # Phase 3: Update ADA Standards
        ada_result = self._update_ada_standards()
        self.report.add_phase(ada_result)

        # Phase 4: Calculate storage and stats
        self._calculate_storage_stats()

        # Phase 5: Generate changelog
        self._generate_changelog()

        # Update last run times
        if not self.dry_run:
            self.tracker.set_last_run('openaps')
            self.tracker.set_last_run('pubmed')
            self.tracker.set_last_run('ada')
            self.tracker.save()

        self.report.end_time = datetime.now()
        return self.report

    def run_openaps_only(self) -> MonthlyUpdateReport:
        """Run OpenAPS documentation update only."""
        logger.info("Running OpenAPS documentation update only")
        openaps_result = self._update_openaps_docs()
        self.report.add_phase(openaps_result)
        self._calculate_storage_stats()
        self._generate_changelog()

        if not self.dry_run:
            self.tracker.set_last_run('openaps')
            self.tracker.save()

        self.report.end_time = datetime.now()
        return self.report

    def run_pubmed_only(self) -> MonthlyUpdateReport:
        """Run PubMed update only."""
        logger.info("Running PubMed article update only")
        pubmed_result = asyncio.run(self._update_pubmed_articles())
        self.report.add_phase(pubmed_result)
        self._calculate_storage_stats()
        self._generate_changelog()

        if not self.dry_run:
            self.tracker.set_last_run('pubmed')
            self.tracker.save()

        self.report.end_time = datetime.now()
        return self.report

    def _update_openaps_docs(self) -> UpdatePhaseResult:
        """Update OpenAPS documentation from git repos."""
        result = UpdatePhaseResult(phase_name="OpenAPS Documentation")
        logger.info("\n" + "-" * 50)
        logger.info("PHASE 1: OpenAPS Documentation Update")
        logger.info("-" * 50)

        try:
            from scripts.ingest_openaps_docs import OpenAPSDocsIngestion, REPO_CONFIG

            ingestion = OpenAPSDocsIngestion()

            # Check if repos are cloned
            repos_exist = all(
                (SOURCES_DIR / repo_key).exists()
                for repo_key in REPO_CONFIG
            )

            if not repos_exist:
                logger.info("First time setup - cloning all repositories...")
                if not self.dry_run:
                    success = ingestion.clone_all()
                    if not success:
                        result.errors.append("Failed to clone some repositories")
                else:
                    logger.info("[DRY RUN] Would clone repositories")
            else:
                # Check for updates
                updates_info = ingestion.check_for_updates()
                has_updates = any(
                    info.get('status') == 'updates_available'
                    for info in updates_info.values()
                )

                if has_updates:
                    logger.info("Updates available, processing...")
                    if not self.dry_run:
                        summaries = ingestion.update_all(notify=False, generate_log=False)
                        for summary in summaries:
                            result.files_updated += summary.files_updated
                            result.files_new += summary.files_new
                            result.embeddings_created += summary.embeddings_created
                            result.errors.extend(summary.errors)
                        result.files_processed = result.files_updated + result.files_new
                    else:
                        for repo_key, info in updates_info.items():
                            if info.get('status') == 'updates_available':
                                logger.info(f"[DRY RUN] Would update {repo_key}: {info.get('changed_files', 0)} files")
                else:
                    logger.info("All repositories are up to date")

            result.success = len(result.errors) == 0

        except ImportError as e:
            logger.error(f"Failed to import OpenAPS ingestion module: {e}")
            result.errors.append(str(e))
            result.success = False
        except Exception as e:
            logger.error(f"Error during OpenAPS update: {e}")
            result.errors.append(str(e))
            result.success = False

        result.end_time = datetime.now()
        logger.info(f"OpenAPS update completed in {result.elapsed_seconds:.1f}s")
        return result

    async def _update_pubmed_articles(self) -> UpdatePhaseResult:
        """Update PubMed research articles."""
        result = UpdatePhaseResult(phase_name="PubMed Research Articles")
        logger.info("\n" + "-" * 50)
        logger.info("PHASE 2: PubMed Research Articles Update")
        logger.info("-" * 50)

        try:
            from agents.pubmed_ingestion import PubMedIngestionPipeline, Config

            config = Config()

            # Calculate days since last run for incremental update
            last_run = self.tracker.get_last_run('pubmed')
            if last_run:
                days_back = (datetime.now() - last_run).days + 1  # Add 1 for safety
                days_back = min(days_back, 365)  # Cap at 1 year
                logger.info(f"Incremental update: searching last {days_back} days")
            else:
                days_back = config.filters.get('days_back', 365)
                logger.info(f"First run: searching last {days_back} days")

            if self.dry_run:
                logger.info(f"[DRY RUN] Would search PubMed for {len(config.search_terms)} terms")
                logger.info(f"[DRY RUN] Days back: {days_back}")
                result.success = True
            else:
                pipeline = PubMedIngestionPipeline(config)
                stats = await pipeline.run_full_ingestion(
                    days_back=days_back,
                    max_results=50,
                    open_access_only=True,
                    fetch_full_text=True
                )

                summary = pipeline.get_summary()
                result.files_new = summary.get('total_articles_added', 0)
                result.embeddings_created = summary.get('total_full_text_fetched', 0)
                result.files_processed = summary.get('total_articles_found', 0)
                result.details = summary

                if summary.get('total_errors', 0) > 0:
                    result.errors.append(f"{summary['total_errors']} errors during ingestion")

                result.success = True

        except ImportError as e:
            logger.error(f"Failed to import PubMed ingestion module: {e}")
            result.errors.append(str(e))
            result.success = False
        except Exception as e:
            logger.error(f"Error during PubMed update: {e}")
            result.errors.append(str(e))
            result.success = False

        result.end_time = datetime.now()
        logger.info(f"PubMed update completed in {result.elapsed_seconds:.1f}s")
        return result

    def _update_ada_standards(self) -> UpdatePhaseResult:
        """Update ADA Standards of Care from PMC."""
        result = UpdatePhaseResult(phase_name="ADA Standards")
        logger.info("\n" + "-" * 50)
        logger.info("PHASE 3: ADA Standards Update")
        logger.info("-" * 50)

        try:
            # Import the ADA ingestion module
            import subprocess
            import sys

            # Check if PDFs are available for ingestion
            pdf_dir = PROJECT_ROOT / "data" / "knowledge" / "ada_standards_pdfs"
            has_pdfs = pdf_dir.exists() and list(pdf_dir.glob("*.pdf"))

            if has_pdfs:
                logger.info(f"Detected {len(list(pdf_dir.glob('*.pdf')))} ADA Standards PDFs")
                # Check if PDFs are already ingested
                try:
                    import chromadb
                    from chromadb.config import Settings
                    client = chromadb.PersistentClient(
                        path=str(CHROMADB_PATH),
                        settings=Settings(anonymized_telemetry=False)
                    )
                    collection = client.get_collection(name="ada_standards")
                    results = collection.get(include=["metadatas"])
                    pdf_chunks = sum(1 for meta in results['metadatas']
                                   if meta.get('source_type') == 'full_text_pdf')

                    if pdf_chunks == 0:
                        logger.info("PDFs detected but not ingested - running ingestion...")
                        if not self.dry_run:
                            # Run PDF ingestion
                            cmd = [sys.executable, "scripts/ingest_ada_standards.py", "--pdf-only"]
                            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
                            if proc.returncode == 0:
                                logger.info("PDF ingestion completed successfully")
                                # Parse output to get chunk count
                                for line in proc.stdout.split('\n'):
                                    if "Chunks added:" in line:
                                        try:
                                            result.embeddings_created = int(line.split(":")[1].strip())
                                        except ValueError:
                                            pass
                            else:
                                result.errors.append(f"PDF ingestion failed: {proc.stderr}")
                        else:
                            logger.info("[DRY RUN] Would ingest ADA Standards PDFs")
                    else:
                        logger.info(f"PDFs already ingested ({pdf_chunks} chunks)")

                except Exception as e:
                    logger.warning(f"Error checking PDF ingestion status: {e}")
            else:
                logger.info("No ADA Standards PDFs found - abstracts update via PMC")

            # Always update abstracts (check for new Standards annually)
            logger.info("Checking for ADA Standards updates via PMC...")
            if not self.dry_run:
                # Run abstract ingestion (will skip if already up to date)
                cmd = [sys.executable, "scripts/ingest_ada_standards.py"]
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
                if proc.returncode == 0:
                    logger.info("ADA Standards abstracts updated successfully")
                    # Could parse chunk count here if needed
                else:
                    # Check if it's just "already up to date" or a real error
                    if "already exists" in proc.stderr or "Chunks added: 0" in proc.stdout:
                        logger.info("ADA Standards already up to date")
                    else:
                        result.errors.append(f"ADA Standards update failed: {proc.stderr}")
            else:
                logger.info("[DRY RUN] Would update ADA Standards abstracts")

            result.success = len(result.errors) == 0

        except ImportError as e:
            logger.error(f"Failed to import ADA ingestion module: {e}")
            result.errors.append(str(e))
            result.success = False
        except Exception as e:
            logger.error(f"Error during ADA Standards update: {e}")
            result.errors.append(str(e))
            result.success = False

        result.end_time = datetime.now()
        logger.info(f"ADA Standards update completed in {result.elapsed_seconds:.1f}s")
        return result

    def _calculate_storage_stats(self):
        """Calculate storage estimates and ChromaDB stats."""
        logger.info("\n" + "-" * 50)
        logger.info("Calculating Storage Statistics")
        logger.info("-" * 50)

        total_size = 0

        # Git repositories
        if SOURCES_DIR.exists():
            for repo_dir in SOURCES_DIR.iterdir():
                if repo_dir.is_dir():
                    try:
                        size = sum(
                            f.stat().st_size for f in repo_dir.rglob('*')
                            if f.is_file()
                        )
                        total_size += size
                        logger.info(f"  {repo_dir.name}: {size / (1024*1024):.2f} MB")
                    except Exception as e:
                        logger.warning(f"  Error calculating size for {repo_dir.name}: {e}")

        # ChromaDB
        if CHROMADB_PATH.exists():
            try:
                chroma_size = sum(
                    f.stat().st_size for f in CHROMADB_PATH.rglob('*')
                    if f.is_file()
                )
                total_size += chroma_size
                logger.info(f"  ChromaDB: {chroma_size / (1024*1024):.2f} MB")

                # Get document count
                try:
                    import chromadb
                    from chromadb.config import Settings
                    client = chromadb.PersistentClient(
                        path=str(CHROMADB_PATH),
                        settings=Settings(anonymized_telemetry=False)
                    )
                    total_chunks = 0
                    for collection in client.list_collections():
                        count = collection.count()
                        total_chunks += count
                        logger.info(f"    Collection '{collection.name}': {count} chunks")
                    self.report.total_chromadb_chunks = total_chunks
                except Exception as e:
                    logger.warning(f"  Error getting ChromaDB stats: {e}")

            except Exception as e:
                logger.warning(f"  Error calculating ChromaDB size: {e}")

        self.report.storage_estimate_mb = total_size / (1024 * 1024)
        logger.info(f"\nTotal storage: {self.report.storage_estimate_mb:.2f} MB")

    def _generate_changelog(self):
        """Generate markdown changelog for this update."""
        UPDATE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_date = datetime.now().strftime('%Y-%m-%d')
        log_path = UPDATE_LOGS_DIR / f"{log_date}_changelog.md"

        content = f"""# Knowledge Base Update - {log_date}

Generated: {datetime.now().isoformat()}
Dry Run: {self.dry_run}

## Update Summary

| Phase | Status | Files Processed | New | Updated | Embeddings | Time (s) |
|-------|--------|-----------------|-----|---------|------------|----------|
"""
        for phase in self.report.phases:
            status = "SUCCESS" if phase.success else "FAILED"
            content += f"| {phase.phase_name} | {status} | {phase.files_processed} | {phase.files_new} | {phase.files_updated} | {phase.embeddings_created} | {phase.elapsed_seconds:.1f} |\n"

        content += f"""
## Storage Statistics

- **Total storage used**: {self.report.storage_estimate_mb:.2f} MB
- **Total ChromaDB chunks**: {self.report.total_chromadb_chunks}

## Phase Details

"""
        for phase in self.report.phases:
            content += f"### {phase.phase_name}\n\n"
            if phase.errors:
                content += "**Errors:**\n"
                for error in phase.errors:
                    content += f"- {error}\n"
                content += "\n"
            if phase.details:
                content += f"**Details:** {json.dumps(phase.details, indent=2)}\n\n"

        # Write changelog
        if not self.dry_run:
            with open(log_path, 'w') as f:
                f.write(content)
            logger.info(f"Changelog written to: {log_path}")
        else:
            logger.info(f"[DRY RUN] Would write changelog to: {log_path}")

    def print_report(self):
        """Print formatted report to console."""
        print("\n" + "=" * 70)
        print("MONTHLY UPDATE REPORT")
        print("=" * 70)

        elapsed = (self.report.end_time - self.report.start_time).total_seconds() if self.report.end_time else 0
        print(f"\nTotal time: {elapsed:.1f} seconds")
        print(f"Overall status: {'SUCCESS' if self.report.success else 'FAILED'}")
        print(f"\nStorage: {self.report.storage_estimate_mb:.2f} MB")
        print(f"ChromaDB chunks: {self.report.total_chromadb_chunks}")

        print("\n" + "-" * 70)
        print("Phase Results:")
        print("-" * 70)

        for phase in self.report.phases:
            status_icon = "" if phase.success else ""
            print(f"\n{status_icon} {phase.phase_name}")
            print(f"  Files processed: {phase.files_processed}")
            print(f"  New files: {phase.files_new}")
            print(f"  Updated files: {phase.files_updated}")
            print(f"  Embeddings created: {phase.embeddings_created}")
            print(f"  Time: {phase.elapsed_seconds:.1f}s")
            if phase.errors:
                print(f"  Errors: {len(phase.errors)}")
                for error in phase.errors[:3]:
                    print(f"    - {error}")

        print("\n" + "=" * 70)


def show_storage_estimate():
    """Show current storage estimate without running updates."""
    print("\n" + "=" * 50)
    print("STORAGE ESTIMATE")
    print("=" * 50)

    total_size = 0

    # Git repositories
    print("\nGit Repositories:")
    if SOURCES_DIR.exists():
        for repo_dir in SOURCES_DIR.iterdir():
            if repo_dir.is_dir():
                try:
                    size = sum(
                        f.stat().st_size for f in repo_dir.rglob('*')
                        if f.is_file()
                    )
                    total_size += size
                    print(f"  {repo_dir.name}: {size / (1024*1024):.2f} MB")
                except Exception as e:
                    print(f"  {repo_dir.name}: Error - {e}")
    else:
        print("  (no repositories cloned)")

    # ChromaDB
    print("\nChromaDB:")
    if CHROMADB_PATH.exists():
        try:
            chroma_size = sum(
                f.stat().st_size for f in CHROMADB_PATH.rglob('*')
                if f.is_file()
            )
            total_size += chroma_size
            print(f"  Database: {chroma_size / (1024*1024):.2f} MB")

            # Try to get collection stats
            try:
                import chromadb
                from chromadb.config import Settings
                client = chromadb.PersistentClient(
                    path=str(CHROMADB_PATH),
                    settings=Settings(anonymized_telemetry=False)
                )
                print("\n  Collections:")
                total_chunks = 0
                for collection in client.list_collections():
                    count = collection.count()
                    total_chunks += count
                    print(f"    {collection.name}: {count} chunks")
                print(f"\n  Total chunks: {total_chunks}")
            except ImportError:
                print("  (chromadb not installed)")
            except Exception as e:
                print(f"  Error getting collection info: {e}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print("  (no database)")

    print("\n" + "-" * 50)
    print(f"TOTAL: {total_size / (1024*1024):.2f} MB")
    print("=" * 50)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Monthly Knowledge Base Update Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full monthly update
  python scripts/monthly_update.py

  # Show what would change without making changes
  python scripts/monthly_update.py --dry-run

  # Update only OpenAPS documentation
  python scripts/monthly_update.py --openaps-only

  # Update only PubMed articles
  python scripts/monthly_update.py --pubmed-only

  # Show current storage usage
  python scripts/monthly_update.py --estimate
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )

    parser.add_argument(
        '--openaps-only',
        action='store_true',
        help='Only update OpenAPS documentation'
    )

    parser.add_argument(
        '--pubmed-only',
        action='store_true',
        help='Only update PubMed articles'
    )

    parser.add_argument(
        '--estimate',
        action='store_true',
        help='Show storage estimate and exit'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.estimate:
        show_storage_estimate()
        return 0

    orchestrator = MonthlyUpdateOrchestrator(dry_run=args.dry_run)

    try:
        if args.openaps_only:
            report = orchestrator.run_openaps_only()
        elif args.pubmed_only:
            report = orchestrator.run_pubmed_only()
        else:
            report = orchestrator.run_full_update()

        orchestrator.print_report()
        return 0 if report.success else 1

    except KeyboardInterrupt:
        logger.info("Update interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
