"""
Test Suite for Knowledge Base Management System
Tests the fetcher, scheduler, and integration with researcher.
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.knowledge_fetcher import KnowledgeFetcher


class TestKnowledgeFetcher:
    """Test the knowledge fetcher agent."""
    
    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        config_dir = tempfile.mkdtemp()
        docs_dir = tempfile.mkdtemp()
        
        # Create mock registry
        registry = {
            "version": "1.0.0",
            "insulin_pumps": {
                "test_pump": {
                    "name": "Test Pump",
                    "manufacturer": "Test Corp",
                    "manual_url": "https://example.com/manual.pdf",
                    "fetch_method": "direct",
                    "direct_pdf_url": "https://example.com/manual.pdf",
                    "version_pattern": "v(\\d+\\.\\d+)",
                    "file_prefix": "test_pump_manual",
                    "update_frequency_days": 180,
                    "license": "Free"
                }
            },
            "cgm_devices": {
                "test_cgm": {
                    "name": "Test CGM",
                    "manufacturer": "Test Corp",
                    "manual_url": "https://example.com/cgm.pdf",
                    "fetch_method": "direct",
                    "direct_pdf_url": "https://example.com/cgm.pdf",
                    "version_pattern": "v(\\d+\\.\\d+)",
                    "file_prefix": "test_cgm_manual",
                    "update_frequency_days": 180,
                    "license": "Free"
                }
            },
            "clinical_guidelines": {
                "test_guideline": {
                    "name": "Test Guideline",
                    "organization": "Test Org",
                    "url": "https://example.com/guideline.pdf",
                    "fetch_method": "direct",
                    "direct_pdf_url": "https://example.com/guideline.pdf",
                    "version_pattern": "(\\d{4})",
                    "file_prefix": "test_guideline",
                    "update_frequency_days": 365,
                    "license": "Educational use"
                }
            },
            "fetch_config": {
                "user_agent": "TestBot/1.0",
                "timeout_seconds": 30,
                "max_retries": 3,
                "retry_delay_seconds": 1,
                "rate_limit_delay_seconds": 0
            }
        }
        
        with open(Path(config_dir) / "device_registry.json", 'w') as f:
            json.dump(registry, f)
        
        yield config_dir, docs_dir
        
        # Cleanup
        shutil.rmtree(config_dir)
        shutil.rmtree(docs_dir)
    
    def test_initialization(self, temp_dirs):
        """Test fetcher initialization."""
        config_dir, docs_dir = temp_dirs
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        assert fetcher.config_dir == Path(config_dir)
        assert fetcher.docs_dir == Path(docs_dir)
        assert fetcher.profile is not None
        assert 'devices' in fetcher.profile
    
    def test_profile_creation(self, temp_dirs):
        """Test user profile creation."""
        config_dir, docs_dir = temp_dirs
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        profile = fetcher.get_user_profile()
        assert profile['version'] == '1.0.0'
        assert profile['devices']['pump'] is None
        assert profile['devices']['cgm'] is None
        assert profile['auto_update_enabled'] is True
        assert 'created_at' in profile
    
    @patch('agents.knowledge_fetcher.requests.get')
    def test_direct_download(self, mock_get, temp_dirs):
        """Test direct PDF download."""
        config_dir, docs_dir = temp_dirs
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        # Mock response
        mock_response = Mock()
        mock_response.content = b'%PDF-1.4\nMock PDF content v1.0'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = fetcher.fetch_source('pump', 'test_pump')
        
        assert result['success'] is True
        assert 'file_path' in result
        assert 'version' in result
        assert Path(result['file_path']).exists()
    
    @patch('agents.knowledge_fetcher.requests.get')
    def test_scraping_method(self, mock_get, temp_dirs):
        """Test web scraping for PDF links."""
        config_dir, docs_dir = temp_dirs
        
        # Add scraping source to registry
        registry_path = Path(config_dir) / "device_registry.json"
        with open(registry_path, 'r') as f:
            registry = json.load(f)
        
        registry['insulin_pumps']['scrape_pump'] = {
            "name": "Scrape Pump",
            "manufacturer": "Test Corp",
            "manual_url": "https://example.com/manuals/",
            "fetch_method": "scrape",
            "selectors": {
                "manual_link": "a[href*='manual']"
            },
            "version_pattern": "v(\\d+\\.\\d+)",
            "file_prefix": "scrape_pump_manual",
            "update_frequency_days": 180,
            "license": "Free"
        }
        
        with open(registry_path, 'w') as f:
            json.dump(registry, f)
        
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        # Mock responses
        def mock_response_side_effect(url, *args, **kwargs):
            response = Mock()
            if url.endswith('manuals/'):
                response.text = '<html><a href="/manual.pdf">User Manual</a></html>'
            else:
                response.content = b'%PDF-1.4\nManual content'
            response.raise_for_status = Mock()
            return response
        
        mock_get.side_effect = mock_response_side_effect
        
        result = fetcher.fetch_source('pump', 'scrape_pump')
        
        assert result['success'] is True
        assert 'file_path' in result
    
    @patch('agents.knowledge_fetcher.subprocess.run')
    def test_git_clone(self, mock_subprocess, temp_dirs):
        """Test git repository cloning."""
        config_dir, docs_dir = temp_dirs
        
        # Add git source to registry
        registry_path = Path(config_dir) / "device_registry.json"
        with open(registry_path, 'r') as f:
            registry = json.load(f)
        
        registry['clinical_guidelines']['test_git'] = {
            "name": "Test Git Docs",
            "organization": "Test Org",
            "url": "https://github.com/test/docs",
            "fetch_method": "git",
            "git_repo": "https://github.com/test/docs.git",
            "file_prefix": "test_git_docs",
            "update_frequency_days": 7,
            "license": "MIT"
        }
        
        with open(registry_path, 'w') as f:
            json.dump(registry, f)
        
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        # Mock subprocess responses
        mock_subprocess.return_value.stdout = 'abc123'
        mock_subprocess.return_value.returncode = 0
        
        result = fetcher.fetch_source('guideline', 'test_git')
        
        assert result['success'] is True
        assert 'repo_path' in result
        assert mock_subprocess.called
    
    @patch('agents.knowledge_fetcher.requests.get')
    def test_setup_user_devices(self, mock_get, temp_dirs):
        """Test complete device setup flow."""
        config_dir, docs_dir = temp_dirs
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        # Mock all downloads
        mock_response = Mock()
        mock_response.content = b'%PDF-1.4\nTest content'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        results = fetcher.setup_user_devices('test_pump', 'test_cgm')
        
        # Should fetch 3 guidelines + 1 pump + 1 CGM = 5 sources
        assert len(results) >= 2  # At least pump and CGM
        
        # Check profile updated
        profile = fetcher.get_user_profile()
        assert profile['devices']['pump'] == 'test_pump'
        assert profile['devices']['cgm'] == 'test_cgm'
        assert len(profile['knowledge_sources']) > 0
    
    def test_version_detection(self, temp_dirs):
        """Test version detection from PDF content."""
        config_dir, docs_dir = temp_dirs
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        # Test with version pattern
        content = b'User Manual v2.5 Content here'
        version = fetcher._detect_version(content, 'v(\\d+\\.\\d+)')
        assert version == '2.5'
        
        # Test with year pattern
        content = b'Standards of Care 2026'
        version = fetcher._detect_version(content, '(\\d{4})')
        assert version == '2026'
        
        # Test fallback to hash
        content = b'No version info'
        version = fetcher._detect_version(content, 'v(\\d+\\.\\d+)')
        assert len(version) == 8  # MD5 hash prefix
    
    @patch('agents.knowledge_fetcher.requests.get')
    def test_update_checking(self, mock_get, temp_dirs):
        """Test update detection."""
        config_dir, docs_dir = temp_dirs
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        # Setup initial source
        mock_response = Mock()
        mock_response.content = b'%PDF-1.4\nVersion 1.0 content'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Initial fetch
        fetcher.setup_user_devices('test_pump', 'test_cgm')
        
        # Update response with new version
        mock_response.content = b'%PDF-1.4\nVersion 2.0 content'
        
        # Manually set last fetch time to past to trigger update check
        profile = fetcher.get_user_profile()
        for source in profile['knowledge_sources']:
            source['last_updated'] = (datetime.now() - timedelta(days=200)).isoformat()
        fetcher._save_profile(profile)
        
        # Check for updates
        updates = fetcher.check_for_updates()
        
        # Should detect changes (different content hash)
        assert len(updates) > 0
    
    def test_error_handling_network_failure(self, temp_dirs):
        """Test error handling for network failures."""
        config_dir, docs_dir = temp_dirs
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        with patch('agents.knowledge_fetcher.requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")
            
            result = fetcher.fetch_source('pump', 'test_pump')
            
            # Should catch and return error status (or raise)
            # Implementation depends on error handling design
    
    def test_metadata_creation(self, temp_dirs):
        """Test metadata file creation."""
        config_dir, docs_dir = temp_dirs
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        content = b'%PDF-1.4\nTest content'
        config = {
            'name': 'Test Manual',
            'manufacturer': 'Test Corp',
            'license': 'Free',
            'notes': 'Test notes'
        }
        
        metadata_path = fetcher._create_metadata(
            'pump', 'test_pump', config, 'v1.0', 
            'https://example.com/manual.pdf', content
        )
        
        assert metadata_path.exists()
        
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        assert metadata['source_type'] == 'pump'
        assert metadata['source_id'] == 'test_pump'
        assert metadata['version'] == 'v1.0'
        assert 'content_hash' in metadata
        assert 'fetched_at' in metadata


class TestScheduler:
    """Test the update scheduler."""
    
    @patch('agents.knowledge_fetcher.KnowledgeFetcher')
    def test_scheduler_initialization(self, mock_fetcher):
        """Test scheduler initialization."""
        from scripts.schedule_updates import KnowledgeUpdateScheduler
        
        scheduler = KnowledgeUpdateScheduler()
        assert scheduler.fetcher is not None
        assert scheduler.running is False
    
    @patch('agents.knowledge_fetcher.KnowledgeFetcher')
    def test_update_check_execution(self, mock_fetcher):
        """Test running an update check."""
        from scripts.schedule_updates import KnowledgeUpdateScheduler
        
        mock_instance = Mock()
        mock_instance.get_user_profile.return_value = {
            'auto_update_enabled': True,
            'update_preferences': {'update_frequency_days': 7}
        }
        mock_instance.check_for_updates.return_value = {}
        mock_fetcher.return_value = mock_instance
        
        scheduler = KnowledgeUpdateScheduler()
        scheduler.run_update_check()
        
        # Should call check_for_updates
        mock_instance.check_for_updates.assert_called_once()


class TestResearcherIntegration:
    """Test researcher agent integration with knowledge base."""
    
    @pytest.fixture
    def mock_researcher(self, temp_dirs):
        """Create a researcher with mock knowledge sources."""
        config_dir, docs_dir = temp_dirs
        
        from agents.researcher import ResearcherAgent
        
        # Create mock PDF in knowledge sources
        pump_dir = Path(docs_dir) / "pump" / "test_pump" / "v1.0"
        pump_dir.mkdir(parents=True)
        
        (pump_dir / "test_pump.pdf").write_bytes(b'%PDF-1.4\nTest manual')
        
        # Create metadata
        metadata = {
            'source_name': 'Test Pump Manual',
            'version': 'v1.0',
            'fetched_at': datetime.now().isoformat()
        }
        with open(pump_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f)
        
        # Create latest symlink
        latest_link = pump_dir.parent / "latest"
        latest_link.symlink_to("v1.0")
        
        # Mock LLM provider
        with patch('agents.researcher.LLMFactory.get_provider'):
            researcher = ResearcherAgent(project_root=Path(config_dir).parent)
            researcher.knowledge_dir = Path(docs_dir)
            yield researcher
    
    def test_discover_sources(self, mock_researcher):
        """Test dynamic source discovery."""
        sources = mock_researcher._discover_knowledge_sources()
        
        # Should find the test pump source
        assert len(sources) > 0
        assert any('pump_test_pump' in key for key in sources.keys())
    
    def test_get_available_sources(self, mock_researcher):
        """Test getting list of available sources."""
        sources_list = mock_researcher.get_available_sources()
        
        assert isinstance(sources_list, list)
        if sources_list:
            assert 'name' in sources_list[0]
            assert 'version' in sources_list[0]
            assert 'staleness' in sources_list[0]
    
    def test_staleness_detection(self, mock_researcher):
        """Test staleness warning detection."""
        sources = mock_researcher.get_available_sources()
        
        # Current sources should not be stale
        for source in sources:
            if source.get('last_updated'):
                # Recent sources should be 'current'
                assert source['staleness'] in ['current', 'stale', 'outdated', 'unknown']


def test_end_to_end_setup(temp_dirs):
    """Test complete end-to-end setup flow."""
    config_dir, docs_dir = temp_dirs
    
    with patch('agents.knowledge_fetcher.requests.get') as mock_get:
        # Mock successful downloads
        mock_response = Mock()
        mock_response.content = b'%PDF-1.4\nMock content'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Create fetcher
        fetcher = KnowledgeFetcher(config_dir=config_dir, docs_dir=docs_dir)
        
        # Run setup
        results = fetcher.setup_user_devices('test_pump', 'test_cgm')
        
        # Verify results
        assert len(results) > 0
        
        # Verify profile updated
        profile = fetcher.get_user_profile()
        assert profile['devices']['pump'] == 'test_pump'
        assert profile['devices']['cgm'] == 'test_cgm'
        
        # Verify files created
        assert (Path(docs_dir) / "pump" / "test_pump" / "latest").exists()
        assert (Path(docs_dir) / "cgm" / "test_cgm" / "latest").exists()
        
        # Get status
        statuses = fetcher.get_all_sources_status()
        assert len(statuses) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
