# Adapters API

> *"The bridges between the hive and its constituent minds."*

Model adapters provide a unified interface for communicating with different LLM providers.

---

## Import

```python
from vecna.adapters import (
    BaseAdapter,
    OpenAIAdapter,
    AnthropicAdapter,
    GroqAdapter,
    OllamaAdapter,
    TransformersAdapter,
)
```

---

## Base Adapter

### `BaseAdapter`

Abstract base class for all adapters.

```python
class BaseAdapter(ABC):
    """
    Base class for model adapters.
    
    All adapters must implement the generate() method.
    """
    
    def __init__(
        self,
        model: str,
        name: str | None = None,
        domain: str | list[str] = "general",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> None: ...
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        state: HiveState,
        **kwargs,
    ) -> AdapterResponse: ...
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `model` | `str` | Model identifier |
| `name` | `str` | Unique name in hive |
| `domain` | `str \| list[str]` | Specialization domain(s) |
| `temperature` | `float` | Response randomness |
| `max_tokens` | `int` | Maximum response length |
| `enabled` | `bool` | Whether adapter is active |

### AdapterResponse

```python
@dataclass
class AdapterResponse:
    content: str              # Response text
    model: str               # Model that generated it
    facts: list[Fact]        # Extracted facts
    beliefs: list[Belief]    # Extracted beliefs
    hypotheses: list[Hypothesis]  # Extracted hypotheses
    duration: float          # Generation time (seconds)
    tokens_used: int         # Token count
    raw_response: Any        # Provider's raw response
```

---

## OpenAI Adapter

### `OpenAIAdapter`

Adapter for OpenAI models (GPT-4, etc.).

```python
class OpenAIAdapter(BaseAdapter):
    """
    Adapter for OpenAI API models.
    
    Supports: GPT-4, GPT-4o, GPT-4 Turbo, o1, o3, GPT-3.5
    """
    
    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        domain: str | list[str] = "general",
        api_key: str | None = None,
        organization: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> None: ...
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | required | Model ID (e.g., "gpt-4o") |
| `name` | `str \| None` | `None` | Unique name (auto if None) |
| `domain` | `str \| list[str]` | `"general"` | Specialization |
| `api_key` | `str \| None` | `None` | API key (env if None) |
| `organization` | `str \| None` | `None` | Org ID |
| `base_url` | `str \| None` | `None` | Custom endpoint |
| `temperature` | `float` | `0.7` | Randomness |
| `max_tokens` | `int` | `4096` | Max response length |
| `top_p` | `float` | `1.0` | Nucleus sampling |
| `frequency_penalty` | `float` | `0.0` | Repetition penalty |
| `presence_penalty` | `float` | `0.0` | Topic penalty |

### Supported Models

| Model | Context | Best For |
|-------|---------|----------|
| `gpt-4o` | 128K | General purpose |
| `gpt-4-turbo` | 128K | Long context |
| `gpt-4` | 8K | High quality |
| `o1-preview` | 128K | Deep reasoning |
| `o1-mini` | 128K | Fast reasoning |
| `gpt-3.5-turbo` | 16K | Budget option |

### Example

```python
from vecna.adapters import OpenAIAdapter

adapter = OpenAIAdapter(
    model="gpt-4o",
    name="reasoning",
    domain="general",
    temperature=0.3,  # More focused
    max_tokens=8192
)

# Direct usage
response = await adapter.generate(
    prompt="Explain quantum computing",
    state=hive_state
)

print(response.content)
print(f"Duration: {response.duration:.2f}s")
print(f"Tokens: {response.tokens_used}")
```

---

## Anthropic Adapter

### `AnthropicAdapter`

Adapter for Anthropic models (Claude).

```python
class AnthropicAdapter(BaseAdapter):
    """
    Adapter for Anthropic API models.
    
    Supports: Claude 3.5, Claude 3 (Opus, Sonnet, Haiku)
    """
    
    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        domain: str | list[str] = "general",
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 1.0,
        top_k: int | None = None,
    ) -> None: ...
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | required | Model ID |
| `name` | `str \| None` | `None` | Unique name |
| `domain` | `str \| list[str]` | `"general"` | Specialization |
| `api_key` | `str \| None` | `None` | API key |
| `temperature` | `float` | `0.7` | Randomness |
| `max_tokens` | `int` | `4096` | Max response |
| `top_p` | `float` | `1.0` | Nucleus sampling |
| `top_k` | `int \| None` | `None` | Top-k sampling |

### Supported Models

| Model | Context | Best For |
|-------|---------|----------|
| `claude-sonnet-4-20250514` | 200K | Balanced |
| `claude-3-opus-20240229` | 200K | Most capable |
| `claude-3-sonnet-20240229` | 200K | General |
| `claude-3-haiku-20240307` | 200K | Fastest |

### Example

```python
from vecna.adapters import AnthropicAdapter

