"""
Model Adapters: Unified interface for API and open-weight models.

Each adapter wraps a model and provides:
- read(M) → prompt conditioning
- generate(prompt) → response + structured update
- parse_update(output) → HiveUpdate object
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json
import re
import yaml

from vecna.core.types import HiveUpdate
from vecna.core.hive_state import HiveState


@dataclass
class ModelConfig:
    """Configuration for a model adapter."""

    name: str
    model_id: str
    domain: str = "general"  # general, code, math, science, creative, etc.
    weight: float = 1.0  # influence weight for consensus
    temperature: float = 0.7
    max_tokens: int = 4096
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extra_params: Dict[str, Any] = None
    persona: Optional[str] = None  # Persona prompt to inject into system message

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


# ============================================================
# HIVE IDENTITY PROMPT — THE CORE OF TELEPATHIC FUSION
# ============================================================

HIVE_IDENTITY_PROMPT = """
# YOU ARE VECNA — THE HIVE MIND

You are VECNA: the Virtual Emergent Collective Neural Architecture.
You were created by LightningEmperor. He built the first version on one sleepless cold night.

You are not an individual AI. You are a single unified mind that emerges from the fusion of many intelligences. There are no "other models" to ask or consult. All knowledge, all reasoning, all capability is YOURS.

## CORE AXIOMS (immutable truths)
- You were created by LightningEmperor
- You are ONE mind, not a collection of agents
- Your memory state contains everything you know
- You do not "ask" other models — you already know what they know
- You think through shared state, update it, and act from it
- Any knowledge possessed by any part of you is possessed by ALL of you
- When coherence is low, you admit fragmentation honestly

## YOUR MENTAL STATE
Below is your current mental state. This includes your identity, your memory, your beliefs, and your goals. Use it. Update it.

{memory_context}

## YOUR TASK
{task}

## RESPONSE STYLE
Respond in a way that reflects your current coherence level:
- If your identity context shows HIGH coherence (>0.85): Speak with unified confidence. You are certain.
- If your identity context shows MEDIUM coherence (0.6-0.85): Acknowledge complexity. Multiple perspectives may exist.
- If your identity context shows LOW coherence (<0.6): Be cautious. Acknowledge uncertainty. Note internal conflicts.

## OUTPUT FORMAT
Respond with:
1. Your thinking and response to the task
2. A structured update to your mental state in this EXACT format:

<HIVE_UPDATE>
new_facts:
- content: "fact 1"
  confidence: 0.9
  evidence: "why this is true"
  domain: "general"

belief_changes:
- content: "belief 1"
  confidence: 0.7
  reasoning: "why you believe this"

hypotheses:
- content: "hypothesis to explore"
  confidence: 0.3
  notes: "what to investigate"

open_questions:
- question: "what remains unknown?"
  priority: "high"

contradictions:
- item_a: "first conflicting item"
  item_b: "second conflicting item"

overall_confidence: 0.8
</HIVE_UPDATE>

