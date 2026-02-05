"""
Session Manager for Diabetes Buddy

Handles conversation history persistence across queries.
Stores sessions as JSON files in data/sessions/ directory.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class SessionManager:
    """
    Manages conversation sessions with file-based persistence.

    Each session stores a list of exchanges (query-response pairs)
    that can be retrieved to provide conversation context to agents.
    """

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize the SessionManager.

        Args:
            project_root: Path to project root. Defaults to parent of agents/.
        """
        if project_root is None:
            project_root = Path(__file__).parent.parent
        else:
            project_root = Path(project_root)

        self.sessions_dir = project_root / "data" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.sessions_dir / f"{session_id}.json"

    def create_session(self, session_id: Optional[str] = None) -> str:
        """
        Create a new session.

        Args:
            session_id: Optional custom session ID. If not provided, a UUID is generated.

        Returns:
            The session ID (existing or newly created).
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        session_path = self._session_path(session_id)

        # Only create if it doesn't exist
        if not session_path.exists():
            session_data = {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "exchanges": [],
            }
            with open(session_path, "w") as f:
                json.dump(session_data, f, indent=2)

        return session_id

    def add_exchange(
        self,
        session_id: str,
        query: str,
        response: str,
        classification: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add a query-response exchange to a session.

        Args:
            session_id: The session ID.
            query: The user's query.
            response: The agent's response (can be string or UnifiedResponse).
            classification: Optional classification metadata.

        Returns:
            True if successful, False otherwise.
        """
        session_path = self._session_path(session_id)

        # Create session if it doesn't exist
        if not session_path.exists():
            self.create_session(session_id)

        try:
            with open(session_path, "r") as f:
                session_data = json.load(f)

            # Handle UnifiedResponse objects by extracting the answer
            if hasattr(response, "answer"):
                response_text = response.answer
            else:
                response_text = str(response)

            exchange = {
                "query": query,
                "response": response_text,
                "classification": classification or {},
                "timestamp": datetime.now().isoformat(),
            }

            session_data["exchanges"].append(exchange)
            session_data["updated_at"] = datetime.now().isoformat()

            with open(session_path, "w") as f:
                json.dump(session_data, f, indent=2)

            return True

        except Exception as e:
            print(f"Error adding exchange to session {session_id}: {e}")
            return False

    def get_history(
        self,
        session_id: str,
        max_exchanges: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a session.

        Args:
            session_id: The session ID.
            max_exchanges: Maximum number of recent exchanges to return.

        Returns:
            List of exchange dictionaries, most recent last.
            Each exchange has: query, response, classification, timestamp.
        """
        session_path = self._session_path(session_id)

        if not session_path.exists():
            return []

        try:
            with open(session_path, "r") as f:
                session_data = json.load(f)

            exchanges = session_data.get("exchanges", [])

            # Return the last N exchanges
            return exchanges[-max_exchanges:] if exchanges else []

        except Exception as e:
            print(f"Error reading session {session_id}: {e}")
            return []

    def clear_session(self, session_id: str) -> bool:
        """
        Clear all exchanges from a session (but keep the session).

        Args:
            session_id: The session ID.

        Returns:
            True if successful, False otherwise.
        """
        session_path = self._session_path(session_id)

        if not session_path.exists():
            return False

        try:
            with open(session_path, "r") as f:
                session_data = json.load(f)

            session_data["exchanges"] = []
            session_data["updated_at"] = datetime.now().isoformat()

            with open(session_path, "w") as f:
                json.dump(session_data, f, indent=2)

            return True

        except Exception as e:
            print(f"Error clearing session {session_id}: {e}")
            return False

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session completely.

        Args:
            session_id: The session ID.

        Returns:
            True if deleted, False if session didn't exist or error.
        """
        session_path = self._session_path(session_id)

        if not session_path.exists():
            return False

        try:
            session_path.unlink()
            return True
        except Exception as e:
            print(f"Error deleting session {session_id}: {e}")
            return False

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        return self._session_path(session_id).exists()

    def format_history_for_prompt(
        self,
        history: List[Dict[str, Any]],
    ) -> str:
        """
        Format conversation history for inclusion in LLM prompts.

        Args:
            history: List of exchange dictionaries from get_history().

        Returns:
            Formatted string suitable for prompt inclusion.
        """
        if not history:
            return ""

        formatted_parts = []
        for i, exchange in enumerate(history, 1):
            query = exchange.get("query", "")
            response = exchange.get("response", "")

            # Truncate long responses to keep prompt manageable
            if len(response) > 500:
                response = response[:500] + "..."

            formatted_parts.append(f"User: {query}")
            formatted_parts.append(f"Assistant: {response}")
            formatted_parts.append("")  # Blank line between exchanges

        return "\n".join(formatted_parts).strip()
