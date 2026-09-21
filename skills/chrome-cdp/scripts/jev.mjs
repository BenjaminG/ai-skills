// jev.mjs — typed judgments via TypeSafe's Jev (System One) for cdp.mjs.
// Two judgments, measured in evals/jev-chrome-cdp before shipping:
//   pickElement  Choice over code-harvested candidates -> a selector to click
//   verifyState  Noul: does the a11y tree show the claimed state
// Design rule: the model never invents values. Options ARE the candidates,
// so the returned selector is byte-for-byte one the page actually has.
// Uncertainty escalates (exit 3 in cdp.mjs) — the caller decides, never us.

const API_URL = 'https://api.typesafe.ai/v1/systemone';
const MODEL = 'jev-latest';
const MIN_CONF = parseFloat(process.env.CDP_JEV_MIN_CONF || '0.6');
// Bounds the per-call cost. Login pages ~1.2k chars; dense lists hit the cap
// and lose deep-tree context — the candidates still carry role+name.
const MAX_TREE_CHARS = 8000;
const MAX_CANDIDATES = 255;

export class JevError extends Error {}

async function callJev(state, questions) {
  const key = process.env.TYPESAFE_API_KEY;
  if (!key) throw new JevError('TYPESAFE_API_KEY not set (https://console.typesafe.ai/)');
  let resp;
  try {
    resp = await fetch(API_URL, {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: MODEL, state, questions }),
      signal: AbortSignal.timeout(30000),
    });
  } catch (e) {
    throw new JevError(`Jev unreachable: ${e.message}`);
  }
  if (!resp.ok) {
    const body = await resp.text().catch(() => '');
    throw new JevError(`Jev http ${resp.status}: ${body.slice(0, 200)}`);
  }
  return resp.json();
}

// --- pick -----------------------------------------------------------------

const PICK_INSTRUCTIONS = `A browser automation harness is executing a step on the page whose accessibility tree is in \`tree\`. The next intended action is described in \`intent\`. \`candidates\` lists the interactive elements currently on the page by selector, role, and accessible name. Which single candidate is the element the intended action targets? The answer must be one candidate's \`ref\`, or \`none\` if no candidate matches the intent.`;

const PICK_NONE = `None of the candidates is the element the intended action targets — the page does not show it (wrong page, not loaded yet, below the fold, or inside an iframe not represented here).`;

export async function pickElement({ intent, candidates, tree, page }) {
  const cands = candidates.slice(0, MAX_CANDIDATES);
  const criteria = {};
  cands.forEach((c, i) => { criteria[String(i)] = `${c.role}: ${c.name}`; });
  criteria.none = PICK_NONE;
  const state = {
    page: page || null,
    tree: (tree || '').slice(0, MAX_TREE_CHARS),
    intent,
    candidates: cands.map((c, i) => ({ ref: String(i), role: c.role, name: c.name })),
  };
  const resp = await callJev(state, {
    pick: {
      type: 'choice',
      instructions: PICK_INSTRUCTIONS,
      criteria,
    },
  });
  const a = resp.answers?.pick || {};
  const ref = a.choice;
  const conf = a.confidence ?? 0;
  if (ref === 'none') {
    return { decision: 'escalate', reason: 'no candidate matched the intent', confidence: conf };
  }
  const idx = parseInt(ref, 10);
  const hit = Number.isInteger(idx) ? cands[idx] : null;
  if (!hit) {
    return { decision: 'escalate', reason: `model returned unknown option ${JSON.stringify(ref)}`, confidence: conf };
  }
  if (conf < MIN_CONF) {
    return { decision: 'escalate', reason: `confidence ${conf.toFixed(2)} < ${MIN_CONF}`, confidence: conf, selector: hit.selector };
  }
  return { decision: 'pick', selector: hit.selector, role: hit.role, name: hit.name, confidence: conf };
}

// --- verify ---------------------------------------------------------------

const VERIFY_INSTRUCTIONS = `Does the accessibility tree in \`tree\` show the page state described in \`claim\`?`;
const VERIFY_CRITERIA = {
  true: `The elements the claim names are present in \`tree\` with the described roles or names, in a state consistent with the claim.`,
  false: `The claim names elements absent from \`tree\`, present with different roles or names, or the tree shows a state that contradicts the claim.`,
};

// The noul is a probability, not a verdict. We report it and apply a
// conservative band: high noul = pass, low = fail, middle = escalate.
// Band edges are env-tunable until measured on a real claims corpus.
const PASS_AT = parseFloat(process.env.CDP_JEV_PASS_AT || '0.8');
const FAIL_AT = parseFloat(process.env.CDP_JEV_FAIL_AT || '0.2');

export async function verifyState({ claim, tree, page }) {
  const state = { page: page || null, tree: (tree || '').slice(0, MAX_TREE_CHARS), claim };
  const resp = await callJev(state, {
    state_matches: {
      type: 'noul',
      instructions: VERIFY_INSTRUCTIONS,
      criteria: VERIFY_CRITERIA,
    },
  });
  const noul = resp.answers?.state_matches?.noul;
  if (typeof noul !== 'number') {
    throw new JevError(`Jev returned no noul: ${JSON.stringify(resp.answers).slice(0, 200)}`);
  }
  if (noul >= PASS_AT) return { decision: 'pass', noul };
  if (noul <= FAIL_AT) return { decision: 'fail', noul };
  return { decision: 'escalate', noul };
}
