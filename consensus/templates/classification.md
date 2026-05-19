# Template: classification

## When to use

The prompt asks for **a single label** describing the input — triage category, sentiment, severity, intent, language. The output is one object (not a list), and the vote is pure majority over the label value.

## Schema

```yaml
type: object
required: [label]
properties:
  label:
    type: string
    enum: [<closed set derived from prompt — e.g. bug, feature, question, spam>]
  confidence:
    type: string
    enum: [low, medium, high]
    description: optional — only include if the prompt asks for confidence
  rationale:
    type: string
    maxLength: 200
    description: optional — brief justification (1 sentence)
```

## Vote key

```yaml
fields: [label]
single_object: true
```

The `single_object: true` flag tells the vote script that each pass produces ONE object (not a list). The consensus is the majority `label` across passes. Threshold semantics: `label` is retained only if it appears in `≥ threshold` passes.

If no label reaches threshold, the consensus is **`undecided`** — the script emits a special record indicating the labels seen and their counts. This is the correct outcome for genuinely ambiguous inputs.

## Schema-adaptation hints

- **`label` enum**: must be a closed set. If the prompt's category list isn't exhaustive, add an explicit `other` to the enum so the LLM has a valid out — but watch for `other` becoming the majority answer (signal that the enum is wrong).
- **`confidence`**: include sparingly. LLM self-confidence is poorly calibrated. The vote itself is a much better confidence signal: 3/3 = high, 2/3 = medium, 1/3 = dropped.
- **`rationale`**: useful for triage tasks where a human will review. Per-pass rationales differ even when labels agree — the vote keeps the consensus label only; rationales from the winning passes are concatenated in the divergences section.

## Example

Prompt: `"Classify this support ticket as one of: bug, feature_request, question, billing, spam."`

Derived schema:

```yaml
label: enum [bug, feature_request, question, billing, spam]
rationale: string  # max 200 chars
```

Vote key: `(label,)` with `single_object: true`.

If 3 passes return `bug, bug, billing` and threshold is 2 → consensus = `bug`.
If 3 passes return `bug, billing, question` and threshold is 2 → consensus = `undecided` (no label hit threshold).