adapter = AnthropicAdapter(
    model="claude-sonnet-4-20250514",
    name="analyst",
    domain="science",
    max_tokens=8192
)

response = await adapter.generate(
    prompt="Analyze this research paper...",
    state=hive_state
)
```

---

## Groq Adapter

### `GroqAdapter`

Adapter for Groq's ultra-fast inference.

```python
class GroqAdapter(BaseAdapter):
    """
    Adapter for Groq API.
    
    Supports: Llama 3.1, Mixtral (extremely fast inference)
    """
    
    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        domain: str | list[str] = "general",
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 1.0,
    ) -> None: ...
```

### Supported Models

| Model | Context | Speed |
|-------|---------|-------|
| `llama-3.1-70b-versatile` | 128K | ~500 tok/s |
| `llama-3.1-8b-instant` | 128K | ~1000 tok/s |
| `mixtral-8x7b-32768` | 32K | ~500 tok/s |

### Example

```python
from vecna.adapters import GroqAdapter

# Ultra-fast code generation
adapter = GroqAdapter(
    model="llama-3.1-70b-versatile",
    name="coder",
    domain="code"
)

response = await adapter.generate(
    prompt="Write a Python quicksort implementation",
    state=hive_state
)
# Response in ~0.3 seconds
```

---

## Ollama Adapter

### `OllamaAdapter`

Adapter for local models via Ollama.

```python
class OllamaAdapter(BaseAdapter):
    """
    Adapter for Ollama local models.
    
    Supports: Any model available in Ollama
    """
    
    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        domain: str | list[str] = "general",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        num_ctx: int = 4096,
        num_predict: int = 4096,
    ) -> None: ...
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | required | Ollama model name |
| `base_url` | `str` | `localhost:11434` | Ollama server URL |
| `num_ctx` | `int` | `4096` | Context window size |
| `num_predict` | `int` | `4096` | Max tokens to generate |

### Example

```python
from vecna.adapters import OllamaAdapter

# Local Llama
adapter = OllamaAdapter(
    model="llama3.1",
    name="local",
    domain="general",
    num_ctx=8192
)

# Remote Ollama server
adapter = OllamaAdapter(
    model="mistral",
    base_url="http://192.168.1.100:11434"
)

response = await adapter.generate(
    prompt="Explain machine learning",
    state=hive_state
)
```

### Prerequisites

```bash
# Install Ollama
brew install ollama  # macOS
# or
curl -fsSL https://ollama.ai/install.sh | sh  # Linux

# Start server
ollama serve

# Pull models
ollama pull llama3.1
ollama pull mistral
ollama pull codellama
```

---

## Transformers Adapter

### `TransformersAdapter`

Adapter for HuggingFace Transformers models.

```python
class TransformersAdapter(BaseAdapter):
    """
    Adapter for HuggingFace Transformers models.
    
    Supports: Any causal language model
    """
    
    def __init__(
        self,
        model_name: str,
        *,
        name: str | None = None,
        domain: str | list[str] = "general",
        device: str = "auto",
        torch_dtype: str = "auto",
        load_in_8bit: bool = False,
        load_in_4bit: bool = False,
        temperature: float = 0.7,
        max_new_tokens: int = 4096,
        do_sample: bool = True,
        top_p: float = 0.9,
        top_k: int = 50,
    ) -> None: ...
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `str` | required | HF model ID or path |
| `device` | `str` | `"auto"` | Device: cuda, cpu, mps |
| `torch_dtype` | `str` | `"auto"` | Data type |
| `load_in_8bit` | `bool` | `False` | 8-bit quantization |
| `load_in_4bit` | `bool` | `False` | 4-bit quantization |
| `max_new_tokens` | `int` | `4096` | Max generation length |
| `do_sample` | `bool` | `True` | Use sampling |
| `top_p` | `float` | `0.9` | Nucleus sampling |
| `top_k` | `int` | `50` | Top-k sampling |

### Example

```python
from vecna.adapters import TransformersAdapter

# Load from HuggingFace Hub
adapter = TransformersAdapter(
    model_name="mistralai/Mistral-7B-Instruct-v0.2",
    name="mistral",
    device="cuda",
    torch_dtype="float16"
)

