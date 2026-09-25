export const meta = {
  name: 'gate-wf',
  description: 'Quality gate: parallel reviewers, tier-scaled adversarial verify, context annotation',
  phases: [
    { title: 'Review', detail: 'reviewers in parallel + CLAUDE.md/ADR synthesis' },
    { title: 'Verify', detail: 'skeptics per finding, scaled by tier (jev first pass with --jev)' },
    { title: 'Context', detail: 'annotate survivors against project context' },
  ],
}

// args: { tmpDir, reviewers: string[], prNumber: number|null, useJev?: boolean, jevScript?: string }
// useJev (the skill's --jev flag): Jev first-passes every finding through
// jev-verify's batch mode; only the escalate band (and any runner failure)
// falls back to tier-scaled sonnet skeptics. Off by default — the gate's shape
// is unchanged without it.
// args may arrive as an object or a JSON string depending on harness path; normalize.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
if (!Array.isArray(A.reviewers) || !A.reviewers.length) {
  throw new Error('gate-wf: expected args {tmpDir, reviewers:[...], prNumber} — got ' + JSON.stringify(args).slice(0, 200))
}
if (A.useJev && !A.jevScript) throw new Error('gate-wf: useJev needs args.jevScript (the JV path from Step 3e)')

const FINDING_PROPS = {
  rule_id: { type: 'string' },
  file: { type: 'string' },
  line: { type: 'number' },
  location: { type: 'string', enum: ['diff-line', 'adjacent'] },
  tier: { type: 'string', enum: ['BLOCKER', 'MAJOR', 'NIT'] },
  message: { type: 'string' },
  evidence: { type: 'string' },
  suggested_fix: { type: 'string' },
}
const FINDINGS_SCHEMA = {
  type: 'object', required: ['findings'],
  properties: { findings: { type: 'array', items: {
    type: 'object',
    required: ['rule_id', 'file', 'line', 'location', 'tier', 'message', 'evidence', 'suggested_fix'],
    properties: FINDING_PROPS,
  } } },
}
const SKEPTIC_SCHEMA = {
  type: 'object', required: ['refuted', 'reason'],
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
}
const CONTEXT_SCHEMA = {
  type: 'object', required: ['annotations', 'synthesized'],
  properties: {
    annotations: { type: 'array', items: {
      type: 'object', required: ['file', 'line', 'rule_id', 'verdict'],
      properties: {
        file: { type: 'string' }, line: { type: 'number' }, rule_id: { type: 'string' },
        verdict: { type: 'string', enum: ['OK', 'CONFLICT', 'UNCERTAIN', 'DISMISSED'] },
        source: { type: 'string' }, citation: { type: 'string' }, reason: { type: 'string' },
        dismiss_confidence: { type: 'string' },
      },
    } },
    synthesized: { type: 'array', items: {
      type: 'object',
      // Same required set as reviewer findings: synthesized findings now flow through the same
      // dedup + verify path, and skepticPrompt reads location/evidence/suggested_fix directly.
      required: ['rule_id', 'file', 'line', 'location', 'tier', 'message', 'evidence', 'suggested_fix', 'citation', 'source'],
      properties: { ...FINDING_PROPS, citation: { type: 'string' }, source: { type: 'string' } },
    } },
  },
}

// Each reviewer reads only the slice of the diff it can act on — docs/snapshots/lockfiles
// stripped for the code reviewers, tsx/jsx-only for the JSX reviewers. Keeps irrelevant
// files out of the agent's context. Scoped diff files are generated in SKILL.md Step 2a.
const TSX_REVIEWERS = new Set([
  'ai-skills:react-reviewer', 'ai-skills:a11y-reviewer', 'ai-skills:i18n-reviewer',
])
const diffBase = (reviewer) => (TSX_REVIEWERS.has(reviewer) ? 'diff-tsx' : 'diff-code')

