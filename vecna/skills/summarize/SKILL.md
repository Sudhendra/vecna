# Content Summarize Skill

> Summarize web content, YouTube videos, and podcasts via the `summarize` CLI.

## When to Use

- User shares a URL and asks "what's this about?"
- User asks to summarize an article, video, or podcast
- CuriosityEngine needs to research a topic (autonomous research)
- DreamLoop generates a research goal that requires reading content
- User asks to "catch me up" on a topic with multiple sources

## Available Commands

| Command | Description |
|---------|-------------|
| `summarize <url> --json` | Summarize any URL (article, video, podcast) |
| `summarize <url> --format=detailed --json` | Detailed summary with key points |
| `summarize <url> --format=bullet_points --json` | Bullet point summary |

## Execution

### Via Tool Registry
The tool is registered as `content_summarize` in Vecna's ToolRegistry:
```python
tool_result = await tool_runtime.execute("content_summarize", {"url": "https://..."})
```

### Direct CLI
```
summarize "https://example.com/article" --json
```

### Output Format (JSON)
```json
{
    "title": "Article Title",
    "summary": "Concise summary of the content...",
    "content_type": "article",
    "word_count": 1500,
    "url": "https://example.com/article"
}
```

## Supported Content Types

- **Articles/Blog Posts** — HTML content extraction and summarization
- **YouTube Videos** — Transcript extraction and summarization
- **Podcasts** — Audio transcription and summarization
- **PDFs** — Text extraction and summarization

## Privacy

- Summarized content may be stored as Facts in the substrate
- Raw content is not persisted — only the summary
- URLs are logged for audit purposes
- Content from LOCAL_ONLY integrations should not be summarized via cloud tools

## Error Handling

- If `summarize` is not installed: inform user to install via `brew install summarize`
- If URL is unreachable: return error with status code
- If content is too long: tool auto-truncates to 50,000 characters
- Timeout: 60 seconds default, configurable
