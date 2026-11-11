# Project brief

The brief turns the winning lever into a project a team can pick up. It is written for people who
were not in the run, product people included: users' words first, implementation names last.

## Shape

```
# <Title: the change, in plain words>

<One-line summary: what moves or changes, for which users, rolled out how.>

## Why
<What users and the team live with today, from the ledger: one bullet per symptom, bold lead,
then the consequence. Link the strongest evidence.>

## What changes
<The new flow in 2 to 4 sentences, then a mermaid flowchart of it. What users will notice, and
what stays the same.>

## How we roll it out
<One slice first (one document type, one endpoint, one tenant), behind a switch that brings back
today's behaviour at once. When the risk calls for it, a shadow mode first: the new path runs
next to the old one and its result is compared, never used. Then milestones, each one a state a
person can check.>

## Done when
<Two to four observable outcomes, the first one in users' terms.>

## Tracking
<What each run records (asked, succeeded, attempts, error) and who is alerted when it fails.>
```

## Rules

- Every claim in **Why** traces to a ledger row.
- The switch and the way back are in **How we roll it out**, always.
- Milestones are states ("runs in staging with the switch off"), not tasks ("write the handler").
- Issue breakdown stays out of the brief; it comes after the project is accepted.