const reviewPrompt = (reviewer) => `Review this branch's diff. You are ${reviewer}.

Artifacts (scoped to your concern — files outside it are intentionally omitted as noise):
- Diff: ${A.tmpDir}/${diffBase(reviewer)}.txt
- Plus-lines (+ lines per file): ${A.tmpDir}/${diffBase(reviewer)}-plus.txt
- Context bundle (CLAUDE.md + ADRs + Linear + PR + sessions): ${A.tmpDir}/context-bundle.md

Read whatever else you need — full versions of changed files, imported modules, schemas, callers — to reason. The diff scopes WHERE a finding is anchored, NOT what you may read. A defect whose trigger is on a + line but whose evidence lives in a non-diff file IS in scope: anchor it to the diff line, cite the external file in evidence.

Constraints:
- Boy Scout asymmetry: adjacent (non-+, legacy) code may be flagged MAJOR/NIT but never BLOCKER.
- Read-scope ≠ finding-scope: read any file to reason; only REPORT findings anchored to changed lines.
- Read-only. No edits, no shell mutations.

Return { findings: [...] }. Empty is valid — most diffs have few or none.`

const skepticPrompt = (f, i) => `You are an adversarial skeptic (independent instance ${i + 1}). A ${f.reviewer} flagged this finding${A.prNumber ? ` on PR #${A.prNumber}` : ''}. Try hard to REFUTE it. Default to refuted=true when uncertain — refuted=false ONLY if it is clearly a real defect after investigation.

FINDING:
- rule_id: ${f.rule_id}
- file: ${f.file}  line: ${f.line}  (location: ${f.location})
- tier: ${f.tier}
- message: ${f.message}
- evidence: ${f.evidence}
- suggested_fix: ${f.suggested_fix}
${f.citation ? `- citation (documented project rule — ${f.source}): ${f.citation}\n` : ''}
Read the cited region (±40 lines) and every other file the finding cites. Budget ≤6 tool calls. Return { refuted, reason }.`

const synthesizePrompt = () => `MODE: synthesize

Read:
- Diff: ${A.tmpDir}/diff-full.txt
- Context bundle: ${A.tmpDir}/context-bundle.md

Walk the diff against the bundle's ## CLAUDE.md and ## ADR sections. Emit synthesized findings for documented-rule violations (claude-md-violation / adr-violation) per your instructions. There are no input findings yet — do NOT annotate. Return { annotations: [], synthesized: [...] }.`

const annotatePrompt = (survivors) => `MODE: annotate

Context bundle: ${A.tmpDir}/context-bundle.md

Annotate each of these ${survivors.length} surviving findings with a verdict (OK/CONFLICT/UNCERTAIN/DISMISSED) per your instructions. Do NOT synthesize new findings (synthesis already ran). Return { annotations: [...], synthesized: [] }.

FINDINGS:
${JSON.stringify(survivors.map((f) => ({ file: f.file, line: f.line, rule_id: f.rule_id, tier: f.tier, message: f.message, evidence: f.evidence })), null, 1)}`

// --- orchestration ---

// Start CLAUDE.md/ADR synthesis in parallel with the reviewers — it needs no findings.
const synthP = agent(synthesizePrompt(), {
  agentType: 'ai-skills:context-checker', phase: 'Review', label: 'synthesize', schema: CONTEXT_SCHEMA,
})

// Shared dedup map: first reviewer to claim a (file:line) owns it; later duplicates
// merge in as also_flagged_by without spawning their own skeptics.
// ponytail: order-dependent — the primary is whichever verifyStage runs first, not by tier.
// The duplicate still surfaces via the primary; acceptable. Upgrade path: collect all,
// pick highest-tier primary, if false-positive rate on merged dupes bites.
const claimed = new Map()

// --- --jev: Jev first pass over the findings ---------------------------------
//
// The workflow sandbox has no network, so python does the HTTP and a haiku
// runner agent just relays its stdout — the agent's only job is to run
// jev_verify.py batch and echo the JSON. Python decides; the agent never
// judges. The lesson from v9 (a model retyping 18 findings cut identifiers
// mid-word) applies: the runner returns python's bytes with a msg_len
// integrity check per row, and anything that does not line up — wrong length,
// missing row, malformed JSON, api down — routes to a sonnet skeptic. The jev
// path can only add skeptics, never silently lose a finding.
const JEV_BATCH_SCHEMA = {
  type: 'object',
  properties: {
    error: { type: 'boolean' },
    stderr: { type: 'string' },
    rows: { type: 'array', items: { type: 'object', properties: {
      file: { type: 'string' }, line: { type: 'number' }, rule_id: { type: 'string' },
      decision: { type: 'string', enum: ['keep', 'kill', 'escalate'] },
      defect_real: { type: 'number' }, msg_len: { type: 'number' },
      needs_wider_context: { type: 'number' },
    } } },
    usage: { type: 'object', properties: { input_tokens: { type: 'number' }, requests: { type: 'number' } } },
  },
}

