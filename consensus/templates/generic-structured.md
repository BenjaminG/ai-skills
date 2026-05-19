# Template: generic-structured

## When to use

**Fallback only** — pick this template when none of the other three templates fit:

- Not a list of issues at coordinates → not `finding-list`
- Not a list of typed extracted values → not `extraction`
- Not a single label → not `classification`

Examples that legitimately fall into generic-structured:

- A list of objects with mixed shapes (e.g., "list the top 3 risks AND the top 3 opportunities")
- A nested structure (e.g., "summarize this PR with sections: intent, risks, follow-ups")
- A list whose items don't have a natural identity key

## Schema

The schema is **fully derived from the prompt** — there is no fixed shape. Build the JSON Schema directly from what the prompt asks for, with these constraints:

1. The top-level type MUST be `array` or `object`.
2. Every leaf field MUST have a primitive type (`string`, `integer`, `number`, `boolean`, `enum`).
3. No free-form text fields longer than 500 chars (consensus on long prose is unreliable — that signals you should be using a different tool, not self-consistency).
4. If the schema is an array, each item MUST have at least one field that can serve as a vote key. If you can't identify a vote key, the prompt is not a fit for self-consistency — abort with a message to the user.

## Vote key

The vote key MUST be picked explicitly during schema confirmation (Step 1d in SKILL.md). The user must accept or edit it before the run starts.

```yaml
fields: [<one or more fields whose combination uniquely identifies an item>]
numeric_tolerance:
  <field>: <±N>     # optional, only for numeric fields where small differences should still match
single_object: false  # set to true if top-level is object (not array)
```

For nested objects: vote keys can use dotted paths (e.g., `risk.id`). The vote script supports one level of nesting; deeper nesting is a smell — flatten the schema.

## Schema-adaptation hints

- **Resist the temptation to over-fit.** If you find yourself adding 5+ fields to make the prompt fit, you're past the value of self-consistency — the LLM will produce 3 wildly different shapes and nothing will vote together.
- **Keep enums tight.** Free-string fields are the #1 reason votes fail. Anywhere you can replace a string with an enum, do.
- **One axis of variation at a time.** Generic-structured works when the output has one varying dimension (the list of items, or the value of one field). When it has many, you have multiple consensus problems mashed together — split into multiple `consensus` runs.

## Example

Prompt: `"For this PR, return: an `intent` summary (1 sentence), a list of `risks` with id+severity+description, and a list of `follow_ups` with id+owner+description."`

Derived schema:

```yaml
type: object
required: [intent, risks, follow_ups]
properties:
  intent:
    type: string
    maxLength: 200
  risks:
    type: array
    items:
      type: object
      required: [id, severity, description]
      properties:
        id: { type: string }
        severity: { type: string, enum: [high, medium, low] }
        description: { type: string, maxLength: 200 }
  follow_ups:
    type: array
    items:
      type: object
      required: [id, owner, description]
      properties:
        id: { type: string }
        owner: { type: string }
        description: { type: string, maxLength: 200 }
```

Vote key (multi-axis — vote script applies it per array):

```yaml
single_object: true
arrays:
  risks:
    fields: [id]
  follow_ups:
    fields: [id]
ignore_fields: [intent]   # free-text scalar, not voted on — kept from the highest-vote pass or first valid pass
```

The `intent` field is too long-form to vote meaningfully — the script picks one and shows divergences. Watch for big divergences here as a signal the prompt is fuzzy.
