# Levers

A lever is what to change to break a causal chain. Families run from the cheapest to the most
expensive. Read the cluster's causal chain, then look across families: the link of the chain a
lever breaks decides its family, not the size of the pain.

| Family | Lever | Symptom that calls for it | Example | Trade-off |
|---|---|---|---|---|
| **Guard** | Type or validate at the boundary | A bug returns because invalid data gets through | Parse with a schema on input; a type that makes the bad state unrepresentable | Callers that relied on loose input break, loudly |
| | Constrain in the database | Duplicates, orphans, inconsistent rows | Unique index, foreign key, check constraint | Existing bad rows must be fixed before it applies |
| | Share the contract | Bugs at the border between two apps or services | Shared schema, versioned event, contract test | Both sides move together, or a version bridges them |
| | Lint rule or test | The same mistake is written again by different people | Custom lint rule, test on the invariant | Covers new code only until the backlog is fixed |
| **Simplify** | Remove a layer | A bug returns because the logic is copied in several places | Merge two paths into one | A migration of every caller |
| | Remodel the data | Endless edge cases around one object | Explicit state machine, drop a derived field | Data migration; read paths change |
| **Harden** | Make it idempotent | Duplicates after a retry | Idempotency key, dedupe on write | Needs a key the caller can provide |
| | Make it observable | Silent failures found by users | Job history, alert after N attempts | Noise until thresholds are tuned |
| **Change when** | Make it asynchronous | A long action times out or is cancelled halfway | Answer at once, notify when ready | The UI must show a pending state |
| | Precompute | A slow read repeated for a result that rarely changes | Materialized view, compute on write | Staleness and invalidation |
| **Change where** | Offload | Heavy work on the servers that answer users | PDF rendering moved to a dedicated function behind a queue | A new runtime to deploy, monitor and pay for |
| | Isolate | One load takes down another that has nothing to do with it | Dedicated pool, queue or quota | More capacity to size |
| | Split reads and writes | Screens slow because of writes, or the reverse | Read replica, dedicated projection | Replication lag |
| | Buy instead of build | In-house code breaks on a problem solved elsewhere | Managed service, standard library | Vendor lock-in, cost |

The lightest lever that would stop a cluster from coming back is usually a Guard or a Harden. When
the causal chain names a shared resource (CPU, pool, connection, process), the strongest lever is
usually in Change when or Change where.
