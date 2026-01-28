"""
Autonomous Knowledge Base Fetcher
Automatically downloads and maintains clinical guidelines and device manuals.
"""

import json
import os
import hashlib
import requests
import time
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

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


class KnowledgeFetcher:
    """Manages automatic fetching and updating of knowledge base sources."""
    
    def __init__(self, config_dir: str = "config", docs_dir: str = "docs/knowledge-sources"):
        self.config_dir = Path(config_dir)
        self.docs_dir = Path(docs_dir)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create logs directory if it doesn't exist
        Path("logs").mkdir(exist_ok=True)
        
        # Load device registry
        registry_path = self.config_dir / "device_registry.json"
        with open(registry_path, 'r') as f:
            self.registry = json.load(f)
        
        # Load or create user profile
        self.profile_path = self.config_dir / "user_profile.json"
        self.profile = self._load_or_create_profile()
        
        # Fetch configuration
        self.fetch_config = self.registry.get('fetch_config', {})
        self.user_agent = self.fetch_config.get('user_agent', 'DiabetesBuddy/1.0')
        self.timeout = self.fetch_config.get('timeout_seconds', 30)
        self.max_retries = self.fetch_config.get('max_retries', 3)
        self.retry_delay = self.fetch_config.get('retry_delay_seconds', 5)
        self.rate_limit_delay = self.fetch_config.get('rate_limit_delay_seconds', 2)
        
    def _load_or_create_profile(self) -> Dict:
        """Load existing user profile or create default."""
        if self.profile_path.exists():
            with open(self.profile_path, 'r') as f:
                return json.load(f)
        else:
            default_profile = {
                "version": "1.0.0",
                "created_at": datetime.now().isoformat(),
                "devices": {
                    "pump": None,
                    "cgm": None
                },
                "knowledge_sources": [],
                "auto_update_enabled": True,
                "last_update_check": None,
                "update_preferences": {
                    "notify_on_guideline_changes": True,
                    "notify_on_device_updates": False,
                    "update_frequency_days": 7
                }
            }
            self._save_profile(default_profile)
            return default_profile
    
    def _save_profile(self, profile: Dict = None):
        """Save user profile to disk."""
        if profile is None:
            profile = self.profile
        with open(self.profile_path, 'w') as f:
            json.dump(profile, f, indent=2)
    
    def setup_user_devices(self, pump_id: str, cgm_id: str) -> Dict:
        """
        Initial setup: Select devices and fetch all required knowledge sources.
        
        Args:
            pump_id: Device ID from registry (e.g., 'camaps_fx')
            cgm_id: CGM ID from registry (e.g., 'libre_3')
            
        Returns:
            Dict with status and results for each source
        """
        logger.info(f"Starting knowledge base setup for {pump_id} + {cgm_id}")
        
        # Update profile
        self.profile['devices']['pump'] = pump_id
        self.profile['devices']['cgm'] = cgm_id
        self.profile['setup_completed_at'] = datetime.now().isoformat()
        
        # Determine sources to fetch
        sources_to_fetch = []
        
        # Add clinical guidelines (always included)
        for guideline_id in self.registry['clinical_guidelines'].keys():
            sources_to_fetch.append(('guideline', guideline_id))
        
        # Add selected pump
        if pump_id and pump_id in self.registry['insulin_pumps']:
            sources_to_fetch.append(('pump', pump_id))
        
        # Add selected CGM
        if cgm_id and cgm_id in self.registry['cgm_devices']:
            sources_to_fetch.append(('cgm', cgm_id))
        
        # Fetch all sources
        results = {}
        for source_type, source_id in sources_to_fetch:
            logger.info(f"Fetching {source_type}: {source_id}")
            try:
                result = self.fetch_source(source_type, source_id)
                results[f"{source_type}_{source_id}"] = result
                
                # Add to profile
                if result['success']:
                    self.profile['knowledge_sources'].append({
                        'type': source_type,
                        'id': source_id,
                        'added_at': datetime.now().isoformat(),
                        'version': result.get('version', 'unknown')
                    })
                
                # Rate limiting
                time.sleep(self.rate_limit_delay)
                
            except Exception as e:
                logger.error(f"Error fetching {source_type} {source_id}: {e}")
                results[f"{source_type}_{source_id}"] = {
                    'success': False,
                    'error': str(e)
                }
        
        # Save updated profile
        self._save_profile()
        
        logger.info("Knowledge base setup completed")
        return results
    
    def fetch_source(self, source_type: str, source_id: str) -> Dict:
        """
        Fetch a single knowledge source.
        
        Args:
            source_type: 'pump', 'cgm', or 'guideline'
            source_id: ID from registry
            
        Returns:
            Dict with success status, file path, version, etc.
        """
        # Get source config
        if source_type == 'pump':
            source_config = self.registry['insulin_pumps'].get(source_id)
        elif source_type == 'cgm':
            source_config = self.registry['cgm_devices'].get(source_id)
        elif source_type == 'guideline':
            source_config = self.registry['clinical_guidelines'].get(source_id)
        else:
            raise ValueError(f"Unknown source type: {source_type}")
        
        if not source_config:
            raise ValueError(f"Source not found: {source_type}/{source_id}")
        
        fetch_method = source_config.get('fetch_method')
        
        if fetch_method == 'direct':
            return self._fetch_direct_download(source_type, source_id, source_config)
        elif fetch_method == 'scrape':
            return self._fetch_with_scraping(source_type, source_id, source_config)
        elif fetch_method == 'git':
            return self._fetch_from_git(source_type, source_id, source_config)
        else:
            raise ValueError(f"Unknown fetch method: {fetch_method}")
    
    def _fetch_direct_download(self, source_type: str, source_id: str, config: Dict) -> Dict:
        """Fetch PDF directly from known URL."""
        url = config.get('direct_pdf_url')
        if not url:
            raise ValueError("No direct_pdf_url configured")
        
        logger.info(f"Direct download from {url}")
        
        # Download with retries
        content = self._download_with_retry(url)
        
        # Detect version
        version = self._detect_version(content, config.get('version_pattern'))
        
        # Save file
        file_path = self._save_pdf(source_type, source_id, content, version)
        
        # Create metadata
        metadata = self._create_metadata(source_type, source_id, config, version, url, content)
        
        return {
            'success': True,
            'file_path': str(file_path),
            'version': version,
            'metadata_path': str(metadata),
            'source_url': url
        }
    
    def _fetch_with_scraping(self, source_type: str, source_id: str, config: Dict) -> Dict:
        """Fetch PDF by scraping webpage for download link."""
        page_url = config.get('manual_url') or config.get('url')
        if not page_url:
            raise ValueError("No manual_url or url configured")
        
        logger.info(f"Scraping page {page_url}")
        
        # Download page
        response = self._download_with_retry(page_url, binary=False)
        soup = BeautifulSoup(response, 'html.parser')
        
        # Find PDF link using selectors
        selectors = config.get('selectors', {})
        pdf_link_selector = selectors.get('pdf_link') or selectors.get('manual_link')
        
        pdf_url = None
        if pdf_link_selector:
            # Try CSS selector
            links = soup.select(pdf_link_selector)
            for link in links:
                href = link.get('href', '')
                if href and (href.endswith('.pdf') or 'pdf' in href.lower()):
                    pdf_url = urljoin(page_url, href)
                    break
        
        # Fallback: search for any PDF links
        if not pdf_url:
            logger.info("Selector didn't find PDF, trying fallback search")
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.endswith('.pdf') or 'manual' in href.lower() or 'user-guide' in href.lower():
                    pdf_url = urljoin(page_url, href)
                    break
        
        if not pdf_url:
            raise ValueError(f"Could not find PDF link on page {page_url}")
        
        logger.info(f"Found PDF at {pdf_url}")
        
        # Download PDF
        pdf_content = self._download_with_retry(pdf_url)
        
        # Detect version
        version = self._detect_version(pdf_content, config.get('version_pattern'))
        
        # Save file
        file_path = self._save_pdf(source_type, source_id, pdf_content, version)
        
        # Create metadata
        metadata = self._create_metadata(source_type, source_id, config, version, pdf_url, pdf_content)
        
        return {
            'success': True,
            'file_path': str(file_path),
            'version': version,
            'metadata_path': str(metadata),
            'source_url': pdf_url
        }
    
    def _fetch_from_git(self, source_type: str, source_id: str, config: Dict) -> Dict:
        """Clone or update git repository."""
        git_repo = config.get('git_repo')
        if not git_repo:
            raise ValueError("No git_repo configured")
        
        logger.info(f"Cloning/updating git repo {git_repo}")
        
        # Create directory for this source
        repo_dir = self.docs_dir / source_type / source_id / "latest"
        repo_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            if (repo_dir / ".git").exists():
                # Update existing repo
                logger.info("Updating existing repository")
                subprocess.run(
                    ["git", "pull"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True
                )
            else:
                # Clone new repo
                logger.info("Cloning repository")
                subprocess.run(
                    ["git", "clone", git_repo, str(repo_dir)],
                    check=True,
                    capture_output=True
                )
            
            # Get current commit hash as version
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True
            )
            version = result.stdout.strip()
            
            # Create metadata
            metadata_path = repo_dir / "metadata.json"
            metadata = {
                'source_type': source_type,
                'source_id': source_id,
                'source_name': config.get('name'),
                'git_repo': git_repo,
                'commit': version,
                'fetched_at': datetime.now().isoformat(),
                'license': config.get('license'),
                'organization': config.get('organization')
            }
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return {
                'success': True,
                'repo_path': str(repo_dir),
                'version': version,
                'metadata_path': str(metadata_path),
                'source_url': git_repo
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            raise RuntimeError(f"Git operation failed: {e.stderr}")
    
    def _download_with_retry(self, url: str, binary: bool = True) -> bytes:
        """Download content with exponential backoff retry."""
        headers = {'User-Agent': self.user_agent}
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Download attempt {attempt + 1}/{self.max_retries}")
                response = requests.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                
                if binary:
                    return response.content
                else:
                    return response.text
                    
            except requests.RequestException as e:
                logger.warning(f"Download attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Failed to download after {self.max_retries} attempts: {e}")
    
    def _detect_version(self, content: bytes, pattern: Optional[str]) -> str:
        """Detect version from PDF content or filename."""
        if not pattern:
            # Use hash as version if no pattern
            return hashlib.md5(content).hexdigest()[:8]
        
        try:
            # Try to extract text from PDF (first 5000 bytes for speed)
            text_content = content[:5000].decode('utf-8', errors='ignore')
            
            match = re.search(pattern, text_content)
            if match:
                return match.group(1) if match.groups() else match.group(0)
        except Exception as e:
            logger.warning(f"Version detection failed: {e}")
        
        # Fallback to content hash
        return hashlib.md5(content).hexdigest()[:8]
    
    def _save_pdf(self, source_type: str, source_id: str, content: bytes, version: str) -> Path:
        """Save PDF to versioned directory."""
        # Create directory structure
        source_dir = self.docs_dir / source_type / source_id
        version_dir = source_dir / version
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # Save PDF
        file_path = version_dir / f"{source_id}.pdf"
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Create 'latest' symlink
        latest_link = source_dir / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(version_dir.name)
        
        logger.info(f"Saved PDF to {file_path}")
        return file_path
    
    def _create_metadata(self, source_type: str, source_id: str, config: Dict, 
                        version: str, url: str, content: bytes) -> Path:
        """Create metadata file for downloaded source."""
        metadata = {
            'source_type': source_type,
            'source_id': source_id,
            'source_name': config.get('name'),
            'manufacturer': config.get('manufacturer') or config.get('organization'),
            'version': version,
            'source_url': url,
            'fetched_at': datetime.now().isoformat(),
            'content_hash': hashlib.sha256(content).hexdigest(),
            'file_size_bytes': len(content),
            'license': config.get('license'),
            'notes': config.get('notes', '')
        }
        
        # Save metadata
        version_dir = self.docs_dir / source_type / source_id / version
        metadata_path = version_dir / "metadata.json"
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return metadata_path
    
    def check_for_updates(self) -> Dict:
        """
        Check all configured sources for updates.
        
        Returns:
            Dict with update status for each source
        """
        logger.info("Starting update check")
        
        updates_found = {}
        
        for source_info in self.profile.get('knowledge_sources', []):
            source_type = source_info['type']
            source_id = source_info['id']
            current_version = source_info.get('version')
            
            logger.info(f"Checking {source_type}/{source_id} (current: {current_version})")
            
            try:
                # Get current metadata
                current_metadata = self._get_latest_metadata(source_type, source_id)
                
                # Fetch source config
                if source_type == 'pump':
                    source_config = self.registry['insulin_pumps'].get(source_id)
                elif source_type == 'cgm':
                    source_config = self.registry['cgm_devices'].get(source_id)
                else:  # guideline
                    source_config = self.registry['clinical_guidelines'].get(source_id)
                
                # Check if update needed based on time
                last_fetch = datetime.fromisoformat(current_metadata.get('fetched_at', '2000-01-01'))
                update_frequency = source_config.get('update_frequency_days', 30)
                days_since_fetch = (datetime.now() - last_fetch).days
                
                if days_since_fetch < update_frequency:
                    logger.info(f"Too soon to check (only {days_since_fetch} days since last fetch)")
                    updates_found[f"{source_type}_{source_id}"] = {
                        'update_available': False,
                        'reason': 'checked_recently'
                    }
                    continue
                
                # Try to fetch and compare
                new_result = self.fetch_source(source_type, source_id)
                new_version = new_result.get('version')
                
                if new_version != current_version:
                    logger.info(f"Update found! {current_version} -> {new_version}")
                    updates_found[f"{source_type}_{source_id}"] = {
                        'update_available': True,
                        'old_version': current_version,
                        'new_version': new_version,
                        'result': new_result
                    }
                    
                    # Update profile
                    for src in self.profile['knowledge_sources']:
                        if src['type'] == source_type and src['id'] == source_id:
                            src['version'] = new_version
                            src['last_updated'] = datetime.now().isoformat()
                else:
                    logger.info("No update available")
                    updates_found[f"{source_type}_{source_id}"] = {
                        'update_available': False,
                        'reason': 'same_version'
                    }
                
                # Rate limiting
                time.sleep(self.rate_limit_delay)
                
            except Exception as e:
                logger.error(f"Error checking {source_type}/{source_id}: {e}")
                updates_found[f"{source_type}_{source_id}"] = {
                    'error': str(e)
                }
        
        # Update last check time
        self.profile['last_update_check'] = datetime.now().isoformat()
        self._save_profile()
        
        logger.info("Update check completed")
        return updates_found
    
    def _get_latest_metadata(self, source_type: str, source_id: str) -> Dict:
        """Get metadata for the latest version of a source."""
        source_dir = self.docs_dir / source_type / source_id / "latest"
        metadata_path = source_dir / "metadata.json"
        
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                return json.load(f)
        
        return {}
    
    def get_all_sources_status(self) -> List[Dict]:
        """
        Get status of all configured knowledge sources.
        
        Returns:
            List of dicts with source info and status
        """
        statuses = []
        
        for source_info in self.profile.get('knowledge_sources', []):
            source_type = source_info['type']
            source_id = source_info['id']
            
            try:
                metadata = self._get_latest_metadata(source_type, source_id)
                
                # Calculate staleness
                fetched_at = datetime.fromisoformat(metadata.get('fetched_at', '2000-01-01'))
                days_old = (datetime.now() - fetched_at).days
                
                # Determine status
                if days_old > 365:
                    status = 'outdated'
                elif days_old > 180:
                    status = 'stale'
                else:
                    status = 'current'
                
                statuses.append({
                    'type': source_type,
                    'id': source_id,
                    'name': metadata.get('source_name', source_id),
                    'version': metadata.get('version', 'unknown'),
                    'last_updated': metadata.get('fetched_at'),
                    'days_old': days_old,
                    'status': status,
                    'file_path': str(self.docs_dir / source_type / source_id / "latest")
                })
                
            except Exception as e:
                logger.error(f"Error getting status for {source_type}/{source_id}: {e}")
                statuses.append({
                    'type': source_type,
                    'id': source_id,
                    'status': 'error',
                    'error': str(e)
                })
        
        return statuses
    
    def get_user_profile(self) -> Dict:
        """Get current user profile."""
        return self.profile
    
    def update_device(self, device_type: str, device_id: str) -> Dict:
        """
        Change pump or CGM and fetch new manual.
        
        Args:
            device_type: 'pump' or 'cgm'
            device_id: New device ID from registry
            
        Returns:
            Dict with fetch result
        """
        logger.info(f"Updating {device_type} to {device_id}")
        
        # Remove old device from sources
        old_device_id = self.profile['devices'].get(device_type)
        if old_device_id:
            self.profile['knowledge_sources'] = [
                src for src in self.profile['knowledge_sources']
                if not (src['type'] == device_type and src['id'] == old_device_id)
            ]
        
        # Update profile
        self.profile['devices'][device_type] = device_id
        
        # Fetch new manual
        result = self.fetch_source(device_type, device_id)
        
        # Add to sources
        if result['success']:
            self.profile['knowledge_sources'].append({
                'type': device_type,
                'id': device_id,
                'added_at': datetime.now().isoformat(),
                'version': result.get('version', 'unknown')
            })
        
        self._save_profile()
        
        return result


def main():
    """CLI interface for testing."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python knowledge_fetcher.py setup <pump_id> <cgm_id>")
        print("  python knowledge_fetcher.py check-updates")
        print("  python knowledge_fetcher.py status")
        sys.exit(1)
    
    fetcher = KnowledgeFetcher()
    
    command = sys.argv[1]
    
    if command == "setup":
        if len(sys.argv) < 4:
            print("Usage: python knowledge_fetcher.py setup <pump_id> <cgm_id>")
            sys.exit(1)
        
        pump_id = sys.argv[2]
        cgm_id = sys.argv[3]
        
        print(f"Setting up knowledge base for {pump_id} + {cgm_id}...")
        results = fetcher.setup_user_devices(pump_id, cgm_id)
        
        print("\nResults:")
        for source, result in results.items():
            print(f"  {source}: {'✓' if result.get('success') else '✗'}")
            if not result.get('success'):
                print(f"    Error: {result.get('error')}")
    
    elif command == "check-updates":
        print("Checking for updates...")
        updates = fetcher.check_for_updates()
        
        print("\nUpdate Check Results:")
        for source, result in updates.items():
            if result.get('update_available'):
                print(f"  {source}: UPDATE AVAILABLE")
                print(f"    {result['old_version']} -> {result['new_version']}")
            elif result.get('error'):
                print(f"  {source}: ERROR - {result['error']}")
            else:
                print(f"  {source}: Up to date")
    
    elif command == "status":
        statuses = fetcher.get_all_sources_status()
        
        print("\nKnowledge Base Status:")
        for status in statuses:
            print(f"\n  {status['name']}")
            print(f"    Version: {status.get('version', 'unknown')}")
            print(f"    Status: {status['status']}")
            print(f"    Age: {status.get('days_old', '?')} days")
            if status.get('error'):
                print(f"    Error: {status['error']}")


if __name__ == "__main__":
    main()
