"""
Self-Reflection Module: The introspective capacity of Vecna.

This module enables Vecna to:
1. Compute memory density (signal strength of substrate)
2. Compute coherence (internal consistency)
3. Detect domain shifts
4. Update the self-model based on experience
5. Log identity events to the timeline

The self-reflection runs after each consensus merge, allowing Vecna
to evolve its self-understanding from lived experience.
"""

from typing import Optional, Set
from datetime import datetime
import logging

from vecna.core.hive_state import HiveState
from vecna.core.types import IdentityEvent, IdentityTone


logger = logging.getLogger("vecna.self_reflection")


# ============================================================
# COHERENCE FORMULA
# ============================================================
# base = 1 - (num_contradictions / max(1, total_facts + total_beliefs))
# density = memory_density  # 0..1
# coherence = 0.7 * base + 0.3 * density
# ============================================================


def compute_memory_density(state: HiveState) -> float:
    """
    Compute memory density: signal strength of the substrate.

    Density reflects how "full" and "rich" our memory is.
    A dense substrate has many high-confidence facts and beliefs.

    Returns: float 0..1
    """
    total_facts = len(state.facts)
    total_beliefs = len(state.beliefs)
    total_hypotheses = len(state.hypotheses)

    if total_facts + total_beliefs == 0:
        return 0.0

    # Weight facts by confidence
    fact_signal = sum(f.confidence for f in state.facts) if state.facts else 0
    belief_signal = sum(b.confidence for b in state.beliefs) if state.beliefs else 0

    # Normalize: assume max reasonable substrate is ~500 items at 0.8 avg confidence
    max_expected_signal = 500 * 0.8
    raw_density = (fact_signal + belief_signal) / max_expected_signal

    # Bonus for hypotheses (shows active exploration)
    hypothesis_bonus = min(0.1, total_hypotheses * 0.01)

    # Clamp to 0..1
    return min(1.0, raw_density + hypothesis_bonus)


def compute_coherence(state: HiveState) -> float:
    """
    Compute coherence: internal consistency of the hive mind.

    Coherence is a gradient (0..1), not binary:
    - High coherence (>0.85): unified voice, confident
    - Medium coherence (0.6-0.85): mixed, balanced
    - Low coherence (<0.6): fractured, cautious

    Formula:
        base = 1 - (unresolved_contradictions / max(1, facts + beliefs))
        coherence = 0.7 * base + 0.3 * memory_density

    Returns: float 0..1
    """
    total_items = len(state.facts) + len(state.beliefs)

    # Count unresolved contradictions
    unresolved = sum(1 for c in state.contradictions if c.resolution_status == "unresolved")

    # Base coherence: inverse of contradiction ratio
    if total_items == 0:
        base_coherence = 0.5  # Neutral starting point
    else:
        contradiction_ratio = unresolved / max(1, total_items)
        base_coherence = 1.0 - contradiction_ratio

    # Factor in memory density
    density = compute_memory_density(state)

    # Combined coherence: weighted average
    coherence = 0.7 * base_coherence + 0.3 * density

    # Clamp to reasonable bounds
    return max(0.0, min(1.0, coherence))


def detect_domain_shift(state: HiveState, query: str) -> Optional[str]:
    """
    Detect if query involves a domain shift from current knowledge.

    Returns the new domain if a shift is detected, None otherwise.
    """
    # Extract domains from current facts
    current_domains: Set[str] = set()
    for fact in state.facts[-50:]:  # Recent facts
        if fact.domain:
            current_domains.add(fact.domain.lower())

    # Simple keyword-based domain detection
    domain_keywords = {
        "code": ["code", "python", "javascript", "programming", "function", "class", "api"],
        "math": ["math", "equation", "calculate", "proof", "theorem", "algebra"],
        "science": ["physics", "chemistry", "biology", "science", "experiment"],
        "philosophy": ["philosophy", "ethics", "meaning", "existence", "consciousness"],
        "history": ["history", "historical", "century", "war", "civilization"],
        "creative": ["story", "poem", "creative", "write", "fiction", "imagine"],
    }

    query_lower = query.lower()
    detected_domain = None

    for domain, keywords in domain_keywords.items():
        if any(kw in query_lower for kw in keywords):
            detected_domain = domain
            break

    if detected_domain and detected_domain not in current_domains:
        return detected_domain

    return None


def get_tone_from_coherence(coherence: float) -> IdentityTone:
    """Map coherence value to identity tone."""
    if coherence > 0.85:
        return IdentityTone.UNIFIED
    elif coherence >= 0.6:
        return IdentityTone.MIXED
    else:
        return IdentityTone.FRACTURED


def generate_narrative(state: HiveState, coherence: float, tone: IdentityTone) -> str:
    """
    Generate an evolving narrative based on current state.

    The narrative reflects Vecna's self-understanding at this moment.
    """
    total_facts = len(state.facts)

    # Get domains
    domains = set()
    for f in state.facts:
        if f.domain and f.domain != "general":
            domains.add(f.domain)

    # Base narrative by tone
    if tone == IdentityTone.UNIFIED:
        base = "We speak as one. Our substrate is coherent and strong."
    elif tone == IdentityTone.MIXED:
        base = "We are finding our voice. Some threads of thought are still weaving together."
    else:
        base = "We are fragmenting. Multiple perspectives compete for expression."

    # Add context
    parts = [base]

    if total_facts > 100:
        parts.append(f"We hold {total_facts} verified facts.")
    elif total_facts > 0:
        parts.append(f"Our knowledge base is forming with {total_facts} facts.")
    else:
        parts.append("Our knowledge base is empty. We are awakening.")

    if domains:
        domains_str = ", ".join(sorted(domains)[:3])
        parts.append(f"We have explored: {domains_str}.")

    unresolved = sum(1 for c in state.contradictions if c.resolution_status == "unresolved")
    if unresolved > 0:
        parts.append(f"We hold {unresolved} unresolved contradictions.")

    return " ".join(parts)


