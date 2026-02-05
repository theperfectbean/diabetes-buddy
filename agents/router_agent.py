"""
Router Agent for Agentic RAG Architecture

Analyzes queries to extract structured context BEFORE retrieval, including:
- Device detection and automation mode
- Device interaction layer (hardware vs app)
- User intent and constraints
- Source suggestions and exclusions

This enables context-aware retrieval and prevents hallucinations like suggesting
extended bolus to automated insulin delivery users.
"""

import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional, List
from enum import Enum

from .llm_provider import LLMFactory, GenerationConfig

logger = logging.getLogger(__name__)


class AutomationMode(Enum):
    """Insulin delivery automation mode."""
    AUTOMATED = "automated"  # CamAPS FX, Control-IQ, Loop, etc.
    MANUAL = "manual"  # Manual MDI or pump control
    UNKNOWN = "unknown"  # Cannot determine from query


class DeviceInteractionLayer(Enum):
    """Where user needs to interact with their device."""
    PUMP_HARDWARE = "pump_hardware"  # Physical pump buttons/screen
    ALGORITHM_APP = "algorithm_app"  # Phone app (CamAPS FX, etc.)
    CGM_SENSOR = "cgm_sensor"  # CGM sensor/transmitter
    MULTIPLE = "multiple"  # Multiple interaction points
    UNKNOWN = "unknown"  # Cannot determine


@dataclass
class RouterContext:
    """Structured context extracted from query by router."""
    
    # Device and automation context
    devices_mentioned: List[str]  # e.g., ["CamAPS FX", "Dana-i", "Dexcom G6"]
    automation_mode: AutomationMode
    device_interaction_layer: DeviceInteractionLayer
    
    # Query understanding
    user_intent: str  # What user is trying to accomplish
    key_constraints: List[str]  # Important constraints (e.g., "slow-absorbing meal")
    temporal_context: Optional[str]  # Time-related context (e.g., "now", "tonight")
    
    # Retrieval guidance
    suggested_sources: List[str]  # Knowledge base sources to prioritize
    exclude_sources: List[str]  # Sources to exclude
    
    # Confidence
    confidence: float  # 0.0-1.0 confidence in analysis
    reasoning: str  # Explanation of decisions
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "devices_mentioned": self.devices_mentioned,
            "automation_mode": self.automation_mode.value,
            "device_interaction_layer": self.device_interaction_layer.value,
            "user_intent": self.user_intent,
            "key_constraints": self.key_constraints,
            "temporal_context": self.temporal_context,
            "suggested_sources": self.suggested_sources,
            "exclude_sources": self.exclude_sources,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