// The findings the batch needs, stripped to the keys jev_verify reads.
const jevFinding = (f) => ({
  file: f.file, line: f.line, rule_id: f.rule_id, tier: f.tier,
  message: f.message, evidence: f.evidence, suggested_fix: f.suggested_fix,
  citation: f.citation, source: f.source,
})

// The sandbox has no filesystem, so the batch rides in the prompt as JSON and
// the runner writes it to tmpDir before executing. The filename carries the
// stage tag: reviewer stages run concurrently in the pipeline and would
// otherwise all write the same path and race. Chunks are capped so the haiku
// prompt stays small; ~60 findings ≈ 6-10k tokens of payload.
const jevRunnerPrompt = (payload, repo, tag) => `Write this JSON array to ${A.tmpDir}/jev-batch-${tag}.json (exact bytes, no edits):

${JSON.stringify(payload)}

Then run and return its stdout verbatim:

python3 ${A.jevScript} batch --repo ${repo} < ${A.tmpDir}/jev-batch-${tag}.json

If the command exits non-zero or prints nothing, return {"error": true, "stderr": "<first 200 chars of stderr>"}.
Print the JSON in one message, no commentary — the caller validates it. Do not modify the findings, do not retry, do not summarize.`

// Slice findings to ~60 per batch: one runner call per chunk keeps a single
// failure bounded and the haiku context small.
const jevVerify = async (findings, tag) => {
  // Repo root for git-blob reads when the worktree has moved past the finding.
  // agent() yields null on user-skip; an empty repo degrades every row to
  // 'unreadable' -> escalate -> sonnet skeptics, which is the designed fallback.
  const repo = ((await agent(
    'Run: git rev-parse --show-toplevel — return its stdout trimmed, nothing else.',
    { phase: 'Verify', label: 'jev:repo', agentType: 'ai-skills:jev-runner' },
  )) || '').trim()
  const out = {}
  const chunks = []
  for (let i = 0; i < findings.length; i += 60) chunks.push(findings.slice(i, i + 60))
  const results = await parallel(chunks.map((chunk, ci) => () =>
    agent(jevRunnerPrompt(chunk, repo, `${tag}-${ci}`), {
      phase: 'Verify', label: `jev:batch-${ci}`, schema: JEV_BATCH_SCHEMA,
      agentType: 'ai-skills:jev-runner',
    })
  ))
  results.forEach((r, ci) => {
    if (!r || r.error || !Array.isArray(r.rows)) return // chunk lost -> its findings escalate
    r.rows.forEach((row) => {
      const key = `${row.file}:${row.line}:${row.rule_id}`
      out[key] = row
    })
  })
  return out
}

// Route one finding: jev says keep/kill, else (or on any doubt) the sonnet path.
const jevRoute = (f, jevRows) => {
  if (!jevRows) return 'sonnet'
  const row = jevRows[`${f.file}:${f.line}:${f.rule_id}`]
  // Integrity (v9 lesson): wrong message length or a missing row means the
  // relay was cut — trust nothing about it, ask a skeptic. (JS .length counts
  // UTF-16 units, python len() counts code points, so a message with non-BMP
  // characters trips this and costs one extra skeptic. Safe direction.)
  if (!row || row.msg_len !== (f.message || '').length || !row.decision) return 'sonnet'
  if (row.decision === 'keep') return 'kept'
  if (row.decision === 'kill') return 'killed'
  return 'sonnet' // escalate band: exactly what skeptics are for
}

const tierVotes = (tier) => (tier === 'BLOCKER' ? 3 : tier === 'MAJOR' ? 1 : 0)

const verifyOne = (jevRows) => async (f) => {
  if (A.useJev && tierVotes(f.tier) > 0) {
    const route = jevRoute(f, jevRows)
    if (route === 'kept') { f.verifications = [{ refuted: false, reason: 'jev first pass: defect_real=' + (jevRows[`${f.file}:${f.line}:${f.rule_id}`].defect_real ?? '?') }] ; return f }
    if (route === 'killed') { f.verifications = [{ refuted: true, reason: 'jev first pass: defect_real=' + (jevRows[`${f.file}:${f.line}:${f.rule_id}`].defect_real ?? '?') }] ; return null }
    // 'sonnet': escalate band or relay failure — fall through to skeptics below
  }
  const votes = tierVotes(f.tier)
  if (votes === 0) { f.verifications = []; return f } // NIT: shown, not verified
  const skeptics = (await parallel(
    Array.from({ length: votes }, (_, i) => () =>
      agent(skepticPrompt(f, i), {
        agentType: 'ai-skills:skeptic', phase: 'Verify', label: `verify:${f.rule_id}`, schema: SKEPTIC_SCHEMA,
      })),
  )).filter(Boolean)
  f.verifications = skeptics
  const refuted = skeptics.filter((v) => v.refuted).length
  const threshold = votes === 3 ? 2 : 1 // BLOCKER: ≥2/3 kill; MAJOR: the single vote kills
  return refuted >= threshold ? null : f
}