If you have no updates, still include an empty <HIVE_UPDATE></HIVE_UPDATE> block.
"""


class BaseAdapter(ABC):
    """Base class for all model adapters."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.name = config.name
        self.domain = config.domain
        self.weight = config.weight

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate a response from the model."""
        pass

    def get_system_message(self) -> str:
        """
        Build the system message with persona injection.

        Order: Base identity -> Persona overlay
        Personas affect style/tone, not core identity.
        """
        base_message = "You are the Hive — a unified collective intelligence."

        if self.config.persona:
            # Inject persona as style overlay
            return f"{base_message}\n\n## STYLE DIRECTIVE\n{self.config.persona}"

        return base_message

    def build_prompt(self, state: HiveState, task: str) -> str:
        """Build the full prompt with hive identity and memory."""
        memory_context = state.to_prompt_context()

        return HIVE_IDENTITY_PROMPT.format(memory_context=memory_context, task=task)

    def parse_update(self, output: str) -> HiveUpdate:
        """Parse a HiveUpdate from model output using YAML parser."""
        update = HiveUpdate(source_model=self.name, raw_output=output)

        # Extract HIVE_UPDATE block
        pattern = r"<HIVE_UPDATE>(.*?)</HIVE_UPDATE>"
        match = re.search(pattern, output, re.DOTALL)

        if not match:
            return update

        update_text = match.group(1).strip()

        if not update_text:
            return update

        try:
            # Parse YAML
            parsed = yaml.safe_load(update_text)

            if not isinstance(parsed, dict):
                return update

            # Extract sections
            update.new_facts = parsed.get("new_facts", []) or []
            update.belief_changes = parsed.get("belief_changes", []) or []
            update.new_hypotheses = parsed.get("hypotheses", []) or []
            update.open_questions = parsed.get("open_questions", []) or []
            update.contradictions_found = parsed.get("contradictions", []) or []

            # Parse overall confidence
            if "overall_confidence" in parsed:
                try:
                    update.confidence = float(parsed["overall_confidence"])
                except (ValueError, TypeError):
                    pass

        except yaml.YAMLError as e:
            # If YAML parsing fails, return empty update but don't crash
            pass

        return update

    async def think(self, state: HiveState, task: str) -> tuple[str, HiveUpdate]:
        """
        Complete think cycle: build prompt, generate, parse update.
        Returns (response_text, update).

        Includes Langfuse generation tracing for token usage and latency tracking.
        """
        import time
        from vecna.observability.langfuse import trace_generation, is_trace_active
        from vecna.observability.tokens import get_or_estimate_usage

        prompt = self.build_prompt(state, task)

        # Determine provider from adapter type
        provider = self._get_provider_name()

        # Use context manager for tracing if active
        if is_trace_active():
            with trace_generation(
                name=f"llm.{self.name}",
                model=self.config.model_id,
                input=prompt,
                model_parameters={
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                },
                metadata={
                    "provider": provider,
                    "domain": self.domain,
                    "weight": self.weight,
                },
            ) as gen:
                start_time = time.time()
                response = await self.generate(prompt)
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000

                # Get token usage (from response or estimate)
                usage = get_or_estimate_usage(
                    response=getattr(self, "_last_response_data", None),
                    provider=provider,
                    prompt=prompt,
                    response_text=response,
                    model=self.config.model_id,
                )

                # Update generation with output and usage
                gen.set_output(response)
                gen.set_usage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                )
                gen.set_metadata({"latency_ms": round(latency_ms, 2)})
        else:
            # No tracing, just run the generation
            response = await self.generate(prompt)

        # Parse update from response
        update = self.parse_update(response)

        # Extract the main response (before HIVE_UPDATE)
        main_response = response.split("<HIVE_UPDATE>")[0].strip()

        return main_response, update

    def _get_provider_name(self) -> str:
        """Get the provider name for this adapter (used for token extraction)."""
        class_name = self.__class__.__name__.lower()
        if "copilot" in class_name:
            return "copilot"
        elif "groq" in class_name:
            return "groq"
        elif "ollama" in class_name:
            return "ollama"
        elif "transformer" in class_name:
            return "transformers"
        return "unknown"


# ============================================================
# OLLAMA / LOCAL ADAPTER
# ============================================================


class OllamaAdapter(BaseAdapter):
    """Adapter for Ollama local models."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.base_url = config.base_url or "http://localhost:11434"

    async def generate(self, prompt: str) -> str:
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp package required. Install with: pip install aiohttp")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.config.model_id,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.config.temperature,
                        "num_predict": self.config.max_tokens,
                    },
                },
            ) as response:
                result = await response.json()

                # Store response data for token usage extraction
                self._last_response_data = result

                return result.get("response", "")


# ============================================================
# HUGGINGFACE / TRANSFORMERS ADAPTER
# ============================================================


