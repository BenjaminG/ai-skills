export const meta = {
  name: 'gate-wf',
  description: 'Quality gate: parallel reviewers, tier-scaled adversarial verify, context annotation',
  phases: [
    { title: 'Review', detail: 'reviewers in parallel + CLAUDE.md/ADR synthesis' },
    { title: 'Verify', detail: 'skeptics per finding, scaled by tier' },
    { title: 'Context', detail: 'annotate survivors against project context' },
  ],
}

// args: { tmpDir, reviewers: string[], prNumber: number|null }
// args may arrive as an object or a JSON string depending on harness path; normalize.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
if (!Array.isArray(A.reviewers) || !A.reviewers.length) {
  throw new Error('gate-wf: expected args {tmpDir, reviewers:[...], prNumber} — got ' + JSON.stringify(args).slice(0, 200))
}

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
      type: 'object', required: ['rule_id', 'file', 'line', 'tier', 'message'],
      properties: { ...FINDING_PROPS, citation: { type: 'string' }, source: { type: 'string' } },
    } },
  },
}

const reviewPrompt = (reviewer) => `Review this branch's diff. You are ${reviewer}.

Artifacts:
- Diff: ${A.tmpDir}/diff-full.txt
- Plus-lines (+ lines per file): ${A.tmpDir}/plus-lines.txt
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
${JSON.stringify(survivors.map((f) => ({ file: f.file, line: f.line, rule_id: f.rule_id, tier: f.tier, message: f.message })), null, 1)}`

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

const tierVotes = (tier) => (tier === 'BLOCKER' ? 3 : tier === 'MAJOR' ? 1 : 0)

const verifyOne = async (f) => {
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
  const toVerify = []
  for (const f of review?.findings || []) {
    const key = `${f.file}:${f.line}`
    if (claimed.has(key)) {
      const primary = claimed.get(key)
      ;(primary.also_flagged_by = primary.also_flagged_by || []).push({ reviewer, rule_id: f.rule_id })
      continue
    }
    f.reviewer = reviewer.replace('ai-skills:', '')
    claimed.set(key, f)
    toVerify.push(f)
  }
  return (await parallel(toVerify.map((f) => () => verifyOne(f)))).filter(Boolean)
}

log(`Reviewing with ${A.reviewers.length} reviewers`)
const streamed = await pipeline(A.reviewers, reviewStage, verifyStage)
const survivors = streamed.filter(Boolean).flat()
log(`${survivors.length} findings survived verify; annotating against context`)

// Annotate survivors (single call). Synthesis result is already in flight.
const [annotated, synth] = await Promise.all([
  survivors.length
    ? agent(annotatePrompt(survivors), {
        agentType: 'ai-skills:context-checker', phase: 'Context', label: 'annotate', schema: CONTEXT_SCHEMA,
      })
    : Promise.resolve({ annotations: [], synthesized: [] }),
  synthP,
])

// Merge annotations onto survivors by (file, line, rule_id).
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

// Synthesized findings (claude-md/adr) skip verify — empty verifications, tagged reviewer.
const synthesized = (synth?.synthesized || []).map((f) => ({
  ...f, reviewer: 'context-checker', verifications: [],
}))

return { findings: [...survivors, ...synthesized] }
