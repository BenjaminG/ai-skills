# Codex CLI Non-Interactive Mode Reference

This document provides detailed command syntax and options for `codex exec`.

## Basic Command Syntax

```bash
codex exec "<task description>"
```

## Execution Modes

### Read-Only Mode (Default)
```bash
codex exec "<task>"
```
- Prevents file modifications
- Blocks network-dependent commands
- Safe for code analysis and review

### Full Automation Mode
```bash
codex exec --full-auto "<task>"
```
- Permits file edits
- Maintains network access restrictions
- Use when file changes are needed

### Unrestricted Mode
```bash
codex exec --sandbox danger-full-access "<task>"
```
- Enables file editing AND networked commands
- Use only when absolutely necessary
- Highest risk mode

## Output Options

### Default Output
- Activity streams to stderr
- Final agent message outputs to stdout
- Pipe-friendly for shell integrations

### Save Output to File
```bash
codex exec "<task>" -o output.txt
codex exec "<task>" --output-last-message output.txt
```

### JSON Streaming Mode
```bash
codex exec --json "<task>"
```

With `--json`, stdout becomes a JSONL stream of every event Codex emits. Stderr continues to show streaming progress.

**Event types:**

| Event | Description | Key Fields |
|---|---|---|
| `thread.started` | Session begins | `thread_id` |
| `turn.started` | Agent turn begins | — |
| `turn.completed` | Turn ends | `usage` (`input_tokens`, `cached_input_tokens`, `output_tokens`) |
| `turn.failed` | Turn error | error details |
| `item.started` | Item begins processing | `item` (`id`, `type`, `status`) |
| `item.completed` | Item finishes | `item` (`id`, `type`, type-specific fields) |
| `error` | General error | error details |

**Item types:** `agent_message`, `reasoning`, `command_execution`, `file_change`, `mcp_tool_call`, `web_search`, `plan_update`

**Example stream:**
```jsonl
{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"bash -lc ls","status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_3","type":"agent_message","text":"Repo contains docs, sdk, and examples directories."}}
{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122}}
```

**Filtering with jq:**
```bash
# Only agent messages
codex exec --json "<task>" | jq 'select(.type == "item.completed" and .item.type == "agent_message")'

# Token usage per turn
codex exec --json "<task>" | jq 'select(.type == "turn.completed") | .usage'

# Command executions only
codex exec --json "<task>" | jq 'select(.item.type == "command_execution")'
```

### Structured Output with Schema
```bash
codex exec "<task>" --output-schema ~/schema.json
```
- Provide JSON Schema file for formatted responses
- Schema must follow OpenAI's strict structured output requirements
- Useful for automation pipelines requiring specific data formats

## Session Management

Sessions are persisted to disk by default, making every non-interactive run resumable.

### Resume Previous Sessions
```bash
# Resume last session
codex exec resume --last "<follow-up task>"

# Resume specific session by ID
codex exec resume <SESSION_ID> "<follow-up task>"
```

### Ephemeral Sessions
Prevent session persistence for one-shot tasks:
```bash
codex exec --ephemeral "<task>"
```

### Taking Over Non-Interactive Sessions
Resume a session started in a different context (e.g., CI → local):
```bash
# CI pipeline captures session ID from JSON stream
SESSION_ID=$(codex exec --json "<task>" 2>/dev/null | \
  jq -r 'select(.type=="thread.started") | .session_id')

# Local machine resumes with full conversation context
codex exec resume "$SESSION_ID" "<follow-up task>" --full-auto
```

**Important Notes:**
- Conversation context persists across resumed sessions
- Behavior flags (--full-auto, --sandbox, etc.) must be re-specified on each invocation
- Session data is stored locally; cross-machine resume requires shared/transferred session files
- Use `--ephemeral` to opt out of persistence for disposable runs

## Environment and Requirements

### Git Repository Requirement
Codex requires a Git repository by default to prevent destructive changes.

Bypass if needed:
```bash
codex exec --skip-git-repo-check "<task>"
```

### Authentication
Uses default Codex CLI authentication.

Override via environment variable:
```bash
CODEX_API_KEY=your-key-here codex exec "<task>"
```

## Common Use Cases

### Code Analysis
```bash
codex exec "Analyze the authentication flow and identify potential security issues"
```

### Generate Reports
```bash
codex exec "Generate a changelog from recent commits" -o changelog.md
```

### Code Review with Structured Output
```bash
codex exec "Review code for bugs and security issues" --output-schema review-schema.json --json
```

### Multi-Step Analysis with Resume
```bash
# Initial analysis
codex exec "Analyze the codebase architecture"

# Follow-up in same context
codex exec resume --last "Now identify performance bottlenecks"
```

## Best Practices

1. **Start with read-only mode** for initial analysis
2. **Use --full-auto only when modifications are intended**
3. **Leverage session resume** for multi-step workflows to maintain context
4. **Combine --json with --output-schema** for automation pipelines
5. **Store session IDs** if you need to resume specific analyses later
6. **Use descriptive task descriptions** to get better results
7. **Pipe stderr to log files** when running in automation to capture activity logs
