"""
Background Scheduler for Knowledge Base Updates
Runs automatic update checks on a configurable schedule.
"""

import schedule
import time
import logging
import sys
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.knowledge_fetcher import KnowledgeFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/knowledge_updates.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class KnowledgeUpdateScheduler:
    """Manages scheduled updates for knowledge base."""
    
    def __init__(self):
        self.fetcher = KnowledgeFetcher()
        self.running = False
        
    def run_update_check(self):
        """Execute update check and log results."""
        logger.info("=" * 60)
        logger.info("Starting scheduled update check")
        logger.info("=" * 60)
        
        try:
            # Check if auto-update is enabled
            profile = self.fetcher.get_user_profile()
            if not profile.get('auto_update_enabled', True):
                logger.info("Auto-update is disabled, skipping check")
                return
            
            # Run update check
            updates = self.fetcher.check_for_updates()
            
            # Log results
            updates_available = []
            errors = []
            
            for source_key, result in updates.items():
                if result.get('update_available'):
                    updates_available.append({
                        'source': source_key,
                        'old_version': result.get('old_version'),
                        'new_version': result.get('new_version')
                    })
                elif result.get('error'):
                    errors.append({
                        'source': source_key,
                        'error': result.get('error')
                    })
            
            # Notify user if configured
            notify_prefs = profile.get('update_preferences', {})
            
            if updates_available:
                logger.info(f"Found {len(updates_available)} updates")
                
                # Check if we should notify about guidelines
                guideline_updates = [u for u in updates_available if 'guideline' in u['source']]
                if guideline_updates and notify_prefs.get('notify_on_guideline_changes', True):
                    self._send_notification("Clinical Guideline Updates Available", guideline_updates)
                
                # Check if we should notify about device updates
                device_updates = [u for u in updates_available if u not in guideline_updates]
                if device_updates and notify_prefs.get('notify_on_device_updates', False):
                    self._send_notification("Device Manual Updates Available", device_updates)
            else:
                logger.info("No updates found")
            
            if errors:
                logger.warning(f"Encountered {len(errors)} errors during update check")
                for error in errors:
                    logger.warning(f"  {error['source']}: {error['error']}")
            
            logger.info("Scheduled update check completed")
            
        except Exception as e:
            logger.error(f"Update check failed with error: {e}", exc_info=True)
    
    def _send_notification(self, title: str, updates: list):
        """
        Send notification to user about updates.
        Currently logs to file, can be extended for system notifications.
        """
        logger.info(f"NOTIFICATION: {title}")
        for update in updates:
            logger.info(f"  - {update['source']}: {update['old_version']} → {update['new_version']}")
        
        # Save notification to file for web UI to display
        notifications_file = Path("data/notifications.json")
        notifications_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing notifications
        notifications = []
        if notifications_file.exists():
            try:
                with open(notifications_file, 'r') as f:
                    notifications = json.load(f)
            except:
                notifications = []
        
        # Add new notification
        notifications.append({
            'timestamp': datetime.now().isoformat(),
            'title': title,
            'updates': updates,
            'read': False
        })
        
        # Keep only last 50 notifications
        notifications = notifications[-50:]
        
        # Save
        with open(notifications_file, 'w') as f:
            json.dump(notifications, f, indent=2)
    
    def start(self, mode='daemon'):
        """
        Start the scheduler.
        
        Args:
            mode: 'daemon' for continuous running, 'once' for single check
        """
        logger.info(f"Starting Knowledge Update Scheduler in {mode} mode")
        
        if mode == 'once':
            # Run once and exit
            self.run_update_check()
            return
        
        # Get update frequency from user profile
        profile = self.fetcher.get_user_profile()
        update_freq_days = profile.get('update_preferences', {}).get('update_frequency_days', 7)
        
        # Schedule weekly updates (or custom frequency)
        if update_freq_days == 1:
            schedule.every().day.at("03:00").do(self.run_update_check)
            logger.info("Scheduled daily updates at 03:00")
        elif update_freq_days == 7:
            schedule.every().monday.at("03:00").do(self.run_update_check)
            logger.info("Scheduled weekly updates (Mondays at 03:00)")
        else:
            schedule.every(update_freq_days).days.at("03:00").do(self.run_update_check)
            logger.info(f"Scheduled updates every {update_freq_days} days at 03:00")
        
        # Run immediately on startup
        logger.info("Running initial update check...")
        self.run_update_check()
        
        # Main loop
        self.running = True
        logger.info("Scheduler running. Press Ctrl+C to stop.")
        
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            self.running = False


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Knowledge Base Update Scheduler')
    parser.add_argument('--mode', choices=['daemon', 'once'], default='daemon',
                       help='Run mode: daemon (continuous) or once (single check)')
    parser.add_argument('--check-now', action='store_true',
                       help='Run update check immediately and exit')
    
    args = parser.parse_args()
    
    scheduler = KnowledgeUpdateScheduler()
    
    if args.check_now:
        scheduler.run_update_check()
    else:
        scheduler.start(mode=args.mode)


if __name__ == "__main__":
    main()