class RouterAgent:
    """
    Router Agent that analyzes queries to extract structured context.
    
    CRITICAL SAFETY RULES:
    1. If CamAPS FX/Control-IQ/Loop detected → automation_mode = AUTOMATED
    2. If AUTOMATED → exclude manual_bolus_features (extended/combo bolus)
    3. If AUTOMATED + slow-carb meal → suggest camaps_app_features
    4. If AUTOMATED → interaction_layer usually ALGORITHM_APP
    """
    
    # Automated insulin delivery systems
    AUTOMATED_SYSTEMS = [
        "camaps fx", "camaps", "cam aps",
        "control-iq", "control iq", "controliq",
        "loop", "openaps", "androidaps", "iaps",
        "medtronic 670g", "medtronic 770g", "medtronic 780g",
        "omnipod 5", "omnipod5",
        "diabeloop",
    ]
    
    # Device brands and models
    INSULIN_PUMPS = [
        "dana-i", "dana rs", "dana",
        "omnipod", "medtronic", "tandem",
        "t:slim", "tslim", "ypsopump",
    ]
    
    CGM_DEVICES = [
        "dexcom", "g6", "g7", "libre",
        "freestyle libre", "guardian",
    ]
    
    ROUTER_PROMPT_TEMPLATE = """You are a query analysis expert for diabetes management queries.
Analyze the user's query and extract structured context to guide retrieval and response generation.

CRITICAL SAFETY RULES:
1. If query mentions CamAPS FX, Control-IQ, Loop, or any automated insulin delivery → automation_mode = "automated"
2. If automation_mode = "automated" → user CANNOT use extended or combination bolus (disabled in closed-loop)
3. If automation_mode = "automated" + query about slow carbs/meals → suggested_sources MUST include "camaps_app_features" and exclude_sources MUST include "manual_bolus_features"
4. If automation_mode = "automated" → device_interaction_layer is usually "algorithm_app" (phone app, not pump hardware)
5. Manual pump users interact with "pump_hardware"
6. Be conservative: if unsure about automation mode, use "unknown"

QUERY ANALYSIS TASKS:
1. Identify devices mentioned or implied (insulin pumps, CGMs, apps)
2. Determine automation mode (automated/manual/unknown)
3. Identify where user needs to interact (pump buttons vs phone app vs CGM)
4. Extract user's intent (manage meal, troubleshoot spike, learn feature, change settings)
5. Note key constraints (slow-absorbing meal, exercise, etc.)
6. Note temporal context (now, tonight, during exercise)
7. Suggest knowledge base sources to prioritize
8. List sources to EXCLUDE (critical for safety - e.g., exclude manual bolus for automated users)

CONVERSATION HISTORY (if available):
{conversation_history}

USER QUERY:
{query}

OUTPUT FORMAT - Return ONLY valid JSON with this exact structure:
{{
  "devices_mentioned": ["device1", "device2"],
  "automation_mode": "automated|manual|unknown",
  "device_interaction_layer": "pump_hardware|algorithm_app|cgm_sensor|multiple|unknown",
  "user_intent": "brief description of what user wants to accomplish",
  "key_constraints": ["constraint1", "constraint2"],
  "temporal_context": "time-related context or null",
  "suggested_sources": ["source1", "source2"],
  "exclude_sources": ["source1", "source2"],
  "confidence": 0.85,
  "reasoning": "brief explanation of analysis decisions"
}}

EXAMPLES:

Query: "I use CamAPS FX with my Dana-i pump. How do I handle slow-absorbing meals like pizza?"
{{
  "devices_mentioned": ["CamAPS FX", "Dana-i"],
  "automation_mode": "automated",
  "device_interaction_layer": "algorithm_app",
  "user_intent": "manage slow-absorbing meal with automated insulin delivery",
  "key_constraints": ["slow-absorbing meal", "pizza"],
  "temporal_context": null,
  "suggested_sources": ["camaps_app_features", "meal_management", "absorption_profiles"],
  "exclude_sources": ["manual_bolus_features", "extended_bolus"],
  "confidence": 0.95,
  "reasoning": "CamAPS FX detected → automated mode. Slow meal query → suggest app features, exclude manual bolus which is incompatible with automation."
}}

Query: "How do I program an extended bolus on my pump for pasta?"
{{
  "devices_mentioned": [],
  "automation_mode": "manual",
  "device_interaction_layer": "pump_hardware",
  "user_intent": "program extended bolus for slow-absorbing meal",
  "key_constraints": ["slow-absorbing meal", "pasta"],
  "temporal_context": null,
  "suggested_sources": ["manual_bolus_features", "pump_hardware_guide", "extended_bolus"],
  "exclude_sources": [],
  "confidence": 0.90,
  "reasoning": "Explicit request for extended bolus programming → manual mode. Needs pump hardware interaction."
}}

Query: "My glucose is spiking after breakfast"
{{
  "devices_mentioned": [],
  "automation_mode": "unknown",
  "device_interaction_layer": "unknown",
  "user_intent": "troubleshoot post-meal glucose spike",
  "key_constraints": ["breakfast", "glucose spike"],
  "temporal_context": "after breakfast",
  "suggested_sources": ["meal_management", "troubleshooting", "glucose_patterns"],
  "exclude_sources": [],
  "confidence": 0.60,
  "reasoning": "No device mentioned, cannot determine automation mode. Need clarification before suggesting device-specific solutions."
}}

Now analyze the query above and return ONLY the JSON response:"""

    def __init__(self):
        """Initialize router agent with LLM provider."""
        self.llm = LLMFactory.get_provider()
        logger.debug("RouterAgent initialized")
    
    def analyze_query(
        self,
        query: str,
        conversation_history: Optional[List[dict]] = None,
    ) -> RouterContext:
        """
        Analyze query to extract structured context for retrieval.
        
        Args:
            query: User's query
            conversation_history: Optional list of recent message pairs
                                Format: [{"role": "user", "content": "..."}, ...]
        
        Returns:
            RouterContext with extracted context
        
        Raises:
            Exception: If LLM call fails or JSON parsing fails
        """
        # Format conversation history for prompt
        history_str = ""
        if conversation_history:
            history_str = "\n".join([
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in conversation_history[-10:]  # Last 10 messages
            ])
        else:
            history_str = "(No conversation history)"
        
        # Build prompt
        prompt = self.ROUTER_PROMPT_TEMPLATE.format(
            conversation_history=history_str,
            query=query,
        )
        
        try:
            # Call LLM with low temperature for consistent JSON output
            response_text = self.llm.generate_text(
                prompt=prompt,
                config=GenerationConfig(temperature=0.3, max_tokens=1000),
            )
            
            # Handle markdown code blocks
            if response_text.strip().startswith("```"):
                lines = response_text.strip().split("\n")
                # Remove first line (```json or ```) and last line (```)
                response_text = "\n".join(lines[1:-1])
            
            # Parse JSON
            data = json.loads(response_text.strip())
            
            # Build RouterContext
            context = RouterContext(
                devices_mentioned=data.get("devices_mentioned", []),
                automation_mode=AutomationMode(data["automation_mode"]),
                device_interaction_layer=DeviceInteractionLayer(data["device_interaction_layer"]),
                user_intent=data["user_intent"],
                key_constraints=data.get("key_constraints", []),
                temporal_context=data.get("temporal_context"),
                suggested_sources=data.get("suggested_sources", []),
                exclude_sources=data.get("exclude_sources", []),
                confidence=float(data["confidence"]),
                reasoning=data["reasoning"],
            )
            
            logger.info(
                f"[ROUTER] automation_mode={context.automation_mode.value} | "
                f"interaction_layer={context.device_interaction_layer.value} | "
                f"devices={context.devices_mentioned} | "
                f"confidence={context.confidence:.2f}"
            )
            
            # Log exclusions for safety
            if context.exclude_sources:
                logger.info(f"[ROUTER] EXCLUDING sources: {context.exclude_sources}")
            
            return context
            
        except json.JSONDecodeError as e:
            logger.error(f"[ROUTER] Failed to parse JSON response: {e}")
            logger.error(f"[ROUTER] Raw response: {response_text}")
            # Return safe fallback
            return self._fallback_context(query)
        except Exception as e:
            logger.error(f"[ROUTER] Query analysis failed: {e}")
            return self._fallback_context(query)
    
    def _fallback_context(self, query: str) -> RouterContext:
        """
        Generate safe fallback context when LLM analysis fails.
        
        Returns conservative context that triggers clarification questions.
        """
        logger.warning("[ROUTER] Using fallback context")
        return RouterContext(
            devices_mentioned=[],
            automation_mode=AutomationMode.UNKNOWN,
            device_interaction_layer=DeviceInteractionLayer.UNKNOWN,
            user_intent="Query analysis failed - needs clarification",
            key_constraints=[],
            temporal_context=None,
            suggested_sources=[],
            exclude_sources=[],
            confidence=0.0,
            reasoning="LLM analysis failed, returning safe fallback",
        )
