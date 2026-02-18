# Google Suite Skill

> Access user's Google Calendar, Gmail, Contacts, and Tasks via `gogcli`.

## When to Use

- User asks about their schedule, calendar, or "what's on today"
- User mentions emails, inbox, or messages from specific people
- User needs to look up a contact's information
- User asks about their tasks or to-do items
- Time-based context is needed for a response (e.g., "do I have time for X?")
- User asks to check, review, or summarize their day

## Available Commands

| Command | Description | Example Output |
|---------|-------------|----------------|
| `gogcli cal events list --json` | Upcoming calendar events | `[{"title": "Standup", "start": "..."}]` |
| `gogcli gmail messages list --max=5 --json` | Recent emails | `[{"subject": "...", "from": "..."}]` |
| `gogcli contacts list --json` | Contact directory | `[{"name": "...", "email": "..."}]` |
| `gogcli tasks list --json` | Google Tasks | `[{"title": "...", "status": "..."}]` |

## Execution

1. All commands are run via `asyncio.create_subprocess_exec` with `--json` flag
2. Parse the JSON response array
3. Summarize relevant information concisely
4. Incorporate into the conversation context naturally

## Privacy

- **All calendar and email data is `LOCAL_ONLY` by default**
- Do NOT include raw email content in hive updates sent to cloud models
- Calendar event titles may be included in context; full attendee lists should not
- Contact information should never be shared with cloud models
- When summarizing for the user, strip PII from any data sent to non-local models

## Error Handling

- If `gogcli` is not installed: inform user to install via `brew install gogcli`
- If authentication fails: instruct user to run `gogcli auth login`
- If no results returned: report "no upcoming events/emails found"

## Integration with Vecna

- Calendar events create temporal Facts with validity windows matching event times
- Important emails can generate Goals (e.g., "Reply to email from X about Y")
- The BackgroundObserver can poll these on a schedule for proactive awareness
