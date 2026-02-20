"""
HumanModel: Learning who the user is.

This is the killer feature — Vecna builds a model of the human it serves.
Preferences, communication style, emotional context, recurring patterns.
The substrate learns and adapts without being told.
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from vecna.core.types import SerializableMixin


@dataclass
class Preference(SerializableMixin):
    """A learned preference about the user."""

    key: str = ""  # Category: "language", "tone", "response_length", etc.
    value: str = ""  # The preference value
    confidence: float = 0.5  # 0.0 - 1.0
    observed_count: int = 1
    first_observed: datetime = field(default_factory=datetime.now)
    last_observed: datetime = field(default_factory=datetime.now)
    context: Optional[str] = None  # When this preference applies

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Preference":
        data = data.copy()
        for dt_key in ("first_observed", "last_observed"):
            if dt_key in data and isinstance(data[dt_key], str):
                data[dt_key] = datetime.fromisoformat(data[dt_key])
        return cls(**data)


@dataclass
class CommunicationStyle(SerializableMixin):
    """
    Learned communication preferences.

    Each dimension is 0.0 to 1.0:
    - 0.0 = low/minimal
    - 0.5 = neutral/default
    - 1.0 = high/maximum
    """

    verbosity: float = 0.5  # 0=terse, 1=verbose
    formality: float = 0.5  # 0=casual, 1=formal
    technical_depth: float = 0.5  # 0=simple, 1=expert
    emoji_usage: float = 0.0  # 0=never, 1=frequent
    humor: float = 0.3  # 0=serious, 1=playful

    # Signal map for dimension adjustments (not serialized by default via to_dict override)
    _SIGNAL_MAP: Dict[str, Dict[str, float]] = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        # Class-level constant stored as instance attr to avoid dataclass field issues
        self._SIGNAL_MAP = {
            "short_response_preferred": {"verbosity": -0.1},
            "long_response_preferred": {"verbosity": 0.1},
            "asked_for_details": {"technical_depth": 0.1, "verbosity": 0.05},
            "asked_to_simplify": {"technical_depth": -0.1},
            "used_emoji": {"emoji_usage": 0.05},
            "formal_language": {"formality": 0.1},
            "casual_language": {"formality": -0.1},
            "made_joke": {"humor": 0.05},
        }

    def update_from_signal(self, signal: str, strength: float = 1.0) -> None:
        """Update style dimensions from an observed signal."""
        adjustments = self._SIGNAL_MAP.get(signal, {})
        for dim, delta in adjustments.items():
            current = getattr(self, dim, 0.5)
            new_val = max(0.0, min(1.0, current + delta * strength))
            setattr(self, dim, new_val)

    def to_prompt_directive(self) -> str:
        """Generate a prompt directive reflecting learned style."""
        parts: List[str] = []
        if self.verbosity < 0.3:
            parts.append("Be extremely concise and direct.")
        elif self.verbosity > 0.7:
            parts.append("Provide thorough, detailed explanations.")

        if self.formality > 0.7:
            parts.append("Use formal, professional language.")
        elif self.formality < 0.3:
            parts.append("Keep it casual and conversational.")

        if self.technical_depth > 0.7:
            parts.append("Assume expert-level technical knowledge.")
        elif self.technical_depth < 0.3:
            parts.append("Explain concepts simply, avoid jargon.")

        if self.emoji_usage < 0.1:
            parts.append("Do not use emojis.")

        return " ".join(parts) if parts else "Respond naturally."

    def to_dict(self) -> Dict[str, Any]:
        """Override to exclude the internal signal map."""
        result = super().to_dict()
        result.pop("_SIGNAL_MAP", None)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommunicationStyle":
        return cls(
            verbosity=data.get("verbosity", 0.5),
            formality=data.get("formality", 0.5),
            technical_depth=data.get("technical_depth", 0.5),
            emoji_usage=data.get("emoji_usage", 0.0),
            humor=data.get("humor", 0.3),
        )


@dataclass
class InteractionPattern(SerializableMixin):
    """A recorded interaction for pattern detection."""

    topic: str = ""
    satisfaction_signal: float = 0.5  # -1.0 to 1.0
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionPattern":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class EmotionalContext(SerializableMixin):
    """
    Inferred emotional state of the user.

    This is NOT sentiment analysis — it's a model of the user's
    likely emotional state based on interaction patterns.
    """

    current_state: str = "neutral"  # neutral, focused, frustrated, excited, tired
    confidence: float = 0.5
    last_trigger: Optional[str] = None
    updated_at: datetime = field(default_factory=datetime.now)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def update(
        self,
        state: str,
        confidence: float = 0.5,
        trigger: Optional[str] = None,
    ) -> None:
        """Update the emotional context."""
        self.history.append(
            {
                "state": self.current_state,
                "confidence": self.confidence,
                "timestamp": self.updated_at.isoformat(),
            }
        )
        # Keep last 50 entries
        if len(self.history) > 50:
            self.history = self.history[-50:]

        self.current_state = state
        self.confidence = confidence
        self.last_trigger = trigger
        self.updated_at = datetime.now()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmotionalContext":
        data = data.copy()
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


@dataclass
class HumanModel(SerializableMixin):
    """
    The user profile that Vecna builds over time.

    This is what makes Vecna feel like Jarvis — it learns who you are,
    what you care about, how you communicate, and what you need.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: Optional[str] = None

    # Learned preferences
    preferences: List[Preference] = field(default_factory=list)

    # Communication style model
    communication_style: CommunicationStyle = field(default_factory=CommunicationStyle)

    # Emotional context
    emotional_context: EmotionalContext = field(default_factory=EmotionalContext)

    # Interaction history (for pattern detection)
    interaction_patterns: List[InteractionPattern] = field(default_factory=list)
    interaction_count: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Limits
    max_patterns: int = 500
    max_preferences: int = 200

    def add_preference(self, pref: Preference) -> None:
        """Add or merge a preference."""
        # Look for existing preference with same key AND value
        for existing in self.preferences:
            if existing.key == pref.key and existing.value == pref.value:
                # Merge: boost confidence and count
                existing.observed_count += pref.observed_count
                existing.confidence = min(
                    1.0,
                    existing.confidence + 0.05 * pref.observed_count,
                )
                existing.last_observed = datetime.now()
                self.updated_at = datetime.now()
                return

        # New preference (different value for same key is allowed — context-dependent)
        self.preferences.append(pref)
        if len(self.preferences) > self.max_preferences:
            # Remove lowest confidence preferences
            self.preferences.sort(key=lambda p: p.confidence, reverse=True)
            self.preferences = self.preferences[: self.max_preferences]
        self.updated_at = datetime.now()

    def get_preference(self, key: str) -> Optional[Preference]:
        """Get the highest-confidence preference for a key."""
        matches = [p for p in self.preferences if p.key == key]
        if not matches:
            return None
        return max(matches, key=lambda p: p.confidence)

    def record_interaction(
        self,
        topic: str,
        satisfaction_signal: float = 0.5,
        duration_seconds: float = 0.0,
    ) -> None:
        """Record an interaction for pattern learning."""
        pattern = InteractionPattern(
            topic=topic,
            satisfaction_signal=satisfaction_signal,
            duration_seconds=duration_seconds,
        )
        self.interaction_patterns.append(pattern)
        self.interaction_count += 1

        if len(self.interaction_patterns) > self.max_patterns:
            self.interaction_patterns = self.interaction_patterns[-self.max_patterns :]

        self.updated_at = datetime.now()

    def get_recurring_topics(self, min_count: int = 3) -> List[str]:
        """Get topics that appear frequently in interactions."""
        topic_counts = Counter(p.topic for p in self.interaction_patterns)
        return [topic for topic, count in topic_counts.items() if count >= min_count]

    def to_prompt_context(self) -> str:
        """Generate prompt context from the human model."""
        lines: List[str] = []

        if self.name:
            lines.append(f"## USER: {self.name}")
        else:
            lines.append("## USER PROFILE")

        # Communication style directive
        style_directive = self.communication_style.to_prompt_directive()
        if style_directive != "Respond naturally.":
            lines.append("\n### COMMUNICATION STYLE")
            lines.append(style_directive)

        # Top preferences
        high_conf_prefs = sorted(
            [p for p in self.preferences if p.confidence >= 0.6],
            key=lambda p: p.confidence,
            reverse=True,
        )
        if high_conf_prefs:
            lines.append("\n### KNOWN PREFERENCES")
            for p in high_conf_prefs[:10]:
                lines.append(f"- {p.key}: {p.value} (confidence: {p.confidence:.1f})")

        # Emotional context (if not neutral)
        if self.emotional_context.current_state != "neutral":
            lines.append("\n### EMOTIONAL CONTEXT")
            lines.append(
                f"User appears {self.emotional_context.current_state} "
                f"(confidence: {self.emotional_context.confidence:.1f})"
            )
            if self.emotional_context.last_trigger:
                lines.append(f"Trigger: {self.emotional_context.last_trigger}")

        # Recurring interests
        topics = self.get_recurring_topics()
        if topics:
            lines.append("\n### RECURRING INTERESTS")
            for topic in topics[:5]:
                lines.append(f"- {topic}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize HumanModel to dict."""
        result = super().to_dict()
        result["preferences"] = [p.to_dict() for p in self.preferences]
        result["communication_style"] = self.communication_style.to_dict()
        result["emotional_context"] = self.emotional_context.to_dict()
        result["interaction_patterns"] = [p.to_dict() for p in self.interaction_patterns[-100:]]
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumanModel":
        """Deserialize HumanModel from dict."""
        data = data.copy()
        for dt_key in ("created_at", "updated_at"):
            if dt_key in data and isinstance(data[dt_key], str):
                data[dt_key] = datetime.fromisoformat(data[dt_key])

        model = cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name"),
            interaction_count=data.get("interaction_count", 0),
            created_at=data.get("created_at", datetime.now()),
            updated_at=data.get("updated_at", datetime.now()),
        )

        model.preferences = [Preference.from_dict(p) for p in data.get("preferences", [])]
        if "communication_style" in data:
            model.communication_style = CommunicationStyle.from_dict(data["communication_style"])
        if "emotional_context" in data:
            model.emotional_context = EmotionalContext.from_dict(data["emotional_context"])
        model.interaction_patterns = [
            InteractionPattern.from_dict(p) for p in data.get("interaction_patterns", [])
        ]

        return model