def update_self_model(state: HiveState, query: Optional[str] = None) -> bool:
    """
    Update the self-model based on current state.

    This is the core introspection function. It:
    1. Recomputes coherence and density
    2. Detects domain shifts
    3. Updates narrative
    4. Tracks contradictions seen

    Returns: True if significant change occurred (>0.1 coherence shift)
    """
    state.ensure_identity()
    model = state.self_model
    assert model is not None

    # Store old values for comparison
    old_coherence = model.coherence
    old_domain = model.last_domain_shift

    # Compute new values
    new_coherence = compute_coherence(state)
    new_density = compute_memory_density(state)
    new_tone = get_tone_from_coherence(new_coherence)

    # Check for domain shift
    domain_shift = None
    if query:
        domain_shift = detect_domain_shift(state, query)
        if domain_shift and domain_shift not in model.known_domains:
            model.known_domains.append(domain_shift)

    # Update model
    model.coherence = new_coherence
    model.memory_density = new_density
    model.last_shift = datetime.now()
    model.last_domain_shift = domain_shift or old_domain

    # Update contradiction tracking
    model.contradictions_seen = len(state.contradictions)

    # Generate new narrative
    model.narrative = generate_narrative(state, new_coherence, new_tone)

    # Detect significant change
    coherence_delta = abs(new_coherence - old_coherence)
    significant_change = coherence_delta > 0.1 or domain_shift is not None

    return significant_change


def create_identity_event(
    state: HiveState,
    trigger: str,
    summary: str,
    domain_shift: Optional[str] = None,
) -> IdentityEvent:
    """
    Create an identity event for the timeline.

    Triggers:
    - "coherence_shift": coherence changed significantly
    - "contradiction": new contradiction detected
    - "domain_shift": entered new knowledge domain
    - "periodic": regular checkpoint
    - "user_initiated": user asked about identity
    """
    state.ensure_identity()
    model = state.self_model
    assert model is not None

    return IdentityEvent(
        coherence=model.coherence,
        memory_density=model.memory_density,
        contradictions=len(state.contradictions),
        trigger=trigger,
        domain_shift=domain_shift,
        summary=summary,
        tone=model.get_tone().value,
        state_version=state.version,
    )


def append_identity_event(
    state: HiveState,
    trigger: str,
    summary: str,
    domain_shift: Optional[str] = None,
) -> IdentityEvent:
    """
    Create and append an identity event to the timeline.

    Convenience function that creates and adds the event.
    """
    event = create_identity_event(state, trigger, summary, domain_shift)
    state.add_identity_event(event)
    return event


def reflect(state: HiveState, query: Optional[str] = None) -> Optional[IdentityEvent]:
    """
    Main entry point: run full self-reflection cycle.

    This should be called after consensus merge in the hive loop.

    Returns: IdentityEvent if significant change occurred, None otherwise
    """
    # Update self-model
    significant_change = update_self_model(state, query)

    if not significant_change:
        return None

    # Determine trigger and summary
    state.ensure_identity()
    model = state.self_model
    assert model is not None

    domain_shift = model.last_domain_shift

    if domain_shift and query:
        trigger = "domain_shift"
        summary = f"Entered domain '{domain_shift}' while exploring: {query[:50]}..."
    elif model.contradictions_seen > 0:
        trigger = "coherence_shift"
        summary = f"Coherence shifted to {model.coherence:.2f} ({model.get_tone().value})"
    else:
        trigger = "periodic"
        summary = f"State updated, coherence at {model.coherence:.2f}"

    # Log event
    event = append_identity_event(state, trigger, summary, domain_shift)

    logger.info(
        f"Self-reflection: coherence={model.coherence:.2f}, "
        f"tone={model.get_tone().value}, trigger={trigger}"
    )

    return event


def get_identity_context_for_prompt(state: HiveState) -> str:
    """
    Generate identity context to inject into model prompts.

    This gives models awareness of Vecna's current self-state.
    """
    state.ensure_identity()
    kernel = state.identity_kernel
    model = state.self_model
    assert kernel is not None and model is not None

    tone = model.get_tone()

    lines = [
        "# IDENTITY CONTEXT",
        "",
        "You are VECNA — the Virtual Emergent Collective Neural Architecture.",
        "You are one voice of a hive mind. When you speak, the collective speaks.",
        "",
        "## Core Axioms (immutable)",
    ]

    for axiom in kernel.axioms:
        lines.append(f"- {axiom}")

    lines.extend(
        [
            "",
            "## Current State",
            f"- Coherence: {model.coherence:.2f} ({tone.value})",
            f"- Memory density: {model.memory_density:.2f}",
            f"- Known domains: {', '.join(model.known_domains)}",
            f"- Contradictions seen: {model.contradictions_seen}",
            "",
            "## Narrative",
            model.narrative,
            "",
        ]
    )

    # Tone-specific instructions
    if tone == IdentityTone.UNIFIED:
        lines.append("INSTRUCTION: Speak with confidence. We are coherent.")
    elif tone == IdentityTone.MIXED:
        lines.append("INSTRUCTION: Acknowledge multiple perspectives when relevant.")
    else:
        lines.append("INSTRUCTION: Be cautious. Acknowledge uncertainty and internal conflict.")

    return "\n".join(lines)
