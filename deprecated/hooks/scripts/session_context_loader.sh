#!/bin/bash
#
# SessionStart hook to load development context at session start.
#
# Example configuration in settings.json:
# {
#   "hooks": {
#     "SessionStart": [
#       {
#         "hooks": [
#           {
#             "type": "command",
#             "command": "/path/to/session_context_loader.sh"
#           }
#         ]
#       }
#     ]
#   }
# }

# Read hook input
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
SOURCE=$(echo "$INPUT" | jq -r '.source')

# Build context message
CONTEXT=""

# Add current git branch and status if in a git repo
if git rev-parse --git-dir > /dev/null 2>&1; then
    BRANCH=$(git branch --show-current)
    CONTEXT+="Current git branch: $BRANCH\n"

    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD --; then
        CONTEXT+="⚠️  You have uncommitted changes\n"
    fi

    # Get recent commits
    RECENT_COMMITS=$(git log --oneline -3)
    CONTEXT+="Recent commits:\n$RECENT_COMMITS\n"
fi

# Add project-specific context (customize this section)
if [ -f "package.json" ]; then
    CONTEXT+="\nNode.js project detected\n"
    PROJECT_NAME=$(jq -r '.name' package.json)
    CONTEXT+="Project: $PROJECT_NAME\n"
fi

# Persist environment variables if CLAUDE_ENV_FILE is available
if [ -n "$CLAUDE_ENV_FILE" ]; then
    # Example: Set NODE_ENV
    echo 'export NODE_ENV=development' >> "$CLAUDE_ENV_FILE"

    # Example: Add node_modules/.bin to PATH
    if [ -d "./node_modules/.bin" ]; then
        echo 'export PATH="$PATH:./node_modules/.bin"' >> "$CLAUDE_ENV_FILE"
    fi
fi

# Output context as JSON
jq -n \
  --arg ctx "$CONTEXT" \
  '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $ctx
    }
  }'

exit 0