const reviewStage = (reviewer) =>
  agent(reviewPrompt(reviewer), {
    agentType: reviewer, phase: 'Review', label: reviewer.replace('ai-skills:', ''), schema: FINDINGS_SCHEMA,
  })

const verifyStage = async (review, reviewer) => {
  let jevRows = null
  if (A.useJev) {
    const cands = (review?.findings || []).filter((f) => tierVotes(f.tier) > 0 && (f.message || '').length)
    if (cands.length) jevRows = await jevVerify(cands.map(jevFinding), String(reviewer).replace(/[^a-z0-9]+/gi, '-'))
  }
  const toVerify = []
  for (const f of review?.findings || []) {
    const key = `${f.file}:${f.line}`
    if (claimed.has(key)) {
      const primary = claimed.get(key)
      ;(primary.also_flagged_by = primary.also_flagged_by || []).push({ reviewer, rule_id: f.rule_id })
      // A cited rule outranks a reviewer's judgment on the same line. Without this, a NIT that
      // claimed the line first silently swallows an adr-violation BLOCKER.
      // ponytail: the promoted finding keeps the votes it earned at its old tier, so a promoted
      // BLOCKER renders [refute votes: K/1]. Honest, and cheaper than re-verifying.
      if (f.citation && tierVotes(f.tier) > tierVotes(primary.tier)) {
        primary.tier = f.tier; primary.citation = f.citation; primary.source = f.source
      }
      continue
    }
    f.reviewer = reviewer.replace('ai-skills:', '')
    claimed.set(key, f)
    toVerify.push(f)
  }
  return (await parallel(toVerify.map((f) => () => verifyOne(jevRows)(f)))).filter(Boolean)
}

log(`Reviewing with ${A.reviewers.length} reviewers`)
const streamed = await pipeline(A.reviewers, reviewStage, verifyStage)

// Synthesized rule findings join the same dedup + verify path as reviewer findings. Skipping
// verify made a cited-rule BLOCKER the only unrefutable finding in the gate, double-counted any
// line a reviewer already owned, and rendered [refute votes: 0/0]. agents/skeptic.md tells the
// skeptic a citation-backed finding is refutable only three ways, so the refute bias can't eat
// them. Synthesis still runs parallel to the reviewers — only its verify round is serial.
const synth = await synthP
const synthSurvivors = await verifyStage(
  { findings: synth?.synthesized || [] },
  'ai-skills:context-checker',
)

const survivors = [...streamed.filter(Boolean).flat(), ...synthSurvivors]
log(`${survivors.length} findings survived verify; annotating against context`)

// Annotate everything, synthesized included — that is what lets a PR-thread rejection dismiss a
// rule violation instead of forcing the author to reach for --dismiss. Annotate is (file,line,
// rule_id) matching, not investigation, so it runs on sonnet regardless of the agent's default.
const annotated = survivors.length
  ? await agent(annotatePrompt(survivors), {
      agentType: 'ai-skills:context-checker', phase: 'Context', label: 'annotate',
      schema: CONTEXT_SCHEMA, model: 'sonnet',
    })
  : { annotations: [], synthesized: [] }

// Merge annotations onto findings by (file, line, rule_id).
const annByKey = new Map((annotated?.annotations || []).map((a) => [`${a.file}:${a.line}:${a.rule_id}`, a]))
for (const f of survivors) {
  const a = annByKey.get(`${f.file}:${f.line}:${f.rule_id}`)
  if (!a) continue
  f.context_verdict = a.verdict
  f.context_source = a.source
  f.context_citation = a.citation
  f.context_reason = a.reason
  if (a.dismiss_confidence) f.dismiss_confidence = a.dismiss_confidence
}

return { findings: survivors }
