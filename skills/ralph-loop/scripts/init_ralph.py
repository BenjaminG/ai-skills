#!/usr/bin/env python3
"""
Initialize a new Ralph loop with interactive configuration.
Usage: python init_ralph.py <output-directory> [--template <name>]
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = SKILL_DIR / "templates"

def get_template_names():
    """Get available template names."""
    if not TEMPLATES_DIR.exists():
        return []
    return [f.stem for f in TEMPLATES_DIR.glob("*.md")]

def read_template(name: str) -> str:
    """Read a template file."""
    template_path = TEMPLATES_DIR / f"{name}.md"
    if template_path.exists():
        return template_path.read_text()
    return ""

def create_ralph_sh() -> str:
    """Create the bash runner script with streaming output."""
    return '''#!/bin/bash
set -e

MAX_ITERATIONS=${1:-50}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Log file setup
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/ralph-$(date +%Y%m%d-%H%M%S).log"

log() {
  echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"
}

# jq filters for streaming output
stream_text='select(.type == "assistant").message.content[]? | select(.type == "text").text // empty | gsub("\\n"; "\\r\\n") | . + "\\r\\n\\n"'
final_result='select(.type == "result").result // empty'

log "Starting Ralph loop (log: $LOG_FILE)"
log "Max iterations: $MAX_ITERATIONS"

for i in $(seq 1 $MAX_ITERATIONS); do
  log "═══ Iteration $i ═══"

  tmpfile=$(mktemp)
  trap "rm -f $tmpfile" EXIT

  claude --dangerously-skip-permissions \\
    --verbose \\
    --print \\
    --output-format stream-json \\
    -p "$(cat "$SCRIPT_DIR/prompt.md")" 2>&1 \\
  | grep --line-buffered '^{' \\
  | tee "$tmpfile" \\
  | tee -a "$LOG_FILE" \\
  | jq --unbuffered -rj "$stream_text"

  result=$(jq -r "$final_result" "$tmpfile" 2>/dev/null || echo "")

  if echo "$result" | grep -q "<promise>COMPLETE</promise>"; then
    log "✅ Loop completed successfully!"
    rm -f "$tmpfile"
    exit 0
  fi

  rm -f "$tmpfile"
  sleep 2
done

log "⚠️ Max iterations reached"
exit 1
'''

def create_progress_txt(goal: str) -> str:
    """Create initial progress.txt."""
    return f'''# Ralph Progress Log

Started: {datetime.now().strftime("%Y-%m-%d")}
Goal: {goal}

---

'''

def create_knowledge_md(goal: str) -> str:
    """Create initial knowledge.md."""
    return f'''# Ralph Loop Knowledge Base

This file accumulates learnings from iterative execution.

## Overview

{goal}

## Patterns Discovered

*Learnings from each iteration will be appended below.*

---
'''

def create_prompt_md(config: dict, template_content: str = "") -> str:
    """Create prompt.md from config or template."""
    if template_content:
        # Replace placeholders in template
        content = template_content
        content = content.replace("{{GOAL}}", config.get("goal", ""))
        content = content.replace("{{DESCRIPTION}}", config.get("description", ""))
        return content

    # Generate custom prompt
    goal = config.get("goal", "Complete all tasks")
    steps = config.get("steps", [])
    acceptance = config.get("acceptance_criteria", [])

    steps_md = "\n".join([f"### Step {i+3}: {step['name']}\n\n{step['instructions']}\n"
                          for i, step in enumerate(steps)])

    acceptance_md = "\n".join([f"- [ ] {c}" for c in acceptance])

    return f'''# Ralph Agent: {goal}

## Configuration

- **Task System**: Use TaskList, TaskGet, TaskUpdate, TaskCreate tools
- **Progress**: `progress.txt`
- **Knowledge**: `knowledge.md`

## Your Task (One Iteration)

### Step 1: Load Context

1. Use `TaskList` to get all tasks with status and dependencies
2. Read `knowledge.md` to understand previous learnings

### Step 2: Determine State

Check TaskList results:

- **If ALL tasks have status "completed"** → Output `<promise>COMPLETE</promise>` and stop
- **If pending tasks exist** → Continue to Step 3

### Step 3: Select Target

Use TaskList to find the FIRST task where:
- status is "pending"
- blockedBy is empty (no unresolved dependencies)

Use TaskUpdate to set status to "in_progress":
```
TaskUpdate:
  taskId: "<selected-task-id>"
  status: "in_progress"
```

Use TaskGet to read full task description and requirements.

{steps_md}

### Final Step: Update Status

**Mark task complete:**
```
TaskUpdate:
  taskId: "<task-id>"
  status: "completed"
```

**Update progress.txt:**
```
[datetime] - Completed: {{task_name}} | Status: success
```

**Update knowledge.md:**
```markdown
---

## {{task_name}} (completed {{date}})

**Findings**: ...

**Notes**: ...
```

## Acceptance Criteria

{acceptance_md if acceptance_md else "- [ ] Task-specific validation passes"}

## Important Rules

- Process ONLY 1 task per iteration
- Only work on tasks with empty blockedBy (dependencies resolved)
- Use TaskUpdate to track status changes
- Fail fast on errors - do not silently continue
- ONLY mark status "completed" when work is fully done and validated

## Completion

When TaskList shows all tasks with status "completed":

```
<promise>COMPLETE</promise>
```
'''

def init_ralph(output_dir: str, template: str = None, config: dict = None):
    """Initialize a new Ralph loop directory."""
    output_path = Path(output_dir)

    # Create directories
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "logs").mkdir(exist_ok=True)

    config = config or {}

    # Load template if specified
    template_content = ""
    if template:
        template_content = read_template(template)
        if not template_content:
            print(f"Warning: Template '{template}' not found, using custom generation")

    # Create files (no backlog.json - uses native Task system)
    files = {
        "ralph.sh": create_ralph_sh(),
        "progress.txt": create_progress_txt(config.get("goal", "")),
        "knowledge.md": create_knowledge_md(config.get("goal", "")),
        "prompt.md": create_prompt_md(config, template_content),
    }

    for filename, content in files.items():
        filepath = output_path / filename
        filepath.write_text(content)
        if filename == "ralph.sh":
            filepath.chmod(0o755)

    print(f"✅ Ralph loop initialized at: {output_path}")
    print(f"\nFiles created:")
    for f in files:
        print(f"  - {f}")
    print(f"\nTo run: cd {output_path} && ./ralph.sh")

def main():
    parser = argparse.ArgumentParser(description="Initialize a new Ralph loop")
    parser.add_argument("output", help="Output directory for the loop")
    parser.add_argument("--template", "-t", choices=get_template_names() or ["custom"],
                        help="Template to use")
    parser.add_argument("--goal", "-g", help="Goal of the loop")
    parser.add_argument("--description", "-d", help="Description of the loop")

    args = parser.parse_args()

    config = {}
    if args.goal:
        config["goal"] = args.goal
    if args.description:
        config["description"] = args.description

    init_ralph(args.output, args.template, config)

if __name__ == "__main__":
    main()
