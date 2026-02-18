# WhatsApp Skill

> Bidirectional WhatsApp communication via the `wacli` CLI.

## When to Use

- User asks to send a WhatsApp message
- User wants to search their WhatsApp message history
- User asks "did anyone message me on WhatsApp?"
- User wants to reply to a specific person on WhatsApp
- Autonomous mode needs to notify the user via WhatsApp

## Requirements

- `wacli` CLI must be installed (`brew install wacli`)
- First-time setup requires QR code scanning for WhatsApp Web authentication
- Local SQLite database stores message history with FTS5 full-text search

## Available Commands

| Command | Description |
|---------|-------------|
| `wacli watch --json` | Stream incoming messages as JSON lines |
| `wacli send <number> <message>` | Send a message to a phone number |
| `wacli search <query> --json` | Search message history (FTS5) |
| `wacli chats --json` | List recent conversations |
| `wacli status` | Check connection status |

## Execution

### Sending Messages

```bash
wacli send "+1234567890" "Hello from Vecna!"
```

- Always confirm with user before sending messages in interactive mode
- In autonomous mode, only send to pre-approved contacts
- Messages are limited to 65,536 characters

### Searching Messages

```bash
wacli search "project deadline" --json --limit=20
```

- Uses SQLite FTS5 for fast full-text search
- Results include sender, text, timestamp, and chat context

### Receiving Messages

Messages are streamed via `wacli watch --json` as newline-delimited JSON:

```json
{"sender": "+1234567890", "sender_name": "Alice", "text": "Hey!", "timestamp": "...", "is_from_me": false}
```

## Privacy

- **ALL WhatsApp content is `LOCAL_ONLY`** — never sent to cloud models
- Message content, contact names, and phone numbers are never shared externally
- Only summarized intent may be used in non-local processing, with user consent

## Error Handling

- If `wacli` is not installed: inform user to install via `brew install wacli`
- If not authenticated: guide user to run `wacli auth` and scan QR code
- If send fails: log error, inform user, do not retry automatically
