# Template: finding-list

## When to use

The prompt asks for a **list of issues at coordinates** — bugs, lints, security findings, code smells, anti-patterns, todos. Each item lives at a specific location (file + line, or symbol + offset).

## Schema

```yaml
type: array
items:
  type: object
  required: [rule_id, file, line, message]
  properties:
    rule_id:
      type: string
      enum: [<closed set derived from prompt — e.g. sql-string-concat, sql-template-literal, sql-other>]
    file:
      type: string
    line:
      type: integer
      minimum: 1
    message:
      type: string
      maxLength: 200
    evidence:
      type: string
      description: verbatim code excerpt or specific reference
    severity:
      type: string
      enum: [BLOCKER, MAJOR, NIT]
      description: optional — only include if the prompt asks for severity
```

## Vote key

```yaml
fields: [file, rule_id, line]
numeric_tolerance:
  line: 5
```

Two findings vote together when they share the same `file` and `rule_id` AND their `line` numbers fall in the same ±5 bucket. The `line` field MUST be listed in `fields` for the tolerance to apply — `numeric_tolerance` only affects fields that are part of the key.

## Schema-adaptation hints

When deriving the schema from the user's prompt:

- **`rule_id` enum**: extract the categories implied by the prompt. If the prompt is "find SQL injection risks", the enum is `[sql-string-concat, sql-template-literal, sql-orm-bypass, sql-other]`. Always include an `-other` catch-all so the LLM has a valid out.
- **Severity**: include only if the prompt explicitly mentions tiering. Default to omitted to keep the schema tight.
- **Evidence**: include for code review prompts (verifiability matters), omit for high-volume scans (saves tokens).

## Example

Prompt: `"Review this diff for null-pointer and undefined-access risks."`

Derived schema:

```yaml
rule_id: enum [null-deref, undefined-access, optional-chain-needed, npe-other]
file: string
line: integer
message: string (max 200)
evidence: string
```

Vote key: `(file, rule_id, line ±5)`.
