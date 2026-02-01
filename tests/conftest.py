import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import pytest

@pytest.fixture
def temp_dirs():
    config_dir = tempfile.mkdtemp()
    docs_dir = tempfile.mkdtemp()

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

    shutil.rmtree(config_dir)
    shutil.rmtree(docs_dir)
