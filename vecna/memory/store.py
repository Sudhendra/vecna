"""
Memory Store: Vector-based semantic memory for the hive.

This provides:
- Embedding storage and retrieval
- Semantic search across hive memory
- Memory compression and summarization
"""

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import json
import numpy as np
from datetime import datetime

from vecna.core.types import Fact, Belief, Hypothesis
from vecna.core.hive_state import HiveState


@dataclass
class MemoryItem:
    """A single item in semantic memory."""

    id: str
    content: str
    item_type: str  # fact, belief, hypothesis, etc.
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class MemoryStore:
    """
    Vector-based memory store for the hive.

    Uses embeddings for semantic retrieval, enabling the hive to
    "remember" relevant context without explicit queries.
    """

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-small",
        embedding_dim: int = 1536,
        use_local: bool = False,
    ):
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self.use_local = use_local

        # In-memory storage
        self.items: List[MemoryItem] = []
        self.embeddings: Optional[np.ndarray] = None

        # Embedding client (lazy init)
        self._embed_client = None
        self._local_model = None

    def _get_embedder(self):
        """
        Lazy initialization of embedding model.

        Embedding routing:
        1. If use_local=True: Use sentence-transformers (MiniLM)
        2. If OPENAI_API_KEY is set: Use OpenAI embeddings
        3. Fallback: Use sentence-transformers locally
        """
        import os

        if self.use_local:
            return self._get_local_embedder()

        # Try OpenAI if API key is available
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            if self._embed_client is None:
                try:
                    from openai import OpenAI

                    self._embed_client = OpenAI(api_key=openai_key)
                except ImportError:
                    # Fall back to local if openai package not installed
                    return self._get_local_embedder()
            return self._embed_client

        # No OpenAI key, fall back to local embeddings
        return self._get_local_embedder()

    def _get_local_embedder(self):
        """Get local sentence-transformers embedder."""
        if self._local_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._local_model = SentenceTransformer("all-MiniLM-L6-v2")
                self.embedding_dim = 384  # MiniLM dimension
            except ImportError:
                raise ImportError(
                    "sentence-transformers required for local embeddings. "
                    "Install with: pip install sentence-transformers"
                )
        return self._local_model

    def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for texts."""
        if not texts:
            return np.array([])

        # Filter out empty strings
        texts = [t for t in texts if t and t.strip()]
        if not texts:
            return np.array([])

        embedder = self._get_embedder()

        # Check if it's a local model (SentenceTransformer) or OpenAI client
        if hasattr(embedder, "encode"):
            # Local sentence-transformers
            embeddings = embedder.encode(texts, convert_to_numpy=True)
            return embeddings
        else:
            # OpenAI API
            response = embedder.embeddings.create(model=self.embedding_model, input=texts)
            embeddings = [item.embedding for item in response.data]
            return np.array(embeddings)

    def add(self, item: MemoryItem) -> None:
        """Add an item to memory."""
        # Generate embedding if not present
        if item.embedding is None:
            embeddings = self.embed([item.content])
            if len(embeddings) > 0:
                item.embedding = embeddings[0].tolist()

        self.items.append(item)

        # Update embedding matrix
        if item.embedding is not None:
            new_emb = np.array([item.embedding])
            if self.embeddings is None:
                self.embeddings = new_emb
            else:
                self.embeddings = np.vstack([self.embeddings, new_emb])

    def add_from_state(self, state: HiveState) -> int:
        """Add all items from a HiveState to memory."""
        count = 0

        # Add facts
        for fact in state.facts:
            item = MemoryItem(
                id=fact.id,
                content=fact.content,
                item_type="fact",
                metadata={
                    "confidence": fact.confidence,
                    "domain": fact.domain,
                    "source": fact.source_model,
                },
            )
            self.add(item)
            count += 1

        # Add beliefs
        for belief in state.beliefs:
            item = MemoryItem(
                id=belief.id,
                content=belief.content,
                item_type="belief",
                metadata={
                    "confidence": belief.confidence,
                    "source": belief.source_model,
                },
            )
            self.add(item)
            count += 1

        # Add hypotheses
        for hyp in state.hypotheses:
            item = MemoryItem(
                id=hyp.id,
                content=hyp.content,
                item_type="hypothesis",
                metadata={"confidence": hyp.confidence, "status": hyp.status},
            )
            self.add(item)
            count += 1

        return count

    def search(
        self,
        query: str,
        top_k: int = 10,
        item_type: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[Tuple[MemoryItem, float]]:
        """
        Semantic search over memory.

        Returns list of (item, similarity_score) tuples.
        """
        if not self.items or self.embeddings is None:
            return []

        # Embed query
        try:
            query_emb = self.embed([query])[0]
        except Exception:
            # Fallback to keyword matching if embedding fails
            return self._keyword_search(query, top_k, item_type, min_confidence)

        # Compute cosine similarities
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
        normalized = self.embeddings / norms

        query_norm = np.linalg.norm(query_emb)
        if query_norm > 0:
            query_emb = query_emb / query_norm

        similarities = normalized @ query_emb

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1]

        results = []
        for idx in top_indices:
            item = self.items[idx]
            score = float(similarities[idx])

            # Apply filters
            if item_type and item.item_type != item_type:
                continue

            conf = item.metadata.get("confidence", 1.0)
            if conf < min_confidence:
                continue

            results.append((item, score))

            if len(results) >= top_k:
                break

        return results

    def _keyword_search(
        self,
        query: str,
        top_k: int = 10,
        item_type: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[Tuple[MemoryItem, float]]:
        """Fallback keyword-based search when embeddings unavailable."""
        query_words = set(query.lower().split())

        scored_items = []
        for item in self.items:
            # Apply filters
            if item_type and item.item_type != item_type:
                continue
            conf = item.metadata.get("confidence", 1.0)
            if conf < min_confidence:
                continue

            # Compute word overlap score
            item_words = set(item.content.lower().split())
            if not query_words or not item_words:
                continue

            overlap = len(query_words & item_words)
            union = len(query_words | item_words)
            score = overlap / union if union > 0 else 0

            if score > 0:
                scored_items.append((item, score))

        # Sort by score descending
        scored_items.sort(key=lambda x: x[1], reverse=True)
        return scored_items[:top_k]

    def get_relevant_context(self, query: str, max_items: int = 15, max_chars: int = 3000) -> str:
        """
        Get relevant memory items formatted as context string.
        This is what gets injected into model prompts.
        """
        results = self.search(query, top_k=max_items * 2)

        lines = []
        total_chars = 0

        for item, score in results:
            if len(lines) >= max_items:
                break

            conf = item.metadata.get("confidence", 0.5)
            line = f"- [{item.item_type}][{conf:.1f}] {item.content}"

            if total_chars + len(line) > max_chars:
                break

            lines.append(line)
            total_chars += len(line)

        if not lines:
            return "No relevant memories found."

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all memory."""
        self.items = []
        self.embeddings = None

    # ============================================================
    # RLM-STYLE RETRIEVAL: Decompose → Retrieve → Recompose
    # ============================================================

    def decompose_query(self, query: str) -> List[str]:
        """
        Decompose a complex query into atomic facets.

        RLM (Retrieval-augmented Language Model) pattern:
        Complex queries are broken into simpler sub-queries that can
        each retrieve more targeted evidence.

        Example:
            "What Python frameworks are good for web APIs and why?"
            →
            ["Python web frameworks", "API development Python",
             "web API best practices", "framework comparison"]
        """
        facets = []

        # The original query is always a facet
        facets.append(query)

        # Extract noun phrases and key terms
        # Simple heuristic: split on common question words and conjunctions
        query_lower = query.lower()

        # Remove question prefixes
        for prefix in [
            "what ",
            "how ",
            "why ",
            "when ",
            "where ",
            "which ",
            "can ",
            "does ",
            "is ",
            "are ",
        ]:
            if query_lower.startswith(prefix):
                query_lower = query_lower[len(prefix) :]
                break

        # Split on conjunctions
        for conj in [" and ", " or ", " but ", " vs ", " versus ", ", "]:
            if conj in query_lower:
                parts = query_lower.split(conj)
                facets.extend([p.strip() for p in parts if p.strip() and len(p.strip()) > 3])

        # Extract potential entity phrases (capitalized words)
        import re

        entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", query)
        facets.extend(entities)

        # Extract technical terms (words with special chars or camelCase)
        tech_terms = re.findall(r"\b[a-z]+[A-Z][a-zA-Z]*\b|\b\w+[-_]\w+\b", query)
        facets.extend(tech_terms)

        # Deduplicate while preserving order
        seen = set()
        unique_facets = []
        for f in facets:
            f_lower = f.lower().strip()
            if f_lower not in seen and len(f_lower) > 2:
                seen.add(f_lower)
                unique_facets.append(f.strip())

        return unique_facets[:8]  # Limit to 8 facets

    def retrieve_by_facets(
        self,
        facets: List[str],
        top_k_per_facet: int = 5,
        min_similarity: float = 0.3,
    ) -> Dict[str, List[Tuple[MemoryItem, float]]]:
        """
        Retrieve relevant items for each facet.

        Returns a dict mapping each facet to its retrieved items.
        This enables targeted retrieval that can be traced back to
        specific aspects of the query.
        """
        results = {}

        for facet in facets:
            facet_results = self.search(facet, top_k=top_k_per_facet)
            # Filter by minimum similarity
            facet_results = [
                (item, score) for item, score in facet_results if score >= min_similarity
            ]
            results[facet] = facet_results

        return results

    def recompose_evidence(
        self,
        facet_results: Dict[str, List[Tuple[MemoryItem, float]]],
        max_items: int = 20,
        max_chars: int = 4000,
    ) -> str:
        """
        Recompose retrieved evidence into a structured context string.

        Groups evidence by facet, deduplicates, and formats for
        injection into the model prompt.
        """
        # Collect all unique items with their best scores
        item_scores: Dict[str, Tuple[MemoryItem, float, str]] = {}  # id -> (item, score, facet)

        for facet, results in facet_results.items():
            for item, score in results:
                if item.id not in item_scores or score > item_scores[item.id][1]:
                    item_scores[item.id] = (item, score, facet)

        # Sort by score
        sorted_items = sorted(item_scores.values(), key=lambda x: x[1], reverse=True)

        if not sorted_items:
            return "No relevant evidence found."

        lines = ["## Retrieved Evidence"]
        total_chars = len(lines[0])
        items_added = 0

        # Group by facet for better organization
        facet_groups: Dict[str, List[Tuple[MemoryItem, float]]] = {}
        for item, score, facet in sorted_items:
            if facet not in facet_groups:
                facet_groups[facet] = []
            facet_groups[facet].append((item, score))

        for facet, items in facet_groups.items():
            if items_added >= max_items:
                break

            facet_header = f"\n### {facet}"
            if total_chars + len(facet_header) > max_chars:
                break

            lines.append(facet_header)
            total_chars += len(facet_header)

            for item, score in items[:5]:  # Max 5 per facet
                if items_added >= max_items:
                    break

                conf = item.metadata.get("confidence", 0.5)
                line = f"- [{item.item_type}][{conf:.1f}][sim:{score:.2f}] {item.content}"

                if total_chars + len(line) > max_chars:
                    break

                lines.append(line)
                total_chars += len(line)
                items_added += 1

        return "\n".join(lines)

    def rlm_retrieve(
        self,
        query: str,
        top_k_per_facet: int = 5,
        max_items: int = 20,
        max_chars: int = 4000,
    ) -> Tuple[str, List[str], Dict[str, int]]:
        """
        Full RLM retrieval pipeline: decompose → retrieve → recompose.

        Returns:
            - context: The recomposed evidence string
            - facets: The decomposed facets
            - stats: Retrieval statistics
        """
        # Decompose
        facets = self.decompose_query(query)

        # Retrieve
        facet_results = self.retrieve_by_facets(facets, top_k_per_facet=top_k_per_facet)

        # Gather stats
        stats = {
            "num_facets": len(facets),
            "total_items_retrieved": sum(len(items) for items in facet_results.values()),
            "facets_with_results": sum(1 for items in facet_results.values() if items),
        }

        # Recompose
        context = self.recompose_evidence(facet_results, max_items=max_items, max_chars=max_chars)

        return context, facets, stats

    def save(self, filepath: str) -> None:
        """
        DEPRECATED: Save memory to disk.

        Warning: File-based storage is deprecated. Use PgMemoryStore for persistent storage.
        This method is retained only for backup/migration purposes.
        Use export_to_file() instead for explicit file exports.
        """
        import warnings

        warnings.warn(
            "MemoryStore.save() is deprecated. Use PgMemoryStore for persistent storage. "
            "For file exports, use export_to_file() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.export_to_file(filepath)

    def load(self, filepath: str) -> None:
        """
        DEPRECATED: Load memory from disk.

        Warning: File-based storage is deprecated. Use PgMemoryStore for persistent storage.
        This method is retained only for backup/migration purposes.
        Use import_from_file() instead for explicit file imports.
        """
        import warnings

        warnings.warn(
            "MemoryStore.load() is deprecated. Use PgMemoryStore for persistent storage. "
            "For file imports, use import_from_file() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.import_from_file(filepath)

    def export_to_file(self, filepath: str) -> None:
        """
        Export memory to a JSON file for backup/migration purposes.

        Note: This is NOT the primary storage mechanism. Use PgMemoryStore for
        persistent storage. This method is for backups and data migration only.
        """
        data = {
            "items": [
                {
                    "id": item.id,
                    "content": item.content,
                    "item_type": item.item_type,
                    "embedding": item.embedding,
                    "metadata": item.metadata,
                    "timestamp": item.timestamp.isoformat(),
                }
                for item in self.items
            ],
            "export_timestamp": datetime.now().isoformat(),
            "export_note": "This is a backup export. Use PgMemoryStore for primary storage.",
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def import_from_file(self, filepath: str) -> int:
        """
        Import memory from a JSON file (backup/migration).

        Note: This is for importing backups or migrating data. Use PgMemoryStore
        for persistent storage.

        Returns:
            Number of items imported.
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        self.items = []
        embeddings_list = []

        for item_data in data.get("items", []):
            item = MemoryItem(
                id=item_data["id"],
                content=item_data["content"],
                item_type=item_data["item_type"],
                embedding=item_data.get("embedding"),
                metadata=item_data.get("metadata", {}),
                timestamp=datetime.fromisoformat(item_data["timestamp"]),
            )
            self.items.append(item)

            if item.embedding:
                embeddings_list.append(item.embedding)

        if embeddings_list:
            self.embeddings = np.array(embeddings_list)

        return len(self.items)


class MemoryCompressor:
    """
    Compresses and summarizes hive memory.

    Prevents memory explosion and creates the "memory_summary"
    that gives models a condensed view of the hive's knowledge.
    """

    def __init__(self, summarizer_adapter=None):
        """
        Initialize compressor.

        Args:
            summarizer_adapter: A model adapter to use for summarization.
                               If None, uses simple extractive summarization.
        """
        self.summarizer = summarizer_adapter

    async def compress(self, state: HiveState, max_summary_length: int = 1500) -> str:
        """
        Generate a compressed summary of the hive state.
        """
        if self.summarizer is not None:
            return await self._model_summarize(state, max_summary_length)
        else:
            return self._extractive_summarize(state, max_summary_length)

    def _extractive_summarize(self, state: HiveState, max_length: int) -> str:
        """Simple extractive summarization without a model."""
        lines = []

        # Most confident facts
        top_facts = sorted(state.facts, key=lambda f: f.confidence, reverse=True)[:10]
        if top_facts:
            lines.append("KEY FACTS:")
            for f in top_facts:
                lines.append(f"• {f.content}")

        # Most confident beliefs
        top_beliefs = sorted(state.beliefs, key=lambda b: b.confidence, reverse=True)[:5]
        if top_beliefs:
            lines.append("\nKEY BELIEFS:")
            for b in top_beliefs:
                lines.append(f"• {b.content}")

        # Active goals
        active_goals = [g for g in state.goals if g.status == "active"][:3]
        if active_goals:
            lines.append("\nACTIVE GOALS:")
            for g in active_goals:
                lines.append(f"• {g.content}")

        # Critical open questions
        open_qs = [q for q in state.open_questions if q.status == "open" and q.priority == "high"][
            :3
        ]
        if open_qs:
            lines.append("\nOPEN QUESTIONS:")
            for q in open_qs:
                lines.append(f"• {q.question}")

        summary = "\n".join(lines)

        # Truncate if too long
        if len(summary) > max_length:
            summary = summary[: max_length - 3] + "..."

        return summary

    async def _model_summarize(self, state: HiveState, max_length: int) -> str:
        """Use a model to generate an abstractive summary."""
        # Build prompt for summarization
        full_context = state.to_prompt_context(max_items=50)

        prompt = f"""Summarize the following hive mind state into a concise summary 
of no more than {max_length} characters. Focus on:
1. The most important facts and beliefs
2. Active goals and their progress
3. Critical open questions
4. Any unresolved contradictions

HIVE STATE:
{full_context}

SUMMARY:"""

        response = await self.summarizer.generate(prompt)

        # Truncate if needed
        if len(response) > max_length:
            response = response[: max_length - 3] + "..."

        return response

    def deduplicate_facts(self, state: HiveState, similarity_threshold: float = 0.85) -> int:
        """
        Remove near-duplicate facts from state.
        Returns count of removed items.
        """
        if len(state.facts) < 2:
            return 0

        # Simple word-overlap deduplication
        removed = 0
        unique_facts = []

        for fact in state.facts:
            is_duplicate = False
            fact_words = set(fact.content.lower().split())

            for existing in unique_facts:
                existing_words = set(existing.content.lower().split())

                if not fact_words or not existing_words:
                    continue

                overlap = len(fact_words & existing_words)
                union = len(fact_words | existing_words)
                similarity = overlap / union if union > 0 else 0

                if similarity >= similarity_threshold:
                    is_duplicate = True
                    # Keep higher confidence one
                    if fact.confidence > existing.confidence:
                        unique_facts.remove(existing)
                        unique_facts.append(fact)
                    break

            if not is_duplicate:
                unique_facts.append(fact)
            else:
                removed += 1

        state.facts = unique_facts
        return removed
