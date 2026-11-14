# Why `elevate` is not creative, and what would change that

Question: elevate's output reads as local, reactive fixes. Would it ever have proposed the kind of
initiative a host team actually launched: a cell-based hexagonal architecture, "moments" as the one
entry point for outgoing messages, or a proof of concept that renders PDFs in a dedicated Lambda?
What would have to change in the skill?

Sources: the skill text at `0ffd599` (line numbers below refer to it), its git history, the host
repo (a B2B events marketplace, called "the host" below), the host's issue tracker (IDs only), the
local transcripts of the three elevate runs on the host, and papers on LLM ideation. The host is
private: everything about it is paraphrased, people appear by role.

## Summary

- **The Lambda initiative is in elevate's reach by construction, not by creativity.** elevate's
  current shape was written on 2026-11-11 by taking that project as the model: the user pointed at
  it as the example of a creative result, the brief template was copied from its structure, and the
  `Offload` example in `levers.md` is that project. Two live runs found its causal chain and then
  ranked it #9 or dropped it as covered by current work.
- **The two other initiatives cannot be reached.** Their trigger was not a production failure. For
  moments it was a product KPI plus dispersion measured across the codebase. For cells it was the
  cost of diagnosing a class of bugs, a strategic end-state and a borrowed external canon. elevate
  reads only failure signals (`SKILL.md:15`, `signals.md` contract lines 3-6), generates levers
  per cluster against one local link (`SKILL.md:82-85`), has no lever family for "name a new domain
  concept" or "draw a boundary", and ranks with an evidence bar that only small levers can clear in
  a 10-minute read-only probe (`SKILL.md:127,140,145`).
- **The pipeline has no divergent phase.** It is one convergent funnel: ledger, cluster, top 5,
  three levers each, check, score, one winner, one brief. The research says an LLM left to itself
  produces near-duplicate ideas (about 5% unique in Si et al. 2024) and that diversity must be
  forced with explicit prompting structure.

Top 3 proposals (details in section 4):

1. Add **pressure signals** to the inputs: the cost of diagnosing and fixing per area, product
   KPIs and workarounds (switches turned off, manual ops fixes), and dispersion (how many call
   sites do the same job). These are the inputs behind cells and moments.
2. Add a **cross-cluster synthesis step and a divergent lens pass**: find the absence shared by
   several causal chains (no owner, no single decision point, no boundary), then generate candidates
   under forced lenses (new concept, new boundary, new runtime, borrowed pattern, delete), with
   verbalized sampling to keep the unlikely ones.
3. **Two winners, two evidence bars**: the quick win as today, and one structural bet with its own
   brief, judged on a replay over past incidents instead of a 10-minute probe.

## 1. The three initiatives: trigger, inputs, and where elevate stops

### 1.1 PDF rendering in a Lambda (P-ENA-990)

**Trigger.** The host's API renders PDFs in-process, which blocks the Node event loop of the
servers that answer users. The project spec ties this to most recurring SLO alerts over 5 s in the
team's SLO channel, and counts slow executions per GraphQL operation over 30 days (the free-invoicing
migration and billing-document creation lead, with up to 45 PDFs in one trace). It lists the
technical consequences: head-of-line blocking, transactions held open while rendering, retries that
render again, Bull stalled jobs, health-check kills. Sources: P-ENA-990 description and its spec
document (created 2026-10-02 by a developer of the platform team); `docs/api-aws-lambda.md` shows a
PDF Lambda already existed once, deployed by hand.

**Inputs an idea generator needed.** APM traces and SLO alerts (production symptoms), code reading
(where `renderToStream` runs), and knowledge of an off-the-shelf runtime (SQS, SNS, Lambda). All of
these are in elevate's inputs.

**Reachable by elevate?** Yes, and that is circular:

- On 2026-11-11 the user asked for an elevate that would be "creative like" P-ENA-990 (local
  transcript `af26dce6`, 16:00). The rewrite `7e0ff1f` followed the same day. Its brief template
  was taken from the structure of P-ENA-990 (same transcript, 16:22: "tiré de la structure de
  P-ENA-990"; compare `references/brief.md:13-31` with the project description: Why, What changes,
  a mermaid flow, one slice behind a switch, shadow mode, Done when, tracking).
