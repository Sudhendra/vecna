# iMessage Skill

> Bidirectional iMessage communication via the `imsg` CLI.

## When to Use

- User asks to send a message to someone via iMessage
- User wants to read or check recent iMessages
- User asks "did anyone message me?"
- User wants to reply to a specific person
- Autonomous mode needs to notify the user of something important

## Requirements

- **macOS only** -- iMessage is not available on other platforms
- **Full Disk Access** required for reading the iMessage database
- `imsg` CLI must be installed (`brew install imsg`)

## Available Commands

| Command | Description |
|---------|-------------|
| `imsg watch --json` | Stream incoming messages as JSON lines |
| `imsg send <number> <message>` | Send a message to a phone number or Apple ID |
| `imsg search <query> --json` | Search message history |
| `imsg chats --json` | List recent conversations |

## Execution

### Sending Messages

```bash
imsg send "+1234567890" "Hello from Vecna!"
```

- Always confirm with user before sending messages in interactive mode
- In autonomous mode, only send to pre-approved contacts
- Truncate messages longer than 10,000 characters

### Receiving Messages

Messages are streamed via `imsg watch --json` as newline-delimited JSON:

```json
{"sender": "+1234567890", "text": "Hey!", "date": "2026-02-16T10:30:00", "is_from_me": false}
```

- Skip messages where `is_from_me` is true
- Parse sender, text, and optional attachments
- Route to HiveLoop.think() for processing

## Privacy

- **ALL iMessage content is `LOCAL_ONLY`** -- never sent to cloud models
- Message content must not appear in hive updates
- Contact names and phone numbers are never shared externally
- Only summarized intent (e.g., "user received a question about project timeline")
  may be used in non-local processing, and only with user consent

## Error Handling

- If `imsg` is not installed: inform user to install via `brew install imsg`
- If Full Disk Access is denied: guide user to System Settings > Privacy > Full Disk Access
- If send fails: log error, inform user, do not retry automatically
