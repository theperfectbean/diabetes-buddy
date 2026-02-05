import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.device_detection import DeviceDetector, UserDeviceManager


def test_device_detection_from_text():
    detector = DeviceDetector()
    results = detector.detect_from_content_sample("User manual for Tandem t:slim X2 and Dexcom G6")
    pump = next(r for r in results if r.device_type == "pump" and r.manufacturer == "tandem")
    cgm = next(r for r in results if r.device_type == "cgm" and r.manufacturer == "dexcom")
    assert pump.confidence >= 0.6
    assert cgm.confidence >= 0.6


def test_device_detection_best():
    detector = DeviceDetector()
    best = detector.detect_best("medtronic_guardian_manual.pdf")
    assert best["pump"].manufacturer in {"medtronic"}
    assert best["cgm"].manufacturer in {"guardian", "medtronic"}


def test_user_device_manager_override(tmp_path: Path):
    manager = UserDeviceManager(base_dir=tmp_path)
    profile = manager.apply_user_override("session-abc", pump="tandem", cgm="dexcom")
    assert profile.override_source == "user"
    loaded = manager.load_profile("session-abc")
    assert loaded is not None
    assert loaded.pump == "tandem"
    assert loaded.cgm == "dexcom"
