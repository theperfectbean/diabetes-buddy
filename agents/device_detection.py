"""Device detection and user device profile management."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None

# Re-export for backward compatibility
from agents.experimentation import anonymize_session_id

logger = logging.getLogger(__name__)


PUMP_MANUFACTURERS = {
    "tandem": ["tandem", "t:slim", "tslim", "control-iq", "control iq"],
    "medtronic": ["medtronic", "minimed", "guardian link"],
    "omnipod": ["omnipod", "insulet", "pod"],
    "ypsomed": ["ypsomed", "mylife", "ypsopump"],
    "insulet": ["insulet"],
    "roche": ["roche", "accu-chek", "accuchek"],
    "sooil": ["sooil", "dana", "dana-i", "dana r"],
    "aeq": ["aeq", "kusur"],
}

CGM_MANUFACTURERS = {
    "dexcom": ["dexcom", "g6", "g7"],
    "libre": ["freestyle", "libre", "abbott"],
    "guardian": ["guardian", "medtronic"],
}


@dataclass
class DeviceDetectionResult:
    device_type: str
    manufacturer: str
    confidence: float
    method: str
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class UserDeviceProfile:
    session_id: str
    pump: Optional[str] = None
    cgm: Optional[str] = None
    override_source: str = "auto_detected"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))


class DeviceDetector:
    """Detect devices from PDF metadata, filename, or content sample."""

    def detect_from_pdf_metadata(self, metadata: Dict[str, Any]) -> List[DeviceDetectionResult]:
        text = " ".join(str(value) for value in metadata.values() if value)
        return self._detect_from_text(text, method="metadata")

    def detect_from_filename(self, filename: str) -> List[DeviceDetectionResult]:
        return self._detect_from_text(filename, method="filename")

    def detect_from_content_sample(self, sample_text: str) -> List[DeviceDetectionResult]:
        return self._detect_from_text(sample_text, method="content")

    def detect_from_pdf(self, pdf_path: Path) -> List[DeviceDetectionResult]:
        if PdfReader is None:
            raise RuntimeError("PyPDF2 is required for PDF parsing")
        reader = PdfReader(str(pdf_path))
        metadata = reader.metadata or {}
        content = ""
        for page in reader.pages[:2]:
            content += page.extract_text() or ""
        results = []
        results.extend(self.detect_from_pdf_metadata(metadata))
        results.extend(self.detect_from_content_sample(content))
        return self._deduplicate_results(results)

    def detect_from_file(self, file_path: str) -> Dict[str, any]:
        """
        Detect devices from a PDF file and return a flat dictionary
        with pump/cgm names and confidence scores.
        
        Returns:
        {
            "pump": "tandem" or None,
            "cgm": "dexcom" or None,
            "pump_confidence": 0.95,
            "cgm_confidence": 0.85
        }
        """
        try:
            pdf_path = Path(file_path)
            filename = pdf_path.name
            
            # Get metadata from PDF
            metadata = None
            if PdfReader is not None:
                try:
                    reader = PdfReader(str(pdf_path))
                    metadata = reader.metadata or {}
                except Exception:
                    pass
            
            # Get text sample from PDF
            sample_text = None
            if PdfReader is not None:
                try:
                    reader = PdfReader(str(pdf_path))
                    content = ""
                    for page in reader.pages[:2]:
                        content += page.extract_text() or ""
                    if content.strip():
                        sample_text = content
                except Exception:
                    pass
            
            # Use detect_best to find devices
            best = self.detect_best(filename, metadata=metadata, sample_text=sample_text)
            
            # Extract pump and cgm results
            pump_result = best.get("pump")
            cgm_result = best.get("cgm")
            
            return {
                "pump": pump_result.manufacturer if pump_result else None,
                "cgm": cgm_result.manufacturer if cgm_result else None,
                "pump_confidence": pump_result.confidence if pump_result else 0.0,
                "cgm_confidence": cgm_result.confidence if cgm_result else 0.0
            }
        except Exception as e:
            logger.error(f"Error detecting devices from file {file_path}: {e}")
            return {
                "pump": None,
                "cgm": None,
                "pump_confidence": 0.0,
                "cgm_confidence": 0.0,
                "error": str(e)
            }

    def detect_best(self, filename: str, metadata: Optional[Dict[str, Any]] = None, sample_text: Optional[str] = None) -> Dict[str, DeviceDetectionResult]:
        results: List[DeviceDetectionResult] = []
        results.extend(self.detect_from_filename(filename))
        if metadata:
            results.extend(self.detect_from_pdf_metadata(metadata))
        if sample_text:
            results.extend(self.detect_from_content_sample(sample_text))
        results = self._deduplicate_results(results)
        best: Dict[str, DeviceDetectionResult] = {}
        for result in results:
            current = best.get(result.device_type)
            if current is None or result.confidence > current.confidence:
                best[result.device_type] = result
        return best

    def _detect_from_text(self, text: str, method: str) -> List[DeviceDetectionResult]:
        normalized = self._normalize(text)
        results: List[DeviceDetectionResult] = []
        results.extend(self._score_manufacturers("pump", PUMP_MANUFACTURERS, normalized, method))
        results.extend(self._score_manufacturers("cgm", CGM_MANUFACTURERS, normalized, method))
        return results

    def _score_manufacturers(
        self,
        device_type: str,
        manufacturers: Dict[str, List[str]],
        normalized_text: str,
        method: str,
    ) -> List[DeviceDetectionResult]:
        results = []
        for manufacturer, keywords in manufacturers.items():
            matched = [keyword for keyword in keywords if keyword in normalized_text]
            if not matched:
                continue
            confidence = min(0.6 + 0.1 * len(matched), 0.99)
            results.append(
                DeviceDetectionResult(
                    device_type=device_type,
                    manufacturer=manufacturer,
                    confidence=confidence,
                    method=method,
                    matched_keywords=matched,
                )
            )
        return results

    def _deduplicate_results(self, results: List[DeviceDetectionResult]) -> List[DeviceDetectionResult]:
        seen = set()
        deduped = []
        for result in results:
            key = (result.device_type, result.manufacturer)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(result)
        return deduped

    @staticmethod
    def _normalize(text: str) -> str:
        return (text or "").lower().replace("-", " ")


class UserDeviceManager:
    """Persist and update user device profiles."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(base_dir or "data/users")

    def load_profile(self, session_id: str) -> Optional[UserDeviceProfile]:
        path = self._profile_path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return UserDeviceProfile(
            session_id=data.get("session_id") or session_id,
            pump=data.get("pump"),
            cgm=data.get("cgm"),
            override_source=data.get("override_source", "auto_detected"),
            timestamp=data.get("timestamp")
            or data.get("detected_at")
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    def save_profile(self, profile: UserDeviceProfile) -> None:
        path = self._profile_path(profile.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": profile.session_id,
            "pump": profile.pump,
            "cgm": profile.cgm,
            "timestamp": profile.timestamp,
            "override_source": profile.override_source,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_from_upload(
        self,
        session_id: str,
        detected_devices: Dict[str, DeviceDetectionResult],
    ) -> UserDeviceProfile:
        profile = UserDeviceProfile(
            session_id=session_id,
            pump=detected_devices.get("pump").manufacturer if detected_devices.get("pump") else None,
            cgm=detected_devices.get("cgm").manufacturer if detected_devices.get("cgm") else None,
            override_source="auto_detected",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        self.save_profile(profile)
        return profile

    def apply_user_override(self, session_id: str, pump: Optional[str], cgm: Optional[str]) -> UserDeviceProfile:
        profile = self.load_profile(session_id) or UserDeviceProfile(session_id=session_id)
        profile.pump = pump or profile.pump
        profile.cgm = cgm or profile.cgm
        profile.override_source = "user"
        profile.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.save_profile(profile)
        return profile

    def _profile_path(self, session_id: str) -> Path:
        safe_session_id = str(session_id).replace("/", "_").replace("\\", "_")
        return self.base_dir / safe_session_id / "devices.json"
