#!/usr/bin/env python3
"""
PreToolUse hook to validate and suggest better bash commands.

Example configuration in settings.json:
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/bash_command_validator.py"
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

# Define validation rules as (regex pattern, message) tuples
VALIDATION_RULES = [
    (
        r"\bgrep\b(?!.*\|)",
        "Use 'rg' (ripgrep) instead of 'grep' for better performance",
    ),
    (
        r"\bfind\s+\S+\s+-name\b",
        "Use 'fd' instead of 'find -name' for better performance",
    ),
    (
        r"\bcat\s+.*\|\s*grep\b",
        "Use 'rg' directly instead of 'cat | grep'",
    ),
]


def validate_command(command: str) -> list[str]:
    """Validate command against rules and return list of issues."""
    issues = []
    for pattern, message in VALIDATION_RULES:
        if re.search(pattern, command):
            issues.append(message)
    return issues


try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
    sys.exit(1)

tool_name = input_data.get("tool_name", "")
tool_input = input_data.get("tool_input", {})
command = tool_input.get("command", "")

if tool_name != "Bash" or not command:
    sys.exit(0)

# Validate the command
issues = validate_command(command)

if issues:
    for message in issues:
        print(f"• {message}", file=sys.stderr)
    # Exit code 2 blocks tool call and shows stderr to Claude
    sys.exit(2)

# No issues - allow command to proceed
sys.exit(0)
