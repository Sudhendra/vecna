"""
Mixture of Agents (MoA) consensus.

Based on "Mixture-of-Agents Enhances Large Language Model Capabilities"
(arXiv:2406.04692). Achieves 65.1% on AlpacaEval 2.0.

Architecture:
- Layer 1: All models generate independently (proposers)
- Layer 2: An aggregator model synthesizes the best response
  considering all proposer outputs.

The aggregator is the Primary Cortex (highest-weight model).
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("vecna.orchestrator.moa")


@dataclass
class MoAConfig:
    """Configuration for Mixture of Agents consensus."""

    # The aggregator prompt template
    aggregator_prompt: str = (
        "You have been provided with responses from multiple AI models "
        "to the same query. Your task is to synthesize the best possible "
        "response by combining the strongest elements from each.\n\n"
        "Model responses:\n{responses}\n\n"
        "Synthesize a single superior response that:\n"
        "1. Combines the most accurate and insightful points\n"
        "2. Resolves any contradictions between responses\n"
        "3. Uses the clearest and most precise language\n"
        "4. Adds nothing that wasn't supported by at least one model"
    )

    # Whether to include model names in the aggregator context
    include_model_names: bool = True

    # Max tokens from each proposer to include
    max_proposer_tokens: int = 2000


class MoAConsensus:
    """
    Mixture of Agents consensus engine.

    This is the upgrade path from Jaccard-based consensus to
    proper multi-model synthesis.
    """

    def __init__(self, config: Optional[MoAConfig] = None):
        self.config = config or MoAConfig()

    def build_aggregator_prompt(
        self,
        responses: Dict[str, str],
        original_task: Optional[str] = None,
    ) -> str:
        """Build the prompt for the aggregator model.

        Args:
            responses: Mapping of model_name → response_text.
            original_task: The original user query (included if provided).

        Returns:
            A formatted prompt string for the aggregator to synthesize.
        """
        parts = []
        for model_name, response in responses.items():
            truncated = response[: self.config.max_proposer_tokens]
            if self.config.include_model_names:
                parts.append(f"### {model_name}\n{truncated}")
            else:
                parts.append(f"### Response\n{truncated}")

        responses_text = "\n\n".join(parts)

        prompt = self.config.aggregator_prompt.format(responses=responses_text)

        if original_task:
            prompt = f"Original query: {original_task}\n\n{prompt}"

        return prompt

    def merge_responses(self, responses: Dict[str, str]) -> str:
        """
        Merge multiple model responses into one.

        This is the synchronous/offline version that picks the
        longest response as a baseline. The full async version uses
        an aggregator LLM call (see merge_responses_async).

        Args:
            responses: Mapping of model_name → response_text.

        Returns:
            The merged response string. Returns empty string if no responses.
        """
        if not responses:
            return ""
        if len(responses) == 1:
            return next(iter(responses.values()))

        # Offline fallback: pick response with most unique information
        # (longest response as proxy, weighted by model)
        return max(responses.values(), key=len)

    async def merge_responses_async(
        self,
        responses: Dict[str, str],
        aggregator_adapter: object,  # BaseAdapter — typed loosely to avoid circular import
        original_task: str = "",
    ) -> str:
        """
        Use an aggregator model to synthesize the best response.

        This is the full MoA pipeline: proposers generate independently,
        then the Primary Cortex synthesizes.

        Args:
            responses: Mapping of model_name → response_text.
            aggregator_adapter: An adapter with an async ``generate(prompt)`` method.
            original_task: The original user query for context.

        Returns:
            The synthesized response string.
        """
        if not responses:
            return ""
        if len(responses) == 1:
            return next(iter(responses.values()))

        prompt = self.build_aggregator_prompt(responses, original_task)
        synthesized = await aggregator_adapter.generate(prompt)  # type: ignore[union-attr]
        return synthesized
