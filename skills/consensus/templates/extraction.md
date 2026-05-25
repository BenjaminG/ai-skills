# Template: extraction

## When to use

The prompt asks to **pull typed values out of an input** — entities from a ticket, fields from a document, dependencies from a manifest, dates from a log, mentions from a thread. Each item has a `type` (the kind of thing extracted) and a `value` (the extracted content).

## Schema

```yaml
type: array
items:
  type: object
  required: [type, value]
  properties:
    type:
      type: string
      enum: [<closed set derived from prompt — e.g. person, date, system, ticket_id>]
    value:
      type: string
    span:
      type: string
      description: optional — verbatim span from input (helps verify extraction is grounded)
    context:
      type: string
      description: optional — surrounding text or metadata
      maxLength: 200
```

## Vote key

```yaml
fields: [type, value]
```

Two extractions vote together when they share the same `type` AND `value` (after trim + case-fold normalization handled by the vote script). No numeric tolerance needed — extracted values should match exactly.

For values with known canonicalization (dates, IDs), prefer that the prompt asks the LLM to emit the canonical form (`2026-05-19` not `May 19th`). The vote does NOT do semantic normalization.

## Schema-adaptation hints

- **`type` enum**: enumerate exactly the entity types the prompt asks for. If the prompt says "extract people, companies, and dates", the enum is `[person, company, date]` — no catch-all (an extraction not fitting any type is hallucinated).
- **`span`**: include for grounding-critical use cases (legal, medical, compliance). Omit for high-volume extractions where token cost matters.
- **`value` normalization**: ask the LLM in the prompt to emit canonical forms (lowercase emails, ISO dates, trimmed strings). The prompt is the place to enforce this, not the schema.

## Example

Prompt: `"Extract all Linear ticket IDs, system names, and people mentioned in this Slack thread."`

Derived schema:

```yaml
type: enum [linear_ticket, system, person]
value: string
span: string  # optional but useful for verification
```

Vote key: `(type, value)`.

Two passes both extracting `{type: person, value: "Benjamin"}` and `{type: person, value: "benjamin"}` would normalize to the same group via case-fold. Two passes extracting `{type: person, value: "Benjamin Gelis"}` and `{type: person, value: "Benjamin"}` would be **distinct** — exact-match only, no fuzzy string matching.
