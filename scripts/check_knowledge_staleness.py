#!/usr/bin/env python3
"""
Knowledge Staleness Monitor for Diabetes Buddy

Checks all knowledge collections for freshness and generates reports.
Designed to run as a systemd timer for weekly monitoring.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json
import logging
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.researcher_chromadb import ResearcherAgent

class KnowledgeStalenessChecker:
    def __init__(self, project_root: Path, config: dict):
        self.project_root = project_root
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.staleness_threshold = timedelta(days=config['knowledge_monitoring']['staleness_threshold_days'])
        self.critical_threshold = timedelta(days=config['knowledge_monitoring']['critical_threshold_days'])

    def check_collection_staleness(self, collection_name: str) -> dict:
        """Check staleness of a specific collection."""
        try:
            # Initialize researcher to access ChromaDB
            researcher = ResearcherAgent(project_root=self.project_root)

            # Get collection metadata
            # This would need to be implemented in the researcher
            # For now, return mock data
            metadata = self._get_collection_metadata(collection_name)

            if not metadata:
                return {
                    'collection': collection_name,
                    'status': 'unknown',
                    'last_updated': None,
                    'days_old': None,
                    'error': 'No metadata available'
                }

            last_updated = datetime.fromisoformat(metadata.get('last_updated', '2020-01-01T00:00:00'))
            days_old = (datetime.now() - last_updated).days

            # Determine status
            if days_old > self.critical_threshold.days:
                status = 'critical'
            elif days_old > self.staleness_threshold.days:
                status = 'stale'
            else:
                status = 'up-to-date'

            return {
                'collection': collection_name,
                'status': status,
                'last_updated': last_updated.isoformat(),
                'days_old': days_old,
                'source_url': metadata.get('source_url'),
                'version': metadata.get('version')
            }

        except Exception as e:
            self.logger.error(f"Error checking collection {collection_name}: {e}")
            return {
                'collection': collection_name,
                'status': 'error',
                'error': str(e)
            }

    def _get_collection_metadata(self, collection_name: str) -> dict:
        """Get metadata for a collection. This is a placeholder."""
        # In a real implementation, this would query ChromaDB for metadata
        # For now, return mock data based on collection name
        mock_metadata = {
            'openaps_docs': {
                'last_updated': '2026-01-15T10:00:00',
                'source_url': 'https://openaps.readthedocs.io/',
                'version': 'latest'
            },
            'androidaps_docs': {
                'last_updated': '2026-01-10T08:00:00',
                'source_url': 'https://androidaps.readthedocs.io/',
                'version': '3.2'
            },
            'loop_docs': {
                'last_updated': '2025-12-01T12:00:00',  # Older - should be stale
                'source_url': 'https://loopkit.github.io/loopdocs/',
                'version': '3.0'
            }
        }
        return mock_metadata.get(collection_name)

    def generate_report(self) -> dict:
        """Generate comprehensive staleness report."""
        collections = [
            'openaps_docs', 'androidaps_docs', 'loop_docs', 'wikipedia_education',
            'ada_standards', 'research_papers'
        ]

        report = {
            'timestamp': datetime.now().isoformat(),
            'collections': [],
            'summary': {
                'total': len(collections),
                'up_to_date': 0,
                'stale': 0,
                'critical': 0,
                'unknown': 0,
                'errors': 0
            },
            'alerts': []
        }

        for collection in collections:
            result = self.check_collection_staleness(collection)
            report['collections'].append(result)

            status = result['status']
            report['summary'][status] = report['summary'].get(status, 0) + 1

            # Generate alerts
            if status == 'critical':
                report['alerts'].append(f"CRITICAL: {collection} is {result['days_old']} days old")
            elif status == 'stale':
                report['alerts'].append(f"WARNING: {collection} is {result['days_old']} days old")

        return report

    def send_alerts(self, report: dict):
        """Send alerts for critical staleness issues."""
        if not report['alerts']:
            self.logger.info("No staleness alerts to send")
            return

        # In a real implementation, this could send emails or notifications
        self.logger.warning("Knowledge Staleness Alerts:")
        for alert in report['alerts']:
            self.logger.warning(f"  {alert}")

    def save_report(self, report: dict, output_file: Path = None):
        """Save the report to a JSON file."""
        if not output_file:
            output_file = self.project_root / "data" / "analysis" / f"staleness_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        self.logger.info(f"Staleness report saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Check knowledge base staleness')
    parser.add_argument('--config', type=str, default='config/hybrid_knowledge.yaml',
                       help='Path to configuration file')
    parser.add_argument('--output', type=str, help='Output file for report')
    parser.add_argument('--alerts-only', action='store_true', help='Only show alerts')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        config_path = Path(__file__).parent.parent / args.config

    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return 1

    # Initialize checker
    project_root = Path(__file__).parent.parent
    checker = KnowledgeStalenessChecker(project_root, config)

    # Generate report
    report = checker.generate_report()

    # Save report
    if args.output:
        output_file = Path(args.output)
    else:
        output_file = None
    checker.save_report(report, output_file)

    # Send alerts
    checker.send_alerts(report)

    # Print summary
    if not args.alerts_only:
        print(f"Knowledge Staleness Report ({report['timestamp']})")
        print(f"Total collections: {report['summary']['total']}")
        print(f"Up to date: {report['summary']['up_to_date']}")
        print(f"Stale: {report['summary']['stale']}")
        print(f"Critical: {report['summary']['critical']}")
        print(f"Unknown: {report['summary']['unknown']}")

        if report['alerts']:
            print("\nAlerts:")
            for alert in report['alerts']:
                print(f"  {alert}")

    return 0

if __name__ == '__main__':
    sys.exit(main())