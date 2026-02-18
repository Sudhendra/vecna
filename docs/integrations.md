# Vecna Integrations Guide

## Supported LLM Providers

Vecna supports multiple LLM providers simultaneously. Each provider is configured as an
adapter and can participate in consensus-driven reasoning.

### GitHub Copilot

Uses GitHub's Models API via Copilot authentication.

- **Setup:** `gh auth login` or set `GITHUB_TOKEN` directly.
- **Env Vars:** `GITHUB_TOKEN`
- **Config:** `provider: copilot`, `model_id: gpt-4o`

### Ollama (Local)

Run models locally via Ollama. No API key required.

- **Setup:** Install Ollama, `ollama pull llama3`.
- **Env Vars:** `OLLAMA_HOST` (default: `http://localhost:11434`)
- **Config:** `provider: ollama`, `model_id: llama3`

### Groq (Cloud)

High-speed inference via Groq's cloud API.

- **Setup:** Sign up at groq.com, generate API key.
- **Env Vars:** `GROQ_API_KEY`
- **Config:** `provider: groq`, `model_id: mixtral-8x7b-32768`

### OpenAI

Direct OpenAI API with native function calling support.

- **Setup:** Create key at platform.openai.com.
- **Env Vars:** `OPENAI_API_KEY`
- **Config:** `provider: openai`, `model_id: gpt-4-turbo`
- **Features:** Native tool calling via `hive_update` function schema, streaming.

### Anthropic

Claude models via Anthropic API with native tool use.

- **Setup:** Create key at console.anthropic.com.
- **Env Vars:** `ANTHROPIC_API_KEY`
- **Config:** `provider: anthropic`, `model_id: claude-3-sonnet-20240229`
- **Features:** Native tool use via `hive_update` tool schema, streaming.

### HuggingFace Transformers (Local)

Run models locally with the `transformers` library.

- **Setup:** `pip install vecna[all]`
- **Env Vars:** `HF_HOME` (cache dir), `HF_TOKEN` (gated models)
- **Config:** `provider: huggingface`, `model_id: mistralai/Mistral-7B-Instruct-v0.2`

## External Integrations

### Slack

Connect Vecna as a Slack bot for team-wide hive mind access.

- Env Vars: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
- Uses Composio integration framework for event handling.
- Messages route through `MessageRouter` to `HiveLoop.think()`.

### Discord

Run Vecna as a Discord bot.

- Env Vars: `DISCORD_BOT_TOKEN`
- Supports slash commands and direct mentions.
- Uses Composio integration framework.

### GitHub

GitHub webhook integration for code review and issue triage.

- Uses Composio for webhook handling.
- Env Vars: `COMPOSIO_API_KEY`
- Can analyze PRs, suggest fixes, respond to issue comments.

## Channel System

Vecna routes all messages through a unified `MessageRouter`:

| Channel | Format | Transport |
|---------|--------|-----------|
| CLI | Rich markup | Direct function call |
| HTTP API | JSON | POST /api/chat |
| WebSocket | JSON | /ws/stream |
| Slack | Markdown | Composio webhook |
| Discord | Markdown | Composio webhook |
| SMS | Plain text | Composio webhook |

All channels call `HiveLoop.think()` and return the response formatted for the target.

## Adding a Custom Adapter

```python
from vecna.adapters.base import BaseAdapter
from vecna.config.schema import ModelConfig

class MyAdapter(BaseAdapter):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        # Initialize your provider client

    async def generate(self, prompt: str) -> str:
        # Call your LLM and return the raw response
        return await self.client.complete(prompt)

    def _get_provider_name(self) -> str:
        return "my_provider"
```

Then update `create_adapter()` in `vecna/adapters/base.py` to route to your adapter.

## Adding a Custom Integration

Use the `BackgroundObserver` pattern:

```python
from vecna.integrations.base import BaseIntegration

class MyIntegration(BaseIntegration):
    async def start(self):
        # Connect to your external service
        pass

    async def on_event(self, event):
        # Process external events into HiveState updates
        update = self.process_event(event)
        self.loop.state.apply_update(update)
```