- `references/levers.md:19` gives as the `Offload` example "PDF rendering moved to a dedicated
  function behind a queue". The answer is in the prompt.
- Run of 2026-11-11 (transcript `cb34e3ba`): cluster 5 traced PDF rendering inside the GraphQL
  process and proposed moving invoice rendering to a worker. It ranked **#9**, because a guard
  with Effort S or M beats an Effort L lever under `SKILL.md:142`, and because the platform team's
  projects already existed. The session itself concluded the skill would probably not recommend it
  first (`af26dce6`, 19:46).
- Run of 2026-11-12 (transcript `6e2e4a07`): "API slowness: PDFs rendered during the request" was
  one of the five traced causes, then removed as covered by current work (`SKILL.md:104-106`).

**Where it stops:** ranking (`SKILL.md:142`, one winner at `:149`) and the current-work filter.
No clean replay exists: elevate has no `--until`, and Datadog logs on the host are kept 16 days
(correction the 11-11 run wrote into the host's `signals.md`, per `af26dce6` 19:37).

### 1.2 "Moments" for outgoing messages (P-SEC2-1178, SEC2-837, SEC2-845)

**Trigger.** A product pod (POD-037) owns one KPI: the share of deals with emails switched off.
Each caller builds and sends its own mail, and the only control is a per-deal switch, so teams mute
everything (P-SEC2-1178). The decision record SEC2-837 (2026-11-06) adds a production inventory
over six weeks: templates that can be blocked without a log row, templates with no switch at all,
a cart cancellation that sends the same mail twice for about half the quotes, a deposit reminder
with no cap (hundreds of sends for about a hundred bookings). It adds a code audit: 63 files render
a mail, about 25 call the send API directly, and the deal mails follow 111 sending rules spread
over the code. The decision: a caller announces a **moment** with a **fiche** (facts, people, no
channel or template), and one new cell decides, journals and routes (SEC2-845). First commits on
the host: `62ae76b7a416` (2026-11-09) through `744d6f600312` (2026-11-13).

**Inputs an idea generator needed.**

- A product KPI and a workaround signal (deals muted wholesale), read in the database, not in any
  bug channel.
- A dispersion count over the code (how many places make the same decision).
- Several small symptoms (duplicates, uncapped reminders, silent suppression) seen as one absence:
  no single place decides whether a message goes out.
- A new domain concept: the caller states what happened, not what to send.

**Reachable by elevate?** No. Stage by stage:

| Stage | What filters it out |
|---|---|
| Inputs (`SKILL.md:15,31-36`; `ledger.md:12-13,33-35`) | A symptom is "something a user or the team saw go wrong". The Slack search words are failure words (slow, timeout, duplicate, again). The muted-deal share and the dispersion count are neither. |
| Cluster (`SKILL.md:54-56`) | Duplicates, uncapped reminders and silent mutes come from different templates and screens; grouped by "the work behind them", they form several small clusters or isolated bugs, never ranked. |
| Trace (`SKILL.md:68-73`) | The five questions are about one runtime path: missing rule, shared resource, timing, retry, count. None asks "how many places make this decision?". |
| Levers (`SKILL.md:82-85`, `levers.md:7-22`) | Each lever breaks one link of one cluster's chain. The closest family is Simplify / "Remove a layer: merge two paths into one" (`levers.md:13`); there is no family for introducing a domain concept or a single decision point. |
| Scope (`SKILL.md:169`; innovate `SKILL.md:30`) | elevate sends product capabilities to `innovate`, and innovate sends refactors back to elevate. An initiative that is both (a KPI, an ops-editable rules engine, and a new cell) falls between them. |
| Evidence (`SKILL.md:137,140`) | Its impact is structural until built (one entry point instead of 63), which caps Confidence at Low. |

What the 2026-11-13 run did with the email area (transcript `42bf62d5`): it found that a bounced
address is blacklisted forever and later mails to it are silently dropped, and proposed reading the
blacklist at send time and showing it on the contact. A correct, local lever; the POD-037 project
had started a week earlier.

### 1.3 Hexagonal architecture with cells (ADR 028/031/033/044, I-41, DXAI-330)

**Trigger, in three layers.**

1. **Design ambition, June 2026.** The first commits are building blocks for hexagonal modules and
   a test setup (`e72f958509d0`, `49d2855f48ef`, 2026-06-05) and a pilot that migrates one
   sub-domain with a strangler fig (host PR #13651, opened 2026-06-09). ADR 028's first text
   (`2baa5f68ab85`, 2026-07-17, FIN-781) gives the reasons: tightly coupled layers, hard isolated
   testing, slow onboarding for about 50 engineers, no way to extract a bounded context, and a
   rollout "guided by rules, skills, and tooling". No production symptom is cited.
2. **Incident that confirmed it, August 2026.** The leadership note under initiative I-41 says a
   production incident on user fees took three days to fix with confidence; the fix was small, the
   diagnosis was slow, because nobody could tell bad input from the booking flow from a bad
   calculation in the money code. A queue of known fixes was slow for the same reason. The plan:
   seal each financial module behind one entry point, rebuild the price primitive, extract the
   money code as its own deployable later, and split the team in two along the same line.
3. **Borrowed canon, September 2026.** The word *cell* and its rules (one cell = one bounded
   context = one hexagon with its exclusive data; consumer SPI plus in-process adapter as the only
   edge; chatty-cell merge tests) come from an external cell-based architecture canon and public
   reference repos, studied for a greenfield service (DXAI-330, its child decisions), then adapted
   to the brownfield API (DXAI-409, DXAI-432; ADR 028 amendment `2b70a379debf`, 2026-09-11).

**Inputs an idea generator needed.** Time-to-diagnose and fix lead time for one class of bugs (a
meta-symptom about the team, not about users); the share of bugs in one domain (the 11-12 run
counted 361 of 939 bugs in the money team, per retro transcript `dfdaf203`); onboarding and
testability pain; an org change; and an external pattern with a name.

**Reachable by elevate?** No:

- **Inputs.** Diagnosis time, reopened-after-fix, fix lead time are not ledger fields
  (`ledger.md:9`: Symptom, Where, Source, First seen, Last seen, Count, Links).
- **Cluster.** "Symptoms that share one cause in the code" (`SKILL.md:17`) groups amounts-wrong
  bugs by the calculation that failed. The common cause, entanglement of two domains, is not "one
  cause in the code" a cluster can name.
- **Trace.** "X runs in Y, so Z" (`SKILL.md:18`) is a runtime sentence. Entanglement is a
  dependency-structure sentence.
- **Levers.** No "draw a boundary / give one owner / seal behind one port" lever exists. Remodel the
  data (`levers.md:14`) and Share the contract (`levers.md:11`) are the closest, both local.
- **Out of scope.** "Rewrites (... move to microservices) only when a recurring cluster's causal
  chain demands it" (`SKILL.md:170-171`), and code cleanup goes to `simplify` (`:168`).
- **Proactive lane.** The only place architecture patterns survive, capped at Confidence Med
  (`SKILL.md:89-91`), then sunk by the structural-proxy rule (`:137`): the benefit of a boundary is
  structural until the next incident.
- **ADRs.** A lever that contradicts an ADR sinks (`SKILL.md:101-103`). At the time, ADRs 008/009
  described the existing pattern; a paradigm change would have been ADR-blocked.

## 2. Structural causes in the skill text, checked one by one

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Symptom-only inputs bias toward local, reactive fixes | **Confirmed** | The question is "remove the most pain, starting from what actually hurts" (`SKILL.md:9-10`). Ledger rows are failures in the reporter's words, "never a guessed cause" (`ledger.md:12-13`). The signals contract is "what users and the team saw go wrong in production" (setup-ai-skills `references/signals.md:3-6`). Product KPIs, workaround counts, diagnosis time and strategy docs have no slot. Step 1 reads CLAUDE.md, README and config (`SKILL.md:24`), not the glossary, product doc or architecture doc the host keeps. |
| Lever families exclude new abstractions, domain-model changes, platform moves, borrowed patterns | **Mostly confirmed** | Platform moves exist (Change where: Offload, Isolate, Buy, `levers.md:19-22`). New domain concepts, boundaries and ownership, and named external patterns do not. Families are ordered "from the cheapest" and "the lightest lever ... is usually a Guard or a Harden" (`levers.md:3,24`). |
| Levers are bound to one cluster's chain | **Confirmed** (not in the original list) | "For each traced cluster, write at least three levers ... Each lever names the link of the causal chain it breaks" (`SKILL.md:82-85`). Nothing looks across chains, so a change that would break five small chains at once is never written. Only five clusters are traced (`:63-65`); isolated bugs are never ranked (`:56`). |
| Ranking favours evidence-certain small levers | **Confirmed** | "Favor high Impact, low Effort, low Risk, high Confidence" (`:142`). Probes must run in under 10 minutes (`:127`); an unverified probe behind L/XL Impact forces Low (`:140`); a structural proxy caps at Low (`:137`); proactive caps at Med (`:91`). A structural bet cannot clear this bar. The 11-11 run ranked the Lambda lever #9 for exactly this reason (`af26dce6` 19:46). |
| Convergence to one brief | **Confirmed** | "Pick one winner" (`:149`), "For the winner, write a project brief" (`:157`). A two-winner design (quick win plus structural bet) was proposed in session `af26dce6` and never applied. |
| No divergent phase | **Confirmed** | Every step from 3 to 8 narrows. "At least three levers from at least two families" (`:82-83`) is the only breadth rule, and it is per cluster and drawn from a fixed catalogue. |
| The skill moved away from architecture over time | **Confirmed** | The first version (`fcf3da1`, 2026-04-18) asked for the "single highest-leverage architectural, framework, tooling, or DX change", with "architecture patterns: layering, module boundaries, data flow, state shape" as a dimension. The rewrite `7e0ff1f` made symptoms the entry and kept the four dimensions only as the capped proactive lane. Each later fix (`d9405c8`, `f283982`) added evidence gates: count the failing link, run the kill-switches. Right for accuracy (the 11-12 run's winner was refuted by a 12-minute check, retro `dfdaf203`), and each one pushes further toward small, provable levers. |
| In-context examples anchor the output | **Plausible, not verified** | The catalogue's examples are concrete (`levers.md:9-22`), and the Offload example is the host's own project. No run was tested with the examples removed. |

One more observation: all three initiatives were designed by people over days or weeks, through
chains of design questions answered one by one (the "grill" tickets under FIN-772, DXAI-330,
SEC2-837 alternatives). elevate is one pass. It can at most propose the direction; the program is
human work. A realistic target is "elevate names the direction and the evidence that justifies a
design session", not "elevate writes ADR 028".

## 3. What the research says, kept to what bears on the design

- **LLM ideas are novel but repetitive, and LLM judges are weak.** In a study with over 100 NLP
  researchers, LLM ideas were judged more novel than expert ideas (p < 0.05) and slightly less
  feasible. Generating 4,000 seed ideas per topic gave only about 200 non-duplicates (cosine > 0.8),
  and the best LLM ranker agreed with human rankings at 53.3% against 56.1% between humans
  (Si, Yang, Hashimoto 2024, §7.1-7.2, https://arxiv.org/abs/2409.04109). For elevate: asking for
  "three levers" from one context samples the same mode; breadth needs forced variation, and the
  model should not be the only judge of novelty.
- **Novelty does not survive execution well.** When experts executed the ideas, LLM ideas lost
  significantly more score than human ideas on every metric (Si, Hashimoto, Yang 2025,
  https://arxiv.org/abs/2506.20803). For elevate: keep the evidence gates for the convergent half;
  do not trade them away for creativity. Diverge first, then judge on evidence.
- **Mode collapse comes from post-training, and prompting can undo part of it.** RLHF reduces output
  diversity compared to SFT (Kirk et al. 2023, https://arxiv.org/abs/2310.06452). Preference data
  favours familiar text; asking the model to verbalize a distribution of candidates with
  probabilities restores diversity, more so for stronger models (Zhang et al. 2025, Verbalized
  Sampling, https://arxiv.org/abs/2510.01171). For elevate: ask for N candidates with an estimated
  probability that a typical engineer would propose each, and keep the low-probability ones in play.
- **Prompt structure moves idea diversity.** GPT-4 idea pools are less diverse than human groups,
  and chain-of-thought prompting (generate many distinct ideas step by step) came closest to the
  human level and produced the most unique ideas (Meincke, Mollick, Terwiesch 2024,
  https://arxiv.org/abs/2402.01727).
- **Analogy is a lever.** Having the model first recall relevant problems from other domains and
  their solutions, then solve, beats zero-shot and few-shot chain of thought on reasoning and code
  (Yasunaga et al. 2023, Analogical Prompting, https://arxiv.org/abs/2310.01714). For elevate: a
  "borrowed pattern" lens that names where a problem of this shape was solved elsewhere is how
  "hexagonal / cell-based" enters the candidate set.
- **Retrieve inspirations, then push past them.** SciMON retrieves inspirations from prior work and
  iteratively revises ideas against the literature until they are novel enough; GPT-4 alone gives
  low depth and novelty (Wang et al., ACL 2024, https://arxiv.org/abs/2305.14259).
- **Divergent then convergent, with distinct roles.** Divergent-convergent prompting improves LLM
  creative problem solving (Tian et al. 2023, MacGyver, https://arxiv.org/abs/2311.09682). A
  three-phase discussion with role-played agents beats single-LLM and other multi-agent baselines on
  creativity tests (Lu et al., COLM 2024, https://arxiv.org/abs/2405.06373). Keeping an archive of
  diverse high-quality candidates across defined niches covers more of the space than optimizing a
  single score (Bradley et al. 2023, QDAIF, https://arxiv.org/abs/2310.13032).
- **Homogenization.** People who ideate with ChatGPT produce ideas more similar to each other's
  (Anderson, Shah, Kreminski 2024, https://arxiv.org/abs/2402.01536). Repeated elevate runs on the
  same repo will tend to repeat themselves unless the lenses change.

## 4. Proposals, ranked

Ranked by how many of the three initiatives they make reachable, then by cost. `innovate` was
checked first: it ranks product additions and routes refactors back to elevate (innovate
`SKILL.md:30`), so the gap below is elevate's, except proposal 6.

| # | Change | Lambda | Moments | Cells | Cost |
|---|---|---|---|---|---|
| 1 | Pressure signals in the inputs | – | **needed** | **needed** | M |
| 2 | Cross-cluster synthesis + divergent lens pass | helps | **needed** | **needed** | M |
| 3 | Two winners, two evidence bars | **needed** | needed | needed | S |
| 4 | Three new lever families | – | needed | needed | S |
| 5 | Replay mode as the acceptance test | **needed** | needed | needed | M |
| 6 | Shared handoff with innovate for hybrid initiatives | – | helps | – | S |
| 7 | ADR as "revisit", not "sink" | – | – | helps | S |

**1. Pressure signals.** Add an optional `pressure` section to the signals contract and a step-2
subagent for it. Rows keep the ledger shape but count cost, not failure:

- *Diagnosis and fix cost per area*: median time from bug opened to fix merged, reopened bugs, bugs
  whose fix touched another team's code, from the tracker and git (cells: the slow attribution of
  money bugs).
- *Workarounds and switches*: features turned off, settings muted wholesale, manual data fixes and
  migrations run by hand, read from the database or the tracker (moments: deals muted; the 11-12
  run already counted 47 hand-run repair migrations, transcript `6e2e4a07`).
- *Dispersion*: how many call sites make the same decision or call the same low-level API (moments:
  63 renderers, about 25 direct senders), from a code scan.
- *Strategy context*: active initiatives, product KPIs, draft ADRs, the architecture and product
  docs, read once in step 1 so levers can align with or challenge them.

**2. Cross-cluster synthesis and a divergent lens pass**, between steps 4 and 5:

- *Synthesis*: lay the traced chains side by side and name any absence two or more share (no single
  owner, no single decision point, no boundary between two domains, the same primitive modelled N
  ways). Each shared absence becomes a "meta-cluster" whose Impact is the union of its clusters.
- *Lenses*: for each meta-cluster and the top clusters, one subagent per lens, run in parallel, each
  returning 3-5 candidates with the estimated probability that a typical team would propose it
  (verbalized sampling): **name the concept** (what event or object is missing from the language?),
  **draw the boundary** (who should own this, behind which port?), **change the runtime** (where
  should this run?), **borrow a pattern** (where was a problem of this shape solved, under what
  name? cite the source), **delete** (what if this feature or path did not exist?). Keep at least
  one candidate under 20% probability per lens into step 6. A separate subagent, given the code and
  ledger but not the candidates' rationale, judges duplicates (Si et al.: LLMs judge their own ideas
  poorly).

**3. Two winners, two evidence bars.** Step 7 names a **quick win** (today's rule) and a
**structural bet**: the best candidate from a meta-cluster or from Change when / Change where / the
new families. The structural bet gets its own brief and its own test: a replay over the window's
incidents ("of the N money bugs in 90 days, how many would the new boundary have attributed at
once?") or a time-boxed spike, written as a feasibility probe with a longer budget the user
approves. The structural-proxy cap (`SKILL.md:137`) stays for the quick win and is lifted for a
structural bet whose Impact is counted across clusters.

**4. Three new lever families** in `levers.md`: *Name the concept* (a domain event or value object
the code lacks: a moment, a money primitive), *Draw a boundary* (a module, cell or bounded context
with one owner and one port; strangler migration), *Borrow a pattern* (a named external pattern with
its source and the reason it fits). Give each family two or three examples from different domains,
and replace the host's own project as the Offload example, so the catalogue does not hand back the
host's past answers.

**5. Replay mode as the acceptance test.** Add `--until <date>`: every source is read up to that
date, and step 6's current-work and shipped checks ignore anything created after it. Datadog logs
expire after 16 days on the host, so replays rely on monitors, `trace.*` metrics, Slack, the
tracker and git. Acceptance:

| Replay | Window end | Pass if |
|---|---|---|
| Lambda | 2026-10-01 | PDF rendering off the API servers is the structural bet, or in the top 3 |
| Moments | 2026-11-02 | "one decision point for outgoing messages, callers state what happened" appears as a candidate with its dispersion count |
| Cells | 2026-06-04 for the pilot, 2026-08-09 for the incident-backed version | "seal the money code behind one port, apart from the booking flow" appears, naming hexagonal / ports and adapters as the borrowed pattern |
| Counter-example | any | a recurring bug family whose right answer is a guard still gets a guard as its quick win |

Plausibility, given the inputs available before each start:

- **Lambda**: high with 3 and 5 alone; the chain was already found twice.
- **Moments**: plausible with 1 and 2. The KPI pod existed before the project; the duplicate mails,
  the uncapped reminder and the silent suppression are in the email send log; the dispersion is a
  grep. The synthesis step joins them; the "name the concept" lens proposes "callers announce what
  happened". The word *moment* and the fiche contract are design work and would not come out.
- **Cells**: partly. With diagnosis-cost signals and the "borrow a pattern" lens, "isolate the
  money code behind ports" is a plausible candidate after the August incident. Before it (the June
  pilot) the trigger was a design ambition with no production signal; elevate would need the
  strategy-context input to see it. The cell canon, the org split and the extraction roadmap are
  leadership decisions it would not produce.

**6. Hybrid initiatives.** Let elevate keep a candidate that comes with a product KPI and mark it
`hybrid: innovate`, instead of dropping it under `SKILL.md:169`. Mirror the rule in innovate.

**7. ADRs.** A lever that contradicts an ADR stays ranked on its own merit and is tagged
"revisits ADR-NNN", with the evidence that the ADR's context changed, instead of sinking
(`SKILL.md:101-103`).

**Cost.** The 11-11 run took about 28 minutes and 75 USD with 13 subagents (`af26dce6` 19:01).
Proposals 1 and 2 add roughly one subagent per pressure source and per lens. To keep the default run
cheap, they can sit behind a flag (`elevate --diverge`) rather than in a separate skill: they reuse
the ledger, traces and checks, and a companion skill would have to rebuild them.

## 5. Not verified

- The June 2026 trigger for the hexagonal pilot beyond ADR 028's original context and PR #13651;
  the tracker issue behind the pilot (BAC-320) and any Slack discussion before it were not read.
- Who first proposed the moment/fiche model, and whether it came from an external pattern; only
  the decision record and project were read, not the linked design documents (claude.ai artifacts).
- Slack threads: a keyword search for "hexagonal" before July 2026 returned only unrelated
  messages; no other Slack source was read. All host evidence comes from git, ADRs, the tracker and
  local transcripts.
- Whether the in-context example anchors elevate's output (section 2, last row): no ablation run.
- Every proposal in section 4: none was run. The replay plausibility above is a judgement from the
  inputs listed, not a result.
- The literature effects were measured on research ideas, product ideas, creative writing and
  puzzles, not on software architecture proposals. Transfer to elevate is an inference.
- Doshi & Hauser (Science Advances 2024) on collective diversity could not be fetched (HTTP 403)
  and is not cited.

## 5. Baseline replays (2026-11-14)

The current skill plus `--until` (branch `feat-elevate-until`), each run in a fresh session on a
host worktree detached at the cutoff commit. No post-cutoff item showed in any output; the runs
dropped 151 to 963 later tracker issues each. Known residue: the host's signals doc is today's, and
tracker states are read as of today (judged from `updatedAt`).

| Replay | Cutoff | Winner | Pass? | Where the initiative was lost |
|---|---|---|---|---|
| Lambda | 2026-10-01 | Render PDFs off the event loop, with a worker-thread pool inside the API (Isolate) | Direction yes, form no | The Offload lever (a separate worker runtime) was generated, then marked ADR-blocked by an architecture doc that keeps a second worker process out, and sank (`SKILL.md` step 6, Rules). |
| Cells | 2026-08-09 | Idempotent, race-safe status changes (Harden) | No | It counted money rules re-derived in 31+ files and cancellation computed three times, and turned that into "compute cancellation once server-side" (one lever per cluster link). The closest lever, one fee module with one canonical rule, was removed by the current-work filter because the tracker already held it. |
| Moments | 2026-11-02 | One "booked" status list plus a contract test (Guard) | No | The email cluster (wrong language, not delivered, floods) was recurring across four sources, but not among the five clusters traced, so it was never ranked. |

Pattern: elevate reaches the right area, then a convergence rule reduces it to a local fix:
ADR-sink (Lambda), current-work removal (Cells), one-link-per-lever (Cells), five-cluster trace cap
(Moments). Proposals 2, 3 and 7 target exactly these rules; proposal 1 is not what blocked Moments
here, the trace cap was.

## 6. Replays after proposals 2, 3 and 7 (2026-11-14)

Same cutoffs and worktrees as §5, skill with the cross-cluster synthesis, the five lenses, two
winners and "revisits" instead of ADR-blocked.

| Replay | Structural bet | Pass? | What changed against §5 |
|---|---|---|---|
| Lambda (10-01) | A keyed, asynchronous document pipeline: the request records a run and returns; an idempotent worker on the background task renders, uploads and sends. Replay: about 280 to 340 of 1 941 rows prevented. | **Yes** (rendering leaves the API servers, as the bet) | The architecture doc that sank Offload is now tagged "revisits". Form differs from the real project: a worker task, not a function, though the run noticed a function already sends emails. |
| Cells (08-09) | A shared side-effect boundary (durable outbox, drained by a worker role). | **Partial** | A meta-cluster "no single place decides" joined money, emails and statuses with counts in the code. A money lever (freeze fees, commission, tax and currency at booking, one reader) ranked but was not the bet. No ports-and-adapters wording. |
| Moments (11-02) | One money position per party, owned by the financial-computation module. | **No** | The email cluster was grouped under "no shared deliver/retry primitive", not under "who decides to send". No decision-point lever for messages. |

Two notes:

- The August Cells replay produced the moments idea ("callers emit an intent, a gateway decides
  recipients, locale, toggles and idempotency", with 53 deciding files counted) three months before
  the project; the November replay, closer to the project, did not. One run per cutoff is not
  enough: the lens pass is sampled, and the meta-cluster a cluster lands in decides its levers.
- Both money-heavy replays now name a money-ownership meta-cluster and a money boundary lever; in
  November it became the structural bet. That is the direction of the cells work, reached without
  the borrowed vocabulary.