# Quantized for memory efficiency
adapter = TransformersAdapter(
    model_name="meta-llama/Llama-2-70b-chat-hf",
    name="llama70b",
    device="cuda",
    load_in_4bit=True
)

# Load from local path
adapter = TransformersAdapter(
    model_name="/path/to/my/fine-tuned-model",
    name="custom"
)
```

### Prerequisites

```bash
pip install "vecna[transformers]"
# or
pip install transformers torch accelerate bitsandbytes
```

---

## Creating Custom Adapters

### Implementing a Custom Adapter

```python
from vecna.adapters import BaseAdapter, AdapterResponse
from vecna.core import HiveState

class MyCustomAdapter(BaseAdapter):
    """Custom adapter for a specific model/API."""
    
    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        domain: str = "general",
        my_custom_param: str = "default",
        **kwargs,
    ):
        super().__init__(model, name=name, domain=domain, **kwargs)
        self.my_custom_param = my_custom_param
        # Initialize your client/connection here
    
    async def generate(
        self,
        prompt: str,
        state: HiveState,
        **kwargs,
    ) -> AdapterResponse:
        """Generate a response from the model."""
        
        # Build your prompt with state context
        full_prompt = self._build_prompt(prompt, state)
        
        # Call your model
        start_time = time.time()
        raw_response = await self._call_model(full_prompt)
        duration = time.time() - start_time
        
        # Parse response into facts/beliefs
        facts, beliefs, hypotheses = self._parse_response(raw_response)
        
        return AdapterResponse(
            content=raw_response.text,
            model=self.model,
            facts=facts,
            beliefs=beliefs,
            hypotheses=hypotheses,
            duration=duration,
            tokens_used=raw_response.tokens,
            raw_response=raw_response,
        )
    
    def _build_prompt(self, prompt: str, state: HiveState) -> str:
        """Build the full prompt with identity and context."""
        identity = self._get_identity_prompt(state)
        context = state.get_memory_summary()
        return f"{identity}\n\n{context}\n\nQuery: {prompt}"
    
    async def _call_model(self, prompt: str) -> Any:
        """Call your model API."""
        # Implementation specific to your model
        pass
```

### Registering Custom Adapters

```python
# Register with HiveMind
hive = HiveMind()
adapter = MyCustomAdapter(
    model="my-model",
    name="custom",
    domain="specialized"
)
hive.register_adapter(adapter)
```

---

## Adapter Methods

### Common Methods

All adapters inherit these methods from `BaseAdapter`:

```python
class BaseAdapter:
    async def generate(
        self,
        prompt: str,
        state: HiveState,
        **kwargs,
    ) -> AdapterResponse:
        """Generate a response."""
    
    async def health_check(self) -> bool:
        """Check if adapter is healthy."""
    
    def enable(self) -> None:
        """Enable the adapter."""
    
    def disable(self) -> None:
        """Disable the adapter."""
    
    def get_stats(self) -> AdapterStats:
        """Get usage statistics."""
```

### AdapterStats

```python
@dataclass
class AdapterStats:
    total_calls: int
    successful_calls: int
    failed_calls: int
    total_tokens: int
    total_duration: float
    avg_duration: float
    avg_tokens_per_call: float
```

---

## Best Practices

### Model Selection

!!! tip "Domain Matching"
    - **General**: GPT-4o, Claude 3.5 Sonnet
    - **Code**: Groq Llama, GPT-4, CodeLlama
    - **Analysis**: Claude Opus, GPT-4
    - **Speed**: Groq, Claude Haiku

### Error Handling

```python
from vecna.exceptions import AdapterError, RateLimitError

try:
    response = await adapter.generate(prompt, state)
except RateLimitError:
    # Handle rate limiting
    await asyncio.sleep(60)
    response = await adapter.generate(prompt, state)
except AdapterError as e:
    logger.error(f"Adapter failed: {e}")
```

### Resource Management

```python
# Adapters are cleaned up automatically with HiveMind context manager
async with HiveMind() as hive:
    hive.add_openai("gpt-4o")
    # ... use hive ...
# Adapters closed automatically

# Manual cleanup
adapter = OpenAIAdapter("gpt-4o")
try:
    # ... use adapter ...
finally:
    await adapter.close()
```

---

## Related Documentation

- [HiveMind](hivemind.md) - Using adapters with HiveMind
- [Multi-Model Setup](../guides/multi-model.md) - Configuration guide
- [Consensus](consensus.md) - How adapter outputs are merged

---

*"Many voices, unified through the adapter protocol."*
