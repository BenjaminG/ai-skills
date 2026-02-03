#!/usr/bin/env python3
"""
UserPromptSubmit hook to validate prompts and add context.

Example configuration in settings.json:
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/prompt_validator.py"
          }
        ]
      }
    ]
  }
}
"""

import json
import re
import sys
from datetime import datetime

# Define patterns to block
BLOCKED_PATTERNS = [
    (r"(?i)\b(password|secret|api[_-]?key)\s*[:=]\s*\S+", "Prompt contains potential secrets"),
]


def validate_prompt(prompt: str) -> tuple[bool, str]:
    """
    Validate prompt against security patterns.
    Returns (is_valid, reason) tuple.
    """
    for pattern, message in BLOCKED_PATTERNS:
        if re.search(pattern, prompt):
            return False, message
    return True, ""


try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
    sys.exit(1)

prompt = input_data.get("prompt", "")

# Validate the prompt
is_valid, reason = validate_prompt(prompt)

if not is_valid:
    # Block the prompt
    output = {
        "decision": "block",
        "reason": f"Security policy violation: {reason}. Please rephrase without sensitive information.",
    }
    print(json.dumps(output))
    sys.exit(0)

# Add current time to context
context = f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": context,
    }
}

print(json.dumps(output))
sys.exit(0)