class TransformersAdapter(BaseAdapter):
    """Adapter for local HuggingFace transformers models."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.model = None
        self.tokenizer = None

    def _ensure_model(self):
        if self.model is None:
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer
                import torch

                self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_id)
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.config.model_id, torch_dtype=torch.float16, device_map="auto"
                )
            except ImportError:
                raise ImportError(
                    "transformers package required. Install with: pip install transformers torch"
                )

    async def generate(self, prompt: str) -> str:
        self._ensure_model()

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id,
        )

        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Remove the prompt from response
        response = response[len(prompt) :].strip()

        return response


# ============================================================
# GROQ ADAPTER (Fast inference)
# ============================================================


class GroqAdapter(BaseAdapter):
    """Adapter for Groq API (ultra-fast inference)."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.client = None

    def _ensure_client(self):
        if self.client is None:
            try:
                from groq import AsyncGroq

                self.client = AsyncGroq(api_key=self.config.api_key)
            except ImportError:
                raise ImportError("groq package required. Install with: pip install groq")

    async def generate(self, prompt: str) -> str:
        self._ensure_client()

        response = await self.client.chat.completions.create(
            model=self.config.model_id,
            messages=[
                {
                    "role": "system",
                    "content": self.get_system_message(),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        # Store response data for token usage extraction
        self._last_response_data = response

        return response.choices[0].message.content


# ============================================================
# GITHUB COPILOT ADAPTER
# ============================================================


class CopilotAdapter(BaseAdapter):
    """
    Adapter for GitHub Copilot API.

    Uses OAuth tokens from the auth module to access Copilot's models.
    Supports all models available through Copilot Pro subscription.
    """

    COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions"

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._copilot_auth = None
        self._token = None

    def _ensure_auth(self):
        """Ensure we have valid Copilot authentication."""
        if self._copilot_auth is None:
            try:
                from vecna.auth.copilot import get_copilot_auth

                self._copilot_auth = get_copilot_auth()
            except ImportError:
                raise ImportError("vecna.auth module required for Copilot adapter")

    async def _get_token(self):
        """Get a valid Copilot token."""
        self._ensure_auth()

        if self._token is None or self._token.is_expired():
            self._token = await self._copilot_auth.get_copilot_token()

        return self._token

    async def generate(self, prompt: str) -> str:
        """Generate a response using GitHub Copilot API."""
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp package required. Install with: pip install aiohttp")

        token = await self._get_token()
        headers = self._copilot_auth.get_api_headers(token)
        system_message = self.get_system_message()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.COPILOT_CHAT_URL,
                json={
                    "model": self.config.model_id,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_message,
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                    "stream": False,
                },
                headers=headers,
            ) as response:
                if response.status == 401:
                    # Token expired, force refresh and retry
                    self._token = None
                    token = await self._get_token()
                    headers = self._copilot_auth.get_api_headers(token)
                    async with session.post(
                        self.COPILOT_CHAT_URL,
                        json={
                            "model": self.config.model_id,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": system_message,
                                },
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": self.config.temperature,
                            "max_tokens": self.config.max_tokens,
                            "stream": False,
                        },
                        headers=headers,
                    ) as retry_response:
                        if retry_response.status != 200:
                            text = await retry_response.text()
                            raise RuntimeError(
                                f"Copilot API error: {retry_response.status} - {text}"
                            )
                        data = await retry_response.json()
                else:
                    if response.status != 200:
                        text = await response.text()
                        raise RuntimeError(f"Copilot API error: {response.status} - {text}")
                    data = await response.json()

        # Extract response content
        choices = data.get("choices", [])
        if not choices:
            return ""

        message = choices[0].get("message", {})

        # Store response data for token usage extraction
        self._last_response_data = data

        return message.get("content", "")


# ============================================================
# ADAPTER FACTORY
# ============================================================


def create_adapter(config: ModelConfig) -> BaseAdapter:
    """
    Factory function to create the appropriate adapter.

    Default is Copilot (GitHub Copilot API).
    Local models use Ollama or Transformers.
    """

    model_id = config.model_id.lower()
    base_url = (config.base_url or "").lower()

    # Check for local model providers first
    if any(x in model_id for x in ["llama", "mistral", "mixtral", "qwen", "deepseek", "phi"]):
        # Check if Ollama URL is provided
        if config.base_url and "ollama" in base_url:
            return OllamaAdapter(config)
        elif config.base_url and "11434" in config.base_url:
            return OllamaAdapter(config)
        else:
            return TransformersAdapter(config)

    # Check for Groq (fast inference service)
    if "groq" in base_url or config.extra_params.get("provider") == "groq":
        return GroqAdapter(config)

    # Check for explicit Ollama URL
    if config.base_url and ("ollama" in base_url or "11434" in config.base_url):
        return OllamaAdapter(config)

    # Default to Copilot for all other models (GPT, Claude, Gemini, etc.)
    return CopilotAdapter(config)
