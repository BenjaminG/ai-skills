#!/usr/bin/env python3
"""
PostToolUse hook to format code after file edits.

Example configuration in settings.json:
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/code_formatter.py"
          }
        ]
      }
    ]
  }
}
"""

import json
import os
import subprocess
import sys

# Define formatters for different file types
FORMATTERS = {
    ".py": ["black", "--quiet"],
    ".js": ["prettier", "--write"],
    ".ts": ["prettier", "--write"],
    ".tsx": ["prettier", "--write"],
    ".jsx": ["prettier", "--write"],
    ".json": ["prettier", "--write"],
}


def format_file(file_path: str) -> tuple[bool, str]:
    """
    Format a file using the appropriate formatter.
    Returns (success, message) tuple.
    """
    _, ext = os.path.splitext(file_path)

    if ext not in FORMATTERS:
        return True, ""  # No formatter needed

    formatter = FORMATTERS[ext]
    try:
        subprocess.run(
            formatter + [file_path],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, f"Formatted {file_path}"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to format {file_path}: {e.stderr}"
    except FileNotFoundError:
        return False, f"Formatter not found: {formatter[0]}"


try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
    sys.exit(1)

tool_name = input_data.get("tool_name", "")
tool_input = input_data.get("tool_input", {})
file_path = tool_input.get("file_path", "")

if not file_path or not os.path.isfile(file_path):
    sys.exit(0)

# Format the file
success, message = format_file(file_path)

if not success:
    print(message, file=sys.stderr)
    sys.exit(1)

if message:
    print(message)

sys.exit(0)
