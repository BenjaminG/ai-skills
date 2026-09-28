# <task name>

One sentence: what the agent must accomplish.

## URL
https://example.com/the-page

## Inputs
- field_name: value
- username: demo_user
- password: secret

## Steps
1. Navigate to the URL.
2. Do action X (click/fill/select ...).
3. Submit and confirm the result.

## Success condition
What, observed in the page, proves success — e.g. "a confirmation banner reading
'Request #NNNNN' is present", or "the <h1> text equals 'Example Domain'". Be concrete;
this is what the inner agent must verify before returning `success: true`.

## Expected output
```json
{ "success": true, "confirmation": "Request #12345", "error_reasoning": null }
```
